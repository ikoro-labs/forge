"""Read the blameless review of an incident and refuse the one that has no fix.

    python incident.py check <review.md> [--projet DIR]
    python incident.py dir <project>

A review follows `templates/incident.md`: a title, the fields `Date`, `Origine` and `Classe`, then
four sections, `Faits` (one dated line at least), `Cause`, `Ce qui l'a laissé passer` and
`Correctif`. `check` lists every fault it finds, one per line, and exits 1 when there is one (0 when
the review is read, 2 when the file cannot be read or the call is wrong).

The class of the fix is `mécanique` (a rule a machine can check) or `jugement` (what only an agent
sees), and the form of each `- Correctif :` line follows it:

    mécanique   `#<n>`, the ticket of a deterministic check and its test, or
                `existant : <path of the check> ; <path of its test>`, a check the repository holds
    jugement    `cas : <path of the case folder>`, a case of the reference set

Any other line, a guideline or a memory note alone included, is not a fix: the review is refused.
With `--projet`, the paths a fix cites must exist under the project (and stay under it); a ticket
number is not looked up, the script reads no GitHub. A `<...>` left from the template is an unfilled
template, refused (a span between backticks is code, not a placeholder). The script does not judge
the tone of a review: "sans blâme" is for the reader.

`dir` prints the folder the key `incident-dir` of `docs/agents/usine.md` names, relative to the
project. Without the key, the step is "sans objet (clé `incident-dir` absente)" and no folder is
guessed; a value that is not a folder under the project, or a key repeated, fails (exit 1).
`factory_slo.py incidents` counts the reviews of that folder by class. The standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402  the reader of `usine.md`, found through the `sys.path` set above

KEY = "incident-dir"
ABSENT = f"sans objet (clé `{KEY}` absente)"
CLASSES = ("mécanique", "jugement")
ORIGINS = ("sev1", "sev2", "usine")
SECTIONS = ("Faits", "Cause", "Ce qui l'a laissé passer", "Correctif")
FIELDS = ("Date", "Origine", "Classe")

FIELD_LINE = re.compile(r"^-\s+(Date|Origine|Classe)\s*:\s*(.*?)\s*$")
FIX_LINE = re.compile(r"^-\s+Correctif\s*:\s*(.*?)\s*$")
FACT_LINE = re.compile(r"^-\s+(\d{4}-\d{2}-\d{2})\s*:\s*\S")
HEADING = re.compile(r"^##\s+(.*?)\s*$")
CODE_SPAN = re.compile(r"`[^`\n]*`")
PLACEHOLDER = re.compile(r"<[^<>\n]+>")
TICKET = re.compile(r"^#(\d+)$")
EXISTING = re.compile(r"^existant\s*:\s*(.+?)\s*;\s*(.+?)$")
CASE = re.compile(r"^cas\s*:\s*(.+?)$")

NOT_A_FIX = (
    "n'est ni un ticket (`#n`), ni un contrôle existant avec son test (`existant : <contrôle> ; <test>`), "
    "ni un cas du jeu de référence (`cas : <dossier>`) : une consigne ou une entrée de mémoire seule "
    "n'est pas un correctif"
)


class IncidentError(Exception):
    """A key of `usine.md` the script cannot use."""


@dataclass
class Review:
    """What a review says, once read: its class and the fixes it names."""

    klass: str | None = None
    origin: str | None = None
    day: date | None = None
    fixes: list[str] = field(default_factory=list)


def plain(word: str) -> str:
    return word.replace("é", "e").replace("è", "e").lower()


def class_of(value: str) -> str | None:
    """The class a field value names (`mecanique` is read as `mécanique`), or None."""
    for name in CLASSES:
        if plain(value) == plain(name):
            return name
    return None


def sections_of(lines: list[str]) -> dict[str, list[str]]:
    """The lines of each `## <title>` section, keyed by title."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in lines:
        if match := HEADING.match(line):
            current = found.setdefault(match.group(1), [])
        elif current is not None:
            current.append(line)
    return found


def inside(project: Path, relative: str) -> Path | None:
    """The path `relative` under `project`, or None when it is absolute or leaves the project."""
    candidate = Path(relative)
    if candidate.is_absolute():
        return None
    root = project.resolve()
    resolved = (root / candidate).resolve()
    return resolved if resolved == root or root in resolved.parents else None


def fix_errors(fix: str, klass: str | None, project: Path | None) -> list[str]:
    """Why a `Correctif` value is refused for this class, or no error."""
    ticket, existing, case = TICKET.match(fix), EXISTING.match(fix), CASE.match(fix)
    if not (ticket or existing or case):
        return [f"`Correctif : {fix}` {NOT_A_FIX}"]
    form = "mécanique" if ticket or existing else "jugement"
    if klass is not None and form != klass:
        return [f"`Correctif : {fix}` est de la classe {form} et la revue dit la classe {klass} : une revue, une classe"]
    paths = [existing.group(1), existing.group(2)] if existing else [case.group(1)] if case else []
    errors = []
    for relative in paths:
        if project is None:
            continue
        found = inside(project, relative)
        if found is None:
            errors.append(f"`{relative}` sort du projet ou n'est pas un chemin relatif à sa racine")
        elif not found.exists():
            errors.append(f"`{relative}` n'existe pas dans le projet : un correctif cite ce que le dépôt contient")
    return errors


