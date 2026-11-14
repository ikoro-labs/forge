"""PreToolUse hook: the infrastructure gestures no agent makes on its own.

A guarded command is refused to a subagent (exit 2) and gets `permissionDecision: ask` in the main
session, where the human answers the prompt. Claude Code sets `agent_id` only from within a
subagent; `agent_type` alone comes from `claude --agent`, which is a main session.

Guarded wherever it runs (a deny list):

- Docker: `rm`, `rmi`, `kill`, `system prune`, `container`, `volume`, `builder`, `buildx`, `image`
  and `network` `prune`, `container rm` and `kill`, `image rm`, `volume rm`, `network rm` (and
  their `remove` alias), and `docker compose down -v` (`down` alone passes);
- `systemctl` `restart` (and its `try-` and `reload-or-` forms), `stop`, `disable`, `mask`, `kill`,
  and the power verbs (`reboot`, `poweroff`, `halt`, `kexec`, `isolate`...), and the standalone
  `reboot`, `shutdown`, `poweroff` and `halt`;
- `lxc` `config set`, `config unset`, `config edit`, `config device remove`, `delete` (alias `rm`),
  `stop`, `restart`, `restore`, `pause`;
- `service <unit>` and `invoke-rc.d <unit>` with a verb `systemctl` is guarded for;
- `networkctl`, every verb but `status`, `list` and `lldp`; a runner's `svc.sh stop` and `uninstall`.

On a host of the project's `infra-hosts` key, reached by `ssh`, `scp`, `sftp`, `rsync`, `lxc exec
<host> --`, `lxc shell`, `lxc console`, `lxc file push|edit|delete`, or by Docker's endpoint (`-H`,
`--host`, `--context`, `-c`, `DOCKER_HOST`, `DOCKER_CONTEXT`, else the current context, resolved by
`docker context inspect`), every command off the read list is guarded (an allow list, not a
detection of writes): `docker ps`, `logs`, `inspect`, `images` and `stats --no-stream`; `df`,
`free`, `uptime`, `pgrep`, `ps`, `true`; `systemctl status`, `show` and `is-active`; `journalctl`
without its writing options; `cat` of `/proc` files; `lxc list`, `info` and `config show`; and the
project's own commands of its `infra-verify` key, word for word (`bash <command>` and
`sh <command>` count as `<command>`). Without that key, no project command is admitted: the plugin
names none.
An output redirection to anything but `/dev/null` is not a read; `scp` and `rsync` to such a host
are never one. A destination is matched by `ssh -G` (aliases, `-o HostName=`, `-J`, `ProxyJump`)
and by its addresses (an IPv4-mapped IPv6 address as its IPv4). Without the key no remote host is
guarded and no Docker context is read; the deny list still holds, also for the command `ssh` runs
on any other host.

Every command is parsed: a guarded program is found in its words, so quotes and escapes
(`dock''er`, `d\\ocker`) hide none. The wrappers `sudo`, `env`, `heavy-slot`, `systemd-run`,
`timeout`, `nice`, `nohup`, `exec`, `command`, `time`, `xargs` and `sshpass` are taken off; `sh -c`,
`bash -c`, `eval`, a shell reading a heredoc, `;`, `&&`, `||`, `|`, `$(...)`, backticks and process
substitutions are walked, and `export VAR=...` is followed. What the guard cannot read is guarded:
a program or a verb named by a variable or a substitution (`${D}er rm`, `"$PY" -m pytest`,
`$(which python)`: name the program itself), a shell reading a pipe, a destination or a
Docker context it cannot resolve, a `-F` ssh config. A text the lexer cannot split (unbalanced
quotes, an unclosed substitution) is guarded when it holds a `$` or a guarded program's name once
its quotes and backslashes are taken off.

Out of reach, on purpose: the hook sees the typed command only. A script that cleans its own
resources (`bash infra/e2e-stack.sh`) and testcontainers run what they run. This guards against an
accident, not against intent.
"""

from __future__ import annotations

import ipaddress
import json
import re
import shlex
import shutil
import socket
import sys
import threading
from collections.abc import Callable, Iterable, Mapping
from typing import Literal

from guard_git import _MASK, _UNMASK, HEREDOC, TIMEOUT_SECONDS, _run
from usine import load, project_root

HOSTS_KEY = "infra-hosts"
VERIFY_KEY = "infra-verify"

# The programs a command the lexer cannot split may hide, searched in its text with quotes and
# backslashes taken off; a `$` may hide any of them.
HIDDEN_PROGRAMS = (
    "docker",
    "systemctl",
    "lxc",
    "networkctl",
    "svc.sh",
    "ssh",
    "scp",
    "sftp",
    "rsync",
    "reboot",
    "shutdown",
    "poweroff",
    "halt",
    "service",
    "invoke-rc.d",
)
MAX_DEPTH = 8
MAX_JUMPS = 4
# What stands for a `$(...)`, a backtick or a process substitution once it is taken out.
SUBSTITUTED = "$FORGE_SUBSTITUTION"

SshConfig = Callable[[list[str]], Mapping[str, str] | None]
AddressLookup = Callable[[str], frozenset[str] | None]
# The endpoint of a Docker context by name (None: the current one), None when it does not resolve.
DockerContext = Callable[[str | None], str | None]


class UnclearError(Exception):
    """A part of the command the guard cannot read: it is guarded."""


class UnsplitError(UnclearError):
    """A text the lexer cannot split into commands: unbalanced quotes, an unclosed substitution."""


# Reading the shell.


