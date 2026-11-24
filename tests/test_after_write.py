import io
import json
import shlex
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401

# isort: split
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
        self.assertEqual(err, f"format-on-write: {command} failed on a.txt (exit 3)\nboom\n")
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

    def grandchild_formatter(self) -> str:
        """A formatter that starts a grandchild holding its outputs open, which would rewrite the
        file 2.5 s later, then hangs."""
        return self.script(
            "fmt.py",
            "import subprocess, sys, time\n"
            "code = 'import sys, time; time.sleep(2.5); open(sys.argv[1], \"a\").write(\"LATE\")'\n"
            "subprocess.Popen([sys.executable, '-c', code, sys.argv[1]])\n"
            "time.sleep(30)\n",
        )

    def check_group_killed_at_the_delay(self) -> None:
        self.configure(f"**/*.txt | {self.grandchild_formatter()}")
        target = self.root / "a.txt"
        target.write_text("x", encoding="utf-8")
        with mock.patch.object(after_write, "COMMAND_TIMEOUT", 1):
            code, err = run_hook(self.root, target)
        self.assertEqual(code, 2)
        self.assertIn("(timed out after 1s)", err)
        time.sleep(3.5)
        self.assertEqual(target.read_text(encoding="utf-8"), "x")

    @unittest.skipUnless(sys.platform.startswith("linux"), "process groups: tried on Linux")
    def test_the_grandchild_is_killed_with_the_formatter_at_the_delay_on_linux(self) -> None:
        """No F-NNNN: ticket #17. `uv run ruff` left `ruff` orphan, free to rewrite the file."""
        self.check_group_killed_at_the_delay()

    @unittest.skipUnless(sys.platform == "win32", "the Win32 job object exists on Windows only")
    def test_the_grandchild_is_killed_with_the_formatter_at_the_delay_on_windows(self) -> None:
        """No F-NNNN: ticket #17. Same scenario, through the job object of handoff_header."""
        self.check_group_killed_at_the_delay()

    @unittest.skipUnless(sys.platform == "win32", "a .cmd shim and cmd.exe exist on Windows only")
    def test_a_cmd_shim_with_an_ampersand_in_the_path_is_refused_on_windows(self) -> None:
        """No F-NNNN: ticket #17. The real cmd.exe does not get to read `R&D.txt` as a command."""
        shim = self.root / "fmt.cmd"
        shim.write_text("@echo ran> ran.marker\r\n", encoding="utf-8")
        self.configure(f'**/*.txt | "{shim}"')
        target = self.root / "R&D.txt"
        target.write_text("x", encoding="utf-8")
        code, err = run_hook(self.root, target)
        self.assertEqual(code, 2)
        self.assertIn("metacharacter", err)
        self.assertFalse((self.root / "ran.marker").exists())

    def test_a_delay_under_a_second_is_shown_rounded_up_never_as_zero(self) -> None:
        """No F-NNNN: ticket #17. The rest of a budget is 0.4 s, not 0 s."""
        command = self.script("fmt.py", "import time\ntime.sleep(30)\n")
        self.configure(f"**/*.txt | {command}")
        target = self.root / "a.txt"
        target.write_text("x", encoding="utf-8")
        with mock.patch.object(after_write, "COMMAND_TIMEOUT", 0.4):
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

    def test_a_cmd_shim_is_not_given_a_path_with_a_cmd_exe_metacharacter(self) -> None:
        """No F-NNNN: ticket #17. A `.cmd` goes through cmd.exe, where `&` would cut the command."""
        self.configure("**/*.txt | prettier --write")
        target = self.root / "R&D.txt"
        target.write_text("x", encoding="utf-8")
        with (
            mock.patch.object(after_write, "WINDOWS", True),
            mock.patch.object(after_write.shutil, "which", return_value="C:\\bin\\prettier.CMD"),
            mock.patch.object(after_write.subprocess, "Popen") as popen,
        ):
            code, err = run_hook(self.root, target)
        popen.assert_not_called()
        self.assertEqual(code, 2)
        self.assertEqual(
            err,
            "format-on-write: prettier --write failed on R&D.txt"
            " (not run: the path holds a cmd.exe metacharacter)\n",
        )

    def test_a_path_with_a_metacharacter_is_formatted_when_no_shell_is_involved(self) -> None:
        """No F-NNNN: ticket #17. Off Windows nothing changes: `&` is a plain character."""
        command = self.script("fmt.py", "import sys\nopen(sys.argv[1], 'a').write('!')\n")
        self.configure(f"**/*.txt | {command}")
        target = self.root / "R&D (1).txt"
        target.write_text("x", encoding="utf-8")
        self.assertEqual(run_hook(self.root, target), (0, ""))
        self.assertEqual(target.read_text(encoding="utf-8"), "x!")

    def test_an_os_error_other_than_a_missing_binary_has_its_own_form(self) -> None:
        """No F-NNNN: ticket #17. A permission error is not `command not found`."""
        self.configure("**/*.txt | fmt --write")
        target = self.root / "a.txt"
        target.write_text("x", encoding="utf-8")
        for error, reason in (
            (PermissionError(13, "Permission denied"), "could not start: Permission denied"),
            (FileNotFoundError(2, "No such file"), "command not found"),
            (OSError(), "could not start: OSError"),
        ):
            with (
                mock.patch.object(after_write.shutil, "which", return_value="/bin/fmt"),
                mock.patch.object(after_write.subprocess, "Popen", side_effect=error),
            ):
                code, err = run_hook(self.root, target)
            self.assertEqual(code, 2)
            self.assertEqual(err, f"format-on-write: fmt --write failed on a.txt ({reason})\n")

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
            "fmt.py", "import sys\nopen(sys.argv[1], 'w').write('clean')\n"
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


