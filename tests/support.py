"""Puts the plugin's hooks and scripts on the import path, as Claude Code runs them."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN = REPO_ROOT / "plugins" / "forge"

for folder in (PLUGIN / "hooks", PLUGIN / "scripts"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

# The guards that refuse in these tests (in this process) journal their refusals: the journal goes
# to a throwaway folder, never to the real `~/.claude`. `test_guard_refusals.py` runs the guards as
# processes under a temporary HOME, and tests the real path.
import atexit  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

import refusal_journal  # noqa: E402

_JOURNAL = tempfile.mkdtemp(prefix="forge-refusals-")
atexit.register(shutil.rmtree, _JOURNAL, ignore_errors=True)
refusal_journal.journal_dir = lambda: Path(_JOURNAL)
