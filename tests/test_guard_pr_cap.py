"""Ticket #314: a ticket holds at most `ticket-pr-cap` PRs, held by `guard_pr_cap`, gh simulated.

The criteria of the ticket, numbered in the order it lists them:

- A1: a PR citing `Closes|Refs #n` is refused when #n already has the cap's PRs, open or merged
  (gh, regex, reservation), and the guard fails closed;
- A2: the key `ticket-pr-cap`, no default, "sans objet" without it;
- A3: the refusal is the 4th PR's `BLOCKED`: comment on the ticket, `needs-your-attention`, no new ticket;
- A4: only the label `pr-cap-raised`, set by a human (author checked), raises the cap to 6;
- A5: the briefs of `forge:coder` and `forge:feature-build` state the cap;
- A6: the template line, the `docs/` page, the CHANGELOG entry;
- A7: the tests cite the criteria and run on Linux and Windows (HOME and USERPROFILE isolated).
"""

import json
import os
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

USINE = (
    "# Usine\n- `ticket-pr-cap` : `3`\n- `accepting-human` : `Kevin Humain | the-human`\n"
    "- `pr-cap-raiser` : `Kevin Humain | the-human`\n"
)


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
    ) -> None:
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
        done = subprocess.run(
            [sys.executable, str(support.PLUGIN / "hooks" / "guard_pr_cap.py")],
            input="not json",
            capture_output=True,
            text=True,
            timeout=60,
            env={k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")},
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

    def test_this_repository_declares_the_key_at_three(self) -> None:
        """Ticket #314, A2: `docs/agents/usine.md` of this repository holds `ticket-pr-cap : 3`."""
        text = (support.REPO_ROOT / "docs" / "agents" / "usine.md").read_text(encoding="utf-8")
        self.assertIn("- `ticket-pr-cap` : `3`", text)


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
        """Ticket #314, A4: with the real `docs/agents/usine.md`, the key is absent: neither account of the agent raises the cap."""
        text = (support.REPO_ROOT / "docs" / "agents" / "usine.md").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?m)^- `pr-cap-raiser` : `")
        self.assertIn("`pr-cap-raiser`", text.split("## Clés absentes", 1)[1])
        project = Project(self, text)
        for login in ("ikoro-labs", "sunderland-labs"):
            with self.subTest(login=login):
                reason = project.create(pr_body("Closes #5"), self.full(3, [raised(login)])) or ""
                self.assertIn("#5 already has 3 PRs for a cap of 3", reason)
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
        self.assertRegex(reading, r"au plus (?:trois|3) PR")
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
        """Ticket #314, A5: the launch of a coder carries the cap: plan at most three PRs for the ticket."""
        text = prose(support.PLUGIN / "skills" / "feature-build" / "SKILL.md")
        launch = text.split("3. Lance l'agent `forge:coder`", 1)[1].split("Puis passe à l'étape 3", 1)[0]
        self.assertIn("`ticket-pr-cap`", launch)
        self.assertRegex(launch, r"au plus (?:trois|3) PR")

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
        entry = changelog.split("## [Non publié]", 1)[1].split("\n## [", 1)[0]
        for phrase in ("- Hooks :", "- Agents :", "- Skills :", "- Tests :", "- Gestes humains :", "- Resté dehors :"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, entry)
        self.assertIn("`guard_pr_cap.py`", entry)
        self.assertIn("`pr-cap-raiser`", entry)
        self.assertIn("ikoro-labs/forge#314", entry)
        self.assertLess(changelog.index("## [Non publié]"), changelog.index("## [1.19.0]"))


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
