"""Hold the tickets of a feature in the GitHub graph, not only in their text.

    python ticket_graph.py link <suivi> <ticket>...
    python ticket_graph.py check <suivi> <ticket>...

`link` runs at publication: each ticket becomes a sub-issue of the tracking issue `<suivi>`, and
each dependency its text declares (a line `Blocked by #n`, `#n, #m` or `#n and #m`) becomes a
`blocked_by` link of the graph. A link the graph already holds is not added twice. `check` runs
after it and lists each ticket that is not a sub-issue of the tracking issue, and each declared
dependency the graph lacks, one line each: `GRAPH ok` and exit 0 when nothing is listed, `GRAPH
missing` and exit 1 otherwise. A call to `gh` that fails exits 2 with its error: an unread graph is
never an `ok`. `feature-build` and `report_mail.py` read the graph (`issue_dependencies_summary`), not
the text, so a dependency written only in a ticket's body blocks nothing for them. The calls run in
the repository of the working directory (`gh api` fills `{owner}/{repo}`). The standard library only.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable, Sequence

Gh = Callable[[list[str]], str]

ISSUES = "repos/{owner}/{repo}/issues"
BLOCKED_BY = "dependencies/blocked_by"
SUB_ISSUES = "sub_issues"
DEPENDENCY_LINE = re.compile(
    r"(?im)^[ \t]*(?:[-*][ \t]+)?(?:\*\*)?Blocked by(?:\*\*)?[ \t]*:?[ \t]*"
    r"(#\d+(?:[ \t]*(?:,|and)[ \t]*#\d+)*)"
)


class GraphError(RuntimeError):
    """A `gh` call that failed, so that the graph is not known."""


def declared(body: str) -> list[int]:
    """The tickets a body declares itself blocked by, in order, without repeats."""
    numbers: list[int] = []
    for line in DEPENDENCY_LINE.findall(body):
        for number in re.findall(r"#(\d+)", line):
            if int(number) not in numbers:
                numbers.append(int(number))
    return numbers


def _run_gh(argv: list[str]) -> str:
    try:
        done = subprocess.run(["gh", *argv], capture_output=True, encoding="utf-8", check=False)
    except OSError as error:
        raise GraphError(f"gh cannot run: {error}") from error
    if done.returncode != 0:
        raise GraphError(f"`gh {' '.join(argv)}` failed: {done.stderr.strip()}")
    return done.stdout


def _numbers(gh: Gh, issue: int, edge: str) -> set[int]:
    out = gh(["api", f"{ISSUES}/{issue}/{edge}", "--paginate", "--jq", ".[].number"])
    return {int(line) for line in out.split() if line.isdigit()}


def _body(gh: Gh, issue: int) -> str:
    return gh(["api", f"{ISSUES}/{issue}", "--jq", ".body"])


def _id(gh: Gh, issue: int) -> str:
    return gh(["api", f"{ISSUES}/{issue}", "--jq", ".id"]).strip()


def link(gh: Gh, tracking: int, tickets: Sequence[int]) -> list[str]:
    """Add what the graph lacks; the lines say each link added."""
    done: list[str] = []
    attached = _numbers(gh, tracking, SUB_ISSUES)
    for ticket in tickets:
        if ticket not in attached:
            gh(["api", "-X", "POST", f"{ISSUES}/{tracking}/{SUB_ISSUES}", "-F", f"sub_issue_id={_id(gh, ticket)}"])
            done.append(f"#{ticket} sub-issue of #{tracking}")
        held = _numbers(gh, ticket, BLOCKED_BY)
        for blocker in declared(_body(gh, ticket)):
            if blocker not in held:
                gh(["api", "-X", "POST", f"{ISSUES}/{ticket}/{BLOCKED_BY}", "-F", f"issue_id={_id(gh, blocker)}"])
                done.append(f"#{ticket} blocked by #{blocker}")
    return done


def main(argv: Sequence[str] | None = None, gh: Gh = _run_gh) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3 or args[0] not in ("link", "check") or not all(a.isdigit() for a in args[1:]):
        print("usage: ticket_graph.py link|check <suivi> <ticket>...", file=sys.stderr)
        return 2
    tracking, tickets = int(args[1]), [int(a) for a in args[2:]]
    try:
        if args[0] == "link":
            for line in link(gh, tracking, tickets):
                print(line)
            return 0
    except GraphError as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
