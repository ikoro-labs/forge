"""The output guard: every exchange follows its template, checked by `scripts/output_check.py`.

One script for four declarations of `hooks.json`, told apart by `hook_event_name`:

- `SubagentStop`: the subagent's final text (`last_assistant_message`), checked against the format
  its `agent_type` declares (`forge:coder` or `coder`, `forge:qc-conf`...), else the generic rule
  `templates/subagent-return.md`. A subagent that delivered its report by `SubagentHandback` is
  skipped here: its report was checked when it called that tool.
- `PreToolUse` on `SubagentHandback`: the report in `tool_input.message`, by the same rule.
- `PreToolUse` on `Bash`: every body gh publishes. `gh issue create|edit|comment` and
  `gh pr create|edit|comment|review|merge` by `--body`, `-b`, `--body-file` or `-F`;
  `gh issue close` and `gh pr close` by `--comment` or `-c`; `gh api` on an issue, pull request,
  comment or review endpoint by its `body` field (`-f body=`, `-F body=`, `-F body=@file`) or the
  `body` of its `--input` JSON, in every reading of its words; `gh api graphql` mutations that
  publish a body (`addComment`, `createIssue`...), the body a literal or a variable. A ticket
  follows `ticket.md`, a pull request `pr.md`, a comment `comment.md`, and a comment that opens
  with `VERDICT:` follows `verdict.md`. A call to `api.github.com` by `curl` or `wget` is refused:
  its body would go unread.
- `Stop`: the session's reply to the human (`last_assistant_message`, else the last assistant
  entry of the transcript), checked against `templates/session-reply.md`.

A non-conforming output exits `REFUSED` (3) with the deviations on stderr, and the command in
`hooks.json` turns that code alone into the 2 that blocks. An agent is refused once: a second
non-conforming output passes with a `systemMessage` and a line in the journal. On `Stop` and
`SubagentStop` that second pass is `stop_hook_active`; on `SubagentHandback` it is a marker per
`agent_id`, which a conforming output clears. A gh command is refused each time: the agent
rewrites its body. A body the guard cannot read before gh runs (a variable, a substitution without
a heredoc, a file it cannot open, a pipe into standard input) is refused too: a publication fails
closed. An event it cannot read passes, and so does a crash, which never exits 3; `Stop` lets
through a reply it cannot read.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from guard_git import (  # noqa: E402
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
from output_check import agent_kind, deviations  # noqa: E402
from usine import load, project_root  # noqa: E402

REFUSED = 3
AGENT_ID = re.compile(r"[A-Za-z0-9_-]+")
HANDBACK = re.compile(r'"name"\s*:\s*"SubagentHandback"')
TRANSCRIPT_TAIL = 2 * 1024 * 1024


@dataclass(frozen=True)
class Outcome:
    """What the guard returns: its exit code, stderr and stdout."""

    code: int
    stderr: str = ""
    stdout: str = ""


def state_dir() -> Path:
    return Path.home() / ".claude" / "hooks" / "state" / "structured-output"


def _listing(found: list[str]) -> str:
    return "".join(f"- {deviation}\n" for deviation in found)


def _journal(event: Mapping[str, object], kind: str, found: list[str]) -> str:
    """Log a non-conforming output let through, and the `systemMessage` that says so."""
    path = state_dir() / "journal.jsonl"
    entry = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event.get("hook_event_name"),
        "agent_type": event.get("agent_type"),
        "agent_id": event.get("agent_id"),
        "kind": kind,
        "deviations": found,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    who = event.get("agent_type") or "the session"
    message = (
        f"output guard (forge plugin): {who} kept a non-conforming {kind} after one refusal;"
        f" it passes, logged in {path}."
    )
    return json.dumps({"systemMessage": message}) + "\n"


# --- agent to agent -----------------------------------------------------------------------------


def _handed_back(event: Mapping[str, object]) -> bool:
    """Whether the subagent's transcript holds a `SubagentHandback` call."""
    path = event.get("agent_transcript_path")
    if not isinstance(path, str) or not path:
        return False
    try:
        with Path(os.path.expanduser(path)).open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - TRANSCRIPT_TAIL))
            tail = stream.read().decode("utf-8", errors="replace")
    except OSError:
        return False
    return HANDBACK.search(tail) is not None


def _subagent(event: Mapping[str, object], text: str) -> Outcome:
    agent = event.get("agent_type")
    if not isinstance(agent, str) or not agent or not text.strip():
        return Outcome(0)  # an internal agent of Claude Code has no agent_type
    root = project_root(event)
    config = load(root)
    kind = agent_kind(agent, config)
    found = deviations(text, kind, config, root)
    agent_id = event.get("agent_id")
    marker = (
        state_dir() / "refused" / agent_id
        if isinstance(agent_id, str) and AGENT_ID.fullmatch(agent_id)
        else None
    )
    if not found:
        if marker is not None:
            marker.unlink(missing_ok=True)
        return Outcome(0)
    if event.get("stop_hook_active") is True:
        return Outcome(0, stdout=_journal(event, kind, found))
    if marker is not None:
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            with marker.open("x", encoding="utf-8"):
                pass
        except FileExistsError:
            return Outcome(0, stdout=_journal(event, kind, found))
        except OSError:
            if event.get("hook_event_name") != "SubagentStop":
                return Outcome(0)  # no marker, no bound on the redeliveries: let it pass
    elif event.get("hook_event_name") != "SubagentStop":
        return Outcome(0)
    reason = (
        f"Blocked by the output guard (forge plugin): your final output does not follow the"
        f" `{kind}` format. Rewrite it, fixing each point, then end again:\n{_listing(found)}"
    )
    return Outcome(REFUSED, stderr=reason)