def read(text: str, project: Path | None = None) -> tuple[Review, list[str]]:
    """The review and every fault found in `text`; the faults are empty when the review is read."""
    lines = text.splitlines()
    review, errors = Review(), []
    if not any(line.startswith("# ") and line[2:].strip() for line in lines):
        errors.append("le titre manque (`# <ce qui s'est passé>`)")
    if PLACEHOLDER.search(CODE_SPAN.sub("", text)):
        errors.append("un `<...>` du gabarit n'est pas rempli : la revue est le gabarit tel quel")
    values: dict[str, str] = {}
    for line in lines:
        if match := FIELD_LINE.match(line):
            values.setdefault(match.group(1), match.group(2))
    for name in FIELDS:
        if name not in values:
            errors.append(f"le champ `{name}` manque (`- {name} : ...`)")
    if "Date" in values:
        try:
            review.day = date.fromisoformat(values["Date"])
        except ValueError:
            errors.append(f"`Date : {values['Date']}` n'est pas une date AAAA-MM-JJ")
    if "Origine" in values:
        if values["Origine"] in ORIGINS:
            review.origin = values["Origine"]
        else:
            errors.append(f"`Origine : {values['Origine']}` n'est pas l'une de {', '.join(ORIGINS)}")
    if "Classe" in values:
        review.klass = class_of(values["Classe"])
        if review.klass is None:
            errors.append(f"`Classe : {values['Classe']}` n'est pas l'une de {' et '.join(CLASSES)}")
    sections = sections_of(lines)
    for name in SECTIONS:
        if name not in sections:
            errors.append(f"la section `## {name}` manque")
        elif not any(line.strip() for line in sections[name]):
            errors.append(f"la section `## {name}` est vide")
    if "Faits" in sections and any(line.strip() for line in sections["Faits"]):
        if not any(FACT_LINE.match(line) for line in sections["Faits"]):
            errors.append("la section `## Faits` n'a aucun fait daté (`- AAAA-MM-JJ : ...`)")
    fixes = [match.group(1) for line in sections.get("Correctif", []) if (match := FIX_LINE.match(line))]
    if "Correctif" in sections and not fixes:
        errors.append("la revue n'a aucun correctif (`- Correctif : ...`) : une revue sans correctif est refusée")
    for fix in fixes:
        if fix:
            errors += fix_errors(fix, review.klass, project)
        else:
            errors.append("une ligne `Correctif :` est vide")
    review.fixes = [fix for fix in fixes if fix]
    return review, errors


def check(text: str, project: Path | None = None) -> list[str]:
    """Every fault of the review in `text`, none when it is read."""
    return read(text, project)[1]


def incident_dir(project: Path) -> Path | None:
    """The folder of the key `incident-dir`, under `project`; None when the key is absent."""
    values = usine.load(project).get(KEY)
    if not values:
        return None
    if len(values) > 1:
        raise IncidentError(f"la clé `{KEY}` est déclarée {len(values)} fois : une seule ligne")
    folder = inside(project, values[0])
    if folder is None or folder == project.resolve():
        raise IncidentError(f"clé `{KEY}` : `{values[0]}` n'est pas un dossier du projet, relatif à sa racine")
    return folder


def review_files(folder: Path) -> list[Path]:
    """The reviews of a folder, by name: every Markdown file but a `README.md`."""
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.glob("*.md") if path.name.lower() != "readme.md")


def run_check(args: argparse.Namespace) -> int:
    try:
        text = args.fichier.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"Lecture impossible : {error}", file=sys.stderr)
        return 2
    review, errors = read(text, args.projet)
    if errors:
        print(f"Revue refusée : {args.fichier}")
        for fault in errors:
            print(f"- {fault}")
        return 1
    print(f"Revue lue : classe {review.klass}, {len(review.fixes)} correctif(s).")
    return 0


def run_dir(args: argparse.Namespace) -> int:
    try:
        folder = incident_dir(args.projet)
    except IncidentError as error:
        print(f"Calcul impossible : {error}", file=sys.stderr)
        return 1
    if folder is None:
        print(f"Revues d'incident : {ABSENT}.")
        return 0
    print(folder.relative_to(args.projet.resolve()).as_posix())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="incident.py", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="commande", required=True)
    checking = commands.add_parser("check", help="lit une revue et refuse celle qui n'a pas de correctif")
    checking.add_argument("fichier", type=Path, help="la revue, en Markdown")
    checking.add_argument("--projet", type=Path, help="le projet : les chemins cités doivent y exister")
    where = commands.add_parser("dir", help="dit le dossier des revues, d'après la clé `incident-dir`")
    where.add_argument("projet", type=Path, help="le dossier du projet")
    args = parser.parse_args(argv)
    return run_check(args) if args.commande == "check" else run_dir(args)


if __name__ == "__main__":
    sys.exit(main())
