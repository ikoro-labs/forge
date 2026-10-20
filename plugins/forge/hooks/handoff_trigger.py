"""UserPromptSubmit and PostToolUse hook: the drained handoff of a session at its context limit.

Every session hands over to a fresh one once its context reaches the limit, while the window
itself may be much larger. Closing a session kills its subagents, so the handoff is a stop
that drains (ikoro-labs/forge#3): at the limit the session launches nothing new and waits for
its agents (stage "drain"). At the hard cap, the threshold plus 35k tokens or 45 minutes after
the first notice, it stops waiting, lists the agents still alive for a rescue and forces the
relay (stage "hard"). Past each notice, only a new user prompt gets a reminder: repeating it
after every tool call would interrupt the work.

The threshold is CLAUDE_SESSION_TOKEN_LIMIT, 150k by default. Only handoff_relay.py raises it,
to 400k for a successor whose handoff carries a feature; no settings, skill or session sets it.

State and handoffs live outside the plugin cache, which every version rewrites:
`~/.claude/hooks/state/`, handoffs under `handoffs/<project>/<date>-r<N>.md`. The first-notice
marker is never touched again: its mtime is the start of the drain.

While `~/.claude/settings.json` still declares a copy of this hook outside the plugin, this one
stays silent: the session would otherwise get every notice twice.

The hook never blocks: any failure exits 0 silently. An earlier hook denied tools at the limit
and, once its script went missing, broke every tool call.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import time
from pathlib import Path

from usine import project_root

DEFAULT_LIMIT = 150000
HARD_MARGIN = 35000
HOOKS = Path(__file__).resolve().parent
MANIFEST = HOOKS.parent / ".claude-plugin" / "plugin.json"
RELAY = HOOKS / "handoff_relay.py"
# The interpreter every hook of the plugin runs on; `python3` is a Microsoft Store alias on Windows.
PYTHON = "uv run --no-project --quiet python"
NAME = "handoff_trigger.py"
KEYS = (
    "projet, feature, passage_depart, jetons_agents, en_vol, file_revue, sauvetage, successeur, "
    "hooks_version, seuil, contexte_passation"
)


def state_dir() -> Path:
    return Path.home() / ".claude" / "hooks" / "state"


def handoff_skill() -> Path | None:
    """The user's handoff skill, when they have one: its front matter forbids model invocation."""
    skill = Path.home() / ".claude" / "skills" / "handoff" / "SKILL.md"
    return skill if skill.is_file() else None


def hooks_version() -> str:
    try:
        return "forge@" + json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return "forge@unknown"


def commands(node: object) -> list[str]:
    """Every hook command declared anywhere under a settings `hooks` block."""
    if isinstance(node, dict):
        found = [node["command"]] if isinstance(node.get("command"), str) else []
        return found + [command for value in node.values() for command in commands(value)]
    if isinstance(node, list):
        return [command for value in node for command in commands(value)]
    return []


def copy_outside_plugin(settings: Path) -> bool:
    """True while the user's settings still run a copy of this hook that is not this file."""
    try:
        declared = commands(json.loads(settings.read_text(encoding="utf-8")).get("hooks", {}))
    except (OSError, ValueError, AttributeError):
        return False
    return any(NAME in command and str(HOOKS) not in command for command in declared)


