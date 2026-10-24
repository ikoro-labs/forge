import contextlib
import io
import json
import os
import shutil
import subprocess
import stat
import sys
import tempfile
import time
import unittest
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest import mock

import support
from guard_git import OWNER_KEY, description_via_gh, guarded_main, main, native_directory, refusal


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


@contextlib.contextmanager
def isolated_environment() -> Iterator[None]:
    """HOME and USERPROFILE in an empty folder, and no `CLAUDE_` variable of the session running us."""
    with tempfile.TemporaryDirectory() as home:
        env = {name: value for name, value in os.environ.items() if not name.startswith("CLAUDE_")}
        env.update(HOME=home, USERPROFILE=home)
        with mock.patch.dict("os.environ", env, clear=True):
            yield


def guard_git_hook() -> dict[str, str]:
    hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    found = [
        hook
        for group in hooks["hooks"]["PreToolUse"]
        for hook in group["hooks"]
        if "guard_git.py" in hook["command"]
    ]
    assert len(found) == 1
    return found[0]


class FailsClosed(unittest.TestCase):
    def test_hooks_json_turns_a_crash_of_guard_git_into_a_refusal(self) -> None:
        command = guard_git_hook()["command"]
        self.assertIn("|| {", command)
        self.assertTrue(command.endswith("exit 2; }"))

    @unittest.skipUnless(
        shutil.which("bash") and sys.platform != "win32",
        "the command of hooks.json is run by the POSIX shell of Linux and macOS; under Windows"
        " Claude Code runs it in Git Bash, which this suite has not tried",
    )
    def test_a_failure_before_the_guard_runs_is_refused_and_says_so(self) -> None:
        def run(uv_script: str | None) -> subprocess.CompletedProcess[str]:
            with tempfile.TemporaryDirectory() as folder:
                if uv_script is not None:
                    fake = Path(folder) / "uv"
                    fake.write_text(f"#!/bin/sh\n{uv_script}\n", encoding="utf-8")
                    fake.chmod(0o755)
                return subprocess.run(  # noqa: S603 - the shell is found by shutil.which
                    [str(shutil.which("bash")), "-c", guard_git_hook()["command"]],
                    env={"PATH": folder, "CLAUDE_PLUGIN_ROOT": str(support.PLUGIN)},
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30,
                )

        for name, script in (
            ("uv is missing", None),
            ("uv fails", "echo 'ModuleNotFoundError: usine' >&2; exit 1"),
        ):
            with self.subTest(case=name):
                done = run(script)
                self.assertEqual(done.returncode, 2)
                self.assertIn("guard_git failed", done.stderr)
                self.assertIn("refused as a precaution", done.stderr)
        # A refusal of a rule is already worded by the guard: not reworded as a failure.
        done = run("echo 'Blocked by the forge plugin (guard_git): force push.' >&2; exit 2")
        self.assertEqual(done.returncode, 2)
        self.assertIn("force push", done.stderr)
        self.assertNotIn("guard_git failed", done.stderr)
        done = run("exit 0")
        self.assertEqual((done.returncode, done.stderr), (0, ""))

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

    def test_an_ordinary_command_never_makes_the_guard_fail(self) -> None:
        # The real `main`, on commands that are none of its business: a crash would refuse them.
        for name, command in (
            ("empty", ""),
            ("a heredoc without gh", "cat > notes.md <<'EOF'\nline one\nline two\nEOF"),
            ("a heredoc never closed", "cat <<EOF\nline one"),
            ("a heredoc to a shell", "bash <<'EOF'\necho hello\nEOF"),
            ("an unclosed quote", 'echo "unclosed'),
            ("an unclosed quote on gh", "gh api graphql -f query='query { viewer"),
            ("an unclosed substitution", 'echo "$(cat <<EOF'),
            ("a very long line", "echo " + "a" * 300_000),
            ("a very long heredoc line", "cat <<EOF\n" + "b" * 300_000 + "\nEOF"),
            ("a very long gh line", "gh api graphql -f query='query { " + "viewer " * 40_000 + "}'"),
            ("only operators", "&& || ; |"),
            ("a dangling sudo", "sudo -u"),
            ("a dangling env", "env"),
            ("a null byte", "ls \x00 ./config.sh"),
            ("non-ASCII", "echo 'été ✓' && ls"),
        ):
            event = json.dumps({"tool_input": {"command": command}, "cwd": None})
            stderr = io.StringIO()
            with (
                self.subTest(case=name),
                isolated_environment(),
                mock.patch("sys.stdin", io.StringIO(event)),
                mock.patch("sys.stderr", stderr),
            ):
                code = guarded_main()
                self.assertNotIn("guard_git failed", stderr.getvalue())
                self.assertEqual(code, 0, stderr.getvalue())

    def test_a_refusal_of_a_rule_is_not_reworded_as_a_failure(self) -> None:
        event = json.dumps({"tool_input": {"command": "git push --force"}, "cwd": None})
        stderr = io.StringIO()
        with (
            isolated_environment(),
            mock.patch("sys.stdin", io.StringIO(event)),
            mock.patch("sys.stderr", stderr),
        ):
            code = guarded_main()
        self.assertEqual(code, 2)
        self.assertIn("force push", stderr.getvalue())
        self.assertNotIn("guard_git failed", stderr.getvalue())


@contextlib.contextmanager
def runner_folder() -> Iterator[str]:
    """A folder laid out like an unpacked Actions runner: `run.sh` and `bin/Runner.Listener`."""
    with tempfile.TemporaryDirectory() as folder:
        (Path(folder) / "bin").mkdir()
        (Path(folder) / "bin" / "Runner.Listener").write_text("", encoding="utf-8")
        (Path(folder) / "run.sh").write_text("", encoding="utf-8")
        yield Path(folder).as_posix()


