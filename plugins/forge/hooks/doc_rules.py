"""The documentation rules `after_write` holds on a file an agent has just written (#199).

Keys of `docs/agents/usine.md`, each absent key making its step "sans objet" (no default):

- `doc-frontmatter`, repeatable, a path pattern (the syntax of `format-on-write`): a written `.md`
  whose relative path matches one must open with a `---` ... `---` front matter of flat
  `key: value` lines that holds a non-empty `type`. Only the written file is judged: a tracked
  document that is not touched blocks nothing.
- `doc-index`, the path of a generated index. When a file covered by `doc-frontmatter` is
  written, the index is rebuilt from `git ls-files` (tracked files, and untracked ones that git
  does not ignore, so that documents written before the commit are listed; plus the written file
  itself): one row per covered `.md` that holds a `type`, sorted by path, the index itself left
  out. The index is generated: `doc-frontmatter` does not judge it and a hand edit is undone.
  The file is written only when its content changes. Without `doc-frontmatter` there is no
  index.
- `doc-cap`, repeatable, `<pattern> | <n> mots` or `<pattern> | <n> lignes`: the body of a
  matching file (front matter excluded; words are cut on whitespace, every line counts, blank
  ones too) stays under the cap. The ratchet is the file as `HEAD` holds it (`git show`): absent
  from `HEAD` or under the cap there, it must stay under the cap; already over it there, it
  may not grow. An unreadable value is reported, never guessed.

Every problem is a line for `after_write`, which reports it with exit code 2: the write stays and
the agent fixes the file. A file written through a shell command does not come through the hook,
so these rules do not see it either.

The front matter is cut by `handoff_header.split`. Its `parse` is not used: it is made for the
relay's header, accepts keys of `[a-z_]` only and raises on any other line, where a document
may well carry `last-updated: ...` or a nested block.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote

from handoff_header import HeaderError, split
from usine import matches, split_value

FRONTMATTER_KEY = "doc-frontmatter"
INDEX_KEY = "doc-index"
CAP_KEY = "doc-cap"
GIT_TIMEOUT = 30
FIELD = re.compile(r"^([A-Za-z0-9_.-]+)[ \t]*:[ \t]*(.*)$")
CAP = re.compile(r"([1-9][0-9]*)\s+(mots|lignes)")
UNITS = {"mots": "words", "lignes": "lines"}
HEADING = re.compile(r"^# +(.+?)\s*$")


def scalar(value: str) -> str:
    """A flat YAML value without its quotes; `[]` and `{}` hold nothing."""
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return "" if text in ("[]", "{}") else text


def read(content: str) -> tuple[dict[str, str], str]:
    """The flat fields of the front matter and the body after it; HeaderError without a front matter."""
    header, rest = split(content.removeprefix("\ufeff"))
    fields: dict[str, str] = {}
    for line in header:
        if match := FIELD.match(line.rstrip("\r\n")):
            fields.setdefault(match.group(1), scalar(match.group(2)))
    return fields, rest.partition("\n")[2]


def body_of(content: str) -> str:
    """The text after the front matter, or the whole text when it has none."""
    try:
        return read(content)[1]
    except HeaderError:
        return content.removeprefix("\ufeff")


def patterns(config: Mapping[str, list[str]], key: str) -> tuple[list[str], list[str]]:
    """The patterns of a key, and one problem line per value that is empty."""
    good: list[str] = []
    problems: list[str] = []
    for value in config.get(key, []):
        if value.strip():
            good.append(value.strip())
        else:
            problems.append(f"{key}: an empty value is not a path pattern, line ignored")
    return good, problems


def frontmatter_problem(relative: str, content: str) -> str | None:
    prefix = f"{FRONTMATTER_KEY}: {relative}"
    add = "add at the top of the file:\n---\ntype: <kind>\n---"
    try:
        fields, _ = read(content)
    except HeaderError as error:
        return f"{prefix} must open with a front matter holding a non-empty `type` ({error}); {add}"
    if not fields.get("type"):
        return f"{prefix} has a front matter without a non-empty `type`; {add}"
    return None


def git(root: Path, *args: str) -> str | None:
    """The standard output of a git command run from `root`, None when it fails."""
    try:
        done = subprocess.run(
            ["git", *args],
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.decode("utf-8", errors="replace") if done.returncode == 0 else None


def first_heading(body: str) -> str:
    fenced = False
    for line in body.splitlines():
        if line.startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and (match := HEADING.match(line)):
            return match.group(1)
    return ""


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def index_text(rows: list[tuple[str, str, str]]) -> str:
    lines = [
        "---",
        "type: index",
        "---",
        "",
        "Generated by the `after_write` hook from `git ls-files`: do not edit by hand.",
        "",
        "| Document | Type | Title |",
        "| --- | --- | --- |",
    ]
    for link, kind, title in rows:
        label = link.replace("[", "\\[").replace("]", "\\]")
        lines.append(f"| [{cell(label)}]({quote(link)}) | {cell(kind)} | {cell(title)} |")
    return "\n".join(lines) + "\n"


def refresh_index(
    root: Path, index: str, covers: list[str], written: str
) -> str | None:
    """Rebuild the index; a problem line when it cannot be, None otherwise."""
    target = (root / index).resolve()
    try:
        relative_index = target.relative_to(root).as_posix()
    except ValueError:
        return f"{INDEX_KEY}: `{index}` is outside the project, index not written"
    listing = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if listing is None:
        return f"{INDEX_KEY}: `git ls-files` failed, index not rebuilt"
    names = {name for name in listing.split("\0") if name} | {written}
    rows: list[tuple[str, str, str]] = []
    for name in sorted(names):
        path = root / name
        if (
            not name.endswith(".md")
            or name == relative_index
            or not any(matches(pattern, name) for pattern in covers)
            or not path.is_file()
        ):
            continue
        try:
            fields, body = read(path.read_text(encoding="utf-8", errors="replace"))
        except HeaderError:
            continue
        if fields.get("type"):
            link = posixpath.relpath(name, posixpath.dirname(relative_index) or ".")
            rows.append((link, fields["type"], fields.get("title") or first_heading(body)))
    text = index_text(rows)
    try:
        if target.is_file() and target.read_bytes() == text.encode("utf-8"):
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
    except OSError as error:
        return f"{INDEX_KEY}: could not write `{index}` ({error.strerror or type(error).__name__})"
    return None


def measure(body: str, unit: str) -> int:
    return len(body.split()) if unit == "mots" else len(body.splitlines())


def cap_problems(
    config: Mapping[str, list[str]], root: Path, relative: str, content: str
) -> list[str]:
    problems: list[str] = []
    head_body: str | None = None
    looked = False
    for value in config.get(CAP_KEY, []):
        parts = split_value(value, 2)
        limit = CAP.fullmatch(parts[1]) if parts else None
        if parts is None or limit is None:
            problems.append(
                f"{CAP_KEY}: `{value}` is not `<pattern> | <n> mots` or `<pattern> | <n> lignes`"
                " (n above 0), line ignored"
            )
            continue
        if not matches(parts[0], relative):
            continue
        cap, unit = int(limit.group(1)), limit.group(2)
        count = measure(body_of(content), unit)
        if count <= cap:
            continue
        if not looked:
            looked = True
            shown = git(root, "show", f"HEAD:./{relative}")
            head_body = None if shown is None else body_of(shown)
        before = None if head_body is None else measure(head_body, unit)
        if before is not None and before > cap and count <= before:
            continue
        said = f"holds {count} {UNITS[unit]}, over the cap of {cap}"
        if before is not None and before > cap:
            said += f", and it held {before} at HEAD, over the cap already: it may not grow"
        problems.append(
            f"{CAP_KEY}: {relative} {said} (`{value}`); shorten it, or write a new document"
            " that replaces this one"
        )
    return problems


def doc_problems(
    config: Mapping[str, list[str]], root: Path, relative: str, content: str
) -> list[str]:
    covers, problems = patterns(config, FRONTMATTER_KEY)
    if relative.endswith(".md") and any(matches(pattern, relative) for pattern in covers):
        index = (config.get(INDEX_KEY) or [""])[-1].strip()
        if not index or relative != posixpath.normpath(index):
            if problem := frontmatter_problem(relative, content):
                problems.append(problem)
        if index and (problem := refresh_index(root, index, covers, relative)):
            problems.append(problem)
    problems.extend(cap_problems(config, root, relative, content))
    return problems
