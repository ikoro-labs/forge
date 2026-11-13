"""The bodies a shell command publishes on GitHub through gh, read before gh runs.

One reader for every hook that judges a body: `gh issue|pr create|edit|comment|review|merge|close`
with `--body`, `--body-file` (`-` and `/dev/stdin` read from the heredoc of the command) or
`--comment`, and `gh api` with `-f/-F body=...` or `--input` on an issue, PR or comment endpoint,
or a GraphQL mutation that carries a `body` argument. A body the reader cannot read before gh does
(a shell variable, a pipe, a missing file, standard input without a heredoc) raises `Unreadable`:
the caller refuses it, never lets it through unread. The standard library only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from guard_git import (
    _standard_input_text,
    api_readings,
    gh_act,
    gh_command,
    is_standard_input_path,
    parse_api,
    read_text_or_none,
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
# The options of the porcelain calls read here that take the next word as their value.
VALUE_OPTIONS = frozenset({*BODY_TEXT, *BODY_FILE, *CLOSE_TEXT, "--title", "-t", "--head", "-H", "--base", "-B"})


class Unreadable(Exception):
    """A body the reader cannot read: the publication is refused, never let through unread."""


@dataclass(frozen=True)
class Publication:
    """One body a command publishes, and where it goes."""

    kind: str  # "ticket", "pr" or "comment"
    body: str
    act: tuple[str, str] | None = None  # `(group, verb)` of a gh porcelain call; None for `gh api`
    args: list[str] = field(default_factory=list)  # the words after the verb
    endpoint: str = ""  # the path of a `gh api` call, "graphql" for a mutation
    repo: str | None = None  # the value of `-R` or `--repo`


def _resolve(mode: str, value: str, heredoc: str, here: str | None) -> str:
    """The text a body option gives gh; `Unreadable` when it cannot be read before gh runs."""
    if mode == "text":
        if EXPANDED.search(value):
            if "$(" in value and heredoc:
                return heredoc
            raise Unreadable(f"`{value}` is filled in by the shell")
        return value
    if value == "-" or is_standard_input_path(value, here):
        if heredoc:
            return heredoc
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


def _standard_input(redirections: list[tuple[str, str]], heredoc: str, here: str | None) -> str:
    text = _standard_input_text(redirections, here, heredoc, read_text_or_none)
    if text is None:
        raise Unreadable("standard input from a pipe or without a heredoc")
    return text


def _input_json(value: str, redirections: list[tuple[str, str]], heredoc: str, here: str | None) -> dict[str, object]:
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


def _fields(options: list[tuple[str, str]], heredoc: str, here: str | None) -> dict[str, str]:
    """The `-f name=value` and `-F name=value` fields of a `gh api` call, files read."""
    fields: dict[str, str] = {}
    for name, value in options:
        if name not in ("raw-field", "field"):
            continue
        key, _, content = value.partition("=")
        if name == "field" and content.startswith("@"):
            fields[key] = _resolve("file", content[1:], heredoc, here)
        else:
            fields[key] = _resolve("text", content, heredoc, here)
    return fields


def _graphql_bodies(
    options: list[tuple[str, str]], redirections: list[tuple[str, str]], heredoc: str, here: str | None
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
    try:
        fields = _fields(options, heredoc, here)
    except Unreadable as error:
        raise Unreadable(f"{error}; refused as a precaution, a mutation could hide in it") from error
    query = fields.pop("query", query)
    variables.update(fields)
    bodies: list[tuple[str, str]] = []
    for match in MUTATION.finditer(query):
        argument = BODY_ARGUMENT.search(query, match.end())
        following = MUTATION.search(query, match.end())
        if argument is None or (following is not None and argument.start() > following.start()):
            continue
        block, literal, variable = argument.groups()
        if block is not None:
            body: object = block
        elif literal is not None:
            body = json.loads(literal)
        else:
            body = variables.get(variable)
        if not isinstance(body, str):
            raise Unreadable(f"the `${variable}` of `{match.group(1)}` is not given")
        bodies.append((GRAPHQL_BODIES[match.group(1)], body))
    return bodies


def _api_bodies(args: list[str], heredoc: str, here: str | None) -> list[Publication]:
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
            body = _fields(call.options, heredoc, here).get("body")
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


def publications(words: list[str], heredoc: str, here: str | None) -> list[Publication]:
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
    body = _resolve(*option, heredoc, here)
    return [Publication(kind, body, act=(act[0], act[1]), args=act[2], repo=repo_of(words))]
