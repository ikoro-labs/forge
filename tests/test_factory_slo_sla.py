"""factory_slo.py queue et sla : la file par gravité et les engagements de délai (ticket #60)."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import support  # noqa: F401  met les scripts sur le chemin d'import
from test_factory_slo import USINE, World, isolate, issue, pr

from factory_slo import compute, main

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
SLA = "- `sla` : `sev1 | 4 h | 24 h | 3 j`\n- `sla` : `sev2 | 2 j | 7 j | 14 j`\n"


def ticket(number: int, created: str, labels: tuple[str, ...] = ()) -> dict:
    return {"number": number, "createdAt": created, "labels": [{"name": name} for name in labels]}


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "vide"))
        self.world = World(Path(self.tmp.name))

    def configure(self, extra: str) -> None:
        (self.world.root / "docs" / "agents" / "usine.md").write_text(USINE + extra, encoding="utf-8")

    def run_main(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([args[0], str(self.world.root), *args[1:]], run=self.world.runner, now=NOW)
        return code, out.getvalue(), err.getvalue()


class Queue(Base):
    def setUp(self) -> None:
        super().setUp()
        self.world.answers = {
            "issue view 1 ": ticket(1, "2026-10-01T00:00:00Z", ("sev3",)),
            "issue view 2 ": ticket(2, "2026-10-02T00:00:00Z"),
            "issue view 3 ": ticket(3, "2026-10-03T00:00:00Z", ("sev2",)),
            "issue view 4 ": ticket(4, "2026-10-19T00:00:00Z", ("sev1",)),
            "issue view 5 ": ticket(5, "2026-10-02T00:00:00Z", ("sev2",)),
        }

    def test_the_queue_takes_the_tickets_by_severity_then_by_deadline(self) -> None:
        """Ticket #60, critère 3 : sev1 devant tout, puis sev2 par échéance, sev3, puis sans gravité."""
        self.configure(SLA)
        code, out, _ = self.run_main("queue", "1", "2", "3", "4", "5", "--json")
        self.assertEqual(code, 0)
        rows = json.loads(out)["file"]
        self.assertEqual([row["ticket"] for row in rows], [4, 5, 3, 1, 2])
        self.assertEqual(rows[0]["gravite"], "sev1")
        self.assertEqual(rows[0]["echeance"], "2026-10-19T04:00:00+00:00")
        self.assertEqual(rows[1]["echeance"], "2026-10-04T00:00:00+00:00")

    def test_the_markdown_queue_names_each_ticket_in_order(self) -> None:
        self.configure(SLA)
        _, out, _ = self.run_main("queue", "1", "2", "3", "4", "5")
        positions = [out.index(f"#{n}") for n in (4, 5, 3, 1, 2)]
        self.assertEqual(positions, sorted(positions))

    def test_without_the_sla_key_the_deadline_is_sans_objet_and_severity_still_sorts(self) -> None:
        """Ticket #60 : clé absente, « sans objet (clé `sla` absente) », aucune échéance devinée."""
        self.configure("")
        _, out, _ = self.run_main("queue", "1", "2", "3", "4", "5", "--json")
        document = json.loads(out)
        self.assertEqual([row["ticket"] for row in document["file"]], [4, 3, 5, 1, 2])
        self.assertTrue(all(row["echeance"] is None for row in document["file"]))
        self.assertIn("sans objet (clé `sla` absente)", document["echeances"])
        _, text, _ = self.run_main("queue", "1", "2")
        self.assertIn("sans objet (clé `sla` absente)", text)

    def test_a_malformed_key_fails_the_command(self) -> None:
        self.configure("- `sla` : `sev1 | 4 | 24 h | 3 j`\n")
        code, _, err = self.run_main("queue", "1")
        self.assertEqual(code, 1)
        self.assertIn("`sla`", err)


def assigned(when: str) -> dict:
    return {"event": "assigned", "created_at": when}


