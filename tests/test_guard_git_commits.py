"""`guard_git` relit les messages des commits de la PR avant une fusion (ticket #64, suivi #55)."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401  met les hooks sur le chemin d'import
from guard_git import commits_via_gh, guarded_main, parse_commits, refusal
from usine import Loaded

Commit = tuple[str, str]
SHA = "8e80a6e46958d38d63deb30b4500f23899bf5c01"


def always_green(*_target: str | None) -> bool:
    return True


def merge(
    command: str,
    commits: list[Commit] | None,
    description: str = "Refs #206\n",
    key: list[str] | None = None,
) -> str | None:
    """Le verdict de `guard_git` sur `command`, pour une PR dont `gh` rend ces commits et cette description."""
    return refusal(
        command,
        "feat/x",
        always_green,
        description=lambda *_target: description,
        commit_messages=lambda *_target: commits,
        merge_method=key,
    )


class ClosingKeywordInACommit(unittest.TestCase):
    def test_a_commit_that_closes_a_ticket_the_description_cites_with_refs_is_refused(self) -> None:
        # #64 : GitHub lit le message de chaque commit de la branche quand la fusion est un commit de fusion.
        verdict = merge("gh pr merge 5 --merge", [(SHA, "feat(x): a\n\nCloses #206\n")])
        assert verdict is not None
        self.assertIn("#206", verdict)

    def test_the_refusal_names_the_commit_and_says_how_to_fix_it(self) -> None:
        # #64 : le sha court, le ticket, puis les deux sorties : réécrire le message ou retirer le `Refs`.
        commits = [("1111111aaaa", "fix: b"), (SHA, "feat(x): a\n\nCloses #206")]
        verdict = merge("gh pr merge 5 --merge", commits)
        assert verdict is not None
        self.assertIn("8e80a6e", verdict)
        self.assertNotIn("1111111", verdict)
        self.assertNotIn(SHA, verdict)
        self.assertIn("rewrite the commit message", verdict)
        self.assertIn("drop #206 from the Refs", verdict)

    def test_a_commit_that_cites_the_ticket_with_refs_passes(self) -> None:
        # #64 : le cas courant, que la règle ne doit pas gêner.
        commits = [(SHA, "feat(x): a\n\nRefs #206\n"), ("2222222", "test(x): b\n\nRefs #206")]
        self.assertIsNone(merge("gh pr merge 5 --merge", commits))

    def test_a_closing_keyword_for_another_ticket_than_the_refs_passes(self) -> None:
        # #64 : seul le ticket que la description cite en `Refs` est gardé ouvert.
        self.assertIsNone(merge("gh pr merge 5 --merge", [(SHA, "fix(x): a\n\nCloses #207\n")]))

    def test_every_closing_keyword_github_reads_is_caught_in_a_commit(self) -> None:
        # #64 : la règle des mots-clés est celle de la description et du message de fusion, une seule fonction.
        for closing in ["Closed #206", "fix #206", "Fixes #206", "resolved: #206", "RESOLVES o/r#206"]:
            with self.subTest(closing=closing):
                self.assertIsNotNone(merge("gh pr merge 5 --merge", [(SHA, f"fix: a\n\n{closing}")]))

    def test_a_commit_that_closes_a_ticket_no_refs_cites_passes(self) -> None:
        # #64 : une PR en `Closes #206` peut porter un commit en `Closes #206`.
        commits = [(SHA, "feat(x): a\n\nCloses #206\n")]
        self.assertIsNone(merge("gh pr merge 5 --merge", commits, description="Closes #206\n"))


class UnderEveryMethod(unittest.TestCase):
    def test_a_squash_applies_the_rule_too(self) -> None:
        # #64 : avec `merge-method` à `squash` (#63), les messages des commits entrent dans le message par défaut.
        commits = [(SHA, "feat(x): a\n\nCloses #206")]
        for flag in ("--squash", "-s"):
            with self.subTest(flag=flag):
                verdict = merge(f"gh pr merge 5 {flag}", commits, key=["squash"])
                assert verdict is not None
                self.assertIn("8e80a6e", verdict)
        self.assertIsNone(merge("gh pr merge 5 --squash", [(SHA, "feat(x): a\n\nRefs #206")], key=["squash"]))

    def test_the_other_methods_apply_it_too(self) -> None:
        commits = [(SHA, "feat(x): a\n\nCloses #206")]
        for method in ("merge", "rebase"):
            with self.subTest(method=method):
                self.assertIsNotNone(merge(f"gh pr merge 5 --{method}", commits, key=[method]))

    def test_a_squash_with_an_explicit_body_is_still_judged_on_the_commits(self) -> None:
        # #64 : le garde ne devine pas ce que GitHub retient du corps donné : une règle plus sûre.
        commits = [(SHA, "feat(x): a\n\nCloses #206")]
        verdict = merge('gh pr merge 5 --squash --body "Refs #206"', commits, key=["squash"])
        assert verdict is not None
        self.assertIn("8e80a6e", verdict)

    def test_a_refs_in_the_merge_message_counts_as_a_citation(self) -> None:
        # #64 : la description ne cite pas le ticket, le message de fusion le fait : le commit qui le ferme est refusé.
        commits = [(SHA, "feat(x): a\n\nCloses #206")]
        self.assertIsNotNone(merge('gh pr merge 5 --squash --body "Refs #206"', commits, description="", key=["squash"]))


class FailsClosed(unittest.TestCase):
    def test_an_unreadable_list_of_commits_refuses_the_merge(self) -> None:
        # #64 : fermé par défaut, la liste que `gh` n'a pas su rendre ne laisse rien passer.
        verdict = merge("gh pr merge 5 --merge", None)
        assert verdict is not None
        self.assertIn("commits", verdict)
        self.assertIn("cannot be read", verdict)

    def test_an_empty_list_is_a_list(self) -> None:
        self.assertIsNone(merge("gh pr merge 5 --merge", []))

    def test_the_text_of_gh_is_read_strictly(self) -> None:
        # #64 : une forme que `gh pr view --json commits` ne rend pas est une liste illisible.
        one = '{"commits":[{"oid":"abc1234","messageHeadline":"feat: a","messageBody":"Refs #3"}]}'
        self.assertEqual(parse_commits(one), [("abc1234", "feat: a\n\nRefs #3")])
        self.assertEqual(parse_commits('{"commits":[]}'), [])
        for text in (
            "",
            "pas du json",
            "[]",
            "{}",
            '{"commits":null}',
            '{"commits":["a"]}',
            '{"commits":[{"messageHeadline":"a","messageBody":""}]}',
            '{"commits":[{"oid":"","messageHeadline":"a","messageBody":""}]}',
            '{"commits":[{"oid":"a1","messageBody":""}]}',
            '{"commits":[{"oid":"a1","messageHeadline":"a"}]}',
            '{"commits":[{"oid":"a1","messageHeadline":3,"messageBody":""}]}',
        ):
            with self.subTest(text=text):
                self.assertIsNone(parse_commits(text))

    def test_a_headline_without_a_body_is_the_whole_message(self) -> None:
        text = '{"commits":[{"oid":"a1","messageHeadline":"feat: a","messageBody":""}]}'
        self.assertEqual(parse_commits(text), [("a1", "feat: a")])

    def test_a_keyword_cut_by_the_headline_limit_is_read_whole(self) -> None:
        # #64 : `gh` coupe un titre long avec une « … » et reprend la suite, en « … », au début du corps :
        # un `Closes #206` à cheval sur la coupure doit se relire en entier.
        text = json.dumps(
            {"commits": [{"oid": SHA, "messageHeadline": "feat(x): " + "m" * 40 + " Clos…", "messageBody": "…es #206\n\nsuite"}]}
        )
        commits = parse_commits(text)
        assert commits is not None
        self.assertEqual(commits[0][1], "feat(x): " + "m" * 40 + " Closes #206\n\nsuite")
        self.assertIsNotNone(merge("gh pr merge 5 --merge", commits))

    def run_gh(self, script: str) -> list[Commit] | None:
        """`gh` est joué par Python, qui exécute le script `pr` du dossier de la commande."""
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "pr").write_text(script, encoding="utf-8")
            with mock.patch("shutil.which", lambda _name: sys.executable):
                return commits_via_gh(folder)("5", None, None)

    def test_a_gh_that_prints_the_commits_is_read(self) -> None:
        script = "print('{\"commits\":[{\"oid\":\"a1\",\"messageHeadline\":\"feat: a\",\"messageBody\":\"\"}]}')"
        self.assertEqual(self.run_gh(script), [("a1", "feat: a")])

    def test_a_gh_that_fails_prints_garbage_or_times_out_is_an_unreadable_list(self) -> None:
        self.assertIsNone(self.run_gh("import sys; print('{\"commits\":[]}'); sys.exit(1)"))
        self.assertIsNone(self.run_gh("print('pas du json')"))
        with mock.patch("guard_git.TIMEOUT_SECONDS", 1):
            self.assertIsNone(self.run_gh("import time; time.sleep(30)"))

    def test_without_gh_the_list_is_unreadable(self) -> None:
        with mock.patch("shutil.which", lambda _name: None):
            self.assertIsNone(commits_via_gh(None)("5", None, None))

    def test_the_commits_are_asked_for_the_pr_the_merge_names(self) -> None:
        # #64 : le numéro, le dépôt et le dossier sont ceux que lisent les autres lectures de la fusion.
        script = (
            "import json, sys\n"
            "args = sys.argv[1:]\n"
            "if args[1:3] != ['5', '-R'] or args[3] != 'o/other' or args[4:] != ['--json', 'commits']:\n"
            "    sys.exit(1)\n"
            "print(json.dumps({'commits': [{'oid': 'a1', 'messageHeadline': 'fix: a', 'messageBody': 'Closes #3'}]}))\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "pr").write_text(script, encoding="utf-8")
            with mock.patch("shutil.which", lambda _name: sys.executable):
                self.assertEqual(commits_via_gh(folder)("5", "o/other", folder), [("a1", "fix: a\n\nCloses #3")])
                self.assertIsNone(commits_via_gh(folder)("6", "o/other", folder))


class TheHook(unittest.TestCase):
    """Le vrai `main` de `guard_git` : il lit les commits de la PR par `commits_via_gh`, pour tout nom d'agent."""

    def run_hook(self, commits: list[Commit] | None, agent_type: str | None = None) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as home:
            event = {"tool_input": {"command": "gh pr merge 7 --merge"}, "cwd": home}
            if agent_type:
                event["agent_type"] = agent_type
            env = {
                **{k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")},
                "HOME": home,
                "USERPROFILE": home,
                "CLAUDE_PROJECT_DIR": home,
            }
            err = io.StringIO()
            with (
                mock.patch.dict(os.environ, env, clear=True),
                mock.patch("sys.stdin", io.StringIO(json.dumps(event))),
                mock.patch("sys.stderr", err),
                mock.patch("guard_git.current_branch", lambda _cwd: "feat/x"),
                mock.patch("guard_git.checks_green_via_gh", lambda _cwd: always_green),
                mock.patch("guard_git.description_via_gh", lambda _cwd: lambda *_target: "Refs #206\n"),
                mock.patch("guard_git.pr_files_via_gh", lambda _cwd: lambda *_args: []),
                mock.patch("guard_git.autonomy_refusal", lambda _directory, _gesture: None),  # the key is read in origin/main: tests/test_guard_git_autonomy.py
                mock.patch("guard_git.changed_files_via_gh", lambda _cwd: lambda *_args: []),
                mock.patch("guard_git.commits_via_gh", lambda _cwd: lambda *_target: commits),
                mock.patch("guard_git.load_checked", lambda _root: Loaded({"merge-method": ["merge"]}, [], None)),
            ):
                return guarded_main(), err.getvalue()

    def test_a_commit_that_closes_a_ticket_cited_with_refs_refuses_the_merge(self) -> None:
        for agent in ("forge:qc-conf", "forge:coder", "autre-agent", None):
            with self.subTest(agent=agent):
                code, message = self.run_hook([(SHA, "fix: a\n\nCloses #206")], agent)
                self.assertEqual(code, 2)
                self.assertIn("8e80a6e", message)
                self.assertNotIn("guard_git failed", message)

    def test_commits_that_cite_the_ticket_with_refs_let_the_merge_through(self) -> None:
        self.assertEqual(self.run_hook([(SHA, "fix: a\n\nRefs #206")])[0], 0)

    def test_an_unreadable_list_refuses_the_merge_through_the_hook(self) -> None:
        code, message = self.run_hook(None)
        self.assertEqual(code, 2)
        self.assertIn("cannot be read", message)


if __name__ == "__main__":
    unittest.main()
