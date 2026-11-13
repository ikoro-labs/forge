"""guard_cases: the validation cases of a ticket, agreed before the PR opens, frozen, and the only
ground a verdict's blocker stands on besides the rules and a regression."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from guard_cases import GitHubError, outcome
from parse_output import OutputError, parse_verdict

USINE = """# Usine

- `validation-cases` : `2026-11-14`
- `validation-reviewer` : `securite | runner/, .github/`
- `validation-owner` : `the-owner`
- `security-rules` : `L-2`
- `review-grid` : `docs/agents/socle.md`
"""
LOCAL_RULES = """| Id | Nature | Rule | Proof |
|---|---|---|---|
| L-1 | code | A local rule. | reading |
| L-2 | test | A local rule the project counts as security. | reading |
"""
CASES = """Motif: to-tickets F-0002 (Kevin, 2026-11-14)
Feature: F-0002

The run stops at a gate.

## Criteria

- A1: the run stops at the gate.

## Validation cases

A1.1 | a run that reaches the gate | the run is stopped, state `waiting`
A1.2 | a run that skips the gate | refused with `gate skipped`
AGREED: test-author, coder, qc-conf
"""
LEGACY = """Motif: to-tickets F-0001
Feature: F-0001

## Criteria

- A1: the runner starts.
- A3: the runner stops.
"""
OPENED = "2026-11-15T10:00:00Z"


def verdict(*findings: str, extra: str = "") -> str:
    body = "\n".join(findings) or "- none"
    result = "REJECT" if any("[BLOCKER]" in finding for finding in findings) else "ACCEPT"
    return (
        f"VERDICT: {result}\nROUND: 1\nHEAD: abcdef1\nSPEC: #12: 1 criteria covered\n"
        f"FINDINGS:\n{body}\n{extra}GATES: ok\n"
    )


class GitHub:
    """The answers of gh and git for one repository: PR #7 closes ticket #12."""

    def __init__(self) -> None:
        self.tickets: dict[int, dict] = {
            12: {"number": 12, "body": CASES, "createdAt": "2026-11-14T09:00:00Z", "lastEditedAt": None, "editor": None},
        }
        self.prs: dict[int, dict] = {7: {"number": 7, "createdAt": OPENED, "body": "Closes #12"}}
        self.files = ["src/gate.py"]
        self.calls: list[list[str]] = []
        self.fail = False

    def run(self, argv: list[str], cwd: str | None) -> str:
        self.calls.append(argv)
        if self.fail:
            raise GitHubError("gh: network unreachable")
        if argv[:3] == ["gh", "api", "graphql"]:
            fields = dict(word.split("=", 1) for word in argv[3:] if not word.startswith("-"))
            number = int(fields["number"])
            if "PullRequest{number createdAt body}" in fields["query"]:
                if number in self.prs:
                    node = {"__typename": "PullRequest", **self.prs[number]}
                elif number in self.tickets:
                    node = {"__typename": "Issue", "number": number}
                else:
                    node = None
                return json.dumps({"data": {"repository": {"issueOrPullRequest": node}}})
            if number in self.prs:
                return json.dumps({"data": {"repository": {"issueOrPullRequest": {"__typename": "PullRequest"}}}})
            ticket = self.tickets.get(number)
            if ticket is None:
                raise GitHubError(f"no issue {number}")
            return json.dumps({"data": {"repository": {"issueOrPullRequest": {"__typename": "Issue", **ticket}}}})
        if argv[:3] == ["gh", "pr", "view"]:
            return json.dumps({"number": 7})
        if argv[:2] == ["git", "symbolic-ref"]:
            return "origin/main\n"
        if argv[:2] == ["git", "diff"]:
            return "\n".join(self.files) + "\n"
        raise AssertionError(f"unexpected call: {argv}")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "docs" / "agents").mkdir(parents=True)
        self.write_usine(USINE)
        (self.root / "docs" / "agents" / "socle.md").write_text(LOCAL_RULES, encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.github = GitHub()

    def write_usine(self, text: str) -> None:
        (self.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def judge(self, command: str) -> tuple[int, str]:
        event = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.root)}
        return outcome(event, self.github.run)

    def file(self, text: str, name: str = "body.md") -> str:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def assert_refused(self, command: str, *reasons: str) -> None:
        code, message = self.judge(command)
        self.assertEqual(code, 2, message)
        for reason in reasons:
            self.assertIn(reason, message)

    def assert_passes(self, command: str) -> None:
        code, message = self.judge(command)
        self.assertEqual((code, message), (0, ""))


