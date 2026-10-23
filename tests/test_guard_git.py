import io
import json
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import support
from guard_git import description_via_gh, guarded_main, native_directory, refusal


def never_green(_pr: str | None) -> bool:
    return False


def always_green(_pr: str | None) -> bool:
    return True


def refused(command: str, branch: str = "feat/x", green: bool = False) -> str | None:
    return refusal(command, branch, always_green if green else never_green)


def files(mapping: dict[str, str]) -> Callable[[str], str | None]:
    """The text of each path, as the hook would read it; None for a file it cannot read."""
    return lambda path: mapping.get(path)


def merge_refused(command: str, texts: dict[str, str], cwd: str | None = None) -> str | None:
    return refusal(command, "feat/x", always_green, cwd, read_text=files(texts))


# A squash body of the first of two PRs for one ticket: its prose closed the ticket.
SPLIT_TICKET_BODY = (
    "Refs #206: this PR delivers the ADRs for D and E, their structure note, their register and"
    " runbook rows. The exchange journal, which closes #206, follows in #216.\n"
)


class DangerousForms(unittest.TestCase):
    def test_the_dangerous_forms_are_refused_with_their_reason(self) -> None:
        cases = [
            ("git commit -m 'x'", "main", "commit on main"),
            ("git push origin main", "feat/x", "push to main"),
            ("git push origin HEAD:main", "feat/x", "push to main"),
            ("git push", "main", "push to main"),
            ("git push --force origin feat/x", "feat/x", "force push"),
            ("git push -f", "feat/x", "force push"),
            ("git branch -D feat/old", "feat/x", "forced branch deletion"),
            ("git reset --hard origin/main", "feat/x", "reset --hard"),
            ("git clean -fd", "feat/x", "clean -f"),
            ("git commit --no-verify -m x", "feat/x", "--no-verify"),
            ("cd apps/web && git push origin main", "feat/x", "push to main"),
            ("gh pr merge 61 --squash", "feat/x", "merge with checks not green"),
            ("git -C ../wt reset --hard origin/feat/x", "feat/x", "reset --hard"),
            ("git -C ../wt push origin main", "feat/x", "push to main"),
            ("git -c core.pager=cat clean -fd", "feat/x", "clean -f"),
            ("git --no-pager branch -D feat/old", "feat/x", "forced branch deletion"),
            ("git --git-dir=.git push --force origin feat/x", "feat/x", "force push"),
            ("git push origin +HEAD:feat/x", "feat/x", "force push"),
            ("git push -fu origin feat/x", "feat/x", "force push"),
            ("git branch --delete --force feat/old", "feat/x", "forced branch deletion"),
            ("git branch -df feat/old", "feat/x", "forced branch deletion"),
            ("git push origin HEAD:refs/heads/main", "feat/x", "push to main"),
            ("git push --all origin", "feat/x", "push to main"),
            ("git --config-env core.x=ENV reset --hard", "feat/x", "reset --hard"),
            ("git --attr-source HEAD clean -fd", "feat/x", "clean -f"),
        ]
        for command, branch, reason in cases:
            with self.subTest(command=command):
                verdict = refused(command, branch)
                self.assertIsNotNone(verdict)
                self.assertIn(reason, verdict or "")

    def test_the_neighbouring_safe_forms_pass(self) -> None:
        for command in [
            "git commit -m 'reset --hard is refused'",
            "git log --grep 'push origin main'",
            "git push -u origin HEAD",
            "git push --force-with-lease origin feat/x",
            "git branch -d feat/merged",
            "git checkout -b feat/new && git commit -m x",
            "git status && git diff --stat",
            "echo 'git push origin main'",
            "git -C ../wt status",
            "git clean -n",
            "git reset --soft HEAD~1",
            "git push origin feat/x:feat/x",
        ]:
            with self.subTest(command=command):
                branch = "main" if "checkout -b" in command else "feat/x"
                self.assertIsNone(refused(command, branch))

    def test_a_commit_message_in_a_heredoc_is_data_not_a_command(self) -> None:
        command = (
            "git commit -q -F - <<'EOF'\n"
            "fix: explain why git push --force origin main is refused\n"
            "EOF\n"
        )
        self.assertIsNone(refused(command))

    def test_a_merge_passes_once_every_check_is_green(self) -> None:
        self.assertIsNone(refused("gh pr merge 61 --squash", green=True))

    def test_a_repository_flag_before_the_verb_leaves_the_merge_judged(self) -> None:
        for command in [
            "gh -R o/r pr merge 61 --squash --body-file m.md",
            "gh --repo o/r pr merge 61 --squash --body-file m.md",
            "gh --repo=o/r pr merge 61 --squash --body-file m.md",
            "gh pr -R o/r merge 61 --squash --body-file m.md",
        ]:
            with self.subTest(command=command):
                self.assertIsNotNone(refused(command))
                self.assertIsNotNone(merge_refused(command, {"m.md": SPLIT_TICKET_BODY}))
                self.assertIsNone(merge_refused(command, {"m.md": "Closes #206\n"}))


