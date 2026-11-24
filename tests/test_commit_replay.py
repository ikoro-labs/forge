"""Ticket #69: `commit_replay.py` replays the suite on each commit of a PR, each in its own copy."""

import re
import subprocess
import sys
import unittest
from pathlib import Path

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


# The lint of the throwaway project: it fails when `style.txt` holds ERROR.
LINT = f'"{sys.executable}" -c "import pathlib, sys; sys.exit(1 if \'ERROR\' in pathlib.Path(\'style.txt\').read_text() else 0)"'


def light_usine(light: bool = True) -> str:
    """The lint and the suite as `ci-replay`, the lint alone as `ci-replay-light` when `light`."""
    key = f"- `ci-replay-light` : `{LINT}`\n" if light else ""
    return f"{LIMITS}- `ci-replay` : `{LINT}`\n- `ci-replay` : `{SUITE}`\n{key}"


class LightReplay(unittest.TestCase):
    def fixture(self) -> tuple[Replay, str]:
        repo = Replay(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": "", "style.txt": "ok"})
        return repo, base

    def test_an_earlier_commit_replays_the_light_list_and_the_head_the_full_list(self) -> None:
        """No F-NNNN: ticket #331, A1 et A1.1: 3 commits, light = lint, une erreur de lint au commit 2 : FAIL au commit 2 seul."""
        repo, base = self.fixture()
        # The suite is red from commit 1 on: the light list skips it, so commit 1 passes.
        first = repo.commit({"tests/test_value.py": TEST_TWO})
        linted = repo.commit({"style.txt": "ERROR"})
        head = repo.commit({"code_under_test.py": CODE_V2, "style.txt": "ok"})
        done = repo.commits(base, head, light_usine())
        rows = repo.rows(done)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(
            [row[:2] for row in rows], [["PASS", first[:7]], ["FAIL", linted[:7]], ["PASS", head[:7]]], done.stdout
        )
        self.assertIn("style.txt", rows[1][2])

    def test_the_head_replays_every_ci_replay_command(self) -> None:
        """No F-NNNN: ticket #331, A1: la dernière ligne rejoue chaque commande de ci-replay, la suite comprise."""
        repo, base = self.fixture()
        first = repo.commit({"tests/test_value.py": TEST_TWO})
        head = repo.commit({"style.txt": "still ok"})
        done = repo.commits(base, head, light_usine())
        rows = repo.rows(done)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in rows], [["PASS", first[:7]], ["FAIL", head[:7]]], done.stdout)
        self.assertIn("AssertionError", rows[1][2])


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