# --- agent to GitHub ----------------------------------------------------------------------------

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
# A value the shell fills in at run time: the guard cannot read it before gh does. A backtick is
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


class Unreadable(Exception):
    """A body the guard cannot read: the publication is refused, never let through unread."""


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


def _api_bodies(args: list[str], heredoc: str, here: str | None) -> list[tuple[str, str]]:
    """`(kind, body)` of each body a `gh api` call publishes, judged in every reading of its words."""
    readings = api_readings(args)
    if readings is None:
        raise Unreadable("too many redirections to read the call")
    bodies: list[tuple[str, str]] = []
    for words, redirections in readings:
        call = parse_api(words)
        if call.method is not None and call.method.upper() in ("GET", "HEAD"):
            continue
        path = call.endpoint.split("?")[0].rstrip("/")
        if path == "graphql":
            bodies += _graphql_bodies(call.options, redirections, heredoc, here)
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
            bodies.append((kind, body))
    return bodies


def _opens_verdict(body: str) -> bool:
    lines = [line.strip() for line in body.strip().splitlines() if line.strip()]
    if lines and lines[0].startswith(("```", "~~~")):
        lines = lines[1:]
    return bool(lines) and lines[0].startswith("VERDICT:")


def _curls_github(words: list[str]) -> bool:
    while words and "=" in words[0] and not words[0].startswith("-"):
        words = words[1:]
    return bool(words) and Path(words[0]).name in CURL and any("api.github.com" in w for w in words)


def _publications(words: list[str], heredoc: str, here: str | None) -> list[tuple[str, str]]:
    """`(kind, body)` of each body this simple command publishes on GitHub."""
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
    return [(kind, _resolve(*option, heredoc, here))] if option else []


def _gh(event: Mapping[str, object]) -> Outcome:
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not ("gh" in command or "api.github.com" in command):
        return Outcome(0)
    here = event.get("cwd") if isinstance(event.get("cwd"), str) else None
    heredoc = split_heredocs(command)[1]
    root = project_root(event)
    config: dict[str, list[str]] | None = None
    for words in _commands(command):
        if isinstance(words, str):
            continue
        if _curls_github(words):
            return Outcome(REFUSED, stderr=(
                "Blocked by the output guard (forge plugin): a call to api.github.com outside gh"
                " could publish a body the guard does not read. Use gh, whose bodies it checks.\n"
            ))
        try:
            publications = _publications(words, heredoc, str(here) if here else None)
        except Unreadable as error:
            return Outcome(REFUSED, stderr=(
                f"Blocked by the output guard (forge plugin): {UNREAD.format(error)}.\n"
            ))
        for kind, body in publications:
            if kind == "comment" and _opens_verdict(body):
                kind = "verdict"
            config = load(root) if config is None else config
            found = deviations(body, kind, config, root)
            if found:
                reason = (
                    f"Blocked by the output guard (forge plugin): this {kind} body does not follow"
                    f" `templates/{kind}.md`. Fix each point, then run the command again:\n"
                    f"{_listing(found)}"
                )
                return Outcome(REFUSED, stderr=reason)
    return Outcome(0)


# --- session to human ---------------------------------------------------------------------------


def _last_reply(event: Mapping[str, object]) -> str:
    """The last assistant text: the event's field, else the transcript's last assistant entry."""
    text = event.get("last_assistant_message")
    if isinstance(text, str) and text.strip():
        return text
    path = event.get("transcript_path")
    if not isinstance(path, str) or not path:
        return ""
    try:
        with Path(os.path.expanduser(path)).open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - TRANSCRIPT_TAIL))
            lines = stream.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict) or entry.get("type") != "assistant":
            continue
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            if any(part.strip() for part in parts):
                return "\n".join(parts)
    return ""


def _stop(event: Mapping[str, object]) -> Outcome:
    text = _last_reply(event)
    if not text.strip():
        return Outcome(0)
    root = project_root(event)
    config = load(root)
    found = deviations(text, "session-reply", config, root)
    if not found:
        return Outcome(0)
    if event.get("stop_hook_active") is True:
        return Outcome(0, stdout=_journal(event, "session-reply", found))
    reason = (
        "Blocked by the output guard (forge plugin): your reply to the human does not follow"
        " `templates/session-reply.md` (Done, Measured, Awaiting your decision; a table for more"
        f" than two elements). Rewrite the reply, fixing each point:\n{_listing(found)}"
    )
    return Outcome(REFUSED, stderr=reason)


def outcome(raw: str) -> Outcome:
    """The guard's answer to the hook event `raw`."""
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return Outcome(0)
    if not isinstance(event, dict):
        return Outcome(0)
    name = event.get("hook_event_name")
    if name == "Stop":
        return _stop(event)
    if name == "SubagentStop":
        if _handed_back(event):
            return Outcome(0)
        text = event.get("last_assistant_message")
        return _subagent(event, text) if isinstance(text, str) else Outcome(0)
    if name == "PreToolUse":
        tool = event.get("tool_name")
        tool_input = event.get("tool_input")
        if tool == "SubagentHandback" and isinstance(tool_input, dict):
            message = tool_input.get("message")
            return _subagent(event, message) if isinstance(message, str) else Outcome(0)
        if tool in ("Bash", "PowerShell"):
            return _gh(event)
    return Outcome(0)


def main() -> int:
    result = outcome(sys.stdin.read())
    sys.stderr.write(result.stderr)
    sys.stdout.write(result.stdout)
    return result.code


if __name__ == "__main__":
    raise SystemExit(main())