class PrCreate(Base):
    def create(self) -> str:
        return f"gh pr create --title 'feat(gate): stop' --body-file {self.file('Closes #12')}"

    def test_a_feature_ticket_with_cases_and_a_full_agreed_line_opens(self) -> None:
        self.assert_passes(self.create())

    def test_a_feature_ticket_without_a_case_is_refused(self) -> None:
        self.github.tickets[12]["body"] = CASES.replace("A1.1 |", "A1.1").replace("A1.2 |", "A1.2")
        self.assert_refused(self.create(), "#12", "no validation case")

    def test_an_agreed_line_that_lacks_a_role_is_refused(self) -> None:
        self.github.tickets[12]["body"] = CASES.replace(", qc-conf", "")
        self.assert_refused(self.create(), "#12", "qc-conf")

    def test_a_ticket_without_an_agreed_line_is_refused(self) -> None:
        self.github.tickets[12]["body"] = CASES.replace("AGREED: test-author, coder, qc-conf\n", "")
        self.assert_refused(self.create(), "#12", "AGREED")

    def test_a_reviewer_whose_perimeter_the_diff_touches_must_agree(self) -> None:
        self.github.files = ["src/gate.py", "runner/sandbox.py"]
        self.assert_refused(self.create(), "securite")
        self.github.tickets[12]["body"] = CASES.replace("qc-conf\n", "qc-conf, securite\n")
        self.assert_passes(self.create())

    def test_a_ticket_created_before_the_adoption_needs_no_case(self) -> None:
        self.github.tickets[12].update(body=LEGACY, createdAt="2026-11-10T09:00:00Z")
        self.assert_passes(self.create())

    def test_a_ticket_outside_a_feature_needs_no_case(self) -> None:
        self.github.tickets[12]["body"] = "Motif: main-rouge 123\n\n## Criteria\n\n- A1: main is green.\n"
        self.assert_passes(self.create())

    def test_without_the_key_nothing_is_read(self) -> None:
        self.write_usine("# Usine\n")
        self.github.fail = True
        self.assert_passes(self.create())
        self.assertEqual(self.github.calls, [])

    def test_a_body_the_guard_cannot_read_is_refused(self) -> None:
        for command in ['gh pr create --title t --body "$BODY"', "gh pr create --fill", "cat b | gh pr create -F -"]:
            with self.subTest(command=command):
                self.assert_refused(command, "cannot be read")

    def test_a_pr_the_body_refers_to_is_no_ticket(self) -> None:
        self.github.tickets[12]["body"] = CASES.replace(", qc-conf", "")
        self.assert_passes(f"gh pr create --title t --body-file {self.file('Refs #7')}")
        self.assert_refused(f"gh pr create --title t --body-file {self.file('Refs #7, Closes #12')}", "qc-conf")

    def test_a_ticket_github_cannot_give_is_refused(self) -> None:
        self.github.fail = True
        self.assert_refused(self.create(), "network unreachable")

    def test_a_wrong_adoption_date_is_refused(self) -> None:
        self.write_usine(USINE.replace("2026-11-14", "soon"))
        self.assert_refused(self.create(), "validation-cases")


