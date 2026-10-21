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

The session writes the handoff with its own file tools, which a managed policy may forbid
under any `.claude` folder. CLAUDE_HANDOFF_DIR then moves the handoffs elsewhere, as
`<CLAUDE_HANDOFF_DIR>/<project>/<date>-r<N>.md`; markers and counters, written by the hooks
themselves, stay in the state folder.

While `~/.claude/settings.json` still declares a copy of this hook outside the plugin, this one
stays silent: the session would otherwise get every notice twice.

The hook never blocks: any failure exits 0 silently. An earlier hook denied tools at the limit
and, once its script went missing, broke every tool call.

Run by a session with arguments, it is a command, not a hook (ikoro-labs/forge#4):
`handoff_trigger.py yield <session id>`, from the project directory, prints what a background
session does when the user's interactive session <session id> asks it to hand over: the same
drain and the same handoff, under the drain cap of CLAUDE_HANDOFF_DRAIN_MINUTES, then
`handoff_header.py set-successor` instead of the relay, the handoff path sent to the interactive
session, and last `handoff_relay.py --yield`, which stops and deletes the background session
after CLAUDE_HANDOFF_CLOSE_DELAY without starting any. Exit 1 on a wrong usage.
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
HEADER = HOOKS / "handoff_header.py"
# The interpreter every hook of the plugin runs on; `python3` is a Microsoft Store alias on Windows.
PYTHON = "uv run --no-project --quiet python"
NAME = "handoff_trigger.py"
KEYS = (
    "projet, feature, passage_depart, jetons_agents, en_vol, file_revue, sauvetage, successeur, "
    "hooks_version, seuil, contexte_passation"
)


def state_dir() -> Path:
    return Path.home() / ".claude" / "hooks" / "state"


def handoff_dir() -> Path:
    """CLAUDE_HANDOFF_DIR, `~` and variables expanded, else the `handoffs` folder of the state."""
    configured = os.environ.get("CLAUDE_HANDOFF_DIR", "").strip()
    if configured:
        return Path(os.path.expandvars(configured)).expanduser()
    return state_dir() / "handoffs"


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


def project_name(root: Path) -> str:
    """The project's folder name, that of its main checkout when `root` is a git worktree.

    A worktree's `.git` is a file naming its own git directory, and there a `commondir` file leads
    to the main checkout's `.git`. Read without running git, which a hook cannot wait for."""
    try:
        text = (root / ".git").read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir:"):
            return root.name
        gitdir = root / text.removeprefix("gitdir:").strip()
        common = gitdir / (gitdir / "commondir").read_text(encoding="utf-8").strip()
        return common.resolve().parent.name or root.name
    except OSError:
        # No `.git` file (a main checkout, or no repository), or no `commondir` (a submodule).
        return root.name


def handoff_path(root: Path) -> Path:
    """First free `<date>-r<N>.md` of the project: a name can already be taken by another session."""
    folder = handoff_dir() / project_name(root)
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


# The first two steps of every drain, at the context limit or on an interactive session's request.
STOP_LAUNCHING = (
    "1. From now on, launch nothing new: no coder, no qc, no decision agent, no other subagent, no new ticket.\n"
    "2. Let every agent in flight run to its exit and process its result as usual (verdict posted, merge on "
    "ACCEPT, worktree cleaned). Finish only the step in progress yourself and leave the working tree clean.\n"
)
# What the handoff says of the agents still alive once the drain stops waiting for them.
RESCUE = (
    "Never write in the worktree of a living agent. In the handoff header, list each agent still "
    "alive under `sauvetage`, one `- ` item each: agent type, ticket or PR, worktree, branch, last sha on "
    "origin (`git ls-remote origin <branch>`); keep them under `en_vol` too."
)


def writing(path: Path) -> str:
    """How to write the handoff at `path`: the same document at the limit and on request."""
    return (
        f"{procedure()} at {path} (create the folder; if the file exists, take the "
        f"next r<N>). It starts with a YAML front matter holding exactly these keys: {KEYS}. passage_depart is a "
        "UTC epoch, lists are inline `[]` or `- item` lines, feature is the feature identifier (F-NNNN) or left "
        "empty, never prose, successeur and seuil are left empty (the relay writes "
        "them), contexte_passation is your context in tokens when you write it, "
        f"hooks_version is `{hooks_version()}`. An agent woken again by SendMessage works in its worktree without "
        "locking it: list it under en_vol, the relay cannot see it otherwise. The body is the resume prompt. No "
        "secret. Respect the project's own end-of-session rules too; a resume memory keeps only a pointer to this "
        "handoff."
    )


def drain(tokens: int, limit: int, drain_minutes: int, root: Path) -> str:
    path = handoff_path(root)
    return (
        f"Context has reached {tokens // 1000}k tokens, the {limit // 1000}k session limit set by the user. "
        "The handoff is a stop that drains its agents (ikoro-labs/forge#3):\n"
        + STOP_LAUNCHING
        + f"3. Hard cap: {(limit + HARD_MARGIN) // 1000}k tokens or {drain_minutes} minutes after this notice, "
        "whichever comes first; you will be told. If you wait on agents, check the clock between notifications.\n"
        f"4. Once nothing is in flight, {writing(path)}\n"
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
        f"for agents. {RESCUE} Write the handoff as instructed "
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


def handover(successor: str, drain_minutes: int, root: Path) -> str:
    """What a background session does when the user's interactive session asks it to hand over
    (ikoro-labs/forge#4): it drains then stops, under the drain cap, and the interactive session
    is its successor in effect. No session is started; the background session is closed as a
    relay closes it, once its handoff names the interactive session and has been sent to it:
    left alive, it would stop the next session of the repository."""
    path = handoff_path(root)
    return (
        f"The user's interactive session ({successor}) takes over this repository: one session acts on a "
        "repository at a time, and an interactive session comes before a background one (ikoro-labs/forge#4). "
        "This background session drains, then stops:\n"
        + STOP_LAUNCHING
        + f"3. Cap: {drain_minutes} minutes from now (CLAUDE_HANDOFF_DRAIN_MINUTES), the drain cap of the "
        "handoff; check the clock between notifications. Past it, stop waiting for agents. " + RESCUE + "\n"
        f"4. Once nothing is in flight, or at the cap, {writing(path)}\n"
        f'5. Run `{PYTHON} "{HEADER}" set-successor <handoff path> {successor}` from the project directory: it '
        "names the interactive session as the successor and this session as the author, so that the interactive "
        "session's `sessions` no longer counts this one. Do not run the relay itself: no successor is started.\n"
        f"6. Send the handoff path to the session {successor} by SendMessage.\n"
        f'7. Then run `{PYTHON} "{RELAY}" --yield <handoff path>` from the project directory, with --force only '
        "when sauvetage lists agents: it starts no session and stops then deletes this one after "
        "CLAUDE_HANDOFF_CLOSE_DELAY seconds, so that no later session of the repository finds it in place. Exit 5 "
        "means an agent of this session is still alive or en_vol is not empty: wait for it, do not force. Exit 2 "
        "means the header is invalid or names no successor: fix it, or run step 5. End your reply with the handoff "
        f"path and `session {successor} takes over`, and act on nothing more.\n"
        f"Agents of this session in flight now: {agents_in_flight(root)}."
    )


def command(argv: list[str]) -> int:
    """`handoff_trigger.py yield <session id>`, run by a background session from the project directory."""
    import handoff_header

    if len(argv) != 2 or argv[0] != "yield" or not handoff_header.SESSION_ID.match(argv[1]):
        print("usage: handoff_trigger.py yield <session id of the interactive session that takes over>")
        return 1
    drain_minutes = int(os.environ.get("CLAUDE_HANDOFF_DRAIN_MINUTES", "45"))
    print(handover(argv[1], drain_minutes, project_root({"cwd": os.getcwd()})))
    return 0


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
    if len(sys.argv) > 1:
        # Run by a session, not by Claude Code as a hook: its exit code is its answer.
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.exit(command(sys.argv[1:]))
    try:
        main()
    except Exception:  # noqa: BLE001 - a hook failure must never block the session
        pass
    sys.exit(0)
