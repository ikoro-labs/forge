"""The ticket graph (ticket #269): the published tickets become sub-issues of the tracking issue
and a `blocked_by` link per declared dependency, then a check names what the graph lacks.

The seam is the `gh` call, the boundary of the system, simulated by a small in-memory GitHub.
Cases of the ticket: A1.1, A2.1.
"""

import io
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout

import support  # noqa: F401  puts the scripts on the import path
from ticket_graph import GraphError, main

TRACKING = 10
ISSUE = r"repos/\{owner\}/\{repo\}/issues/(\d+)(?:/(sub_issues|dependencies/blocked_by))?"


class FakeGitHub:
    """Issues by number (id = 1000 + number, and a body), the sub-issues of each issue and its
    `blocked_by` links, answered to the `gh api` calls the script makes."""

    def __init__(self, bodies: dict[int, str]) -> None:
        self.bodies = dict(bodies)
        self.subs: dict[int, set[int]] = {TRACKING: set()}
        self.blocked: dict[int, set[int]] = {}
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> str:
        self.calls.append(argv)
        write = "-X" in argv
        endpoint = argv[argv.index("-X") + 2] if write else argv[1]
        found = re.fullmatch(ISSUE, endpoint)
        assert found, argv
        number, edge = int(found.group(1)), found.group(2)
        links = self.subs if edge == "sub_issues" else self.blocked
        if write:
            field = next(a for a in argv if a.startswith(("sub_issue_id=", "issue_id=")))
            links.setdefault(number, set()).add(int(field.split("=", 1)[1]) - 1000)
            return ""
        if edge is None:
            return str(1000 + number) if argv[-1] == ".id" else self.bodies[number]
        return "".join(f"{n}\n" for n in sorted(links.get(number, set())))


def run(github: FakeGitHub, *args: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = main([*args], gh=github)
    return code, out.getvalue()


class Publication(unittest.TestCase):
    def test_a1_1_a_declared_dependency_becomes_a_blocked_by_link(self) -> None:
        """#269 A1: B declares "Blocked by #A", the graph then says B blocked_by A."""
        github = FakeGitHub({11: "First ticket.", 12: "Blocked by #11\n\nSecond ticket."})
        code, _out = run(github, "link", str(TRACKING), "11", "12")
        self.assertEqual(code, 0)
        self.assertEqual(github.blocked, {12: {11}})

    def test_a1_each_ticket_becomes_a_sub_issue_of_the_tracking_issue(self) -> None:
        """#269 A1: the published tickets are sub-issues of the tracking issue."""
        github = FakeGitHub({11: "First ticket.", 12: "Blocked by #11"})
        run(github, "link", str(TRACKING), "11", "12")
        self.assertEqual(github.subs[TRACKING], {11, 12})

    def test_a1_a_second_run_adds_nothing(self) -> None:
        """#269 A1: a link the graph holds is not posted again (GitHub refuses a duplicate)."""
        github = FakeGitHub({11: "First ticket.", 12: "Blocked by #11"})
        run(github, "link", str(TRACKING), "11", "12")
        github.calls.clear()
        run(github, "link", str(TRACKING), "11", "12")
        self.assertEqual([c for c in github.calls if "-X" in c], [])

    def test_a1_every_spelling_of_the_declaration_is_read(self) -> None:
        """#269 A1: a list, a bullet, bold and a colon declare a dependency like the plain line."""
        github = FakeGitHub(
            {
                11: "x",
                12: "x",
                13: "x",
                14: "- **Blocked by**: #11, #12 and #13\n\nBody",
                15: "Mentions #11 in prose, blocked by nothing; see also Blocked by design",
            }
        )
        run(github, "link", str(TRACKING), "14", "15")
        self.assertEqual(github.blocked, {14: {11, 12, 13}})


class Check(unittest.TestCase):
    def test_a2_1_a_text_dependency_without_graph_link_is_named(self) -> None:
        """#269 A2: the check names the ticket whose text declares a dependency the graph lacks."""
        github = FakeGitHub({11: "First ticket.", 12: "Blocked by #11"})
        github.subs[TRACKING] = {11, 12}
        code, out = run(github, "check", str(TRACKING), "11", "12")
        self.assertEqual(code, 1)
        self.assertIn("#12 declares `Blocked by #11`", out)
        self.assertIn("GRAPH missing", out)

    def test_a2_the_check_is_clean_once_the_graph_holds_every_link(self) -> None:
        """#269 A2: publication is done only when the list is empty."""
        github = FakeGitHub({11: "First ticket.", 12: "Blocked by #11"})
        run(github, "link", str(TRACKING), "11", "12")
        code, out = run(github, "check", str(TRACKING), "11", "12")
        self.assertEqual((code, out.strip()), (0, "GRAPH ok"))

    def test_a2_a_ticket_that_is_not_a_sub_issue_is_named(self) -> None:
        """#269 A2: a ticket left out of the tracking issue is invisible to feature-build too."""
        github = FakeGitHub({11: "First ticket."})
        code, out = run(github, "check", str(TRACKING), "11")
        self.assertEqual(code, 1)
        self.assertIn("#11 is not a sub-issue of #10", out)

    def test_a2_the_check_changes_nothing(self) -> None:
        """#269 A2: the check only reads."""
        github = FakeGitHub({11: "First ticket.", 12: "Blocked by #11"})
        run(github, "check", str(TRACKING), "11", "12")
        self.assertEqual([c for c in github.calls if "-X" in c], [])

    def test_a2_a_graph_gh_cannot_read_is_never_ok(self) -> None:
        """#269 A2: a failing gh exits 2 and prints no `GRAPH ok`."""

        def failing(argv: list[str]) -> str:
            raise GraphError("gh: HTTP 403")

        err = io.StringIO()
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["check", str(TRACKING), "11"], gh=failing)
        self.assertEqual(code, 2)
        self.assertNotIn("ok", out.getvalue())
        self.assertIn("HTTP 403", err.getvalue())


if __name__ == "__main__":
    unittest.main()
