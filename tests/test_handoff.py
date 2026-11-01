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

import handoff_header
import handoff_trigger
import support

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

    def test_the_successor_is_written_with_the_session_that_hands_over(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = handoff(Path(root))
            handoff_header.set_successor(path, "abcdef12", "150000", "0801df0e-3c3b")
            self.assertEqual(handoff_header.check(path)["auteur"], ["0801df0e-3c3b"])
            # Written again, the header keeps one author.
            handoff_header.set_successor(path, "abcdef12", "150000", "0801df0e-3c3b")
            self.assertEqual(path.read_text(encoding="utf-8").count("auteur:"), 1)
            # From the command line, the author is the calling session.
            with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "77777777-8888"}):
                self.assertEqual(handoff_header.main(["handoff_header.py", "set-successor", str(path), "12345678"]), 0)
            values = handoff_header.check(path)
            self.assertEqual((values["successeur"], values["auteur"]), (["12345678"], ["77777777-8888"]))

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


class ProcessGroupKill(unittest.TestCase):
    """#26: kill tests the return of TerminateJobObject and falls back to process.kill();
    the wait that follows is bounded, never blocking the session."""

    def test_a_failed_terminate_falls_back_to_process_kill(self) -> None:
        """#26: TerminateJobObject returns 0 on failure without raising; kill must
        test that return and fall back to process.kill()."""
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(sleeper.kill)
        self.addCleanup(sleeper.wait)
        group = handoff_header.ProcessGroup(sleeper)
        with (
            mock.patch.object(handoff_header, "WINDOWS", True),
            mock.patch.object(handoff_header, "LINUX", False),
            mock.patch.object(handoff_header, "_win32") as win32,
        ):
            kernel32 = mock.Mock()
            kernel32.TerminateJobObject.return_value = 0
            win32.return_value = (mock.Mock(), mock.Mock(), kernel32)
            group.job = mock.sentinel.job
            group.kill()
            kernel32.TerminateJobObject.assert_called_once_with(mock.sentinel.job, 1)
        self.assertIsNotNone(sleeper.poll(), "the process was not killed by the fallback")

    def test_wait_is_bounded_and_does_not_block(self) -> None:
        """#26: the wait after kill is bounded; a process that does not die in time
        does not block the session."""
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(sleeper.kill)
        self.addCleanup(sleeper.wait)
        group = handoff_header.ProcessGroup(sleeper)
        with (
            mock.patch.object(handoff_header, "WINDOWS", False),
            mock.patch.object(handoff_header, "LINUX", True),
            mock.patch.object(handoff_header.os, "killpg", side_effect=OSError("no such group")),
            mock.patch.object(handoff_header, "KILL_WAIT_SECONDS", 0.1),
        ):
            start = time.monotonic()
            group.kill()
            elapsed = time.monotonic() - start
        self.assertLess(elapsed, 5, "kill blocked waiting for a process that would not die")
        self.assertIsNotNone(sleeper.poll(), "the process was not killed by the fallback")


