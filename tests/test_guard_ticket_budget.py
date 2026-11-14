"""The ticket budget of a feature: the design's ceiling and the closed budget, gh simulated."""

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
from guard_ticket_budget import CEILING, Runner, counts_for, placement, refusal

DESIGN = "---\nfeature: F-0001\ndocument: design\nstatut: {statut}\n{budget}base: abc1234\n---\n\n# F-0001\n"


def design(statut: str = "en-revue", budget: int | None = None) -> str:
    line = "" if budget is None else f"feature-tickets: {budget}\n"
    return DESIGN.format(statut=statut, budget=line)


def ticket(motif: str, feature: str | None = None) -> str:
    lines = [f"Motif : {motif}", "", "What is missing.", ""]
    if feature is not None:
        lines.append(f"Feature: {feature}")
    return "\n".join(lines) + "\n"


class FakeGh:
    """`gh issue list` answered from a list of bodies; None plays an unreachable gh."""

    def __init__(
        self, bodies: Sequence[str | tuple[str, dict]] | None, viewed: str | tuple[str, dict] | None = None
    ) -> None:
        self.bodies = bodies
        self.viewed = viewed  # the body (and fields) `gh issue view` gives, None plays a gh error
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], cwd: str | None) -> str | None:
        self.calls.append(argv)
        if argv[:2] == ["issue", "view"]:
            if self.viewed is None:
                return None
            body, fields = self.viewed if isinstance(self.viewed, tuple) else (self.viewed, {})
            return json.dumps({"body": body, **fields})
        if self.bodies is None:
            return None
        issues = []
        for n, item in enumerate(self.bodies, start=1):
            body, fields = item if isinstance(item, tuple) else (item, {})
            issues.append({"number": n, "body": body, **fields})
        return json.dumps(issues)


class Project:
    """A project folder with its usine.md and one design, the session's CLAUDE_ variables kept out."""

    def __init__(
        self,
        test: unittest.TestCase,
        design_text: str | None,
        memory: bool = False,
        usine: str = "# Usine\n- `feature-dir` : `docs/features`\n",
    ) -> None:
        self.dir = Path(tempfile.mkdtemp())
        test.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "docs" / "agents").mkdir(parents=True)
        (self.dir / "docs" / "agents" / "usine.md").write_text(usine, encoding="utf-8")
        self.design = self.dir / "docs" / "features" / "0001-runner" / "design.md"
        self.design.parent.mkdir(parents=True)
        if design_text is not None:
            self.design.write_text(design_text, encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
        env.update(HOME=str(self.dir), USERPROFILE=str(self.dir))
        if memory:
            env["CLAUDE_PLUGIN_DATA"] = str(self.dir / "plugin-data")
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        test.addCleanup(patcher.stop)

    def bash(self, command: str, gh: Runner) -> str | None:
        event = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.dir)}
        return refusal(event, gh)

    def create(self, body: str, gh: Runner) -> str | None:
        body_file = self.dir / "body.md"
        body_file.write_text(body, encoding="utf-8")
        return self.bash(f"gh issue create --title T --body-file {body_file}", gh)

    def write(self, content: str, gh: Runner | None = None) -> str | None:
        event = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.design), "content": content},
            "cwd": str(self.dir),
        }
        return refusal(event, gh or FakeGh([]))

    def tool(self, name: str, tool_input: dict, gh: Runner) -> str | None:
        event = {"tool_name": name, "tool_input": tool_input, "cwd": str(self.dir)}
        return refusal(event, gh)


def full(count: int) -> FakeGh:
    return FakeGh([ticket("to-tickets F-0001") for _ in range(count)])


class DesignAcceptance(unittest.TestCase):
    def test_a_design_at_the_ceiling_is_accepted(self) -> None:
        project = Project(self, design())
        self.assertEqual(CEILING, 15)
        self.assertIsNone(project.write(design("accepte", 15)))

    def test_a_design_above_the_ceiling_is_refused(self) -> None:
        project = Project(self, design())
        reason = project.write(design("accepte", 16))
        self.assertIsNotNone(reason)
        self.assertIn(
            "re-split the feature with the product-owner to at most 15 tickets", reason or ""
        )

    def test_a_design_without_a_budget_is_refused(self) -> None:
        project = Project(self, design())
        self.assertIn("feature-tickets", project.write(design("accepte")) or "")

    def test_a_budget_of_zero_is_refused(self) -> None:
        project = Project(self, design())
        self.assertIsNotNone(project.write(design("accepte", 0)))

    def test_a_design_in_review_is_held_to_the_ceiling_too(self) -> None:
        project = Project(self, design())
        self.assertIsNone(project.write(design("en-revue", 12)))
        self.assertIn("outside 1 to 15", project.write(design("en-revue", 40)) or "")

    def test_an_edit_that_accepts_is_checked_on_the_resulting_header(self) -> None:
        project = Project(self, design("en-revue", 16))
        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(project.design),
                "old_string": "statut: en-revue",
                "new_string": "statut: accepte",
            },
            "cwd": str(project.dir),
        }
        self.assertIsNotNone(refusal(event, FakeGh([])))
        project.design.write_text(design("en-revue", 12), encoding="utf-8")
        self.assertIsNone(refusal(event, FakeGh([])))

    def test_a_multiedit_that_accepts_is_checked(self) -> None:
        project = Project(self, design("en-revue"))
        event = {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(project.design),
                "edits": [{"old_string": "statut: en-revue", "new_string": "statut: accepte"}],
            },
            "cwd": str(project.dir),
        }
        self.assertIsNotNone(refusal(event, FakeGh([])))

    def test_an_accepted_design_may_not_raise_its_budget(self) -> None:
        project = Project(self, design("accepte", 10))
        self.assertIn("the budget is closed", project.write(design("accepte", 12)) or "")
        self.assertIsNotNone(project.write(design("accepte")))
        self.assertIsNone(project.write(design("accepte", 8)))

    def test_an_accepted_design_without_a_budget_may_declare_one(self) -> None:
        project = Project(self, design("accepte"))
        self.assertIsNone(project.write(design("accepte", 12)))
        self.assertIn("outside 1 to 15", project.write(design("accepte", 24)) or "")

    def test_another_file_is_not_checked(self) -> None:
        project = Project(self, design())
        event = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(project.dir / "spec.md"), "content": design("accepte")},
        }
        self.assertIsNone(refusal(event, FakeGh([])))

    def test_a_shell_write_of_the_acceptance_is_refused_and_a_read_passes(self) -> None:
        project = Project(self, design())
        path = project.design
        self.assertIn(
            "Edit or Write",
            project.bash(f"sed -i 's/statut: en-revue/statut: accepte/' {path}", FakeGh([])) or "",
        )
        self.assertIsNone(project.bash(f"grep -n 'statut: accepte' {path}", FakeGh([])))


