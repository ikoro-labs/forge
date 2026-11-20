"""The output guard: every exchange follows its template, checked by `scripts/output_check.py`.

One script for the declarations of `hooks.json`, told apart by `hook_event_name`:

- `SubagentStop`: the subagent's final text (`last_assistant_message`), checked against the format
  its `agent_type` declares (`forge:coder` or `coder`, `forge:qc-conf`...), else the generic rule
  `templates/subagent-return.md`. A subagent that delivered its report by `SubagentHandback` is
  skipped here: its report was checked when it called that tool.
- `PreToolUse` on `SubagentHandback`: the report in `tool_input.message`, by the same rule.
- `PreToolUse` on `Bash` and on a GitHub tool of an MCP server: every body published on GitHub, read
  by `gh_bodies.py`, the one reader `guard_cases` shares (gh porcelain and `gh api` bodies, GraphQL
  mutations, gh behind a wrapper, in `bash -c`, `eval` or a substitution, a body file read from the
  directory a `cd` moved to). A ticket follows `ticket.md`, a pull request `pr.md`, a comment
  `comment.md`, and a comment that opens with `VERDICT:` follows `verdict.md`. A call to
  `api.github.com` by `curl` or `wget` is refused: its body would go unread.
- `PreToolUse` on `SendMessage`: a message to another session (an address `uds:`, `bridge:` or
  `did:`, or the name or id of a session of `~/.claude/sessions/`) must be a billet,
  `templates/billet.md`, its `time` within 5 minutes of the host clock. A message to an agent of the
  session (`main`, a teammate) is free prose, and so is a structured message. The two handoff
  billets are held to the host too: a `handoff-request` carries the id of a session of the registry,
  a `handoff` the path of a file whose header names the receiver as successor (the rule of
  `handoff_header.py successor-ok`). A refused message does not leave, and is refused each time.
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

import handoff_header  # noqa: E402
from gh_bodies import (  # noqa: E402
    UNREAD,
    Publication,
    Unreadable,
    commands,
    curls_github,
    heredocs,
    may_publish,
    mcp_publications,
    opens_verdict,
    publications,
)
from guard_git import UNKNOWN, _moved  # noqa: E402
from output_check import agent_kind, billet_fields, deviations  # noqa: E402
from usine import load, project_root  # noqa: E402
from utf8_stdio import use_utf8  # noqa: E402

REFUSED = 3
AGENT_ID = re.compile(r"[A-Za-z0-9_-]+")
HANDBACK = re.compile(r'"name"\s*:\s*"SubagentHandback"')
TRANSCRIPT_TAIL = 2 * 1024 * 1024
# What `SendMessage` accepts for a session other than the caller's: `uds:<socket>`, `bridge:<id>`,
# `did:<id>`, or a bare socket path.
SESSION_ADDRESS = re.compile(r"^(?:uds|bridge|did):|\.sock$")
# The shortest id of a session the handoff request accepts for a registered session: `claude --bg` prints it.
SHORT_SESSION_ID = 8


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


def _judged(publications: list[Publication], root: Path, config: Mapping[str, list[str]]) -> Outcome:
    """Refuse the first body that departs from its template; a comment that opens a verdict is one."""
    for item in publications:
        kind = "verdict" if item.kind == "comment" and opens_verdict(item.body) else item.kind
        found = deviations(item.body, kind, config, root)
        if found:
            return Outcome(REFUSED, stderr=(
                f"Blocked by the output guard (forge plugin): this {kind} body does not follow"
                f" `templates/{kind}.md`. Fix each point, then run the command again:\n"
                f"{_listing(found)}"
            ))
    return Outcome(0)


def _unread(error: Unreadable) -> Outcome:
    return Outcome(REFUSED, stderr=f"Blocked by the output guard (forge plugin): {UNREAD.format(error)}.\n")


def _mcp(event: Mapping[str, object], tool: str) -> Outcome:
    tool_input = event.get("tool_input")
    try:
        found = mcp_publications(tool, tool_input if isinstance(tool_input, dict) else {})
    except Unreadable as error:
        return _unread(error)
    root = project_root(event)
    return _judged(found, root, load(root)) if found else Outcome(0)


def _gh(event: Mapping[str, object]) -> Outcome:
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not may_publish(command):
        return Outcome(0)
    cwd = event.get("cwd")
    here: str | None = cwd if isinstance(cwd, str) else None
    root = project_root(event)
    config: dict[str, list[str]] | None = None
    docs = heredocs(command)
    try:
        for words in commands(command, docs):
            if isinstance(words, str):
                continue
            if words[:1] == ["cd"] and len(words) > 1:
                here = _moved(here, words[1])
                continue
            if curls_github(words):
                return Outcome(REFUSED, stderr=(
                    "Blocked by the output guard (forge plugin): a call to api.github.com outside gh"
                    " could publish a body the guard does not read. Use gh, whose bodies it checks.\n"
                ))
            found = publications(words, docs, None if here == UNKNOWN else here)
            if found:
                config = load(root) if config is None else config
                judged = _judged(found, root, config)
                if judged.code:
                    return judged
    except Unreadable as error:
        return _unread(error)
    return Outcome(0)


# --- session to session -------------------------------------------------------------------------


def _registry() -> list[dict[str, str]]:
    """The sessions Claude Code lists in `~/.claude/sessions/<pid>.json`: each one's `name` and
    `sessionId`, when it has them."""
    sessions: list[dict[str, str]] = []
    for entry in (Path.home() / ".claude" / "sessions").glob("*.json"):
        try:
            fields = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(fields, dict):
            sessions.append({key: value for key in ("name", "sessionId") if isinstance(value := fields.get(key), str)})
    return sessions


def _registered() -> set[str]:
    """The names and ids of the sessions of the registry."""
    return {value for session in _registry() for value in session.values()}


def _other_session(to: object) -> bool:
    """Whether `SendMessage` addresses another session: an explicit `uds:`, `bridge:` or `did:`
    address or a socket path, or the name or id of a session of the registry. A name of the
    session's own agents (`main`, a teammate) is not one."""
    if not isinstance(to, str) or not to.strip():
        return False
    target = to.strip()
    return SESSION_ADDRESS.search(target) is not None or target in _registered()


