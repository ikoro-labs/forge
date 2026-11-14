"""No F-NNNN: ticket #102 : les indicateurs de la revue de bout en bout, calculés sans modèle.

The coverage of the matrix and the reintroduced gaps, added to the SLO report with a proposed SLO.
A review opens no ticket, so no indicator of the review reads tickets.
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import support
from factory_slo import compute, main, parse_slo, review_check
from test_factory_slo import SINCE, UNTIL, USINE, build, isolate

HEADER = "| Identifiant | Lot | Ticket | Test | Écran | Capture | État | Jugé le |\n|---|---|---|---|---|---|---|---|\n"
MATRICE = HEADER + (
    "| EXI-01 | L1 | #20 | t1 | Écran 1 | | tenu | 2026-10-09 |\n"
    "| EXI-02 | L1 | #21 | t2 | Écran 2 | | tenu | 2026-10-09 |\n"
    "| C01 | L2 | #21 | | Écran 2 | | partiel | 2026-10-09 |\n"
    "| EXI-03 | L2 | #22 | | | | absent | |\n"
)
JOURNAL = "\n".join(
    "\t".join(fields)
    for fields in [
        ("TOUR", "1", "EXI-01", "absent"), ("TOUR", "1", "EXI-02", "partiel"), ("TOUR", "1", "C01", "tenu"), ("TOUR", "1", "EXI-03", "absent"),
        ("CORRECTION", "#20", "EXI-01"),
        ("TOUR", "2", "EXI-01", "tenu"), ("TOUR", "2", "EXI-02", "partiel"), ("TOUR", "2", "C01", "absent"), ("TOUR", "2", "EXI-03", "absent"),
        ("CORRECTION", "#21", "EXI-02"),
        ("TOUR", "3", "EXI-01", "absent"), ("TOUR", "3", "EXI-02", "tenu"), ("TOUR", "3", "C01", "absent"), ("TOUR", "3", "EXI-03", "absent"),
    ]
) + "\n"
SLO = "review-regressions | <= 10 % | 30"
USINE_REVUE = USINE + "- `feature-dir` : `docs/features`\n"
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


class Revue(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.world = build(Path(self.tmp.name))
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "claude"))
        self.usine(USINE_REVUE)
        folder = self.world.root / "docs" / "features" / "0007-demo"
        (folder / "revue").mkdir(parents=True)
        (folder / "matrice.md").write_text(MATRICE, encoding="utf-8")
        (folder / "revue" / "boucle.tsv").write_text(JOURNAL, encoding="utf-8")

    def usine(self, text: str) -> None:
        (self.world.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def runner(self, cmd: list[str], cwd: Path) -> str:
        if cmd[:2] == ["gh", "api"] and cmd[2].endswith("/check-runs") and cmd[2] not in self.world.answers:
            return json.dumps({"check_runs": []})
        return self.world.runner(cmd, cwd)

    def sli(self, name: str) -> dict:
        results = compute(self.world.root, SINCE, UNTIL, self.runner)
        return {item.name: item for item in results}[name].to_dict()

    def report(self) -> str:
        out = io.StringIO()
        with redirect_stdout(out):
            main(["report", str(self.world.root)], run=self.runner, now=NOW)
        return out.getvalue()

    def test_a3_matrix_coverage(self) -> None:
        """No F-NNNN: ticket #102 A3 : la couverture de la matrice, lignes tenu ou écarté sur le total."""
        result = self.sli("matrix-coverage")
        self.assertEqual((result["numerateur"], result["denominateur"]), (2, 4))

    def test_a4_reintroduced_gaps(self) -> None:
        """No F-NNNN: ticket #102 A4 : un identifiant de nouveau non tenu après correction compte, sur ceux qui ont été un écart."""
        result = self.sli("review-regressions")
        self.assertEqual((result["numerateur"], result["denominateur"]), (1, 4))
        self.assertEqual(result["retours"], {"F-0007/EXI-01": 1})

    def test_a5_without_the_feature_dir_key_every_indicator_is_without_object(self) -> None:
        """No F-NNNN: ticket #102 A5 : sans la clé `feature-dir`, « sans objet (clé `feature-dir` absente) », jamais 0 ni 100 %."""
        self.usine(USINE)
        for name in ("matrix-coverage", "review-regressions"):
            result = self.sli(name)
            self.assertEqual(result["statut"], "sans objet", name)
            self.assertIn("clé `feature-dir` absente", result["raison"])

    def test_a5_a_missing_journal_is_without_object_for_the_regressions_only(self) -> None:
        """No F-NNNN: ticket #102 A5 : une feature sans journal n'a pas de retours à compter, et la couverture se lit encore."""
        (self.world.root / "docs" / "features" / "0007-demo" / "revue" / "boucle.tsv").unlink()
        self.assertEqual(self.sli("review-regressions")["statut"], "sans objet")
        self.assertEqual(self.sli("matrix-coverage")["numerateur"], 2)

    def test_a6_the_regressions_objective_is_proposed_and_valid(self) -> None:
        """No F-NNNN: ticket #102 A6 : l'objectif proposé sur les écarts réintroduits se lit comme une ligne de la clé `slo`."""
        self.assertEqual(parse_slo([SLO])[0].sli, "review-regressions")
        self.assertIn(SLO, (support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8"))

    def test_a7_the_report_shows_the_review_indicators(self) -> None:
        """No F-NNNN: ticket #102 A7 : le rapport des SLO porte la section de la revue de bout en bout."""
        self.usine(USINE_REVUE + f"- `slo` : `{SLO}`\n")
        text = self.report()
        self.assertIn("Revue de bout en bout", text)
        self.assertIn("50 % (2/4)", text)
        self.assertIn("`review-regressions`", text)
        self.assertIn("25 % (1/4)", text)

    def test_a7_the_report_says_so_when_the_key_is_absent(self) -> None:
        """No F-NNNN: ticket #102 A7 : sans `feature-dir`, la section du rapport dit la clé absente."""
        self.usine(USINE + f"- `slo` : `{SLO}`\n")
        self.assertIn("sans objet (clé `feature-dir` absente)", self.report())

    def test_a7_the_review_section_asks_nothing_of_github(self) -> None:
        """No F-NNNN: ticket #102 A7: the review section computes its two SLIs from the files alone, without any gh call."""
        calls: list[list[str]] = []

        def recording(cmd: list[str], cwd: Path) -> str:
            calls.append(cmd)
            return self.runner(cmd, cwd)

        document = review_check(self.world.root, NOW, recording)
        self.assertEqual([item["nom"] for item in document["indicateurs"]], ["matrix-coverage", "review-regressions"])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
