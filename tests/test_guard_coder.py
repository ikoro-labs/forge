import io
import json
import unittest
from pathlib import Path
from unittest import mock

import support
from guard_coder import main, refusal


def bash(command: str) -> str | None:
    return refusal("Bash", {"command": command})


def run_main(event: object) -> int:
    stdin = io.StringIO(event if isinstance(event, str) else json.dumps(event))
    with mock.patch("sys.stdin", stdin), mock.patch("sys.stderr", io.StringIO()):
        return main()


class CoderActs(unittest.TestCase):
    def test_the_orchestrator_acts_are_refused(self) -> None:
        for command, reason in [
            ("gh pr merge 61 --squash", "qc merges"),
            ("gh pr review 61 --approve", "qc judges"),
            ("gh issue close 12", "ticket's state"),
            ("gh issue edit 12 --add-label agent-claimed", "labels and assignees"),
            ("cd apps && gh -R o/r pr merge 61", "qc merges"),
        ]:
            with self.subTest(command=command):
                self.assertIn(reason, bash(command) or "")

    def test_the_coder_own_acts_pass(self) -> None:
        for command in [
            "gh pr create --fill",
            "gh pr view 61",
            "gh pr checks 61",
            "gh issue view 12",
            "gh issue comment 12 --body x",
            "git commit -m 'gh pr merge is refused to the coder'",
        ]:
            with self.subTest(command=command):
                self.assertIsNone(bash(command))

    def test_the_qc_skill_is_refused_under_both_names(self) -> None:
        for skill in ("qc", "/qc", "forge:qc", "/forge:qc", " forge:qc "):
            with self.subTest(skill=skill):
                self.assertIsNotNone(refusal("Skill", {"skill": skill}))
        self.assertIsNone(refusal("Skill", {"skill": "tdd"}))
        self.assertIsNone(refusal("Skill", {"skill": "forge:feature-status"}))


class Main(unittest.TestCase):
    def test_only_the_coder_is_guarded(self) -> None:
        call = {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 61"}}
        self.assertEqual(run_main({**call, "agent_type": "forge:coder"}), 2)
        self.assertEqual(run_main({**call, "agent_type": "forge:qc-gate"}), 0)
        self.assertEqual(run_main({**call, "agent_type": "coder"}), 0)
        self.assertEqual(run_main(call), 0)

    def test_an_event_the_hook_cannot_read_is_refused(self) -> None:
        self.assertEqual(run_main("not json"), 2)
        self.assertEqual(run_main({"agent_type": "forge:coder", "tool_input": "x"}), 2)
        self.assertEqual(run_main([1, 2]), 2)


class Binding(unittest.TestCase):
    def test_hooks_json_turns_a_crash_of_the_strict_guards_into_a_refusal(self) -> None:
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        commands = {
            hook["command"]: group["matcher"]
            for group in hooks["hooks"]["PreToolUse"]
            for hook in group["hooks"]
        }
        for script, tools in [
            ("guard_coder.py", ("Bash", "PowerShell", "Skill")),
            ("guard_readonly.py", ("Bash", "PowerShell", "Edit", "Write", "MultiEdit")),
            ("guard_git.py", ("Bash", "PowerShell")),
            ("guard_pause.py", ("Agent", "Task")),
        ]:
            with self.subTest(script=script):
                found = [command for command in commands if script in command]
                self.assertEqual(len(found), 1)
                matcher = commands[found[0]].split("|")
                for tool in tools:
                    self.assertIn(tool, matcher)
                self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/", found[0])
                if script in ("guard_coder.py", "guard_readonly.py"):
                    self.assertTrue(found[0].endswith("|| exit 2"))

    def test_every_hook_hooks_json_names_exists(self) -> None:
        text = (support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8")
        for name in ("guard_git", "guard_coder", "guard_readonly", "guard_pause", "after_write"):
            with self.subTest(name=name):
                self.assertIn(f"/hooks/{name}.py", text)
                self.assertTrue(Path(support.PLUGIN / "hooks" / f"{name}.py").is_file())


if __name__ == "__main__":
    unittest.main()
