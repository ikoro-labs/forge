"""The bodies a shell command publishes on GitHub through gh, read before gh runs.

One reader for every hook that judges a body: `gh issue|pr create|edit|comment|review|merge|close`
with `--body`, `--body-file` (`-` and `/dev/stdin` read from the command's own `<<NAME` heredoc or
`< file`) or `--comment`, and `gh api` with `-f/-F body=...` or `--input` on an issue, PR or comment
endpoint, or a GraphQL mutation that carries a `body` argument, a literal or a variable. A body
option `"$(cat <<'NAME' ... NAME)"` is read from the heredoc it names. `commands` finds gh wherever
the shell runs it: behind `env`, `command`, `sudo`, `xargs` or a path (`/usr/bin/gh`), in
`bash -c`, `sh -c`, `eval`, a shell fed by a heredoc, or a `$(...)` substitution. A body the reader
cannot read before gh does (a shell variable, a substitution other than a literal heredoc, a pipe,
a missing file) raises `Unreadable`, and so does gh run through a variable: the caller refuses,
never lets it through unread. The standard library only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from guard_git import (
    HEREDOC,
    _commands,
    _standard_input_text,
    api_readings,
    gh_act,
    gh_command,
    is_standard_input_path,
    parse_api,
    read_text_or_none,
    split_heredocs,
)

BODY_TEXT = ("--body", "-b")
BODY_FILE = ("--body-file", "-F")
CLOSE_TEXT = ("--comment", "-c")
# `(group, verb)` of gh: the kind of body it publishes, its text options and its file options.
GH_BODIES: dict[tuple[str, str], tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    ("issue", "create"): ("ticket", BODY_TEXT, BODY_FILE),
    ("issue", "edit"): ("ticket", BODY_TEXT, BODY_FILE),
    ("issue", "comment"): ("comment", BODY_TEXT, BODY_FILE),
    ("issue", "close"): ("comment", CLOSE_TEXT, ()),
    ("pr", "create"): ("pr", BODY_TEXT, BODY_FILE),
    ("pr", "edit"): ("pr", BODY_TEXT, BODY_FILE),
    ("pr", "comment"): ("comment", BODY_TEXT, BODY_FILE),
    ("pr", "review"): ("comment", BODY_TEXT, BODY_FILE),
    ("pr", "merge"): ("comment", BODY_TEXT, BODY_FILE),
    ("pr", "close"): ("comment", CLOSE_TEXT, ()),
}
# A value the shell fills in at run time: the reader cannot see it before gh does. A backtick is
# not one: the quotes are gone from the words, and Markdown backticks far outnumber substitutions.
EXPANDED = re.compile(r"\$[\w{(]")
COMMENT_ENDPOINT = re.compile(
    r"/issues/comments/\d+$|/issues/\d+/comments$|/pulls/comments/\d+$"
    r"|/pulls/\d+/(?:comments|reviews)(?:/\d+)?$"
)
TICKET_ENDPOINT = re.compile(r"/issues(?:/\d+)?$")
PR_ENDPOINT = re.compile(r"/pulls(?:/\d+)?$")
# The GraphQL mutations that publish a body, and the kind of each.
GRAPHQL_BODIES = {
    "addComment": "comment",
    "updateIssueComment": "comment",
    "addPullRequestReview": "comment",
    "addPullRequestReviewComment": "comment",
    "addDiscussionComment": "comment",
    "createIssue": "ticket",
    "updateIssue": "ticket",
    "createPullRequest": "pr",
    "updatePullRequest": "pr",
}
MUTATION = re.compile(r"\b(" + "|".join(GRAPHQL_BODIES) + r")\s*\(")
BODY_ARGUMENT = re.compile(r'\bbody\s*:\s*(?:"""(.*?)"""|("(?:\\.|[^"\\])*")|\$(\w+))', re.DOTALL)
CURL = frozenset({"curl", "wget"})
UNREAD = "the body cannot be read before gh runs ({}): write it in a file or a heredoc"
# A `$(cat <<'NAME' ... NAME)` substitution: the body of the heredoc NAME of the same command.
CAT_HEREDOC = re.compile(r"\$\(\s*cat\s+<<-?\s*(['\"]?)(\w+)\1\s*\)")
# A GraphQL query holds `$name` variables of its own: only these are the shell's (guard_git's rule).
SHELL_QUERY = re.compile(r"\$\(|`|^\s*\$\{?\w+\}?\s*$")
GH_WORD = re.compile(r"(?:^|[/\\])gh(?:\.exe)?$", re.IGNORECASE)
SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
NESTED_DEPTH = 3
# The options of the porcelain calls read here that take the next word as their value.
VALUE_OPTIONS = frozenset({*BODY_TEXT, *BODY_FILE, *CLOSE_TEXT, "--title", "-t", "--head", "-H", "--base", "-B"})


class Unreadable(Exception):
    """A body the reader cannot read: the publication is refused, never let through unread."""


@dataclass(frozen=True)
class Heredocs:
    """The heredocs of a command: each `(name, body, literal)`, in order."""

    found: tuple[tuple[str, str, bool], ...] = ()

    @property
    def text(self) -> str:
        return "\n".join(body for _, body, _ in self.found)

    def named(self, name: str) -> str:
        """The body of the one heredoc `name`; `Unreadable` when missing, repeated or expanded."""
        bodies = [(body, literal) for found, body, literal in self.found if found == name]
        if len(bodies) != 1:
            raise Unreadable(f"the heredoc `{name}` is {'missing' if not bodies else 'repeated'}")
        if not bodies[0][1]:
            raise Unreadable(f"the heredoc `{name}` is expanded by the shell; quote its name, `<<'{name}'`")
        return bodies[0][0]


def heredocs(command: str) -> Heredocs:
    """The heredocs of `command`, cut on the lines `guard_git.split_heredocs` cuts."""
    found: list[tuple[str, str, bool]] = []
    current: tuple[str, bool] | None = None
    lines: list[str] = []
    for line in command.splitlines():
        if current is not None:
            if line.strip() == current[0]:
                body = "\n".join(lines)
                found.append((current[0], body, current[1] or not re.search(r"[`\\]|\$[\w{(]", body)))
                current, lines = None, []
            else:
                lines.append(line)
            continue
        if match := HEREDOC.search(line):
            current = (match.group(2), bool(match.group(1)))
    if current is not None:
        found.append((current[0], "\n".join(lines), False))
    return Heredocs(tuple(found))


def _docs(heredoc: Heredocs | str) -> Heredocs:
    """A plain text is the one, literal, heredoc of a caller that read no name."""
    return heredoc if isinstance(heredoc, Heredocs) else Heredocs((("", heredoc, True),) if heredoc else ())


@dataclass(frozen=True)
class Publication:
    """One body a command publishes, and where it goes."""

    kind: str  # "ticket", "pr" or "comment"
    body: str
    act: tuple[str, str] | None = None  # `(group, verb)` of a gh porcelain call; None for `gh api`
    args: list[str] = field(default_factory=list)  # the words after the verb
    endpoint: str = ""  # the path of a `gh api` call, "graphql" for a mutation
    repo: str | None = None  # the value of `-R` or `--repo`


# The text fields a GitHub tool of an MCP server publishes.
MCP_TEXT_FIELDS = ("body", "comment", "commit_message")


def mcp_publications(tool_name: str, tool_input: Mapping[str, object]) -> list[Publication]:
    """The bodies a GitHub tool of an MCP server publishes, by the words of its name.

    A comment, a review or a reply is a comment, a pull request or an issue that it creates, updates
    or writes is a PR or a ticket, a merge message is a comment. `Unreadable` when a tool outside
    these carries a text field, or a field is no text: its body would pass unjudged.
    """
    name = tool_name.rsplit("__", 1)[-1].lower()
    texts = {key: tool_input[key] for key in MCP_TEXT_FIELDS if key in tool_input}
    if not texts:
        return []
    if any(word in name for word in ("comment", "review", "reply", "merge")):
        kind = "comment"
    elif "pull_request" in name and any(word in name for word in ("create", "update", "write")):
        kind = "pr"
    elif "issue" in name and any(word in name for word in ("create", "update", "write")):
        kind = "ticket"
    else:
        raise Unreadable(f"the tool `{tool_name}` carries a body the hook cannot place; use gh")
    found = []
    for key, value in texts.items():
        if not isinstance(value, str):
            raise Unreadable(f"the field `{key}` of `{tool_name}` is no text")
        found.append(Publication(kind, value, endpoint=f"mcp:{tool_name}"))
    return found

def _inline(value: str, docs: Heredocs) -> str:
    """A typed value; each `$(cat <<'NAME' ...)` in it is the body of its heredoc."""
    parts: list[str] = []
    last = 0
    for match in CAT_HEREDOC.finditer(value):
        parts += [value[last : match.start()], docs.named(match.group(2))]
        last = match.end()
    if EXPANDED.search(value[last:]) or any(EXPANDED.search(part) for part in parts[::2]):
        raise Unreadable(f"`{value[:60]}` is filled in by the shell")
    return "".join(parts) + value[last:]


def _redirected_input(words: list[str], docs: Heredocs, here: str | None) -> str:
    """What the shell feeds to gh's standard input: its own last `<<NAME` or `< file`."""
    for index in range(len(words) - 2, -1, -1):
        if words[index] in ("<<", "<<-"):
            return docs.named(words[index + 1])
        if words[index] == "<":
            return _resolve("file", words[index + 1], docs, here)
    raise Unreadable("standard input from a pipe or without a heredoc of its own")


