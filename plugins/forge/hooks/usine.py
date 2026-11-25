"""The project's factory configuration, `docs/agents/usine.md`, as the hooks read it.

Each key is a Markdown list item, the key and its value in backticks:

    - `domain-arbiter` : `pricing-arbiter`
    - `install` : `uv sync --locked`
    - `install` : `pnpm install --frozen-lockfile`

A repeated key is a list, in the file's order. A value of several parts is `<part> | <part>`,
which `split_value` cuts. Any other line is prose and is ignored. An absent key has no default: whoever reads it says the step is "sans objet" and names the key.

The keys that bound the agent's powers (`SENSITIVE_KEYS`) are read in a second file,
`docs/agents/usine-gardes.md`, as `origin/main` holds it; `load` merges the two.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

CONFIG_PATH = Path("docs") / "agents" / "usine.md"
# The keys that bound the agent's powers live in a second file, protected like the guards, and are
# read as `origin/main` holds it. Its path is a constant here, never a key: a key could be moved.
GUARD_PATH = Path("docs") / "agents" / "usine-gardes.md"
MAIN_REF = "refs/remotes/origin/main"
GIT_TIMEOUT_SECONDS = 5
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "accepting-human", "agent-autonomy", "budget-action", "gh-api-allow", "infra-hosts",
        "infra-verify", "never-weaken", "owner-gesture", "pin-bump", "pr-cap-raiser",
        "protected-path", "readonly-agent", "readonly-command", "run-budget", "run-limits",
        "slo", "ticket-budget", "ticket-pr-cap", "ticket-pr-cap-exempt", "ticket-pr-cap-since",
        "validation-owner", "validation-reviewer",
    }
)  # fmt: skip
ENTRY =re.compile(r"^\s*[-*]\s+`([A-Za-z0-9_.-]+)`\s*:\s*`([^`]*)`\s*$")


def parse(text: str) -> dict[str, list[str]]:
    config: dict[str, list[str]] = {}
    for line in text.splitlines():
        if match := ENTRY.match(line):
            config.setdefault(match.group(1), []).append(match.group(2).strip())
    return config


def split_value(value: str, parts: int) -> list[str] | None:
    """A value of `parts` parts joined by ` | `, or None when one is missing or empty.

    The cut is at the first separators only, so the last part keeps the rest (a command may hold
    a `|`). A value short of a part is never completed: the caller reports it.
    """
    pieces = [piece.strip() for piece in value.split(" | ", parts - 1)]
    if len(pieces) != parts or not all(pieces):
        return None
    return pieces


def pattern_regex(pattern: str) -> re.Pattern[str]:
    """The regular expression of a path pattern: `**/`, `*`, `?` and `{a,b}`, the rest literal."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**/", i) and (i == 0 or pattern[i - 1] == "/"):
            out.append("(?:.*/)?")
            i += 3
            continue
        end = pattern.find("}", i) if char == "{" else -1
        if char == "{" and end != -1 and "{" not in pattern[i + 1 : end]:
            choices = pattern[i + 1 : end].split(",")
            out.append("(?:" + "|".join(re.escape(choice) for choice in choices) + ")")
            i = end
        elif char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
        i += 1
    return re.compile("".join(out))


def matches(pattern: str, relative: str) -> bool:
    return pattern_regex(pattern).fullmatch(relative) is not None


def project_root(event: Mapping[str, object] | None = None) -> Path:
    """The project's directory: Claude Code's `CLAUDE_PROJECT_DIR`, else the event's cwd."""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or (event or {}).get("cwd") or "."
    return Path(str(root))


class OnMain(NamedTuple):
    """A file as `refs/remotes/origin/main` holds it.

    `text` set: the file is there. `text` and `why` both None: the ref is readable and has no such
    file. `why` set: git could not tell (no git, a timeout, no repository, no ref, an object that
    cannot be read), and nothing else is known.
    """

    text: str | None
    why: str | None


def _git(argv: list[str], directory: Path | str) -> subprocess.CompletedProcess[bytes] | None:
    """The finished git process, or None when it did not finish within the timeout."""
    try:
        # Fixed argv resolved by shutil.which: git, and arguments built here.
        return subprocess.run(  # noqa: S603
            argv, cwd=directory, capture_output=True, check=False, timeout=GIT_TIMEOUT_SECONDS
        )
    except (subprocess.SubprocessError, OSError, ValueError):  # ValueError: an argument git cannot take
        return None