def _closing(text: str, start: int) -> int:
    """The index of the `)` that closes the `(` before `start`, quotes and nesting followed."""
    depth = 1
    quote = ""
    index = start
    while index < len(text):
        char = text[index]
        if quote == "'":
            quote = "" if char == "'" else quote
        elif char == "\\":
            index += 1
        elif char in "'\"" and quote in ("", char):
            quote = "" if quote else char
        elif not quote and char == "(":
            depth += 1
        elif not quote and char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise UnsplitError("a `$(` or `<(` that is never closed")


def heredocs(text: str) -> tuple[str, str, str]:
    """`text` without its heredoc bodies, those bodies, and the ones the shell expands.

    The body of a heredoc whose delimiter is unquoted runs its substitutions; a quoted one is data.
    Its quotes are text: an apostrophe in a body opens nothing.
    """
    kept: list[str] = []
    bodies: list[str] = []
    expanded: list[str] = []
    delimiter: str | None = None
    quoted = False
    for line in text.splitlines():
        if delimiter is not None:
            if line.strip() == delimiter:
                delimiter = None
            else:
                bodies.append(line)
                if not quoted:
                    expanded.append(line)
            continue
        kept.append(line)
        if match := HEREDOC.search(line):
            quoted, delimiter = bool(match.group(1)), match.group(2)
    return "\n".join(kept), "\n".join(bodies), "\n".join(expanded)


def substitutions(text: str, backticks: bool = True, quotes: bool = True) -> tuple[str, list[str]]:
    """`text` with each `$(...)`, `<(...)`, `>(...)` and backtick replaced, and what they run.

    A single-quoted part is data. Under PowerShell a backtick is an escape, not a substitution.
    In a heredoc body (`quotes` False) a quote is text and `<(` is no substitution.
    """
    out: list[str] = []
    inner: list[str] = []
    quote = ""
    index = 0
    while index < len(text):
        char = text[index]
        following = text[index + 1 : index + 2]
        if quote == "'":
            quote = "" if char == "'" else quote
        elif char == "\\" and following:
            out.append(text[index : index + 2])
            index += 2
            continue
        elif char == '"':
            quote = "" if quote else '"'
        elif char == "'" and not quote and quotes:
            quote = "'"
        elif following == "(" and (char == "$" or (char in "<>" and not quote and quotes)):
            end = _closing(text, index + 2)
            inner.append(text[index + 2 : end])
            out.append(SUBSTITUTED)
            index = end + 1
            continue
        elif char == "`" and backticks:
            end = text.find("`", index + 1)
            if end < 0:
                raise UnsplitError("a backtick that is never closed")
            inner.append(text[index + 1 : end])
            out.append(SUBSTITUTED)
            index = end + 1
            continue
        out.append(char)
        index += 1
    return "".join(out), inner


def _mask(text: str) -> str:
    """`text` with its quoted or escaped shell characters masked, as `guard_git` does."""
    out: list[str] = []
    quote = ""
    index = 0
    while index < len(text):
        char = text[index]
        if quote == "'":
            quote = "" if char == "'" else quote
            out.append(char if char == "'" else char.translate(_MASK))
        elif char == "\\" and text[index + 1 : index + 2] == "\n" and quote != "'":
            index += 1
        elif char == "\n" and not quote:
            out.append(" ; ")
        elif char == "\\" and index + 1 < len(text):
            index += 1
            masked = text[index].translate(_MASK)
            if quote == '"' or masked == text[index]:
                out.append(char)
            out.append(masked)
        elif quote == '"':
            quote = "" if char == '"' else quote
            out.append(char if char == '"' else char.translate(_MASK))
        else:
            quote = char if char in "'\"" else ""
            out.append(char)
        index += 1
    return "".join(out)


def simple_commands(text: str) -> list[list[str]]:
    """The simple commands of `text`, each as its words, split on every control operator."""
    lexer = shlex.shlex(_mask(text), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r\n"
    result: list[list[str]] = []
    current: list[str] = []
    try:
        for token in lexer:
            if token and set(token) <= set(";&|()"):
                result.append(current)
                current = []
            else:
                current.append(token.translate(_UNMASK))
    except ValueError as error:
        raise UnsplitError(f"a command with unbalanced quotes ({error})") from error
    result.append(current)
    return [words for words in result if words]


def _is_redirection(word: str) -> bool:
    return bool(word) and set(word) <= set("<>&|") and ("<" in word or ">" in word)


def strip_redirections(words: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """The words of a command without its redirections, and those as `(operator, target)`."""
    kept: list[str] = []
    redirections: list[tuple[str, str]] = []
    index = 0
    while index < len(words):
        word = words[index]
        if _is_redirection(word):
            if kept and kept[-1].isdigit():
                kept.pop()  # `2>`: the number is the descriptor
            redirections.append((word, words[index + 1] if index + 1 < len(words) else ""))
            index += 2
            continue
        kept.append(word)
        index += 1
    return kept, redirections


def _writes_a_file(redirections: Iterable[tuple[str, str]]) -> str | None:
    for operator, target in redirections:
        if ">" not in operator or target == "/dev/null":
            continue
        if operator in (">&", "<&") and (target.isdigit() or target == "-"):
            continue  # `2>&1`: a descriptor, no file
        return target
    return None


# Wrappers.

ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
KEYWORDS = frozenset({"!", "{", "}", "then", "do", "else", "elif", "if", "while", "until"})
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})


