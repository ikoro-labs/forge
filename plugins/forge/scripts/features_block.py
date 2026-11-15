"""The "Features" block of the session's reply: what `report_mail.py --features` prints, and its check.

One module holds both sides, so that the script that writes the block and the guard that reads it
agree on its shape. The block is the field `Features` of `templates/session-reply.md`:

    Features:

    | Feature | Closed / total | Open PRs | Blocked | Ready |
    |---|---|---|---|---|
    | F-0001 <title> | 33 % (1 / 3) | #77 | #13 | #12 |

    In parallel: free slots 1; tickets #12 (F-0001); or features F-0001.

or, when there is no table, a single line: `Features: not applicable (key `<key>` absent).` or
`Features: no open feature.`. The last line of the table says what can start in parallel, or
`In parallel: no proposal, <why>.`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

HEADER_CELLS = ("Feature", "Closed / total", "Open PRs", "Blocked", "Ready")
PARALLEL = "In parallel:"
NONE = "none"
UNREAD = "-"
ABSENT_KEYS = ("report-repo", "feature-dir")
_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
_SINGLE_LINES = (
    re.compile(r"^not applicable \(key `(?:" + "|".join(ABSENT_KEYS) + r")` absent\)\.$"),
    re.compile(r"^no open feature\.$"),
)


def not_applicable(key: str) -> str:
    """The single line printed when the key `key` is absent."""
    return f"Features: not applicable (key `{key}` absent).\n"


def _numbers(numbers: list[int]) -> str:
    return ", ".join(f"#{n}" for n in numbers) or NONE


def _parallel(state: Mapping[str, Any]) -> str:
    if state["why"]:
        return f"{PARALLEL} no proposal, {state['why']}."
    if not state["proposal"]:
        return f"{PARALLEL} no proposal, no ready ticket."
    tickets = ", ".join(f"#{n} ({feature})" for feature, n in state["proposal"])
    return (
        f"{PARALLEL} free slots {state['free']}; tickets {tickets};"
        f" or features {', '.join(state['parallel'])}."
    )


def render(state: Mapping[str, Any]) -> str:
    """The block for the `features_state` of `report_mail.py`: the table, then the parallel line."""
    if state["absent"]:
        return not_applicable(state["absent"])
    if state["note"]:
        return "Features: no open feature.\n"
    out = ["Features:", "", "| " + " | ".join(HEADER_CELLS) + " |", "|" + "---|" * len(HEADER_CELLS)]
    for entry in state["features"]:
        if entry["error"]:
            cells = [entry["label"], entry["error"], UNREAD, UNREAD, UNREAD]
        else:
            cells = [
                entry["label"], entry["percent"], _numbers(entry["prs"]),
                _numbers(entry["blocked"]), _numbers(entry["ready"]),
            ]
        out.append("| " + " | ".join(cells) + " |")
    out += ["", _parallel(state)]
    return "\n".join(out) + "\n"


def _cells(line: str) -> list[str]:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return []
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", stripped[1:-1])]


def end(lines: list[str], start: int) -> int:
    """Where the block that opens at `lines[start]` stops (exclusive): the first line that is neither
    blank, nor a table row, nor the parallel line."""
    index = start + 1
    while index < len(lines):
        line = lines[index].strip()
        if line and not line.startswith("|") and not line.startswith(PARALLEL):
            break
        index += 1
    return index


def deviations(value: str, body: list[str]) -> list[str]:
    """What departs from the block, given the text after `Features:` on its first line and the lines
    under it. A table needs its header row, its separator, a row per feature and the parallel line."""
    if value:
        if any(line.strip() for line in body) or not any(p.match(value) for p in _SINGLE_LINES):
            return [_refusal()]
        return []
    rows = [line for line in body if line.strip()]
    if len(rows) < 4:
        return [_refusal()]
    header, separator, *table, last = rows
    expected = [cell.lower() for cell in HEADER_CELLS]
    shaped = (
        [cell.lower() for cell in _cells(header)] == expected
        and len(_cells(separator)) == len(HEADER_CELLS)
        and all(_SEPARATOR_CELL.match(cell) for cell in _cells(separator))
        and all(len(_cells(row)) == len(HEADER_CELLS) for row in table)
        and last.startswith(PARALLEL)
        and len(last) > len(PARALLEL)
    )
    return [] if shaped else [_refusal()]


def _refusal() -> str:
    return (
        "the field `Features` is neither the table of `scripts/report_mail.py --features` (header row"
        f" `| {' | '.join(HEADER_CELLS)} |`, its separator, one row per feature, then a line `{PARALLEL}`)"
        " nor one of its single lines (`Features: not applicable (key `...` absent).` or"
        " `Features: no open feature.`): run the command and copy its output as printed"
    )
