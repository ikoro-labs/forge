"""Ticket #314: a ticket holds at most `ticket-pr-cap` PRs, held by `guard_pr_cap`, gh simulated.

The criteria of the ticket, numbered in the order it lists them:

- A1: a PR citing `Closes|Refs #n` is refused when #n already has the cap's PRs, open or merged
  (gh, regex, reservation), and the guard fails closed;
- A2: the key `ticket-pr-cap`, no default, "sans objet" without it;
- A3: the refusal is the 4th PR's `BLOCKED`: comment on the ticket, `needs-your-attention`, no new ticket;
- A4: only the label `pr-cap-raised`, set by a human (author checked), raises the cap to 6;
- A5: the briefs of `forge:coder` and `forge:feature-build` state the cap;
- A6: the template line, the `docs/` page, the CHANGELOG entry;
- A7: the tests cite the criteria and run on Linux and Windows (HOME and USERPROFILE isolated);
- A8 (asked by the human on 2026-11-23, the grant of round 4): the key `ticket-pr-cap-since` (`AAAA-MM-JJ`)
  keeps out of the count the PRs created before that day (`createdAt`); without it every PR counts;
- A9 (decision of the human on 2026-11-23, comment 7114825269): a ticket with a PR created before that
  day finishes the PR in flight, then admits one last new PR instead of the cap; the label still raises to 6.

Third part of #314 (the decision of the human of 2026-11-25 and the staff-engineer's, whose criteria restart at
A1; the tests of this part say "part 3"):

- A1: the key `ticket-pr-cap-exempt` (one `type(scope)` per line) takes a PR whose title starts with
  `type(scope):` out of the count of a ticket, open or merged, the title read in the one `gh pr list` call;
  absent, every PR counts; the key is protected;
- A2: a PR being created is exempt only through its `--title` / `-t` argument;
- A3: the template documents the key;
- A4: the page, the coder's brief, the judge's grid and this repository's `usine.md`;
- A5: these tests (HOME and USERPROFILE isolated, no `CLAUDE_` variable, Linux and Windows).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from unittest import mock

import support
from guard_pr_cap import Runner, refusal
from usine import SENSITIVE_KEYS

USINE = (
    "# Usine\n- `ticket-pr-cap` : `3`\n- `accepting-human` : `Kevin Humain | the-human`\n"
    "- `pr-cap-raiser` : `Kevin Humain | the-human`\n"
)
SINCE = "- `ticket-pr-cap-since` : `2026-11-23`\n"


def pr_body(*lines: str) -> str:
    return "\n".join(["## Summary", "", "What changes.", "", *lines, ""])


class FakeGh:
    """`gh pr list`, `gh pr view` and the events of an issue answered from lists; None plays a gh error."""

    def __init__(
        self,
        prs: Sequence[tuple[str, str]] | None = (),
        viewed: tuple[int, str] | None = None,
        events: list[dict] | None = None,
        issue: dict | None = None,
        created: Sequence[str | None] | None = None,
        titles: Sequence[str | None] | None = None,
        sizes: Sequence[tuple[object, object]] | None = None,
    ) -> None:
        self.sizes = sizes  # (additions, deletions) of each listed PR, None as a field leaves it out (None as a whole: no fields)
        self.titles = titles  # title of each listed PR, None leaves the field out (None as a whole: no field)
        self.created = created  # createdAt of each listed PR, None leaves the field out (None as a whole: no field)
        self.prs = prs  # (state, body) of each PR gh lists; None plays an unreachable gh
        self.viewed = viewed  # (number, body) of the PR `gh pr view` gives, None plays a gh error
        self.events = events  # the events of the ticket; None plays a gh error
        self.issue = issue  # what `gh api repos/<o>/<r>/issues/<n>` gives, None plays a gh error
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], cwd: str | None) -> str | None:
        self.calls.append(argv)
        if argv[:2] == ["pr", "view"]:
            if self.viewed is None:
                return None
            return json.dumps({"number": self.viewed[0], "body": self.viewed[1]})
        if argv[:1] == ["api"] and "/events" not in argv[1]:
            return None if self.issue is None else json.dumps(self.issue)
        if argv[:1] == ["api"]:
            return None if self.events is None else json.dumps(self.events)
        if argv[:2] == ["pr", "list"]:
            if self.prs is None:
                return None
            listed = [
                {"number": 100 + n, "state": state, "body": body}
                for n, (state, body) in enumerate(self.prs)
            ]
            if self.created is not None:
                for item, stamp in zip(listed, self.created):
                    if stamp is not None:
                        item["createdAt"] = stamp
            if self.titles is not None:
                for item, title in zip(listed, self.titles):
                    if title is not None:
                        item["title"] = title
            if self.sizes is not None:
                for item, (added, removed) in zip(listed, self.sizes):
                    if added is not None:
                        item["additions"] = added
                    if removed is not None:
                        item["deletions"] = removed
            return json.dumps(listed)
        return None

    def asked(self, *words: str) -> list[list[str]]:
        return [call for call in self.calls if list(words) == call[: len(words)]]


def cited(count: int, ticket: int = 5, state: str = "MERGED", verb: str = "Closes") -> FakeGh:
    return FakeGh([(state, pr_body(f"{verb} #{ticket}")) for _ in range(count)])


class Project:
    """A project folder with its usine.md, the session's CLAUDE_ variables kept out, HOME isolated."""

    def __init__(
        self,
        test: unittest.TestCase,
        usine: str | None = USINE,
        memory: bool = False,
    ) -> None:
        self.dir = Path(tempfile.mkdtemp())
        test.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "docs" / "agents").mkdir(parents=True)
        if usine is not None:
            (self.dir / "docs" / "agents" / "usine.md").write_text(usine, encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
        env.update(HOME=str(self.dir), USERPROFILE=str(self.dir))
        if memory:
            env["CLAUDE_PLUGIN_DATA"] = str(self.dir / "plugin-data")
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        test.addCleanup(patcher.stop)

    def body_file(self, body: str, name: str = "body.md") -> str:
        path = self.dir / name
        path.write_text(body, encoding="utf-8")
        return path.as_posix()

    def bash(self, command: str, gh: Runner) -> str | None:
        event = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.dir)}
        return refusal(event, gh)

    def create(self, body: str, gh: Runner) -> str | None:
        return self.bash(f"gh pr create --title T --body-file {self.body_file(body)}", gh)

    def edit(self, body: str, gh: Runner, selector: str = "7") -> str | None:
        return self.bash(f"gh pr edit {selector} --body-file {self.body_file(body)}", gh)

    def tool(self, name: str, tool_input: dict, gh: Runner) -> str | None:
        event = {"tool_name": name, "tool_input": tool_input, "cwd": str(self.dir)}
        return refusal(event, gh)


class CapOfPrs(unittest.TestCase):
    def test_a_pr_that_reaches_the_cap_is_let_through(self) -> None:
        """Ticket #314, A1: a ticket with two PRs, open or merged, takes its third."""
        project = Project(self)
        gh = FakeGh([("OPEN", pr_body("Refs #5")), ("MERGED", pr_body("Closes #5"))])
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))
        listing = gh.asked("pr", "list")
        self.assertEqual(len(listing), 1)
        self.assertIn("--state", listing[0])
        self.assertEqual(listing[0][listing[0].index("--state") + 1], "all")
        self.assertIn("5 in:body", listing[0])

    def test_a_pr_past_the_cap_is_refused(self) -> None:
        """Ticket #314, A1: a ticket that already has three PRs, open or merged, takes no fourth."""
        project = Project(self)
        gh = FakeGh(
            [
                ("OPEN", pr_body("Refs #5")),
                ("MERGED", pr_body("Refs #5")),
                ("MERGED", pr_body("Closes #5")),
            ]
        )
        reason = project.create(pr_body("Closes #5"), gh) or ""
        self.assertIn("#5 already has 3 PRs", reason)
        self.assertIn("ticket-pr-cap", reason)

    def test_a_pr_closed_without_merge_is_not_counted(self) -> None:
        """Ticket #314, A1: open or merged only; a PR closed unmerged leaves its place."""
        project = Project(self)
        gh = FakeGh(
            [
                ("CLOSED", pr_body("Refs #5")),
                ("OPEN", pr_body("Refs #5")),
                ("MERGED", pr_body("Closes #5")),
            ]
        )
        self.assertIsNone(project.create(pr_body("Refs #5"), gh))

    def test_only_a_citation_of_that_number_counts(self) -> None:
        """Ticket #314, A1: `Closes|Refs #n` by regex; #50, a bare 5 and `See #5` are no citation of #5."""
        project = Project(self)
        gh = FakeGh(
            [
                ("MERGED", pr_body("Closes #50")),
                ("MERGED", pr_body("See #5 and 5 more")),
                ("MERGED", pr_body("Closes #5")),
            ]
        )
        self.assertIsNone(project.create(pr_body("Refs #5"), gh))

    def test_the_citation_is_read_in_any_case_and_a_second_one_counts(self) -> None:
        """Ticket #314, A1: `closes #5` counts, and a PR citing two tickets is checked on each."""
        project = Project(self)
        gh = FakeGh([("OPEN", pr_body("closes #5")), ("OPEN", pr_body("REFS #5")), ("OPEN", pr_body("refs #5"))])
        self.assertIn("#5 already has 3", project.create(pr_body("Refs #9", "Closes #5"), gh) or "")

    def test_every_form_that_links_a_ticket_to_a_pr_is_a_citation(self) -> None:
        """Ticket #314, A1: `Closes: #n`, `Closes owner/repo#n`, `Fixes`, `Resolves`, `Refs: #n`, `Refs #n, #m` count."""
        project = Project(self)
        for line in (
            "Closes: #5",
            "Closes ikoro-labs/forge#5",
            "Fixes #5",
            "resolved: #5",
            "Refs: #5",
            "Refs #9, #5",
        ):
            with self.subTest(line=line):
                self.assertIn("#5 already has 3", project.create(pr_body(line), cited(3)) or "")
                counted = FakeGh([("MERGED", pr_body(line)) for _ in range(3)])
                self.assertIn("#5 already has 3", project.create(pr_body("Closes #5"), counted) or "")
        self.assertIsNone(project.create(pr_body("Closes: #50"), cited(3)))

    def test_a_pr_that_cites_no_ticket_is_not_looked_up(self) -> None:
        """Ticket #314, A1: a body without `Closes|Refs #n` costs no gh call."""
        project = Project(self)
        gh = cited(9)
        self.assertIsNone(project.create(pr_body("A note, no ticket."), gh))
        self.assertEqual(gh.calls, [])

    def test_the_repository_named_is_the_one_searched(self) -> None:
        """Ticket #314, A1: `--repo o/r` is passed to the search."""
        project = Project(self)
        gh = cited(0)
        command = f"gh pr create --repo o/r --title T --body-file {project.body_file(pr_body('Closes #5'))}"
        self.assertIsNone(project.bash(command, gh))
        self.assertEqual(gh.asked("pr", "list")[0][-2:], ["--repo", "o/r"])


