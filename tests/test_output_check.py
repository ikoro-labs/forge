"""The validator of every exchange: one test per deviation it refuses, one per conforming text."""

import io
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import support
from output_check import (
    DEFAULT_PARAGRAPH_WORDS,
    DEFAULT_WORDS,
    FORGE_AGENTS,
    KINDS,
    _template_text,
    agent_kind,
    deviations,
    line_cap,
    main,
    required_fields,
)
from parse_output import RESULT_KEYS, VERDICT_KEYS

TICKET = """Motif: demande-kevin, 2026-11-13 chat
Replies run long, so the human reads prose instead of facts.

## Criteria

- A1: a reply over the cap is refused.

## Out of scope

- The parser of the frozen rules.

Refs: design section 4
"""
PR = """## Summary

Adds the output guard and its validator. Closes #12.

## Door

two-way: removing the hook entries restores the old behavior.

## Blast radius

consumers: every session of a project that pins this version.

## Proofs

```
FAILED test_refuses (red: no validator)
OK
```

## Agent report
"""
VERDICT = """```text
VERDICT: REJECT
ROUND: 1
HEAD: 0123456789abcdef0123456789abcdef01234567
SPEC: #12: 1 criteria covered, 0 partial, 0 missing
FINDINGS:
- [BLOCKER] a.py:3 | A1 | the cap is never read
GATES: all probes pass
```
"""
REPLY = """| Field | State |
|---|---|
| Done | merged #12 at abc1234. |
| Measured | CI 4 min 10 s, run 99, 2026-11-13, 1 run of 1. |
| Awaiting your decision | nothing. |

CI and runners: pc 2/2 online, 1 busy; queued 0, main success abc1234.

Features:

| Feature | Closed / total | Merged PRs | Open PRs | Blocked | Ready |
|---|---|---|---|---|---|
| F-0001 demo | 33 % (1 / 3) | 4 / 45 (#12: 3, #13: 1) | #77 | #13 | #12 |

In parallel: free slots 1; tickets #12 (F-0001); or features F-0001.
"""
FEATURES_BLOCK = REPLY[REPLY.index("Features:") :]
CODER_PR = """RESULT: PR
PR: #40
TICKET: #12 closes
CRITERIA: A1, A2 ; not covered: none
NOTES: none
"""
DECIDER = """VERDICT: DECIDED
QUESTION: which cap applies to a verdict?
DECISION: none, the review keeps its findings whole.
GROUND: socle.md:12
MATRIX_CELL: review format
READ: socle.md
"""
GATE = "| Probe | Result | Detail |\n|---|---|---|\n| CI | PASS 3 | none |\n"


def words(count: int) -> str:
    return " ".join(["word"] * count)


def prose(count: int, per_paragraph: int = 40) -> str:
    """`count` words of prose, in paragraphs short enough for the paragraph rule."""
    chunks = []
    while count > 0:
        chunks.append(words(min(per_paragraph, count)))
        count -= per_paragraph
    return "\n\n".join(chunks)