class ClosedBudget(unittest.TestCase):
    def test_a_ticket_that_reaches_the_budget_is_accepted(self) -> None:
        project = Project(self, design("accepte", 3))
        gh = full(2)
        self.assertIsNone(project.create(ticket("to-tickets F-0001"), gh))
        self.assertTrue(all(["--state", "all"] == call[2:4] for call in gh.calls))
        self.assertTrue(all("--search" in call for call in gh.calls))

    def test_a_ticket_beyond_the_budget_is_refused(self) -> None:
        project = Project(self, design("accepte", 3))
        reason = project.create(ticket("to-tickets F-0001"), full(3))
        self.assertIn("add a part to an existing ticket (`Refs #n`)", reason or "")

    def test_the_motif_line_without_spaces_counts_too(self) -> None:
        project = Project(self, design("accepte", 1))
        self.assertIsNotNone(project.create("Motif: to-tickets F-0001\n", full(1)))

    def test_another_features_tickets_do_not_count(self) -> None:
        project = Project(self, design("accepte", 1))
        gh = FakeGh([ticket("to-tickets F-0002"), ticket("main-rouge 12", "F-0001")])
        self.assertIsNone(project.create(ticket("to-tickets F-0001"), gh))

    def test_the_three_out_of_budget_motifs_are_accepted(self) -> None:
        project = Project(self, design("accepte", 1))
        for motif in ("main-rouge 4242", "securite", "demande-kevin"):
            with self.subTest(motif=motif):
                gh = FakeGh(None)
                self.assertIsNone(project.create(ticket(motif, "F-0001"), gh))
                self.assertEqual(gh.calls, [])

    def test_fusion_bloquee_without_a_feature_line_is_refused(self) -> None:
        project = Project(self, design("accepte", 5))
        reason = project.create(ticket("fusion-bloquee #12"), full(0))
        self.assertIn("Feature: F-NNNN", reason or "")

    def test_fusion_bloquee_counts_in_the_budget_of_its_feature(self) -> None:
        project = Project(self, design("accepte", 2))
        gh = FakeGh([ticket("to-tickets F-0001"), ticket("fusion-bloquee #9", "F-0001")])
        self.assertIsNotNone(project.create(ticket("fusion-bloquee #12", "F-0001"), gh))
        self.assertIsNone(project.create(ticket("fusion-bloquee #12", "F-0001"), full(1)))

    def test_a_count_that_cannot_be_made_refuses(self) -> None:
        project = Project(self, design("accepte", 5))
        self.assertIn(
            "cannot be counted", project.create(ticket("to-tickets F-0001"), FakeGh(None)) or ""
        )

    def test_without_gh_the_ticket_is_refused(self) -> None:
        project = Project(self, design("accepte", 5))
        with mock.patch("guard_ticket_budget.shutil.which", return_value=None):
            event = {
                "tool_name": "Bash",
                "tool_input": {"command": "gh issue create -t T -b 'Motif : to-tickets F-0001'"},
                "cwd": str(project.dir),
            }
            self.assertIn("cannot be counted", refusal(event) or "")

    def test_an_answer_gh_cannot_be_read_from_refuses(self) -> None:
        project = Project(self, design("accepte", 5))
        reason = project.create(ticket("to-tickets F-0001"), lambda argv, cwd: "not json")
        self.assertIn("cannot be counted", reason or "")

    def test_an_accepted_design_above_the_ceiling_refuses_every_ticket(self) -> None:
        project = Project(self, design("accepte", 24))
        reason = project.create(ticket("to-tickets F-0001"), full(0))
        self.assertIn(
            "re-split the feature with the product-owner to at most 15 tickets", reason or ""
        )

    def test_a_design_without_a_budget_refuses_the_ticket(self) -> None:
        project = Project(self, design("accepte"))
        reason = project.create(ticket("to-tickets F-0001"), full(0))
        self.assertIn("declare feature-tickets in the design first", reason or "")
        self.assertIn("re-split the feature with the product-owner", reason or "")

    def test_a_missing_or_unaccepted_design_refuses_the_ticket(self) -> None:
        self.assertIn(
            "no design", Project(self, None).create(ticket("to-tickets F-0001"), full(0)) or ""
        )
        project = Project(self, design("en-revue", 5))
        self.assertIn("not accepted", project.create(ticket("to-tickets F-0001"), full(0)) or "")

    def test_a_legacy_ticket_with_a_feature_line_still_uses_the_budget(self) -> None:
        project = Project(self, design("accepte", 1))
        gh = FakeGh(["Feature: F-0001\n\nOpened before the reason was required.\n"])
        self.assertIn("add a part", project.create(ticket("to-tickets F-0001"), gh) or "")