@contextlib.contextmanager
def windows_runner_folder() -> Iterator[str]:
    """A folder laid out like an unpacked Windows runner: `run.cmd` and `bin/Runner.Listener.exe`."""
    with tempfile.TemporaryDirectory() as folder:
        (Path(folder) / "bin").mkdir()
        (Path(folder) / "bin" / "Runner.Listener.exe").write_text("", encoding="utf-8")
        (Path(folder) / "bin" / "Runner.Listener.dll").write_text("", encoding="utf-8")
        (Path(folder) / "run.cmd").write_text("", encoding="utf-8")
        yield Path(folder).as_posix()


def refused_in(command: str, cwd: str) -> str | None:
    return refusal(command, "feat/x", always_green, cwd)


OWNER_REFUSAL = "geste du propriétaire du dépôt, à lister pour l'humain en fin de compte rendu"
OWNER_KEY_VALUE = "gh label delete | les étiquettes sont au propriétaire"


def owner_refused(command: str, lines: list[str]) -> str | None:
    return refusal(command, "feat/x", always_green, owner_gestures=lines)


class OwnerGestures(unittest.TestCase):
    """Les gestes du propriétaire du dépôt, refusés à tout agent."""

    def test_the_gh_commands_of_the_owner_are_refused_and_named(self) -> None:
        cases = [
            ("gh secret set TOKEN --body x", "gh secret set"),
            ("gh secret delete TOKEN", "gh secret delete"),
            ("gh variable set NAME --body x", "gh variable set"),
            ("gh variable delete NAME", "gh variable delete"),
            ("gh repo edit --visibility public", "gh repo edit --visibility"),
            ("gh repo edit o/r --visibility=private --accept-visibility-change-consequences",
             "gh repo edit --visibility"),
            ("gh repo delete o/r --yes", "gh repo delete"),
            ("gh repo rename new-name", "gh repo rename"),
            ("gh repo archive o/r --yes", "gh repo archive"),
            ("gh repo deploy-key add key.pub", "gh repo deploy-key add"),
            ("cd /work && gh secret set X", "gh secret set"),
            ("echo ok; gh variable set X --body 1", "gh variable set"),
        ]
        for command, gesture in cases:
            with self.subTest(command=command):
                verdict = refused(command)
                self.assertIn(gesture, verdict or "")
                self.assertIn(OWNER_REFUSAL, verdict or "")

    def test_gh_global_options_and_environment_do_not_hide_a_gesture(self) -> None:
        for command in (
            "gh -R o/r secret set TOKEN --body x",
            "gh --repo=o/r secret set TOKEN",
            "GH_TOKEN=x gh -R o/r variable delete NAME",
            "gh secret -R o/r set TOKEN",
        ):
            with self.subTest(command=command):
                self.assertIn(OWNER_REFUSAL, refused(command) or "")

    def test_the_reads_of_the_same_commands_stay_allowed(self) -> None:
        for command in (
            "gh secret list",
            "gh variable list",
            "gh variable get NAME",
            "gh repo view o/r",
            "gh repo edit --description 'x'",
            "gh repo list",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))

    def test_a_write_by_gh_api_on_an_owner_endpoint_is_refused(self) -> None:
        cases = [
            "gh api -X PUT repos/o/r/collaborators/bob -f permission=push",
            "gh api --method DELETE /repos/o/r/collaborators/bob",
            "gh api -X DELETE repos/o/r/invitations/12",
            "gh api -X PUT repos/o/r/branches/main/protection --input p.json",
            "gh api -X PUT repos/o/r/branches/release/1.x/protection -f x=1",
            "gh api repos/o/r/rulesets -f name=x",
            "gh api -X PUT repos/o/r/rulesets/9 --input r.json",
            "gh api -X POST repos/o/r/actions/runners/registration-token",
            "gh api -X DELETE repos/o/r/actions/runners/4",
            "gh api -X PUT repos/o/r/actions/secrets/TOKEN -f encrypted_value=x",
            "gh api -X DELETE repos/o/r/actions/variables/NAME",
            "gh api -X POST repos/o/r/actions/variables -f name=A -f value=1",
            "gh api -X PATCH repos/o/r -f private=false",
            "gh api -X DELETE repos/o/r",
            "gh api -X POST repos/o/r/transfer -f new_owner=x",
            "gh api -X POST repos/o/r/keys -f key=k",
            "gh api -X POST repos/o/r/hooks --input h.json",
            "gh api -X PUT repos/o/r/environments/prod",
            "gh api -X PUT repos/o/r/actions/permissions -F enabled=true",
            "gh api -X PUT orgs/o/actions/secrets/TOKEN",
            "gh api -XDELETE repos/o/r/collaborators/bob",
            "gh -R o/r api -X DELETE repos/{owner}/{repo}/collaborators/bob",
            "gh api repos/o/r/collaborators/bob?permission=push -X PUT",
            "gh api -H 'Accept: application/json' -X PUT repos/o/r/rulesets/1",
        ]
        for command in cases:
            with self.subTest(command=command):
                verdict = refused(command)
                self.assertIn(OWNER_REFUSAL, verdict or "")
                self.assertIn("gh api", verdict or "")

    def test_a_read_by_gh_api_stays_allowed_even_on_an_owner_endpoint(self) -> None:
        for command in (
            "gh api repos/o/r/collaborators",
            "gh api -X GET repos/o/r/rulesets",
            "gh api --method HEAD repos/o/r/branches/main/protection",
            "gh api repos/o/r/actions/secrets",
            "gh api repos/o/r/actions/runners --jq '.runners[].name'",
            "gh api repos/o/r",
            "gh api repos/o/r/pulls/3 -X GET -f state=open",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))

    def test_an_explicit_get_or_head_stays_a_read_even_with_fields(self) -> None:
        for command in (
            "gh api -X GET repos/o/r/collaborators -f per_page=100",
            "gh api --method GET repos/o/r/collaborators -F per_page=100",
            "gh api --method=get repos/o/r/rulesets --raw-field includes_parents=true",
            "gh api -XGET repos/o/r/actions/secrets -f per_page=100",
            "gh api -X HEAD repos/o/r/keys -f per_page=1",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))

    def test_a_repeated_method_counts_as_the_last_one_like_gh_does(self) -> None:
        for command in (
            "gh api -X GET repos/o/r/collaborators/bob -X PUT",
            "gh api --method GET --method PUT repos/o/r/collaborators/bob",
            "gh api -XGET repos/o/r/collaborators/bob --method=PUT",
        ):
            with self.subTest(command=command):
                verdict = refused(command) or ""
                self.assertIn(OWNER_REFUSAL, verdict)
                self.assertIn("PUT", verdict)
        for command in (
            "gh api -X PUT repos/o/r/collaborators/bob -X GET",
            "gh api --method PUT --method GET repos/o/r/collaborators",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))

    def test_fields_without_a_method_are_a_post_and_the_refusal_says_so(self) -> None:
        for command in (
            "gh api repos/o/r/collaborators -f per_page=100",
            "gh api repos/o/r/rulesets --input r.json",
        ):
            with self.subTest(command=command):
                verdict = refused(command) or ""
                self.assertIn(OWNER_REFUSAL, verdict)
                self.assertIn("POST", verdict)
                self.assertNotIn("GET", verdict)

    def test_a_write_by_gh_api_outside_the_owner_endpoints_is_left_alone(self) -> None:
        for command in (
            "gh api -X POST repos/o/r/issues/3/comments -f body=x",
            "gh api -X PUT repos/o/r/contents/plugins/forge/hooks/x.py -f message=m",
            "gh api -X PATCH repos/o/r/issues/3 -f state=closed",
            "gh api -X POST repos/o/r/git/refs -f ref=refs/heads/x",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))

    def test_graphql_mutations_of_protection_ruleset_collaborator_and_repository_are_refused(
        self,
    ) -> None:
        for mutation in (
            'createBranchProtectionRule(input: {pattern: "main"})',
            "updateBranchProtectionRule(input: {})",
            'deleteBranchProtectionRule(input: {id: "x"})',
            "createRepositoryRuleset(input: {})",
            "updateRepositoryRuleset(input: {})",
            "deleteRepositoryRuleset(input: {})",
            'updateRepository(input: {repositoryId: "x", hasIssuesEnabled: false})',
            'deleteRepository(input: {repositoryId: "x"})',
            'archiveRepository(input: {repositoryId: "x"})',
            "transferRepository(input: {})",
            "addRepositoryCollaborator(input: {})",
            "removeRepositoryCollaborator(input: {})",
        ):
            command = f"gh api graphql -f query='mutation {{ {mutation} {{ clientMutationId }} }}'"
            with self.subTest(mutation=mutation):
                verdict = refused(command)
                self.assertIn(OWNER_REFUSAL, verdict or "")
                self.assertIn("gh api graphql", verdict or "")

    def test_the_runner_scripts_are_refused_behind_a_wrapper_too(self) -> None:
        for command in (
            "./config.sh --url https://github.com/o/r --token T",
            "cd actions-runner && ./config.sh remove --token T",
            ".\\config.cmd --url https://github.com/o/r --token T",
            "config.cmd remove",
            "sudo ./svc.sh install",
            "sudo -u runner ./svc.sh start",
            "sudo bash ./config.sh --token T",
            "bash config.sh --token T",
            "sh -x ./svc.sh uninstall",
            "cmd /c config.cmd --token T",
            "C:\\actions-runner\\config.cmd --token T",
            "/home/runner/actions-runner/svc.sh stop",
        ):
            with self.subTest(command=command):
                verdict = refused(command)
                self.assertIn(OWNER_REFUSAL, verdict or "")
                self.assertRegex(verdict or "", r"config\.(sh|cmd)|svc\.sh")

    def test_a_runner_status_and_other_scripts_stay_allowed(self) -> None:
        for command in (
            "sudo ./svc.sh status",
            "./run.sh",
            "bash ./build.sh",
            "cat config.sh",
            "grep -n token config.cmd",
            "sudo apt update",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))

    def test_a_script_with_a_runner_argument_is_refused_wherever_it_stands(self) -> None:
        for command in (
            "./config.sh --url https://github.com/o/r --token T",
            "scripts/config.sh --token=T",
            "bash scripts/config.sh --url=https://github.com/o/r",
            "./svc.sh install",
            "sudo ./svc.sh uninstall",
            "./svc.sh start",
            "./svc.sh stop",
        ):
            with self.subTest(command=command):
                self.assertIn(OWNER_REFUSAL, refused(command) or "")

    def test_a_config_script_of_a_project_is_not_a_runner_script(self) -> None:
        with runner_folder() as runner, tempfile.TemporaryDirectory() as plain:
            for command in (
                "bash scripts/config.sh",
                "bash scripts/config.sh --verbose",
                "./config.sh --dry-run",
                f"cd {plain} && ./config.sh",
                f"{plain}/svc.sh",
                f"{plain}/svc.sh status",
                f"cd {runner} && ./svc.sh status",
            ):
                with self.subTest(command=command):
                    self.assertIsNone(refused_in(command, plain))

    def test_a_script_in_a_runner_folder_is_refused_without_any_argument(self) -> None:
        with runner_folder() as runner, tempfile.TemporaryDirectory() as plain:
            for command, cwd in (
                ("./config.sh", runner),
                ("bash ./svc.sh", runner),
                ("./config.cmd", runner),
                (f"{runner}/config.sh", plain),
                (f"cd {runner} && ./config.sh", plain),
                (f"sudo -u runner {runner}/svc.sh", plain),
            ):
                with self.subTest(command=command):
                    self.assertIn(OWNER_REFUSAL, refused_in(command, cwd) or "")

    def test_a_script_in_a_windows_runner_folder_is_refused_without_any_argument(self) -> None:
        with windows_runner_folder() as runner, tempfile.TemporaryDirectory() as plain:
            for command, cwd in (
                ("./config.cmd", runner),
                ("cmd /c config.cmd", runner),
                (f"{runner}/config.cmd", plain),
                (f"cd {runner} && ./config.cmd", plain),
                (f"cd {runner} && cd bin/.. && ./config.cmd", plain),
            ):
                with self.subTest(command=command):
                    self.assertIn(OWNER_REFUSAL, refused_in(command, cwd) or "")
            for command, cwd in (("./config.cmd", plain), (f"{plain}/config.cmd", plain)):
                with self.subTest(command=command):
                    self.assertIsNone(refused_in(command, cwd))

    def test_a_folder_with_only_one_marker_is_not_a_runner_folder(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "bin").mkdir()
            (Path(folder) / "bin" / "Runner.Listener.exe").write_text("", encoding="utf-8")
            self.assertIsNone(refused_in("./config.cmd", Path(folder).as_posix()))
            (Path(folder) / "run.cmd").write_text("", encoding="utf-8")
            self.assertIn(OWNER_REFUSAL, refused_in("./config.cmd", Path(folder).as_posix()) or "")

    def test_a_runner_registered_by_its_environment_or_by_other_options_is_refused(self) -> None:
        for command in (
            "./config.sh --unattended",
            "./config.sh --unattended --pat=P",
            "./config.sh --pat P",
            "scripts/config.sh --pat=P",
            "ACTIONS_RUNNER_INPUT_URL=https://github.com/o/r ACTIONS_RUNNER_INPUT_TOKEN=T ./config.sh",
            "ACTIONS_RUNNER_INPUT_TOKEN=T ./config.sh --unattended",
            "env ACTIONS_RUNNER_INPUT_TOKEN=T ./config.sh",
            "sudo env ACTIONS_RUNNER_INPUT_URL=u bash ./config.sh",
            "export ACTIONS_RUNNER_INPUT_TOKEN=T",
            "export ACTIONS_RUNNER_INPUT_TOKEN=T && ./config.sh",
            "ACTIONS_RUNNER_INPUT_TOKEN=T",
            "bash -c 'ACTIONS_RUNNER_INPUT_TOKEN=T ./config.sh'",
            "bash <<'EOF'\nACTIONS_RUNNER_INPUT_TOKEN=T ./config.sh\nEOF",
            "echo x; ACTIONS_RUNNER_INPUT_NAME=n ./config.sh",
        ):
            with self.subTest(command=command):
                self.assertIn(OWNER_REFUSAL, refused(command) or "")
        for command in (
            "echo ACTIONS_RUNNER_INPUT_URL",
            "grep -r ACTIONS_RUNNER_INPUT_ docs",
            "./config.sh --dry-run",
            "ACTIONS_RUNNER=1 ./build.sh",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))

    def test_gh_global_options_before_deploy_key_do_not_hide_its_action(self) -> None:
        for command in (
            "gh repo deploy-key -R o/r add key.pub",
            "gh repo deploy-key --repo=o/r delete 5",
            "gh -R o/r repo deploy-key -R o/r add key.pub",
        ):
            with self.subTest(command=command):
                self.assertIn("deploy-key", refused(command) or "")
        for command in ("gh repo deploy-key -R o/r list", "gh repo deploy-key list"):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))

    def test_sudo_with_a_joined_option_env_and_nohup_do_not_hide_a_runner_script(self) -> None:
        for command in (
            "sudo -iu runner ./svc.sh install",
            "sudo -u runner -H ./svc.sh start",
            "sudo -urunner ./svc.sh start",
            "env ./config.sh --token T",
            "env -i HOME=/x ./svc.sh stop",
            "env -u FOO ./svc.sh stop",
            "nohup ./svc.sh start",
            "nohup sudo ./svc.sh start",
            "nohup env A=1 bash ./config.sh --url u",
            "sudo env PATH=/bin ./svc.sh uninstall",
        ):
            with self.subTest(command=command):
                self.assertIn(OWNER_REFUSAL, refused(command) or "")
        for command in (
            "sudo -iu runner ./svc.sh status",
            "env FOO=1 ./build.sh",
            "nohup ./run.sh",
            "sudo -iu runner ls",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))

    def test_a_heredoc_fed_to_a_shell_is_read_as_the_script_it_is(self) -> None:
        for command in (
            "bash <<'EOF'\n./config.sh --url u --token T\nEOF",
            "sudo bash <<EOF\ncd /srv/runner && ./svc.sh install\nEOF",
            "sh -s <<'EOF'\ngh secret set TOKEN\nEOF",
            "bash <<'EOF' && echo done\n./svc.sh start\nEOF",
        ):
            with self.subTest(command=command):
                self.assertIn(OWNER_REFUSAL, refused(command) or "")
        for command in (
            "bash <<'EOF'\necho hello\nEOF",
            "cat <<'EOF'\n./config.sh --token T\nEOF",
            "git commit -m \"$(cat <<'EOF'\nfix: gh secret set\nEOF\n)\"",
            "bash scripts/build.sh <<'EOF'\nyes\nEOF",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))

    def test_a_gesture_the_project_declares_is_refused_with_its_reason(self) -> None:
        lines = [OWNER_KEY_VALUE, "uv run python -m scripts.release | la publication est humaine"]
        for command in (
            "gh label delete bug",
            "gh -R o/r label delete bug",
            "GH_TOKEN=x gh --repo=o/r label delete bug",
            "cd /work && gh label delete bug --yes",
            "uv run python -m scripts.release --tag v1",
        ):
            with self.subTest(command=command):
                verdict = owner_refused(command, lines)
                self.assertIn(OWNER_REFUSAL, verdict or "")
                self.assertRegex(verdict or "", "les étiquettes sont au propriétaire|publication")

    def test_a_declared_prefix_is_compared_word_by_word(self) -> None:
        for command in ("gh label deleted bug", "gh label list", "gh issue delete 3", "ghx label delete"):
            with self.subTest(command=command):
                self.assertIsNone(owner_refused(command, [OWNER_KEY_VALUE]))

    def test_a_declared_gesture_without_a_reason_still_refuses_and_says_so(self) -> None:
        for value in ("gh label delete", "gh label delete | ", "gh label delete |"):
            with self.subTest(value=value):
                verdict = owner_refused("gh label delete bug", [value])
                self.assertIn(OWNER_REFUSAL, verdict or "")
                self.assertIn("sans raison", verdict or "")

    def test_a_declared_gesture_with_no_command_refuses_nothing(self) -> None:
        self.assertIsNone(owner_refused("gh label delete bug", [" | une raison", ""]))

    def test_the_hook_reads_the_gestures_from_the_project_configuration(self) -> None:
        event = json.dumps({"tool_input": {"command": "gh label delete bug"}, "cwd": "/nowhere"})

        def run(project: str | None) -> tuple[int, str]:
            env = {"CLAUDE_PROJECT_DIR": project} if project else {}
            err = io.StringIO()
            with (
                mock.patch.dict("os.environ", env, clear=True),
                mock.patch("sys.stdin", io.StringIO(event)),
                mock.patch("sys.stderr", err),
                mock.patch("guard_git.current_branch", lambda _cwd: "feat/x"),
                mock.patch("guard_git.checks_green_via_gh", lambda _cwd: always_green),
            ):
                return main(), err.getvalue()

        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "docs" / "agents"
            config.mkdir(parents=True)
            (config / "usine.md").write_text(f"- `{OWNER_KEY}` : `{OWNER_KEY_VALUE}`\n", "utf-8")
            code, message = run(root)
            self.assertEqual(code, 2)
            self.assertIn("les étiquettes sont au propriétaire", message)
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(run(root)[0], 0)

    def test_a_mutation_written_in_a_heredoc_is_read(self) -> None:
        for body in (
            "mutation { deleteRepository(input: {repositoryId: \"x\"}) { clientMutationId } }",
            "mutation { updateBranchProtectionRule(input: {}) { clientMutationId } }",
            "mutation { createRepositoryRuleset(input: {}) { clientMutationId } }",
            "mutation { addRepositoryCollaborator(input: {}) { clientMutationId } }",
        ):
            for command in (
                f"gh api graphql -f query=\"$(cat <<'EOF'\n{body}\nEOF\n)\"",
                f"gh api graphql -f query=\"$(cat <<EOF\n{body}\nEOF\n)\" -F owner=o",
                f"gh api graphql --input - <<'EOF'\n{json.dumps({'query': body})}\nEOF",
                f"cd /w && gh api graphql --input - <<-'EOF'\n\t{body}\n\tEOF",
            ):
                with self.subTest(command=command):
                    verdict = refused(command) or ""
                    self.assertIn(OWNER_REFUSAL, verdict)
                    self.assertIn("gh api graphql", verdict)

    def test_a_mutation_written_in_a_readable_file_is_read(self) -> None:
        texts = {
            "/w/m.graphql": "mutation { deleteRepository(input: {}) { clientMutationId } }",
            "/w/m.json": '{"query": "mutation { updateRepository(input: {}) { id } }"}',
            "/w/q.graphql": "query { viewer { login } }",
            "/w/sub.graphql": "mutation { addSubIssue(input: {}) { issue { id } } }",
        }
        for command in (
            "gh api graphql -F query=@m.graphql",
            "gh api graphql -f query=@m.graphql",
            "gh api graphql --field query=@/w/m.graphql",
            "gh api graphql --input m.json",
            "gh api graphql --input=m.json",
            "cd /w/sub && gh api graphql --input ../m.json",
        ):
            with self.subTest(command=command):
                verdict = refusal(command, "feat/x", always_green, "/w", read_text=files(texts))
                self.assertIn(OWNER_REFUSAL, verdict or "")
        for command in (
            "gh api graphql -F query=@q.graphql",
            "gh api graphql --input q.graphql",
            "gh api graphql -F query=@sub.graphql",
        ):
            with self.subTest(command=command):
                self.assertIsNone(
                    refusal(command, "feat/x", always_green, "/w", read_text=files(texts))
                )

    def test_a_graphql_form_that_cannot_be_read_is_refused_as_a_precaution(self) -> None:
        for command in (
            "gh api graphql --input missing.json",
            "gh api graphql -F query=@missing.graphql",
            "cat q.json | gh api graphql --input -",
            "echo \"$QUERY\" | gh api graphql -F query=@-",
            "gh api graphql -f query=\"$(cat q.graphql)\"",
            "gh api graphql -f query=\"`cat q.graphql`\"",
            "gh api graphql -f query=\"$QUERY\"",
            "gh api graphql -f query=${QUERY}",
            "gh api graphql --input - <<<\"$QUERY\"",
            "cd \"$DIR\" && gh api graphql --input m.json",
        ):
            with self.subTest(command=command):
                verdict = refused(command) or ""
                self.assertIn("gh api graphql", verdict)
                self.assertIn("par précaution", verdict)

    def test_the_standard_input_under_another_name_is_the_heredoc(self) -> None:
        mutation = '{"query": "mutation { updateRepository(input: {}) { clientMutationId } }"}'
        sub_issue = '{"query": "mutation { addSubIssue(input: {}) { issue { id } } }"}'
        for name in ("/dev/stdin", "/dev/fd/0", "/proc/self/fd/0"):
            for form in (f"--input {name}", f"-F query=@{name}", f"--input={name}"):
                with self.subTest(form=form):
                    verdict = refused(f"gh api graphql {form} <<'EOF'\n{mutation}\nEOF") or ""
                    self.assertIn("mutation", verdict)
                    self.assertNotIn("par précaution", verdict)
                    self.assertIsNone(refused(f"gh api graphql {form} <<'EOF'\n{sub_issue}\nEOF"))

    def test_the_standard_input_under_another_name_without_a_heredoc_is_refused(self) -> None:
        verdict = refused("cat q.json | gh api graphql --input /dev/stdin") or ""
        self.assertIn("par précaution", verdict)

    def test_a_graphql_read_in_a_heredoc_or_with_variables_passes(self) -> None:
        for command in (
            "gh api graphql -f query=\"$(cat <<'EOF'\nquery { viewer { login } }\nEOF\n)\"",
            "gh api graphql --input - <<'EOF'\n{\"query\": \"query { viewer { login } }\"}\nEOF",
            "gh api graphql -f query=\"$(cat <<'EOF'\nmutation { addSubIssue(input: {}) { issue { id } } }\n"
            "EOF\n)\"",
            "gh api graphql -f query='query($o: String!) { repository(owner: $o, name: \"r\") { id } }'"
            " -F o=x",
            "gh api graphql -f query='query { viewer { login } }' -F cursor=\"$CURSOR\"",
            "gh api repos/o/r/issues --jq '.[].title' <<'EOF'\nupdateRepository\nEOF",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))

    def test_the_sub_issue_mutations_the_plugin_uses_and_graphql_reads_pass(self) -> None:
        for command in (
            "gh api graphql -f query='mutation { addSubIssue(input: {issueId: \"a\", "
            "subIssueId: \"b\"}) { issue { id } } }'",
            "gh api graphql -f query='mutation { removeSubIssue(input: {}) { issue { id } } }'",
            "gh api graphql -f query='mutation { reprioritizeSubIssue(input: {}) { id } }'",
            "gh api graphql -f query='query { repository(owner: \"o\", name: \"r\") { id } }'",
            "gh api graphql -f query='query { repository(owner: \"o\", name: \"r\") "
            "{ branchProtectionRules(first: 5) { nodes { pattern } } } }'",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))


