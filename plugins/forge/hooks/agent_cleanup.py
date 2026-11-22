"""SubagentStop and SessionStart hook: the cleanup after a finished agent (ikoro-labs/forge#199, (c)).

What an agent leaves behind used to be cleaned by hand at each relay. The hook does it, on the
main checkout of the repository (`handoff_header.main_checkout`), without network (no `git fetch`:
"contained in a remote branch" means in the remote-tracking refs as they are), and does nothing
outside a git repository. It touches only what follows, and a read error deletes nothing: the
doubt keeps.

1. Worktrees `<main checkout>/.claude/worktrees/agent-*` whose agent is finished:
   - locked by a holder that is gone (`handoff_header.lock_holder_alive`, the rule of `live_agents`:
     a dead pid, or a live pid with another start time, was reused): the session is dead, its agents
     with it;
   - unlocked: only when Claude Code records the agent as returned (`agent-<id>.meta.json` with
     `"finished": true`, under `<config folder>/projects/<project>/<session>/subagents/`, the config
     folder being `CLAUDE_CONFIG_DIR` or `~/.claude`) and its transcript `agent-<id>.jsonl` has not been
     written for `TRANSCRIPT_GRACE` (30 minutes). An agent woken by `SendMessage` works in its worktree
     without locking it, and what becomes of `finished` then was not observed: the silence of the
     transcript tells a living agent. A record missing or unreadable keeps the worktree, silently.
   A clean one (`git status --porcelain` empty, untracked files included) is unlocked if it is
   locked, then removed without `--force`; a branch it carried stays, with its work. A detached head
   is removed only if its commit is contained in `main`, `origin/main` or a remote branch, else it
   would be lost. A dirty one, or one whose detached head is found nowhere else, is left and reported.
   At SubagentStop, the worktree of the agent that stops is still locked by the living session, or
   its transcript was just written: it stays, and goes at a later passage. The cost of the delay: an
   agent returned, clean and pushed, then woken by `SendMessage` more than 30 minutes later, finds no
   worktree; its work is on its pushed branch.
2. Local branches `worktree-agent-*` that no worktree holds and whose tip is contained in `main`,
   `origin/main` or a remote-tracking branch: `git branch -D`. The deletion is run here, by
   subprocess: `guard_git` refuses `git branch -D` to an agent unless a verified bundle of the key
   `rescue-bundle-dir` holds the branch; here the tip is already in `main` or a remote branch, so
   no bundle is needed.
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

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import handoff_header
from usine import load, project_root
from utf8_stdio import use_utf8

GIT_TIMEOUT = 20
MAX_TRANSCRIPT = 64 * 1024 * 1024  # a larger transcript is not read: the doubt keeps
# An unlocked worktree is a finished agent's only when its transcript has been silent this long: 30
# minutes, beyond the longest tool call, so that an agent woken by SendMessage (it works in its
# worktree without locking it, and its transcript grows with each step) is not taken for finished.
TRANSCRIPT_GRACE = 30 * 60
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


def claude_config_dir() -> Path:
    """Where Claude Code keeps its records: `CLAUDE_CONFIG_DIR` when set, else `~/.claude`."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path(os.path.expanduser("~")) / ".claude")


