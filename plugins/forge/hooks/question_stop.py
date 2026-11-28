"""Stop hook: a session that stops on its own question has it decided at `question-default-delay`.

A long session that labels a ticket or a pull request `ready-for-human` or `needs-info` and ends its turn
would stop and wait, and nothing wakes it (`question_delay.py` is read by `forge:feature-build` alone).
This hook reads the transcript for the waiting labels the session set since the human's last message,
keeps the session alive until the question is due, then blocks the stop (`decision: block`) with the
instruction: ask the decider (`forge:staff-engineer` or `forge:product-owner`), write its block to a file,
run `question_delay.py route ... --apply`. The delay, the due date and what a question is come from
`question_delay.py` itself, imported, not copied.

The wait happens in this process: the question is read again every `POLL` seconds until it is due, so the
decider is asked at most `POLL` seconds after the due date, or until `HOOK_TIMEOUT` less `MARGIN`. The
`timeout` of the hook's entry in `hooks.json` is `HOOK_TIMEOUT`. A question due further away lets the
stop pass; the dispatcher's tick takes it there. The hook never loops and never traps a session:

- a question that carries a `Rappel (question-default-delay)`, a subagent, a session the key
  `ignored-session` names behind a live dispatcher lock (its agent of the dispatcher is served by the
  tick), and the ninth stop in a row (`STOP_CAP`, Claude Code's own cap) all pass;
- the hook fails open: the key `question-default-delay` absent, a delay or a transcript that cannot be
  read, `gh` failing, an error of its own, and the stop passes. It exits 0 whatever happens.

Only the Bash commands of the session are read (`gh issue edit` and `gh pr edit` with `--add-label`, and
`gh api .../issues/<n>/labels` with a `labels[]=` field); a label set by another tool is not seen.
"""

from __future__ import annotations

import json
import shlex
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import agent_lock  # noqa: E402  the dispatcher's locks
import factory_slo  # noqa: E402  its `gh` runner
import handoff_header  # noqa: E402  the registry of live sessions and the key `ignored-session`
import question_delay  # noqa: E402  the delay, the due date and the questions, shared with `route`
from guard_completion import human_text  # noqa: E402  what a person typed, in a transcript
from usine import project_root  # noqa: E402
from utf8_stdio import use_utf8  # noqa: E402

HOOK_TIMEOUT = 780  # seconds; the `timeout` of the entry in `hooks.json`
MARGIN = 60  # seconds kept free before the hook's timeout
POLL = 30  # seconds between two readings of the question
STOP_CAP = 8  # blocks in a row Claude Code admits before it lets the session stop
FEEDBACK = "Stop hook feedback:"  # the first line of a Stop hook block, as the transcript keeps it
TRANSCRIPT_LIMIT = 16 * 1024 * 1024
CAP_MESSAGE = (
    f"question_stop: the cap of {STOP_CAP} Stop hook blocks in a row is reached; the stop passes with a question"
    " still unanswered. The dispatcher's tick, or the next session, takes it."
)
SCRIPT = Path(question_delay.__file__).resolve()
OPERATORS = {";", "&&", "||", "|", "&", "(", ")"}

Runner = question_delay.Runner
Answer = dict[str, str]  # `decision` and `reason`, or `systemMessage`


def transcript_tail(path: Path) -> Iterator[dict]:
    """The transcript's entries, oldest first, from its last `TRANSCRIPT_LIMIT` bytes."""
    with path.open("rb") as stream:
        size = stream.seek(0, 2)
        start = max(0, size - TRANSCRIPT_LIMIT)
        stream.seek(start)
        data = stream.read()
    lines = data.split(b"\n")
    for raw in lines[1:] if start > 0 else lines:
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if isinstance(entry, dict):
            yield entry


def passage(path: Path) -> list[dict]:
    """The entries since the human's last message (all of them when none is in the window)."""
    entries = list(transcript_tail(path))
    for index in range(len(entries) - 1, -1, -1):
        if human_text(entries[index]) is not None:
            return entries[index + 1 :]
    return entries


def tool_uses(entry: Mapping[str, object]) -> list[dict]:
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if entry.get("type") != "assistant" or not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict) and block.get("type") == "tool_use"]