def _skip(words: list[str], index: int, valued: Iterable[str], letters: str = "") -> int:
    """The index past the options from `index`: `valued` and the short `letters` take a value."""
    valued = frozenset(valued)
    while index < len(words):
        word = words[index]
        if word == "--":
            return index + 1
        if not word.startswith("-") or word == "-":
            return index
        if word in valued:
            index += 2
            continue
        if letters and not word.startswith("--"):
            position = next((at for at, letter in enumerate(word[1:], 1) if letter in letters), 0)
            if position == len(word) - 1:
                index += 2
                continue
        index += 1
    return index


def _operand(words: list[str], index: int, valued: Iterable[str]) -> tuple[str | None, int]:
    """The first operand from `index`, options skipped, and the index after it."""
    index = _skip(words, index, valued)
    return (words[index], index + 1) if index < len(words) else (None, index)


SUDO_VALUED = {
    "--user",
    "--group",
    "--host",
    "--prompt",
    "--close-from",
    "--chdir",
    "--chroot",
    "--role",
    "--type",
    "--command-timeout",
    "--other-user",
}
SYSTEMD_RUN_VALUED = {
    "-p",
    "--property",
    "-E",
    "--setenv",
    "-u",
    "--unit",
    "-M",
    "--machine",
    "-H",
    "--host",
    "--description",
    "--slice",
    "--uid",
    "--gid",
    "--nice",
    "--working-directory",
    "--service-type",
    "--path-property",
    "--socket-property",
    "--timer-property",
    "--on-active",
    "--on-boot",
    "--on-startup",
    "--on-unit-active",
    "--on-unit-inactive",
    "--on-calendar",
}
XARGS_VALUED = {
    "--arg-file",
    "--delimiter",
    "--max-lines",
    "--max-args",
    "--max-procs",
    "--max-chars",
    "--process-slot-var",
}


def _wrapped(name: str, words: list[str]) -> list[str] | None:
    """The command a wrapper runs, or None when `name` is not a wrapper."""
    if name == "sudo":
        # `-s` and `-i` run the rest through a shell: the rest is still the command.
        return words[_skip(words, 1, SUDO_VALUED, "ughpCDRTUrt") :]
    if name == "env":
        index = 1
        while index < len(words):
            word = words[index]
            if word in ("-S", "--split-string") or word.startswith(("-S", "--split-string=")):
                raise UnclearError("`env -S`, whose command is one string the guard does not split")
            if ASSIGNMENT.match(word):
                index += 1
            elif word == "--":
                index += 1
                break
            elif word.startswith("-") and word != "-":
                index += 2 if word in ("-u", "--unset", "-C", "--chdir") else 1
            else:
                break
        return words[index:]
    if name == "heavy-slot":
        index = 1
        while index < len(words) and words[index].startswith("-"):
            if words[index] == "--":
                return words[index + 1 :]
            if words[index] not in ("--timeout", "--label"):
                raise UnclearError(f"`heavy-slot {words[index]}`, an option it does not take")
            index += 2
        return words[index:]
    if name == "systemd-run":
        if "--" in words:
            return words[words.index("--") + 1 :]
        if any(word in ("-S", "--shell") for word in words):
            raise UnclearError("`systemd-run --shell`, an interactive shell")
        return words[_skip(words, 1, SYSTEMD_RUN_VALUED) :]
    if name == "timeout":
        index = _skip(words, 1, {"-s", "--signal", "-k", "--kill-after"})
        return words[index + 1 :]  # the duration, then the command
    if name == "nice":
        return words[_skip(words, 1, {"-n", "--adjustment"}) :]
    if name in ("nohup", "exec"):
        return words[_skip(words, 1, {"-a"}) :]
    if name == "command":
        if any(word in ("-v", "-V") for word in words[1:]):
            return []  # a lookup, which runs nothing
        return words[_skip(words, 1, ()) :]
    if name == "time":
        return words[_skip(words, 1, {"-o", "--output", "-f", "--format"}) :]
    if name == "xargs":
        return words[_skip(words, 1, XARGS_VALUED, "adEILnPs") :]
    if name == "sshpass":
        return words[_skip(words, 1, {"-p", "-f", "-d", "-P"}, "pfdP") :]
    return None


def program_name(word: str) -> str:
    """The name a word runs: its last path part, lowercase, without `.exe`."""
    if "$" in word or "`" in word:
        raise UnclearError(f"the program `{word}`, named by a variable or a substitution")
    name = re.split(r"[/\\]", word)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def unwrap_with_env(words: list[str]) -> tuple[list[str], dict[str, str]]:
    """`unwrap`, and the variables its assignments and wrappers (`env A=1`) set for the command."""
    env: dict[str, str] = {}
    while words:
        if ASSIGNMENT.match(words[0]) or words[0] in KEYWORDS:
            _assign(env, words[:1])
            words = words[1:]
            continue
        inner = _wrapped(program_name(words[0]), words)
        if inner is None:
            return words, env
        _assign(env, words[1 : len(words) - len(inner)])
        words = inner
    return words, env


def unwrap(words: list[str]) -> list[str]:
    """The words of the command that actually runs, assignments, keywords and wrappers taken off."""
    return unwrap_with_env(words)[0]


def _assign(env: dict[str, str], words: Iterable[str]) -> None:
    for word in words:
        if ASSIGNMENT.match(word):
            key, _, value = word.partition("=")
            env[key] = value


def _verb(word: str | None) -> str | None:
    if word is not None and ("$" in word or "`" in word):
        raise UnclearError(f"the verb `{word}`, named by a variable or a substitution")
    return word


