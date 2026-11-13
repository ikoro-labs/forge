"""The output guard on its three events: what it refuses, what it lets through, and its bound."""

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import support
from guard_output import REFUSED, outcome, state_dir

TICKET = "Motif: demande-kevin\nWhat is missing.\n\n## Criteria\n\n- A1: a test.\n"
REPLY = "Done: merged #12.\n\nMeasured: CI 4 min, run 99.\n\nAwaiting your decision: nothing.\n"
CODER = "RESULT: PR\nPR: #40\nTICKET: #12 closes\nCRITERIA: A1 ; not covered: none\nNOTES: none\n"
VERDICT_ACCEPT_WITH_BLOCKER = (
    "VERDICT: ACCEPT\nROUND: 1\nHEAD: abcdef1\nSPEC: #12: 1 criteria covered, 0 partial, 0 missing\n"
    "FINDINGS:\n- [BLOCKER] a.py:1 | A1 | broken\nGATES: pass\n"
)


@contextlib.contextmanager
def isolated() -> Iterator[Path]:
    """A HOME and a project of their own, without the CLAUDE_ variables of the running session."""
    with tempfile.TemporaryDirectory() as folder:
        home = Path(folder) / "home"
        project = Path(folder) / "project"
        home.mkdir()
        project.mkdir()
        env = {key: value for key, value in os.environ.items() if not key.startswith("CLAUDE_")}
        env.update(HOME=str(home), USERPROFILE=str(home), CLAUDE_PROJECT_DIR=str(project))
        with mock.patch.dict("os.environ", env, clear=True):
            yield project


def run(event: dict[str, object]) -> tuple[int, str, str]:
    result = outcome(json.dumps(event))
    return result.code, result.stderr, result.stdout


def bash(command: str, cwd: str = ".") -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": cwd,
    }


def subagent_stop(agent: str, text: str, active: bool = False, **extra: object) -> dict[str, object]:
    return {
        "hook_event_name": "SubagentStop",
        "agent_type": agent,
        "agent_id": "a1b2",
        "stop_hook_active": active,
        "last_assistant_message": text,
        **extra,
    }


def handback(agent: str, text: str) -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "SubagentHandback",
        "agent_type": agent,
        "agent_id": "c3d4",
        "tool_input": {"message": text},
    }


class SubagentStop(unittest.TestCase):
    def test_a_forge_agent_out_of_its_format_is_refused_with_the_deviations(self) -> None:
        with isolated():
            code, err, _ = run(subagent_stop("forge:coder", "I opened the PR."))
        self.assertEqual(code, REFUSED)
        self.assertIn("`coder` format", err)
        self.assertIn("- no line starts with `RESULT:`", err)

    def test_a_forge_agent_in_its_format_passes(self) -> None:
        with isolated():
            self.assertEqual(run(subagent_stop("forge:coder", CODER)), (0, "", ""))

    def test_the_judge_is_held_to_the_verdict(self) -> None:
        with isolated():
            code, err, _ = run(subagent_stop("forge:qc-conf", VERDICT_ACCEPT_WITH_BLOCKER))
        self.assertEqual(code, REFUSED)
        self.assertIn("`VERDICT: ACCEPT` with 1", err)

    def test_any_other_agent_follows_the_generic_rule(self) -> None:
        long = "\n\n".join(" ".join(["word"] * 40) for _ in range(6))
        with isolated():
            code, err, _ = run(subagent_stop("Explore", long))
            self.assertEqual(code, REFUSED)
            self.assertIn("at most 200", err)
            self.assertEqual(run(subagent_stop("Explore", "Found it at a.py:3.")), (0, "", ""))

    def test_after_one_refusal_it_passes_and_logs(self) -> None:
        with isolated():
            code, _, out = run(subagent_stop("forge:coder", "still prose", active=True))
            journal = (state_dir() / "journal.jsonl").read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn("after one refusal", json.loads(out)["systemMessage"])
        entry = json.loads(journal.splitlines()[-1])
        self.assertEqual((entry["agent_type"], entry["kind"]), ("forge:coder", "coder"))

    def test_an_internal_agent_without_a_type_passes(self) -> None:
        with isolated():
            self.assertEqual(run(subagent_stop("", "anything at all")), (0, "", ""))

    def test_a_report_delivered_by_handback_is_not_checked_again(self) -> None:
        with isolated() as project:
            transcript = project / "agent.jsonl"
            call = {"type": "tool_use", "name": "SubagentHandback", "input": {"message": CODER}}
            transcript.write_text(json.dumps({"message": {"content": [call]}}) + "\n", encoding="utf-8")
            event = subagent_stop("forge:coder", "", agent_transcript_path=str(transcript))
            self.assertEqual(run(event)[0], 0)
            event["last_assistant_message"] = "closing words"
            self.assertEqual(run(event)[0], 0)


