"""gh_bodies: the bodies a shell command publishes through gh, wherever the shell runs gh."""

import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401  puts the plugin on the import path
from gh_bodies import Unreadable, commands, heredocs, may_publish, mcp_publications, publications


def bodies(command: str, here: str | None = None) -> list[tuple[str, str]]:
    docs = heredocs(command)
    found = []
    for words in commands(command, docs):
        if isinstance(words, list):
            found += [(item.kind, item.body) for item in publications(words, docs, here)]
    return found


class GraphQLVariables(unittest.TestCase):
    def test_a_body_given_by_a_graphql_variable_is_read(self) -> None:
        command = (
            "gh api graphql -f query='mutation($b: String!){addComment(input:{subjectId:\"I_1\",body:$b}){clientMutationId}}'"
            " -f b='Merged in abc123, see run 42.'"
        )
        self.assertEqual(bodies(command), [("comment", "Merged in abc123, see run 42.")])

    def test_a_query_with_variables_and_no_mutation_publishes_nothing(self) -> None:
        command = "gh api graphql -F owner=o -f query='query($owner: String!){repository(owner:$owner,name:\"r\"){id}}'"
        self.assertEqual(bodies(command), [])

    def test_a_query_the_shell_fills_in_is_refused(self) -> None:
        for query in ('"$(cat q.graphql)"', '"$Q"', "\"`cat q`\""):
            with self.subTest(query=query), self.assertRaises(Unreadable):
                bodies(f"gh api graphql -f query={query}")

    def test_a_body_variable_the_shell_fills_in_is_refused(self) -> None:
        command = "gh api graphql -f query='mutation($b: String!){addComment(input:{subjectId:\"I\",body:$b}){x}}' -f b=\"$TEXT\""
        with self.assertRaises(Unreadable):
            bodies(command)

    def test_an_unread_field_beside_a_literal_body_does_not_refuse(self) -> None:
        self.assertEqual(bodies('gh api repos/o/r/issues/3/comments -F n="$N" -f body=done'), [("comment", "done")])


class Heredocs(unittest.TestCase):
    def test_a_substitution_without_a_heredoc_is_unread_even_when_another_heredoc_exists(self) -> None:
        command = "cat > ok.md <<'EOF'\nfine\nEOF\ngh issue comment 1 --body \"$(cat bad.md)\""
        with self.assertRaises(Unreadable):
            bodies(command)

    def test_a_cat_heredoc_is_read_from_the_heredoc_it_names(self) -> None:
        command = "cat > ok.md <<'EOF'\nother\nEOF\ngh issue comment 1 --body \"$(cat <<'X'\nhello\nX\n)\""
        self.assertEqual(bodies(command), [("comment", "hello")])

    def test_an_expanded_heredoc_is_unread(self) -> None:
        with self.assertRaises(Unreadable):
            bodies('gh issue comment 1 --body "$(cat <<X\nhello $NAME\nX\n)"')

    def test_standard_input_is_its_own_heredoc_or_file_never_another_commands(self) -> None:
        self.assertEqual(bodies("gh issue comment 1 --body-file - <<'X'\nhi\nX"), [("comment", "hi")])
        with self.assertRaises(Unreadable):
            bodies("cat > ok.md <<'EOF'\nfine\nEOF\ncat bad.md | gh issue comment 1 --body-file -")
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "b.md").write_text("from file", encoding="utf-8")
            self.assertEqual(bodies("gh issue comment 1 --body-file - < b.md", folder), [("comment", "from file")])


class FilesTheCommandWrites(unittest.TestCase):
    def test_a_body_file_the_same_command_writes_is_unread(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "b.md").write_text("old and fine", encoding="utf-8")
            for command in (
                "cat > b.md <<'EOF'\nnew text\nEOF\ngh issue comment 1 --body-file b.md",
                "echo new >> b.md && gh issue comment 1 -F b.md",
                "printf x >./b.md; gh issue comment 1 --body-file b.md",
                "echo new | tee b.md && gh issue comment 1 --body-file b.md",
                f"echo new > {Path(folder, 'b.md').as_posix()} && gh issue comment 1 --body-file b.md",
            ):
                with self.subTest(command=command), self.assertRaises(Unreadable):
                    bodies(command, folder)
            self.assertEqual(bodies("echo x > other.md && gh issue comment 1 --body-file b.md", folder), [("comment", "old and fine")])