class Conforming(unittest.TestCase):
    def test_each_template_filled_conforms(self) -> None:
        for kind, text in [
            ("ticket", TICKET),
            ("pr", PR),
            ("verdict", VERDICT),
            ("session-reply", REPLY),
            ("comment", "Merged at abc1234, run 99 green.\n\nRefs: #12\n"),
            ("subagent-return", "RESULT: done, three files read.\n\n| a | b |\n|---|---|\n"),
            ("coder", CODER_PR),
            ("decider", DECIDER),
            ("gate", GATE),
        ]:
            with self.subTest(kind=kind):
                self.assertEqual(deviations(text, kind), [])

    def test_the_other_forms_of_the_coder_conform(self) -> None:
        blocked = (
            "RESULT: BLOCKED\nTICKET: #3\nQUESTION: which cap?\nRECOMMENDATION: 150\nSTATE: pushed\n"
        )
        failed = "RESULT: FAILED\nTICKET: #3\nCOMMAND: make\nOUTPUT: error\nSTATE: not pushed\n"
        self.assertEqual(deviations(blocked, "coder"), [])
        self.assertEqual(deviations(failed, "coder"), [])

    def test_a_keyed_block_wrapped_in_a_fence_is_read_as_its_keys(self) -> None:
        self.assertEqual(deviations(f"```text\n{CODER_PR}```\n", "coder"), [])
        long_gates = VERDICT.replace("all probes pass", " ".join(["word"] * 61))
        self.assertTrue(any("paragraph" in d for d in deviations(long_gates, "verdict")))

    def test_a3_1_the_french_table_then_the_ci_line_and_features_conforms(self) -> None:
        """F-0181 ticket #252 A3.1: a `Champ / État` table, then the CI line and Features."""
        reply = (
            "| Champ | État |\n|---|---|\n| Fait | PR #12 fusionnée. |\n| Mesure | CI 4 min. |\n"
            "| Attend ta décision | rien |\n\nCI et runners : poste 2/2.\n\n"
            "**Features :** \n\n" + FEATURES_BLOCK.split("\n", 2)[2]
        )
        self.assertEqual(deviations(reply, "session-reply"), [])
        self.assertEqual(deviations(reply.replace("**Features :**", "Features :"), "session-reply"), [])

    def test_a3_2_the_english_table_conforms_and_its_markup_may_vary(self) -> None:
        """F-0181 ticket #252 A3.2: a `Field / State` table with the English names."""
        self.assertEqual(deviations(REPLY, "session-reply"), [])
        for name, text in {
            "bold labels": REPLY.replace("| Done |", "| **Done** |"),
            "lower case header": REPLY.replace("| Field | State |", "| field | state |"),
            "French labels under the English header": REPLY.replace("| Done |", "| Fait |"),
            "aligned separator": REPLY.replace("|---|---|", "| :--- | ---: |"),
        }.items():
            with self.subTest(name):
                self.assertEqual(deviations(text, "session-reply"), [])

    def test_a_key_written_with_a_space_before_its_colon_counts(self) -> None:
        self.assertEqual(deviations(TICKET.replace("Motif:", "Motif :"), "ticket"), [])

    def test_a_verdict_with_optional_keys_and_long_findings_conforms(self) -> None:
        findings = "".join(f"- [BLOCKER] a.py:{n} | A1 | {words(25)}\n" for n in range(12))
        verdict = (
            "VERDICT: REJECT\nROUND: 3\nREGIME: strict\nHEAD: abcdef1\nSPEC: none (pin bump)\n"
            f"FINDINGS:\n{findings}REMARKS:\n- [REMARK] a.py:1 | r | s\nGATES: pass\n"
        )
        config = {"output-extra-keys": ["verdict | REGIME, REMARKS"]}
        self.assertEqual(deviations(verdict, "verdict", config), [])

    def test_html_comments_do_not_count(self) -> None:
        comment = f"<!-- {words(300)} -->\n"
        self.assertEqual(deviations(f"Merged.\n\n{comment}", "comment"), [])

    def test_exempt_checks_nothing(self) -> None:
        self.assertEqual(deviations(words(500), "exempt"), [])


