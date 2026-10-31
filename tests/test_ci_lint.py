"""Ticket #75 : lint, types et actions épinglées par SHA dans la CI de ce dépôt."""

import re
import unittest

import support

WORKFLOW = (support.REPO_ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
USINE = (support.REPO_ROOT / "docs" / "agents" / "usine.md").read_text(encoding="utf-8")
CLAUDE = (support.REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

RUFF = "uv run --no-project --quiet --with ruff==0.17.3 ruff check plugins/forge tests"
MYPY = "uv run --no-project --quiet --with mypy==2.4.1 mypy"


class ActionsPinned(unittest.TestCase):
    def test_every_action_is_pinned_by_commit_sha_with_its_tag_in_a_comment(self) -> None:
        """Ticket #75, point 3 : chaque action est épinglée par SHA de commit, son tag en commentaire."""
        uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)(.*)$", WORKFLOW, re.M)
        self.assertGreaterEqual(len(uses), 3)
        for reference, rest in uses:
            with self.subTest(reference):
                self.assertRegex(reference, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")
                self.assertRegex(rest, r"#\s*v\d+(\.\d+)*")


class LintJob(unittest.TestCase):
    def test_the_workflow_has_a_lint_job_that_runs_both_checks(self) -> None:
        """Ticket #75, point 2 : un job `lint` lance `ruff check` et `mypy` à leur version épinglée."""
        job = re.search(r"^  lint:\n(.*?)(?=^  \w|\Z)", WORKFLOW, re.M | re.S)
        self.assertIsNotNone(job)
        assert job is not None
        self.assertIn(RUFF, job.group(1))
        self.assertIn(MYPY, job.group(1))


class CommandsListed(unittest.TestCase):
    def test_ci_replay_and_the_pre_pr_list_carry_both_commands(self) -> None:
        """Ticket #75, point 4 : les commandes sont dans `ci-replay` et dans « Vérifier avant toute PR »."""
        for command in (RUFF, MYPY):
            with self.subTest(command):
                self.assertIn(f"- `ci-replay` : `{command}`", USINE)
                self.assertIn(command, CLAUDE)


class ToolVersions(unittest.TestCase):
    def test_versions_are_pinned_and_the_configuration_gives_a_reason_per_exception(self) -> None:
        """Ticket #75, point 1 : règles et exceptions écrites dans la configuration, chaque exception motivée."""
        ruff = (support.REPO_ROOT / "ruff.toml").read_text(encoding="utf-8")
        mypy = (support.REPO_ROOT / "mypy.ini").read_text(encoding="utf-8")
        self.assertRegex(ruff, r'(?m)^ignore = \["B905"\]')
        self.assertRegex(ruff, r"(?m)^# B905 : \S")
        self.assertRegex(mypy, r"(?m)^# .*Windows[^\n]*\n(?:#[^\n]*\n)*\[mypy-handoff_header\]")


if __name__ == "__main__":
    unittest.main()