class VerdictCitations(Base):
    def post(self, text: str) -> str:
        return f"gh pr comment 7 --body-file {self.file(text, 'verdict.md')}"

    def test_a_blocker_that_cites_a_frozen_case_passes(self) -> None:
        self.assert_passes(self.post(verdict("- [BLOCKER] src/gate.py:3 | A1.2 | a skipped gate runs")))

    def test_a_blocker_that_cites_nothing_is_refused(self) -> None:
        self.assert_refused(
            self.post(verdict("- [BLOCKER] src/gate.py:3 | style | I would name it differently")),
            "cites no validation case",
        )

    def test_a_blocker_that_cites_a_case_off_the_list_is_refused(self) -> None:
        self.assert_refused(self.post(verdict("- [BLOCKER] src/gate.py:3 | A1.9 | x")), "`A1.9`", "#12")

    def test_a_bare_criterion_is_refused_on_a_ticket_with_cases(self) -> None:
        self.assert_refused(self.post(verdict("- [BLOCKER] src/gate.py:3 | A1 | x")), "`A1.<k>`")

    def test_a_socle_or_local_rule_passes_and_an_unknown_one_is_refused(self) -> None:
        self.assert_passes(self.post(verdict("- [BLOCKER] src/gate.py:3 | F-10 | the test asserts nothing")))
        self.assert_passes(self.post(verdict("- [BLOCKER] src/gate.py:3 | L-1 | x")))
        self.assert_refused(self.post(verdict("- [BLOCKER] src/gate.py:3 | F-99 | x")), "`F-99`")

    def test_a_regression_names_its_test(self) -> None:
        self.assert_passes(self.post(verdict("- [BLOCKER] src/gate.py:3 | regression tests/test_run.py::test_stop | x")))
        self.assert_refused(self.post(verdict("- [BLOCKER] src/gate.py:3 | regression | x")), "cites no validation case")

    def test_a_security_rule_needs_its_proof(self) -> None:
        self.assert_refused(self.post(verdict("- [BLOCKER] src/gate.py:3 | F-3 | input runs")), "`F-3`", "proof")
        self.assert_refused(self.post(verdict("- [BLOCKER] src/gate.py:3 | L-2 | x")), "`L-2`", "proof")
        for proof in ("proof: tests/test_gate.py::test_refuses_input", "proof: `uv run gate --input '$(id)'`"):
            with self.subTest(proof=proof):
                self.assert_passes(self.post(verdict(f"- [BLOCKER] src/gate.py:3 | F-3 | input runs | {proof}")))

    def test_minor_and_note_findings_are_not_judged_here(self) -> None:
        self.assert_passes(self.post(verdict("- [NOTE] src/x.py:1 | out of diff: old | not this PR")))

    def test_a_proposal_never_blocks(self) -> None:
        text = verdict(extra="PROPOSAL: a run with two gates | both stop the run\n")
        self.assert_passes(self.post(text))
        self.assertEqual(parse_verdict(text)["PROPOSAL"], ["a run with two gates | both stop the run"])

    def test_a_proposal_states_an_input_and_an_expected_result(self) -> None:
        with self.assertRaises(OutputError):
            parse_verdict(verdict(extra="PROPOSAL: more tests\n"))


class VerdictFreeze(Base):
    def post(self) -> str:
        text = verdict("- [BLOCKER] src/gate.py:3 | A1.2 | a skipped gate runs")
        return f"gh pr comment 7 --body-file {self.file(text, 'verdict.md')}"

    def test_a_ticket_edited_after_the_pr_opened_refuses_the_verdict(self) -> None:
        self.github.tickets[12].update(lastEditedAt="2026-11-15T11:00:00Z", editor={"login": "an-agent"})
        self.assert_refused(self.post(), "#12", "frozen", "Refs #12", "validation-owner")

    def test_an_edit_before_the_pr_opened_passes(self) -> None:
        self.github.tickets[12].update(lastEditedAt="2026-11-15T09:59:00Z", editor={"login": "an-agent"})
        self.assert_passes(self.post())

    def test_the_owner_may_correct_the_list_after_the_opening(self) -> None:
        self.github.tickets[12].update(lastEditedAt="2026-11-15T11:00:00Z", editor={"login": "the-owner"})
        self.assert_passes(self.post())