MUTATION_JSON = '{"query": "mutation { updateRepository(input: {}) { clientMutationId } }"}'
SUB_ISSUE_JSON = '{"query": "mutation { addSubIssue(input: {}) { issue { id } } }"}'
STDIN_SPELLINGS = (
    "/dev/stdin",
    "/dev/fd/0",
    "/proc/self/fd/0",
    "/dev/./stdin",
    "//dev/stdin",
    "///dev/stdin",
    "/dev//stdin",
    "/dev/fd/../fd/0",
    "/dev/../dev/stdin",
    "/proc/self/../self/fd/0",
    "/tmp/../dev/stdin",
    "/proc/thread-self/fd/0",
)


def _refuse_unsafe_open(path: object) -> None:
    """Raise rather than open what could read without end or block: a device, /proc, a pipe.

    The check is a `stat`, which never blocks, and it runs before any real open: a test written
    against code that still opens such a path fails here, red, instead of filling the memory.
    """
    if isinstance(path, int):
        raise AssertionError(f"opened the descriptor {path}")
    text = os.fspath(path)  # type: ignore[arg-type]
    if isinstance(text, bytes):
        text = os.fsdecode(text)
    for candidate in (text, os.path.realpath(text)):
        normal = os.path.normpath(candidate).replace("\\", "/")
        if normal.lstrip("/").startswith(("dev/", "proc/")) or normal in ("/dev", "/proc"):
            raise AssertionError(f"opened {text} ({normal})")
    try:
        mode = os.stat(text).st_mode
    except (OSError, ValueError):
        return  # it cannot be opened either
    if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
        raise AssertionError(f"opened {text}, which is not an ordinary file")


