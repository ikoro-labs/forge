"""The `SubagentStop` and `SessionStart` hook agent_cleanup.py: the cleanup after an agent, held by
a hook instead of prose (ikoro-labs/forge#199, point (c)).

The seam is the hook as Claude Code runs it: a process of its own, the event as JSON on stdin,
against throwaway git repositories (a bare one as `origin`). Every test runs under an isolated
HOME and USERPROFILE, without the CLAUDE_ variables of the session running the tests, and writes
nothing in the real ~/.claude or ~/.cache. The hook is never run against a real repository.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import handoff_header
import support

HOOK = support.PLUGIN / "hooks" / "agent_cleanup.py"
WINDOWS = sys.platform == "win32"
LINUX = sys.platform.startswith("linux")
HAS_GIT = shutil.which("git") is not None


def remove_tree(path: Path) -> None:
    """rmtree that also removes the read-only files git leaves under .git (Windows)."""

    def writable(function, target, _error) -> None:
        os.chmod(target, 0o700)
        function(target)

    shutil.rmtree(path, onerror=writable)


@unittest.skipUnless(HAS_GIT, "the hook works on git repositories")
class Cleanup(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(remove_tree, self.home)
        self.origin = self.home / "origin.git"
        self.repo = self.home / "demo"
        self.worktrees = self.repo / ".claude" / "worktrees"
        self.env = {key: value for key, value in os.environ.items() if not key.startswith(("CLAUDE_", "GIT_"))}
        self.env.update(
            HOME=str(self.home), USERPROFILE=str(self.home), GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
        )
        self.git_in(self.home, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.git_in(self.home, "init", "-q", "-b", "main", str(self.repo))
        self.commit("init")
        self.git("remote", "add", "origin", str(self.origin))
        self.git("push", "-q", "origin", "main")
        self.git("fetch", "-q", "origin")

    # --- a throwaway repository ----------------------------------------------------------------

    def git_in(self, folder: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(folder), *args], capture_output=True, text=True, env=self.env, check=False,
        )
        self.assertEqual(result.returncode, 0, f"git {' '.join(args)}: {result.stderr}")
        return result.stdout.strip()

    def git(self, *args: str) -> str:
        return self.git_in(self.repo, *args)

    def commit(self, message: str, folder: Path | None = None) -> str:
        """A commit on the current branch of `folder` (the main checkout by default), its sha."""
        folder = folder or self.repo
        (folder / f"{message.replace(' ', '-')}.txt").write_text(message, encoding="utf-8")
        self.git_in(folder, "add", "-A")
        self.git_in(folder, "commit", "-q", "-m", message)
        return self.git_in(folder, "rev-parse", "HEAD")

    def branches(self) -> list[str]:
        return self.git("for-each-ref", "--format=%(refname:short)", "refs/heads").split()

    def worktree_paths(self) -> list[Path]:
        listing = self.git("worktree", "list", "--porcelain")
        return [Path(line.removeprefix("worktree ")) for line in listing.splitlines() if line.startswith("worktree ")]

    # --- the hook as Claude Code runs it -------------------------------------------------------

    def event(self, name: str = "SubagentStop", **fields: object) -> dict[str, object]:
        base: dict[str, object] = {
            "session_id": "abcdef12-3456-7890-abcd-ef1234567890", "transcript_path": "", "cwd": str(self.repo),
            "hook_event_name": name,
        }
        if name == "SubagentStop":
            base.update(agent_id="a0123456789abcdef", agent_type="forge:coder", stop_hook_active=False)
        return {**base, **fields}

    def run_hook(self, event: object, folder: Path | None = None) -> subprocess.CompletedProcess[str]:
        stdin = event if isinstance(event, str) else json.dumps(event)
        return subprocess.run(
            [sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True, env=self.env,
            cwd=folder or self.repo, timeout=120, check=False,
        )

    def message(self, result: subprocess.CompletedProcess[str]) -> str:
        """The one-line-per-element report the hook printed, "" when it said nothing."""
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["systemMessage"] if result.stdout.strip() else ""


    # --- agent worktrees, as Claude Code makes and locks them ----------------------------------

    def agent_worktree(self, agent_id: str, detach: bool = False) -> Path:
        """`<repo>/.claude/worktrees/agent-<id>` on branch `worktree-agent-<id>`, or on a detached head."""
        path = self.worktrees / f"agent-{agent_id}"
        if detach:
            self.git("worktree", "add", "-q", "--detach", str(path))
        else:
            self.git("worktree", "add", "-q", "-b", f"worktree-agent-{agent_id}", str(path))
        return path

    def lock(self, path: Path, pid: int, start: str | None = None) -> None:
        """Lock a worktree as Claude Code does: the session's pid, with its start time off Windows."""
        if not WINDOWS:
            start = handoff_header.process_start(pid) if start is None else start
        stamp = f" start {start}" if start else ""
        self.git("worktree", "lock", "--reason", f"claude agent {path.name} (pid {pid}{stamp})", str(path))

    def running_session(self) -> int:
        """A running process, standing for the session that holds the lock of a live agent."""
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return process.pid

    def gone_session(self) -> int:
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait()
        return process.pid


