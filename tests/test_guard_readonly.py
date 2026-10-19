import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401
from guard_readonly import gate_refusal, main, reader_refusal, refusal, split_redirections


class ReaderCommands(unittest.TestCase):
    def test_reads_pass(self) -> None:
        for command in [
            "git log --oneline -5 2>/dev/null | head -3",
            "git diff origin/main...HEAD --stat",
            "git show HEAD:docs/x.md",
            "git branch 2>&1",
            "git branch -a --list 'feat/*'",
            "git config --get remote.origin.url",
            "git remote -v",
            "git worktree list",
            "gh pr view 61 --json body,files",
            "gh pr diff 61",
            "gh api repos/o/r/pulls/61/comments",
            "gh api -X GET repos/o/r/issues",
            "rg -n 'def main' plugins | sort | uniq -c",
            "find . -name '*.md' -type f",
            "sed -n '1,20p' README.md",
            "cat a.md >&2",
            "cd docs && ls -la",
        ]:
            with self.subTest(command=command):
                self.assertIsNone(reader_refusal(command))

    def test_writes_are_refused(self) -> None:
        for command, reason in [
            ("cat a > b", "by a redirection"),
            ("echo x >> notes.md", "by a redirection"),
            ("git log 2> err.txt", "by a redirection"),
            ("sed -i 's/a/b/' x.md", "not a read"),
            ("sort -o out.txt in.txt", "not a read"),
            ("uniq in.txt out.txt", "not a read"),
            ("find . -name x -delete", "not a read"),
            ("find . -exec rm {} ;", "not a read"),
            ("git commit -m x", "not a read"),
            ("git checkout main", "not a read"),
            ("git branch feat/new", "not a read"),
            ("git config user.name x", "not a read"),
            ("git diff --output=patch.diff", "writes a file"),
            ("gh pr comment 61 --body x", "not a read"),
            ("gh pr merge 61", "not a read"),
            ("gh api -X POST repos/o/r/issues", "not a read"),
            ("gh api repos/o/r/issues -f title=x", "not a read"),
            ("rm -rf build", "not a read"),
            ("python -c 'open(\"x\", \"w\")'", "not a read"),
            ("cat `which rm`", "hides the command"),
            ("diff <(ls a) <(ls b)", "hides the command"),
            ("ls && touch x", "not a read"),
        ]:
            with self.subTest(command=command):
                self.assertIn(reason, reader_refusal(command) or "")

    def test_a_project_prefix_lets_its_reads_through(self) -> None:
        self.assertIsNotNone(reader_refusal("uv run python scripts/features.py status"))
        self.assertIsNone(
            reader_refusal("uv run python scripts/features.py status", ["uv run python scripts/features.py status"])
        )

    def test_redirections_are_told_from_their_files(self) -> None:
        self.assertEqual(split_redirections(["cat", "a", ">", "b"]), (["cat", "a"], ["b"]))
        self.assertEqual(split_redirections(["git", "log", "2", ">", "/dev/null"]), (["git", "log"], []))
        self.assertEqual(split_redirections(["git", "branch", "2", ">&", "1"]), (["git", "branch"], []))


class GateCommands(unittest.TestCase):
    def test_the_head_copy_can_be_built_and_measured(self) -> None:
        for command in [
            "git worktree add /tmp/qc-61 origin/feat/x",
            "cd /tmp/qc-61 && git checkout --detach origin/feat/x && uv sync --locked",
            "cd /tmp/qc-61 && pnpm install --frozen-lockfile && pnpm test",
            "git fetch origin",
            "gh pr checks 61",
            "gh api repos/o/r/check-runs/1/annotations",
            "git diff origin/main...origin/feat/x --stat",
        ]:
            with self.subTest(command=command):
                self.assertIsNone(gate_refusal(command, "/repo", "/repo"))

    def test_the_gate_never_changes_a_history_github_or_the_project_copy(self) -> None:
        for command, reason in [
            ("git commit -m x", "never changes a history"),
            ("git push origin feat/x", "never changes a history"),
            ("git checkout main", "outside it"),
            ("git -C /repo checkout main", "outside it"),
            ("cd /repo/apps && git restore .", "outside it"),
            ("gh pr comment 61 --body x", "never writes to GitHub"),
            ("gh pr merge 61", "never writes to GitHub"),
        ]:
            with self.subTest(command=command):
                self.assertIn(reason, gate_refusal(command, "/repo", "/repo") or "")


class Events(unittest.TestCase):
    def event(self, agent: str, tool: str, tool_input: object, cwd: str = "/repo") -> dict[str, object]:
        return {"agent_type": agent, "tool_name": tool, "tool_input": tool_input, "cwd": cwd}

    def test_only_the_judges_and_the_configured_readers_are_guarded(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "docs" / "agents").mkdir(parents=True)
            (Path(root) / "docs" / "agents" / "usine.md").write_text(
                "- `readonly-agent`: `pricing-arbiter`\n", encoding="utf-8"
            )
            write = {"file_path": "x.md", "content": "x"}
            with mock.patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": root}):
                for agent in ("forge:qc-conf", "forge:qc-gate", "forge:staff-engineer", "pricing-arbiter"):
                    with self.subTest(agent=agent):
                        self.assertIn("never writes", refusal(self.event(agent, "Write", write)) or "")
                self.assertIsNone(refusal(self.event("forge:coder", "Write", write)))
                self.assertIsNone(refusal(self.event("forge:coder", "Bash", {"command": "rm -rf x"})))
                self.assertIsNone(refusal(self.event("forge:qc-conf", "Read", {"file_path": "x"})))
                self.assertIsNotNone(refusal(self.event("forge:qc-conf", "Bash", "x")))

    def test_main_refuses_with_exit_2_and_fails_closed(self) -> None:
        def run(stdin: str) -> int:
            with mock.patch("sys.stdin", io.StringIO(stdin)), mock.patch("sys.stderr", io.StringIO()):
                return main()

        reader = {"agent_type": "forge:qc-conf", "tool_name": "Bash", "tool_input": {"command": "cat a > b"}}
        self.assertEqual(run(json.dumps(reader)), 2)
        reader["tool_input"] = {"command": "cat a"}
        self.assertEqual(run(json.dumps(reader)), 0)
        self.assertEqual(run("not json"), 2)


if __name__ == "__main__":
    unittest.main()