def _resolve(mode: str, value: str, heredoc: Heredocs | str, here: str | None, words: list[str] | None = None) -> str:
    """The text a body option gives gh; `Unreadable` when it cannot be read before gh runs."""
    docs = _docs(heredoc)
    if mode == "text":
        return _inline(value, docs)
    if value == "-" or is_standard_input_path(value, here):
        if words is not None:
            return _redirected_input(words, docs, here)
        if docs.found:
            return docs.text
        raise Unreadable("standard input without a heredoc")
    if EXPANDED.search(value):
        raise Unreadable(f"the path `{value}` is filled in by the shell")
    path = Path(value)
    if not path.is_absolute() and here:
        path = Path(here) / path
    text = read_text_or_none(str(path))
    if text is None:
        raise Unreadable(f"the file `{value}` cannot be read")
    return text


def _body_option(
    args: list[str], text_options: tuple[str, ...], file_options: tuple[str, ...]
) -> tuple[str, str] | None:
    """`("text" | "file", value)` of the last body option among `args`, as gh's pflag reads it."""
    found: tuple[str, str] | None = None
    index = 0
    while index < len(args):
        word = args[index]
        if word == "--":
            break
        for mode, options in (("text", text_options), ("file", file_options)):
            if not options:
                continue
            long, short = options
            if word in options:
                found = (mode, args[index + 1] if index + 1 < len(args) else "")
                index += 1
            elif word.startswith(long + "="):
                found = (mode, word[len(long) + 1 :])
            elif word.startswith(short) and not word.startswith("--") and len(word) > 2:
                value = word[2:]
                found = (mode, value[1:] if value.startswith("=") else value)
        index += 1
    return found


