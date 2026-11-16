"""The conditions of a continuous release: when a version is due, and whether the agent may publish it.

    python release.py trigger <project> [--json]

`trigger` reads the key `release-trigger` of `docs/agents/usine.md`, one line
`<merges> | <longest wait>` (`10 | 7 j`: the wait is a number followed by `h` or `j`, as in the key
`sla`). A key absent is "sans objet": the agent publishes nothing, and no value is guessed. A line it
cannot read (a count that is not a whole number above zero, a wait it cannot read, a missing part, a
repeated key) fails the command with code 2 and prints no state: it is never completed.

The output is one fact per line, in French, on standard output. The standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import budget  # noqa: E402  the hooks' reader of `slo-status.json` and of the key `budget-action`
import factory_slo  # noqa: E402  the indicators of the factory, whose runner and base this script reuses
import sla  # noqa: E402  the hooks' reader of a delay (`4 h`, `3 j`)
import usine  # noqa: E402  the reader of `usine.md`

Runner = Callable[[list[str], Path], str]

TRIGGER_KEY = "release-trigger"
TAG_KEY = "release-tag"
REACHED, NOT_REACHED, ABSENT = "atteint", "non atteint", "sans objet"
MET, NOT_MET, UNVERIFIABLE = "tenue", "non tenue", "non vérifiable"
STATE_MAX_AGE = timedelta(hours=1)
WRONG_CALL = 2


class ReleaseError(ValueError):
    """A key the script cannot read: the command fails and guesses nothing."""


@dataclass(frozen=True)
class Trigger:
    merges: int
    wait: timedelta
    wait_text: str


def parse_trigger(values: list[str]) -> Trigger:
    """The trigger the key declares; ReleaseError when it is repeated or one of its parts is unreadable."""
    if len(values) > 1:
        raise ReleaseError(f"`{TRIGGER_KEY}` : une seule ligne attendue, {len(values)} lignes déclarées")
    value = values[0]
    parts = usine.split_value(value, 2)
    if parts is None:
        raise ReleaseError(f"`{TRIGGER_KEY}` : `{value}` : attendu `<N fusions> | <délai max>`, comme `10 | 7 j`")
    count, wait_text = parts
    if not count.isdigit() or int(count) == 0:
        raise ReleaseError(f"`{TRIGGER_KEY}` : `{value}` : le nombre de fusions est un entier au-dessus de 0")
    wait = sla.parse_delay(wait_text)
    if wait is None:
        raise ReleaseError(
            f"`{TRIGGER_KEY}` : `{value}` : délai illisible `{wait_text}` "
            "(attendu un nombre au-dessus de 0 suivi de `h` ou `j`, comme `7 j`)"
        )
    return Trigger(int(count), wait, wait_text)


def load_trigger(project: Path) -> Trigger | None:
    """The trigger of the project, None when the key is absent."""
    values = usine.load(project).get(TRIGGER_KEY)
    return parse_trigger(values) if values else None


@dataclass(frozen=True)
class Due:
    """Whether a version is due: `atteint`, `non atteint` or `sans objet`, and the sentence that says why."""

    status: str
    text: str
    waiting: int = 0
    oldest: datetime | None = None

    @property
    def reached(self) -> bool:
        return self.status == REACHED

    def line(self) -> str:
        return f"DECLENCHEUR: {self.text}"


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count > 1 else ''}"


def wait_text(delta: timedelta) -> str:
    """A wait in the unit of the key: days from two days on, hours below."""
    hours = int(delta.total_seconds() // 3600)
    return f"{hours // 24} j" if hours >= 48 or (hours >= 24 and hours % 24 == 0) else f"{hours} h"


def waiting_merges(f: factory_slo.Factory, patterns: list[re.Pattern[str]]) -> list[datetime]:
    """The merge dates of the pull requests on the base whose merge commit is in no version tag.

    A merge commit that git does not know (not fetched) is in no tag as far as git can say: it counts
    as waiting, so a version may fall due early, never late.
    """
    fields = "number,mergedAt,mergeCommit"
    merged = f.gh("pr", "list", "--state", "merged", "--base", f.base, "--limit", "1000", "--json", fields)
    waiting = []
    for item in merged:
        moment = factory_slo.when(item, "mergedAt")
        oid = (item.get("mergeCommit") or {}).get("oid")
        if moment is not None and factory_slo.first_tag_date(f, patterns, oid) is None:
            waiting.append(moment)
    return sorted(waiting)


def due(project: Path, run: Runner, now: datetime) -> Due:
    """The trigger of the key `release-trigger` against the merges waiting for a tag of `release-tag`."""
    trigger = load_trigger(project)
    if trigger is None:
        return Due(ABSENT, f"sans objet (clé `{TRIGGER_KEY}` absente), aucune publication par l'agent")
    f = factory_slo.Factory(project, now - timedelta(days=1), now, run)
    templates = f.required(TAG_KEY)
    if not templates:
        return Due(ABSENT, f"sans objet (clé `{TAG_KEY}` absente), aucune publication par l'agent")
    waiting = waiting_merges(f, [factory_slo.tag_pattern(template) for template in templates])
    if not waiting:
        return Due(NOT_REACHED, f"{NOT_REACHED} : aucune fusion n'attend de version")
    elapsed = now - waiting[0]
    count, wanted = plural(len(waiting), "fusion"), plural(trigger.merges, "demandée")
    if len(waiting) >= trigger.merges:
        return Due(REACHED, f"{REACHED} par le nombre : {count} en attente pour {wanted}", len(waiting), waiting[0])
    if elapsed >= trigger.wait:
        oldest = f"la plus ancienne attend depuis {wait_text(elapsed)} pour {trigger.wait_text}"
        return Due(REACHED, f"{REACHED} par le délai : {oldest}", len(waiting), waiting[0])
    oldest = f"la plus ancienne depuis {wait_text(elapsed)} pour {trigger.wait_text}"
    return Due(NOT_REACHED, f"{NOT_REACHED} : {count} en attente pour {wanted}, {oldest}", len(waiting), waiting[0])


def run_trigger(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    print(due(args.projet, run, now).line())
    return 0


@dataclass(frozen=True)
class Condition:
    """One condition of the release: `tenue`, `non tenue`, or `non vérifiable` (never read as `tenue`)."""

    name: str
    status: str
    text: str

    @property
    def held(self) -> bool:
        return self.status == MET

    def line(self) -> str:
        return f"CONDITION: {self.name} | {self.status} | {self.text}"


def objective_name(item: dict) -> str:
    sli, stat = str(item.get("sli")), item.get("statistique")
    return f"{sli} {stat}" if stat else sli


def state_of(project: Path, run: Runner, now: datetime) -> tuple[dict | None, str | None]:
    """The `slo-status.json` of the project, read as a state fresh within the hour, and why it is not usable."""
    try:
        path = factory_slo.state_path(project, run)
    except RuntimeError as error:
        return None, f"le dossier git commun est illisible ({error})"
    state, reason = budget.load_state(path, now, STATE_MAX_AGE)
    if state is None:
        return None, f"{reason}. Recalcule l'état : `{budget.STATUS_COMMAND}`"
    return state, None


def slo_condition(project: Path, run: Runner, now: datetime) -> Condition:
    """Every objective of the `slo` key is `tenu` in a state computed within the hour."""
    if not usine.load(project).get("slo"):
        return Condition("slo", UNVERIFIABLE, "sans objet (clé `slo` absente) : aucun objectif à lire")
    state, reason = state_of(project, run, now)
    if state is None:
        return Condition("slo", UNVERIFIABLE, str(reason))
    objectives = state["objectifs"]
    if not objectives:
        return Condition("slo", UNVERIFIABLE, "aucun objectif dans le fichier d'état")
    missing = [
        f"{objective_name(item)} ({item.get('etat') or 'sans objet'})"
        for item in objectives
        if item.get("statut") != "calculé" or item.get("etat") != budget.HELD
    ]
    if missing:
        return Condition("slo", NOT_MET, "objectifs qui ne sont pas `tenu` : " + ", ".join(missing))
    return Condition("slo", MET, f"{plural(len(objectives), 'objectif')} `tenu`, calculés dans l'heure")


CONDITIONS: dict[str, Callable[[Path, Runner, datetime], Condition]] = {"slo": slo_condition}


def run_condition(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    print(CONDITIONS[args.name](args.projet, run, now).line())
    return 0


def main(argv: list[str] | None = None, run: Runner | None = None, now: datetime | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    trigger = commands.add_parser("trigger", help="whether a version is due")
    trigger.add_argument("projet", type=Path)
    condition = commands.add_parser("condition", help="one condition of the release")
    condition.add_argument("name", choices=sorted(CONDITIONS))
    condition.add_argument("projet", type=Path)
    args = parser.parse_args(argv)
    run = run or factory_slo.run_command
    moment = now or datetime.now(timezone.utc)
    try:
        return run_trigger(args, run, moment) if args.command == "trigger" else run_condition(args, run, moment)
    except ReleaseError as error:
        print(f"release: {error}", file=sys.stderr)
        return WRONG_CALL


if __name__ == "__main__":
    sys.exit(main())