class Reason(unittest.TestCase):
    MESSAGE = "every ticket names its reason: Motif : <one of the admitted reasons>"

    def test_a_ticket_without_a_motif_is_refused(self) -> None:
        project = Project(self, design("accepte", 5))
        for body in ("idea\n", "Feature: F-0001\n", ""):
            with self.subTest(body=body):
                self.assertIn(self.MESSAGE, project.create(body, FakeGh(None)) or "")
        reason = project.bash("gh api repos/o/r/issues -f title=T", FakeGh(None))
        self.assertIn(self.MESSAGE, reason or "")

    def test_an_unknown_motif_is_refused(self) -> None:
        project = Project(self, design("accepte", 5))
        for motif in ("amelioration", "<case allowed by the repository>", "To-tickets F-0001"):
            with self.subTest(motif=motif):
                reason = project.create(ticket(motif, "F-0001"), FakeGh(None))
                self.assertIn(self.MESSAGE, reason or "")

    def test_the_first_tracking_ticket_is_admitted(self) -> None:
        project = Project(self, None)
        gh = FakeGh([ticket("feature-new F-0002"), ticket("to-tickets F-0001")])
        self.assertIsNone(project.create(ticket("feature-new F-0001"), gh))
        self.assertEqual(len(gh.calls), 1)
        self.assertIn('"feature-new F-0001" in:body', gh.calls[0])

    def test_a_second_tracking_ticket_for_the_same_feature_is_refused(self) -> None:
        project = Project(self, None)
        reason = project.create(
            ticket("feature-new F-0001"), FakeGh([ticket("feature-new F-0001")])
        )
        self.assertIn("already has its tracking ticket #1", reason or "")

    def test_tracking_tickets_that_cannot_be_read_refuse(self) -> None:
        project = Project(self, None)
        reason = project.create(ticket("feature-new F-0001"), FakeGh(None))
        self.assertIn("cannot be read", reason or "")
        self.assertIsNotNone(project.create("Motif : feature-new\n", FakeGh([])))

    def test_the_tracking_ticket_of_the_feature_new_skill_passes(self) -> None:
        skill = (support.PLUGIN / "skills" / "feature-new" / "SKILL.md").read_text(encoding="utf-8")
        found = re.search(r"`(Motif : feature-new F-NNNN)`", skill)
        self.assertIsNotNone(found)
        line = (found.group(1) if found else "").replace("F-NNNN", "F-0003")
        body = (
            f"{line}\n\nThe idea, in one page.\n\nFolder: docs/features/0003-x/\n\n"
            "Les tickets de cette feature en seront des sous-issues.\n"
        )
        project = Project(self, None)
        self.assertIsNone(project.create(body, FakeGh([ticket("feature-new F-0001")])))

    def test_a_body_that_cannot_be_read_refuses(self) -> None:
        project = Project(self, design("accepte", 5))
        for command in (
            "gh issue create --title T --web",
            'gh issue create -t T --body "$(cat f)"',
        ):
            with self.subTest(command=command):
                self.assertIn("cannot be read", project.bash(command, full(0)) or "")


