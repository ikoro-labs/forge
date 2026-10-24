"""Ticket #43: `base_replay.py` replays the tests a PR adds on a copy of the base, where each must fail."""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support

SCRIPT = support.PLUGIN / "scripts" / "base_replay.py"

CODE_V1 = "def value():\n    return 1\n"
CODE_V2 = "def value():\n    return 2\n"
PASSING = (
    "import unittest\nimport code_under_test\n\n\nclass T(unittest.TestCase):\n"
    "    def test_value(self):\n        self.assertEqual(code_under_test.value(), 1)\n"
)
RED_ON_BASE = PASSING.replace("value(), 1", "value(), 2")
# `-t .` keeps the copy's root on the import path, as the project's own suite would.
REPLAY = f'"{sys.executable}" -m unittest discover -s tests -t . -p {{name}}'


class Repo:
    """A throwaway repository with a base commit and a head commit, isolated from the real HOME."""

    def __init__(self, test: unittest.TestCase) -> None:
        self.root = Path(tempfile.mkdtemp())
        test.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.work = self.root / "work"
        self.work.mkdir()
        self.scratch = self.root / "tmp"
        self.scratch.mkdir()
        self.env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "HOME": str(self.root),
            "USERPROFILE": str(self.root),
            "TMPDIR": str(self.scratch),
            "TEMP": str(self.scratch),
            "TMP": str(self.scratch),
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        self.git("init", "-q")

    def git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
            cwd=self.work, env=self.env, capture_output=True, text=True, check=True,
        )
        return done.stdout.strip()

    def commit(self, files: dict[str, str]) -> str:
        for name, text in files.items():
            target = self.work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "state")
        return self.git("rev-parse", "HEAD")

    def replay(self, base: str, head: str, usine: str, *extra: str) -> subprocess.CompletedProcess:
        (self.root / "usine-base.md").write_text(usine, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--base", base, "--head", head,
             "--usine", str(self.root / "usine-base.md"), *extra],
            cwd=self.work, env=self.env, capture_output=True, text=True, timeout=120,
        )


def usine(replay: str = REPLAY) -> str:
    return f"- `test-path` : `tests/`\n- `red-replay` : `{replay}`\n"


