"""SubagentStop and SessionStart hook: the cleanup after a finished agent (ikoro-labs/forge#199, (c)).

What an agent leaves behind used to be cleaned by hand at each relay. The hook does it, on the
main checkout of the repository (`handoff_header.main_checkout`), without network (no `git fetch`:
"contained in a remote branch" means in the remote-tracking refs as they are), and does nothing
outside a git repository. It touches only what follows, and a read error deletes nothing: the
doubt keeps.

1. Worktrees `<main checkout>/.claude/worktrees/agent-*` whose agent is finished: unlocked, or
   locked by a holder that is gone (`handoff_header.lock_holder_alive`, the rule of `live_agents`:
   a dead pid, or a live pid with another start time, was reused). A clean one (`git status
   --porcelain` empty, untracked files included) is unlocked if it is locked, then removed
   without `--force`; a branch it carried stays, with its work. A detached head is removed only if
   its commit is contained in `main`, `origin/main` or a remote branch, else it would be lost. A
   dirty one, or one whose detached head is found nowhere else, is left and reported.
   At SubagentStop, the worktree of the agent that stops is still locked by the living session:
   it stays, and goes at a later passage.
2. Local branches `worktree-agent-*` that no worktree holds and whose tip is contained in `main`,
   `origin/main` or a remote-tracking branch: `git branch -D`. The deletion is run here, by
   subprocess: `guard_git` keeps refusing `git branch -D` to an agent.
3. Agent caches, key `agent-cache-dir` (a folder, `~` expanded). At SubagentStop only: the direct
   subfolders of that folder that the transcript of the stopping agent (`agent_transcript_path`)
   names are deleted. Never at SessionStart: other sessions of the machine may have live agents in
   the same folder, and a cache a live agent still uses is not told apart from a finished one.
4. Rescue bundles, key `rescue-bundle-dir` (a folder, `~` expanded): each `*.bundle` whose heads
   (`git bundle list-heads`) all exist in this repository and are contained in `main`,
   `origin/main` or a remote-tracking branch is deleted; an unreadable bundle, or one with a head
   this repository lacks, stays and is reported.

A key that is absent makes its step "sans objet (clé `<nom>` absente)": nothing is done and no
default is taken. Steps 1 and 2 read no key: they follow Claude Code's convention, not a project
value.

It reports one line per removed, deleted or left element, in `systemMessage` (and, at
SessionStart, in `additionalContext`), and says nothing when there is nothing to say.

It is not a guard: it never blocks. Any failure exits 0 and says nothing, and it never exits 2,
which would hold a subagent at SubagentStop.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import handoff_header
from usine import load, project_root

GIT_TIMEOUT = 20
AGENT_DIR = "agent-"
BRANCH_PREFIX = "worktree-agent-"
# Where a commit is safe: the local `main`, or any remote-tracking ref (`origin/main` among them).
SAFE_REFS = ("refs/heads/main", "refs/remotes")
# Git location variables leaked by a calling git hook would aim every command at another repository.
LEAKED_GIT_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY")


def git(folder: Path | str, *args: str) -> subprocess.CompletedProcess[str] | None:
    """`git -C <folder> <args>`, None when git cannot be run or times out."""
    env = {key: value for key, value in os.environ.items() if key not in LEAKED_GIT_VARIABLES}
    env["GIT_OPTIONAL_LOCKS"] = "0"  # a status taken in passing must not take the index lock
    try:
        return subprocess.run(
            ["git", "-C", str(folder), *args], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=GIT_TIMEOUT, check=False, env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def git_output(folder: Path | str, *args: str) -> str | None:
    """The stripped standard output of a git command that succeeded, else None."""
    result = git(folder, *args)
    return result.stdout.strip() if result is not None and result.returncode == 0 else None


def contained(repo: Path, sha: str) -> bool:
    """Whether a commit is in `main` or in a remote-tracking branch; an unknown commit is not."""
    return bool(git_output(repo, "for-each-ref", "--contains", sha, "--format=%(refname)", *SAFE_REFS))


def worktree_entries(repo: Path) -> list[dict[str, str]] | None:
    """The fields of each worktree of the repository, None when the list cannot be read."""
    listing = git_output(repo, "worktree", "list", "--porcelain")
    if listing is None:
        return None
    return [
        {key: rest for key, _, rest in (line.partition(" ") for line in block.splitlines())}
        for block in listing.split("\n\n") if block.strip()
    ]


def same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right))


def is_agent_worktree(repo: Path, path: str) -> bool:
    """`<repo>/.claude/worktrees/agent-*`, the place and the name Claude Code gives an agent's worktree."""
    return Path(path).name.startswith(AGENT_DIR) and same_path(Path(path).parent, repo / ".claude" / "worktrees")


def finished(fields: dict[str, str]) -> bool:
    """An agent is finished when nothing locks its worktree, or the lock's holder is gone."""
    if "locked" not in fields:
        return True
    return not handoff_header.lock_holder_alive(fields["locked"])[0]


def clean_worktrees(repo: Path) -> list[str]:
    entries = worktree_entries(repo)
    if entries is None:
        return []
    report = []
    for fields in entries:
        path = fields.get("worktree", "")
        if not is_agent_worktree(repo, path) or "prunable" in fields or not finished(fields):
            continue
        state = git_output(path, "status", "--porcelain", "--untracked-files=all")
        if state is None:
            report.append(f"left worktree {path}: its state cannot be read")
        elif state:
            report.append(f"left worktree {path}: uncommitted or untracked files")
        elif "detached" in fields and not contained(repo, fields.get("HEAD", "")):
            report.append(f"left worktree {path}: its detached head {fields.get('HEAD', '')[:8]} is in no branch")
        else:
            if "locked" in fields:
                git(repo, "worktree", "unlock", path)
            removal = git(repo, "worktree", "remove", path)
            if removal is not None and removal.returncode == 0:
                report.append(f"removed worktree {path} (agent finished, clean)")
            else:
                why = (removal.stderr.strip().splitlines() or ["git did not answer"])[-1] if removal else "git failed"
                report.append(f"left worktree {path}: git refused to remove it ({why})")
    return report


def emit(event_name: str, lines: list[str]) -> None:
    """One line per element, by the channel of the event; nothing when there is nothing."""
    if not lines:
        return
    text = "\n".join(f"agent cleanup (forge plugin): {line}" for line in lines)
    output: dict[str, object] = {"systemMessage": text}
    if event_name == "SessionStart":
        output["hookSpecificOutput"] = {"hookEventName": event_name, "additionalContext": text}
    sys.stdout.write(json.dumps(output) + "\n")


def clean(event: dict[str, object]) -> list[str]:
    name = event.get("hook_event_name")
    if name not in ("SubagentStop", "SessionStart"):
        return []
    root = handoff_header.main_checkout(project_root(event))
    repo = Path(root)
    if not (repo / ".git").is_dir():
        return []
    config = load(project_root(event))
    del config  # the keys of steps 3 and 4 are read there
    report: list[str] = []
    for step in (clean_worktrees,):
        try:
            report.extend(step(repo))
        except Exception:  # noqa: BLE001 - one step failing must not stop the others
            continue
    return report


def main(stdin) -> int:
    try:
        event = json.load(stdin)
        if isinstance(event, dict) and isinstance(event.get("cwd", ""), str):
            emit(str(event.get("hook_event_name")), clean(event))
    except Exception:  # noqa: BLE001 - a cleanup hook never blocks, whatever fails
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin))
