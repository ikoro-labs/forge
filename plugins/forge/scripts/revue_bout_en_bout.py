"""Check the files of an end-to-end review (`forge:feature-review`): what the run captured, what the judge said.

    python revue_bout_en_bout.py manifeste [--captures DIR] <parcours.md> <manifeste.tsv>

The run (the skill, in its own session) plays the wanted path of the feature in the real application
and writes a manifest, one line per fact, fields separated by tabs:

- `CAPTURE <file> <Écran n> <clair|sombre> <bureau|mobile>`: a capture of a screen in a theme and on a
  screen size;
- `NON-JOUE <Écran n> <reason>`: a screen the run could not play, with the reason (never empty);
- `ENVIRONNEMENT <name> <value>`: where the run happened. A line named `système` is required: what ran
  on one system only says so in the report.

`manifeste` crosses the manifest with the screens of `parcours.md` (the contract of `parcours.py`). Each
screen is expected in four variants (light and dark, desktop and mobile). One line per fact:
COUVERT (screen, theme, size, file), NON-JOUE (screen, reason), MANQUE (screen, theme, size: no capture and
no reason), INVALID (the line, the reason: a screen the path does not hold, an unknown theme or size, an
empty reason, a capture file that does not exist under `--captures`), ENVIRONNEMENT (passed through) and
SANS-ENVIRONNEMENT. Exit 0 when none of MANQUE, INVALID or SANS-ENVIRONNEMENT is printed, 1 otherwise,
2 when a file is unreadable or the call wrong. The output is UTF-8. The standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import matrice  # noqa: E402
import parcours  # noqa: E402

THEMES = ("clair", "sombre")
SIZES = ("bureau", "mobile")
STATES = ("tenu", "partiel", "absent", "contraire")
SEVERITIES = ("bloquant", "majeur", "mineur")
# A `tenu` whose finding says something is missing: the second reader weighs it with care.
_LACK = re.compile(
    r"\b(manque|manquent|manquant\w*|absent\w*|incomplet\w*|invisible|partiel\w*|aucun\w*|pas de|n'a pas|ne s'affiche pas|sans)\b",
    re.IGNORECASE,
)
_SCREEN = re.compile(r"^Écran\s+(\d+)$")


def _print(status: str, *fields: str) -> None:
    print("\t".join((status, *fields)))


def _records(text: str) -> list[tuple[int, list[str]]]:
    return [(number, line.split("\t")) for number, line in enumerate(text.splitlines(), start=1) if line.strip()]


def manifeste(path_text: str, manifest_text: str, captures: Path | None) -> int:
    """Print the coverage of the wanted path by the manifest; the exit code."""
    screens = [f"Écran {screen['number']}" for screen in parcours.parse(path_text) if screen["number"]]
    taken: dict[tuple[str, str, str], str] = {}
    not_played: dict[str, str] = {}
    environment: list[tuple[str, str]] = []
    bad = False
    for number, fields in _records(manifest_text):
        kind, rest = fields[0], [f.strip() for f in fields[1:]]
        if kind == "ENVIRONNEMENT" and len(rest) >= 2 and rest[0] and rest[1]:
            environment.append((rest[0], rest[1]))
        elif kind == "CAPTURE" and len(rest) == 4 and all(rest):
            name, screen, theme, size = rest
            if screen not in screens:
                _print("INVALID", f"ligne {number}", f"{screen} : le parcours voulu n'a pas cet écran")
            elif theme not in THEMES or size not in SIZES:
                _print("INVALID", f"ligne {number}", f"{theme} / {size} : attendu {'|'.join(THEMES)} puis {'|'.join(SIZES)}")
            elif captures is not None and not (captures / name).is_file():
                _print("INVALID", name, f"le fichier n'existe pas sous {captures} : une capture citée doit avoir été prise")
            else:
                taken[(screen, theme, size)] = name
                continue
            bad = True
        elif kind == "NON-JOUE" and len(rest) == 2 and rest[0] and rest[1]:
            if rest[0] in screens:
                not_played[rest[0]] = rest[1]
            else:
                _print("INVALID", f"ligne {number}", f"{rest[0]} : le parcours voulu n'a pas cet écran")
                bad = True
        elif kind in ("ENVIRONNEMENT", "CAPTURE", "NON-JOUE"):
            _print("INVALID", f"ligne {number}", f"{kind} : champs manquants ou vides (la raison d'un NON-JOUE ne s'omet pas)")
            bad = True
        else:
            _print("INVALID", f"ligne {number}", f"« {kind} » : attendu CAPTURE, NON-JOUE ou ENVIRONNEMENT")
            bad = True
    for screen in screens:
        if screen in not_played:
            _print("NON-JOUE", screen, not_played[screen])
            continue
        for theme in THEMES:
            for size in SIZES:
                if (screen, theme, size) in taken:
                    _print("COUVERT", screen, theme, size, taken[(screen, theme, size)])
                else:
                    _print("MANQUE", screen, theme, size)
                    bad = True
    for name, value in environment:
        _print("ENVIRONNEMENT", name, value)
    if not any(name == "système" for name, _ in environment):
        _print("SANS-ENVIRONNEMENT", "système", "dire sur quel système la revue a tourné")
        bad = True
    return 1 if bad else 0


def _verdict_entries(text: str) -> tuple[list[dict[str, str]], list[tuple[str, str]]]:
    """The ELEMENT lines of a verdict as dicts, and the INVALID findings as (subject, reason)."""
    entries: list[dict[str, str]] = []
    invalid: list[tuple[str, str]] = []
    for number, fields in _records(text):
        if fields[0].startswith("#"):
            continue
        fields = [f.strip() for f in fields]
        if fields[0] != "ELEMENT" or len(fields) != 7:
            invalid.append((f"ligne {number}", "attendu ELEMENT et six champs : identifiant, état, gravité, écran, capture, constat"))
            continue
        entry = dict(zip(("kind", "id", "state", "severity", "screen", "capture", "finding"), fields))
        reason = _entry_reason(entry)
        if reason:
            invalid.append((entry["id"] or f"ligne {number}", reason))
        else:
            entries.append(entry)
    return entries, invalid


def _entry_reason(entry: dict[str, str]) -> str | None:
    """Why one verdict line is unreadable, or None. The rules of the single state, and of the severities."""
    state, severity = entry["state"], entry["severity"]
    if not entry["id"]:
        return "identifiant vide"
    if state == "écarté":
        return "REFUSED : « écarté » est à l'auteur de la source (clé source-author), jamais au juge"
    if state not in STATES:
        return f"état « {state} » : attendu {', '.join(STATES)}"
    if not entry["finding"]:
        return "constat vide : dire ce que l'écran montre"
    if state == "tenu":
        if severity != "-":
            return "un élément tenu ne porte pas de gravité (« - »)"
        if entry["capture"] in ("", "-"):
            return "tenu sans capture : le jugement se fait sur l'écran réel"
    elif severity not in SEVERITIES:
        return f"gravité « {severity} » : un écart est {', '.join(SEVERITIES)}"
    return None


def _manifest_captures(text: str) -> set[str]:
    return {fields[1].strip() for _, fields in _records(text) if fields[0] == "CAPTURE" and len(fields) > 1}


def _matrix_cells(line: str) -> list[str]:
    return matrice._cells(line)


def judge(args: argparse.Namespace, verdict_text: str, matrix_text: str) -> int:
    """Check a verdict against the matrix, the captures and the second reading; apply it when asked."""
    try:
        rows = matrice.parse(matrix_text)
    except ValueError as error:
        _print("INVALID", "matrice", str(error))
        return 1
    by_id = {row["Identifiant"]: row for row in rows}
    entries, invalid = _verdict_entries(verdict_text)
    findings = [("INVALID", subject, reason) for subject, reason in invalid]
    grouped: dict[str, list[dict[str, str]]] = {}
    for entry in entries:
        grouped.setdefault(entry["id"], []).append(entry)
    judged: list[dict[str, str]] = []
    for identifier, group in grouped.items():
        row = by_id.get(identifier)
        if row is None:
            findings.append(("UNKNOWN", identifier, "identifiant absent de la matrice"))
        elif row["État"] == "écarté":
            findings.append(("REFUSED", identifier, "écarté par l'auteur de la source : la revue ne le juge pas"))
        elif len(group) > 1:
            same = len({e["state"] for e in group}) == 1
            findings.append(("DUPLICATE" if same else "CONTRADICTION", identifier,
                             "états " + " / ".join(e["state"] for e in group) + " : un élément n'a qu'un état, le juge tranche"))
        else:
            judged.append(group[0])
    invalid_ids = {subject for subject, _ in invalid}
    for row in rows:
        identifier = row["Identifiant"]
        if row["État"] != "écarté" and identifier not in grouped and identifier not in invalid_ids:
            findings.append(("NON-JUGE", identifier, "aucune ligne du verdict : la revue juge chaque élément de la source"))
    taken = _manifest_captures(Path(args.manifeste).read_text(encoding="utf-8")) if args.manifeste else None
    for entry in judged:
        name = entry["capture"]
        if name in ("", "-"):
            continue
        if args.captures and not (Path(args.captures) / name).is_file():
            findings.append(("SANS-FICHIER", entry["id"], f"{name} : le fichier n'existe pas sous {args.captures}"))
        elif taken is not None and name not in taken:
            findings.append(("HORS-MANIFESTE", entry["id"], f"{name} : l'exécution ne l'a pas prise"))
    findings += _second_reading(args, judged)
    for finding in findings:
        _print(*finding)
    if findings:
        return 1
    _print("OK", "", "chaque élément est jugé, sur des captures prises, et chaque tenu relu")
    return 0


def _second_reading(args: argparse.Namespace, judged: list[dict[str, str]]) -> list[tuple[str, str, str]]:
    """The `tenu` verdicts the second reader has not confirmed, one finding each."""
    held = [e for e in judged if e["state"] == "tenu"]
    for entry in held:
        if _LACK.search(entry["finding"]):
            _print("SUSPECT", entry["id"], "le constat d'un tenu décrit un manque : à relire avec soin")
    if not held:
        return []
    if not args.relecture:
        return [("A-RELIRE", e["id"], f"{e['capture']} : la seconde lecture confirme ou conteste ce tenu avant publication") for e in held]
    readings: dict[str, tuple[str, str]] = {}
    out: list[tuple[str, str, str]] = []
    for number, fields in _records(Path(args.relecture).read_text(encoding="utf-8")):
        fields = [f.strip() for f in fields]
        if len(fields) != 4 or fields[0] != "LECTURE" or fields[2] not in ("confirmé", "contesté") or not fields[3]:
            out.append(("INVALID", f"relecture ligne {number}", "attendu LECTURE, identifiant, confirmé|contesté, raison"))
        else:
            readings[fields[1]] = (fields[2], fields[3])
    for entry in held:
        reading = readings.get(entry["id"])
        if reading is None:
            out.append(("NON-RELU", entry["id"], "aucune LECTURE de la seconde lecture pour ce tenu"))
        elif reading[0] == "contesté":
            out.append(("CONTESTE", entry["id"], reading[1]))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    cover = commands.add_parser("manifeste", help="the captures of the run against the wanted path")
    cover.add_argument("parcours", help="the path file of the feature")
    cover.add_argument("manifeste", help="the manifest of the run")
    cover.add_argument("--captures", help="the folder of the capture files, checked when given")
    verdict = commands.add_parser("verdict", help="the verdict of the judge against the matrix")
    verdict.add_argument("verdict", help="the verdict of the judge")
    verdict.add_argument("--matrice", required=True, help="the matrix file of the feature")
    verdict.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md)")
    verdict.add_argument("--root", help="the project copy to read (default: the project directory)")
    verdict.add_argument("--manifeste", help="the manifest of the run: a capture cited must be in it")
    verdict.add_argument("--captures", help="the folder of the capture files, checked when given")
    verdict.add_argument("--relecture", help="the second reading of the `tenu` verdicts")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        if args.command == "manifeste":
            path_text = Path(args.parcours).read_text(encoding="utf-8")
            manifest_text = Path(args.manifeste).read_text(encoding="utf-8")
            return manifeste(path_text, manifest_text, Path(args.captures) if args.captures else None)
        return judge(args, Path(args.verdict).read_text(encoding="utf-8"), Path(args.matrice).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        print(f"revue_bout_en_bout: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
