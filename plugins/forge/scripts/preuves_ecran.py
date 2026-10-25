"""Say which screen proofs a PR is expected to carry and whether they are attached, without an opinion.

    python preuves_ecran.py [--usine FILE] [--root DIR] [--matrice FILE] [--ticket '#n'] <pr-body-file | ->

The four capabilities a project turns on, each by its own key of `docs/agents/usine.md`, none with a
default value:

- `screenshot-command` : the command that takes browser captures without a screen, run from the root
  of the repository. `{out}` is mandatory: the folder where it writes the files, quoted by the caller.
- `recording-command` : the same for a video or a GIF of a path. `{out}` is mandatory.
- `browser-drive` : `<tool> | <station>`, a driven browser. It runs only on a station with an open
  session, never in CI.
- `computer-use-host` : the dedicated station where the computer is driven. Never the personal station
  of a member.

One line per finding, fields separated by tabs. A missing key prints `sans objet (clé <nom> absente)`
for itself and never stops the others. `CAPACITE` names a key that is declared, its value and its
limit. When at least one key is declared and `--matrice` is given, the rows of the matrix that name a
screen (`Écran` not empty) and, with `--ticket`, a `Ticket` cell citing that ticket are the screen
criteria the PR carries: `LIEE` (the row has a `Capture`) or `SANS-CAPTURE`. The PR body is searched
for attached images and videos (`![..](..)`, or a link to a `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`,
`.mp4`, `.webm`): `JOINTE` and the count, `MANQUE` when screen criteria are carried and none is
attached. The script reports, it does not judge. Exit 0 when nothing is missing, 1 on `SANS-CAPTURE`
or `MANQUE`, 2 when a declared value is invalid, a file unreadable or the call wrong. The output is
UTF-8. The standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402
from matrice import parse as parse_matrice  # noqa: E402

COMMAND_KEYS = ("screenshot-command", "recording-command")
DRIVE_KEY = "browser-drive"
HOST_KEY = "computer-use-host"
KEYS = ("screenshot-command", DRIVE_KEY, HOST_KEY, "recording-command")
LIMITS = {
    DRIVE_KEY: "poste avec session ouverte, jamais en CI",
    HOST_KEY: "poste dédié, jamais le poste personnel d'un membre",
}
_MEDIA = re.compile(r"!\[[^\]]*\]\([^)]+\)|\]\([^)]*\.(?:png|jpe?g|gif|webp|mp4|webm)(?:[?#][^)]*)?\)", re.IGNORECASE)


def attached(body: str) -> int:
    """The images and videos the body attaches."""
    return len(_MEDIA.findall(body))


def invalid(config: dict[str, list[str]]) -> list[str]:
    """What is wrong in a declared value, one message each."""
    problems = []
    for key in COMMAND_KEYS:
        for value in config.get(key, []):
            if "{out}" not in value:
                problems.append(f"{key} : « {value} » ne porte pas {{out}}, le dossier où écrire les fichiers")
    for value in config.get(DRIVE_KEY, []):
        if usine.split_value(value, 2) is None:
            problems.append(f"{DRIVE_KEY} : « {value} » s'écrit « outil | poste »")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("body", help="the body of the PR, or - for the standard input")
    parser.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md)")
    parser.add_argument("--root", help="the project copy to read (default: the project directory)")
    parser.add_argument("--matrice", help="the matrix of the feature, to find the screen criteria")
    parser.add_argument("--ticket", help="only the rows that cite this ticket, written #n")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = Path(args.root) if args.root else usine.project_root()
    config_file = Path(args.usine) if args.usine else root / usine.CONFIG_PATH
    try:
        try:
            config = usine.parse(config_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if args.usine:
                raise
            config = {}
        body = sys.stdin.read() if args.body == "-" else Path(args.body).read_text(encoding="utf-8")
        rows = parse_matrice(Path(args.matrice).read_text(encoding="utf-8")) if args.matrice else []
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(f"preuves_ecran: {error}", file=sys.stderr)
        return 2
    problems = invalid(config)
    if problems:
        for problem in problems:
            print(f"preuves_ecran: {problem}", file=sys.stderr)
        return 2
    declared = [key for key in KEYS if config.get(key)]
    for key in KEYS:
        if key not in declared:
            print(f"sans objet (clé {key} absente)")
        for value in config.get(key, []):
            print(f"CAPACITE\t{key}\t{value}\t{LIMITS.get(key, 'commande du projet')}")
    if not declared:
        return 0
    count = attached(body)
    missing = False
    carried = 0
    if args.matrice:
        wanted = re.compile(rf"(?<!\w){re.escape(args.ticket)}(?!\w)") if args.ticket else None
        for row in rows:
            if not row["Écran"] or (wanted and not wanted.search(row["Ticket"])):
                continue
            carried += 1
            if row["Capture"]:
                print(f"LIEE\t{row['Identifiant']}\t{row['Capture']}")
            else:
                missing = True
                print(f"SANS-CAPTURE\t{row['Identifiant']}\tcritère d'écran sans capture dans la matrice")
    if carried and not count:
        missing = True
        print("MANQUE\tcorps de PR\taucune capture ni vidéo jointe")
    elif count:
        print(f"JOINTE\tcorps de PR\t{count}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
