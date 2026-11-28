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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import support  # noqa: F401  met les scripts sur le chemin d'import
from factory_slo import main
from test_factory_slo import USINE, World, build, event, isolate, issue
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

    def test_a84_the_comment_names_the_repository_not_the_worktree_folder(self) -> None:
        """F-0003 A84 : lancé depuis un arbre de travail, le relevé nomme le dépôt, pas le dossier de l'arbre."""
        self.world.git("worktree", "add", "-q", "-b", "autre", str(self.folder / "arbre-jetable"))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["baseline", str(self.folder / "arbre-jetable")], run=self.world.runner, now=datetime(2026, 10, 31, tzinfo=timezone.utc))
        self.assertEqual((code, err.getvalue()), (0, ""))
        self.assertIn("pour `projet`", out.getvalue())

    def test_a84_decimals_are_written_with_a_comma(self) -> None:
        """F-0003 A84 : le texte est en français : 1,5 et non 1.5, pour le délai comme pour les interventions."""
        self.world.answers["pr list"][1]["mergedAt"] = "2026-10-03T10:30:00Z"  # le ticket 1 : 48 h 30
        code, out, _ = self.run_baseline("--depuis", "2026-10-01", "--jusqua", "2026-10-31")
        self.assertEqual(code, 0)
        self.assertIn("p90 48,5 h", out)

    def test_a84_the_window_must_end_after_it_starts(self) -> None:
        """F-0003 A84 : `--depuis` après `--jusqua` est refusé, sans appel à GitHub."""
        code, _, err = self.run_baseline("--depuis", "2026-10-31", "--jusqua", "2026-10-01")
        self.assertEqual(code, 1)
        self.assertIn("--jusqua", err)


