"""PreToolUse hook: the ticket budget of a feature, a standard common to every forge project.

The design of a feature declares `feature-tickets: N` in its header, and the hook holds it at two
moments:

- **Accepting a design.** An Edit, Write or MultiEdit of a `design.md` that turns its `statut` to
  `accepte` passes only when the header declares `feature-tickets` as an integer from 1 to
  `CEILING`. Above it, the feature is split. A design already accepted may not raise its budget
  (it may declare one when it had none). A shell command that names a `design.md`, writes, and
  carries `statut: accepte` is refused: the acceptance is written with Edit or Write, so that it
  is checked here.
- **Opening a ticket.** `gh issue create`, a POST by `gh api` on `repos/<owner>/<repo>/issues` and
  a `createIssue` mutation by `gh api graphql` are read for the ticket's body. Its `Motif :` line
  places it: `to-tickets F-NNNN` belongs to that feature; `fusion-bloquee` belongs to the feature
  of its `Feature: F-NNNN` line, which it must carry; `main-rouge`, `securite` and a human's
  request (`demande-<who>`) are out of every budget. Any other ticket that carries a `Feature:
  F-NNNN` line belongs to that feature; one with neither line (a feature's tracking issue) is not
  this hook's concern. A ticket
  of a feature is refused when its design (`<feature-dir>/NNNN-*/design.md`, header `feature:
  F-NNNN`) is missing, not accepted, has no `feature-tickets`, has one above `CEILING`, or when the
  tickets the feature already has, open or closed (`gh issue list --state all --search`), fill
  its budget. A body the hook cannot read, and a count it cannot make (no gh, the network, a gh
  error or timeout), refuse the ticket.

The ceiling is a constant of the plugin, not a key of `docs/agents/usine.md`. As the other guards,
this one guards against an accident, not against intent. `hooks.json` turns a crash into a refusal.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import NamedTuple

from guard_git import (
    _commands,
    _run,
    _standard_input_text,
    api_readings,
    gh_act,
    gh_command,
    parse_api,
    read_text_or_none,
    split_heredocs,
)
from guard_readonly import reader_refusal
from usine import load, project_root

CEILING = 15
FEATURE_DIR_KEY = "feature-dir"
OUT_OF_BUDGET = frozenset({"main-rouge", "securite"})
# A human's own request: `demande-<who>`, the repository naming its human after the dash.
HUMAN_REQUEST = re.compile(r"^demande-[A-Za-z0-9_-]+$")
SEARCH_LIMIT = "1000"

PREFIX = "Blocked by the forge plugin (guard_ticket_budget)"
RESPLIT = f"re-split the feature with the product-owner to at most {CEILING} tickets"
ADD_A_PART = "add a part to an existing ticket (`Refs #n`)"

MOTIF_LINE = re.compile(r"^[ \t]*Motif[ \t]*:[ \t]*(\S.*?)[ \t]*$", re.MULTILINE)
FEATURE_LINE = re.compile(r"^[ \t]*Feature[ \t]*:[ \t]*(F-\d{4})\b", re.MULTILINE)
TO_TICKETS = re.compile(r"^to-tickets\s+(F-\d{4})\b")
ISSUES_ENDPOINT = re.compile(r"^/?repos/([^/]+)/([^/]+)/issues/?(?:\?.*)?$")
GRAPHQL_BODY = re.compile(r'\bbody\s*:\s*(?:"((?:[^"\\]|\\.)*)"|\$(\w+))')
SHELL_ACCEPTANCE = re.compile(r"statut\W{0,3}accepte\b|en-revue\W{1,3}accepte\b")
SUBSTITUTION = ("$(", "`")

# `gh issue create` options that take a value (pflag: the next word, or `--name=value`).
CREATE_VALUE_OPTIONS = frozenset(
    {"--title", "-t", "--body", "-b", "--body-file", "-F", "--assignee", "-a", "--label", "-l"}
    | {"--milestone", "-m", "--project", "-p", "--repo", "-R", "--template", "-T", "--recover"}
    | {"--type"}
)

Runner = Callable[[list[str], str | None], str | None]


class Placement(NamedTuple):
    """Where a ticket sits: `kind` is `none`, `out`, `feature` or `refused`."""

    kind: str
    detail: str = ""


class Creation(NamedTuple):
    """A ticket a command creates: its body (None when unreadable) and its repository, if named."""

    body: str | None
    repo: str | None


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


def design_refusal(old: str, new: str) -> str | None:
    """Why a design may not go from `old` to `new`, or None."""
    before, after = front_matter(old), front_matter(new)
    if not accepted(after):
        return None
    budget = budget_of(after)
    if not accepted(before):
        if budget is None:
            return (
                "a design is accepted only with `feature-tickets: N` in its header, N from 1 to"
                f" {CEILING}: declare it, or {RESPLIT}"
            )
        if not 1 <= budget <= CEILING:
            return f"the design declares `feature-tickets: {budget}`, outside 1 to {CEILING}: {RESPLIT}"
        return None
    previous = budget_of(before)
    if previous is not None and (budget is None or budget > previous):
        shown = "removes it" if budget is None else f"raises it to {budget}"
        return f"the design is accepted with `feature-tickets: {previous}` and the write {shown}: the budget is closed"
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


def write_refusal(tool: str, tool_input: Mapping[str, object]) -> str | None:
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
        if old is None:
            old = ""  # a Write replaces a file it cannot read: judge the new text alone
        return design_refusal(old, content)
    edits: list[Mapping[str, object]]
    if tool == "MultiEdit":
        raw = tool_input.get("edits")
        edits = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    else:
        edits = [tool_input]
    if old is None:
        written = " ".join(str(edit.get("new_string", "")) for edit in edits)
        return (
            "the design cannot be read, so its budget cannot be checked"
            if "accepte" in written
            else None
        )
    new = _edited(old, edits)
    return None if new is None else design_refusal(old, new)


def shell_design_refusal(command: str) -> str | None:
    """A shell command that writes the acceptance of a design, which only Edit or Write may do."""
    if "design.md" not in command or not SHELL_ACCEPTANCE.search(command):
        return None
    if reader_refusal(command) is None:
        return None
    return (
        "write the acceptance of a design with Edit or Write, so that its ticket budget is checked"
    )


# --- Ticket bodies ----------------------------------------------------------------------------


def placement(body: str) -> Placement:
    """Where the ticket of `body` sits in the feature budgets."""
    text = body.replace("\r\n", "\n")
    motif_match = MOTIF_LINE.search(text)
    feature_match = FEATURE_LINE.search(text)
    motif = motif_match.group(1) if motif_match else ""
    case = motif.split()[0] if motif else ""
    if case in OUT_OF_BUDGET or HUMAN_REQUEST.match(case):
        return Placement("out")
    if case == "to-tickets":
        named = TO_TICKETS.match(motif)
        if named is None:
            return Placement(
                "refused", "a `Motif : to-tickets` line names its feature: `to-tickets F-NNNN`"
            )
        return Placement("feature", named.group(1))
    if case == "fusion-bloquee" and feature_match is None:
        return Placement(
            "refused", "a `fusion-bloquee` ticket names its feature with a `Feature: F-NNNN` line"
        )
    if feature_match is not None:
        return Placement("feature", feature_match.group(1))
    return Placement("none")


def _path_in(cwd: str | None, path: str) -> str:
    return path if Path(path).is_absolute() or cwd is None else str(Path(cwd) / path)


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


def _redirected_input(words: list[str], cwd: str | None, bodies: str) -> str | None:
    """What the shell feeds to this command's standard input: a `<` file or a heredoc."""
    text: str | None = None
    for index, word in enumerate(words):
        if word == "<" and index + 1 < len(words):
            text = read_text_or_none(_path_in(cwd, words[index + 1]))
        elif word in ("<<", "<<-"):
            text = bodies or None
    return text


