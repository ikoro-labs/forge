"""PreToolUse hook on agent launches: the factory's pause switch.

While `.claude/PAUSED` exists in the project, no agent is launched: an incident (a CI down, a
quota spent) is stopped by one gesture, without killing the session. The file is not versioned;
its text, if any, is the reason, and is shown to whoever tried. A coder already running finishes
its call; `/forge:feature-build` reads the switch again before each launch and stops.
"""

from __future__ import annotations

import json
import sys

from usine import project_root

SWITCH = (".claude", "PAUSED")


def paused_reason(text: str | None) -> str | None:
    """Why launches are refused, or None when the factory is not paused."""
    if text is None:
        return None
    return text.strip() or "no reason given"


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        event = {}
    switch = project_root(event if isinstance(event, dict) else None).joinpath(*SWITCH)
    try:
        text: str | None = switch.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        text = None
    except OSError:
        text = "the switch exists but cannot be read"
    reason = paused_reason(text)
    if reason is None:
        return 0
    sys.stderr.write(
        f"Blocked by the forge plugin: the factory is paused (.claude/PAUSED: {reason})."
        " Remove the file to resume.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