class Handback(unittest.TestCase):
    def test_refused_once_then_let_through_and_logged(self) -> None:
        with isolated():
            first = run(handback("forge:staff-engineer", "I think yes."))
            second = run(handback("forge:staff-engineer", "I still think yes."))
        self.assertEqual(first[0], REFUSED)
        self.assertIn("`DECISION:`", first[1])
        self.assertEqual(second[0], 0)
        self.assertIn("systemMessage", second[2])

    def test_a_conforming_report_passes_and_clears_the_marker(self) -> None:
        decision = "VERDICT: DECIDED\nDECISION: yes\nREAD: a.md\n"
        with isolated():
            self.assertEqual(run(handback("forge:product-owner", "prose"))[0], REFUSED)
            self.assertEqual(run(handback("forge:product-owner", decision)), (0, "", ""))
            self.assertEqual(run(handback("forge:product-owner", "prose"))[0], REFUSED)


class GhBodies(unittest.TestCase):
    def test_a_ticket_without_its_fields_is_refused(self) -> None:
        with isolated():
            code, err, _ = run(bash("gh issue create --title t --body 'Just do it.'"))
        self.assertEqual(code, REFUSED)
        self.assertIn("this ticket body", err)
        self.assertIn("`Motif` is missing", err)

    def test_a_conforming_ticket_passes(self) -> None:
        with isolated():
            self.assertEqual(run(bash(f"gh issue create -t t -b '{TICKET}'"))[0], 0)

    def test_a_body_file_is_read(self) -> None:
        with isolated() as project:
            (project / "body.md").write_text("Too short a PR.", encoding="utf-8")
            code, err, _ = run(bash("gh pr create --body-file body.md", cwd=str(project)))
            self.assertEqual(code, REFUSED)
            self.assertIn("`Summary` is missing", err)
            (project / "c.md").write_text("Merged at abc1234.", encoding="utf-8")
            self.assertEqual(run(bash("gh pr comment 5 -F c.md", cwd=str(project)))[0], 0)

    def test_a_heredoc_body_is_read(self) -> None:
        substitution = "gh issue create -t t --body \"$(cat <<'EOF'\nNo motif here.\nEOF\n)\""
        standard_input = f"gh issue edit 3 --body-file - <<'EOF'\n{TICKET}EOF"
        with isolated():
            self.assertEqual(run(bash(substitution))[0], REFUSED)
            self.assertEqual(run(bash(standard_input))[0], 0)

    def test_a_comment_that_opens_with_a_verdict_follows_the_verdict_template(self) -> None:
        body = "```text\n" + VERDICT_ACCEPT_WITH_BLOCKER + "```"
        with isolated():
            code, err, _ = run(bash(f"gh pr comment 7 --body '{body}'"))
        self.assertEqual(code, REFUSED)
        self.assertIn("this verdict body", err)

    def test_a_long_comment_or_review_is_refused(self) -> None:
        long = " ".join(["word"] * 40)
        body = "\n\n".join([long] * 5)
        with isolated():
            self.assertEqual(run(bash(f"gh pr review 7 --comment -b '{body}'"))[0], REFUSED)
            self.assertEqual(run(bash(f"gh issue comment 7 --body='{body}'"))[0], REFUSED)

    def test_gh_api_body_fields_are_checked(self) -> None:
        long = "\n\n".join([" ".join(["word"] * 40)] * 5)
        with isolated() as project:
            self.assertEqual(
                run(bash(f"gh api repos/o/r/issues/3/comments -f body='{long}'"))[0], REFUSED
            )
            (project / "t.md").write_text("No motif.", encoding="utf-8")
            command = "gh api repos/o/r/issues -f title=x -F body=@t.md"
            self.assertEqual(run(bash(command, cwd=str(project)))[0], REFUSED)
            self.assertEqual(run(bash("gh api repos/o/r/pulls/3/reviews -f body=fine"))[0], 0)

    def test_what_the_guard_cannot_read_or_does_not_cover_passes(self) -> None:
        with isolated():
            for command in [
                'gh issue create --title t --body "$BODY"',
                "gh pr create --body-file missing.md",
                "gh pr review 3 --approve",
                "gh pr edit 3 --add-label x",
                "gh pr merge 3 --body 'x'",
                "gh api repos/o/r/labels -f name=x",
                "git commit -m 'no gh'",
                "echo gh",
            ]:
                with self.subTest(command=command):
                    self.assertEqual(run(bash(command)), (0, "", ""))


