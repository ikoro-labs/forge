"""Ticket #156: the three guards leave a line in `~/.claude/hooks/state/refusals/` for each refusal.

Each case runs the guard as Claude Code does, as a process fed an event on standard input, with a
temporary `HOME` and `USERPROFILE` and none of the session's `CLAUDE_` or `GIT_` variables: the real
`~/.claude` is never read nor written.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import support
from refusal_journal import rule_of

import guard_coder  # isort: skip - after `support`, which puts the hooks on the import path
import guard_git  # isort: skip
import guard_readonly  # isort: skip

HOOKS = support.PLUGIN / "hooks"
SECRET = "ghp_S3CR3T0123456789"
# One refused call by guard: the guard, the event it is given, and the line expected in the journal.
REFUSED = {
    "git": ("guard_git.py", {"command": "git push --force origin feat/x"}, None, "force-push", "git push"),
    "coder": ("guard_coder.py", {"command": "gh pr merge 5 --merge"}, "forge:coder", "gh-pr-merge", "gh pr merge"),
    "readonly": ("guard_readonly.py", {"command": "cat a > b"}, "forge:qc-conf", "redirection", "cat"),
}
# One command each guard lets through (the coder's is no git command: it would first need a linked worktree).
ALLOWED = {"git": "git status", "coder": "ls", "readonly": "git log -1"}


def environment(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "GIT_"))}
    env.update(HOME=str(home), USERPROFILE=str(home), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    return env


class Journal(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name) / "home"
        self.depot = Path(folder.name) / "depot"
        self.home.mkdir()
        subprocess.run(  # noqa: S603, S607 - fixed argv in a temporary repository
            ["git", "init", "-q", "-b", "feat/essai", str(self.depot)],
            env=environment(self.home),
            check=True,
        )
        self.journal = self.home / ".claude" / "hooks" / "state" / "refusals"

    def run_guard(
        self, script: str, tool_input: dict[str, str], agent: str | None, home: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        event: dict[str, object] = {"tool_name": "Bash", "tool_input": tool_input, "cwd": str(self.depot)}
        if agent is not None:
            event["agent_type"] = agent
        return subprocess.run(  # noqa: S603 - the interpreter running this suite, a fixed script
            [sys.executable, str(HOOKS / script)],
            input=json.dumps(event),
            env=environment(home or self.home),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

    def lines(self) -> list[dict[str, str]]:
        if not self.journal.is_dir():
            return []
        found = [
            json.loads(line)
            for path in sorted(self.journal.glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        return found

    def test_each_guard_adds_one_line_for_a_refusal(self) -> None:
        """#156 A1.1: guard, fixed rule, agent or main, repo, branch and verb; one line per refusal."""
        for name, (script, tool_input, agent, rule, verb) in REFUSED.items():
            with self.subTest(guard=name):
                before = len(self.lines())
                done = self.run_guard(script, tool_input, agent)
                self.assertEqual(done.returncode, 2, done.stderr)
                found = self.lines()
                self.assertEqual(len(found), before + 1)
                line = found[-1]
                self.assertEqual(line["guard"], script.removesuffix(".py"))
                self.assertEqual(line["rule"], rule)
                self.assertEqual(line["agent"], agent or "main")
                self.assertEqual(line["repo"], "depot")
                self.assertEqual(line["branch"], "feat/essai")
                self.assertEqual(line["verb"], verb)
                moment = datetime.fromisoformat(line["date"])
                self.assertLess(abs((datetime.now(timezone.utc) - moment).total_seconds()), 300)
                self.assertTrue((self.journal / f"{moment.astimezone(timezone.utc):%Y-%m-%d}.jsonl").is_file())

    def test_the_journal_never_holds_the_command_nor_an_argument_secret(self) -> None:
        """#156 A1.2: a refused `gh api` that carries a token leaves the verb, never the token."""
        command = f'gh api -X DELETE -H "Authorization: token {SECRET}" repos/o/r'
        done = self.run_guard("guard_git.py", {"command": command}, None)
        self.assertEqual(done.returncode, 2, done.stderr)
        written = "".join(path.read_text(encoding="utf-8") for path in self.journal.glob("*.jsonl"))
        self.assertEqual(self.lines()[0]["verb"], "gh api")
        self.assertNotIn(SECRET, written)
        self.assertNotIn("Authorization", written)

    def test_an_allowed_command_writes_nothing(self) -> None:
        """#156 A2.1: a command the guard lets through leaves no line, and no folder."""
        for name, (script, _tool_input, agent, _rule, _verb) in REFUSED.items():
            allowed = {"command": ALLOWED[name]}
            with self.subTest(guard=name):
                done = self.run_guard(script, allowed, agent)
                self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(self.journal.exists())

    def test_a_journal_that_cannot_be_written_leaves_the_refusal_as_it_is(self) -> None:
        """#156 A2.1: `refusals` is a file, so no line can be added: same exit code, same message."""
        for name, (script, tool_input, agent, _rule, _verb) in REFUSED.items():
            with self.subTest(guard=name):
                clear = self.run_guard(script, tool_input, agent)
                blocked = Path(self.home) / "bloque"
                (blocked / ".claude" / "hooks" / "state").mkdir(parents=True, exist_ok=True)
                (blocked / ".claude" / "hooks" / "state" / "refusals").write_text("un fichier", encoding="utf-8")
                done = self.run_guard(script, tool_input, agent, home=blocked)
                self.assertEqual((done.returncode, done.stderr), (2, clear.stderr))
                self.assertEqual(done.returncode, clear.returncode)


