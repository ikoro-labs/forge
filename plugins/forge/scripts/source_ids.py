"""List the elements of the business source that a feature spec does not take up by their identifier.

    python source_ids.py [--usine FILE] [--root DIR] <spec-file>

The contract, which the skill `feature-spec` repeats:

- An **identifier** is `LETTERS-NUMBER`, capitals and digits, then digits joined by dots: `EX-12`,
  `CT-3`, `RG-3.1`. An **identified element** of the source is a line of the Markdown source that
  begins with an identifier, after at most a list marker, heading marks, a table bar, bold marks or
  a bracket. An identifier cited in the middle of a sentence is not an element. Lines inside a
  fenced code block are ignored.
- The spec **takes up** an element when it holds its identifier as a whole token (`EX-1` is not found
  in `EX-12`, `EX-1.2` or `AEX-1`).
- A spec sets an element aside with one line each, which the script reads and which never counts as
  taking the element up: `Écarté : <identifiant> | accord : <fichier> | <AAAA-MM-JJ> | <rôle>`
  (a list marker may precede it). It is accepted when the file exists and names the identifier,
  the date is ISO, and the role (or GitHub account, with or without `@`) is a value of the key
  `source-author`.
- An element with no identifier in the source is given one by the spec, in the same form, with the
  source line it stands for; the script cannot see those and does not count them.

The keys of `docs/agents/usine.md` it reads: `product-source` (the source files, Markdown only: any
other format is BLOCKED, and nothing converts it) and `source-author`.

One line per finding, `<status>`, `<identifier or file>`, `<file or agreement>` and `<detail>`
separated by tabs: BLOCKED (a source that is not Markdown), EXCLUDED (an element set aside with a
valid agreement), REFUSED (an exclusion not accepted, the detail says why), MISSING (an identifier of
the source that the spec does not take up, with its source file) or NONE (nothing missing). Exit code
0 when no BLOCKED, REFUSED or MISSING line is printed, 1 otherwise, 2 when a file is unreadable or
the call wrong. A missing key prints `sans objet (clé <nom> absente)`; without `source-author` the
line adds that no element is set aside. The output is UTF-8. The standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402

SOURCE_KEY = "product-source"
AUTHOR_KEY = "source-author"
IDENTIFIER = r"[A-Z][A-Z0-9]*-\d+(?:\.\d+)*"
MARKDOWN = (".md", ".markdown")

_ELEMENT = re.compile(
    rf"^\s*(?:(?:[-*+]|\d+\.)\s+(?:\[[ xX]\]\s+)?|#{{1,6}}\s+|\|\s*)?(?:\*\*|__|`)?\[?({IDENTIFIER})(?![\w-]|\.\d)"
)
_EXCLUSION = re.compile(
    rf"^\s*(?:[-*+]\s+)?Écarté\s*:\s*({IDENTIFIER})\s*\|\s*accord\s*:\s*(.+?)\s*\|\s*(\S+)\s*\|\s*(.+?)\s*$"
)
_EXCLUSION_START = re.compile(r"^\s*(?:[-*+]\s+)?Écarté\s*:")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def ids_of_source(text: str) -> list[str]:
    """The identifiers of the identified elements of a Markdown source, in order and without repeat."""
    found: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        if (match := _ELEMENT.match(line)) and match.group(1) not in found:
            found.append(match.group(1))
    return found


def mentions(text: str, identifier: str) -> bool:
    """Whether the text holds the identifier as a whole token."""
    return re.search(rf"(?<![\w-]){re.escape(identifier)}(?![\w-]|\.\d)", text) is not None


def _print(status: str, first: str = "", second: str = "", detail: str = "") -> None:
    print(f"{status}\t{first}\t{second}\t{detail}")


def _exclusions(spec: str, authors: list[str], root: Path) -> tuple[str, list[tuple[str, ...]], list[tuple[str, ...]]]:
    """The spec without its exclusion lines, the accepted exclusions and the refused ones."""
    kept: list[str] = []
    accepted: list[tuple[str, ...]] = []
    refused: list[tuple[str, ...]] = []
    wanted = {a.lower().lstrip("@") for a in authors}
    for line in spec.splitlines():
        if not _EXCLUSION_START.match(line):
            kept.append(line)
            continue
        match = _EXCLUSION.match(line)
        if not match:
            refused.append(("", "", "ligne d'exclusion illisible : " + line.strip()))
            continue
        identifier, agreement, date, role = match.groups()
        if not authors:
            reason = f"clé {AUTHOR_KEY} absente, aucun élément ne s'écarte"
        elif role.lower().lstrip("@") not in wanted:
            reason = f"{role} n'est pas une valeur de la clé {AUTHOR_KEY}"
        elif not _DATE.match(date):
            reason = f"date {date} : attendu AAAA-MM-JJ"
        else:
            try:
                written = (root / agreement).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                reason = "fichier d'accord introuvable ou illisible"
            else:
                if mentions(written, identifier):
                    accepted.append((identifier, agreement, f"{date} {role}"))
                    continue
                reason = "le fichier d'accord ne cite pas l'identifiant"
        refused.append((identifier, agreement, reason))
    return "\n".join(kept), accepted, refused


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("spec", help="the spec file of the feature")
    parser.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md)")
    parser.add_argument("--root", help="the project copy to read (default: the project directory)")
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
        spec = Path(args.spec).read_text(encoding="utf-8")
        sources = config.get(SOURCE_KEY)
        if not sources:
            print(f"sans objet (clé {SOURCE_KEY} absente)")
            return 0
        blocked = [name for name in sources if not name.lower().endswith(MARKDOWN)]
        for name in blocked:
            _print("BLOCKED", name, "", "source non lisible en Markdown : demander un export Markdown à son auteur, aucun agent ne la convertit")
        if blocked:
            return 1
        elements: dict[str, str] = {}
        for name in sources:
            for identifier in ids_of_source((root / name).read_text(encoding="utf-8")):
                elements.setdefault(identifier, name)
    except (OSError, UnicodeDecodeError) as error:
        print(f"source_ids: {error}", file=sys.stderr)
        return 2
    authors = config.get(AUTHOR_KEY, [])
    taken, accepted, refused = _exclusions(spec, authors, root)
    excluded = {identifier for identifier, *_ in accepted}
    missing = [i for i in elements if i not in excluded and not mentions(taken, i)]
    for identifier, agreement, detail in accepted:
        _print("EXCLUDED", identifier, agreement, detail)
    for identifier, agreement, detail in refused:
        _print("REFUSED", identifier, agreement, detail)
    for identifier in missing:
        _print("MISSING", identifier, elements[identifier])
    if not (accepted or refused or missing):
        _print("NONE", "", "", "aucun identifiant de la source n'est absent de la spec")
    if not authors:
        print(f"sans objet (clé {AUTHOR_KEY} absente) : aucun élément ne s'écarte")
    return 1 if (refused or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