class Channels(unittest.TestCase):
    def test_gh_behind_a_wrapper_or_a_path_is_read(self) -> None:
        for prefix in ("env", "env GH_TOKEN=x", "command", "/usr/bin/gh", "sudo -u me gh", "xargs gh", "nohup gh"):
            command = f"{prefix} {'' if prefix.endswith('gh') else 'gh '}issue comment 1 --body hi"
            with self.subTest(command=command):
                self.assertEqual(bodies(command), [("comment", "hi")])

    def test_gh_in_a_nested_shell_or_eval_is_read(self) -> None:
        for command in (
            "bash -c 'gh issue comment 1 --body hi'",
            "sh -c 'gh issue comment 1 --body hi'",
            "eval gh issue comment 1 --body hi",
            "echo \"$(gh issue comment 1 --body hi)\"",
            "bash <<'S'\ngh issue comment 1 --body hi\nS",
        ):
            with self.subTest(command=command):
                self.assertEqual(bodies(command), [("comment", "hi")])

    def test_a_substitution_runs_where_the_shell_runs_it_not_in_single_quotes(self) -> None:
        # unquoted, shlex also hands the words over as a subshell: the body is judged twice
        self.assertEqual(set(bodies("echo $(gh issue comment 1 --body hi)")), {("comment", "hi")})
        self.assertEqual(bodies("cat > f <<EOF\n$(gh issue comment 1 --body hi)\nEOF"), [("comment", "hi")])
        quoted = "gh issue comment 2 --body 'run `gh pr create --body-file missing.md`'"
        self.assertEqual(bodies(quoted), [("comment", "run `gh pr create --body-file missing.md`")])

    def test_a_command_may_run_gh_however_the_name_is_quoted(self) -> None:
        for command in ("g''h issue comment 1 --body hi", 'g""h issue comment 1 --body hi', "g\\h issue comment 1 --body hi"):
            with self.subTest(command=command):
                self.assertTrue(may_publish(command))
                self.assertEqual(bodies(command), [("comment", "hi")])
        self.assertTrue(may_publish("curl https://api.git''hub.com/x"))
        self.assertFalse(may_publish("ls -la"))

    def test_gh_or_a_script_given_by_a_variable_is_unread(self) -> None:
        for command in ('bash -c "$S"', "eval \"$CMD\"", "$GH issue comment 1 --body hi", '"$GH" api repos/o/r/issues -f body=x'):
            with self.subTest(command=command), self.assertRaises(Unreadable):
                bodies(command)


class McpTools(unittest.TestCase):
    def kinds(self, tool: str, **fields: object) -> list[tuple[str, str]]:
        return [(item.kind, item.body) for item in mcp_publications(tool, fields)]

    def test_each_github_tool_is_placed_by_its_name(self) -> None:
        self.assertEqual(self.kinds("mcp__github__add_issue_comment", body="a"), [("comment", "a")])
        self.assertEqual(self.kinds("mcp__github__create_pull_request_review", body="b"), [("comment", "b")])
        self.assertEqual(self.kinds("mcp__github__merge_pull_request", commit_message="c"), [("comment", "c")])
        self.assertEqual(self.kinds("mcp__github__create_pull_request", body="d"), [("pr", "d")])
        self.assertEqual(self.kinds("mcp__plugin_x_github__issue_write", body="e"), [("ticket", "e")])

    def test_a_tool_without_a_body_publishes_nothing(self) -> None:
        self.assertEqual(self.kinds("mcp__github__get_issue", issue_number=3), [])

    def test_an_unknown_tool_with_a_body_or_a_body_that_is_no_text_is_unread(self) -> None:
        with self.assertRaises(Unreadable):
            self.kinds("mcp__github__create_gist", body="x")
        with self.assertRaises(Unreadable):
            self.kinds("mcp__github__add_issue_comment", body=["x"])


if __name__ == "__main__":
    unittest.main()