class RuleNames(unittest.TestCase):
    """#156 A1: each refusal of a guard gets the fixed name of its rule, never `other`."""

    def test_guard_git_names_each_rule(self) -> None:
        def named(command: str, branch: str = "feat/x", green: bool = True, **keys: Any) -> str:
            reason = guard_git.refusal(command, branch, lambda *_target: green, **keys)
            self.assertIsNotNone(reason, command)
            return rule_of(str(reason), guard_git.RULES)

        cases: list[tuple[str, str, dict[str, Any]]] = [
            ("git commit --no-verify -m x", "no-verify", {}),
            ("git push --force origin feat/x", "force-push", {}),
            ("git push origin main", "push-to-main", {}),
            ("git branch -D feat/x", "branch-force-delete", {}),
            ("git reset --hard", "reset-hard", {}),
            ("git clean -fd", "clean-force", {}),
            ("gh secret set TOKEN", "owner-gesture", {}),
            ("GIT_DIR=/x git status", "git-location", {}),
            ("gh pr merge 5 --merge && ls", "merge-form", {}),
            ("gh pr merge 5 --merge -b $X", "merge-variable", {}),
            ("gh pr merge 5 --merge", "merge-method", {"merge_method": ["squash"]}),
            ("gh pr merge 5 --merge", "merge-closes-refs", {"description": lambda *_t: "Refs #5\nCloses #5"}),
            (
                "gh pr merge 5 --merge",
                "commit-closes-refs",
                {"description": lambda *_t: "Refs #5", "commit_messages": lambda *_t: [("a" * 40, "Closes #5")]},
            ),
            ("gh pr merge 5 --merge", "commits-unreadable", {"commit_messages": lambda *_t: None}),
            ("gh pr merge 5 --merge", "infra-guard", {"pr_files": lambda *_t: ["plugins/forge/hooks/hooks.json"]}),
            (
                "gh pr merge 5 --merge",
                "protected-path",
                {"protected_paths": ["README.md"], "changed_files": lambda *_t: ["README.md"]},
            ),
            ("gh pr merge 5 --merge", "checks-not-green", {"green": False}),
        ]
        for command, rule, keys in cases:
            with self.subTest(command=command, rule=rule):
                self.assertEqual(named(command, **keys), rule)
        self.assertEqual(named("git commit -m x", branch="main"), "commit-on-main")
        self.assertEqual(named("gh alias set m 'pr merge'", subagent=True), "alias-change")

    def test_guard_coder_names_each_rule(self) -> None:
        for tool, tool_input, rule in [
            ("Bash", {"command": "gh pr merge 5"}, "gh-pr-merge"),
            ("Bash", {"command": "gh pr review 5 --approve"}, "gh-pr-review"),
            ("Bash", {"command": "gh issue close 5"}, "gh-issue-close"),
            ("Bash", {"command": "gh issue edit 5 --add-label x"}, "gh-issue-edit"),
            ("Skill", {"skill": "forge:qc"}, "skill-qc"),
            ("Skill", {"skill": "feature-review"}, "skill-feature-review"),
            ("Write", {"file_path": ""}, "no-isolation"),
        ]:
            with self.subTest(tool=tool, rule=rule):
                reason = guard_coder.refusal(tool, tool_input, "/w", lambda _cwd: (None, guard_coder.NO_ISOLATION))
                self.assertEqual(rule_of(str(reason), guard_coder.RULES), rule)
        for command, rule in [
            ("git push -u origin x", "push-upstream"),
            ("git push --force-with-lease origin x", "force-push"),
            ("git config user.name x", "config-write"),
            ("git rebase main", "rebase"),
            ("git pull --rebase", "rebase"),
            ("git add -A", "add-whole-tree"),
            ("git --git-dir=/x status", "git-dir"),
        ]:
            with self.subTest(command=command, rule=rule):
                reason = guard_coder.refusal("Bash", {"command": command})
                self.assertEqual(rule_of(str(reason), guard_coder.RULES), rule)
        outside = guard_coder.refusal("Write", {"file_path": "/elsewhere/a.py"}, "/w", lambda _cwd: ("/w", None))
        self.assertEqual(rule_of(str(outside), guard_coder.RULES), "outside-worktree")

    def test_guard_readonly_names_each_rule(self) -> None:
        for command, rule in [
            ("cat `which rm`", "hidden-command"),
            ("cat a > b", "redirection"),
            ("git diff --output=p.diff", "output-option"),
            ("rm -rf build", "not-a-read"),
        ]:
            with self.subTest(command=command, rule=rule):
                self.assertEqual(rule_of(str(guard_readonly.reader_refusal(command)), guard_readonly.RULES), rule)
        for command, rule in [
            ("git commit -m x", "git-history"),
            ("git config user.name x", "git-config"),
            ("git branch feat/new", "git-branch"),
            ("git checkout main", "working-copy"),
            ("gh pr comment 5 --body x", "gh-write"),
        ]:
            with self.subTest(command=command, rule=rule):
                reason = guard_readonly.gate_refusal(command, "/project", "/project")
                self.assertEqual(rule_of(str(reason), guard_readonly.RULES), rule)

    def test_the_verb_is_the_call_and_never_an_argument(self) -> None:
        for command, verb in [
            ("git push --force origin feat/x", "git push"),
            ("git -C /w commit -m 'a secret'", "git commit"),
            ("cd /w && gh pr merge 5 --merge", "gh pr merge"),
            ("GH_TOKEN=abc gh -R o/r issue close 3", "gh issue close"),
            (f'gh api -H "Authorization: token {SECRET}" repos/o/r', "gh api"),
            (f"curl -H 'Authorization: token {SECRET}' https://x", "curl"),
            (f"git {SECRET}", "git"),
            ("bash -c 'git reset --hard'", "git reset"),
            ("ls | wc -l", "ls"),
        ]:
            with self.subTest(command=command):
                self.assertEqual(guard_git.verb_of(command), verb)


if __name__ == "__main__":
    unittest.main()
