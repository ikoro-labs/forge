"""The project's factory configuration, `docs/agents/usine.md`, as the hooks read it.

Each key is a Markdown list item, the key and its value in backticks:

    - `domain-arbiter` : `pricing-arbiter`
    - `install` : `uv sync --locked`
    - `install` : `pnpm install --frozen-lockfile`

A repeated key is a list, in the file's order. Any other line is prose and is ignored. An absent
key has no default: whoever reads it says the step is "sans objet" and names the key.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

CONFIG_PATH = Path("docs") / "agents" / "usine.md"
ENTRY = re.compile(r"^\s*[-*]\s+`([A-Za-z0-9_.-]+)`\s*:\s*`([^`]*)`\s*$")


def parse(text: str) -> dict[str, list[str]]:
    config: dict[str, list[str]] = {}
    for line in text.splitlines():
        if match := ENTRY.match(line):
            config.setdefault(match.group(1), []).append(match.group(2).strip())
    return config


def project_root(event: dict[str, object] | None = None) -> Path:
    """The project's directory: Claude Code's `CLAUDE_PROJECT_DIR`, else the event's cwd."""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or (event or {}).get("cwd") or "."
    return Path(str(root))


def load(root: Path) -> dict[str, list[str]]:
    """The configuration of the project at `root`; empty when it has none or it is unreadable."""
    try:
        return parse((root / CONFIG_PATH).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return {}
