"""The hooks read their event, and write their answer, in UTF-8 whatever the host's code page.

Claude Code sends the hook event in UTF-8. Under Windows, a Python started by `uv` takes the ANSI
code page (`cp1252`) for its standard streams, so `| Champ | État |` arrived as `| Champ | Ã‰tat |`
and a French session reply was refused on every first try. `PYTHONIOENCODING=cp1252` reproduces
that host on any system.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support

HOOKS = support.PLUGIN / "hooks"
REPLY_FR = (
    "| Champ | État |\n|---|---|\n| Fait | PR #12 fusionnée. |\n| Mesuré | CI 4 min, run 99. |\n"
    "| Attend ta décision | rien. |\n\n"
    "CI et runners: poste 2/2 en ligne; main success abc1234.\n\n"
    "Features:\n\n| Feature | Closed / total | Merged PRs | Open PRs | Blocked | Ready |\n|---|---|---|---|---|---|\n"
    "| F-0001 demo | 33 % (1 / 3) | 4 / 45 (#12: 3, #13: 1) | #77 | #13 | #12 |\n\n"
    "In parallel: free slots 1; tickets #12 (F-0001); or features F-0001.\n"
)
# A French reply out of its template: its prose sits outside the table.
REFUSED_FR = "J'ai tout fait. État : vert.\n- a\n- b\n- c\n"


def run_stop(reply: str) -> subprocess.CompletedProcess[bytes]:
    """`guard_output.py` on a Stop event, as Claude Code feeds it, on a host whose code page is cp1252."""
    with tempfile.TemporaryDirectory() as folder:
        home = Path(folder) / "home"
        project = Path(folder) / "project"
        home.mkdir()
        project.mkdir()
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("CLAUDE_") and key not in ("PYTHONUTF8", "PYTHONIOENCODING")
        }
        env.update(
            HOME=str(home),
            USERPROFILE=str(home),
            CLAUDE_PROJECT_DIR=str(project),
            PYTHONIOENCODING="cp1252",
        )
        event = {"hook_event_name": "Stop", "stop_hook_active": False, "last_assistant_message": reply}
        return subprocess.run(  # noqa: S603 - the interpreter running this suite, a fixed script
            [sys.executable, str(HOOKS / "guard_output.py")],
            input=json.dumps(event, ensure_ascii=False).encode("utf-8"),
            env=env,
            capture_output=True,
            check=False,
            timeout=60,
        )


class EndToEnd(unittest.TestCase):
    def test_a_french_reply_passes_on_a_cp1252_host(self) -> None:
        done = run_stop(REPLY_FR)
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", errors="replace"))
        self.assertEqual(done.stderr, b"")

    def test_a_refusal_is_written_in_utf8(self) -> None:
        done = run_stop(REFUSED_FR)
        self.assertEqual(done.returncode, 3)
        err = done.stderr.decode("utf-8")
        self.assertIn("your reply to the human", err)
        self.assertIn("`Mesuré`", err)
        self.assertIn("`Attend ta décision`", err)


def stdin_hooks() -> list[str]:
    """The scripts `hooks.json` runs that read their event from standard input."""
    hooks = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
    names = {
        match
        for groups in hooks["hooks"].values()
        for group in groups
        for hook in group["hooks"]
        for match in re.findall(r"hooks/(\w+\.py)", hook["command"])
    }
    return sorted(name for name in names if "sys.stdin" in (HOOKS / name).read_text(encoding="utf-8"))


class Structure(unittest.TestCase):
    def test_every_hook_that_reads_stdin_switches_to_utf8_first(self) -> None:
        found = stdin_hooks()
        self.assertGreaterEqual(len(found), 16)
        for name in found:
            with self.subTest(hook=name):
                source = (HOOKS / name).read_text(encoding="utf-8")
                self.assertIn("from utf8_stdio import use_utf8", source)
                entry = source.split('if __name__ == "__main__":', 1)
                self.assertEqual(len(entry), 2, "no entry point")
                self.assertTrue(entry[1].lstrip().startswith("use_utf8()"), "use_utf8() is not its first call")


class Helper(unittest.TestCase):
    def test_a_stream_without_reconfigure_is_left_alone(self) -> None:
        import io
        from unittest import mock

        from utf8_stdio import use_utf8

        with mock.patch.object(sys, "stdin", io.StringIO("x")):
            use_utf8()
            self.assertEqual(sys.stdin.read(), "x")


if __name__ == "__main__":
    unittest.main()