class Gestures(unittest.TestCase):
    """A1: every gesture that opens or edits a PR is read, behind a wrapper too."""

    def test_an_edit_that_adds_a_ticket_to_a_full_one_is_refused(self) -> None:
        """Ticket #314, A1: `gh pr edit` that adds `Refs #5` to a PR counts as a new PR of #5."""
        project = Project(self)
        gh = cited(3)
        gh.viewed = (7, pr_body("A PR with no ticket yet."))
        self.assertIn("#5 already has 3 PRs", project.edit(pr_body("Refs #5"), gh) or "")
        self.assertEqual(gh.asked("pr", "view")[0][:3], ["pr", "view", "7"])

    def test_an_edit_that_keeps_its_ticket_is_never_refused(self) -> None:
        """Ticket #314, A1: a PR already counted for #5 is not a new one; its report goes through."""
        project = Project(self)
        gh = cited(4)  # the PR itself and three others, say after the cap was raised and lowered
        gh.viewed = (7, pr_body("Closes #5"))
        self.assertIsNone(project.edit(pr_body("Closes #5", "", "Rapport d'agent: tout va bien."), gh))
        self.assertEqual(gh.asked("pr", "list"), [])

    def test_the_pr_being_edited_is_not_counted_against_itself(self) -> None:
        """Ticket #314, A1: editing PR #101 to add a ticket it cites with two others leaves it at the cap."""
        project = Project(self)
        gh = cited(3)  # PRs 100, 101, 102 cite #5; the edited one is 101
        gh.viewed = (101, pr_body("Refs #8"))
        self.assertIsNone(project.edit(pr_body("Refs #5", "Refs #8"), gh))

    def test_an_edit_without_a_body_is_not_read(self) -> None:
        """Ticket #314, A1: `gh pr edit --add-label` carries no body and no citation."""
        project = Project(self)
        gh = cited(9)
        self.assertIsNone(project.bash("gh pr edit 7 --add-label needs-your-attention", gh))
        self.assertEqual(gh.calls, [])

    def test_a_pr_of_the_current_branch_is_resolved_by_gh(self) -> None:
        """Ticket #314, A1: `gh pr edit` without a selector asks gh which PR the branch has."""
        project = Project(self)
        gh = cited(3)
        gh.viewed = (7, pr_body(""))
        command = f"gh pr edit --body-file {project.body_file(pr_body('Refs #5'))}"
        self.assertIn("#5 already has 3", project.bash(command, gh) or "")
        self.assertEqual(gh.asked("pr", "view")[0][:3], ["pr", "view", "--json"])

    def test_a_body_in_a_heredoc_and_a_nested_shell_are_read(self) -> None:
        """Ticket #314, A1: `bash -c` and `$(cat <<'EOF')` do not hide the citation."""
        project = Project(self)
        command = "bash -c \"gh pr create --title T --body 'Closes #5'\""
        self.assertIn("#5 already has 3", project.bash(command, cited(3)) or "")
        heredoc = "gh pr create --title T --body \"$(cat <<'EOF'\nCloses #5\nEOF\n)\""
        self.assertIn("#5 already has 3", project.bash(heredoc, cited(3)) or "")

    def test_gh_api_on_the_pulls_endpoints_is_read(self) -> None:
        """Ticket #314, A1: a POST on `pulls` and a PATCH on `pulls/<n>` carry the body to count."""
        project = Project(self)
        path = project.body_file(pr_body("Closes #5"))
        create = f"gh api -X POST repos/o/r/pulls -f title=T -f head=h -f base=main -F body=@{path}"
        self.assertIn("#5 already has 3", project.bash(create, cited(3)) or "")
        gh = cited(3)
        gh.viewed = (7, pr_body(""))
        patch = f"gh api -X PATCH repos/o/r/pulls/7 -F body=@{path}"
        self.assertIn("#5 already has 3", project.bash(patch, gh) or "")
        self.assertEqual(gh.asked("pr", "list")[0][-2:], ["--repo", "o/r"])

    def test_gh_api_on_the_issues_endpoint_is_read_when_the_issue_is_a_pr(self) -> None:
        """Ticket #314, A1: a PR is an issue; a PATCH on `issues/<n>` that is a PR adds its tickets to the count."""
        project = Project(self)
        path = project.body_file(pr_body("Closes #5"))
        patch = f"gh api -X PATCH repos/o/r/issues/7 -F body=@{path}"
        gh = cited(3)
        gh.issue = {"number": 7, "body": pr_body("No ticket yet."), "pull_request": {"url": "u"}}
        self.assertIn("#5 already has 3", project.bash(patch, gh) or "")
        self.assertEqual(gh.asked("pr", "list")[0][-2:], ["--repo", "o/r"])
        self.assertEqual(gh.asked("api")[0][1], "repos/o/r/issues/7")
        # a PR that already cites the ticket is not a new one, and is not counted against itself
        kept = cited(2)
        kept.issue = {"number": 7, "body": pr_body("Closes #5"), "pull_request": {"url": "u"}}
        self.assertIsNone(project.bash(patch, kept))
        self.assertEqual(kept.asked("pr", "list"), [])

    def test_gh_api_on_the_issues_endpoint_lets_a_real_ticket_be_edited(self) -> None:
        """Ticket #314, A1: a ticket (no `pull_request`) is edited freely, even when its body names a full ticket."""
        project = Project(self)
        path = project.body_file(pr_body("Blocked by Closes #5 is the other ticket"))
        patch = f"gh api -X PATCH repos/o/r/issues/8 -F body=@{path}"
        gh = cited(3)
        gh.issue = {"number": 8, "body": "old", "title": "a ticket"}
        self.assertIsNone(project.bash(patch, gh))
        self.assertEqual(gh.asked("pr", "list"), [])
        plain = project.body_file(pr_body("A ticket body that cites no ticket."))
        untouched = cited(3)
        self.assertIsNone(project.bash(f"gh api -X PATCH repos/o/r/issues/8 -F body=@{plain}", untouched))
        self.assertEqual(untouched.calls, [])
        created = cited(3)
        self.assertIsNone(project.bash(f"gh api -X POST repos/o/r/issues -F body=@{path}", created))
        self.assertEqual(created.calls, [])

    def test_an_issue_gh_cannot_read_is_refused_when_its_body_cites_a_ticket(self) -> None:
        """Ticket #314, A1: fails closed: whether #7 is a PR is unknown, so the edit is refused."""
        project = Project(self)
        patch = f"gh api -X PATCH repos/o/r/issues/7 -F body=@{project.body_file(pr_body('Refs #5'))}"
        self.assertIn("cannot be read", project.bash(patch, cited(0)) or "")

    def test_an_mcp_issue_edit_is_read_as_gh_api_on_the_issues_endpoint(self) -> None:
        """Ticket #314, A1: `update_issue` on a PR number edits the PR; a real ticket is left free."""
        project = Project(self)
        pull = {"number": 7, "body": pr_body("No ticket yet."), "pull_request": {"url": "u"}}
        edited = {"owner": "o", "repo": "r", "issue_number": 7, "body": "Closes #5"}
        gh = cited(3)
        gh.issue = pull
        self.assertIn("#5 already has 3", project.tool("mcp__github__update_issue", edited, gh) or "")
        self.assertEqual(gh.asked("api")[0][1], "repos/o/r/issues/7")
        self.assertEqual(gh.asked("pr", "list")[0][-2:], ["--repo", "o/r"])
        written = {**edited, "method": "update"}
        self.assertIn("#5 already has 3", project.tool("mcp__github__issue_write", written, gh) or "")
        # a PR that already cites the ticket is not a new one
        kept = cited(2)
        kept.issue = {**pull, "body": pr_body("Closes #5")}
        self.assertIsNone(project.tool("mcp__github__update_issue", edited, kept))
        # a real ticket is not a PR: its body is free, whatever it cites
        ticket = cited(3)
        ticket.issue = {"number": 8, "body": "old", "title": "a ticket"}
        self.assertIsNone(project.tool("mcp__github__update_issue", {**edited, "issue_number": 8}, ticket))
        self.assertEqual(ticket.asked("pr", "list"), [])
        # opening a ticket, or an edit that carries no body, costs no gh call
        created = cited(3)
        opened = {"owner": "o", "repo": "r", "title": "T", "body": "Closes #5"}
        self.assertIsNone(project.tool("mcp__github__create_issue", opened, created))
        self.assertIsNone(project.tool("mcp__github__update_issue", {"owner": "o", "repo": "r", "issue_number": 7, "state": "closed"}, created))
        self.assertEqual(created.calls, [])

    def test_an_mcp_issue_edit_gh_cannot_read_is_refused(self) -> None:
        """Ticket #314, A1: fails closed: whether #7 is a PR is unknown, and no number names no issue."""
        project = Project(self)
        edited = {"owner": "o", "repo": "r", "issue_number": 7, "body": "Refs #5"}
        self.assertIn("cannot be read", project.tool("mcp__github__update_issue", edited, cited(0)) or "")
        unnamed = {"owner": "o", "repo": "r", "body": "Refs #5"}
        self.assertIn("cannot be read", project.tool("mcp__github__update_issue", unnamed, cited(0)) or "")

    def test_a_curl_to_the_issues_of_the_api_is_read_as_gh_api_on_the_issues_endpoint(self) -> None:
        """Ticket #314, A1: another HTTP client edits a PR through `issues/<n>` as `gh api` does: a PR is refused, a ticket is free."""
        project = Project(self)
        command = "curl -X PATCH -d '{\"body\": \"Closes #5\"}' https://api.github.com/repos/o/r/issues/7"
        pull = cited(3)
        pull.issue = {"number": 7, "body": pr_body("No ticket yet."), "pull_request": {"url": "u"}}
        self.assertIn("api.github.com", project.bash(command, pull) or "")
        self.assertEqual(pull.asked("api")[0][1], "repos/o/r/issues/7")
        ticket = cited(3)
        ticket.issue = {"number": 7, "body": "old", "title": "a ticket"}
        self.assertIsNone(project.bash(command, ticket))
        self.assertEqual(ticket.asked("pr", "list"), [])
        self.assertIn("cannot be read", project.bash(command, cited(0)) or "")
        # the comments of an issue and the opening of a ticket are not an edit of it
        free = cited(3)
        for other in (
            "curl -X POST -d @b.json https://api.github.com/repos/o/r/issues/7/comments",
            "curl -X POST -d @b.json https://api.github.com/repos/o/r/issues",
        ):
            with self.subTest(command=other):
                self.assertIsNone(project.bash(other, free))
        self.assertEqual(free.calls, [])

    def test_gh_issue_edit_of_a_pr_number_is_read_as_gh_api_on_the_issues_endpoint(self) -> None:
        """Ticket #314, A1: `gh issue view` resolves a PR number, so `gh issue edit 7` may edit a PR's body."""
        project = Project(self)
        pull = cited(3)
        pull.issue = {"number": 7, "body": pr_body("No ticket yet."), "pull_request": {"url": "u"}}
        self.assertIn("#5 already has 3", project.bash("gh issue edit 7 --body 'Closes #5'", pull) or "")
        self.assertEqual(pull.asked("api")[0][1], "repos/{owner}/{repo}/issues/7")
        named = cited(3)
        named.issue = pull.issue
        edit = "gh issue edit 7 -R o/r --body 'Closes #5'"
        self.assertIn("#5 already has 3", project.bash(edit, named) or "")
        self.assertEqual(named.asked("api")[0][1], "repos/o/r/issues/7")
        self.assertEqual(named.asked("pr", "list")[0][-2:], ["--repo", "o/r"])
        by_url = cited(3)
        by_url.issue = pull.issue
        url = "gh issue edit https://github.com/o/r/issues/7 --body 'Closes #5'"
        self.assertIn("#5 already has 3", project.bash(url, by_url) or "")
        self.assertEqual(by_url.asked("api")[0][1], "repos/o/r/issues/7")
        ticket = cited(3)
        ticket.issue = {"number": 8, "body": "old", "title": "a ticket"}
        self.assertIsNone(project.bash("gh issue edit 8 --body 'Closes #5'", ticket))
        self.assertEqual(ticket.asked("pr", "list"), [])
        self.assertIn("cannot be read", project.bash("gh issue edit 7 --body 'Refs #5'", cited(0)) or "")

    def test_a_github_mcp_tool_that_opens_or_edits_a_pr_is_read(self) -> None:
        """Ticket #314, A1: `create_pull_request` and `update_pull_request` carry the body to count."""
        project = Project(self)
        opened = {"owner": "o", "repo": "r", "title": "T", "body": "Closes #5", "head": "h", "base": "main"}
        self.assertIn("#5 already has 3", project.tool("mcp__github__create_pull_request", opened, cited(3)) or "")
        gh = cited(3)
        gh.viewed = (7, pr_body(""))
        edited = {"owner": "o", "repo": "r", "pullNumber": 7, "body": "Refs #5"}
        self.assertIn("#5 already has 3", project.tool("mcp__github__update_pull_request", edited, gh) or "")
        self.assertIsNone(project.tool("mcp__github__add_issue_comment", {"body": "Closes #5"}, cited(3)))

    def test_a_command_that_publishes_no_pr_is_not_read(self) -> None:
        """Ticket #314, A1: a ticket, a comment and a read cost no gh call."""
        project = Project(self)
        gh = cited(9)
        for command in (
            "gh issue create --title T --body 'Closes #5'",
            "gh pr comment 7 --body 'Refs #5'",
            "gh pr list --search 'Closes #5'",
            "echo gh",
        ):
            with self.subTest(command=command):
                self.assertIsNone(project.bash(command, gh))
        self.assertEqual(gh.calls, [])