class WhereGitActs(unittest.TestCase):
    def test_the_branch_is_the_one_where_git_acts_not_where_the_agent_stands(self) -> None:
        mapping = {"../wt-main": "main", "wt-main": "main"}

        def on_main(directory: str | None) -> str:
            return mapping.get(directory or "", "feat/x")

        self.assertIsNotNone(refusal("git -C ../wt-main commit -m x", on_main, never_green))
        self.assertIsNotNone(refusal("cd wt-main && git commit -m x", on_main, never_green))
        self.assertIsNone(refusal("git commit -m x", on_main, never_green))

    def test_a_directory_whose_branch_cannot_be_read_is_judged_as_the_event_cwd(self) -> None:
        def branch_of(directory: str | None) -> str:
            return {"/repo": "main", "/repo/../repo-feat": "feat/x"}.get(directory or "", "")

        for command in [
            "cd ~/anything && git commit -m x",
            'cd "$CLAUDE_PROJECT_DIR" && git commit -m x',
            "cd - && git commit -m x",
            "(cd ../repo-feat && git status) && git commit -m x",
            "cd does/not/exist && git commit -m x",
            'cd "$OTHER" && cd ../repo-feat && git commit -m x',
            "cd ~ && git -C ../repo-feat commit -m x",
        ]:
            with self.subTest(command=command):
                verdict = refusal(command, branch_of, never_green, cwd="/repo")
                self.assertIn("commit on main", verdict or "")

    def test_an_absolute_cd_leaves_the_unknown_directory(self) -> None:
        for target in ("/work/repo-feat", "C:/work/repo-feat"):

            def branch_of(directory: str | None, target: str = target) -> str:
                return {"/repo": "main", target: "feat/x"}.get(directory or "", "")

            command = f'cd "$OTHER" && cd {target} && git commit -m x'
            with self.subTest(target=target):
                self.assertIsNone(refusal(command, branch_of, never_green, cwd="/repo"))

    def test_a_git_bash_path_is_read_as_windows_reads_it(self) -> None:
        for directory, platform, native in [
            ("/c/Users/dev/repo", "win32", "c:/Users/dev/repo"),
            ("/d", "win32", "d:/"),
            ("/srv/repo", "win32", "/srv/repo"),
            ("../wt", "win32", "../wt"),
            ("C:/work/repo", "win32", "C:/work/repo"),
            ("/c/Users/dev/repo", "linux", "/c/Users/dev/repo"),
            (None, "win32", None),
        ]:
            with self.subTest(directory=directory, platform=platform):
                self.assertEqual(native_directory(directory, platform), native)


