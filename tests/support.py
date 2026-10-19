"""Puts the plugin's hooks and scripts on the import path, as Claude Code runs them."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN = REPO_ROOT / "plugins" / "forge"

for folder in (PLUGIN / "hooks", PLUGIN / "scripts"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