class Refused(unittest.TestCase):
    def assertRefused(self, text: str, kind: str, phrase: str) -> None:
        found = deviations(text, kind)
        self.assertTrue(any(phrase in deviation for deviation in found), found)

    def test_a_missing_required_field(self) -> None:
        self.assertRefused(TICKET.replace("Motif:", "Reason:"), "ticket", "`Motif` is missing")
        self.assertRefused(TICKET.replace("## Criteria", "## Tests"), "ticket", "`Criteria` is missing")
        self.assertRefused(PR.replace("## Door", "## Gate"), "pr", "`Door` is missing")
        self.assertRefused(VERDICT.replace("GATES: all probes pass\n", ""), "verdict", "`GATES:`")
        self.assertRefused(REPLY.replace("| Measured |", "| Numbers |"), "session-reply", "`Measured`")
        # A6 of forge#181: the reply carries the one-line "CI and runners" part.
        self.assertRefused(
            REPLY.replace("CI and runners:", "Runners:"), "session-reply", "`CI and runners`"
        )
        self.assertRefused(
            REPLY.replace("CI and runners: pc 2/2 online, 1 busy; queued 0, main success abc1234.", "CI and runners:"),
            "session-reply", "`CI and runners` or `CI et runners` is empty",
        )

    def test_a11_the_features_field_is_required_and_holds_the_script_output(self) -> None:
        without = REPLY.replace(FEATURES_BLOCK, "")
        self.assertRefused(without, "session-reply", "the field `Features` is missing")
        self.assertRefused(REPLY.replace(FEATURES_BLOCK, "Features:\n"), "session-reply", "`Features` is empty")
        by_hand = (
            "Features: F-0001 at 33 %, one ticket ready.",
            "Features:\n\n- F-0001: 33 %\n",
            "Features: no open feature",  # the period of the script's line is part of it
            "Features: not applicable (key `other` absent).",
        )
        for text in by_hand:
            with self.subTest(text=text):
                self.assertRefused(without + text + "\n", "session-reply", "neither the table")

    def test_a11_the_table_needs_its_header_its_separator_its_rows_and_its_parallel_line(self) -> None:
        header = "| Feature | Closed / total | Merged PRs | Open PRs | Blocked | Ready |\n"
        row = "| F-0001 demo | 33 % (1 / 3) | 4 / 45 (#12: 3, #13: 1) | #77 | #13 | #12 |\n"
        parallel = "In parallel: free slots 1; tickets #12 (F-0001); or features F-0001.\n"
        broken = {
            "no header": FEATURES_BLOCK.replace(header, ""),
            "another header": FEATURES_BLOCK.replace("Blocked", "Stuck"),
            "no separator": FEATURES_BLOCK.replace("|---|---|---|---|---|---|\n", ""),
            "no row": FEATURES_BLOCK.replace(row, ""),
            "short row": FEATURES_BLOCK.replace(row, "| F-0001 demo | 33 % |\n"),
            # #335 A1: the five columns of the earlier pin no longer pass the reply check.
            "earlier five columns": FEATURES_BLOCK.replace(" Merged PRs |", "").replace(
                "|---|---|---|---|---|---|", "|---|---|---|---|---|"
            ).replace(" 4 / 45 (#12: 3, #13: 1) |", ""),
            "no parallel line": FEATURES_BLOCK.replace(parallel, ""),
            "empty parallel line": FEATURES_BLOCK.replace(parallel, "In parallel:\n"),
        }
        for name, block in broken.items():
            with self.subTest(name):
                self.assertRefused(REPLY.replace(FEATURES_BLOCK, block), "session-reply", "neither the table")

    def test_a11_what_the_script_renders_is_what_the_guard_accepts(self) -> None:
        import features_block

        entry: dict[str, Any] = {"feature": "F-0001", "label": "F-0001 demo", "percent": "33 % (1 / 3)", "prs": [77],
                 "merged": "4 / 45 (#12: 3, #13: 1)", "blocked": [13], "ready": [12], "error": None}
        unread = {**entry, "feature": "F-0002", "label": "F-0002 other", "percent": None, "prs": [], "merged": "-",
                  "blocked": [], "ready": [], "error": "tickets not read"}
        base: dict[str, Any] = {"note": None, "absent": None, "features": [entry, unread], "free": 1,
                "proposal": [("F-0001", 12)], "parallel": ["F-0001"], "why": None}
        absent = {**base, "features": [], "absent": "report-repo", "note": "x"}
        for name, state in {
            "proposal": base, "zero slots": {**base, "why": "free slots 0", "proposal": [], "parallel": []},
            "no ready ticket": {**base, "proposal": [], "parallel": []},
            "no feature": {**base, "features": [], "note": "No open feature."}, "absent key": absent,
            "absent dir": {**absent, "absent": "feature-dir"},
        }.items():
            with self.subTest(name):
                text = REPLY.replace(FEATURES_BLOCK, features_block.render(state))
                self.assertEqual(deviations(text, "session-reply"), [])

    def test_a11_the_block_is_left_out_of_the_line_and_word_caps_only(self) -> None:
        rows = "".join(f"| F-{n:04d} a feature title of some length | 33 % (1 / 3) | 4 / 45 (#12: 3, #13: 1) | #77 | #13 | #12 |\n"
                       for n in range(2, 12))
        long = REPLY.replace("\n\nIn parallel", "\n" + rows + "\nIn parallel")
        self.assertEqual(deviations(long, "session-reply"), [])
        # What follows the block is held to the caps as before.
        self.assertRefused(long + prose(200), "session-reply", "at most 150")
        self.assertRefused(long + "\n- a\n- b\n- c\n", "session-reply", "go in a table")
        lines = REPLY.replace(FEATURES_BLOCK, "") + "x\n" * 12 + FEATURES_BLOCK
        self.assertRefused(lines, "session-reply", "lines, at most 15")

    def test_a2_1_a_table_field_written_outside_the_table_is_refused(self) -> None:
        """F-0181 ticket #252 A2.1: `Fait: ...` as prose is refused; so is each of the three fields."""
        prose_form = {
            "Done": "Done: merged #12 at abc1234.",
            "Measured": "Measured: CI 4 min 10 s, run 99, 2026-11-13, 1 run of 1.",
            "Awaiting your decision": "Awaiting your decision: nothing.",
        }
        for field, line in prose_form.items():
            with self.subTest(field=field):
                row = next(r for r in REPLY.splitlines() if r.startswith(f"| {field} |"))
                outside = REPLY.replace(row + "\n", "") + "\n" + line + "\n"
                self.assertRefused(outside, "session-reply", f"`{field}`")
                self.assertRefused(outside, "session-reply", "outside the table")
        french = REPLY.replace("| Field | State |", "| Champ | État |").replace("| Done | merged", "| Fait | merged")
        self.assertRefused(french.replace("| Fait | merged #12 at abc1234. |\n", "") + "\nFait: PR #12.\n",
                           "session-reply", "`Fait`")

    def test_a2_1_the_same_field_in_prose_and_in_the_table_is_still_refused(self) -> None:
        self.assertRefused("Done: merged #12.\n\n" + REPLY, "session-reply", "outside the table")
        for form in ("**Done:** merged.", "## Done\n\nmerged.", "Done | merged."):
            with self.subTest(form=form):
                self.assertRefused(form + "\n\n" + REPLY, "session-reply", "outside the table")

    def test_a2_1_fields_in_prose_without_any_table_are_refused(self) -> None:
        old = (
            "Done: merged #12.\n\nMeasured: CI 4 min.\n\nAwaiting your decision: nothing.\n\n"
            + REPLY[REPLY.index("CI and runners:") :]
        )
        found = deviations(old, "session-reply")
        for field in ("Done", "Measured", "Awaiting your decision"):
            self.assertTrue(any(f"`{field}`" in d and "outside the table" in d for d in found), found)

    def test_a2_1_a_table_under_another_header_is_not_the_table_of_the_fields(self) -> None:
        for header in ("| Item | Value |", "| Field | State | Note |", "| State | Field |"):
            with self.subTest(header=header):
                text = REPLY.replace("| Field | State |", header)
                self.assertRefused(text, "session-reply", "outside the table")

    def test_a2_1_a_table_without_its_separator_row_is_not_a_table(self) -> None:
        self.assertRefused(REPLY.replace("|---|---|\n", "", 1), "session-reply", "outside the table")

    def test_a2_1_the_refusal_names_the_header_the_fields_go_under(self) -> None:
        found = deviations("Done: x.\n\n" + REPLY, "session-reply")
        self.assertTrue(any("| Field | State |" in d and "| Champ | État |" in d for d in found), found)

    def test_a2_1_a_missing_row_and_an_empty_state_are_refused_in_the_table(self) -> None:
        self.assertRefused(REPLY.replace("| Measured | CI 4 min 10 s, run 99, 2026-11-13, 1 run of 1. |\n", ""),
                           "session-reply", "`Mesuré` is missing")
        for empty in ("| Measured | |", "| Measured |", "| Measured |   |"):
            with self.subTest(row=empty):
                text = REPLY.replace("| Measured | CI 4 min 10 s, run 99, 2026-11-13, 1 run of 1. |", empty)
                self.assertRefused(text, "session-reply", "`Mesuré` is empty")
        # An empty last row is read as empty too, whatever follows it.
        last = REPLY.replace("| Awaiting your decision | nothing. |", "| Awaiting your decision | |")
        self.assertRefused(last, "session-reply", "`Awaiting your decision`")

    def test_a2_1_the_features_table_is_not_mistaken_for_the_table_of_the_fields(self) -> None:
        feature = REPLY.replace("| F-0001 demo |", "| Done and Measured |")
        self.assertEqual(deviations(feature, "session-reply"), [])

    def test_an_empty_required_field(self) -> None:
        self.assertRefused(TICKET.replace("Motif: demande-kevin, 2026-11-13 chat", "Motif:"),
                           "ticket", "`Motif` is empty")
        unfilled = PR.replace(
            "two-way: removing the hook entries restores the old behavior.",
            "<!-- `two-way` or `one-way` -->",
        )
        self.assertRefused(unfilled, "pr", "`Door` is empty")

    def test_too_many_words(self) -> None:
        for kind, cap in DEFAULT_WORDS.items():
            text = {"ticket": TICKET, "pr": PR, "session-reply": REPLY}.get(kind, "")
            with self.subTest(kind=kind):
                self.assertRefused(text + "\n" + prose(cap + 1), kind, f"at most {cap}")

    def test_a_paragraph_over_the_cap(self) -> None:
        self.assertRefused(words(DEFAULT_PARAGRAPH_WORDS + 1), "comment", "a paragraph of 61 words")
        self.assertRefused(f"- {words(61)}\n- short\n", "comment", "a paragraph of 61 words")
        self.assertRefused(VERDICT.replace("all probes pass", words(61)), "verdict", "paragraph")

    def test_a_reply_lists_more_than_two_elements(self) -> None:
        self.assertRefused(REPLY + "\n- a\n- b\n- c\n", "session-reply", "go in a table")
        self.assertEqual(deviations(REPLY + "\n- a\n- b\n", "session-reply"), [])

    def test_a_verdict_that_contradicts_itself(self) -> None:
        accept = VERDICT.replace("VERDICT: REJECT", "VERDICT: ACCEPT")
        self.assertRefused(accept, "verdict", "`VERDICT: ACCEPT` with 1 `[BLOCKER]`")
        no_blocker = VERDICT.replace("[BLOCKER]", "[MINOR]")
        self.assertRefused(no_blocker, "verdict", "no `[BLOCKER]` finding")
        self.assertRefused(VERDICT.replace("REJECT", "MAYBE"), "verdict", "ACCEPT or REJECT")
        self.assertRefused(VERDICT.replace("ROUND: 1", "ROUND: 4"), "verdict", "past round 3")
        self.assertRefused(VERDICT.replace("0123456789abcdef", "zz", 1), "verdict", "hexadecimal")
        bad = VERDICT.replace("- [BLOCKER]", "* BLOCKER")
        self.assertRefused(bad, "verdict", "it must read `- [BLOCKER|MINOR|NOTE]")

    def test_a_coder_block_out_of_form(self) -> None:
        self.assertRefused("Done, PR opened.", "coder", "no line starts with `RESULT:`")
        self.assertRefused(CODER_PR.replace("RESULT: PR", "RESULT: DONE"), "coder", "PR, BLOCKED")
        self.assertRefused(CODER_PR.replace("NOTES: none\n", ""), "coder", "`NOTES:`")
        self.assertRefused(CODER_PR.replace("#12 closes", "twelve"), "coder", "it must start with `#<number>`")

    def test_a_decision_without_its_decision(self) -> None:
        self.assertRefused(DECIDER.replace("DECISION:", "ANSWER:"), "decider", "`DECISION:`")

    def test_a_gate_without_a_table_or_with_too_long_a_table(self) -> None:
        self.assertRefused("All probes pass.", "gate", "no line starts with `|`")
        self.assertRefused(GATE + "| x | y | z |\n" * 30, "gate", "at most 30")

    def test_an_unknown_kind_is_a_usage_error(self) -> None:
        with self.assertRaises(ValueError):
            deviations("x", "letter")


