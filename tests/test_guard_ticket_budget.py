"""The ticket budget of a feature: the design's ceiling and the closed budget, gh simulated."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from guard_ticket_budget import CEILING, Runner, placement, refusal

DESIGN = "---\nfeature: F-0001\ndocument: design\nstatut: {statut}\n{budget}base: abc1234\n---\n\n# F-0001\n"


def design(statut: str = "en-revue", budget: int | None = None) -> str:
    line = "" if budget is None else f"ticket-budget: {budget}\n"
    return DESIGN.format(statut=statut, budget=line)


def ticket(motif: str, feature: str | None = None) -> str:
    lines = [f"Motif : {motif}", "", "What is missing.", ""]
    if feature is not None:
        lines.append(f"Feature: {feature}")
    return "\n".join(lines) + "\n"


class FakeGh:
    """`gh issue list` answered from a list of bodies; None plays an unreachable gh."""

    def __init__(self, bodies: list[str] | None) -> None:
        self.bodies = bodies
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], cwd: str | None) -> str | None:
        self.calls.append(argv)
        if self.bodies is None:
            return None
        issues = [{"number": n, "body": body} for n, body in enumerate(self.bodies, start=1)]
        return json.dumps(issues)


class Project:
    """A project folder with its usine.md and one design, the session's CLAUDE_ variables kept out."""

    def __init__(self, test: unittest.TestCase, design_text: str | None) -> None:
        self.dir = Path(tempfile.mkdtemp())
        test.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "docs" / "agents").mkdir(parents=True)
        (self.dir / "docs" / "agents" / "usine.md").write_text(
            "# Usine\n- `feature-dir` : `docs/features`\n", encoding="utf-8"
        )
        self.design = self.dir / "docs" / "features" / "0001-runner" / "design.md"
        self.design.parent.mkdir(parents=True)
        if design_text is not None:
            self.design.write_text(design_text, encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
        env.update(HOME=str(self.dir), USERPROFILE=str(self.dir))
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

    def write(self, content: str) -> str | None:
        event = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.design), "content": content},
            "cwd": str(self.dir),
        }
        return refusal(event, FakeGh([]))


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
        self.assertIn("ticket-budget", project.write(design("accepte")) or "")

    def test_a_budget_of_zero_is_refused(self) -> None:
        project = Project(self, design())
        self.assertIsNotNone(project.write(design("accepte", 0)))

    def test_a_design_in_review_is_not_checked(self) -> None:
        project = Project(self, design())
        self.assertIsNone(project.write(design("en-revue", 40)))

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
        self.assertIsNone(project.write(design("accepte", 24)))

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
        self.assertIn("declare ticket-budget in the design first", reason or "")
        self.assertIn("re-split the feature with the product-owner", reason or "")

    def test_a_missing_or_unaccepted_design_refuses_the_ticket(self) -> None:
        self.assertIn(
            "no design", Project(self, None).create(ticket("to-tickets F-0001"), full(0)) or ""
        )
        project = Project(self, design("en-revue", 5))
        self.assertIn("not accepted", project.create(ticket("to-tickets F-0001"), full(0)) or "")

    def test_a_tracking_issue_without_motif_or_feature_passes(self) -> None:
        project = Project(self, design("accepte", 1))
        self.assertIsNone(
            project.bash(
                "gh issue create --label feature --title 'F-0002 : x' --body 'idea'", FakeGh(None)
            )
        )

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
        self.assertEqual(placement("Feature: F-0003\n").detail, "F-0003")
        self.assertEqual(placement("no motif\n").kind, "none")
        self.assertEqual(placement("Motif : to-tickets\n").kind, "refused")


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
        self.assertIn("\nticket-budget: <N, at most 15", template.split("\n---\n")[0])
        skill = (support.PLUGIN / "skills" / "feature-design" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("`forge:product-owner` cuts the feature into at most 15 tickets", skill)


if __name__ == "__main__":
    unittest.main()