class FailsClosed(unittest.TestCase):
    """A1: what the guard cannot read or count, it refuses."""

    def test_a_count_gh_cannot_make_is_refused(self) -> None:
        """Ticket #314, A1: gh absent, the network or a gh error refuses the PR."""
        project = Project(self)
        self.assertIn("cannot be counted", project.create(pr_body("Closes #5"), FakeGh(None)) or "")

    @staticmethod
    def answering(text: str) -> Runner:
        def run(argv: list[str], cwd: str | None) -> str | None:
            return text

        return run

    def test_an_answer_that_is_no_list_of_prs_is_refused(self) -> None:
        """Ticket #314, A1: a gh that answers something else than a list counts nothing, so refuses."""
        project = Project(self)
        for output in ("not json", "{}", '[{"number": "x"}]', "[1]"):
            with self.subTest(output=output):
                refused = project.create(pr_body("Closes #5"), self.answering(output))
                self.assertIn("cannot be counted", refused or "")

    def test_an_edit_whose_pr_gh_cannot_give_is_refused(self) -> None:
        """Ticket #314, A1: the current body of the PR is needed to know which tickets are new."""
        project = Project(self)
        self.assertIn("cannot be read", project.edit(pr_body("Refs #5"), cited(0)) or "")

    def test_a_body_the_hook_cannot_read_is_refused(self) -> None:
        """Ticket #314, A1: a variable, a substitution and a missing file are refused, not let through."""
        project = Project(self)
        for command in (
            'gh pr create --title T --body "$BODY"',
            'gh pr create --title T --body "$(make_body)"',
            "gh pr create --title T --body-file /nope/missing.md",
            "gh pr create --title T --fill",
            "gh pr create --title T",
        ):
            with self.subTest(command=command):
                self.assertIn("cannot be read", project.bash(command, cited(0)) or "")

    def test_a_graphql_mutation_that_cites_a_ticket_is_refused(self) -> None:
        """Ticket #314, A1: `createPullRequest` hides the PR from the count; the hook refuses it."""
        project = Project(self)
        query = 'mutation { createPullRequest(input: {title: "T", body: "Closes #5"}) { pullRequest { id } } }'
        refused = project.bash(f"gh api graphql -f query='{query}'", cited(0))
        self.assertIn("mutation is refused", refused or "")

    def test_a_curl_to_the_pulls_of_the_api_is_refused(self) -> None:
        """Ticket #314, A1: another HTTP client would open the PR unread."""
        project = Project(self)
        command = "curl -X POST https://api.github.com/repos/o/r/pulls -d @body.json"
        self.assertIn("api.github.com", project.bash(command, cited(0)) or "")

    def test_a_crash_of_the_guard_refuses_the_call(self) -> None:
        """Ticket #314, A1: run as the hook runs, an event that is no JSON exits 2 and says why."""
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
        env.update(HOME=str(home), USERPROFILE=str(home))
        done = subprocess.run(
            [sys.executable, str(support.PLUGIN / "hooks" / "guard_pr_cap.py")],
            input="not json",
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        self.assertEqual(done.returncode, 2)
        self.assertIn("guard_pr_cap failed", done.stderr)


class Reservation(unittest.TestCase):
    """A1: a PR the hook let through counts for ten minutes, GitHub's search lagging."""

    def test_a_pr_let_through_counts_before_the_search_shows_it(self) -> None:
        """Ticket #314, A1: two PRs listed, a third let through, a fourth body refused at once."""
        project = Project(self, memory=True)
        self.assertIsNone(project.create(pr_body("Refs #5", "Third part."), cited(2)))
        self.assertIn("#5 already has 3 PRs", project.create(pr_body("Refs #5", "Fourth part."), cited(2)) or "")

    def test_the_same_body_retried_is_the_same_pr(self) -> None:
        """Ticket #314, A1: a `gh pr create` that failed afterwards is retried without a place lost."""
        project = Project(self, memory=True)
        body = pr_body("Refs #5", "Third part.")
        self.assertIsNone(project.create(body, cited(2)))
        self.assertIsNone(project.create(body, cited(2)))

    def test_a_refused_call_reserves_nothing(self) -> None:
        """Ticket #314, A1: one ticket full, the other not: the PR is refused and #8 keeps its place."""
        project = Project(self, memory=True)
        self.assertIn("#5 already has", project.create(pr_body("Refs #8", "Refs #5"), cited(3)) or "")
        listing = FakeGh([("MERGED", pr_body("Refs #8")), ("MERGED", pr_body("Refs #8"))])
        self.assertIsNone(project.create(pr_body("Refs #8", "Other."), listing))

    def test_without_the_data_directory_the_hook_keeps_no_memory(self) -> None:
        """Ticket #314, A1: an older Claude Code leaves no state file; the count is GitHub's alone."""
        project = Project(self, memory=False)
        self.assertIsNone(project.create(pr_body("Refs #5", "Third."), cited(2)))
        self.assertIsNone(project.create(pr_body("Refs #5", "Fourth."), cited(2)))


class TheKey(unittest.TestCase):
    """A2: `ticket-pr-cap`, one whole number, no default, sans objet without it."""

    def test_without_the_key_the_step_is_not_applicable_and_nothing_is_read(self) -> None:
        """Ticket #314, A2: no key, no default cap: a ticket with ten PRs takes an eleventh, no gh call."""
        for usine in ("# Usine\n- `accepting-human` : `x`\n", None):
            with self.subTest(usine=usine):
                project = Project(self, usine)
                gh = cited(10)
                self.assertIsNone(project.create(pr_body("Closes #5"), gh))
                self.assertEqual(gh.calls, [])

    def test_the_cap_is_the_value_of_the_key(self) -> None:
        """Ticket #314, A2: a cap of 2 refuses the third PR, a cap of 4 lets a fourth through."""
        two = Project(self, "- `ticket-pr-cap` : `2`\n")
        self.assertIn("#5 already has 2 PRs for a cap of 2", two.create(pr_body("Closes #5"), cited(2)) or "")
        four = Project(self, "- `ticket-pr-cap` : `4`\n")
        self.assertIsNone(four.create(pr_body("Closes #5"), cited(3)))
        self.assertIn("cap of 4", four.create(pr_body("Closes #5"), cited(4)) or "")

    def test_a_value_that_is_no_whole_number_above_zero_refuses_a_pr_that_cites_a_ticket(self) -> None:
        """Ticket #314, A2: `three`, `0`, `-1`, `3 PRs` and a repeated key name the key; no default is guessed."""
        for lines in ("`three`", "`0`", "`-1`", "`3 PRs`", "``"):
            with self.subTest(value=lines):
                project = Project(self, f"- `ticket-pr-cap` : {lines}\n")
                self.assertIn("`ticket-pr-cap`", project.create(pr_body("Closes #5"), cited(0)) or "")
        repeated = Project(self, "- `ticket-pr-cap` : `3`\n- `ticket-pr-cap` : `4`\n")
        self.assertIn("`ticket-pr-cap`", repeated.create(pr_body("Closes #5"), cited(0)) or "")

    def test_an_unreadable_value_refuses_nothing_that_cites_no_ticket(self) -> None:
        """Ticket #314, A2: a PR with no `Closes|Refs #n` is not held by a key that cannot be read."""
        project = Project(self, "- `ticket-pr-cap` : `three`\n")
        self.assertIsNone(project.create(pr_body("No ticket."), cited(0)))

    def test_the_template_documents_the_key_without_a_default(self) -> None:
        """Ticket #314, A2: the template names the key, its form, `sans objet` and the absence of a default."""
        text = " ".join((support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8").split())
        self.assertIn("- `ticket-pr-cap` : `<3>`", text)
        self.assertIn("sans objet (clé `ticket-pr-cap` absente)", text)
        self.assertIn("aucune valeur par défaut", text.split("- `ticket-pr-cap`")[0][-900:])
        self.assertIn("- `pr-cap-raiser` : `<", text)
        self.assertIn("sans objet (clé `pr-cap-raiser` absente)", text)
        self.assertIn("aucun jeton", text)

    def test_the_template_documents_the_date_key_without_a_default(self) -> None:
        """Ticket #314, A8: the template names `ticket-pr-cap-since`, its form, the PR date it reads and the absent key."""
        text = " ".join((support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8").split())
        self.assertIn("- `ticket-pr-cap-since` : `<AAAA-MM-JJ>`", text)
        before = text.split("- `ticket-pr-cap-since`")[0][-1500:]
        for phrase in ("createdAt", "avant cette date", "sans objet (clé `ticket-pr-cap-since` absente)", "aucune date par défaut"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, before)

    def test_this_repository_counts_from_the_day_the_human_asked(self) -> None:
        """Ticket #314, A8: `docs/agents/usine-gardes.md` (moved by #345) holds `ticket-pr-cap-since : 2026-11-23`."""
        text = support.repo_usine_text()
        self.assertIn("- `ticket-pr-cap-since` : `2026-11-23`", text)

    def test_the_plugin_names_no_date_of_its_own(self) -> None:
        """Ticket #314, A8: the plugin's content stays generic: the guard holds no date, no project, no ticket."""
        text = (support.PLUGIN / "hooks" / "guard_pr_cap.py").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"\b20\d\d-\d\d-\d\d\b")

    def test_this_repository_declares_the_key_at_six(self) -> None:
        """Ticket #381, A4 (was #367 at 4, #314 at 3): `docs/agents/usine-gardes.md` (moved by #345) holds `ticket-pr-cap : 6`, once."""
        text = support.repo_usine_text()
        self.assertEqual(re.findall(r"^- `ticket-pr-cap` : `(\d+)`$", text, re.MULTILINE), ["6"])


class SinceDate(unittest.TestCase):
    """A8: the key `ticket-pr-cap-since` counts only the PRs created on that day or after it."""

    def merged(self, *created: str | None, ticket: int = 5) -> FakeGh:
        return FakeGh([("MERGED", pr_body(f"Closes #{ticket}")) for _ in created], created=list(created))

    def test_a_pr_created_before_the_date_is_not_counted(self) -> None:
        """Ticket #314, A8: three PRs created before the day leave the cap untouched."""
        project = Project(self, USINE + SINCE)
        gh = self.merged("2026-11-22T23:59:59Z", "2026-11-01T08:00:00Z", "2025-01-01T00:00:00Z")
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))

    def test_a_pr_created_that_day_or_after_is_counted(self) -> None:
        """Ticket #314, A8: the day itself counts, from its first second, and so does any later day."""
        project = Project(self, USINE + SINCE)
        gh = self.merged("2026-11-23T00:00:00Z", "2026-11-23T18:30:00Z", "2026-12-02T09:00:00Z")
        self.assertIn("#5 already has 3 PRs", project.create(pr_body("Closes #5"), gh) or "")

    def test_old_and_recent_prs_are_counted_apart(self) -> None:
        """Ticket #314, A8: two old PRs and one recent one count one (a ticket started before the day, see A9)."""
        project = Project(self, USINE + SINCE)
        gh = self.merged("2026-11-20T10:00:00Z", "2026-11-21T10:00:00Z", "2026-11-23T10:00:00Z")
        self.assertIn("#5 already has 1 PRs", project.create(pr_body("Closes #5"), gh) or "")
        only_recent = self.merged("2026-11-23T10:00:00Z", "2026-11-24T10:00:00Z")
        self.assertIsNone(project.create(pr_body("Closes #5"), only_recent))

    def test_the_refusal_names_the_date_it_counts_from(self) -> None:
        """Ticket #314, A8: the message says the count starts at the date of the key."""
        project = Project(self, USINE + SINCE)
        gh = self.merged("2026-11-23T10:00:00Z", "2026-11-24T10:00:00Z", "2026-11-25T10:00:00Z")
        reason = project.create(pr_body("Closes #5"), gh) or ""
        self.assertIn("ticket-pr-cap-since", reason)
        self.assertIn("2026-11-23", reason)

    def test_the_listing_asks_for_the_creation_date(self) -> None:
        """Ticket #314, A8: `gh pr list --json` carries `createdAt`."""
        project = Project(self, USINE + SINCE)
        gh = self.merged("2026-11-23T10:00:00Z")
        project.create(pr_body("Closes #5"), gh)
        listing = gh.asked("pr", "list")[0]
        self.assertIn("createdAt", listing[listing.index("--json") + 1].split(","))

    def test_without_the_key_every_pr_counts_whatever_its_date(self) -> None:
        """Ticket #314, A8: no key `ticket-pr-cap-since`, no date step: the cap counts all the PRs, as before, with no default date."""
        project = Project(self, USINE)
        gh = self.merged("2020-01-01T00:00:00Z", "2021-01-01T00:00:00Z", None)
        self.assertIn("#5 already has 3 PRs", project.create(pr_body("Closes #5"), gh) or "")

    def test_the_date_alone_without_the_cap_reads_nothing(self) -> None:
        """Ticket #314, A8: the date filters the count of a cap; with no `ticket-pr-cap` the step is sans objet."""
        project = Project(self, "# Usine\n" + SINCE)
        gh = self.merged("2026-11-23T10:00:00Z")
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))
        self.assertEqual(gh.calls, [])

    def test_a_date_that_cannot_be_read_refuses_a_pr_that_cites_a_ticket(self) -> None:
        """Ticket #314, A8: fails closed: a value that is no `AAAA-MM-JJ` day, empty or repeated names the key."""
        for value in ("`tomorrow`", "`23/11/2026`", "`2026-13-45`", "`2026-02-30`", "`2026-11-23T10:00:00Z`", "``"):
            with self.subTest(value=value):
                project = Project(self, USINE + f"- `ticket-pr-cap-since` : {value}\n")
                refused = project.create(pr_body("Closes #5"), self.merged("2026-11-23T10:00:00Z")) or ""
                self.assertIn("`ticket-pr-cap-since`", refused)
        repeated = Project(self, USINE + SINCE + "- `ticket-pr-cap-since` : `2026-11-24`\n")
        self.assertIn("`ticket-pr-cap-since`", repeated.create(pr_body("Closes #5"), self.merged()) or "")

    def test_an_unreadable_date_holds_back_nothing_that_cites_no_ticket(self) -> None:
        """Ticket #314, A8: a PR with no `Closes|Refs #n` is not held by a date that cannot be read."""
        project = Project(self, USINE + "- `ticket-pr-cap-since` : `tomorrow`\n")
        self.assertIsNone(project.create(pr_body("No ticket."), self.merged()))

    def test_a_pr_with_no_readable_creation_date_cannot_be_counted(self) -> None:
        """Ticket #314, A8: a missing `createdAt`, or one that is no timestamp, fails closed like a gh error."""
        project = Project(self, USINE + SINCE)
        for stamp in (None, "", "yesterday", "23-11-2026", "2026-13-45T10:00:00Z"):
            with self.subTest(stamp=stamp):
                refused = project.create(pr_body("Closes #5"), self.merged("2026-11-23T10:00:00Z", stamp))
                self.assertIn("cannot be counted", refused or "")

    def test_the_day_is_the_utc_day_of_the_timestamp(self) -> None:
        """Ticket #314, A8: gh gives UTC (`Z`); a numeric offset is brought back to UTC before the day is read."""
        project = Project(self, USINE + SINCE)
        before = self.merged("2026-11-23T01:00:00+02:00", "2026-11-22T23:59:59+00:00", "2026-11-22T10:00:00.123Z")
        self.assertIsNone(project.create(pr_body("Closes #5"), before))
        after = self.merged("2026-11-22T23:30:00-02:00", "2026-11-23T00:00:00+00:00", "2026-11-23T00:00:00.500Z")
        self.assertIn("#5 already has 3 PRs", project.create(pr_body("Closes #5"), after) or "")

    def test_a_reservation_still_counts_when_the_search_lags(self) -> None:
        """Ticket #314, A8: a PR the hook let through today is created today, so it counts at once."""
        project = Project(self, USINE + SINCE, memory=True)
        old = self.merged("2026-11-01T10:00:00Z", "2026-11-02T10:00:00Z")
        recent = self.merged("2026-11-23T10:00:00Z", "2026-11-24T10:00:00Z")
        self.assertIsNone(project.create(pr_body("Refs #5", "Third part."), recent))
        self.assertIn("#5 already has 3 PRs", project.create(pr_body("Refs #5", "Fourth part."), recent) or "")
        other = Project(self, USINE + SINCE, memory=True)
        self.assertIsNone(other.create(pr_body("Refs #5", "Third."), old))
        self.assertIn("#5 already has 1 PRs", other.create(pr_body("Refs #5", "Fourth."), old) or "")


