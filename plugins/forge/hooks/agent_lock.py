"""The dispatcher's local lock on a ticket, read side (F-0003, ticket 4 part a).

One JSON file per ticket, `~/.claude/hooks/state/dispatch/locks/<project>/<ticket>.json`, the project
path flattened as the relay's counters flatten it. Fields: `ticket`, `pid`, `start` (the value of
`handoff_header.process_start` for `pid`), `name`, `worktree`, `zones`, `since`. The dispatcher that
launches an agent writes the lock (ticket 8 adds `claim` and `release`); this module only reads it, so
that `handoff_header.other_sessions` can tell a dispatcher's agent from a session of the human.

A lock is dead when its process is gone, or when the pid now runs another process (its start time
differs from `start`). A lock that cannot be read names no pid: it is skipped here, which can only
leave a session listed, the prudent side.
"""

from __future__ import annotations

import json
import re
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
