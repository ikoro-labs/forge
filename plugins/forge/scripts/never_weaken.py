"""Say which `never-weaken` entries of `docs/agents/usine.md` a PR's diff touches.

    python never_weaken.py [--usine FILE] <diff-file | ->

The diff is the unified diff of the PR (`git diff <base>...<head>`), read and never run: the
script launches no command the project declares. Each `never-weaken` entry is
`<path> | <type> [| <parameter>]`, and says a change the project reserves to a human:

    .github/workflows/ | removed-line
    config/tolerances.toml | raised-number | ^rel_tol = (\\S+)
    docs/fonctions/ | lowered-rank | statut | certifie > valide > brouillon

`<path>` is a file, or a directory when it ends with `/`. One line per entry is printed, `<status>`,
`<entry>` and `<detail>` separated by tabs, the status being APPLIES (the diff weakens what the
entry guards), NONE, or INVALID (the entry is malformed, or its diff cannot be read: it is never
read as NONE). Exit code 0 when no entry applies, 1 when one does, 2 when one is invalid or the
call is wrong. Without the key, the step is "sans objet" and the exit code is 0.

The entries are read from the base (`--usine`, `git show origin/<base>:docs/agents/usine.md`), so a
PR cannot lift the guard it is judged by. The standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402

KEY = "never-weaken"
APPLIES, NONE, INVALID = "APPLIES", "NONE", "INVALID"


@dataclass
class FileChange:
    old_path: str | None = None
    new_path: str | None = None
    removed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)


@dataclass
class Result:
    entry: str
    status: str
    detail: str


def _path(raw: str) -> str | None:
    raw = raw.split("\t")[0].strip().strip('"')
    if raw == "/dev/null":
        return None
    return raw[2:] if raw[:2] in ("a/", "b/") else raw


def parse_diff(text: str) -> list[FileChange]:
    """The files of a unified diff, with the lines each removed and added (prefix dropped)."""
    changes: list[FileChange] = []
    current: FileChange | None = None
    in_hunk = False
    for line in text.splitlines():
        if line.startswith("diff --git "):
            current, in_hunk = FileChange(), False
            changes.append(current)
            if header := re.match(r"^diff --git (\"?a/.+?\"?) (\"?b/.+\"?)$", line):
                current.old_path, current.new_path = _path(header.group(1)), _path(header.group(2))
        elif current is None:
            continue
        elif not in_hunk:
            if line.startswith("@@"):
                in_hunk = True
            elif line.startswith("--- "):
                current.old_path = _path(line[4:])
            elif line.startswith("+++ "):
                current.new_path = _path(line[4:])
            elif line.startswith("rename from "):
                current.old_path = line[len("rename from "):]
            elif line.startswith("rename to "):
                current.new_path = line[len("rename to "):]
        elif line.startswith("-"):
            current.removed.append(line[1:])
        elif line.startswith("+"):
            current.added.append(line[1:])
    return changes


def under(path: str | None, scope: str) -> bool:
    """Whether `path` is the file `scope`, or inside it when `scope` ends with `/`."""
    if path is None:
        return False
    return path.startswith(scope) if scope.endswith("/") else path == scope


def _removed_line(changes: list[FileChange], scope: str) -> tuple[str, str]:
    hits: list[str] = []
    for change in changes:
        if not under(change.old_path, scope):
            continue
        if change.removed:
            hits.append(f"{change.old_path}: -{change.removed[0]}")
        elif not under(change.new_path, scope):
            hits.append(f"{change.old_path}: déplacé ou retiré du chemin")
    if hits:
        return APPLIES, "; ".join(hits)
    return NONE, "aucune ligne retirée sous le chemin"


def _changed_values(change: FileChange, pattern: re.Pattern[str]) -> list[tuple[str, str]]:
    """The (old, new) captures of the removed and added lines the pattern matches, in order."""
    old = [m.group(1) for line in change.removed if (m := pattern.search(line))]
    new = [m.group(1) for line in change.added if (m := pattern.search(line))]
    return list(zip(old, new))


def _raised_number(changes: list[FileChange], scope: str, parameter: str) -> tuple[str, str]:
    pattern = re.compile(parameter)
    hits: list[str] = []
    for change in changes:
        if not under(change.new_path, scope):
            continue
        for old, new in _changed_values(change, pattern):
            try:
                raised = float(new) > float(old)
            except ValueError:
                if old != new:
                    hits.append(f"{change.new_path}: valeur illisible, {old} puis {new}")
                continue
            if raised:
                hits.append(f"{change.new_path}: {old} relevé à {new}")
    if hits:
        return APPLIES, "; ".join(hits)
    return NONE, "aucune valeur relevée sous le chemin"


def _pattern(parameter: str) -> str | None:
    """Why `parameter` is not a regular expression with exactly one group, or None."""
    try:
        groups = re.compile(parameter).groups
    except re.error as error:
        return f"le paramètre n'est pas une expression régulière ({error})"
    return None if groups == 1 else "le paramètre doit contenir un seul groupe de capture"


def _scale(parameter: str) -> tuple[re.Pattern[str], list[str]] | str:
    """The field pattern and the ranks (best first) of `<field> | <a> > <b> > ...`, or why not."""
    parts = usine.split_value(parameter, 2)
    if parts is None:
        return "le paramètre est `<champ> | <rang> > <rang> [> ...]`"
    ranks = [rank.strip() for rank in parts[1].split(">")]
    if len(ranks) < 2 or not all(ranks) or len(set(ranks)) != len(ranks):
        return "l'échelle demande au moins deux rangs distincts, séparés par `>`"
    pattern = re.compile(
        r"^[\s>*_#-]*" + re.escape(parts[0]) + r"[\s*_]*[:=]\s*[\"'`]?([^\s\"'`,]+)"
    )
    return pattern, ranks


def _lowered_rank(
    changes: list[FileChange], scope: str, scale: tuple[re.Pattern[str], list[str]]
) -> tuple[str, str]:
    pattern, ranks = scale
    hits: list[str] = []
    for change in changes:
        if not under(change.new_path, scope):
            continue
        for old, new in _changed_values(change, pattern):
            if old == new:
                continue
            if old not in ranks or new not in ranks:
                hits.append(f"{change.new_path}: rang hors échelle, {old} puis {new}")
            elif ranks.index(new) > ranks.index(old):
                hits.append(f"{change.new_path}: {old} abaissé à {new}")
    if hits:
        return APPLIES, "; ".join(hits)
    return NONE, "aucun rang abaissé sous le chemin"


def check_entry(entry: str, changes: list[FileChange]) -> Result:
    parts = usine.split_value(entry, 3) or usine.split_value(entry, 2)
    if parts is None:
        return Result(entry, INVALID, "il manque une partie : `<chemin> | <type> [| <paramètre>]`")
    scope, kind = parts[0], parts[1]
    parameter = parts[2] if len(parts) == 3 else None
    if kind == "removed-line":
        if parameter is not None:
            return Result(entry, INVALID, "le type `removed-line` ne prend pas de paramètre")
        return Result(entry, *_removed_line(changes, scope))
    if kind == "raised-number":
        if parameter is None:
            return Result(entry, INVALID, "le type `raised-number` demande une expression régulière")
        if problem := _pattern(parameter):
            return Result(entry, INVALID, problem)
        return Result(entry, *_raised_number(changes, scope, parameter))
    if kind == "lowered-rank":
        scale = _scale(parameter) if parameter else "le type `lowered-rank` demande `<champ> | <échelle>`"
        if isinstance(scale, str):
            return Result(entry, INVALID, scale)
        return Result(entry, *_lowered_rank(changes, scope, scale))
    return Result(entry, INVALID, f"type inconnu `{kind}` (removed-line, raised-number, lowered-rank)")


def check(entries: list[str], diff_text: str) -> list[Result]:
    changes = parse_diff(diff_text)
    return [check_entry(entry, changes) for entry in entries]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("diff", help="the unified diff of the PR, or - for the standard input")
    parser.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md)")
    args = parser.parse_args(argv)
    config_file = Path(args.usine) if args.usine else usine.project_root() / usine.CONFIG_PATH
    try:
        config = usine.parse(config_file.read_text(encoding="utf-8"))
        text = sys.stdin.read() if args.diff == "-" else Path(args.diff).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"never_weaken: {error}", file=sys.stderr)
        return 2
    entries = config.get(KEY)
    if not entries:
        print(f"sans objet (clé {KEY} absente)")
        return 0
    results = check(entries, text)
    for result in results:
        print(f"{result.status}\t{result.entry}\t{result.detail}")
    statuses = {result.status for result in results}
    return 2 if INVALID in statuses else 1 if APPLIES in statuses else 0


if __name__ == "__main__":
    sys.exit(main())