def _shell_script(args: list[str]) -> tuple[bool, list[str]]:
    """`(is -c, operands)` of a shell's arguments: with -c the first operand is the script."""
    dash_c = False
    reads_stdin = False
    index = 0
    while index < len(args):
        word = args[index]
        if word == "--":
            index += 1
            break
        if word in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
            index += 2
            continue
        if word.startswith(("-", "+")) and len(word) > 1:
            if not word.startswith("--"):
                dash_c = dash_c or "c" in word[1:]
                reads_stdin = reads_stdin or "s" in word[1:]
            index += 1
            continue
        break
    operands = args[index:]
    return dash_c, ([] if reads_stdin and not dash_c else operands)


# The deny list.

DOCKER_VALUED = {
    "-H",
    "--host",
    "-c",
    "--context",
    "--config",
    "-l",
    "--log-level",
    "--tlscacert",
    "--tlscert",
    "--tlskey",
}
COMPOSE_VALUED = {
    "-f",
    "--file",
    "-p",
    "--project-name",
    "--profile",
    "--env-file",
    "--project-directory",
    "--ansi",
    "--parallel",
    "--progress",
}
DOCKER_GUARDED = frozenset({"rm", "rmi", "kill"})
DOCKER_GUARDED_PAIRS = frozenset(
    {
        (group, "prune")
        for group in ("system", "container", "volume", "builder", "buildx", "image", "network")
    }
    | {
        (group, verb)
        for group in ("container", "image", "volume", "network")
        for verb in ("rm", "remove")
    }
    | {("container", "kill")}
)
SYSTEMCTL_VALUED = {
    "-H",
    "--host",
    "-M",
    "--machine",
    "-p",
    "--property",
    "-P",
    "-t",
    "--type",
    "-n",
    "--lines",
    "-o",
    "--output",
    "-s",
    "--signal",
    "--state",
    "--kill-whom",
    "--kill-value",
    "--root",
    "--image",
    "--what",
    "--job-mode",
    "--when",
    "--message",
    "--drop-in",
    "--capsule",
    "-C",
}
SYSTEMCTL_GUARDED = frozenset(
    {"restart", "try-restart", "reload-or-restart", "try-reload-or-restart", "condrestart"}
    | {"force-reload", "stop", "disable", "mask", "kill"}
    | {"reboot", "soft-reboot", "poweroff", "halt", "kexec", "isolate", "rescue", "emergency"}
)
POWER_COMMANDS = frozenset({"reboot", "shutdown", "poweroff", "halt"})
LXC_VALUED = {"--project"}
LXC_GUARDED = frozenset({"delete", "rm", "stop", "restart", "restore", "pause"})
LXC_EXEC_VALUED = {"--env", "--mode", "--user", "--group", "--cwd", "--project"}
NETWORKCTL_VALUED = {"-n", "--lines"}
NETWORKCTL_READS = frozenset({"status", "list", "lldp"})


def _compose_refusal(args: list[str], shown: str) -> str | None:
    verb, index = _operand(args, 0, COMPOSE_VALUED)
    if _verb(verb) != "down":
        return None
    for word in args[index:]:
        _verb(word)  # `down $FLAGS` cannot be read
        volumes = word in ("-v", "--volumes") or (
            word.startswith("--volumes=") and word.split("=", 1)[1].lower() not in ("false", "0")
        )
        if volumes or (word.startswith("-") and not word.startswith("--") and "v" in word[1:]):
            return f"`{shown} down -v`, which deletes the volumes"
    return None


def _docker_refusal(args: list[str]) -> str | None:
    verb, index = _operand(args, 0, DOCKER_VALUED)
    verb = _verb(verb)
    if verb in DOCKER_GUARDED:
        return f"`docker {verb}`"
    if verb == "compose":
        return _compose_refusal(args[index:], "docker compose")
    sub = _verb(_operand(args, index, ())[0])
    if verb is not None and sub is not None and (verb, sub) in DOCKER_GUARDED_PAIRS:
        return f"`docker {verb} {sub}`"
    return None


def deny_list_refusal(name: str, args: list[str]) -> str | None:
    """Why a local command is guarded, by its program name and arguments, or None."""
    if name == "docker":
        return _docker_refusal(args)
    if name == "docker-compose":
        return _compose_refusal(args, "docker-compose")
    if name == "systemctl":
        verb = _verb(_operand(args, 0, SYSTEMCTL_VALUED)[0])
        return f"`systemctl {verb}`" if verb in SYSTEMCTL_GUARDED else None
    if name in POWER_COMMANDS:
        return f"`{name}`"
    if name == "lxc":
        verb, index = _operand(args, 0, LXC_VALUED)
        verb = _verb(verb)
        if verb in LXC_GUARDED:
            return f"`lxc {verb}`"
        sub, index = _operand(args, index, ()) if verb == "config" else (None, index)
        sub = _verb(sub)
        if sub == "device" and _verb(_operand(args, index, ())[0]) in ("remove", "rm"):
            return "`lxc config device remove`"
        return f"`lxc config {sub}`" if sub in ("set", "unset", "edit") else None
    if name == "networkctl":
        verb = _verb(_operand(args, 0, NETWORKCTL_VALUED)[0])
        return None if verb is None or verb in NETWORKCTL_READS else f"`networkctl {verb}`"
    if name == "svc.sh":
        verb = _verb(args[0] if args else None)
        return f"`svc.sh {verb}`" if verb in ("stop", "uninstall") else None
    if name in ("service", "invoke-rc.d"):
        operands = [word for word in args if not word.startswith("-")]
        verb = _verb(operands[1]) if len(operands) > 1 else None
        return f"`{name} {operands[0]} {verb}`" if verb in SYSTEMCTL_GUARDED else None
    return None


