"""The observing `SessionStart` hook, sessions_notice.py: at the start of a session, it names the
other live sessions of the repository (ikoro-labs/forge#4, critère 5).

Every test runs on a stand-in registry under an isolated HOME and USERPROFILE, without the
CLAUDE_ variables of the session running the tests, and writes nothing in the real ~/.claude.
"""

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import support
import handoff_header

HOOK = support.PLUGIN / "hooks" / "sessions_notice.py"
SKILL = support.PLUGIN / "skills" / "feature-build" / "SKILL.md"
RULE = "**Une seule session par projet.**"


def isolated_home(home: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("CLAUDE_")}
    env.update(HOME=str(home), USERPROFILE=str(home))
    return env


class SessionStartNotice(unittest.TestCase):
    def setUp(self) -> None:
        import shutil

        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.repo = self.home / "demo"
        (self.repo / ".git").mkdir(parents=True)
        self.registry = self.home / ".claude" / "sessions"
        self.registry.mkdir(parents=True)
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in [key for key in os.environ if key.startswith("CLAUDE_")]:
            del os.environ[name]
        os.environ.update(HOME=str(self.home), USERPROFILE=str(self.home))

    def sleeper(self) -> int:
        """A running process that is neither this one nor one of its ancestors."""
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return process.pid

    def register(self, pid: int, **fields: object) -> None:
        entry = {
            "pid": pid, "sessionId": "0801df0e-3c3b-48e6-a43f-375ac6d170e3", "cwd": str(self.repo), "kind": "bg",
            "name": "relais-1-demo", "status": "busy", "procStart": handoff_header.process_start(pid), **fields,
        }
        (self.registry / f"{pid}.json").write_text(json.dumps(entry), encoding="utf-8")

    def event(self, **fields: object) -> dict[str, object]:
        return {
            "session_id": "abcdef12-3456-7890-abcd-ef1234567890", "transcript_path": "", "cwd": str(self.repo),
            "hook_event_name": "SessionStart", "source": "startup", **fields,
        }

    def run_hook(self, stdin: str) -> subprocess.CompletedProcess[str]:
        """The hook as Claude Code runs it: a process of its own, the event on stdin."""
        return subprocess.run(
            [sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True,
            env=isolated_home(self.home), cwd=self.repo, timeout=60, check=False,
        )

    def context(self, result: subprocess.CompletedProcess[str]) -> str:
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "SessionStart")
        return output["additionalContext"]

    def test_another_live_session_of_the_repository_is_named(self) -> None:
        """ikoro-labs/forge#4, critère 5: the context names each other live session, as
        `handoff_header.py sessions` prints it, and sends the session to the rule of
        `feature-build`, step 0, point 5."""
        pid = self.sleeper()
        self.register(pid)
        text = self.context(self.run_hook(json.dumps(self.event())))
        self.assertIn(f"{pid} bg relais-1-demo busy {self.repo}", text)
        self.assertIn(RULE.strip("*"), text)
        self.assertIn(str(SKILL), text)
        self.assertIn(f'"{support.PLUGIN / "hooks" / "handoff_header.py"}" sessions .', text)

    def test_the_rule_the_context_cites_is_point_5_of_step_0(self) -> None:
        """The title the context cites is the one point 5 of step 0 carries: the hook sends the
        session there and does not write the rule a second time."""
        step = SKILL.read_text(encoding="utf-8").split("## 0.", 1)[1].split("\n## ", 1)[0]
        point = re.search(r"^5\. (\S.*)$", step, re.MULTILINE)
        self.assertIsNotNone(point)
        self.assertTrue((point.group(1) if point else "").startswith(RULE))
        import sessions_notice

        self.assertIn(RULE.strip("*"), sessions_notice.RULE)
        self.assertNotIn("SendMessage", sessions_notice.notice_text(["1 bg x busy /d"]))

    def test_no_other_session_says_nothing(self) -> None:
        result = self.run_hook(json.dumps(self.event()))
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)
        # A session of another repository is no other session of this one.
        other = self.home / "autre"
        (other / ".git").mkdir(parents=True)
        self.register(self.sleeper(), cwd=str(other))
        result = self.run_hook(json.dumps(self.event()))
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    def test_a_subagent_is_told_nothing(self) -> None:
        """ikoro-labs/forge#4, critère 5: `agent_id` is present only when a hook fires within a
        subagent, never on the main thread, even with `claude --agent`."""
        self.register(self.sleeper())
        result = self.run_hook(json.dumps(self.event(agent_id="a4d2c8f1e0b3a297", agent_type="forge:coder")))
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)
        # A main session started with `claude --agent` carries `agent_type` alone: it is told.
        self.assertIn("relais-1-demo", self.context(self.run_hook(json.dumps(self.event(agent_type="forge:coder")))))

    def test_the_session_that_handed_over_to_this_one_is_not_named(self) -> None:
        """The detection is that of `sessions`: the `auteur` of a handoff whose `successeur` is
        this session, still alive during its closing delay, is left out; the session id is the
        event's."""
        self.register(self.sleeper())
        folder = self.home / ".claude" / "hooks" / "state" / "handoffs" / "demo"
        folder.mkdir(parents=True)
        path = folder / "2026-10-21-r1.md"
        path.write_text("---\nprojet: demo\nsuccesseur:\n---\n", encoding="utf-8")
        handoff_header.set_successor(path, "abcdef12", "150000", "0801df0e-3c3b-48e6-a43f-375ac6d170e3")
        result = self.run_hook(json.dumps(self.event()))
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    def test_an_unreadable_registry_entry_is_named_as_live(self) -> None:
        (self.registry / "4242.json").write_text("{pas du json", encoding="utf-8")
        self.assertIn("unreadable", self.context(self.run_hook(json.dumps(self.event()))))

    def test_an_unreadable_event_or_a_failure_exits_0_and_says_nothing(self) -> None:
        """ikoro-labs/forge#4, critère 5: the hook observes, it never blocks the session."""
        self.register(self.sleeper())
        for stdin in ("", "pas du json", "[1, 2]", json.dumps({"cwd": 3})):
            with self.subTest(stdin=stdin):
                result = self.run_hook(stdin)
                self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)
        import sessions_notice

        with mock.patch.object(handoff_header, "other_sessions", side_effect=OSError("registre")):
            with redirect_stdout(io.StringIO()) as out:
                code = sessions_notice.main(io.StringIO(json.dumps(self.event())))
        self.assertEqual((code, out.getvalue()), (0, ""))
        with mock.patch.object(handoff_header, "other_sessions", side_effect=RuntimeError("bug")):
            with redirect_stdout(io.StringIO()) as out:
                code = sessions_notice.main(io.StringIO(json.dumps(self.event())))
        self.assertEqual((code, out.getvalue()), (0, ""))


class Declaration(unittest.TestCase):
    def test_hooks_json_declares_the_hook_on_session_start_with_a_timeout(self) -> None:
        """ikoro-labs/forge#4, critère 5: `${CLAUDE_PLUGIN_ROOT}`, the plugin's interpreter, a
        `timeout`, and no matcher, so that every source (startup, resume, clear, compact, fork)
        runs it."""
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        groups = hooks.get("SessionStart", [])
        found = [
            (group, hook) for group in groups for hook in group["hooks"] if "sessions_notice.py" in hook.get("command", "")
        ]
        self.assertEqual(len(found), 1, groups)
        group, hook = found[0]
        self.assertNotIn("matcher", group)
        self.assertEqual(hook["type"], "command")
        self.assertEqual(
            hook["command"], 'uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/hooks/sessions_notice.py"',
        )
        self.assertIsInstance(hook.get("timeout"), int)
        self.assertGreater(hook["timeout"], 0)
        self.assertLessEqual(hook["timeout"], 30)
        self.assertTrue(HOOK.is_file())


if __name__ == "__main__":
    unittest.main()