def context_tokens(transcript: Path) -> int:
    """Context size of the main thread, read from its last assistant usage."""
    last = 0
    with transcript.open(encoding="utf-8") as lines:
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("type") != "assistant" or entry.get("isSidechain"):
                continue
            usage = (entry.get("message") or {}).get("usage") or {}
            total = (
                usage.get("input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
                + usage.get("output_tokens", 0)
            )
            if total:
                last = total
    return last


def agents_in_flight(root: Path) -> str:
    try:
        # Imported here so that a broken sibling costs only this listing, never the notice.
        import handoff_header

        # This hook's ancestors, among them the Claude Code process that holds this session's agent locks.
        agents = handoff_header.live_agents(root, handoff_header.ancestors(os.getpid()))
    except Exception:  # noqa: BLE001 - outside a repository there is simply nothing to list
        return "none found by worktree lock (agents without a worktree, such as qc-gate and qc-conf, are not seen)"
    listed = "; ".join(f"{path} on {branch}" for path, branch in agents) or "none with a worktree"
    return listed + " (agents without a worktree, such as qc-gate and qc-conf, are not seen here)"


def handoff_path(root: Path) -> Path:
    """First free `<date>-r<N>.md` of the project: a name can already be taken by another session."""
    folder = state_dir() / "handoffs" / root.name
    day = datetime.date.today().isoformat()
    rank = 1
    while (folder / f"{day}-r{rank}.md").exists():
        rank += 1
    return folder / f"{day}-r{rank}.md"


def procedure() -> str:
    skill = handoff_skill()
    if skill is None:
        return "write the handoff"
    return f"write the handoff by following {skill} (read that file; the skill cannot be invoked through the Skill tool)"


def drain(tokens: int, limit: int, drain_minutes: int, root: Path) -> str:
    path = handoff_path(root)
    return (
        f"Context has reached {tokens // 1000}k tokens, the {limit // 1000}k session limit set by the user. "
        "The handoff is a stop that drains its agents (ikoro-labs/forge#3):\n"
        "1. From now on, launch nothing new: no coder, no qc, no decision agent, no other subagent, no new ticket.\n"
        "2. Let every agent in flight run to its exit and process its result as usual (verdict posted, merge on "
        "ACCEPT, worktree cleaned). Finish only the step in progress yourself and leave the working tree clean.\n"
        f"3. Hard cap: {(limit + HARD_MARGIN) // 1000}k tokens or {drain_minutes} minutes after this notice, "
        "whichever comes first; you will be told. If you wait on agents, check the clock between notifications.\n"
        f"4. Once nothing is in flight, {procedure()} at {path} (create the folder; if the file exists, take the "
        f"next r<N>). It starts with a YAML front matter holding exactly these keys: {KEYS}. passage_depart is a "
        "UTC epoch, lists are inline `[]` or `- item` lines, successeur and seuil are left empty (the relay writes "
        "them), contexte_passation is your context in tokens when you write it, "
        f"hooks_version is `{hooks_version()}`. An agent woken again by SendMessage works in its worktree without "
        "locking it: list it under en_vol, the relay cannot see it otherwise. The body is the resume prompt. No "
        "secret. Respect the project's own end-of-session rules too; a resume memory keeps only a pointer to this "
        "handoff.\n"
        f'5. Run `{PYTHON} "{RELAY}" <handoff path>` from the project directory. '
        "Exit 5 means an agent of this session "
        "is still alive or en_vol is not empty: wait for it, do not force. Exit 2 means the header is invalid: fix "
        "it. End your reply with the handoff path, the relay session id and `claude attach <id>`; if the relay "
        "refuses its daily cap (exit 3), tell the user to open a new session from the handoff by hand.\n"
        f"Agents of this session in flight now: {agents_in_flight(root)}."
    )


def hard(tokens: int, minutes: int, root: Path) -> str:
    return (
        f"Hard cap reached ({tokens // 1000}k tokens, {minutes} minutes since the handoff notice): stop waiting "
        "for agents. Never write in the worktree of a living agent. In the handoff header, list each agent still "
        "alive under `sauvetage`, one `- ` item each: agent type, ticket or PR, worktree, branch, last sha on "
        "origin (`git ls-remote origin <branch>`); keep them under `en_vol` too. Write the handoff as instructed "
        f'before, then run `{PYTHON} "{RELAY}" --force <handoff path>`: --force is refused while `sauvetage` is empty. '
        "The successor's first move is to rescue each listed worktree (a Conventional Commits commit in the "
        "project's language, a push, a fresh agent relaunched).\n"
        f"Agents of this session in flight now: {agents_in_flight(root)}."
    )


def reminder(tokens: int, limit: int, minutes: int, stage: str) -> str:
    return (
        f"Context is at {tokens // 1000}k tokens, past the {limit // 1000}k session limit, {minutes} minutes "
        f"since the handoff notice (stage {stage}). Start no new work here: follow the handoff instruction given "
        "earlier. If the relay has run, point the user to `claude agents` and `claude attach <id>`."
    )


def notice(payload: dict) -> str | None:
    """What this event tells the session, or None below the limit, for a subagent, or once told."""
    if payload.get("agent_id") or copy_outside_plugin(Path.home() / ".claude" / "settings.json"):
        return None
    transcript = Path(payload.get("transcript_path") or "")
    if not transcript.is_file():
        return None
    limit = int(os.environ.get("CLAUDE_SESSION_TOKEN_LIMIT", DEFAULT_LIMIT))
    drain_minutes = int(os.environ.get("CLAUDE_HANDOFF_DRAIN_MINUTES", "45"))
    tokens = context_tokens(transcript)
    if tokens < limit:
        return None
    root = project_root(payload)
    state = state_dir()
    state.mkdir(parents=True, exist_ok=True)
    session = payload.get("session_id", "unknown")
    marker = state / f"{session}.handoff"
    hard_marker = state / f"{session}.hard"
    if not marker.exists():
        marker.touch()
        return drain(tokens, limit, drain_minutes, root)
    minutes = int(time.time() - marker.stat().st_mtime) // 60
    if (tokens >= limit + HARD_MARGIN or minutes >= drain_minutes) and not hard_marker.exists():
        hard_marker.touch()
        return hard(tokens, minutes, root)
    if payload.get("hook_event_name") == "UserPromptSubmit":
        return reminder(tokens, limit, minutes, "hard" if hard_marker.exists() else "drain")
    return None


def main() -> None:
    payload = json.load(sys.stdin)
    message = notice(payload)
    if message is not None:
        event = payload.get("hook_event_name", "PostToolUse")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": message}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - a hook failure must never block the session
        pass
    sys.exit(0)