# The read list, the only commands admitted on a declared host.

READ_PROGRAMS = frozenset({"df", "free", "uptime", "pgrep", "ps", "true", ":"})
DOCKER_READS = frozenset({"ps", "logs", "inspect", "images"})
SYSTEMCTL_READS = frozenset({"status", "show", "is-active"})
JOURNALCTL_WRITES = (
    "--vacuum",
    "--rotate",
    "--flush",
    "--sync",
    "--relinquish-var",
    "--smart-relinquish-var",
    "--setup-keys",
    "--update-catalog",
)


def verify_commands(values: Iterable[str]) -> frozenset[tuple[str, ...]]:
    """The commands of the `infra-verify` key, as words; a value shlex cannot split adds none."""
    commands = set()
    for value in values:
        try:
            words = shlex.split(value)
        except ValueError:
            continue
        if words:
            commands.add(tuple(words))
    return frozenset(commands)


def reads(words: list[str], verify: frozenset[tuple[str, ...]] = frozenset()) -> bool:
    """Whether a command (wrappers off) is on the read list or a declared verify command.

    A declared command that meets the deny list is no read: the key does not lift it.
    """
    name, args = program_name(words[0]), words[1:]
    if tuple(words) in verify:
        return deny_list_refusal(name, args) is None
    if name in READ_PROGRAMS:
        return True
    if name == "docker":
        verb, index = _operand(args, 0, DOCKER_VALUED)
        verb = _verb(verb)
        return verb in DOCKER_READS or (verb == "stats" and "--no-stream" in args[index:])
    if name == "systemctl":
        return _verb(_operand(args, 0, SYSTEMCTL_VALUED)[0]) in SYSTEMCTL_READS
    if name == "journalctl":
        return not any(arg.startswith(JOURNALCTL_WRITES) for arg in args)
    if name == "cat":
        files = [arg for arg in args if not arg.startswith("-")]
        return bool(files) and all(
            path.startswith("/proc/") and ".." not in path.split("/") and "$" not in path
            for path in files
        )
    if name == "lxc":
        verb, index = _operand(args, 0, LXC_VALUED)
        verb = _verb(verb)
        return verb in ("list", "ls", "info") or (
            verb == "config" and _operand(args, index, ())[0] == "show"
        )
    return False


# Destinations.

SSH_VALUED = frozenset("BbcDEeFIiJLlmOoPpQRSWw")
SCP_VALUED = frozenset("cDFiJloPSX")
SFTP_VALUED = frozenset("BbcDFiJloPRSsX")


def _host(authority: str) -> str:
    """The host of `[user@]host[:port]`; `ssh -G` prints a jump's address in brackets."""
    host = authority.removeprefix("ssh://").rpartition("@")[2]
    if host.startswith("["):
        return host[1:].partition("]")[0]
    return host if host.count(":") > 1 else host.partition(":")[0]  # a bare IPv6 address


def _remote_host(operand: str) -> str | None:
    """The host of an scp or rsync operand (`host:path`, `host::module`, `scp://`, `rsync://`)."""
    for scheme in ("scp://", "rsync://"):
        if operand.startswith(scheme):
            return _host(operand.removeprefix(scheme).partition("/")[0])
    head, colon, _ = operand.partition(":")
    return head.rpartition("@")[2] if colon and head and "/" not in head else None


def _short_options(
    args: list[str], valued: frozenset[str]
) -> tuple[list[tuple[str, str]], list[str]]:
    """`(options that take a value, operands)` of an scp or rsync call."""
    options: list[tuple[str, str]] = []
    operands: list[str] = []
    words = iter(args)
    for word in words:
        if word.startswith("-") and len(word) > 1:
            letter = next((char for char in word[1:] if char in valued), None)
            if letter is not None:
                options.append((f"-{letter}", word.partition(letter)[2] or next(words, "")))
        else:
            operands.append(word)
    return options, operands


def parse_ssh(args: list[str]) -> tuple[str | None, list[tuple[str, str]], list[str]]:
    """`(destination, options that take a value, remote command words)` of an ssh call.

    ssh reads options after its destination too, until the first word of its command.
    """
    options: list[tuple[str, str]] = []
    destination: str | None = None
    index = 0
    while index < len(args):
        word = args[index]
        if word == "--":
            index += 1
            if destination is None and index < len(args):
                destination = args[index]
                index += 1
            break
        if word.startswith("-") and len(word) > 1:
            letter = next((char for char in word[1:] if char in SSH_VALUED), None)
            if letter is not None:
                value = word.partition(letter)[2]
                if not value:
                    index += 1
                    value = args[index] if index < len(args) else ""
                options.append((f"-{letter}", value))
            index += 1
            continue
        if destination is not None:
            break
        destination = word
        index += 1
    return destination, options, args[index:]


def _address(text: str) -> str | None:
    """An IP address in one spelling, an IPv4-mapped IPv6 one as its IPv4; None for a name."""
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    mapped = getattr(address, "ipv4_mapped", None)
    return str(mapped or address)


