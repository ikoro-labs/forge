"""PostToolUse hook: what an agent writes is formatted, and carries no em dash.

After an Edit or a Write, the commands of the `format-on-write` key of `docs/agents/usine.md`
whose pattern matches the file run on it, in the file's order, then an em dash beyond the file's
allowance is reported. Both report with exit code 2, which Claude Code shows to the agent so it
fixes the file before going on; the write itself stays.

A `format-on-write` line is `<pattern> | <command>`. The pattern is compared with the whole
relative POSIX path, case included: `**/` (any directories, or none), `*` and `?` (not a `/`),
`{a,b}` (alternatives, not nested); anything else is literal. The command is split like a POSIX
shell would, run without a shell from the project root, with the file's absolute path as its last
argument. Each command has `COMMAND_TIMEOUT` seconds, all of them together `TOTAL_TIMEOUT`.
Each runs in its own process group, killed whole at the delay. On Windows a `.cmd` or `.bat`
formatter goes through cmd.exe, so a path with a cmd.exe metacharacter is refused, not quoted.
Without the key nothing is formatted and no formatter is guessed.

The em dash allowances are the project's, in the file the `em-dash-allowances` key names, one
`<count> <path>` line per file; without that key no file has any.

A file written through a shell command (a heredoc, `sed`) does not come through here: the
project's commit hook is the net for those.
"""

from __future__ import annotations

import json
import math
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import IO

from doc_rules import doc_problems
from handoff_header import ProcessGroup, group_options
from usine import load, matches, project_root, split_value
from utf8_stdio import use_utf8

EM_DASH = chr(0x2014)
ALLOWANCES_KEY = "em-dash-allowances"
FORMAT_KEY = "format-on-write"
COMMAND_TIMEOUT = 30
TOTAL_TIMEOUT = 120
TAIL_LINES = 20
TAIL_BYTES = 2000
READ_BYTES = 64 * 1024
WINDOWS = sys.platform == "win32"
# CreateProcess runs a `.cmd` or `.bat` through cmd.exe, which reads these as syntax, not as text.
CMD_METACHARACTERS = frozenset('&|<>^%!"()')
CMD_SCRIPTS = (".cmd", ".bat")


def em_dash_problem(path: str, content: str, allowances: Mapping[str, int]) -> str | None:
    count = content.count(EM_DASH)
    if count <= allowances.get(path, 0):
        return None
    return f"{path} holds {count} em dash: replace each with a comma, a colon or parentheses"


def parse_allowances(text: str) -> dict[str, int]:
    allowances: dict[str, int] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            count, _, path = line.partition(" ")
            if count.isdigit():
                allowances[path.strip()] = int(count)
    return allowances


def load_allowances(root: Path) -> dict[str, int]:
    listing = load(root).get(ALLOWANCES_KEY)
    if not listing:
        return {}
    try:
        return parse_allowances((root / listing[-1]).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return {}


def _split_command(command: str) -> list[str]:
    """The command split like a POSIX shell would; empty when it cannot be (an unclosed quote)."""
    try:
        return shlex.split(command)
    except ValueError:
        return []


def _tail(sink: IO[bytes]) -> str:
    """The end of what the tool printed: `TAIL_LINES` lines and `TAIL_BYTES` bytes at most.

    Only the last `READ_BYTES` of the file are read, so a tool that prints a lot costs nothing. The
    text is decoded before the byte cap, so a byte that is not UTF-8 never grows past it, and a cut
    that lands inside a character drops that character.
    """
    size = sink.seek(0, 2)
    sink.seek(max(0, size - READ_BYTES))
    text = sink.read().decode("utf-8", errors="replace").rstrip()
    kept = "\n".join(text.splitlines()[-TAIL_LINES:]).encode("utf-8")[-TAIL_BYTES:]
    return kept.decode("utf-8", errors="ignore")


def _run_command(
    command: str, path: Path, root: Path, timeout: float
) -> tuple[str | None, str]:
    """Why the command failed on the file (`exit 3`, `timed out after 30s`...) or None, and the end
    of its output."""
    argv = _split_command(command)
    executable = shutil.which(argv[0])
    if executable is None:
        return "command not found", ""
    if (
        WINDOWS
        and executable.lower().endswith(CMD_SCRIPTS)
        and CMD_METACHARACTERS & set(str(path))
    ):
        return "not run: the path holds a cmd.exe metacharacter", ""
    try:
        # The output goes to a file, not a pipe: a grandchild of `uv run` would hold a pipe open.
        with tempfile.TemporaryFile() as sink:
            process = subprocess.Popen(
                [executable, *argv[1:], str(path)],
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=sink,
                stderr=subprocess.STDOUT,
                **group_options(),
            )
            group = ProcessGroup(process)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                group.kill()
                return f"timed out after {max(1, math.ceil(timeout))}s", _tail(sink)
            finally:
                group.close()
            if process.returncode == 0:
                return None, ""
            return f"exit {process.returncode}", _tail(sink)
    except FileNotFoundError:
        return "command not found", ""
    except OSError as error:
        return f"could not start: {error.strerror or type(error).__name__}", ""


class _Deadline:
    """The `TOTAL_TIMEOUT` seconds of one write, started with the hook and spent by every key."""

    def __init__(self) -> None:
        self.started = time.monotonic()

    def left_for_a_command(self) -> float:
        """The seconds the next command may take; zero or less once the write has none left."""
        return min(COMMAND_TIMEOUT, TOTAL_TIMEOUT - (time.monotonic() - self.started))


def _run_key(
    key: str,
    config: Mapping[str, list[str]],
    root: Path,
    path: Path,
    relative: str,
    deadline: _Deadline,
) -> list[str]:
    """The problems of every `<pattern> | <command>` line of `key` whose pattern matches the file."""
    problems: list[str] = []
    for value in config.get(key, []):
        parts = split_value(value, 2)
        if parts is None or not _split_command(parts[1]):
            problems.append(f"{key}: `{value}` is not `<pattern> | <command>`, line ignored")
            continue
        pattern, command = parts
        if not matches(pattern, relative):
            continue
        timeout = deadline.left_for_a_command()
        if timeout <= 0:
            reason: str | None = f"timed out after {TOTAL_TIMEOUT}s"
            output = ""
        else:
            reason, output = _run_command(command, path, root, timeout)
        if reason:
            problem = f"{key}: {command} failed on {relative} ({reason})"
            problems.append(f"{problem}\n{output}" if output else problem)
    return problems


def main() -> int:
    event = json.load(sys.stdin)
    file_path = event.get("tool_input", {}).get("file_path")
    if not file_path:
        return 0
    root = project_root(event).resolve()
    path = Path(file_path)
    try:
        relative = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return 0  # outside the project: not ours to judge
    if not path.is_file():
        return 0
    config = load(root)
    problems = _run_key(FORMAT_KEY, config, root, path.resolve(), relative, _Deadline())
    content = path.read_text(encoding="utf-8", errors="replace")
    if problem := em_dash_problem(relative, content, load_allowances(root)):
        problems.append(problem)
    problems.extend(doc_problems(config, root, relative, content))
    if not problems:
        return 0
    sys.stderr.write("".join(line + "\n" for line in problems))
    return 2


if __name__ == "__main__":
    use_utf8()
    raise SystemExit(main())
