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
RULES = (
    ("only from the human", "human-collection"),
    ("is not `<page> | <collection>`", "unreadable-key-line"),
)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _targets(call: Mapping[str, object]) -> list[tuple[str | None, str | None]]:
    """The `(page, collection)` each write of the call aims at: one, or one per operation of a batch."""
    page = _text(call.get("page"))
    if call.get("action") != "batch":
        return [(page, _text(call.get("collection")))]
    operations = call.get("writes")
    if not isinstance(operations, list):
        return []
    return [
        (page, _text(operation.get("collection")))
        for operation in operations
        if isinstance(operation, Mapping)
    ]


def refusal(event: object, lines: Sequence[str]) -> str | None:
    """Why the call is refused, None when it passes: `lines` are the values of the key."""
    if not lines or not isinstance(event, Mapping):
        return None
    call = event.get("tool_input")
    if not isinstance(call, Mapping) or call.get("action") not in WRITES | {"batch"}:
        return None
    targets = _targets(call)
    for line in lines:
        pieces = split_value(line, 2)
        if pieces is None:
            return (
                f"Blocked by the forge plugin ({GUARD}): the line `{line}` of the key `{KEY}` is not"
                " `<page> | <collection>`, so no write into a page database is cleared until it is fixed"
            )
        if any(target == (pieces[0], pieces[1]) for target in targets):
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
