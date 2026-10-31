"""Hold the tokens spent for each ticket against the `ticket-budget` key of `docs/agents/usine.md`.

    python ticket_budget.py ajouter <registre> --ticket '#n' --role <rôle> --notification <fichier>
    python ticket_budget.py controle <registre> <projet> --ticket '#n' [--depuis DATE] [--verdict TEXTE]
    python ticket_budget.py passation <registre>
    python ticket_budget.py reprendre <registre> <passation>

The ledger is a text file, one `<ticket>TAB<rôle>TAB<jetons>` line per agent that ended. `ajouter`
reads the tokens in the `subagent_tokens` of the end notification of an agent (the `<usage>` block);
a notification without it is refused, never counted as zero. `controle` adds the main session's
share since `--depuis` (read by `token_audit.py`, the replies without an agent), compares the sum
to the key and prints `BUDGET ok`, `BUDGET depasse` (exit 1, with the sum, the tokens of each role
and the last verdict) or `BUDGET sans objet` when the key is absent: no ceiling, no default. A
value that is not a whole number of tokens, or a key repeated, exits 2. A sum equal to the budget
still launches. `passation` prints the items of the `jetons_agents` key of a handoff
(`- #n rôle jetons`), and `reprendre` loads them back into a ledger, replacing its content, so a
relay resumes the sums instead of starting from zero; a bare number there (a handoff from before
the budget) carries nothing. The standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import handoff_header  # noqa: E402  the reader of the handoff's front matter
import token_audit  # noqa: E402  the main session's share
import usine  # noqa: E402

KEY = "ticket-budget"
ABSENT = f"sans objet (clé `{KEY}` absente)"
USAGE = re.compile(r"subagent_tokens[\"']?\s*[:=]\s*(\d+)")
ITEM = re.compile(r"^(#\d+)\s+(.+?)\s+(\d+)$")
TICKET = re.compile(r"^#\d+$")


class BudgetError(ValueError):
    """A key, a notification or a ledger the budget cannot trust."""


def tokens_of(notification: str) -> int:
    found = USAGE.findall(notification)
    if not found:
        raise BudgetError("la notification ne porte pas de `subagent_tokens` : rien n'est compté")
    return int(found[-1])


def read_ledger(path: Path) -> list[tuple[str, str, int]]:
    if not path.exists():
        return []
    entries = []
    for text in path.read_text(encoding="utf-8").splitlines():
        if text.strip():
            ticket, role, amount = text.split("\t")
            entries.append((ticket, role, int(amount)))
    return entries


def write_ledger(path: Path, entries: list[tuple[str, str, int]]) -> None:
    path.write_text("".join(f"{t}\t{r}\t{n}\n" for t, r, n in entries), encoding="utf-8")


def budget_of(project: Path) -> int | None:
    values = usine.load(project).get(KEY)
    if not values:
        return None
    if len(values) != 1 or not values[0].isdigit():
        raise BudgetError(f"la clé `{KEY}` est un nombre entier de jetons, sur une seule ligne")
    return int(values[0])


def per_role(entries: list[tuple[str, str, int]], ticket: str) -> dict[str, int]:
    roles: dict[str, int] = {}
    for mine, role, amount in entries:
        if mine == ticket:
            roles[role] = roles.get(role, 0) + amount
    return roles


def main_share(project: Path, since: datetime) -> int:
    calls, _ = token_audit.read_calls(token_audit.config_dir(), project, since=since)
    return sum(sum(call.tokens) for call in calls if call.role == token_audit.MAIN_SESSION)


def cmd_ajouter(args: argparse.Namespace) -> int:
    if not TICKET.match(args.ticket):
        raise BudgetError(f"`{args.ticket}` n'est pas un ticket (`#n`)")
    amount = tokens_of(args.notification.read_text(encoding="utf-8"))
    entries = read_ledger(args.registre)
    entries.append((args.ticket, args.role.replace("\t", " "), amount))
    write_ledger(args.registre, entries)
    print(f"{args.ticket} {args.role} {amount}")
    return 0


def cmd_controle(args: argparse.Namespace) -> int:
    budget = budget_of(args.projet)
    roles = per_role(read_ledger(args.registre), args.ticket)
    if args.depuis is not None:
        roles[token_audit.MAIN_SESSION] = main_share(args.projet, args.depuis)
    total = sum(roles.values())
    if budget is None:
        print(f"BUDGET {ABSENT} : aucun plafond, somme={total}")
        return 0
    state = "depasse" if total > budget else "ok"
    print(f"BUDGET {state} {args.ticket} somme={total} budget={budget}")
    for role, amount in sorted(roles.items()):
        print(f"DETAIL {role} {amount}")
    if args.depuis is None:
        print("DETAIL session principale non comptée (--depuis absent)")
    if state == "depasse":
        print(f"VERDICT {args.verdict or 'aucun'}")
    return 1 if state == "depasse" else 0


def cmd_passation(args: argparse.Namespace) -> int:
    totals: dict[tuple[str, str], int] = {}
    for ticket, role, amount in read_ledger(args.registre):
        totals[(ticket, role)] = totals.get((ticket, role), 0) + amount
    for (ticket, role), amount in sorted(totals.items(), key=lambda item: (int(item[0][0][1:]), item[0][1])):
        print(f"  - {ticket} {role} {amount}")
    if not totals:
        print("  - 0")
    return 0


def cmd_reprendre(args: argparse.Namespace) -> int:
    values = handoff_header.check(args.passation)
    entries = []
    for item in values["jetons_agents"]:
        if match := ITEM.match(item):
            entries.append((match.group(1), match.group(2), int(match.group(3))))
        elif not item.isdigit():
            raise BudgetError(f"`jetons_agents` : `{item}` n'est ni `#n rôle jetons` ni un nombre")
    write_ledger(args.registre, entries)
    print(f"{len(entries)} ligne(s) reprise(s)")
    return 0


def _date(text: str) -> datetime:
    try:
        return token_audit.parse_time(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"`{text}` n'est pas une date ISO") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ticket_budget.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="commande", required=True)
    add = sub.add_parser("ajouter")
    add.add_argument("registre", type=Path)
    add.add_argument("--ticket", required=True)
    add.add_argument("--role", required=True)
    add.add_argument("--notification", type=Path, required=True)
    add.set_defaults(run=cmd_ajouter)
    check = sub.add_parser("controle")
    check.add_argument("registre", type=Path)
    check.add_argument("projet", type=Path)
    check.add_argument("--ticket", required=True)
    check.add_argument("--depuis", type=_date)
    check.add_argument("--verdict")
    check.set_defaults(run=cmd_controle)
    out = sub.add_parser("passation")
    out.add_argument("registre", type=Path)
    out.set_defaults(run=cmd_passation)
    back = sub.add_parser("reprendre")
    back.add_argument("registre", type=Path)
    back.add_argument("passation", type=Path)
    back.set_defaults(run=cmd_reprendre)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (BudgetError, handoff_header.HeaderError, OSError, ValueError) as error:
        print(f"ticket_budget.py : {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
