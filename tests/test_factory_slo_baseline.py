"""F-0003, story 18 : `factory_slo.py baseline` relève la base avant le répartiteur (ticket #405).

La couture est celle du script lancé par `main(argv, run)` : un faux `gh` rend des réponses figées, un dépôt git
jetable tient les commits, un `HOME` jetable tient les journaux de jetons et des questions. Le monde de
`test_factory_slo.py` donne trois PR fusionnées en octobre (#10, #11, #13) qui ferment les tickets 1, 2 et 4.
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support  # noqa: F401  met les scripts sur le chemin d'import
from factory_slo import main
from test_factory_slo import World, build, event, isolate
from test_token_audit import line

ATTENTION = "needs-your-attention"
HUMAN = {"login": "kevin-h"}
AGENT = {"login": "ikoro-agent"}


def baseline_world(folder: Path) -> World:
    """Le monde d'octobre, avec ses interventions : étiquettes sur les tickets et les PR, fusions."""
    world = build(folder)
    prs = {item["number"]: item for item in world.answers["pr list"]}
    prs[10].update(mergedBy=HUMAN, labels=[{"name": "agent-merged"}])  # fusionnée par l'agent, sous le compte de l'humain
    prs[11].update(mergedBy=HUMAN)  # fusionnée par l'humain : une intervention
    prs[13].update(mergedBy=AGENT)
    world.answers.update(
        {
            "api repos/{owner}/{repo}/issues/1/events": [
                event("ready-for-agent", "2026-10-01T10:00:00Z"),
                event(ATTENTION, "2026-10-02T10:00:00Z"),
            ],
            "api repos/{owner}/{repo}/issues/2/events": [
                event("ready-for-agent", "2026-10-05T10:00:00Z"),
                event(ATTENTION, "2026-10-05T12:00:00Z"),
                event(ATTENTION, "2026-10-05T15:00:00Z"),
            ],
            "api repos/{owner}/{repo}/issues/10/events": [event(ATTENTION, "2026-10-03T08:00:00Z")],
            "api repos/{owner}/{repo}/issues/11/events": [],
            "api repos/{owner}/{repo}/issues/13/events": [],
        }
    )
    usine = world.root / "docs" / "agents" / "usine.md"
    usine.write_text(usine.read_text(encoding="utf-8") + "- `accepting-human` : `Kevin | kevin-h`\n", encoding="utf-8")
    return world


class BaselineCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.world = baseline_world(self.folder)
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(self.folder / "claude"))
        logs = self.folder / "claude" / "projects" / "p"
        logs.mkdir(parents=True)
        calls = [line(self.world.root, "2026-10-10T10:00:00", message=f"m{n}", usage=(1, 10, 100, 5)) for n in range(3)]
        (logs / "s.jsonl").write_text("\n".join(calls), encoding="utf-8")

    def run_baseline(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["baseline", str(self.world.root), *args], run=self.world.runner)
        return code, out.getvalue(), err.getvalue()

    def document(self, *args: str) -> dict:
        code, out, err = self.run_baseline("--json", *args)
        self.assertEqual((code, err), (0, ""))
        return json.loads(out)


