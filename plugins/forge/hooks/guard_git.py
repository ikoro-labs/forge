"""PreToolUse hook: the git and GitHub commands an agent may not run.

Refused, with the reason on stderr and exit code 2 so Claude Code blocks the call:

- a commit on `main`, a push to `main`, any `--force` push (`--force-with-lease` on a feature
  branch stays allowed: restacking a PR after its base merged needs it);
- `git branch -D`, `git reset --hard`, `git clean -f`, and `--no-verify`, which skips the hooks;
- `gh pr merge` while any check of the PR is not green;
- `gh pr merge` whose message or PR description closes a ticket it cites with `Refs`: the first
  PR of a split ticket must leave it open, and GitHub reads a closing keyword anywhere, prose
  included, in the squash message as in the description. The message is read from `--subject`,
  `--body` and `--body-file`, the description from `gh pr view`; a body built by a shell
  substitution cannot be read here, which is why `/forge:qc` writes it to a file.

The command is parsed, not grepped: a commit message that says "push --force" is data. Heredoc
bodies are dropped first, then the command is split on shell operators with `shlex`. This is
protection against an accident, not against intent: the human can always run the command, and
a wrapper (`env git`, `command git`, `/usr/bin/git`, `git.exe`) is intent, so it is left alone
on purpose.

The branch that matters is the one of the directory git acts on: `cd <dir> &&` and `git -C
<dir>` move it, so each command is judged against the branch checked out there.

A project's own gestures (runners, protection, labels reserved to a human) are not here: the
project keeps them in its own `.claude/settings.json` hooks, which run beside this one.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath

# Every external call has a timeout: a hook that hangs blocks the agent's command.
TIMEOUT_SECONDS = 20

HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")
OPERATORS = {";", "&&", "||", "|", "&", "(", ")"}
BRANCH_SWITCH = ({"checkout", "-b"}, {"checkout", "-B"}, {"switch", "-c"}, {"switch", "-C"})


def without_heredoc_bodies(command: str) -> str:
    kept: list[str] = []
    delimiter: str | None = None
    for line in command.splitlines():
        if delimiter is not None:
            if line.strip() == delimiter:
                delimiter = None
            continue
        kept.append(line)
        if match := HEREDOC.search(line):
            delimiter = match.group(2)
    return "\n".join(kept)


def _commands(command: str) -> list[list[str] | str]:
    """Simple commands as their words, with `(` and `)` kept as markers of a subshell."""
    lexer = shlex.shlex(without_heredoc_bodies(command), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r\n"
    result: list[list[str] | str] = []
    current: list[str] = []
    try:
        for token in lexer:
            if token in OPERATORS:
                result.append(current)
                if token in ("(", ")"):
                    result.append(token)
                current = []
            else:
                current.append(token)
        result.append(current)
    except ValueError:
        # Unbalanced quotes: fall back to plain words rather than let the command through.
        return [without_heredoc_bodies(command).split()]
    return [item for item in result if item]


def segments(command: str) -> list[list[str]]:
    """Simple commands, each as its words; `cd x &&` and environment assignments are kept."""
    return [item for item in _commands(command) if isinstance(item, list)]


# The flags gh takes before its group with a value, as the next word: `-R` and `--repo`, which
# every group inherits and gh 2.96 also reads before it. Its root has no other (`--help` and
# `--version` take none). The forms `--repo=o/r` and `-Ro/r` are one word.
GH_OPTIONS_WITH_VALUE = frozenset({"-R", "--repo"})


def _skip_options(words: list[str], index: int) -> int:
    while index < len(words) and words[index].startswith("-"):
        index += 2 if words[index] in GH_OPTIONS_WITH_VALUE else 1
    return index


def gh_command(words: list[str]) -> list[str] | None:
    """The words of a gh call from its group on, or None when the command is not gh.

    Environment assignments and gh's global flags are skipped: `gh -R o/r pr merge 5` and
    `gh --repo=o/r issue close 3` are a merge and a close, which both hooks read from the
    third word as a group `-R` and let by.
    """
    while words and "=" in words[0] and not words[0].startswith("-"):
        words = words[1:]
    if not words or words[0] != "gh":
        return None
    return words[_skip_options(words, 1) :]


def gh_act(words: list[str]) -> tuple[str, str, list[str]] | None:
    """`(group, verb, words after the verb)` of a gh call: `gh pr -R o/r merge 5` is a merge."""
    command = gh_command(words)
    if not command:
        return None
    index = _skip_options(command, 1)
    return (command[0], command[index], command[index + 1 :]) if index < len(command) else None


def _targets_main(ref: str) -> bool:
    destination = ref.lstrip("+").rsplit(":", 1)[-1]
    return destination in ("main", "refs/heads/main")


def _pushes_to_main(args: list[str], branch: str) -> bool:
    if "--all" in args or "--mirror" in args:  # every branch, main included
        return True
    refs = [arg for arg in args if not arg.startswith("-")]
    if len(refs) <= 1:  # `git push` or `git push origin`: the current branch
        return branch == "main"
    return any(_targets_main(ref) for ref in refs[1:]) or (
        any(ref.lstrip("+") == "HEAD" for ref in refs[1:]) and branch == "main"
    )


def _forces(args: list[str]) -> bool:
    """`--force`, `-f` alone or among short flags (`-fu`), or a `+refspec`."""
    if "--force" in args:
        return True
    if any(arg.startswith("-") and not arg.startswith("--") and "f" in arg[1:] for arg in args):
        return True
    refs = [arg for arg in args if not arg.startswith("-")]
    return any(ref.startswith("+") for ref in refs[1:])


# Git's global options that take their value as the next word, per git 2.54's `git(1)`.
# A word starting with `-` before the subcommand that is not listed here is taken as a flag or an
# `--option=value` form (`--no-pager`, `--git-dir=...`, `-P`).
GLOBAL_OPTIONS_WITH_VALUE = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--attr-source"}
)


def _subcommand_and_args(args: list[str]) -> list[str]:
    """The words from the subcommand on: `git -C <wt> reset --hard` is still a reset --hard."""
    index = 0
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in GLOBAL_OPTIONS_WITH_VALUE else 1
    return args[index:]


# A directory the hook cannot know (after `cd -`, `cd ~`, `cd "$VAR"`). It stays unknown under
# every relative `cd` or `-C` that follows, and only an absolute path leaves it: joining a
# relative path to the event's directory instead would judge a directory git never acts on.
UNKNOWN = "\0unknown"


def _moved(directory: str | None, target: str) -> str | None:
    """The directory after `cd target` or `-C target` from `directory`.

    Shell arithmetic, so POSIX paths whatever the host: under Windows, `Path` would take
    `/work/repo` for a relative path (it has no drive) and join with backslashes. A Windows
    absolute path (`C:/work`) is absolute too, since Git Bash accepts it.
    """
    if target == "-" or target.startswith("~") or "$" in target:
        return UNKNOWN
    if PurePosixPath(target).is_absolute() or PureWindowsPath(target).is_absolute():
        return target
    if directory == UNKNOWN:
        return UNKNOWN
    return str(PurePosixPath(directory or ".") / target)


# A Git Bash drive root: `/c/Users/...` is `c:/Users/...` to a native Windows process.
_GIT_BASH_DRIVE = re.compile(r"^/([A-Za-z])(?=/|$)/?")


def native_directory(directory: str | None, platform: str = sys.platform) -> str | None:
    """`directory` as the host opens it: a Git Bash drive path translated under Windows.

    Without it, `cd /c/.../a-main-checkout && git commit` could not be read under Windows, and was
    judged as the event's directory: from a feature branch, a commit on main went through. Any
    other root (`/srv`) is left alone; it stays unreadable and falls back to the event's cwd.
    """
    if directory is None or platform != "win32":
        return directory
    return _GIT_BASH_DRIVE.sub(lambda drive: f"{drive.group(1)}:/", directory, count=1)


def _directory_of(args: list[str], cwd: str | None) -> str | None:
    """Where git acts: each `-C <dir>` before the subcommand applies relative to the last."""
    directory = cwd
    index = 0
    while index < len(args) and args[index].startswith("-"):
        if args[index] == "-C" and index + 1 < len(args):
            directory = _moved(directory, args[index + 1])
        index += 2 if args[index] in GLOBAL_OPTIONS_WITH_VALUE else 1
    return directory


def _git_refusal(args: list[str], branch: str, switched: bool) -> str | None:
    args = _subcommand_and_args(args)
    if not args:
        return None
    sub, rest = args[0], args[1:]
    if "--no-verify" in rest:
        return "--no-verify skips the repository hooks"
    if sub == "commit" and branch == "main" and not switched:
        return "commit on main: create a branch for the ticket first"
    if sub == "push":
        if _forces(rest):
            return "force push: use --force-with-lease on your own feature branch"
        if _pushes_to_main(rest, branch):
            return "push to main: open a pull request instead"
    if sub == "branch" and _deletes_by_force(rest):
        return "forced branch deletion: use `git branch -d`, which refuses an unmerged branch"
    if sub == "reset" and "--hard" in rest:
        return "reset --hard discards work: use `git stash` or a new branch"
    if sub == "clean" and any(arg.startswith("-") and "f" in arg for arg in rest):
        return "clean -f deletes untracked files for good"
    return None


def _deletes_by_force(args: list[str]) -> bool:
    """`-D`, `-df`/`-fd`, or `--delete` with `--force`/`-f`."""
    short = "".join(arg[1:] for arg in args if arg.startswith("-") and not arg.startswith("--"))
    deletes = "D" in short or "d" in short or "--delete" in args
    forced = "D" in short or "f" in short or "--force" in args
    return deletes and forced


# GitHub closes the issue that follows one of these words in a merged commit message or in the
# description of a merged PR, wherever it stands, with or without a colon, and in the
# `owner/repo#n` form too.
CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s+(?:[\w.-]+/[\w.-]+)?#(\d+)", re.IGNORECASE
)
REFS = re.compile(r"\brefs\b:?\s*(#\d+(?:\s*,\s*#\d+)*)", re.IGNORECASE)
MERGE_TEXT_OPTIONS = frozenset({"--subject", "-t", "--body", "-b"})
MERGE_FILE_OPTIONS = frozenset({"--body-file", "-F"})


def closed_despite_refs(message: str) -> tuple[str, str] | None:
    """The ticket cited with `Refs` and closed anyway, with the phrase that closes it."""
    cited = {number for group in REFS.findall(message) for number in re.findall(r"\d+", group)}
    for match in CLOSING.finditer(message):
        if match.group(1) in cited:
            return match.group(1), match.group(0)
    return None


def _merge_message(
    args: list[str], here: str | None, read_text: Callable[[str], str | None]
) -> str:
    """Subject and body of `gh pr merge` as GitHub reads them; an unreadable file adds nothing."""
    parts: list[str] = []
    index = 0
    while index < len(args):
        name, equals, value = args[index].partition("=")
        if name in MERGE_TEXT_OPTIONS or name in MERGE_FILE_OPTIONS:
            if not equals:
                index += 1
                value = args[index] if index < len(args) else ""
            if name in MERGE_TEXT_OPTIONS:
                parts.append(value)
            elif value and value != "-":
                path = _moved(here, value)
                text = read_text(path) if path is not None and path != UNKNOWN else None
                parts.append(text or "")
        index += 1
    return "\n".join(parts)


def read_text_or_none(path: str) -> str | None:
    """The file's text, or None when it cannot be read: gh reports a missing file itself."""
    try:
        return Path(native_directory(path) or path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None


# The gestures that belong to the owner of the repository, which no agent makes: a human does,
# and the agent lists them at the end of its report. `(group, verb)` of a gh call.
OWNER_GH_GESTURES = frozenset(
    {("secret", "set"), ("secret", "delete"), ("secret", "remove")}
    | {("variable", "set"), ("variable", "delete"), ("variable", "remove")}
    | {("repo", "delete"), ("repo", "rename"), ("repo", "archive")}
    | {("repo", "deploy-key")}
)


def _gh_gesture(words: list[str]) -> str | None:
    """The owner gesture of a gh call, named as the agent typed it, or None."""
    act = gh_act(words)
    if act is None:
        return None
    group, verb, rest = act
    if (group, verb) == ("repo", "deploy-key"):
        action = next((word for word in rest if not word.startswith("-")), "")
        return f"gh repo deploy-key {action}" if action in ("add", "delete") else None
    if (group, verb) in OWNER_GH_GESTURES:
        return f"gh {group} {verb}"
    if (group, verb) == ("repo", "edit") and any(
        word == "--visibility" or word.startswith("--visibility=") for word in rest
    ):
        return "gh repo edit --visibility"
    return None


def owner_gesture(words: list[str]) -> str | None:
    """The owner gesture a simple command makes, named for the refusal, or None."""
    return _gh_gesture(words)


def _owner_refusal(gesture: str) -> str:
    return f"{gesture} : geste du propriétaire du dépôt, à lister pour l'humain en fin de compte rendu"


def refusal(
    command: str,
    branch: str | Callable[[str | None], str],
    checks_green: Callable[[str | None], bool],
    cwd: str | None = None,
    read_text: Callable[[str], str | None] = read_text_or_none,
    description: Callable[[str | None], str] = lambda _pr: "",
) -> str | None:
    """Why the command is refused, or None when it may run.

    `branch` is the branch of a directory: a callable is asked about the directory each git
    command acts on (after `cd` and `-C`); a string is that branch wherever git runs.
    `description` is the body of a PR, by its number (None for the current branch's PR).
    """
    branch_of = branch if callable(branch) else (lambda _directory: branch)

    def branch_where(directory: str | None) -> str:
        # A directory whose branch cannot be read (an unexpanded `~` or `$VAR`, `cd -`, a path
        # that does not exist) is judged as the event's own: never as "no branch", which would
        # let a commit on main through.
        if directory == UNKNOWN:
            return branch_of(cwd)
        return branch_of(directory) or branch_of(cwd)

    switched = False
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
        if words[0] == "git":
            args = words[1:]
            if any(switch <= set(args) for switch in BRANCH_SWITCH):
                switched = True
            if reason := _git_refusal(args, branch_where(_directory_of(args, here)), switched):
                return reason
        if gesture := owner_gesture(words):
            return _owner_refusal(gesture)
        act = gh_act(words)
        if act is not None and act[:2] == ("pr", "merge"):
            rest = act[2]
            number = next((word for word in rest if not word.startswith("-")), None)
            message = _merge_message(rest, here, read_text) + "\n" + description(number)
            if closed := closed_despite_refs(message):
                ticket, phrase = closed
                return (
                    f"the merge message or PR description cites #{ticket} with Refs and closes it"
                    f" (`{phrase}`): the first PR of a split ticket must leave it open"
                )
            if not checks_green(number):
                return "merge with checks not green: wait for every check, `gh pr checks`"
    return None


def _run(argv: list[str], cwd: str | None) -> subprocess.CompletedProcess[str] | None:
    """The finished process, or None when it did not finish within the timeout."""
    try:
        # Fixed argv resolved by shutil.which: git or gh, and arguments built here. Both print
        # UTF-8 whatever the console's code page; a byte that is not, replaced, still leaves text.
        return subprocess.run(  # noqa: S603
            argv,
            cwd=cwd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def current_branch(cwd: str | None) -> str:
    """The branch checked out in `cwd`; empty when unknown (no git, a timeout, not a repo)."""
    git = shutil.which("git")
    completed = (
        _run([git, "rev-parse", "--abbrev-ref", "HEAD"], native_directory(cwd)) if git else None
    )
    return completed.stdout.strip() if completed is not None else ""


def checks_green_via_gh(cwd: str | None) -> Callable[[str | None], bool]:
    def green(pr: str | None) -> bool:
        gh = shutil.which("gh")
        if gh is None:
            return False
        completed = _run([gh, "pr", "checks", *([pr] if pr else [])], cwd)
        # A timeout is not green: the merge waits rather than going through unchecked.
        return completed is not None and completed.returncode == 0

    return green


def description_via_gh(cwd: str | None) -> Callable[[str | None], str]:
    def body(pr: str | None) -> str:
        gh = shutil.which("gh")
        completed = (
            _run([gh, "pr", "view", *([pr] if pr else []), "--json", "body", "--jq", ".body"], cwd)
            if gh
            else None
        )
        # A description that cannot be read adds nothing, like an unreadable body file: without
        # gh the checks are not green anyway, and a timeout here must not block every merge.
        if completed is None or completed.returncode != 0:
            return ""
        return completed.stdout

    return body


def main() -> int:
    event = json.load(sys.stdin)
    command = str(event.get("tool_input", {}).get("command", ""))
    cwd = event.get("cwd")
    if "git" not in command and "gh" not in command:
        return 0
    reason = refusal(
        command, current_branch, checks_green_via_gh(cwd), cwd, description=description_via_gh(cwd)
    )
    if reason is None:
        return 0
    sys.stderr.write(f"Blocked by the forge plugin (guard_git): {reason}.\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