class ProjectKeys(unittest.TestCase):
    def test_a_word_key_raises_or_lifts_the_cap(self) -> None:
        text = REPLY + "\n" + prose(200)
        self.assertNotEqual(deviations(text, "session-reply"), [])
        self.assertEqual(deviations(text, "session-reply", {"output-words-session-reply": ["400"]}), [])
        self.assertEqual(deviations(text, "session-reply", {"output-words-session-reply": ["0"]}), [])

    def test_an_unreadable_word_key_keeps_the_default(self) -> None:
        text = REPLY + "\n" + prose(200)
        found = deviations(text, "session-reply", {"output-words-session-reply": ["many"]})
        self.assertTrue(any("at most 150" in deviation for deviation in found))

    def test_the_paragraph_key(self) -> None:
        self.assertEqual(deviations(words(70), "comment", {"output-words-paragraph": ["80"]}), [])
        found = deviations(words(30), "comment", {"output-words-paragraph": ["20"]})
        self.assertTrue(any("at most 20" in deviation for deviation in found))

    def test_a_project_template_replaces_the_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            header = "<!-- template: pr | max-lines: 40 | required: Résumé, Porte -->\n"
            (root / "pr.md").write_text(header + "## Résumé\n\n## Porte\n", encoding="utf-8")
            config = {"output-template": ["pr | pr.md"]}
            french = "## Résumé\n\nAjoute le garde.\n\n## Porte\n\ntwo-way\n"
            self.assertEqual(deviations(french, "pr", config, root), [])
            found = deviations("## Résumé\n\nx\n", "pr", config, root)
            self.assertTrue(any("`Porte` is missing" in deviation for deviation in found))

    def test_a_project_maps_its_agents_to_a_format(self) -> None:
        config = {"output-agent-format": ["security | exempt", "arbiter | decider", "x | bogus"]}
        self.assertEqual(agent_kind("security", config), "exempt")
        self.assertEqual(agent_kind("arbiter", config), "decider")
        self.assertEqual(agent_kind("x", config), "subagent-return")
        self.assertEqual(agent_kind("Explore", config), "subagent-return")
        self.assertEqual(agent_kind("forge:coder", {}), "coder")


