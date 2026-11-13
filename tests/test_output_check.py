"""The validator of every exchange: one test per deviation it refuses, one per conforming text."""

import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from output_check import (
    DEFAULT_PARAGRAPH_WORDS,
    DEFAULT_WORDS,
    FORGE_AGENTS,
    KINDS,
    agent_kind,
    deviations,
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
REPLY = """Done: merged #12 at abc1234.

Measured: CI 4 min 10 s, run 99, 2026-11-13, 1 run of 1.

Awaiting your decision: nothing.
"""
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
            "RESULT: BLOCKED\nTICKET: none\nQUESTION: which cap?\nRECOMMENDATION: 150\nSTATE: pushed\n"
        )
        failed = "RESULT: FAILED\nTICKET: #3\nCOMMAND: make\nOUTPUT: error\nSTATE: not pushed\n"
        self.assertEqual(deviations(blocked, "coder"), [])
        self.assertEqual(deviations(failed, "coder"), [])

    def test_a_keyed_block_wrapped_in_a_fence_is_read_as_its_keys(self) -> None:
        self.assertEqual(deviations(f"```text\n{CODER_PR}```\n", "coder"), [])
        long_gates = VERDICT.replace("all probes pass", " ".join(["word"] * 61))
        self.assertTrue(any("paragraph" in d for d in deviations(long_gates, "verdict")))

    def test_the_reply_labels_hold_in_french_and_in_markup(self) -> None:
        reply = (
            "**Fait** : PR #12 fusionnée.\n\n## Mesure\n\nCI 4 min.\n\n"
            "| Attend ta décision | rien |\n|---|---|\n"
        )
        self.assertEqual(deviations(reply, "session-reply"), [])

    def test_a_key_written_with_a_space_before_its_colon_counts(self) -> None:
        self.assertEqual(deviations(TICKET.replace("Motif:", "Motif :"), "ticket"), [])

    def test_a_verdict_with_optional_keys_and_long_findings_conforms(self) -> None:
        findings = "".join(f"- [BLOCKER] a.py:{n} | A1 | {words(25)}\n" for n in range(12))
        verdict = (
            "VERDICT: REJECT\nROUND: 3\nREGIME: strict\nHEAD: abcdef1\nSPEC: none (pin bump)\n"
            f"FINDINGS:\n{findings}REMARKS:\n- [REMARK] a.py:1 | r | s\nGATES: pass\n"
        )
        self.assertEqual(deviations(verdict, "verdict"), [])

    def test_tables_code_blocks_and_html_comments_do_not_count(self) -> None:
        table = "".join(f"| {words(10)} |\n" for _ in range(30))
        code = "```\n" + "\n".join(words(30) for _ in range(20)) + "\n```\n"
        comment = f"<!-- {words(300)} -->\n"
        text = f"Merged.\n\n{table}\n{code}\n{comment}"
        self.assertEqual(deviations(text, "comment"), [])

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
        self.assertRefused(VERDICT.replace("GATES:", "PROBES:"), "verdict", "`GATES` is missing")
        self.assertRefused(REPLY.replace("Measured:", "Numbers:"), "session-reply", "`Measured`")

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
        self.assertRefused(VERDICT.replace("ROUND: 1", "ROUND: 4"), "verdict", "1, 2 or 3")
        self.assertRefused(VERDICT.replace("0123456789abcdef", "zz", 1), "verdict", "hexadecimal")
        bad = VERDICT.replace("- [BLOCKER]", "* BLOCKER")
        self.assertRefused(bad, "verdict", "it must read `- [BLOCKER|MINOR|NOTE]")

    def test_a_coder_block_out_of_form(self) -> None:
        self.assertRefused("Done, PR opened.", "coder", "no line starts with `RESULT:`")
        self.assertRefused(CODER_PR.replace("RESULT: PR", "RESULT: DONE"), "coder", "PR, BLOCKED")
        self.assertRefused(CODER_PR.replace("NOTES: none\n", ""), "coder", "`NOTES:`")
        self.assertRefused(CODER_PR.replace("#12 closes", "twelve"), "coder", "`#<number>` or `none`")

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

    def test_the_verdict_template_requires_the_keys_parse_output_reads(self) -> None:
        text = (support.PLUGIN / "templates" / "verdict.md").read_text(encoding="utf-8")
        self.assertEqual([labels[0] for labels in required_fields(text)], list(VERDICT_KEYS))

    def test_the_reply_template_names_the_three_fields_in_both_languages(self) -> None:
        text = (support.PLUGIN / "templates" / "session-reply.md").read_text(encoding="utf-8")
        fields = required_fields(text)
        self.assertEqual(len(fields), 3)
        for english, french in (("Done", "Fait"), ("Measured", "Mesure"),
                                ("Awaiting your decision", "Attend ta décision")):
            self.assertTrue(any(english in f and french in f for f in fields), fields)

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


if __name__ == "__main__":
    unittest.main()