class Sessions(unittest.TestCase):
    """`handoff_header.py sessions <repo>` on a stand-in registry under an isolated HOME
    (ikoro-labs/forge#4, critère 1)."""

    def setUp(self) -> None:
        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(remove_tree, self.home)
        self.repo = self.home / "demo"
        (self.repo / ".git").mkdir(parents=True)
        self.registry = self.home / ".claude" / "sessions"
        self.registry.mkdir(parents=True)
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in [key for key in os.environ if key.startswith("CLAUDE_")]:
            del os.environ[name]
        os.environ.update(HOME=str(self.home), USERPROFILE=str(self.home))

    def sleeper(self) -> int:
        """A running process that is neither this one nor one of its ancestors."""
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return process.pid

    def register(self, pid: int, cwd: Path, **fields: object) -> None:
        entry = {
            "pid": pid, "sessionId": "0801df0e-3c3b", "cwd": str(cwd), "kind": "bg", "name": "relais-1-demo",
            "status": "busy", "procStart": handoff_header.process_start(pid), **fields,
        }
        (self.registry / f"{pid}.json").write_text(json.dumps(entry), encoding="utf-8")

    def sessions(self, repo: Path | None = None) -> tuple[int, list[str]]:
        with redirect_stdout(io.StringIO()) as out:
            code = handoff_header.main(["handoff_header.py", "sessions", str(repo or self.repo)])
        return code, out.getvalue().splitlines()

    def test_a_live_session_of_the_repository_is_listed_with_code_6(self) -> None:
        pid = self.sleeper()
        self.register(pid, self.repo)
        self.assertEqual(self.sessions(), (6, [f"{pid} bg relais-1-demo busy {self.repo}"]))

    def test_no_registry_and_no_other_session_exit_0(self) -> None:
        self.assertEqual(self.sessions(), (0, []))
        remove_tree(self.registry)
        self.assertEqual(self.sessions(), (0, []))

    def test_a_dead_pid_is_ignored(self) -> None:
        gone = subprocess.Popen([sys.executable, "-c", "pass"])
        gone.wait()
        self.register(gone.pid, self.repo, procStart="1")
        self.assertEqual(self.sessions(), (0, []))

    @unittest.skipUnless(HAS_GIT, "a worktree is made by git")
    def test_a_session_in_a_worktree_of_the_repository_is_listed(self) -> None:
        git = ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t"]
        remove_tree(self.repo / ".git")
        subprocess.run([*git, "init", "-q"], check=True, env=isolated_home(self.home))
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True, env=isolated_home(self.home))
        inside = self.repo / ".claude" / "worktrees" / "agent-x"
        beside = self.home / "demo-ailleurs"
        for path, branch in ((inside, "agent-x"), (beside, "ailleurs")):
            subprocess.run([*git, "worktree", "add", "-q", "-b", branch, str(path)], check=True, env=isolated_home(self.home))
        first, second = self.sleeper(), self.sleeper()
        self.register(first, inside)
        self.register(second, beside, kind="interactive", name="revue", status="idle")
        code, lines = self.sessions(beside)
        self.assertEqual(code, 6)
        self.assertEqual(
            sorted(lines), sorted([f"{first} bg relais-1-demo busy {inside}", f"{second} interactive revue idle {beside}"]),
        )

    def test_a_session_of_another_repository_is_ignored(self) -> None:
        other = self.home / "autre"
        (other / ".git").mkdir(parents=True)
        self.register(self.sleeper(), other)
        self.register(self.sleeper(), self.home / "hors-depot")
        self.assertEqual(self.sessions(), (0, []))

    @unittest.skipUnless(sys.platform.startswith("linux"), "procStart is compared to the start time read in /proc")
    def test_a_reused_pid_whose_start_differs_is_ignored(self) -> None:
        self.register(self.sleeper(), self.repo, procStart="1")
        self.assertEqual(self.sessions(), (0, []))

    def test_an_unreadable_entry_counts_as_live(self) -> None:
        (self.registry / "4242.json").write_text("{pas du json", encoding="utf-8")
        (self.registry / "4243.json").write_text(json.dumps({"pid": 4243, "kind": "bg"}), encoding="utf-8")
        code, lines = self.sessions()
        self.assertEqual(code, 6)
        self.assertEqual(len(lines), 2, lines)
        for line, name in zip(sorted(lines), ("4242.json", "4243.json")):
            self.assertTrue(line.startswith(name[:4] + " "), line)
            self.assertIn("unreadable", line)
            self.assertIn(name, line)

    def test_the_calling_session_and_its_ancestors_are_excluded(self) -> None:
        caller = self.sleeper()
        self.register(caller, self.repo)
        self.register(os.getpid(), self.repo, kind="interactive")
        (self.registry / f"{caller}.json").write_text(json.dumps({"pid": caller, "kind": "bg"}), encoding="utf-8")
        os.environ["CLAUDE_PID"] = str(caller)
        self.assertEqual(self.sessions(), (0, []))
        self.register(caller, self.repo)
        self.assertEqual(self.sessions(), (0, []))
        del os.environ["CLAUDE_PID"]
        self.assertEqual(self.sessions(), (6, [f"{caller} bg relais-1-demo busy {self.repo}"]))

    def test_a_name_with_spaces_keeps_five_columns(self) -> None:
        pid = self.sleeper()
        self.register(pid, self.repo, name="ma revue du soir")
        self.assertEqual(self.sessions(), (6, [f"{pid} bg ma_revue_du_soir busy {self.repo}"]))

    def test_self_prints_the_kind_and_the_id_of_the_calling_session(self) -> None:
        """ikoro-labs/forge#4, MINOR 1 of #36: precedence asks a session whether it is the
        interactive one, which Claude Code records in its registry entry."""
        def self_line() -> tuple[int, str]:
            with redirect_stdout(io.StringIO()) as out:
                code = handoff_header.main(["handoff_header.py", "self"])
            return code, out.getvalue().strip()

        self.assertEqual(self_line(), (0, "? ?"))
        caller = self.sleeper()
        os.environ.update(CLAUDE_PID=str(caller), CLAUDE_CODE_SESSION_ID="abcdef12-3456")
        self.assertEqual(self_line(), (0, "? abcdef12-3456"))
        self.register(caller, self.repo, kind="interactive")
        self.assertEqual(self_line(), (0, "interactive abcdef12-3456"))
        self.register(caller, self.repo, kind="bg")
        self.assertEqual(self_line(), (0, "bg abcdef12-3456"))

    def test_a_background_session_that_yielded_no_longer_stops_the_interactive_one(self) -> None:
        """ikoro-labs/forge#4, MINOR 1 of #36: once the background session has written its
        handoff and named the interactive session with `set-successor`, the interactive session
        is its successor in effect and `sessions` lets it act."""
        background = self.sleeper()
        self.register(background, self.repo, sessionId="0801df0e-3c3b-48e6-a43f-375ac6d170e3", status="idle")
        folder = self.home / ".claude" / "hooks" / "state" / "handoffs" / "demo"
        folder.mkdir(parents=True)
        path = handoff(folder)
        interactive = "abcdef12-3456-7890-abcd-ef1234567890"
        os.environ["CLAUDE_CODE_SESSION_ID"] = interactive
        self.assertEqual(self.sessions(), (6, [f"{background} bg relais-1-demo idle {self.repo}"]))
        # The background session runs the command `yield` printed, with its own id in its environment.
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "0801df0e-3c3b-48e6-a43f-375ac6d170e3"}):
            self.assertEqual(handoff_header.main(["handoff_header.py", "set-successor", str(path), interactive]), 0)
        self.assertEqual(self.sessions(), (0, []))
        self.assertTrue(handoff_header.successor_ok(path, interactive, wait=0)[0])

    def handed_over(self, successor: str, author: str, folder: Path | None = None) -> Path:
        """A handoff of the project whose header names its successor and its author."""
        folder = folder or self.home / ".claude" / "hooks" / "state" / "handoffs" / "demo"
        folder.mkdir(parents=True, exist_ok=True)
        path = handoff(folder)
        handoff_header.set_successor(path, successor, "150000", author)
        return path

    def test_the_predecessor_of_the_calling_session_is_not_counted(self) -> None:
        """ikoro-labs/forge#4, MINOR 2 of #36: a session that handed over to the caller, alive
        during its closing delay, does not make its successor stop."""
        predecessor = self.sleeper()
        self.register(predecessor, self.repo, sessionId="0801df0e-3c3b-48e6-a43f-375ac6d170e3")
        listed = (6, [f"{predecessor} bg relais-1-demo busy {self.repo}"])
        self.handed_over("abcdef12", "0801df0e-3c3b-48e6-a43f-375ac6d170e3")
        self.assertEqual(self.sessions(), listed)
        os.environ["CLAUDE_CODE_SESSION_ID"] = "abcdef12-3456-7890-abcd-ef1234567890"
        self.assertEqual(self.sessions(), (0, []))
        # Another session of the repository still counts.
        other = self.sleeper()
        self.register(other, self.repo, sessionId="11111111-2222", kind="interactive", name="revue")
        self.assertEqual(self.sessions(), (6, [f"{other} interactive revue busy {self.repo}"]))

    def test_a_handoff_to_another_session_or_by_another_author_excludes_nothing(self) -> None:
        predecessor = self.sleeper()
        self.register(predecessor, self.repo, sessionId="0801df0e-3c3b-48e6-a43f-375ac6d170e3")
        listed = (6, [f"{predecessor} bg relais-1-demo busy {self.repo}"])
        os.environ["CLAUDE_CODE_SESSION_ID"] = "abcdef12-3456-7890-abcd-ef1234567890"
        self.handed_over("99999999", "0801df0e-3c3b-48e6-a43f-375ac6d170e3")
        self.assertEqual(self.sessions(), listed)
        remove_tree(self.home / ".claude" / "hooks" / "state" / "handoffs")
        self.handed_over("abcdef12", "22222222-3333-4444-5555-666666666666")
        self.assertEqual(self.sessions(), listed)
        # An older handoff, without `auteur`, names no predecessor.
        remove_tree(self.home / ".claude" / "hooks" / "state" / "handoffs")
        self.handed_over("abcdef12", "")
        self.assertEqual(self.sessions(), listed)
        # A handoff of another project neither.
        remove_tree(self.home / ".claude" / "hooks" / "state" / "handoffs")
        self.handed_over(
            "abcdef12", "0801df0e-3c3b-48e6-a43f-375ac6d170e3",
            self.home / ".claude" / "hooks" / "state" / "handoffs" / "autre",
        )
        self.assertEqual(self.sessions(), listed)

    def test_the_handoffs_are_read_where_claude_handoff_dir_puts_them(self) -> None:
        predecessor = self.sleeper()
        self.register(predecessor, self.repo, sessionId="0801df0e-3c3b-48e6-a43f-375ac6d170e3")
        os.environ["CLAUDE_CODE_SESSION_ID"] = "abcdef12-3456-7890-abcd-ef1234567890"
        os.environ["CLAUDE_HANDOFF_DIR"] = str(self.home / "passations")
        self.handed_over("abcdef12", "0801df0e-3c3b-48e6-a43f-375ac6d170e3", self.home / "passations" / "demo")
        self.assertEqual(self.sessions(), (0, []))


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

    def yield_to(self, *argv: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(support.PLUGIN / "hooks" / "handoff_trigger.py"), "yield", *argv],
            cwd=self.project, capture_output=True, encoding="utf-8",
            env={**isolated_home(self.home), "CLAUDE_HANDOFF_DRAIN_MINUTES": "30"}, check=False,
        )

    def test_a_background_session_asked_to_yield_drains_writes_its_handoff_and_stops(self) -> None:
        """ikoro-labs/forge#4, MINOR 1 of #36: what a background session does when the user's
        interactive session asks it to hand over, under the drain cap of the handoff."""
        result = self.yield_to("abcdef12-3456-7890")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = " ".join(result.stdout.split())
        day = datetime.date.today().isoformat()
        path = self.home / ".claude" / "hooks" / "state" / "handoffs" / "demo" / f"{day}-r1.md"
        for expected in (
            "launch nothing new",
            "run to its exit",
            "30 minutes",
            "sauvetage",
            str(path),
            f'"{HEADER}" set-successor <handoff path> abcdef12-3456-7890',
            "Do not run the relay itself",
            "SendMessage",
            f'"{RELAY}" --yield <handoff path>',
            "stops then deletes this one",
            "session abcdef12-3456-7890 takes over",
        ):
            self.assertIn(expected, text)
        self.assertLess(text.index("launch nothing new"), text.index(str(path)))
        self.assertLess(text.index(str(path)), text.index("set-successor"))
        # BLOCKER of round 1 on #37: the handoff is named and sent before this session is closed.
        sent = "Send the handoff path to the session abcdef12-3456-7890 by SendMessage"
        self.assertLess(text.index("set-successor"), text.index(sent))
        self.assertLess(text.index(sent), text.index("--yield"))
        # The hook's own markers are left alone: the session's context has not reached its limit.
        self.assertFalse((self.home / ".claude" / "hooks" / "state" / "s1.handoff").exists())

    def test_yield_needs_the_id_of_the_session_that_takes_over(self) -> None:
        for argv in ((), ("pas un identifiant; rm -rf",), ("abcdef12", "en trop")):
            with self.subTest(argv=argv):
                result = self.yield_to(*argv)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertNotIn("launch nothing new", result.stdout)

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
            # `claude rm <id>` ends the session and takes it out of the registry, as Claude Code does.
            "if sys.argv[1:2] == ['rm']:\n"
            "    import json, pathlib, signal\n"
            "    for entry in (pathlib.Path.home() / '.claude' / 'sessions').glob('*.json'):\n"
            "        fields = json.loads(entry.read_text(encoding='utf-8'))\n"
            "        if fields.get('sessionId', '').startswith(sys.argv[2]):\n"
            "            os.kill(int(fields['pid']), signal.SIGTERM)\n"
            "            entry.unlink()\n"
            "    sys.exit(0)\n"
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

    def test_another_live_session_of_the_repository_refuses_the_relay_with_code_6(self) -> None:
        """ikoro-labs/forge#4, critère 2: before the counter moves and before `claude --bg`."""
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(other.wait)
        self.addCleanup(other.kill)
        registry = self.home / ".claude" / "sessions"
        registry.mkdir(parents=True)
        entry = {"pid": other.pid, "cwd": str(self.repo), "kind": "interactive", "status": "busy",
                 "procStart": handoff_header.process_start(other.pid)}
        (registry / f"{other.pid}.json").write_text(json.dumps(entry), encoding="utf-8")
        for dry_run in ("", "1"):
            with self.subTest(dry_run=dry_run):
                result = self.relay(handoff(self.home), CLAUDE_HANDOFF_CLOSE_DRY_RUN=dry_run, CLAUDE_PID="4242")
                self.assertEqual(result.returncode, 6, result.stderr)
                self.assertIn(f"{other.pid} interactive ? busy {self.repo}", result.stderr)
                self.assertFalse(self.counter.exists())
                self.assertFalse(self.log.exists())
                self.assertNotIn("claude --bg", result.stdout)
        # The calling session's own entry does not count.
        result = self.relay(handoff(self.home), CLAUDE_PID=str(other.pid))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_relay_names_the_session_that_hands_over_and_its_successor_relays_past_it(self) -> None:
        """ikoro-labs/forge#4, MINOR 2 of #36: the predecessor, alive during its closing delay,
        does not refuse its successor's own relay."""
        first = self.home / ".claude" / "hooks" / "state" / "handoffs" / "demo"
        first.mkdir(parents=True)
        path = handoff(first)
        result = self.relay(path, CLAUDE_HANDOFF_CLOSE_DRY_RUN="", CLAUDE_CODE_SESSION_ID="0801df0e-3c3b-48e6")
        self.assertEqual(result.returncode, 0, result.stderr)
        values = handoff_header.check(path)
        self.assertEqual((values["successeur"], values["auteur"]), (["abcdef12"], ["0801df0e-3c3b-48e6"]))
        predecessor = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(predecessor.wait)
        self.addCleanup(predecessor.kill)
        registry = self.home / ".claude" / "sessions"
        registry.mkdir(parents=True)
        entry = {"pid": predecessor.pid, "sessionId": "0801df0e-3c3b-48e6", "cwd": str(self.repo), "kind": "bg",
                 "status": "idle", "procStart": handoff_header.process_start(predecessor.pid)}
        (registry / f"{predecessor.pid}.json").write_text(json.dumps(entry), encoding="utf-8")
        second = self.home / "r2"
        second.mkdir()
        self.assertEqual(self.relay(handoff(second), CLAUDE_PID="4242").returncode, 6)
        result = self.relay(handoff(second), CLAUDE_PID="4242", CLAUDE_CODE_SESSION_ID="abcdef12-0000-1111")
        self.assertEqual(result.returncode, 0, result.stderr)

    def registered(self, session: str, kind: str) -> subprocess.Popen[bytes]:
        """A running process recorded in the session registry as the live session `session`."""
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        registry = self.home / ".claude" / "sessions"
        registry.mkdir(parents=True, exist_ok=True)
        entry = {"pid": process.pid, "sessionId": session, "cwd": str(self.repo), "kind": kind, "status": "idle",
                 "name": kind, "procStart": handoff_header.process_start(process.pid)}
        (registry / f"{process.pid}.json").write_text(json.dumps(entry), encoding="utf-8")
        return process

    def yielding(self, process: subprocess.Popen[bytes], session: str, **env: str) -> dict[str, str]:
        """The environment of the background session `session` running the commands `yield` prints."""
        return {"CLAUDE_PID": str(process.pid), "CLAUDE_CODE_SESSION_ID": session, "CLAUDE_CODE_CHILD_SESSION": "1",
                **env}

    def test_a_background_session_that_yielded_is_gone_for_a_third_session(self) -> None:
        """ikoro-labs/forge#4, BLOCKER of round 1 on #37: the background session B that yields to
        the user's interactive session I is stopped and deleted once its handoff names I. A third
        session, here C, the relay I starts at its own limit, does not find B in place and stop."""
        b, i, c = "b0b0b0b0-1111-2222", "1a1a1a1a-3333-4444", "c0c0c0c0-5555-6666"
        background = self.registered(b, "bg")
        self.registered(i, "interactive")
        folder = self.state / "handoffs" / "demo"
        folder.mkdir(parents=True)
        path = handoff(folder)
        # B follows what `yield` prints: it names I, sends I the path (SendMessage), then closes.
        env = self.yielding(background, b, CLAUDE_HANDOFF_CLOSE_DELAY="1", CLAUDE_HANDOFF_CLOSE_DRY_RUN="")
        named = subprocess.run(
            [sys.executable, str(HEADER), "set-successor", str(path), i],
            cwd=self.repo, capture_output=True, encoding="utf-8", env={**self.env, **env}, check=False,
        )
        self.assertEqual(named.returncode, 0, named.stdout)
        closing = self.relay(path, "--yield", **env)
        deadline = time.monotonic() + 30
        entry = self.home / ".claude" / "sessions" / f"{background.pid}.json"
        while closing.returncode == 0 and entry.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        # I relays to C at its own limit: the relay writes C as successor and I as author.
        second = handoff(self.home).rename(folder / "2026-10-20-r2.md")
        handoff_header.set_successor(second, c, "150000", i)
        seen = subprocess.run(
            [sys.executable, str(HEADER), "sessions", "."], cwd=self.repo, capture_output=True,
            encoding="utf-8", env={**self.env, "CLAUDE_CODE_SESSION_ID": c}, check=False,
        )
        self.assertEqual((seen.returncode, seen.stdout), (0, ""))
        self.assertEqual(closing.returncode, 0, closing.stderr)
        self.assertIn(f"rm {b[:8]}", self.log.read_text(encoding="utf-8"))
        # No successor was started and the daily counter did not move.
        self.assertNotIn("--bg", self.log.read_text(encoding="utf-8"))
        self.assertFalse(self.counter.exists())

    def test_yield_closes_only_a_background_session_whose_handoff_names_its_successor(self) -> None:
        """ikoro-labs/forge#4, BLOCKER of round 1 on #37: `--yield` refuses what would close the
        wrong session or kill an agent the handoff does not leave for a rescue."""
        b = "b0b0b0b0-1111-2222"
        env = self.yielding(self.registered(b, "bg"), b, CLAUDE_HANDOFF_CLOSE_DELAY="45")
        path = handoff(self.home)
        # Nothing names the interactive session yet: set-successor comes first.
        self.assertEqual(self.relay(path, "--yield", **env).returncode, 2)
        handoff_header.set_successor(path, "1a1a1a1a", "", b)
        result = self.relay(path, "--yield", **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry run, would run in 45s:", result.stdout)
        self.assertIn(f"stop {b[:8]}", result.stdout)
        self.assertIn(f"rm {b[:8]}", result.stdout)
        self.assertNotIn("--bg", result.stdout)
        self.assertFalse(self.counter.exists())
        # An agent in flight is waited for; listed for a rescue, --force admits it.
        for flags, en_vol, sauvetage, code in (((), "[agent-x]", "[]", 5), (("--force",), "[]", "[]", 5),
                                               (("--force",), "[agent-x]", "[agent-x]", 0)):
            with self.subTest(flags=flags, en_vol=en_vol, sauvetage=sauvetage):
                folder = Path(tempfile.mkdtemp(dir=self.home))
                drained = handoff(folder, en_vol=en_vol, sauvetage=sauvetage)
                handoff_header.set_successor(drained, "1a1a1a1a", "", b)
                self.assertEqual(self.relay(drained, "--yield", *flags, **env).returncode, code)
        # The user's interactive session, or a session whose pid is unknown, is never closed this way.
        i = "1a1a1a1a-3333-4444"
        interactive = self.relay(path, "--yield", **self.yielding(self.registered(i, "interactive"), i))
        self.assertEqual(interactive.returncode, 1)
        self.assertNotIn("would run", interactive.stdout)
        unknown = self.relay(path, "--yield", CLAUDE_CODE_CHILD_SESSION="1", CLAUDE_CODE_SESSION_ID=b)
        self.assertEqual(unknown.returncode, 1)

    def test_the_docstring_names_code_6_among_the_exit_codes(self) -> None:
        import handoff_relay

        exit_line = next(line for line in (handoff_relay.__doc__ or "").splitlines() if line.startswith("Exit:"))
        self.assertRegex(exit_line, r"\b6 [a-z]")

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
