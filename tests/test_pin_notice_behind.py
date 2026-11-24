"""ikoro-labs/forge#333 A3: the `SessionStart` hook `pin_notice.py` warns on BEHIND, with the command, and fails open.

BEHIND is the verdict of `pin_state.check`, the one `pin_sync.py check` gives: the installed plugin
differs from the `ref` pinned on origin/main. The real `claude` is never run: `FakeClaude` stands in
for it, or a stand-in script on the PATH. Git is real, on throwaway repositories under an isolated
HOME and USERPROFILE (see `pin_support.py`).
"""

import json
import os
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import support
from pin_notice import behind_notice
from pin_support import FakeClaude, PinCase, entry, git

HOOK = support.PLUGIN / "hooks" / "pin_notice.py"
APPLY = support.PLUGIN / "scripts" / "pin_sync.py"


class BehindNotice(PinCase):
    def notice(self, project: Path, claude: FakeClaude, **event: object) -> str | None:
        return behind_notice({"cwd": str(project), **event}, claude)

    def test_a_project_behind_is_told_both_versions_and_the_command_that_installs(self) -> None:
        """#333 A3: pinned 1.21.0 on origin/main, installed 1.20.0."""
        project = self.project("app", "forge--v1.21.0")
        message = self.notice(project, FakeClaude([entry(project, "1.20.0")]))
        assert message is not None
        self.assertIn("1.20.0", message)
        self.assertIn("forge--v1.21.0", message)
        self.assertIn(f'python "{APPLY}" apply "{project}"', message)
        self.assertIn("feature-build", message)

    def test_the_message_says_where_it_stops_and_that_no_user_setting_is_touched(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        message = self.notice(project, FakeClaude([entry(project, "1.20.0")]))
        assert message is not None
        for word in ("coder", "verdict", "réglages utilisateur"):
            self.assertIn(word, message)

    def test_a_project_installed_at_its_pin_is_told_nothing(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        self.assertIsNone(self.notice(project, FakeClaude([entry(project, "1.21.0")])))

    def test_what_cannot_be_read_is_told_nothing(self) -> None:
        """NOT RUN is not a warning: `claude` missing or failing, no pin on origin/main, a user-level pin that differs."""
        project = self.project("app", "forge--v1.21.0")
        bare = self.project("bare", ref=None)
        stuck = self.project("stuck", "forge--v1.21.0")
        self.user_settings("forge--v1.20.0")
        cases = {
            "claude missing": (project, FakeClaude(available=False)),
            "claude failing": (project, FakeClaude(fail={"list": (1, "boom")})),
            "no pin on origin/main": (bare, FakeClaude([entry(bare, "1.20.0")])),
            "user-level pin differs": (stuck, FakeClaude([entry(stuck, "1.20.0")])),
        }
        for name, (where, claude) in cases.items():
            with self.subTest(name):
                self.assertIsNone(self.notice(where, claude))

    def test_a_subagent_is_told_nothing_and_nothing_is_run(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        claude = FakeClaude([entry(project, "1.20.0")])
        self.assertIsNone(self.notice(project, claude, agent_id="a1"))
        self.assertEqual(claude.calls, [])

    def test_a_session_in_a_subfolder_or_a_worktree_is_judged_as_its_main_checkout(self) -> None:
        """The plugin is installed for the main checkout: a worktree path would look like a project never installed."""
        project = self.project("app", "forge--v1.21.0")
        worktree = project / ".claude" / "worktrees" / "agent-a1"
        git(project, "worktree", "add", "-b", "worktree-agent-a1", str(worktree))
        for where in (project / ".claude", worktree):
            with self.subTest(where=str(where)):
                message = self.notice(where, FakeClaude([entry(project, "1.21.0")]))
                self.assertIsNone(message)
        message = self.notice(worktree, FakeClaude([entry(project, "1.20.0")]))
        assert message is not None
        self.assertIn(f'apply "{project}"', message)

    def test_it_asks_nothing_of_the_network(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        claude = FakeClaude([entry(project, "1.20.0")])
        self.notice(project, claude)
        self.assertEqual(claude.commands(), [])
        self.assertEqual([argv[:3] for argv, _ in claude.calls], [["claude", "plugin", "list"]])


class AsAProcess(PinCase):
    """The hook as Claude Code launches it: the event on stdin, additional context on stdout, always exit 0."""

    def setUp(self) -> None:
        super().setUp()
        self.bin = self.root / "bin"
        self.bin.mkdir()

    def stand_in(self, name: str, script: str) -> None:
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def run_hook(self, project: Path, stdin: str | None = None, path: str | None = None) -> subprocess.CompletedProcess[str]:
        env = {key: value for key, value in os.environ.items() if not key.startswith("CLAUDE_")}
        env.update(HOME=str(self.home), USERPROFILE=str(self.home), PATH=path or f"{self.bin}{os.pathsep}{os.environ['PATH']}")
        return subprocess.run(
            [sys.executable, str(HOOK)], input=stdin if stdin is not None else json.dumps({"cwd": str(project)}),
            capture_output=True, text=True, env=env, cwd=project, timeout=60, check=False,
        )

    @unittest.skipIf(os.name == "nt", "the stand-in `claude` is a POSIX shell script")
    def test_a_behind_project_makes_the_hook_print_the_notice_as_additional_context(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        listing = json.dumps([entry(project, "1.20.0")])
        self.stand_in("claude", f"cat <<'EOF'\n{listing}\nEOF")
        result = self.run_hook(project)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "SessionStart")
        self.assertIn("1.20.0", output["additionalContext"])
        self.assertIn("pin_sync.py", output["additionalContext"])

    @unittest.skipIf(os.name == "nt", "the stand-in `claude` and `gh` are POSIX shell scripts")
    def test_both_notices_reach_the_session_in_one_context(self) -> None:
        """With the key `pin-bump` and a newer tag, the bump notice and the BEHIND notice are both said."""
        project = self.project("app", "forge--v1.21.0")
        (project / "docs" / "agents").mkdir(parents=True)
        (project / "docs" / "agents" / "usine.md").write_text("- `pin-bump` : `auto`\n", encoding="utf-8")
        listing = json.dumps([entry(project, "1.20.0")])
        self.stand_in("claude", f"cat <<'EOF'\n{listing}\nEOF")
        self.stand_in("gh", 'case "$*" in *matching-refs*) echo refs/tags/forge--v1.22.0 ;; esac')
        result = self.run_hook(project)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("forge--v1.22.0", context)
        self.assertIn("pin_sync.py", context)

    @unittest.skipIf(os.name == "nt", "the stand-in `claude` is a POSIX shell script")
    def test_it_fails_open_whatever_claude_does(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        for name, script in {
            "exits 1": "echo boom >&2; exit 1",
            "prints garbage": "echo '<<<not json'",
            "prints another shape": "echo '{\"plugins\": []}'",
            "prints nothing": "exit 0",
        }.items():
            with self.subTest(name):
                self.stand_in("claude", script)
                result = self.run_hook(project)
                self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    def test_without_claude_or_git_on_the_path_it_is_silent_and_exits_zero(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        empty = self.root / "empty"
        empty.mkdir()
        result = self.run_hook(project, path=str(empty))
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    def test_an_unreadable_event_is_silent_and_exits_zero(self) -> None:
        project = self.project("app", "forge--v1.21.0")
        for stdin in ("", "not json", "[]", json.dumps({"cwd": 3})):
            with self.subTest(stdin=stdin):
                result = self.run_hook(project, stdin=stdin)
                self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    def test_an_error_in_the_check_costs_only_its_notice(self) -> None:
        """A broken `pin_state` is not an error of the session: the process still exits 0, silently."""
        import pin_notice

        project = self.project("app", "forge--v1.21.0")
        with mock.patch("pin_state.check", side_effect=RuntimeError("boom")):
            self.assertIsNone(pin_notice.safely(pin_notice.behind_notice, {"cwd": str(project)}))

    def test_every_command_of_the_check_is_bounded_in_time(self) -> None:
        import pin_state

        seen: list[object] = []

        def fake(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            seen.append(kwargs.get("timeout"))
            raise subprocess.TimeoutExpired(argv, 1)

        with mock.patch("shutil.which", return_value="/usr/bin/claude"), mock.patch("subprocess.run", fake):
            self.assertIsNone(pin_state.run_command(["claude", "plugin", "list", "--json"], self.root))
        self.assertTrue(seen and all(isinstance(t, (int, float)) and 0 < float(t) <= 4 for t in seen), seen)


class Declaration(unittest.TestCase):
    def test_the_timeout_of_the_hook_covers_every_command_it_can_run(self) -> None:
        """Two `gh` calls of the bump notice, and the `claude` and git calls of the BEHIND notice, each at its bound."""
        import pin_notice
        import pin_state

        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        found = [hook for group in hooks["SessionStart"] for hook in group["hooks"] if "pin_notice.py" in hook.get("command", "")]
        worst = 2 * pin_notice.GH_SECONDS + 2 * pin_state.SECONDS
        self.assertGreaterEqual(int(found[0]["timeout"]), worst)
        self.assertNotIn("onFailure", found[0])

if __name__ == "__main__":
    unittest.main()
