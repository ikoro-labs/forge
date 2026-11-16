"""Read a JUnit XML report, and tell which of its tests a diff adds or changes.

The two halves of the test grain of `base_replay.py`. The standard library only.

`parse(path)` gives one `Case` per `<testcase>` of the report: `pass`, `fail` (a `<failure>` or an
`<error>`) or `skipped`. The report is written by test code the PR controls, so a report that declares
a DOCTYPE or an entity, or that is over 20 MB, is refused (`ReportError`) before the parser sees it.

`touched(cases, text, ranges)` keeps the cases a diff touches. `text` is the test file as the head
has it, `ranges` the line ranges the diff adds or changes in it (`changed_ranges` reads them from a
`git diff -U0`). A case is placed at the line of `text` that holds its name, without the `[parameters]`
a runner appends, as a whole word. When the name is written once, that line is the one; when it is
written several times (two classes with a test of the same name, a comment, a call), the case is placed
by its class: at the first line with the name below the line that holds the last part of its
`classname`, provided that gives one line only. A case that cannot be placed, whether its name is not
written in the file or it stays ambiguous after its class, counts as touched, so that the replay shows
it rather than hides it. A placed case begins at the decorators, attributes and comments (`@`, `#`,
`//`, `/*`, `*`, `[`) right above it and owns the lines up to the next placed case, or up to the line
of its class when that sits between the two, less the blank lines that end them. It is touched when a changed range falls in them.

This is a reading of the text, not of the language. A helper or a fixture changed below a test, or at
the end of the file, falls in the lines of the test above it, which is then taken for changed (a
passing, unchanged test can be shown); only a line above the first test touches no case. A name
written once is taken for the definition, even in a comment. Where it is written several times, the
class decides, and a comment or a call between the class and the definition can still mislead it.
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


def place(lines: list[str], case: Case) -> int | None:
    """The line of the definition of a case, or None when the text does not say it with certainty."""
    found = holding(lines, case.bare_name)
    if len(found) > 1:
        owner = case.classname.rsplit(".", 1)[-1]
        below = {min((n for n in found if n > line), default=0) for line in holding(lines, owner)} if owner else set()
        below.discard(0)
        found = sorted(below) if len(below) == 1 else []
    return with_its_decorations(lines, found[0]) if found else None


def touched(cases: list[Case], text: str, ranges: list[range]) -> list[Case]:
    lines = text.splitlines()
    placed = {index: place(lines, case) for index, case in enumerate(cases)}
    starts = sorted({line for line in placed.values() if line is not None})
    # The line of a class, when it sits between two tests, ends the test above it: a class added after
    # a test is not a change of that test.
    stops = set(starts)
    for index, case in enumerate(cases):
        start, owner = placed[index], case.classname.rsplit(".", 1)[-1]
        if start is not None and owner:
            before = max((line for line in starts if line < start), default=0)
            stops.update(line for line in holding(lines, owner) if before < line < start)
    stops_sorted = sorted(stops)
    result = []
    for index, case in enumerate(cases):
        start = placed[index]
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
