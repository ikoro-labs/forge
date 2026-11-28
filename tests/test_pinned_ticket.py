"""F-0003 A47 to A50, A57, A59 (ikoro-labs/forge#406): a short agent leads one ticket with
`forge:feature-build F-NNNN --ticket <n>`, asks its question in the G5 format, and gets the ticket back
as ready once a default decision answers it.

`gh` is simulated, every test runs under an isolated HOME and USERPROFILE and without the CLAUDE_ variables
of the session running the tests, and nothing is written in the real ~/.claude.
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import support
from agent_lock import main as lock_main
from handoff_header import process_start
from test_question_delay import STAFF, Gh, Project, issue, labeled, waiting

LOCK_SCRIPT = support.PLUGIN / "hooks" / "agent_lock.py"


class ReadyAgain(unittest.TestCase):
    """A59: a `post-default` on a ticket puts `ready-for-agent` back."""

    def test_a_default_decision_on_a_ticket_that_waited_gives_ready_for_agent_back(self) -> None:
        """F-0003 A59: the ticket loses `needs-info` and regains `ready-for-agent`, with the decision comment."""
        project = Project(self)
        gh = waiting(["needs-info"], 30)
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertTrue(gh.bodies()[0].startswith("Décision (staff-engineer, P1) par défaut"))
        self.assertEqual(gh.removed(), ["needs-info"])
        self.assertEqual(gh.added(), ["labels[]=ready-for-agent"])

    def test_a_ticket_that_waited_on_a_human_gesture_label_is_ready_again_too(self) -> None:
        """F-0003 A59: `ready-for-human`, which the skill also sets on a ticket, is answered the same way."""
        project = Project(self)
        gh = waiting(["ready-for-human"], 30)
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.removed(), ["ready-for-human"])
        self.assertEqual(gh.added(), ["labels[]=ready-for-agent"])

    def test_a_pull_request_never_gets_the_ready_label(self) -> None:
        """F-0003 A59: the label is for a ticket (an issue); a pull request that waited keeps only its removal."""
        project = Project(self)
        gh = waiting(["needs-info"], 30, pull_request=True)
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.added(), [])

    def test_a_ticket_already_ready_is_not_labeled_twice(self) -> None:
        """F-0003 A59: a ticket that already carries `ready-for-agent` is left as it is."""
        project = Project(self)
        gh = Gh({12: issue(12, ["needs-info", "ready-for-agent"])}, {12: [labeled("needs-info", 30)]})
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.added(), [])

    def test_a_reminder_gives_no_ready_label(self) -> None:
        """F-0003 A59: a verdict that is not a default decision leaves the ticket with the human."""
        project = Project(self)
        gh = waiting(["needs-info"], 30)
        code, out = project.route(gh, "VERDICT: RESERVED\nDECISION: a human\nMATRIX_CELL: H1\nGROUND: x\n", "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.added(), ["labels[]=needs-your-attention"])

    def test_the_plan_without_apply_says_the_label_and_writes_nothing(self) -> None:
        """F-0003 A59: the printed plan lists `ready-for-agent` among the labels to add; `gh` gets no write."""
        project = Project(self)
        gh = waiting(["needs-info"], 30)
        code, out = project.route(gh, STAFF, "--json")
        self.assertEqual(code, 0, out)
        self.assertIn('"ready-for-agent"', out)
        self.assertEqual(gh.writes, [])


class Locked(unittest.TestCase):
    """A48, A57: the pinned agent runs only on a ticket whose lock it holds itself, and frees it to ask."""

    def setUp(self) -> None:
        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.repo = self.home / "demo"
        (self.repo / ".git").mkdir(parents=True)
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in [key for key in os.environ if key.startswith(("CLAUDE_", "GIT_"))]:
            del os.environ[name]
        os.environ.update(HOME=str(self.home), USERPROFILE=str(self.home))

    def sleeper(self) -> int:
        """A running process that is neither this one nor one of its ancestors."""
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return process.pid

    def dead_pid(self) -> int:
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait()
        return process.pid

    def lock(self, pid: int, ticket: str = "406", text: str | None = None) -> Path:
        """The lock of a ticket as the design's data model writes it."""
        project = re.sub(r"[\\/:]", "-", str(self.repo))
        folder = self.home / ".claude" / "hooks" / "state" / "dispatch" / "locks" / project
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{ticket}.json"
        fields = {
            "ticket": ticket, "pid": pid, "start": process_start(pid), "name": "forge-dispatch-406",
            "worktree": str(self.repo), "zones": [], "since": "2026-11-28T12:00:00Z",
        }
        path.write_text(json.dumps(fields) if text is None else text, encoding="utf-8")
        return path

    def call(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = lock_main(list(args))
        return code, out.getvalue()

    def test_a_lock_held_by_the_session_itself_passes(self) -> None:
        """F-0003 A48: the lock names this process (or an ancestor): the agent may go on."""
        self.lock(os.getpid())
        code, out = self.call("check", str(self.repo), "406")
        self.assertEqual(code, 0, out)
        self.assertIn("tenu par cette session", out)

    def test_without_a_lock_the_agent_stops(self) -> None:
        """F-0003 A48: no lock file for the ticket, code 1 and the reason."""
        code, out = self.call("check", str(self.repo), "406")
        self.assertEqual(code, 1, out)
        self.assertIn("aucun verrou", out)

    def test_a_lock_of_another_live_process_stops_the_agent(self) -> None:
        """F-0003 A48: a lock a live process of another agent holds is not this session's."""
        self.lock(self.sleeper())
        code, out = self.call("check", str(self.repo), "406")
        self.assertEqual(code, 1, out)
        self.assertIn("autre processus", out)

    def test_a_lock_of_a_dead_process_stops_the_agent(self) -> None:
        """F-0003 A48: a lock whose pid is gone says nothing for this session."""
        self.lock(self.dead_pid())
        code, out = self.call("check", str(self.repo), "406")
        self.assertEqual(code, 1, out)
        self.assertIn("pid mort", out)

    def test_an_unreadable_lock_stops_the_agent(self) -> None:
        """F-0003 A48: a lock file that cannot be read is no lock."""
        self.lock(os.getpid(), text="not json")
        code, out = self.call("check", str(self.repo), "406")
        self.assertEqual(code, 1, out)
        self.assertIn("illisible", out)

    def test_the_lock_of_another_ticket_does_not_count(self) -> None:
        """F-0003 A47, A48: the agent holds the lock of its own ticket, not the one of #407."""
        self.lock(os.getpid(), ticket="407")
        code, out = self.call("check", str(self.repo), "406")
        self.assertEqual(code, 1, out)

    def test_a_worktree_path_reads_the_locks_of_its_main_checkout(self) -> None:
        """F-0003 A48: the dispatcher keys its locks by the main checkout; the agent runs in a worktree of it."""
        self.lock(os.getpid())
        worktree = self.home / "wt"
        gitdir = self.repo / ".git" / "worktrees" / "wt"
        gitdir.mkdir(parents=True)
        (gitdir / "commondir").write_text("../..\n", encoding="utf-8")
        worktree.mkdir()
        (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
        code, out = self.call("check", str(worktree), "406")
        self.assertEqual(code, 0, out)

    def test_a_ticket_that_is_not_a_number_is_a_wrong_call(self) -> None:
        """F-0003 A48: the ticket names a file, so `../x` is refused with code 2 and nothing is read."""
        code, out = self.call("check", str(self.repo), "../406")
        self.assertEqual(code, 2, out)

    def test_releasing_removes_the_lock_this_session_holds(self) -> None:
        """F-0003 A57: the agent that asks its question frees its lock; the ticket is then without one."""
        path = self.lock(os.getpid())
        code, out = self.call("release", str(self.repo), "406")
        self.assertEqual(code, 0, out)
        self.assertFalse(path.exists())

    def test_releasing_never_removes_the_lock_of_another_process(self) -> None:
        """F-0003 A57: a lock another agent holds stays, and the command says it did nothing."""
        path = self.lock(self.sleeper())
        code, out = self.call("release", str(self.repo), "406")
        self.assertEqual(code, 1, out)
        self.assertTrue(path.exists())

    def test_the_script_runs_as_a_process(self) -> None:
        """F-0003 A48: the form the skill calls, `agent_lock.py check <project> <ticket>`, under an isolated HOME."""
        env = {k: v for k, v in os.environ.items()}
        done = subprocess.run(
            [sys.executable, str(LOCK_SCRIPT), "check", str(self.repo), "406"],
            capture_output=True, text=True, env=env, timeout=30,
        )  # fmt: skip
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("aucun verrou", done.stdout)


if __name__ == "__main__":
    unittest.main()
