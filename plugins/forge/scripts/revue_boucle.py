"""Decide the steps of the end-to-end review loop of `forge:feature-build`, without an opinion on the code.

The loop runs `forge:feature-review` after a merge, sends its gaps back to construction as tickets, plays
the path again, and opens the acceptance test only on a clean review. This script holds the four facts
the orchestrator reads; it merges and publishes nothing. The standard library only; the output is UTF-8.

    python revue_boucle.py declencher --files FILE [--usine FILE] [--root DIR] [--matrice FILE --ticket '#n']

`--files` lists the files a merged PR changed, one per line. Each one under a prefix of the key
`journey-paths` (the front, and the APIs it consumes) is printed `PARCOURS-TOUCHE`, then one line
`REVUE declenchee` (exit 0) or `REVUE non declenchee` (exit 1). Without the key: `sans objet (clé
journey-paths absente)` and exit 1, no prefix is guessed. With `--matrice` and `--ticket`, the review
plays the screens the matrix links to that ticket, one `ECRAN <Écran n> <identifiers>` line each; a
ticket linked to no screen is reviewed on the whole path (`ECRAN tous`).

    python revue_boucle.py porte <compte-rendu>

The gate of the acceptance test (`forge:feature-verify`): the report `RESULT: REVUE` of a review
of the whole path (`PORTEE: entière`) holds zero `bloquant` and zero `majeur`. `OUVERTE` (exit 0) or
`FERMEE` and the reason (exit 1). A `mineur` stays in the report and does not close the gate.

    python revue_boucle.py tour <journal> <verdict>
    python revue_boucle.py retours <journal>

The journal keeps, for each round of the loop, the state of every element the judge has judged
(`TOUR <n> <identifier> <état>`). An identifier of the source is a gap in a round when its state is not
`tenu`; it returns once for each round after its first gap in which it is a gap again, whether the fix
did not hold or a fixed element broke again. `retours` prints `RETOUR <id> <n>` for those, and
`ARRET <id> <n>` (exit 1) for each identifier that returned twice: the loop stops and the human takes
over. The count rests on the identifier of the source and the state alone, never on a ticket number.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import matrice  # noqa: E402
import preuves_ecran  # noqa: E402
import usine  # noqa: E402

MAX_RETURNS = 2
STATES = ("tenu", "partiel", "absent", "contraire")


def _print(*fields: str) -> None:
    print("\t".join(fields))


def declencher(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else usine.project_root()
    config_file = Path(args.usine) if args.usine else root / usine.CONFIG_PATH
    try:
        config = usine.parse(config_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if args.usine:
            raise
        config = {}
    changed = [line.strip() for line in Path(args.files).read_text(encoding="utf-8").splitlines() if line.strip()]
    prefixes = [value for value in config.get(preuves_ecran.PATHS_KEY, []) if value.strip()]
    if not prefixes:
        print(f"sans objet (clé {preuves_ecran.PATHS_KEY} absente)")
        return 1
    touched = [path for path in changed if any(path.startswith(prefix) for prefix in prefixes)]
    for path in touched:
        _print("PARCOURS-TOUCHE", path)
    if not touched:
        _print("REVUE", "non declenchee", "aucun fichier du diff sous un chemin du parcours")
        return 1
    _print("REVUE", "declenchee", f"{len(touched)} fichier(s) du parcours touchés")
    if args.matrice and args.ticket:
        wanted = re.compile(rf"(?<!\w){re.escape(args.ticket)}(?!\w)")
        screens: dict[str, list[str]] = {}
        for row in matrice.parse(Path(args.matrice).read_text(encoding="utf-8")):
            if row["Écran"] and wanted.search(row["Ticket"]):
                screens.setdefault(row["Écran"], []).append(row["Identifiant"])
        for screen, identifiers in screens.items():
            _print("ECRAN", screen, ", ".join(identifiers))
        if not screens:
            _print("ECRAN", "tous", "le ticket n'est relié à aucun écran de la matrice : le parcours entier")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    trigger = commands.add_parser("declencher", help="does a merged diff trigger the review, and on which screens")
    trigger.add_argument("--files", required=True, help="the files the merged PR changed, one per line")
    trigger.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md)")
    trigger.add_argument("--root", help="the project copy to read (default: the project directory)")
    trigger.add_argument("--matrice", help="the matrix of the feature, to find the screens of the ticket")
    trigger.add_argument("--ticket", help="the merged ticket, written #n")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        return declencher(args)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(f"revue_boucle: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
