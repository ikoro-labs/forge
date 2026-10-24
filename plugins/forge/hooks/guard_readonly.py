"""PreToolUse hook of the judges and deciders: they read, they never write.

Plugin hooks run for every agent, so this one first reads `agent_type`. Two lists apply:

- `forge:qc-conf`, `forge:staff-engineer`, `forge:product-owner`, and every agent the project
  names with the `readonly-agent` key of `docs/agents/usine.md` (its domain arbiter, say), run
  on an allow list: a shell command passes only when each of its simple commands is a read
  (`git show`, `gh pr view`, `grep`, a GET by `gh api`...) or starts with a command the project
  names with `readonly-command`, and writes no file by a redirection;
- `forge:qc-gate`, which must install and replay the CI in a copy of the head, runs on a deny
  list: no commit, push, history rewrite or configuration write, no checkout or cleaning of the
  project's own working copy, and no GitHub write.

To both, Edit, Write, MultiEdit and NotebookEdit are refused. As in `guard_git`, this guards
against an accident, not against intent. An event the hook cannot read is refused, and
`hooks.json` turns any crash into a refusal.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from pathlib import PurePosixPath

from guard_git import (
    GLOBAL_OPTIONS_WITH_VALUE,
    UNKNOWN,
    _commands,
    _gh_api_reads,
    _moved,
    _subcommand_and_args,
    gh_act,
    gh_command,
)
from usine import load, project_root

GATE = "forge:qc-gate"
READERS = frozenset({"forge:qc-conf", "forge:staff-engineer", "forge:product-owner"})
WRITE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})

READ_COMMANDS = frozenset(
    {"cat", "head", "tail", "wc", "grep", "egrep", "fgrep", "rg", "ls", "find", "sed", "sort"}
    | {"uniq", "cut", "tr", "jq", "echo", "printf", "pwd", "date", "diff", "cmp", "comm", "test"}
    | {"[", "true", "false", "basename", "dirname", "realpath", "readlink", "stat", "file", "nl"}
    | {"column", "sha256sum", "md5sum", "which", "type", "cd", "tree", "less", "more"}
)
GIT_READS = frozenset(
    {"show", "log", "diff", "grep", "merge-tree", "rev-parse", "rev-list", "ls-files", "ls-tree"}
    | {"cat-file", "merge-base", "status", "fetch", "blame", "describe", "shortlog", "show-ref"}
    | {"for-each-ref", "name-rev", "range-diff", "whatchanged", "help", "version"}
)
GH_READS = frozenset(
    {("pr", "view"), ("pr", "diff"), ("pr", "checks"), ("pr", "list"), ("pr", "status")}
    | {("issue", "view"), ("issue", "list"), ("issue", "status"), ("run", "view"), ("run", "list")}
    | {("release", "view"), ("release", "list"), ("repo", "view"), ("label", "list")}
    | {("workflow", "view"), ("workflow", "list"), ("auth", "status")}
)
GIT_WRITES = frozenset(
    {"commit", "push", "merge", "rebase", "reset", "cherry-pick", "revert", "am", "apply"}
    | {"tag", "stash", "filter-branch", "replace", "notes", "update-ref", "gc", "prune"}
)
WORKING_COPY = frozenset({"checkout", "switch", "restore", "clean", "rm", "mv"})
CONFIG_READS = frozenset({"--get", "--get-all", "--get-regexp", "--list", "-l"})
BRANCH_LISTS = frozenset(
    {"-a", "-r", "-v", "-vv", "--all", "--remotes", "--list", "-l", "--show-current"}
    | {"--contains", "--no-contains", "--merged", "--no-merged", "--points-at", "--sort"}
    | {"--format", "--color", "--no-color", "--column", "--no-column"}
)
BRANCH_LIST_MODE = frozenset(
    {"-a", "-r", "--all", "--remotes", "--list", "-l", "--points-at"}
    | {"--contains", "--no-contains", "--merged", "--no-merged"}
)


def _words(item: list[str]) -> list[str]:
    while item and "=" in item[0] and not item[0].startswith("-"):
        item = item[1:]
    return item


def _is_redirection(word: str) -> bool:
    """The tokenizer splits `2>out` into `2`, `>`, `out`: an operator word is made of `<>&|`."""
    return bool(word) and set(word) <= set("<>&|") and ("<" in word or ">" in word)


def split_redirections(words: list[str]) -> tuple[list[str], list[str]]:
    """The words of a command without its redirections, and the files it writes by them.

    `/dev/null` is no file, nor is a duplicated descriptor (`2>&1`, `>&2`); `<` and `<<` read.
    """
    plain: list[str] = []
    written: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        if not _is_redirection(word):
            plain.append(word)
            index += 1
            continue
        if plain and plain[-1].isdigit():
            plain.pop()
        target = words[index + 1] if index + 1 < len(words) else ""
        duplicates = word.endswith("&") and (target.isdigit() or target == "-")
        if ">" in word and not duplicates and target != "/dev/null":
            written.append(target)
        index += 2
    return plain, written


def _gh_reads(words: list[str]) -> bool:
    call = gh_command(words)
    if call is None:
        return False
    if call and call[0] == "api":
        return _gh_api_reads(call[1:])
    if call and call[0] in ("search", "help", "version", "status"):
        return True
    act = gh_act(words)
    return act is not None and act[:2] in GH_READS


def _git_reads(args: list[str]) -> bool:
    args = _subcommand_and_args(args)
    if not args:
        return True
    sub, rest = args[0], args[1:]
    if sub == "config":
        return any(flag in CONFIG_READS for flag in rest)
    if sub == "branch":
        flags = [arg.partition("=")[0] for arg in rest if arg.startswith("-")]
        if not all(flag in BRANCH_LISTS for flag in flags):
            return False
        # A word that is not a flag names a branch to create, unless a list flag makes it a pattern.
        return len(flags) == len(rest) or any(flag in BRANCH_LIST_MODE for flag in flags)
    if sub == "remote":
        return not rest or rest[0] in ("-v", "--verbose", "get-url", "show")
    if sub == "worktree":
        return bool(rest) and rest[0] == "list"
    return sub in GIT_READS


def _plain_read(words: list[str]) -> bool:
    command = PurePosixPath(words[0]).name
    if command not in READ_COMMANDS:
        return False
    if command == "sed":
        return not any(w.startswith("-i") or w.startswith("--in-place") for w in words[1:])
    if command in ("sort", "tree") and any(w.startswith("-o") for w in words[1:]):
        return False  # `sort -o out` and `tree -o out` write `out`
    if command == "uniq":  # `uniq in out` writes `out`
        return len([w for w in words[1:] if not w.startswith("-")]) <= 1
    if command == "find":
        return not any(w in ("-delete", "-exec", "-execdir", "-ok", "-okdir") for w in words[1:]) and (
            not any(w.startswith("-fprint") or w == "-fls" for w in words[1:])
        )
    return True


def reader_refusal(command: str, allowed_prefixes: Iterable[str] = ()) -> str | None:
    """Why a reader may not run `command`, or None when every part of it is a read."""
    prefixes = [prefix.split() for prefix in allowed_prefixes if prefix.strip()]
    if "`" in command or "<(" in command or ">(" in command:
        return "a backtick or process substitution hides the command it runs"
    for item in _commands(command):
        if isinstance(item, str):
            continue
        words, written = split_redirections(_words(item))
        if written:
            return f"`{' '.join(words)}` writes `{written[0]}` by a redirection"
        if not words:
            continue
        if any(words[: len(prefix)] == prefix for prefix in prefixes):
            continue
        if any(word.startswith("--output") for word in words[1:]):
            return f"`{' '.join(words)}` writes a file by `--output`"
        if words[0] == "git":
            if _git_reads(words[1:]):
                continue
        elif words[0] == "gh":
            if _gh_reads(words):
                continue
        elif _plain_read(words):
            continue
        return f"`{' '.join(words)}` is not a read this role may run"
    return None


def _inside(directory: str | None, project: str) -> bool:
    if directory is None or directory == UNKNOWN:
        return True
    path, root = PurePosixPath(directory), PurePosixPath(project)
    if not path.is_absolute():
        return True
    return path == root or root in path.parents


def gate_refusal(command: str, cwd: str | None, project: str) -> str | None:
    """Why qc-gate may not run `command`, or None: a deny list, so the head copy can be built."""
    here = cwd
    saved: list[str | None] = []
    for item in _commands(command):
        if isinstance(item, str):
            if item == "(":
                saved.append(here)
            else:
                here = saved.pop() if saved else cwd
            continue
        words = split_redirections(_words(item))[0]
        if not words:
            continue
        if words[0] == "cd":
            here = _moved(here, words[1] if len(words) > 1 else "~")
            continue
        if words[0] == "git":
            directory = here
            args = words[1:]
            index = 0
            while index < len(args) and args[index].startswith("-"):
                if args[index] == "-C" and index + 1 < len(args):
                    directory = _moved(directory, args[index + 1])
                index += 2 if args[index] in GLOBAL_OPTIONS_WITH_VALUE else 1
            rest = _subcommand_and_args(args)
            sub = rest[0] if rest else ""
            if sub in GIT_WRITES:
                return f"`git {sub}`: the gate measures, it never changes a history"
            if sub == "config" and not any(flag in CONFIG_READS for flag in rest[1:]):
                return "`git config` write: the gate reads the configuration, it never sets it"
            if sub == "branch" and not _git_reads(args):
                return "`git branch` write: the gate never creates or deletes a branch"
            if sub in WORKING_COPY and _inside(directory, project):
                return (
                    f"`git {sub}` in the project's working copy: replay in a copy of the head"
                    " outside it"
                )
            continue
        if words[0] == "gh" and not _gh_reads(words):
            return f"`{' '.join(words)}`: the gate never writes to GitHub"
    return None


def refusal(event: dict[str, object]) -> str | None:
    agent = event.get("agent_type")
    tool = str(event.get("tool_name", ""))
    tool_input = event.get("tool_input")
    config = load(project_root(event))
    if agent != GATE and agent not in READERS and agent not in config.get("readonly-agent", []):
        return None
    if not isinstance(tool_input, dict):
        return "the hook could not read the tool call it was given"
    if tool in WRITE_TOOLS:
        return f"{tool}: this role reads, it never writes a file"
    if tool not in ("Bash", "PowerShell"):
        return None
    command = str(tool_input.get("command", ""))
    if agent == GATE:
        return gate_refusal(command, _str(event.get("cwd")), str(project_root(event)))
    return reader_refusal(command, config.get("readonly-command", []))


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        event = None
    if not isinstance(event, dict):
        # Fail closed: an event this hook cannot read is a call it cannot clear.
        reason: str | None = "the hook could not read the tool call it was given"
    else:
        reason = refusal(event)
    if reason is None:
        return 0
    sys.stderr.write(f"Blocked by the read-only guard (forge plugin): {reason}.\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
