"""PreToolUse hook: the ticket budget of a feature, a standard common to every forge project.

The design of a feature declares `feature-tickets: N` in its header, and the hook holds it at two
moments:

- **Writing a design.** An Edit, Write or MultiEdit of a `design.md` that leaves `feature-tickets: N`
  in its header passes only when N is at most `CEILING`, at least 1 once the design is accepted,
  never above a budget the design was once accepted with (read from the file, its git history and
  the hook's state file, so that taking `statut: accepte` off and back on raises nothing), and never
  below the tickets the feature already has. A design is accepted only with the key, and an
  accepted design may not remove it. A shell command that names a `design.md`, writes, and carries
  `statut: accepte` or `feature-tickets` is refused: these are written with Edit or Write, so that
  they are checked here.
- **Opening a ticket.** `gh issue create`, a POST by `gh api` on `repos/<owner>/<repo>/issues`, a
  `createIssue` mutation by `gh api graphql` and the issue tools of a GitHub MCP server are read for
  the ticket's body, also inside `sh -c`, `bash -c`, `eval`, a shell fed by a heredoc, and behind a
  wrapper (`env`, `sudo`, `timeout`, `xargs`...). Its `Motif :` line places it: `to-tickets F-NNNN`
  belongs to that feature; `fusion-bloquee` belongs to the feature of its `Feature: F-NNNN` line,
  which it must carry; `main-rouge`, `securite` and a human's request (`demande-<who>`) are out of
  every budget; `feature-new F-NNNN`, the tracking ticket of a feature, is out of budget too, one
  per feature. A ticket without an admitted reason is refused. An existing ticket with a
  `Feature: F-NNNN` line and no admitted reason still uses its feature's budget. A ticket of a
  feature is refused when its design (`<feature-dir>/NNNN-*/design.md`, header `feature: F-NNNN`;
  `feature-dir` defaults to the value of the plugin's `usine.md` template) is missing, not
  accepted, has no `feature-tickets`, has one above `CEILING`, or when the tickets the feature
  already has fill its budget: those GitHub's search finds, open or closed, plus those this hook
  let through in the last `RESERVATION_SECONDS` that the search may not show yet.
- **Editing a ticket.** `gh issue edit`, a PATCH by `gh api` on `repos/<owner>/<repo>/issues/<n>`
  and the update tool of a GitHub MCP server may not add, remove or change a `Motif :` or
  `Feature:` line of the ticket's body. A body set by an `updateIssue` mutation is refused.

A body the hook cannot read is refused: a variable (`"$BODY"`), a command substitution other than
`$(cat <<'EOF' ... EOF)`, a heredoc whose unquoted delimiter lets the shell expand it, an editor or
a pipe. So are a count it cannot make (no gh, the network, a gh error or timeout), an alias of gh,
a gh called through a variable, and a call to `api.github.com` that names issues or GraphQL by
another client (`curl`...).

The ceiling is a constant of the plugin, not a key of `docs/agents/usine.md`. As the other guards,
this one guards against an accident, not against intent. `hooks.json` turns a crash into a refusal.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

from guard_git import (
    HEREDOC,
    _commands,
    _run,
    _standard_input_text,
    api_readings,
    gh_act,
    gh_command,
    parse_api,
    read_text_or_none,
)
from guard_readonly import reader_refusal
from usine import load, parse, project_root

CEILING = 15
FEATURE_DIR_KEY = "feature-dir"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "usine.md"
OUT_OF_BUDGET = frozenset({"main-rouge", "securite"})
# A human's own request: `demande-<who>`, the repository naming its human after the dash.
HUMAN_REQUEST = re.compile(r"^demande-[A-Za-z0-9_-]+$")
SEARCH_LIMIT = "1000"
# How long a ticket the hook let through counts on top of GitHub's search, whose index lags.
RESERVATION_SECONDS = 600
STATE_FILE = "ticket-budget.json"
HISTORY_DEPTH = 30

PREFIX = "Blocked by the forge plugin (guard_ticket_budget)"
RESPLIT = f"re-split the feature with the product-owner to at most {CEILING} tickets"
ADD_A_PART = "add a part to an existing ticket (`Refs #n`)"
NO_REASON = (
    "every ticket names its reason: Motif : <one of the admitted reasons> (`to-tickets F-NNNN`,"
    " `fusion-bloquee #<pr>` with `Feature: F-NNNN`, `main-rouge <run>`, `securite`,"
    " `demande-<who>`, `feature-new F-NNNN`)"
)
UNREADABLE = (
    "the ticket's body cannot be read (a variable, a command substitution, an expanded heredoc, an"
    " editor or a pipe), so its feature budget cannot be checked: pass it with --body '<text>',"
    " a quoted heredoc (<<'EOF'), or --body-file and a readable file"
)

MOTIF_LINE = re.compile(r"^[ \t]*Motif[ \t]*:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)
FEATURE_LINE = re.compile(r"^[ \t]*Feature[ \t]*:[ \t]*(F-\d{4})\b", re.MULTILINE)
NAMED_FEATURE = re.compile(r"^(?:to-tickets|feature-new)\s+(F-\d{4})\b")
ISSUES_ENDPOINT = re.compile(r"^/?repos/([^/]+)/([^/]+)/issues/?(?:\?.*)?$")
ISSUE_ENDPOINT = re.compile(r"^/?repos/([^/]+)/([^/]+)/issues/(\d+)/?(?:\?.*)?$")
ISSUE_URL = re.compile(r"^https?://[^/]+/([^/]+)/([^/]+)/issues/(\d+)/?$")
GRAPHQL_BODY = re.compile(r'\bbody\s*:\s*(?:"((?:[^"\\]|\\.)*)"|\$(\w+))')
SHELL_ACCEPTANCE = re.compile(r"statut\W{0,3}accepte\b|en-revue\W{1,3}accepte\b")
API_GITHUB = re.compile(r"api\.github\.com/+(?:repos/[^/\s'\"]+/[^/\s'\"]+/issues\b|graphql\b)")
GH_WORD = re.compile(r"(?:^|[/\\])gh(?:\.exe)?$", re.IGNORECASE)
GH_IN_TEXT = re.compile(r"(?:^|[\s=;|&'\"/\\(])gh(?:\.exe)?(?=$|[\s;|&'\")])", re.IGNORECASE)
SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
ALIASES = frozenset({"alias", "set-alias", "new-alias", "sal", "nal"})

# `$` and the backtick the shell expands, swapped for private-use characters before the words are
# split: a word that still holds one depends on the shell's state, which the hook cannot read.
DOLLAR, TICK = "", ""
MARKERS = (DOLLAR, TICK)
EXPANDS = re.compile(r"[A-Za-z_0-9{(@*#?!$'\"-]")
CAT_HEREDOC = re.compile(DOLLAR + r"\(\s*cat\s+<<-?\s*(['\"]?)(\w+)\1\s*\)")

# `gh issue create` and `gh issue edit` options that take a value (the next word, or `--name=value`).
CREATE_VALUE_OPTIONS = frozenset(
    {"--title", "-t", "--body", "-b", "--body-file", "-F", "--assignee", "-a", "--label", "-l"}
    | {"--milestone", "-m", "--project", "-p", "--repo", "-R", "--template", "-T", "--recover"}
    | {"--type"}
)
EDIT_VALUE_OPTIONS = frozenset(
    {"--title", "-t", "--body", "-b", "--body-file", "-F", "--milestone", "-m", "--repo", "-R"}
    | {"--add-assignee", "--remove-assignee", "--add-label", "--remove-label", "--type"}
    | {"--add-project", "--remove-project"}
)

Runner = Callable[[list[str], str | None], str | None]


class Placement(NamedTuple):
    """Where a ticket sits: `kind` is `out`, `feature`, `tracking` or `refused`."""

    kind: str
    detail: str = ""


class Creation(NamedTuple):
    """A ticket a command creates: its body (None when unreadable) and its repository, if named."""

    body: str | None
    repo: str | None


class Edit(NamedTuple):
    """A ticket body a command replaces: the ticket, the new body (None when unreadable), the repo."""

    number: str
    body: str | None
    repo: str | None


class Gestures(NamedTuple):
    """What a command does to tickets: creations, edits, and refusals found on the way."""

    creations: list[Creation]
    edits: list[Edit]
    refusals: list[str]


class Heredoc(NamedTuple):
    name: str
    text: str
    literal: bool  # False when the shell expands it (unquoted delimiter, an expansion inside)


# --- State --------------------------------------------------------------------------------------


class State:
    """The hook's memory between calls, in `$CLAUDE_PLUGIN_DATA/ticket-budget.json`.

    `reservations`: the tickets let through lately, each `{key, kind, time, seen}` (`seen`, the
    count GitHub's search gave then). `accepted`: per design, the lowest budget it was accepted
    with. Without `CLAUDE_PLUGIN_DATA` (an older Claude Code) the hook keeps no memory.
    """

    def __init__(self, data: dict) -> None:
        self.data = data
        self.changed = False
        now = time.time()
        reservations = data.get("reservations")
        self.reservations: list[dict] = [
            item
            for item in (reservations if isinstance(reservations, list) else [])
            if isinstance(item, dict)
            and isinstance(item.get("time"), (int, float))
            and now - item["time"] < RESERVATION_SECONDS
        ]
        accepted = data.get("accepted")
        self.accepted: dict[str, int] = {
            key: value
            for key, value in (accepted.items() if isinstance(accepted, dict) else [])
            if isinstance(value, int)
        }

    def reserved(self, key: str, kind: str) -> list[dict]:
        found = [
            item for item in self.reservations if (item.get("key"), item.get("kind")) == (key, kind)
        ]
        return sorted(found, key=lambda item: item["time"])

    def reserve(self, key: str, kind: str, seen: int) -> None:
        self.reservations.append({"key": key, "kind": kind, "time": time.time(), "seen": seen})
        self.changed = True

    def accept(self, key: str, budget: int) -> None:
        if self.accepted.get(key, budget + 1) > budget:
            self.accepted[key] = budget
            self.changed = True

    def dump(self) -> str:
        return json.dumps({"reservations": self.reservations, "accepted": self.accepted})


@contextmanager
def state_file() -> Iterator[State]:
    """The state, locked for the whole call where the platform locks, written back if changed."""
    directory = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not directory:
        yield State({})
        return
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / STATE_FILE
    with open(folder / (STATE_FILE + ".lock"), "a", encoding="utf-8") as lock:
        try:
            import fcntl  # POSIX only: Windows runs without the lock

            fcntl.flock(lock, fcntl.LOCK_EX)
        except ImportError:
            pass
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            data = {}
        state = State(data if isinstance(data, dict) else {})
        yield state
        if state.changed:
            temporary = path.with_suffix(".tmp")
            temporary.write_text(state.dump(), encoding="utf-8")
            temporary.replace(path)


# --- Design headers ---------------------------------------------------------------------------


def front_matter(text: str) -> dict[str, str]:
    """The `key: value` lines of the header between the first two `---` lines; empty without one."""
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    header: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return header
        key, colon, value = line.partition(":")
        if colon and key.strip() and not key.startswith((" ", "\t")):
            header.setdefault(key.strip(), value.strip())
    return {}


def budget_of(header: Mapping[str, str]) -> int | None:
    """The declared `feature-tickets`, or None when it is absent or not a whole number."""
    value = header.get("feature-tickets", "")
    return int(value) if re.fullmatch(r"\d+", value) else None


def accepted(header: Mapping[str, str]) -> bool:
    return header.get("statut", "") == "accepte"


class DesignContext(NamedTuple):
    """What judging a design write needs beyond its text."""

    floor: int | None  # the lowest budget the design was ever accepted with, None if never
    published: Callable[[str], int | None]  # the tickets a feature has; None when unknown


def design_refusal(old: str, new: str, context: DesignContext) -> str | None:
    """Why a design may not go from `old` to `new`, or None."""
    before, after = front_matter(old), front_matter(new)
    budget, previous = budget_of(after), budget_of(before)
    if budget is None:
        if not accepted(after):
            return None
        if accepted(before) and previous is not None:
            return f"the design is accepted with `feature-tickets: {previous}` and the write removes it: the budget is closed"
        if accepted(before):
            return None
        return (
            "a design is accepted only with `feature-tickets: N` in its header, N from 1 to"
            f" {CEILING}: declare it, or {RESPLIT}"
        )
    if budget == previous and accepted(after) == accepted(before):
        return None
    if budget > CEILING or (accepted(after) and budget < 1):
        return f"the design declares `feature-tickets: {budget}`, outside 1 to {CEILING}: {RESPLIT}"
    if accepted(before) and previous is not None and budget > previous:
        return f"the design is accepted with `feature-tickets: {previous}` and the write raises it to {budget}: the budget is closed"
    if context.floor is not None and budget > context.floor:
        return (
            f"the design was accepted with `feature-tickets: {context.floor}` and the write raises"
            f" it to {budget}: the budget of an accepted design never rises, {ADD_A_PART}"
        )
    if not (accepted(after) or accepted(before) or context.floor is not None):
        return None  # a design never accepted has no tickets yet
    feature = after.get("feature") or before.get("feature") or ""
    if not re.fullmatch(r"F-\d{4}", feature):
        return "the design names no `feature: F-NNNN`, so the tickets it has cannot be counted"
    count = context.published(feature)
    if count is None:
        return (
            f"the tickets of {feature} cannot be counted (gh absent, the network, or a gh error):"
            " the budget is refused as a precaution"
        )
    if budget < count:
        return f"{feature} already has {count} tickets: `feature-tickets: {budget}` is below them"
    return None


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path)[-1]


def _edited(old: str, edits: list[Mapping[str, object]]) -> str | None:
    """`old` with the edits applied as the Edit tool applies them; None when one cannot apply."""
    text = old
    for edit in edits:
        before, after = edit.get("old_string"), edit.get("new_string")
        if not isinstance(before, str) or not isinstance(after, str) or before not in text:
            return None
        text = (
            text.replace(before, after)
            if edit.get("replace_all")
            else text.replace(before, after, 1)
        )
    return text


def history_budgets(path: Path) -> list[int]:
    """The budgets of the versions of `path` that git holds as accepted, on any ref."""
    git = shutil.which("git")
    if git is None or not path.parent.is_dir():
        return []
    cwd = str(path.parent)
    log = _run([git, "log", "--all", "--format=%H", "-n", str(HISTORY_DEPTH), "--", path.name], cwd)
    if log is None or log.returncode != 0:
        return []
    budgets: list[int] = []
    for commit in log.stdout.split():
        shown = _run([git, "show", f"{commit}:./{path.name}"], cwd)
        if shown is None or shown.returncode != 0:
            continue
        header = front_matter(shown.stdout)
        if accepted(header) and (budget := budget_of(header)) is not None:
            budgets.append(budget)
    return budgets


def design_key(root: Path, header: Mapping[str, str], path: Path) -> str:
    return f"{root.resolve()}|{header.get('feature') or path.parent.name}"


def write_refusal(
    tool: str,
    tool_input: Mapping[str, object],
    root: Path,
    state: State,
    run: Runner,
    cwd: str | None,
) -> str | None:
    """Why an Edit, Write or MultiEdit of a `design.md` may not run, or None."""
    path = tool_input.get("file_path")
    if not isinstance(path, str) or _basename(path) != "design.md":
        return None
    target = Path(path)
    old = "" if not target.exists() else read_text_or_none(path)
    if tool == "Write":
        content = tool_input.get("content")
        if not isinstance(content, str):
            return None
        new: str | None = content
        old = old or ""  # a Write replaces a file it cannot read: judge the new text alone
    else:
        edits: list[Mapping[str, object]]
        if tool == "MultiEdit":
            raw = tool_input.get("edits")
            edits = (
                [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
            )
        else:
            edits = [tool_input]
        if old is None:
            written = " ".join(str(edit.get("new_string", "")) for edit in edits)
            touches = "accepte" in written or "feature-tickets" in written
            return "the design cannot be read, so its budget cannot be checked" if touches else None
        new = _edited(old, edits)
    if new is None:
        return None
    before, after = front_matter(old), front_matter(new)
    key = design_key(root, after or before, target)
    known = [*history_budgets(target), *([state.accepted[key]] if key in state.accepted else [])]

    def published(feature: str) -> int | None:
        indexed = count_tickets(feature, None, cwd, run)
        reserved = state.reserved(f"{root.resolve()}|{feature}", "feature")
        return None if indexed is None else with_reservations(indexed, reserved)

    context = DesignContext(floor=min(known) if known else None, published=published)
    if reason := design_refusal(old, new, context):
        return reason
    for header in (before, after):
        if accepted(header) and (budget := budget_of(header)) is not None:
            state.accept(key, budget)  # the floor survives taking `statut: accepte` off
    return None


def shell_design_refusal(command: str) -> str | None:
    """A shell command that writes the acceptance or the budget of a design: only Edit or Write may."""
    if "design.md" not in command:
        return None
    if not SHELL_ACCEPTANCE.search(command) and "feature-tickets" not in command:
        return None
    if reader_refusal(command) is None:
        return None
    return (
        "write the acceptance and the `feature-tickets` of a design with Edit or Write, so that its"
        " ticket budget is checked"
    )


# --- Ticket bodies ----------------------------------------------------------------------------


def placement(body: str) -> Placement:
    """Where the ticket of `body` sits: its `Motif :` line, one of the admitted reasons, rules."""
    text = body.replace("\r\n", "\n")
    motif_match = MOTIF_LINE.search(text)
    feature_match = FEATURE_LINE.search(text)
    motif = motif_match.group(1) if motif_match else ""
    case = motif.split()[0] if motif else ""
    if case in OUT_OF_BUDGET or HUMAN_REQUEST.match(case):
        return Placement("out")
    if case in ("to-tickets", "feature-new"):
        named = NAMED_FEATURE.match(motif)
        if named is None:
            return Placement(
                "refused", f"a `Motif : {case}` line names its feature: `{case} F-NNNN`"
            )
        return Placement("feature" if case == "to-tickets" else "tracking", named.group(1))
    if case == "fusion-bloquee":
        if feature_match is None:
            return Placement(
                "refused",
                "a `fusion-bloquee` ticket names its feature with a `Feature: F-NNNN` line",
            )
        return Placement("feature", feature_match.group(1))
    return Placement("refused", NO_REASON)


def counts_for(body: str) -> str | None:
    """The feature whose budget an existing ticket uses, or None.

    A ticket opened before the reason was required, with a `Feature: F-NNNN` line and no admitted
    reason, still uses its feature's budget: the budget stays closed on the past too.
    """
    place = placement(body)
    if place.kind == "feature":
        return place.detail
    if place.kind == "refused" and (found := FEATURE_LINE.search(body.replace("\r\n", "\n"))):
        return found.group(1)
    return None


def signature(body: str) -> tuple[list[str], list[str]]:
    """The `Motif :` and `Feature:` lines of a body, which an edit may not change."""
    text = body.replace("\r\n", "\n")
    return MOTIF_LINE.findall(text), FEATURE_LINE.findall(text)


# --- Shell words ------------------------------------------------------------------------------


def mark_expansions(command: str) -> str:
    """`command` with each `$` and backtick the shell expands swapped for `DOLLAR` and `TICK`.

    Single quotes keep them literal, and so does a backslash; heredoc bodies are left as they are,
    on the same lines `split_heredocs` cuts, so that the words `_commands` gives keep the markers.
    """
    out: list[str] = []
    quote = ""
    delimiter: str | None = None
    for line in command.splitlines():
        if delimiter is not None:
            out.append(line)
            if line.strip() == delimiter:
                delimiter = None
            continue
        marked: list[str] = []
        index = 0
        while index < len(line):
            char = line[index]
            following = line[index + 1 : index + 2]
            if quote == "'":
                quote = "" if char == "'" else quote
                marked.append(char)
            elif char == "\\":
                marked.append(line[index : index + 2])
                index += 1
            elif char == "`":
                marked.append(TICK)
            elif char == "$" and EXPANDS.match(following) and not (quote and following in "'\""):
                marked.append(DOLLAR)
            else:
                if quote == '"' and char == '"':
                    quote = ""
                elif not quote and char in "'\"":
                    quote = char
                marked.append(char)
            index += 1
        out.append("".join(marked))
        if match := HEREDOC.search(line):
            delimiter = match.group(2)
    return "\n".join(out)


def heredocs(command: str) -> list[Heredoc]:
    """The heredocs of `command`, cut as `split_heredocs` cuts them, each with its body if literal."""
    found: list[Heredoc] = []
    current: tuple[str, bool] | None = None
    lines: list[str] = []
    for line in command.splitlines():
        if current is not None:
            if line.strip() == current[0]:
                name, quoted = current
                body = "\n".join(lines)
                expanded = not quoted and re.search(r"[`\\]|\$" + EXPANDS.pattern, body)
                found.append(Heredoc(name, body, not expanded))
                current, lines = None, []
            else:
                lines.append(line)
            continue
        if match := HEREDOC.search(line):
            current = (match.group(2), bool(match.group(1)))
    if current is not None:
        found.append(Heredoc(current[0], "\n".join(lines), False))
    return found


def heredoc_text(docs: list[Heredoc], name: str) -> str | None:
    """The body of the one heredoc named `name`; None when it is expanded, missing or not alone."""
    named = [doc for doc in docs if doc.name == name]
    return named[0].text if len(named) == 1 and named[0].literal else None


def _inline(value: str, docs: list[Heredoc]) -> str | None:
    """A value typed in the command; `$(cat <<'EOF' ...)` is read from its heredoc, if literal."""
    parts: list[str] = []
    last = 0
    for match in CAT_HEREDOC.finditer(value):
        text = heredoc_text(docs, match.group(2))
        if text is None:
            return None
        parts += [value[last : match.start()], text]
        last = match.end()
    result = "".join(parts) + value[last:]
    return None if any(marker in result for marker in MARKERS) else result


def _readable(word: str) -> bool:
    return not any(marker in word for marker in MARKERS)


def _path_in(cwd: str | None, path: str) -> str:
    return path if Path(path).is_absolute() or cwd is None else str(Path(cwd) / path)


def _read(cwd: str | None, path: str) -> str | None:
    return read_text_or_none(_path_in(cwd, path)) if _readable(path) else None


def _value(
    word: str, words: list[str], index: int, names: tuple[str, str]
) -> tuple[str, int] | None:
    """The value of option `names` (long, short) at `words[index]`, and the next index; or None."""
    long, short = names
    if word == long or word == short:
        return (words[index + 1] if index + 1 < len(words) else ""), index + 2
    if word.startswith(long + "="):
        return word[len(long) + 1 :], index + 1
    if word.startswith(short) and not word.startswith("--") and len(word) > 2:
        rest = word[2:]
        return (rest[1:] if rest.startswith("=") else rest), index + 1
    return None


def _repo_of(words: list[str]) -> str | None:
    repo = None
    for index, word in enumerate(words):
        found = _value(word, words, index, ("--repo", "-R"))
        if found is not None:
            repo = found[0]
    return repo


def _stdin(redirections: list[tuple[str, str]], cwd: str | None, docs: list[Heredoc]) -> str | None:
    """What the shell feeds to this command's standard input: its last `<` file or heredoc."""
    last = next((item for item in reversed(redirections) if item[0] in ("<", "<<", "<<-")), None)
    if last is None:
        return None
    if last[0] != "<":
        return heredoc_text(docs, last[1])
    if not _readable(last[1]):
        return None
    return _standard_input_text([last], cwd, "", read_text_or_none)


def _redirections(words: list[str]) -> list[tuple[str, str]]:
    return [
        (word, words[index + 1] if index + 1 < len(words) else "")
        for index, word in enumerate(words)
        if word in ("<", "<<", "<<-")
    ]


def _issue_body(
    rest: list[str], words: list[str], cwd: str | None, docs: list[Heredoc], options: frozenset[str]
) -> tuple[bool, str | None, list[str]]:
    """`(given, body, positional words)` of a `gh issue create` or `edit`; body None if unreadable."""
    body: str | None = None
    given = False
    positional: list[str] = []
    index = 0
    while index < len(rest):
        word = rest[index]
        text = _value(word, rest, index, ("--body", "-b"))
        path = _value(word, rest, index, ("--body-file", "-F"))
        if text is not None:
            body, index, given = _inline(text[0], docs), text[1], True
        elif path is not None:
            name, index, given = path[0], path[1], True
            body = _stdin(_redirections(words), cwd, docs) if name == "-" else _read(cwd, name)
        elif word in options:
            index += 2
        elif word in ("<", "<<", "<<-", ">", ">>", "2>", "&>"):
            index += 2
        else:
            if not word.startswith("-"):
                positional.append(word)
            index += 1
    return given, body, positional


def _api_body(
    options: list[tuple[str, str]],
    redirections: list[tuple[str, str]],
    cwd: str | None,
    docs: list[Heredoc],
) -> str | None:
    """The `body` a `gh api` call sends, `""` when it sends none; None when it cannot be read."""
    body: str | None = ""
    for name, value in options:
        if name == "input":
            raw = _stdin(redirections, cwd, docs) if value == "-" else _read(cwd, value)
            try:
                document = json.loads(raw) if raw is not None else None
            except ValueError:
                document = None
            if not isinstance(document, dict):
                body = None
            else:
                found = document.get("body", "")
                body = found if isinstance(found, str) else None
            continue
        key, _, content = value.partition("=")
        if key != "body":
            if not _readable(key):
                body = None  # a field whose name the shell gives may be the body
            continue
        if name == "field" and content.startswith("@"):
            source = content[1:]
            body = _stdin(redirections, cwd, docs) if source == "-" else _read(cwd, source)
        else:
            body = _inline(content, docs)
    return body


def _graphql_gestures(
    words: list[str], redirections: list[tuple[str, str]], cwd: str | None, docs: list[Heredoc]
) -> Gestures:
    """What a `gh api graphql` call does to tickets: a `createIssue`, or a refused `updateIssue`.

    The body is the `body:` string of the mutation, or the field its `$variable` names; a variable
    the call does not fill (one fed by a JSON `--input`) leaves the body unreadable.
    """
    options = parse_api(words).options
    parts = [" ".join(words), *(doc.text for doc in docs)]
    for name, value in options:
        if name == "input" and value != "-":
            parts.append(_read(cwd, value) or "")
        elif value.partition("=")[2].startswith("@"):
            parts.append(_read(cwd, value.partition("=")[2][1:]) or "")
    text = "\n".join(parts)
    found = Gestures([], [], [])
    if "updateIssue" in text and GRAPHQL_BODY.search(text):
        found.refusals.append("a ticket's body is edited with `gh issue edit`, not `updateIssue`")
    if "createIssue" not in text:
        return found
    match = GRAPHQL_BODY.search(text)
    if match is None:
        found.creations.append(Creation("", None))
    elif match.group(1) is not None:
        try:
            literal = json.loads(f'"{match.group(1)}"')
        except ValueError:
            literal = match.group(1).replace("\\n", "\n")
        found.creations.append(Creation(literal if isinstance(literal, str) else None, None))
    else:
        fields = [(n, v) for n, v in options if v.startswith(f"{match.group(2)}=")]
        renamed = [(n, "body=" + v.partition("=")[2]) for n, v in fields]
        body = _api_body(renamed, redirections, cwd, docs) if fields else None
        found.creations.append(Creation(body, None))
    return found


def api_gestures(args: list[str], cwd: str | None, docs: list[Heredoc]) -> Gestures:
    """What a `gh api` call does to tickets, over every reading of its words."""
    found = Gestures([], [], [])
    readings = api_readings(args)
    if readings is None:
        if any("/issues" in word or word == "graphql" for word in args):
            found.creations.append(Creation(None, None))
        return found
    for kept, redirections in readings:
        call = parse_api(kept)
        if not _readable(call.endpoint):
            found.refusals.append("a `gh api` endpoint the shell gives cannot be read")
            continue
        if call.endpoint == "graphql":
            graphql = _graphql_gestures(kept, redirections, cwd, docs)
            found.creations.extend(graphql.creations)
            found.refusals.extend(graphql.refusals)
            continue
        method = (call.method or ("POST" if call.options else "GET")).upper()
        if method == "GET":
            continue
        if (endpoint := ISSUES_ENDPOINT.match(call.endpoint)) and method == "POST":
            owner, repo = endpoint.group(1), endpoint.group(2)
            named = None if "{" in owner or "{" in repo else f"{owner}/{repo}"
            body = _api_body(call.options, redirections, cwd, docs)
            found.creations.append(Creation(body, named))
        elif item := ISSUE_ENDPOINT.match(call.endpoint):
            body = _api_body(call.options, redirections, cwd, docs)
            if body != "":
                owner, repo = item.group(1), item.group(2)
                named = None if "{" in owner or "{" in repo else f"{owner}/{repo}"
                found.edits.append(Edit(item.group(3), body, named))
    return found


def _gh_words(words: list[str]) -> list[str] | None:
    """The words of the gh call in `words` from `gh` on, wherever a wrapper put it; None if none."""
    for index, word in enumerate(words):
        if GH_WORD.search(word):
            return ["gh", *words[index + 1 :]]
    return None


def _script_of(words: list[str], docs: list[Heredoc]) -> str | None:
    """The script a shell, `eval` or a shell fed by a heredoc runs; None when `words` runs none."""
    names = [_basename(word).lower().removesuffix(".exe") for word in words]
    for index, name in enumerate(names):
        if name == "eval":
            return " ".join(words[index + 1 :])
        if name not in SHELLS:
            continue
        position = index + 1
        while position < len(words):
            word = words[position]
            if word.startswith("-") and not word.startswith("--") and "c" in word:
                return words[position + 1] if position + 1 < len(words) else ""
            if word in ("<<", "<<-") and position + 1 < len(words):
                named = [doc.text for doc in docs if doc.name == words[position + 1]]
                return "\n".join(named)  # an expanded body keeps its markers once re-read
            if word in ("-o", "+o", "-O", "+O"):
                position += 2
            elif word.startswith(("-", "+")):
                position += 1
            else:
                break
    return None


def _merge(into: Gestures, other: Gestures) -> None:
    into.creations.extend(other.creations)
    into.edits.extend(other.edits)
    into.refusals.extend(other.refusals)


SUBSTITUTIONS = re.compile(DOLLAR + r"\((.*)\)|" + TICK + "(.*?)" + TICK, re.DOTALL)


def _substitutions(word: str) -> list[str]:
    """The commands a word runs by a quoted substitution, `$(cat <<'EOF' ...)` aside."""
    found: list[str] = []
    for match in SUBSTITUTIONS.finditer(CAT_HEREDOC.sub("", word)):
        inner = match.group(1) if match.group(1) is not None else match.group(2)
        found.append(inner.replace(DOLLAR, "$").replace(TICK, "`"))
    return found


def gestures(command: str, cwd: str | None, depth: int = 0) -> Gestures:
    """What `command` does to tickets, by gh, a nested shell, an alias or another HTTP client."""
    found = Gestures([], [], [])
    if API_GITHUB.search(command):
        found.refusals.append(
            "a call to api.github.com that names issues or GraphQL goes through gh, so that the"
            " ticket budget is checked: it is refused as a precaution"
        )
    docs = heredocs(command)
    for item in _commands(mark_expansions(command)):
        if isinstance(item, str):
            continue
        words = item
        while words and "=" in words[0] and not words[0].startswith("-"):
            words = words[1:]
        if not words:
            continue
        if words[0].lower() in ALIASES and any(GH_IN_TEXT.search(word) for word in words[1:]):
            found.refusals.append("an alias of gh hides the tickets it opens: call gh by its name")
            continue
        nested = [inner for word in words for inner in _substitutions(word)]
        script = _script_of(words, docs)
        if script is not None:
            first = script.split()[0] if script.split() else ""
            if not _readable(first):
                found.refusals.append("a script the shell gives by a variable cannot be read")
                continue
            nested.append(script)
        if nested and depth >= 3:
            found.refusals.append("too many nested shells to read")
            continue
        for inner in nested:
            _merge(found, gestures(inner, cwd, depth + 1))
        if script is not None:
            continue
        call = _gh_words(words)
        if call is None:
            if not _readable(words[0]) and {"issue", "api"} & set(words):
                found.refusals.append("gh called through a variable cannot be read")
            continue
        act = gh_act(call)
        if act is None:
            if not all(_readable(word) for word in call):
                found.refusals.append("a gh subcommand the shell gives cannot be read")
            continue
        group, verb, rest = act
        if not (_readable(group) and _readable(verb)):
            found.refusals.append("a gh subcommand the shell gives cannot be read")
        elif group == "issue" and verb in ("create", "new"):
            given, body, _ = _issue_body(rest, call, cwd, docs, CREATE_VALUE_OPTIONS)
            repo = _repo_of(call)
            unreadable = not given or (repo is not None and not _readable(repo))
            found.creations.append(Creation(None if unreadable else body, repo))
        elif group == "issue" and verb == "edit":
            given, body, positional = _issue_body(rest, call, cwd, docs, EDIT_VALUE_OPTIONS)
            if given:
                found.edits.extend(_issue_edits(positional, body, _repo_of(call)))
        elif group == "api":
            _merge(found, api_gestures((gh_command(call) or [])[1:], cwd, docs))
    return found


def _issue_edits(positional: list[str], body: str | None, repo: str | None) -> list[Edit]:
    edits: list[Edit] = []
    for word in positional or [""]:
        if url := ISSUE_URL.match(word):
            edits.append(Edit(url.group(3), body, f"{url.group(1)}/{url.group(2)}"))
        else:
            number = word.lstrip("#")
            edits.append(Edit(number if number.isdigit() else "", body, repo))
    return edits


# --- Designs and counts -----------------------------------------------------------------------


def feature_dir(config: Mapping[str, list[str]]) -> str | None:
    """The key `feature-dir` of the project, else its value in the plugin's `usine.md` template."""
    directories = config.get(FEATURE_DIR_KEY) or parse(read_text_or_none(str(TEMPLATE)) or "").get(
        FEATURE_DIR_KEY, []
    )
    return directories[-1].strip("<>") if directories else None


def find_design(root: Path, directory: str, feature: str) -> list[Path]:
    """The `design.md` files of `feature` under the feature folder, header `feature:` checked."""
    digits = feature.removeprefix("F-")
    found: list[Path] = []
    for path in sorted((root / directory).glob(f"{digits}-*/design.md")):
        text = read_text_or_none(str(path))
        if text is not None and front_matter(text).get("feature") == feature:
            found.append(path)
    return found


def run_gh(argv: list[str], cwd: str | None) -> str | None:
    """The output of `gh <argv>`, or None without gh, on a failure or a timeout."""
    gh = shutil.which("gh")
    if gh is None:
        return None
    completed = _run([gh, *argv], cwd)
    if completed is None or completed.returncode != 0:
        return None
    return completed.stdout


def matching_issues(
    phrases: tuple[str, ...], repo: str | None, cwd: str | None, run: Runner
) -> dict[int, str] | None:
    """The issues, open or closed, whose body holds one of `phrases`; None when gh cannot say."""
    found: dict[int, str] = {}
    for phrase in phrases:
        argv = ["issue", "list", "--state", "all", "--search", f'"{phrase}" in:body']
        argv += ["--json", "number,body", "--limit", SEARCH_LIMIT]
        if repo:
            argv += ["--repo", repo]
        output = run(argv, cwd)
        if output is None:
            return None
        try:
            issues = json.loads(output)
        except ValueError:
            return None
        if not isinstance(issues, list):
            return None
        for issue in issues:
            if not isinstance(issue, dict):
                return None
            number, body = issue.get("number"), issue.get("body")
            if not isinstance(number, int) or not isinstance(body, str):
                return None
            found[number] = body
    return found


def count_tickets(feature: str, repo: str | None, cwd: str | None, run: Runner) -> int | None:
    """The tickets GitHub's search finds that use the budget of `feature`; None when unknown."""
    issues = matching_issues((f"to-tickets {feature}", f"Feature: {feature}"), repo, cwd, run)
    if issues is None:
        return None
    return sum(1 for body in issues.values() if counts_for(body) == feature)


def with_reservations(count: int, reservations: list[dict]) -> int:
    """The count, raised by the tickets let through that the search may not show yet.

    Each reservation saw `seen` tickets then; it and the ones after it make at least `seen + k`.
    """
    total = len(reservations)
    return max(
        [count] + [int(item.get("seen", 0)) + total - k for k, item in enumerate(reservations)]
    )


def tracking_tickets(
    feature: str, repo: str | None, cwd: str | None, run: Runner
) -> list[int] | None:
    """The tracking tickets `feature` already has; None when they cannot be read."""
    issues = matching_issues((f"feature-new {feature}",), repo, cwd, run)
    if issues is None:
        return None
    tracking = Placement("tracking", feature)
    return sorted(number for number, body in issues.items() if placement(body) == tracking)


def ticket_refusal(
    creation: Creation,
    cwd: str | None,
    root: Path,
    config: Mapping[str, list[str]],
    run: Runner,
    state: State,
) -> str | None:
    """Why the ticket `creation` may not be opened, or None (it is then reserved in `state`)."""
    if creation.body is None:
        return UNREADABLE
    place = placement(creation.body)
    if place.kind == "refused":
        return place.detail
    key = f"{root.resolve()}|{place.detail}"
    if place.kind == "tracking":
        existing = tracking_tickets(place.detail, creation.repo, cwd, run)
        if existing is None:
            return (
                f"the tracking tickets of {place.detail} cannot be read (gh absent, the network,"
                " or a gh error): the ticket is refused as a precaution"
            )
        if existing:
            return f"{place.detail} already has its tracking ticket #{existing[0]}: one per feature"
        if state.reserved(key, "tracking"):
            return f"{place.detail} has just been given its tracking ticket: one per feature"
        state.reserve(key, "tracking", 0)
        return None
    if place.kind != "feature":
        return None
    feature = place.detail
    declare = f"declare feature-tickets in the design first, and {RESPLIT}"
    directory = feature_dir(config)
    if directory is None:
        return f"{feature} has no design to read its budget from (key `{FEATURE_DIR_KEY}` absent): {declare}"
    designs = find_design(root, directory, feature)
    if len(designs) != 1:
        found = "no design" if not designs else f"{len(designs)} designs"
        return f"{feature} has {found} under `{directory}/`: {declare}"
    header = front_matter(read_text_or_none(str(designs[0])) or "")
    if not accepted(header):
        return f"the design of {feature} is not accepted: its tickets are published once it is"
    budget = budget_of(header)
    if budget is None:
        return f"the design of {feature} has no `feature-tickets`: {declare}"
    if budget > CEILING:
        return f"the design of {feature} declares `feature-tickets: {budget}`, above {CEILING}: {RESPLIT}"
    indexed = count_tickets(feature, creation.repo, cwd, run)
    if indexed is None:
        return (
            f"the tickets of {feature} cannot be counted (gh absent, the network, or a gh error):"
            " the ticket is refused as a precaution"
        )
    count = with_reservations(indexed, state.reserved(key, "feature"))
    if count >= budget:
        return f"{feature} already has {count} tickets for a budget of {budget}: {ADD_A_PART}"
    state.reserve(key, "feature", indexed)
    return None


def current_body(number: str, repo: str | None, cwd: str | None, run: Runner) -> str | None:
    """The body of ticket `number` now; None when gh cannot give it."""
    if not number.isdigit():
        return None
    argv = ["issue", "view", number, "--json", "body"] + (["--repo", repo] if repo else [])
    output = run(argv, cwd)
    try:
        document = json.loads(output) if output is not None else None
    except ValueError:
        return None
    body = document.get("body") if isinstance(document, dict) else None
    return body if isinstance(body, str) else None


def edit_refusal(edit: Edit, cwd: str | None, run: Runner) -> str | None:
    """Why the body of a ticket may not be replaced, or None."""
    if edit.body is None:
        return UNREADABLE.replace("ticket's body", "ticket's new body")
    old = current_body(edit.number, edit.repo, cwd, run)
    if old is None:
        return (
            f"the body of ticket #{edit.number or '?'} cannot be read (gh absent, the network, or a"
            " gh error), so the edit of its `Motif :` and `Feature:` lines cannot be checked"
        )
    if signature(old) != signature(edit.body):
        return (
            f"the edit changes the `Motif :` or `Feature:` lines of ticket #{edit.number}: they"
            " place it in a budget and stay as written"
        )
    return None


def mcp_gestures(tool: str, tool_input: Mapping[str, object]) -> Gestures | None:
    """The ticket gestures of a GitHub MCP tool; None when the tool is no issue tool of one."""
    if not tool.startswith("mcp__") or "github" not in tool.lower():
        return None
    action = tool.rsplit("__", 1)[-1]
    method = tool_input.get("method")
    owner, name = tool_input.get("owner"), tool_input.get("repo")
    repo = f"{owner}/{name}" if isinstance(owner, str) and isinstance(name, str) else None
    raw = tool_input.get("body", "")
    body = raw if isinstance(raw, str) else None
    if action == "create_issue" or (action == "issue_write" and method == "create"):
        return Gestures([Creation(body, repo)], [], [])
    if action == "update_issue" or (action == "issue_write" and method == "update"):
        if "body" not in tool_input:
            return Gestures([], [], [])
        return Gestures([], [Edit(str(tool_input.get("issue_number", "")), body, repo)], [])
    return None


# --- Entry point ------------------------------------------------------------------------------


def refusal(event: Mapping[str, object], run: Runner = run_gh) -> str | None:
    """Why the tool call of `event` may not run, or None."""
    tool = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict) or not isinstance(tool, str):
        return None
    cwd = _cwd(event)
    if tool in ("Edit", "Write", "MultiEdit"):
        with state_file() as state:
            return write_refusal(tool, tool_input, project_root(event), state, run, cwd)
    if tool in ("Bash", "PowerShell"):
        command = tool_input.get("command")
        if not isinstance(command, str):
            return None
        if reason := shell_design_refusal(command):
            return reason
        found = gestures(command, cwd)
    else:
        mcp = mcp_gestures(tool, tool_input)
        if mcp is None:
            return None
        found = mcp
    if found.refusals:
        return found.refusals[0]
    for edit in found.edits:
        if reason := edit_refusal(edit, cwd, run):
            return reason
    if not found.creations:
        return None
    root = project_root(event)
    config = load(root)
    with state_file() as state:
        for creation in found.creations:
            if reason := ticket_refusal(creation, cwd, root, config, run, state):
                state.changed = False  # the call is refused: nothing it would open is reserved
                return reason
    return None


def _cwd(event: Mapping[str, object]) -> str | None:
    cwd = event.get("cwd")
    return cwd if isinstance(cwd, str) else None


def main() -> int:
    event = json.load(sys.stdin)
    reason = refusal(event if isinstance(event, dict) else {})
    if reason is None:
        return 0
    sys.stderr.write(f"{PREFIX}: {reason}.\n")
    return 2


def guarded_main() -> int:
    """`main`, failing closed: a crash of the guard refuses the call and says so."""
    try:
        return main()
    except Exception as error:  # noqa: BLE001 - any failure of the guard must refuse the call
        sys.stderr.write(
            f"guard_ticket_budget failed ({type(error).__name__}: {error}): the call is refused as"
            " a precaution. This is not a rule of the repository; retry, and tell the human if it"
            " persists.\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(guarded_main())
