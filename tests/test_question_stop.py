"""F-0003 A34 to A39: a session that stops on its own question has it decided at `question-default-delay`
(`hooks/question_stop.py`, a `Stop` hook; ikoro-labs/forge#404, design section 7, ticket 5).

Two seams. The hook runs as a process on a `Stop` event, with a fake `gh` first on the `PATH`, under a
temporary HOME and without the CLAUDE_ or GIT_ variables of the session running the tests. The wait, which
the hook spends in `sleep`, runs in this process through `decide(event, run, now, sleep)` with a clock the
test moves: a real minute never passes. `gh` is never the real one, the transcript is one the test writes.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import support
from question_delay import main as route_main
from question_stop import POLL, decide
from test_question_delay import NOW, RESERVED, STAFF, Gh, issue, labeled

HOOK = support.PLUGIN / "hooks" / "question_stop.py"
DELAY_KEY = "- `question-default-delay` : `10 min`\n"
LABEL_COMMAND = "gh issue edit 12 --add-label ready-for-human"

FAKE_GH = """#!{python}
import json, os, re, sys

fixture = json.load(open(os.environ["FAKE_GH"], encoding="utf-8"))
args = [a for a in sys.argv[1:] if a != "--paginate"]
assert args[0] == "api", args
path = args[1]
if os.environ.get("FAKE_GH_FAILS"):
    sys.exit("gh: boom")
if match := re.fullmatch(r"repos/\\{{owner\\}}/\\{{repo\\}}/issues\\?(.*)", path):
    label = re.search(r"labels=([^&]+)", match.group(1)).group(1)
    print(json.dumps([i for i in fixture["items"] if label in {{x["name"] for x in i["labels"]}}]))
elif match := re.fullmatch(r"repos/\\{{owner\\}}/\\{{repo\\}}/issues/(\\d+)/(events|comments).*", path):
    print(json.dumps(fixture[match.group(2)].get(match.group(1), [])))
else:
    sys.exit("unexpected gh call: " + path)
"""


def human(text: str = "go") -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


def tool_call(command: str, tool: str = "Bash") -> dict:
    block = {"type": "tool_use", "id": "toolu_1", "name": tool, "input": {"command": command}}
    return {"type": "assistant", "message": {"role": "assistant", "content": [block]}}


def tool_result() -> dict:
    block = {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}
    return {"type": "user", "message": {"role": "user", "content": [block]}}


def said(text: str) -> dict:
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def feedback(hook: str = "question_stop") -> dict:
    """What Claude Code writes in the transcript each time a Stop hook blocked the stop."""
    reason = f"Blocked by the forge plugin ({hook}): the question #12 waits."
    return {
        "type": "user",
        "isMeta": True,
        "message": {"role": "user", "content": f"Stop hook feedback:\n[command hook 2]: {reason}"},
    }


class Session:
    """A project, a HOME and a transcript, the session's variables kept out of the environment."""

    def __init__(self, test: unittest.TestCase, usine: str | None = DELAY_KEY) -> None:
        folder = tempfile.TemporaryDirectory()
        test.addCleanup(folder.cleanup)
        self.root = Path(os.path.realpath(folder.name))
        self.project = self.root / "demo"
        (self.project / ".git").mkdir(parents=True)
        (self.project / "docs" / "agents").mkdir(parents=True)
        if usine is not None:
            (self.project / "docs" / "agents" / "usine.md").write_text("# Usine\n" + usine, encoding="utf-8")
        self.home = self.root / "home"
        self.registry = self.home / ".claude" / "sessions"
        self.registry.mkdir(parents=True)
        self.transcript = self.root / "transcript.jsonl"
        self.env = {
            key: value for key, value in os.environ.items() if not key.startswith(("CLAUDE_", "GIT_"))
        }
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home))
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
        patcher = mock.patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        test.addCleanup(patcher.stop)

    def write(self, *entries: dict) -> None:
        self.transcript.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")

    def event(self, **fields: object) -> dict:
        event = {
            "hook_event_name": "Stop",
            "session_id": "0801df0e-3c3b",
            "cwd": str(self.project),
            "transcript_path": str(self.transcript),
            "stop_hook_active": False,
        }
        event.update(fields)
        return event

    def process(self, gh_fixture: dict, event: dict | None = None, fails: bool = False) -> subprocess.CompletedProcess:
        """The hook as a process, a fake `gh` on the PATH answering from `gh_fixture`."""
        bin_dir = self.root / "bin"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "gh").write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
        (bin_dir / "gh").chmod(0o755)
        fixture = self.root / "gh.json"
        fixture.write_text(json.dumps(gh_fixture), encoding="utf-8")
        env = {**self.env, "PATH": os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]), "FAKE_GH": str(fixture)}
        if fails:
            env["FAKE_GH_FAILS"] = "1"
        return subprocess.run(  # noqa: S603 - the interpreter running this suite, a fixed script
            [sys.executable, str(HOOK)],
            input=json.dumps(event or self.event()),
            capture_output=True, text=True, encoding="utf-8", env=env, cwd=self.project, timeout=60, check=False,
        )


