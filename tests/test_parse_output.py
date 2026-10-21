import io
import unittest
from unittest import mock

import support  # noqa: F401
from parse_output import OutputError, main, parse_result, parse_verdict

PR_RESULT = """J'ai ouvert la PR.

```
RESULT: PR
PR: #61
TICKET: #12 closes
CRITERIA: A1 OK, A2 OK
NOTES: the migration is idempotent
  and replayed twice
```
"""

VERDICT = """VERDICT: REJECT
ROUND: 1
HEAD: 3f2a9c1
SPEC: #12 A1 met
SPEC: #12 A2 missing
FINDINGS:
- [BLOCKER] src/a.py:12 rule X: an empty list crashes
- [NOTE] wording
GATES: 9 probes, 1 NOT RUN
"""


class Result(unittest.TestCase):
    def test_a_pr_result_after_prose_and_in_a_fence_is_read(self) -> None:
        parsed = parse_result(PR_RESULT)
        self.assertEqual(parsed["PR"], "#61")
        self.assertEqual(parsed["TICKET"], "#12 closes")
        self.assertEqual(parsed["NOTES"], "the migration is idempotent\nand replayed twice")

    def test_blocked_and_failed_take_their_own_keys(self) -> None:
        blocked = "RESULT: BLOCKED\nTICKET: #12\nQUESTION: q\nRECOMMENDATION: r\nSTATE: s\n"
        self.assertEqual(parse_result(blocked)["RESULT"], "BLOCKED")
        failed = "RESULT: FAILED\nTICKET: #12\nCOMMAND: pnpm test\nOUTPUT: 3 failed\nSTATE: s\n"
        self.assertEqual(parse_result(failed)["COMMAND"], "pnpm test")

    def test_each_defect_is_named(self) -> None:
        for text, words in [
            ("nothing here", "no line starts with `RESULT:`"),
            ("RESULT: DONE\nTICKET: #1\n", "PR, BLOCKED or FAILED"),
            ("RESULT: PR\nPR: #1\nTICKET: #2 closes\nCRITERIA: x\n", "`NOTES:`"),
            ("RESULT: PR\nPR: 61\nTICKET: #2 closes\nCRITERIA: x\nNOTES: n\n", "`PR: 61`"),
            ("RESULT: PR\nPR: #1\nTICKET: #2\nCRITERIA: x\nNOTES: n\n", "`closes` or `refs`"),
            ("RESULT: PR\nPR: #1\nPR: #2\nTICKET: #2 refs\nCRITERIA: x\nNOTES: n\n", "twice"),
            ("RESULT: BLOCKED\nTICKET: #1\nQUESTION: q\nRECOMMENDATION: r\nSTATE: s\nPR: #3\n", "takes no `PR:`"),
            ("RESULT: FAILED\nTICKET: 12\nCOMMAND: c\nOUTPUT: o\nSTATE: s\n", "`#<number>`"),
        ]:
            with self.subTest(text=text):
                with self.assertRaises(OutputError) as raised:
                    parse_result(text)
                self.assertIn(words, str(raised.exception))


class Verdict(unittest.TestCase):
    def test_a_verdict_is_read_with_its_findings(self) -> None:
        parsed = parse_verdict(VERDICT)
        self.assertEqual(parsed["ROUND"], 1)
        self.assertEqual(parsed["SPEC"], ["#12 A1 met", "#12 A2 missing"])
        self.assertEqual([finding["severity"] for finding in parsed["FINDINGS"]], ["BLOCKER", "NOTE"])

    def test_an_accept_without_findings_is_read(self) -> None:
        text = VERDICT.replace("REJECT", "ACCEPT").replace(
            "- [BLOCKER] src/a.py:12 rule X: an empty list crashes\n- [NOTE] wording", "aucun"
        )
        self.assertEqual(parse_verdict(text)["FINDINGS"], [])

    def test_a_verdict_without_ticket_says_none_and_why(self) -> None:
        text = VERDICT.replace(
            "SPEC: #12 A1 met\nSPEC: #12 A2 missing",
            "SPEC: none (a Dependabot bump,\n  judged against its changelog)",
        )
        self.assertEqual(
            parse_verdict(text)["SPEC"], ["none (a Dependabot bump,\njudged against its changelog)"]
        )

    def test_a_verdict_without_ticket_needs_its_reason_and_stands_alone(self) -> None:
        for spec, words in [
            ("SPEC: none", "`none (<reason>)`"),
            ("SPEC: none ( )", "`none (<reason>)`"),
            ("SPEC: no ticket", "or the one line reads `none (<reason>)`"),
            ("SPEC: none (a pin bump)\nSPEC: #12 A1 met", "stands alone"),
        ]:
            with self.subTest(spec=spec):
                text = VERDICT.replace("SPEC: #12 A1 met\nSPEC: #12 A2 missing", spec)
                with self.assertRaises(OutputError) as raised:
                    parse_verdict(text)
                self.assertIn(words, str(raised.exception))

    def test_the_verdict_and_its_findings_must_agree(self) -> None:
        for text, words in [
            (VERDICT.replace("- [BLOCKER]", "- [MINOR]"), "only a blocker rejects"),
            (VERDICT.replace("REJECT", "ACCEPT"), "1 `[BLOCKER]`"),
            (VERDICT.replace("ROUND: 1", "ROUND: 3"), "1 or 2"),
            (VERDICT.replace("HEAD: 3f2a9c1", "HEAD: main"), "hexadecimal SHA"),
            (VERDICT.replace("SPEC: #12 A1", "SPEC: A1"), "`#<ticket>`"),
            (VERDICT.replace("- [NOTE] wording", "wording"), "`- [BLOCKER|MINOR|NOTE] ...`"),
            (VERDICT.replace("GATES: 9 probes, 1 NOT RUN\n", ""), "`GATES:`"),
        ]:
            with self.subTest(words=words):
                with self.assertRaises(OutputError) as raised:
                    parse_verdict(text)
                self.assertIn(words, str(raised.exception))


class Cli(unittest.TestCase):
    def run_cli(self, argv: list[str], stdin: str) -> tuple[int, str]:
        out = io.StringIO()
        with (
            mock.patch("sys.stdin", io.StringIO(stdin)),
            mock.patch("sys.stdout", out),
            mock.patch("sys.stderr", io.StringIO()),
        ):
            return main(argv), out.getvalue()

    def test_exit_codes(self) -> None:
        self.assertEqual(self.run_cli(["result", "-"], PR_RESULT)[0], 0)
        code, out = self.run_cli(["verdict", "-"], "VERDICT: MAYBE\n")
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("invalid verdict: "))
        self.assertEqual(self.run_cli(["other", "-"], "")[0], 2)


if __name__ == "__main__":
    unittest.main()
