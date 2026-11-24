"""Compare the direct dependencies a PR adds with the packages the project allows (the `stack` key).

    python stack_check.py [--usine FILE] [--root DIR] --base REF --head REF

Run from a clone of the project (`--root`, the current directory by default). The `stack` key of
`docs/agents/usine.md` names a file of lines `<ecosystem> | <package> | <source>`, the ecosystem
being `pypi` or `npm` and the source the accepted decision (an ADR, a session) that allows the
package. The script reads the path of that file from `--usine`, which `forge:qc-gate` points at
`usine.md` on the base (a PR cannot lift the list it is judged by), and the content of the file at
`--head`: a head without the file is an empty list. Without the `stack` key or the `lockfile` key,
the step is "sans objet" and the exit code is 0.

One line per result, `<status>`, `<subject>`, `<package>` and `<detail>` separated by tabs. The
status is INVALID (a malformed list line, at its number, or a malformed lockfile or key). The
script launches no command and opens no network access. Exit code 0 when nothing is refused, 2 when
a line is INVALID or the call is wrong. The standard library only.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402  hooks/ is not importable until the path insertion above
from lockfiles import direct_dependencies, normalize_pypi, read_at  # noqa: E402  shared with `lockfile_age.py`

STACK_KEY = "stack"
LOCKFILE_KEY = "lockfile"
ECOSYSTEMS = ("pypi", "npm")


@dataclass(frozen=True)
class Entry:
    number: int  # the line number in the stack file
    ecosystem: str
    package: str
    source: str


def invalid(subject: str, why: str) -> str:
    return f"INVALID\t{subject}\t-\t{why}"


def parse_stack(text: str, path: str) -> tuple[list[Entry], list[str]]:
    """The entries of a stack file, and an INVALID line per malformed line; a line is never completed."""
    entries: list[Entry] = []
    problems: list[str] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        subject = f"{path}:{number}"
        fields = [field.strip() for field in raw.split("|", 2)]
        if len(fields) < 3:
            problems.append(invalid(subject, f"moins de trois champs : `<écosystème> | <paquet> | <source>`, lu : {raw.strip()}"))
        elif fields[0] not in ECOSYSTEMS:
            problems.append(invalid(subject, f"écosystème inconnu `{fields[0]}` ({', '.join(ECOSYSTEMS)})"))
        elif not fields[1]:
            problems.append(invalid(subject, "le nom du paquet est vide"))
        else:
            entries.append(Entry(number, fields[0], fields[1], fields[2]))
    return entries, problems


def added_dependencies(root: Path, path: str, ecosystem: str, base: str, head: str) -> list[str]:
    """The direct dependencies the lock at `head` declares and the one at `base` did not."""
    before, after = read_at(root, base, path), read_at(root, head, path)
    known = set(direct_dependencies(before, ecosystem)) if before else set()
    return [name for name in (direct_dependencies(after, ecosystem) if after else []) if name not in known]


def canonical(ecosystem: str, name: str) -> str:
    """The name that makes two spellings one package: normalized for pypi, left as written for npm."""
    return normalize_pypi(name) if ecosystem == "pypi" else name


def judge(ecosystem: str, name: str, lock_path: str, stack_path: str, entries: list[Entry]) -> str:
    """The line for one added direct dependency, against the entries of the head's list."""
    wanted_name = canonical(ecosystem, name)
    listed = [entry for entry in entries if entry.ecosystem == ecosystem and canonical(ecosystem, entry.package) == wanted_name]
    if not listed:
        wanted = f"{ecosystem} | {name} | <ADR ou séance>"
        return f"UNLISTED\t{lock_path}\t{ecosystem} {name}\tligne à écrire : `{wanted}` dans {stack_path}"
    if not any(entry.source for entry in listed):
        lines = ", ".join(str(entry.number) for entry in listed)
        return f"NO SOURCE\t{lock_path}\t{ecosystem} {name}\tligne {lines} de {stack_path} sans source : écrire l'ADR ou la séance qui l'autorise"
    source = next(entry.source for entry in listed if entry.source)
    return f"OK\t{lock_path}\t{ecosystem} {name}\tdans {stack_path}, source : {source}"


