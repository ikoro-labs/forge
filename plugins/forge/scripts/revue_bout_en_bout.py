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

import parcours  # noqa: E402

THEMES = ("clair", "sombre")
SIZES = ("bureau", "mobile")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    cover = commands.add_parser("manifeste", help="the captures of the run against the wanted path")
    cover.add_argument("parcours", help="the path file of the feature")
    cover.add_argument("manifeste", help="the manifest of the run")
    cover.add_argument("--captures", help="the folder of the capture files, checked when given")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        path_text = Path(args.parcours).read_text(encoding="utf-8")
        manifest_text = Path(args.manifeste).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"revue_bout_en_bout: {error}", file=sys.stderr)
        return 2
    return manifeste(path_text, manifest_text, Path(args.captures) if args.captures else None)


if __name__ == "__main__":
    sys.exit(main())
