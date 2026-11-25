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


def repo_usine_text() -> str:
    """The configuration of this repository as its PR holds it: `usine.md` then `usine-gardes.md`.

    The keys that bound the agent moved to the second file (ikoro-labs/forge#345). The loader reads that
    file on `origin/main`, which a test cannot rely on before the PR is merged; a test of what this
    repository declares reads the two files in the working tree.
    """
    folder = REPO_ROOT / "docs" / "agents"
    return "\n".join((folder / name).read_text(encoding="utf-8") for name in ("usine.md", "usine-gardes.md"))


def repo_usine() -> dict[str, list[str]]:
    """The keys of `repo_usine_text`, as `usine.parse` reads them."""
    from usine import parse

    return parse(repo_usine_text())
