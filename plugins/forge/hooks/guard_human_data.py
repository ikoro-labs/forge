"""PreToolUse hook on `ArtifactData`: an agent never writes into the human's collections.

An agent can write into the database of a published page, so a click on that page proves nothing
unless a hook keeps the agent out of the collections where only the human writes. The key
`human-collections` of `docs/agents/usine-gardes.md` names them, one line `<page> | <collection>`
each, as `origin/main` holds the file: a PR that removes a line does not open the collection before
it is merged.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from refusal_journal import record
from usine import GUARD_PATH, on_main, parse, split_value
from utf8_stdio import use_utf8

KEY = "human-collections"
GUARD = "guard_human_data"
WRITES = frozenset({"set", "update", "str_replace", "delete"})

# The refusals journal: the name of each rule, found by a fixed phrase of the reason.
RULES = (("only from the human", "human-collection"),)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def refusal(event: object, lines: Sequence[str]) -> str | None:
    """Why the call is refused, None when it passes: `lines` are the values of the key."""
    if not lines or not isinstance(event, Mapping):
        return None
    call = event.get("tool_input")
    if not isinstance(call, Mapping) or call.get("action") not in WRITES:
        return None
    page, collection = _text(call.get("page")), _text(call.get("collection"))
    for line in lines:
        pieces = split_value(line, 2)
        if pieces and (page, collection) == (pieces[0], pieces[1]):
            return (
                f"Blocked by the forge plugin ({GUARD}): {pieces[0]} | {pieces[1]} is a collection that"
                " a row comes into only from the human, from their page: an agent does not write it"
            )
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        event = None
    root = Path(str(event.get("cwd") or ".")) if isinstance(event, dict) else Path(".")
    shown = on_main(root, GUARD_PATH)
    lines = parse(shown.text or "").get(KEY, [])
    reason = refusal(event, lines)
    if reason is None:
        return 0
    record(GUARD, reason, RULES, event, lambda: "ArtifactData write")
    sys.stderr.write(reason + ".\n")
    return 2


if __name__ == "__main__":
    use_utf8()
    raise SystemExit(main())
