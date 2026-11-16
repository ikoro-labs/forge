"""Read a JUnit XML report, and tell which of its tests a diff adds or changes.

The two halves of the test grain of `base_replay.py`. The standard library only.

`parse(path)` gives one `Case` per `<testcase>` of the report: `pass`, `fail` (a `<failure>` or an
`<error>`) or `skipped`. The report is written by test code the PR controls, so a report that declares
a DOCTYPE or an entity, or that is over 20 MB, is refused (`ReportError`) before the parser sees it.

`touched(cases, text, ranges)` keeps the cases a diff touches. `text` is the test file as the head
has it, `ranges` the line ranges the diff adds or changes in it (`changed_ranges` reads them from a
`git diff -U0`). The class of a case is the last part of its `classname`; its declaration is the line
that declares it with a keyword (`class`, `object`, `struct`, `interface`, `trait`, with only words
before it, then the name), when it is the only such line of the file. A case is placed at the line of
`text` that holds its name, without the `[parameters]` a runner appends, as a whole word. When the name
is written once, that line is the one. When it is written several times (two classes with a test of
the same name, a comment, a call), it is the one line with the name between the declaration of its
class and the next declaration of a class of the report; with no declaration, or with the name written
twice there, the case is not placed. Nor is a case whose line is more indented than the placed case
above it with no declaration between them: that line sits in the body of the test above (a call, a
comment), and is no definition. A case that is not placed counts as touched, so that the replay shows
it rather than hides it.

A placed case begins at the decorators, attributes and comments (`@`, `#`, `//`, `/*`, `*`, `[`) right
above it, and owns the lines down to the next placed case or the next declaration, less the blank lines
that end them. Nothing else ends it: a mention of a class (a call, a string, a comment) ends no case. A
case is touched when a changed range falls in its lines.

This is a reading of the text, not of the language. A helper or a fixture changed below a test, or at
the end of the file, falls in the lines of the test above it, which is then taken for changed (a
passing, unchanged test can be shown); only a line above the first test touches no case. A name
written once, at the indentation of the tests or less, is taken for the definition, even in a comment
or a string; a line that declares a class inside a multiline string is read as a declaration.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

MAX_BYTES = 20 * 1024 * 1024
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)
PASS, FAIL, SKIPPED = "pass", "fail", "skipped"
DECORATION = ("@", "#", "//", "/*", "*", "[")
DECLARATION = r"^\s*(?:[\w@]+\s+)*(?:class|object|struct|interface|trait)\s+{}(?!\w)"


class ReportError(Exception):
    """The report cannot be read as a JUnit report."""


@dataclass(frozen=True)
class Case:
    classname: str
    name: str
    status: str

    @property
    def ident(self) -> str:
        return f"{self.classname}.{self.name}" if self.classname else self.name

    @property
    def bare_name(self) -> str:
        return re.sub(r"\[.*\]$", "", self.name)


def parse(path: Path) -> list[Case]:
    if path.stat().st_size > MAX_BYTES:
        raise ReportError("le rapport dépasse 20 Mo, refusé")
    raw = path.read_bytes()
    if re.search(rb"<!(?:DOCTYPE|ENTITY)", raw, re.IGNORECASE):
        raise ReportError("le rapport déclare un DOCTYPE ou une entité (DOCTYPE), refusé")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ReportError(f"le rapport n'est pas un XML lisible ({error})") from error
    cases = []
    for element in root.iter("testcase"):
        tags = {child.tag for child in element}
        status = FAIL if tags & {"failure", "error"} else SKIPPED if "skipped" in tags else PASS
        cases.append(Case(element.get("classname", ""), element.get("name", ""), status))
    return cases


def changed_ranges(diff: str) -> list[range]:
    """The line ranges of the new side of a `git diff -U0`; a pure deletion points at the line before it."""
    ranges = []
    for match in HUNK.finditer(diff):
        start = int(match.group(1))
        length = 1 if match.group(2) is None else int(match.group(2))
        start = max(start, 1)
        ranges.append(range(start, start + max(length, 1)))
    return ranges


def with_its_decorations(lines: list[str], line: int) -> int:
    """The line where a test begins: the decorators, attributes and comments right above its name belong to it."""
    while line > 1 and lines[line - 2].lstrip().startswith(DECORATION):
        line -= 1
    return line


def holding(lines: list[str], name: str) -> list[int]:
    """The numbers of the lines that hold `name` as a whole word."""
    word = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)")
    return [number for number, line in enumerate(lines, start=1) if word.search(line)]


def declared_once(lines: list[str], owner: str) -> int | None:
    """The line that declares the class `owner` with a keyword, when it is the only one; else None."""
    if not owner:
        return None
    declaration = re.compile(DECLARATION.format(re.escape(owner)))
    found = [number for number, line in enumerate(lines, start=1) if declaration.match(line)]
    return found[0] if len(found) == 1 else None


def owner(case: Case) -> str:
    """The class of a case: the last part of its `classname` (`Outer$Inner` gives `Inner`)."""
    return re.split(r"[.$]", case.classname)[-1]


def place(lines: list[str], case: Case, declarations: list[int]) -> int | None:
    """The line that names a case where it is defined, or None when the text does not say it with certainty."""
    found = holding(lines, case.bare_name)
    if len(found) > 1:
        declared = declared_once(lines, owner(case))
        if declared is None:
            return None
        end = min((line for line in declarations if line > declared), default=len(lines) + 1)
        found = [line for line in found if declared < line < end]
    return found[0] if len(found) == 1 else None


def indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def touched(cases: list[Case], text: str, ranges: list[range]) -> list[Case]:
    lines = text.splitlines()
    declarations = sorted({line for line in (declared_once(lines, owner(case)) for case in cases) if line})
    named = {index: place(lines, case, declarations) for index, case in enumerate(cases)}
    # A name more indented than the placed case above it, with no declaration between them, sits in the
    # body of that test (a call, a comment): it is no definition, and its case is not placed.
    definitions: set[int] = set()
    above = 0
    for line in sorted({line for line in named.values() if line is not None}):
        inside = above > 0 and indent(lines[line - 1]) > indent(lines[above - 1])
        if inside and not any(above < declared < line for declared in declarations):
            continue
        definitions.add(line)
        above = line
    placed = {index: with_its_decorations(lines, line) for index, line in named.items() if line in definitions}
    starts = {line for line in placed.values() if line is not None}
    # Only a line that surely ends a test ends one: the start of the next placed case, or a declaration
    # (a class added after a test is not a change of that test). A mention of a class inside a test (a
    # call, a string, a comment) ends nothing.
    stops = starts | set(declarations)
    stops_sorted = sorted(stops)
    result = []
    for index, case in enumerate(cases):
        start = placed.get(index)
        if start is None:
            result.append(case)
            continue
        later = [other for other in stops_sorted if other > start]
        end = (later[0] - 1) if later else max(len(lines), start)
        while end > start and not lines[end - 1].strip():
            end -= 1  # the blank lines that separate two tests belong to neither
        if any(r.start <= end and r.stop - 1 >= start for r in ranges):
            result.append(case)
    return result