EXEMPT = "- `ticket-pr-cap-exempt` : `chore(factory)`\n"


class ExemptKey(unittest.TestCase):
    """Part 3, A1: `ticket-pr-cap-exempt` takes a PR out of the count by the prefix `type(scope):` of its title."""

    def listed(self, *entries: tuple[str, str], ticket: int = 5) -> FakeGh:
        """gh lists one PR per `(state, title)`, each citing `ticket`."""
        return FakeGh(
            [(state, pr_body(f"Refs #{ticket}")) for state, _ in entries], titles=[title for _, title in entries]
        )

    def test_a_listed_pr_leaves_the_count_open_or_merged(self) -> None:
        """Ticket #314 part 3, A1: two `chore(factory)` PRs, one open and one merged, do not fill a cap of 3."""
        project = Project(self, USINE + EXEMPT)
        gh = self.listed(
            ("OPEN", "chore(factory): pin forge--v1.21.0"),
            ("MERGED", "chore(factory): count from 2026-11-24"),
            ("MERGED", "feat(j2): screens"),
            ("MERGED", "feat(j2): more screens"),
        )
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))
        full = self.listed(
            ("MERGED", "feat(a): one"), ("OPEN", "feat(b): two"), ("OPEN", "chore(factory): pin"), ("MERGED", "fix(c): three")
        )
        self.assertIn("#5 already has 3 PRs", project.create(pr_body("Closes #5"), full) or "")

    def test_the_title_is_read_in_the_one_listing(self) -> None:
        """Ticket #314 part 3, A1: `title` is a field of the `gh pr list --json` call the guard already makes, no other call."""
        project = Project(self, USINE + EXEMPT)
        gh = self.listed(("MERGED", "chore(factory): pin"))
        project.create(pr_body("Closes #5"), gh)
        listing = gh.asked("pr", "list")
        self.assertEqual(len(listing), 1)
        self.assertIn("title", listing[0][listing[0].index("--json") + 1].split(","))
        self.assertEqual(gh.asked("pr", "view"), [])

    def test_without_the_key_every_pr_counts_whatever_its_title(self) -> None:
        """Ticket #314 part 3, A1: no key `ticket-pr-cap-exempt`, no default: three `chore(factory)` PRs fill the cap."""
        project = Project(self, USINE)
        gh = self.listed(*[("MERGED", "chore(factory): pin")] * 3)
        self.assertIn("#5 already has 3 PRs", project.create(pr_body("Closes #5"), gh) or "")

    def test_the_match_is_the_exact_prefix_type_scope_colon(self) -> None:
        """Ticket #314 part 3, A1: another scope, no scope, no colon, another case or a leading space still count."""
        project = Project(self, USINE + EXEMPT)
        for title in (
            "chore(factory-x): a",
            "chore(factor): a",
            "chore: a",
            "chore(factory) a",
            "Chore(factory): a",
            "feat(factory): a",
            " chore(factory): a",
            "fix: chore(factory): a",
            "",
        ):
            with self.subTest(title=title):
                gh = self.listed(*[("MERGED", title)] * 3)
                self.assertIn("#5 already has 3 PRs", project.create(pr_body("Closes #5"), gh) or "")
        for title in ("chore(factory): a", "chore(factory):a", "chore(factory):"):
            with self.subTest(title=title):
                gh = self.listed(*[("MERGED", title)] * 3)
                self.assertIsNone(project.create(pr_body("Closes #5"), gh))

    def test_each_line_of_the_key_is_one_exempt_prefix(self) -> None:
        """Ticket #314 part 3, A1: `chore(pin)` and `chore(release)` on two lines each exempt their own PRs, and no other."""
        project = Project(self, USINE + "- `ticket-pr-cap-exempt` : `chore(pin)`\n- `ticket-pr-cap-exempt` : `chore(release)`\n")
        gh = self.listed(
            ("MERGED", "chore(pin): forge--v1.22.0"),
            ("MERGED", "chore(release): forge 1.22.0, a thing"),
            ("MERGED", "chore(factory): not listed"),
            ("MERGED", "chore(pin): again"),
        )
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))
        three = self.listed(*[("MERGED", "chore(factory): x")] * 3)
        self.assertIn("#5 already has 3 PRs", project.create(pr_body("Closes #5"), three) or "")

    def test_a_listed_pr_is_left_out_whatever_its_date(self) -> None:
        """Ticket #314 part 3, A1: the exemption and the day `ticket-pr-cap-since` filter the same count, one after the other."""
        project = Project(self, USINE + SINCE + EXEMPT)
        gh = self.listed(
            ("MERGED", "chore(factory): pin"),
            ("MERGED", "chore(factory): date"),
            ("MERGED", "feat(a): one"),
        )
        gh.created = ["2026-11-24T10:00:00Z", "2026-11-22T10:00:00Z", "2026-11-24T11:00:00Z"]
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))

    def test_a_listed_pr_does_not_start_a_ticket(self) -> None:
        """Ticket #314 part 3, A1: a `chore(factory)` PR from before the day does not make the ticket a started one."""
        project = Project(self, USINE + SINCE + EXEMPT)
        gh = self.listed(("MERGED", "chore(factory): pin"), ("MERGED", "feat(a): one"), ("MERGED", "feat(b): two"))
        gh.created = ["2026-11-20T10:00:00Z", "2026-11-24T10:00:00Z", "2026-11-24T11:00:00Z"]
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))

    def test_a_value_that_is_no_type_scope_refuses_a_pr_that_cites_a_ticket(self) -> None:
        """Ticket #314 part 3, A1: fails closed: `chore`, `chore(factory):`, an empty value or one with a space names the key."""
        for value in ("`chore`", "`chore(factory):`", "``", "`chore (factory)`", "`(factory)`", "`chore()`"):
            with self.subTest(value=value):
                project = Project(self, USINE + f"- `ticket-pr-cap-exempt` : {value}\n")
                refused = project.create(pr_body("Closes #5"), self.listed(("MERGED", "chore(factory): a"))) or ""
                self.assertIn("`ticket-pr-cap-exempt`", refused)

    def test_a_malformed_key_holds_back_nothing_that_cites_no_ticket(self) -> None:
        """Ticket #314 part 3, A1: a PR with no `Closes|Refs #n` is not held by an exempt key that cannot be read."""
        project = Project(self, USINE + "- `ticket-pr-cap-exempt` : `chore`\n")
        self.assertIsNone(project.create(pr_body("No ticket."), self.listed()))

    def test_a_pr_with_no_readable_title_cannot_be_counted_once_the_key_is_declared(self) -> None:
        """Ticket #314 part 3, A1: a listed PR without a `title` text fails closed like a gh error; no key, no title is read."""
        keyed = Project(self, USINE + EXEMPT)
        gh = FakeGh([("MERGED", pr_body("Refs #5"))])
        self.assertIn("cannot be counted", keyed.create(pr_body("Closes #5"), gh) or "")
        bare = Project(self, USINE)
        self.assertIsNone(bare.create(pr_body("Closes #5"), FakeGh([("MERGED", pr_body("Refs #5"))])))

    def test_the_key_alone_without_the_cap_reads_nothing(self) -> None:
        """Ticket #314 part 3, A1: `ticket-pr-cap` absent, the step is sans objet: no gh call, whatever the exempt key."""
        project = Project(self, "# Usine\n" + EXEMPT)
        gh = self.listed(("MERGED", "chore(factory): pin"))
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))
        self.assertEqual(gh.calls, [])


