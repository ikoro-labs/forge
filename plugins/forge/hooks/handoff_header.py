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
                                                    write `successeur: <id>` in the header,
                                                    `seuil: <seuil>`, the successor's drain threshold,
                                                    and `auteur:`, this session (CLAUDE_CODE_SESSION_ID)
  handoff_header.py successor-ok <handoff>          exit 0 if this session (CLAUDE_CODE_SESSION_ID)
                                                    may act on the handoff, exit 3 if another
                                                    session is its successor
  handoff_header.py live <repo> [<owner pid>]       print `<worktree> <branch>` for each agent
                                                    worktree whose lock holder is still alive,
                                                    only those of <owner pid> when given
  handoff_header.py sessions <repo>                 print `<pid> <kind> <name> <status> <cwd>` for
                                                    each other live Claude Code session of the
                                                    repository; exit 0 if there is none, 6 if
                                                    there is one
  handoff_header.py self                            print `<kind> <id>` of this session: the kind
                                                    its registry entry records (CLAUDE_PID), such
                                                    as `interactive` or `bg`, and
                                                    CLAUDE_CODE_SESSION_ID; `?` when unknown

`sessions` reads the registry Claude Code keeps of its live sessions, ~/.claude/sessions/<pid>.json
(ikoro-labs/forge#4: one session per repository). A session belongs to the repository when its
cwd resolves to the same main checkout, a worktree included. The calling session is left out:
CLAUDE_PID, the process running the command, and their ancestors. So is the session that handed
it over: the `auteur` of a handoff of the project whose `successeur` names the calling session
(CLAUDE_CODE_SESSION_ID): a successor is no child of the session that hands over to it, and that
session stays alive during its closing delay, CLAUDE_HANDOFF_CLOSE_DELAY. An entry that cannot be read
counts as a live session of the repository, the prudent side, printed as
`<pid> ? ? unreadable <file>`. When the registry is missing or its format changes,
`claude agents --json` lists the live sessions with their cwd.
"""

from __future__ import annotations

import json
import os
import re
import signal
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
# A feature is named by its identifier; anything else in `feature` ("aucune", prose) is none.
FEATURE_ID = re.compile(r"F-\d+")
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


def features(values: dict[str, list[str]]) -> list[str]:
    """The feature identifiers (`F-NNNN`) the handoff carries."""
    return [item.strip("\"' ") for item in values.get("feature", []) if FEATURE_ID.fullmatch(item.strip("\"' "))]


def set_successor(path: Path, session: str, threshold: str = "", author: str = "") -> None:
    """Write `successeur`, and `seuil` and `auteur` when given: `auteur` is the session that
    hands over, which `sessions` then leaves out for its successor."""
    header, rest = split(path.read_text(encoding="utf-8"))
    written = ("successeur:",) + (("seuil:",) if threshold else ()) + (("auteur:",) if author else ())
    kept = [line for line in header if not line.startswith(written)]
    kept.append(f"successeur: {session}\n")
    if threshold:
        kept.append(f"seuil: {threshold}\n")
    if author:
        kept.append(f"auteur: {author}\n")
    path.write_text("---\n" + "".join(kept) + rest, encoding="utf-8")


def recorded_successor(path: Path) -> str:
    """The session id written by the relay, or "" when the header holds none (an older handoff)."""
    items = check(path)["successeur"]
    value = items[0].strip("\"'") if items else ""
    return value if SESSION_ID.match(value) else ""


def names(successor: str, session: str) -> bool:
    """The `successeur` of a header, often the short id `claude --bg` prints, names `session`."""
    return bool(successor and session) and (session.startswith(successor) or successor.startswith(session[:8]))


def successor_ok(path: Path, session: str, wait: float = SUCCESSOR_WAIT_SECONDS) -> tuple[bool, str]:
    deadline = time.monotonic() + wait
    successor = recorded_successor(path)
    while not successor and time.monotonic() < deadline:
        time.sleep(1)
        successor = recorded_successor(path)
    if not successor:
        return True, "no successor recorded in the header, an older handoff: confirm with ListAgents"
    if names(successor, session):
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
    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    return ctypes, wintypes, kernel32


def _win_process(pid: int, query, access: int = 0x1000):
    """query(handle) on a process opened for limited queries, None when it cannot be opened."""
    ctypes, wintypes, kernel32 = _win32()
    handle = kernel32.OpenProcess(access, False, pid)  # 0x1000: PROCESS_QUERY_LIMITED_INFORMATION
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


def group_options(suspended: bool = False) -> dict[str, object]:
    """`subprocess.Popen` options that make a command the leader of its own process group.

    Linux: a new session, so `os.killpg` reaches the command and what it started. Windows: the
    group is a job object, see `ProcessGroup`; with `suspended` the command is created suspended,
    so that nothing it starts can run before the job holds it (`ProcessGroup.start` resumes it).
    Elsewhere: nothing.
    """
    if LINUX:
        return {"start_new_session": True}
    if WINDOWS and suspended:
        return {"creationflags": 0x4}  # CREATE_SUSPENDED
    return {}


def _limit_job(job, memory_mb: int) -> bool:
    """Cap the memory of each process of the job and kill what is left when the job closes."""
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
        ]

    class Counters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class Extended(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        _fields_ = [
            ("BasicLimitInformation", Basic), ("IoInfo", Counters), ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = _win32()[2]
    kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    info = Extended()
    # JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    info.BasicLimitInformation.LimitFlags = 0x0100 | 0x2000
    info.ProcessMemoryLimit = memory_mb * 1024 * 1024
    return bool(kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)))


class ProcessGroup:
    """A started command and everything it starts, killed together.

    Linux: the process group `group_options` made. Windows: a job object the command is assigned
    to right after it starts. A child it spawned in that instant escapes, a window the API leaves
    open unless the command was created suspended (`group_options(suspended=True)`): `start`
    then resumes it only once the job holds it. With `memory_mb`, the job caps the memory of each
    of its processes and kills what is left when it closes; a limit the platform refuses leaves
    `limited` false. A job nested in the job of the session needs Windows 8 or later. Anything the
    platform refuses leaves the command alone to be killed, the prudent side.
    """

    def __init__(self, process: subprocess.Popen, memory_mb: int | None = None, suspended: bool = False) -> None:
        self.process = process
        self.job = None
        self.suspended = suspended and WINDOWS
        if WINDOWS:
            try:
                _, _, kernel32 = _win32()
                job = kernel32.CreateJobObjectW(None, None)

                def assign(ctypes, wintypes, kernel32, handle) -> bool:
                    return bool(kernel32.AssignProcessToJobObject(job, handle))

                # 0x0101: PROCESS_SET_QUOTA | PROCESS_TERMINATE, what the assignment asks for.
                if job and _win_process(process.pid, assign, 0x0101) and (
                    memory_mb is None or _limit_job(job, memory_mb)
                ):
                    self.job = job
                elif job:
                    kernel32.CloseHandle(job)
            except (OSError, AttributeError, ValueError):
                self.job = None

    @property
    def limited(self) -> bool:
        """The command is in its job, with the memory limit asked for. Always true off Windows."""
        return bool(self.job) if WINDOWS else True

    def start(self) -> None:
        """Let a command created suspended run. Windows only; a command not held by a job is killed."""
        if not self.suspended:
            return
        self.suspended = False
        if not self.job:
            self.kill()
            return
        ctypes = _win32()[0]
        ntdll = ctypes.WinDLL("ntdll")
        ntdll.NtResumeProcess.argtypes = (ctypes.c_void_p,)
        ntdll.NtResumeProcess(int(self.process._handle))  # type: ignore[attr-defined]  # Popen's own handle

    def kill(self) -> None:
        """Kill the command and its descendants, then reap the command."""
        try:
            if WINDOWS and self.job:
                _win32()[2].TerminateJobObject(self.job, 1)
            elif LINUX:
                os.killpg(self.process.pid, signal.SIGKILL)
            else:
                self.process.kill()
        except (OSError, AttributeError):
            self.process.kill()
        self.process.wait()

    def close(self) -> None:
        """Release the job; what a limited job still holds dies with it."""
        if WINDOWS and self.job:
            _win32()[2].CloseHandle(self.job)
            self.job = None


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


def main_checkout(path: Path) -> str:
    """The main checkout a path belongs to, normalized for comparison.

    The first folder up from `path` that holds a `.git`: a directory there is the main checkout;
    a file names the worktree's own git directory, whose `commondir` leads to the main
    checkout's `.git`. A `.git` file without `commondir` (a submodule) is its own checkout.
    Read without running git, and without requiring `path` to exist: a session may outlive
    its worktree. Outside any repository, the path itself.
    """
    path = Path(os.path.abspath(path))
    found = path
    for folder in (path, *path.parents):
        dot_git = folder / ".git"
        if dot_git.is_dir():
            found = folder
            break
        if dot_git.is_file():
            found = folder
            try:
                text = dot_git.read_text(encoding="utf-8").strip()
                if text.startswith("gitdir:"):
                    gitdir = folder / text.removeprefix("gitdir:").strip()
                    common = gitdir / (gitdir / "commondir").read_text(encoding="utf-8").strip()
                    found = Path(os.path.realpath(common)).parent
            except OSError:
                pass
            break
    return os.path.normcase(os.path.realpath(found))


def session_alive(pid: int, recorded_start: object) -> bool:
    """A registered pid still runs the session it was recorded for. On Linux the start time
    Claude Code records (`procStart`, clock ticks since boot) must match: a pid can be reused."""
    if LINUX and recorded_start:
        return process_start(pid) == str(recorded_start)
    return process_alive(pid)


def column(value: object) -> str:
    """A registry field as one column of the listing: spaces become `_`, `?` when absent."""
    text = "" if value is None else "_".join(str(value).split())
    return text or "?"


def predecessors(checkout: str, session: str) -> set[str]:
    """The sessions that handed `session` over the project of `checkout`: the `auteur` of each of
    its handoffs whose `successeur` names `session`. The relay writes both; a handoff that cannot
    be read, or carries no `auteur` (an older one), names nobody, the prudent side."""
    if not session:
        return set()
    # Imported here: handoff_trigger imports this module, and only `sessions` needs the folder.
    from handoff_trigger import handoff_dir

    found = set()
    for path in (handoff_dir() / Path(checkout).name).glob("*.md"):
        try:
            values = parse(split(path.read_text(encoding="utf-8"))[0])
        except (HeaderError, OSError, ValueError):
            continue
        successor = (values.get("successeur") or [""])[0].strip("\"'")
        author = (values.get("auteur") or [""])[0].strip("\"'")
        if author and names(successor, session):
            found.add(author)
    return found


def other_sessions(repo: Path, caller: set[int], session: str = "") -> list[str]:
    """`<pid> <kind> <name> <status> <cwd>` for each live session of `repo` outside `caller`,
    and outside the sessions that handed `session` over (`predecessors`)."""
    target = main_checkout(repo)
    handed_over = predecessors(target, session)
    found = []
    for entry in sorted((Path.home() / ".claude" / "sessions").glob("*.json")):
        if entry.stem.isdigit() and int(entry.stem) in caller:
            continue
        try:
            fields = json.loads(entry.read_text(encoding="utf-8"))
            pid, cwd = int(fields["pid"]), str(fields["cwd"])
        except (OSError, ValueError, KeyError, TypeError):
            found.append(f"{column(entry.stem)} ? ? unreadable {entry}")
            continue
        if pid in caller or str(fields.get("sessionId", "")) in handed_over:
            continue
        if not session_alive(pid, fields.get("procStart")):
            continue
        if main_checkout(Path(cwd)) != target:
            continue
        found.append(" ".join([str(pid), *(column(fields.get(key)) for key in ("kind", "name", "status")), cwd]))
    return found


def session_kind(pid: int) -> str:
    """The kind Claude Code records for a live session, "" when unknown. Claude Code 2.1.306
    writes `interactive` unless the session was started as `bg` (`claude --bg`), `daemon` or
    `daemon-worker`."""
    try:
        entry = json.loads((Path.home() / ".claude" / "sessions" / f"{pid}.json").read_text(encoding="utf-8"))
        return str(entry.get("kind", ""))
    except (OSError, ValueError, AttributeError):
        return ""


def calling_session() -> set[int]:
    """CLAUDE_PID, the process running this, and their ancestors."""
    pids = ancestors(os.getpid())
    owner = os.environ.get("CLAUDE_PID", "")
    if owner.isdigit():
        pids |= ancestors(int(owner)) | {int(owner)}
    return pids


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 3 and argv[1] == "check":
            values = check(Path(argv[2]))
            print(
                f"en_vol={len(values['en_vol'])} sauvetage={len(values['sauvetage'])} "
                f"feature={len(features(values))}"
            )
            return 0
        if len(argv) in (4, 5) and argv[1] == "set-successor":
            threshold = argv[4] if len(argv) == 5 else ""
            set_successor(Path(argv[2]), argv[3], threshold, os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
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
        if len(argv) == 2 and argv[1] == "self":
            owner = os.environ.get("CLAUDE_PID", "")
            kind = session_kind(int(owner)) if owner.isdigit() else ""
            print(column(kind), column(os.environ.get("CLAUDE_CODE_SESSION_ID")))
            return 0
        if len(argv) == 3 and argv[1] == "sessions":
            found = other_sessions(Path(argv[2]), calling_session(), os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
            for line in found:
                print(line)
            return 6 if found else 0
    except (HeaderError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(error)
        return 2
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
