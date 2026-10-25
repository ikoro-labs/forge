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