class ExemptKeyDeclared(unittest.TestCase):
    """Part 3, A1 and A3: the key is protected and the template documents it."""

    def test_the_key_is_protected_like_the_cap(self) -> None:
        """Ticket #314 part 3, A1: `ticket-pr-cap-exempt` is read in `usine-gardes.md`, wherever `ticket-pr-cap` is."""
        self.assertIn("ticket-pr-cap-exempt", SENSITIVE_KEYS)
        self.assertIn("ticket-pr-cap", SENSITIVE_KEYS)

    def test_the_template_documents_the_key_next_to_the_cap_without_a_default(self) -> None:
        """Ticket #314 part 3, A3: the template line, its form, the exact prefix, `sans objet`, no default, no em dash."""
        raw = (support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8")
        text = " ".join(raw.split())
        self.assertIn("- `ticket-pr-cap-exempt` : `<chore(factory)>`", text)
        self.assertLess(text.index("- `ticket-pr-cap-since` :"), text.index("- `ticket-pr-cap-exempt` :"))
        self.assertLess(text.index("- `ticket-pr-cap-exempt` :"), text.index("- `pr-cap-raiser` :"))
        before = text.split("- `ticket-pr-cap-exempt`")[0][-1800:]
        for phrase in (
            "une ligne par `type(scope)`",
            "type(scope):",
            "ouvertes ou fusionnées",
            "sans objet (clé `ticket-pr-cap-exempt` absente)",
            "aucune valeur par défaut",
            "ne cite aucun ticket",
            "forge:qc-conf",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, before)
        self.assertNotIn("\u2014", raw)

    def test_the_template_lists_the_key_among_the_protected_ones(self) -> None:
        """Ticket #314 part 3, A1: the protected section of the template counts and names the key."""
        text = " ".join((support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8").split())
        section = text.split("## Clés protégées")[1].split(" Les autres clés")[0]
        self.assertIn("`ticket-pr-cap-exempt`", section)
        self.assertIn("Vingt-cinq clés", section)
        self.assertEqual(len(SENSITIVE_KEYS), 25)


class ExemptCreation(unittest.TestCase):
    """Part 3, A2 and A5: a PR being created is exempt only through its `--title` / `-t` argument."""

    TITLE = "chore(factory): pin forge--v1.22.0"

    def create(self, project: Project, tool: str, command: str, gh: Runner) -> str | None:
        """`command` run by the tool `tool` (`Bash` or `PowerShell`), `{body}` the body file."""
        body = project.body_file(pr_body("Closes #5"))
        return project.tool(tool, {"command": command.format(body=body)}, gh)

    def full(self) -> FakeGh:
        """A ticket that holds its three PRs, none of them listed."""
        return FakeGh([("MERGED", pr_body("Closes #5"))] * 3, titles=["feat(a): x", "feat(b): y", "fix(c): z"])

    def test_a_listed_title_is_exempt_under_bash_and_powershell(self) -> None:
        """Ticket #314 part 3, A2 and A5: a quoted title with parentheses, as typed under each shell, passes a full ticket."""
        project = Project(self, USINE + EXEMPT)
        typed = (
            'gh pr create --title "chore(factory): pin forge--v1.22.0" --body-file {body}',
            "gh pr create --title 'chore(factory): pin forge--v1.22.0' --body-file {body}",
            'gh pr create -t "chore(factory): pin forge--v1.22.0" --body-file {body}',
            'gh pr create -t"chore(factory): pin" --body-file {body}',
            'gh pr create --title="chore(factory): pin" --body-file {body}',
            "gh pr create --body-file {body} --title 'chore(factory): pin' --draft",
            'gh.exe pr create --title "chore(factory): pin forge--v1.22.0" --body-file {body}',
            'gh pr create --title "chore(factory): pin" --body "Closes #5"',
        )
        for tool in ("Bash", "PowerShell"):
            for command in typed:
                with self.subTest(tool=tool, command=command):
                    self.assertIsNone(self.create(project, tool, command, self.full()))

    def test_a_listed_title_reserves_no_place(self) -> None:
        """Ticket #314 part 3, A2: the exempt PR counts for no one, not even in the reservations of the next PR."""
        project = Project(self, USINE + EXEMPT, memory=True)
        gh = FakeGh([("MERGED", pr_body("Closes #5"))], titles=["feat(a): x"])

        def open_pr(title: str, part: str) -> str | None:
            """`gh pr create` of its own body (the same body twice is one PR for the guard)."""
            body = project.body_file(pr_body("Closes #5", part), name=f"{part}.md")
            return project.bash(f'gh pr create --title "{title}" --body-file {body}', gh)

        for part in ("one", "two", "three"):
            self.assertIsNone(open_pr(self.TITLE, part))
        self.assertIsNone(open_pr("feat(b): next", "four"))
        self.assertIsNone(open_pr("feat(c): next", "five"))
        self.assertIn("#5 already has 3 PRs", open_pr("feat(d): next", "six") or "")

    def test_no_title_argument_counts(self) -> None:
        """Ticket #314 part 3, A2: no `--title` or `-t`, the PR counts and a full ticket refuses it, whatever the shell."""
        project = Project(self, USINE + EXEMPT)
        for tool in ("Bash", "PowerShell"):
            for command in (
                "gh pr create --body-file {body}",
                "gh pr create --body-file {body} --fill",
                'gh pr create --body-file {body} --head "chore(factory): x"',
                'gh pr create --body-file {body} --body "Closes #5 chore(factory): x"',
                "gh pr create --body-file {body} --label -t 'chore(factory): x'",
                "gh pr create --body-file {body} --title",
            ):
                with self.subTest(tool=tool, command=command):
                    self.assertIn("#5 already has 3 PRs", self.create(project, tool, command, self.full()) or "")

    def test_another_title_counts(self) -> None:
        """Ticket #314 part 3, A2: a title outside the key, near it or empty, counts under both shells."""
        project = Project(self, USINE + EXEMPT)
        for tool in ("Bash", "PowerShell"):
            for title in ("feat(factory): x", "chore(factory-x): x", "chore: x", "chore(factory) x", "fix: chore(factory): x", ""):
                with self.subTest(tool=tool, title=title):
                    command = f"gh pr create --title '{title}' --body-file {{body}}"
                    self.assertIn("#5 already has 3 PRs", self.create(project, tool, command, self.full()) or "")

    def test_the_last_title_is_the_one_gh_uses(self) -> None:
        """Ticket #314 part 3, A2: gh keeps the last `--title`; a listed one before an ordinary one does not exempt."""
        project = Project(self, USINE + EXEMPT)
        first = "gh pr create --title 'chore(factory): a' -t 'feat: b' --body-file {body}"
        self.assertIn("#5 already has 3 PRs", self.create(project, "Bash", first, self.full()) or "")
        last = "gh pr create --title 'feat: b' -t 'chore(factory): a' --body-file {body}"
        self.assertIsNone(self.create(project, "Bash", last, self.full()))

    def test_a_title_the_shell_fills_in_cannot_be_read_and_counts(self) -> None:
        """Ticket #314 part 3, A2: a variable, a substitution or a PowerShell escape is no readable title: the PR counts."""
        project = Project(self, USINE + EXEMPT)
        for tool, title in (
            ("Bash", '"$TITLE"'),
            ("Bash", '"chore(factory): $(date)"'),
            ("Bash", '"chore(factory): $5"'),
            ("PowerShell", '"chore(factory): $title"'),
            ("PowerShell", '"chore(factory): $($x)"'),
            ("PowerShell", '"chore`(factory): x"'),
        ):
            with self.subTest(tool=tool, title=title):
                command = f"gh pr create --title {title} --body-file {{body}}"
                self.assertIn("#5 already has 3 PRs", self.create(project, tool, command, self.full()) or "")

    def test_without_the_key_a_title_exempts_nothing(self) -> None:
        """Ticket #314 part 3, A2: the key absent, a `chore(factory)` title is a title like another: the PR counts."""
        project = Project(self, USINE)
        command = f'gh pr create --title "{self.TITLE}" --body-file {{body}}'
        self.assertIn("#5 already has 3 PRs", self.create(project, "Bash", command, self.full()) or "")

    def test_the_other_doors_do_not_read_a_title(self) -> None:
        """Ticket #314 part 3, A2: only `gh pr create` is exempted by a title: `gh api` and the MCP tool create count."""
        project = Project(self, USINE + EXEMPT)
        body = pr_body("Closes #5")
        api = f"gh api repos/o/r/pulls -f title='{self.TITLE}' -f head=h -f base=main -F body=@{project.body_file(body)}"
        self.assertIn("#5 already has 3 PRs", project.bash(api, self.full()) or "")
        mcp = {"owner": "o", "repo": "r", "title": self.TITLE, "head": "h", "base": "main", "body": body}
        self.assertIn("#5 already has 3 PRs", project.tool("mcp__github__create_pull_request", mcp, self.full()) or "")

    def test_an_edit_is_not_exempted_by_a_title(self) -> None:
        """Ticket #314 part 3, A2: `gh pr edit --title` does not exempt the tickets an edit adds to a PR."""
        project = Project(self, USINE + EXEMPT)
        gh = self.full()
        gh.viewed = (7, pr_body("No ticket."))
        edit = f"gh pr edit 7 --title '{self.TITLE}' --body-file {project.body_file(pr_body('Closes #5'))}"
        self.assertIn("#5 already has 3 PRs", project.bash(edit, gh) or "")


class LastPr(unittest.TestCase):
    """A9: a ticket started before `ticket-pr-cap-since` finishes its PR in flight, then admits one last PR."""

    OLD = "2026-11-20T10:00:00Z"
    NEW = "2026-11-24T10:00:00Z"

    def listed(self, *created: str, state: str = "MERGED", ticket: int = 5, verb: str = "Closes") -> FakeGh:
        return FakeGh([(state, pr_body(f"{verb} #{ticket}")) for _ in created], created=list(created))

    def test_a_ticket_started_before_the_day_admits_a_first_new_pr(self) -> None:
        """Ticket #314, A9: the PR in flight, created before the day, is not counted: one new PR goes through."""
        project = Project(self, USINE + SINCE)
        gh = self.listed(self.OLD, "2026-11-01T08:00:00Z", state="OPEN")
        self.assertIsNone(project.create(pr_body("Refs #5", "Last part."), gh))

    def test_a_ticket_started_before_the_day_admits_no_second_new_pr(self) -> None:
        """Ticket #314, A9: a PR from before the day and one new PR: the ticket takes no other, the cap is 1 new."""
        project = Project(self, USINE + SINCE)
        reason = project.create(pr_body("Closes #5"), self.listed(self.OLD, self.NEW)) or ""
        self.assertIn("#5 already has 1 PRs for a cap of 1", reason)
        self.assertIn("2026-11-23", reason)
        self.assertIn("started before", reason)
        self.assertIn("BLOCKED", reason)

    def test_a_ticket_with_only_new_prs_keeps_the_cap(self) -> None:
        """Ticket #314, A9: no PR from before the day, so the cap of the key holds: two new PRs, a third goes through."""
        project = Project(self, USINE + SINCE)
        self.assertIsNone(project.create(pr_body("Closes #5"), self.listed(self.NEW, "2026-12-01T10:00:00Z")))
        reason = project.create(pr_body("Closes #5"), self.listed(self.NEW, self.NEW, self.NEW)) or ""
        self.assertIn("#5 already has 3 PRs for a cap of 3", reason)
        self.assertNotIn("started before", reason)

    def test_a_pr_from_before_the_day_of_another_ticket_changes_nothing(self) -> None:
        """Ticket #314, A9: only a PR that cites the ticket makes it a started one: #5 keeps its cap of 3."""
        project = Project(self, USINE + SINCE)
        gh = FakeGh(
            [("MERGED", pr_body("Closes #8")), ("MERGED", pr_body("Closes #5")), ("MERGED", pr_body("Closes #5"))],
            created=[self.OLD, self.NEW, self.NEW],
        )
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))

    def test_a_pr_closed_without_a_merge_does_not_start_the_ticket(self) -> None:
        """Ticket #314, A9: a closed PR leaves its place in the count, and does not make the ticket a started one."""
        project = Project(self, USINE + SINCE)
        gh = FakeGh(
            [("CLOSED", pr_body("Closes #5")), ("MERGED", pr_body("Closes #5")), ("MERGED", pr_body("Closes #5"))],
            created=[self.OLD, self.NEW, self.NEW],
        )
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))

    def test_without_the_key_a_pr_from_before_counts_and_the_cap_holds(self) -> None:
        """Ticket #314, A9: no key `ticket-pr-cap-since`, no date step: the old PR counts as any other, cap 3."""
        project = Project(self, USINE)
        gh = self.listed(self.OLD, self.NEW)
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))
        reason = project.create(pr_body("Closes #5"), self.listed(self.OLD, self.NEW, self.NEW)) or ""
        self.assertIn("#5 already has 3 PRs for a cap of 3", reason)
        self.assertNotIn("started before", reason)

    def test_the_last_pr_of_a_started_ticket_is_reserved_when_the_search_lags(self) -> None:
        """Ticket #314, A9: the last PR the hook let through counts at once: a second one is refused."""
        project = Project(self, USINE + SINCE, memory=True)
        gh = self.listed(self.OLD, state="OPEN")
        self.assertIsNone(project.create(pr_body("Refs #5", "Last."), gh))
        self.assertIn("#5 already has 1 PRs for a cap of 1", project.create(pr_body("Refs #5", "After last."), gh) or "")

    def test_the_label_raises_the_limit_of_a_started_ticket_to_six(self) -> None:
        """Ticket #314, A9: `pr-cap-raised` set by a raiser lifts the limit of 1 to 6, as it lifts the cap."""
        project = Project(self, USINE + SINCE)
        gh = self.listed(self.OLD, self.NEW)
        gh.events = [raised()]
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))
        full = self.listed(self.OLD, *[self.NEW] * 6)
        full.events = [raised()]
        self.assertIn("#5 already has 6 PRs for a cap of 6", project.create(pr_body("Closes #5"), full) or "")

    def test_a_label_set_by_a_stranger_raises_nothing_for_a_started_ticket(self) -> None:
        """Ticket #314, A9: the author of the label is checked here as for the cap."""
        project = Project(self, USINE + SINCE)
        gh = self.listed(self.OLD, self.NEW)
        gh.events = [raised("the-agent")]
        self.assertIn("for a cap of 1", project.create(pr_body("Closes #5"), gh) or "")

    def test_the_pr_in_flight_is_edited_without_being_refused(self) -> None:
        """Ticket #314, A9: the report written into the PR from before the day (an edit) is never a new PR."""
        project = Project(self, USINE + SINCE)
        gh = self.listed(self.OLD, self.NEW)
        gh.viewed = (100, pr_body("Closes #5"))
        self.assertIsNone(project.edit(pr_body("Closes #5", "Report."), gh, selector="100"))

    def test_a_new_ticket_added_by_an_edit_is_held_by_its_own_history(self) -> None:
        """Ticket #314, A9: an edit that adds #5 to a PR is a new PR for #5, with the limit of #5's history."""
        project = Project(self, USINE + SINCE)
        gh = self.listed(self.OLD, self.NEW)
        gh.viewed = (150, pr_body("No ticket."))
        reason = project.edit(pr_body("Closes #5"), gh, selector="150") or ""
        self.assertIn("#5 already has 1 PRs for a cap of 1", reason)

    def test_the_cap_is_a_cap_of_one_whatever_the_key_says(self) -> None:
        """Ticket #314, A9: the limit for a started ticket is a constant, not a key: a cap of 5 gives 1 as well."""
        project = Project(self, "- `ticket-pr-cap` : `5`\n" + SINCE)
        reason = project.create(pr_body("Closes #5"), self.listed(self.OLD, self.NEW)) or ""
        self.assertIn("for a cap of 1", reason)
        self.assertIsNone(project.create(pr_body("Closes #5"), self.listed(self.OLD)))

    def test_the_plugin_adds_no_key_for_the_last_pr(self) -> None:
        """Ticket #314, A9: the last PR has no key of its own; part 3 adds `ticket-pr-cap-exempt`, a key of the count."""
        text = (support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8")
        keys = {line.split("`")[1] for line in text.splitlines() if line.startswith("- `ticket-pr-cap")}
        self.assertEqual(keys, {"ticket-pr-cap", "ticket-pr-cap-since", "ticket-pr-cap-exempt", "ticket-pr-cap-small"})


class FourthPr(unittest.TestCase):
    """A3: the refusal is the BLOCKED of the fourth PR."""

    def test_the_refusal_says_blocked_comment_attention_and_no_new_ticket(self) -> None:
        """Ticket #314, A3: no PR, the ticket commented, `needs-your-attention`, no ticket born of the cap."""
        project = Project(self)
        reason = project.create(pr_body("Closes #5"), cited(3)) or ""
        for phrase in ("BLOCKED", "no new ticket", "commented", "needs-your-attention", "pr-cap-raised"):
            self.assertIn(phrase, reason)

    def test_the_guard_never_opens_a_ticket_nor_comments(self) -> None:
        """Ticket #314, A3: the hook only reads (`pr list`, `pr view`, `api` GET): it writes nothing to GitHub."""
        project = Project(self)
        gh = cited(3)
        project.create(pr_body("Closes #5"), gh)
        reads = (["pr", "list"], ["pr", "view"])
        self.assertTrue(all(call[:2] in reads or call[0] == "api" for call in gh.calls), gh.calls)
        self.assertEqual([call for call in gh.calls if call[:2] in (["issue", "create"], ["issue", "comment"])], [])


def raised(login: str = "the-human", name: str = "pr-cap-raised", event: str = "labeled") -> dict:
    return {"event": event, "label": {"name": name}, "actor": {"login": login}}


class RaisedCap(unittest.TestCase):
    """A4: only the label `pr-cap-raised`, set by a login of the key `pr-cap-raiser`, raises the cap to 6."""

    def full(self, count: int, events: list[dict] | None) -> FakeGh:
        gh = cited(count)
        gh.events = events
        return gh

    def test_the_label_set_by_the_human_lets_the_fourth_pr_through_up_to_six(self) -> None:
        """Ticket #314, A4: three PRs and the label by the login of `pr-cap-raiser`: a fourth, a fifth, a sixth."""
        project = Project(self)
        for count in (3, 4, 5):
            with self.subTest(count=count):
                self.assertIsNone(project.create(pr_body("Closes #5"), self.full(count, [raised()])))
        self.assertIn("cap of 6", project.create(pr_body("Closes #5"), self.full(6, [raised()])) or "")

    def test_the_label_set_by_another_login_does_not_raise_the_cap(self) -> None:
        """Ticket #314, A4: the author of the label is checked: an agent's own label counts for nothing."""
        project = Project(self)
        reason = project.create(pr_body("Closes #5"), self.full(3, [raised("some-agent")])) or ""
        self.assertIn("#5 already has 3 PRs for a cap of 3", reason)

    def test_the_human_is_the_short_identifier_of_the_line_or_its_whole_value(self) -> None:
        """Ticket #314, A4: `<name> | <id>` names the id; a line without ` | ` names itself; the case is free."""
        named = Project(self)
        self.assertIsNotNone(named.create(pr_body("Closes #5"), self.full(3, [raised("Kevin Humain")])))
        self.assertIsNone(named.create(pr_body("Closes #5"), self.full(3, [raised("The-Human")])))
        alone = Project(self, "- `ticket-pr-cap` : `3`\n- `pr-cap-raiser` : `solo`\n")
        self.assertIsNone(alone.create(pr_body("Closes #5"), self.full(3, [raised("solo")])))

    def test_the_last_event_on_the_label_decides(self) -> None:
        """Ticket #314, A4: the human removed it, or someone else put it back after: not raised."""
        project = Project(self)
        removed = [raised(), raised(event="unlabeled")]
        self.assertIn("cap of 3", project.create(pr_body("Closes #5"), self.full(3, removed)) or "")
        taken_over = [raised("the-human"), raised("some-agent", event="unlabeled"), raised("some-agent")]
        self.assertIn("cap of 3", project.create(pr_body("Closes #5"), self.full(3, taken_over)) or "")
        restored = [raised(), raised(event="unlabeled"), raised()]
        self.assertIsNone(project.create(pr_body("Closes #5"), self.full(3, restored)))

    def test_another_label_and_other_events_do_not_raise_it(self) -> None:
        """Ticket #314, A4: only the label `pr-cap-raised` counts, only `labeled` events set it."""
        project = Project(self)
        events = [raised(name="needs-your-attention"), {"event": "assigned", "actor": {"login": "the-human"}}]
        self.assertIn("cap of 3", project.create(pr_body("Closes #5"), self.full(3, events)) or "")

    def test_events_gh_cannot_give_leave_the_cap_where_it_is(self) -> None:
        """Ticket #314, A4: a gh error on the events never raises the cap (and is not a crash)."""
        project = Project(self)
        self.assertIn("cap of 3", project.create(pr_body("Closes #5"), self.full(3, None)) or "")

    def test_without_the_key_pr_cap_raiser_nobody_can_raise_the_cap(self) -> None:
        """Ticket #314, A4: no `pr-cap-raiser`, no default: the label raises nothing, and the refusal says so."""
        project = Project(self, "- `ticket-pr-cap` : `3`\n- `accepting-human` : `Kevin | the-human`\n")
        reason = project.create(pr_body("Closes #5"), self.full(3, [raised()])) or ""
        self.assertIn("cap of 3", reason)
        self.assertIn("pr-cap-raiser", reason)

    def test_a_login_of_accepting_human_that_is_not_a_raiser_does_not_raise_the_cap(self) -> None:
        """Ticket #314, A4: the agent's account may sit in `accepting-human`; only `pr-cap-raiser` counts."""
        project = Project(
            self,
            "- `ticket-pr-cap` : `3`\n- `accepting-human` : `Kevin | kevin`\n"
            "- `accepting-human` : `Agent | agent`\n- `pr-cap-raiser` : `Kevin | kevin`\n",
        )
        self.assertIn("cap of 3", project.create(pr_body("Closes #5"), self.full(3, [raised("agent")])) or "")
        self.assertIsNone(project.create(pr_body("Closes #5"), self.full(3, [raised("kevin")])))

    def test_in_this_repository_no_account_raises_the_cap(self) -> None:
        """Ticket #314, A4: with the real configuration of this repository, the key is absent: neither account of the agent raises the cap."""
        text = support.repo_usine_text()
        self.assertNotRegex(text, r"(?m)^- `pr-cap-raiser` : `")
        guard = (support.REPO_ROOT / "docs" / "agents" / "usine-gardes.md").read_text(encoding="utf-8")
        self.assertIn("`pr-cap-raiser`", guard.split("## Clés absentes", 1)[1])
        project = Project(self, text)
        for login in ("ikoro-labs", "sunderland-labs"):
            with self.subTest(login=login):
                gh = self.full(6, [raised(login)])  # the cap of this repository (#381)
                gh.created = ["2026-11-23T10:00:00Z"] * 6  # this repository counts from a day: its PRs carry one
                gh.titles = ["feat(x): one", "feat(y): two", "fix(z): three", "docs(w): four", "fix(v): five", "feat(u): six"]
                gh.sizes = [(300, 20)] * 6  # and leaves out the small PRs (#381): gh gives their sizes
                reason = project.create(pr_body("Closes #5"), gh) or ""
                self.assertIn("#5 already has 6 PRs for a cap of 6", reason)
                self.assertIn("clé `pr-cap-raiser` absente", reason)

    def test_the_events_are_read_only_when_the_count_reaches_the_cap(self) -> None:
        """Ticket #314, A4: below the cap no label is looked up."""
        project = Project(self)
        gh = self.full(2, [raised()])
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))
        self.assertEqual(gh.asked("api"), [])

    def test_the_events_of_the_ticket_are_read_in_the_repository_named(self) -> None:
        """Ticket #314, A4: `gh api repos/<o>/<r>/issues/<n>/events`, all the pages."""
        project = Project(self)
        gh = self.full(3, [raised()])
        command = f"gh pr create --repo o/r --title T --body-file {project.body_file(pr_body('Closes #5'))}"
        self.assertIsNone(project.bash(command, gh))
        asked = gh.asked("api")[0]
        self.assertEqual(asked[1], "repos/o/r/issues/5/events?per_page=100")
        self.assertIn("--paginate", asked)

    def test_paginated_events_arrive_as_several_arrays(self) -> None:
        """Ticket #314, A4: `gh api --paginate` prints one JSON array per page; the guard reads them all."""
        project = Project(self)
        gh = self.full(3, [])
        pages = json.dumps([raised("the-human")]) + json.dumps([{"event": "closed", "actor": {"login": "x"}}])
        gh.events = None
        original = gh.__call__

        def run(argv: list[str], cwd: str | None) -> str | None:
            return pages if argv[:1] == ["api"] else original(argv, cwd)

        self.assertIsNone(project.create(pr_body("Closes #5"), run))


