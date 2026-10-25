"""Read what the end-to-end review loop leaves behind: its gap tickets, its matrices, its journals.

The helpers of the indicators `factory_slo.py` adds to its report (`review-gaps`, `review-gap-lead-time`,
`matrix-coverage`, `review-regressions`). Nothing here asks a model or the network: a ticket is a dict
`gh issue list --json` returned, a feature is a folder of the key `feature-dir`. The standard library only.

- A **gap ticket** is a ticket of the loop: its body holds a `Couvre : <identifiers>` line and a
  `Feature: F-NNNN` line (what `forge:feature-build` writes when it publishes a gap). Its severity is read
  from a label `gravite:bloquant`, `gravite:majeur` or `gravite:mineur`; without one it is « sans gravité ».
- A **feature** is a folder `<feature-dir>/NNNN-<slug>/`; `F-NNNN` names it by its number. Its matrix is
  `matrice.md`, its journal `revue/boucle.tsv`.
- A **round** (« passage ») is a `TOUR <n>` of the journal.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import matrice  # noqa: E402

FEATURE_KEY = "feature-dir"
SEVERITIES = ("bloquant", "majeur", "mineur")
NO_SEVERITY = "sans gravité"
COVERS = re.compile(r"^\s*Couvre\s*:\s*(.+?)\s*$", re.MULTILINE)
FEATURE = re.compile(r"^\s*Feature\s*:\s*F-(\d+)\s*$", re.MULTILINE)
SEVERITY_LABEL = re.compile(r"^(?:gravite|gravité|severity):(.+)$")


@dataclass(frozen=True)
class GapTicket:
    number: int
    feature: str
    identifiers: tuple[str, ...]
    severity: str
    opened: datetime | None
    closed: datetime | None


@dataclass(frozen=True)
class Feature:
    number: str
    matrice: Path
    journal: Path


def severity_of(labels: set[str]) -> str:
    for label in sorted(labels):
        found = SEVERITY_LABEL.match(label)
        if found and found.group(1) in SEVERITIES:
            return found.group(1)
    return NO_SEVERITY


def gap_ticket(item: dict, opened: datetime | None, closed: datetime | None, labels: set[str]) -> GapTicket | None:
    """The ticket as a gap of the loop, or None when it is not one (no `Couvre :` line, or no `Feature:` line)."""
    body = str(item.get("body") or "")
    covers, feature = COVERS.search(body), FEATURE.search(body)
    if not covers or not feature:
        return None
    identifiers = tuple(i.strip() for i in covers.group(1).split(",") if i.strip())
    if not identifiers:
        return None
    closed = closed if str(item.get("state")).upper() == "CLOSED" else None
    return GapTicket(int(item["number"]), feature.group(1), identifiers, severity_of(labels), opened, closed)


def features(project: Path, directories: list[str]) -> list[Feature]:
    """The features under the folders of the key `feature-dir`, in the order of their numbers."""
    found: list[Feature] = []
    for directory in directories:
        for folder in sorted((project / directory).glob("[0-9]*-*")):
            number = folder.name.split("-", 1)[0]
            if folder.is_dir() and number.isdigit():
                found.append(Feature(number, folder / "matrice.md", folder / "revue" / "boucle.tsv"))
    return found


def rounds(lines: list[str]) -> dict[int, dict[str, str]]:
    """The journal as {round: {identifier: state}}."""
    out: dict[int, dict[str, str]] = {}
    for text in lines:
        fields = text.split("\t")
        if len(fields) == 4 and fields[0] == "TOUR" and fields[1].isdigit():
            out.setdefault(int(fields[1]), {})[fields[2]] = fields[3]
    return out


def severity_by_identifier(tickets: list[GapTicket], feature: str) -> dict[str, str]:
    """The severity of the first ticket (the lowest number) that covers each identifier of a feature."""
    out: dict[str, str] = {}
    for ticket in sorted(tickets, key=lambda t: t.number):
        if ticket.feature.lstrip("0") == feature.lstrip("0"):
            for identifier in ticket.identifiers:
                out.setdefault(identifier, ticket.severity)
    return out


def gaps_by_round(found: list[Feature], tickets: list[GapTicket]) -> dict[str, dict[str, int]]:
    """For each round, the identifiers that are not `tenu`, counted by the severity of the ticket that covers them."""
    out: dict[str, dict[str, int]] = {}
    for feature in found:
        if not feature.journal.is_file():
            continue
        severity = severity_by_identifier(tickets, feature.number)
        lines = feature.journal.read_text(encoding="utf-8").splitlines()
        for number, states in sorted(rounds(lines).items()):
            for identifier, state in states.items():
                if state != "tenu":
                    counts = out.setdefault(str(number), {})
                    kind = severity.get(identifier, NO_SEVERITY)
                    counts[kind] = counts.get(kind, 0) + 1
    return {number: {k: counts[k] for k in (*SEVERITIES, NO_SEVERITY) if k in counts} for number, counts in out.items()}


def coverage_of(found: list[Feature]) -> tuple[int, int, list[str]]:
    """Rows held (`tenu` or `écarté`), total rows, and the matrices that cannot be read, over the features."""
    held = total = 0
    unreadable: list[str] = []
    for feature in found:
        if not feature.matrice.is_file():
            continue
        try:
            rows = matrice.parse(feature.matrice.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            unreadable.append(feature.number)
            continue
        covered, count = matrice.coverage(rows)
        held, total = held + covered, total + count
    return held, total, unreadable