def returned_and_silent(agent_dir: str) -> bool:
    """Whether Claude Code records the agent as returned and its transcript has been silent for the
    grace delay. The records are `<config>/projects/<project>/<session>/subagents/agent-<id>.meta.json`
    (`"finished": true` once the agent has returned) and `agent-<id>.jsonl`, its transcript. A record
    that is missing, unreadable or not as expected, or a clock that puts the write in the future, is
    not that: the doubt keeps the worktree, and says nothing."""
    try:
        metas = sorted(claude_config_dir().glob(f"projects/*/*/subagents/{glob.escape(agent_dir)}.meta.json"))
        if not metas:
            return False
        for meta in metas:
            record = json.loads(meta.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("finished") is not True:
                return False
            age = time.time() - meta.with_name(f"{agent_dir}.jsonl").stat().st_mtime
            if age < TRANSCRIPT_GRACE:
                return False
        return True
    except (OSError, ValueError):
        return False


def finished(fields: dict[str, str]) -> bool:
    """A locked worktree is a finished agent's when the lock's holder is gone (its session is dead, and
    its agents with it). An unlocked one may be a living agent woken by SendMessage, which does not lock
    it: it is finished only when Claude Code records the agent as returned and its transcript is silent."""
    if "locked" in fields:
        return not handoff_header.lock_holder_alive(fields["locked"])[0]
    return returned_and_silent(Path(fields.get("worktree", "")).name)


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


def clean_branches(repo: Path) -> list[str]:
    """`git branch -D` on each `worktree-agent-*` branch that no worktree holds and whose tip is safe."""
    entries = worktree_entries(repo)
    listing = git_output(repo, "for-each-ref", "--format=%(refname) %(objectname)", f"refs/heads/{BRANCH_PREFIX}*")
    if entries is None or not listing:
        return []
    held = {fields.get("branch") for fields in entries}
    report = []
    for line in listing.splitlines():
        ref, _, sha = line.partition(" ")
        name = ref.removeprefix("refs/heads/")
        if ref in held or not name.startswith(BRANCH_PREFIX) or not contained(repo, sha):
            continue
        deletion = git(repo, "branch", "-D", name)
        if deletion is not None and deletion.returncode == 0:
            report.append(f"deleted branch {name} ({sha[:8]}, in main or a remote branch, no worktree)")
    return report


def declared_folders(config: dict[str, list[str]], key: str, repo: Path) -> list[Path]:
    """The folders a key names, `~` expanded. A relative one is dropped, and so is one that holds the
    home or the repository (a purge there would reach the user's own folders): the doubt keeps."""
    found = []
    for value in config.get(key, []):
        folder = Path(os.path.expanduser(value))
        home = Path(os.path.expanduser("~"))
        if folder.is_absolute() and not any(
            Path(os.path.normcase(os.path.realpath(held))).is_relative_to(os.path.normcase(os.path.realpath(folder)))
            for held in (home, repo)
        ):
            found.append(folder)
    return found


def mentions(folder: Path, text: str) -> bool:
    """Whether the text names the folder: by its path, as JSON writes it, or from `~`, and not a
    longer name that merely starts the same."""
    spellings = {str(folder), folder.as_posix(), json.dumps(str(folder))[1:-1]}
    home = Path(os.path.expanduser("~"))
    if folder.is_relative_to(home):
        spellings.add("~/" + folder.relative_to(home).as_posix())
    return any(
        re.search(re.escape(spelling) + r"(?![\w.-])", text) for spelling in spellings
    )


def clean_caches(folders: list[Path], transcript: object) -> list[str]:
    """Delete the direct subfolders of each cache folder that the agent's transcript names."""
    if not folders or not isinstance(transcript, str) or not transcript:
        return []
    path = Path(os.path.expanduser(transcript))
    try:
        if path.stat().st_size > MAX_TRANSCRIPT:
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    report = []
    for folder in folders:
        try:
            children = sorted(child for child in folder.iterdir() if child.is_dir() and not child.is_symlink())
        except OSError:
            continue
        for child in children:
            if not mentions(child, text):
                continue
            try:
                remove_tree(child)
                report.append(f"purged agent cache {child}")
            except OSError:
                report.append(f"left agent cache {child}: it cannot be removed")
    return report


def remove_tree(path: Path) -> None:
    """rmtree that also removes the read-only files a Windows folder may hold."""

    def writable(function, target, _error) -> None:
        os.chmod(target, 0o700)
        function(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=writable)
    else:
        shutil.rmtree(path, onerror=writable)


def clean_bundles(repo: Path, folders: list[Path]) -> list[str]:
    """Delete each `*.bundle` whose heads all exist here and are contained in `main` or a remote branch.

    A bundle that cannot be read, or has a head this repository lacks, stays and is reported; one
    whose heads exist but are not contained yet stays silently, it is still the only copy.
    """
    report = []
    for folder in folders:
        try:
            bundles = sorted(path for path in folder.glob("*.bundle") if path.is_file() and not path.is_symlink())
        except OSError:
            continue
        for bundle in bundles:
            listing = git_output(repo, "bundle", "list-heads", str(bundle))
            heads = [line.split()[0] for line in (listing or "").splitlines() if line.split()]
            if not heads:
                report.append(f"left rescue bundle {bundle}: it cannot be read")
            elif any(git_output(repo, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}") is None for sha in heads):
                report.append(f"left rescue bundle {bundle}: a head is not in this repository")
            elif all(contained(repo, sha) for sha in heads):
                try:
                    bundle.unlink()
                    report.append(f"deleted rescue bundle {bundle} (its heads are in main or a remote branch)")
                except OSError:
                    report.append(f"left rescue bundle {bundle}: it cannot be deleted")
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
    # Caches are purged at SubagentStop only: at SessionStart another session's agent may live in them.
    caches = declared_folders(config, "agent-cache-dir", repo) if name == "SubagentStop" else []
    steps = (
        lambda: clean_worktrees(repo),
        lambda: clean_branches(repo),
        lambda: clean_caches(caches, event.get("agent_transcript_path")),
        lambda: clean_bundles(repo, declared_folders(config, "rescue-bundle-dir", repo)),
    )
    report: list[str] = []
    for step in steps:
        try:
            report.extend(step())
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
    use_utf8()
    sys.exit(main(sys.stdin))