class Measure(Base):
    """Quatre tickets à l'instant NOW : un tenu puis dépassé, deux en retard ou en cours, un sans ligne."""

    def setUp(self) -> None:
        super().setUp()
        first = self.world.commit("avant", "2026-09-20T10:00:00Z")
        fixed = self.world.commit("fix: dix", "2026-10-02T06:00:00Z")
        self.world.git("tag", "-a", "-m", "v", "forge--v1.0.0", fixed, when="2026-10-03T00:00:00Z")
        self.world.answers = {
            "repo view": {"nameWithOwner": "o/r", "defaultBranchRef": {"name": "main"}},
            "pr list": [
                pr(100, "2026-10-01T05:00:00Z", state="MERGED", mergedAt="2026-10-02T06:00:00Z",
                   mergeCommit={"oid": fixed}, closingIssuesReferences=[{"number": 10}]),
                pr(99, "2026-09-19T00:00:00Z", state="MERGED", mergedAt="2026-09-20T10:00:00Z", mergeCommit={"oid": first}),
            ],
            "issue list --state all --label sev1": [issue(10, "2026-10-01T00:00:00Z", ("sev1", "escaped-defect"))],
            "issue list --state all --label sev2": [
                issue(11, "2026-10-10T00:00:00Z", ("sev2",)), issue(12, "2026-10-19T00:00:00Z", ("sev2",)),
            ],
            "issue list --state all --label sev3": [issue(13, "2026-10-12T00:00:00Z", ("sev3",))],
            "issue list": [],
            "api repos/{owner}/{repo}/issues/10/events": [assigned("2026-10-01T03:00:00Z")],
            "api repos/{owner}/{repo}/issues/11/events": [],
            "api repos/{owner}/{repo}/issues/12/events": [],
            "api repos/{owner}/{repo}/issues/13/events": [],
            "api repos/{owner}/{repo}/commits/": {"check_runs": []},
        }
        self.configure(SLA)

    def tickets(self, *extra: str) -> dict:
        code, out, err = self.run_main("sla", "--json", *extra)
        self.assertEqual(code, 0, err)
        return {item["ticket"]: item for item in json.loads(out)["tickets"]}

    def states(self, ticket: int, *extra: str) -> list[str]:
        return [stage["etat"] for stage in self.tickets(*extra)[ticket]["etapes"]]

    def test_a_deadline_is_the_opening_plus_the_delay_of_the_class(self) -> None:
        """Ticket #60, critère 4 : l'échéance de chaque étape se calcule depuis l'ouverture du ticket."""
        stages = self.tickets()[10]["etapes"]
        self.assertEqual(
            [stage["echeance"] for stage in stages],
            ["2026-10-01T04:00:00+00:00", "2026-10-02T00:00:00+00:00", "2026-10-04T00:00:00+00:00"],
        )

    def test_a_stage_reached_late_is_a_breach_and_the_others_are_held(self) -> None:
        """Ticket #60, critère 4 : pris en charge à temps, fusionné trop tard, publié à temps."""
        self.assertEqual(self.states(10), ["tenue", "dépassée", "tenue"])

    def test_a_deadline_passed_without_the_stage_is_a_breach(self) -> None:
        """Ticket #60, critère 4 : un sev2 ouvert le 10, jamais pris, est en retard au 20 ; son correctif publié ne l'est pas encore."""
        self.assertEqual(self.states(11), ["dépassée", "dépassée", "en cours"])
        self.assertEqual(self.states(12), ["en cours", "en cours", "en cours"])

    def test_a_class_without_a_line_is_sans_objet_with_its_reason(self) -> None:
        stages = self.tickets()[13]["etapes"]
        self.assertEqual({stage["etat"] for stage in stages}, {"sans objet"})
        self.assertIn("`sev3`", stages[0]["raison"])

    def test_the_markdown_lists_every_breach(self) -> None:
        _, out, _ = self.run_main("sla")
        self.assertIn("Dépassements", out)
        self.assertIn("#10 (sev1) : correctif fusionné", out)
        self.assertIn("#11 (sev2) : prise en charge", out)
        self.assertIn("#11 (sev2) : correctif fusionné", out)
        self.assertNotIn("#12 (sev2) :", out)

    def test_the_missing_key_is_sans_objet(self) -> None:
        """Ticket #60 : clé absente, « sans objet (clé `sla` absente) » et aucun ticket relu."""
        self.configure("")
        code, out, _ = self.run_main("sla")
        self.assertEqual(code, 0)
        self.assertIn("sans objet (clé `sla` absente)", out)
        self.assertNotIn("#10", out)

    def test_without_the_release_tag_key_the_published_stage_is_sans_objet(self) -> None:
        (self.world.root / "docs" / "agents" / "usine.md").write_text("# u\n" + SLA, encoding="utf-8")
        stage = self.tickets()[10]["etapes"][2]
        self.assertEqual(stage["etat"], "sans objet")
        self.assertIn("clé `release-tag` absente", stage["raison"])

    def test_a_closed_ticket_opened_before_the_window_is_left_out(self) -> None:
        old = issue(14, "2026-08-01T00:00:00Z", ("sev2",))
        old["state"] = "CLOSED"
        self.world.answers["issue list --state all --label sev2"].append(old)
        self.world.answers["api repos/{owner}/{repo}/issues/14/events"] = []
        self.assertNotIn(14, self.tickets())
        self.assertIn(14, self.tickets("--depuis", "2026-07-01"))

    def test_restore_time_is_split_by_the_severity_class(self) -> None:
        """Ticket #60, critère 4 : `restore-time` se ventile par `sev1`, `sev2`, `sev3`."""
        self.world.answers = {
            "issue list --state all --label escaped-defect": [issue(10, "2026-10-01T00:00:00Z", ("sev1", "escaped-defect"))],
            **self.world.answers,
        }
        since, until = datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 11, 1, tzinfo=timezone.utc)
        results = {item.name: item for item in compute(self.world.root, since, until, self.world.runner)}
        self.assertEqual(results["restore-time"].to_dict()["par_gravite"], {"sev1": {"echantillons": 1, "mediane_h": 30, "p90_h": 30}})

    def test_the_report_lists_each_breach_of_the_commitments(self) -> None:
        """Ticket #60, critère 4 : le rapport (#58) liste chaque dépassement des engagements de délai."""
        self.configure(SLA + "- `slo` : `accept-round-1 | >= 5 % | 31`\n")
        code, out, err = self.run_main("report")
        self.assertEqual(code, 0, err)
        section = out[out.index("Engagements de délai"):]
        for line in ("#10 (sev1) : correctif fusionné", "#11 (sev2) : prise en charge", "#11 (sev2) : correctif fusionné"):
            self.assertIn(line, section)
        self.assertNotIn("#12", section)
        _, as_json, _ = self.run_main("report", "--json")
        self.assertEqual(len(json.loads(as_json)["sla"]["depassements"]), 3)

    def test_the_report_without_the_sla_key_says_so(self) -> None:
        self.configure("- `slo` : `accept-round-1 | >= 5 % | 31`\n")
        _, out, _ = self.run_main("report")
        self.assertIn("Engagements de délai : sans objet (clé `sla` absente)", out)


if __name__ == "__main__":
    unittest.main()
