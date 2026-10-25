"""Confront the labels a PR adds on screen with the project's forbidden words and its glossary.

    python ui_labels.py [--usine FILE] [--root DIR] <diff-file | ->

The diff is the unified diff of the PR (`git diff <base>...<head>`), read and never run. The keys
of `docs/agents/usine.md` it reads:

- `ui-labels` : a label file, or a directory when it ends with `/`, one per line. A label is the
  value of an added line of such a file (`key: "Value"`, `key=Value`, or a bare line); the key that
  carries it, a blank line and a comment (`#`, `//`) are not labels.
- `ui-forbidden-word` : a word or a pattern refused on screen, one per line. It is a regular
  expression, matched without case and as a whole word, so a plain word does not match the longer
  word that contains it.

One line per finding is printed, `<status>`, `<path>`, `<label>` and `<detail>` separated by tabs:
FORBIDDEN (the label holds a forbidden word, the detail), UNKNOWN (a business term of the label is
in no glossary file of the key `glossary`: a capitalised word, the first of the label apart) or NONE
(no forbidden word found). Exit code 0 when nothing is found, 1 when a label holds a forbidden word
or an unknown term, 2 when a pattern is invalid, a glossary file unreadable, a file given to `--usine` missing or
unreadable, or the call wrong. A missing key prints `sans objet (clé <nom> absente)` for its part
and never stops the other part. Without `--usine`, a project with no `docs/agents/usine.md` has no
key at all. The output is UTF-8. The standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402
from never_weaken import parse_diff, under  # noqa: E402

FORBIDDEN = "FORBIDDEN"
UNKNOWN = "UNKNOWN"
NONE = "NONE"
INVALID = "INVALID"
LABELS_KEY = "ui-labels"
WORD_KEY = "ui-forbidden-word"
GLOSSARY_KEY = "glossary"

_KEY = re.compile(r"""^\s*(?:-\s+)?(?:"[^"]*"|'[^']*'|[\w.\-]+)\s*[:=]\s*(.*)$""")
_OPENERS = {"|", ">", "|-", ">-", "{", "[", "|+", ">+"}


@dataclass
class Finding:
    status: str
    path: str
    label: str
    detail: str


def label_of(line: str) -> str | None:
    """The label an added line carries, or None for a blank line, a comment or a key alone."""
    stripped = line.strip()
    if not stripped or stripped.startswith(("#", "//")):
        return None
    match = _KEY.match(line)
    value = match.group(1) if match else re.sub(r"^-\s+", "", stripped)
    value = value.strip().rstrip(",").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    if not value or value in _OPENERS:
        return None
    return value


def labels(paths: list[str], diff_text: str) -> list[tuple[str, str]]:
    """The (file, label) pairs the diff adds under the label files."""
    found: list[tuple[str, str]] = []
    for change in parse_diff(diff_text):
        if not any(under(change.new_path, scope) for scope in paths):
            continue
        for line in change.added:
            if (label := label_of(line)) is not None:
                found.append((change.new_path or "", label))
    return found


def compile_word(word: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w)(?:{word})(?!\w)", re.IGNORECASE)


def check(paths: list[str], forbidden: list[str], diff_text: str) -> list[Finding]:
    patterns = [(word, compile_word(word)) for word in forbidden]
    findings: list[Finding] = []
    for path, label in labels(paths, diff_text):
        for word, pattern in patterns:
            if hit := pattern.search(label):
                findings.append(Finding(FORBIDDEN, path, label, hit.group()))
    return findings


_WORD = re.compile(r"[^\W\d_]{3,}")


def terms(label: str) -> list[str]:
    """The business terms of a label: its capitalised words, the first word of the label apart."""
    words = label.split()
    found: list[str] = []
    for index, word in enumerate(words):
        if index == 0:
            continue
        found.extend(m for m in _WORD.findall(word) if m[0].isupper())
    return found


def unknown_terms(glossary: str, diff_text: str, paths: list[str]) -> list[Finding]:
    """Each term of an added label that no glossary text holds, as a whole word and without case."""
    findings: list[Finding] = []
    for path, label in labels(paths, diff_text):
        for term in dict.fromkeys(terms(label)):
            if not re.search(rf"(?<!\w){re.escape(term)}(?!\w)", glossary, re.IGNORECASE):
                findings.append(Finding(UNKNOWN, path, label, term))
    return findings


def _print(finding: Finding) -> None:
    print(f"{finding.status}\t{finding.path}\t{finding.label}\t{finding.detail}")


def _forbidden_section(config: dict[str, list[str]], paths: list[str], text: str) -> tuple[int, list[Finding]]:
    words = config.get(WORD_KEY)
    if not words:
        print(f"sans objet (clé {WORD_KEY} absente)")
        return 0, []
    invalid = []
    for word in words:
        try:
            compile_word(word)
        except re.error as error:
            invalid.append(Finding(INVALID, "", "", f"{word} : pas une expression régulière ({error})"))
    if invalid:
        for finding in invalid:
            _print(finding)
        return 2, []
    findings = check(paths, words, text)
    for finding in findings or [Finding(NONE, "", "", "aucun libellé refusé")]:
        _print(finding)
    return (1 if findings else 0), findings


def _glossary_section(config: dict[str, list[str]], paths: list[str], text: str, root: Path) -> int:
    files = config.get(GLOSSARY_KEY)
    if not files:
        print(f"sans objet (clé {GLOSSARY_KEY} absente)")
        return 0
    try:
        glossary = "\n".join((root / name).read_text(encoding="utf-8") for name in files)
    except (OSError, UnicodeDecodeError) as error:
        _print(Finding(INVALID, "", "", f"glossaire illisible : {error}"))
        return 2
    findings = unknown_terms(glossary, text, paths)
    for finding in findings:
        _print(finding)
    return 1 if findings else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("diff", help="the unified diff of the PR, or - for the standard input")
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
        text = sys.stdin.read() if args.diff == "-" else Path(args.diff).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"ui_labels: {error}", file=sys.stderr)
        return 2
    paths = config.get(LABELS_KEY)
    if not paths:
        print(f"sans objet (clé {LABELS_KEY} absente)")
        return 0
    first, _ = _forbidden_section(config, paths, text)
    second = _glossary_section(config, paths, text, root)
    return 2 if 2 in (first, second) else max(first, second)


if __name__ == "__main__":
    sys.exit(main())
