"""#260 A1, A2: a question left unanswered past `question-default-delay` is decided by default where
the matrix allows, and stays with the human where it does not. `gh` is simulated."""

import io
import json
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import support
from question_delay import main as question_delay_main

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)

DECIDED = """VERDICT: DECIDED
QUESTION: Which wording for the label?
DECISION: Call it `needs info`.
GROUND: docs/agents/decisions.md:34 `P1` the wording of a label
MATRIX_CELL: P1
USER_IMPACT: none
VETO: no
REFERENTIAL_UPDATE: none
WRITE_TO: ticket comment
READ: CLAUDE.md
"""
STAFF = DECIDED.replace("USER_IMPACT: none\n", "REVERSIBLE: yes, one comment undoes it\n")
RESERVED = """VERDICT: RESERVED
QUESTION: May the PR touching a guard be merged?
DECISION: A human merges it; the agent recommends yes.
GROUND: docs/agents/decisions.md:62 `H1` the merge of a protected path
MATRIX_CELL: H1
REVERSIBLE: no, the guard changes the agents themselves
VETO: no
REFERENTIAL_UPDATE: none
WRITE_TO: PR body
READ: CLAUDE.md
"""


def hours_ago(hours: float) -> str:
    return (NOW - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def issue(number: int, labels: list[str], pull_request: bool = False) -> dict:
    found: dict = {
        "number": number,
        "title": f"item {number}",
        "labels": [{"name": name} for name in labels],
    }
    if pull_request:
        found["pull_request"] = {}
    return found


def labeled(label: str, hours: float) -> dict:
    return {"event": "labeled", "label": {"name": label}, "created_at": hours_ago(hours)}


class Gh:
    """`gh api` answered from fixtures; every write is kept in `writes` as (method, path, field)."""

    def __init__(
        self,
        items: dict[int, dict],
        events: dict[int, list[dict]] | None = None,
        comments: dict[int, list[dict]] | None = None,
    ) -> None:
        self.items = items
        self.events = events or {}
        self.comments = comments or {}
        self.writes: list[tuple[str, str, str]] = []

    def __call__(self, argv: list[str], cwd: Path) -> str:
        assert argv[:2] == ["gh", "api"], argv
        args = [a for a in argv[2:] if a != "--paginate"]
        method = "GET"
        if "-X" in args:
            index = args.index("-X")
            method = args[index + 1]
            del args[index : index + 2]
        fields = [args[i + 1] for i, a in enumerate(args) if a == "-f"]
        path = next(a for a in args if a.startswith("repos/"))
        if fields and method == "GET":
            method = "POST"
        if method != "GET":
            self.writes.append((method, path, fields[0] if fields else ""))
            return "{}"
        if match := re.fullmatch(r"repos/\{owner\}/\{repo\}/issues\?(.*)", path):
            label = re.search(r"labels=([^&]+)", match.group(1))
            wanted = label.group(1) if label else ""
            found = [
                i for i in self.items.values() if wanted in {x["name"] for x in i["labels"]}
            ]
            return json.dumps(found)
        if match := re.fullmatch(r"repos/\{owner\}/\{repo\}/issues/(\d+)/events.*", path):
            return json.dumps(self.events.get(int(match.group(1)), []))
        if match := re.fullmatch(r"repos/\{owner\}/\{repo\}/issues/(\d+)/comments.*", path):
            return json.dumps(self.comments.get(int(match.group(1)), []))
        if match := re.fullmatch(r"repos/\{owner\}/\{repo\}/issues/(\d+)", path):
            return json.dumps(self.items[int(match.group(1))])
        raise AssertionError(f"unexpected gh call: {argv}")

    def bodies(self) -> list[str]:
        return [f[len("body=") :] for m, p, f in self.writes if p.endswith("/comments")]

    def added(self) -> list[str]:
        return [f for m, p, f in self.writes if m == "POST" and p.endswith("/labels")]

    def removed(self) -> list[str]:
        return [p.rsplit("/", 1)[1] for m, p, f in self.writes if m == "DELETE"]


class Project:
    """A project folder with its usine.md and a verdict file, the session's variables kept out."""

    def __init__(self, test: unittest.TestCase, usine: str | None = "- `question-default-delay` : `24 h`\n"):
        self.dir = Path(tempfile.mkdtemp())
        test.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "docs" / "agents").mkdir(parents=True)
        text = "# Usine\n" + (usine or "")
        (self.dir / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")
        self.verdict = self.dir / "verdict.txt"
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
        env.update(HOME=str(self.dir), USERPROFILE=str(self.dir))
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        test.addCleanup(patcher.stop)

    def call(self, gh: Gh, *args: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = question_delay_main(list(args), run=gh, now=NOW)
        return code, out.getvalue() + err.getvalue()

    def due(self, gh: Gh, *extra: str) -> tuple[int, str]:
        return self.call(gh, "due", str(self.dir), *extra)

    def route(self, gh: Gh, verdict: str, *extra: str, item: int = 12) -> tuple[int, str]:
        self.verdict.write_text(verdict, encoding="utf-8")
        return self.call(
            gh, "route", str(self.dir), str(self.verdict), "--item", str(item),
            "--agent", "staff-engineer", *extra,
        )  # fmt: skip


def waiting(labels: list[str], hours: float, pull_request: bool = False) -> Gh:
    """One item, number 12, that carries `labels` since `hours` ago."""
    events = [labeled(label, hours) for label in labels]
    return Gh({12: issue(12, labels, pull_request)}, {12: events})


class Delegated(unittest.TestCase):
    def test_a_delegated_decision_past_the_delay_is_posted_as_a_reversible_default(self) -> None:
        """#260 A1 (A1.1): `DECIDED` with its cell, its source and `REVERSIBLE: yes` is posted."""
        project = Project(self)
        gh = waiting(["ready-for-human"], 30)
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(gh.bodies()), 1)
        body = gh.bodies()[0]
        self.assertTrue(body.startswith("Décision (staff-engineer, P1) par défaut (question-default-delay)"), body)
        self.assertIn("Call it `needs info`.", body)
        self.assertIn("docs/agents/decisions.md:34", body)
        self.assertIn("24 h", body)
        self.assertIn("humain peut y revenir par un commentaire", body)
        self.assertEqual(gh.removed(), ["ready-for-human"])
        self.assertEqual(gh.added(), [])

    def test_the_product_owner_block_has_no_reversible_line_and_still_posts(self) -> None:
        """#260 A1: `forge:product-owner` writes no `REVERSIBLE:`; the matrix makes its decisions reversible."""
        project = Project(self)
        gh = waiting(["needs-info"], 30)
        project.verdict.write_text(DECIDED, encoding="utf-8")
        code, out = project.call(
            gh, "route", str(project.dir), str(project.verdict), "--item", "12",
            "--agent", "product-owner", "--apply",
        )  # fmt: skip
        self.assertEqual(code, 0, out)
        self.assertTrue(gh.bodies()[0].startswith("Décision (product-owner, P1) par défaut"))

    def test_a_veto_cell_adds_the_attention_label_to_the_default(self) -> None:
        """#260 A1: a cell that leaves the human a veto (`VETO: yes`) is posted and flagged."""
        project = Project(self)
        gh = waiting(["needs-info"], 30)
        code, out = project.route(gh, STAFF.replace("VETO: no", "VETO: yes"), "--apply")
        self.assertEqual(code, 0, out)
        self.assertTrue(gh.bodies()[0].startswith("Décision (staff-engineer, P1)"))
        self.assertEqual(gh.added(), ["labels[]=needs-your-attention"])

    def test_without_apply_nothing_is_written_and_the_plan_is_printed(self) -> None:
        """#260 A1: the plan is one JSON document, and `gh` receives no write."""
        project = Project(self)
        gh = waiting(["ready-for-human"], 30)
        code, out = project.route(gh, STAFF, "--json")
        self.assertEqual(code, 0, out)
        plan = json.loads(out)
        self.assertEqual(plan["action"], "post-default")
        self.assertTrue(plan["commentaire"].startswith("Décision (staff-engineer, P1)"))
        self.assertEqual(gh.writes, [])


class Reserved(unittest.TestCase):
    def test_a_reserved_case_past_the_delay_reminds_the_human_and_decides_nothing(self) -> None:
        """#260 A2 (A2.1): `RESERVED` posts a reminder and `needs-your-attention`, never a decision."""
        project = Project(self)
        gh = waiting(["needs-your-attention"], 30, pull_request=True)
        code, out = project.route(gh, RESERVED, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(gh.bodies()), 1)
        body = gh.bodies()[0]
        self.assertTrue(body.startswith("Rappel (question-default-delay)"), body)
        self.assertIn("H1", body)
        self.assertIn("A human merges it", body)
        self.assertNotIn("Décision (", body)
        self.assertEqual(gh.added(), [])  # the item already carries the label: nothing is added twice
        self.assertEqual(gh.removed(), [])

    def test_the_reminder_adds_the_attention_label_when_the_item_lacks_it(self) -> None:
        """#260 A2: a question held by `ready-for-human` reaches the human through `needs-your-attention`."""
        project = Project(self)
        gh = waiting(["ready-for-human"], 30)
        code, out = project.route(gh, RESERVED, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.added(), ["labels[]=needs-your-attention"])
        self.assertEqual(gh.removed(), [])

    def test_a_decision_the_matrix_does_not_give_stays_with_the_human(self) -> None:
        """#260 A2: a `DECIDED` without a cell, without a source or not reversible is not a default."""
        project = Project(self)
        cases = {
            "no cell": STAFF.replace("MATRIX_CELL: P1", "MATRIX_CELL: "),
            "no source": STAFF.replace("GROUND: docs/agents/decisions.md:34 `P1` the wording of a label", "GROUND: "),
            "irreversible": STAFF.replace("REVERSIBLE: yes, one comment undoes it", "REVERSIBLE: no, a tag is pushed"),
        }
        for name, verdict in cases.items():
            with self.subTest(case=name):
                gh = waiting(["ready-for-human"], 30)
                code, out = project.route(gh, verdict, "--apply")
                self.assertEqual(code, 0, out)
                self.assertTrue(gh.bodies()[0].startswith("Rappel (question-default-delay)"), gh.bodies())
                self.assertNotIn("Décision (", gh.bodies()[0])

    def test_a_staff_engineer_block_without_a_reversible_line_stays_with_the_human(self) -> None:
        """#260 A2: `forge:staff-engineer` must write `REVERSIBLE: yes`; a block without the line is not a default."""
        project = Project(self)
        gh = waiting(["ready-for-human"], 30)
        code, out = project.route(gh, DECIDED, "--apply")  # `DECIDED` has no `REVERSIBLE:` line
        self.assertEqual(code, 0, out)
        self.assertEqual(len(gh.bodies()), 1)
        self.assertTrue(gh.bodies()[0].startswith("Rappel (question-default-delay)"), gh.bodies())
        self.assertNotIn("Décision (", gh.bodies()[0])
        self.assertEqual(gh.added(), ["labels[]=needs-your-attention"])
        self.assertEqual(gh.removed(), [])

    def test_a_verdict_that_is_not_a_decision_stays_with_the_human(self) -> None:
        """#260 A2: `DOMAIN` and `TECHNICAL` hand the question elsewhere; no default is invented."""
        project = Project(self)
        for verdict in ("DOMAIN", "TECHNICAL"):
            with self.subTest(verdict=verdict):
                gh = waiting(["needs-info"], 30)
                code, out = project.route(gh, STAFF.replace("VERDICT: DECIDED", f"VERDICT: {verdict}"), "--apply")
                self.assertEqual(code, 0, out)
                self.assertTrue(gh.bodies()[0].startswith("Rappel (question-default-delay)"))
                self.assertIn(verdict, gh.bodies()[0])

    def test_a_verdict_that_cannot_be_read_writes_nothing(self) -> None:
        """#260 A2: no block, no action: the command fails (code 2) and `gh` receives no write."""
        project = Project(self)
        gh = waiting(["ready-for-human"], 30)
        code, out = project.route(gh, "I think we should do X.\n", "--apply")
        self.assertEqual(code, 2, out)
        self.assertEqual(gh.writes, [])


class Due(unittest.TestCase):
    def test_a_question_past_the_delay_is_listed_and_one_under_it_is_not(self) -> None:
        """#260 A1: waiting since the last label event; the bound itself is past."""
        project = Project(self)
        gh = Gh(
            {
                1: issue(1, ["ready-for-human"]),
                2: issue(2, ["needs-your-attention"], pull_request=True),
                3: issue(3, ["needs-info"]),
            },
            {1: [labeled("ready-for-human", 30)], 2: [labeled("needs-your-attention", 24)], 3: [labeled("needs-info", 23.9)]},
        )
        code, out = project.due(gh, "--json")
        self.assertEqual(code, 0, out)
        found = json.loads(out)
        self.assertEqual(found["statut"], "calculé")
        self.assertEqual([item["number"] for item in found["echues"]], [1, 2])
        self.assertEqual([item["kind"] for item in found["echues"]], ["issue", "pull request"])

    def test_the_wait_counts_from_the_latest_label_event(self) -> None:
        """#260 A1: a label taken off and put back restarts the wait."""
        project = Project(self)
        gh = Gh(
            {1: issue(1, ["needs-info"])},
            {1: [labeled("needs-info", 80), {"event": "unlabeled", "label": {"name": "needs-info"}, "created_at": hours_ago(60)}, labeled("needs-info", 10)]},
        )
        code, out = project.due(gh, "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["echues"], [])

    def test_a_default_or_a_reminder_restarts_the_delay(self) -> None:
        """#260 A1, A2: after the default or the reminder the question is due again one delay later."""
        project = Project(self)
        mark = "Rappel (question-default-delay) : still waiting"
        decision = "Décision (staff-engineer, P1) par défaut (question-default-delay) : x"
        for body in (mark, decision):
            with self.subTest(body=body[:8]):
                gh = Gh(
                    {1: issue(1, ["ready-for-human"])},
                    {1: [labeled("ready-for-human", 100)]},
                    {1: [{"body": "a human comment", "created_at": hours_ago(90)}, {"body": body, "created_at": hours_ago(10)}]},
                )
                self.assertEqual(json.loads(project.due(gh, "--json")[1])["echues"], [])
                gh.comments[1][1]["created_at"] = hours_ago(25)
                self.assertEqual([i["number"] for i in json.loads(project.due(gh, "--json")[1])["echues"]], [1])

    def test_an_item_with_no_label_event_is_reported_undated_and_never_due(self) -> None:
        """#260 A1: no event, no date: nothing is guessed, the item is reported apart."""
        project = Project(self)
        gh = Gh({1: issue(1, ["needs-info"])}, {})
        code, out = project.due(gh, "--json")
        self.assertEqual(code, 0, out)
        found = json.loads(out)
        self.assertEqual(found["echues"], [])
        self.assertEqual([item["number"] for item in found["non_datees"]], [1])

    def test_the_text_output_names_each_due_question(self) -> None:
        """#260 A1: one `ECHUE:` line per question with its age and the delay."""
        project = Project(self)
        code, out = project.due(waiting(["ready-for-human"], 30))
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"ECHUE: #12 \(issue\) ready-for-human depuis 30 h \(délai 24 h\)")


class Absent(unittest.TestCase):
    def test_without_the_key_nothing_is_listed_decided_or_written(self) -> None:
        """#260 A1 (A3.4 for the other key): no `question-default-delay`, the step is not applicable."""
        project = Project(self, usine=None)
        gh = waiting(["ready-for-human"], 300)
        code, out = project.due(gh)
        self.assertEqual(code, 0, out)
        self.assertIn("sans objet (clé `question-default-delay` absente)", out)
        self.assertNotIn("ECHUE", out)
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("sans objet (clé `question-default-delay` absente)", out)
        self.assertEqual(gh.writes, [])

    def test_an_unreadable_or_repeated_key_fails_instead_of_guessing(self) -> None:
        """#260 A1: a delay the script cannot read stops the command with code 2."""
        gh = waiting(["ready-for-human"], 30)
        for usine in (
            "- `question-default-delay` : `soon`\n",
            "- `question-default-delay` : `0 h`\n",
            "- `question-default-delay` : `24`\n",
            "- `question-default-delay` : `24 h`\n- `question-default-delay` : `2 j`\n",
        ):
            with self.subTest(usine=usine):
                code, out = Project(self, usine=usine).due(gh)
                self.assertEqual(code, 2, out)
                self.assertIn("question-default-delay", out)


class Minutes(unittest.TestCase):
    """#380: `question-default-delay` reads minutes, so the floor is no longer one hour."""

    def minutes(self, usine: str, waited: float) -> list[int]:
        code, out = Project(self, usine=usine).due(waiting(["ready-for-human"], waited / 60), "--json")
        self.assertEqual(code, 0, out)
        return [item["number"] for item in json.loads(out)["echues"]]

    def test_ten_minutes_is_due_at_ten_and_not_at_nine(self) -> None:
        """#380 A1: with `10 min`, a question waiting 10 minutes is due (the bound included), 9 is not."""
        usine = "- `question-default-delay` : `10 min`\n"
        self.assertEqual(self.minutes(usine, 10), [12])
        self.assertEqual(self.minutes(usine, 9), [])

    def test_the_minute_unit_is_read_with_or_without_a_space(self) -> None:
        """#380 A1: `10min` and `10 min` are the same delay."""
        self.assertEqual(self.minutes("- `question-default-delay` : `10min`\n", 10), [12])

    def test_hours_and_days_still_work(self) -> None:
        """#380 A1: `h` and `j` keep their meaning next to `min`."""
        self.assertEqual(self.minutes("- `question-default-delay` : `2 h`\n", 119), [])
        self.assertEqual(self.minutes("- `question-default-delay` : `2 h`\n", 120), [12])
        self.assertEqual(self.minutes("- `question-default-delay` : `1 j`\n", 24 * 60 - 1), [])
        self.assertEqual(self.minutes("- `question-default-delay` : `1 j`\n", 24 * 60), [12])

    def test_the_text_output_names_the_minutes_delay(self) -> None:
        """#380 A1: the line says the delay as declared."""
        code, out = Project(self, usine="- `question-default-delay` : `10 min`\n").due(
            waiting(["ready-for-human"], 0.5)
        )
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"ECHUE: #12 \(issue\) ready-for-human depuis .* \(délai 10 min\)")

    def test_the_shared_reader_of_the_other_keys_stays_without_minutes(self) -> None:
        """#380 A1: `min` is the delay's alone; `sla` and `release-trigger` keep `h` and `j`."""
        import sla

        self.assertIsNone(sla.parse_delay("10 min"))
        self.assertIsNotNone(sla.parse_delay("10 h"))

    def test_an_unreadable_unit_still_fails_with_code_2(self) -> None:
        """#380 A2: seconds, zero minutes or a word are not delays; nothing is guessed."""
        gh = waiting(["ready-for-human"], 1)
        for value in ("10 s", "0 min", "min", "10 mins", "10 minutes", "-5 min"):
            with self.subTest(value=value):
                code, out = Project(self, usine=f"- `question-default-delay` : `{value}`\n").due(gh)
                self.assertEqual(code, 2, out)
                self.assertIn("question-default-delay", out)
                self.assertIn("min", out)


class Docs(unittest.TestCase):
    def test_the_template_documents_the_key_without_a_default(self) -> None:
        """#260 A1: the template of `usine.md` documents `question-default-delay` and its absence."""
        template = " ".join((support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8").split())
        self.assertIn("- `question-default-delay` : `<", template)
        self.assertIn("sans objet (clé `question-default-delay` absente)", template)

    def test_feature_build_runs_the_script_and_routes_to_the_deciders(self) -> None:
        """#260 A1, A2: the skill lists the due questions, asks the deciders, applies the route."""
        text = " ".join((support.PLUGIN / "skills" / "feature-build" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("question_delay.py\" due", text)
        self.assertIn("question_delay.py\" route", text)
        self.assertIn("forge:staff-engineer", text)
        self.assertIn("forge:product-owner", text)
        self.assertIn("`question-default-delay`", text)


if __name__ == "__main__":
    unittest.main()