def prose(path: Path) -> str:
    """The file on one line, so a sentence wrapped by the editor still matches."""
    return " ".join(path.read_text(encoding="utf-8").split())


class Briefs(unittest.TestCase):
    """A5: the briefs of `forge:coder` and `forge:feature-build` state the cap."""

    def test_the_coder_plans_at_most_the_cap_from_its_first_reading(self) -> None:
        """Ticket #314, A5: the coder plans the PRs of its ticket within the key's cap before it codes."""
        text = prose(support.PLUGIN / "agents" / "coder.md")
        reading = text.split("## 1. Lire, avant la première ligne", 1)[1].split("## 2.", 1)[0]
        self.assertIn("`ticket-pr-cap`", reading)
        counting = reading.split("Compte aussi", 1)[1].split("Si, après cette lecture", 1)[0]
        self.assertIn("la valeur de la clé `ticket-pr-cap`", counting)
        self.assertNotRegex(counting, r"\b3\b|(?i:trois)")
        self.assertIn("sans objet (clé `ticket-pr-cap` absente)", text)

    def test_the_coder_returns_blocked_at_the_fourth_pr_and_opens_no_ticket(self) -> None:
        """Ticket #314, A3: `BLOCKED`, the guard names the cap, `pr-cap-raised` is the human's only way out."""
        text = prose(support.PLUGIN / "agents" / "coder.md")
        cap = text.split("**Trois PR au plus par ticket.**", 1)[1].split("## 5. Livrer", 1)[0]
        self.assertIn("`guard_pr_cap`", cap)
        self.assertIn("`RESULT: BLOCKED`", cap)
        self.assertIn("`pr-cap-raised`", cap)
        self.assertRegex(cap, r"(?i)aucun ticket")

    def test_feature_build_tells_the_cap_in_the_brief_of_each_coder(self) -> None:
        """Ticket #314, A5: the launch of a coder carries the cap, as the value of the key and no figure."""
        text = prose(support.PLUGIN / "skills" / "feature-build" / "SKILL.md")
        launch = text.split("3. Lance l'agent `forge:coder`", 1)[1].split("Puis passe à l'étape 3", 1)[0]
        self.assertIn("`ticket-pr-cap`", launch)
        telling = launch.split("Écris aussi le plafond", 1)[1].split("aucun plafond n'est deviné", 1)[0]
        self.assertIn("la valeur de la clé `ticket-pr-cap`", telling)
        self.assertNotRegex(telling, r"\b3\b|(?i:trois)")

    def test_feature_build_comments_the_ticket_and_flags_it_when_the_cap_blocks(self) -> None:
        """Ticket #314, A3: a cap `BLOCKED` is commented on the ticket with `needs-your-attention`, no ticket born."""
        text = prose(support.PLUGIN / "skills" / "feature-build" / "SKILL.md")
        blocked = text.split("Un `BLOCKED` du plafond de trois PR par ticket", 1)[1].split("Selon le verdict", 1)[0]
        self.assertIn("`needs-your-attention`", blocked)
        self.assertIn("`pr-cap-raised`", blocked)
        self.assertRegex(blocked, r"aucun ticket")

    def test_the_cap_briefs_hold_no_project_name_and_no_em_dash(self) -> None:
        """Ticket #314, A5: the plugin's content stays generic, in plain prose."""
        for path in (
            support.PLUGIN / "agents" / "coder.md",
            support.PLUGIN / "skills" / "feature-build" / "SKILL.md",
            support.PLUGIN / "hooks" / "guard_pr_cap.py",
            support.PLUGIN / "templates" / "usine.md",
        ):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn(chr(0x2014), text)
                self.assertNotIn("ikoro-labs", text.replace("ikoro-labs/forge#", ""))


