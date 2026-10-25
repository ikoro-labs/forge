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
(`TOUR <n> <identifier> <état>`), and, in the order they happened, the merged tickets that covered an
identifier (`CORRECTION <ticket> <identifier>`, written by `correction <journal> --ticket '#n' --couvre
'<identifiers>'` when a ticket that lists them under `Couvre :` merges, before the review it triggers).

    python revue_boucle.py correction <journal> --ticket '#n' --couvre 'EXI-01, C01'

An identifier of the source is a gap in a round when its state is not `tenu`. It returns once each time it
is a gap again after a first gap AND a fix happened since that gap was last seen: a merged ticket that
covered it, or a round where it was `tenu`. Two rounds with no such fix between them are one gap seen
twice, not a return (several tickets merge before the first fix does). `retours` prints `RETOUR <id> <n>`
for those, and `ARRET <id> <n>` (exit 1) for each identifier that returned twice: the loop stops and the
human takes over. The count rests on the identifier of the source, the state and the merged fixes, never
on a ticket number as a key of the gap.

    python revue_boucle.py doublons <tickets> <ouverts>

The loop publishes no second ticket for an identifier an open ticket already covers. `<tickets>` holds the
`TICKET` lines of `revue_bout_en_bout.py verdict --tickets`; `<ouverts>` one line `#n<TAB>id, id` per open
ticket of the feature (its `Couvre :` line; open until merged, so in flight too). Prints `DEJA-COUVERT <id>
#n` for each covered identifier, then `PUBLIER` with the ticket line narrowed to the identifiers left, or
`OMIS` when none is left.
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


def correction(args: argparse.Namespace) -> int:
    """Record that a merged ticket covered these identifiers, before the review it triggers."""
    identifiers = [i.strip() for i in args.couvre.split(",") if i.strip()]
    if not identifiers or not re.fullmatch(r"#\d+", args.ticket):
        _print("INVALID", args.ticket, "attendu : --ticket '#n' et --couvre 'identifiants séparés par des virgules'")
        return 1
    with Path(args.journal).open("a", encoding="utf-8", newline="\n") as handle:
        for identifier in identifiers:
            handle.write(f"CORRECTION\t{args.ticket}\t{identifier}\n")
    _print("CORRECTION", args.ticket, ", ".join(identifiers))
    return 0


def doublons(args: argparse.Namespace) -> int:
    """Narrow the ticket drafts to the identifiers no open ticket covers."""
    covered: dict[str, str] = {}
    for text in Path(args.ouverts).read_text(encoding="utf-8").splitlines():
        fields = text.split("\t")
        if len(fields) == 2 and re.fullmatch(r"#\d+", fields[0].strip()):
            for identifier in fields[1].split(","):
                covered.setdefault(identifier.strip(), fields[0].strip())
    for text in Path(args.tickets).read_text(encoding="utf-8").splitlines():
        fields = text.split("\t")
        if len(fields) != 6 or fields[0] != "TICKET":
            continue
        identifiers = [i.strip() for i in fields[3].split(",")]
        for identifier in identifiers:
            if identifier in covered:
                _print("DEJA-COUVERT", identifier, covered[identifier])
        left = [i for i in identifiers if i not in covered]
        if not left:
            _print("OMIS", fields[1], fields[2], fields[3])
            continue
        findings = [f for f in fields[5].split(" ; ") if f.split(" : ")[0].strip() in left]
        _print("PUBLIER", fields[1], fields[2], ", ".join(left), fields[4], " ; ".join(findings))
    return 0


def retours(args: argparse.Namespace) -> int:
    """The returns of each gap, and the stop when one returned MAX_RETURNS times."""
    seen_gap: dict[str, bool] = {}
    fixed: dict[str, bool] = {}
    count: dict[str, int] = {}
    journal = Path(args.journal)
    lines = journal.read_text(encoding="utf-8").splitlines() if journal.is_file() else []
    for text in lines:
        fields = text.split("\t")
        if len(fields) == 3 and fields[0] == "CORRECTION":
            fixed[fields[2]] = True
        elif len(fields) == 4 and fields[0] == "TOUR" and fields[1].isdigit():
            identifier, state = fields[2], fields[3]
            if state == "tenu":
                # Held again: whatever changed it, the gap was fixed; a break after it is a return.
                fixed[identifier] = seen_gap.get(identifier, False)
            else:
                if seen_gap.get(identifier) and fixed.get(identifier):
                    count[identifier] = count.get(identifier, 0) + 1
                seen_gap[identifier] = True
                fixed[identifier] = False
    stop = False
    for identifier, number in count.items():
        if number >= MAX_RETURNS:
            _print("ARRET", identifier, str(number), f"revenu {number} fois : la boucle s'arrête, l'humain reprend la main")
            stop = True
        else:
            _print("RETOUR", identifier, str(number))
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
    fix = commands.add_parser("correction", help="record the identifiers a merged ticket covered")
    fix.add_argument("journal", help="the journal file of the loop")
    fix.add_argument("--ticket", required=True, help="the merged ticket, written #n")
    fix.add_argument("--couvre", required=True, help="the identifiers of its `Couvre :` line, separated by commas")
    twice = commands.add_parser("doublons", help="drop from the drafts the identifiers an open ticket covers")
    twice.add_argument("tickets", help="the TICKET lines of the verdict")
    twice.add_argument("ouverts", help="one line `#n<TAB>identifiers` per open ticket")
    back = commands.add_parser("retours", help="the gaps that returned, and the stop")
    back.add_argument("journal", help="the journal file of the loop")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        return {"porte": porte, "tour": tour, "retours": retours, "correction": correction, "doublons": doublons}.get(args.command, declencher)(args)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(f"revue_boucle: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
