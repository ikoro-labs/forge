"""SessionStart hook: tell a session, as it starts, which other sessions act on its repository.

One session acts on a repository at a time (ikoro-labs/forge#4). The rule is point 5 of step 0
of the feature-build skill; this hook only observes. It runs the detection of
`handoff_header.py sessions`, the same function on the same registry, with the same exclusions:
the calling session (this hook's ancestors, among them the Claude Code process, and CLAUDE_PID),
and the `auteur` of a handoff of the project whose `successeur` is this session (the event's
`session_id`). When another live session is found, it adds an `additionalContext` that names
each one and sends the session to the rule, without writing the rule a second time.

It says nothing when no other session lives, nor for a subagent: Claude Code puts `agent_id` in a
hook's event only when the hook fires within a subagent, never on the main thread, even in a
`claude --agent` session. It runs on every source (startup, resume, clear, compact, fork): after a
compaction, the earlier notice is summarized away.

The hook never blocks: an event it cannot read, or any failure, exits 0 and says nothing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
HEADER = HOOKS / "handoff_header.py"
SKILL = HOOKS.parent / "skills" / "feature-build" / "SKILL.md"
PYTHON = "uv run --no-project --quiet python"
# The title of point 5 of step 0 of feature-build, as the skill writes it.
RULE = "Une seule session par projet."


def notice_text(found: list[str]) -> str:
    listed = "\n".join(f"- {line}" for line in found)
    return (
        "Other live Claude Code sessions act on this repository, found at the start of this session by "
        f"`handoff_header.py sessions` (`<pid> <kind> <name> <status> <cwd>`; `unreadable` counts as live):\n"
        f"{listed}\n"
        f"Before acting on this repository, follow the rule \"{RULE}\", point 5 of step 0 of {SKILL}: read it "
        f'and apply it as written, starting with `{PYTHON} "{HEADER}" sessions .` run from the repository, '
        "since this list may have changed since the session started. A subagent ignores this notice."
    )


def notice(event: dict) -> str | None:
    """The context for this session, or None for a subagent or when no other session lives."""
    if event.get("agent_id"):
        return None
    # Imported here, so that a broken sibling costs only the notice.
    import handoff_header
    from usine import project_root

    session = str(event.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    found = handoff_header.other_sessions(project_root(event), handoff_header.calling_session(), session)
    return notice_text(found) if found else None


def main(stdin) -> int:
    try:
        event = json.load(stdin)
        if not isinstance(event, dict) or not isinstance(event.get("cwd", ""), str):
            return 0
        message = notice(event)
        if message is not None:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": message}}))
    except Exception:  # noqa: BLE001 - an observing hook never blocks the session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin))