class PointOfDecision(BaselineCase):
    """A85 : la règle du point de décision, sur la base d'octobre (p90 de 48 h, 1,67 intervention par ticket)."""

    def trial(self, lead_hours: int, attention: tuple[int, ...] = (1,)) -> None:
        """Ajoute en novembre une PR fusionnée par ticket, `lead_hours` heures après la pose de `ready-for-agent`.

        `attention` donne, pour chaque ticket, les étiquettes `needs-your-attention` posées ; les PR portent
        `agent-merged`, la fusion n'est donc pas une intervention.
        """
        moment = datetime(2026, 11, 5, tzinfo=timezone.utc) + timedelta(hours=lead_hours)
        for index, posed in enumerate(attention):
            pr_number, ticket = 20 + index, 30 + index
            self.world.answers["pr list"].append(
                {
                    "number": pr_number, "title": f"PR {pr_number}", "body": "", "state": "MERGED",
                    "createdAt": "2026-11-04T00:00:00Z", "mergedAt": moment.isoformat(), "closedAt": None,
                    "labels": [{"name": "agent-merged"}], "mergeCommit": None, "comments": [],
                    "closingIssuesReferences": [{"number": ticket}], "mergedBy": HUMAN,
                }
            )
            self.world.answers[f"api repos/{{owner}}/{{repo}}/issues/{ticket}/events"] = [
                event("ready-for-agent", "2026-11-05T00:00:00Z"),
                *[event(ATTENTION, "2026-11-05T01:00:00Z")] * posed,
            ]
            self.world.answers[f"api repos/{{owner}}/{{repo}}/issues/{pr_number}/events"] = []
        logs = self.folder / "claude" / "projects" / "p" / "t.jsonl"
        logs.write_text(line(self.world.root, "2026-11-06T10:00:00", message="essai", usage=(1, 10, 100, 5)), encoding="utf-8")

    def journal(self, *entries: dict) -> None:
        folder = self.folder / ".claude" / "hooks" / "state" / "dispatch"
        folder.mkdir(parents=True)
        (folder / "2026-11-10.jsonl").write_text("\n".join(json.dumps(item) for item in entries) + "\n", encoding="utf-8")

    def decide(self) -> dict:
        return self.document("--depuis", "2026-10-01", "--essai", "2026-11-01", "--le", "2026-11-30")

    def test_a85_yes_when_the_p90_drops_the_interventions_do_not_rise_and_no_h_gesture(self) -> None:
        """F-0003 A85 : p90 de 10 h contre 48 h, 1 intervention par ticket contre 1,67, aucun geste H : « oui »."""
        self.trial(lead_hours=10)
        self.journal({"date": "2026-11-10T10:00:00+00:00", "project": "projet", "event": "question", "case": "T2", "action": "post-default"})
        found = self.decide()
        self.assertEqual(found["verdict"], {"verdict": "oui", "raisons": []})
        self.assertEqual(found["essai"]["delai"]["p90_h"], 10)
        self.assertEqual(found["essai"]["interventions"]["valeur"], 1)
        self.assertEqual(found["base"]["jusqua"][:10], "2026-11-01")

    def test_a85_interventions_equal_to_the_base_do_not_rise(self) -> None:
        """F-0003 A85 : « ne montent pas » : 5 interventions sur 3 tickets, comme la base, et un p90 qui baisse : « oui »."""
        self.trial(lead_hours=10, attention=(2, 2, 1))
        found = self.decide()
        self.assertEqual(found["essai"]["interventions"]["valeur"], found["base"]["interventions"]["valeur"])
        self.assertEqual(found["verdict"]["verdict"], "oui")

    def test_a85_no_when_the_p90_does_not_drop(self) -> None:
        """F-0003 A85 : un p90 égal à celui de la base ne « baisse » pas : « non », avec sa raison."""
        self.trial(lead_hours=48)
        verdict = self.decide()["verdict"]
        self.assertEqual(verdict["verdict"], "non")
        self.assertEqual(len(verdict["raisons"]), 1)
        self.assertIn("délai p90", verdict["raisons"][0])

    def test_a85_no_when_the_interventions_per_ticket_rise(self) -> None:
        """F-0003 A85 : 2 interventions par ticket contre 1,67 : « non »."""
        self.trial(lead_hours=10, attention=(2,))
        verdict = self.decide()["verdict"]
        self.assertEqual(verdict["verdict"], "non")
        self.assertEqual(len(verdict["raisons"]), 1)
        self.assertIn("interventions", verdict["raisons"][0])

    def test_a85_no_when_an_h_case_gesture_is_in_the_question_journal(self) -> None:
        """F-0003 A85 : un `post-default` d'une case `H4` au journal des questions de l'essai : « non »."""
        self.trial(lead_hours=10)
        self.journal(
            {"date": "2026-11-10T10:00:00+00:00", "project": "projet", "event": "question", "case": "H4", "action": "post-default"},
            {"date": "2026-11-10T11:00:00+00:00", "project": "projet", "event": "question", "case": "H1", "action": "remind-human"},
        )
        verdict = self.decide()["verdict"]
        self.assertEqual(verdict["verdict"], "non")
        self.assertEqual(len(verdict["raisons"]), 1)
        self.assertIn("1 geste", verdict["raisons"][0])

    def test_a85_a_gesture_of_another_project_or_outside_the_trial_does_not_count(self) -> None:
        """F-0003 A85 : le journal est celui du poste : seules les lignes de ce projet et de la fenêtre de l'essai comptent."""
        self.trial(lead_hours=10)
        self.journal(
            {"date": "2026-11-10T10:00:00+00:00", "project": "autre", "event": "question", "case": "H4", "action": "post-default"},
            {"date": "2026-10-10T10:00:00+00:00", "project": "projet", "event": "question", "case": "H4", "action": "post-default"},
            {"date": "2026-11-10T10:00:00+00:00", "project": "projet", "event": "tick", "ready": 2},
        )
        self.assertEqual(self.decide()["verdict"]["verdict"], "oui")

    def test_a85_no_when_the_trial_has_no_measure(self) -> None:
        """F-0003 A85 : un essai sans ticket fusionné ne prouve rien : « non », avec la mesure sans objet dite."""
        verdict = self.decide()["verdict"]
        self.assertEqual(verdict["verdict"], "non")
        self.assertTrue(all("sans objet" in reason for reason in verdict["raisons"]))

    def test_a85_the_markdown_gives_both_windows_and_the_verdict(self) -> None:
        """F-0003 A85 : le texte donne la base, l'essai, le verdict."""
        self.trial(lead_hours=10)
        code, out, _ = self.run_baseline("--depuis", "2026-10-01", "--essai", "2026-11-01", "--le", "2026-11-30")
        self.assertEqual(code, 0)
        for text in ("Base : du 2026-10-01 au 2026-11-01", "Essai : du 2026-11-01 au 2026-11-30", "Point de décision : oui"):
            self.assertIn(text, out)

    def test_a85_the_trial_window_must_end_after_it_starts(self) -> None:
        """F-0003 A85 : `--le` avant `--essai` est refusé."""
        code, _, err = self.run_baseline("--essai", "2026-11-30", "--le", "2026-11-01")
        self.assertEqual(code, 1)
        self.assertIn("--le", err)


KEYS = """- `ticket-pr-cap` : `3`
- `ticket-pr-cap-small` : `50`
- `ticket-pr-cap-exempt` : `chore(pin)`
"""
SIZE_KEY = "- `ticket-size-max` : `1000`\n"


def cited_pr(number: int, body: str, state: str = "MERGED", title: str = "feat(x): y", lines: int = 200) -> dict:
    return {
        "number": number, "title": title, "body": body, "state": state, "createdAt": "2026-10-21T00:00:00Z",
        "mergedAt": None, "closedAt": None, "labels": [], "mergeCommit": None, "comments": [],
        "closingIssuesReferences": [], "additions": lines, "deletions": 0,
    }


def configure(world: World, keys: str) -> None:
    """Réécrit `usine.md` : la base du monde, la clé de l'humain, puis `keys` (rien n'est commité)."""
    usine = world.root / "docs" / "agents" / "usine.md"
    usine.write_text(USINE + "- `accepting-human` : `Kevin | kevin-h`\n" + keys, encoding="utf-8")


