import io
import json
import os
import time
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import support
from trim_output import KEEP_LINES, MAX_LINES, main, named, trimmed_output

SUITE = "uv run --no-project --quiet python -m unittest discover -s tests"


def lines(count: int, name: str) -> str:
    return "".join(f"{name} {n}\n" for n in range(count))


class Trimming(unittest.TestCase):
    def test_a_command_is_named_when_it_holds_a_value_of_the_key(self) -> None:
        self.assertTrue(named(f"cd x && {SUITE} -v", [SUITE]))
        self.assertFalse(named("ls -la", [SUITE]))
        self.assertFalse(named("ls -la", [""]))
        self.assertFalse(named(SUITE, []))

    def test_a_short_output_is_left_alone(self) -> None:
        response = {"stdout": lines(MAX_LINES // 2, "out"), "stderr": lines(MAX_LINES // 2, "err")}
        self.assertIsNone(trimmed_output(response, Path("journal.log")))

    def test_a_long_output_keeps_the_end_of_each_stream_and_the_journal_path(self) -> None:
        response = {"stdout": lines(5, "out"), "stderr": lines(MAX_LINES * 3, "err"),
                    "interrupted": False, "isImage": False}
        trimmed = trimmed_output(response, Path("journal.log"))
        assert trimmed is not None
        self.assertEqual(trimmed["interrupted"], False)
        self.assertEqual(trimmed["isImage"], False)
        self.assertEqual(trimmed["stdout"], lines(5, "out"))
        stderr = trimmed["stderr"].splitlines()
        self.assertIn("journal.log", stderr[0])
        self.assertIn(f"{KEEP_LINES} of {MAX_LINES * 3}", stderr[0])
        self.assertEqual(stderr[1:], lines(MAX_LINES * 3, "err").splitlines()[-KEEP_LINES:])

    def test_an_interrupted_command_is_left_alone(self) -> None:
        response = {"stdout": lines(MAX_LINES * 3, "out"), "stderr": "", "interrupted": True}
        self.assertIsNone(trimmed_output(response, Path("journal.log")))


class Hook(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name) / "home"
        self.project = Path(folder.name) / "project"
        self.home.mkdir()
        (self.project / "docs" / "agents").mkdir(parents=True)
        environ = mock.patch.dict(
            "os.environ",
            {"HOME": str(self.home), "USERPROFILE": str(self.home), "CLAUDE_PROJECT_DIR": str(self.project)},
        )
        environ.start()
        self.addCleanup(environ.stop)

    def configure(self, text: str) -> None:
        (self.project / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def run_hook(self, stdin: str) -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), redirect_stdout(out):
            code = main()
        return code, out.getvalue()

    def event(self, command: str, stdout: str) -> str:
        return json.dumps({
            "session_id": "0123abcd", "tool_name": "Bash", "cwd": str(self.project),
            "tool_input": {"command": command},
            "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False},
        })

    def journals(self) -> list[Path]:
        return sorted((self.home / ".claude").rglob("*.log")) if (self.home / ".claude").exists() else []

    def test_without_the_key_the_output_is_untouched(self) -> None:
        self.assertEqual(self.run_hook(self.event(SUITE, lines(MAX_LINES * 3, "ok"))), (0, ""))
        self.configure("- `ci-replay` : `uv run pytest`\n")
        self.assertEqual(self.run_hook(self.event(SUITE, lines(MAX_LINES * 3, "ok"))), (0, ""))
        self.assertEqual(self.journals(), [])

    def test_a_command_the_key_does_not_name_is_untouched(self) -> None:
        self.configure(f"- `trimmed-command` : `{SUITE}`\n")
        self.assertEqual(self.run_hook(self.event("git log", lines(MAX_LINES * 3, "commit"))), (0, ""))
        self.assertEqual(self.journals(), [])

    def test_a_long_output_of_a_named_command_is_replaced_and_kept_in_a_journal(self) -> None:
        self.configure(f"- `trimmed-command` : `uv run pytest`\n- `trimmed-command` : `{SUITE}`\n")
        full = lines(MAX_LINES * 3, "test")
        code, out = self.run_hook(self.event(f"{SUITE} -v", full))
        self.assertEqual(code, 0)
        hook = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(hook["hookEventName"], "PostToolUse")
        stdout = hook["updatedToolOutput"]["stdout"].splitlines()
        self.assertEqual(stdout[1:], full.splitlines()[-KEEP_LINES:])
        [journal] = self.journals()
        self.assertIn(str(journal), stdout[0])
        self.assertIn(full, journal.read_text(encoding="utf-8"))

    def test_the_journals_do_not_pile_up(self) -> None:
        self.configure(f"- `trimmed-command` : `{SUITE}`\n")
        for _ in range(25):
            self.run_hook(self.event(SUITE, lines(MAX_LINES * 3, "test")))
        self.assertLessEqual(len(self.journals()), 20)

    def test_the_journal_just_written_survives_the_pruning(self) -> None:
        # Another session's journals, older by name but stamped later: a coarse clock or a
        # parallel session leaves the file times out of order.
        self.configure(f"- `trimmed-command` : `{SUITE}`\n")
        folder = self.home / ".claude" / "hooks" / "state" / "trimmed"
        folder.mkdir(parents=True)
        later = time.time() + 3600
        for n in range(25):
            other = folder / f"other-{n}.log"
            other.write_text("an older run", encoding="utf-8")
            os.utime(other, (later, later))
        code, out = self.run_hook(self.event(SUITE, lines(MAX_LINES * 3, "test")))
        self.assertEqual(code, 0)
        notice = json.loads(out)["hookSpecificOutput"]["updatedToolOutput"]["stdout"].splitlines()[0]
        [journal] = [path for path in self.journals() if str(path) in notice]
        self.assertTrue(journal.exists())
        self.assertEqual(len(self.journals()), 20)
        self.assertFalse((folder / "other-0.log").exists())

    def test_an_unreadable_event_or_journal_exits_0_and_replaces_nothing(self) -> None:
        self.assertEqual(self.run_hook("not json"), (0, ""))
        self.assertEqual(self.run_hook("[]"), (0, ""))
        self.configure(f"- `trimmed-command` : `{SUITE}`\n")
        (self.home / ".claude").write_text("a file where the journal folder should be", encoding="utf-8")
        self.assertEqual(self.run_hook(self.event(SUITE, lines(MAX_LINES * 3, "test"))), (0, ""))


class Wiring(unittest.TestCase):
    def test_hooks_json_runs_the_hook_after_a_bash_command(self) -> None:
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        commands = [
            hook["command"]
            for entry in hooks["PostToolUse"]
            if entry.get("matcher") == "Bash"
            for hook in entry["hooks"]
        ]
        self.assertEqual(
            commands,
            ['uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/hooks/trim_output.py"'],
        )


if __name__ == "__main__":
    unittest.main()


class Gate(unittest.TestCase):
    def test_the_gate_reads_the_skips_in_the_journal_of_a_trimmed_output(self) -> None:
        response = {"stdout": lines(MAX_LINES * 3, "test"), "stderr": ""}
        trimmed = trimmed_output(response, Path("JOURNAL"))
        assert trimmed is not None
        notice = str(trimmed["stdout"]).splitlines()[0]
        prefix = notice[: notice.index(" of ")].rsplit(" ", 1)[0]
        gate = (support.PLUGIN / "agents" / "qc-gate.md").read_text(encoding="utf-8")
        skips = gate[gate.index("**Tests sautés.**"):gate.index("**Listes de référence.**")]
        self.assertIn(prefix, skips)
        self.assertIn("journal", skips)