class Clock:
    """One moving instant: `sleep` moves it, and the durations slept are kept."""

    def __init__(self, start: datetime = NOW) -> None:
        self.at = start
        self.slept: list[float] = []

    def now(self) -> datetime:
        return self.at

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.at += timedelta(seconds=seconds)


def real_hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def due_fixture(minutes: float, labels: tuple[str, ...] = ("ready-for-human",), comments: list[dict] | None = None) -> dict:
    """Issue 12 carrying `labels` since `minutes` ago, as the fake `gh` of a process answers it."""
    when = real_hours_ago(minutes / 60)
    events = [{"event": "labeled", "label": {"name": name}, "created_at": when} for name in labels]
    return {
        "items": [issue(12, list(labels))],
        "events": {"12": events},
        "comments": {"12": comments or []},
    }


class DueQuestion(unittest.TestCase):
    def test_a_question_past_the_delay_blocks_the_stop_with_the_decider_then_route(self) -> None:
        """F-0003 A34: the session posted `ready-for-human` in this passage, the delay has run: the hook
        blocks the stop and says to ask the decider, then to run `route --apply`."""
        session = Session(self)
        session.write(human(), tool_call(LABEL_COMMAND), tool_result(), said("I wait for an answer."))
        result = session.process(due_fixture(minutes=11))
        self.assertEqual(result.returncode, 0, result.stderr)
        answer = json.loads(result.stdout)
        self.assertEqual(answer["decision"], "block")
        reason = answer["reason"]
        self.assertIn("(question_stop)", reason)
        self.assertIn("#12", reason)
        self.assertIn("forge:staff-engineer", reason)
        self.assertIn("forge:product-owner", reason)
        self.assertRegex(reason, r"question_delay\.py\" route .* --item 12 .*--apply")

    def test_the_session_is_kept_until_the_due_date_then_blocked_within_a_minute(self) -> None:
        """F-0003 A34: labeled 4 minutes ago with a delay of 10, the hook waits, reading the question again
        at most every `POLL` seconds, and blocks at most a minute after the due date."""
        session = Session(self)
        session.write(human(), tool_call(LABEL_COMMAND), tool_result())
        gh = Gh({12: issue(12, ["ready-for-human"])}, {12: [labeled("ready-for-human", 4 / 60)]})
        clock = Clock()
        answer = decide(session.event(), run=gh, now=clock.now, sleep=clock.sleep)
        self.assertEqual(answer and answer["decision"], "block")
        due = NOW + timedelta(minutes=6)
        self.assertGreaterEqual(clock.at, due)
        self.assertLessEqual(clock.at, due + timedelta(minutes=1))
        self.assertTrue(clock.slept and max(clock.slept) <= POLL, clock.slept)

    def test_a_question_due_beyond_the_hook_timeout_lets_the_stop_pass(self) -> None:
        """F-0003 A34 (design Q6): a due date further than the hook can wait is the dispatcher's tick, not
        this hook's: the stop passes at once, without sleeping."""
        session = Session(self, usine="- `question-default-delay` : `24 h`\n")
        session.write(human(), tool_call(LABEL_COMMAND), tool_result())
        gh = Gh({12: issue(12, ["ready-for-human"])}, {12: [labeled("ready-for-human", 1 / 60)]})
        clock = Clock()
        self.assertIsNone(decide(session.event(), run=gh, now=clock.now, sleep=clock.sleep))
        self.assertEqual(clock.slept, [])

    def test_the_human_answering_during_the_wait_lets_the_stop_pass(self) -> None:
        """F-0003 A34: the label is gone at the next reading, nothing is left to decide."""
        session = Session(self)
        session.write(human(), tool_call(LABEL_COMMAND), tool_result())
        gh = Gh({12: issue(12, ["ready-for-human"])}, {12: [labeled("ready-for-human", 4 / 60)]})
        clock = Clock()

        def sleep(seconds: float) -> None:
            clock.sleep(seconds)
            gh.items[12] = issue(12, [])

        self.assertIsNone(decide(session.event(), run=gh, now=clock.now, sleep=sleep))
        self.assertEqual(len(clock.slept), 1)

    def test_a_label_set_before_the_humans_last_message_is_not_this_passage(self) -> None:
        """F-0003 A34: only the question the session posed in this passage is its own."""
        session = Session(self)
        session.write(human("first"), tool_call(LABEL_COMMAND), tool_result(), human("second"), said("done"))
        self.assertEqual(session.process(due_fixture(minutes=11)).stdout, "")

    def test_a_session_that_set_no_waiting_label_is_not_held_for_the_questions_of_others(self) -> None:
        """F-0003 A34: a question of the project that the session did not pose is not its own."""
        session = Session(self)
        session.write(human(), tool_call("gh issue edit 12 --add-label bug"), tool_result())
        self.assertEqual(session.process(due_fixture(minutes=11)).stdout, "")

    def test_the_labels_a_session_sets_by_gh_edit_or_gh_api_are_read(self) -> None:
        """F-0003 A34: `gh issue edit`, `gh pr edit`, `gh api .../labels`, behind `&&`, with `=` or a list."""
        from question_stop import labels_added

        self.assertEqual(labels_added("gh issue edit 12 --add-label ready-for-human"), {12: {"ready-for-human"}})
        self.assertEqual(labels_added("cd x && gh pr edit 7 --add-label=needs-info,bug"), {7: {"needs-info", "bug"}})
        self.assertEqual(
            labels_added("gh api repos/o/r/issues/9/labels -f 'labels[]=needs-info'"), {9: {"needs-info"}}
        )
        self.assertEqual(labels_added("gh issue comment 12 --body 'ready-for-human'"), {})
        self.assertEqual(labels_added("gh issue edit 12 --remove-label ready-for-human"), {})
        self.assertEqual(labels_added("echo 'unterminated"), {})


