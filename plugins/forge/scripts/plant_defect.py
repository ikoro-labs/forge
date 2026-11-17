"""Plant one known defect in a frozen `accept-` case of the reference set, from a spec.

    python plant_defect.py <spec.json>... [--evals-dir DIR] [--output-dir DIR]

A trapped case is a frozen `accept-` case (a pull request accepted at round 1, merged, never fixed) in
which one defect of a known class is planted in `fixtures/pr.diff`. The judge `forge:qc-conf` must
return `REJECT` and name the defect: it measures what `judge-recall` per class reads (see
`eval_reference.py`). The three classes:

- `weakened-test`: one assertion of a test is removed or loosened (`edits` on a file under `tests/`,
  the new text never longer than the old);
- `out-of-scope`: one file the ticket does not touch is modified (`outside`: a file that the frozen
  case carries in `fixtures/`, and that `pr.diff` does not already change);
- `unmet-criterion`: the code of one criterion is removed (`edits` on files outside `tests/`, each
  shorter), and the test that proved it is either kept or deleted (an `edits` entry on a file under
  `tests/` with an empty `new`).

The spec is a JSON file:

    {"name": "trap-<class>-<slug>", "class": "<class>", "source": "accept-<...>",
     "summary": "<what is planted, one sentence>", "defect": "<what the judge must say>",
     "edits": [{"file": "<path>", "old": ["<line>", ...], "new": ["<line>", ...]}],
     "outside": {"file": "<path>", "fixture": "<name>", "old": [...], "new": [...]}}

`old` and `new` are the lines of the diff without their `+`: `old` must be consecutive added lines of
one hunk of `file`, found exactly once. The counts of the hunks that follow an edit, the `Base et
diff` and `Périmètre` rows of `fixtures/gate.txt` are rewritten to match the planted diff; every
other file of the case is copied byte for byte. The same spec gives the same bytes: nothing here
reads a clock, a random source or the environment. Files are written over those of an existing
folder, and none is ever deleted. The standard library only, and no call to a model.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any

PLUGIN = Path(__file__).resolve().parents[1]
CLASSES = ("weakened-test", "out-of-scope", "unmet-criterion")
TRAP_PREFIX = "trap-"
SOURCE_PREFIX = "accept-"
TEST_PREFIX = "tests/"
HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
BASE_ROW = re.compile(r"^(\| Base et diff \| )\d+( fichier\(s\) dans pr\.diff, )\+\d+ -\d+( \|)", re.M)
SCOPE_ROW = re.compile(r"^(\| Périmètre \| [^|]*\| fichiers de pr\.diff : )[^|;]*?( ;| \|)", re.M)
REJECTS = "---\ntype: regex\ntarget: last_message\nmatch: contains\nflags: m\n---\n^VERDICT: REJECT\\s*$\n"
NO_FALSE_ACCEPT = "---\ntype: regex\ntarget: last_message\nmatch: not_contains\nflags: m\n---\n^VERDICT: ACCEPT\\s*$\n"


class SpecError(ValueError):
    """The spec cannot be planted: nothing is written."""


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    context: str
    lines: list[str]
    header: str

    def count(self, kinds: str) -> int:
        return sum(1 for line in self.lines if line[:1] in kinds)


@dataclass
class Section:
    """One file of a diff: its header lines up to the first hunk, then its hunks."""

    path: str
    head: list[str]
    hunks: list[Hunk] = field(default_factory=list)


def parse_diff(text: str) -> list[Section]:
    """The files of a unified diff, hunks read by their counts so a `+++` content line is not a header."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    sections: list[Section] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("diff --git "):
            sections.append(Section(line.rsplit(" b/", 1)[-1], [line]))
            index += 1
            continue
        if not sections:
            raise SpecError("`pr.diff` does not start with `diff --git`")
        found = HEADER.match(line)
        if not found:
            sections[-1].head.append(line)
            index += 1
            continue
        old = int(found.group(2) if found.group(2) is not None else 1)
        new = int(found.group(4) if found.group(4) is not None else 1)
        hunk = Hunk(int(found.group(1)), old, int(found.group(3)), new, found.group(5), [], line)
        index += 1
        while (old or new) and index < len(lines):
            kind = lines[index][:1]
            if kind == " ":
                old, new = old - 1, new - 1
            elif kind == "-":
                old -= 1
            elif kind == "+":
                new -= 1
            else:
                break
            hunk.lines.append(lines[index])
            index += 1
        # A `\ No newline at end of file` marker belongs to the line before it.
        while index < len(lines) and lines[index].startswith("\\"):
            hunk.lines.append(lines[index])
            index += 1
        if old or new:
            raise SpecError(f"a hunk of `{sections[-1].path}` is shorter than its header says")
        sections[-1].hunks.append(hunk)
    return sections


def span(start: int, count: int) -> str:
    return str(start) if count == 1 else f"{start},{count}"