def _inline(value: str, bodies: str) -> str | None:
    """A body typed in the command; a shell substitution is read from the heredocs, if any."""
    if any(marker in value for marker in SUBSTITUTION):
        return f"{value}\n{bodies}" if bodies else None
    return value


def issue_create_body(
    rest: list[str], words: list[str], cwd: str | None, bodies: str
) -> str | None:
    """The body of a `gh issue create`, or None when it cannot be read (editor, web, a pipe)."""
    body: str | None = None
    given = False
    index = 0
    while index < len(rest):
        word = rest[index]
        text = _value(word, rest, index, ("--body", "-b"))
        path = _value(word, rest, index, ("--body-file", "-F"))
        if text is not None:
            body, index, given = _inline(text[0], bodies), text[1], True
        elif path is not None:
            name, index, given = path[0], path[1], True
            if name == "-":
                body = _redirected_input(words, cwd, bodies)
            else:
                body = read_text_or_none(_path_in(cwd, name))
        elif word in CREATE_VALUE_OPTIONS:
            index += 2
        else:
            index += 1
    return body if given else None


def _api_body(
    options: list[tuple[str, str]],
    redirections: list[tuple[str, str]],
    cwd: str | None,
    bodies: str,
) -> str | None:
    """The `body` a `gh api` POST sends, `""` when it sends none; None when it cannot be read."""
    body: str | None = ""

    def stdin() -> str | None:
        return _standard_input_text(redirections, cwd, bodies, read_text_or_none)

    for name, value in options:
        if name == "input":
            raw = stdin() if value == "-" else read_text_or_none(_path_in(cwd, value))
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
            continue
        if name == "field" and content.startswith("@"):
            source = content[1:]
            body = stdin() if source == "-" else read_text_or_none(_path_in(cwd, source))
        else:
            body = _inline(content, bodies)
    return body


