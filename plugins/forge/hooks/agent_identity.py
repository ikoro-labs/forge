"""The GitHub identity of the agents: an installation token of the project's GitHub App.

Two keys of `docs/agents/usine-gardes.md` (`usine.SENSITIVE_KEYS`, read as `origin/main` holds it)
turn it on: `agent-token-command`, a command that prints an installation token on one line, and
`agent-login`, the login the App's gestures carry. With both, a gesture that writes on GitHub is made
with a token that starts with `ghs_`; `guard_git` refuses it otherwise, and never takes the human's
token in its place. With one of them absent, nothing here refuses anything.

The module depends on nothing but the standard library: `guard_git` and the dispatcher import it.
No token is ever written, in a message, a journal or a file: a message names the command by its key.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping

TOKEN_KEY = "agent-token-command"
LOGIN_KEY = "agent-login"
PREFIX = "ghs_"
# The variables `gh` reads for a token, in the order it reads them: the first one set decides.
TOKEN_VARIABLES = ("GH_TOKEN", "GITHUB_TOKEN")
# The command of `agent-token-command` signs and calls GitHub: it may take a while, never forever.
TIMEOUT_SECONDS = 30.0


class IdentityError(Exception):
    """The installation token cannot be had. The message names the key, never the command or a token."""


def is_agent_token(env: Mapping[str, str]) -> bool:
    """Whether the token `gh` would send starts with `ghs_`: `GH_TOKEN`, else `GITHUB_TOKEN`.

    Only the prefix is read, never the length or the form of the rest. A `GH_TOKEN` of the human's
    beside an installation `GITHUB_TOKEN` is what `gh` sends: it is not an agent's token.
    """
    for name in TOKEN_VARIABLES:
        if token := env.get(name, ""):
            return token.startswith(PREFIX)
    return False


def _key_problem(config: Mapping[str, list[str]]) -> str | None:
    """Why a key of the identity cannot be read (one line each, not empty), or None."""
    for key in (TOKEN_KEY, LOGIN_KEY):
        lines = config.get(key, [])
        if len(lines) != 1:
            listed = ", ".join(f"- `{key}` : `{value}`" for value in lines)
            return f"the `{key}` key takes one line, and has {len(lines)}: {listed}"
        if not lines[0].strip():
            return f"the `{key}` key has an empty value"
    return None


def asked(config: Mapping[str, list[str]]) -> bool:
    """Whether the project asks for the identity of the agents: both keys are there."""
    return bool(config.get(TOKEN_KEY)) and bool(config.get(LOGIN_KEY))


def write_refusal(config: Mapping[str, list[str]], env: Mapping[str, str], gesture: str) -> str | None:
    """Why `gesture`, a write on GitHub, is refused for the identity of the agents, or None.

    None when the project does not ask for it (a key absent) and when the environment holds an
    installation token. A key that cannot be read refuses: closed by default.
    """
    if not asked(config):
        return None
    if problem := _key_problem(config):
        return f"{problem}: `{gesture}` writes on GitHub, and the identity of the agents cannot be judged"
    if is_agent_token(env):
        return None
    login = config[LOGIN_KEY][0]
    return (
        f"`{gesture}` writes on GitHub, and a write is made under the identity of the agents"
        f" (`{LOGIN_KEY}` : `{login}`, a GitHub App): the environment of this session holds no"
        f" installation token (`GH_TOKEN` or `GITHUB_TOKEN` starting with `{PREFIX}`). Launch the agent"
        f" with the token that the command of the `{TOKEN_KEY}` key prints; the human's own token is"
        f" never taken in its place"
    )


def mcp_refusal(config: Mapping[str, list[str]], tool: str) -> str | None:
    """Why a write by the MCP GitHub tool `tool` is refused for the identity of the agents, or None.

    The MCP server holds its own token, which no check of the environment covers: with both keys
    there, such a write is refused whatever the token, and the agents write by `gh`.
    """
    if not asked(config):
        return None
    if problem := _key_problem(config):
        return f"{problem}: `{tool}` writes on GitHub, and the identity of the agents cannot be judged"
    return (
        f"`{tool}` writes on GitHub through the token of its MCP server, which cannot be the identity of"
        f" the agents (`{LOGIN_KEY}` : `{config[LOGIN_KEY][0]}`): write by `gh`, under the installation"
        f" token that the `{TOKEN_KEY}` key gives"
    )


def token_command(config: Mapping[str, list[str]]) -> str:
    """The command of the `agent-token-command` key: one line, not empty, or `IdentityError`."""
    lines = config.get(TOKEN_KEY, [])
    if len(lines) != 1 or not lines[0].strip():
        raise IdentityError(f"the `{TOKEN_KEY}` key takes one non-empty line, and has {len(lines)}")
    return lines[0]


def fresh_token(command: str, timeout: float = TIMEOUT_SECONDS) -> str:
    """The installation token that `command` prints, or `IdentityError`: no agent is launched without it.

    The command runs in the shell (it is the project's, read on `origin/main`), with no input; it exits 0
    and prints one line that starts with `ghs_`. Its output and its text are never put in an error: a
    failure names the key and what went wrong, and the human's token is never taken in its place.
    """
    try:
        done = subprocess.run(  # noqa: S602 - the project's own command, a protected key
            command,
            shell=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise IdentityError(f"the command of the `{TOKEN_KEY}` key timed out after {timeout:g} s") from None
    except OSError:
        raise IdentityError(f"the command of the `{TOKEN_KEY}` key could not be started") from None
    if done.returncode != 0:
        raise IdentityError(f"the command of the `{TOKEN_KEY}` key failed (exit {done.returncode})")
    lines = [line.strip() for line in done.stdout.splitlines() if line.strip()]
    if not lines:
        raise IdentityError(f"the command of the `{TOKEN_KEY}` key printed no token")
    if len(lines) > 1:
        raise IdentityError(f"the command of the `{TOKEN_KEY}` key printed more than one line")
    if not lines[0].startswith(PREFIX):
        raise IdentityError(f"the command of the `{TOKEN_KEY}` key printed a token that does not start with `{PREFIX}`")
    return lines[0]
