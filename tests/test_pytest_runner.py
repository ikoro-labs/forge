"""Ticket #43, last part: this repository runs its suite with a pinned `pytest`, for running tests only.

Hooks and scripts stay on the standard library; the tests stay `unittest` classes. The pytest runner is
what lets `red-replay` carry `{report}` (a JUnit XML report), so the base replay judges each test.
"""

import re
import unittest
from pathlib import Path

import support
from usine import load

PIN = re.compile(r"--with pytest==(\d+\.\d+\.\d+)(?= )")
SUITE = re.compile(r"uv run --no-project --quiet --with pytest==\d+\.\d+\.\d+ python -m pytest tests")


def read(*parts: str) -> str:
    return support.REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8")


class TheSuiteRunsUnderPytest(unittest.TestCase):
    def test_every_place_that_names_the_suite_names_the_same_pinned_pytest_command(self) -> None:
        """F-0043 A1.1: CI workflow, CLAUDE.md, the rules and `ci-replay` run `pytest tests`, one pin."""
        config = load(support.REPO_ROOT)
        places = {
            "workflow": read(".github", "workflows", "tests.yml"),
            "CLAUDE.md": read("CLAUDE.md"),
            "rules": read(".claude", "rules", "forge.md"),
            "ci-replay": "\n".join(config["ci-replay"]),
        }
        pins = set()
        for name, text in places.items():
            with self.subTest(name):
                self.assertRegex(text, SUITE)
                self.assertNotIn("unittest discover", text)
                pins.update(PIN.findall(text))
        self.assertEqual(len(pins), 1, f"one pinned version, got {sorted(pins)}")

    def test_the_trimmed_command_still_names_the_suite(self) -> None:
        """F-0043 A1.1: the hook that shortens a passing run keeps naming the command of the suite."""
        config = load(support.REPO_ROOT)
        self.assertEqual(config["trimmed-command"], ["python -m pytest tests"])


class TheBaseReplayJudgesEachTest(unittest.TestCase):
    def test_red_replay_writes_a_junit_report_by_the_same_pinned_pytest(self) -> None:
        """F-0043 A2.1: `{file}` is run by pytest with `--junitxml={report}`, the pin of the suite."""
        config = load(support.REPO_ROOT)
        self.assertEqual(len(config["red-replay"]), 1)
        command = config["red-replay"][0]
        self.assertRegex(command, r"python -m pytest \{file\} --junitxml=\{report\}$")
        self.assertEqual(PIN.findall(command), PIN.findall(config["ci-replay"][0]))

    def test_the_replay_hands_the_report_path_to_the_declared_command(self) -> None:
        """F-0043 A2.1: the placeholders of the declared key are all replaced by the base replay."""
        import base_replay

        template = load(support.REPO_ROOT)["red-replay"][0]
        command = base_replay.command_for(template, "tests/test_x.py", Path("/tmp/report.xml"))
        self.assertIn("--junitxml=", command)
        self.assertIn("report.xml", command)
        self.assertNotIn("{", command)


if __name__ == "__main__":
    unittest.main()