def _graphql_creation(
    words: list[str], redirections: list[tuple[str, str]], cwd: str | None, bodies: str
) -> Creation | None:
    """The ticket a `gh api graphql` call creates by `createIssue`, or None when it creates none.

    The body is the `body:` string of the mutation, or the field its `$variable` names; a variable
    the call does not fill (one fed by a JSON `--input`) leaves the body unreadable.
    """
    options = parse_api(words).options
    parts = [" ".join(words), bodies]
    for name, value in options:
        if name == "input" and value != "-":
            parts.append(read_text_or_none(_path_in(cwd, value)) or "")
        elif value.partition("=")[2].startswith("@"):
            parts.append(read_text_or_none(_path_in(cwd, value.partition("=")[2][1:])) or "")
    text = "\n".join(parts)
    if "createIssue" not in text:
        return None
    match = GRAPHQL_BODY.search(text)
    if match is None:
        return Creation("", None)
    if match.group(1) is not None:
        try:
            literal = json.loads(f'"{match.group(1)}"')
        except ValueError:
            literal = match.group(1).replace("\\n", "\n")
        return Creation(literal if isinstance(literal, str) else None, None)
    fields = [(name, value) for name, value in options if value.startswith(f"{match.group(2)}=")]
    if not fields:
        return Creation(None, None)
    renamed = [(name, "body=" + value.partition("=")[2]) for name, value in fields]
    return Creation(_api_body(renamed, redirections, cwd, bodies), None)


def api_creations(args: list[str], cwd: str | None, bodies: str) -> list[Creation]:
    """The tickets a `gh api` call creates, one per reading of its words that creates one."""
    creations: list[Creation] = []
    readings = api_readings(args)
    if readings is None:
        return (
            [Creation(None, None)]
            if any("/issues" in word or word == "graphql" for word in args)
            else []
        )
    for kept, redirections in readings:
        call = parse_api(kept)
        if call.endpoint == "graphql":
            created = _graphql_creation(kept, redirections, cwd, bodies)
            if created is not None:
                creations.append(created)
            continue
        endpoint = ISSUES_ENDPOINT.match(call.endpoint)
        method = (call.method or ("POST" if call.options else "GET")).upper()
        if endpoint is None or method != "POST":
            continue
        owner, repo = endpoint.group(1), endpoint.group(2)
        named = None if "{" in owner or "{" in repo else f"{owner}/{repo}"
        creations.append(Creation(_api_body(call.options, redirections, cwd, bodies), named))
    return creations


