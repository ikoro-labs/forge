"""Ticket #66: `bounded_run.py` runs any test command under a memory limit, a delay and the budget of the post.

Every test names its ticket and its point (`No F-NNNN: ticket #66, critère N`), the ticket having no
feature. The bounds the tests set are tiny (tens of MB, a few seconds) and none reads an endless source.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support

SCRIPT = support.PLUGIN / "scripts" / "bounded_run.py"

# Distinct exit codes of the launcher, documented in the script: a command's own code never hides them.
BUDGET, WRONG_CALL, REFUSED, MEMORY, DELAY, NOT_FOUND = 120, 121, 122, 123, 124, 127


class Runner:
    """Runs the launcher in a throwaway folder, isolated from the real HOME and the session's variables."""

    def __init__(self, test: unittest.TestCase) -> None:
        self.root = Path(tempfile.mkdtemp())
        test.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "HOME": str(self.root),
            "USERPROFILE": str(self.root),
            "TMPDIR": str(self.root),
            "TEMP": str(self.root),
            "TMP": str(self.root),
        }

    def usine(self, text: str) -> str:
        path = self.root / "usine.md"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def run(self, *options: str, command: list[str] | None = None) -> subprocess.CompletedProcess:
        tail = ["--", *command] if command is not None else []
        return subprocess.run(
            [sys.executable, str(SCRIPT), *options, *tail],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=60,
        )


def python(source: str, *args: str) -> list[str]:
    return [sys.executable, "-c", source, *args]


class ExitCode(unittest.TestCase):
    def test_a_command_that_passes_returns_its_own_code(self) -> None:
        """No F-NNNN: ticket #66, critère 1: la commande qui passe rend son code, 0 comme un code non nul."""
        runner = Runner(self)
        limits = ("--memory-mb", "400", "--timeout", "20")
        passing = runner.run(*limits, command=python("print('vert')"))
        self.assertEqual(passing.returncode, 0, passing.stderr)
        self.assertIn("vert", passing.stdout)
        failing = runner.run(*limits, command=python("import sys; sys.exit(3)"))
        self.assertEqual(failing.returncode, 3, failing.stderr)


if __name__ == "__main__":
    unittest.main()
