"""Ticket #61, part 3, A2: an option value never exempts a suite from the bounded launcher.

`NOT_A_RUN` (`sync`, `lock`, `add`...) exempts `uv add pytest`, where the word stands before the
suite name. After the suite name it is an argument of the suite (`-k sync`), not a subcommand.
The seam is the guard's `refusal` function: a command goes in, a refusal (or none) comes out.
"""

import unittest

import support
from guard_coder import refusal

BOUNDED = 'uv run --no-project --quiet python "/plugin/scripts/bounded_run.py" --'


def bash(command: str) -> str | None:
    return refusal("Bash", {"command": command}, config=None)


class OptionValue(unittest.TestCase):
    def test_a_word_of_not_a_run_after_pytest_does_not_exempt_the_suite(self) -> None:
        """Ticket #61 A2.1: `uv run pytest -k sync` is refused, the bounded form is given."""
        reason = bash("uv run pytest -k sync") or ""
        launcher = (support.PLUGIN / "scripts" / "bounded_run.py").resolve().as_posix()
        self.assertIn(f'python "{launcher}" -- ', reason)

    def test_a_word_of_not_a_run_after_unittest_does_not_exempt_the_suite(self) -> None:
        """Ticket #61 A2.2: `python -m unittest tests.test_x -k lock` is refused."""
        self.assertIsNotNone(bash("python -m unittest tests.test_x -k lock"))

    def test_the_other_values_and_launchers_are_refused_too(self) -> None:
        """Ticket #61 A2: `-k install`, `-m freeze`, a launcher in front, a value after `=`."""
        for command in [
            "pytest -k install",
            "pytest -k=show",
            "pytest -m freeze tests",
            "uv run --no-project pytest -k add",
            "timeout 900 python3 -m pytest -k remove",
            "python -m unittest -k pip",
        ]:
            with self.subTest(command=command):
                self.assertIsNotNone(bash(command))

    def test_the_bounded_form_passes(self) -> None:
        """Ticket #61 A2.3: `bounded_run.py -- uv run pytest -k sync` is allowed."""
        for suite in ["uv run pytest -k sync", "python -m unittest tests.test_x -k lock"]:
            with self.subTest(suite=suite):
                self.assertIsNone(bash(f"{BOUNDED} {suite}"))

    def test_a_word_of_not_a_run_before_the_suite_name_still_passes(self) -> None:
        """Ticket #61 A2: the exemption stays for what installs the suite instead of running it."""
        for command in [
            "pip install pytest",
            "python -m pip install pytest",
            "python3 -m pip install -U pytest pytest-cov",
            "uv add --dev pytest",
            "uv pip install pytest",
            "uv sync --with pytest",
            "uv remove pytest",
        ]:
            with self.subTest(command=command):
                self.assertIsNone(bash(command))


if __name__ == "__main__":
    unittest.main()