class VerdictTransition(Base):
    def setUp(self) -> None:
        super().setUp()
        self.github.tickets[12].update(body=LEGACY, createdAt="2026-11-10T09:00:00Z")

    def post(self, rule: str) -> str:
        text = verdict(f"- [BLOCKER] src/run.py:3 | {rule} | x")
        return f"gh pr comment 7 --body-file {self.file(text, 'verdict.md')}"

    def test_a_criterion_of_a_ticket_taken_before_the_adoption_is_its_first_case(self) -> None:
        self.assert_passes(self.post("A1"))
        self.assert_passes(self.post("A3.1"))
        self.assert_refused(self.post("A2"), "`A2.1`")
        self.assert_refused(self.post("A1.2"), "`A1.2`")


class VerdictChannels(Base):
    def test_a_verdict_through_the_rest_api_is_judged(self) -> None:
        path = self.file(verdict("- [BLOCKER] src/gate.py:3 | style | x"), "verdict.md")
        self.assert_refused(f"gh api repos/{{owner}}/{{repo}}/issues/7/comments -F body=@{path}", "cites no validation case")

    def test_a_verdict_through_graphql_or_an_edit_is_refused(self) -> None:
        text = verdict("- [BLOCKER] src/gate.py:3 | A1.2 | x")
        query = self.file('mutation { addComment(input: {subjectId: "PR_1", body: """' + text + '"""}) { clientMutationId } }', "q.graphql")
        self.assert_refused(f"gh api graphql -F query=@{query}", "gh pr comment")
        path = self.file(text, "verdict.md")
        self.assert_refused(f"gh api -X PATCH repos/o/r/issues/comments/99 -F body=@{path}", "gh pr comment")

    def test_a_verdict_on_a_ticket_is_not_a_pr_verdict(self) -> None:
        path = self.file(verdict("- [BLOCKER] src/gate.py:3 | style | x"), "verdict.md")
        self.assert_passes(f"gh issue comment 12 --body-file {path}")

    def test_a_verdict_on_the_branch_pr_is_resolved(self) -> None:
        path = self.file(verdict("- [BLOCKER] src/gate.py:3 | style | x"), "verdict.md")
        self.assert_refused(f"gh pr comment feat/gate --body-file {path}", "cites no validation case")

    def test_an_unreadable_comment_is_refused(self) -> None:
        self.assert_refused('gh pr comment 7 --body "$VERDICT"', "cannot be read")

    def test_a_comment_that_is_no_verdict_passes(self) -> None:
        self.assert_passes(f"gh pr comment 7 --body-file {self.file('Thanks')}")
        self.assertEqual(self.github.calls, [])



class Wiring(unittest.TestCase):
    """The hook runs on every Bash call, and the texts say round 0 and what the hook cannot hold."""

    def test_hooks_json_runs_the_guard_on_bash(self) -> None:
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        entries = [e for e in hooks["hooks"]["PreToolUse"] if "guard_cases.py" in e["hooks"][0]["command"]]
        self.assertEqual([e["matcher"] for e in entries], ["Bash|PowerShell"])
        self.assertTrue(entries[0]["hooks"][0]["command"].endswith("|| exit 2"))

    def test_round_zero_is_written_where_the_agents_read_it(self) -> None:
        build = (support.PLUGIN / "skills" / "feature-build" / "SKILL.md").read_text(encoding="utf-8")
        conf = (support.PLUGIN / "agents" / "qc-conf.md").read_text(encoding="utf-8")
        socle = (support.PLUGIN / "socle.md").read_text(encoding="utf-8")
        self.assertIn("Tour 0, sans code", build)
        self.assertIn("`ticket-budget`", build)
        self.assertIn("seulement le corps du ticket et les fichiers que ce\ncorps nomme, une seule fois, sans diff ni rejeu", conf)
        self.assertIn("**Not held by a hook**", socle)
        self.assertIn("`security-rules`", socle)
        self.assertIn("A1.1 | <input> | <expected result>", (support.PLUGIN / "templates" / "ticket.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
