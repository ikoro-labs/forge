"""Start the session that takes over from a handoff document, stop this one.

At the context limit the session drains its agents, writes its handoff (handoff_trigger.py)
and then calls this script from the project directory. The new session runs in the
background, and the session that called the script is stopped and deleted once it has had
time to give its last reply. A daily cap per project keeps a chain of relays from running
unattended forever.

Source: ikoro-labs/forge#3. Closing a session kills its subagents, so the relay refuses
(exit 5) while an agent of the calling session is alive or the handoff header lists agents
`en_vol`. --force is the hard cap of the drain: it is admitted only when the header lists
the agents left for a rescue under `sauvetage`. Every check runs before the daily counter
moves. The successor's drain threshold is set here and nowhere else: 400k when the handoff
carries a feature, 150k otherwise, written in the header as `seuil`. It is always passed
explicitly: the relay inherits the threshold of the session that runs it, which may be the
400k of an orchestration.

Runs on Linux and Windows with the standard library, like every hook of the plugin:
`uv run --no-project --quiet python handoff_relay.py`. It replaces handoff_relay.sh, which
read /proc and ran under bash. The old session is closed by a detached copy of this script
(`--close`), which outlives the session it stops.

State (the daily counters) lives in ~/.claude/hooks/state, outside the plugin cache.

Usage: handoff_relay.py [--force] <handoff document>
Exit: 1 usage, 2 invalid header, 3 daily cap, 4 relay id unreadable, 5 agents alive.
Environment: CLAUDE_HANDOFF_RELAY_MAX (default 5), CLAUDE_HANDOFF_CLOSE_DELAY seconds
before closing the old session (default 45, 0 keeps it open), CLAUDE_HANDOFF_TERMINAL (a
terminal command that runs the words after it, such as `ghostty -e`, `gnome-terminal --` or
`wt.exe` on Windows: the relay opens `claude attach <id>` in it; unset, no window opens), and
CLAUDE_HANDOFF_CLOSE_DRY_RUN (set: print the relay and closing commands instead of running
them; the counter and the handoff are left untouched).
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import handoff_header

HOOKS = Path(__file__).resolve().parent
HEADER = HOOKS / "handoff_header.py"
PYTHON = "uv run --no-project --quiet python"
WINDOWS = handoff_header.WINDOWS
BACKGROUNDED = re.compile(r"backgrounded\W+([0-9a-f]+)\b")
# The kernel keeps 15 characters of a command name.
COMM_LENGTH = 15


def fail(message: str, code: int) -> int:
    print(message, file=sys.stderr)
    return code


def claude() -> str:
    """The claude executable; on Windows the .exe first, so that no cmd.exe reparses the prompt."""
    return (shutil.which("claude.exe") if WINDOWS else None) or shutil.which("claude") or "claude"


def counter_path(state: Path, project: Path) -> Path:
    name = re.sub(r"[\\/:]", "-", str(project))
    return state / f"relay-{name}-{datetime.date.today().isoformat()}.count"


def detached() -> dict[str, object]:
    """Popen options for a process that survives the session that starts it."""
    options: dict[str, object] = {
        "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
    }
    if WINDOWS:
        options["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | 0x01000000  # CREATE_BREAKAWAY_FROM_JOB
        )
    else:
        options["start_new_session"] = True
    return options


def spawn(argv: list[str]) -> None:
    try:
        subprocess.Popen(argv, **detached())
    except OSError:
        if not WINDOWS:
            raise
        # The job of the session may forbid breaking away: start without it.
        options = detached()
        options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(argv, **options)


# A closing plan is a list of steps; a step is a list of alternative commands, tried in order
# until one exits 0 (`a || b`). An empty step list keeps the session open.
Plan = list[list[list[str]]]


def render(plan: Plan) -> str:
    return "; ".join(" || ".join(shlex.join(command) for command in step) for step in plan)


def command_name(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def closing_plan(pid: int, terminal: str) -> Plan:
    """How to end the session that runs this script (CLAUDE_PID)."""
    cli = claude()
    session = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if os.environ.get("CLAUDE_CODE_CHILD_SESSION") == "1" and session:
        # A background session (a previous relay). A stopped session restarts on the next
        # message or `claude attach`, so it is deleted after the stop: only `claude rm` ends
        # everything it carries. Its viewers, `claude attach <id>` in their own windows,
        # fall back to the agent view and stay open, so they are ended first.
        short = session[:8]
        if WINDOWS:
            viewers = [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "
                f"'claude(\\.exe)?\"? attach {short}( |$)' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}",
            ]
            kill = ["taskkill", "/PID", str(pid), "/F"]
        else:
            viewers = ["pkill", "-TERM", "-f", f"^claude attach {short}( |$)"]
            kill = ["kill", "-TERM", str(pid)]
        return [[viewers], [[cli, "stop", short], kill], [[cli, "rm", short]]]
    if WINDOWS:
        # An interactive session. Its console window belongs to the shell that started
        # claude and stays open on that shell's prompt.
        return [[["taskkill", "/PID", str(pid), "/F"]]]
    # An interactive session. Its window closes only when the shell that started claude
    # exits, so that shell is hung up too, but only when the user's terminal
    # (CLAUDE_HANDOFF_TERMINAL) is its direct parent: a claude started from a script or tmux
    # keeps its parent.
    plan: Plan = [[["kill", "-TERM", str(pid)]]]
    shell = handoff_header.parent_pid(pid)
    term = handoff_header.parent_pid(shell) if shell else None
    wanted = Path(shlex.split(terminal)[0]).name[:COMM_LENGTH] if terminal else ""
    if shell and term and wanted and command_name(shell) in ("bash", "zsh", "fish"):
        if command_name(term).startswith(wanted):
            plan += [[["sleep", "2"]], [["kill", "-HUP", str(shell)]]]
    return plan


def close(delay: int, plan: Plan) -> None:
    time.sleep(delay)
    for step in plan:
        for command in step:
            try:
                if subprocess.run(command, check=False, **detached()).returncode == 0:
                    break
            except OSError:
                continue


def open_viewer(terminal: str, relay_id: str) -> bool:
    """`claude attach <id>` in a new window: only a desktop session can show one."""
    if not WINDOWS and not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        return False
    try:
        spawn([*shlex.split(terminal, posix=not WINDOWS), claude(), "attach", relay_id])
    except OSError:
        return False
    return True


def relay(argv: list[str]) -> int:
    force = bool(argv) and argv[0] == "--force"
    if force:
        argv = argv[1:]
    if len(argv) != 1:
        return fail("usage: handoff_relay.py [--force] <handoff document>", 1)
    handoff = Path(argv[0])
    if not handoff.is_file():
        return fail(f"handoff document not found: {handoff}", 1)
    handoff = handoff.resolve()
    dry_run = bool(os.environ.get("CLAUDE_HANDOFF_CLOSE_DRY_RUN"))
    cap = int(os.environ.get("CLAUDE_HANDOFF_RELAY_MAX", "5"))
    close_delay = int(os.environ.get("CLAUDE_HANDOFF_CLOSE_DELAY", "45"))
    terminal = os.environ.get("CLAUDE_HANDOFF_TERMINAL", "")
    state = Path.home() / ".claude" / "hooks" / "state"
    state.mkdir(parents=True, exist_ok=True)
    project = Path.cwd()
    try:
        values = handoff_header.check(handoff)
    except (handoff_header.HeaderError, OSError, ValueError) as error:
        return fail(f"invalid handoff header: {error}", 2)
    en_vol, sauvetage = len(values["en_vol"]), len(values["sauvetage"])
    threshold = 400000 if values["feature"] else 150000
    # Only the agents of the calling session: another session's agents in the same
    # repository do not die with this one. Run by hand, without CLAUDE_PID, every live
    # agent of the repository counts, the prudent side.
    owner = os.environ.get("CLAUDE_PID", "")
    try:
        live = handoff_header.live_agents(project, {int(owner)} if owner else None)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return fail(f"could not list the agent worktrees: {error}", 5)
    if force:
        if not sauvetage:
            return fail("--force refused: the handoff lists no agent under sauvetage; wait for the agents instead", 5)
    elif live or en_vol:
        print(
            "relay refused: agents of this session are still in flight; let them finish, or at the hard cap list "
            "them under sauvetage and pass --force",
            file=sys.stderr,
        )
        for path, branch in live:
            print(f"live agent worktree: {path} {branch}", file=sys.stderr)
        if en_vol:
            print(f"en_vol in the header: {en_vol}", file=sys.stderr)
        return 5
    counter = counter_path(state, project)
    try:
        count = int(counter.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        count = 0
    if count >= cap:
        return fail(f"relay cap reached: {count}/{cap} relays today for {project}; open the next session by hand", 3)
    count += 1
    prompt = (
        f"Reprise automatique (relais {count}/{cap} du jour). Avant tout geste, lance "
        f'`{PYTHON} "{HEADER}" successor-ok "{handoff}"` : s\'il sort en code 3, une autre session est le '
        f"successeur désigné, arrête-toi sans rien faire. Sinon, lis le document de passation {handoff}, "
        "confronte son en-tête à GitHub, sauve d'abord chaque worktree listé sous sauvetage, puis poursuis la "
        "suite qu'il décrit, en respectant les règles du projet."
    )
    # The counter alone repeats across days and machines: the time keeps the name free.
    name = f"relais-{count}-{project.name}-{datetime.datetime.now():%H%M}"
    if dry_run:
        print(f"dry run, would run: CLAUDE_SESSION_TOKEN_LIMIT={threshold} claude --bg --permission-mode auto -n {name} <prompt>")
        print(f"dry run, prompt: {prompt}")
        relay_id = "00000000"
    else:
        counter.write_text(f"{count}\n", encoding="utf-8")
        result = subprocess.run(
            [claude(), "--bg", "--permission-mode", "auto", "-n", name, prompt],
            capture_output=True, encoding="utf-8", errors="replace", check=False,
            env={**os.environ, "CLAUDE_SESSION_TOKEN_LIMIT": str(threshold)},
        )
        output = result.stdout + result.stderr
        print(output.rstrip())
        found = BACKGROUNDED.search(output)
        if not found:
            return fail("could not read the relay session id", 4)
        relay_id = found.group(1)
        handoff_header.set_successor(handoff, relay_id, str(threshold))
        print(f"successeur: {relay_id} and seuil: {threshold} written in {handoff}")
    if terminal and not dry_run and open_viewer(terminal, relay_id):
        print(f"relay {relay_id} opened in a new terminal window")
    else:
        print(f"follow the relay with: claude attach {relay_id}")
    # CLAUDE_PID is the session that runs this script. The delay lets it finish its reply.
    if close_delay > 0 and owner:
        plan = closing_plan(int(owner), terminal)
        if dry_run:
            print(f"dry run, would run in {close_delay}s: {render(plan)}")
        else:
            spawn([sys.executable, str(Path(__file__).resolve()), "--close", str(close_delay), json.dumps(plan)])
            print(f"this session (pid {owner}) closes in {close_delay}s")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "--close":
        close(int(argv[1]), json.loads(argv[2]))
        return 0
    return relay(argv)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