class Stop(unittest.TestCase):
    def test_a_reply_out_of_its_template_is_refused(self) -> None:
        event = {"hook_event_name": "Stop", "stop_hook_active": False,
                 "last_assistant_message": "I did it all.\n- a\n- b\n- c\n"}
        with isolated():
            code, err, _ = run(event)
        self.assertEqual(code, REFUSED)
        self.assertIn("your reply to the human", err)
        self.assertIn("go in a table", err)

    def test_a_conforming_reply_passes(self) -> None:
        event = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": REPLY}
        with isolated():
            self.assertEqual(run(event), (0, "", ""))

    def test_stop_hook_active_bounds_the_refusals(self) -> None:
        event = {"hook_event_name": "Stop", "stop_hook_active": True, "last_assistant_message": "x"}
        with isolated():
            code, _, out = run(event)
            self.assertTrue((state_dir() / "journal.jsonl").is_file())
        self.assertEqual(code, 0)
        self.assertIn("the session kept a non-conforming session-reply", out)

    def test_the_transcript_is_read_when_the_field_is_absent(self) -> None:
        with isolated() as project:
            transcript = project / "session.jsonl"
            lines = [
                {"type": "user", "message": {"content": "go"}},
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "prose"}]}},
            ]
            transcript.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
            event: dict[str, object] = {"hook_event_name": "Stop", "transcript_path": str(transcript)}
            self.assertEqual(run(event)[0], REFUSED)

    def test_an_event_it_cannot_read_passes(self) -> None:
        with isolated():
            self.assertEqual(outcome("not json").code, 0)
            self.assertEqual(outcome("[1]").code, 0)
            self.assertEqual(run({"hook_event_name": "Stop"}), (0, "", ""))


def guard_output_hooks() -> dict[str, list[dict[str, object]]]:
    hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    found: dict[str, list[dict[str, object]]] = {}
    for event, groups in hooks["hooks"].items():
        for group in groups:
            for hook in group["hooks"]:
                if "guard_output.py" in hook["command"]:
                    found.setdefault(event, []).append({**hook, "matcher": group.get("matcher")})
    return found


class HooksJson(unittest.TestCase):
    def test_the_guard_is_declared_on_its_three_events(self) -> None:
        found = guard_output_hooks()
        self.assertEqual(sorted(found), ["PreToolUse", "Stop", "SubagentStop"])
        matcher = str(found["PreToolUse"][0]["matcher"]).split("|")
        self.assertIn("Bash", matcher)
        self.assertIn("SubagentHandback", matcher)
        self.assertIsNone(found["SubagentStop"][0]["matcher"])

    @unittest.skipUnless(
        shutil.which("bash") and sys.platform != "win32",
        "the command of hooks.json is run by the POSIX shell of Linux and macOS; under Windows"
        " Claude Code runs it in Git Bash, which this suite has not tried",
    )
    def test_only_the_refusal_code_blocks(self) -> None:
        command = str(guard_output_hooks()["Stop"][0]["command"])
        for script, expected in (("exit 3", 2), ("exit 0", 0), ("exit 1", 0), ("exit 2", 0)):
            with self.subTest(script=script), tempfile.TemporaryDirectory() as folder:
                fake = Path(folder) / "uv"
                fake.write_text(f"#!/bin/sh\necho reason >&2\n{script}\n", encoding="utf-8")
                fake.chmod(0o755)
                done = subprocess.run(  # noqa: S603 - the shell is found by shutil.which
                    [str(shutil.which("bash")), "-c", command],
                    env={"PATH": folder, "CLAUDE_PLUGIN_ROOT": str(support.PLUGIN)},
                    input="{}",
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30,
                )
                self.assertEqual(done.returncode, expected)


if __name__ == "__main__":
    unittest.main()