class Documentation(unittest.TestCase):
    """A6: the `docs/` page, the README row, the CHANGELOG entry."""

    def section(self) -> str:
        text = (support.REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
        return " ".join(text.split("## The PRs of a ticket", 1)[1].split("\n## ", 1)[0].split())

    def test_the_docs_page_describes_the_guard_the_key_and_the_label(self) -> None:
        """Ticket #314, A6: `docs/installation.md` has a section for the cap, its key, its label and its limits."""
        section = self.section()
        for phrase in (
            "`guard_pr_cap`",
            "`ticket-pr-cap`",
            "sans objet (clé `ticket-pr-cap` absente)",
            "`pr-cap-raised`",
            "`pr-cap-raiser`",
            "sans objet (clé `pr-cap-raiser` absente)",
            "`ticket-pr-cap-since`",
            "`createdAt`",
            "sans objet (clé `ticket-pr-cap-since` absente)",
            "BLOCKED",
            "needs-your-attention",
            "gh pr list --state all",
            "fails closed",
            "Limits",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)

    def test_the_budget_section_no_longer_says_the_hook_does_not_enforce_the_pr_cap(self) -> None:
        """Ticket #314, A6: the older page said the cap of three PRs was not enforced by a hook."""
        text = " ".join((support.REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8").split())
        self.assertNotIn("The hook does not enforce it", text)
        self.assertIn("[The PRs of a ticket](#the-prs-of-a-ticket)", text)

    def test_the_readme_lists_the_guard_and_links_the_page(self) -> None:
        """Ticket #314, A6: the README summarises and points to the page."""
        row = next(line for line in (support.REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines() if "`guard_pr_cap`" in line)
        self.assertIn("docs/installation.md#the-prs-of-a-ticket", row)

    def test_the_changelog_opens_an_entry_for_the_guard(self) -> None:
        """Ticket #314, A6: an entry above the last published version, in the zones Hooks, Agents, Skills, Tests."""
        changelog = (support.REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        entry = changelog.split("## [1.20.0]", 1)[1].split("\n## [", 1)[0]
        for phrase in ("- Hooks :", "- Agents :", "- Skills :", "- Tests :", "- Gestes humains :", "- Resté dehors :"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, entry)
        self.assertIn("`guard_pr_cap.py`", entry)
        self.assertIn("`pr-cap-raiser`", entry)
        self.assertIn("ikoro-labs/forge#314", entry)
        self.assertIn("`ticket-pr-cap-since`", entry)
        self.assertLess(changelog.index("## [1.20.0]"), changelog.index("## [1.19.0]"))


class LastPrDocumentation(unittest.TestCase):
    """A9: the page, the template, the README, the coder's brief and the CHANGELOG say the last PR."""

    PHRASES = ("avant cette date", "dernière PR", "dernier recours")

    def flat(self, path: Path) -> str:
        return " ".join(path.read_text(encoding="utf-8").split())

    def test_the_docs_page_describes_the_last_pr_of_a_started_ticket(self) -> None:
        """Ticket #314, A9: the section « From a day » says started ticket, the PR in flight, one last PR, the label."""
        text = self.flat(support.REPO_ROOT / "docs" / "installation.md")
        section = text.split("**From a day.**", 1)[1].split("The guard fails closed", 1)[0]
        for phrase in ("started before", "PR in flight", "one last PR", "last resort", "`pr-cap-raised`", "constant"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)

    def test_the_template_describes_the_last_pr_without_a_new_key(self) -> None:
        """Ticket #314, A9: the template text of `ticket-pr-cap-since` says the started ticket and its last PR."""
        text = self.flat(support.PLUGIN / "templates" / "usine.md")
        block = text.split("- `ticket-pr-cap` : `<3>`", 1)[1].split("- `ticket-pr-cap-since` : `<AAAA-MM-JJ>`", 1)[0]
        for phrase in self.PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, block)

    def test_the_readme_row_says_the_last_pr(self) -> None:
        """Ticket #314, A9: the README row of `guard_pr_cap` says what a started ticket admits."""
        row = next(line for line in (support.REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines() if "`guard_pr_cap`" in line)
        self.assertIn("dernière PR", row)

    def test_the_coder_brief_says_the_last_pr_in_both_places(self) -> None:
        """Ticket #314, A9: the reading step and the cap paragraph of `forge:coder` say the limit of a started ticket."""
        text = self.flat(support.PLUGIN / "agents" / "coder.md")
        reading = text.split("Compte aussi, dès cette lecture", 1)[1].split("Si, après cette lecture", 1)[0]
        paragraph = text.split("**Trois PR au plus par ticket.**", 1)[1].split("## 5. Livrer", 1)[0]
        for where in (reading, paragraph):
            for phrase in ("`ticket-pr-cap-since`", "dernière PR", "dernier recours"):
                with self.subTest(phrase=phrase):
                    self.assertIn(phrase, where)

    def test_the_changelog_has_an_entry_for_the_last_pr(self) -> None:
        """Ticket #314, A9: an entry above 1.20.0 (opened by the release 1.21.0), with its zones and the reason left out."""
        changelog = (support.REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertLess(changelog.index("## [1.21.0]"), changelog.index("## [1.20.0]"))
        entry = changelog.split("## [1.21.0]", 1)[1].split("\n## [", 1)[0]
        for phrase in ("- Hooks :", "- Agents :", "- Tests :", "- Gestes humains :", "- Resté dehors :", "dernière PR"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, entry)
        self.assertIn("ikoro-labs/forge#314", entry)
        self.assertNotIn("`ticket-pr-cap-last`", entry)


class ExemptDocumentation(unittest.TestCase):
    """Part 3, A4: the page, the README row, the coder's brief, the judge's grid and this repository's `usine.md`."""

    def section(self) -> str:
        text = (support.REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
        return " ".join(text.split("## The PRs of a ticket", 1)[1].split("\n## ", 1)[0].split())

    def test_the_page_describes_the_exempt_key(self) -> None:
        """Ticket #314 part 3, A4: the page names the key, the exact prefix, the title door, the judge and the absent key."""
        section = self.section()
        for phrase in (
            "`ticket-pr-cap-exempt`",
            "`type(scope):`",
            "`--title`",
            "cites no ticket",
            "`forge:qc-conf`",
            "sans objet (clé `ticket-pr-cap-exempt` absente)",
            "`gh pr edit`",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)

    def test_the_readme_row_names_the_exempt_key(self) -> None:
        """Ticket #314 part 3, A4: the README summarises the key and keeps the link to the page."""
        row = next(line for line in (support.REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines() if "`guard_pr_cap`" in line)
        self.assertIn("`ticket-pr-cap-exempt`", row)
        self.assertIn("docs/installation.md#the-prs-of-a-ticket", row)

    def test_the_coder_cites_no_ticket_in_a_maintenance_pr(self) -> None:
        """Ticket #314 part 3, A4: the brief says a listed PR is not counted, cites no ticket, and the key's absence."""
        text = " ".join((support.PLUGIN / "agents" / "coder.md").read_text(encoding="utf-8").split())
        for phrase in (
            "`ticket-pr-cap-exempt`",
            "ne cite aucun ticket",
            "sans objet (clé `ticket-pr-cap-exempt` absente)",
            "--json number,state,body,title",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_the_judge_refuses_a_listed_title_on_a_diff_that_is_not_factory_maintenance(self) -> None:
        """Ticket #314 part 3, A4: the grid of `forge:qc-conf` has one line: a listed title on another diff is a `BLOCKER`, `F-25`."""
        text = " ".join((support.PLUGIN / "agents" / "qc-conf.md").read_text(encoding="utf-8").split())
        line = next(part for part in text.split(" - ") if "`ticket-pr-cap-exempt`" in part)
        for phrase in ("`BLOCKER`", "`F-25`", "entretien de l'usine", "ne cite aucun ticket"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, line)

    def test_this_repository_exempts_the_pin_and_the_release(self) -> None:
        """Ticket #314 part 3, A4: `docs/agents/usine-gardes.md` (moved by #345) lists `chore(pin)` and `chore(release)` next to the cap, and only them."""
        text = support.repo_usine_text()
        lines = [line for line in text.splitlines() if line.startswith("- `ticket-pr-cap-exempt`")]
        self.assertEqual(lines, ["- `ticket-pr-cap-exempt` : `chore(pin)`", "- `ticket-pr-cap-exempt` : `chore(release)`"])
        self.assertLess(text.index("- `ticket-pr-cap` :"), text.index("- `ticket-pr-cap-exempt` :"))
        self.assertNotIn(chr(0x2014), text)

    def test_the_git_rules_of_this_repository_say_a_maintenance_pr_cites_no_ticket(self) -> None:
        """Ticket #314 part 3, A4: `.claude/rules/git.md` says what the page says: a listed title, no ticket, not counted."""
        rules = " ".join((support.REPO_ROOT / ".claude" / "rules" / "git.md").read_text(encoding="utf-8").split())
        bullet = next(part for part in rules.split(" - ") if "`ticket-pr-cap-exempt`" in part)
        for phrase in ("PR d'entretien de l'usine", "ne cite aucun ticket", "`type(scope)`", "plafond de PR"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, bullet)


class Binding(unittest.TestCase):
    def test_hooks_json_binds_the_guard_on_every_gh_gesture_and_fails_closed(self) -> None:
        """Ticket #314, A1: Bash, PowerShell and the GitHub MCP tools reach the guard, a failure refuses."""
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        found = [
            (group["matcher"], hook)
            for group in hooks["hooks"]["PreToolUse"]
            for hook in group["hooks"]
            if "/hooks/guard_pr_cap.py" in hook["command"]
        ]
        self.assertEqual(len(found), 1)
        matcher, hook = found[0]
        for tool in ("Bash", "PowerShell"):
            self.assertIn(tool, matcher.split("|"))
        for tool in ("mcp__github__create_pull_request", "mcp__claude_ai_GitHub__pull_request_write"):
            self.assertRegex(tool, f"^(?:{matcher})$")
        self.assertNotRegex("mcp__notion__create_page", f"^(?:{matcher})$")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/", hook["command"])
        self.assertTrue(hook["command"].endswith("|| exit 2"))
        self.assertEqual(hook.get("onFailure"), "block")
        self.assertIn("PRs of a ticket", hooks["description"])

    def test_the_script_refuses_with_exit_2_when_gh_is_absent(self) -> None:
        """Ticket #314, A1: run as the hook runs, with no gh on the PATH, a PR that cites a ticket exits 2."""
        project = Project(self)
        empty = project.dir / "bin"
        empty.mkdir()
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr create --title T --body 'Closes #5'"},
            "cwd": str(project.dir),
        }
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
        env.update(PATH=str(empty), HOME=str(project.dir), USERPROFILE=str(project.dir))
        env["CLAUDE_PROJECT_DIR"] = str(project.dir)
        completed = subprocess.run(  # noqa: S603 - the interpreter running the tests, a fixed script
            [sys.executable, str(support.PLUGIN / "hooks" / "guard_pr_cap.py")],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("Blocked by the forge plugin (guard_pr_cap)", completed.stderr)
        self.assertIn("cannot be counted", completed.stderr)


if __name__ == "__main__":
    unittest.main()
