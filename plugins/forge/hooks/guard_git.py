"""PreToolUse hook: the git and GitHub commands an agent may not run.

Refused, with the reason on stderr and exit code 2 so Claude Code blocks the call:

- a commit on `main`, a push to `main`, any `--force` push (`--force-with-lease` on a feature
  branch stays allowed: restacking a PR after its base merged needs it);
- `git branch -D`, `git reset --hard`, `git clean -f`, and `--no-verify`, which skips the hooks;
- `gh pr merge` while any check of the PR is not green;
- `gh pr merge`, for every agent whatever its name, while a `human-merge` line of the project's
  `budget-action` key is active (its SLO was exhausted in `slo-status.json` and is not back to `tenu`), and, closed by
  default, when that key is declared but the state file is absent, unreadable or over 24 h old
  (the refusal gives the command that recalculates it); see `budget.py`;
- `gh pr merge` whose message or PR description closes a ticket it cites with `Refs`: the first
  PR of a split ticket must leave it open, and GitHub reads a closing keyword anywhere, prose
  included, in the squash message as in the description. The message is read from `--subject`,
  `--body` and `--body-file`, the description from `gh pr view`; a body built by a shell
  substitution cannot be read here, which is why `/forge:qc` writes it to a file;
- `gh pr merge`, for every agent whatever its name, when a file of the PR's diff starts with a
  line of the project's `protected-path` key (a path or a prefix, compared word for word on the
  POSIX path): the merge is the human's. The files come from `gh pr view --json files`, under
  the timeout of the other calls. Closed by default: once the key is declared, a list that
  cannot be read, or a `gh` that fails or times out, refuses the merge too. Without the key the
  guard refuses nothing on that account and reads nothing. `/forge:qc` keeps its own rule, which
  stops before the merge: the guard is the net, the rule avoids the refusal.

The command is parsed, not grepped: a commit message that says "push --force" is data. Heredoc
bodies are dropped first, then the command is split on shell operators with `shlex`. A wrapper
hides no refusal: assignments, `env`, `sudo`, `command`, `timeout`, `nice`, `nohup`, `xargs` and
the others `guard_infra` takes off are taken off, a path or `.exe` is read as its program
(`/usr/bin/gh`, `git.exe`), and the script of `sh -c` or of a shell reading a heredoc is judged
like the command itself. The human can always run the command himself.

The branch that matters is the one of the directory git acts on: `cd <dir> &&` and `git -C
<dir>` move it, so each command is judged against the branch checked out there.

Also refused, to every agent, are the gestures of the owner of the repository: a write by
`gh api` (any method but an explicit GET or HEAD) on collaborators, invitations, branch
protection, rulesets, runners, secrets, variables, Actions permissions, keys, webhooks,
environments, a transfer or the repository itself; the GraphQL mutations of protection, rulesets,
collaborators and the repository (the sub-issue mutations the plugin uses are not among them),
read in the arguments, in the heredocs of the command and in the files `--input` and `-F
query=@file` name, a form aimed at `graphql` that cannot be read being refused as a precaution;
`gh secret` and `gh variable` `set` and `delete`; `gh repo` `delete`, `rename`, `archive`, `edit
--visibility` and `deploy-key add` and `delete`; the runner scripts `config.sh`, `config.cmd` and
`svc.sh`, only in a runner's folder or with a runner's argument, also behind `sudo`, `env`,
`nohup`, `bash`, `sh`, `cmd /c` and a heredoc fed to a shell. A reading is always allowed. The
refusal names the gesture and says it is the human's, to list at the end of the report. A project
adds its own with the `owner-gesture` key of `docs/agents/usine.md`, one `<command prefix> |
<reason>` per line; the built-in list holds without it. This replaces the earlier choice to leave
every owner gesture to the project's own hooks.

Also refused, to every agent, is the merge of a PR whose diff touches the infra guard
(`plugins/forge/hooks/guard_infra.py`, its tests, this file or `hooks.json`, which runs the guard):
`gh pr merge`, a REST merge by `gh api` (its files read by `gh pr view <n> -R <repo> --json
files`, a reading that fails refusing too) and any GraphQL merge mutation, whose node id the guard
does not look up. Only the owner merges it, by hand.

A merge runs alone: `guard_git` judges it only as `[cd <path> &&] [GH_REPO=owner/repo] gh pr
merge <n> [options] [| tee <file> | cat]` (or the same `gh api` merge), with a literal number,
`-R`, `GH_REPO` and `cd` path, the options of `gh pr merge` one by one, and a variable only in
double quotes in the value of `--body-file`, `--body`, `--subject` or `--match-head-commit`, or in
a file of `tee`. Any
other form is refused ("run the merge alone"): only there do the checks, the description and the
files read the PR the merge acts on. `cd x; gh pr merge` is refused: if the `cd` fails, the merge
runs in the first directory. A merge counts wherever the guard sees it: behind a wrapper, in
`sh -c` or `eval`, behind a gh alias, or among another program's arguments. A program the shell
names (a variable, a `$(...)` or a backtick, quoted or not, behind assignments and wrappers, at any
depth of substitution) counts as a merge whenever a word of the command, substitutions included and
quoted values split on their blanks, is `merge`, `api`, `graphql` or a path ending in `/merge`:
`$(echo gh) pr merge 5` and `G='gh pr merge'; $G 5` are refused as not run alone. One that names
none (`$(printf 'gh pr mer%s' ge) 5`, a `$G` set in an earlier call) is not seen here;
`guard_infra` holds every program the shell names, refused to a subagent and asked in the main
session. A gh call that names no gh command is read through `gh alias list` when it
runs alone (a literal `cd` aside), and counts as a merge beside anything else; `gh alias set`,
`import` and `delete` are refused to a subagent.

Known limits:

- a `gh api` write with a variable in its endpoint escapes the owner gestures
  (`gh api --method PUT repos/$R/collaborators/x`);
- `OWNER_ENDPOINT` does not cover the full URL `https://api.github.com/repos/...`;
- extended globs (`extglob`) are not handled;
- a merge run by a file (a script, a program that calls gh or the API itself, a gh extension) or
  by a program that runs gh from one argument string (`script -c "gh pr merge 5"`) escapes it.
"""

from __future__ import annotations

import fnmatch
import json
import os
import posixpath
import re
import shlex
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import NamedTuple

from budget import merge_refusal, state_path
from usine import load, project_root, split_value

# The project's own owner gestures, one per line: `<command prefix> | <reason>`.
OWNER_KEY = "owner-gesture"
# The paths and prefixes no agent merges, one per line.
PROTECTED_KEY = "protected-path"

# Every external call has a timeout: a hook that hangs blocks the agent's command.
TIMEOUT_SECONDS = 20

# `<<<` is a here-string, which has no body: only a `<<` that is neither preceded nor followed by `<`.
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)(\w+)\1")
OPERATORS = {";", "&&", "||", "|", "&", "(", ")"}
BRANCH_SWITCH = ({"checkout", "-b"}, {"checkout", "-B"}, {"switch", "-c"}, {"switch", "-C"})


def split_heredocs(command: str) -> tuple[str, str]:
    """The command without its heredoc bodies, and those bodies, one after the other."""
    kept: list[str] = []
    bodies: list[str] = []
    delimiter: str | None = None
    for line in command.splitlines():
        if delimiter is not None:
            if line.strip() == delimiter:
                delimiter = None
            else:
                bodies.append(line)
            continue
        kept.append(line)
        if match := HEREDOC.search(line):
            delimiter = match.group(2)
    return "\n".join(kept), "\n".join(bodies)


def without_heredoc_bodies(command: str) -> str:
    return split_heredocs(command)[0]


# shlex hands over a quoted `'&'` and a bare `&` as the same token. The shell characters are
# swapped for private-use ones where they are quoted or escaped, then swapped back in each word:
# `-H '|'` is the value of an option, not a pipe.
_SHELL_CHARACTERS = ";&|()<>"
_MASK = str.maketrans({char: chr(0xE000 + index) for index, char in enumerate(_SHELL_CHARACTERS)})
_UNMASK = str.maketrans({chr(0xE000 + index): char for index, char in enumerate(_SHELL_CHARACTERS)})


def _mask_quoted(text: str) -> str:
    """`text` with the shell characters that are quoted or escaped replaced by private-use ones."""
    out: list[str] = []
    quote = ""
    index = 0
    while index < len(text):
        char = text[index]
        if quote == "'":
            quote = "" if char == "'" else quote
            out.append(char if char == "'" else char.translate(_MASK))
        elif char == "\\" and text[index + 1 : index + 2] == "\n" and quote != "'":
            index += 1  # a line continuation joins the lines: it is no separator
        elif char == "\n" and not quote:
            out.append(" ; ")  # a newline outside quotes ends a command, like `;`
        elif char == "\\" and index + 1 < len(text):
            index += 1
            following = text[index]
            masked = following.translate(_MASK)
            if quote == '"' or masked == following:
                out.append(char)  # shlex keeps the backslash in double quotes, and before a letter
            out.append(masked)
        elif quote == '"':
            quote = "" if char == '"' else quote
            out.append(char if char == '"' else char.translate(_MASK))
        else:
            quote = char if char in "'\"" else ""
            out.append(char)
        index += 1
    return "".join(out)


