"""Stop hook: a question on completion is answered with the completion table.

When the human's last message asks how far the work is (completion, avancement, progress,
pourcentage, or a `%` beside a feature, a project or an `F-NNNN`), the session's reply since that
message must hold the Markdown table `scripts/completion.py` prints: a header row with every column
of `HEADERS`, plus the project's own column when the key `completion-column` names one, and its
separator row. Otherwise the stop is blocked once (`decision: block`) with the command to run;
the reply that follows passes whatever it holds (`stop_hook_active`), so the hook never loops.

The human's message is the transcript's last `user` entry Claude Code marks as typed by a person
(`origin.kind: human`); without that mark, a `user` entry that is no tool result, no meta or
compaction entry and does not open with a tag (`<task-notification>`, `<bash-input>`...).
Subagents' entries (`isSidechain`) are left out. The transcript is read from its end, at most
`TRANSCRIPT_LIMIT` bytes; a question further back, an unreadable transcript or event passes.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

from usine import load, project_root, split_value

HEADERS = (
    "Feature",
    "Suivi",
    "Fermés (completed) / budget",
    "%",
    "Ouverts",
    "Hors compte (not_planned)",
    "Reste (numéros ouverts)",
    "Relevé (date UTC)",
)
COLUMN_KEY = "completion-column"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "completion.py"
TRANSCRIPT_LIMIT = 16 * 1024 * 1024
CHUNK = 256 * 1024

ASKS = re.compile(
    r"\b(?:compl[ée]tion|avancement|progress\w*|pourcentage|percentage)\b", re.IGNORECASE
)
NAMES_WORK = re.compile(r"\b(?:features?|projets?|projects?|F-\d{4})\b", re.IGNORECASE)
FEATURE = re.compile(r"\bF-\d{4}\b")
REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL)
SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")


def extra_column(config: Mapping[str, list[str]]) -> tuple[str, str] | None:
    """The project's own column, `<header> | <command>`, or None without the key.

    The command holds `{feature}`, replaced by the feature's `F-NNNN`. A value that is not two
    parts raises ValueError.
    """
    values = config.get(COLUMN_KEY)
    if not values:
        return None
    parts = split_value(values[-1], 2)
    if parts is None:
        raise ValueError(f"the key `{COLUMN_KEY}` is `<header> | <command>`, got `{values[-1]}`")
    return parts[0], parts[1]


def headers_of(config: Mapping[str, list[str]]) -> tuple[str, ...]:
    try:
        column = extra_column(config)
    except ValueError:
        column = None
    return HEADERS if column is None else (*HEADERS, column[0])


def asks_completion(text: str) -> bool:
    return bool(ASKS.search(text)) or ("%" in text and bool(NAMES_WORK.search(text)))


def _cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def has_table(text: str, headers: tuple[str, ...]) -> bool:
    """Whether `text` holds a Markdown table whose header row names every one of `headers`."""
    lines = text.splitlines()
    for here, line in enumerate(lines[:-1]):
        cells = _cells(line)
        below = _cells(lines[here + 1])
        if cells is None or below is None or not all(SEPARATOR_CELL.match(cell) for cell in below):
            continue
        if all(header in cells for header in headers):
            return True
    return False


def _lines_backwards(path: Path) -> Iterator[bytes]:
    """The transcript's lines from the last one, within `TRANSCRIPT_LIMIT` bytes."""
    with path.open("rb") as stream:
        stream.seek(0, 2)
        position = stream.tell()
        tail = b""
        read = 0
        while position > 0 and read < TRANSCRIPT_LIMIT:
            size = min(CHUNK, position)
            position -= size
            stream.seek(position)
            block = stream.read(size) + tail
            read += size
            lines = block.split(b"\n")
            tail = lines[0]
            yield from reversed(lines[1:])
        if position == 0:
            yield tail


def _content_text(entry: Mapping[str, object]) -> str | None:
    """The text of an entry's message; None when it carries a tool result."""
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    if any(isinstance(block, dict) and block.get("type") == "tool_result" for block in content):
        return None
    return "\n".join(
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def human_text(entry: Mapping[str, object]) -> str | None:
    """What a person typed, when `entry` is a message of the human; else None."""
    if entry.get("type") != "user" or entry.get("isSidechain") is True:
        return None
    if entry.get("isMeta") is True or entry.get("isCompactSummary") is True:
        return None
    origin = entry.get("origin")
    if isinstance(origin, dict) and origin.get("kind") != "human":
        return None
    text = _content_text(entry)
    if text is None:
        return None
    text = REMINDER.sub("", text).strip()
    if not text or (origin is None and text.startswith("<")):
        return None
    return text


def last_turn(path: Path) -> tuple[str, list[str]] | None:
    """The human's last message and the session's texts since, oldest first; None if not found."""
    replies: list[str] = []
    for raw in _lines_backwards(path):
        if b'"user"' not in raw and b'"assistant"' not in raw:
            continue
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "assistant" and entry.get("isSidechain") is not True:
            text = _content_text(entry)
            if text:
                replies.append(text)
            continue
        question = human_text(entry)
        if question is not None:
            return question, replies[::-1]
    return None


def decision(event: Mapping[str, object]) -> dict[str, str] | None:
    """The Stop hook's answer: a block with its reason, or None to let the session stop."""
    if event.get("stop_hook_active") is True:
        return None
    path = event.get("transcript_path")
    if not isinstance(path, str) or not path:
        return None
    try:
        turn = last_turn(Path(path).expanduser())
    except OSError:
        return None
    if turn is None or not asks_completion(turn[0]):
        return None
    question, replies = turn
    last = event.get("last_assistant_message")
    if isinstance(last, str):
        replies.append(last)
    headers = headers_of(load(project_root(event)))
    if any(has_table(reply, headers) for reply in replies):
        return None
    features = " ".join(dict.fromkeys(FEATURE.findall(question)))
    command = f'uv run --no-project --quiet python "{SCRIPT.as_posix()}"' + (
        f" {features}" if features else ""
    )
    reason = (
        "Blocked by the forge plugin (guard_completion): the human asked for the completion. Run"
        f" `{command}` from the project root and paste its Markdown table as printed"
        f" (columns: {' | '.join(headers)}), without a total row."
    )
    return {"decision": "block", "reason": reason}


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(event, dict):
        return 0
    answer = decision(event)
    if answer is not None:
        sys.stdout.write(json.dumps(answer, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
