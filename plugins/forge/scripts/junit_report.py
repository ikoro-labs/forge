"""Read a JUnit XML report, and tell which of its tests a diff adds or changes.

The two halves of the test grain of `base_replay.py`. The standard library only.

`parse(path)` gives one `Case` per `<testcase>` of the report: `pass`, `fail` (a `<failure>` or an
`<error>`) or `skipped`. The report is written by test code the PR controls, so a report that declares
a DOCTYPE or an entity, or that is over 20 MB, is refused (`ReportError`) before the parser sees it.

`touched(cases, text, ranges)` keeps the cases a diff touches. `text` is the test file as the head
has it, `ranges` the line ranges the diff adds or changes in it (`changed_ranges` reads them from a
`git diff -U0`). A case is placed at the first line of `text` that holds its name, without the
`[parameters]` a runner appends, as a whole word, and begins at the decorators, attributes and comments
(`@`, `#`, `//`, `/*`, `*`, `[`) right above it; it owns the lines up to the next case, less the blank
lines that end them. It is touched when a changed range falls in them. This is a reading of the text,
not of the language: a test whose name is not written in the file, a helper or a fixture changed beside
it, and a name that also appears earlier in the file (a comment, a call) are not placed right. A case
that cannot be placed counts as touched, so that the replay shows it rather than hides it; a helper
changed alone touches no case.
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


def touched(cases: list[Case], text: str, ranges: list[range]) -> list[Case]:
    lines = text.splitlines()
    placed: dict[int, int | None] = {}
    for index, case in enumerate(cases):
        word = re.compile(r"(?<!\w)" + re.escape(case.bare_name) + r"(?!\w)")
        found = next((n for n, line in enumerate(lines, start=1) if word.search(line)), None)
        placed[index] = None if found is None else with_its_decorations(lines, found)
    starts = sorted({line for line in placed.values() if line is not None})
    result = []
    for index, case in enumerate(cases):
        start = placed[index]
        if start is None:
            result.append(case)
            continue
        later = [other for other in starts if other > start]
        end = (later[0] - 1) if later else max(len(lines), start)
        while end > start and not lines[end - 1].strip():
            end -= 1  # the blank lines that separate two tests belong to neither
        if any(r.start <= end and r.stop - 1 >= start for r in ranges):
            result.append(case)
    return result