def _standard_input(redirections: list[tuple[str, str]], heredoc: Heredocs | str, here: str | None) -> str:
    docs = _docs(heredoc)
    last = next((item for item in reversed(redirections) if item[0] in ("<", "<<", "<<-")), None)
    bodies = docs.named(last[1]) if last and last[0] != "<" and isinstance(heredoc, Heredocs) else docs.text
    text = _standard_input_text(redirections, here, bodies, read_text_or_none)
    if text is None:
        raise Unreadable("standard input from a pipe or without a heredoc")
    return text


def _input_json(value: str, redirections: list[tuple[str, str]], heredoc: Heredocs | str, here: str | None) -> dict[str, object]:
    """The JSON object `gh api --input <value>` sends."""
    if value == "-" or is_standard_input_path(value, here):
        text = _standard_input(redirections, heredoc, here)
    else:
        text = _resolve("file", value, heredoc, here)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise Unreadable(f"`--input {value}` is not JSON") from error
    if not isinstance(data, dict):
        raise Unreadable(f"`--input {value}` is not a JSON object")
    return data


def _query(content: str, heredoc: Heredocs | str) -> str:
    """A GraphQL query: its `$name` are its own variables; a substitution or a whole variable is not."""
    if CAT_HEREDOC.fullmatch(content.strip()):
        return _docs(heredoc).named(CAT_HEREDOC.fullmatch(content.strip()).group(2))  # type: ignore[union-attr]
    if SHELL_QUERY.search(content):
        raise Unreadable(f"the query `{content[:40]}` is filled in by the shell; refused as a precaution, a mutation could hide in it")
    return content