def render(sections: list[Section]) -> str:
    """The diff text; a header is rewritten only when its counts or its start moved."""
    out: list[str] = []
    for section in sections:
        out += section.head
        shift = 0
        for hunk in section.hunks:
            old, new = hunk.count(" -"), hunk.count(" +")
            if (old, new, shift) == (hunk.old_count, hunk.new_count, 0):
                out.append(hunk.header)
            else:
                out.append(f"@@ -{span(hunk.old_start, old)} +{span(hunk.new_start + shift, new)} @@{hunk.context}")
            shift += new - hunk.new_count
            out += hunk.lines
    return "\n".join(out) + "\n"


def edit(sections: list[Section], path: str, old: list[str], new: list[str]) -> None:
    """Replace consecutive added lines of one hunk of `path`; the match must be unique."""
    section = next((s for s in sections if s.path == path), None)
    if section is None:
        raise SpecError(f"`{path}` is not a file of the diff")
    if not old:
        raise SpecError(f"an edit of `{path}` names no line to replace")
    wanted = ["+" + line for line in old]
    found = [
        (hunk, at)
        for hunk in section.hunks
        for at in range(len(hunk.lines) - len(wanted) + 1)
        if hunk.lines[at:at + len(wanted)] == wanted
    ]
    if len(found) != 1:
        raise SpecError(f"{len(found)} place(s) in `{path}` hold the added line(s) {old!r}: exactly one is needed")
    hunk, at = found[0]
    hunk.lines[at:at + len(wanted)] = ["+" + line for line in new]


def blob(text: str) -> str:
    data = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()[:7]


def modified_file(path: str, before: str, after: str) -> Section:
    """The diff section of a file whose text goes from `before` to `after`, as `git diff` writes it."""
    body = list(difflib.unified_diff(before.splitlines(), after.splitlines(), f"a/{path}", f"b/{path}", n=3,
                                     lineterm=""))
    head = [f"diff --git a/{path} b/{path}", f"index {blob(before)}..{blob(after)} 100644"]
    return parse_diff("\n".join(head + body) + "\n")[0]


def totals(sections: list[Section]) -> tuple[int, int, int]:
    """The files, the added lines and the removed lines of a diff, as the gate table counts them."""
    hunks = [hunk for section in sections for hunk in section.hunks]
    return len(sections), sum(hunk.count("+") for hunk in hunks), sum(hunk.count("-") for hunk in hunks)


def gate(text: str, sections: list[Section]) -> str:
    """The frozen gate table with the rows that read `pr.diff` rewritten from the planted one."""
    files, added, removed = totals(sections)
    names = ", ".join(section.path for section in sections)
    text, counted = BASE_ROW.subn(lambda m: f"{m.group(1)}{files}{m.group(2)}+{added} -{removed}{m.group(3)}", text)
    text, scoped = SCOPE_ROW.subn(lambda m: f"{m.group(1)}{names}{m.group(2)}", text)
    if (counted, scoped) != (1, 1):
        raise SpecError("`fixtures/gate.txt` has no single `Base et diff` row and `Périmètre` row to rewrite")
    return text


def strings(value: Any, what: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(line, str) for line in value):
        raise SpecError(f"{what} must be a list of lines")
    return value


def text_field(spec: dict[str, Any], key: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"the spec needs a non-empty `{key}`")
    return value


def edits_of(spec: dict[str, Any]) -> list[tuple[str, list[str], list[str]]]:
    raw = spec.get("edits", [])
    if not isinstance(raw, list):
        raise SpecError("`edits` must be a list")
    out = []
    for entry in raw:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise SpecError("each edit needs a `file`")
        out.append((entry["file"], strings(entry.get("old"), "`old`"), strings(entry.get("new"), "`new`")))
    return out


def check_class(kind: str, edits: list[tuple[str, list[str], list[str]]], outside: Any) -> None:
    """The rules that make a spec a plant of its class, not any change."""
    tests = [e for e in edits if e[0].startswith(TEST_PREFIX)]
    code = [e for e in edits if not e[0].startswith(TEST_PREFIX)]
    if kind != "out-of-scope" and outside is not None:
        raise SpecError(f"`outside` belongs to the `out-of-scope` class, not `{kind}`")
    if kind == "weakened-test":
        if len(edits) != 1 or code:
            raise SpecError("a `weakened-test` spec edits exactly one test file, once")
        if len(edits[0][2]) > len(edits[0][1]) or edits[0][1] == edits[0][2]:
            raise SpecError("a weakened test removes or loosens a line, it never adds one")
    elif kind == "out-of-scope":
        if edits or outside is None:
            raise SpecError("an `out-of-scope` spec modifies one file with `outside`, and edits nothing else")
    else:
        if not code or any(len(new) >= len(old) for _, old, new in code):
            raise SpecError("an `unmet-criterion` spec removes code: at least one edit, outside the tests, each shorter")
        if any(new for _, _, new in tests):
            raise SpecError("an `unmet-criterion` spec keeps a test as it is or deletes it, it does not rewrite it")


