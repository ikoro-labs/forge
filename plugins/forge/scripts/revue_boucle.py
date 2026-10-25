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

    python revue_boucle.py tour <journal> <verdict> [--matrice FILE --ecrans "Écran n, Écran m"]
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
import revue_bout_en_bout  # noqa: E402
import usine  # noqa: E402

# "Un écart qui revient deux fois" (the ticket of the loop): the number of returns that sends it back to the human.
MAX_RETURNS = 2


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


def porte(args: argparse.Namespace) -> int:
    """The gate of the acceptance test: open only on a review of the whole path with no `bloquant` and no `majeur`."""
    text = Path(args.compte_rendu).read_text(encoding="utf-8")
    fields = {key: value.strip() for key, value in re.findall(r"^([A-Z]+):[ \t]*(.*)$", text, re.MULTILINE)}
    if fields.get("RESULT") != "REVUE":
        _print("FERMEE", "pas de compte rendu de revue", "attendu RESULT: REVUE, celui de forge:feature-review")
        return 1
    counts = {name: re.search(rf"\b{name}\s+(\d+)", fields.get("ECARTS", "")) for name in ("bloquant", "majeur", "mineur")}
    if not all(counts.values()):
        _print("FERMEE", "ECARTS illisible", "attendu : bloquant <n>, majeur <n>, mineur <n>")
        return 1
    number = {name: int(match.group(1)) for name, match in counts.items() if match}
    if not re.fullmatch(r"entière|entiere", fields.get("PORTEE", "")):
        _print("FERMEE", "revue partielle", f"PORTEE « {fields.get('PORTEE', '')} » : la recette suit une revue du parcours en entier")
        return 1
    if number["bloquant"] or number["majeur"]:
        _print("FERMEE", f"bloquant {number['bloquant']}, majeur {number['majeur']}", "la recette attend zéro bloquant et zéro majeur")
        return 1
    _print("OUVERTE", "zéro bloquant, zéro majeur", f"mineur {number['mineur']} : au rapport, sans fermer la porte")
    return 0


def _rounds(journal: Path) -> dict[int, dict[str, str]]:
    """The journal as {round: {identifier: state}}; no file, no round."""
    rounds: dict[int, dict[str, str]] = {}
    if journal.is_file():
        for line in journal.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) == 4 and fields[0] == "TOUR" and fields[1].isdigit():
                rounds.setdefault(int(fields[1]), {})[fields[2]] = fields[3]
    return rounds


def tour(args: argparse.Namespace) -> int:
    """Append the judged elements of a verdict to the journal as the next round."""
    entries, invalid = revue_bout_en_bout._verdict_entries(Path(args.verdict).read_text(encoding="utf-8"))
    scope = revue_bout_en_bout.scope_of(args.ecrans)
    if scope is not None:
        # A review on the touched screens: the rows of the other screens were not judged, they enter no round.
        if not args.matrice:
            print("revue_boucle: --ecrans demande --matrice, pour savoir l'écran de chaque identifiant", file=sys.stderr)
            return 2
        by_id = {row["Identifiant"]: row for row in matrice.parse(Path(args.matrice).read_text(encoding="utf-8"))}
        entries = [e for e in entries if e["id"] not in by_id or by_id[e["id"]]["Écran"] in scope]
    if invalid or not entries:
        for subject, reason in invalid:
            _print("INVALID", subject, reason)
        if not entries and not invalid:
            _print("INVALID", "verdict", "aucune ligne ELEMENT : rien à inscrire au journal")
        return 1
    journal = Path(args.journal)
    number = max(_rounds(journal), default=0) + 1
    with journal.open("a", encoding="utf-8", newline="\n") as handle:
        for entry in entries:
            handle.write(f"TOUR\t{number}\t{entry['id']}\t{entry['state']}\n")
    _print("TOUR", str(number), f"{len(entries)} éléments inscrits")
    return 0


def retours(args: argparse.Namespace) -> int:
    """The returns of each gap, and the stop when one returned MAX_RETURNS times."""
    history: dict[str, list[bool]] = {}
    for _, states in sorted(_rounds(Path(args.journal)).items()):
        for identifier, state in states.items():
            history.setdefault(identifier, []).append(state != "tenu")
    stop = False
    for identifier, gaps in history.items():
        count = sum(gaps[gaps.index(True) + 1:]) if True in gaps else 0
        if count >= MAX_RETURNS:
            _print("ARRET", identifier, str(count), f"revenu {count} fois : la boucle s'arrête, l'humain reprend la main")
            stop = True
        elif count:
            _print("RETOUR", identifier, str(count))
    return 1 if stop else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    trigger = commands.add_parser("declencher", help="does a merged diff trigger the review, and on which screens")
    trigger.add_argument("--files", required=True, help="the files the merged PR changed, one per line")
    trigger.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md)")
    trigger.add_argument("--root", help="the project copy to read (default: the project directory)")
    trigger.add_argument("--matrice", help="the matrix of the feature, to find the screens of the ticket")
    trigger.add_argument("--ticket", help="the merged ticket, written #n")
    gate = commands.add_parser("porte", help="may the acceptance test start, from the report of the review")
    gate.add_argument("compte_rendu", help="the file holding the `RESULT: REVUE` report")
    record = commands.add_parser("tour", help="add the verdict of a review to the journal as the next round")
    record.add_argument("journal", help="the journal file of the loop")
    record.add_argument("verdict", help="the verdict of the judge")
    record.add_argument("--matrice", help="the matrix of the feature, with --ecrans")
    record.add_argument("--ecrans", help="a review on the touched screens: only their elements enter the round")
    back = commands.add_parser("retours", help="the gaps that returned, and the stop")
    back.add_argument("journal", help="the journal file of the loop")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        return {"porte": porte, "tour": tour, "retours": retours}.get(args.command, declencher)(args)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(f"revue_boucle: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
