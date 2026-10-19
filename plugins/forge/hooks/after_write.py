"""PostToolUse hook: what an agent writes carries no em dash.

After an Edit or a Write, an em dash beyond the file's allowance is reported with exit code 2,
which Claude Code shows to the agent so it fixes the file before going on. The allowances are
the project's, in the file the `em-dash-allowances` key of `docs/agents/usine.md` names, one
`<count> <path>` line per file; without that key no file has any.

Formatting (ruff, Prettier) is each project's own, in its `.claude/settings.json`. A file
written through a shell command (a heredoc, `sed`) does not come through here: the project's
commit hook is the net for those.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path

from usine import load, project_root

EM_DASH = chr(0x2014)
ALLOWANCES_KEY = "em-dash-allowances"


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
    content = path.read_text(encoding="utf-8", errors="replace")
    problem = em_dash_problem(relative, content, load_allowances(root))
    if problem is None:
        return 0
    sys.stderr.write(problem + "\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
