"""Read and update the machine-readable header of a handoff document, and find live agents.

Part of the drained session relay (ikoro-labs/forge#3), with handoff_trigger.py and
handoff_relay.py. The header is a YAML front matter restricted to flat keys whose value is a
scalar, an inline list, or a block of `- item` lines, so the standard library is enough to
read it.

The process questions (is a pid alive, when did it start, who is its parent) are answered
from /proc on Linux and from the Win32 API through ctypes on Windows. Elsewhere they cannot be
answered: a process counts as alive and without a parent, the prudent side for the relay.

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
# Claude Code locks an agent worktree with this reason while the agent runs. The start time
# is written on Linux only: on Windows the reason ends at the pid.
LOCK = re.compile(r"claude (?:agent|session) .+? \(pid (\d+)(?: start (\S+))?\)")
WINDOWS = sys.platform == "win32"
LINUX = sys.platform.startswith("linux")
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


def _win32():
    """kernel32 with the signatures the process questions need; loaded on first use."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.GetProcessTimes.argtypes = (wintypes.HANDLE, *[ctypes.POINTER(wintypes.FILETIME)] * 4)
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
    kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
    return ctypes, wintypes, kernel32


def _win_process(pid: int, query):
    """query(handle) on a process opened for limited queries, None when it cannot be opened."""
    ctypes, wintypes, kernel32 = _win32()
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        return query(ctypes, wintypes, kernel32, handle)
    finally:
        kernel32.CloseHandle(handle)


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if LINUX:
        return Path(f"/proc/{pid}").exists()
    if WINDOWS:
        def running(ctypes, wintypes, kernel32, handle) -> bool:
            code = wintypes.DWORD()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE

        return bool(_win_process(pid, running))
    return True


def process_start(pid: int) -> str:
    """Start time of a process, "" if it is gone; the pid alone can be reused.

    Clock ticks since boot on Linux, the creation FILETIME on Windows.
    """
    if WINDOWS:
        def created(ctypes, wintypes, kernel32, handle) -> str:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel32.GetProcessTimes(handle, *map(ctypes.byref, times)):
                return ""
            return str(times[0].dwHighDateTime << 32 | times[0].dwLowDateTime)

        return (_win_process(pid, created) or "") if process_alive(pid) else ""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return ""
    # Field 22; the command name in field 2 may hold spaces, so count from its closing parenthesis.
    return stat.rsplit(")", 1)[1].split()[19]


def parent_pid(pid: int) -> int | None:
    """The parent of a process, None when it is gone or the platform cannot tell."""
    if LINUX:
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        except OSError:
            return None
        return int(stat.rsplit(")", 1)[1].split()[1])
    if not WINDOWS:
        return None
    ctypes, wintypes, kernel32 = _win32()

    class Entry(ctypes.Structure):  # PROCESSENTRY32W
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
        ]

    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snapshot in (None, wintypes.HANDLE(-1).value):
        return None
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            if entry.th32ProcessID == pid:
                return int(entry.th32ParentProcessID)
            found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        return None
    finally:
        kernel32.CloseHandle(snapshot)


def ancestors(pid: int) -> set[int]:
    """The process and its ancestors. A Windows parent may be gone and its pid reused by a
    younger process: the walk stops at a parent born after its child, or at a pid seen twice."""
    pids: set[int] = set()
    while pid > 1 and pid not in pids:
        pids.add(pid)
        parent = parent_pid(pid)
        if parent is None:
            break
        if WINDOWS:
            child_start, parent_start = process_start(pid), process_start(parent)
            if not parent_start or (child_start and int(parent_start) > int(child_start)):
                break
        pid = parent
    return pids


def live_agents(repo: Path, owners: set[int] | None = None) -> list[tuple[str, str]]:
    """Agent worktrees whose lock holder still runs, as (path, branch).

    A lock whose holder is gone is left behind by a dead agent: its work stays on disk for a
    rescue, but nothing waits for it. A lock in an unknown format counts as live, the prudent side.
    Without a start time in the lock (Windows), a running pid is taken for its holder.
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
            alive = process_start(pid) == start if start else process_alive(pid)
            if not alive or (owners is not None and pid not in owners):
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