class UncommittedKey(BaselineCase):
    def test_a86_a_key_in_no_commit_has_no_date_so_it_is_not_applicable(self) -> None:
        """F-0003 A86 : une clé écrite mais jamais commitée n'a pas de date : « sans objet », pas un compte faux."""
        configure(self.world, KEYS + SIZE_KEY)
        found = self.document("--depuis", "2026-10-01", "--jusqua", "2026-10-31")["taille"]
        self.assertEqual(found["statut"], "sans objet")
        self.assertIn("aucun commit", found["raison"])


class SizeCap(BaselineCase):
    """A86 : les tickets publiés après la clé `ticket-size-max` qui ont atteint le plafond de PR (cible 0)."""

    def setUp(self) -> None:
        super().setUp()
        self.configure(KEYS + SIZE_KEY)
        self.world.commit("chore: ticket-size-max", "2026-10-15T00:00:00Z")
        after, before = "2026-10-20T00:00:00Z", "2026-10-01T00:00:00Z"
        self.world.answers["issue list"] = [issue(number, after) for number in (50, 60, 80, 90, 100)] + [issue(70, before)]
        for item in self.world.answers["pr list"]:
            item.update(additions=100, deletions=0)
        self.world.answers["pr list"] += [
            *[cited_pr(n, "Refs #50") for n in (51, 52, 53)],  # trois PR comptées : le plafond
            *[cited_pr(n, "Refs #60") for n in (61, 62)],  # deux : sous le plafond
            *[cited_pr(n, "Refs #70") for n in (71, 72, 73)],  # ticket publié avant la clé
            *[cited_pr(n, "Refs #80") for n in (81, 82)], cited_pr(83, "Refs #80", title="chore(pin): bump forge"),
            *[cited_pr(n, "Refs #90") for n in (91, 92)], cited_pr(93, "Refs #90", lines=10),
            *[cited_pr(n, "Refs #100") for n in (101, 102)], cited_pr(103, "Refs #100", state="CLOSED"),
        ]

    def configure(self, keys: str) -> None:
        configure(self.world, keys)

    def size(self) -> dict:
        return self.document("--depuis", "2026-10-01", "--jusqua", "2026-10-31")["taille"]

    def test_a86_counts_the_tickets_published_after_the_key_that_reached_the_cap(self) -> None:
        """F-0003 A86 : seul le ticket 50, publié après la clé, a trois PR : un ticket au plafond, cible 0."""
        found = self.size()
        self.assertEqual((found["numerateur"], found["tickets"], found["cap"]), (1, [50], 3))
        self.assertEqual(found["depuis"][:10], "2026-10-15")

    def test_a86_the_denominator_is_the_tickets_published_since_with_a_counted_pr(self) -> None:
        """F-0003 A86 : 50, 60, 80, 90 et 100 sont publiés après la clé et ont une PR comptée ; 70 est antérieur."""
        self.assertEqual(self.size()["denominateur"], 5)

    def test_a86_an_exempt_title_a_small_pr_and_a_closed_pr_do_not_count_toward_the_cap(self) -> None:
        """F-0003 A86 : comme `guard_pr_cap` : `chore(pin)`, une PR sous 50 lignes et une PR fermée sans fusion ne comptent pas."""
        self.assertNotIn(80, self.size()["tickets"])
        self.assertNotIn(90, self.size()["tickets"])
        self.assertNotIn(100, self.size()["tickets"])

    def test_a86_zero_tickets_at_the_cap_is_a_count_not_a_missing_measure(self) -> None:
        """F-0003 A86 : sans ticket au plafond, le relevé rend 0 sur son dénominateur, la cible tenue."""
        self.configure(KEYS.replace("`3`", "`4`") + SIZE_KEY)
        found = self.size()
        self.assertEqual((found["statut"], found["numerateur"], found["tickets"]), ("calculé", 0, []))

    def test_a86_without_the_size_key_it_is_not_applicable_never_zero(self) -> None:
        """F-0003 A86 : sans la clé `ticket-size-max`, « sans objet (clé `ticket-size-max` absente) »."""
        self.configure(KEYS)
        found = self.size()
        self.assertEqual(found["statut"], "sans objet")
        self.assertIn("clé `ticket-size-max` absente", found["raison"])

    def test_a86_without_the_cap_key_it_is_not_applicable(self) -> None:
        """F-0003 A86 : sans la clé `ticket-pr-cap`, « sans objet (clé `ticket-pr-cap` absente) »."""
        self.configure(SIZE_KEY)
        self.assertIn("clé `ticket-pr-cap` absente", self.size()["raison"])

    def test_a86_the_markdown_says_the_count_and_the_target(self) -> None:
        """F-0003 A86 : le texte du relevé dit le compte, le plafond et la cible 0."""
        code, out, _ = self.run_baseline("--depuis", "2026-10-01", "--jusqua", "2026-10-31")
        self.assertEqual(code, 0)
        self.assertIn("Tickets publiés après `ticket-size-max` au plafond de 3 PR : 1 (cible 0), #50", out)


if __name__ == "__main__":
    unittest.main()
