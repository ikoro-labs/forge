"""The validation cases of a ticket: read from its body, agreed before the PR opens, then frozen.

A ticket of a feature holds, in its body, one line per case and one `AGREED:` line:

    A1.1 | <input> | <expected result>
    AGREED: test-author, coder, qc-conf, securite

`pr_problems` says what keeps `gh pr create` from opening a PR for such a ticket: no case, no
`AGREED:` line, or a role missing from it (`test-author`, `coder`, `qc-conf`, and each reviewer of
the `validation-reviewer` key whose paths the PR's diff touches). `verdict_problems` says what
keeps a verdict from being posted: a `[BLOCKER]` whose rule field cites neither a case of the
frozen list, nor a rule `F-n` of `socle.md` or `L-n` of the local rules, nor `regression <test>`;
a case or a rule that does not exist; a security rule cited without its proof (`proof:` and a test
`<path>::<name>` or a command in backticks); a ticket body edited after the PR opened, unless the
editor is a login of the `validation-owner` key.

A ticket created before the date of the `validation-cases` key (its adoption) needs no case, and
its criterion `A<n>` counts as the case `A<n>.1`. Without the key, nothing here is read. The
standard library only.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from usine import split_value

KEY = "validation-cases"
REVIEWER_KEY = "validation-reviewer"
OWNER_KEY = "validation-owner"
SECURITY_KEY = "security-rules"
GRID_KEY = "review-grid"
ROLES = ("test-author", "coder", "qc-conf")
SOCLE = Path(__file__).resolve().parent.parent / "socle.md"

CASE_ID = re.compile(r"^\s*(?:[-*]\s+)?(A[1-9]\d*\.[1-9]\d*)\s*\|(.*)$")
AGREED = re.compile(r"^\s*AGREED:(.*)$", re.MULTILINE)
CRITERION = re.compile(r"^\s*[-*]\s+A([1-9]\d*)\s*:", re.MULTILINE)
FEATURE = re.compile(r"^Feature:\s*F-\d+", re.MULTILINE)
TICKET_REF = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs)\b:?\s+#(\d+)", re.IGNORECASE)
BLOCKER = re.compile(r"^\s*-\s*\[BLOCKER\]\s*(.*)$", re.MULTILINE)
CITED_CASE = re.compile(r"\bA([1-9]\d*)(?:\.([1-9]\d*))?\b")
CITED_RULE = re.compile(r"\b([FL]-[1-9]\d*)\b")
REGRESSION = re.compile(r"\bregression\s+\S+")
PROOF = re.compile(r"^proof:\s*(?:\S+::\S+|`[^`]+`)", re.IGNORECASE)
RULE_ROW = re.compile(r"^\|\s*([FL]-[1-9]\d*)\s*\|\s*([\w-]+)\s*\|", re.MULTILINE)


class ConfigError(ValueError):
    """A key of the project's configuration that cannot be read: the guard refuses."""


@dataclass(frozen=True)
class Ticket:
    number: int
    body: str
    created_at: datetime
    last_edited_at: datetime | None = None
    editor: str | None = None


@dataclass(frozen=True)
class PullRequest:
    number: int
    body: str
    created_at: datetime


def adoption(config: Mapping[str, list[str]]) -> date | None:
    """The date of the `validation-cases` key, None when the project has not adopted the cases."""
    values = config.get(KEY)
    if not values:
        return None
    if len(values) > 1:
        raise ConfigError(f"the key `{KEY}` is repeated: one date, `YYYY-MM-DD`")
    try:
        return date.fromisoformat(values[0])
    except ValueError as error:
        raise ConfigError(f"the key `{KEY}` reads `{values[0]}`: it must be a date, `YYYY-MM-DD`") from error


def reviewers(config: Mapping[str, list[str]]) -> list[tuple[str, list[str]]]:
    """Each `validation-reviewer` line: the agent, and the path prefixes of its perimeter."""
    found = []
    for value in config.get(REVIEWER_KEY, []):
        parts = split_value(value, 2)
        prefixes = [prefix.strip() for prefix in parts[1].split(",") if prefix.strip()] if parts else []
        if not parts or not prefixes:
            raise ConfigError(f"the key `{REVIEWER_KEY}` reads `{value}`: it must be `<agent> | <path>, <path>`")
        found.append((parts[0], prefixes))
    return found


def ticket_refs(text: str) -> list[int]:
    """The tickets a PR body closes or refers to, in order, once each."""
    return list(dict.fromkeys(int(number) for number in TICKET_REF.findall(text)))


def cases_of(body: str) -> list[str]:
    """The ids of the case lines of a body, each with an input and an expected result."""
    found = []
    for line in body.splitlines():
        match = CASE_ID.match(line)
        if match and len([part for part in match.group(2).split("|") if part.strip()]) >= 2:
            found.append(match.group(1))
    return found


def agreed_of(body: str) -> list[set[str]]:
    """The roles of each `AGREED:` line of a body."""
    return [{name for name in re.split(r"[,\s]+", line) if name} for line in AGREED.findall(body)]


def is_legacy(ticket: Ticket, since: date) -> bool:
    return ticket.created_at.date() < since


def is_governed(ticket: Ticket, since: date) -> bool:
    """A ticket of a feature created since the adoption: it opens a PR only with agreed cases."""
    return bool(FEATURE.search(ticket.body)) and not is_legacy(ticket, since)