class SplitTicket(unittest.TestCase):
    def test_a_squash_body_that_cites_a_ticket_with_refs_may_not_close_it(self) -> None:
        verdict = merge_refused(
            "gh pr merge 215 --squash --body-file m.md", {"m.md": SPLIT_TICKET_BODY}
        )
        self.assertIn("#206", verdict or "")
        self.assertIn("closes #206", verdict or "")

    def test_a_split_ticket_cited_without_a_closing_keyword_passes(self) -> None:
        body = "Refs #206: the ADRs for D and E. The exchange journal follows in #216.\n"
        self.assertIsNone(merge_refused("gh pr merge 215 --squash --body-file m.md", {"m.md": body}))

    def test_a_ticket_closed_and_never_cited_with_refs_passes(self) -> None:
        body = "The exchange journal.\n\nCloses #206\n"
        self.assertIsNone(merge_refused("gh pr merge 216 --squash --body-file m.md", {"m.md": body}))

    def test_the_merge_that_deletes_its_branch_is_judged_like_any_merge(self) -> None:
        command = "gh pr merge 215 --squash --delete-branch --body-file m.md"
        self.assertIsNotNone(merge_refused(command, {"m.md": SPLIT_TICKET_BODY}))
        self.assertIsNone(merge_refused(command, {"m.md": "Refs #206: the ADRs.\n"}))
        self.assertIsNone(refused("git push origin --delete chore/merged", "main"))

    def test_every_closing_keyword_github_reads_is_caught(self) -> None:
        for closing in ["Closed #206", "fix #206", "Fixes #206", "resolved: #206", "RESOLVES o/r#206"]:
            body = f"Refs: #206, the first half.\n\n{closing}\n"
            with self.subTest(closing=closing):
                self.assertIsNotNone(
                    merge_refused("gh pr merge 1 --squash --body-file m.md", {"m.md": body})
                )

    def test_the_subject_and_an_inline_body_are_read_too(self) -> None:
        command = 'gh pr merge 1 --squash --subject "docs: x, fixes #12" --body "Refs #12"'
        self.assertIsNotNone(merge_refused(command, {}))
        self.assertIsNone(merge_refused('gh pr merge 1 --squash -t "docs: x" -b "Refs #12"', {}))

    def test_the_body_file_is_read_where_the_command_stands(self) -> None:
        command = "cd /work && gh pr merge 1 --squash --body-file=m.md"
        self.assertIsNotNone(merge_refused(command, {"/work/m.md": SPLIT_TICKET_BODY}, cwd="/repo"))

    def test_a_body_file_the_hook_cannot_read_is_left_to_gh(self) -> None:
        self.assertIsNone(merge_refused("gh pr merge 1 --squash --body-file gone.md", {}))

    def test_the_pr_description_is_read_too_since_github_closes_from_it(self) -> None:
        body = "Refs #322: part 3d.\n"
        description = "Refs #322\n\n- **REX:** a front ticket before #507 closes #322.\n"
        command = "gh pr merge 506 --squash --body-file m.md"
        verdict = refusal(
            command,
            "feat/x",
            always_green,
            read_text=files({"m.md": body}),
            description=lambda pr: description if pr == "506" else "",
        )
        self.assertIn("closes #322", verdict or "")
        self.assertIsNone(merge_refused(command, {"m.md": body}))

    def test_a_description_gh_prints_in_utf8_is_read_whatever_the_console_code_page(self) -> None:
        # gh is played by Python, which runs the script named `pr` of the command's directory.
        script = "import sys; sys.stdout.buffer.write('Refs #322. \\u0141 closes #322'.encode())"
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "pr").write_text(script, encoding="utf-8")
            with mock.patch("shutil.which", lambda _name: sys.executable):
                description = description_via_gh(folder)
                verdict = refusal("gh pr merge 506", "feat/x", always_green, description=description)
        self.assertIn("closes #322", verdict or "")


class FailsClosed(unittest.TestCase):
    def test_hooks_json_turns_a_crash_of_guard_git_into_a_refusal(self) -> None:
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        found = [
            hook
            for group in hooks["hooks"]["PreToolUse"]
            for hook in group["hooks"]
            if "guard_git.py" in hook["command"]
        ]
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["command"].endswith("|| exit 2"))

    def test_hooks_json_blocks_the_command_when_guard_git_times_out(self) -> None:
        # `|| exit 2` does not cover a timeout: the shell is killed before it can run it.
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        found = [
            hook
            for group in hooks["hooks"]["PreToolUse"]
            for hook in group["hooks"]
            if "guard_git.py" in hook["command"]
        ]
        self.assertEqual(found[0].get("onFailure"), "block")

    def test_a_guard_that_raises_refuses_and_says_it_failed(self) -> None:
        stderr = io.StringIO()
        with mock.patch("guard_git.main", side_effect=RuntimeError("boom")):
            with mock.patch("sys.stderr", stderr):
                code = guarded_main()
        self.assertEqual(code, 2)
        self.assertIn("guard_git failed", stderr.getvalue())
        self.assertIn("refused as a precaution", stderr.getvalue())
        self.assertIn("RuntimeError", stderr.getvalue())

    def test_an_event_that_is_not_json_is_a_refusal_not_a_traceback(self) -> None:
        stderr = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("not json")), mock.patch("sys.stderr", stderr):
            code = guarded_main()
        self.assertEqual(code, 2)
        self.assertIn("refused as a precaution", stderr.getvalue())

    def test_a_refusal_of_a_rule_is_not_reworded_as_a_failure(self) -> None:
        event = json.dumps({"tool_input": {"command": "git push --force"}, "cwd": None})
        stderr = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(event)), mock.patch("sys.stderr", stderr):
            code = guarded_main()
        self.assertEqual(code, 2)
        self.assertIn("force push", stderr.getvalue())
        self.assertNotIn("guard_git failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