class CopyNotExtracted(unittest.TestCase):
    def test_a_commit_whose_copy_cannot_be_extracted_is_not_run_and_never_passes(self) -> None:
        """No F-NNNN: ticket #69, critère 3: un commit dont la copie ne s'extrait pas est NOT RUN, jamais PASS, et les autres commits sont rejoués."""
        repo = Replay(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        first = repo.commit({"code_under_test.py": CODE_V2, "tests/test_value.py": TEST_TWO})
        broken = repo.commit({"notes.txt": "un objet qui va manquer"})
        repo.git("rm", "-q", "notes.txt")
        last = repo.commit({"autre.txt": "suite"})
        # Delete the loose object of `notes.txt` in the throwaway repository: `git archive` cannot read it.
        blob = repo.git("rev-parse", f"{broken}:notes.txt")
        loose = repo.work / ".git" / "objects" / blob[:2] / blob[2:]
        loose.chmod(0o600)
        loose.unlink()
        done = repo.commits(base, last, usine())
        rows = repo.rows(done)
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertEqual(
            [row[:2] for row in rows],
            [["PASS", first[:7]], ["NOT RUN", broken[:7]], ["PASS", last[:7]]],
            done.stdout,
        )
        self.assertIn("copie non extraite", rows[1][2])


def snapshot(folder: Path) -> dict[str, tuple[int, int]]:
    """Each file under `folder` with its size and modification time."""
    return {
        str(path.relative_to(folder)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(folder.rglob("*")) if path.is_file()
    }


class RepositoryLeftIntact(unittest.TestCase):
    def test_the_replayed_repository_and_its_configuration_are_not_written(self) -> None:
        """No F-NNNN: ticket #69, critère 4: rien n'est écrit dans le dépôt rejoué, sa configuration comprise, et les copies sont supprimées."""
        repo = Replay(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        repo.commit({"tests/test_value.py": TEST_TWO})
        head = repo.commit({"code_under_test.py": CODE_V2})
        before = snapshot(repo.work)
        config = (repo.work / ".git" / "config").read_bytes()
        done = repo.commits(base, head, usine())
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(snapshot(repo.work), before)
        self.assertEqual((repo.work / ".git" / "config").read_bytes(), config)
        # The copies live in the scratch folder the script was given as TMPDIR: none is left.
        self.assertEqual(list(repo.scratch.iterdir()), [])


class WithoutItsKeys(unittest.TestCase):
    def test_an_absent_key_is_sans_objet_and_runs_nothing(self) -> None:
        """No F-NNNN: ticket #69, critère 5: une clé absente rend « sans objet (clé <nom> absente) » et ne lance rien."""
        repo = Replay(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        head = repo.commit({"tests/test_value.py": TEST_TWO})
        no_replay = repo.commits(base, head, LIMITS)
        self.assertEqual((no_replay.returncode, no_replay.stdout.strip()), (0, "sans objet (clé ci-replay absente)"))
        no_limits = repo.commits(base, head, f"- `ci-replay` : `{SUITE}`\n")
        self.assertEqual((no_limits.returncode, no_limits.stdout.strip()), (0, "sans objet (clé run-limits absente)"))
        self.assertEqual(list(repo.scratch.iterdir()), [])

    def test_a_pr_without_commit_of_its_own_says_none(self) -> None:
        """No F-NNNN: ticket #69, critère 1: une tête qui est la base n'a aucun commit à rejouer, et le dit sans PASS."""
        repo = Replay(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        done = repo.commits(base, base, usine())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^NONE\t-\t")
        self.assertNotIn("PASS", done.stdout)


class Bounds(unittest.TestCase):
    def fixture(self) -> tuple[Replay, str, str]:
        repo = Replay(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        repo.commit({"code_under_test.py": CODE_V2})
        return repo, base, repo.commit({"notes.txt": "rien"})

    def test_a_post_out_of_budget_runs_nothing_and_every_commit_is_not_run(self) -> None:
        """No F-NNNN: ticket #69, critère 6: hors budget du poste, rien n'est lancé et chaque commit est NOT RUN avec la raison."""
        repo, base, head = self.fixture()
        marker = repo.root / "launched"
        suite = f'"{sys.executable}" -c "open(r\'{marker}\', \'w\').close()"'
        # A post with 10**9 MB available at least is never within budget; the wait is 0 s.
        done = repo.commits(base, head, usine(suite, "- `run-budget` : `1000000000 | 100000 | 2 | 0`\n"))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertEqual([row[0] for row in repo.rows(done)], ["NOT RUN", "NOT RUN"])
        self.assertIn("budget du poste non tenu", done.stdout)
        self.assertFalse(marker.exists(), "the suite was launched out of budget")

    def test_a_command_over_its_delay_is_not_run_and_never_passes(self) -> None:
        """No F-NNNN: ticket #69, critère 6: une suite qui dépasse le délai est NOT RUN avec sa commande, jamais PASS."""
        repo, base, head = self.fixture()
        suite = f'"{sys.executable}" -c "import time; time.sleep(60)"'
        done = repo.commits(base, head, usine(suite), "--timeout", "2")
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^NOT RUN\t\w+\t.*time\.sleep.*délai de 2 s")
        self.assertNotIn("PASS", done.stdout)

    def test_a_bad_run_budget_is_a_failed_call_never_a_pass(self) -> None:
        """No F-NNNN: ticket #69, critère 6: une clé run-budget invalide est un appel en échec, sans valeur devinée."""
        repo, base, head = self.fixture()
        done = repo.commits(base, head, usine(extra="- `run-budget` : `4096 | 12`\n"))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^NOT RUN\t-\t.*run-budget")


class EscapeHatches(unittest.TestCase):
    def test_each_noqa_of_the_script_carries_its_reason(self) -> None:
        """No F-NNNN: ticket #69, F-13: chaque noqa de commit_replay.py porte sa raison sur la même ligne."""
        bare = [
            line.strip() for line in SCRIPT.read_text(encoding="utf-8").splitlines()
            if "noqa" in line and not re.search(r"noqa: \w+\s+\S", line)
        ]
        self.assertEqual(bare, [])


if __name__ == "__main__":
    unittest.main()