class CommandForms(unittest.TestCase):
    def test_a_heredoc_body_is_read(self) -> None:
        project = Project(self, design("accepte", 1))
        command = "gh issue create --title T --body-file - <<'EOF'\nMotif : to-tickets F-0001\nEOF"
        self.assertIsNotNone(project.bash(command, full(1)))
        command = (
            "gh issue create --title T --body \"$(cat <<'EOF'\nMotif : to-tickets F-0001\nEOF\n)\""
        )
        self.assertIsNotNone(project.bash(command, full(1)))
        self.assertIsNone(project.bash(command, full(0)))

    def test_a_post_by_gh_api_is_read(self) -> None:
        project = Project(self, design("accepte", 1))
        command = "gh api repos/o/r/issues -f title=T -f body='Motif : to-tickets F-0001'"
        gh = full(1)
        self.assertIsNotNone(project.bash(command, gh))
        self.assertIn(["--repo", "o/r"], [call[-2:] for call in gh.calls])
        self.assertIsNone(project.bash("gh api repos/o/r/issues", full(1)))
        self.assertIsNone(project.bash("gh api repos/o/r/issues/5/comments -f body=x", full(1)))

    def test_a_post_by_gh_api_with_a_json_input_is_read(self) -> None:
        project = Project(self, design("accepte", 1))
        (project.dir / "issue.json").write_text(
            json.dumps({"title": "T", "body": "Motif : to-tickets F-0001\n"}), encoding="utf-8"
        )
        self.assertIsNotNone(
            project.bash("gh api -X POST repos/o/r/issues --input issue.json", full(1))
        )

    def test_a_graphql_create_issue_is_read(self) -> None:
        project = Project(self, design("accepte", 1))
        command = (
            'gh api graphql -f query=\'mutation { createIssue(input: {repositoryId: "R",'
            ' title: "T", body: "Motif : to-tickets F-0001\\nx"}) { issue { number } } }\''
        )
        self.assertIsNotNone(project.bash(command, full(1)))

    def test_a_graphql_body_variable_is_read(self) -> None:
        project = Project(self, design("accepte", 1))
        command = (
            "gh api graphql -f query='mutation($b: String!) { createIssue(input: {repositoryId:"
            ' "R", title: "T", body: $b}) { issue { number } } }\' -f b=\'Motif : to-tickets F-0001\''
        )
        self.assertIsNotNone(project.bash(command, full(1)))
        self.assertIsNone(project.bash(command, full(0)))

    def test_placement(self) -> None:
        self.assertEqual(placement(ticket("to-tickets F-0007")), ("feature", "F-0007"))
        self.assertEqual(placement(ticket("securite", "F-0007")).kind, "out")
        self.assertEqual(placement(ticket("feature-new F-0007")), ("tracking", "F-0007"))
        self.assertEqual(placement("Feature: F-0003\n").kind, "refused")
        self.assertEqual(counts_for("Feature: F-0003\n"), "F-0003")
        self.assertIsNone(counts_for(ticket("main-rouge 3", "F-0003")))
        self.assertEqual(placement("no motif\n").kind, "refused")
        self.assertEqual(placement("Motif : to-tickets\n").kind, "refused")


UNREADABLE = "the ticket's body cannot be read"


class Bodies(unittest.TestCase):
    """2026-11-13 findings 1 and 6: a body passed by a variable, a nested shell, a backtick."""

    def test_a_body_passed_by_a_variable_is_refused(self) -> None:
        project = Project(self, design("accepte", 5))
        for command in (
            'gh issue create -t T --body "Motif : to-tickets F-0001\n$REST"',
            "gh issue create -t T --body Motif\\ :\\ securite$REST",
            'gh api repos/o/r/issues -f title=T -f body="Motif : securite $REST"',
            'gh issue create -t T --body-file "$FILE"',
            'gh issue create -t T --body "$(cat <<EOF\nMotif : securite $X\nEOF\n)"',
        ):
            with self.subTest(command=command):
                self.assertIn(UNREADABLE, project.bash(command, full(0)) or "")

    def test_a_dollar_in_single_quotes_or_escaped_is_literal(self) -> None:
        project = Project(self, design("accepte", 5))
        for command in (
            "gh issue create -t T --body 'Motif : to-tickets F-0001\n\nCosts $5, see $HOME.'",
            'gh issue create -t T --body "Motif : to-tickets F-0001 costs \\$HOME"',
            "gh issue create -t T --body \"$(cat <<'EOF'\nMotif : to-tickets F-0001\n$X\nEOF\n)\"",
        ):
            with self.subTest(command=command):
                self.assertIsNone(project.bash(command, full(0)))

    def test_a_ticket_opened_inside_a_nested_shell_is_read(self) -> None:
        project = Project(self, design("accepte", 1))
        inner = "gh issue create -t T --body 'Motif : to-tickets F-0001'"
        for command in (
            f'bash -c "{inner}"',
            f'sh -c "{inner}"',
            f'bash -lc "{inner}"',
            f'eval "{inner}"',
            f"env FOO=1 {inner}",
            f"timeout 30 {inner}",
            f'echo "$({inner})"',
            f"bash <<'EOF'\n{inner}\nEOF",
        ):
            with self.subTest(command=command):
                self.assertIn("already has 1 tickets", project.bash(command, full(1)) or "")
                self.assertIsNone(project.bash(command, full(0)))
        self.assertIn(
            UNREADABLE, project.bash('bash -c "gh issue create -t T -b \\"$B\\""', full(0)) or ""
        )
        self.assertIn(
            Reason.MESSAGE, project.bash("sh -c 'gh issue create -t T -b idea'", full(0)) or ""
        )

    def test_a_backtick_in_a_quoted_inline_body_keeps_it_readable(self) -> None:
        project = Project(self, design("accepte", 5))
        body = "Motif : to-tickets F-0001\n\nRun `make check`."
        self.assertIsNone(project.bash(f"gh issue create -t T --body '{body}'", full(0)))
        escaped = body.replace("`", "\\`")
        self.assertIsNone(project.bash(f'gh issue create -t T --body "{escaped}"', full(0)))
        self.assertIn(
            UNREADABLE, project.bash(f'gh issue create -t T --body "{body}"', full(0)) or ""
        )

    def test_a_misspelled_motif_is_refused(self) -> None:
        project = Project(self, design("accepte", 5))
        for motif in ("to-ticket F-0001", "totickets F-0001", "fusion-bloque #3"):
            with self.subTest(motif=motif):
                reason = project.create(ticket(motif, "F-0001"), full(0))
                self.assertIn(Reason.MESSAGE, reason or "")


