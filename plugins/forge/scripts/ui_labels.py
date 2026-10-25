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
FORBIDDEN (the label holds a forbidden word, the detail) or NONE (nothing found). Exit code 0 when
nothing is found, 1 when a label holds a forbidden word, 2 when a pattern is invalid or the call is
wrong. The standard library only.
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
NONE = "NONE"
INVALID = "INVALID"
LABELS_KEY = "ui-labels"
WORD_KEY = "ui-forbidden-word"

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


def _print(finding: Finding) -> None:
    print(f"{finding.status}\t{finding.path}\t{finding.label}\t{finding.detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("diff", help="the unified diff of the PR, or - for the standard input")
    parser.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md)")
    parser.add_argument("--root", help="the project copy to read (default: the project directory)")
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else usine.project_root()
    config_file = Path(args.usine) if args.usine else root / usine.CONFIG_PATH
    try:
        try:
            config = usine.parse(config_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            config = {}
        text = sys.stdin.read() if args.diff == "-" else Path(args.diff).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"ui_labels: {error}", file=sys.stderr)
        return 2
    paths = config.get(LABELS_KEY)
    if not paths:
        print(f"sans objet (clé {LABELS_KEY} absente)")
        return 0
    words = config.get(WORD_KEY)
    if not words:
        print(f"sans objet (clé {WORD_KEY} absente)")
        return 0
    invalid = []
    for word in words:
        try:
            compile_word(word)
        except re.error as error:
            invalid.append(Finding(INVALID, "", "", f"{word} : pas une expression régulière ({error})"))
    if invalid:
        for finding in invalid:
            _print(finding)
        return 2
    findings = check(paths, words, text)
    for finding in findings or [Finding(NONE, "", "", "aucun libellé refusé")]:
        _print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
