"""The drained session handoff: the trigger's stages, the header, and the relay's refusals."""

import datetime
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import support
import handoff_header
import handoff_trigger

RELAY = support.PLUGIN / "hooks" / "handoff_relay.py"
HEADER = support.PLUGIN / "hooks" / "handoff_header.py"
VERSION = json.loads((support.PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
WINDOWS = sys.platform == "win32"
HAS_GIT = shutil.which("git") is not None


def remove_tree(path: Path) -> None:
    """rmtree that also removes git's read-only object files, which Windows refuses to unlink."""
    def writable(function, target, _error) -> None:
        os.chmod(target, stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onerror=writable)


def isolated_home(home: Path) -> dict[str, str]:
    """The environment of a child that must not see this session: Path.home() reads HOME on
    POSIX and USERPROFILE on Windows, and no CLAUDE_ variable of the session running the tests
    may leak into a relay."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("CLAUDE_")}
    env.update(HOME=str(home), USERPROFILE=str(home))
    return env


def handoff(folder: Path, feature: str = "", en_vol: str = "[]", sauvetage: str = "[]") -> Path:
    path = folder / "2026-10-20-r1.md"
    path.write_text(
        "---\n"
        "projet: demo\n"
        f"feature: {feature}\n"
        "passage_depart: 1792494562\n"
        "jetons_agents: 0\n"
        f"en_vol: {en_vol}\n"
        "file_revue: []\n"
        f"sauvetage: {sauvetage}\n"
        "successeur:\n"
        "hooks_version: forge@test\n"
        "seuil:\n"
        "contexte_passation: 151000\n"
        "---\n\n# Reprise\n",
        encoding="utf-8",
    )
    return path


class Header(unittest.TestCase):
    def test_a_header_without_a_required_key_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = handoff(Path(root))
            path.write_text(path.read_text(encoding="utf-8").replace("seuil:\n", ""), encoding="utf-8")
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(handoff_header.main(["handoff_header.py", "check", str(path)]), 2)
            self.assertIn("seuil", out.getvalue())

    def test_check_counts_the_lists(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = handoff(Path(root), feature="F-0001", sauvetage="\n  - coder #12 agent-x")
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(handoff_header.main(["handoff_header.py", "check", str(path)]), 0)
            self.assertEqual(out.getvalue().strip(), "en_vol=0 sauvetage=1 feature=1")

    def test_only_the_recorded_successor_may_act(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = handoff(Path(root))
            self.assertTrue(handoff_header.successor_ok(path, "abcdef12-3456", wait=0)[0])
            handoff_header.set_successor(path, "abcdef12", "400000")
            values = handoff_header.check(path)
            self.assertEqual((values["successeur"], values["seuil"]), (["abcdef12"], ["400000"]))
            self.assertTrue(handoff_header.successor_ok(path, "abcdef12-3456", wait=0)[0])
            self.assertFalse(handoff_header.successor_ok(path, "99999999-0000", wait=0)[0])

    def test_the_lock_is_read_with_or_without_its_start_time(self) -> None:
        linux = handoff_header.LOCK.search("claude agent agent-a1b2 (pid 4242 start 987654)")
        windows = handoff_header.LOCK.search("claude agent agent-a1b2 (pid 4242)")
        session = handoff_header.LOCK.search("claude session my worktree (pid 7 start 12)")
        self.assertEqual(linux.groups() if linux else None, ("4242", "987654"))
        self.assertEqual(windows.groups() if windows else None, ("4242", None))
        self.assertEqual(session.groups() if session else None, ("7", "12"))


class Processes(unittest.TestCase):
    def test_this_process_is_alive_and_has_a_start_time(self) -> None:
        self.assertTrue(handoff_header.process_alive(os.getpid()))
        self.assertNotEqual(handoff_header.process_start(os.getpid()), "")

    def test_a_finished_process_is_gone(self) -> None:
        gone = subprocess.Popen([sys.executable, "-c", "pass"])
        gone.wait()
        self.assertFalse(handoff_header.process_alive(gone.pid))
        self.assertEqual(handoff_header.process_start(gone.pid), "")

    def test_a_child_names_this_process_among_its_ancestors(self) -> None:
        code = f"import sys; sys.path.insert(0, {str(support.PLUGIN / 'hooks')!r}); import os, handoff_header; " \
               "print(sorted(handoff_header.ancestors(os.getpid())))"
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        self.assertIn(os.getpid(), json.loads(result.stdout))
        self.assertEqual(handoff_header.parent_pid(os.getpid()), os.getppid())


class Trigger(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(remove_tree, self.home)
        self.project = self.home / "demo"
        self.project.mkdir()
        self.transcript = self.home / "session.jsonl"
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("CLAUDE_SESSION_TOKEN_LIMIT", "CLAUDE_HANDOFF_DRAIN_MINUTES", "CLAUDE_HANDOFF_DIR"):
            os.environ.pop(name, None)
        os.environ.update(HOME=str(self.home), USERPROFILE=str(self.home), CLAUDE_PROJECT_DIR=str(self.project))

    def notice(self, tokens: int, event: str = "PostToolUse", **extra: object) -> str | None:
        line = {"type": "assistant", "message": {"usage": {"input_tokens": tokens}}}
        self.transcript.write_text(json.dumps(line) + "\n", encoding="utf-8")
        payload = {"transcript_path": str(self.transcript), "session_id": "s1", "hook_event_name": event, **extra}
        return handoff_trigger.notice(payload)

    def test_below_the_limit_nothing_is_said(self) -> None:
        self.assertIsNone(self.notice(149_999))

    def test_the_limit_opens_the_drain_once(self) -> None:
        message = self.notice(150_000)
        self.assertIsNotNone(message)
        self.assertIn("launch nothing new", message or "")
        self.assertIn(f"forge@{VERSION}", message or "")
        self.assertIn("185k tokens or 45 minutes", message or "")
        self.assertIn(f'uv run --no-project --quiet python "{RELAY}"', message or "")
        self.assertIn(str(self.home / ".claude" / "hooks" / "state" / "handoffs" / "demo"), message or "")
        self.assertIn("en_vol", message or "")
        self.assertIsNone(self.notice(151_000))
        self.assertIn("stage drain", self.notice(151_000, "UserPromptSubmit") or "")

    def test_the_handoffs_can_live_outside_any_claude_folder(self) -> None:
        os.environ["FORGE_TEST_ROOT"] = str(self.home)
        os.environ["CLAUDE_HANDOFF_DIR"] = os.path.join("$FORGE_TEST_ROOT", "passations")
        message = self.notice(150_000) or ""
        self.assertIn(str(self.home / "passations" / "demo" / f"{datetime.date.today().isoformat()}-r1.md"), message)
        self.assertNotIn(str(self.home / ".claude" / "hooks" / "state" / "handoffs"), message)
        self.assertTrue((self.home / ".claude" / "hooks" / "state" / "s1.handoff").exists())

    @unittest.skipUnless(HAS_GIT, "a worktree is made by git")
    def test_a_session_in_a_worktree_files_its_handoff_under_the_project(self) -> None:
        def git(*args: str, cwd: Path) -> None:
            subprocess.run(
                ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                env=isolated_home(self.home), check=True, capture_output=True,
            )

        git("init", "-q", cwd=self.project)
        git("commit", "-q", "--allow-empty", "-m", "init", cwd=self.project)
        worktree = self.project / ".claude" / "worktrees" / "feature-x"
        git("worktree", "add", "-q", "-b", "feature-x", str(worktree), cwd=self.project)
        os.environ["CLAUDE_PROJECT_DIR"] = str(worktree)
        message = self.notice(150_000) or ""
        day = datetime.date.today().isoformat()
        self.assertIn(str(self.home / ".claude" / "hooks" / "state" / "handoffs" / "demo" / f"{day}-r1.md"), message)

    def test_a_git_file_without_a_common_dir_keeps_the_folder_name(self) -> None:
        # A submodule's `.git` is a file too, but names no common directory: it is its own project.
        (self.project / ".git").write_text("gitdir: ../elsewhere/modules/demo\n", encoding="utf-8")
        self.assertEqual(handoff_trigger.project_name(self.project), "demo")

    def test_the_hard_cap_comes_with_the_tokens_or_the_clock(self) -> None:
        self.notice(150_000)
        self.assertIn("Hard cap reached", self.notice(185_000) or "")
        self.assertIsNone(self.notice(190_000))
        self.assertIn("stage hard", self.notice(190_000, "UserPromptSubmit") or "")

        marker = self.home / ".claude" / "hooks" / "state" / "s1.handoff"
        (self.home / ".claude" / "hooks" / "state" / "s1.hard").unlink()
        old = time.time() - 46 * 60
        os.utime(marker, (old, old))
        self.assertIn("46 minutes", self.notice(160_000) or "")

    def test_an_orchestration_relay_drains_at_its_own_threshold(self) -> None:
        os.environ["CLAUDE_SESSION_TOKEN_LIMIT"] = "400000"
        self.assertIsNone(self.notice(399_000))
        self.assertIn("435k tokens", self.notice(400_000) or "")

    def test_a_subagent_is_never_told(self) -> None:
        self.assertIsNone(self.notice(200_000, agent_id="a1"))

    def test_a_copy_outside_the_plugin_keeps_it_silent(self) -> None:
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        own = f'python3 "{handoff_trigger.HOOKS}/handoff_trigger.py"'
        settings.write_text(json.dumps({"hooks": {"PostToolUse": [{"hooks": [{"command": own}]}]}}), encoding="utf-8")
        self.assertIsNotNone(self.notice(150_000))
        copy = f"python3 {self.home}/.claude/hooks/handoff_trigger.py"
        settings.write_text(json.dumps({"hooks": {"PostToolUse": [{"hooks": [{"command": copy}]}]}}), encoding="utf-8")
        (self.home / ".claude" / "hooks" / "state" / "s1.handoff").unlink()
        self.assertIsNone(self.notice(150_000))

    def test_the_user_skill_is_cited_only_when_it_exists(self) -> None:
        self.assertNotIn("SKILL.md", self.notice(150_000) or "")
        skill = self.home / ".claude" / "skills" / "handoff" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: handoff\n---\n", encoding="utf-8")
        (self.home / ".claude" / "hooks" / "state" / "s1.handoff").unlink()
        self.assertIn(str(skill), self.notice(150_000) or "")

    def test_the_hook_prints_its_notice_for_claude_code(self) -> None:
        self.transcript.write_text(
            json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": 150_000}}}) + "\n",
            encoding="utf-8",
        )
        event = {"transcript_path": str(self.transcript), "session_id": "s2", "hook_event_name": "UserPromptSubmit"}
        result = subprocess.run(
            [sys.executable, str(support.PLUGIN / "hooks" / "handoff_trigger.py")],
            input=json.dumps(event), capture_output=True, text=True,
            env={**isolated_home(self.home), "CLAUDE_PROJECT_DIR": str(self.project)}, check=False,
        )
        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "UserPromptSubmit")
        self.assertIn("launch nothing new", output["additionalContext"])


@unittest.skipUnless(HAS_GIT, "the relay lists agent worktrees with git")
class Relay(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(remove_tree, self.home)
        self.repo = self.home / "demo"
        self.repo.mkdir()
        git = ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        self.git = git
        self.state = self.home / ".claude" / "hooks" / "state"
        name = re.sub(r"[\\/:]", "-", str(self.repo))
        self.counter = self.state / f"relay-{name}-{datetime.date.today().isoformat()}.count"
        # A stand-in for `claude`: a relay test never starts or stops a real session.
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        self.log = self.home / "claude.log"
        fake = bin_dir / "fake_claude.py"
        fake.write_text(
            "import os, sys\n"
            f"with open({str(self.log)!r}, 'a', encoding='utf-8') as log:\n"
            "    log.write(os.environ.get('CLAUDE_SESSION_TOKEN_LIMIT', '') + ' ' + ' '.join(sys.argv[1:]) + '\\n')\n"
            "sys.stdout.reconfigure(encoding='utf-8')\n"
            "print('relais backgrounded · abcdef12 · claude attach abcdef12')\n",
            encoding="utf-8",
        )
        if WINDOWS:
            (bin_dir / "claude.cmd").write_text(f'@"{sys.executable}" "{fake}" %*\r\n', encoding="utf-8")
        else:
            launcher = bin_dir / "claude"
            launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" "$@"\n', encoding="utf-8")
            launcher.chmod(0o755)
        self.env = {
            **isolated_home(self.home),
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "CLAUDE_HANDOFF_RELAY_MAX": "3",
            "CLAUDE_HANDOFF_CLOSE_DELAY": "0",
            "CLAUDE_HANDOFF_CLOSE_DRY_RUN": "1",
        }

    def relay(self, path: Path, *flags: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RELAY), *flags, str(path)],
            cwd=self.repo, capture_output=True, encoding="utf-8", env={**self.env, **env}, check=False,
        )

    def live_agent(self) -> int:
        """An agent worktree locked the way Claude Code locks it on this platform, held by a running process."""
        holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)
        self.holder = holder
        worktree = self.repo / ".claude" / "worktrees" / "agent-x"
        subprocess.run([*self.git, "worktree", "add", "-q", "-b", "agent-x", str(worktree)], check=True)
        if WINDOWS:
            reason = f"claude agent x (pid {holder.pid})"
        else:
            reason = f"claude agent x (pid {holder.pid} start {handoff_header.process_start(holder.pid)})"
        subprocess.run([*self.git, "worktree", "lock", "--reason", reason, str(worktree)], check=True)
        return holder.pid

    def test_a_dead_holder_frees_its_worktree(self) -> None:
        pid = self.live_agent()
        # Reaped, not only killed: on Linux an unreaped child stays a zombie in /proc with its
        # start time, as alive as before for the lock check. A real holder is reaped by its parent.
        self.holder.kill()
        self.holder.wait()
        result = self.relay(handoff(self.home), CLAUDE_PID=str(pid))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_dry_run_shows_how_the_session_closes(self) -> None:
        result = self.relay(handoff(self.home), CLAUDE_PID="4242", CLAUDE_HANDOFF_CLOSE_DELAY="45")
        self.assertEqual(result.returncode, 0, result.stderr)
        closer = "--exit-console 4242" if WINDOWS else "dry run, would run in 45s: kill -TERM 4242"
        self.assertIn(closer, result.stdout)
        self.assertNotIn("taskkill", result.stdout)
        child = {"CLAUDE_PID": "4242", "CLAUDE_HANDOFF_CLOSE_DELAY": "45",
                 "CLAUDE_CODE_CHILD_SESSION": "1", "CLAUDE_CODE_SESSION_ID": "0123abcd-ffff"}
        background = self.relay(handoff(self.home), **child)
        self.assertIn("stop 0123abcd", background.stdout)
        self.assertIn("rm 0123abcd", background.stdout)
        # Interactive sessions carry CLAUDE_CODE_CHILD_SESSION too: the registry tells them apart.
        registry = self.home / ".claude" / "sessions" / "4242.json"
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({"pid": 4242, "kind": "interactive"}), encoding="utf-8")
        interactive = self.relay(handoff(self.home), **child)
        self.assertNotIn("rm 0123abcd", interactive.stdout)
        self.assertIn(closer, interactive.stdout)

    def test_zero_or_false_leaves_the_dry_run_off(self) -> None:
        for value in ("0", "false", "off"):
            with self.subTest(value=value):
                result = self.relay(handoff(self.home), CLAUDE_HANDOFF_CLOSE_DRY_RUN=value)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("dry run", result.stdout)
        self.assertEqual(self.counter.read_text(encoding="utf-8").strip(), "3")

    def test_an_invalid_header_is_refused(self) -> None:
        path = handoff(self.home)
        path.write_text("no front matter\n", encoding="utf-8")
        result = self.relay(path)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.counter.exists())

    def test_a_live_agent_of_this_session_holds_the_relay(self) -> None:
        pid = self.live_agent()
        result = self.relay(handoff(self.home), CLAUDE_PID=str(pid))
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertIn("agent-x", result.stderr)
        self.assertEqual(self.relay(handoff(self.home), CLAUDE_PID=str(os.getpid())).returncode, 0)

    def test_agents_listed_in_flight_hold_the_relay(self) -> None:
        result = self.relay(handoff(self.home, en_vol="\n  - coder #12"))
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertIn("en_vol", result.stderr)

    def test_force_needs_agents_listed_for_a_rescue(self) -> None:
        result = self.relay(handoff(self.home, en_vol="[coder #12]"), "--force")
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertIn("sauvetage", result.stderr)
        rescued = handoff(self.home, en_vol="[coder #12]", sauvetage="[coder #12 agent-x]")
        self.assertEqual(self.relay(rescued, "--force").returncode, 0)

    def test_the_daily_cap_stops_the_chain_without_moving_the_counter(self) -> None:
        self.state.mkdir(parents=True)
        self.counter.write_text("3\n", encoding="utf-8")
        result = self.relay(handoff(self.home), CLAUDE_HANDOFF_CLOSE_DRY_RUN="")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(self.counter.read_text(encoding="utf-8").strip(), "3")
        self.assertFalse(self.log.exists())

    def test_a_dry_run_moves_nothing(self) -> None:
        path = handoff(self.home, feature="F-0001")
        before = path.read_text(encoding="utf-8")
        result = self.relay(path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CLAUDE_SESSION_TOKEN_LIMIT=400000 claude --bg", result.stdout)
        self.assertEqual(path.read_text(encoding="utf-8"), before)
        self.assertFalse(self.counter.exists())
        self.assertFalse(self.log.exists())

    def test_a_feature_gives_the_successor_400k_and_none_gives_150k(self) -> None:
        prose = "aucune (demande ponctuelle hors forge)"
        for feature, threshold in (("F-0001", "400000"), ("", "150000"), (prose, "150000")):
            with self.subTest(feature=feature):
                path = handoff(self.home, feature=feature)
                result = self.relay(path, CLAUDE_HANDOFF_CLOSE_DRY_RUN="", CLAUDE_SESSION_TOKEN_LIMIT="400000")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(self.log.read_text(encoding="utf-8").splitlines()[-1].startswith(f"{threshold} --bg"))
                values = handoff_header.check(path)
                self.assertEqual((values["successeur"], values["seuil"]), (["abcdef12"], [threshold]))
                self.assertIn("claude attach abcdef12", result.stdout)
        self.assertEqual(self.counter.read_text(encoding="utf-8").strip(), "3")


@unittest.skipUnless(WINDOWS, "the console of an interactive session is a Windows console")
class ExitConsole(unittest.TestCase):
    """--exit-console against a stand-in session in its own hidden console."""

    def session(self, code: str) -> subprocess.Popen:
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0  # SW_HIDE
        process = subprocess.Popen(
            [sys.executable, "-c", code], creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup,
        )
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        time.sleep(1)  # let it reach its read
        return process

    def exit_console(self, pid: int) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(RELAY), "--exit-console", str(pid)],
            creationflags=subprocess.DETACHED_PROCESS, capture_output=True, text=True, timeout=60, check=False,
        )

    def test_the_session_ends_on_the_exit_typed_in_its_console(self) -> None:
        session = self.session("import sys; sys.exit(0 if sys.stdin.readline().strip() == '/exit' else 3)")
        result = self.exit_console(session.pid)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(session.wait(timeout=5), 0)

    def test_a_session_deaf_to_exit_is_killed(self) -> None:
        session = self.session("import time; time.sleep(120)")
        result = self.exit_console(session.pid)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIsNotNone(session.wait(timeout=5))


@unittest.skipUnless(WINDOWS, "a job that forbids breaking away is a Windows job object")
class CloseInAJob(unittest.TestCase):
    """The --close copy that spawn() could only start inside the session's job."""

    def test_the_closing_plan_runs_in_a_job_that_forbids_breaking_away(self) -> None:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(remove_tree, folder)
        marker = folder / "closed"
        touch = f"open({str(marker)!r}, 'w').close()"
        # The child puts itself in a fresh job, whose limits do not include JOB_OBJECT_LIMIT_BREAKAWAY_OK.
        code = (
            "import ctypes, sys\n"
            f"sys.path.insert(0, {str(RELAY.parent)!r})\n"
            "import handoff_relay\n"
            "kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)\n"
            "kernel32.CreateJobObjectW.restype = ctypes.c_void_p\n"
            "kernel32.GetCurrentProcess.restype = ctypes.c_void_p\n"
            "kernel32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)\n"
            "job = kernel32.CreateJobObjectW(None, None)\n"
            "if not job or not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):\n"
            "    sys.exit(f'no job: {ctypes.get_last_error()}')\n"
            f"step = [sys.executable, '-c', {touch!r}]\n"
            "handoff_relay.close(0, [[step]])\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], env=isolated_home(folder), capture_output=True, text=True, timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(marker.exists(), "a command of the closing plan did not run inside the job")


if __name__ == "__main__":
    unittest.main()
