"""`gh api` passe par une liste d'acceptation (ticket #73, partie 1 ; suivi #55).

Un appel passe quand sa méthode et son chemin correspondent à la liste du plugin ou à une ligne de
la clé `gh-api-allow` ; tout autre appel est refusé, l'appel et la raison nommés. Cas de validation :
A1.1, A1.2, A2.1, A2.2, A3.1 du ticket.
"""

import io
import json
import os
import re
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest import mock

import support  # noqa: F401  met les hooks sur le chemin d'import
from guard_git import RULES, guarded_main, refusal
from support import PLUGIN, REPO_ROOT
from usine import parse


def verdict(command: str, allow: Sequence[str] = (), **keys: Any) -> str | None:
    return refusal(command, "feat/x", lambda *_target: True, gh_api_allow=allow, **keys)


class AcceptedAndRefused(unittest.TestCase):
    def test_a1_1_a_plugin_read_of_a_pr_is_accepted(self) -> None:
        self.assertIsNone(verdict("gh api repos/o/r/pulls/1"))

    def test_a1_2_a_delete_outside_the_list_is_refused_and_the_call_is_named(self) -> None:
        reason = verdict("gh api -X DELETE repos/o/r/git/refs/tags/x")
        assert reason is not None
        self.assertIn("DELETE repos/o/r/git/refs/tags/x", reason)
        self.assertIn("allow-list", reason)

    def test_a1_a_read_outside_the_list_is_refused_too(self) -> None:
        for command in ("gh api user", "gh api repos/o/r", "gh api repos/o/r/actions/secrets"):
            with self.subTest(command=command):
                reason = verdict(command)
                assert reason is not None
                self.assertIn("GET", reason)

    def test_a1_every_call_the_ticket_names_is_accepted(self) -> None:
        for command in (
            "gh api repos/o/r/pulls/1/files",
            "gh api repos/o/r/pulls/1/comments",
            "gh api repos/o/r/commits/abc/check-runs",
            "gh api repos/o/r/issues/1/comments",
            "gh api repos/o/r/issues/1/comments -f body=x",
            "gh api repos/o/r/issues/1/sub_issues -F sub_issue_id=5",
            "gh api -X POST repos/o/r/issues/1/labels -f 'labels[]=bug'",
            "gh api -X DELETE repos/o/r/issues/1/labels/bug",
            "gh api repos/{owner}/{repo}/issues/1/sub_issues --jq '.[] | [.number, .state] | @tsv'",
            "gh api /repos/o/r/pulls/1",
            "gh api 'repos/o/r/actions/runs?per_page=1'",
        ):
            with self.subTest(command=command):
                self.assertIsNone(verdict(command))

    def test_a1_a_wrapper_or_a_path_before_gh_changes_nothing(self) -> None:
        self.assertIsNotNone(verdict("GH_REPO=o/r gh api -X DELETE repos/o/r/git/refs/tags/x"))
        self.assertIsNotNone(verdict("gh -R o/r api -X DELETE repos/o/r/git/refs/tags/x"))
        self.assertIsNotNone(verdict("sudo gh api -X DELETE repos/o/r/git/refs/tags/x"))
        self.assertIsNotNone(verdict("bash -c 'gh api -X DELETE repos/o/r/git/refs/tags/x'"))
        self.assertIsNotNone(verdict("cd /tmp && gh api -X DELETE repos/o/r/git/refs/tags/x"))

    def test_a1_a_pattern_stands_for_one_segment_per_star(self) -> None:
        for command in (
            "gh api repos/o/r/pulls/1/extra",
            "gh api repos/o/r/pulls",
            "gh api repos/o/r/pulls/1/files/more",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(verdict(command))

    def test_a1_a_path_the_server_may_resolve_elsewhere_is_unreadable(self) -> None:
        for command in (
            "gh api repos/o/r/pulls/../actions/secrets",
            "gh api repos/o/r/pulls/..",
            "gh api repos//r/pulls/1",
            "gh api repos/o/r/pulls/%2e%2e",
            "gh api repos/o/r/pulls/1#x",
            "gh api https://api.github.com/repos/o/r/pulls/1",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(verdict(command))

    def test_a1_a_hash_inside_a_word_is_no_comment(self) -> None:
        # shlex would drop `#a -X DELETE`: the guard would read a GET of a path the shell sends a DELETE to.
        reason = verdict("gh api repos/o/r/actions/runs/1#a -X DELETE")
        assert reason is not None
        self.assertIn("cannot be read", reason)
        self.assertIsNotNone(verdict("gh api repos/o/r/pulls/1#a -X DELETE"))
        # a `#` that opens a word is a comment, to the shell as to the guard
        self.assertIsNone(verdict("gh api repos/o/r/pulls/1 # -X DELETE"))
        self.assertIsNone(verdict("gh api repos/o/r/pulls/1 -q '.title # x'"))

    def test_a1_a_call_is_judged_in_every_reading_of_its_words(self) -> None:
        # `-t '>'` may be a redirection: both readings are judged, one refuses.
        self.assertIsNotNone(verdict("gh api -X DELETE repos/o/r/pulls/1 -t '>' x"))

    def test_a1_a_call_run_among_others_is_judged_like_the_rest(self) -> None:
        self.assertIsNotNone(verdict("echo ok && gh api -X DELETE repos/o/r/git/refs/tags/x"))
        self.assertIsNotNone(verdict("echo ok\ngh api -X DELETE repos/o/r/git/refs/tags/x"))
        self.assertIsNone(verdict("echo ok && gh api repos/o/r/pulls/1 | cat"))


class MethodAsGhReadsIt(unittest.TestCase):
    def test_a2_1_a_field_without_method_is_a_post(self) -> None:
        # `pulls/1` is allowed as a GET only: the field turns the call into a POST.
        for command in (
            "gh api repos/o/r/pulls/1 -f body=x",
            "gh api repos/o/r/pulls/1 -F body=x",
            "gh api repos/o/r/pulls/1 --field body=x",
            "gh api repos/o/r/pulls/1 --raw-field body=x",
            "gh api repos/o/r/pulls/1 --input body.json",
        ):
            with self.subTest(command=command):
                reason = verdict(command)
                assert reason is not None
                self.assertIn("POST repos/o/r/pulls/1", reason)
        # and on a path that allows the POST, no `-X` is needed
        self.assertIsNone(verdict("gh api repos/o/r/issues/1/comments -f body=x"))

    def test_a2_2_the_last_method_wins(self) -> None:
        reason = verdict("gh api -X GET -X DELETE repos/o/r/pulls/1")
        assert reason is not None
        self.assertIn("DELETE repos/o/r/pulls/1", reason)
        self.assertIsNone(verdict("gh api -X DELETE -X GET repos/o/r/pulls/1"))
        self.assertIsNotNone(verdict("gh api --method GET --method=PUT repos/o/r/pulls/1"))

    def test_a2_every_spelling_of_the_method_is_read(self) -> None:
        for command in (
            "gh api -XDELETE repos/o/r/pulls/1",
            "gh api -X=DELETE repos/o/r/pulls/1",
            "gh api -iXDELETE repos/o/r/pulls/1",
            "gh api --method=DELETE repos/o/r/pulls/1",
            "gh api --method DELETE repos/o/r/pulls/1",
            "gh api repos/o/r/pulls/1 -X DELETE",
            "gh api -X delete repos/o/r/pulls/1",
        ):
            with self.subTest(command=command):
                reason = verdict(command)
                assert reason is not None
                self.assertIn("DELETE", reason)

    def test_a2_an_explicit_get_keeps_its_fields_as_a_query(self) -> None:
        self.assertIsNone(verdict("gh api -X GET repos/o/r/pulls/1 -f per_page=5"))
        self.assertIsNone(verdict("gh api -X HEAD repos/o/r/pulls/1"))

    def test_a2_the_value_of_an_option_is_not_a_method(self) -> None:
        self.assertIsNone(verdict("gh api repos/o/r/pulls/1 --jq -XDELETE"))
        self.assertIsNone(verdict("gh api repos/o/r/pulls/1 -q '-X DELETE'"))
        self.assertIsNone(verdict("gh api repos/o/r/pulls/1 -H 'X-Foo: -X DELETE'"))


class UnreadableCalls(unittest.TestCase):
    def test_a3_1_a_variable_endpoint_is_refused(self) -> None:
        reason = verdict('gh api "$URL"')
        assert reason is not None
        self.assertIn("cannot be read", reason)
        self.assertIn("$URL", reason)

    def test_a3_a_substitution_or_a_variable_in_the_structure_is_refused(self) -> None:
        for command in (
            "gh api $URL",
            "gh api repos/o/r/pulls/$N",
            'gh api "repos/o/r/pulls/$(echo 1)"',
            "gh api `echo repos/o/r/pulls/1`",
            "gh api $(echo repos/o/r/pulls/1)",
            'gh api -X "$M" repos/o/r/pulls/1',
            "gh api --method=$M repos/o/r/pulls/1",
            'gh api repos/o/r/pulls/1 "$EXTRA"',
            "gh api repos/o/r/pulls/{1,2}",
            "gh api repos/o/r/pulls/*",
            "gh api repos/o/r/pulls/[1]",
            "gh api",
            "gh api -X GET",
        ):
            with self.subTest(command=command):
                reason = verdict(command)
                assert reason is not None
                self.assertIn("allow-list", reason)

    def test_a3_a_variable_in_the_value_of_a_field_is_not_the_structure(self) -> None:
        self.assertIsNone(verdict('gh api repos/o/r/issues/1/comments -f body="$BODY"'))
        self.assertIsNone(verdict('gh api repos/o/r/issues/1/comments -f body="$(cat <<EOF\nhi\nEOF\n)"'))

    def test_a3_graphql_keeps_its_own_reading_of_the_query(self) -> None:
        self.assertIsNone(verdict("gh api graphql -f query='query($o: String!) { viewer { login } }' -F o=x"))
        self.assertIsNotNone(verdict('gh api graphql -f query="$Q"'))
        self.assertIsNotNone(verdict("gh api graphql -f query=\"$(cat q.graphql)\""))
        self.assertIsNotNone(verdict("gh api graphql -f query='mutation { deleteRepositoryRuleset(input: {}) { x } }'"))
        self.assertIsNotNone(verdict("gh api graphql --input q.json", read_text=lambda _path: None))

    def test_a3_a_heredoc_that_carries_the_request_is_read_or_refused(self) -> None:
        benign = "gh api graphql --input - <<EOF\n{\"query\": \"{ viewer { login } }\"}\nEOF"
        self.assertIsNone(verdict(benign))
        owner = "gh api graphql --input - <<EOF\n{\"query\": \"mutation { deleteRepositoryRuleset(input: {}) { x } }\"}\nEOF"
        assert (reason := verdict(owner)) is not None
        self.assertIn("propriétaire", reason)
        # a shell that reads the script from a heredoc runs the call: judged like the call itself
        script = "bash <<EOF\ngh api -X DELETE repos/o/r/git/refs/tags/x\nEOF"
        self.assertIsNotNone(verdict(script))

    def test_a3_an_owner_gesture_is_named_as_before_and_is_not_unlocked_by_a_project_line(self) -> None:
        for allow in ((), ("PUT | repos/*/*/collaborators/* | essai",)):
            with self.subTest(allow=allow):
                reason = verdict("gh api -X PUT repos/o/r/collaborators/bob", allow)
                assert reason is not None
                self.assertIn("geste du propriétaire", reason)


class StandardInputOfAnotherDescriptor(unittest.TestCase):
    """The defect #30 left in `main`: `3< file` was read as the standard input of the call."""

    FILES = {
        "m.json": '{"query": "mutation { deleteRepositoryRuleset(input: {}) { x } }"}',
        "anodin.json": '{"query": "{ viewer { login } }"}',
    }

    def read(self, path: str) -> str | None:
        return self.FILES.get(path)

    def judged(self, command: str) -> str | None:
        return verdict(command, read_text=self.read)

    def test_a3_a_redirection_of_another_descriptor_is_not_the_standard_input(self) -> None:
        refused = (
            "gh api graphql --input - < m.json",  # the control, refused without any `3<`
            "gh api graphql --input - < m.json 3< anodin.json",
            "gh api graphql --input - 3< anodin.json < m.json",
            "cat m.json | gh api graphql --input - 3< anodin.json",
            "cat m.json | gh api graphql -F query=@- 3< anodin.json",
            "gh api graphql --input - 3< anodin.json",
            "gh api graphql --input - 10< anodin.json",
            "gh api graphql --input - 3<<EOF\n{\"query\": \"{ viewer { login } }\"}\nEOF",
        )
        for command in refused:
            with self.subTest(command=command):
                self.assertIsNotNone(self.judged(command))

    def test_a3_the_standard_input_is_still_read_by_its_own_redirection(self) -> None:
        self.assertIsNone(self.judged("gh api graphql --input - < anodin.json"))
        self.assertIsNone(self.judged("gh api graphql --input - 0< anodin.json"))
        self.assertIsNotNone(self.judged("gh api graphql --input - 0< m.json"))
        # the last redirection of the standard input wins, as in the shell
        self.assertIsNotNone(self.judged("gh api graphql --input - < anodin.json < m.json"))
        self.assertIsNone(self.judged("gh api graphql --input - < m.json < anodin.json"))


class ProjectKey(unittest.TestCase):
    def test_a4_a_line_of_the_key_adds_a_call_the_plugin_does_not_make(self) -> None:
        command = "gh api -X DELETE repos/o/r/git/refs/heads/x"
        self.assertIsNotNone(verdict(command))
        allow = ("DELETE | repos/*/*/git/refs/heads/* | le nettoyage des branches de PR",)
        self.assertIsNone(verdict(command, allow))
        # only that method and that path
        self.assertIsNotNone(verdict("gh api -X PATCH repos/o/r/git/refs/heads/x", allow))
        self.assertIsNotNone(verdict("gh api -X DELETE repos/o/r/git/refs/tags/x", allow))
        self.assertIsNotNone(verdict("gh api -X DELETE repos/o/r/git/refs/heads/x/y", allow))

    def test_a4_the_method_of_a_line_is_compared_whatever_its_case(self) -> None:
        allow = ("delete | repos/*/*/git/refs/heads/* | essai",)
        self.assertIsNone(verdict("gh api -X DELETE repos/o/r/git/refs/heads/x", allow))

    def test_a4_a_double_star_line_matches_across_segments(self) -> None:
        allow = ("GET | repos/*/*/contents/**/*.md | lire la documentation",)
        self.assertIsNone(verdict("gh api repos/o/r/contents/docs/a/b.md", allow))
        self.assertIsNone(verdict("gh api repos/o/r/contents/b.md", allow))

    def test_a4_a_line_that_is_not_three_parts_allows_nothing_and_is_named(self) -> None:
        for line in (
            "DELETE | repos/*/*/git/refs/heads/*",
            "DELETE | repos/*/*/git/refs/heads/* | ",
            "repos/*/*/git/refs/heads/* | sans méthode | essai",
            "* | repos/*/*/git/refs/heads/* | toute méthode",
            "",
        ):
            with self.subTest(line=line):
                reason = verdict("gh api -X DELETE repos/o/r/git/refs/heads/x", (line,))
                assert reason is not None
                self.assertIn("gh-api-allow", reason)
                if line:
                    self.assertIn(line, reason)

    def test_a4_a_faulty_line_does_not_spoil_the_good_ones(self) -> None:
        allow = ("DELETE | x", "DELETE | repos/*/*/git/refs/heads/* | essai")
        self.assertIsNone(verdict("gh api -X DELETE repos/o/r/git/refs/heads/x", allow))

    def test_a4_the_key_is_read_from_usine_md_by_the_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "projet"
            (root / "docs" / "agents").mkdir(parents=True)
            (root / "docs" / "agents" / "usine.md").write_text(
                "- `gh-api-allow` : `DELETE | repos/*/*/git/refs/heads/* | le nettoyage`\n", encoding="utf-8"
            )
            base = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
            environment = {**base, "HOME": tmp, "USERPROFILE": tmp, "CLAUDE_PROJECT_DIR": str(root)}

            def run(command: str) -> tuple[int, str]:
                event = {"tool_input": {"command": command}, "cwd": str(root)}
                err = io.StringIO()
                with (
                    mock.patch.dict(os.environ, environment, clear=True),
                    mock.patch("sys.stdin", io.StringIO(json.dumps(event))),
                    mock.patch("sys.stderr", err),
                    mock.patch("guard_git.current_branch", lambda _cwd: "feat/x"),
                ):
                    return guarded_main(), err.getvalue()

            self.assertEqual(run("gh api -X DELETE repos/o/r/git/refs/heads/x")[0], 0)
            code, message = run("gh api -X DELETE repos/o/r/git/refs/tags/x")
            self.assertEqual(code, 2)
            self.assertIn("DELETE repos/o/r/git/refs/tags/x", message)

    def test_a4_the_refusal_has_a_name_in_the_journal(self) -> None:
        reason = str(verdict("gh api user"))
        unreadable = str(verdict('gh api "$URL"'))
        names = {name for marker, name in RULES if marker in reason}
        self.assertEqual(names, {"gh-api-allow"})
        self.assertEqual({name for marker, name in RULES if marker in unreadable}, {"gh-api-allow"})


def quoted_calls() -> list[tuple[str, str]]:
    """`(file, call)` of each `gh api` the skills, the agents and the templates quote with an endpoint."""
    found: list[tuple[str, str]] = []
    folders = [PLUGIN / "skills", PLUGIN / "agents", PLUGIN / "templates"]
    files = [PLUGIN / "socle.md", *(path for folder in folders for path in sorted(folder.rglob("*.md")))]
    for path in files:
        for span in re.findall(r"`([^`\n]*\bgh api\b[^`\n]*)`", path.read_text(encoding="utf-8")):
            if span.strip() != "gh api":
                found.append((str(path.relative_to(REPO_ROOT)), span))
    return found


def as_typed(call: str) -> str:
    """The call with each `<placeholder>` replaced by a word: `<dépôt>` is an `owner/repo`."""
    return re.sub(r"<([^>]+)>", lambda m: "o/r" if m.group(1) == "dépôt" else "x", call)


class PluginCalls(unittest.TestCase):
    def test_a4_every_gh_api_call_the_plugin_quotes_is_accepted(self) -> None:
        calls = quoted_calls()
        self.assertGreaterEqual(len(calls), 10, "the scan found no call: the pattern is wrong")
        for path, call in calls:
            with self.subTest(file=path, call=call):
                self.assertIsNone(verdict(as_typed(call)))

    def test_a4_the_scan_reads_a_call_with_a_pipe_in_its_filter(self) -> None:
        calls = [call for _path, call in quoted_calls()]
        self.assertTrue(any("select(.type" in call for call in calls))


class Documentation(unittest.TestCase):
    def test_a4_the_template_documents_the_key_without_a_default(self) -> None:
        template = (PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8")
        self.assertRegex(template, r"(?m)^- `gh-api-allow` : `<[^`]*\|[^`]*\|[^`]*>`$")
        self.assertIn("Sans la clé, seule la liste du plugin", template)

    def test_a4_this_repository_declares_no_value_for_the_key(self) -> None:
        guard = (REPO_ROOT / "docs" / "agents" / "usine-gardes.md").read_text(encoding="utf-8")
        self.assertNotIn("gh-api-allow", parse((REPO_ROOT / "docs" / "agents" / "usine.md").read_text(encoding="utf-8")))
        self.assertNotIn("gh-api-allow", parse(guard))
        self.assertIn("`gh-api-allow`", guard.split("## Clés absentes", 1)[1], "the absent key is listed with its reason")


if __name__ == "__main__":
    unittest.main()