class Hosts:
    """The declared hosts of the `infra-hosts` key, matched through `ssh -G` and a resolver."""

    def __init__(
        self, declared: Iterable[str], ssh_config: SshConfig, addresses_of: AddressLookup
    ) -> None:
        self.declared = [_host(value.strip()) for value in declared if value.strip()]
        self._ssh_config = ssh_config
        self._addresses_of = addresses_of
        self._names: frozenset[str] | None = None
        self._addresses: frozenset[str] | None = None

    def _addresses_of_name(self, name: str) -> frozenset[str]:
        if (address := _address(name)) is not None:
            return frozenset({address})
        found = self._addresses_of(name)
        if found is None:
            raise UnclearError(f"`{name}`, which the resolver did not answer in time")
        return frozenset(_address(value) or value for value in found)

    def _declared_names(self) -> frozenset[str]:
        if self._names is None:
            names = set(self.declared)
            for value in self.declared:
                printed = self._ssh_config([value])
                if printed is not None and printed.get("hostname"):
                    names.add(printed["hostname"])
            self._names = frozenset(names)
        return self._names

    def _declared_addresses(self) -> frozenset[str]:
        if self._addresses is None:
            self._addresses = frozenset().union(
                *(self._addresses_of_name(name) for name in self._declared_names())
            )
        return self._addresses

    def instance(self, name: str) -> bool:
        """Whether an lxc instance (`[remote:]name`) is a declared host, by name."""
        if "$" in name or "`" in name:
            raise UnclearError(f"the instance `{name}`, named by a variable or a substitution")
        return name in self.declared or name.rpartition(":")[2] in self.declared

    def reaches(self, destination: str, options: list[tuple[str, str]], jumps: int = 0) -> bool:
        """Whether an ssh destination reaches a declared host; `UnclearError` when it cannot tell."""
        if not destination or "$" in destination or "`" in destination:
            raise UnclearError(f"the destination `{destination}`")
        if any(flag == "-F" for flag, _ in options):
            raise UnclearError(f"`{destination}` under a `-F` config the guard does not read")
        if jumps > MAX_JUMPS:
            raise UnclearError(
                f"`{destination}`, at the end of a ProxyJump chain too deep to follow"
            )
        if _host(destination) in self.declared:
            return True
        given = [word for flag, value in options if flag in ("-o", "-J") for word in (flag, value)]
        printed = self._ssh_config([*given, destination])
        if printed is None:
            raise UnclearError(f"`{destination}`, for which `ssh -G` printed no configuration")
        name = printed.get("hostname", _host(destination))
        if name in self._declared_names():
            return True
        if self._addresses_of_name(name) & self._declared_addresses():
            return True
        chain = [_host(jump.strip()) for jump in printed.get("proxyjump", "").split(",")]
        return any(self.reaches(jump, [], jumps + 1) for jump in chain if jump not in ("", "none"))


# The judge.


