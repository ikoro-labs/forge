"""ikoro-labs/forge#333 A1: `pin_sync.py check` compares, per project, the `ref` pinned on origin/main
with the version `claude plugin list --json` reports, one line per project.

The real `claude` is never run: `FakeClaude` stands in for it, and git is real, on throwaway
repositories under an isolated HOME and USERPROFILE (see `pin_support.py`). Nothing writes in the real
`~/.claude`.
"""

import io
import os
import stat
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support
from pin_support import SETTINGS, FakeClaude, PinCase, entry, settings
from pin_sync import main

SCRIPT = support.PLUGIN / "scripts" / "pin_sync.py"


class Check(PinCase):
    def check(self, claude: FakeClaude, *argv: str) -> tuple[int, list[list[str]]]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["check", *argv], run=claude)
        lines = [line.split("\t") for line in out.getvalue().splitlines()]
        return code, lines

    def test_a_project_installed_at_its_pin_is_ok_and_the_exit_code_is_zero(self) -> None:
        """#333 A1: pinned 1.21.0 on origin/main, installed 1.21.0."""
        project = self.project("app", "forge--v1.21.0")
        code, lines = self.check(FakeClaude([entry(project, "1.21.0")]), str(project))
        self.assertEqual(code, 0)
        self.assertEqual([(line[0], line[1]) for line in lines], [("OK", str(project))])

    def test_a_project_installed_below_its_pin_is_behind_and_the_line_says_both_versions(self) -> None:
        """#333 A1: pinned 1.21.0, installed 1.20.0."""
        project = self.project("app", "forge--v1.21.0")
        code, lines = self.check(FakeClaude([entry(project, "1.20.0")]), str(project))
        self.assertEqual(code, 1)
        self.assertEqual([(line[0], line[1]) for line in lines], [("BEHIND", str(project))])
        self.assertIn("1.20.0", lines[0][2])
        self.assertIn("forge--v1.21.0", lines[0][2])

    def test_an_install_above_the_pin_is_not_ok_either(self) -> None:
        """The workstation is never equal by luck: any difference is reported, and the line says which way."""
        project = self.project("app", "forge--v1.20.0")
        code, lines = self.check(FakeClaude([entry(project, "1.21.0")]), str(project))
        self.assertEqual((code, lines[0][0]), (1, "BEHIND"))
        self.assertIn("1.21.0", lines[0][2])

    def test_the_pin_is_read_on_origin_main_not_in_the_working_tree(self) -> None:
        """#333 A1: an edit not on origin/main changes nothing; a merged bump not yet fetched changes nothing."""
        project = self.project("app", "forge--v1.20.0")
        (project / SETTINGS).write_text(settings("forge--v1.99.0"), encoding="utf-8")
        code, lines = self.check(FakeClaude([entry(project, "1.20.0")]), str(project))
        self.assertEqual((code, lines[0][0]), (0, "OK"))

    def test_a_project_the_workstation_does_not_list_is_behind(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        code, lines = self.check(FakeClaude([]), str(project))
        self.assertEqual((code, lines[0][0]), (1, "BEHIND"))
        self.assertIn("pas installé", lines[0][2])

    def test_the_install_of_another_project_is_not_this_projects(self) -> None:
        """`claude plugin list` without `--json` shows one entry per plugin; with it, one per project path."""
        mine, other = self.project("mine", "forge--v1.21.0"), self.project("other", "forge--v1.21.0")
        claude = FakeClaude([entry(other, "1.21.0"), entry(mine, "1.20.0")])
        code, lines = self.check(claude, str(mine))
        self.assertEqual((code, lines[0][0]), (1, "BEHIND"))

    def test_all_reads_every_project_the_workstation_lists_for_the_plugin_and_only_those(self) -> None:
        """#333 A1: `--all` takes the projects of `claude plugin list --json`: forge, project scope."""
        first, second = self.project("first", "forge--v1.21.0"), self.project("second", "forge--v1.21.0")
        elsewhere = self.project("elsewhere", "forge--v1.21.0")
        claude = FakeClaude([
            entry(first, "1.21.0"),
            entry(second, "1.20.0"),
            entry(elsewhere, "0.2.4", plugin="ai-delivery-gates@ikoro-labs"),
            entry(elsewhere, "1.3.1", plugin="forge@ikoro-labs", scope="user"),
        ])
        code, lines = self.check(claude, "--all")
        self.assertEqual([(line[0], line[1]) for line in lines], [("OK", str(first)), ("BEHIND", str(second))])
        self.assertEqual(code, 1)

    def test_all_with_every_project_ok_exits_zero(self) -> None:
        first, second = self.project("first", "forge--v1.21.0"), self.project("second", "forge--v1.21.0")
        code, lines = self.check(FakeClaude([entry(first, "1.21.0"), entry(second, "1.21.0")]), "--all")
        self.assertEqual((code, [line[0] for line in lines]), (0, ["OK", "OK"]))

    def test_all_with_no_project_listed_is_not_run_never_ok(self) -> None:
        code, lines = self.check(FakeClaude([]), "--all")
        self.assertEqual((code, lines[0][0]), (2, "NOT RUN"))

    def test_a_workstation_that_cannot_list_is_not_run(self) -> None:
        """`claude` missing, failing, or answering something that is not the list."""
        project = self.project("app")
        cases = {
            "missing": FakeClaude(available=False),
            "failing": FakeClaude(fail={"list": (1, "boom")}),
        }
        for name, claude in cases.items():
            with self.subTest(name):
                code, lines = self.check(claude, str(project))
                self.assertEqual((code, lines[0][0]), (2, "NOT RUN"))
        broken = FakeClaude()
        broken.entries = {"not": "a list"}  # type: ignore[assignment]  # the stand-in answers JSON that is not a list
        code, lines = self.check(broken, str(project))
        self.assertEqual((code, lines[0][0]), (2, "NOT RUN"))

    def test_a_pin_that_cannot_be_read_is_not_run_with_the_reason(self) -> None:
        """No settings on origin/main, a file that is not JSON, a pin that is not a tag, a plugin not enabled."""
        claude_for = lambda project: FakeClaude([entry(project, "1.21.0")])  # noqa: E731
        cases = {
            "no settings file": self.project("a", ref=None),
            "not json": self.project("b", text="{not json"),
            "not a version tag": self.project("c", "main"),
            "plugin not enabled": self.project("d", text='{"enabledPlugins": {"x@y": true}}'),
        }
        for name, project in cases.items():
            with self.subTest(name):
                code, lines = self.check(claude_for(project), str(project))
                self.assertEqual((code, lines[0][0]), (2, "NOT RUN"))
                self.assertTrue(lines[0][2])

    def test_a_folder_that_is_not_a_project_is_not_run(self) -> None:
        code, lines = self.check(FakeClaude([]), str(self.root / "nowhere"))
        self.assertEqual((code, lines[0][0]), (2, "NOT RUN"))

    def test_the_worst_line_sets_the_exit_code(self) -> None:
        """A BEHIND and a NOT RUN together exit 2: nothing was proved for the second."""
        behind, unreadable = self.project("behind"), self.project("unreadable", ref=None)
        claude = FakeClaude([entry(behind, "1.20.0"), entry(unreadable, "1.20.0")])
        code, lines = self.check(claude, "--all")
        self.assertEqual((code, sorted(line[0] for line in lines)), (2, ["BEHIND", "NOT RUN"]))

    def test_a_user_level_entry_that_differs_from_the_pin_makes_a_behind_project_not_run(self) -> None:
        """#333 comment of 2026-11-24: `marketplace add` would be refused, so the line says why and never edits it."""
        project = self.project("app", "forge--v1.21.0")
        user = self.user_settings("forge--v1.20.0")
        before = user.read_bytes()
        code, lines = self.check(FakeClaude([entry(project, "1.20.0")]), str(project))
        self.assertEqual((code, lines[0][0]), (2, "NOT RUN"))
        self.assertIn("l'entrée de marketplace de niveau utilisateur diffère de l'épingle", lines[0][2])
        self.assertIn("forge--v1.20.0", lines[0][2])
        self.assertIn("forge--v1.21.0", lines[0][2])
        self.assertEqual(user.read_bytes(), before)

    def test_a_user_level_entry_equal_to_the_pin_leaves_behind_as_it_is(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        self.user_settings("forge--v1.21.0")
        code, lines = self.check(FakeClaude([entry(project, "1.20.0")]), str(project))
        self.assertEqual((code, lines[0][0]), (1, "BEHIND"))

    def test_a_user_level_entry_does_not_hide_a_project_that_is_ok(self) -> None:
        project = self.project("app", "forge--v1.20.0")
        self.user_settings("forge--v1.19.0")
        code, lines = self.check(FakeClaude([entry(project, "1.20.0")]), str(project))
        self.assertEqual((code, lines[0][0]), (0, "OK"))

    def test_user_settings_that_pin_nothing_or_that_are_unreadable_do_not_stop_the_check(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        for name, write in {
            "no marketplace": lambda: self.user_settings(None),
            "not json": lambda: (self.home / ".claude" / "settings.json").write_text("{", encoding="utf-8"),
            "no file": lambda: (self.home / ".claude" / "settings.json").unlink(missing_ok=True),
        }.items():
            with self.subTest(name):
                write()
                code, lines = self.check(FakeClaude([entry(project, "1.20.0")]), str(project))
                self.assertEqual((code, lines[0][0]), (1, "BEHIND"))

    def test_a_user_level_entry_for_another_marketplace_is_not_the_pins(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        self.user_settings("forge--v1.20.0", marketplace="elsewhere")
        code, lines = self.check(FakeClaude([entry(project, "1.20.0")]), str(project))
        self.assertEqual((code, lines[0][0]), (1, "BEHIND"))

    def test_check_never_installs_anything(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        claude = FakeClaude([entry(project, "1.20.0")])
        self.check(claude, str(project))
        self.assertEqual(claude.commands(), [])

    def test_a_wrong_call_is_exit_two_with_a_usage_message(self) -> None:
        for argv in ([], ["--all", "/tmp/x"]):
            with self.subTest(argv=argv):
                err = io.StringIO()
                with redirect_stderr(err):
                    code = main(["check", *argv], run=FakeClaude())
                self.assertEqual(code, 2)
                self.assertIn("--all", err.getvalue())


@unittest.skipIf(os.name == "nt", "the stand-in `claude` is a POSIX shell script")
class AsAProcess(PinCase):
    """The script as `uv run python pin_sync.py ...` launches it, with a stand-in `claude` on the PATH."""

    def test_check_all_prints_one_line_per_project_and_exits_with_the_worst(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        listing = (
            '[{"id": "forge@ikoro-labs", "version": "1.20.0", "scope": "project", '
            f'"projectPath": "{project}"}}]'
        )
        claude = bin_dir / "claude"
        claude.write_text(f"#!/bin/sh\ncat <<'EOF'\n{listing}\nEOF\n", encoding="utf-8")
        claude.chmod(claude.stat().st_mode | stat.S_IEXEC)
        env = {key: value for key, value in os.environ.items() if not key.startswith("CLAUDE_")}
        env.update(HOME=str(self.home), USERPROFILE=str(self.home), PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "check", "--all"], env=env, cwd=self.root,
            capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(done.returncode, 1, done.stderr)
        fields = done.stdout.splitlines()[0].split("\t")
        self.assertEqual((fields[0], fields[1]), ("BEHIND", str(Path(project))))

    def test_without_claude_on_the_path_the_line_is_not_run(self) -> None:
        env = {key: value for key, value in os.environ.items() if not key.startswith("CLAUDE_")}
        empty = self.root / "empty"
        empty.mkdir()
        env.update(HOME=str(self.home), USERPROFILE=str(self.home), PATH=str(empty))
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "check", "--all"], env=env, cwd=self.root,
            capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertTrue(done.stdout.startswith("NOT RUN"), done.stdout)


if __name__ == "__main__":
    unittest.main()