def creations(command: str, cwd: str | None) -> list[Creation]:
    """The tickets `command` creates, by `gh issue create` or by `gh api`."""
    _, bodies = split_heredocs(command)
    found: list[Creation] = []
    for item in _commands(command):
        if isinstance(item, str):
            continue
        act = gh_act(item)
        if act is None:
            continue
        group, verb, rest = act
        if group == "issue" and verb in ("create", "new"):
            found.append(Creation(issue_create_body(rest, item, cwd, bodies), _repo_of(item)))
        elif group == "api":
            command_words = gh_command(item) or []
            found.extend(api_creations(command_words[1:], cwd, bodies))
    return found


# --- Designs and counts -----------------------------------------------------------------------


def find_design(root: Path, feature_dir: str, feature: str) -> list[Path]:
    """The `design.md` files of `feature` under the feature folder, header `feature:` checked."""
    digits = feature.removeprefix("F-")
    found: list[Path] = []
    for path in sorted((root / feature_dir).glob(f"{digits}-*/design.md")):
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


def count_tickets(feature: str, repo: str | None, cwd: str | None, run: Runner) -> int | None:
    """The tickets of `feature`, open or closed, by its motif or feature line; None if unknown."""
    numbers: set[int] = set()
    for phrase in (f'"to-tickets {feature}"', f'"Feature: {feature}"'):
        argv = ["issue", "list", "--state", "all", "--search", f"{phrase} in:body"]
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
            if placement(body) == Placement("feature", feature):
                numbers.add(number)
    return len(numbers)


def ticket_refusal(
    creation: Creation, cwd: str | None, root: Path, config: Mapping[str, list[str]], run: Runner
) -> str | None:
    """Why the ticket `creation` may not be opened, or None."""
    if creation.body is None:
        return (
            "the ticket's body cannot be read, so its feature budget cannot be checked: pass it"
            " with --body, or --body-file and a readable file"
        )
    place = placement(creation.body)
    if place.kind == "refused":
        return place.detail
    if place.kind != "feature":
        return None
    feature = place.detail
    declare = f"declare feature-tickets in the design first, and {RESPLIT}"
    directories = config.get(FEATURE_DIR_KEY, [])
    if not directories:
        return f"{feature} has no design to read its budget from (key `{FEATURE_DIR_KEY}` absent): {declare}"
    designs = find_design(root, directories[-1], feature)
    if len(designs) != 1:
        found = "no design" if not designs else f"{len(designs)} designs"
        return f"{feature} has {found} under `{directories[-1]}/`: {declare}"
    header = front_matter(read_text_or_none(str(designs[0])) or "")
    if not accepted(header):
        return f"the design of {feature} is not accepted: its tickets are published once it is"
    budget = budget_of(header)
    if budget is None:
        return f"the design of {feature} has no `feature-tickets`: {declare}"
    if budget > CEILING:
        return f"the design of {feature} declares `feature-tickets: {budget}`, above {CEILING}: {RESPLIT}"
    count = count_tickets(feature, creation.repo, cwd, run)
    if count is None:
        return (
            f"the tickets of {feature} cannot be counted (gh absent, the network, or a gh error):"
            " the ticket is refused as a precaution"
        )
    if count >= budget:
        return f"{feature} already has {count} tickets for a budget of {budget}: {ADD_A_PART}"
    return None


# --- Entry point ------------------------------------------------------------------------------


def refusal(event: Mapping[str, object], run: Runner = run_gh) -> str | None:
    """Why the tool call of `event` may not run, or None."""
    tool = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    if tool in ("Edit", "Write", "MultiEdit"):
        return write_refusal(str(tool), tool_input)
    if tool not in ("Bash", "PowerShell"):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str):
        return None
    if reason := shell_design_refusal(command):
        return reason
    found = creations(command, cwd := _cwd(event))
    if not found:
        return None
    root = project_root(event)
    config = load(root)
    for creation in found:
        if reason := ticket_refusal(creation, cwd, root, config, run):
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
