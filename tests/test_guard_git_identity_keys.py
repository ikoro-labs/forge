"""F-0003 A11, A16 (ticket #401, part a): the hook `guard_git` as a process, with the keys of the identity.

The keys are read in `docs/agents/usine-gardes.md` as `origin/main` holds it. Every repository is a
temporary one under a temporary `HOME`; no `CLAUDE_`, `GIT_`, `GH_TOKEN` or `GITHUB_TOKEN` of the
session reaches the hook, and the real `~/.claude` is never read nor written.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import support
from guard_git import RULES
from refusal_journal import rule_of
from test_guard_git_autonomy import git

GUARD_FILE = Path("docs") / "agents" / "usine-gardes.md"
GUARD = support.PLUGIN / "hooks" / "guard_git.py"
KEYS = "- `agent-token-command` : `python app_token.py`\n- `agent-login` : `forge-agents[bot]`\n"
INSTALLATION = "ghs_" + "x" * 12
HUMANS = "ghp_" + "h" * 12


@contextmanager
def project(on_main: str | None, in_tree: str | None = None) -> Iterator[Path]:
    """A repository whose `origin/main` holds `on_main` as the guard file (None: no file), and whose
    working tree then holds `in_tree` (None: left as committed)."""
    with tempfile.TemporaryDirectory() as folder:
        home = Path(folder) / "home"
        where = Path(folder) / "depot"
        home.mkdir()
        where.mkdir()
        git(where, home, "init", "-q", "-b", "feat/x")
        (where / "README.md").write_text("x\n", encoding="utf-8")
        if on_main is not None:
            (where / GUARD_FILE).parent.mkdir(parents=True)
            (where / GUARD_FILE).write_text(on_main, encoding="utf-8")
        git(where, home, "add", "-A")
        git(where, home, "commit", "-q", "-m", "init")
        git(where, home, "update-ref", "refs/remotes/origin/main", "HEAD")
        if in_tree is not None:
            (where / GUARD_FILE).parent.mkdir(parents=True, exist_ok=True)
            (where / GUARD_FILE).write_text(in_tree, encoding="utf-8")
        yield where


def run_guard(where: Path, tool: str, tool_input: dict[str, Any], **env: str) -> subprocess.CompletedProcess[str]:
    """`guard_git` as Claude Code runs it, with `env` (a token, say) added to a clean environment."""
    home = where.parent / "home"
    clean = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("CLAUDE_", "GIT_")) and name not in ("GH_TOKEN", "GITHUB_TOKEN")
    }
    clean.update(HOME=str(home), USERPROFILE=str(home), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    event = {"tool_name": tool, "tool_input": tool_input, "cwd": str(where)}
    return subprocess.run(  # noqa: S603 - the interpreter running this suite, the plugin's script
        [sys.executable, str(GUARD)],
        input=json.dumps(event),
        env={**clean, **env},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def bash(where: Path, command: str, **env: str) -> subprocess.CompletedProcess[str]:
    return run_guard(where, "Bash", {"command": command}, **env)


class AWriteNeedsTheInstallationTokenWhenTheKeysAreThere(unittest.TestCase):
    def test_a11_a_push_without_a_token_is_refused_and_says_whose_identity_the_gesture_takes(self) -> None:
        """F-0003 A11: exit 2, the refusal on stderr, naming the gesture and the key of the command."""
        with project(KEYS) as where:
            done = bash(where, "git push origin feat/x")
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("Blocked by the forge plugin (guard_git)", done.stderr)
        self.assertIn("`git push`", done.stderr)
        self.assertIn("the identity of the agents", done.stderr)
        self.assertIn("`agent-token-command`", done.stderr)

    def test_a11_the_writes_of_gh_are_refused_without_a_token(self) -> None:
        with project(KEYS) as where:
            for command in (
                "gh pr create --title t --body b",
                "gh issue comment 3 -b x",
                "gh api -X POST repos/o/r/issues/3/comments -f body=x",
            ):
                with self.subTest(command=command):
                    self.assertEqual(bash(where, command).returncode, 2)

    def test_a11_an_installation_token_in_the_environment_lets_the_same_commands_run(self) -> None:
        """F-0003 A11: `GH_TOKEN` or `GITHUB_TOKEN` starting with `ghs_`."""
        with project(KEYS) as where:
            for name in ("GH_TOKEN", "GITHUB_TOKEN"):
                for command in ("git push origin feat/x", "gh issue comment 3 -b x"):
                    with self.subTest(name=name, command=command):
                        done = bash(where, command, **{name: INSTALLATION})
                        self.assertEqual(done.returncode, 0, done.stderr)

    def test_a12_the_humans_token_is_refused_like_no_token_and_never_echoed(self) -> None:
        """F-0003 A12, T10: a `ghp_` token takes no write through, and is not in the refusal."""
        with project(KEYS) as where:
            done = bash(where, "git push origin feat/x", GH_TOKEN=HUMANS)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertNotIn(HUMANS, done.stderr)

    def test_a11_a_reading_runs_without_a_token(self) -> None:
        with project(KEYS) as where:
            for command in ("git status", "git fetch origin", "gh pr view 5", "gh issue list", "gh api repos/o/r/pulls/5"):
                with self.subTest(command=command):
                    self.assertEqual(bash(where, command).returncode, 0)

    def test_a11_the_refusal_is_journaled_under_the_rule_agent_identity(self) -> None:
        """F-0003 A11: the refusals journal of the temporary HOME names the rule `agent-identity`."""
        with project(KEYS) as where:
            bash(where, "git push origin feat/x")
            folder = where.parent / "home" / ".claude" / "hooks" / "state" / "refusals"
            lines = [
                json.loads(line)
                for path in sorted(folder.glob("*.jsonl"))
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
        self.assertEqual([(line["rule"], line["verb"]) for line in lines], [("agent-identity", "git push")])

    def test_a11_both_refusals_of_the_identity_have_their_rule_name(self) -> None:
        """F-0003 A11: the text of the two reasons holds the fixed phrase `RULES` looks for."""
        with project(KEYS) as where:
            written = bash(where, "git push origin feat/x").stderr
            mcp = run_guard(where, "mcp__github__issue_write", {"method": "create"}).stderr
        self.assertEqual(rule_of(written, RULES), "agent-identity")
        self.assertEqual(rule_of(mcp, RULES), "agent-identity")

    def test_a11_the_keys_are_those_of_origin_main_not_of_the_working_tree(self) -> None:
        """F-0003 A11: a key removed in the tree the agent edits still refuses; one added there asks nothing."""
        with project(KEYS, in_tree="") as where:
            self.assertEqual(bash(where, "git push origin feat/x").returncode, 2)
        with project("- `merge-method` : `merge`\n", in_tree=KEYS) as where:
            self.assertEqual(bash(where, "git push origin feat/x").returncode, 0)


class WithoutTheKeysNothingChanges(unittest.TestCase):
    def test_a16_without_the_keys_no_write_is_refused_for_the_identity(self) -> None:
        """F-0003 A16: a guard file without the keys, or one of the two keys alone, whatever the token."""
        one = "- `agent-login` : `forge-agents[bot]`\n"
        other = "- `agent-token-command` : `python app_token.py`\n"
        for on_main in ("- `merge-method` : `merge`\n", one, other, None):
            with self.subTest(on_main=on_main), project(on_main) as where:
                for env in ({}, {"GH_TOKEN": HUMANS}, {"GH_TOKEN": INSTALLATION}):
                    for command in ("git push origin feat/x", "gh pr create --title t", "gh issue close 3"):
                        done = bash(where, command, **env)
                        self.assertEqual(done.returncode, 0, f"{command} {env}: {done.stderr}")
                self.assertEqual(run_guard(where, "mcp__github__issue_write", {"method": "create"}).returncode, 0)


class AnMcpWriteIsRefusedClosed(unittest.TestCase):
    def test_a11_a_write_by_an_mcp_github_tool_is_refused_with_the_token_too(self) -> None:
        """F-0003 A11 (Q4): the server holds its own token, so the agents write by `gh`."""
        with project(KEYS) as where:
            for tool, tool_input in (
                ("mcp__github__issue_write", {"method": "create", "title": "t"}),
                ("mcp__github__add_issue_comment", {"issue_number": 3, "body": "x"}),
                ("mcp__github__create_pull_request", {"title": "t"}),
                ("mcp__plugin_github_github__pull_request_write", {"method": "update"}),
            ):
                for env in ({}, {"GH_TOKEN": INSTALLATION}):
                    with self.subTest(tool=tool, env=env):
                        done = run_guard(where, tool, tool_input, **env)
                        self.assertEqual(done.returncode, 2, done.stderr)
                        self.assertIn(f"`{tool}`", done.stderr)

    def test_a11_a_reading_by_an_mcp_github_tool_runs(self) -> None:
        with project(KEYS) as where:
            for tool in (
                "mcp__github__get_issue",
                "mcp__github__list_pull_requests",
                "mcp__github__search_code",
                "mcp__github__issue_read",
                "mcp__github__pull_request_read",
            ):
                with self.subTest(tool=tool):
                    self.assertEqual(run_guard(where, tool, {"issue_number": 3}).returncode, 0)

    def test_a11_the_merge_tool_still_answers_to_the_autonomy_key_when_the_token_is_there(self) -> None:
        """F-0003 A11: refused for the identity first, and the merge rules are not weakened by it."""
        with project(KEYS) as where:
            done = run_guard(where, "mcp__github__merge_pull_request", {"pullNumber": 5}, GH_TOKEN=INSTALLATION)
        self.assertEqual(done.returncode, 2, done.stderr)