class RenderedWhenPassingOnTheBase(unittest.TestCase):
    def test_a_test_that_passes_on_the_base_is_rendered(self) -> None:
        """No F-NNNN: ticket #43, critère 1: un test qui passe sur la base est rendu."""
        repo = Repo(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        head = repo.commit({"tests/test_new.py": PASSING})
        done = repo.replay(base, head, usine())
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^PASSES\ttests/test_new\.py\t")

    def test_a_test_that_is_red_on_the_base_is_not_rendered(self) -> None:
        """No F-NNNN: ticket #43, critère 1: un test rouge sur la base ne l'est pas."""
        repo = Repo(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        head = repo.commit({"code_under_test.py": CODE_V2, "tests/test_new.py": RED_ON_BASE})
        done = repo.replay(base, head, usine())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("PASSES", done.stdout)
        self.assertRegex(done.stdout, r"(?m)^RED\ttests/test_new\.py\t")

    def test_a_red_line_says_the_grain_of_the_file(self) -> None:
        """No F-NNNN: ticket #43, décision du grain: un RED dit le fichier, pas que chaque test y est rouge."""
        repo = Repo(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        head = repo.commit({"code_under_test.py": CODE_V2, "tests/test_new.py": RED_ON_BASE})
        done = repo.replay(base, head, usine())
        self.assertRegex(done.stdout, r"(?m)^RED\ttests/test_new\.py\tcode \d+ \(grain du fichier")
        self.assertIn("un test qui passe à côté n'est pas vu", done.stdout)

    def test_the_tests_come_from_the_head_and_the_code_from_the_base(self) -> None:
        """No F-NNNN: ticket #43, critère 1: la copie est celle de la base, les tests posés sont ceux de la tête."""
        repo = Repo(self)
        base = repo.commit(
            {"code_under_test.py": CODE_V1, "tests/__init__.py": "", "tests/test_old.py": PASSING}
        )
        head = repo.commit({"code_under_test.py": CODE_V2, "tests/test_old.py": RED_ON_BASE})
        done = repo.replay(base, head, usine())
        self.assertRegex(done.stdout, r"(?m)^RED\ttests/test_old\.py\t")

    def test_only_files_under_a_test_path_are_replayed(self) -> None:
        """No F-NNNN: ticket #43, critère 1: seuls les fichiers sous test-path sont rejoués."""
        repo = Repo(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        head = repo.commit({"tests/test_new.py": PASSING, "other/test_elsewhere.py": PASSING})
        done = repo.replay(base, head, usine())
        self.assertNotIn("test_elsewhere", done.stdout)

    def test_no_test_added_or_changed_is_said_and_exits_zero(self) -> None:
        """No F-NNNN: ticket #43, critère 1: aucun test ajouté ni changé se dit, sans PASS."""
        repo = Repo(self)
        base = repo.commit({"code_under_test.py": CODE_V1})
        head = repo.commit({"code_under_test.py": CODE_V2})
        done = repo.replay(base, head, usine())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("aucun fichier de test ajouté ou changé", done.stdout)


class CleanupFailure(unittest.TestCase):
    def test_a_folder_that_cannot_be_deleted_does_not_lose_the_rows(self) -> None:
        """No F-NNNN: ticket #43, critère 4: un nettoyage qui échoue (WinError 32) ne perd pas les lignes du rejeu."""
        repo = Repo(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        head = repo.commit({"tests/test_new.py": PASSING})
        (repo.root / "usine-base.md").write_text(usine(), encoding="utf-8")
        sys.path.insert(0, str(SCRIPT.parent))
        self.addCleanup(sys.path.remove, str(SCRIPT.parent))
        import base_replay

        previous = Path.cwd()
        os.chdir(repo.work)
        self.addCleanup(os.chdir, previous)
        out = io.StringIO()
        with mock.patch("shutil.rmtree", side_effect=OSError("still held")), mock.patch("sys.stdout", out):
            code = base_replay.main(["--base", base, "--head", head, "--usine", str(repo.root / "usine-base.md")])
        self.assertEqual(code, 1, out.getvalue())
        self.assertRegex(out.getvalue(), r"(?m)^PASSES\ttests/test_new\.py\t")


class WithoutItsKeys(unittest.TestCase):
    def test_an_absent_key_is_sans_objet_and_runs_nothing(self) -> None:
        """No F-NNNN: ticket #43, critère 1: une clé absente rend « sans objet (clé <nom> absente) »."""
        repo = Repo(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        head = repo.commit({"tests/test_new.py": PASSING})
        only_path = repo.replay(base, head, "- `test-path` : `tests/`\n")
        self.assertEqual(only_path.returncode, 0)
        self.assertEqual(only_path.stdout.strip(), "sans objet (clé red-replay absente)")
        only_replay = repo.replay(base, head, f"- `red-replay` : `{REPLAY}`\n")
        self.assertEqual(only_replay.returncode, 0)
        self.assertEqual(only_replay.stdout.strip(), "sans objet (clé test-path absente)")
        neither = repo.replay(base, head, "")
        self.assertEqual(neither.stdout.strip(), "sans objet (clé test-path absente)")


class BoundedReplay(unittest.TestCase):
    """Ticket #43, critère 4: the replay runs test code against code that does not expect it."""

    def fixture(self) -> tuple[Repo, str, str]:
        repo = Repo(self)
        base = repo.commit({"code_under_test.py": CODE_V1, "tests/__init__.py": ""})
        return repo, base, repo.commit({"tests/test_new.py": PASSING})

    def command(self, source: str) -> str:
        # The file name is passed on so the command holds the `{name}` placeholder.
        return f'"{sys.executable}" -c "{source}" {{name}}'

    def test_a_command_over_its_delay_is_not_run_and_never_passes(self) -> None:
        """No F-NNNN: ticket #43, critère 4: un délai dépassé se rend NOT RUN avec sa commande."""
        repo, base, head = self.fixture()
        done = repo.replay(base, head, usine(self.command("import time; time.sleep(60)")), "--timeout", "2")
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^NOT RUN\ttests/test_new\.py\t.*time\.sleep.*délai de 2 s")
        self.assertNotIn("PASSES", done.stdout)

    @unittest.skipUnless(
        sys.platform == "linux" or os.name == "nt",
        "the memory limit is set with RLIMIT_AS on Linux and a job object on Windows; macOS is not covered",
    )
    def test_a_command_over_its_memory_limit_fails_instead_of_passing(self) -> None:
        """No F-NNNN: ticket #43, critère 4: la mémoire est bornée, la commande qui la dépasse échoue."""
        repo, base, head = self.fixture()
        # 700 MB asked, 400 MB allowed: without the limit this command exits 0.
        done = repo.replay(base, head, usine(self.command("bytearray(700 * 10**6)")), "--memory-mb", "400")
        self.assertNotIn("PASSES", done.stdout, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^RED\ttests/test_new\.py\t")

    def test_the_limits_have_defaults_and_are_documented(self) -> None:
        """No F-NNNN: ticket #43, critère 4: mémoire et délai ont une valeur par défaut, dite dans le script."""
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"--memory-mb", type=int, default=2000', text)
        self.assertIn('"--timeout", type=int, default=300', text)
        self.assertIn("Linux", text)
        self.assertIn("Windows", text)


if __name__ == "__main__":
    unittest.main()