class BaseWindow(BaselineCase):
    def test_a84_the_p90_lead_time_with_its_window_and_its_denominator(self) -> None:
        """F-0003 A84 : le délai p90 de la base, sa fenêtre de 30 jours et les tickets qu'il compte."""
        base = self.document("--depuis", "2026-10-01", "--jusqua", "2026-10-31")["base"]
        self.assertEqual((base["depuis"][:10], base["jusqua"][:10]), ("2026-10-01", "2026-10-31"))
        delay = base["delai"]
        self.assertEqual((delay["p90_h"], delay["echantillons"], delay["sans_evenement"]), (48, 2, 1))

    def test_a84_the_window_defaults_to_the_30_days_before_the_end(self) -> None:
        """F-0003 A84 : sans `--depuis`, la base couvre les 30 jours qui précèdent `--jusqua`."""
        base = self.document("--jusqua", "2026-10-31")["base"]
        self.assertEqual((base["depuis"][:10], base["jours"]), ("2026-10-01", 30))

    def test_a84_interventions_per_merged_ticket_are_labels_plus_human_merges(self) -> None:
        """F-0003 A84 (section 22) : 4 étiquettes posées (tickets 1 et 2, PR #10) et 1 fusion par l'humain (#11) sur 3 tickets."""
        found = self.document("--depuis", "2026-10-01", "--jusqua", "2026-10-31")["base"]["interventions"]
        self.assertEqual((found["numerateur"], found["denominateur"], found["valeur"]), (5, 3, 1.67))
        self.assertEqual((found["etiquettes"], found["fusions_humain"]), (4, 1))

    def test_a84_a_merge_the_agent_labelled_is_not_a_human_merge(self) -> None:
        """F-0003 A84 : #10 est fusionnée sous le compte de l'humain mais porte `agent-merged` : elle ne compte pas."""
        found = self.document("--depuis", "2026-10-01", "--jusqua", "2026-10-31")["base"]["interventions"]
        self.assertEqual(found["fusions_humain"], 1)

    def test_a84_tokens_per_pr_with_their_denominator(self) -> None:
        """F-0003 A84 : les jetons par PR fusionnée, par `token_audit.py`, sur la même fenêtre."""
        found = self.document("--depuis", "2026-10-01", "--jusqua", "2026-10-31")["base"]["jetons"]
        self.assertEqual((found["jetons"], found["denominateur"], found["valeur"]), (348, 3, 116))

    def test_a84_the_markdown_comment_names_each_window_and_denominator(self) -> None:
        """F-0003 A84 : le texte à poster sur #340 dit, pour chaque mesure, sa fenêtre et son dénominateur."""
        code, out, _ = self.run_baseline("--depuis", "2026-10-01", "--jusqua", "2026-10-31")
        self.assertEqual(code, 0)
        self.assertIn("2026-10-01", out)
        self.assertIn("2026-10-31", out)
        self.assertIn("p90 48", out)
        self.assertIn("2 tickets", out)
        self.assertIn("1,67 par ticket fusionné (5/3)", out)
        self.assertIn("116 jetons par PR fusionnée (348/3)", out)

    def test_a84_without_a_human_key_the_human_merges_are_not_applicable_never_zero(self) -> None:
        """F-0003 A84 : sans la clé `accepting-human`, les fusions de l'humain sont « sans objet », pas 0."""
        usine = self.world.root / "docs" / "agents" / "usine.md"
        usine.write_text(usine.read_text(encoding="utf-8").replace("- `accepting-human` : `Kevin | kevin-h`\n", ""), encoding="utf-8")
        found = self.document("--depuis", "2026-10-01", "--jusqua", "2026-10-31")["base"]["interventions"]
        self.assertEqual((found["numerateur"], found["etiquettes"]), (4, 4))
        self.assertIn("accepting-human", found["fusions_humain"])

    def test_a84_an_empty_window_is_not_applicable_never_zero(self) -> None:
        """F-0003 A84 : une fenêtre sans ticket fusionné rend « sans objet » avec sa raison."""
        base = self.document("--depuis", "2026-07-01", "--jusqua", "2026-07-31")["base"]
        for name in ("delai", "interventions", "jetons"):
            self.assertEqual(base[name]["statut"], "sans objet", name)
            self.assertTrue(base[name]["raison"], name)

    def test_a84_the_window_must_end_after_it_starts(self) -> None:
        """F-0003 A84 : `--depuis` après `--jusqua` est refusé, sans appel à GitHub."""
        code, _, err = self.run_baseline("--depuis", "2026-10-31", "--jusqua", "2026-10-01")
        self.assertEqual(code, 1)
        self.assertIn("--jusqua", err)


if __name__ == "__main__":
    unittest.main()
