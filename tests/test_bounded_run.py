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


class Bounds(unittest.TestCase):
    def test_a_command_over_its_delay_gets_the_delay_code_and_a_reason(self) -> None:
        """No F-NNNN: ticket #66, critère 2: le délai dépassé tue la commande, code distinct, raison sur stderr."""
        runner = Runner(self)
        done = runner.run("--memory-mb", "400", "--timeout", "2", command=python("import time; time.sleep(60)"))
        self.assertEqual(done.returncode, DELAY, done.stderr)
        self.assertIn("délai de 2 s dépassé", done.stderr)

    @unittest.skipUnless(
        sys.platform == "linux" or os.name == "nt",
        "the memory limit is set with RLIMIT_AS on Linux and a job object on Windows; macOS is not covered",
    )
    def test_a_command_over_its_memory_limit_gets_the_memory_code_and_a_reason(self) -> None:
        """No F-NNNN: ticket #66, critère 2: la mémoire dépassée donne un code distinct et sa raison sur stderr."""
        runner = Runner(self)
        # Tiny on Linux (the allocation fails, nothing is committed); a Windows Python needs more to start.
        limit, asked = ("64", 200) if sys.platform == "linux" else ("300", 800)
        done = runner.run(
            "--memory-mb", limit, "--timeout", "20", command=python(f"bytearray({asked} * 10**6)"),
        )
        self.assertEqual(done.returncode, MEMORY, done.stderr)
        self.assertIn("mémoire", done.stderr.splitlines()[-1])
        self.assertIn("MemoryError", done.stderr)  # the command's own error is still shown

    @unittest.skipUnless(
        sys.platform == "linux",
        "an impossible RLIMIT_AS is built by overflowing it; the Windows refusal is seen in CI only, never forced here",
    )
    def test_a_bound_that_cannot_be_set_refuses_to_run(self) -> None:
        """No F-NNNN: ticket #66, critère 3: une borne impossible à poser refuse de lancer, la commande ne tourne pas."""
        import resource

        if resource.getrlimit(resource.RLIMIT_AS)[1] != resource.RLIM_INFINITY:
            self.skipTest("the session's own limit caps the huge value instead of refusing it")
        runner = Runner(self)
        marker = runner.root / "ran"
        source = f"open({str(marker)!r}, 'w').close()"
        # 10**15 MB is past 2**64 bytes, the largest limit setrlimit takes: it overflows.
        done = runner.run("--memory-mb", str(10**15), "--timeout", "20", command=python(source))
        self.assertEqual(done.returncode, REFUSED, done.stderr)
        self.assertIn("limite non posée", done.stderr)
        self.assertFalse(marker.exists(), "the command ran without its bound")

    def test_a_command_that_does_not_exist_gets_the_not_found_code(self) -> None:
        """No F-NNNN: ticket #66, critère 1: une commande introuvable se dit, sans passer pour une borne."""
        runner = Runner(self)
        done = runner.run("--memory-mb", "400", "--timeout", "20", command=["no-such-command-forge-66"])
        self.assertEqual(done.returncode, NOT_FOUND, done.stderr)
        self.assertIn("no-such-command-forge-66", done.stderr)


class Limits(unittest.TestCase):
    def test_the_key_run_limits_gives_the_memory_and_the_delay(self) -> None:
        """No F-NNNN: ticket #66, critère 4: la clé run-limits pose mémoire et délai, sans option."""
        runner = Runner(self)
        usine = runner.usine("- `run-limits` : `400 | 2`\n")
        slept = runner.run("--usine", usine, command=python("import time; time.sleep(60)"))
        self.assertEqual(slept.returncode, DELAY, slept.stderr)
        self.assertIn("délai de 2 s dépassé", slept.stderr)
        fine = runner.run("--usine", usine, command=python("print('vert')"))
        self.assertEqual(fine.returncode, 0, fine.stderr)

    def test_an_option_wins_over_the_key(self) -> None:
        """No F-NNNN: ticket #66, critère 4: une option passe avant la clé."""
        runner = Runner(self)
        usine = runner.usine("- `run-limits` : `400 | 60`\n")
        done = runner.run(
            "--usine", usine, "--timeout", "2", command=python("import time; time.sleep(30)"),
        )
        self.assertEqual(done.returncode, DELAY, done.stderr)

    def test_without_the_key_both_options_are_required(self) -> None:
        """No F-NNNN: ticket #66, critère 4: sans clé run-limits, le lanceur exige ses deux options et la nomme."""
        runner = Runner(self)
        usine = runner.usine("- `ci-replay` : `autre`\n")
        for options in ([], ["--memory-mb", "400"], ["--timeout", "20"]):
            with self.subTest(options=options):
                done = runner.run("--usine", usine, *options, command=python("print('vert')"))
                self.assertEqual(done.returncode, WRONG_CALL, done.stderr)
                self.assertIn("clé `run-limits` absente", done.stderr)
                self.assertNotIn("vert", done.stdout)

    def test_a_malformed_key_or_a_non_positive_option_is_a_wrong_call(self) -> None:
        """No F-NNNN: ticket #66, critère 4: une valeur invalide est un appel faux, jamais une borne devinée."""
        runner = Runner(self)
        for text in ("- `run-limits` : `400`\n", "- `run-limits` : `beaucoup | 300`\n", "- `run-limits` : `0 | 300`\n"):
            with self.subTest(text=text):
                done = runner.run("--usine", runner.usine(text), command=python("print('vert')"))
                self.assertEqual(done.returncode, WRONG_CALL, done.stderr)
                self.assertIn("run-limits", done.stderr)
        done = runner.run("--memory-mb", "0", "--timeout", "20", command=python("print('vert')"))
        self.assertEqual(done.returncode, WRONG_CALL, done.stderr)


class SharedBound(unittest.TestCase):
    def test_base_replay_holds_its_commands_with_the_same_bound(self) -> None:
        """No F-NNNN: ticket #66, critère 5: la borne de base_replay est celle du lanceur, une seule fonction."""
        replay = (support.PLUGIN / "scripts" / "base_replay.py").read_text(encoding="utf-8")
        self.assertNotIn("setrlimit", replay, "base_replay sets its own limit instead of sharing run_bounded")
        self.assertIn("from bounded_run import", replay)
        self.assertIn("setrlimit", SCRIPT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
