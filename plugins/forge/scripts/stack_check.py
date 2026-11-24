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
from lockfiles import read_at  # noqa: E402  shared with `lockfile_age.py`

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--base", required=True, help="the git ref the PR starts from")
    parser.add_argument("--head", required=True, help="the git ref of the PR's head")
    parser.add_argument("--root", default=".", help="a clone of the project (default: the current directory)")
    parser.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md under --root)")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    config_file = Path(args.usine) if args.usine else Path(args.root) / usine.CONFIG_PATH
    try:
        config = usine.parse(config_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        config = {}
    except (OSError, UnicodeDecodeError) as error:
        print(f"stack_check: {error}", file=sys.stderr)
        return 2
    for key in (STACK_KEY, LOCKFILE_KEY):
        if not config.get(key):
            print(f"sans objet (clé {key} absente)")
            return 0
    for ref in (args.base, args.head):
        found = subprocess.run(
            ["git", "-C", args.root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], capture_output=True
        )
        if found.returncode != 0:
            print(f"stack_check: la référence git `{ref}` est introuvable dans {args.root}", file=sys.stderr)
            return 2
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
    _, problems = parse_stack(text, stack_path)
    for line in problems:
        print(line)
    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
