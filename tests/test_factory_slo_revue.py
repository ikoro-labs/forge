"""No F-NNNN: ticket #102 : les indicateurs de la revue de bout en bout, calculés sans modèle.

Les écarts par gravité et par passage, le délai d'un écart à sa fermeture, la couverture de la
matrice et les écarts réintroduits, ajoutés au rapport des SLO avec un SLO proposé.
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


def gap(number: int, created: str, closed: str | None, severity: str | None, covers: str) -> dict:
    return {
        "number": number, "title": f"Écart {number}", "state": "CLOSED" if closed else "OPEN",
        "createdAt": created, "closedAt": closed,
        "labels": [{"name": "ready-for-agent"}] + ([{"name": f"gravite:{severity}"}] if severity else []),
        "body": f"Couvre : {covers}\nFeature: F-0007\n",
    }


class Revue(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.world = build(Path(self.tmp.name))
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "claude"))
        self.world.answers["issue list"] = []
        self.tickets = [
            gap(20, "2026-10-05T00:00:00Z", "2026-10-06T06:00:00Z", "bloquant", "EXI-01"),
            gap(21, "2026-10-08T00:00:00Z", "2026-10-10T00:00:00Z", "majeur", "EXI-02, C01"),
            gap(22, "2026-10-12T00:00:00Z", None, "mineur", "EXI-03"),
            gap(23, "2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z", "bloquant", "EXI-09"),
            {"number": 24, "title": "Un ticket ordinaire", "state": "OPEN", "createdAt": "2026-10-09T00:00:00Z",
             "closedAt": None, "labels": [], "body": "Feature: F-0007\n"},
        ]
        self.usine(USINE_REVUE)
        folder = self.world.root / "docs" / "features" / "0007-demo"
        (folder / "revue").mkdir(parents=True)
        (folder / "matrice.md").write_text(MATRICE, encoding="utf-8")
        (folder / "revue" / "boucle.tsv").write_text(JOURNAL, encoding="utf-8")

    def usine(self, text: str) -> None:
        (self.world.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def runner(self, cmd: list[str], cwd: Path) -> str:
        if cmd[:3] == ["gh", "issue", "list"] and "--label" not in cmd:
            return json.dumps(self.tickets)
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

    def test_a1_gaps_by_severity_and_by_round(self) -> None:
        """No F-NNNN: ticket #102 A1 : les écarts par gravité (tickets de la fenêtre) et par passage (tours du journal)."""
        result = self.sli("review-gaps")
        self.assertEqual(result["par_gravite"], {"bloquant": 1, "majeur": 2, "mineur": 1})
        self.assertEqual(result["valeur"], 4)
        self.assertEqual(result["par_passage"]["1"], {"bloquant": 1, "majeur": 1, "mineur": 1})
        self.assertEqual(result["par_passage"]["2"], {"majeur": 2, "mineur": 1})
        self.assertEqual(result["par_passage"]["3"], {"bloquant": 1, "majeur": 1, "mineur": 1})

    def test_a1_a_gap_without_a_severity_label_is_counted_apart(self) -> None:
        """No F-NNNN: ticket #102 A1 : un ticket de la boucle sans étiquette de gravité s'appelle « sans gravité »."""
        self.tickets.append(gap(25, "2026-10-13T00:00:00Z", None, None, "EXI-04"))
        self.assertEqual(self.sli("review-gaps")["par_gravite"]["sans gravité"], 1)

    def test_a2_delay_from_a_gap_to_its_closing(self) -> None:
        """No F-NNNN: ticket #102 A2 : le délai de l'ouverture du ticket d'écart à sa fermeture, fermé dans la fenêtre."""
        result = self.sli("review-gap-lead-time")
        self.assertEqual((result["mediane_h"], result["p90_h"], result["echantillons"]), (39, 48, 2))

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
        for name in ("review-gaps", "review-gap-lead-time", "matrix-coverage", "review-regressions"):
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
        self.assertIn("bloquant 1", text)
        self.assertIn("50 % (2/4)", text)
        self.assertIn("`review-regressions`", text)
        self.assertIn("25 % (1/4)", text)

    def test_a7_the_report_says_so_when_the_key_is_absent(self) -> None:
        """No F-NNNN: ticket #102 A7 : sans `feature-dir`, la section du rapport dit la clé absente."""
        self.usine(USINE + f"- `slo` : `{SLO}`\n")
        self.assertIn("sans objet (clé `feature-dir` absente)", self.report())

    def test_a7_the_review_section_asks_for_the_issues_only(self) -> None:
        """No F-NNNN: ticket #102 A7 : la section de la revue ne calcule que ses quatre SLI, un seul `gh issue list`, ni PR ni événements."""
        calls: list[list[str]] = []

        def recording(cmd: list[str], cwd: Path) -> str:
            calls.append(cmd)
            return self.runner(cmd, cwd)

        document = review_check(self.world.root, NOW, recording)
        self.assertEqual(document["indicateurs"][0]["nom"], "review-gaps")
        self.assertEqual([cmd[:3] for cmd in calls], [["gh", "issue", "list"]])


if __name__ == "__main__":
    unittest.main()
