"""F-0003 A12 (ticket #401, part a): the command of `agent-token-command` gives the token, or nothing.

The command is a real one (the interpreter running this suite, a script written in a temporary folder):
the boundary is the process, and no token is made up by a mock.
"""

import sys
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401  met les hooks sur le chemin d'import
from agent_identity import TOKEN_KEY, IdentityError, fresh_token, token_command

INSTALLATION = "ghs_" + "x" * 12
HUMANS = "ghp_" + "h" * 12


def command_of(folder: str, source: str) -> str:
    """A command that runs `source` as a Python script, quoted for `sh` and for `cmd` alike."""
    script = Path(folder) / "app_token.py"
    script.write_text(source, encoding="utf-8")
    return f'"{sys.executable}" "{script}"'


class TheTokenComesFromTheCommand(unittest.TestCase):
    def test_a12_a_command_that_prints_an_installation_token_gives_it(self) -> None:
        """F-0003 A12: one non-empty line that starts with `ghs_`, trailing newline or blanks cut."""
        with tempfile.TemporaryDirectory() as folder:
            command = command_of(folder, f"print({INSTALLATION!r})")
            self.assertEqual(fresh_token(command), INSTALLATION)

    def test_a12_each_failure_raises_an_error_that_names_the_key_and_never_the_command_or_a_token(self) -> None:
        """F-0003 A12, T10: a failing command, no output, two lines, another prefix, a timeout."""
        leaks = f"import sys; sys.stderr.write({INSTALLATION!r}); sys.exit(3)"
        failures = {
            "exit": leaks,
            "silent": "pass",
            "blank": "print('   ')",
            "two lines": f"print({INSTALLATION!r}); print({INSTALLATION!r})",
            "humans": f"print({HUMANS!r})",
            "late": "import time; time.sleep(30)",
        }
        for name, source in failures.items():
            with self.subTest(failure=name), tempfile.TemporaryDirectory() as folder:
                command = command_of(folder, source)
                with self.assertRaises(IdentityError) as caught:
                    fresh_token(command, timeout=1.5)
                message = str(caught.exception)
                self.assertIn(f"`{TOKEN_KEY}`", message)
                for secret in (INSTALLATION, HUMANS, "app_token.py", sys.executable):
                    self.assertNotIn(secret, message)

    def test_a12_a_command_that_cannot_start_is_a_failure_too(self) -> None:
        """F-0003 A12: no such program: the same error, not a crash of the caller."""
        with self.assertRaises(IdentityError) as caught:
            fresh_token("forge-no-such-program-401")
        self.assertIn(f"`{TOKEN_KEY}`", str(caught.exception))

    def test_a12_the_command_is_read_from_the_key_and_a_repeated_or_missing_line_is_an_error(self) -> None:
        """F-0003 A12: one line only; the error cites the key, never its value."""
        self.assertEqual(token_command({TOKEN_KEY: ["cmd"]}), "cmd")
        for lines in ([], ["a", "b"], [""]):
            with self.subTest(lines=lines), self.assertRaises(IdentityError) as caught:
                token_command({TOKEN_KEY: lines})
            self.assertIn(f"`{TOKEN_KEY}`", str(caught.exception))
            self.assertNotIn("a, b", str(caught.exception))
