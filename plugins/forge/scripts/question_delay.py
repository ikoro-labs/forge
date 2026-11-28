"""The questions a human leaves unanswered: which are past `question-default-delay`, and what to do
with the verdict of the decider that was asked.

    python question_delay.py due <project> [--json]
    python question_delay.py route <project> <verdict-file> --item <n> --agent <name> [--apply] [--json]

`due` reads the key `question-default-delay` of `docs/agents/usine.md`, one line: a number above zero
followed by `min`, `h` or `j`. `h` and `j` are read as in the key `sla`; `min` is read here only, so the
key `sla` and the other keys that share its reader keep their two units. A question is an open ticket or pull request that carries
`ready-for-human`, `needs-info` or `needs-your-attention`. It waits since the latest `labeled` event of
one of the waiting labels it still carries, or since the latest default decision or reminder this
script's `route` posted (a comment whose first line says `(question-default-delay)`), whichever is
later. It is due once it has waited the delay, the bound itself included. An item with no label event
to read is reported apart (`NON DATEE`) and is never due: no date is guessed. `forge:feature-build`
passes each due question to `forge:staff-engineer` or `forge:product-owner`.

`route` reads the block that decider wrote (`VERDICT:`, `DECISION:`, `GROUND:`, `MATRIX_CELL:`,
`REVERSIBLE:`, `VETO:`) and plans one of two actions on the item `--item`:

    - `post-default`: the verdict is `DECIDED`, with its cell, its decision and its source, and a
      `REVERSIBLE: yes` line (`--agent staff-engineer` requires the line; `product-owner` writes none,
      and a line it does write must say `yes`). The comment `Décision (<agent>,
      <case>) par défaut (question-default-delay)` is posted, the labels `ready-for-human` and
      `needs-info` the item holds are removed, `needs-your-attention` is added when the cell
      leaves the human a veto (`VETO: yes`), and a ticket (an issue, not a pull request) that held one of
      those two labels gets `ready-for-agent` back, so that the next agent resumes from its branch and
      its pull request (F-0003 A59);
    - `remind-human`: any other verdict (`RESERVED`, `DOMAIN`, `TECHNICAL`), or a `DECIDED` that has no
      cell, no source, or is not reversible (a staff-engineer block without `REVERSIBLE:` included). No decision is invented: the comment `Rappel
      (question-default-delay)` says why and `needs-your-attention` is added where the item lacks it.

Nothing is written without `--apply`; the plan is printed (`--json` for one document). The two
comments restart the delay of `due`. A key `question-default-delay` absent is "sans objet": nothing is
listed, decided or written, and no delay is guessed. A delay it cannot read, or a key repeated, a
verdict it cannot read, fail the command (code 2); a `gh` that fails, code 1. The standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import factory_slo  # noqa: E402  its `gh` runner and its reader of paginated JSON
import parse_output  # noqa: E402  the reader of the deciders' block
import sla  # noqa: E402  the hooks' reader of a delay (`24 h`, `3 j`), which `min` extends here
import token_audit  # noqa: E402  the reader of an ISO date
import usine  # noqa: E402  the reader of `usine.md`

Runner = Callable[[list[str], Path], str]

KEY = "question-default-delay"
MINUTES = re.compile(r"^(\d+)\s*min$")
ABSENT = f"sans objet (clé `{KEY}` absente)"
ATTENTION = "needs-your-attention"
# Labels that say a human is awaited; the first two are answered by a default decision and removed.
ANSWERABLE = ("ready-for-human", "needs-info")
READY = "ready-for-agent"
WAITING = (*ANSWERABLE, ATTENTION)
# The first line of what `route` posts: it restarts the delay of the question.
MARK = re.compile(rf"^(?:Rappel|Décision)\b[^\n]*\({re.escape(KEY)}\)")
REMINDER = re.compile(rf"^Rappel\b[^\n]*\({re.escape(KEY)}\)")
WRONG_CALL = 2
GH_FAILED = 1
ISSUES = "repos/{owner}/{repo}/issues"


class DelayError(ValueError):
    """A key or a verdict the script cannot read: the command fails and guesses nothing."""


def parse_delay(text: str) -> timedelta | None:
    """`10 min` as a delay, else `2 h` or `3 j` as the key `sla` reads them; None when unreadable."""
    match = MINUTES.match(text.strip())
    if match is None:
        return sla.parse_delay(text)
    return timedelta(minutes=int(match.group(1))) if int(match.group(1)) > 0 else None


def load_delay(project: Path) -> tuple[timedelta, str] | None:
    """The delay the key declares and its text, None when the key is absent."""
    values = usine.load(project).get(KEY)
    if not values:
        return None
    if len(values) > 1:
        raise DelayError(f"`{KEY}` : une seule ligne attendue, {len(values)} lignes déclarées")
    delay = parse_delay(values[0])
    if delay is None:
        raise DelayError(
            f"`{KEY}` : délai illisible `{values[0]}` "
            "(attendu un nombre au-dessus de 0 suivi de `min`, `h` ou `j`, comme `10 min`, `24 h` ou `2 j`)"
        )
    return delay, values[0].strip()


def gh_list(run: Runner, project: Path, endpoint: str) -> list[dict]:
    """The objects `gh api --paginate <endpoint>` prints; RuntimeError when `gh` fails."""
    text = run(["gh", "api", "--paginate", endpoint], project)
    return [item for item in factory_slo.parse_stream(text) if isinstance(item, dict)]


def label_names(item: dict) -> list[str]:
    return [str(label.get("name")) for label in item.get("labels") or [] if isinstance(label, dict)]


def kind_of(item: dict) -> str:
    return "pull request" if "pull_request" in item else "issue"


def instant(value: object) -> datetime | None:
    try:
        return token_audit.parse_time(str(value)) if value else None
    except ValueError:
        return None


@dataclass
class Question:
    number: int
    kind: str
    labels: list[str]
    since: datetime | None = None
    reminded: datetime | None = None
    reminder: bool = False

    def clock(self) -> datetime | None:
        """When the wait last started: the later of the label and the last default or reminder."""
        moments = [m for m in (self.since, self.reminded) if m is not None]
        return max(moments) if moments else None

    def due_at(self, delay: timedelta) -> datetime | None:
        """When the wait reaches `delay` (the bound itself included); None for an item no date can be read for."""
        start = self.clock()
        return None if start is None else start + delay

    def to_dict(self, now: datetime) -> dict:
        start = self.clock()
        waited = None if start is None else round((now - start).total_seconds() / 3600, 1)
        return {
            "number": self.number,
            "kind": self.kind,
            "labels": self.labels,
            "depuis": None if start is None else start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "attente_heures": waited,
        }


def questions(project: Path, run: Runner, only: set[int] | None = None) -> list[Question]:
    """The open tickets and pull requests that carry a waiting label, with the wait that applies.

    With `only`, the events and comments of those numbers alone are read: the `Stop` hook asks about the
    items its session labeled, and does not pay two `gh` calls for every other question of the project.
    """
    items: dict[int, dict] = {}
    for label in WAITING:
        for item in gh_list(run, project, f"{ISSUES}?state=open&labels={label}&per_page=100"):
            if isinstance(item.get("number"), int):
                items[item["number"]] = item
    found = []
    for number in sorted(items):
        if only is not None and number not in only:
            continue
        held = [name for name in label_names(items[number]) if name in WAITING]
        question = Question(number, kind_of(items[number]), held)
        events = gh_list(run, project, f"{ISSUES}/{number}/events?per_page=100")
        dates = [
            when
            for event in events
            if event.get("event") == "labeled"
            and isinstance(event.get("label"), dict)
            and event["label"].get("name") in held
            and (when := instant(event.get("created_at"))) is not None
        ]
        question.since = max(dates) if dates else None
        comments = gh_list(run, project, f"{ISSUES}/{number}/comments?per_page=100")
        marks = [
            when
            for comment in comments
            if MARK.match(str(comment.get("body") or ""))
            and (when := instant(comment.get("created_at"))) is not None
        ]
        question.reminded = max(marks) if marks else None
        question.reminder = any(REMINDER.match(str(comment.get("body") or "")) for comment in comments)
        found.append(question)
    return found


def hours_text(hours: float) -> str:
    return f"{hours:g} h"


def run_due(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    loaded = load_delay(args.projet)
    if loaded is None:
        if args.json:
            print(json.dumps({"statut": "sans objet", "raison": ABSENT}, ensure_ascii=False))
        else:
            print(f"QUESTIONS: {ABSENT}")
        return 0
    delay, text = loaded
    due, undated = [], []
    for question in questions(args.projet, run):
        moment = question.due_at(delay)
        if moment is None:
            undated.append(question)
        elif now >= moment:
            due.append(question)
    if args.json:
        document = {
            "statut": "calculé",
            "delai": text,
            "echues": [q.to_dict(now) for q in due],
            "non_datees": [q.to_dict(now) for q in undated],
        }
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return 0
    for question in due:
        waited = question.to_dict(now)["attente_heures"]
        labels = ", ".join(question.labels)
        print(f"ECHUE: #{question.number} ({question.kind}) {labels} depuis {hours_text(waited)} (délai {text})")
    for question in undated:
        labels = ", ".join(question.labels)
        print(f"NON DATEE: #{question.number} ({question.kind}) {labels} : aucun événement d'étiquette lu")
    if not due:
        print(f"AUCUNE: aucune question n'attend depuis {text} ou plus")
    return 0


@dataclass
class Plan:
    action: str
    item: int
    comment: str
    reason: str
    add_labels: list[str] = field(default_factory=list)
    remove_labels: list[str] = field(default_factory=list)

    def to_dict(self, applied: bool) -> dict:
        return {
            "action": self.action,
            "item": self.item,
            "raison": self.reason,
            "commentaire": self.comment,
            "ajouter": self.add_labels,
            "retirer": self.remove_labels,
            "applique": applied,
        }


def undecided(fields: dict[str, str], agent: str) -> str | None:
    """Why a verdict is not a default decision, or None when it is one.

    `forge:staff-engineer` must write `REVERSIBLE: yes`. `forge:product-owner` writes no such line, its
    matrix cells being reversible by construction; a line it does write still has to say `yes`.
    """
    verdict = fields["VERDICT"]
    if verdict != "DECIDED":
        return f"le verdict est {verdict}, que la matrice ne donne pas à un agent"
    if not fields.get("MATRIX_CELL", "").strip() or not fields.get("DECISION", "").strip():
        return "la décision n'a pas de case de la matrice ou pas de texte"
    if not fields.get("GROUND", "").strip():
        return "la décision n'a pas de source : sans source, ce n'est pas une décision"
    reversible = fields.get("REVERSIBLE")
    if reversible is None and agent == "staff-engineer":
        return "la décision ne dit pas si elle est réversible (pas de ligne `REVERSIBLE:`)"
    if reversible is not None and not reversible.strip().lower().startswith("yes"):
        return f"la décision n'est pas réversible ({reversible.strip() or 'sans raison'})"
    return None


def plan_for(fields: dict[str, str], item: dict, agent: str, delay_text: str) -> Plan:
    """The comment and the labels that follow the verdict, for the ticket or pull request `item`."""
    number = int(item["number"])
    held = label_names(item)
    cell = fields.get("MATRIX_CELL", "").strip()
    decision = fields.get("DECISION", "").strip()
    ground = fields.get("GROUND", "").strip()
    why = undecided(fields, agent)
    if why is None:
        comment = (
            f"Décision ({agent}, {cell}) par défaut ({KEY}) : {decision}\n\n"
            f"Raison et source : {ground}\n\n"
            f"Cette question attendait une réponse depuis plus de {delay_text}. La décision est posée par "
            "défaut et reste réversible : l'humain peut y revenir par un commentaire, rien n'attend sa lecture."
        )
        veto = fields.get("VETO", "").strip().lower().startswith("yes")
        add = [ATTENTION] if veto and ATTENTION not in held else []
        remove = [name for name in held if name in ANSWERABLE]
        if remove and kind_of(item) == "issue" and READY not in held:
            add.append(READY)
        return Plan("post-default", number, comment, "décision déléguée, posée par défaut", add, remove)
    comment = (
        f"Rappel ({KEY}) : cette question attend une réponse depuis plus de {delay_text} et ne se "
        f"tranche pas par défaut ({why}).\n\n"
        f"Case : {cell or 'aucune'}\n"
        f"Décision ou geste attendu : {decision or 'non écrit'}\n"
        f"Source : {ground or 'non écrite'}\n\n"
        f"L'étiquette `{ATTENTION}` la signale à l'humain, qui garde la décision."
    )
    add = [ATTENTION] if ATTENTION not in held else []
    return Plan("remind-human", number, comment, why, add, [])


def apply(plan: Plan, run: Runner, project: Path) -> None:
    """Post the comment, then add and remove the labels, in that order; RuntimeError when `gh` fails."""
    base = f"{ISSUES}/{plan.item}"
    run(["gh", "api", f"{base}/comments", "-f", f"body={plan.comment}"], project)
    for label in plan.add_labels:
        run(["gh", "api", f"{base}/labels", "-f", f"labels[]={label}"], project)
    for label in plan.remove_labels:
        run(["gh", "api", "-X", "DELETE", f"{base}/labels/{label}"], project)


def run_route(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    loaded = load_delay(args.projet)
    if loaded is None:
        print(f"ROUTE: {ABSENT}")
        return 0
    _, text = loaded
    try:
        fields = parse_output.parse_decider(Path(args.verdict).read_text(encoding="utf-8"))
    except (parse_output.OutputError, OSError, UnicodeDecodeError) as error:
        raise DelayError(f"le verdict de `{args.verdict}` ne se lit pas : {error}") from error
    item = factory_slo.parse_stream(run(["gh", "api", f"{ISSUES}/{args.item}"], args.projet))
    if not item or not isinstance(item[0], dict) or "number" not in item[0]:
        raise RuntimeError(f"le ticket ou la PR #{args.item} ne se lit pas")
    plan = plan_for(fields, item[0], args.agent, text)
    if args.apply:
        apply(plan, run, args.projet)
    if args.json:
        print(json.dumps(plan.to_dict(args.apply), ensure_ascii=False, indent=2))
        return 0
    print(f"ACTION: {plan.action} #{plan.item}")
    print(f"RAISON: {plan.reason}")
    print(f"APPLIQUE: {'oui' if args.apply else 'non'}")
    return 0


def main(argv: list[str] | None = None, run: Runner | None = None, now: datetime | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    due = commands.add_parser("due", help="the questions that waited past the delay")
    due.add_argument("projet", type=Path)
    due.add_argument("--json", action="store_true")
    route = commands.add_parser("route", help="the default decision or the reminder that follows a verdict")
    route.add_argument("projet", type=Path)
    route.add_argument("verdict", type=Path, help="the file holding the decider's block")
    route.add_argument("--item", type=int, required=True, help="the number of the ticket or pull request")
    route.add_argument("--agent", required=True, choices=("staff-engineer", "product-owner"))
    route.add_argument("--apply", action="store_true", help="post the comment and set the labels")
    route.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    run = run or factory_slo.run_command
    moment = now or datetime.now(timezone.utc)
    handlers = {"due": run_due, "route": run_route}
    try:
        return handlers[args.command](args, run, moment)
    except DelayError as error:
        print(f"question_delay: {error}", file=sys.stderr)
        return WRONG_CALL
    except RuntimeError as error:
        print(f"question_delay: {error}", file=sys.stderr)
        return GH_FAILED


if __name__ == "__main__":
    sys.exit(main())