def added_entries(root: Path, base: str, stack_path: str, entries: list[Entry]) -> list[str]:
    """An ADDED line per entry the head's list has and the base's list did not, with its source."""
    try:
        before = parse_stack(read_at(root, base, stack_path) or "", stack_path)[0]
    except UnicodeDecodeError:
        before = []  # an unreadable base list holds nothing the head can be compared to
    known = {(entry.ecosystem, entry.package, entry.source) for entry in before}
    return [
        f"ADDED\t{stack_path}:{entry.number}\t{entry.ecosystem} {entry.package}\t{entry.source or 'sans source'}"
        for entry in entries
        if (entry.ecosystem, entry.package, entry.source) not in known
    ]


def evaluate(root: Path, lock_entry: str, base: str, head: str, stack_path: str, entries: list[Entry]) -> list[str]:
    parts = usine.split_value(lock_entry, 2)
    if parts is None:
        return [invalid(lock_entry, f"il manque une partie à l'entrée de la clé {LOCKFILE_KEY} : `<chemin> | <écosystème>`")]
    path, ecosystem = parts
    if ecosystem not in ECOSYSTEMS:
        return [invalid(path, f"écosystème inconnu `{ecosystem}` ({', '.join(ECOSYSTEMS)})")]
    try:
        added = added_dependencies(root, path, ecosystem, base, head)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        return [invalid(path, f"illisible comme un lockfile `{ecosystem}` ({type(error).__name__} : {error})")]
    if not added:
        return [f"NONE\t{path}\t-\taucun paquet direct ajouté"]
    return [line for name in added if (line := judge(ecosystem, name, path, stack_path, entries))]


def uncovered(lock_entries: list[str], entries: list[Entry], stack_path: str) -> list[str]:
    """A NOT RUN line per ecosystem the list names and no `lockfile` entry reads: nothing there is compared."""
    covered = {parts[1] for entry in lock_entries if (parts := usine.split_value(entry, 2))}
    named = dict.fromkeys(entry.ecosystem for entry in entries)
    return [
        f"NOT RUN\t{stack_path}\t{ecosystem}\taucune entrée `<chemin> | {ecosystem}` dans la clé {LOCKFILE_KEY} : "
        f"les paquets {ecosystem} ajoutés ne sont pas comparés"
        for ecosystem in named
        if ecosystem not in covered
    ]


def read_config(args: argparse.Namespace) -> dict[str, list[str]]:
    """The keys of the usine file: `--usine` when given, else `usine.md` as the base has it (never the head's)."""
    if args.usine:
        try:
            return usine.parse(Path(args.usine).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
    text = read_at(Path(args.root), args.base, usine.CONFIG_PATH.as_posix())
    return usine.parse(text) if text else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--base", required=True, help="the git ref the PR starts from")
    parser.add_argument("--head", required=True, help="the git ref of the PR's head")
    parser.add_argument("--root", default=".", help="a clone of the project (default: the current directory)")
    parser.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md at --base)")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    for ref in (args.base, args.head):
        found = subprocess.run(
            ["git", "-C", args.root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], capture_output=True
        )
        if found.returncode != 0:
            print(f"stack_check: la référence git `{ref}` est introuvable dans {args.root}", file=sys.stderr)
            return 2
    try:
        config = read_config(args)
    except (OSError, UnicodeDecodeError) as error:
        print(f"stack_check: {error}", file=sys.stderr)
        return 2
    for key in (STACK_KEY, LOCKFILE_KEY):
        if not config.get(key):
            print(f"sans objet (clé {key} absente)")
            return 0
    stack_values = config[STACK_KEY]
    if len(stack_values) != 1:
        print(invalid(STACK_KEY, f"un seul fichier par la clé {STACK_KEY}, lu : {' ; '.join(stack_values)}"))
        return 2
    stack_path = stack_values[0]
    try:
        text = read_at(Path(args.root), args.head, stack_path) or ""
    except UnicodeDecodeError as error:
        print(invalid(stack_path, f"fichier illisible en UTF-8 : {error}"))
        return 2
    entries, problems = parse_stack(text, stack_path)
    lines = problems + added_entries(Path(args.root), args.base, stack_path, entries)
    for lock_entry in config[LOCKFILE_KEY]:
        lines += evaluate(Path(args.root), lock_entry, args.base, args.head, stack_path, entries)
    lines += uncovered(config[LOCKFILE_KEY], entries, stack_path)
    for line in lines:
        print(line)
    statuses = {line.split("\t", 1)[0] for line in lines}
    if statuses & {"NOT RUN", "INVALID"}:
        return 2
    return 1 if statuses & {"UNLISTED", "NO SOURCE"} else 0


if __name__ == "__main__":
    sys.exit(main())
