"""PreToolUse hook on `ArtifactData`: an agent never writes into the human's collections.

An agent can write into the database of a published page, so a click on that page proves nothing
unless a hook keeps the agent out of the collections where only the human writes. The key
`human-collections` of `docs/agents/usine-gardes.md` names them, one line `<page> | <collection>`
each, as `origin/main` holds the file: a PR that removes a line does not open the collection before
it is merged.

The guard refuses a write (`set`, `update`, `str_replace`, `delete`, and a `batch` of which one
operation is aimed at a listed collection, the whole call then) and lets a read (`get`, `list`,
`query`, `profiles`) and every other page or collection pass. It fails closed: a line of the key it
cannot read, a call it cannot read, a key it cannot tell, all refuse the write. Without the key it
refuses nothing: the step is "sans objet (clé `human-collections` absente)". `hooks.json` turns a
crash, a missing script and a timeout into a refusal. The message never holds what is written.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from refusal_journal import record
from usine import CONFIG_PATH, GUARD_PATH, on_main, parse, project_root, split_value
from utf8_stdio import use_utf8

KEY = "human-collections"
GUARD = "guard_human_data"
READS = frozenset({"get", "list", "query", "profiles"})

# The refusals journal: the name of each rule, found by a fixed phrase of the reason.
RULES = (
    ("only from the human", "human-collection"),
    ("is not `<page> | <collection>`", "unreadable-key-line"),
    ("could not read the tool call", "unreadable-event"),
    ("cannot be told", "unreadable-key"),
)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _action(event: object) -> str | None:
    call = event.get("tool_input") if isinstance(event, Mapping) else None
    action = call.get("action") if isinstance(call, Mapping) else None
    return action if isinstance(action, str) and action else None


def _targets(call: Mapping[str, object]) -> list[tuple[str | None, str | None]]:
    """The `(page, collection)` each write of the call aims at, None for a part it does not name.

    One target, or one per operation of a batch; an operation the guard cannot read is `(None, None)`.
    """
    page = _text(call.get("page"))
    if call.get("action") != "batch":
        return [(page, _text(call.get("collection")))]
    operations = call.get("writes")
    if not isinstance(operations, list):
        return [(page, None)]
    return [
        (page, _text(operation.get("collection")) if isinstance(operation, Mapping) else None)
        for operation in operations
    ]


def _aims(target: tuple[str | None, str | None], page: str, collection: str) -> bool:
    """Whether a write may reach `page | collection`: a part the call does not name counts as a match."""
    return target[0] in (None, page) and target[1] in (None, collection)


def key_lines(root: Path) -> tuple[list[str], str | None]:
    """The values of the key as `origin/main` holds them, and why they cannot be told (None when they can).

    The guard file first; while it is absent there, `usine.md` as the same ref holds it. Never the
    working tree, which an agent can edit. A ref or a file the repository cannot give leaves the key
    untold, unless the project has neither file on disk: it then holds no key.
    """
    shown, path = on_main(root, GUARD_PATH), GUARD_PATH
    if shown.text is None and shown.why is None:
        shown, path = on_main(root, CONFIG_PATH), CONFIG_PATH
    if shown.text is not None:
        return parse(shown.text).get(KEY, []), None
    if shown.why is None or not any((root / name).exists() for name in (GUARD_PATH, CONFIG_PATH)):
        return [], None
    return [], f"{path.as_posix()} cannot be read on origin/main ({shown.why}), so the key `{KEY}` cannot be told"


def refusal(event: object, lines: Sequence[str]) -> str | None:
    """Why the call is refused, None when it passes: `lines` are the values of the key.

    Without a line the key is absent and nothing is refused. With one, a call the guard cannot read
    is refused: it cannot tell it from a write into the collection.
    """
    if not lines:
        return None
    action = _action(event)
    call = event.get("tool_input") if isinstance(event, Mapping) else None
    if action is None or not isinstance(call, Mapping):
        return f"Blocked by the forge plugin ({GUARD}): the hook could not read the tool call it was given"
    if action in READS:
        return None
    targets = _targets(call)
    for line in lines:
        pieces = split_value(line, 2)
        if pieces is None:
            return (
                f"Blocked by the forge plugin ({GUARD}): the line `{line}` of the key `{KEY}` is not"
                " `<page> | <collection>`, so no write into a page database is cleared until it is fixed"
            )
        if any(_aims(target, pieces[0], pieces[1]) for target in targets):
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
    lines, why = key_lines(project_root(event if isinstance(event, dict) else None))
    if why is None:
        reason = refusal(event, lines)
    else:
        # A read cannot reach a collection: only a write, or a call that cannot be read, is refused.
        reason = None if _action(event) in READS else f"Blocked by the forge plugin ({GUARD}): {why}"
    if reason is None:
        return 0
    record(GUARD, reason, RULES, event, lambda: "ArtifactData write")
    sys.stderr.write(reason + ".\n")
    return 2


if __name__ == "__main__":
    use_utf8()
    raise SystemExit(main())
