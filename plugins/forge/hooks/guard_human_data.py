"""PreToolUse hook on `ArtifactData`: an agent never writes into the human's collections.

An agent can write into the database of a published page, so a click on that page proves nothing
unless a hook keeps the agent out of the collections where only the human writes. The key
`human-collections` of `docs/agents/usine-gardes.md` names them, one line `<page> | <collection>`
each, as `origin/main` holds the file: a PR that removes a line does not open the collection before
it is merged.

The real tool names the artifact by its `url` (`claude.ai/artifact/<id>` or
`claude.ai/code/artifact/<uuid>`), never by a title, so `<page>` is the URL of the artifact and two
URLs are the same page when they hold the same id. A `collection` is a path of slashes whose segments
alternate collection and document (`boards/b1/columns`): a listed collection closes what is under it,
told by whole segments (`humancol2` is not under `humancol`).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from usine import CONFIG_PATH, GUARD_PATH, ConfigUnreadable, load_at, project_root, split_value
from utf8_stdio import use_utf8

KEY = "human-collections"
GUARD = "guard_human_data"


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _artifact(reference: str) -> str | None:
    """The id an artifact URL names, lower-cased; None when the text is not the URL of an artifact.

    Scheme, query, fragment and trailing slashes do not matter, nor does the `code/` form: the id is
    the segment after `artifact`. Two URLs with the same id are taken for one page, the cautious side.
    """
    path = reference.strip().split("#", 1)[0].split("?", 1)[0]
    segments = [segment for segment in path.replace("://", "/").split("/") if segment]
    if "artifact" not in segments[:-1]:
        return None
    return segments[segments.index("artifact") + 1].lower()


def _segments(path: str) -> list[str]:
    return [segment for segment in path.split("/") if segment]


def _under(collection: str | None, listed: str) -> bool:
    """Whether a write on `collection` reaches `listed`: the collection or something under it.

    A collection the call does not name counts as under it: the guard cannot tell it apart.
    """
    if collection is None:
        return True
    wanted = _segments(listed)
    return _segments(collection)[: len(wanted)] == wanted


def key_lines(root: Path) -> tuple[list[str], str | None]:
    """The values of the key as `origin/main` holds it, and why they cannot be told (None when they can).

    `usine.load_at` reads both files on that ref, never the working tree, which an agent can edit.
    A ref or a file the repository cannot give leaves the key untold, unless the project has neither
    file on disk: it then holds no key.
    """
    try:
        return load_at(root, "origin/main").config.get(KEY, []), None
    except ConfigUnreadable as error:
        if not any((root / name).exists() for name in (GUARD_PATH, CONFIG_PATH)):
            return [], None
        return [], f"{error}, so the key `{KEY}` cannot be told"


def refusal(event: object, lines: Sequence[str]) -> str | None:
    """Why the call is refused, None when it passes: `lines` are the values of the key."""
    call = event.get("tool_input") if isinstance(event, Mapping) else None
    if not lines or not isinstance(call, Mapping):
        return None
    url = _text(call.get("url"))
    artifact = _artifact(url) if url else None
    collection = _text(call.get("collection"))
    for line in lines:
        pieces = split_value(line, 2)
        if pieces is None:
            continue
        page, listed = pieces
        if artifact in (None, _artifact(page)) and _under(collection, listed):
            return (
                f"Blocked by the forge plugin ({GUARD}): {page} | {listed} is a collection that"
                " a row comes into only from the human, from their page: an agent does not write it"
            )
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        event = None
    lines, _why = key_lines(project_root(event if isinstance(event, dict) else None))
    reason = refusal(event, lines)
    if reason is None:
        return 0
    sys.stderr.write(reason + ".\n")
    return 2


if __name__ == "__main__":
    use_utf8()
    raise SystemExit(main())