def segments(command: str) -> list[list[str]]:
    """The words of each simple command of a shell line; [] when the line cannot be split."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return []
    found: list[list[str]] = [[]]
    for word in words:
        if word in OPERATORS or set(word) <= set(";&|()"):
            found.append([])
        else:
            found[-1].append(word)
    return [words for words in found if words]


def item_number(word: str) -> int | None:
    tail = word.rstrip("/").rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else None


def labels_added(command: str) -> dict[int, set[str]]:
    """The labels a shell line adds, by ticket or pull request number."""
    found: dict[int, set[str]] = {}
    for words in segments(command):
        if words[:1] != ["gh"]:
            continue
        number: int | None = None
        labels: set[str] = set()
        if words[1:2] in (["issue"], ["pr"]) and words[2:3] == ["edit"]:
            number = next((n for w in words[3:] if (n := item_number(w)) is not None), None)
            for position, word in enumerate(words):
                if word == "--add-label" and position + 1 < len(words):
                    labels.update(part.strip() for part in words[position + 1].split(","))
                elif word.startswith("--add-label="):
                    labels.update(part.strip() for part in word.split("=", 1)[1].split(","))
        elif words[1:2] == ["api"]:
            for word in words[2:]:
                parts = word.rstrip("/").split("/")
                if len(parts) >= 3 and parts[-1] == "labels" and parts[-3] == "issues" and parts[-2].isdigit():
                    number = int(parts[-2])
            labels.update(
                word.split("=", 1)[1].strip() for word in words[2:] if word.startswith("labels[]=")
            )
        if number is not None and labels:
            found.setdefault(number, set()).update(labels)
    return found


def feedback_text(entry: Mapping[str, object]) -> bool:
    """Whether `entry` is what Claude Code writes after a Stop hook blocked the stop."""
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return entry.get("type") == "user" and isinstance(content, str) and content.startswith(FEEDBACK)


def blocks_in_a_row(entries: list[dict]) -> int:
    """The Stop hook blocks since the session's last tool call, which resets Claude Code's cap."""
    count = 0
    for entry in reversed(entries):
        if tool_uses(entry):
            break
        count += feedback_text(entry)
    return count


def asked(entries: list[dict]) -> set[int]:
    """The tickets and pull requests the session labeled with a label a human answers, in these entries."""
    numbers: set[int] = set()
    for entry in entries:
        for block in tool_uses(entry):
            command = (block.get("input") or {}).get("command") if block.get("name") == "Bash" else None
            if not isinstance(command, str):
                continue
            for number, labels in labels_added(command).items():
                if labels & set(question_delay.ANSWERABLE):
                    numbers.add(number)
    return numbers


def open_questions(project: Path, run: Runner, numbers: set[int]) -> list[question_delay.Question]:
    """The questions among `numbers` that still wait for a human, and that no reminder has taken yet."""
    return [
        question
        for question in question_delay.questions(project, run, only=numbers)
        if set(question.labels) & set(question_delay.ANSWERABLE) and not question.reminder
    ]


def instruction(question: question_delay.Question, delay_text: str, project: Path) -> str:
    command = (
        f'uv run --no-project --quiet python "{SCRIPT.as_posix()}" route "{project.as_posix()}"'
        f" <verdict-file> --item {question.number} --agent <staff-engineer|product-owner> --apply"
    )
    return (
        f"Blocked by the forge plugin (question_stop): the {question.kind} #{question.number}, labeled"
        f" {', '.join(f'`{label}`' for label in question.labels)} in this turn, has waited past"
        f" `question-default-delay` ({delay_text}). Do not stop on it. Ask its decider: `forge:staff-engineer`"
        " for a technical question, `forge:product-owner` for a product question (the decision matrix says which),"
        " and write the block it returns to a file. Then run"
        f" `{command}`, the agent being the one that answered. It posts the default decision, or a reminder when"
        " the matrix keeps the gesture for the human, and the stop that follows passes."
    )


def dispatcher_agent(event: Mapping[str, object], project: Path) -> bool:
    """Whether the stopping session is an agent of the dispatcher: the registry names it, the key
    `ignored-session` lists that name, and its pid holds a live lock (the form of design Q1: the name alone
    proves nothing, a session of the human holds no lock)."""
    session = event.get("session_id")
    target = handoff_header.main_checkout(project)
    patterns = handoff_header.ignored_names(target)
    if not isinstance(session, str) or not session or not patterns:
        return False
    for entry in sorted((Path.home() / ".claude" / "sessions").glob("*.json")):
        try:
            fields = json.loads(entry.read_text(encoding="utf-8"))
            pid = int(fields["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if fields.get("sessionId") == session and handoff_header.name_ignored(fields.get("name"), patterns):
            return pid in {lock.pid for lock in agent_lock.held(Path(target))}
    return False


def decide(
    event: Mapping[str, object],
    run: Runner | None = None,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> Answer | None:
    """The hook's answer for a Stop event: a block, or None to let the session stop."""
    run = run or factory_slo.run_command
    now = now or (lambda: datetime.now(timezone.utc))
    sleep = sleep or time.sleep
    path = event.get("transcript_path")
    if not isinstance(path, str) or not path or event.get("agent_id"):
        return None
    project = project_root(event)
    if dispatcher_agent(event, project):
        return None
    loaded = question_delay.load_delay(project)
    if loaded is None:
        return None
    delay, delay_text = loaded
    entries = passage(Path(path).expanduser())
    numbers = asked(entries)
    if not numbers:
        return None
    capped = blocks_in_a_row(entries) >= STOP_CAP
    deadline = now() + timedelta(seconds=HOOK_TIMEOUT - MARGIN)
    while True:
        dated = [
            (moment, question)
            for question in open_questions(project, run, numbers)
            if (moment := question.due_at(delay)) is not None
        ]
        if not dated:
            return None
        current = now()
        due = [question for moment, question in dated if current >= moment]
        soonest = min(moment for moment, _ in dated)
        if not due and soonest > deadline:
            return None
        if capped:
            return {"systemMessage": CAP_MESSAGE}
        if due:
            return {"decision": "block", "reason": instruction(due[0], delay_text, project)}
        sleep(max(0.0, min(POLL, (soonest - current).total_seconds())))


def main() -> int:
    try:
        event = json.load(sys.stdin)
        answer = decide(event) if isinstance(event, dict) else None
    except Exception:  # noqa: BLE001 - a Stop hook that fails lets the session stop, whatever the failure
        return 0
    if answer is not None:
        sys.stdout.write(json.dumps(answer, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    use_utf8()
    raise SystemExit(main())