class OneRunner(unittest.TestCase):
    """F-0002 T4: `format-on-write` and `lint-on-write` (ticket 6) share one runner and deadline."""

    def test_the_module_keeps_no_public_runner_beside_main(self) -> None:
        """F-0002 T4.1: the runner and its helpers are private; `main` is the hook's entry."""
        kept_for_their_tests = {"em_dash_problem", "load_allowances", "parse_allowances"}
        public = {
            name
            for name, value in vars(after_write).items()
            if not name.startswith("_")
            and callable(value)
            and getattr(value, "__module__", None) == after_write.__name__
        }
        self.assertEqual(public - kept_for_their_tests, {"main"})

    def test_two_keys_run_through_one_runner_under_one_deadline(self) -> None:
        """F-0002 T4.2: the deadline of a write is spent across keys, not once per key."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "docs" / "agents").mkdir(parents=True)
            python = shlex.quote(Path(sys.executable).as_posix())
            slow = root / "slow.py"
            slow.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
            quick = root / "quick.py"
            quick.write_text("import sys\nopen(sys.argv[1], 'a').write('!')\n", encoding="utf-8")
            slow_command = f"{python} {shlex.quote(slow.as_posix())}"
            quick_command = f"{python} {shlex.quote(quick.as_posix())}"
            (root / "docs" / "agents" / "usine.md").write_text(
                f"- `format-on-write` : `**/*.txt | {slow_command}`\n"
                f"- `lint-on-write` : `**/*.txt | {quick_command}`\n",
                encoding="utf-8",
            )
            target = root / "a.txt"
            target.write_text("x", encoding="utf-8")
            config = after_write.load(root)
            deadline = after_write._Deadline()
            with (
                mock.patch.object(after_write, "COMMAND_TIMEOUT", 30),
                mock.patch.object(after_write, "TOTAL_TIMEOUT", 1),
            ):
                first = after_write._run_key(
                    "format-on-write", config, root, target, "a.txt", deadline
                )
                second = after_write._run_key(
                    "lint-on-write", config, root, target, "a.txt", deadline
                )
            self.assertEqual(
                first, [f"format-on-write: {slow_command} failed on a.txt (timed out after 1s)"]
            )
            self.assertEqual(
                second, [f"lint-on-write: {quick_command} failed on a.txt (timed out after 1s)"]
            )
            self.assertEqual(target.read_text(encoding="utf-8"), "x")


class _KeyedHook(unittest.TestCase):
    """A throwaway project whose `usine.md` holds the given keys, and scripts that print known output."""

    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        (self.root / "docs" / "agents").mkdir(parents=True)
        self.python = shlex.quote(Path(sys.executable).as_posix())
        self.target = self.root / "a.txt"
        self.target.write_text("x", encoding="utf-8")

    def configure(self, *entries: tuple[str, str]) -> None:
        text = "".join(f"- `{key}` : `{line}`\n" for key, line in entries)
        (self.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def script(self, name: str, body: str) -> str:
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        return f"{self.python} {shlex.quote(path.as_posix())}"

    def failing(self, body: str) -> str:
        """A command that runs `body`, then exits 1."""
        return self.script("tool.py", f"import sys\n{body}\nsys.exit(1)\n")


class OutputTail(_KeyedHook):
    """F-0002 A18, A19: the end of a failing tool's output reaches the agent, bounded."""

    def test_a_failing_formatter_relays_the_end_of_its_output(self) -> None:
        """F-0002 A19: `format-on-write` no longer throws the tool output away."""
        command = self.failing("print('E501 line too long')")
        self.configure(("format-on-write", f"**/*.txt | {command}"))
        code, err = run_hook(self.root, self.target)
        self.assertEqual(code, 2)
        self.assertEqual(
            err, f"format-on-write: {command} failed on a.txt (exit 1)\nE501 line too long\n"
        )
        self.assertEqual(self.target.read_text(encoding="utf-8"), "x")

    def relayed(self, body: str) -> list[str]:
        """The lines that follow the failure line of a formatter running `body`."""
        self.configure(("format-on-write", f"**/*.txt | {self.failing(body)}"))
        code, err = run_hook(self.root, self.target)
        self.assertEqual(code, 2)
        return err.splitlines()[1:]

    def test_at_most_the_last_20_lines_are_relayed(self) -> None:
        """F-0002 A18: 100 lines of output, the agent gets the last 20."""
        lines = self.relayed("for n in range(1, 101): print(f'line {n}')")
        self.assertEqual(lines, [f"line {n}" for n in range(81, 101)])

    def test_at_most_2000_bytes_are_relayed_the_end_kept(self) -> None:
        """F-0002 A18: 5 lines of 900 bytes, the agent gets the last 2000 bytes, not the first."""
        lines = self.relayed("for n in range(5): print(str(n) * 900)")
        relayed = "\n".join(lines)
        self.assertEqual(len(relayed.encode("utf-8")), 2000)
        self.assertTrue(relayed.endswith("4" * 900))
        self.assertNotIn("0", relayed)

    def test_the_byte_cap_never_cuts_a_character_in_two(self) -> None:
        """F-0002 A18: 1500 two-byte characters, the cut lands on a whole character."""
        # The child writes UTF-8 whatever the console code page is (cp1252 on Windows).
        lines = self.relayed("sys.stdout.reconfigure(encoding='utf-8')\nprint('\\u00e9' * 1500)")
        relayed = "\n".join(lines)
        self.assertLessEqual(len(relayed.encode("utf-8")), 2000)
        self.assertEqual(set(relayed), {"\u00e9"})


class RelayedOutputTemplate(unittest.TestCase):
    """F-0002 A18, A19, T1: the template says what the agent gets of a failing tool's output."""

    def test_the_template_says_the_tool_output_is_relayed_for_format_on_write(self) -> None:
        """F-0002 A18, A19: the 20 lines and 2000 bytes the agent gets after the failure line."""
        template = (support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8")
        self.assertIn("20 derni\u00e8res lignes", template)
        self.assertIn("2000 octets", template)


if __name__ == "__main__":
    unittest.main()