def _commands(command: str) -> list[list[str] | str]:
    """Simple commands as their words, with `(` and `)` kept as markers of a subshell."""
    lexer = shlex.shlex(_mask_quoted(without_heredoc_bodies(command)), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r\n"
    result: list[list[str] | str] = []
    current: list[str] = []
    try:
        for token in lexer:
            # shlex glues operators that follow each other (`);`, `)&&`): they are taken apart.
            glued = set(token) <= set(";&|()") and token not in OPERATORS
            for part in re.findall(r"&&|\|\||[;&|()]", token) if glued else [token]:
                if part in OPERATORS:
                    result.append(current)
                    if part in ("(", ")"):
                        result.append(part)
                    current = []
                else:
                    current.append(part.translate(_UNMASK))
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
                reads = path is not None and path != UNKNOWN and device_path_kind(path, here) is None
                parts.append((read_text(path) if path is not None and reads else None) or "")
        index += 1
    return "\n".join(parts)


# The most a file read for its text may weigh: a query or a message is far smaller.
READ_CAP = 1024 * 1024


_STANDARD_INPUT = re.compile(r"^/(?:dev/(?:stdin|fd/0)|proc/(?:self|thread-self|\d+)(?:/task/\d+)?/fd/0)$")
_MOST_LINKS = 40


def device_path_kind(path: str, here: str | None = None) -> str | None:
    """`"stdin"`, `"other"` or None: what a path names once written out in full.

    `"stdin"` is a spelling of the descriptor 0 (`/dev/stdin`, `/dev/fd/0`, `/proc/self/fd/0`,
    `/proc/<pid>/fd/0`), which the guard has read already as the input of the command. `"other"`
    is anything else under `/dev/` or `/proc/` (`/dev/fd/3`, `/dev/tty`, `/dev/zero`): it is never
    opened, because it is not the standard input and a device never ends or blocks. None is a path
    elsewhere. The path is made absolute from `here` (or the working directory), normalised
    (`//`, `/./`, `..`) and its symbolic links followed one component at a time, up to the
    entry in `/dev` or `/proc`, which the guard never looks into.
    """
    text = path.replace("\\", "/")
    if not text.startswith("/") and here not in (None, UNKNOWN):
        text = posixpath.join(str(here).replace("\\", "/"), text)
    if not text.startswith("/"):
        try:
            text = posixpath.join(os.getcwd().replace("\\", "/"), text)
        except OSError:
            return "other"  # a directory that cannot be told: not a path to open
    pending = [part for part in reversed(text.split("/")) if part]
    resolved = "/"
    links = 0
    while pending:
        part = pending.pop()
        if part == ".":
            continue
        if part == "..":
            resolved = posixpath.dirname(resolved)
            continue
        candidate = posixpath.join(resolved, part)
        if candidate in ("/dev", "/proc"):
            rest = list(reversed(pending))
            final = posixpath.normpath("/".join([candidate, *rest]))
            if _STANDARD_INPUT.match(final):
                return "stdin"
            return "other"  # under /dev or /proc, or out of it through `..`: never opened
        try:
            is_link = os.path.islink(candidate)
        except (OSError, ValueError):
            return "other"
        if is_link:
            links += 1
            try:
                target = os.readlink(candidate).replace("\\", "/")
            except (OSError, ValueError):
                return "other"
            if links > _MOST_LINKS:
                return "other"
            if target.startswith("/"):
                resolved = "/"
            pending.extend(part for part in reversed(target.split("/")) if part)
        else:
            resolved = candidate
    return None


def is_standard_input_path(path: str, here: str | None = None) -> bool:
    """Whether `path` is a spelling of the standard input (the descriptor 0), nothing else."""
    return device_path_kind(path, here) == "stdin"


def read_text_or_none(path: str) -> str | None:
    """The text of an ordinary file of at most `READ_CAP` bytes, or None.

    None when it cannot be read: gh reports a missing file itself. A device, a FIFO, a directory
    and a file over the cap are not read, and the open never waits: `stat` rules first.
    """
    try:
        target = Path(native_directory(path) or path)
        if device_path_kind(str(target)) is not None or not stat.S_ISREG(target.stat().st_mode):
            return None
        with target.open("rb") as stream:
            data = stream.read(READ_CAP + 1)
        return None if len(data) > READ_CAP else data.decode("utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None


# The options of `gh api` as pflag, the library gh parses with, reads them. The ones that take a
# value consume the next word whatever it looks like (`--jq -XGET` is a filter, not a method), and
# a short one takes the rest of its word (`-XGET`, `-X=GET`, `-iXGET`). The other ones are flags.
API_LONG_VALUE_OPTIONS = {
    "method": "method",
    "header": "header",
    "raw-field": "raw-field",
    "field": "field",
    "input": "input",
    "jq": "jq",
    "template": "template",
    "cache": "cache",
    "hostname": "hostname",
    "preview": "preview",
}
API_SHORT_VALUE_OPTIONS = {
    "X": "method",
    "H": "header",
    "f": "raw-field",
    "F": "field",
    "q": "jq",
    "t": "template",
    "p": "preview",
}
# What makes gh send a body, or fields: a POST unless `-X` says otherwise.
API_BODY_OPTIONS = frozenset({"raw-field", "field", "input"})
# A redirection operator, which takes the next word as its target: `>`, `2>&1`'s `>&`, `<<`, `<<<`.
REDIRECTION = re.compile(r"^[<>&]+$")


class ApiCall(NamedTuple):
    """A `gh api` call as gh reads it: its method, its endpoint and its body options in order."""

    method: str | None  # the last `-X` or `--method`; None when there is none
    endpoint: str
    options: list[tuple[str, str]]  # `(name, value)` of each field and `--input`, as typed


# More operator-like words than this in a `gh api` call and the guard refuses: each one doubles or
# triples the readings to judge.
MOST_OPERATOR_WORDS = 5
Reading = tuple[list[str], list[tuple[str, str]]]


def _awaits_value(word: str) -> bool:
    """Whether `word` is an option of `gh api` that takes the next word as its value."""
    if word.startswith("--"):
        return "=" not in word and word[2:] in API_LONG_VALUE_OPTIONS
    if word.startswith("-") and len(word) > 1:
        for position, letter in enumerate(word[1:], start=1):
            if letter in API_SHORT_VALUE_OPTIONS:
                return position == len(word) - 1
    return False


def api_readings(words: list[str]) -> list[Reading] | None:
    """Every way the shell may have split `words` into arguments and redirections, or None.

    shlex hands over `'>'` and `>` alike, and `1 >` as it does `1>`: a word made of `<`, `>` or
    `&` is a redirection (which takes the next word as its target, and a bare number before it as
    its descriptor) or the value of an option (`-t '>'`, `-q 1 > out`): that is a reading only
    after an option that awaits a value. The words cannot tell, so a reading is made of each
    choice, as `(arguments, [(operator, target)])`. The caller judges them all and refuses when
    one refuses. None when there are too many to judge.
    """
    if sum(1 for word in words if REDIRECTION.match(word)) > MOST_OPERATOR_WORDS:
        return None
    readings: list[Reading] = []

    def walk(index: int, kept: list[str], redirections: list[tuple[str, str]]) -> None:
        if index >= len(words):
            readings.append((kept, redirections))
            return
        word = words[index]
        if not REDIRECTION.match(word) or (kept and _awaits_value(kept[-1])):
            walk(index + 1, [*kept, word], redirections)  # an argument, or the value of an option
        if REDIRECTION.match(word):
            target = words[index + 1] if index + 1 < len(words) else ""
            redirected = [*redirections, (word, target)]
            walk(index + 2, kept, redirected)
            if kept and kept[-1].isdigit():  # `2>/dev/null`: the number is the descriptor
                walk(index + 2, kept[:-1], redirected)

    walk(0, [], [])
    return readings


def parse_api(words: list[str]) -> ApiCall:
    """Split the arguments of `gh api` (redirections removed) the way gh does.

    The one place that knows its options.
    """
    method: str | None = None
    endpoint: str | None = None
    options: list[tuple[str, str]] = []

    def take(name: str, value: str) -> None:
        nonlocal method
        if name == "method":
            method = value
        elif name in API_BODY_OPTIONS:
            options.append((name, value))

    index = 0
    while index < len(words):
        word = words[index]
        index += 1
        if word == "--":
            endpoint = endpoint if endpoint is not None else (words[index] if index < len(words) else "")
            break
        if word.startswith("--"):
            name, equals, value = word[2:].partition("=")
            if name in API_LONG_VALUE_OPTIONS:
                if not equals:
                    value = words[index] if index < len(words) else ""
                    index += 1
                take(API_LONG_VALUE_OPTIONS[name], value)
        elif word.startswith("-") and len(word) > 1:
            position = 1
            while position < len(word):
                letter = word[position]
                position += 1
                if letter not in API_SHORT_VALUE_OPTIONS:
                    continue
                rest = word[position:]
                if rest.startswith("=") and len(rest) > 1:
                    value = rest[1:]
                elif rest:
                    value = rest
                else:
                    value = words[index] if index < len(words) else ""
                    index += 1
                take(API_SHORT_VALUE_OPTIONS[letter], value)
                break
        elif endpoint is None:
            endpoint = word
    return ApiCall(method, endpoint or "", options)


def _gh_api_reads(args: list[str]) -> bool:
    """A `gh api` call that is a read in every reading of its words (see `api_readings`)."""
    readings = api_readings(args)
    return readings is not None and all(_reads(words) for words, _ in readings)


def _reads(words: list[str]) -> bool:
    """An explicit GET or HEAD, or no method, field or `--input`.

    An explicit `-X GET` keeps its fields as query parameters, so it is a read with `-f` too;
    without a method, a field or a body makes gh send a POST.
    """
    call = parse_api(words)
    if call.method is not None:
        return call.method.upper() in ("GET", "HEAD")
    return not call.options


# What follows `repos/<owner>/<repo>/` or `orgs/<org>/` that belongs to the owner: a write there
# is a human's. Anchored at the start, so a file named `hooks` under `contents/` is not one.
OWNER_ENDPOINT = re.compile(
    r"(?:collaborators|invitations|rulesets|hooks|keys|environments|transfer"
    r"|branches/.+/protection|actions/(?:runners|secrets|variables|permissions)"
    r"|dependabot/secrets)(?:/|$)"
)
OWNER_SCOPE = re.compile(r"^(?:repos/[^/]+/[^/]+|orgs/[^/]+)(?:/(.*))?$")
# GraphQL mutations that change protection, rulesets, collaborators or the repository itself. The
# sub-issue mutations the plugin uses (`addSubIssue`...) are not among them.
OWNER_MUTATION = re.compile(
    r"\b(?:(?:create|update|delete)(?:BranchProtectionRule|RepositoryRuleset)"
    r"|(?:update|delete|archive|unarchive|transfer)Repository"
    r"|\w*(?:add|remove|update|invite|create|delete)\w*Collaborator\w*)\b",
    re.IGNORECASE,
)


def _api_method(words: list[str]) -> str:
    method = parse_api(words).method
    return method.upper() if method is not None else "POST"


GRAPHQL_MUTATION_GESTURE = (
    "gh api graphql (mutation de protection, de ruleset, de collaborateur ou du dépôt)"
)
_VARIABLE = re.compile(r"\$\{?\w+\}?")


def _graphql_inputs(words: list[str]) -> list[tuple[str, str]]:
    """What a `gh api graphql` call is fed: `(kind, value)` per `--input` and per field.

    The kind is `input` for `--input <value>` and `query` for a field named `query`; the value of
    any other field cannot hold the query, except `name=@file`, which reads one.
    """
    inputs: list[tuple[str, str]] = []
    for name, value in parse_api(words).options:
        if name == "input":
            if value:  # `--input` with nothing after it: gh fails, it opens nothing
                inputs.append(("input", value))
            continue
        key, _, content = value.partition("=")
        if content.startswith("@"):
            inputs.append(("file", content[1:]))
        elif key == "query":
            inputs.append(("query", content))
    return inputs


def _standard_input_text(
    redirections: list[tuple[str, str]], here: str | None, bodies: str, read_text: Callable[[str], str | None]
) -> str | None:
    """What the shell feeds to the standard input of this very command, or None when unknown.

    Its own redirection counts, the last one as the shell applies it: a file (`< q.json`) is read,
    a heredoc (`<<EOF`) is the bodies of the command. A heredoc of another command, a pipe and a
    here-string (`<<<`) are not known.
    """
    last = next(
        (item for item in reversed(redirections) if item[0] in ("<", "<<", "<<-")),
        None,
    )
    if last is None:
        return None
    operator, target = last
    if operator == "<":
        path = _moved(here, target)
        if path is None or path == UNKNOWN or device_path_kind(path, here) is not None:
            return None
        return read_text(path)
    return bodies or None


def _graphql_texts(
    args: list[str],
    words: list[str],
    redirections: list[tuple[str, str]],
    here: str | None,
    bodies: str,
    read_text: Callable[[str], str | None],
) -> tuple[list[str], str]:
    """`(texts, unread)` of a `gh api graphql` call: what its query is made of, and what is not read.

    The query is read in the arguments, in the heredocs of the command (`--input - <<EOF`, or
    `query="$(cat <<EOF ...)"`) and in the files it names. `unread` says what cannot be read (a
    file that is not there, stdin from a pipe, a substitution or a variable), empty when all is.
    """
    texts = [" ".join(args)]
    unread = ""
    for kind, value in _graphql_inputs(words):
        if kind == "query" and not (
            "`" in value or "$(" in value or _VARIABLE.fullmatch(value.strip())
        ):
            continue
        if kind == "query" and "<<" in value and bodies:
            texts.append(bodies)  # `$(cat <<EOF ...)`: the heredoc of this command
        elif kind == "query":
            unread = unread or "la requête vient d'une substitution ou d'une variable du shell"
        elif value != "-" and device_path_kind(value, here) == "other":
            unread = unread or f"le chemin `{value}` est un descripteur ou un périphérique, qui ne s'ouvre pas"
        elif value == "-" or is_standard_input_path(value, here):
            text = _standard_input_text(redirections, here, bodies, read_text)
            if text is None:
                unread = unread or "la requête vient de l'entrée standard"
            else:
                texts.append(text)
        else:
            path = _moved(here, value)
            text = read_text(path) if path is not None and path != UNKNOWN else None
            if text is None:
                unread = unread or f"le fichier `{value}` ne peut pas être lu"
            else:
                texts.append(text)
    return texts, unread


def _graphql_gesture(
    args: list[str],
    words: list[str],
    redirections: list[tuple[str, str]],
    here: str | None,
    bodies: str,
    read_text: Callable[[str], str | None],
) -> str | None:
    """The owner gesture of a `gh api graphql` call: a mutation of the owner, read wherever it is.

    What cannot be read is refused as a precaution: a mutation of the owner could hide in it, and a
    guard that fails closed.
    """
    texts, unread = _graphql_texts(args, words, redirections, here, bodies, read_text)
    if OWNER_MUTATION.search("\n".join(texts)):
        return GRAPHQL_MUTATION_GESTURE
    if unread:
        return f"gh api graphql ({unread} ; refusée par précaution, car une mutation du propriétaire pourrait s'y cacher)"
    return None


def _api_gesture(
    args: list[str],
    here: str | None = None,
    bodies: str = "",
    read_text: Callable[[str], str | None] = read_text_or_none,
) -> str | None:
    """The owner gesture of a `gh api` call (the words after `api`), or None.

    Judged in every reading of its words (see `api_readings`): the first that refuses wins.
    """
    readings = api_readings(args)
    if readings is None:
        return "gh api (trop de redirections pour être lues ; refusée par précaution)"
    for words, redirections in readings:
        gesture = _api_gesture_of(args, words, redirections, here, bodies, read_text)
        if gesture is not None:
            return gesture
    return None


def _api_gesture_of(
    args: list[str],
    words: list[str],
    redirections: list[tuple[str, str]],
    here: str | None,
    bodies: str,
    read_text: Callable[[str], str | None],
) -> str | None:
    endpoint = parse_api(words).endpoint.split("?", 1)[0].strip("/")
    if endpoint.lower() == "graphql":
        return _graphql_gesture(args, words, redirections, here, bodies, read_text)
    if _reads(words):
        return None
    scope = OWNER_SCOPE.match(endpoint)
    if scope is not None and (
        (scope.group(1) is None and endpoint.startswith("repos/"))
        or (scope.group(1) and OWNER_ENDPOINT.match(scope.group(1)))
    ):
        return f"gh api {_api_method(words)} {endpoint}"
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
        index = _skip_options(rest, 0)
        action = rest[index] if index < len(rest) else ""
        return f"gh repo deploy-key {action}" if action in ("add", "delete") else None
    if (group, verb) in OWNER_GH_GESTURES:
        return f"gh {group} {verb}"
    if (group, verb) == ("repo", "edit") and any(
        word == "--visibility" or word.startswith("--visibility=") for word in rest
    ):
        return "gh repo edit --visibility"
    return None


# The scripts of a self-hosted runner: `config` registers or removes it, `svc` installs and starts
# it as a service. The wrappers they are run behind, and the options of those that take a value.
RUNNER_SCRIPT = re.compile(r"(?:^|[/\\])(config\.(?:sh|cmd)|svc\.sh)$", re.IGNORECASE)
# shlex reads a backslash as an escape, so `.\config.cmd` and `C:\runner\config.cmd` reach the hook
# with their separators gone: a word that starts with `.` or a drive letter still names the script.
MANGLED_RUNNER_SCRIPT = re.compile(r"^(?:\.|[A-Za-z]:).*?(config\.(?:sh|cmd)|svc\.sh)$", re.IGNORECASE)
SHELLS = frozenset({"bash", "sh", "zsh", "dash"})
WRAPPERS = SHELLS | {"sudo", "env", "nohup", "cmd", "cmd.exe", "powershell", "pwsh"} | {
    "powershell.exe",
    "pwsh.exe",
}
# The letters of sudo's short options that take a value, alone (`-u runner`), joined to other
# letters (`-iu runner`) or followed by it (`-urunner`).
SUDO_VALUE_LETTERS = frozenset("ughpCDRTU")
ENV_OPTIONS_WITH_VALUE = frozenset({"-u", "-C", "-S", "--unset", "--chdir", "--split-string"})


def _option_width(wrapper: str, option: str) -> int:
    """How many words an option of a wrapper takes: itself, and its value when it is the next word."""
    if wrapper == "env":
        return 2 if option in ENV_OPTIONS_WITH_VALUE else 1
    if wrapper == "sudo" and not option.startswith("--"):
        for position, letter in enumerate(option[1:], start=1):
            if letter in SUDO_VALUE_LETTERS:
                return 2 if position == len(option) - 1 else 1
    return 1


def _skip_wrapper_options(wrapper: str, words: list[str], index: int) -> int:
    while index < len(words):
        word = words[index]
        if wrapper == "env" and "=" in word and not word.startswith("-"):
            index += 1  # an assignment `env` sets for the command
        elif word.startswith("-"):
            index += _option_width(wrapper, word)
        elif wrapper.startswith("cmd") and word.lower() == "/c":
            index += 1
        else:
            break
    return index


# What only a runner's script is called with, and the files that make a folder a runner's.
RUNNER_ARGUMENTS = frozenset(
    {"--url", "--token", "--pat", "--unattended", "install", "uninstall", "start", "stop", "remove"}
)
# The registration can also come from the environment: the runner reads `ACTIONS_RUNNER_INPUT_*`.
RUNNER_INPUT_VARIABLE = re.compile(r"^ACTIONS_RUNNER_INPUT_\w+=")
RUNNER_REGISTRATION_GESTURE = "ACTIONS_RUNNER_INPUT_* (enregistrement d'un runner par l'environnement)"
# The unpacked runner has a launcher and its listener: `.exe` is the Windows build's.
RUNNER_MARKERS = (("run.sh", "run.cmd"), ("bin/Runner.Listener", "bin/Runner.Listener.exe"))


def is_runner_directory(directory: str | None) -> bool:
    """Whether `directory` holds an unpacked runner: `run.sh` or `run.cmd`, and `bin/Runner.Listener`."""
    if directory is None or directory == UNKNOWN:
        return False
    try:
        base = Path(native_directory(directory) or directory)
        return all(any((base / name).exists() for name in names) for names in RUNNER_MARKERS)
    except (OSError, ValueError):
        return False


def _is_runner_call(word: str, arguments: list[str], here: str | None) -> bool:
    """A `config` or `svc` script that is a runner's: its folder, or an argument only a runner takes."""
    if any(argument.split("=", 1)[0] in RUNNER_ARGUMENTS for argument in arguments):
        return True
    folder = _moved(here, str(PurePosixPath(word.replace("\\", "/")).parent)) if "/" in word else here
    return is_runner_directory(folder)


def runner_registration_gesture(words: list[str]) -> str | None:
    """The refusal of a word that sets a registration variable of the runner, wherever it stands."""
    if any(RUNNER_INPUT_VARIABLE.match(word) for word in words):
        return RUNNER_REGISTRATION_GESTURE
    return None


def _runner_gesture(words: list[str], here: str | None = None, bodies: str = "") -> str | None:
    if gesture := runner_registration_gesture(words):
        return gesture
    index = 0
    while index < len(words):
        word = words[index]
        if word in WRAPPERS:
            if word in SHELLS and "-c" in words[index + 1 :]:
                position = words.index("-c", index + 1) + 1
                if position < len(words):
                    return _commands_gesture(words[position], here)
            index = _skip_wrapper_options(word, words, index + 1)
            if word in SHELLS and bodies and (index >= len(words) or words[index] in ("<<", "<<-")):
                return _commands_gesture(bodies, here)  # a script read from a heredoc
            continue
        match = RUNNER_SCRIPT.search(word) or MANGLED_RUNNER_SCRIPT.match(word)
        if match is None:
            return None
        script = match.group(1).lower()
        if script == "svc.sh" and words[index + 1 : index + 2] == ["status"]:
            return None
        return script if _is_runner_call(word, words[index + 1 :], here) else None
    return None


def _commands_gesture(command: str, here: str | None = None) -> str | None:
    """The owner gesture of the first simple command of `command` that makes one."""
    for words in segments(command):
        if gesture := owner_gesture(words, here=here):
            return gesture
    return None


def owner_gesture(
    words: list[str],
    here: str | None = None,
    bodies: str = "",
    read_text: Callable[[str], str | None] = read_text_or_none,
) -> str | None:
    """The owner gesture a simple command makes, named for the refusal, or None.

    `here` is the directory the command runs in, where a runner's folder is told from a project's.
    """
    call = gh_command(words)
    if call and call[0] == "api":
        return _api_gesture(call[1:], here, bodies, read_text)
    return _gh_gesture(words) or _runner_gesture(words, here, bodies)


def _owner_refusal(gesture: str) -> str:
    return (
        f"{gesture} : geste du propriétaire du dépôt, à lister pour l'humain en fin de compte rendu"
    )


def _declared_gesture(words: list[str], declared: Iterable[str]) -> str | None:
    """The refusal of the first `owner-gesture` line whose prefix opens the command, or None.

    Compared word by word, after the environment assignments and gh's global options, so that
    `gh -R o/r label delete` matches `gh label delete`. A line without a reason still refuses,
    and says so: it is never completed.
    """
    call = gh_command(words)
    normalised = ["gh", *call] if call is not None else words
    for value in declared:
        parts = split_value(value, 2)
        prefix_text = parts[0] if parts else re.sub(r"\s*\|\s*$", "", value).strip()
        try:
            prefix = shlex.split(prefix_text)
        except ValueError:
            prefix = prefix_text.split()
        if prefix and normalised[: len(prefix)] == prefix:
            reason = parts[1] if parts else "la ligne `owner-gesture` de ce geste est sans raison"
            return f"{_owner_refusal(prefix_text)} : {reason}"
    return None


def _posix(path: str) -> str:
    """A path as `forge:qc` compares it: relative, with `/`, without a leading `./`."""
    text = path.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def protected_refusal(protected: Iterable[str], changed: PrFiles, target: Target) -> str | None:
    """Why a merge is the human's: a file of the diff under a `protected-path` prefix, or None.

    Without a declared prefix nothing is read. Once one is, a list that cannot be read refuses.
    """
    prefixes = [_posix(value) for value in protected if _posix(value)]
    if not prefixes:
        return None
    paths = changed(*target)
    if paths is None:
        return (
            "la liste des fichiers de la PR est illisible (appel `gh pr view --json files` en échec,"
            f" hors délai ou réponse inattendue) et la clé `{PROTECTED_KEY}` est déclarée : refusée par"
            " précaution, la fusion revient à l'humain, à lister en fin de compte rendu"
        )
    for path in paths:
        for prefix in prefixes:
            if _posix(path).startswith(prefix):
                return (
                    f"le fichier `{path}` de la PR commence par le préfixe `{prefix}` de la clé"
                    f" `{PROTECTED_KEY}` : la fusion revient à l'humain, à lister en fin de compte rendu"
                )
    return None


# The files of the infra guard: `guard_infra.py`, its tests (which also prove this refusal), this
# file, which holds the refusal, and `hooks.json`, which runs the guard. A PR whose diff touches one
# is merged by the owner, by hand. Compared with the POSIX path of each file of the diff, so it
# holds in forge and in any copy of it.
INFRA_GUARD_FILES = frozenset(
    {
        "plugins/forge/hooks/guard_infra.py",
        "tests/test_guard_infra.py",
        "plugins/forge/hooks/guard_git.py",
        "plugins/forge/hooks/hooks.json",
    }
)
INFRA_GUARD_REFUSAL = "this PR changes the infra guard: only the owner merges it, by hand"
MERGE_ENDPOINT = re.compile(
    r"^(?:https?://api\.github\.com/)?repos/([^/]+/[^/]+)/pulls/([^/]+)/merge$", re.IGNORECASE
)
MERGE_MUTATION = re.compile(r"\b(?:mergePullRequest|enablePullRequestAutoMerge)\b", re.IGNORECASE)
# A PR as gh reads it: its number, its repository and the directory gh runs in (None: the current
# branch, the repository of that directory, the event's directory).
Target = tuple[str | None, str | None, str | None]
# The files of a PR by its target, or None when they cannot be read.
PrFiles = Callable[[str | None, str | None, str | None], list[str] | None]
# Why a merge whose PR the guard cannot tell is the owner's.
UNREADABLE_MERGE = (
    "the guard cannot tell which PR is merged ({}), so it may change the infra guard: only the"
    " owner merges it, by hand"
)
GRAPHQL_MERGE = (
    "a GraphQL merge names its PR by node id, whose files the guard does not read, so it may"
    f" change the infra guard; {INFRA_GUARD_REFUSAL}"
)


def _unreadable(word: str | None) -> bool:
    return word is not None and any(char in word for char in "$`")


def infra_guard_refusal(target: Target, pr_files: PrFiles) -> str | None:
    """Why a merge is the owner's: its PR changes the infra guard, or its files cannot be read."""
    paths = pr_files(*target)
    if paths is None:
        return (
            "the files of the PR cannot be read (`gh pr view --json files` failed, timed out or"
            f" answered something else), so it may change the infra guard; {INFRA_GUARD_REFUSAL}"
        )
    if any(_posix(path) in INFRA_GUARD_FILES for path in paths):
        return INFRA_GUARD_REFUSAL
    return None


# A brace expansion of bash, `{a,b}` or `{1..3}`; gh's own `{owner}` and `{repo}` are none.
BRACE_EXPANSION = re.compile(r"\{[^{}]*(?:,|\.\.)[^{}]*\}")
# The segments of a REST merge endpoint; None stands for any name.
MERGE_SEGMENTS = ("repos", None, None, "pulls", None, "merge")


def _may_become_merge(endpoint: str, words: list[str]) -> bool:
    """Whether the shell may turn the endpoint of a `gh api` write into a merge the guard can't read.

    A variable or a substitution in it (or in any word, when the call names no endpoint), a brace
    expansion, or a glob whose segments may match `repos/<owner>/<repo>/pulls/<n>/merge`.
    """
    if _unreadable(endpoint) or (not endpoint and any(_unreadable(word) for word in words)):
        return True
    if BRACE_EXPANSION.search(endpoint):
        return True
    if not any(char in endpoint for char in "*?["):
        return False
    # bash reads `[^x]` as fnmatch reads `[!x]`; a scheme and a host before the path are dropped.
    path = re.sub(r"^[^/]*//[^/]*/", "", endpoint.replace("[^", "[!")).strip("/").lower()
    segments = path.split("/")
    return len(segments) == len(MERGE_SEGMENTS) and all(
        fnmatch.fnmatchcase(name, segment) if name else bool(segment)
        for name, segment in zip(MERGE_SEGMENTS, segments, strict=True)
    )


def _api_merge(
    args: list[str], here: str | None, bodies: str, read_text: Callable[[str], str | None]
) -> tuple[str, str | None] | str | None:
    """The merge a `gh api` call makes (the words after `api`): `(number, owner/repo)`, or None.

    `owner/repo` is None for gh's `{owner}/{repo}`, which it fills from `GH_REPO` or the
    directory. A merge the guard cannot read is its refusal instead: a GraphQL merge, which names
    its PR by node id, or a write whose endpoint the shell may change into a merge. A query that
    cannot be read is refused before, as an owner gesture.
    """
    for words, redirections in api_readings(args) or []:
        call = parse_api(words)
        endpoint = call.endpoint.split("?", 1)[0].strip("/")
        if endpoint.lower() == "graphql":
            texts, _ = _graphql_texts(args, words, redirections, here, bodies, read_text)
            if MERGE_MUTATION.search("\n".join(texts)):
                return GRAPHQL_MERGE
            continue
        if _reads(words):
            continue
        if _may_become_merge(call.endpoint, words):
            return UNREADABLE_MERGE.format("the shell may change its endpoint")
        if (merge := MERGE_ENDPOINT.match(endpoint)) is not None:
            return merge.group(2), None if "{" in merge.group(1) else merge.group(1)
    return None


def _merges(
    words: list[str], here: str | None, bodies: str, read_text: Callable[[str], str | None]
) -> bool:
    """Whether a simple command (its alias expanded) may merge a PR.

    `gh pr merge`, a `gh api` merge, or a gh call whose group, or verb under `pr`, the shell may
    change (`gh $X 5`, `gh pr $V 5`).
    """
    call = gh_command(words)
    if not call:
        return False
    if _unreadable(call[0]):
        return True
    if call[0] == "api":
        return _api_merge(call[1:], here, bodies, read_text) is not None
    act = gh_act(words)
    return act is not None and act[0] == "pr" and (act[1] == "merge" or _unreadable(act[1]))


def _alias_unknowable(words: list[str], alone: bool) -> bool:
    """Whether a gh call names no gh group in a command where its alias cannot be known.

    The table `gh alias list` gives before the command runs holds for a gh call run alone (a
    `cd` aside), with no assignment or wrapper: anything else beside it (`gh alias set`, a write
    to gh's config, a `GH_CONFIG_DIR=` or `HOME=`) may change what the name expands to.
    """
    call = gh_command(words)
    if not call or alone:
        return False
    return call[0] not in GH_GROUPS and not call[0].startswith("-")


def _plain_cd(item: list[str] | str) -> bool:
    """`cd <path>` with nothing the shell expands: it changes no gh alias."""
    return isinstance(item, list) and item[:1] == ["cd"] and not any(map(_unreadable, item))


# The words after which a program that runs gh from its arguments may merge.
MERGE_WORDS = frozenset({"merge", "api", "graphql"})
# A REST merge endpoint, whatever comes before it: `repos/o/r/pulls/5/merge`.
MERGE_PATH = re.compile(r"/merge(?:$|[?#/])")


def _merge_sign(word: str) -> bool:
    return word in MERGE_WORDS or MERGE_PATH.search(word) is not None


def _shell_named_merge(text: str, depth: int = 0) -> bool:
    """Whether a program the shell names may run a merge: the class `$(echo gh) pr merge 5`.

    One rule: a simple command whose program, behind assignments and wrappers, is a variable or a
    substitution (`$G`, `$(...)`, a backtick, quoted or not), in a text where a word, substitutions
    included and each word split on its blanks, is a merge sign (`_merge_sign`). The substitutions are read as `guard_infra` reads
    them, each replaced by one word and its commands judged in turn; heredoc bodies are data.
    """
    # Imported here: guard_infra imports this module.
    from guard_infra import (  # noqa: PLC0415
        MAX_DEPTH,
        UnclearError,
        UnsplitError,
        simple_commands,
        substitutions,
        unwrap_with_env,
    )

    def named(words: list[str]) -> bool:
        try:
            unwrap_with_env(words)
        except UnclearError:
            return True
        return False

    found: list[list[str]] = []
    pending = [(without_heredoc_bodies(text), depth)]
    while pending:
        part, level = pending.pop()
        if level > MAX_DEPTH:
            return True  # deeper than the guard reads: judged as a merge
        try:
            outer, inner = substitutions(part)
        except UnsplitError:  # a backtick never closed: the text is read as plain words
            outer, inner = part, []
        try:
            found += simple_commands(outer)
        except UnsplitError:  # a quote never closed, as `_commands` reads it
            found.append(outer.split())
        pending += [(nested, level + 1) for nested in inner]
    # A sign may sit inside one word: `G='gh pr merge'; $G 5`.
    signs = (part for words in found for word in words for part in word.split())
    return any(map(named, found)) and any(map(_merge_sign, signs))


def _hidden_gh(words: list[str]) -> bool:
    """Whether a command may run a gh merge the guard does not see as gh.

    A program named by the shell (`$G pr merge 5`), or gh among the arguments of another
    program (`find . -exec gh pr merge 5 \\;`), followed by a merge word or a word the shell
    may change.
    """
    def merging(rest: list[str]) -> bool:
        return any(_merge_sign(word) or _unreadable(word) for word in rest)

    if words and _unreadable(words[0]) and merging(words[1:]):
        return True
    return any(
        re.split(r"[/\\]", word)[-1].lower() in ("gh", "gh.exe") and merging(words[index + 1 :])
        for index, word in enumerate(words[1:], 1)
    )


class ShellWord(NamedTuple):
    """A word as bash reads it."""

    raw: str  # as typed, quotes included
    value: str  # quotes and escapes removed
    literal: bool  # nothing in it the shell expands
    one_word: bool  # the shell keeps it one word and runs nothing: only `$VAR` in double quotes


SHELL_OPERATORS = ("&&", "||", ";;", "<<", ">>", ">&", "<&", "&>", "|&", ";", "&", "|", "(", ")", "<", ">")


def shell_words(command: str) -> list[ShellWord | str] | None:
    """The words and operators of a command, a newline read as `;`; None when a quote is open."""
    tokens: list[ShellWord | str] = []
    index, size = 0, len(command)
    while index < size:
        char = command[index]
        if char in " \t\r":
            index += 1
            continue
        if char == "\n":
            tokens.append(";")
            index += 1
            continue
        operator = next((op for op in SHELL_OPERATORS if command.startswith(op, index)), None)
        if operator is not None:
            tokens.append(operator)
            index += len(operator)
            continue
        start = index
        value: list[str] = []
        bare: list[str] = []
        quoted_variable = substitution = False
        while index < size and command[index] not in " \t\r\n;&|()<>":
            char = command[index]
            if char == "'":
                end = command.find("'", index + 1)
                if end < 0:
                    return None
                value.append(command[index + 1 : end])
                index = end + 1
            elif char == '"':
                index += 1
                while index < size and command[index] != '"':
                    char = command[index]
                    if char == "\\" and index + 1 < size and command[index + 1] in '$`"\\\n':
                        value.append(command[index + 1])
                        index += 2
                        continue
                    if char == "`" or command.startswith(("$(", "$["), index):
                        substitution = True
                    elif char == "$":
                        quoted_variable = True
                    value.append(char)
                    index += 1
                if index >= size:
                    return None
                index += 1
            elif char == "\\":
                if index + 1 >= size:
                    return None
                value.append(command[index + 1])
                index += 2
            else:
                bare.append(char if bare or char not in "~#" else "$")  # a leading `~` or `#`
                value.append(char)
                index += 1
        unquoted = "".join(bare)
        expands = any(char in unquoted for char in "$`*?[") or bool(BRACE_EXPANSION.search(unquoted))
        tokens.append(
            ShellWord(
                command[start:index],
                "".join(value),
                not (expands or quoted_variable or substitution),
                not (expands or substitution),
            )
        )
    return tokens


MERGE_ALONE = (
    "run the merge alone: `[cd <path> &&] gh pr merge <n> [-R owner/repo]`, with at most a"
    " `GH_REPO=owner/repo` before gh and a `| tee <file>` or `| cat` after it, and nothing else in"
    " the command (a label or any other step goes in a command of its own); the PR number, `-R`,"
    " `GH_REPO` and the `cd` path are literal. Only in that form does the guard read the PR the"
    " merge acts on"
)
QUOTE_VARIABLE = (
    "the value of `{}` of a merge holds a variable outside double quotes, where word splitting may"
    " slip in a `-R`: quote the variable or use a literal path"
)
# The options of `gh pr merge` (gh 2.102), by whether they take a value. A merge with any other
# word starting with `-` (a cluster such as `-sR`, `--squash=false`, `--`) is refused: only on
# these does the guard know which word is the PR and which the repository.
MERGE_FLAGS = frozenset(
    {"--admin", "--auto", "--disable-auto", "-d", "--delete-branch", "-m", "--merge", "-r",
     "--rebase", "-s", "--squash"}
)
MERGE_VALUED = frozenset(
    {"-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--subject", "-A",
     "--author-email", "--match-head-commit"}
)
# Those whose value may hold a variable in double quotes: one word, which changes no PR.
QUOTABLE_OPTIONS = frozenset(
    {"--body-file", "-F", "--body", "-b", "--subject", "-t", "--match-head-commit"}
)


class PrMerge(NamedTuple):
    """What a `gh pr merge` names."""

    number: str | None  # None for the current branch's PR
    repository: str | None  # the last `-R`/`--repo`, as gh keeps it
    words: list[str]  # the words after `merge`


def pr_merge(words: list[ShellWord]) -> PrMerge | str:
    """The PR `gh pr merge ...` names (all its words), or why the guard cannot tell it.

    Each option is one of `MERGE_FLAGS` or `MERGE_VALUED`; only the value of a `QUOTABLE_OPTIONS`
    may hold a `$VAR`, and in double quotes. At most one PR is named.
    """
    if [word.raw for word in words[:3]] != ["gh", "pr", "merge"]:
        return MERGE_ALONE
    rest = words[3:]
    numbers: list[str] = []
    repository = None
    index = 0
    while index < len(rest):
        word = rest[index]
        name, equals, inline = word.value.partition("=")
        if not word.value.startswith("-"):
            if not word.literal:
                return MERGE_ALONE
            numbers.append(word.value)
            index += 1
            continue
        if word.value in MERGE_FLAGS and word.literal:
            index += 1
            continue
        if equals and name.startswith("--") and name in MERGE_VALUED:
            value, valued = inline, word
            index += 1
        elif word.value in MERGE_VALUED and word.literal and index + 1 < len(rest):
            name, value, valued = word.value, rest[index + 1].value, rest[index + 1]
            index += 2
        else:
            return MERGE_ALONE
        if not valued.literal:
            if name not in QUOTABLE_OPTIONS or _substitutes(valued.raw):
                return MERGE_ALONE
            if not valued.one_word:
                return QUOTE_VARIABLE.format(name)
        if name in ("-R", "--repo"):
            repository = value
    if len(numbers) > 1:
        return MERGE_ALONE
    return PrMerge(numbers[0] if numbers else None, repository, [word.value for word in rest])


def _substitutes(raw: str) -> bool:
    return "`" in raw or "$(" in raw or "$[" in raw
GH_REPO_ASSIGNMENT = re.compile(r"GH_REPO=[\w.-]+/[\w.-]+")
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")


class MergeCall(NamedTuple):
    """A merge in the one form the guard judges."""

    words: list[ShellWord]  # the gh call, from `gh` on
    directory: str | None  # where gh runs: the literal `cd`, else the event's directory
    repository: str | None  # the literal `GH_REPO` before gh, or None


def merge_call(command: str, cwd: str | None) -> MergeCall | str:
    """The merge `command` runs, in the form `[cd <path> &&] [GH_REPO=o/r] gh ... [| tee f]`.

    Anything else beside it (another command, an assignment, `export`, `pushd`, `eval`, a
    subshell, a redirection...) is refused, by the reason returned: the guard reads the PR a
    merge acts on only where nothing else may move it.
    """
    tokens = shell_words(command.strip())
    if tokens is None:
        return MERGE_ALONE
    if "|" in tokens:
        pipe = tokens.index("|")
        tail, tokens = tokens[pipe + 1 :], tokens[:pipe]
        if not _harmless_tail(tail):
            return MERGE_ALONE
    directory = cwd
    head = tokens[:3]
    if len(head) == 3 and isinstance(head[0], ShellWord) and head[0].raw == "cd" and head[2] == "&&":
        path = head[1]
        if not isinstance(path, ShellWord) or not path.literal or path.value.startswith("-"):
            return MERGE_ALONE
        directory = _moved(cwd, path.value)
        tokens = tokens[3:]
    words = [token for token in tokens if isinstance(token, ShellWord)]
    if len(words) != len(tokens) or directory == UNKNOWN:
        return MERGE_ALONE
    repository = None
    if words and ASSIGNMENT.match(words[0].raw):
        if not GH_REPO_ASSIGNMENT.fullmatch(words[0].value):  # nothing the shell expands
            return MERGE_ALONE
        repository = words[0].value.partition("=")[2]
        words = words[1:]
    return MergeCall(words, directory, repository)


def _harmless_tail(tail: list[ShellWord | str]) -> bool:
    """`tee <file>...` or `cat`: what a merge may be piped to.

    The program is written `tee` or `cat` as such; a file of `tee` may hold a variable in double
    quotes (`"$T/f"`), one word the shell runs nothing for, never one outside quotes or a
    substitution.
    """
    words = [token for token in tail if isinstance(token, ShellWord)]
    if len(words) != len(tail) or not words:
        return False
    if words[0].raw == "cat":
        return len(words) == 1
    return words[0].raw == "tee" and all(word.one_word for word in words[1:])


# The groups gh runs itself, which no alias overrides (gh refuses to set one).
GH_GROUPS = frozenset(
    {
        "agent-task", "alias", "api", "attestation", "auth", "browse", "cache", "codespace", "cs",
        "completion", "config", "copilot", "discussion", "extension", "extensions", "ext", "gist",
        "gpg-key", "help", "issue", "label", "licenses", "org", "pr", "preview", "project",
        "release", "repo", "ruleset", "rs", "run", "search", "secret", "skill", "ssh-key",
        "status", "variable", "version", "workflow",
    }
)
# What `gh alias list` gives, by name; None when it cannot be read.
GhAliases = Callable[[], "dict[str, str] | None"]
UNREADABLE_ALIAS = (
    "`gh {}` names no gh command, and the aliases cannot be read (`gh alias list` failed): it may"
    " be a merge the guard cannot judge. Name the gh command itself"
)


class Expanded(NamedTuple):
    """A gh call with its alias expanded, or the script of a shell alias."""

    words: list[str]
    script: str | None  # the script of an alias set with `!` (gh runs it with `sh -c`)


def expand_gh_alias(words: list[str], aliases: GhAliases) -> Expanded | str:
    """The gh call behind an alias, as gh expands it; the words as they are when none applies.

    A name that is no gh group is looked up; an alias table that cannot be read is the refusal
    returned.
    """
    call = gh_command(words)
    if not call or call[0] in GH_GROUPS or call[0].startswith("-") or _unreadable(call[0]):
        return Expanded(words, None)
    table = aliases()
    if table is None:
        return UNREADABLE_ALIAS.format(call[0])
    expansion = table.get(call[0])
    if expansion is None:
        return Expanded(words, None)
    if expansion.startswith("!"):
        return Expanded([], expansion[1:])
    # As gh 2.102 does: each argument replaces its `$N` in the text while one `$` is left, and
    # follows the expansion once none is; the text is split after, so an argument may hold
    # several words. A `$N` left unfilled makes gh fail, before running anything.
    rest: list[str] = []
    for position, argument in enumerate(call[1:], 1):
        if "$" in expansion:
            expansion = expansion.replace(f"${position}", argument)
        else:
            rest.append(argument)
    if re.search(r"\$\d", expansion):
        return Expanded(words, None)
    try:
        expanded = shlex.split(expansion)
    except ValueError:
        return UNREADABLE_ALIAS.format(call[0])
    return Expanded([*words[: len(words) - len(call)], *expanded, *rest], None)


ALIAS_GESTURES = frozenset({("alias", "set"), ("alias", "import"), ("alias", "delete")})
ALIAS_REFUSAL = (
    "gh alias {}: an alias may hide a merge from the guard; a subagent never changes the gh"
    " aliases, the human does"
)


# The reserved words after which the shell runs a command as it would run alone.
COMMAND_KEYWORDS = frozenset(
    {"if", "elif", "while", "until", "then", "else", "do", "time", "!", "{"}
)
# The variables git finds a repository by: set for a command, they send its writes (and those of a
# suite it replays) into another repository than the one of the directory.
LOCATION_VARIABLES = frozenset(
    {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY"}
)
LOCATION_OPTIONS = frozenset({"--git-dir", "--work-tree"})
# The builtins that export the names they are given, with or without a value.
EXPORTING_BUILTINS = frozenset({"export", "declare", "typeset", "readonly", "local"})


def after_keywords(words: list[str]) -> list[str]:
    """`words` without the reserved words that precede the command (`if`, `then`, `time -p`...)."""
    while words[:1] and words[0] in COMMAND_KEYWORDS:
        words = words[2:] if words[:2] == ["time", "-p"] else words[1:]
    return words


def location_refusal(words: list[str], bodies: str = "") -> str | None:
    """Why a simple command is refused for aiming git elsewhere, or None.

    The command is read as it would run alone: behind reserved words (`if`, `then`, `time`, `!`),
    assignments, `env` and the builtins that export, and into the script of a shell `-c`.
    `unset` and a word that only says the name (`echo GIT_DIR=x`) are not a setting.
    """
    seen = looked_through(after_keywords(words), bodies)
    names = list(seen.env)
    if seen.words[:1] and seen.words[0] in EXPORTING_BUILTINS:
        names += [word.partition("=")[0] for word in seen.words[1:] if not word.startswith("-")]
    for name in names:
        if name in LOCATION_VARIABLES:
            return _location_reason(name)
    if seen.words[:1] == ["git"]:
        rest = seen.words[1:]
        leading = rest[: len(rest) - len(_subcommand_and_args(rest))]
        for word in leading:
            if word.split("=")[0] in LOCATION_OPTIONS:
                return _location_reason(word.split("=")[0])
    if seen.script is not None:
        for inner in segments(seen.script):
            if reason := location_refusal(inner):
                return reason
    return None


def commands_location_refusal(command: str) -> str | None:
    """The first `location_refusal` among the simple commands of `command`."""
    bodies = split_heredocs(command)[1]
    for words in segments(command):
        if reason := location_refusal(words, bodies):
            return reason
    return None


def _location_reason(name: str) -> str:
    return (
        f"`{name}`: git finds the repository by it, and a suite replayed under it writes in"
        " another repository than the one of the directory; work in the copy with `git -C <copy>`"
    )


def refusal(
    command: str,
    branch: str | Callable[[str | None], str],
    checks_green: Callable[[str | None, str | None, str | None], bool],
    cwd: str | None = None,
    read_text: Callable[[str], str | None] = read_text_or_none,
    description: Callable[[str | None, str | None, str | None], str] = lambda *_target: "",
    owner_gestures: Iterable[str] = (),
    budget: Callable[[], str | None] = lambda: None,
    protected_paths: Iterable[str] = (),
    changed_files: PrFiles = lambda *_target: None,
    pr_files: PrFiles = lambda *_target: [],
    *,
    gh_aliases: GhAliases = dict,
    subagent: bool = False,
) -> str | None:
    """Why the command is refused, or None when it may run.

    `branch` is the branch of a directory: a callable is asked about the directory each git
    command acts on (after `cd` and `-C`); a string is that branch wherever git runs.
    `checks_green`, `description` (the body), `changed_files` and `pr_files` read the merged PR
    by its target (`Target`), the same for all four.
    `owner_gestures` are the values of the project's `owner-gesture` key, beside the built-in list.
    `budget` says why the error budget forbids a merge (key `budget-action`), or None.
    `protected_paths` are the values of the `protected-path` key, judged on `changed_files`, None
    when they cannot be read; `pr_files` are judged by the infra guard. `gh_aliases` reads the gh
    aliases; `subagent` says whether a subagent runs the command.
    """
    declared = list(owner_gestures)
    branch_of = branch if callable(branch) else (lambda _directory: branch)

    def branch_where(directory: str | None) -> str:
        # A directory whose branch cannot be read (an unexpanded `~` or `$VAR`, `cd -`, a path
        # that does not exist) is judged as the event's own: never as "no branch", which would
        # let a commit on main through.
        if directory == UNKNOWN:
            return branch_of(cwd)
        return branch_of(directory) or branch_of(cwd)

    def walk(text: str, begin: str | None, top: bool) -> tuple[str | None, bool]:
        """The refusal of `text` run from `begin`, and whether it may merge a PR anywhere.

        `top` says whether `text` is the event's command itself, not a script it runs.
        """
        bodies = split_heredocs(text)[1]
        switched = merges = False
        here = begin
        saved: list[str | None] = []
        items = _commands(text)
        for item in items:
            if isinstance(item, str):
                if item == "(":
                    saved.append(here)  # a subshell's `cd` ends with it
                else:
                    here = saved.pop() if saved else begin
                continue
            if gesture := runner_registration_gesture(item):
                return _owner_refusal(gesture), merges  # before the assignments are set aside
            seen = looked_through(item, bodies)
            words, script = seen.words, seen.script
            if script is None and words and words[0] == "eval":
                script = " ".join(words[1:])
            others = [other for other in items if other is not item]
            alone = top and item == words and all(map(_plain_cd, others))
            if script is None and _alias_unknowable(words, alone):
                merges = True  # judged, and refused, as a merge not run alone
                continue
            if script is None:
                expanded = expand_gh_alias(words, gh_aliases)
                if isinstance(expanded, str):
                    return expanded, merges
                words, script = expanded
            if script is not None:
                reason, nested = walk(script, here, False)
                if reason is not None:
                    return reason, merges
                merges = merges or nested
                continue
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
                    return reason, merges
            if gesture := owner_gesture(words, here, bodies, read_text):
                return _owner_refusal(gesture), merges
            if declared_refusal := _declared_gesture(words, declared):
                return declared_refusal, merges
            act = gh_act(words)
            if subagent and act is not None and act[:2] in ALIAS_GESTURES:
                return ALIAS_REFUSAL.format(act[1]), merges
            merges = merges or _merges(words, here, bodies, read_text) or _hidden_gh(words)
        return None, merges or _shell_named_merge(text)

    reason, merges = walk(command, cwd, True)
    if reason is None and not merges:
        return commands_location_refusal(command)
    if reason is not None:
        return reason
    return merge_call_refusal(
        command,
        cwd,
        checks_green,
        read_text,
        description,
        budget,
        protected_paths,
        changed_files,
        pr_files,
        gh_aliases,
    ) or commands_location_refusal(command)


def merge_call_refusal(
    command: str,
    cwd: str | None,
    checks_green: Callable[[str | None, str | None, str | None], bool],
    read_text: Callable[[str], str | None],
    description: Callable[[str | None, str | None, str | None], str],
    budget: Callable[[], str | None],
    protected_paths: Iterable[str],
    changed_files: PrFiles,
    pr_files: PrFiles,
    gh_aliases: GhAliases,
) -> str | None:
    """Why a command that merges is refused, or None: run alone, its PR read where it runs."""
    call = merge_call(command, cwd)
    if isinstance(call, str):
        return call
    words = call.words
    if (gh := gh_command([word.value for word in words])) and gh[0] not in GH_GROUPS:
        if not all(word.literal for word in words):
            return MERGE_ALONE
        expanded = expand_gh_alias([word.value for word in words], gh_aliases)
        if isinstance(expanded, str):
            return expanded
        words = [ShellWord(word, word, True, True) for word in expanded.words]
    message = ""
    number: str | None
    repository: str | None
    if [word.raw for word in words[:2]] == ["gh", "api"]:
        if not all(word.literal for word in words):
            return MERGE_ALONE
        found = _api_merge([word.value for word in words[2:]], call.directory, "", read_text)
        if found is None or isinstance(found, str):
            return found or MERGE_ALONE
        number, named = found
        repository = named or call.repository
    else:
        merge = pr_merge(words)
        if isinstance(merge, str):
            return merge
        number = merge.number
        message = _merge_message(merge.words, call.directory, read_text)
        if merge.repository is not None:
            repository = merge.repository
        elif number is not None and number.startswith(("https://", "http://")):
            repository = None  # the URL names the repository
        else:
            repository = call.repository
    target: Target = (number, repository, call.directory)
    if closed := closed_despite_refs(message + "\n" + description(*target)):
        ticket, phrase = closed
        return (
            f"the merge message or PR description cites #{ticket} with Refs and closes it"
            f" (`{phrase}`): the first PR of a split ticket must leave it open"
        )
    if exhausted := budget():
        return exhausted
    if infra := infra_guard_refusal(target, pr_files):
        return infra
    if protected := protected_refusal(protected_paths, changed_files, target):
        return protected
    if not checks_green(*target):
        return "merge with checks not green: wait for every check, `gh pr checks`"
    return None


class LookedThrough(NamedTuple):
    """What a simple command runs behind its assignments and wrappers."""

    words: list[str]
    script: str | None  # the script a shell runs instead, from `-c` or a heredoc
    env: dict[str, str]  # the variables the assignments and `env` set for it


def looked_through(words: list[str], bodies: str) -> LookedThrough:
    """The words that run behind assignments and wrappers, or the script a shell runs instead.

    `gh` and `git` are named as such whatever their path or `.exe`. A shell's script is that of
    `-c`, or the heredoc bodies when it reads its standard input. Words the infra guard cannot
    read are kept as they are: that guard holds them.
    """
    # Imported here: guard_infra imports this module.
    from guard_infra import (  # noqa: PLC0415
        SHELLS,
        UnclearError,
        _shell_script,
        program_name,
        strip_redirections,
        unwrap_with_env,
    )

    try:
        inner, env = unwrap_with_env(words)
        name = program_name(inner[0]) if inner else ""
    except UnclearError:
        return LookedThrough(words, None, {})
    if name in SHELLS:
        bare, redirections = strip_redirections(inner)
        dash_c, operands = _shell_script(bare[1:])
        if dash_c and operands:
            return LookedThrough([], operands[0], env)
        if not operands and bodies and any(op.startswith("<<") for op, _ in redirections):
            return LookedThrough([], bodies, env)
    if name in ("gh", "git"):
        return LookedThrough([name, *inner[1:]], None, env)
    return LookedThrough(inner, None, env)


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


def _gh_pr(
    cwd: str | None, action: str, target: Target, *options: str
) -> subprocess.CompletedProcess[str] | None:
    """`gh pr <action> <n> -R <repo> <options>` run where the target says (None: `cwd`).

    None when gh is missing or does not finish.
    """
    pr, repository, directory = target
    gh = shutil.which("gh")
    if gh is None:
        return None
    where = cwd if directory is None else native_directory(directory)
    numbered = [*([pr] if pr else []), *(["-R", repository] if repository else [])]
    return _run([gh, "pr", action, *numbered, *options], where)


def checks_green_via_gh(cwd: str | None) -> Callable[[str | None, str | None, str | None], bool]:
    def green(pr: str | None, repository: str | None, directory: str | None) -> bool:
        completed = _gh_pr(cwd, "checks", (pr, repository, directory))
        # A timeout is not green: the merge waits rather than going through unchecked.
        return completed is not None and completed.returncode == 0

    return green


def description_via_gh(cwd: str | None) -> Callable[[str | None, str | None, str | None], str]:
    def body(pr: str | None, repository: str | None, directory: str | None) -> str:
        completed = _gh_pr(cwd, "view", (pr, repository, directory), "--json", "body", "--jq", ".body")
        # A description that cannot be read adds nothing, like an unreadable body file: without
        # gh the checks are not green anyway, and a timeout here must not block every merge.
        if completed is None or completed.returncode != 0:
            return ""
        return completed.stdout

    return body


def parse_changed_files(text: str) -> list[str] | None:
    """The paths of `gh pr view --json files`, or None when the answer is not that list."""
    try:
        document = json.loads(text)
    except ValueError:
        return None
    entries = document.get("files") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        return None
    paths: list[str] = []
    for entry in entries:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(path, str) or not path:
            return None
        paths.append(path)
    return paths


def pr_files_via_gh(cwd: str | None) -> PrFiles:
    """`gh pr view <n> -R <repo> --json files` where the target says, None when unreadable."""

    def files(pr: str | None, repository: str | None, directory: str | None) -> list[str] | None:
        completed = _gh_pr(cwd, "view", (pr, repository, directory), "--json", "files")
        # No gh, a failure or a timeout: the list is unknown, and the caller refuses.
        if completed is None or completed.returncode != 0:
            return None
        return parse_changed_files(completed.stdout)

    return files


def parse_gh_aliases(text: str) -> dict[str, str] | None:
    """The aliases of `gh alias list` (`name: expansion` per line), or None for anything else."""
    aliases: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"(\S+): (.+)", line)
        if match is None:
            return None
        aliases[match.group(1)] = match.group(2)
    return aliases


def gh_aliases_via_gh(cwd: str | None) -> GhAliases:
    """`gh alias list` in `cwd`, read once; None when it fails, times out or answers otherwise."""
    cache: list[dict[str, str] | None] = []

    def aliases() -> dict[str, str] | None:
        if not cache:
            gh = shutil.which("gh")
            completed = _run([gh, "alias", "list"], cwd) if gh else None
            ok = completed is not None and completed.returncode == 0
            cache.append(parse_gh_aliases(completed.stdout) if ok and completed else None)
        return cache[0]

    return aliases


def changed_files_via_gh(cwd: str | None) -> PrFiles:
    """The files of a PR for the `protected-path` key: the infra guard's reading."""
    return pr_files_via_gh(cwd)


def main() -> int:
    event = json.load(sys.stdin)
    command = str(event.get("tool_input", {}).get("command", ""))
    cwd = event.get("cwd")
    root = project_root(event)
    config = load(root)
    reason = refusal(
        command,
        current_branch,
        checks_green_via_gh(cwd),
        cwd,
        description=description_via_gh(cwd),
        owner_gestures=config.get(OWNER_KEY, []),
        budget=lambda: merge_refusal(config, state_path(root), datetime.now(tz=timezone.utc)),
        protected_paths=config.get(PROTECTED_KEY, []),
        changed_files=changed_files_via_gh(cwd),
        pr_files=pr_files_via_gh(cwd),
        gh_aliases=gh_aliases_via_gh(cwd),
        subagent=bool(event.get("agent_id")),
    )
    if reason is None:
        return 0
    sys.stderr.write(f"Blocked by the forge plugin (guard_git): {reason}.\n")
    return 2


def guarded_main() -> int:
    """`main`, failing closed: a crash of the guard refuses the command and says so.

    Without it a traceback exits 1, which Claude Code treats as a non-blocking error (the command
    runs), or, behind `|| exit 2` in hooks.json, a refusal the agent could take for a rule.
    """
    try:
        return main()
    except Exception as error:  # noqa: BLE001 - any failure of the guard must refuse the command
        sys.stderr.write(
            f"guard_git failed ({type(error).__name__}: {error}): the command is refused as a"
            " precaution. This is not a rule of the repository; retry, and tell the human if it"
            " persists.\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(guarded_main())