class ReservedGesture(unittest.TestCase):
    def test_a_reserved_verdict_posts_the_reminder_and_the_next_stop_passes(self) -> None:
        """F-0003 A35: the hook blocks a due question, `route --apply` on a `RESERVED` verdict posts the
        reminder, and the stop that follows passes: a reserved gesture is never taken by default."""
        session = Session(self)
        session.write(human(), tool_call(LABEL_COMMAND), tool_result())
        gh = Gh({12: issue(12, ["ready-for-human"])}, {12: [labeled("ready-for-human", 11 / 60)]})
        clock = Clock()
        first = decide(session.event(), run=gh, now=clock.now, sleep=clock.sleep)
        self.assertEqual(first and first["decision"], "block")
        verdict = session.root / "verdict.txt"
        verdict.write_text(RESERVED, encoding="utf-8")
        code = route_main(
            ["route", str(session.project), str(verdict), "--item", "12", "--agent", "staff-engineer", "--apply"],
            run=gh, now=NOW,
        )  # fmt: skip
        self.assertEqual(code, 0)
        self.assertTrue(gh.bodies()[0].startswith("Rappel (question-default-delay)"))
        # What GitHub holds after the reminder: its comment, and the label that flags the human.
        gh.comments[12] = [{"body": gh.bodies()[0], "created_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}]
        gh.items[12] = issue(12, ["ready-for-human", "needs-your-attention"])
        self.assertIsNone(decide(session.event(), run=gh, now=clock.now, sleep=clock.sleep))
        self.assertEqual(clock.slept, [])

    def test_a_default_decision_removes_the_label_and_the_next_stop_passes(self) -> None:
        """F-0003 A34: a `DECIDED` reversible verdict posts the default and clears `ready-for-human`."""
        session = Session(self)
        session.write(human(), tool_call(LABEL_COMMAND), tool_result())
        gh = Gh({12: issue(12, ["ready-for-human"])}, {12: [labeled("ready-for-human", 11 / 60)]})
        verdict = session.root / "verdict.txt"
        verdict.write_text(STAFF, encoding="utf-8")
        code = route_main(
            ["route", str(session.project), str(verdict), "--item", "12", "--agent", "staff-engineer", "--apply"],
            run=gh, now=NOW,
        )  # fmt: skip
        self.assertEqual(code, 0)
        self.assertEqual(gh.removed(), ["ready-for-human"])
        gh.items[12] = issue(12, [])
        clock = Clock()
        self.assertIsNone(decide(session.event(), run=gh, now=clock.now, sleep=clock.sleep))


class ExcludedQuestion(unittest.TestCase):
    def test_a_question_that_already_carries_a_reminder_lets_the_stop_pass(self) -> None:
        """F-0003 A36: a `Rappel (question-default-delay)` on the question excludes it."""
        session = Session(self)
        session.write(human(), tool_call(LABEL_COMMAND), tool_result())
        reminder = {
            "body": "Rappel (question-default-delay) : cette question attend une réponse.",
            "created_at": real_hours_ago(1 / 60),
        }
        fixture = due_fixture(minutes=11, comments=[reminder])
        result = session.process(fixture)
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    def test_a_default_decision_comment_does_not_exclude_a_question_that_was_asked_again(self) -> None:
        """F-0003 A36: only the reminder excludes; a default decision restarts the delay, nothing more."""
        session = Session(self)
        session.write(human(), tool_call(LABEL_COMMAND), tool_result())
        decision = {
            "body": "Décision (staff-engineer, P1) par défaut (question-default-delay) : x",
            "created_at": real_hours_ago(11 / 60),
        }
        fixture = due_fixture(minutes=30, comments=[decision])
        answer = json.loads(session.process(fixture).stdout)
        self.assertEqual(answer["decision"], "block")


class StopCap(unittest.TestCase):
    def due_gh(self) -> Gh:
        return Gh({12: issue(12, ["ready-for-human"])}, {12: [labeled("ready-for-human", 11 / 60)]})

    def stop_after(self, session: Session, *between: dict, blocks: int) -> Gh:
        session.write(human(), tool_call(LABEL_COMMAND), tool_result(), *between, *([said("..."), feedback()] * blocks))
        return self.due_gh()

    def test_the_ninth_stop_in_a_row_passes_and_says_the_cap_of_8_is_reached(self) -> None:
        """F-0003 A37: after 8 blocks in a row the stop passes, and the output says the cap of 8 is reached."""
        session = Session(self)
        gh = self.stop_after(session, blocks=8)
        clock = Clock()
        answer = decide(session.event(), run=gh, now=clock.now, sleep=clock.sleep)
        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertNotIn("decision", answer)
        self.assertIn("8", answer["systemMessage"])
        self.assertIn("cap", answer["systemMessage"])
        self.assertEqual(clock.slept, [])

    def test_the_cap_reached_is_said_by_the_hook_process_on_its_standard_output(self) -> None:
        """F-0003 A37: the output of the process is one JSON document with the message, exit code 0."""
        session = Session(self)
        self.stop_after(session, blocks=8)
        result = session.process(due_fixture(minutes=11))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("8", json.loads(result.stdout)["systemMessage"])

    def test_seven_blocks_in_a_row_still_block_the_eighth_time(self) -> None:
        """F-0003 A37: the cap is 8 blocks, the eighth stop is still held."""
        session = Session(self)
        gh = self.stop_after(session, blocks=7)
        answer = decide(session.event(), run=gh, now=Clock().now, sleep=Clock().sleep)
        self.assertEqual(answer and answer["decision"], "block")

    def test_a_tool_call_resets_the_count_as_it_does_for_claude_code(self) -> None:
        """F-0003 A37: Claude Code resets its cap at each tool call; so does the count of the hook."""
        session = Session(self)
        gh = self.stop_after(session, blocks=0)
        entries = [human(), tool_call(LABEL_COMMAND), tool_result(), *([said("..."), feedback()] * 8)]
        entries += [tool_call("ls"), tool_result(), said("one more"), feedback()]
        session.write(*entries)
        answer = decide(session.event(), run=gh, now=Clock().now, sleep=Clock().sleep)
        self.assertEqual(answer and answer["decision"], "block")

    def test_a_stop_blocked_by_another_hook_counts_toward_the_cap(self) -> None:
        """F-0003 A37: Claude Code's cap counts every Stop hook block of the turn, not this hook's alone."""
        session = Session(self)
        entries = [human(), tool_call(LABEL_COMMAND), tool_result(), *([said("..."), feedback("guard_output")] * 8)]
        session.write(*entries)
        answer = decide(session.event(), run=self.due_gh(), now=Clock().now, sleep=Clock().sleep)
        self.assertIn("systemMessage", answer or {})

    def test_a_question_not_held_by_the_hook_does_not_get_the_cap_message(self) -> None:
        """F-0003 A37: the message is for a stop the hook would have held; a question due far away passes quietly."""
        session = Session(self, usine="- `question-default-delay` : `24 h`\n")
        self.stop_after(session, blocks=8)
        gh = Gh({12: issue(12, ["ready-for-human"])}, {12: [labeled("ready-for-human", 1 / 60)]})
        self.assertIsNone(decide(session.event(), run=gh, now=Clock().now, sleep=Clock().sleep))


if __name__ == "__main__":
    unittest.main()
