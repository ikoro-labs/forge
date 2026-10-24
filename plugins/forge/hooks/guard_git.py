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
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath, PureWindowsPath

from usine import load, project_root, split_value

# The project's own owner gestures, one per line: `<command prefix> | <reason>`.
OWNER_KEY = "owner-gesture"

# Every external call has a timeout: a hook that hangs blocks the agent's command.
TIMEOUT_SECONDS = 20

HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")
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


# The fields and bodies of `gh api`: any of them makes gh send a POST unless `-X` says otherwise.
API_FIELDS = frozenset({"-f", "-F", "--field", "--raw-field", "--input"})


def _gh_api_reads(args: list[str]) -> bool:
    """A `gh api` call that is a read: an explicit GET or HEAD, or no method, field or `--input`.

    An explicit `-X GET` keeps its fields as query parameters, so it is a read with `-f` too;
    without a method, a field or a body makes gh send a POST.
    """
    sends_a_body = False
    for index, word in enumerate(args):
        name, _, value = word.partition("=")
        if name in API_FIELDS or (name.startswith("-f") or name.startswith("-F")) and len(name) > 2:
            sends_a_body = True
        if name in ("-X", "--method"):
            method = value or (args[index + 1] if index + 1 < len(args) else "")
            return method.upper() in ("GET", "HEAD")
        if name.startswith("-X") and len(name) > 2:
            return name[2:].lstrip("=").upper() in ("GET", "HEAD")
    return not sends_a_body


# The options of `gh api` that take their value as the next word (`--flag=value` is one word).
API_OPTIONS_WITH_VALUE = frozenset(
    {"-X", "--method", "-H", "--header", "-f", "-F", "--field", "--raw-field", "--input"}
    | {"-q", "--jq", "-t", "--template", "--cache", "--hostname", "-p", "--preview"}
)
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


def _api_endpoint(args: list[str]) -> str:
    index = 0
    while index < len(args):
        word = args[index]
        if word.startswith("-"):
            index += 2 if word in API_OPTIONS_WITH_VALUE else 1
            continue
        return word
    return ""


def _api_method(args: list[str]) -> str:
    for index, word in enumerate(args):
        name, _, value = word.partition("=")
        if name in ("-X", "--method"):
            return (value or (args[index + 1] if index + 1 < len(args) else "")).upper()
        if name.startswith("-X") and len(name) > 2:
            return name[2:].lstrip("=").upper()
    return "POST"


GRAPHQL_MUTATION_GESTURE = (
    "gh api graphql (mutation de protection, de ruleset, de collaborateur ou du dépôt)"
)
_VARIABLE = re.compile(r"\$\{?\w+\}?")


def _graphql_inputs(args: list[str]) -> list[tuple[str, str]]:
    """What a `gh api graphql` call is fed: `(kind, value)` per `--input` and per field.

    The kind is `input` for `--input <value>` and `query` for a field named `query`; the value of
    any other field cannot hold the query, except `name=@file`, which reads one.
    """
    inputs: list[tuple[str, str]] = []
    index = 0
    while index < len(args):
        word = args[index]
        name, equals, value = word.partition("=")
        field: str | None = None
        if name == "--input":
            if not equals:
                index += 1
                value = args[index] if index < len(args) else ""
            inputs.append(("input", value))
        elif name in ("--field", "--raw-field") or word in ("-f", "-F"):
            if not equals or word in ("-f", "-F"):
                index += 1
                field = args[index] if index < len(args) else ""
            else:
                field = value
        elif word.startswith(("-f", "-F")) and not word.startswith("--"):
            field = word[2:]
        elif word.startswith("-") and word in API_OPTIONS_WITH_VALUE:
            index += 1
        if field is not None:
            key, _, content = field.partition("=")
            if content.startswith("@"):
                inputs.append(("file", content[1:]))
            elif key == "query":
                inputs.append(("query", content))
        index += 1
    return inputs


def _graphql_gesture(
    args: list[str], here: str | None, bodies: str, read_text: Callable[[str], str | None]
) -> str | None:
    """The owner gesture of a `gh api graphql` call: a mutation of the owner, read wherever it is.

    The query is read in the arguments, in the heredocs of the command (`--input - <<EOF`, or
    `query="$(cat <<EOF ...)"`) and in the files it names. What cannot be read (a file that is not
    there, stdin from a pipe, a substitution or a variable) is refused as a precaution: a mutation
    of the owner could hide in it, and a guard that fails closes.
    """
    texts = [" ".join(args)]
    unread = ""
    for kind, value in _graphql_inputs(args):
        if kind == "query" and not (
            "`" in value or "$(" in value or _VARIABLE.fullmatch(value.strip())
        ):
            continue
        if kind == "query" and "<<" in value and bodies:
            texts.append(bodies)  # `$(cat <<EOF ...)`: the heredoc of this command
        elif kind == "query":
            unread = unread or "la requête vient d'une substitution ou d'une variable du shell"
        elif value == "-":
            if bodies:
                texts.append(bodies)
            else:
                unread = unread or "la requête vient de l'entrée standard"
        else:
            path = _moved(here, value)
            text = read_text(path) if path is not None and path != UNKNOWN else None
            if text is None:
                unread = unread or f"le fichier `{value}` ne peut pas être lu"
            else:
                texts.append(text)
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
    """The owner gesture of a `gh api` call (the words after `api`), or None."""
    endpoint = _api_endpoint(args).split("?", 1)[0].strip("/")
    if endpoint.lower() == "graphql":
        return _graphql_gesture(args, here, bodies, read_text)
    if _gh_api_reads(args):
        return None
    scope = OWNER_SCOPE.match(endpoint)
    if scope is not None and (
        (scope.group(1) is None and endpoint.startswith("repos/"))
        or (scope.group(1) and OWNER_ENDPOINT.match(scope.group(1)))
    ):
        return f"gh api {_api_method(args)} {endpoint}"
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
    {"--url", "--token", "install", "uninstall", "start", "stop", "remove"}
)
RUNNER_MARKERS = (("run.sh", "run.cmd"), ("bin/Runner.Listener",))


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


def _runner_gesture(words: list[str], here: str | None = None, bodies: str = "") -> str | None:
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


def refusal(
    command: str,
    branch: str | Callable[[str | None], str],
    checks_green: Callable[[str | None], bool],
    cwd: str | None = None,
    read_text: Callable[[str], str | None] = read_text_or_none,
    description: Callable[[str | None], str] = lambda _pr: "",
    owner_gestures: Iterable[str] = (),
) -> str | None:
    """Why the command is refused, or None when it may run.

    `branch` is the branch of a directory: a callable is asked about the directory each git
    command acts on (after `cd` and `-C`); a string is that branch wherever git runs.
    `description` is the body of a PR, by its number (None for the current branch's PR).
    `owner_gestures` are the values of the project's `owner-gesture` key, beside the built-in list.
    """
    declared = list(owner_gestures)
    bodies = split_heredocs(command)[1]
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
        if gesture := owner_gesture(words, here, bodies, read_text):
            return _owner_refusal(gesture)
        if declared_refusal := _declared_gesture(words, declared):
            return declared_refusal
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
    reason = refusal(
        command,
        current_branch,
        checks_green_via_gh(cwd),
        cwd,
        description=description_via_gh(cwd),
        owner_gestures=load(project_root(event)).get(OWNER_KEY, []),
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
