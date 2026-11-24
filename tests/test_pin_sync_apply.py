"""ikoro-labs/forge#333 A2: `pin_sync.py apply <project>` runs the two install commands, then `check`, and
refuses while a coder or a qc round is in flight.

The real `claude` is never run: `FakeClaude` stands in for it (see `pin_support.py`), and git is real, on
throwaway repositories with a local bare `origin`, under an isolated HOME and USERPROFILE.
"""

import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support  # noqa: F401  puts the hooks and the scripts of the plugin on the import path
from pin_support import FakeClaude, PinCase, entry, git
from pin_sync import main

MARKETPLACE_ADD = "claude plugin marketplace add ikoro-labs/forge@forge--v1.21.0 --scope project"
REFUSAL = "its source doesn't match its extraKnownMarketplaces entry in user or managed settings"


def passation(folder: Path, en_vol: str = "[]", file_revue: str = "[]") -> Path:
    path = folder / "2026-11-24-r1.md"
    path.write_text(
        "---\n"
        "projet: demo\n"
        "feature:\n"
        "passage_depart: 1792494562\n"
        "jetons_agents: 0\n"
        f"en_vol: {en_vol}\n"
        f"file_revue: {file_revue}\n"
        "sauvetage: []\n"
        "successeur:\n"
        "hooks_version: forge@test\n"
        "seuil:\n"
        "contexte_passation: 1000\n"
        "---\n\n# Reprise\n",
        encoding="utf-8",
    )
    return path


