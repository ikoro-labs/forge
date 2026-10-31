"""PostToolUse hook: a named command that succeeds hands the agent the end of its output only.

A test suite that passes prints hundreds of lines the agent reads in full and pays for, when only
its summary matters. For a Bash command holding a value of the `trimmed-command` key of
`docs/agents/usine.md`, an output longer than `MAX_LINES` is written in full to a journal under
`~/.claude/hooks/state/trimmed/`, and the agent gets the last `KEEP_LINES` lines of each stream
(where the summary and, for the usual runners, the failures are) and the journal's path. Without
the key, nothing is trimmed.

A command that fails is never trimmed: Claude Code sends `PostToolUseFailure` for it, without its
output, in place of `PostToolUse`. Only the exit code of the whole command counts: a suite that
fails behind a pipe (`| tee log`) or followed by another command (`; echo done`) exits 0 and is
trimmed like one that passes. This hook only observes: whatever goes wrong, it exits 0 and
leaves the output as it was.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import cast

from usine import load, project_root

TRIM_KEY = "trimmed-command"
MAX_LINES = 60
KEEP_LINES = 20
KEEP_JOURNALS = 20
STREAMS = ("stdout", "stderr")


def named(command: str, values: Iterable[str]) -> bool:
    return any(value and value in command for value in values)


def too_long(response: Mapping[str, object]) -> bool:
    if response.get("interrupted"):
        return False
    return sum(len(str(response.get(name) or "").splitlines()) for name in STREAMS) > MAX_LINES


def trimmed_output(response: Mapping[str, object], journal: Path) -> dict[str, object] | None:
    """The tool response with each stream cut to its end, or None when it is short enough."""
    if not too_long(response):
        return None
    trimmed = dict(response)
    for name in STREAMS:
        kept = str(response.get(name) or "").splitlines()
        if len(kept) > KEEP_LINES:
            notice = f"[forge kept the last {KEEP_LINES} of {len(kept)} lines; full output in {journal}]"
            trimmed[name] = "\n".join([notice, *kept[-KEEP_LINES:]]) + "\n"
    return trimmed


def journal_dir() -> Path:
    return Path.home() / ".claude" / "hooks" / "state" / "trimmed"


def write_journal(folder: Path, session: str, command: str, response: Mapping[str, object]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    journal = folder / f"{session or 'session'}-{time.time_ns()}.log"
    parts = [f"$ {command}\n"]
    for name in STREAMS:
        parts += [f"\n== {name} ==\n", str(response.get(name) or "")]
    journal.write_text("".join(parts), encoding="utf-8")
    others = sorted((path for path in folder.glob("*.log") if path != journal), key=written_at)
    for path in others[: max(len(others) - (KEEP_JOURNALS - 1), 0)]:
        path.unlink(missing_ok=True)
    return journal


def written_at(journal: Path) -> int:
    """The instant in the journal's name: file times tie or run backwards across sessions."""
    instant = journal.stem.rsplit("-", 1)[-1]
    return int(instant) if instant.isdigit() else 0


def run(event: Mapping[str, object]) -> dict[str, object] | None:
    tool_input = cast("dict[str, object]", event.get("tool_input") or {})
    command = str(tool_input.get("command") or "")
    response = event.get("tool_response")
    if event.get("tool_name") != "Bash" or not isinstance(response, dict):
        return None
    if not named(command, load(project_root(event)).get(TRIM_KEY, [])):
        return None
    if not too_long(response):
        return None
    journal = write_journal(journal_dir(), str(event.get("session_id") or ""), command, response)
    return trimmed_output(response, journal)


def main() -> int:
    try:
        trimmed = run(json.load(sys.stdin))
    except Exception:  # an observer: a failure keeps the output as it was
        return 0
    if trimmed is not None:
        json.dump({"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": trimmed}},
                  sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