@contextlib.contextmanager
def no_open_under_devices() -> Iterator[None]:
    """Fail the test if the guard opens a device, /proc or any file that is not an ordinary one.

    `pathlib` opens through `io.open`, which does not call `os.open` or `builtins.open` by name:
    all three are patched, so that no road to a real open is left.
    """
    real_io_open, real_os_open = io.open, os.open

    def checked_io_open(path: object, *args: object, **kwargs: object) -> object:
        _refuse_unsafe_open(path)
        return real_io_open(path, *args, **kwargs)  # type: ignore[arg-type]

    def checked_os_open(path: object, *args: object, **kwargs: object) -> int:
        _refuse_unsafe_open(path)
        return real_os_open(path, *args, **kwargs)  # type: ignore[arg-type]

    with (
        mock.patch("io.open", checked_io_open),
        mock.patch("builtins.open", checked_io_open),
        mock.patch("os.open", checked_os_open),
    ):
        yield


class StandardInputIsNeverOpened(unittest.TestCase):
    """Un chemin qui vaut l'entrée standard n'est jamais ouvert : le garde l'a déjà lue."""

    def test_every_spelling_of_the_standard_input_reads_the_heredoc(self) -> None:
        for name in STDIN_SPELLINGS:
            for form in (
                f"--input {name}",
                f"--input={name}",
                f"-F query=@{name}",
                f"-f query=@{name}",
                f"--field=query=@{name}",
            ):
                with self.subTest(name=name, form=form), no_open_under_devices():
                    heredoc = f"gh api graphql {form} <<'EOF'\n%s\nEOF"
                    verdict = refused(heredoc % MUTATION_JSON) or ""
                    self.assertIn("mutation", verdict)
                    self.assertNotIn("par précaution", verdict)
                    self.assertIsNone(refused(heredoc % SUB_ISSUE_JSON))
                    self.assertIn("par précaution", refused(f"cat q | gh api graphql {form}") or "")

    def test_a_relative_name_is_resolved_where_the_command_stands(self) -> None:
        for command, cwd in (
            ("gh api graphql --input stdin", "/dev"),
            ("gh api graphql --input 0", "/dev/fd"),
            ("gh api graphql --input 0", "/proc/self/fd"),
            ("gh api graphql --input fd/0", "/proc/self"),
            ("gh api graphql --input dev/stdin", "/"),
            ("gh api graphql --input ../dev/stdin", "/tmp"),
            ("cd /dev && gh api graphql --input stdin", "/work"),
            ("cd /dev/fd && gh api graphql -F query=@0", "/work"),
            ("cd /dev && cd . && gh api graphql --input ./stdin", "/work"),
            ("cd /w && cd /dev && gh api graphql --input ./stdin", "/work"),
            ("cd /proc && cd self/fd && gh api graphql --input 0", "/work"),
        ):
            with self.subTest(command=command, cwd=cwd), no_open_under_devices():
                full = f"{command} <<'EOF'\n{MUTATION_JSON}\nEOF"
                verdict = refusal(full, "feat/x", always_green, cwd) or ""
                self.assertIn("mutation", verdict)
                self.assertNotIn("par précaution", verdict)
                harmless = f"{command} <<'EOF'\n{SUB_ISSUE_JSON}\nEOF"
                self.assertIsNone(refusal(harmless, "feat/x", always_green, cwd))

    @unittest.skipIf(sys.platform == "win32", "a symbolic link to /dev/stdin is a POSIX thing")
    def test_a_link_to_the_standard_input_is_the_standard_input(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            link = Path(folder) / "in"
            link.symlink_to("/dev/stdin")
            with no_open_under_devices():
                command = f"gh api graphql --input {link} <<'EOF'\n%s\nEOF"
                self.assertIn("mutation", refused(command % MUTATION_JSON) or "")
                self.assertIsNone(refused(command % SUB_ISSUE_JSON))

    def test_a_heredoc_of_another_command_is_not_the_standard_input_of_the_call(self) -> None:
        texts = {"/w/q.json": SUB_ISSUE_JSON, "/w/m.json": MUTATION_JSON}
        other = "&& cat <<'EOF'\nupdateRepository\nEOF"
        for command, expected_mutation in (
            (f"gh api graphql --input - < q.json {other}", False),
            (f"gh api graphql --input - < m.json {other}", True),
            (f"gh api graphql --input - < /w/m.json {other}", True),
            (f"gh api graphql -F query=@- < m.json {other}", True),
        ):
            with self.subTest(command=command):
                verdict = refusal(command, "feat/x", always_green, "/w", read_text=files(texts))
                if expected_mutation:
                    self.assertIn("mutation", verdict or "")
                    self.assertNotIn("par précaution", verdict or "")
                else:
                    self.assertIsNone(verdict)
        for command in (
            f"gh api graphql --input - {other}",
            "gh api graphql --input - < missing.json",
            'gh api graphql --input - <<< "$QUERY"',
            f"echo '{SUB_ISSUE_JSON}' | gh api graphql --input - {other}",
        ):
            with self.subTest(command=command):
                verdict = refusal(command, "feat/x", always_green, "/w", read_text=files(texts))
                self.assertIn("par précaution", verdict or "")

    def test_a_file_that_is_not_an_ordinary_small_file_is_not_read(self) -> None:
        with tempfile.TemporaryDirectory() as folder, no_open_under_devices():
            root = Path(folder)
            big = root / "big.json"
            big.write_text(" " * (2 * 1024 * 1024) + MUTATION_JSON, encoding="utf-8")
            small = root / "small.json"
            small.write_text(MUTATION_JSON, encoding="utf-8")
            forms = {
                "a file over the cap": (big.as_posix(), "par précaution"),
                "a directory": (root.as_posix(), "par précaution"),
                "an ordinary small file": (small.as_posix(), "mutation"),
            }
            if sys.platform != "win32":
                forms["/dev/zero"] = ("/dev/zero", "par précaution")
                forms["/dev/null"] = ("/dev/null", "par précaution")
                forms["/dev/urandom"] = ("/dev/urandom", "par précaution")
            if hasattr(os, "mkfifo"):
                fifo = root / "pipe"
                os.mkfifo(fifo)
                forms["a FIFO nobody writes to"] = (fifo.as_posix(), "par précaution")
            for name, (path, expected) in forms.items():
                for form in (f"--input {path}", f"-F query=@{path}"):
                    with self.subTest(case=name, form=form):
                        started = time.monotonic()
                        verdict = refused(f"gh api graphql {form}") or ""
                        self.assertLess(time.monotonic() - started, 5)
                        self.assertIn(expected, verdict)

    def test_a_body_file_of_a_merge_under_a_device_path_is_not_opened(self) -> None:
        for name in ("/dev/stdin", "/dev/./stdin", "//dev/stdin", "/dev/zero", "/proc/self/fd/0"):
            for option in (f"--body-file {name}", f"-F {name}", f"--body-file={name}"):
                with self.subTest(name=name, option=option), no_open_under_devices():
                    self.assertIsNone(refused(f"gh pr merge 5 {option}", green=True))


COLLABORATOR = "repos/o/r/collaborators/bob"


class GhApiArgumentsLikeGh(unittest.TestCase):
    """Un seul découpeur des arguments de `gh api`, comme pflag : la méthode, le point d'accès et
    les champs ne se lisent pas autrement que gh les lit."""

    def test_the_value_of_an_option_is_never_taken_for_the_method(self) -> None:
        # gh (pflag) prend le mot suivant pour la valeur de l'option, même s'il commence par `-`.
        for tail in (
            "--jq -XGET",
            "-q -XGET",
            "-q --method=GET",
            "-t --method=GET",
            "-t -X=GET",
            "--template -XGET",
            "-p -XGET",
            "--preview -XGET",
            "--cache -XGET",
            "--hostname -XGET",
            "-H -XGET",
            "--header -X=GET",
            "--jq=. -q -XGET",
        ):
            with self.subTest(tail=tail):
                verdict = refused(f"gh api -X PUT {COLLABORATOR} {tail}") or ""
                self.assertIn(OWNER_REFUSAL, verdict)
                self.assertIn("PUT", verdict)
        for command in (
            f"gh api {COLLABORATOR} --jq -XPUT",
            f"gh api {COLLABORATOR} -q -X",
            f"gh api {COLLABORATOR} --template --method=DELETE",
            f"gh api {COLLABORATOR} --jq -f",
            f"gh api {COLLABORATOR} -H -F",
            f"gh api -X GET --jq -XPUT {COLLABORATOR}",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))

    def test_every_spelling_of_the_method_is_read_and_the_last_one_counts(self) -> None:
        for command, method in (
            (f"gh api -XPUT {COLLABORATOR}", "PUT"),
            (f"gh api -X=PUT {COLLABORATOR}", "PUT"),
            (f"gh api --method=PUT {COLLABORATOR}", "PUT"),
            (f"gh api --method PUT {COLLABORATOR}", "PUT"),
            (f"gh api -iXPUT {COLLABORATOR}", "PUT"),
            (f"gh api -X GET -XPUT {COLLABORATOR}", "PUT"),
            (f"gh api -XGET -X=PUT {COLLABORATOR}", "PUT"),
            (f"gh api -X GET {COLLABORATOR} -f a=b -X DELETE", "DELETE"),
            (f"gh api -X GET {COLLABORATOR} -fa=b -iXDELETE", "DELETE"),
            (f"gh api --method=GET --method=PUT {COLLABORATOR}", "PUT"),
            (f"gh api -X PUT -- {COLLABORATOR}", "PUT"),
            (f"gh api -X PUT --jq . {COLLABORATOR}", "PUT"),
            (f"gh api -pXGET {COLLABORATOR} -f permission=admin", "POST"),
        ):
            with self.subTest(command=command):
                verdict = refused(command) or ""
                self.assertIn(OWNER_REFUSAL, verdict)
                self.assertIn(f"gh api {method} ", verdict)
        for command in (
            f"gh api -XGET {COLLABORATOR}",
            f"gh api -X=get {COLLABORATOR} -f per_page=1",
            f"gh api --method=HEAD {COLLABORATOR}",
            f"gh api -iXGET {COLLABORATOR} -F a=b",
            f"gh api -X PUT -X GET {COLLABORATOR} -f a=b",
            f"gh api -X PUT {COLLABORATOR} -XGET",
            f"gh api -pXGET {COLLABORATOR}",
            f"gh api -X GET -- {COLLABORATOR}",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))

    def test_a_redirection_does_not_hide_the_endpoint_or_the_method(self) -> None:
        for command in (
            f"gh api 2>/dev/null -X PUT {COLLABORATOR}",
            f"gh api > out.json -X PUT {COLLABORATOR}",
            f"gh api -X PUT {COLLABORATOR} > out.json 2>&1",
            f"gh api >> log.txt {COLLABORATOR} -f permission=admin",
        ):
            with self.subTest(command=command):
                self.assertIn(OWNER_REFUSAL, refused(command) or "")
        for command in (
            f"gh api {COLLABORATOR} > out.json",
            f"gh api -X GET {COLLABORATOR} -f per_page=1 2>&1",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))


if __name__ == "__main__":
    unittest.main()
