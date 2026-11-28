"""Ticket #376: the Windows tests of the CI are frozen (decision of 2026-11-28), not deleted.

The check `tests (windows-latest)` is a required context of the ruleset of `main` and a `required-contexts`
key of `docs/agents/usine.md`: its name stays. A job skipped by a job-level `if` is reported as passing
(GitHub documentation, "Using conditions to control job execution"), so the job stays declared and only
`workflow_dispatch` runs it.
"""

import re
import unittest

import support

WORKFLOW = (support.REPO_ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
USINE = (support.REPO_ROOT / "docs" / "agents" / "usine.md").read_text(encoding="utf-8")
CLAUDE = (support.REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
RULES = (support.REPO_ROOT / ".claude" / "rules" / "forge.md").read_text(encoding="utf-8")

SUITE = "uv run --no-project --quiet --with pytest==9.2.0 python -m pytest tests -v"


def jobs() -> dict[str, str]:
    """The text of each job of the workflow, by job id."""
    body = WORKFLOW.split("\njobs:\n", 1)[1]
    pattern = r"^  (\w[\w-]*):\n(.*?)(?=^  \S|\Z)"
    return {match.group(1): match.group(2) for match in re.finditer(pattern, body, re.M | re.S)}


def job_named(name: str) -> str:
    found = [text for text in jobs().values() if re.search(rf"^    name: {re.escape(name)}$", text, re.M)]
    assert len(found) == 1, f"one job named {name!r}, got {len(found)}"
    return found[0]


def steps(job: str) -> str:
    return job.split("    steps:\n", 1)[1]


class WindowsJobIsFrozen(unittest.TestCase):
    def test_a1_the_windows_check_keeps_its_name_and_a_job_level_if_skips_it_on_pull_request_and_push(self) -> None:
        """#376 A1: a job named `tests (windows-latest)`, literal, whose `if` lets only `workflow_dispatch` in."""
        job = job_named("tests (windows-latest)")
        self.assertRegex(job, r"(?m)^    runs-on: windows-latest$")
        self.assertRegex(job, r"(?m)^    if: github\.event_name == 'workflow_dispatch'$")
        self.assertNotIn("matrix", job)

    def test_a2_the_windows_job_runs_the_same_steps_as_before_and_the_workflow_can_be_dispatched(self) -> None:
        """#376 A2: `workflow_dispatch` is a trigger, and the Windows job runs the suite of the Linux job."""
        self.assertRegex(WORKFLOW, r"(?m)^  workflow_dispatch:")
        windows = steps(job_named("tests (windows-latest)"))
        self.assertIn(SUITE, windows)
        self.assertEqual(windows, steps(job_named("tests (ubuntu-latest)")))

    def test_a3_the_linux_lint_and_validate_jobs_run_on_every_trigger(self) -> None:
        """#376 A3: no `if` on `tests (ubuntu-latest)`, `lint` or `validate`; the required contexts all exist."""
        linux = job_named("tests (ubuntu-latest)")
        self.assertRegex(linux, r"(?m)^    runs-on: ubuntu-latest$")
        unfrozen = {"tests (ubuntu-latest)": linux, "lint": jobs()["lint"], "validate": jobs()["validate"]}
        for name, text in unfrozen.items():
            with self.subTest(name):
                self.assertNotRegex(text, r"(?m)^    if:")
        for context in re.findall(r"- `required-contexts` : `([^`]+)`", USINE):
            with self.subTest(context):
                declared = context in jobs() or any(f"name: {context}" in text for text in jobs().values())
                self.assertTrue(declared)


if __name__ == "__main__":
    unittest.main()
