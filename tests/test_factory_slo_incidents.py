"""Ticket #61, critère 5 : `factory_slo.py incidents` compte les revues d'incident par classe.

Le décompte lit le dossier de la clé `incident-dir` et rien d'autre : aucun appel à GitHub.
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support  # noqa: F401  met les scripts sur le chemin d'import
from factory_slo import main
from test_factory_slo import isolate
from test_incident import review


def no_github(cmd: list[str], cwd: Path) -> str:
    raise AssertionError(f"le décompte des incidents n'appelle rien : {cmd}")


class Incidents(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate(self, self.tmp.name)
        self.root = Path(self.tmp.name) / "projet"
        (self.root / "docs" / "agents").mkdir(parents=True)

    def configure(self, text: str = "- `incident-dir` : `docs/incidents`\n") -> None:
        (self.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def add(self, name: str, text: str) -> None:
        folder = self.root / "docs" / "incidents"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")

    def run_main(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["incidents", str(self.root), *args], run=no_github)
        return code, out.getvalue(), err.getvalue()

    def test_the_reviews_are_counted_by_class(self) -> None:
        """Ticket #61, critère 5 : deux revues mécaniques et une de jugement."""
        self.configure()
        self.add("2026-10-24-a.md", review("mécanique", ("#64",)))
        self.add("2026-10-24-b.md", review("mecanique", ("#65",)))
        self.add("2026-10-25-c.md", review("jugement", ("cas : evals/x",)))
        (self.root / "evals" / "x").mkdir(parents=True)
        code, out, _ = self.run_main("--json")
        self.assertEqual(code, 0)
        document = json.loads(out)
        self.assertEqual(document["total"], 3)
        self.assertEqual(document["classes"], {"mécanique": 2, "jugement": 1})
        self.assertEqual(document["refusees"], [])

    def test_the_table_says_each_class_and_the_total(self) -> None:
        """Ticket #61, critère 5 : sans `--json`, un tableau Markdown par classe."""
        self.configure()
        self.add("2026-10-24-a.md", review("mécanique", ("#64",)))
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertRegex(out, r"\| mécanique \| 1 \|")
        self.assertRegex(out, r"\| jugement \| 0 \|")
        self.assertIn("1 revue", out)

    def test_a_class_without_a_review_counts_zero_not_sans_objet(self) -> None:
        """Ticket #61, critère 5 : une classe sans revue vaut 0 quand le dossier existe."""
        self.configure()
        self.add("2026-10-24-a.md", review("mécanique", ("#64",)))
        _, out, _ = self.run_main("--json")
        self.assertEqual(json.loads(out)["classes"]["jugement"], 0)

    def test_a_refused_review_is_not_counted_and_fails_the_command(self) -> None:
        """Ticket #61, critère 5 : une revue sans correctif n'est comptée dans aucune classe, et le dit."""
        self.configure()
        self.add("2026-10-24-a.md", review("mécanique", ("#64",)))
        self.add("2026-10-24-sans.md", review("jugement", ()))
        code, out, _ = self.run_main("--json")
        self.assertEqual(code, 1)
        document = json.loads(out)
        self.assertEqual(document["classes"], {"mécanique": 1, "jugement": 0})
        self.assertEqual([item["fichier"] for item in document["refusees"]], ["2026-10-24-sans.md"])
        self.assertTrue(any("correctif" in error for error in document["refusees"][0]["erreurs"]))

    def test_a_readme_is_not_a_review(self) -> None:
        """Ticket #61, critère 5 : le `README.md` du dossier n'est pas une revue."""
        self.configure()
        self.add("README.md", "# Les revues d'incident\n")
        self.add("2026-10-24-a.md", review("mécanique", ("#64",)))
        code, out, _ = self.run_main("--json")
        self.assertEqual((code, json.loads(out)["total"]), (0, 1))

    def test_a_folder_that_does_not_exist_yet_holds_no_review(self) -> None:
        """Ticket #61, critère 5 : la clé est déclarée, aucun incident n'a encore de revue."""
        self.configure()
        code, out, _ = self.run_main("--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["total"], 0)

    def test_without_the_key_the_count_is_sans_objet(self) -> None:
        """Ticket #61, critère 5 : sans `incident-dir`, « sans objet (clé `incident-dir` absente) », jamais 0."""
        self.configure("- `merge-method` : `merge`\n")
        self.add("2026-10-24-a.md", review("mécanique", ("#64",)))
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("sans objet (clé `incident-dir` absente)", out)
        code, out, _ = self.run_main("--json")
        self.assertEqual(json.loads(out), {"incident-dir": "sans objet (clé `incident-dir` absente)"})

    def test_a_key_that_cannot_be_used_fails_with_its_reason(self) -> None:
        """Ticket #61, critère 5 : une clé qui sort du dépôt fait échouer le décompte."""
        self.configure("- `incident-dir` : `../dehors`\n")
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("incident-dir", err)

    def test_the_paths_a_fix_cites_are_checked_against_the_project(self) -> None:
        """Ticket #61, critère 5 : un correctif qui cite un fichier absent du dépôt est refusé, donc non compté."""
        self.configure()
        self.add("2026-10-24-a.md", review("mécanique", ("existant : absent.py ; tests/test_absent.py",)))
        code, out, _ = self.run_main("--json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["total"], 0)


if __name__ == "__main__":
    unittest.main()
