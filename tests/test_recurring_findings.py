"""F-0002 C04: `recurring_findings.py` counts the distinct PRs that cite a finding id, and writes one comment."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import support  # noqa: F401  puts the plugin on the import path
from recurring_findings import MARKER, main
from test_factory_slo import isolate

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
COMMENTS = "repos/{owner}/{repo}/issues/55/comments"
FRESH = (NOW - timedelta(days=3)).isoformat()
OLD = (NOW - timedelta(days=40)).isoformat()
USINE = "# Usine\n\n- `recurring-finding` : `3 | 30`\n- `slo-issue` : `55`\n"


def rule(identifier: str, severity: str = "BLOCKER") -> str:
    return f"- [{severity}] hook.py:12 | {identifier} | the hook lets a heredoc through"


def verdict(findings: list[str], when: str = FRESH, round_: int = 1) -> dict:
    result = "REJECT" if any("[BLOCKER]" in line for line in findings) else "ACCEPT"
    body = (
        f"VERDICT: {result}\nROUND: {round_}\nHEAD: abcdef1\nSPEC: #1: 1 criteria covered\n"
        f"FINDINGS:\n{chr(10).join(findings) or '- none'}\nGATES: ok"
    )
    return {"body": body, "createdAt": when}


def pr(number: int, *comments: dict) -> dict:
    return {"number": number, "comments": list(comments)}


class FakeGitHub:
    """`gh` as the script calls it: the PR list, the comments of the ticket, and each write it receives."""

    def __init__(self, prs: list[dict]) -> None:
        self.prs = prs
        self.comments: list[dict] = []
        self.writes: list[list[str]] = []
        self.calls: list[list[str]] = []
        self.ticket_missing = False

    def __call__(self, cmd: list[str], cwd: Path) -> str:
        self.calls.append(cmd)
        args = cmd[1:]
        if args[:2] == ["pr", "list"]:
            return json.dumps(self.prs)
        if args[:2] == ["api", "--paginate"] and args[2] == COMMENTS:
            if self.ticket_missing:
                raise RuntimeError("`gh api --paginate repos/{owner}/{repo}/issues/55/comments` a échoué : Not Found")
            return json.dumps(self.comments)
        if args[0] == "api" and args[1] == COMMENTS:
            self.writes.append(args)
            ident = 700 + len(self.comments)
            self.comments.append({"id": ident, "body": args[3].removeprefix("body=")})
            return json.dumps({"id": ident})
        if args[:3] == ["api", "-X", "PATCH"]:
            self.writes.append(args)
            ident = int(args[3].rsplit("/", 1)[1])
            next(c for c in self.comments if c["id"] == ident)["body"] = args[5].removeprefix("body=")
            return json.dumps({"id": ident})
        raise AssertionError(f"unexpected gh call: {cmd}")


class Recurring(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate(self, self.tmp.name)
        self.project = Path(self.tmp.name) / "projet"
        (self.project / "docs" / "agents").mkdir(parents=True)
        self.configure(USINE)

    def configure(self, text: str) -> None:
        (self.project / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def run_main(self, github: FakeGitHub) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(self.project)], run=github, now=NOW)
        return code, out.getvalue(), err.getvalue()

    def test_three_distinct_prs_in_the_window_list_the_id_with_its_prs(self) -> None:
        """F-0002 A29: three distinct PRs judged in 30 days that cite `F-25` get it listed with its PRs; older ones do not count."""
        github = FakeGitHub([
            pr(10, verdict([rule("F-25")])),
            pr(11, verdict([rule("F-25")])),
            pr(12, verdict([rule("F-25"), rule("L-3", "MINOR")])),
            pr(13, verdict([rule("L-3")], OLD)),
        ])
        code, _, _ = self.run_main(github)
        self.assertEqual(code, 0)
        self.assertEqual(len(github.comments), 1)
        body = github.comments[0]["body"]
        self.assertTrue(body.startswith(MARKER))
        self.assertIn("| F-25 | 3 | #10, #11, #12 |", body)
        self.assertIn("2026-10-26", body)
        self.assertNotIn("L-3", body)

    def test_two_prs_or_one_pr_over_several_rounds_are_not_listed(self) -> None:
        """F-0002 A30: two distinct PRs, or one PR citing the id over three rounds, count as fewer than three."""
        github = FakeGitHub([
            pr(10, verdict([rule("F-25")]), verdict([rule("F-25")], round_=2), verdict([rule("F-25")], round_=3)),
            pr(11, verdict([rule("F-25")])),
        ])
        code, out, _ = self.run_main(github)
        self.assertEqual(code, 0)
        self.assertEqual(github.writes, [])
        self.assertIn("aucun identifiant cité par 3 PR distinctes", out)

    def test_a_finding_without_an_id_is_counted_apart(self) -> None:
        """F-0002 A31: a finding that cites neither `F-n` nor `L-n` is counted on its own line, never as an id."""
        loose = [rule("A3.1"), "- [NOTE] docs.md:4 | wording of the changelog"]
        github = FakeGitHub([pr(10, verdict([rule("F-25"), *loose])), pr(11, verdict([rule("F-25")])), pr(12, verdict([rule("F-25")]))])
        self.run_main(github)
        body = github.comments[0]["body"]
        self.assertIn("| F-25 | 3 | #10, #11, #12 |", body)
        self.assertIn("Constats sans identifiant : 2, sur 1 PR", body)
        self.assertNotIn("A3.1", body)


if __name__ == "__main__":
    unittest.main()