def _asking(session: str) -> list[str]:
    """What is wrong with the `session` of a `handoff-request`: an id the registry does not list.
    A short id (`claude --bg` prints eight characters) names the session it starts."""
    ids = [entry["sessionId"] for entry in _registry() if "sessionId" in entry]
    if any(known == session or (len(session) >= SHORT_SESSION_ID and known.startswith(session)) for known in ids):
        return []
    return [
        f"`session: {session}` is not the id of a session of the registry (`~/.claude/sessions/`): the"
        " handoff request carries the id of the session that asks, which `handoff_header.py self` prints"
    ]


def _handing(path: str, to: str, cwd: object) -> list[str]:
    """What is wrong with the `handoff` of a `handoff` billet: a file that does not exist, or whose
    header does not name the receiver, the session `to` addresses, as its successor (`successor-ok`)."""
    file = Path(os.path.expanduser(path))
    if not file.is_absolute() and isinstance(cwd, str):
        file = Path(cwd) / file
    if not file.is_file():
        return [f"`handoff: {path}` is no file: write the handoff there before you send its path"]
    ids = {
        entry["sessionId"]
        for entry in _registry()
        if "sessionId" in entry and to.strip() in (entry.get("name"), entry["sessionId"])
    }
    if not ids:
        return [
            f"the receiver `{to}` has no id in the registry to hold the header to: address the message by"
            " the name or the id of its session"
        ]
    try:
        successor = handoff_header.recorded_successor(file)
    except (handoff_header.HeaderError, OSError) as error:
        return [f"`handoff: {path}` has no readable header: {error}"]
    if not successor:
        return [
            f"the header of `{path}` names no successor: run `handoff_header.py set-successor {path} <id of"
            f" `{to}`>` first"
        ]
    if not any(handoff_header.names(successor, known) for known in ids):
        return [f"the header of `{path}` names `{successor}` as its successor, not the receiver `{to}`"]
    return []


def _handoff_checks(fields: Mapping[str, str], to: str, cwd: object) -> list[str]:
    """The checks of the two handoff types that need the host: the registry, the handoff file."""
    if fields.get("type") == "handoff-request" and fields.get("session"):
        return _asking(fields["session"])
    if fields.get("type") == "handoff" and fields.get("handoff"):
        return _handing(fields["handoff"], to, cwd)
    return []


def _send(event: Mapping[str, object]) -> Outcome:
    """Refuse a message to another session that is not a billet; the message does not leave."""
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return Outcome(0)
    message = tool_input.get("message")
    if not isinstance(message, str) or not _other_session(tool_input.get("to")):
        return Outcome(0)  # a structured message is a protocol object, not prose to hold to the billet
    root = project_root(event)
    found = deviations(message, "billet", load(root), root, datetime.now(timezone.utc))
    found += _handoff_checks(billet_fields(message), str(tool_input.get("to")), event.get("cwd"))
    if not found:
        return Outcome(0)
    return Outcome(REFUSED, stderr=(
        "Blocked by the output guard (forge plugin): a message to another session is a billet, and"
        " this one does not follow `templates/billet.md`. The message was not sent; fix each point,"
        f" then send it again:\n{_listing(found)}"
    ))


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
        " `templates/session-reply.md` (Done, Measured, Awaiting your decision, CI and runners, Features; a table for"
        f" more than two elements). Rewrite the reply, fixing each point:\n{_listing(found)}"
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
        if tool == "SendMessage":
            return _send(event)
        if tool in ("Bash", "PowerShell"):
            return _gh(event)
        if isinstance(tool, str) and tool.startswith("mcp__"):
            return _mcp(event, tool)
    return Outcome(0)


def main() -> int:
    result = outcome(sys.stdin.read())
    sys.stderr.write(result.stderr)
    sys.stdout.write(result.stdout)
    return result.code


if __name__ == "__main__":
    use_utf8()
    raise SystemExit(main())
