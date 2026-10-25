"""Check the wanted path of a feature (`parcours.md`), screen by screen.

    python parcours.py [--spec FILE] [--usine FILE] [--root DIR] <parcours-file>

The format, which the skill `feature-design` and the template `templates/features/parcours.md` repeat:

- One screen per heading `## Écran <n> : <name>`, numbered from 1 in order with no gap.
- Under it, four list items, each `- <Field> : <value>`:
  `Voit` (the exact labels the user sees, each between « and », separated by `;`), `Fait` (what the
  user does there), `Suivant` (`Écran <n>` of the path, or `fin`) and `Source` (the identifiers of the
  business source the screen holds, at least one, separated by commas). The last screen ends with `fin`.
- An identifier follows the contract of `source_ids.py` (`EXI-01`, `RG-3.1`, `C01`, `G0`). The matrix
  of the feature does not exist yet: the path cites identifiers of the source elements, not matrix rows.

The identifiers cited are checked against the source files of the key `product-source` of
`docs/agents/usine.md` when it is declared (Markdown only; any other format is BLOCKED), otherwise
against the spec given by `--spec`; with neither, the check prints `sans objet (clé product-source
absente)` and never passes the identifiers as checked. The format is checked in every case.

One line per finding, fields separated by tabs: INVALID (screen, reason), UNKNOWN (screen, identifier
absent from the reference), BLOCKED (a source that is not Markdown) or OK (nothing found). Exit code 0
when no INVALID, UNKNOWN or BLOCKED line is printed, 1 otherwise, 2 when a file is unreadable or the
call wrong. The output is UTF-8. The standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402
from source_ids import IDENTIFIER, MARKDOWN, SOURCE_KEY, ids_of_source, mentions  # noqa: E402

FIELDS = ("Voit", "Fait", "Suivant", "Source")
_SCREEN = re.compile(r"^##\s+Écran\s+(\d+)\s*:\s*(\S.*?)\s*$")
_ANY_SCREEN = re.compile(r"^##\s+Écran\b")
_FIELD = re.compile(r"^\s*[-*+]\s+(Voit|Fait|Suivant|Source)\s*:\s*(.*?)\s*$")
_LABEL = re.compile(r"«\s*(.+?)\s*»")
_NEXT = re.compile(r"^(?:Écran\s+(\d+)|fin)$")
_ID = re.compile(rf"(?<![\w-])({IDENTIFIER})(?![\w-]|\.\d)")


def parse(text: str) -> list[dict]:
    """The screens of a path file, in order: number (or None), name, line, and each field's value."""
    screens: list[dict] = []
    for line in text.splitlines():
        if _ANY_SCREEN.match(line):
            match = _SCREEN.match(line)
            screens.append({"number": int(match.group(1)) if match else None,
                            "name": match.group(2) if match else line.lstrip("# ").strip(), "fields": {}})
        elif screens and (field := _FIELD.match(line)):
            screens[-1]["fields"].setdefault(field.group(1), field.group(2))
    return screens


def labels_of(text: str) -> list[str]:
    """The exact labels of the path, in order and without repeat: the vocabulary the glossary takes up."""
    found: list[str] = []
    for screen in parse(text):
        for label in _LABEL.findall(screen["fields"].get("Voit", "")):
            if label not in found:
                found.append(label)
    return found


def check(text: str) -> tuple[list[tuple[str, str]], dict[str, list[str]]]:
    """The format findings as (screen, reason), and the identifiers each screen cites."""
    problems: list[tuple[str, str]] = []
    cited: dict[str, list[str]] = {}
    screens = parse(text)
    if not screens:
        return [("", "aucun écran : un écran s'écrit « ## Écran 1 : <nom> »")], cited
    for position, screen in enumerate(screens, start=1):
        name = f"Écran {position}" if screen["number"] is None else f"Écran {screen['number']}"
        fields = screen["fields"]
        if screen["number"] != position:
            problems.append((name, f"numéro attendu {position} : les écrans se suivent de 1, sans trou"))
        for field in FIELDS:
            if not fields.get(field):
                problems.append((name, f"champ « {field} » absent ou vide"))
        if fields.get("Voit") and not _LABEL.search(fields["Voit"]):
            problems.append((name, "champ « Voit » : les libellés s'écrivent entre « et », tels qu'à l'écran"))
        following = fields.get("Suivant")
        if following:
            match = _NEXT.match(following)
            if not match:
                problems.append((name, f"champ « Suivant » : « {following} », attendu « Écran <n> » ou « fin »"))
            elif match.group(1) and not 1 <= int(match.group(1)) <= len(screens):
                problems.append((name, f"champ « Suivant » : Écran {match.group(1)} n'existe pas dans le parcours"))
            elif position == len(screens) and match.group(1):
                problems.append((name, "le dernier écran finit par « Suivant : fin »"))
        ids = _ID.findall(fields.get("Source", ""))
        if fields.get("Source") and not ids:
            problems.append((name, "champ « Source » : au moins un identifiant de la source (EXI-01, RG-3.1, C01...)"))
        cited[name] = ids
    return problems, cited


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("parcours", help="the path file of the feature")
    parser.add_argument("--spec", help="the spec file, the reference when the key product-source is absent")
    parser.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md)")
    parser.add_argument("--root", help="the project copy to read (default: the project directory)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = Path(args.root) if args.root else usine.project_root()
    config_file = Path(args.usine) if args.usine else root / usine.CONFIG_PATH
    reference: list[str] | None = None
    notes: list[str] = []
    findings: list[str] = []
    try:
        try:
            config = usine.parse(config_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if args.usine:
                raise
            config = {}
        text = Path(args.parcours).read_text(encoding="utf-8")
        sources = config.get(SOURCE_KEY)
        if sources:
            blocked = [name for name in sources if not name.lower().endswith(MARKDOWN)]
            for name in blocked:
                findings.append(f"BLOCKED\t{name}\t\tsource non lisible en Markdown : demander un export Markdown à son auteur")
            if not blocked:
                reference = [i for name in sources for i in ids_of_source((root / name).read_text(encoding="utf-8"))]
        elif args.spec:
            spec = Path(args.spec).read_text(encoding="utf-8")
            reference = sorted({m for m in _ID.findall(spec)})
            notes.append(f"clé {SOURCE_KEY} absente : identifiants vérifiés contre la spec")
        else:
            notes.append(f"sans objet (clé {SOURCE_KEY} absente) : identifiants non vérifiés, ni source ni spec")
    except (OSError, UnicodeDecodeError) as error:
        print(f"parcours: {error}", file=sys.stderr)
        return 2
    problems, cited = check(text)
    for screen, reason in problems:
        findings.append(f"INVALID\t{screen}\t\t{reason}")
    if reference is not None:
        for screen, ids in cited.items():
            for identifier in dict.fromkeys(ids):
                if identifier not in reference:
                    findings.append(f"UNKNOWN\t{screen}\t{identifier}\tidentifiant absent de la référence")
    if not findings:
        findings.append("OK\t\t\tchaque écran est complet et cite un identifiant")
    for line in findings:
        print(line)
    for note in notes:
        print(note)
    return 0 if findings[0].startswith("OK") else 1


if __name__ == "__main__":
    sys.exit(main())