class Detours(unittest.TestCase):
    """2026-11-13 finding 2: another HTTP client, an alias, an edit of the reason, a GitHub MCP tool."""

    def test_another_client_on_the_issues_api_is_refused(self) -> None:
        project = Project(self, design("accepte", 5))
        for command in (
            'curl -X POST https://api.github.com/repos/o/r/issues -d \'{"title":"T"}\'',
            "wget --post-data x https://api.github.com/graphql",
            "python3 - <<'EOF'\nurlopen('https://api.github.com/repos/o/r/issues')\nEOF",
        ):
            with self.subTest(command=command):
                self.assertIn("api.github.com", project.bash(command, full(0)) or "")
        self.assertIsNone(project.bash("curl https://api.github.com/repos/o/r/pulls", full(0)))

    def test_an_alias_or_a_variable_for_gh_is_refused(self) -> None:
        project = Project(self, design("accepte", 5))
        for command in (
            "alias g=gh; g issue create -t T -b x",
            "alias g='gh issue create'",
            "G=gh; $G issue create -t T -b x",
            'g() { gh "$@"; }',
            "gh $GROUP create -t T -b x",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(project.bash(command, full(0)))
        self.assertIsNone(project.bash("alias ll='ls -l'", full(0)))

    def test_an_edit_may_not_change_the_reason_or_the_feature(self) -> None:
        project = Project(self, design("accepte", 5))
        old = ticket("to-tickets F-0001", "F-0001")
        for new in (
            "No reason any more.\n",
            ticket("securite", "F-0001"),
            ticket("to-tickets F-0001", "F-0002"),
            ticket("to-tickets F-0001", "F-0001") + "Motif : securite\n",
        ):
            with self.subTest(new=new):
                (project.dir / "new.md").write_text(new, encoding="utf-8")
                reason = project.bash("gh issue edit 7 --body-file new.md", FakeGh([], old))
                self.assertIn("`Motif :` or `Feature:` lines of ticket #7", reason or "")
        kept = old + "\nOne more sentence.\n"
        (project.dir / "new.md").write_text(kept, encoding="utf-8")
        self.assertIsNone(project.bash("gh issue edit 7 --body-file new.md", FakeGh([], old)))
        self.assertIsNone(project.bash("gh issue edit 7 --add-label x", FakeGh([], None)))
        self.assertIn(
            "cannot be read", project.bash("gh issue edit 7 -F new.md", FakeGh([], None)) or ""
        )
        patch = "gh api -X PATCH repos/o/r/issues/7 -f body='No reason.'"
        self.assertIn("ticket #7", project.bash(patch, FakeGh([], old)) or "")
        update = 'gh api graphql -f query=\'mutation { updateIssue(input: {id: "I", body: "x"}) { issue { id } } }\''
        self.assertIn("updateIssue", project.bash(update, FakeGh([], old)) or "")

    def test_the_issue_tools_of_a_github_mcp_server_are_held_too(self) -> None:
        project = Project(self, design("accepte", 1))
        create = {"owner": "o", "repo": "r", "title": "T", "body": "idea"}
        self.assertIn(
            Reason.MESSAGE, project.tool("mcp__github__create_issue", create, full(0)) or ""
        )
        create["body"] = "Motif : to-tickets F-0001"
        self.assertIsNone(project.tool("mcp__github__create_issue", create, full(0)))
        self.assertIsNotNone(project.tool("mcp__github__create_issue", create, full(1)))
        written = {**create, "method": "create"}
        self.assertIsNotNone(project.tool("mcp__claude_ai_GitHub__issue_write", written, full(1)))
        old = ticket("to-tickets F-0001")
        update = {"owner": "o", "repo": "r", "issue_number": 3, "body": "gone"}
        self.assertIn(
            "ticket #3", project.tool("mcp__github__update_issue", update, FakeGh([], old)) or ""
        )
        self.assertIsNone(project.tool("mcp__github__get_issue", {"issue_number": 3}, full(9)))


class Removals(unittest.TestCase):
    """A ticket that holds a place in a budget is neither deleted nor transferred."""

    def test_a_counted_ticket_is_neither_deleted_nor_transferred(self) -> None:
        project = Project(self, design("accepte", 5))
        for body in (
            ticket("to-tickets F-0001"),
            ticket("fusion-bloquee #12", "F-0001"),
            "Old ticket.\n\nFeature: F-0001\n",
            ticket("feature-new F-0001"),
        ):
            for command in (
                "gh issue delete 7 --yes",
                "gh issue delete https://github.com/o/r/issues/7 --yes",
                "gh issue transfer 7 o/other",
                "gh -R o/r issue transfer 7 o/other",
                "bash -c 'gh issue delete 7 --yes'",
            ):
                with self.subTest(body=body, command=command):
                    reason = project.bash(command, FakeGh([], body))
                    self.assertIn("holds a place in the budget of F-0001", reason or "")

    def test_an_out_of_budget_ticket_may_go(self) -> None:
        project = Project(self, design("accepte", 5))
        gh = FakeGh([], ticket("securite"))
        self.assertIsNone(project.bash("gh issue delete 7 --yes", gh))
        self.assertIsNone(project.bash("gh issue transfer 7 o/other", gh))
        self.assertIn(["issue", "view", "7", "--json", "body"], gh.calls)

    def test_an_unknown_or_unreadable_ticket_is_refused(self) -> None:
        project = Project(self, design("accepte", 5))
        self.assertIn(
            "cannot be read", project.bash("gh issue delete 7 --yes", FakeGh([], None)) or ""
        )
        self.assertIn(
            "cannot be read", project.bash('gh issue delete "$N" --yes', FakeGh([], "")) or ""
        )
        self.assertIn("cannot be read", project.bash("gh issue delete --yes", FakeGh([], "")) or "")

    def test_the_mutations_and_the_mcp_tools_are_held_too(self) -> None:
        project = Project(self, design("accepte", 5))
        for mutation in ("deleteIssue", "transferIssue"):
            command = f"gh api graphql -f query='mutation {{ {mutation}(input: {{issueId: \"I\"}}) {{ clientMutationId }} }}'"
            with self.subTest(mutation=mutation):
                self.assertIn("refused", project.bash(command, FakeGh([], "")) or "")
        counted = FakeGh([], ticket("to-tickets F-0001"))
        target = {"owner": "o", "repo": "r", "issue_number": 7}
        for tool, extra in (
            ("mcp__github__delete_issue", {}),
            ("mcp__github__transfer_issue", {}),
            ("mcp__claude_ai_GitHub__issue_write", {"method": "delete"}),
        ):
            with self.subTest(tool=tool):
                reason = project.tool(tool, {**target, **extra}, counted)
                self.assertIn("budget of F-0001", reason or "")
        self.assertIsNone(
            project.tool("mcp__github__delete_issue", target, FakeGh([], "Motif : securite"))
        )


def closed(reason: object) -> tuple[str, dict]:
    return ticket("to-tickets F-0001"), {"state": "CLOSED", "stateReason": reason}


class ClosedReason(unittest.TestCase):
    """A ticket closed as not planned (merged into another) leaves the budget; any other stays in it."""

    def test_a_ticket_closed_as_not_planned_does_not_count(self) -> None:
        project = Project(self, design("accepte", 1))
        self.assertIsNone(project.create(ticket("to-tickets F-0001"), FakeGh([closed("NOT_PLANNED")])))

    def test_a_completed_an_open_or_an_unknown_ticket_counts(self) -> None:
        open_ticket = (ticket("to-tickets F-0001"), {"state": "OPEN", "stateReason": ""})
        for item in (closed("COMPLETED"), open_ticket, closed("DUPLICATE"), closed(None), closed(7), ticket("to-tickets F-0001")):
            with self.subTest(item=item):
                project = Project(self, design("accepte", 1))
                self.assertIn("already has 1 tickets", project.create(ticket("to-tickets F-0001"), FakeGh([item])) or "")

    def test_the_search_asks_for_the_state_and_its_reason(self) -> None:
        gh = FakeGh([])
        Project(self, design("accepte", 1)).create(ticket("to-tickets F-0001"), gh)
        self.assertTrue(all("number,body,state,stateReason" in call for call in gh.calls))

    def test_a_feature_recut_by_closing_merged_tickets_keeps_its_budget(self) -> None:
        tickets = [closed("NOT_PLANNED")] * 45 + [closed("COMPLETED")] * 10 + [ticket("to-tickets F-0001")] * 5
        project = Project(self, design("en-revue"))
        self.assertIsNone(project.write(design("accepte", 15), FakeGh(tickets)))
        project.design.write_text(design("accepte", 15), encoding="utf-8")
        self.assertIn("already has 15 tickets", project.create(ticket("to-tickets F-0001"), FakeGh(tickets)) or "")


REOPEN_COMMANDS = (
    "gh issue reopen 16",
    "gh issue reopen https://github.com/o/r/issues/16",
    "gh -R o/r issue reopen 16 -c 'back in scope'",
    "gh issue reopen --comment back 16",
    "bash -c 'gh issue reopen 16'",
    "gh api -X PATCH repos/o/r/issues/16 -f state=open",
    "gh api --method POST repos/o/r/issues/16 -F state=open",
    "gh api -X PATCH repos/o/r/issues/16 --input - <<'EOF'\n{\"state\": \"open\"}\nEOF",
)
REOPEN_TOOLS = (
    ("mcp__github__update_issue", {"state": "open"}),
    ("mcp__claude_ai_GitHub__issue_write", {"method": "update", "state": "open"}),
)


class Reopenings(unittest.TestCase):
    """Reopening a ticket closed as not planned brings it back in the count: the budget holds it."""

    def reasons(self, counted: int, viewed: object) -> list[str | None]:
        project = Project(self, design("accepte", 15))
        gh = FakeGh([ticket("to-tickets F-0001")] * counted, viewed)  # type: ignore[arg-type]
        target = {"owner": "o", "repo": "r", "issue_number": 16}
        found = [project.bash(command, gh) for command in REOPEN_COMMANDS]
        return found + [project.tool(tool, {**target, **extra}, gh) for tool, extra in REOPEN_TOOLS]

    def test_a_released_ticket_is_not_reopened_past_the_budget(self) -> None:
        for form, reason in zip(REOPEN_COMMANDS + tuple(t for t, _ in REOPEN_TOOLS), self.reasons(15, closed("NOT_PLANNED"))):
            with self.subTest(form=form):
                self.assertIn("F-0001 already has 15 tickets for a budget of 15", reason or "")

    def test_a_released_ticket_reopens_within_the_budget(self) -> None:
        self.assertEqual(self.reasons(14, closed("NOT_PLANNED")), [None] * (len(REOPEN_COMMANDS) + len(REOPEN_TOOLS)))

    def test_a_ticket_that_already_counts_or_sits_out_of_the_budget_reopens(self) -> None:
        for viewed in (closed("COMPLETED"), (ticket("securite"), {"state": "CLOSED", "stateReason": "NOT_PLANNED"})):
            with self.subTest(viewed=viewed):
                self.assertEqual(set(self.reasons(15, viewed)), {None})

    def test_an_unreadable_number_or_state_is_refused(self) -> None:
        project = Project(self, design("accepte", 15))
        gh = FakeGh([], closed("NOT_PLANNED"))
        for command in ('gh issue reopen "$N"', "gh issue reopen", 'gh api -X PATCH repos/o/r/issues/16 -f state="$S"'):
            with self.subTest(command=command):
                self.assertIn("cannot be read", project.bash(command, gh) or "")
        self.assertIn("cannot be read", project.bash("gh issue reopen 16", FakeGh([], None)) or "")
        target = {"owner": "o", "repo": "r", "issue_number": 16}
        self.assertIn("cannot be read", project.tool("mcp__github__update_issue", {**target, "state": ["open"]}, gh) or "")

    def test_the_reopening_mutations_are_refused(self) -> None:
        project = Project(self, design("accepte", 15))
        for mutation in ('reopenIssue(input: {issueId: "I"})', 'updateIssue(input: {id: "I", state: OPEN})'):
            command = f"gh api graphql -f query='mutation {{ {mutation} {{ clientMutationId }} }}'"
            with self.subTest(mutation=mutation):
                self.assertIn("gh issue reopen", project.bash(command, FakeGh([], "")) or "")

    def test_closing_a_ticket_is_no_reopening(self) -> None:
        project = Project(self, design("accepte", 15))
        gh = FakeGh(None, None)
        self.assertIsNone(project.bash("gh api -X PATCH repos/o/r/issues/16 -f state=closed", gh))
        self.assertIsNone(project.bash("gh issue close 16", gh))
        self.assertEqual(gh.calls, [])


class CeilingEverywhere(unittest.TestCase):
    """2026-11-13 finding 3: the ceiling and the published tickets bound every write of the budget."""

    def test_a_budget_below_the_published_tickets_is_refused(self) -> None:
        project = Project(self, design("accepte", 10))
        self.assertIn("already has 6 tickets", project.write(design("accepte", 5), full(6)) or "")
        self.assertIsNone(project.write(design("accepte", 7), full(6)))
        self.assertIn("cannot be counted", project.write(design("accepte", 7), FakeGh(None)) or "")

    def test_taking_the_acceptance_off_does_not_raise_the_budget(self) -> None:
        project = Project(self, design("accepte", 10), memory=True)
        self.assertIsNone(project.write(design("en-revue", 10)))
        project.design.write_text(design("en-revue", 10), encoding="utf-8")
        self.assertIn("never rises", project.write(design("en-revue", 14)) or "")
        self.assertIn("never rises", project.write(design("accepte", 14)) or "")
        self.assertIsNone(project.write(design("accepte", 9)))

    def test_git_history_keeps_the_accepted_budget(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git absent")
        project = Project(self, design("accepte", 10))

        def git(*args: str) -> None:
            subprocess.run(  # noqa: S603 - git with fixed arguments, in a temporary folder
                ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(project.dir), *args],
                check=True,
                capture_output=True,
            )

        git("init", "-q")
        git("add", "-A")
        git("commit", "-q", "-m", "accepted")
        project.design.write_text(design("en-revue", 10), encoding="utf-8")
        self.assertIn("never rises", project.write(design("en-revue", 12)) or "")
        self.assertIsNone(project.write(design("en-revue", 8)))

    def test_a_shell_write_of_the_budget_is_refused(self) -> None:
        project = Project(self, design("accepte", 10))
        command = "sed -i 's/feature-tickets: 10/feature-tickets: 14/' docs/features/0001-runner/design.md"
        self.assertIn("with Edit or Write", project.bash(command, full(0)) or "")
        self.assertIsNone(
            project.bash("grep feature-tickets docs/features/0001-runner/design.md", full(0))
        )


class DefaultFeatureDir(unittest.TestCase):
    """2026-11-13 finding 4: without the key, the template's `feature-dir` is read."""

    def test_the_template_value_stands_in_for_an_absent_key(self) -> None:
        project = Project(self, design("accepte", 2), usine="# Usine\n")
        self.assertIsNone(project.create(ticket("to-tickets F-0001"), full(1)))
        self.assertIn(
            "already has 2 tickets", project.create(ticket("to-tickets F-0001"), full(2)) or ""
        )


class Burst(unittest.TestCase):
    """2026-11-13 finding 5: the tickets let through count while GitHub's index lags."""

    def test_a_burst_stops_at_the_budget_although_the_index_lags(self) -> None:
        project = Project(self, design("accepte", 2), memory=True)
        body = ticket("to-tickets F-0001")
        self.assertIsNone(project.create(body, full(0)))
        self.assertIsNone(project.create(body, full(0)))
        self.assertIn("already has 2 tickets", project.create(body, full(0)) or "")
        self.assertIn("already has 2 tickets", project.create(body, full(2)) or "")

    def test_one_command_that_opens_more_than_the_budget_is_refused_whole(self) -> None:
        project = Project(self, design("accepte", 2), memory=True)
        one = "gh issue create -t T -b 'Motif : to-tickets F-0001'"
        self.assertIsNotNone(project.bash(f"{one}; {one}; {one}", full(0)))
        self.assertIsNone(project.bash(f"{one}; {one}", full(0)))

    def test_a_second_tracking_ticket_in_a_burst_is_refused(self) -> None:
        project = Project(self, None, memory=True)
        self.assertIsNone(project.create(ticket("feature-new F-0004"), FakeGh([])))
        self.assertIn(
            "one per feature", project.create(ticket("feature-new F-0004"), FakeGh([])) or ""
        )

    def test_reservations_expire(self) -> None:
        project = Project(self, design("accepte", 1), memory=True)
        body = ticket("to-tickets F-0001")
        self.assertIsNone(project.create(body, full(0)))
        with mock.patch("time.time", return_value=__import__("time").time() + 601):
            self.assertIsNone(project.create(body, full(0)))


def skill_text(name: str) -> str:
    return (support.PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


class SkillTickets(unittest.TestCase):
    """The tickets the skills describe pass the hook, and every `gh issue create` names a Motif."""

    def test_the_tickets_of_the_feature_design_skill_pass(self) -> None:
        found = re.search(r"`(Motif : to-tickets F-NNNN)`", skill_text("feature-design"))
        self.assertIsNotNone(found)
        line = (found.group(1) if found else "").replace("F-NNNN", "F-0001")
        body = f"{line}\n\nWhat is missing.\n\n## Criteria\n\n- A1: a test proves it\n"
        project = Project(self, design("accepte", 5))
        self.assertIsNone(project.create(body, full(4)))
        self.assertIsNotNone(project.create(body, full(5)))

    def test_the_merge_blocking_ticket_of_the_review_skills_passes(self) -> None:
        for name in ("feature-build", "feature-review"):
            with self.subTest(skill=name):
                text = skill_text(name)
                motif = re.search(r"`(Motif : fusion-bloquee #<pr>)`", text)
                feature = re.search(r"`(Feature: F-NNNN)`", text)
                self.assertIsNotNone(motif)
                self.assertIsNotNone(feature)
                lines = [
                    (motif.group(1) if motif else "").replace("#<pr>", "#12"),
                    (feature.group(1) if feature else "").replace("F-NNNN", "F-0001"),
                ]
                body = f"{lines[0]}\n\nThe merge of #12 is blocked.\n\n{lines[1]}\n"
                project = Project(self, design("accepte", 5))
                self.assertIsNone(project.create(body, full(2)))

    def test_no_skill_or_agent_creates_a_ticket_without_a_motif(self) -> None:
        checked = 0
        for folder in ("skills", "agents"):
            for path in sorted((support.PLUGIN / folder).rglob("*.md")):
                text = path.read_text(encoding="utf-8")
                for paragraph in re.split(r"\n\s*\n", text):
                    if "gh issue create" in paragraph or "createIssue" in paragraph:
                        checked += 1
                        with self.subTest(path=str(path.relative_to(support.PLUGIN))):
                            self.assertRegex(paragraph, r"`Motif : [a-z-]+")
        self.assertGreaterEqual(checked, 4)


class Binding(unittest.TestCase):
    def test_hooks_json_binds_the_guard_and_fails_closed(self) -> None:
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        found = [
            (group["matcher"], hook)
            for group in hooks["hooks"]["PreToolUse"]
            for hook in group["hooks"]
            if "/hooks/guard_ticket_budget.py" in hook["command"]
        ]
        self.assertEqual(len(found), 1)
        matcher, hook = found[0]
        for tool in ("Bash", "PowerShell", "Edit", "Write", "MultiEdit"):
            self.assertIn(tool, matcher.split("|"))
        for tool in ("mcp__github__create_issue", "mcp__claude_ai_GitHub__issue_write"):
            self.assertRegex(tool, f"^(?:{matcher})$")
        self.assertNotRegex("mcp__notion__create_page", f"^(?:{matcher})$")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/", hook["command"])
        self.assertTrue(hook["command"].endswith("|| exit 2"))
        self.assertEqual(hook.get("onFailure"), "block")

    def test_the_script_refuses_with_exit_2_when_gh_is_absent(self) -> None:
        project = Project(self, design("accepte", 5))
        empty = project.dir / "bin"
        empty.mkdir()
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh issue create -t T -b 'Motif : to-tickets F-0001'"},
            "cwd": str(project.dir),
        }
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
        env.update(PATH=str(empty), HOME=str(project.dir), USERPROFILE=str(project.dir))
        completed = subprocess.run(  # noqa: S603 - the interpreter running the tests, a fixed script
            [sys.executable, str(support.PLUGIN / "hooks" / "guard_ticket_budget.py")],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("Blocked by the forge plugin (guard_ticket_budget)", completed.stderr)

    def test_the_template_and_the_skill_declare_the_budget(self) -> None:
        template = (support.PLUGIN / "templates" / "features" / "design.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("\nfeature-tickets: <N, at most 15", template.split("\n---\n")[0])
        skill = (support.PLUGIN / "skills" / "feature-design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("`forge:product-owner` cuts the feature into at most 15 tickets", skill)


if __name__ == "__main__":
    unittest.main()