def _fields(options: list[tuple[str, str]], heredoc: Heredocs | str, here: str | None) -> dict[str, str | Unreadable]:
    """The `-f name=value` and `-F name=value` fields of a `gh api` call, files read.

    A field the reader cannot read is kept as its `Unreadable`: it refuses only once it is used as
    a body, so that `-F number=$N` beside a literal body stays readable.
    """
    fields: dict[str, str | Unreadable] = {}
    for name, value in options:
        if name not in ("raw-field", "field"):
            continue
        key, _, content = value.partition("=")
        try:
            if name == "field" and content.startswith("@"):
                fields[key] = _resolve("file", content[1:], heredoc, here)
            elif key == "query":
                fields[key] = _query(content, heredoc)
            else:
                fields[key] = _resolve("text", content, heredoc, here)
        except Unreadable as error:
            fields[key] = error
    return fields


def _used(value: object) -> object:
    if isinstance(value, Unreadable):
        raise value
    return value


def _graphql_bodies(
    options: list[tuple[str, str]], redirections: list[tuple[str, str]], heredoc: Heredocs | str, here: str | None
) -> list[tuple[str, str]]:
    """`(kind, body)` of each body a `gh api graphql` mutation publishes."""
    variables: dict[str, object] = {}
    query = ""
    for name, value in options:
        if name == "input" and value:
            data = _input_json(value, redirections, heredoc, here)
            query = str(data.get("query", "")) or query
            given = data.get("variables")
            variables.update(given if isinstance(given, dict) else {})
    fields = _fields(options, heredoc, here)
    query = str(_used(fields.pop("query", query)))
    variables.update(fields)
    bodies: list[tuple[str, str]] = []
    for match in MUTATION.finditer(query):
        argument = BODY_ARGUMENT.search(query, match.end())
        following = MUTATION.search(query, match.end())
        if argument is None or (following is not None and argument.start() > following.start()):
            continue
        block, literal, variable = argument.groups()
        if block is not None or literal is not None:
            body: object = block if block is not None else json.loads(literal)
            if EXPANDED.search(str(body)):
                raise Unreadable(f"the body of `{match.group(1)}` holds `$`, which the shell may fill in")
        else:
            body = _used(variables.get(variable))
        if not isinstance(body, str):
            raise Unreadable(f"the `${variable}` of `{match.group(1)}` is not given")
        bodies.append((GRAPHQL_BODIES[match.group(1)], body))
    return bodies


def _api_bodies(args: list[str], heredoc: Heredocs | str, here: str | None) -> list[Publication]:
    """Each body a `gh api` call publishes, judged in every reading of its words."""
    readings = api_readings(args)
    if readings is None:
        raise Unreadable("too many redirections to read the call")
    found: list[Publication] = []
    for words, redirections in readings:
        call = parse_api(words)
        if call.method is not None and call.method.upper() in ("GET", "HEAD"):
            continue
        path = call.endpoint.split("?")[0].rstrip("/")
        if path == "graphql":
            found += [
                Publication(kind, body, endpoint="graphql")
                for kind, body in _graphql_bodies(call.options, redirections, heredoc, here)
            ]
            continue
        if COMMENT_ENDPOINT.search(path):
            kind = "comment"
        elif TICKET_ENDPOINT.search(path):
            kind = "ticket"
        elif PR_ENDPOINT.search(path):
            kind = "pr"
        else:
            continue
        body: object = None
        for name, value in call.options:
            if name == "input" and value:
                body = _input_json(value, redirections, heredoc, here).get("body", body)
        if any(value.startswith("body=") for name, value in call.options if name != "input"):
            body = _used(_fields(call.options, heredoc, here).get("body"))
        if isinstance(body, str):
            found.append(Publication(kind, body, endpoint=path))
    return found


def opens_verdict(body: str) -> bool:
    """Whether the body's first line, past an opening fence, is `VERDICT:`."""
    lines = [line.strip() for line in body.strip().splitlines() if line.strip()]
    if lines and lines[0].startswith(("```", "~~~")):
        lines = lines[1:]
    return bool(lines) and lines[0].startswith("VERDICT:")


def curls_github(words: list[str]) -> bool:
    """A curl or wget call aimed at api.github.com, which could publish a body unread."""
    while words and "=" in words[0] and not words[0].startswith("-"):
        words = words[1:]
    return bool(words) and Path(words[0]).name in CURL and any("api.github.com" in w for w in words)


def repo_of(words: list[str]) -> str | None:
    """The repository a gh call names with `-R` or `--repo`, None when it names none.

    The value of an option that takes one (a body, a title) is skipped: `--body "-R x"` names none.
    """
    index = 0
    while index < len(words):
        word = words[index]
        if word in ("-R", "--repo"):
            return words[index + 1] if index + 1 < len(words) else None
        if word.startswith("--repo="):
            return word[len("--repo=") :]
        if word.startswith("-R") and len(word) > 2:
            return word[2:].removeprefix("=")
        index += 2 if word in VALUE_OPTIONS else 1
    return None


