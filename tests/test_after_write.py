import io
import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401
import after_write
from after_write import (
    EM_DASH,
    em_dash_problem,
    load_allowances,
    main,
    matches,
    parse_allowances,
)


class EmDash(unittest.TestCase):
    def test_an_em_dash_beyond_the_allowance_is_reported(self) -> None:
        self.assertIsNone(em_dash_problem("a.md", "plain, text", {}))
        problem = em_dash_problem("a.md", f"one {EM_DASH} two {EM_DASH}", {})
        self.assertEqual(
            problem, "a.md holds 2 em dash: replace each with a comma, a colon or parentheses"
        )
        self.assertIsNone(em_dash_problem("a.md", f"one {EM_DASH} two", {"a.md": 1}))

    def test_the_allowances_file_is_read_line_by_line(self) -> None:
        text = "# count path\n3 docs/legacy.md\n\nx not-a-count\n1 notes/a b.md\n"
        self.assertEqual(parse_allowances(text), {"docs/legacy.md": 3, "notes/a b.md": 1})

    def test_the_allowances_come_from_the_key_the_config_names(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(load_allowances(root), {})
            (root / "docs" / "agents").mkdir(parents=True)
            (root / "docs" / "agents" / "usine.md").write_text(
                "- `em-dash-allowances`: `docs/agents/em-dash.txt`\n", encoding="utf-8"
            )
            self.assertEqual(load_allowances(root), {})
            (root / "docs" / "agents" / "em-dash.txt").write_text("2 a.md\n", encoding="utf-8")
            self.assertEqual(load_allowances(root), {"a.md": 2})

    def test_main_reports_a_written_file_of_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "a.md"
            target.write_text(f"x {EM_DASH} y", encoding="utf-8")

            def run(path: Path) -> int:
                event = json.dumps({"tool_input": {"file_path": str(path)}, "cwd": str(root)})
                with (
                    mock.patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": str(root)}),
                    mock.patch("sys.stdin", io.StringIO(event)),
                    mock.patch("sys.stderr", io.StringIO()),
                ):
                    return main()

            self.assertEqual(run(target), 2)
            target.write_text("x, y", encoding="utf-8")
            self.assertEqual(run(target), 0)
            with tempfile.TemporaryDirectory() as elsewhere:
                outside = Path(elsewhere) / "b.md"
                outside.write_text(EM_DASH, encoding="utf-8")
                self.assertEqual(run(outside), 0)


class Pattern(unittest.TestCase):
    """The path patterns of `format-on-write`: the whole relative POSIX path, case included."""

    def test_double_star_slash_crosses_directories_or_none(self) -> None:
        self.assertTrue(matches("**/*.py", "a.py"))
        self.assertTrue(matches("**/*.py", "src/pkg/a.py"))
        self.assertFalse(matches("**/*.py", "src/a.pyc"))

    def test_star_stays_inside_one_directory(self) -> None:
        self.assertTrue(matches("src/*.py", "src/a.py"))
        self.assertFalse(matches("src/*.py", "src/pkg/a.py"))

    def test_question_mark_is_one_character_but_not_a_slash(self) -> None:
        self.assertTrue(matches("a?.py", "ab.py"))
        self.assertFalse(matches("a?.py", "a.py"))
        self.assertFalse(matches("a?b", "a/b"))

    def test_braces_are_alternatives(self) -> None:
        pattern = "apps/web/**/*.{ts,tsx}"
        self.assertTrue(matches(pattern, "apps/web/src/a.ts"))
        self.assertTrue(matches(pattern, "apps/web/a.tsx"))
        self.assertFalse(matches(pattern, "apps/web/a.js"))
        self.assertFalse(matches(pattern, "apps/api/a.ts"))

    def test_the_case_counts(self) -> None:
        self.assertFalse(matches("**/*.py", "A.PY"))

    def test_everything_else_is_literal(self) -> None:
        self.assertTrue(matches("a.b+c(d)[e].py", "a.b+c(d)[e].py"))
        self.assertFalse(matches("a.py", "axpy"))
        self.assertTrue(matches("a{b.py", "a{b.py"))


def run_hook(root: Path, target: Path) -> tuple[int, str]:
    event = json.dumps({"tool_input": {"file_path": str(target)}, "cwd": str(root)})
    err = io.StringIO()
    with (
        mock.patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": str(root)}),
        mock.patch("sys.stdin", io.StringIO(event)),
        mock.patch("sys.stderr", err),
    ):
        return main(), err.getvalue()


class FormatOnWrite(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        (self.root / "docs" / "agents").mkdir(parents=True)
        self.python = shlex.quote(Path(sys.executable).as_posix())

    def configure(self, *lines: str) -> None:
        text = "".join(f"- `format-on-write` : `{line}`\n" for line in lines)
        (self.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def script(self, name: str, body: str) -> str:
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        return f"{self.python} {shlex.quote(path.as_posix())}"

    def test_a_matching_pattern_runs_its_command_on_the_absolute_path_from_the_root(self) -> None:
        """No F-NNNN: ticket #2. The path is the last argument, the command runs from the root."""
        command = self.script(
            "fmt.py",
            "import os, sys\n"
            "open(sys.argv[1], 'a').write('|' + os.getcwd() + '|' + sys.argv[1])\n",
        )
        self.configure(f"**/*.txt | {command}")
        target = self.root / "sub" / "a.txt"
        target.parent.mkdir()
        target.write_text("x", encoding="utf-8")
        self.assertEqual(run_hook(self.root, target), (0, ""))
        self.assertEqual(
            target.read_text(encoding="utf-8"), f"x|{self.root}|{target}"
        )

    def test_a_pattern_that_does_not_match_runs_nothing(self) -> None:
        command = self.script("fmt.py", "import sys\nopen(sys.argv[1], 'a').write('!')\n")
        self.configure(f"**/*.py | {command}")
        target = self.root / "a.txt"
        target.write_text("x", encoding="utf-8")
        self.assertEqual(run_hook(self.root, target), (0, ""))
        self.assertEqual(target.read_text(encoding="utf-8"), "x")

    def test_without_the_key_nothing_runs(self) -> None:
        target = self.root / "a.txt"
        target.write_text("x", encoding="utf-8")
        self.assertEqual(run_hook(self.root, target), (0, ""))

    def test_several_patterns_run_every_command_in_the_file_order(self) -> None:
        one = self.script("one.py", "import sys\nopen(sys.argv[1], 'a').write('1')\n")
        two = self.script("two.py", "import sys\nopen(sys.argv[1], 'a').write('2')\n")
        self.configure(f"**/*.txt | {one}", f"a.* | {two}", f"**/*.py | {one}")
        target = self.root / "a.txt"
        target.write_text("x", encoding="utf-8")
        self.assertEqual(run_hook(self.root, target), (0, ""))
        self.assertEqual(target.read_text(encoding="utf-8"), "x12")

    def test_a_failing_formatter_is_reported_and_the_write_stays(self) -> None:
        command = self.script("fmt.py", "import sys\nprint('boom')\nsys.exit(3)\n")
        self.configure(f"**/*.txt | {command}")
        target = self.root / "a.txt"
        target.write_text("x", encoding="utf-8")
        code, err = run_hook(self.root, target)
        self.assertEqual(code, 2)
        self.assertEqual(err, f"format-on-write: {command} failed on a.txt (exit 3)\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "x")

    def test_a_formatter_past_its_delay_is_reported(self) -> None:
        command = self.script("fmt.py", "import time\ntime.sleep(30)\n")
        self.configure(f"**/*.txt | {command}")
        target = self.root / "a.txt"
        target.write_text("x", encoding="utf-8")
        with mock.patch.object(after_write, "COMMAND_TIMEOUT", 1):
            code, err = run_hook(self.root, target)
        self.assertEqual(code, 2)
        self.assertEqual(err, f"format-on-write: {command} failed on a.txt (timed out after 1s)\n")

    def test_the_total_delay_bounds_the_commands_together(self) -> None:
        slow = self.script("slow.py", "import time\ntime.sleep(30)\n")
        quick = self.script("quick.py", "import sys\nopen(sys.argv[1], 'a').write('!')\n")
        self.configure(f"**/*.txt | {slow}", f"**/*.txt | {quick}")
        target = self.root / "a.txt"
        target.write_text("x", encoding="utf-8")
        with (
            mock.patch.object(after_write, "COMMAND_TIMEOUT", 30),
            mock.patch.object(after_write, "TOTAL_TIMEOUT", 1),
        ):
            code, err = run_hook(self.root, target)
        self.assertEqual(code, 2)
        self.assertIn("(timed out after 1s)", err)
        self.assertEqual(err.count("format-on-write:"), 2)
        self.assertEqual(target.read_text(encoding="utf-8"), "x")

    def test_a_command_that_is_not_found_is_reported(self) -> None:
        self.configure("**/*.txt | no-such-formatter-xyz --write")
        target = self.root / "a.txt"
        target.write_text("x", encoding="utf-8")
        code, err = run_hook(self.root, target)
        self.assertEqual(code, 2)
        self.assertEqual(
            err,
            "format-on-write: no-such-formatter-xyz --write failed on a.txt (command not found)\n",
        )

    def test_a_line_missing_its_command_is_reported_not_completed(self) -> None:
        self.configure("**/*.txt")
        target = self.root / "a.txt"
        target.write_text("x", encoding="utf-8")
        code, err = run_hook(self.root, target)
        self.assertEqual(code, 2)
        self.assertEqual(
            err, "format-on-write: `**/*.txt` is not `<pattern> | <command>`, line ignored\n"
        )

    def test_a_command_with_an_unclosed_quote_is_reported_and_the_em_dash_check_runs(self) -> None:
        self.configure('**/*.txt | fmt "unclosed')
        target = self.root / "a.txt"
        target.write_text(f"x {EM_DASH} y", encoding="utf-8")
        code, err = run_hook(self.root, target)
        self.assertEqual(code, 2)
        self.assertIn(
            'format-on-write: `**/*.txt | fmt "unclosed` is not `<pattern> | <command>`, line ignored',
            err,
        )
        self.assertIn("a.txt holds 1 em dash", err)

    def test_the_command_may_hold_a_pipe(self) -> None:
        command = self.script("fmt.py", "import sys\nopen(sys.argv[2], 'a').write(sys.argv[1])\n")
        self.configure(f"**/*.txt | {command} a|b {self.root.as_posix()}/log")
        target = self.root / "a.txt"
        target.write_text("x", encoding="utf-8")
        self.assertEqual(run_hook(self.root, target)[0], 0)
        self.assertEqual((self.root / "log").read_text(encoding="utf-8"), "a|b")

    def test_the_formatters_run_before_the_em_dash_check(self) -> None:
        command = self.script(
            "fmt.py", f"import sys\nopen(sys.argv[1], 'w').write('clean')\n"
        )
        self.configure(f"**/*.txt | {command}")
        target = self.root / "a.txt"
        target.write_text(f"x {EM_DASH} y", encoding="utf-8")
        self.assertEqual(run_hook(self.root, target), (0, ""))
        target.write_text("x", encoding="utf-8")
        failing = self.script("bad.py", "import sys\nsys.exit(1)\n")
        self.configure(f"**/*.txt | {failing}")
        target.write_text(f"x {EM_DASH} y", encoding="utf-8")
        code, err = run_hook(self.root, target)
        self.assertEqual(code, 2)
        self.assertIn("failed on a.txt (exit 1)", err)
        self.assertIn("a.txt holds 1 em dash", err)


if __name__ == "__main__":
    unittest.main()
