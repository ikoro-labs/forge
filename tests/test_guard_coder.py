import io
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from guard_coder import NO_ISOLATION, linked_worktree, main, refusal


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


class SharedConfiguration(unittest.TestCase):
    """#65: the coder never writes the configuration shared by every worktree."""

    def test_a_push_that_sets_the_upstream_or_forces_is_refused(self) -> None:
        for command in [
            "git push -u origin HEAD:feat/x",
            "git push --set-upstream origin HEAD:feat/x",
            "git push -fu origin HEAD:feat/x",
            "git push -f origin HEAD:feat/x",
            "git push --force origin HEAD:feat/x",
            "git push origin +HEAD:feat/x",
            "git -C work push -u origin HEAD",
            "cd work && git push --force origin HEAD",
        ]:
            with self.subTest(command=command):
                self.assertIsNotNone(bash(command))

    def test_a_plain_push_and_a_lease_push_pass(self) -> None:
        for command in [
            "git push origin HEAD:feat/x",
            "git push --force-with-lease origin HEAD:feat/x",
            "git push --force-with-lease=feat/x origin HEAD:feat/x",
            "git commit -m 'git push -u est refuse au coder'",
        ]:
            with self.subTest(command=command):
                self.assertIsNone(bash(command))

    def test_config_in_write_mode_is_refused_and_a_read_passes(self) -> None:
        for command in [
            "git config user.name x",
            "git config --global user.email x@y.z",
            "git config --add remote.origin.fetch x",
            "git config --unset branch.x.merge",
            "git config --unset-all branch.x.merge",
            "git config --edit",
            "git -C work config core.hooksPath /x",
        ]:
            with self.subTest(command=command):
                self.assertIsNotNone(bash(command))
        for command in [
            "git config user.name",
            "git config --get remote.origin.url",
            "git config --list",
            "git config --get-regexp branch",
        ]:
            with self.subTest(command=command):
                self.assertIsNone(bash(command))