class TemplatesAndAgents(unittest.TestCase):
    """The validator reads the templates and the agents' declared formats, never a copy."""

    def test_every_kind_with_a_template_has_one_with_its_header(self) -> None:
        for kind, spec in KINDS.items():
            if spec.template is None:
                continue
            with self.subTest(kind=kind):
                text = (support.PLUGIN / "templates" / spec.template).read_text(encoding="utf-8")
                header = text.splitlines()[0]
                self.assertRegex(header, rf"^<!-- template: {kind} \| max-lines: \d+")
                self.assertIn("| required: ", header)

    def test_the_new_templates_stay_within_their_line_cap(self) -> None:
        for name in ("comment.md", "subagent-return.md", "session-reply.md"):
            text = (support.PLUGIN / "templates" / name).read_text(encoding="utf-8")
            cap = int(re.search(r"max-lines: (\d+)", text).group(1))  # type: ignore[union-attr]
            with self.subTest(template=name):
                self.assertLessEqual(len(text.splitlines()) - 1, cap)

    def test_the_verdict_has_one_source_of_rules_parse_output(self) -> None:
        text = (support.PLUGIN / "templates" / "verdict.md").read_text(encoding="utf-8")
        self.assertEqual(required_fields(text), [])
        self.assertIsNone(KINDS["verdict"].template)
        for key in ("ROUND", "HEAD", "SPEC", "GATES"):
            with self.subTest(key=key):
                found = deviations(re.sub(rf"(?m)^{key}:.*\n", "", VERDICT), "verdict")
                self.assertTrue(any(f"`{key}:`" in deviation for deviation in found), found)

    def test_the_reply_template_names_the_three_fields_in_both_languages(self) -> None:
        text = (support.PLUGIN / "templates" / "session-reply.md").read_text(encoding="utf-8")
        fields = required_fields(text)
        self.assertEqual(len(fields), 5)  # `CI and runners` is A6 of forge#181, `Features` A11
        self.assertIn(["Features"], fields)
        for english, french in (("Done", "Fait"), ("Measured", "Mesure"),
                                ("Awaiting your decision", "Attend ta décision")):
            self.assertTrue(any(english in f and french in f for f in fields), fields)

    def test_a1_the_reply_template_puts_the_three_fields_in_one_table_then_the_ci_line_and_features(self) -> None:
        """F-0181 ticket #252 A1: one `Field | State` table, then the CI line and Features."""
        text = (support.PLUGIN / "templates" / "session-reply.md").read_text(encoding="utf-8")
        body = text.split("\n", 1)[1].split("\n- ", 1)[0].strip().splitlines()
        lines = [line for line in body if line.strip()]
        self.assertEqual(lines[0], "| Field | State |")
        self.assertRegex(lines[1], r"^\|\s*:?-{3,}:?\s*\|\s*:?-{3,}:?\s*\|$")
        self.assertEqual([line.split("|")[1].strip() for line in lines[2:5]],
                         ["Done", "Measured", "Awaiting your decision"])
        self.assertTrue(lines[5].startswith("CI and runners:"), lines[5])
        self.assertTrue(lines[6].startswith("Features:"), lines[6])
        self.assertEqual(len(lines), 7)

    def test_a1_the_reply_template_filled_in_conforms(self) -> None:
        text = (support.PLUGIN / "templates" / "session-reply.md").read_text(encoding="utf-8")
        body = text.split("\n", 1)[1].split("\n- ", 1)[0]
        filled = re.sub(r"(?m)^Features:.*$", lambda _: FEATURES_BLOCK.rstrip(), body)
        filled = re.sub(r"<[^>\n]*>", "text", filled)
        self.assertEqual(deviations(filled, "session-reply"), [])

    def test_each_forge_agent_the_validator_names_exists_and_declares_its_keys(self) -> None:
        declared = {
            "coder": {"RESULT", *(key for keys in RESULT_KEYS.values() for key in keys)},
            "verdict": set(VERDICT_KEYS),
            "decider": {"VERDICT", "DECISION"},
            "gate": set(),
            "exempt": set(),
        }
        for agent, kind in FORGE_AGENTS.items():
            path = support.PLUGIN / "agents" / f"{agent.removeprefix('forge:')}.md"
            with self.subTest(agent=agent):
                self.assertTrue(path.is_file())
                text = path.read_text(encoding="utf-8")
                for key in declared[kind]:
                    self.assertRegex(text, rf"(?m)^{key}:")
        gate = (support.PLUGIN / "agents" / "qc-gate.md").read_text(encoding="utf-8")
        self.assertIn("au plus trente lignes", gate)

    def test_the_usine_template_documents_every_key(self) -> None:
        text = (support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8")
        for key in [f"output-words-{name}" for name in DEFAULT_WORDS] + [
            "output-words-paragraph", "output-template", "output-agent-format",
        ]:
            with self.subTest(key=key):
                self.assertIn(f"`{key}`", text)


class CommandLine(unittest.TestCase):
    def run_main(self, argv: list[str], text: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(
            "os.environ", {"CLAUDE_PROJECT_DIR": folder, "HOME": folder, "USERPROFILE": folder},
            clear=True,
        ), mock.patch("sys.stdin", io.StringIO(text)), mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ) as out, mock.patch("sys.stderr", new_callable=io.StringIO):
            return main(argv), out.getvalue()

    def test_exit_codes(self) -> None:
        self.assertEqual(self.run_main(["session-reply", "-"], REPLY), (0, ""))
        code, out = self.run_main(["ticket"], "nothing")
        self.assertEqual(code, 1)
        self.assertIn("- the field `Motif` is missing", out)
        self.assertEqual(self.run_main(["letter"], "x")[0], 2)


class StaffDecisionOfTheThirteenth(unittest.TestCase):
    """The 60-word cap holds in verdicts too; a span between backticks counts as one word."""

    def test_a_span_between_backticks_counts_as_one_word(self) -> None:
        spans = " ".join(["`git merge-tree --write-tree origin/main abc1234`"] * 15)
        paragraph = f"{words(45)} {spans}"
        self.assertEqual(deviations(paragraph, "comment"), [])
        found = deviations(f"{words(46)} {spans}", "comment")
        self.assertTrue(any("a paragraph of 61 words" in d for d in found), found)

    def test_a_verdict_with_spec_and_gates_sub_lines_conforms(self) -> None:
        verdict = (
            "VERDICT: ACCEPT\nROUND: 1\nHEAD: abcdef1\nSPEC:\n"
            "  - #12: 1 criteria covered, 0 partial, 0 missing\nFINDINGS:\n- none\nGATES:\n"
            f"  - CI: {words(50)}\n  - merge-tree: `git merge-tree --write-tree origin/main x` clean\n"
        )
        self.assertEqual(deviations(verdict, "verdict"), [])

    def test_a_gates_sub_line_over_the_cap_is_refused(self) -> None:
        verdict = (
            "VERDICT: ACCEPT\nROUND: 1\nHEAD: abcdef1\nSPEC:\n  - #12: 1 covered\n"
            f"FINDINGS:\n- none\nGATES:\n  - CI: {words(60)}\n"
        )
        found = deviations(verdict, "verdict")
        self.assertTrue(any("a paragraph of 61 words" in d for d in found), found)


class MeridianReviewChecks(unittest.TestCase):
    """The review of the MeridianRE session, 2026-11-13, on `deviations`."""

    def assertRefused(self, text: str, kind: str, phrase: str, config: dict[str, list[str]] | None = None) -> None:
        found = deviations(text, kind, config)
        self.assertTrue(any(phrase in deviation for deviation in found), found)

    def test_code_blocks_and_table_cells_count_in_the_total(self) -> None:
        code = "```\n" + "\n".join(words(30) for _ in range(30)) + "\n```\n"
        self.assertRefused(f"Done.\n\n{code}", "comment", "at most 150")
        self.assertRefused(f"Done.\n\n| {words(800)} |\n", "comment", "at most 150")

    def test_the_paragraph_rule_skips_tables_and_code_blocks(self) -> None:
        text = f"Done.\n\n| {words(70)} |\n\n```\n{words(70)}\n```\n"
        self.assertFalse(any("paragraph" in d for d in deviations(text, "comment")))

    def test_an_unknown_key_is_refused_in_a_structured_format(self) -> None:
        self.assertRefused(VERDICT.replace("GATES:", "GARBAGE: x\nGATES:"), "verdict", "`GARBAGE:`")
        self.assertRefused(CODER_PR + "GARBAGE: x\n", "coder", "`GARBAGE:`")
        self.assertRefused(DECIDER + "GARBAGE: x\n", "decider", "`GARBAGE:`")

    def test_a_project_declares_the_extra_keys_of_its_verdict(self) -> None:
        text = VERDICT.replace("GATES:", "REGIME: strict\nREMARKS:\n- [REMARK] a.py:1 | r | s\nGATES:")
        self.assertRefused(text, "verdict", "`REGIME:`")
        config = {"output-extra-keys": ["verdict | REGIME, VERIFIED, REMARKS, OUT OF SCOPE"]}
        self.assertEqual(deviations(text, "verdict", config), [])

    def test_the_verdict_rules_come_from_parse_verdict(self) -> None:
        self.assertRefused(VERDICT.replace("ROUND: 1", "ROUND: 4"), "verdict", "`GRANTED: <https link>`")
        grant = "ROUND: 4\nGRANTED: https://github.com/o/r/issues/9#issuecomment-1"
        self.assertEqual(deviations(VERDICT.replace("ROUND: 1", grant), "verdict"), [])

    def test_an_accept_may_leave_findings_empty(self) -> None:
        accept = VERDICT.replace("VERDICT: REJECT", "VERDICT: ACCEPT").replace(
            "- [BLOCKER] a.py:3 | A1 | the cap is never read\n", ""
        )
        self.assertEqual(deviations(accept, "verdict"), [])

    def test_a_round_followed_by_text_is_refused(self) -> None:
        self.assertRefused(VERDICT.replace("ROUND: 1", "ROUND: 2 (after the sync)"), "verdict", "`ROUND:")

    def test_an_agent_without_the_forge_prefix_is_matched_by_its_name(self) -> None:
        for name, kind in [("coder", "coder"), ("qc-conf", "verdict"), ("staff-engineer", "decider")]:
            with self.subTest(name=name):
                self.assertEqual(agent_kind(name, {}), kind)
        self.assertEqual(agent_kind("other:coder", {}), "subagent-return")


class LineCap(unittest.TestCase):
    """The `max-lines` of a template header caps the written lines of the text it shapes."""

    def test_each_capped_kind_refuses_one_line_past_its_cap(self) -> None:
        for kind in ("comment", "subagent-return", "session-reply", "ticket", "pr"):
            cap = line_cap(_template_text(kind, {}, None))
            assert cap is not None, kind
            with self.subTest(kind=kind):
                text = "\n".join(f"- point {index}" for index in range(cap + 1))
                found = deviations(text, kind)
                self.assertIn(f"{cap + 1} lines, at most {cap} (template `{kind}`)", " ".join(found))

    def test_blank_lines_and_html_comments_do_not_count(self) -> None:
        text = "\n\n".join(f"- point {index}" for index in range(12)) + "\n<!-- a\nb\nc -->\n"
        self.assertEqual([d for d in deviations(text, "comment") if "lines" in d], [])

    def test_a_verdict_keeps_every_finding(self) -> None:
        # the review never shortens its findings to fit a cap, of words or of lines
        findings = "".join(f"- [BLOCKER] a.py:{n} | A1 | broken\n" for n in range(40))
        verdict = VERDICT.replace("FINDINGS:\n", "FINDINGS:\n" + findings, 1)
        self.assertEqual(deviations(verdict, "verdict"), [])

    def test_a_project_template_brings_its_own_cap(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "c.md").write_text("<!-- template: comment | max-lines: 2 | required: none -->\nx\n", encoding="utf-8")
            config = {"output-template": ["comment | c.md"]}
            self.assertTrue(any("at most 2" in d for d in deviations("a\nb\nc", "comment", config, Path(folder))))

    def test_max_lines_zero_means_no_cap_as_a_zero_word_cap_does(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "p.md").write_text("<!-- template: pr | max-lines: 0 | required: none -->\nx\n", encoding="utf-8")
            config = {"output-template": ["pr | p.md"], "output-words-pr": ["0"]}
            text = "\n".join(f"- line {index}" for index in range(80))
            self.assertIsNone(line_cap(_template_text("pr", config, Path(folder))))
            self.assertEqual(deviations(text, "pr", config, Path(folder)), [])

    def test_a_kind_without_a_template_has_no_line_cap(self) -> None:
        self.assertIsNone(line_cap(_template_text("decider", {}, None)))


if __name__ == "__main__":
    unittest.main()
