"""Ticket #69: `commit_replay.py` replays the suite on each commit of a PR, each in its own copy."""

import subprocess
import sys
import unittest

import support
from test_base_replay import CODE_V1, CODE_V2, Repo

SCRIPT = support.PLUGIN / "scripts" / "commit_replay.py"

# The suite of the throwaway project: its own tests, with the copy's root on the import path.
SUITE = f'"{sys.executable}" -m unittest discover -s tests -t .'
LIMITS = "- `run-limits` : `2000 | 120`\n"
TEST_TWO = (
    "import unittest\nimport code_under_test\n\n\nclass T(unittest.TestCase):\n"
    "    def test_value(self):\n        self.assertEqual(code_under_test.value(), 2)\n"
)


def usine(suite: str = SUITE, extra: str = "") -> str:
    return f"{LIMITS}- `ci-replay` : `{suite}`\n{extra}"


class Replay(Repo):
    """The throwaway repository, and the script launched on it."""

    def commits(self, base: str, head: str, config: str, *extra: str) -> subprocess.CompletedProcess:
        (self.root / "usine-base.md").write_text(config, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--base", base, "--head", head,
             "--usine", str(self.root / "usine-base.md"), *extra],
            cwd=self.work, env=self.env, capture_output=True, text=True, timeout=240,
        )

    def rows(self, done: subprocess.CompletedProcess) -> list[list[str]]:
        return [line.split("\t") for line in done.stdout.splitlines() if line.strip()]


class RedIntermediateCommit(unittest.TestCase):
    def test_a_red_commit_beside_a_green_head_is_a_row_of_its_own(self) -> None:
        """No F-NNNN: ticket #69, critère 1 et 2: un commit rouge pris seul est une ligne FAIL, la tête verte reste PASS."""
        repo = Replay(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        red = repo.commit({"tests/test_value.py": TEST_TWO})
        green = repo.commit({"code_under_test.py": CODE_V2})
        done = repo.commits(base, green, usine())
        rows = repo.rows(done)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in rows], [["FAIL", red[:7]], ["PASS", green[:7]]], done.stdout)
        # The end of the failing output, as the commit alone produced it.
        self.assertIn("AssertionError", rows[0][2])


if __name__ == "__main__":
    unittest.main()
