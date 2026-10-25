"""PreToolUse hook of the `forge:coder` agent: the acts that belong to the orchestrator.

Plugin hooks run for every agent, so this one first reads `agent_type` and lets any other
agent through. For the coder, it refuses, with the reason on stderr and exit code 2:

- `gh pr merge` and `gh pr review`: qc judges and merges, through two agents the coder cannot
  launch;
- `gh issue close` and `gh issue edit`: the ticket's state, labels and assignees are
  `/forge:feature-build`'s, which is how it tells its claim from a human's (`agent-claimed`);
- the qc skill, under its plugin name `forge:qc` as under a bare `qc`, which the coder would
  otherwise run as the last step of opening a PR;
- `git push` with `-u`, `--set-upstream`, `-f` or `--force` (`--force-with-lease` stays allowed),
  and `git config` in write mode: the first writes, and the last two rewrite, the configuration
  shared by every worktree of the repository;
- a write (Edit, Write, MultiEdit, NotebookEdit) or a git command whose directory is not under the
  coder's own worktree, read from the event's `cwd`. A `cwd` that is not a linked worktree
  (`git rev-parse --git-dir` equal to `--git-common-dir`) is a coder launched without isolation,
  and is refused from its first write.

The command is parsed with `guard_git`'s splitter, which reads a backslash as an escape, as Bash
does; from a `PowerShell` call, where it escapes nothing, the backslashes become slashes first so
that a Windows path stays whole. A commit message that says
`gh pr merge` is data. As there, this guards against an accident, not against intent: a wrapper
(`env gh`, `gh.exe`) or `gh api` on the same endpoint is intent and is left alone.
An event the hook cannot read is refused, and `hooks.json` turns any crash into a refusal.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Callable, Mapping

from guard_git import (
    UNKNOWN,
    _commands,
    _directory_of,
    _forces,
    _moved,
    _run,
    _subcommand_and_args,
    gh_act,
    native_directory,
)

CODER = "forge:coder"
REFUSED_GH = {
    ("pr", "merge"): "`gh pr merge`: qc merges, once its two agents have judged the PR",
    ("pr", "review"): "`gh pr review`: qc judges, never the agent that coded the PR",
    ("issue", "close"): "`gh issue close`: the ticket's state is the orchestrator's",
    ("issue", "edit"): "`gh issue edit`: the ticket's labels and assignees are the orchestrator's",
}
QC_SKILLS = frozenset({"qc", "forge:qc"})
REFUSED_SKILL = (
    "the qc skill: the coder cannot launch qc-gate and qc-conf, so it would judge and merge its"
    " own PR alone; the orchestrator runs qc"
)


WRITE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
CONFIG_READS = frozenset(
    {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--get-color", "--get-colorbool"}
    | {"-l", "--list", "--show-origin", "--show-scope", "--name-only"}
)
CONFIG_WRITES = frozenset(
    {"--add", "--unset", "--unset-all", "--replace-all", "--rename-section", "--remove-section"}
    | {"-e", "--edit", "--set"}
)
NO_ISOLATION = (
    "the coder was launched without isolation: its directory is not a linked worktree, so it"
    " would write in the main copy; the orchestrator launches it with `isolation: worktree`"
)

# The coder's worktree from the event's directory: (root, None), or (None, why it has none).
Worktree = Callable[[str | None], tuple[str | None, str | None]]


def linked_worktree(cwd: str | None) -> tuple[str | None, str | None]:
    """The top of the linked worktree `cwd` is in, or why it is not in one."""
    program = shutil.which("git")
    if cwd is None or program is None:
        return None, "the hook could not read the coder's directory or find git"
    done = _run(
        [
            program,
            "rev-parse",
            "--path-format=absolute",
            "--git-dir",
            "--git-common-dir",
            "--show-toplevel",
        ],
        native_directory(cwd),
    )
    lines = done.stdout.splitlines() if done is not None and done.returncode == 0 else []
    if len(lines) != 3:
        return None, f"the coder's directory ({cwd}) is not in a git working tree"
    own_dir, common_dir, top = lines
    if _real(own_dir) == _real(common_dir):
        return None, NO_ISOLATION
    return top, None


def _real(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def _under(path: str, root: str) -> bool:
    here, top = _real(path), _real(root)
    return here == top or here.startswith(top.rstrip(os.sep) + os.sep)


def _outside(path: str, root: str, what: str) -> str | None:
    if _under(path, root):
        return None
    return f"{what} ({path}) is outside the coder's worktree ({root}): it works in its own"


def _config_writes(args: list[str]) -> bool:
    if any(arg in CONFIG_WRITES for arg in args):
        return True
    if any(arg in CONFIG_READS for arg in args):
        return False
    # `config <key>` reads; `config <key> <value>` writes.
    return len([arg for arg in args if not arg.startswith("-")]) >= 2


def _act_refusal(args: list[str]) -> str | None:
    """The git acts that touch the configuration shared by every worktree, or leave the worktree."""
    sub_args = _subcommand_and_args(args)
    leading = args[: len(args) - len(sub_args)]
    if any(word.split("=")[0] in ("--git-dir", "--work-tree") for word in leading):
        return "`--git-dir` and `--work-tree` aim git away from the coder's worktree"
    if not sub_args:
        return None
    sub, rest = sub_args[0], sub_args[1:]
    if sub == "push":
        if "--set-upstream" in rest or any(
            arg.startswith("-") and not arg.startswith("--") and "u" in arg[1:] for arg in rest
        ):
            return (
                "`push -u` writes the configuration shared by every worktree:"
                " use `push origin HEAD:<branch>`"
            )
        if _forces(rest):
            return "force push: the coder never rewrites a pushed branch"
    if sub == "config" and _config_writes(rest):
        return "`config` in write mode changes the configuration shared by every worktree"
    return None


def _git_commands(command: str, cwd: str | None, root: str | None) -> str | None:
    """Why a git command is refused: its act, or a directory outside `root` when `root` is known."""
    here = cwd
    saved: list[str | None] = []
    for item in _commands(command):
        if isinstance(item, str):
            if item == "(":
                saved.append(here)  # a subshell's `cd` ends with it
            else:
                here = saved.pop() if saved else cwd
            continue
        words = item
        while words and "=" in words[0] and not words[0].startswith("-"):
            words = words[1:]
        if not words:
            continue
        if words[0] == "cd":
            here = _moved(here, words[1] if len(words) > 1 else "~")
            continue
        if words[0] != "git":
            continue
        args = words[1:]
        if reason := _act_refusal(args):
            return reason
        if root is not None:
            directory = _directory_of(args, here)
            if directory is None or directory == UNKNOWN:
                return "a git command in a directory the hook cannot read: it may leave the worktree"
            where = native_directory(directory) or ""
            if reason := _outside(where, root, "the git command's directory"):
                return reason
    return None


def _runs_git(command: str) -> bool:
    for item in _commands(command):
        words = [w for w in item if "=" not in w or w.startswith("-")] if isinstance(item, list) else []
        if words and words[0] == "git":
            return True
    return False


def refusal(
    tool_name: str,
    tool_input: Mapping[str, object],
    cwd: str | None = None,
    worktree: Worktree | None = None,
) -> str | None:
    """Why the coder may not make this call, or None when it may.

    `worktree` finds the coder's worktree from the event's `cwd`; without it, only the acts that
    need no directory are judged.
    """
    if tool_name == "Skill":
        skill = str(tool_input.get("skill", "")).strip().lstrip("/")
        return REFUSED_SKILL if skill in QC_SKILLS else None
    if tool_name in WRITE_TOOLS:
        if worktree is None:
            return None
        root, why = worktree(cwd)
        if root is None:
            return why
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not isinstance(path, str) or not path:
            return "a write without a path the hook can read"
        return _outside(path if os.path.isabs(path) else os.path.join(cwd or "", path), root, "the file")
    command = str(tool_input.get("command", ""))
    if tool_name == "PowerShell":
        # A backslash escapes nothing in PowerShell, but the POSIX splitter eats it: `C:\work\tree`
        # would reach the guard as `C:worktree`, a relative path. Slashes are read by Windows too.
        command = command.replace("\\", "/")
    for item in _commands(command):
        if isinstance(item, list) and (act := gh_act(item)) is not None:
            if reason := REFUSED_GH.get(act[:2]):
                return reason
    root = None
    if worktree is not None and _runs_git(command):
        root, why = worktree(cwd)
        if root is None:
            return why
    return _git_commands(command, cwd, root)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        event = None
    tool_input = event.get("tool_input") if isinstance(event, dict) else None
    if not isinstance(event, dict) or not isinstance(tool_input, dict):
        # Fail closed: an event this hook cannot read is a call it cannot clear.
        reason: str | None = "the hook could not read the tool call it was given"
    elif event.get("agent_type") != CODER:
        return 0
    else:
        cwd = event.get("cwd")
        reason = refusal(
            str(event.get("tool_name", "")),
            tool_input,
            cwd if isinstance(cwd, str) else None,
            linked_worktree,
        )
    if reason is None:
        return 0
    sys.stderr.write(f"Blocked by the coder's guard (forge plugin): {reason}.\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
