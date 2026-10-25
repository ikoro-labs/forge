"""Check and read the traceability matrix of a feature (`matrice.md`): one row per identifier of the source.

    python matrice.py [--usine FILE] [--root DIR] [--reste | --sans-ticket | --cloture] <matrice-file>

The format, which the skills `feature-design`, `feature-verify` and `feature-close` and the template
`templates/features/matrice.md` repeat:

- One Markdown table, with the columns `Identifiant | Lot | Ticket | Test | Écran | Capture | État | Jugé le`,
  in that order, and one row per identifier of the source (the contract of `source_ids.py`: `EXI-01`,
  `RG-3.1`, `C01`, `G0`). `Lot` is the batch of the spec (empty: « sans lot »), `Ticket` the issue that
  covers the identifier, `Test` the test that proves it, `Écran` the screen of `parcours.md`, `Capture`
  the file of the capture, `Jugé le` the ISO date of the last judgment.
- **One state rule.** `tenu`: the criterion is held in full. `partiel`: held in part. `absent`: not
  built. `contraire`: the product does the opposite, even in part. `écarté`: set aside by the author of
  the source, with the agreement cited. Nothing else is a state.
- A row `tenu` with neither `Test` nor `Capture` has no proof and is refused. A row `tenu`, `partiel`,
  `contraire` or `écarté` carries the ISO date of its judgment; `absent` may have none (the matrix a
  design writes judges nothing).
- A row `écarté` is accepted only when a line `Écarté : <identifiant> | accord : <fichier> | <AAAA-MM-JJ>
  | <rôle>` outside the table cites the same agreement as `source_ids.py` demands (an existing file that
  names the identifier, a role or account of the key `source-author`). The script reuses that parser.

The identifiers are checked against the source files of the key `product-source` of
`docs/agents/usine.md` when it is declared (Markdown only; any other format is BLOCKED): an identifier
of the matrix that the source does not hold is UNKNOWN, an identifier of the source with no row is
MISSING. Without the key the check prints `sans objet (clé product-source absente)` and passes no
identifier as checked. The spec is never a reference.

Default mode, one line per finding, fields separated by tabs: INVALID (identifier or empty, reason),
UNKNOWN, DUPLICATE, MISSING, REFUSED (an exclusion line not accepted), BLOCKED or OK. Exit 0 when none of
the first six is printed, 1 otherwise, 2 when a file is unreadable or the call wrong.

- `--reste`: what remains to hold, per batch and per state: `RESTE`, batch, state, the identifiers; then
  one line `COUVERTURE`, `<held>/<total>`, the percentage. A row is covered when `tenu` or `écarté`. An
  identifier of the source with no row counts in the total and remains as `absent`, under « sans lot ».
  Exit 0 whatever the figures; the command reports, it does not judge.
- `--sans-ticket`: the identifiers whose `Ticket` is empty and whose state is not `écarté`, and every
  identifier of the source with no row (it has no ticket either), one `SANS-TICKET` line each, or `NONE`.
  Exit 1 when there is one.
- `--cloture`: `REFUSE` lines naming every row that is neither `tenu` nor `écarté`, and any finding of the
  default mode; `CLORE` and exit 0 only at 100 % and with no finding.

The output is UTF-8. The standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402
from source_ids import AUTHOR_KEY, IDENTIFIER, MARKDOWN, SOURCE_KEY, _exclusions, ids_of_source  # noqa: E402

COLUMNS = ("Identifiant", "Lot", "Ticket", "Test", "Écran", "Capture", "État", "Jugé le")
STATES = ("tenu", "partiel", "absent", "contraire", "écarté")
COVERED = ("tenu", "écarté")
NO_BATCH = "sans lot"
_ID = re.compile(rf"^{IDENTIFIER}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SEPARATOR = re.compile(r"^\|?[\s:|-]+\|?$")


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse(text: str) -> list[dict[str, str]]:
    """The rows of the matrix table, in order: each column's value, plus `_line` (the row number in the file).

    Raises ValueError when no table holds the columns of the format; the message says what is wrong."""
    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced or not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if header is None:
            if cells[0] != COLUMNS[0]:
                continue
            if tuple(cells) != COLUMNS:
                missing = [c for c in COLUMNS if c not in cells]
                raise ValueError(
                    "colonnes attendues dans l'ordre : " + " | ".join(COLUMNS)
                    + (" ; absentes : " + ", ".join(missing) if missing else "")
                )
            header = cells
        elif _SEPARATOR.match(line.strip()):
            continue
        else:
            cells = (cells + [""] * len(header))[: len(header)]
            row = dict(zip(header, cells))
            row["Identifiant"] = row["Identifiant"].strip("`*[] ")
            row["_line"] = str(number)
            rows.append(row)
    if header is None:
        raise ValueError("aucun tableau : l'en-tête s'écrit « | " + " | ".join(COLUMNS) + " | »")
    return rows


def check(rows: list[dict[str, str]], excluded: set[str]) -> list[tuple[str, str, str]]:
    """The findings on the rows as (status, identifier, reason): INVALID and DUPLICATE."""
    findings: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for row in rows:
        identifier = row["Identifiant"]
        if not _ID.match(identifier):
            findings.append(("INVALID", identifier, "identifiant illisible : un identifiant de la source (EXI-01, RG-3.1, C01, G0)"))
            continue
        if identifier in seen:
            findings.append(("DUPLICATE", identifier, "plusieurs lignes pour le même identifiant : une seule par identifiant"))
            continue
        seen.add(identifier)
        state = row["État"]
        if state not in STATES:
            findings.append(("INVALID", identifier, f"état « {state} » : attendu {', '.join(STATES)}"))
            continue
        if state == "tenu" and not (row["Test"] or row["Capture"]):
            findings.append(("INVALID", identifier, "état tenu sans preuve : ni test ni capture"))
        if state != "absent" and not _DATE.match(row["Jugé le"]):
            findings.append(("INVALID", identifier, f"état {state} : la date du jugement s'écrit AAAA-MM-JJ"))
        if state == "écarté" and identifier not in excluded:
            findings.append(("INVALID", identifier, "état écarté sans ligne « Écarté : » acceptée (accord de l'auteur de la source)"))
        if state != "écarté" and identifier in excluded:
            findings.append(("INVALID", identifier, f"un accord écarte cet identifiant, l'état est {state}"))
    return findings


def coverage(rows: list[dict[str, str]]) -> tuple[int, int]:
    """The rows held (`tenu` or `écarté`) and the total."""
    return sum(1 for r in rows if r["État"] in COVERED), len(rows)


def remaining(rows: list[dict[str, str]]) -> dict[str, dict[str, list[str]]]:
    """What is not covered, per batch then per state, in the order of the matrix."""
    out: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        if row["État"] in COVERED:
            continue
        batch = row["Lot"] or NO_BATCH
        out.setdefault(batch, {}).setdefault(row["État"] or "(vide)", []).append(row["Identifiant"])
    return out


def with_missing(rows: list[dict[str, str]], findings: list[tuple[str, str, str, str]]) -> list[dict[str, str]]:
    """The rows plus one virtual row per MISSING identifier: no batch, no ticket, state `absent`.

    An identifier of the source with no row is work to do like an `absent` row; `--reste` and
    `--sans-ticket` count it, so that an incomplete matrix does not read as complete."""
    virtual = [
        {"Identifiant": first, "Lot": "", "Ticket": "", "Test": "", "Écran": "", "Capture": "", "État": "absent", "Jugé le": "", "_line": ""}
        for status, first, _second, _detail in findings
        if status == "MISSING"
    ]
    return rows + virtual


def _print(status: str, first: str = "", second: str = "", detail: str = "") -> None:
    print(f"{status}\t{first}\t{second}\t{detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("matrice", help="the matrix file of the feature")
    parser.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md)")
    parser.add_argument("--root", help="the project copy to read (default: the project directory)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--reste", action="store_true", help="what remains to hold, per batch and per state")
    mode.add_argument("--sans-ticket", action="store_true", help="the identifiers no ticket covers")
    mode.add_argument("--cloture", action="store_true", help="refuse unless every row is tenu or écarté")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = Path(args.root) if args.root else usine.project_root()
    config_file = Path(args.usine) if args.usine else root / usine.CONFIG_PATH
    reference: list[str] | None = None
    notes: list[str] = []
    findings: list[tuple[str, str, str, str]] = []
    try:
        try:
            config = usine.parse(config_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if args.usine:
                raise
            config = {}
        text = Path(args.matrice).read_text(encoding="utf-8")
        sources = config.get(SOURCE_KEY)
        if sources:
            blocked = [name for name in sources if not name.lower().endswith(MARKDOWN)]
            for name in blocked:
                findings.append(("BLOCKED", name, "", "source non lisible en Markdown : demander un export Markdown à son auteur"))
            if not blocked:
                reference = [i for name in sources for i in ids_of_source((root / name).read_text(encoding="utf-8"))]
        else:
            notes.append(f"sans objet (clé {SOURCE_KEY} absente) : identifiants non vérifiés")
    except (OSError, UnicodeDecodeError) as error:
        print(f"matrice: {error}", file=sys.stderr)
        return 2
    authors = config.get(AUTHOR_KEY, [])
    table, accepted, refused = _exclusions(text, authors, root)
    try:
        rows = parse(table)
    except ValueError as error:
        _print("INVALID", "", "", str(error))
        return 1
    for identifier, agreement, reason in refused:
        findings.append(("REFUSED", identifier, agreement, reason))
    for status, identifier, reason in check(rows, {identifier for identifier, *_ in accepted}):
        findings.append((status, identifier, "", reason))
    if reference is not None:
        held = {r["Identifiant"] for r in rows}
        for row in rows:
            if _ID.match(row["Identifiant"]) and row["Identifiant"] not in reference:
                findings.append(("UNKNOWN", row["Identifiant"], "", "identifiant absent de la source"))
        for identifier in reference:
            if identifier not in held:
                findings.append(("MISSING", identifier, "", "identifiant de la source sans ligne dans la matrice"))
    if not authors:
        notes.append(f"sans objet (clé {AUTHOR_KEY} absente) : aucun élément ne s'écarte")
    return _report(args, rows, findings, notes)


def _report(args: argparse.Namespace, rows: list[dict[str, str]], findings: list[tuple[str, str, str, str]], notes: list[str]) -> int:
    if args.reste:
        completed = with_missing(rows, findings)
        for batch, states in remaining(completed).items():
            for state, ids in states.items():
                _print("RESTE", batch, state, ", ".join(ids))
        held, total = coverage(completed)
        _print("COUVERTURE", f"{held}/{total}", f"{100 * held // total if total else 0} %")
        for note in notes:
            print(note)
        return 0
    if args.sans_ticket:
        open_ids = [r["Identifiant"] for r in with_missing(rows, findings) if not r["Ticket"] and r["État"] != "écarté"]
        for identifier in open_ids:
            _print("SANS-TICKET", identifier)
        if not open_ids:
            _print("NONE", "", "", "chaque identifiant a un ticket ou est écarté")
        for note in notes:
            print(note)
        return 1 if open_ids else 0
    if args.cloture:
        for status, first, second, detail in findings:
            _print(status, first, second, detail)
        open_rows = [r for r in rows if r["État"] not in COVERED]
        for row in open_rows:
            _print("REFUSE", row["Identifiant"], row["État"] or "(vide)", "ni tenu ni écarté : la clôture exige 100 %")
        held, total = coverage(rows)
        if not total:
            _print("REFUSE", "", "", "matrice vide : aucun identifiant à clore")
        if findings or open_rows or not total:
            return 1
        _print("CLORE", f"{held}/{total}", "100 %", "chaque ligne est tenue ou écartée")
        for note in notes:
            print(note)
        return 0
    if not findings:
        _print("OK", "", "", "chaque ligne a un état, une preuve quand elle est tenue, et un identifiant connu")
    for finding in findings:
        _print(*finding)
    for note in notes:
        print(note)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
