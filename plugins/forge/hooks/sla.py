"""The severity classes and the delay commitments (SLA): the `sla` key of `docs/agents/usine.md`.

A ticket carries one severity label: `sev1`, `sev2` or `sev3`. A line of the key is

    <severity> | <taken in charge> | <fix merged> | <fix published>

each delay being a number followed by `h` (hours) or `j` (days), counted from the opening of the
ticket. The key has no default: an absent key is "sans objet" and no deadline is guessed. Read by
`scripts/factory_slo.py` (`sla`, `queue`, `report`). Standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from usine import split_value

KEY = "sla"
CLASSES = ("sev1", "sev2", "sev3")
STAGES = ("prise en charge", "correctif fusionné", "correctif publié")
DELAY = re.compile(r"^(\d+)\s*([hj])$")


@dataclass(frozen=True)
class Rule:
    severity: str
    take: timedelta
    merge: timedelta
    publish: timedelta


def parse_delay(text: str) -> timedelta | None:
    """`4 h` or `3 j` as a delay; None when it is neither or is not above zero."""
    match = DELAY.match(text.strip())
    if match is None or int(match.group(1)) == 0:
        return None
    count = int(match.group(1))
    return timedelta(hours=count) if match.group(2) == "h" else timedelta(days=count)


def parse(values: list[str]) -> tuple[dict[str, Rule], list[str]]:
    """The readable rules of the key by severity, and one message for each line that is not."""
    rules: dict[str, Rule] = {}
    errors: list[str] = []
    for value in values:
        parts = split_value(value, 4)
        if parts is None:
            errors.append(f"`{value}` : attendu `<gravité> | <prise en charge> | <correctif fusionné> | <correctif publié>`")
            continue
        severity, *texts = parts
        if severity not in CLASSES:
            errors.append(f"`{value}` : gravité inconnue `{severity}` (attendu : {', '.join(CLASSES)})")
            continue
        if severity in rules:
            errors.append(f"`{value}` : gravité `{severity}` répétée")
            continue
        delays = [parse_delay(text) for text in texts]
        bad = [text for text, delay in zip(texts, delays) if delay is None]
        if bad:
            errors.append(f"`{value}` : délai illisible `{bad[0]}` (attendu un nombre au-dessus de 0 suivi de `h` ou `j`, comme `4 h` ou `3 j`)")
            continue
        take, merge, publish = (delay for delay in delays if delay is not None)
        rules[severity] = Rule(severity, take, merge, publish)
    return rules, errors


def severity_of(labels: set[str]) -> str | None:
    """The highest class among the labels of a ticket, None when it has none."""
    return next((name for name in CLASSES if name in labels), None)


def deadlines(rule: Rule, opened: datetime) -> dict[str, datetime]:
    """The deadline of each stage: the opening of the ticket plus its delay."""
    return {STAGES[0]: opened + rule.take, STAGES[1]: opened + rule.merge, STAGES[2]: opened + rule.publish}


@dataclass(frozen=True)
class Ticket:
    number: int
    labels: set[str]
    opened: datetime


def take_deadline(ticket: Ticket, rules: dict[str, Rule]) -> datetime | None:
    """When the ticket must be taken in charge; None without a severity or without a line for it."""
    severity = severity_of(ticket.labels)
    rule = rules.get(severity) if severity else None
    return ticket.opened + rule.take if rule else None


def order(tickets: list[Ticket], rules: dict[str, Rule]) -> list[Ticket]:
    """The tickets by severity, then by nearest deadline to take in charge, then in the order given.

    A ticket without a severity comes after `sev3`, one without a deadline after those that have one
    of the same class. The sort is stable: the order given (the sub-issues') settles the rest.
    """
    def key(ticket: Ticket) -> tuple[int, bool, datetime]:
        severity = severity_of(ticket.labels)
        rank = CLASSES.index(severity) if severity else len(CLASSES)
        deadline = take_deadline(ticket, rules)
        return rank, deadline is None, deadline or datetime.max.replace(tzinfo=ticket.opened.tzinfo)

    return sorted(tickets, key=key)


MET = "tenue"
LATE = "dépassée"
RUNNING = "en cours"
NOT_APPLICABLE = "sans objet"


@dataclass(frozen=True)
class Stage:
    stage: str
    deadline: datetime
    reached: datetime | None
    state: str
    reason: str | None = None


def assess(
    rule: Rule, opened: datetime, reached: dict[str, datetime | None], now: datetime,
    closed_at: datetime | None = None, unavailable: dict[str, str] | None = None,
) -> list[Stage]:
    """Each stage of a ticket against its deadline.

    `tenue`: reached on or before the deadline. `dépassée`: reached after it, or not reached and `now`
    is past it. `en cours`: not reached, deadline ahead. `sans objet`, with its reason: the data cannot
    say (`unavailable`), or the ticket was closed (`closed_at`) before the deadline of a stage it never
    reached, so the stage was never due. A stage still due at closing is measured like an open ticket's,
    and so is the publication of a ticket closed by its fix, since the fix closes it before the release.
    """
    unavailable = unavailable or {}
    results = []
    for stage, deadline in deadlines(rule, opened).items():
        at = reached.get(stage)
        if stage in unavailable:
            results.append(Stage(stage, deadline, None, NOT_APPLICABLE, unavailable[stage]))
        elif at is not None:
            results.append(Stage(stage, deadline, at, MET if at <= deadline else LATE))
        elif closed_at is not None and closed_at <= deadline and not (
            stage == STAGES[2] and reached.get(STAGES[1]) is not None
        ):
            results.append(Stage(stage, deadline, None, NOT_APPLICABLE, "ticket fermé avant l'échéance de cette étape"))
        else:
            results.append(Stage(stage, deadline, None, LATE if now > deadline else RUNNING))
    return results


def breaches(stages: list[Stage]) -> list[Stage]:
    return [stage for stage in stages if stage.state == LATE]
