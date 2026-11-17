"""Ticket #61, part 2: `guard_coder` refuses a test suite the coder runs without the bounded launcher.

The seam is the guard's `refusal` function and its `main` entry point: a command goes in, a refusal
(or none) comes out. The configuration the guard reads (`ci-replay`, `red-replay`) is given as a
mapping or, through `main`, as a `docs/agents/usine.md` in a temporary project. Nothing here runs a
suite: the commands are only read.
"""

import io
import json
import os
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from unittest import mock

import support
from guard_coder import main, refusal

UNITTEST = "uv run --no-project --quiet python -m unittest discover -s tests"
BOUNDED = 'uv run --no-project --quiet python "/plugin/scripts/bounded_run.py" --'
CONFIG = {
    "ci-replay": [
        UNITTEST,
        "uv run --no-project --quiet --with ruff==0.17.3 ruff check plugins/forge tests",
        "uv run --no-project --quiet --with mypy==2.4.1 mypy",
        "claude plugin validate .",
        "make check",
    ],
    "red-replay": ["tox -e unit -- -k {name}"],
}


def bash(command: str, config: dict[str, list[str]] | None = None) -> str | None:
    return refusal("Bash", {"command": command}, config=config)


class SuiteWithoutBound(unittest.TestCase):
    def test_the_unittest_suite_is_refused_with_the_bounded_form(self) -> None:
        """Ticket #61, A1.1: `python -m unittest discover` run bare is refused, the form is given."""
        reason = bash(UNITTEST) or ""
        launcher = (support.PLUGIN / "scripts" / "bounded_run.py").resolve().as_posix()
        self.assertIn(f'python "{launcher}" -- ', reason)

    def test_pytest_is_refused_in_each_way_to_start_it(self) -> None:
        """Ticket #61, A1.2: `pytest -q` and its usual launchers are refused."""
        for command in [
            "pytest -q",
            "python -m pytest tests",
            "uv run pytest",
            "uv run --with pytest-cov pytest -q",
            ".venv/bin/pytest -x",
            "cd work && pytest",
            "timeout 900 pytest",
            "bash -c 'pytest -q'",
            "PYTHONPATH=src pytest",
            "python3 -m unittest",
        ]:
            with self.subTest(command=command):
                self.assertIsNotNone(bash(command))

    def test_a_line_of_ci_replay_or_red_replay_is_refused_with_its_arguments_changed(self) -> None:
        """Ticket #61, A1: the project's own lines count, a `{name}` placeholder matches any word."""
        for command in [
            "make check",
            "make check -j4",
            "cd work && make check",
            "tox -e unit -- -k test_guard",
        ]:
            with self.subTest(command=command):
                self.assertIsNotNone(bash(command, CONFIG))
        self.assertIsNone(bash("make check"))  # no configuration: only the named runners


class Allowed(unittest.TestCase):
    def test_the_bounded_launcher_wraps_the_suite(self) -> None:
        """Ticket #61, A2.1: the same commands pass through `bounded_run.py --`."""
        for suite in [UNITTEST.removeprefix("uv run --no-project --quiet "), "pytest -q", "make check"]:
            for prefix in [BOUNDED, "ulimit -v 2000000; timeout 900 " + BOUNDED]:
                with self.subTest(suite=suite, prefix=prefix):
                    self.assertIsNone(bash(f"{prefix} {suite}", CONFIG))

    def test_a_command_that_runs_no_suite_passes(self) -> None:
        """Ticket #61, A2.2: git, the lints and the plugin validation are not suites."""
        for command in [
            "git status",
            "git commit -m 'run pytest through bounded_run.py'",
            "ruff check plugins/forge tests",
            "uv run --no-project --quiet --with ruff==0.17.3 ruff check plugins/forge tests",
            "uv run --no-project --quiet --with mypy==2.4.1 mypy",
            "claude plugin validate .",
            "claude plugin validate plugins/forge",
            "pip install pytest",
            "uv add --dev pytest",
            "grep -rn pytest tests",
            "uv run --with pytest python script.py",
            "cat tests/unittest_notes.md",
        ]:
            with self.subTest(command=command):
                self.assertIsNone(bash(command, CONFIG))

    def test_only_the_coder_is_bound(self) -> None:
        """Ticket #61, A2.2: the main session, or any other agent, runs `pytest` freely."""
        call = {"tool_name": "Bash", "tool_input": {"command": "pytest -q"}}
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(self.run_main({**call, "agent_type": "forge:coder"}), 2)
            self.assertEqual(self.run_main(call), 0)
            self.assertEqual(self.run_main({**call, "agent_type": "forge:qc-gate"}), 0)

    @staticmethod
    def run_main(event: Mapping[str, object]) -> int:
        with mock.patch("sys.stdin", io.StringIO(json.dumps(event))):
            return main()


class ProjectConfiguration(unittest.TestCase):
    def test_main_reads_the_lines_of_the_project_usine(self) -> None:
        """Ticket #61, A1: `main` loads `docs/agents/usine.md` of the project and refuses its line."""
        with tempfile.TemporaryDirectory() as folder:
            usine = Path(folder) / "docs" / "agents" / "usine.md"
            usine.parent.mkdir(parents=True)
            usine.write_text("- `ci-replay` : `make check`\n", encoding="utf-8")
            event = {
                "agent_type": "forge:coder",
                "tool_name": "Bash",
                "tool_input": {"command": "make check"},
            }
            err = io.StringIO()
            with (
                mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": folder}),
                mock.patch("sys.stdin", io.StringIO(json.dumps(event))),
                mock.patch("sys.stderr", err),
            ):
                self.assertEqual(main(), 2)
            self.assertIn("bounded_run.py", err.getvalue())


if __name__ == "__main__":
    unittest.main()
