"""The output guard: every exchange follows its template, checked by `scripts/output_check.py`.

One script for four declarations of `hooks.json`, told apart by `hook_event_name`:

- `SubagentStop`: the subagent's final text (`last_assistant_message`), checked against the format
  its `agent_type` declares (`forge:coder`, `forge:qc-conf`...), else the generic rule
  `templates/subagent-return.md`. A subagent that delivered its report by `SubagentHandback` is
  skipped here: its report was checked when it called that tool.
- `PreToolUse` on `SubagentHandback`: the report in `tool_input.message`, by the same rule.
- `PreToolUse` on `Bash`: the body of `gh issue create|edit|comment` and
  `gh pr create|edit|comment|review` given by `--body`, `-b`, `--body-file` or `-F`, and the
  `body` field of `gh api` (`-f body=`, `-F body=`, `-F body=@file`) on an issue, pull request,
  comment or review endpoint. A ticket follows `ticket.md`, a pull request `pr.md`, a comment
  `comment.md`, and a comment that opens with `VERDICT:` follows `verdict.md`.
- `Stop`: the session's reply to the human (`last_assistant_message`, else the last assistant
  entry of the transcript), checked against `templates/session-reply.md`.

A non-conforming output exits `REFUSED` (3) with the deviations on stderr, and the command in
`hooks.json` turns that code alone into the 2 that blocks. An agent is refused once: a second
non-conforming output passes with a `systemMessage` and a line in the journal. On `Stop` and
`SubagentStop` that second pass is `stop_hook_active`; on `SubagentHandback` it is a marker per
`agent_id`, which a conforming output clears. A gh command is refused each time: the agent
rewrites its body. Anything the guard cannot read (an event, a body held in a variable, a file it
cannot open) passes, and so does a crash, which never exits 3: this guard never blocks what it
does not understand.
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
    api_readings,
    gh_act,
    gh_command,
    parse_api,
    read_text_or_none,
    split_heredocs,
)
from output_check import agent_kind, deviations  # noqa: E402
from usine import load, project_root  # noqa: E402

REFUSED = 3
AGENT_ID = re.compile(r"[A-Za-z0-9_-]+")
GH_BODY_KINDS = {
    ("issue", "create"): "ticket",
    ("issue", "edit"): "ticket",
    ("issue", "comment"): "comment",
    ("pr", "create"): "pr",
    ("pr", "edit"): "pr",
    ("pr", "comment"): "comment",
    ("pr", "review"): "comment",
}
TEXT_OPTIONS = ("--body", "-b")
FILE_OPTIONS = ("--body-file", "-F")
# A value the shell fills in at run time: the guard cannot read it before gh does. A backtick is
# not one: the quotes are gone from the words, and Markdown backticks far outnumber substitutions.
EXPANDED = re.compile(r"\$[\w{(]")
HANDBACK = re.compile(r'"name"\s*:\s*"SubagentHandback"')
TRANSCRIPT_TAIL = 2 * 1024 * 1024
COMMENT_ENDPOINT = re.compile(
    r"/issues/comments/\d+$|/issues/\d+/comments$|/pulls/comments/\d+$"
    r"|/pulls/\d+/(?:comments|reviews)(?:/\d+)?$"
)
TICKET_ENDPOINT = re.compile(r"/issues(?:/\d+)?$")
PR_ENDPOINT = re.compile(r"/pulls(?:/\d+)?$")


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


def _resolve(mode: str, value: str, heredoc: str, here: str | None) -> str | None:
    """The text a body option gives gh, or None when it cannot be read before gh runs."""
    if mode == "text":
        if EXPANDED.search(value):
            return heredoc if "$(" in value and heredoc else None
        return value
    if value == "-":
        return heredoc or None
    path = Path(value)
    if not path.is_absolute() and here:
        path = Path(here) / path
    return read_text_or_none(str(path))


def _body_option(args: list[str]) -> tuple[str, str] | None:
    """`("text" | "file", value)` of the last body option among `args`, as gh's pflag reads it."""
    found: tuple[str, str] | None = None
    index = 0
    while index < len(args):
        word = args[index]
        if word == "--":
            break
        for mode, options in (("text", TEXT_OPTIONS), ("file", FILE_OPTIONS)):
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


def _api_body(args: list[str], heredoc: str, here: str | None) -> tuple[str, str] | None:
    """`(kind, body)` of a `gh api` call that writes the body of an issue, a PR or a comment."""
    readings = api_readings(args)
    if not readings:
        return None
    call = parse_api(readings[0][0])
    path = call.endpoint.split("?")[0].rstrip("/")
    if COMMENT_ENDPOINT.search(path):
        kind = "comment"
    elif TICKET_ENDPOINT.search(path):
        kind = "ticket"
    elif PR_ENDPOINT.search(path):
        kind = "pr"
    else:
        return None
    body: str | None = None
    for name, value in call.options:
        if name not in ("raw-field", "field") or not value.startswith("body="):
            continue
        value = value[len("body=") :]
        if name == "field" and value.startswith("@"):
            body = _resolve("file", value[1:], heredoc, here)
        else:
            body = _resolve("text", value, heredoc, here)
    return (kind, body) if body is not None else None


def _opens_verdict(body: str) -> bool:
    lines = [line.strip() for line in body.strip().splitlines() if line.strip()]
    if lines and lines[0].startswith(("```", "~~~")):
        lines = lines[1:]
    return bool(lines) and lines[0].startswith("VERDICT:")


def _gh(event: Mapping[str, object]) -> Outcome:
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or "gh" not in command:
        return Outcome(0)
    here = event.get("cwd") if isinstance(event.get("cwd"), str) else None
    heredoc = split_heredocs(command)[1]
    root = project_root(event)
    config: dict[str, list[str]] | None = None
    for words in _commands(command):
        if isinstance(words, str):
            continue
        call = gh_command(words)
        if not call:
            continue
        if call[0] == "api":
            found_body = _api_body(call[1:], heredoc, str(here) if here else None)
            if found_body is None:
                continue
            kind, body = found_body
        else:
            act = gh_act(words)
            kind_or_none = GH_BODY_KINDS.get(act[:2]) if act else None
            option = _body_option(act[2]) if act and kind_or_none else None
            text = _resolve(*option, heredoc, str(here) if here else None) if option else None
            if kind_or_none is None or text is None:
                continue
            kind, body = kind_or_none, text
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
