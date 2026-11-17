"""The journal of the guards' refusals, `~/.claude/hooks/state/refusals/<YYYY-MM-DD>.jsonl`.

`guard_git`, `guard_coder` and `guard_readonly` call `record` at the one point where they refuse. A
line holds `date` (UTC, ISO 8601), `guard`, `rule`, `agent` (the prefixed name, `main` for the main
session), `repo`, `branch` and `verb`, and nothing else: never the command, whose arguments may
carry a secret, and never the reason, which quotes it.

`rule` is a fixed name. Each guard keeps a table of `(marker, name)` beside the texts it refuses
with, and `rule_of` returns the name of the first marker found in the reason, `other` when none is.
The name comes from the table, never from the reason, so no text of the command reaches the journal.
The journal lives on the host: two hosts give two journals.

Writing the journal never changes a decision: `record` swallows every failure, and the caller keeps
its exit code and its message. `factory_slo.py` reads the journal with `read`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path

OTHER = "other"
MAIN = "main"
UNKNOWN_AGENT = "unknown"
GIT_TIMEOUT_SECONDS = 5


def journal_dir() -> Path:
    return Path.home() / ".claude" / "hooks" / "state" / "refusals"


def rule_of(reason: str, rules: Iterable[tuple[str, str]]) -> str:
    """The name of the first rule whose marker is in `reason`, `other` when none is."""
    for marker, name in rules:
        if marker in reason:
            return name
    return OTHER


def _git(directory: str | None, *args: str) -> str:
    program = shutil.which("git")
    if program is None or not directory:
        return ""
    try:
        done = subprocess.run(  # noqa: S603 - a fixed argv, the event's directory as cwd
            [program, *args],
            cwd=directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def repo_of(directory: str | None) -> str:
    """The name of the repository of `directory`: the same from the main copy and its worktrees."""
    common = _git(directory, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        return ""
    path = Path(common)
    return (path.parent if path.name == ".git" else path).name


def _branch_of(directory: str | None) -> str:
    return _git(directory, "branch", "--show-current") or ("detached" if repo_of(directory) else "")


def record(
    guard: str,
    reason: str,
    rules: Iterable[tuple[str, str]],
    event: object,
    verb: Callable[[], str],
) -> None:
    """Add a line for a refused call: `rules` name the rule from `reason`, `verb` the call.

    `verb` is asked here, inside the guard against failure, and says `git push` or `gh pr merge`,
    never an argument. Any failure is swallowed: the refusal stands as it is.
    """
    try:
        agent, cwd = UNKNOWN_AGENT, None
        if isinstance(event, Mapping):
            kind = event.get("agent_type")
            agent = kind if isinstance(kind, str) and kind else MAIN
            where = event.get("cwd")
            cwd = where if isinstance(where, str) else None
        now = datetime.now(timezone.utc)
        line = {
            "date": now.isoformat(timespec="seconds"),
            "guard": guard,
            "rule": rule_of(reason, rules),
            "agent": agent,
            "repo": repo_of(cwd),
            "branch": _branch_of(cwd),
            "verb": verb(),
        }
        folder = journal_dir()
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / f"{now:%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - the journal must never change the decision it follows
        return


def read(since: datetime, until: datetime) -> Iterator[dict[str, str]] | None:
    """The lines dated in `[since, until[`, or None when there is no journal on this host.

    A line that cannot be read, or whose date is not one, is left out.
    """
    folder = journal_dir()
    if not folder.is_dir():
        return None
    return _lines(folder, since, until)


def _lines(folder: Path, since: datetime, until: datetime) -> Iterator[dict[str, str]]:
    for path in sorted(folder.glob("*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in text.splitlines():
            try:
                line = json.loads(raw)
                moment = datetime.fromisoformat(line["date"])
            except (ValueError, KeyError, TypeError):
                continue
            if not isinstance(line, dict) or moment.tzinfo is None:
                continue
            if since <= moment < until:
                yield line
