"""#29, point par point de « Ce qui est attendu » : le saut de ligne sépare deux commandes."""

import io
import json
import unittest
from unittest import mock

import support  # noqa: F401
from guard_coder import _runs_git
from guard_git import _commands, refusal
from guard_readonly import reader_refusal


def refused(command: str) -> str | None:
    return refusal(command, "feat/x", lambda _pr: False)


class NewlineSeparatesCommands(unittest.TestCase):
    def test_29_p1_the_second_line_is_judged(self) -> None:
        for command in (
            "echo hi\ngit push --force origin feat/x",
            "echo hi\r\ngit push --force origin feat/x",
            "echo hi\n\n  git push --force origin feat/x",
            "echo 'a\nb'\ngit push --force origin feat/x",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(refused(command))

    def test_29_p1_a_commit_on_main_on_a_second_line_is_refused(self) -> None:
        self.assertIsNotNone(refusal("echo hi\ngit commit -m x", "main", lambda _pr: False))

    def test_29_p1_the_other_guards_split_on_a_newline_too(self) -> None:
        self.assertEqual(_commands("echo hi\ngit status"), [["echo", "hi"], ["git", "status"]])
        self.assertIsNotNone(reader_refusal("cat a\nrm -rf /"))

    def test_29_p1_the_coder_guard_sees_git_on_a_second_line(self) -> None:
        self.assertTrue(_runs_git("echo hi\ngit status"))

    def test_29_p5_an_ordinary_multiline_command_passes(self) -> None:
        for command in (
            "echo hi\ngit status\nls -la",
            "echo 'git push --force\nis text'",
            'echo "line one\nline two"',
            "git commit -m 'one\ntwo'",
        ):
            with self.subTest(command=command):
                self.assertIsNone(refused(command))


class ContinuationDoesNotSeparate(unittest.TestCase):
    def test_29_p2_a_backslash_at_the_end_of_a_line_joins_the_lines(self) -> None:
        self.assertEqual(_commands("echo hi \\\n  there"), [["echo", "hi", "there"]])
        self.assertIsNone(refused("git log \\\n  --oneline"))

    def test_29_p2_a_continued_command_is_still_judged(self) -> None:
        self.assertIsNotNone(refused("git push \\\n  --force origin feat/x"))

    def test_29_p2_a_backslash_in_single_quotes_stays_literal(self) -> None:
        self.assertEqual(_commands("echo 'a\\\nb'"), [["echo", "a\\\nb"]])


class HeredocBodies(unittest.TestCase):
    def test_29_p3_a_body_with_a_forbidden_command_passes_when_no_shell_reads_it(self) -> None:
        self.assertIsNone(refused("cat > notes.md <<'EOF'\ngit push --force\nEOF"))
        self.assertIsNone(refused("cat <<EOF\necho hi\ngit push --force\nEOF\nls"))

    def test_29_p3_a_command_after_the_terminator_is_judged(self) -> None:
        self.assertIsNotNone(refused("cat <<EOF\nnotes\nEOF\ngit push --force origin feat/x"))

    def test_29_p4_a_here_string_is_not_a_heredoc(self) -> None:
        # With `<<<` taken for a heredoc, `EOF` would be a delimiter that swallows the next line.
        self.assertIsNotNone(refused("cat <<<EOF\ngit push --force origin feat/x"))
        self.assertIsNotNone(refused("cat <<< EOF\ngit push --force origin feat/x"))
        self.assertIsNone(refused("cat <<< hello\nls"))


class Main(unittest.TestCase):
    def test_29_the_hook_refuses_a_second_line_end_to_end(self) -> None:
        event = {"tool_name": "Bash", "tool_input": {"command": "echo hi\ngit push --force origin feat/x"}}
        with mock.patch("sys.stdin", io.StringIO(json.dumps(event))), mock.patch("sys.stderr", io.StringIO()):
            import guard_git

            with mock.patch.object(guard_git, "current_branch", return_value="feat/x"):
                self.assertEqual(guard_git.main(), 2)


if __name__ == "__main__":
    unittest.main()