@unittest.skipUnless(HAS_GIT, "the hook works on git repositories")
class Worktrees(Cleanup):
    def test_a_finished_clean_worktree_is_removed_and_its_work_stays_on_its_branch(self) -> None:
        """#199 (c): a worktree no lock holds is an agent that finished; clean, it goes."""
        path = self.agent_worktree("a1")
        self.commit("work", folder=path)
        result = self.run_hook(self.event())
        self.assertFalse(path.exists())
        self.assertIn("agent-a1", self.message(result))
        self.assertIn("worktree-agent-a1", self.branches())

    def test_a_worktree_locked_by_a_dead_session_is_unlocked_then_removed(self) -> None:
        """#199 (c): the lock of a gone pid is a dead agent's; `git worktree unlock`, then `remove`."""
        path = self.agent_worktree("a1")
        pid = self.gone_session()
        self.lock(path, pid, start="1")
        result = self.run_hook(self.event())
        self.assertFalse(path.exists())
        self.assertIn("agent-a1", self.message(result))

    @unittest.skipIf(WINDOWS, "a Windows lock has no start time: a running pid is taken for its holder")
    def test_a_running_pid_with_another_start_time_counts_as_dead(self) -> None:
        """#199 (c): a pid reused by another process (its start time is not the lock's) held nothing."""
        path = self.agent_worktree("a1")
        pid = self.running_session()
        self.lock(path, pid, start=str(int(handoff_header.process_start(pid)) + 1))
        self.run_hook(self.event())
        self.assertFalse(path.exists())

    def test_a_worktree_held_by_a_live_session_stays_locked(self) -> None:
        """#199 (c): at SubagentStop the stopping agent's worktree is still locked by the living
        session; it stays, and goes at a later passage."""
        path = self.agent_worktree("a1")
        self.lock(path, self.running_session())
        result = self.run_hook(self.event())
        self.assertTrue(path.exists())
        self.assertEqual(self.message(result), "")
        self.assertIn("locked", self.git("worktree", "list", "--porcelain"))

    def test_a_dirty_worktree_is_left_and_reported(self) -> None:
        """#199 (c): untracked files, or a changed tracked file, are work: left, and said."""
        untracked = self.agent_worktree("a1")
        (untracked / "notes.txt").write_text("unsaved", encoding="utf-8")
        changed = self.agent_worktree("a2")
        (changed / "init.txt").write_text("edited", encoding="utf-8")
        message = self.message(self.run_hook(self.event()))
        self.assertTrue(untracked.exists() and changed.exists())
        self.assertIn("agent-a1", message)
        self.assertIn("agent-a2", message)
        self.assertEqual(len(message.splitlines()), 2)

    def test_a_detached_head_found_nowhere_else_is_left_and_reported(self) -> None:
        """#199 (c): removing a detached worktree whose commit no branch holds would lose it."""
        path = self.agent_worktree("a1", detach=True)
        self.commit("only here", folder=path)
        message = self.message(self.run_hook(self.event()))
        self.assertTrue(path.exists())
        self.assertIn("agent-a1", message)

    def test_a_detached_head_contained_in_main_or_a_remote_branch_is_removed(self) -> None:
        """#199 (c): the commit lives elsewhere (`main`, or a branch of the remote): safe to remove."""
        in_main = self.agent_worktree("a1", detach=True)
        pushed = self.agent_worktree("a2", detach=True)
        self.commit("pushed work", folder=pushed)
        self.git_in(pushed, "push", "-q", "origin", "HEAD:refs/heads/feature")
        self.git("fetch", "-q", "origin")
        self.run_hook(self.event())
        self.assertFalse(in_main.exists())
        self.assertFalse(pushed.exists())

    def test_only_agent_worktrees_under_the_repository_are_touched(self) -> None:
        """#199 (c): the convention is `<repo>/.claude/worktrees/agent-*`; any other worktree is left alone."""
        other = self.worktrees / "feature-x"
        self.git("worktree", "add", "-q", "-b", "feature-x", str(other))
        elsewhere = self.home / "agent-elsewhere"
        self.git("worktree", "add", "-q", "-b", "worktree-agent-elsewhere", str(elsewhere))
        result = self.run_hook(self.event())
        self.assertTrue(other.exists() and elsewhere.exists())
        self.assertEqual(self.message(result), "")

    def test_an_event_from_inside_a_worktree_cleans_the_main_checkout(self) -> None:
        """#199 (c): a subagent's cwd is its worktree; the hook acts on the main checkout it belongs to."""
        mine = self.agent_worktree("mine")
        self.lock(mine, self.running_session())
        finished = self.agent_worktree("done")
        self.run_hook(self.event(cwd=str(mine)), folder=mine)
        self.assertTrue(mine.exists())
        self.assertFalse(finished.exists())

    def test_a_repository_without_agent_worktrees_prints_nothing(self) -> None:
        """#199 (c): nothing removed, nothing left: nothing said."""
        result = self.run_hook(self.event())
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)


@unittest.skipUnless(HAS_GIT, "the hook works on git repositories")
class FailsOpen(Cleanup):
    def test_an_event_it_cannot_read_exits_zero_and_says_nothing(self) -> None:
        """#199 (c): the hook never blocks, never exits 2, which would hold the agent at SubagentStop."""
        for stdin in ("", "not json", "[]", '{"cwd": 3}'):
            with self.subTest(stdin=stdin):
                result = self.run_hook(stdin)
                self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    def test_outside_a_git_repository_it_does_nothing(self) -> None:
        """#199 (c): no repository, nothing to clean, nothing printed."""
        folder = self.home / "plain"
        folder.mkdir()
        result = self.run_hook(self.event(cwd=str(folder)), folder)
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)
        self.assertTrue(self.repo.exists())


if __name__ == "__main__":
    unittest.main()
