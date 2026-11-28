"""The dispatcher's local lock on a ticket, read side (F-0003, ticket 4 part a).

One JSON file per ticket, `~/.claude/hooks/state/dispatch/locks/<project>/<ticket>.json`, the project
path flattened as the relay's counters flatten it. Fields: `ticket`, `pid`, `start` (the value of
`handoff_header.process_start` for `pid`), `name`, `worktree`, `zones`, `since`. The dispatcher that
launches an agent writes the lock (ticket 8 adds `claim`); this module reads it, so that
`handoff_header.other_sessions` can tell a dispatcher's agent from a session of the human, and a pinned agent
(`forge:feature-build --ticket`) checks (`own`) and frees (`release`) its own lock, from the command line.

A lock is dead when its process is gone, or when the pid now runs another process (its start time
differs from `start`). A lock that cannot be read names no pid: it is skipped here, which can only
leave a session listed, the prudent side.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

import handoff_header
import handoff_trigger


class Lock(NamedTuple):
    ticket: str
    pid: int
    start: str
    name: str

    @property
    def alive(self) -> bool:
        """The locked process still runs. Without a recorded start, the pid alone says."""
        if not handoff_header.process_alive(self.pid):
            return False
        return not self.start or handoff_header.process_start(self.pid) == self.start


def locks_dir(project: Path) -> Path:
    name = re.sub(r"[\\/:]", "-", str(project))
    return handoff_trigger.state_dir() / "dispatch" / "locks" / name


def read(path: Path) -> Lock | None:
    """The lock a file holds, None when it cannot be read."""
    try:
        fields = json.loads(path.read_text(encoding="utf-8"))
        return Lock(
            str(fields["ticket"]), int(fields["pid"]), str(fields.get("start") or ""), str(fields.get("name") or ""),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def held(project: Path) -> list[Lock]:
    """The readable locks of `project` whose process is alive."""
    found = []
    for path in sorted(locks_dir(project).glob("*.json")):
        lock = read(path)
        if lock is not None and lock.alive:
            found.append(lock)
    return found


def lock_path(project: Path, ticket: str) -> Path:
    return locks_dir(project) / f"{ticket}.json"


def own(project: Path, ticket: str, session: set[int]) -> tuple[bool, str]:
    """Whether the lock of `ticket` is held by a process of `session`, and the reason in words.

    A pinned agent (`forge:feature-build --ticket`) goes on only when it is the process the dispatcher
    locked the ticket for: no file, an unreadable one, a dead pid, or the pid of another agent says no.
    """
    path = lock_path(project, ticket)
    if not path.exists():
        return False, f"aucun verrou pour le ticket #{ticket}"
    lock = read(path)
    if lock is None:
        return False, f"le verrou du ticket #{ticket} est illisible"
    if not lock.alive:
        return False, f"le verrou du ticket #{ticket} tient un pid mort ({lock.pid})"
    if lock.pid not in session:
        return False, f"le verrou du ticket #{ticket} est tenu par un autre processus (pid {lock.pid})"
    return True, f"verrou du ticket #{ticket} tenu par cette session (pid {lock.pid})"


def release(project: Path, ticket: str) -> bool:
    """Remove the lock file of `ticket`; False when there was none."""
    try:
        lock_path(project, ticket).unlink()
    except FileNotFoundError:
        return False
    return True


def main(argv: list[str]) -> int:
    """`check <project> <ticket>` and `release <project> <ticket>`, for the pinned agent's own lock.

    The project may be a worktree: the locks are keyed by its main checkout. Code 0: the lock is this
    session's (and, for `release`, is removed). Code 1: it is not, and nothing is removed. Code 2: a wrong call.
    """
    if len(argv) != 3 or argv[0] not in ("check", "release") or not argv[2].isdigit():
        print("usage: agent_lock.py check|release <project> <ticket number>")
        return 2
    project, ticket = Path(handoff_header.main_checkout(Path(argv[1]))), argv[2]
    ok, reason = own(project, ticket, handoff_header.calling_session())
    if ok and argv[0] == "release":
        release(project, ticket)
        reason = f"verrou du ticket #{ticket} libéré"
    print(f"VERROU: {reason}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