class Judge:
    """Walks a command and says why it is guarded, or None."""

    def __init__(
        self,
        hosts: Hosts,
        verify: frozenset[tuple[str, ...]] = frozenset(),
        powershell: bool = False,
        docker_context: DockerContext = lambda _name: None,
    ) -> None:
        self.hosts = hosts
        self.verify = verify
        self.powershell = powershell
        self.docker_context = docker_context

    def text(
        self,
        text: str,
        remote: str | None,
        depth: int,
        env: Mapping[str, str] | None = None,
        enclosing_bodies: str = "",
    ) -> str | None:
        """A command line, run locally (`remote` None) or on the declared host `remote`.

        `env` holds the variables set before it; an `export` or a bare assignment adds to them for
        the commands that follow. The heredoc bodies are set apart before the substitutions are
        read; a substitution without bodies of its own reads those of the text around it
        (`enclosing_bodies`), since its heredoc may have been cut there.
        """
        if depth > MAX_DEPTH:
            raise UnclearError("commands nested deeper than the guard follows")
        shell_env = dict(env or {})
        kept, bodies, expanded = heredocs(text)
        bodies = bodies or enclosing_bodies
        outer, inner = substitutions(kept, backticks=not self.powershell)
        inner += substitutions(expanded, backticks=not self.powershell, quotes=False)[1]
        for part in inner:
            if reason := self.text(part, remote, depth + 1, shell_env, bodies):
                return reason
        for words in simple_commands(outer):
            bare = strip_redirections(words)[0]
            if bare and bare[0] == "export":
                _assign(shell_env, bare[1:])
            elif all(ASSIGNMENT.match(word) for word in bare):
                _assign(shell_env, bare)
            if reason := self.command(words, remote, bodies, depth, shell_env):
                return reason
            if (context := _context_used(bare)) is not None:
                shell_env["DOCKER_CONTEXT"] = context  # the context of the commands that follow
        return None

    def command(
        self,
        words: list[str],
        remote: str | None,
        bodies: str,
        depth: int,
        env: Mapping[str, str] | None = None,
    ) -> str | None:
        words, redirections = strip_redirections(words)
        if remote is not None and (target := _writes_a_file(redirections)):
            return f"a redirection to `{target}`, which writes on the declared host `{remote}`"
        if self.powershell and words:
            words = _powershell_value(words)
        words, assigned = unwrap_with_env(words)
        env = {**(env or {}), **assigned}
        if not words:
            return None
        name, args = program_name(words[0]), words[1:]
        if name in SHELLS:
            dash_c, operands = _shell_script(args)
            if dash_c and operands:
                return self.text(operands[0], remote, depth + 1, env)
            if operands:
                # a script and its arguments
                return self.command(operands, remote, "", depth + 1, env)
            if bodies and any(operator.startswith("<<") for operator, _ in redirections):
                return self.text(bodies, remote, depth + 1, env)
            raise UnclearError(
                f"`{' '.join(words)}`, a shell that reads its commands from standard input"
            )
        if name == "eval":
            return self.text(" ".join(args), remote, depth + 1, env)
        if remote is not None:
            if reads(words, self.verify):
                return None
            return f"`{' '.join(words)[:120]}`, off the read list, on the declared host `{remote}`"
        if reason := deny_list_refusal(name, args):
            return reason
        if name == "ssh":
            return self._ssh(args, depth)
        if name in ("scp", "rsync") and self.hosts.declared:
            options, operands = _short_options(args, SCP_VALUED if name == "scp" else frozenset())
            for operand in operands:
                if "$" in operand or "`" in operand:
                    raise UnclearError(f"the {name} operand `{operand}`")
                host = _remote_host(operand)
                if host and self.hosts.reaches(host, options):
                    return f"`{name}` to or from the declared host `{host}`"
        if name == "sftp" and self.hosts.declared:
            options, operands = _short_options(args, SFTP_VALUED)
            if operands:
                host = _host(operands[0].removeprefix("sftp://").partition("/")[0])
                if self.hosts.reaches(host, options):
                    return f"`sftp` to the declared host `{host}`"
        if name in ("docker", "docker-compose") and self.hosts.declared:
            if host := self._docker_host(name, words, env):
                return (
                    f"`{' '.join(words)[:120]}`, off the read list, on the declared host `{host}`"
                    " through Docker's endpoint"
                )
        if name == "lxc":
            return self._lxc(args, depth)
        return None

    def _docker_host(self, name: str, words: list[str], env: Mapping[str, str]) -> str | None:
        """The declared host a Docker call that is no read acts on, by its endpoint, or None.

        The endpoint comes from `-H`, `--host`, `--context`, `-c`, `DOCKER_HOST` and
        `DOCKER_CONTEXT`, every one given being judged; without any, from the current context.
        A context that does not resolve cannot be read.
        """
        endpoints: list[str] = []
        contexts: list[str | None] = []
        args = words[1:]
        index = 0
        while name == "docker" and index < len(args) and args[index].startswith("-"):
            flag, equals, value = args[index].partition("=")
            if flag in ("-H", "--host", "-c", "--context"):
                if not equals:
                    index += 1
                    value = args[index] if index < len(args) else ""
                (endpoints if flag in ("-H", "--host") else contexts).append(value)
            elif flag[:2] in ("-H", "-c") and not flag.startswith("--") and len(flag) > 2:
                (endpoints if flag[1] == "H" else contexts).append(args[index][2:])
            elif args[index] in DOCKER_VALUED:
                index += 1
            index += 1
        endpoints += [env["DOCKER_HOST"]] if env.get("DOCKER_HOST") else []
        contexts += [env["DOCKER_CONTEXT"]] if env.get("DOCKER_CONTEXT") else []
        if not endpoints and not contexts:
            if reads(words, self.verify):
                return None
            contexts.append(None)
        for context in contexts:
            resolved = self.docker_context(_verb(context))
            if resolved is None:
                raise UnclearError(
                    f"the Docker context `{context or 'current'}`, which does not resolve"
                )
            endpoints.append(resolved)
        for endpoint in endpoints:
            _verb(endpoint)
            scheme, separator, rest = endpoint.strip().partition("://")
            if separator and scheme in ("unix", "npipe", "fd"):
                continue
            host = _host((rest if separator else scheme).partition("/")[0])
            if host and self.hosts.reaches(host, []) and not reads(words, self.verify):
                return host
        return None

    def _ssh(self, args: list[str], depth: int) -> str | None:
        destination, options, remote_words = parse_ssh(args)
        if self.hosts.declared:
            if destination is None:
                raise UnclearError("an ssh call without a destination")
            if self.hosts.reaches(destination, options):
                if not remote_words:
                    return f"an interactive ssh session on the declared host `{destination}`"
                return self.text(" ".join(remote_words), destination, depth + 1)
        # Any other host: the remote command still meets the deny list.
        return self.text(" ".join(remote_words), None, depth + 1) if remote_words else None

    def _lxc(self, args: list[str], depth: int) -> str | None:
        verb, index = _operand(args, 0, LXC_VALUED)
        if verb in ("shell", "console") and self.hosts.declared:
            instance = _operand(args, index, LXC_VALUED)[0]
            if instance is not None and self.hosts.instance(instance):
                return f"`lxc {verb}` on the declared instance `{instance}`"
            return None
        if verb == "file" and self.hosts.declared:
            sub, index = _operand(args, index, LXC_VALUED)
            if _verb(sub) not in ("push", "edit", "delete"):
                return None
            # The values of its options (`--mode 0644`, `--uid 0`) hold no `/`.
            for word in args[index:]:
                instance = word.partition("/")[0]
                if not word.startswith("-") and "/" in word and self.hosts.instance(instance):
                    return f"`lxc file {sub}` on the declared instance `{instance}`"
            return None
        if verb != "exec":
            return None
        instance, index = _operand(args, index, LXC_EXEC_VALUED)
        if instance is None:
            return None
        rest = args[index:]
        inner = (
            rest[rest.index("--") + 1 :]
            if "--" in rest
            else rest[_skip(rest, 0, LXC_EXEC_VALUED) :]
        )
        if not inner:
            return None
        declared = bool(self.hosts.declared) and self.hosts.instance(instance)
        # `lxc exec` runs its words without a shell: they are one command already.
        return self.command(inner, instance if declared else None, "", depth + 1)


def _context_used(words: list[str]) -> str | None:
    """The context `docker context use <name>` switches to, or None."""
    try:
        inner = unwrap(words)
    except UnclearError:
        return None  # judged, and held, as the command it is
    is_use = (
        len(inner) > 3 and program_name(inner[0]) == "docker" and inner[1:3] == ["context", "use"]
    )
    return inner[3] if is_use else None


