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


class GreenAtEveryCommit(unittest.TestCase):
    def test_a_pr_green_at_each_commit_passes_in_order(self) -> None:
        """No F-NNNN: ticket #69, critère 2: une PR verte à chaque commit rend une ligne PASS par commit, du plus ancien au plus récent."""
        repo = Replay(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        first = repo.commit({"code_under_test.py": CODE_V2, "tests/test_value.py": TEST_TWO})
        second = repo.commit({"notes.txt": "rien"})
        done = repo.commits(base, second, usine())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(
            [row[:2] for row in repo.rows(done)], [["PASS", first[:7]], ["PASS", second[:7]]], done.stdout
        )

    def test_a_commit_of_the_base_is_not_replayed(self) -> None:
        """No F-NNNN: ticket #69, critère 1: seuls les commits que la PR ajoute à la base sont rejoués."""
        repo = Replay(self)
        # The base is red (its test fails): only the commits of the PR are judged, from the merge base.
        repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": "", "tests/test_value.py": TEST_TWO})
        trunk = repo.git("branch", "--show-current")
        repo.git("switch", "-q", "-c", "pr")
        head = repo.commit({"code_under_test.py": CODE_V2})
        repo.git("switch", "-q", trunk)
        advanced = repo.commit({"autre.txt": "la base a avancé"})
        done = repo.commits(trunk, head, usine())
        self.assertEqual([row[:2] for row in repo.rows(done)], [["PASS", head[:7]]], done.stdout + done.stderr)
        self.assertNotIn(advanced[:7], done.stdout)


if __name__ == "__main__":
    unittest.main()
