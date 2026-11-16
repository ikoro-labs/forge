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
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import factory_slo  # noqa: E402  the indicators of the factory, whose runner and base this script reuses
import sla  # noqa: E402  the hooks' reader of a delay (`4 h`, `3 j`)
import usine  # noqa: E402  the reader of `usine.md`

Runner = Callable[[list[str], Path], str]

TRIGGER_KEY = "release-trigger"
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


def run_trigger(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    trigger = load_trigger(args.projet)
    if trigger is None:
        print(f"DECLENCHEUR: sans objet (clé `{TRIGGER_KEY}` absente), aucune publication par l'agent")
        return 0
    print(f"DECLENCHEUR: déclaré, {trigger.merges} fusions ou {trigger.wait_text}")
    return 0


def main(argv: list[str] | None = None, run: Runner | None = None, now: datetime | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    trigger = commands.add_parser("trigger", help="whether a version is due")
    trigger.add_argument("projet", type=Path)
    trigger.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    run = run or factory_slo.run_command
    moment = now or datetime.now(timezone.utc)
    try:
        return run_trigger(args, run, moment)
    except ReleaseError as error:
        print(f"release: {error}", file=sys.stderr)
        return WRONG_CALL


if __name__ == "__main__":
    sys.exit(main())