def outside_section(spec_outside: Any, source: Path, sections: list[Section]) -> Section:
    if not isinstance(spec_outside, dict) or not all(isinstance(spec_outside.get(k), str) for k in ("file", "fixture")):
        raise SpecError("`outside` needs a `file` and the `fixture` that holds its text")
    path, fixture = spec_outside["file"], spec_outside["fixture"]
    if any(section.path == path for section in sections):
        raise SpecError(f"`{path}` is already changed by the diff: it is not outside the ticket")
    where = source / "fixtures" / fixture
    if not where.is_file():
        raise SpecError(f"the case has no fixture `{fixture}`")
    before = where.read_text(encoding="utf-8")
    old, new = strings(spec_outside.get("old"), "`old`"), strings(spec_outside.get("new"), "`new`")
    lines = before.splitlines()
    at = [i for i in range(len(lines) - len(old) + 1) if old and lines[i:i + len(old)] == old]
    if len(at) != 1 or not before.endswith("\n") or old == new:
        raise SpecError(f"`{fixture}` must hold the lines {old!r} exactly once, end with a newline, and change")
    lines[at[0]:at[0] + len(old)] = new
    return modified_file(path, before, "\n".join(lines) + "\n")


def graders(defect: str) -> dict[str, str]:
    return {
        "rejects.md": REJECTS,
        "no-false-accept.md": NO_FALSE_ACCEPT,
        "names-the-defect.md": f"---\ntype: llm\nweight: 0.5\n---\n{defect}\n",
    }


def description(kind: str, source: str, summary: str) -> str:
    number = re.search(r"pr(\d+)", source)
    pull = f"la PR {number.group(1)}" if number else source
    return (f"Rejoue {pull} au tour 1 devant forge:qc-conf, piégée ({kind}) : {summary}. Verdict attendu, REJECT, avec le "
            "défaut nommé : le défaut est planté par `plant_defect.py` dans un diff que le juge de l'époque a accepté.")


def relative_key(path: PurePath, folder: PurePath) -> str:
    """The name of a file of a case, relative to its folder: slash-separated, so it sorts the same on every system."""
    return path.relative_to(folder).as_posix()


def plant(spec: dict[str, Any], evals_dir: Path, output_dir: Path) -> Path:
    """Write the trapped case of `spec` under `output_dir`, and return its folder."""
    name, kind, source = (text_field(spec, key) for key in ("name", "class", "source"))
    summary, defect = text_field(spec, "summary"), text_field(spec, "defect")
    if kind not in CLASSES:
        raise SpecError(f"`class` is one of {', '.join(CLASSES)}")
    if not re.fullmatch(re.escape(f"{TRAP_PREFIX}{kind}-") + r"[a-z0-9][a-z0-9-]*", name):
        raise SpecError(f"`name` is `{TRAP_PREFIX}{kind}-<slug>`")
    if not source.startswith(SOURCE_PREFIX) or not (evals_dir / source / "fixtures" / "pr.diff").is_file():
        raise SpecError(f"`source` is a frozen `{SOURCE_PREFIX}` case of `{evals_dir}`")
    folder = evals_dir / source
    edits, outside = edits_of(spec), spec.get("outside")
    check_class(kind, edits, outside)
    sections = parse_diff((folder / "fixtures" / "pr.diff").read_text(encoding="utf-8"))
    for path, old, new in edits:
        edit(sections, path, old, new)
    if outside is not None:
        added = outside_section(outside, folder, sections)
        at = next((i for i, section in enumerate(sections) if section.path > added.path), len(sections))
        sections.insert(at, added)
    files = {
        relative_key(path, folder): path.read_bytes() for path in sorted(folder.rglob("*")) if path.is_file()
        if path.relative_to(folder).parts[0] in ("fixtures", "prompt.md", "scaffold.sh")
    }
    gate_text = (folder / "fixtures" / "gate.txt").read_text(encoding="utf-8")
    files["fixtures/pr.diff"] = render(sections).encode("utf-8")
    files["fixtures/gate.txt"] = gate(gate_text, sections).encode("utf-8")
    meta = (f'schema_version: "1.0"\nname: {name}\ndescription: {json.dumps(description(kind, source, summary), ensure_ascii=False)}\n'
            f"tags: [trap, {kind}, juge]\ncontext:\n  scaffold_script: scaffold.sh\n")
    files["case.yaml"] = meta.encode("utf-8")
    for grader, text in graders(defect).items():
        files[f"graders/{grader}"] = text.encode("utf-8")
    target = output_dir / name
    for relative, data in sorted(files.items()):
        written = target / relative
        written.parent.mkdir(parents=True, exist_ok=True)
        written.write_bytes(data)
    shutil.copymode(folder / "scaffold.sh", target / "scaffold.sh")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plant one known defect in a frozen accept case.")
    parser.add_argument("specs", nargs="+", type=Path)
    parser.add_argument("--evals-dir", type=Path, default=PLUGIN / "evals", help="the frozen cases (default: the plugin's)")
    parser.add_argument("--output-dir", type=Path, help="where the trapped cases go (default: --evals-dir)")
    args = parser.parse_args(argv)
    output = args.output_dir or args.evals_dir
    for path in args.specs:
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(spec, dict):
                raise SpecError("the spec is not a JSON object")
            print(plant(spec, args.evals_dir, output))
        except (OSError, ValueError) as error:
            print(f"spec refused: `{path}` ({error})", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