def publications(words: list[str], heredoc: Heredocs | str, here: str | None) -> list[Publication]:
    """Each body this simple command publishes on GitHub."""
    call = gh_command(words)
    if not call:
        return []
    if call[0] == "api":
        return _api_bodies(call[1:], heredoc, here)
    act = gh_act(words)
    entry = GH_BODIES.get(act[:2]) if act else None
    if act is None or entry is None:
        return []
    kind, text_options, file_options = entry
    option = _body_option(act[2], text_options, file_options)
    if option is None:
        return []
    body = _resolve(*option, heredoc, here, words=act[2])
    return [Publication(kind, body, act=(act[0], act[1]), args=act[2], repo=repo_of(words))]


def _basename(word: str) -> str:
    return re.split(r"[/\\]", word)[-1].lower().removesuffix(".exe")


def _script_of(words: list[str], docs: Heredocs) -> str | None:
    """The script a shell `-c`, `eval` or a shell fed by a heredoc runs; None when `words` runs none."""
    for index, word in enumerate(words):
        name = _basename(word)
        if name == "eval":
            return " ".join(words[index + 1 :])
        if name not in SHELLS:
            continue
        position = index + 1
        while position < len(words):
            option = words[position]
            if option.startswith("-") and not option.startswith("--") and "c" in option:
                return words[position + 1] if position + 1 < len(words) else ""
            if option in ("<<", "<<-") and position + 1 < len(words):
                return docs.named(words[position + 1])
            if not option.startswith(("-", "+")):
                break
            position += 2 if option in ("-o", "+o", "-O", "+O") else 1
    return None


def _substitutions(text: str, raw: bool = False) -> list[str]:
    """The commands of each `$(...)` and backtick substitution the shell runs in `text`.

    Single quotes keep their text literal, unless `raw` (the body of an unquoted heredoc, where
    quotes are plain characters). A `$((` is arithmetic, not a command.
    """
    found: list[str] = []
    quote = ""
    index = 0
    while index < len(text):
        char = text[index]
        if quote == "'":
            quote = "" if char == "'" else quote
        elif char == "\\":
            index += 1
        elif char == "'" and not quote and not raw:
            quote = "'"
        elif char == '"' and not raw:
            quote = "" if quote == '"' else '"'
        elif text.startswith("$(", index) and not text.startswith("$((", index):
            depth, position = 1, index + 2
            while position < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[position], 0)
                position += 1
            found.append(text[index + 2 : position - 1 if not depth else position])
            index = position
            continue
        elif char == "`":
            close = text.find("`", index + 1)
            close = len(text) if close < 0 else close
            found.append(text[index + 1 : close])
            index = close + 1
            continue
        index += 1
    return found


def commands(command: str, docs: Heredocs, depth: int = 0) -> list[list[str] | str]:
    """The simple commands the shell runs, gh found behind a wrapper or a path, nested shells opened.

    A gh call after a wrapper (`env`, `command`, `sudo`, `xargs`, a path) is given from `gh` on.
    `Unreadable` when gh or a script comes from a variable, or the shells nest too deep.
    """
    if depth > NESTED_DEPTH:
        raise Unreadable("too many nested shells to read")
    found: list[list[str] | str] = []
    inner = _substitutions(split_heredocs(command)[0])
    inner += [part for _, body, literal in heredocs(command).found if not literal for part in _substitutions(body, raw=True)]
    for substituted in inner:
        if not CAT_HEREDOC.fullmatch(f"$({substituted})"):
            found += commands(substituted, docs, depth + 1)
    for item in _commands(command):
        if isinstance(item, str):
            found.append(item)
            continue
        words = item
        script = _script_of(words, docs)
        if script is not None:
            if EXPANDED.match(script.strip()):
                raise Unreadable("a script the shell gives by a variable")
            found += commands(script, docs, depth + 1)
            continue
        index = next((position for position, word in enumerate(words) if GH_WORD.search(word)), None)
        if index is not None:
            found.append(["gh", *words[index + 1 :]])
        elif words and EXPANDED.match(words[0]) and {"issue", "pr", "api"} & set(words):
            raise Unreadable(f"gh called through `{words[0]}`")
        else:
            found.append(words)
    return found
