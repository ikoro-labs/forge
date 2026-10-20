"""Read and update the machine-readable header of a handoff document, and find live agents.

Part of the drained session relay (ikoro-labs/forge#3), with handoff_trigger.py and
handoff_relay.sh. The header is a YAML front matter restricted to flat keys whose value is a
scalar, an inline list, or a block of `- item` lines, so the standard library is enough to
read it.

Usage:
  handoff_header.py check <handoff>                 exit 0 and print `en_vol=<n> sauvetage=<n> feature=<n>`,
                                                    exit 2 and print the reason if invalid
  handoff_header.py set-successor <handoff> <id> [<seuil>]
                                                    write `successeur: <id>` in the header, and
                                                    `seuil: <seuil>`, the successor's drain threshold
  handoff_header.py successor-ok <handoff>          exit 0 if this session (CLAUDE_CODE_SESSION_ID)
                                                    may act on the handoff, exit 3 if another
                                                    session is its successor
  handoff_header.py live <repo> [<owner pid>]       print `<worktree> <branch>` for each agent
                                                    worktree whose lock holder is still alive,
                                                    only those of <owner pid> when given
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

REQUIRED = (
    "projet",
    "feature",
    "passage_depart",
    "jetons_agents",
    "en_vol",
    "file_revue",
    "sauvetage",
    "successeur",
    "hooks_version",
    "seuil",
    "contexte_passation",
)
KEY = re.compile(r"^([a-z_]+):\s*(.*)$")
SESSION_ID = re.compile(r"^[0-9a-f]{8,}(-[0-9a-f-]+)?$")
# Claude Code locks an agent worktree with this reason while the agent runs.
LOCK = re.compile(r"claude agent \S+ \(pid (\d+) start (\d+)\)")
# The relay writes `successeur` right after `claude --bg` returns, while the new session
# may already be reading the header: wait that long for it before giving up.
SUCCESSOR_WAIT_SECONDS = 30


class HeaderError(ValueError):
    """The handoff has no header the relay can trust."""


def split(text: str) -> tuple[list[str], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise HeaderError("the handoff does not start with a `---` front matter")
    for end, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return lines[1:end], "".join(lines[end:])
    raise HeaderError("the front matter is never closed by `---`")


def parse(header: list[str]) -> dict[str, list[str]]:
    """Each key maps to its items; a scalar is a one-item list, `[]` or nothing is empty."""
    values: dict[str, list[str]] = {}
    current = None
    for raw in header:
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = KEY.match(line)
        if match:
            current, inline = match.group(1), match.group(2).strip()
            if inline in ("", "[]", '""', "''"):
                values[current] = []
            elif inline.startswith("[") and inline.endswith("]"):
                values[current] = [item.strip() for item in inline[1:-1].split(",") if item.strip()]
            else:
                values[current] = [inline]
            continue
        if current is not None and line.lstrip().startswith("-"):
            values[current].append(line.lstrip()[1:].strip())
            continue
        if current is not None and line.startswith((" ", "\t")):
            continue
        raise HeaderError(f"unreadable header line: {line!r}")
    return values


def check(path: Path) -> dict[str, list[str]]:
    values = parse(split(path.read_text(encoding="utf-8"))[0])
    missing = [key for key in REQUIRED if key not in values]
    if missing:
        raise HeaderError("missing header keys: " + ", ".join(missing))
    return values


def set_successor(path: Path, session: str, threshold: str = "") -> None:
    header, rest = split(path.read_text(encoding="utf-8"))
    written = ("successeur:", "seuil:") if threshold else ("successeur:",)
    kept = [line for line in header if not line.startswith(written)]
    kept.append(f"successeur: {session}\n")
    if threshold:
        kept.append(f"seuil: {threshold}\n")
    path.write_text("---\n" + "".join(kept) + rest, encoding="utf-8")


def recorded_successor(path: Path) -> str:
    """The session id written by the relay, or "" when the header holds none (an older handoff)."""
    items = check(path)["successeur"]
    value = items[0].strip("\"'") if items else ""
    return value if SESSION_ID.match(value) else ""


def successor_ok(path: Path, session: str, wait: float = SUCCESSOR_WAIT_SECONDS) -> tuple[bool, str]:
    deadline = time.monotonic() + wait
    successor = recorded_successor(path)
    while not successor and time.monotonic() < deadline:
        time.sleep(1)
        successor = recorded_successor(path)
    if not successor:
        return True, "no successor recorded in the header, an older handoff: confirm with ListAgents"
    if session and (session.startswith(successor) or successor.startswith(session[:8])):
        return True, f"this session ({session[:8]}) is the successor"
    return False, f"the successor is {successor}, not this session ({session[:8] or 'unknown'}): stop here"


def process_start(pid: int) -> str:
    """Start time of a process in clock ticks, "" if it is gone; the pid alone can be reused."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return ""
    # Field 22; the command name in field 2 may hold spaces, so count from its closing parenthesis.
    return stat.rsplit(")", 1)[1].split()[19]


def live_agents(repo: Path, owners: set[int] | None = None) -> list[tuple[str, str]]:
    """Agent worktrees whose lock holder still runs, as (path, branch).

    A lock whose holder is gone is left behind by a dead agent: its work stays on disk for a
    rescue, but nothing waits for it. A lock in an unknown format counts as live, the prudent side.
    """
    listing = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
        capture_output=True, text=True, timeout=5, check=True,
    ).stdout
    found = []
    for block in listing.strip().split("\n\n"):
        fields = dict(line.split(" ", 1) if " " in line else (line, "") for line in block.splitlines())
        path = fields.get("worktree", "")
        if "/.claude/worktrees/agent-" not in path or "locked" not in fields:
            continue
        holder = LOCK.search(fields["locked"])
        if holder:
            pid, start = int(holder.group(1)), holder.group(2)
            if process_start(pid) != start or (owners is not None and pid not in owners):
                continue
        branch = fields.get("branch", "(detached)").removeprefix("refs/heads/")
        found.append((path, branch))
    return found


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 3 and argv[1] == "check":
            values = check(Path(argv[2]))
            print(
                f"en_vol={len(values['en_vol'])} sauvetage={len(values['sauvetage'])} "
                f"feature={len(values['feature'])}"
            )
            return 0
        if len(argv) in (4, 5) and argv[1] == "set-successor":
            set_successor(Path(argv[2]), *argv[3:])
            return 0
        if len(argv) == 3 and argv[1] == "successor-ok":
            ok, reason = successor_ok(Path(argv[2]), os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
            print(reason)
            return 0 if ok else 3
        if len(argv) in (3, 4) and argv[1] == "live":
            owners = {int(argv[3])} if len(argv) == 4 else None
            for path, branch in live_agents(Path(argv[2]), owners):
                print(f"{path} {branch}")
            return 0
    except (HeaderError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(error)
        return 2
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