class OwnWorktree(unittest.TestCase):
    """#65: writes and git commands stay under the coder's own worktree."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        base = Path(holder.name).resolve()
        (base / "tree").mkdir()
        (base / "main-copy").mkdir()
        self.tree = str(base / "tree")
        self.other = str(base / "main-copy")

    def judge(self, tool: str, tool_input: dict[str, object]) -> str | None:
        return refusal(tool, tool_input, self.tree, lambda _cwd: (self.tree, None))

    def test_a_write_outside_the_worktree_is_refused_whatever_the_tool(self) -> None:
        for tool, key in [
            ("Edit", "file_path"),
            ("Write", "file_path"),
            ("MultiEdit", "file_path"),
            ("NotebookEdit", "notebook_path"),
        ]:
            with self.subTest(tool=tool):
                reason = self.judge(tool, {key: str(Path(self.other) / "a.py")})
                self.assertIn("outside the coder's worktree", reason or "")
                self.assertIsNone(self.judge(tool, {key: str(Path(self.tree) / "src" / "a.py")}))

    def test_a_relative_path_is_judged_from_the_event_directory(self) -> None:
        self.assertIsNone(self.judge("Write", {"file_path": "docs/a.md"}))
        self.assertIsNotNone(self.judge("Write", {"file_path": "../main-copy/a.md"}))

    def test_a_write_without_a_path_is_refused(self) -> None:
        self.assertIsNotNone(self.judge("Write", {}))

    def test_a_git_command_outside_the_worktree_is_refused(self) -> None:
        for command in [
            f"git -C {self.other} status",
            f"cd {self.other} && git commit -m x",
            f"(cd {self.other}; git add .)",
            "git -C ../main-copy log",
            "git -C ~ status",
            'cd "$SOMEWHERE" && git status',
            "git --git-dir=/x/.git status",
            f"git --work-tree {self.other} status",
        ]:
            with self.subTest(command=command):
                self.assertIsNotNone(self.judge("Bash", {"command": command}))

    def test_a_git_command_under_the_worktree_passes(self) -> None:
        for command in [
            "git status",
            f"git -C {shlex.quote(self.tree)} log",
            "git -C src log",
            f"cd {shlex.quote(self.other)} && cd {shlex.quote(self.tree)} && git status",
            f"(cd {self.other}); git status",
            "git commit -m 'cd ../main-copy'",
            "ls ../main-copy",
        ]:
            with self.subTest(command=command):
                self.assertIsNone(self.judge("Bash", {"command": command}))

    def test_a_windows_path_is_read_whole_by_powershell(self) -> None:
        """#65: in PowerShell a backslash escapes nothing, so `C:\\x\\tree` is a path, not `C:xtree`.

        Read as POSIX words the drive path loses its backslashes and passes for a relative one,
        which is pasted onto the event's directory: a command outside the worktree went through,
        and, on Windows, one inside it was refused. The tree is a fixed Windows-style root here, so
        the splitting is reproduced on any system.
        """
        tree = "C:/work/tree"

        def judge(command: str) -> str | None:
            return refusal("PowerShell", {"command": command}, tree, lambda _cwd: (tree, None))

        for command in [
            "git -C C:\\work\\main status",
            "cd C:\\work\\main; git status",
            "git -C 'C:\\work\\main' log",
        ]:
            with self.subTest(command=command):
                self.assertIn("outside the coder's worktree", judge(command) or "")
        for command in [
            "git -C C:\\work\\tree log",
            "cd C:\\work\\main; cd C:\\work\\tree; git status",
            "git -C C:\\work\\tree\\sub log",
        ]:
            with self.subTest(command=command):
                self.assertIsNone(judge(command))

    def test_a_coder_without_a_worktree_is_refused_with_the_reason(self) -> None:
        def without(_cwd: str | None) -> tuple[None, str]:
            return None, NO_ISOLATION

        for tool, tool_input in [
            ("Write", {"file_path": str(Path(self.tree) / "a.py")}),
            ("Bash", {"command": "git status"}),
        ]:
            with self.subTest(tool=tool):
                reason = refusal(tool, tool_input, self.tree, without)
                self.assertIn("without isolation", reason or "")
        self.assertIsNone(refusal("Bash", {"command": "ls"}, self.tree, without))


def run_git(folder: Path, *args: str) -> None:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith(("GIT_", "CLAUDE_"))
    }
    environment.update(HOME=str(folder.parent), USERPROFILE=str(folder.parent), GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(  # noqa: S603 - fixed argv in a temporary repository
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.org", *args],  # noqa: S607
        cwd=folder,
        env=environment,
        check=True,
        capture_output=True,
        timeout=60,
    )


@unittest.skipUnless(shutil.which("git"), "needs git to build a repository and a worktree")
class RealWorktree(unittest.TestCase):
    """#65: the worktree is read from the event's directory, in a real repository."""

    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        base = Path(holder.name).resolve()
        self.main = base / "main-copy"
        self.main.mkdir()
        run_git(self.main, "init", "-q", "-b", "main")
        run_git(self.main, "commit", "-q", "--allow-empty", "-m", "first")
        self.tree = base / "tree"
        run_git(self.main, "worktree", "add", "-q", "--no-track", "-b", "feat/x", str(self.tree))
        (self.tree / "sub").mkdir()

    def event(self, folder: Path, name: str, **tool_input: object) -> dict[str, object]:
        return {
            "agent_type": "forge:coder",
            "cwd": str(folder),
            "tool_name": name,
            "tool_input": tool_input,
        }

    def test_a_linked_worktree_is_found_from_a_subfolder(self) -> None:
        root, why = linked_worktree(str(self.tree / "sub"))
        self.assertIsNone(why)
        self.assertEqual(Path(root or "").resolve(), self.tree)

    def test_the_main_copy_is_refused_from_its_first_write(self) -> None:
        write = self.event(self.main, "Write", file_path=str(self.main / "a.py"))
        self.assertEqual(run_main(write), 2)
        self.assertEqual(run_main(self.event(self.main, "Bash", command="git status")), 2)

    def test_the_worktree_may_write_and_not_the_main_copy(self) -> None:
        own = self.event(self.tree, "Write", file_path=str(self.tree / "a.py"))
        elsewhere = self.event(self.tree, "Write", file_path=str(self.main / "a.py"))
        self.assertEqual(run_main(own), 0)
        self.assertEqual(run_main(elsewhere), 2)
        self.assertEqual(run_main(self.event(self.tree, "Bash", command="git status")), 0)

    def test_a_directory_that_is_no_repository_is_refused(self) -> None:
        folder = self.tree.parent / "plain"
        folder.mkdir()
        self.assertEqual(run_main(self.event(folder, "Write", file_path=str(folder / "a"))), 2)

    def test_only_the_coder_is_filtered_on_its_prefixed_name(self) -> None:
        write = self.event(self.main, "Write", file_path=str(self.main / "a.py"))
        for agent in ("coder", "forge:qc-gate", "forge:qc-conf"):
            with self.subTest(agent=agent):
                self.assertEqual(run_main({**write, "agent_type": agent}), 0)
        self.assertEqual(run_main({k: v for k, v in write.items() if k != "agent_type"}), 0)


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


class Instructions(unittest.TestCase):
    def test_the_coder_pushes_without_upstream_and_branches_without_tracking(self) -> None:
        """#65: the agent's own instructions agree with what the guard allows."""
        text = (support.PLUGIN / "agents" / "coder.md").read_text(encoding="utf-8")
        self.assertNotIn("push -u", text)
        self.assertEqual(text.count("`git push origin HEAD:<branche>`"), 3)
        self.assertIn("--no-track origin/<base>", text)

    def test_feature_build_checks_the_main_copy_when_a_coder_leaves(self) -> None:
        text = (support.PLUGIN / "skills" / "feature-build" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`git status --porcelain` vide et même tête", text)
        self.assertIn("**sans lancer de revue**", text)


class Binding(unittest.TestCase):
    def test_hooks_json_turns_a_crash_of_the_strict_guards_into_a_refusal(self) -> None:
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        commands = {
            hook["command"]: group["matcher"]
            for group in hooks["hooks"]["PreToolUse"]
            for hook in group["hooks"]
        }
        for script, tools in [
            (
                "guard_coder.py",
                ("Bash", "PowerShell", "Skill", "Edit", "Write", "MultiEdit", "NotebookEdit"),
            ),
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