class Apply(PinCase):
    def apply(self, claude: FakeClaude, project: Path, *more: str) -> tuple[int, list[list[str]], str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["apply", str(project), *more], run=claude)
        return code, [line.split("\t") for line in out.getvalue().splitlines()], err.getvalue()

    def workstation(self, project: Path, version: str = "1.20.0", **fail: tuple[int, str]) -> FakeClaude:
        """A workstation that installs: `marketplace add` records the source, `update` and `install` move the version."""
        claude = FakeClaude([entry(project, version)], fail={key.replace("_", " "): value for key, value in fail.items()})

        def move(argv: list[str], cwd: Path) -> None:
            claude.entries = [entry(project, "1.21.0")]

        claude.on_success = {"update": move, "install": move}
        return claude

    def test_a_project_behind_gets_the_two_commands_from_its_root_then_a_check_that_says_ok(self) -> None:
        """#333 A2: `marketplace add <repo>@<ref> --scope project`, `update`, then `check`."""
        project = self.project("app", "forge--v1.21.0")
        claude = self.workstation(project)
        code, lines, _ = self.apply(claude, project)
        self.assertEqual(
            claude.commands(),
            [MARKETPLACE_ADD, "claude plugin update forge@ikoro-labs --scope project"],
        )
        self.assertTrue(all(cwd == project for argv, cwd in claude.calls if argv[1:4] != ["plugin", "list", "--json"]))
        self.assertEqual((code, [(line[0], line[1]) for line in lines]), (0, [("OK", str(project))]))

    def test_a_project_the_workstation_does_not_list_is_installed_not_updated(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        claude = self.workstation(project)
        claude.entries = []
        code, lines, _ = self.apply(claude, project)
        self.assertEqual(
            claude.commands(),
            [MARKETPLACE_ADD, "claude plugin install forge@ikoro-labs --scope project"],
        )
        self.assertEqual((code, lines[-1][0]), (0, "OK"))

    def test_the_commands_are_said_on_stderr_before_they_run(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        _, _, err = self.apply(self.workstation(project), project)
        self.assertIn(MARKETPLACE_ADD, err)
        self.assertIn("claude plugin update forge@ikoro-labs --scope project", err)

    def test_a_project_already_at_its_pin_runs_nothing(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        claude = self.workstation(project, "1.21.0")
        code, lines, _ = self.apply(claude, project)
        self.assertEqual((code, lines[0][0], claude.commands()), (0, "OK", []))

    def test_the_pin_is_the_one_a_merged_bump_put_on_origin_main_the_clone_has_not_fetched_yet(self) -> None:
        """The apply fetches `origin main` first: a stale `origin/main` would install the old ref and call it OK."""
        project = self.project("app", "forge--v1.20.0")
        self.push_pin(project, "forge--v1.21.0")
        git(project, "update-ref", "refs/remotes/origin/main", "HEAD~1")
        claude = self.workstation(project)
        code, lines, _ = self.apply(claude, project)
        self.assertEqual(claude.commands()[0], MARKETPLACE_ADD)
        self.assertEqual((code, lines[-1][0]), (0, "OK"))

    def test_a_fetch_that_fails_is_not_run_and_nothing_is_installed(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        git(project, "remote", "set-url", "origin", str(self.root / "gone.git"))
        claude = self.workstation(project)
        code, lines, _ = self.apply(claude, project)
        self.assertEqual((code, lines[0][0], claude.commands()), (2, "NOT RUN", []))
        self.assertIn("fetch", lines[0][2])

    def test_a_user_level_pin_that_differs_is_not_run_with_the_reason_and_runs_no_command(self) -> None:
        """#333 comment of 2026-11-24: `marketplace add` would exit 1, and no user settings file is edited."""
        project = self.project("app", "forge--v1.21.0")
        user = self.user_settings("forge--v1.20.0")
        before = user.read_bytes()
        claude = self.workstation(project)
        code, lines, _ = self.apply(claude, project)
        self.assertEqual((code, lines[0][0], claude.commands()), (2, "NOT RUN", []))
        self.assertIn("l'entrée de marketplace de niveau utilisateur diffère de l'épingle", lines[0][2])
        self.assertEqual(user.read_bytes(), before)

    def test_a_refusal_of_marketplace_add_the_check_could_not_foresee_is_not_run_with_the_same_reason(self) -> None:
        """Managed settings, or a user file that cannot be read: the command's own refusal is recognised."""
        project = self.project("app", "forge--v1.21.0")
        claude = self.workstation(project, marketplace_add=(1, f"Error: {REFUSAL}"))
        code, lines, _ = self.apply(claude, project)
        self.assertEqual((code, lines[-1][0]), (2, "NOT RUN"))
        self.assertIn("l'entrée de marketplace de niveau utilisateur diffère de l'épingle", lines[-1][2])
        self.assertEqual(claude.commands(), [MARKETPLACE_ADD])

    def test_another_failure_of_a_command_is_not_run_with_its_message_and_the_next_command_does_not_run(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        claude = self.workstation(project, marketplace_add=(1, "network is down"))
        code, lines, _ = self.apply(claude, project)
        self.assertEqual((code, lines[-1][0], claude.commands()), (2, "NOT RUN", [MARKETPLACE_ADD]))
        self.assertIn("network is down", lines[-1][2])

    def test_a_failing_update_is_not_run(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        code, lines, _ = self.apply(self.workstation(project, update=(1, "not found")), project)
        self.assertEqual((code, lines[-1][0]), (2, "NOT RUN"))
        self.assertIn("not found", lines[-1][2])

    def test_commands_that_succeed_but_leave_the_version_old_end_on_behind_never_ok(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        claude = FakeClaude([entry(project, "1.20.0")])  # `update` answers 0 and moves nothing
        code, lines, _ = self.apply(claude, project)
        self.assertEqual((code, lines[-1][0]), (1, "BEHIND"))

    def test_a_command_that_does_not_answer_is_not_run(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        code, lines, _ = self.apply(FakeClaude(available=False), project)
        self.assertEqual((code, lines[-1][0]), (2, "NOT RUN"))

    def test_a_wrong_call_exits_two(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as stop:
            main(["apply"], run=FakeClaude())
        self.assertEqual(stop.exception.code, 2)


class InFlight(PinCase):
    """#333 A2: no install while a coder or a qc round is in flight; the same facts as the relay's refusal."""

    def apply(self, claude: FakeClaude, project: Path, *more: str) -> tuple[int, list[list[str]]]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = main(["apply", str(project), *more], run=claude)
        return code, [line.split("\t") for line in out.getvalue().splitlines()]

    def agent(self, project: Path, pid: int, name: str = "agent-a1") -> Path:
        """A worktree of the project, locked the way Claude Code locks an agent's while it runs."""
        folder = project / ".claude" / "worktrees" / name
        git(project, "worktree", "add", "-b", f"worktree-{name}", str(folder))
        git(project, "worktree", "lock", "--reason", f"claude agent {name} (pid {pid})", str(folder))
        return folder

    def dead_pid(self) -> int:
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        return child.pid

    def refused(self, claude: FakeClaude, project: Path, *more: str) -> list[list[str]]:
        code, lines = self.apply(claude, project, *more)
        self.assertEqual((code, lines[0][0]), (3, "REFUSED"), lines)
        self.assertEqual(claude.commands(), [])
        self.assertEqual(claude.calls, [], "nothing is even asked of claude")
        return lines

    def test_a_live_agent_worktree_refuses_and_runs_nothing(self) -> None:
        import os

        project = self.project("app", "forge--v1.21.0")
        self.agent(project, os.getpid())
        lines = self.refused(FakeClaude([entry(project, "1.20.0")]), project)
        self.assertIn("agent-a1", lines[0][2])

    def test_an_agent_whose_session_is_gone_does_not_refuse(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        self.agent(project, self.dead_pid())
        claude = FakeClaude([entry(project, "1.20.0")])
        code, lines = self.apply(claude, project)
        self.assertNotEqual(lines[0][0], "REFUSED")
        self.assertEqual(claude.commands()[0], MARKETPLACE_ADD)
        self.assertEqual(code, 1)  # the stand-in moved no version: BEHIND, but the install ran

    def test_the_passation_en_vol_and_file_revue_refuse(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        for header in ({"en_vol": "[a1 coder #12]"}, {"file_revue": "[#33]"}, {"en_vol": "[x]", "file_revue": "[y]"}):
            with self.subTest(header=header):
                claude = FakeClaude([entry(project, "1.20.0")])
                lines = self.refused(claude, project, "--passation", str(passation(self.root, **header)))
                self.assertIn("passation", lines[0][2])

    def test_a_passation_with_nothing_in_flight_lets_the_install_run(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        claude = FakeClaude([entry(project, "1.20.0")])
        self.apply(claude, project, "--passation", str(passation(self.root)))
        self.assertEqual(claude.commands()[0], MARKETPLACE_ADD)

    def test_a_passation_that_cannot_be_read_refuses(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        broken = self.root / "broken.md"
        broken.write_text("not a handoff\n", encoding="utf-8")
        for path in (broken, self.root / "missing.md"):
            with self.subTest(path=path.name):
                self.refused(FakeClaude([entry(project, "1.20.0")]), project, "--passation", str(path))

    def test_worktrees_that_cannot_be_listed_refuse(self) -> None:
        """Not a repository: whether an agent runs cannot be said, so the install does not start."""
        folder = self.root / "plain"
        folder.mkdir()
        self.refused(FakeClaude([]), folder)

    def test_the_refusal_comes_before_any_fetch(self) -> None:
        import os

        project = self.project("app", "forge--v1.21.0")
        self.agent(project, os.getpid())
        git(project, "remote", "set-url", "origin", str(self.root / "gone.git"))
        lines = self.refused(FakeClaude([entry(project, "1.20.0")]), project)
        self.assertNotIn("fetch", lines[0][2])


if __name__ == "__main__":
    unittest.main()