def on_main(directory: Path | str, path: Path) -> OnMain:
    """`path` as `origin/main` holds it, read by `git ls-tree` then `git cat-file`.

    Never the working tree, which an agent can edit: what counts is what the human merged. The ref
    is the one this clone last fetched. The tree is listed first so that a file the ref lacks
    (absent) is told apart from a ref or a repository git cannot read (unreadable).
    """
    git = shutil.which("git")
    if not git:
        return OnMain(None, "git is not installed")
    name = path.as_posix()
    listed = _git([git, "ls-tree", "-z", "--full-tree", MAIN_REF, "--", name], directory)
    if listed is None:
        return OnMain(None, "git ls-tree did not finish")
    if listed.returncode != 0:
        detail = listed.stderr.decode("utf-8", "replace").strip()
        return OnMain(None, f"git ls-tree failed: {detail}")
    entry = listed.stdout.decode("utf-8", "replace").rstrip("\0")
    if not entry:
        return OnMain(None, None)
    fields = entry.split("\t", 1)[0].split()
    if len(fields) != 3 or fields[1] != "blob":
        return OnMain(None, f"{name} is not a file on {MAIN_REF}")
    shown = _git([git, "cat-file", "blob", fields[2]], directory)
    if shown is None or shown.returncode != 0:
        return OnMain(None, f"git cat-file could not read {name}")
    try:
        return OnMain(shown.stdout.decode("utf-8"), None)
    except UnicodeDecodeError:
        return OnMain(None, f"{name} on {MAIN_REF} is not UTF-8")


class Loaded(NamedTuple):
    """The configuration, and what the loader has to say about how it was read.

    `notices`: one line each for a sensitive key dropped from `usine.md`, a key the guard file
    holds that is not sensitive, and a guard file read from `usine.md` for want of one on
    `origin/main`. `unreadable`: why the guard file could not be read, None when it could (or is
    absent); a caller that merges refuses then.
    """

    config: dict[str, list[str]]
    notices: list[str]
    unreadable: str | None


def _working_tree(root: Path) -> dict[str, list[str]]:
    try:
        return parse((root / CONFIG_PATH).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return {}


def load_checked(root: Path) -> Loaded:
    """The configuration of the project at `root`: `usine.md` for the free keys, `usine-gardes.md`
    as `origin/main` holds it for the sensitive ones (`SENSITIVE_KEYS`).

    A sensitive key in `usine.md` is dropped and reported when the guard file is on `origin/main`;
    a key of the guard file that is not sensitive is ignored and reported. Without the guard file
    on `origin/main`, or when git cannot tell, every key comes from `usine.md`, as before the file
    existed, with a notice; in the second case `unreadable` says why, and a merge is refused.
    """
    working = _working_tree(root)
    guard = on_main(root, GUARD_PATH)
    path = GUARD_PATH.as_posix()
    if guard.text is None:
        if guard.why is not None:
            note = f"{path} cannot be read on origin/main ({guard.why}): its keys are read from {CONFIG_PATH.as_posix()}"
        else:
            note = f"{path} is absent on origin/main: its keys are read from {CONFIG_PATH.as_posix()}"
        return Loaded(working, [note], guard.why)
    notices: list[str] = []
    config = {key: value for key, value in working.items() if key not in SENSITIVE_KEYS}
    for key in sorted(working.keys() & SENSITIVE_KEYS):
        notices.append(
            f"`{key}` in {CONFIG_PATH.as_posix()} is dropped: a key that bounds the agent counts only in {path} on origin/main"
        )
    for key, values in parse(guard.text).items():
        if key in SENSITIVE_KEYS:
            config[key] = values
        else:
            notices.append(f"`{key}` in {path} is ignored: it is not a key that bounds the agent")
    return Loaded(config, notices, None)


def load(root: Path) -> dict[str, list[str]]:
    """The configuration of the project at `root`; empty when it has none or it is unreadable."""
    return load_checked(root).config
