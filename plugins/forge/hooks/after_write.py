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
Without the key nothing is formatted and no formatter is guessed.

The em dash allowances are the project's, in the file the `em-dash-allowances` key names, one
`<count> <path>` line per file; without that key no file has any.

A file written through a shell command (a heredoc, `sed`) does not come through here: the
project's commit hook is the net for those.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path

from usine import load, project_root, split_value

EM_DASH = chr(0x2014)
ALLOWANCES_KEY = "em-dash-allowances"
FORMAT_KEY = "format-on-write"
COMMAND_TIMEOUT = 30
TOTAL_TIMEOUT = 120


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


def pattern_regex(pattern: str) -> re.Pattern[str]:
    """The regular expression of a path pattern: `**/`, `*`, `?` and `{a,b}`, the rest literal."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**/", i) and (i == 0 or pattern[i - 1] == "/"):
            out.append("(?:.*/)?")
            i += 3
            continue
        end = pattern.find("}", i) if char == "{" else -1
        if char == "{" and end != -1 and "{" not in pattern[i + 1 : end]:
            choices = pattern[i + 1 : end].split(",")
            out.append("(?:" + "|".join(re.escape(choice) for choice in choices) + ")")
            i = end
        elif char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
        i += 1
    return re.compile("".join(out))


def matches(pattern: str, relative: str) -> bool:
    return pattern_regex(pattern).fullmatch(relative) is not None


def split_command(command: str) -> list[str]:
    """The command split like a POSIX shell would; empty when it cannot be (an unclosed quote)."""
    try:
        return shlex.split(command)
    except ValueError:
        return []


def run_formatter(command: str, path: Path, root: Path, timeout: float) -> str | None:
    """Why the command failed on the file (`exit 3`, `timed out after 30s`...), or None."""
    argv = split_command(command)
    executable = shutil.which(argv[0])
    if executable is None:
        return "command not found"
    try:
        # The output goes to a file, not a pipe: a grandchild of `uv run` would hold a pipe open.
        with tempfile.TemporaryFile() as sink:
            done = subprocess.run(
                [executable, *argv[1:], str(path)],
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=sink,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
    except subprocess.TimeoutExpired:
        return f"timed out after {int(timeout)}s"
    except OSError:
        return "command not found"
    return None if done.returncode == 0 else f"exit {done.returncode}"


def format_problems(
    config: Mapping[str, list[str]], root: Path, path: Path, relative: str
) -> list[str]:
    problems: list[str] = []
    started = time.monotonic()
    for value in config.get(FORMAT_KEY, []):
        parts = split_value(value, 2)
        if parts is None or not split_command(parts[1]):
            problems.append(f"{FORMAT_KEY}: `{value}` is not `<pattern> | <command>`, line ignored")
            continue
        pattern, command = parts
        if not matches(pattern, relative):
            continue
        timeout = min(COMMAND_TIMEOUT, TOTAL_TIMEOUT - (time.monotonic() - started))
        if timeout <= 0:
            reason: str | None = f"timed out after {TOTAL_TIMEOUT}s"
        else:
            reason = run_formatter(command, path, root, timeout)
        if reason:
            problems.append(f"{FORMAT_KEY}: {command} failed on {relative} ({reason})")
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
    problems = format_problems(config, root, path.resolve(), relative)
    content = path.read_text(encoding="utf-8", errors="replace")
    if problem := em_dash_problem(relative, content, load_allowances(root)):
        problems.append(problem)
    if not problems:
        return 0
    sys.stderr.write("".join(line + "\n" for line in problems))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