def _powershell_value(words: list[str]) -> list[str]:
    """Under PowerShell, the command of `$name = <command>`: the variable is no program."""
    match = re.match(r"^\$[\w:.]+([-+*/%]?=)(.*)$", words[0])
    if match is not None:
        return ([match.group(2)] if match.group(2) else []) + words[1:]
    if words[0].startswith("$") and len(words) > 1 and re.fullmatch(r"[-+*/%]?=", words[1]):
        return words[2:]
    return words


def _may_hide(command: str) -> bool:
    """Whether a text the lexer cannot split may hide a guarded program."""
    flat = re.sub(r"[\\'\"]", "", command).lower()
    return "$" in flat or any(program in flat for program in HIDDEN_PROGRAMS)


def verdict(
    event: Mapping[str, object],
    declared: Iterable[str],
    ssh_config: SshConfig,
    addresses_of: AddressLookup,
    verify: Iterable[str] = (),
    docker_context: DockerContext = lambda _name: None,
) -> tuple[Literal["deny", "ask"], str] | None:
    """`("deny" | "ask", reason)` for a shell call the guard holds, or None.

    `declared` holds the values of the `infra-hosts` key, `verify` those of `infra-verify`;
    `docker_context` resolves a Docker context to its endpoint. Every command is parsed: the
    guarded programs are found in its words, not in its text.
    """
    tool_input = event.get("tool_input")
    command = str(tool_input.get("command", "")) if isinstance(tool_input, Mapping) else ""
    judge = Judge(
        Hosts(declared, ssh_config, addresses_of),
        verify_commands(verify),
        powershell=event.get("tool_name") == "PowerShell",
        docker_context=docker_context,
    )
    try:
        found = judge.text(command, None, 0)
    except UnsplitError as unsplit:
        # A text bash cannot run either, but whose earlier lines it may: held when it may hide a
        # guarded program or a variable.
        found = (
            f"the guard cannot read {unsplit}, and guards what it cannot read"
            if _may_hide(command)
            else None
        )
    except UnclearError as unclear:
        found = f"the guard cannot read {unclear}, and guards what it cannot read"
    if found is None:
        return None
    reason = (
        f"{found}: an infrastructure gesture is the human's. A subagent never makes it; the main"
        " session asks the human, who may also type it with `! <command>`"
    )
    return ("deny" if event.get("agent_id") else "ask"), reason


def ssh_config_via_ssh() -> SshConfig:
    """`ssh -G`, which prints ssh's configuration and connects to nothing."""

    def printed(args: list[str]) -> Mapping[str, str] | None:
        ssh = shutil.which("ssh")
        # No shell: ssh resolved by shutil.which, `-G`, and the words the guard kept.
        completed = _run([ssh, "-G", *args], None) if ssh else None
        if completed is None or completed.returncode != 0:
            return None
        lines = (line.partition(" ") for line in completed.stdout.splitlines())
        return {key.lower(): value for key, _, value in lines}

    return printed


def docker_context_via_docker() -> DockerContext:
    """`docker context inspect`, which reads the client's configuration and connects to nothing."""

    def endpoint(name: str | None) -> str | None:
        docker = shutil.which("docker")
        if docker is None:
            return None
        # No shell: docker resolved by shutil.which, a fixed argv and the context's name.
        completed = _run(
            [docker, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]
            + (["--", name] if name else []),
            None,
        )
        if completed is None or completed.returncode != 0 or not completed.stdout.strip():
            return None
        return completed.stdout.strip()

    return endpoint


def addresses_via_dns(name: str) -> frozenset[str] | None:
    """What `getaddrinfo` answers within the timeout, which it does not take itself."""
    found: list[frozenset[str]] = []

    def resolve() -> None:
        try:
            found.append(frozenset(str(info[4][0]) for info in socket.getaddrinfo(name, None)))
        except (socket.gaierror, UnicodeError):
            found.append(frozenset())  # a name that resolves to nothing, ssh cannot reach either

    # A daemon thread: one stuck in the resolver past the timeout does not hold the hook's exit.
    worker = threading.Thread(target=resolve, daemon=True)
    worker.start()
    worker.join(TIMEOUT_SECONDS)
    return found[0] if found else None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        event = None
    found: tuple[str, str] | None
    if not isinstance(event, dict) or not isinstance(event.get("tool_input"), dict):
        found = ("deny", "the guard could not read the call")
    else:
        config = load(project_root(event))
        found = verdict(
            event,
            config.get(HOSTS_KEY, []),
            ssh_config_via_ssh(),
            addresses_via_dns,
            verify=config.get(VERIFY_KEY, []),
            docker_context=docker_context_via_docker(),
        )
    if found is None:
        return 0
    if found[0] == "deny":
        sys.stderr.write(f"Blocked by the forge plugin (guard_infra): {found[1]}.\n")
        return 2
    ask = {"hookEventName": "PreToolUse", "permissionDecision": "ask"}
    sys.stdout.write(
        json.dumps({"hookSpecificOutput": {**ask, "permissionDecisionReason": found[1]}})
    )
    return 0


def guarded_main() -> int:
    """`main`, failing closed: a crash of the guard refuses the command and says so."""
    try:
        return main()
    except Exception as error:  # noqa: BLE001 - any failure of the guard must refuse the command
        sys.stderr.write(
            f"guard_infra failed ({type(error).__name__}: {error}): the command is refused as a"
            " precaution. This is not a rule of the repository; retry, and tell the human if it"
            " persists.\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(guarded_main())
