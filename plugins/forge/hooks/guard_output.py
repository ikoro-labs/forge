"""The output guard: every exchange follows its template, checked by `scripts/output_check.py`.

One script for four declarations of `hooks.json`, told apart by `hook_event_name`:

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
        if isinstance(tool, str) and tool.startswith("mcp__"):
            return _mcp(event, tool)
    return Outcome(0)


def main() -> int:
    result = outcome(sys.stdin.read())
    sys.stderr.write(result.stderr)
    sys.stdout.write(result.stdout)
    return result.code


if __name__ == "__main__":
    raise SystemExit(main())
