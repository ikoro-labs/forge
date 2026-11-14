"""The report mail's template and its hook: a mail that departs from the template is refused (forge#181)."""

import contextlib
import json
import os
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import support
from guard_report_mail import REFUSED, outcome
from output_check import deviations
from report_mail import MAIL_FILE

GOOD = """<h2>Factory report, acme/widgets, 2030-01-02T10:00Z</h2>
<h3>What changed</h3>
<p>Since 2030-01-02T08:00:00Z.</p><ul><li>acme/widgets: merged #2 new change (1 round(s), 30 min).</li></ul>
<h3>Awaiting you</h3>
<ul><li>acme/widgets: PR #3 is green and unmerged.</li></ul>
<h3>CI and runners</h3>
<table><tr><td>Repository</td><td>Host</td><td>Runners</td></tr><tr><td>acme/widgets</td><td>pc</td><td>2 online, 1 busy, 0 offline</td></tr></table>
<h3>Figures</h3>
<table><tr><td>Repository</td><td>Merged</td></tr><tr><td>acme/widgets</td><td>1</td></tr></table>
"""
WITHOUT_AWAITING = GOOD.replace(
    "<h3>Awaiting you</h3>\n<ul><li>acme/widgets: PR #3 is green and unmerged.</li></ul>\n", ""
)
CONFIG = "- `report-repo` : `acme/widgets`\n"


@contextlib.contextmanager
def project(mail: str | None) -> Iterator[tuple[Path, Path]]:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / "project"
        (root / "docs" / "agents").mkdir(parents=True)
        (root / "docs" / "agents" / "usine.md").write_text(CONFIG, encoding="utf-8")
        state = Path(folder) / "state"
        state.mkdir()
        if mail is not None:
            (state / MAIL_FILE).write_text(mail, encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
        env.update(HOME=folder, USERPROFILE=folder, CLAUDE_PROJECT_DIR=str(root))
        with mock.patch.dict("os.environ", env, clear=True):
            yield root, state


def bash(command: str) -> str:
    return json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}})


def sent(state: Path) -> str:
    return f"uv run --no-project --quiet python plugins/forge/scripts/report_mail.py --state-dir {state} --sent"


class TemplateTests(unittest.TestCase):
    def test_a3_the_template_fixes_the_parts_of_the_mail(self) -> None:
        text = (support.PLUGIN / "templates" / "report-mail.md").read_text(encoding="utf-8")
        for part in ("What changed", "Awaiting you", "CI and runners", "table"):
            self.assertIn(part, text)
        self.assertEqual(deviations(GOOD, "report-mail"), [])

    def test_a3_each_missing_part_and_a_missing_table_are_listed(self) -> None:
        found = deviations(WITHOUT_AWAITING, "report-mail")
        self.assertTrue(any("Awaiting you" in line and "missing" in line for line in found), found)
        no_table = "\n".join(line for line in GOOD.splitlines() if "<table>" not in line)
        self.assertTrue(any("table" in line for line in deviations(no_table, "report-mail")))
        self.assertTrue(any("What changed" in line for line in deviations("<p>hello</p>", "report-mail")))

    def test_a3_the_french_labels_are_accepted_and_a_long_mail_is_refused(self) -> None:
        french = GOOD.replace("What changed", "Ce qui a changé").replace("Awaiting you", "Ce qui t'attend")
        french = french.replace("CI and runners", "CI et runners")
        self.assertEqual(deviations(french, "report-mail"), [])
        long = GOOD + "<table><tr>" + "<td>word</td>" * 600 + "</tr></table>"
        self.assertTrue(any("words" in line for line in deviations(long, "report-mail")))
        self.assertEqual(deviations(long, "report-mail", {"output-words-report-mail": ["0"]}), [])


class HookTests(unittest.TestCase):
    def test_a3_1_a_mail_without_the_part_awaiting_you_is_refused_by_the_hook(self) -> None:
        with project(WITHOUT_AWAITING) as (_, state):
            result = outcome(bash(sent(state)))
            self.assertEqual(result.code, REFUSED)
            self.assertIn("Awaiting you", result.stderr)

    def test_a3_a_conforming_mail_passes_and_so_does_a_command_that_is_not_the_send(self) -> None:
        with project(GOOD) as (_, state):
            self.assertEqual(outcome(bash(sent(state))).code, 0)
            self.assertEqual(outcome(bash("ls")).code, 0)
        with project(WITHOUT_AWAITING) as (_, state):
            printing = f"uv run python plugins/forge/scripts/report_mail.py --state-dir {state}"
            self.assertEqual(outcome(bash(printing)).code, 0)

    def test_a3_the_hook_reads_the_mail_of_the_default_state_folder_too(self) -> None:
        with project(None) as (_, state):
            default = Path.home() / ".claude" / "hooks" / "state" / "report-mail" / "acme-widgets"
            default.mkdir(parents=True)
            (default / MAIL_FILE).write_text(WITHOUT_AWAITING, encoding="utf-8")
            command = "uv run python report_mail.py --sent"
            self.assertEqual(outcome(bash(command)).code, REFUSED)

    def test_a3_no_mail_to_read_lets_the_command_through(self) -> None:
        with project(None) as (_, state):
            self.assertEqual(outcome(bash(sent(state))).code, 0)

    def test_a3_a_send_inside_a_compound_command_is_read(self) -> None:
        with project(WITHOUT_AWAITING) as (_, state):
            command = f"python send.py && python plugins/forge/scripts/report_mail.py --state-dir {state} --sent"
            self.assertEqual(outcome(bash(command)).code, REFUSED)

    def test_a3_hooks_json_runs_the_hook_on_shell_calls_and_turns_its_code_3_into_a_block(self) -> None:
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        found = [
            (group["matcher"], hook["command"])
            for group in hooks["PreToolUse"]
            for hook in group["hooks"]
            if "guard_report_mail.py" in hook["command"]
        ]
        self.assertEqual(len(found), 1)
        matcher, command = found[0]
        self.assertIn("Bash", matcher)
        self.assertIn("[ $? -eq 3 ] && exit 2", command)


if __name__ == "__main__":
    unittest.main()