def pr_problems(
    tickets: Iterable[Ticket],
    since: date,
    config: Mapping[str, list[str]],
    changed_files: Callable[[], list[str]],
) -> list[str]:
    """What keeps a PR for these tickets from opening."""
    problems: list[str] = []
    declared = reviewers(config)
    for ticket in tickets:
        if not is_governed(ticket, since):
            continue
        if not cases_of(ticket.body):
            problems.append(
                f"ticket #{ticket.number} holds no validation case `A<n>.<k> | <input> | <expected result>`:"
                " round 0 writes them in its body before the code"
            )
        lines = agreed_of(ticket.body)
        if len(lines) != 1:
            problems.append(f"ticket #{ticket.number} needs one `AGREED:` line, it has {len(lines)}")
            continue
        required = list(ROLES)
        if declared:
            files = changed_files()
            for agent, prefixes in declared:
                if any(path.startswith(prefix) for path in files for prefix in prefixes):
                    required.append(agent)
        missing = [role for role in required if role not in lines[0]]
        if missing:
            problems.append(
                f"the `AGREED:` line of ticket #{ticket.number} lacks {', '.join(missing)}:"
                " each must read the cases once, and may add some, before the PR opens"
            )
    return problems


def rules(root: Path, config: Mapping[str, list[str]], socle: Path = SOCLE) -> dict[str, str]:
    """Each rule id of `socle.md` and of the local rules (key `review-grid`), with its nature."""
    found = {rule: nature for rule, nature in RULE_ROW.findall(socle.read_text(encoding="utf-8")) if rule.startswith("F-")}
    for value in config.get(GRID_KEY, []):
        try:
            text = (root / value).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found.update((rule, nature) for rule, nature in RULE_ROW.findall(text) if rule.startswith("L-"))
    return found


def security_rules(known: Mapping[str, str], config: Mapping[str, list[str]]) -> set[str]:
    """The closed list of security rules: the `security` rows of the socle, plus the key `security-rules`."""
    extra = {rule for value in config.get(SECURITY_KEY, []) for rule in re.split(r"[,\s]+", value) if rule}
    unknown = sorted(extra - set(known))
    if unknown:
        raise ConfigError(f"the key `{SECURITY_KEY}` names {', '.join(unknown)}, which is no rule of the socle")
    return {rule for rule, nature in known.items() if nature == "security"} | extra


def _frozen(ticket: Ticket, pr: PullRequest, owners: list[str]) -> str | None:
    edited = ticket.last_edited_at
    if edited is None or edited <= pr.created_at or (ticket.editor or "") in owners:
        return None
    return (
        f"ticket #{ticket.number} was edited at {edited.isoformat()}, after PR #{pr.number} opened at"
        f" {pr.created_at.isoformat()}: its validation cases are frozen at the opening. Correct the list"
        f" in a next part of the ticket (a new PR `Refs #{ticket.number}`, opened after the edit), or"
        f" have a login of the `{OWNER_KEY}` key make the edit"
    )


def verdict_problems(
    text: str,
    pr: PullRequest,
    tickets: Iterable[Ticket],
    since: date,
    config: Mapping[str, list[str]],
    known: Mapping[str, str],
) -> list[str]:
    """What keeps this verdict from being posted on this PR."""
    problems: list[str] = []
    owners = config.get(OWNER_KEY, [])
    cases: dict[str, int] = {}
    legacy = False
    numbers = []
    for ticket in tickets:
        numbers.append(f"#{ticket.number}")
        if is_legacy(ticket, since):
            legacy = True
            cases.update((f"A{n}.1", ticket.number) for n in CRITERION.findall(ticket.body))
            continue
        own = cases_of(ticket.body)
        cases.update((case, ticket.number) for case in own)
        if is_governed(ticket, since) or own or agreed_of(ticket.body):
            if refusal := _frozen(ticket, pr, owners):
                problems.append(refusal)
    security = security_rules(known, config)
    source = ", ".join(numbers) or "the PR, which cites no ticket"
    for line in BLOCKER.findall(text):
        fields = [field.strip() for field in line.split("|")]
        rule_field = fields[1] if len(fields) > 1 else ""
        quoted = f"`[BLOCKER] {line.strip()[:80]}`"
        cited = False
        for number, index in CITED_CASE.findall(rule_field):
            cited = True
            case = f"A{number}.{index}" if index else f"A{number}.1"
            if not index and not legacy:
                problems.append(f"{quoted} cites `A{number}`: cite the case `A{number}.<k>` of the frozen list")
            elif case not in cases:
                shown = case if index else f"A{number}.1"
                problems.append(f"{quoted} cites `{shown}`, which is not a case of the frozen list of {source}")
        for rule in CITED_RULE.findall(rule_field):
            cited = True
            if rule not in known:
                problems.append(f"{quoted} cites `{rule}`, which is no rule of `socle.md` nor of the local rules")
            elif rule in security and not any(PROOF.match(field) for field in fields[2:]):
                problems.append(
                    f"{quoted} cites the security rule `{rule}` without its proof: add"
                    " `| proof: <path>::<test>` or `| proof: `<command reproduced>``"
                )
        if REGRESSION.search(rule_field):
            cited = True
        if not cited:
            problems.append(
                f"{quoted} cites no validation case `A<n>.<k>`, no rule `F-n` or `L-n` and no"
                " `regression <test>`: it cannot reject. Make it a NOTE, or a `PROPOSAL:` for the next tickets"
            )
    return problems
