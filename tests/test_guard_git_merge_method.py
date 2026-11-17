"""La méthode de fusion que dit la clé `merge-method` est la seule qu'un agent lance (ticket #63, suivi #55)."""

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401  met les hooks sur le chemin d'import
from guard_git import guarded_main, refusal


def always_green(*_target: str | None) -> bool:
    return True


def merge(command: str, key: list[str]) -> str | None:
    """Le verdict de `guard_git` sur `command`, pour un projet dont la clé `merge-method` vaut `key`."""
    return refusal(command, "feat/x", always_green, merge_method=key)


FLAGS = {"squash": ("--squash", "-s"), "merge": ("--merge", "-m"), "rebase": ("--rebase", "-r")}


class MethodAgainstTheKey(unittest.TestCase):
    def test_each_method_is_accepted_when_it_is_the_key(self) -> None:
        # #63 : chaque méthode que dit la clé passe, sous son option longue comme sous la courte.
        for method, flags in FLAGS.items():
            for flag in flags:
                with self.subTest(method=method, flag=flag):
                    self.assertIsNone(merge(f"gh pr merge 5 {flag} --delete-branch", [method]))

    def test_a_method_other_than_the_key_is_refused_and_names_both(self) -> None:
        # #63 : `--squash` sous une clé `merge` fusionne contre la règle du projet.
        for key, other in (("merge", "squash"), ("squash", "merge"), ("merge", "rebase"), ("rebase", "squash")):
            for flag in FLAGS[other]:
                with self.subTest(key=key, flag=flag):
                    verdict = merge(f"gh pr merge 5 {flag}", [key])
                    assert verdict is not None
                    self.assertIn("merge-method", verdict)
                    self.assertIn(f"`{key}`", verdict)
                    self.assertIn(f"`{other}`", verdict)


class NoMethod(unittest.TestCase):
    def test_a_merge_without_a_method_is_refused(self) -> None:
        # #63 : sans option de méthode, gh demande à un humain ; la méthode n'est pas celle de la clé.
        for command in ("gh pr merge 5", "gh pr merge 5 --delete-branch --body-file b.md", "gh pr merge --auto"):
            with self.subTest(command=command):
                verdict = merge(command, ["merge"])
                assert verdict is not None
                self.assertIn("merge-method", verdict)
                self.assertIn("--merge", verdict)

    def test_two_methods_are_refused_even_when_one_is_the_key(self) -> None:
        # #63 : gh refuse deux méthodes, mais le garde ne s'en remet pas à lui.
        self.assertIsNotNone(merge("gh pr merge 5 --merge --squash", ["merge"]))
        self.assertIsNotNone(merge("gh pr merge 5 -s -m", ["merge"]))

    def test_the_same_method_twice_is_the_method(self) -> None:
        self.assertIsNone(merge("gh pr merge 5 --merge -m", ["merge"]))

    def test_cancelling_an_auto_merge_merges_nothing_and_needs_no_method(self) -> None:
        self.assertIsNone(merge("gh pr merge 5 --disable-auto", ["merge"]))

    def test_a_value_that_looks_like_a_method_option_is_not_one(self) -> None:
        self.assertIsNone(merge("gh pr merge 5 --merge --body -s", ["merge"]))


class TheKey(unittest.TestCase):
    def test_an_absent_key_refuses_every_merge_and_says_the_merge_is_the_humans(self) -> None:
        # #63 : sans clé, aucune méthode n'est celle du projet ; `/forge:qc` ne fusionne pas non plus.
        for flag in ("--merge", "--squash", "--rebase"):
            with self.subTest(flag=flag):
                verdict = merge(f"gh pr merge 5 {flag}", [])
                assert verdict is not None
                self.assertIn("merge-method", verdict)
                self.assertIn("not declared", verdict)
                self.assertIn("human", verdict)

    def test_an_unknown_value_refuses_and_gives_the_faulty_line(self) -> None:
        # #63 : une faute de frappe ne se lit pas comme une méthode ; la ligne fautive est citée.
        for value in ("ff-only", "Merge", "squash,merge", "", "--merge"):
            with self.subTest(value=value):
                verdict = merge("gh pr merge 5 --merge", [value])
                assert verdict is not None
                self.assertIn(f"- `merge-method` : `{value}`", verdict)
                self.assertIn("merge, squash or rebase", verdict)

    def test_two_lines_are_not_one_method(self) -> None:
        # #63 : la clé tient en une seule ligne.
        verdict = merge("gh pr merge 5 --merge", ["merge", "squash"])
        assert verdict is not None
        self.assertIn("one line", verdict)

    def test_cancelling_an_auto_merge_needs_no_key(self) -> None:
        self.assertIsNone(merge("gh pr merge 5 --disable-auto", []))
        self.assertIsNone(merge("gh pr merge 5 --disable-auto", ["ff-only"]))

    def test_other_commands_do_not_read_the_key(self) -> None:
        self.assertIsNone(merge("gh pr view 5", []))
        self.assertIsNone(merge("git status", []))
        self.assertIsNone(merge("gh pr edit 5 --add-label agent-merged", []))


REST = "gh api -X PUT repos/o/r/pulls/5/merge"


class RestMerge(unittest.TestCase):
    """La fusion par l'API REST porte sa méthode dans le champ `merge_method`, que GitHub lit."""

    def test_the_field_of_the_key_is_accepted_in_every_form_of_a_field(self) -> None:
        # #63 : `-f`, `-F`, `--field`, `--raw-field`, accolé ou avec `=`, comme gh les lit.
        for fields in (
            "-f merge_method=squash", "-F merge_method=squash", "--field merge_method=squash",
            "--raw-field merge_method=squash", "-fmerge_method=squash", "--raw-field=merge_method=squash",
        ):
            with self.subTest(fields=fields):
                self.assertIsNone(merge(f"{REST} {fields}", ["squash"]))

    def test_a_field_other_than_the_key_is_refused(self) -> None:
        verdict = merge(f"{REST} -f merge_method=merge", ["squash"])
        assert verdict is not None
        self.assertIn("`merge`", verdict)
        self.assertIn("`squash`", verdict)

    def test_the_method_in_the_query_string_counts(self) -> None:
        self.assertIsNone(merge("gh api -X PUT 'repos/o/r/pulls/5/merge?merge_method=squash'", ["squash"]))
        self.assertIsNotNone(merge("gh api -X PUT 'repos/o/r/pulls/5/merge?merge_method=merge'", ["squash"]))

    def test_a_rest_merge_without_a_method_is_refused(self) -> None:
        # GitHub fusionnerait alors par commit de fusion, quelle que soit la clé : le garde ne le suppose pas.
        for command in (REST, f"{REST} -f commit_title=x", f"{REST} -f merge_method_other=merge"):
            with self.subTest(command=command):
                verdict = merge(command, ["squash"])
                assert verdict is not None
                self.assertIn("names no method", verdict)

    def test_two_fields_that_disagree_are_refused(self) -> None:
        self.assertIsNotNone(merge(f"{REST} -f merge_method=squash -f merge_method=merge", ["squash"]))

    def test_a_method_the_guard_cannot_read_is_refused(self) -> None:
        # Un corps lu dans un fichier, une valeur lue dans un fichier : la méthode n'est pas lisible.
        for command in (
            f"{REST} --input body.json",
            f"{REST} -F merge_method=@method.txt",
            f"{REST} -f merge_method=squash --input body.json",
        ):
            with self.subTest(command=command):
                verdict = merge(command, ["squash"])
                assert verdict is not None
                self.assertIn("cannot read", verdict)

    def test_the_key_is_judged_before_the_method_of_a_rest_merge(self) -> None:
        self.assertIn("not declared", merge(f"{REST} -f merge_method=squash", []) or "")
        self.assertIn("names no method", merge(f"{REST} -f merge_method=ff-only", ["ff-only"]) or "")

    def test_a_read_of_the_merge_endpoint_is_not_a_merge(self) -> None:
        self.assertIsNone(merge("gh api repos/o/r/pulls/5/merge", ["squash"]))


class TheHook(unittest.TestCase):
    """Le vrai `main` de `guard_git`, qui lit la clé `merge-method` de `docs/agents/usine.md`."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "projet"
        (self.root / "docs" / "agents").mkdir(parents=True)

    def configure(self, text: str) -> None:
        (self.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def run_hook(self, command: str, agent_type: str | None = None) -> tuple[int, str]:
        event = {"tool_input": {"command": command}, "cwd": str(self.root)}
        if agent_type:
            event["agent_type"] = agent_type
        env = {
            **{k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")},
            "HOME": self.tmp.name,
            "USERPROFILE": self.tmp.name,
            "CLAUDE_PROJECT_DIR": str(self.root),
        }
        err = io.StringIO()
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("sys.stdin", io.StringIO(json.dumps(event))),
            mock.patch("sys.stderr", err),
            mock.patch("guard_git.current_branch", lambda _cwd: "feat/x"),
            mock.patch("guard_git.checks_green_via_gh", lambda _cwd: always_green),
            mock.patch("guard_git.description_via_gh", lambda _cwd: lambda *_target: ""),
            mock.patch("guard_git.commits_via_gh", lambda _cwd: lambda *_target: []),
            mock.patch("guard_git.pr_files_via_gh", lambda _cwd: lambda *_args: []),
            mock.patch("guard_git.changed_files_via_gh", lambda _cwd: lambda *_args: []),
        ):
            return guarded_main(), err.getvalue()

    def test_the_method_of_the_key_goes_through_for_every_agent_name(self) -> None:
        self.configure("- `merge-method` : `merge`\n")
        for agent in ("forge:qc-conf", "forge:coder", "autre-agent", None):
            with self.subTest(agent=agent):
                self.assertEqual(self.run_hook("gh pr merge 7 --merge --delete-branch", agent)[0], 0)

    def test_another_method_is_refused_for_every_agent_name(self) -> None:
        self.configure("- `merge-method` : `merge`\n")
        for agent in ("forge:qc-conf", "forge:coder", "autre-agent", None):
            with self.subTest(agent=agent):
                code, message = self.run_hook("gh pr merge 7 --squash", agent)
                self.assertEqual(code, 2)
                self.assertIn("merge-method", message)
                self.assertNotIn("guard_git failed", message)

    def test_a_project_without_the_key_refuses_the_merge(self) -> None:
        self.configure("# Usine\n")
        code, message = self.run_hook("gh pr merge 7 --squash")
        self.assertEqual(code, 2)
        self.assertIn("not declared", message)

    def test_a_project_without_a_usine_file_refuses_the_merge(self) -> None:
        code, message = self.run_hook("gh pr merge 7 --merge")
        self.assertEqual(code, 2)
        self.assertIn("not declared", message)

    def test_an_unknown_value_refuses_the_merge_and_cites_its_line(self) -> None:
        self.configure("- `merge-method` : `ff-only`\n")
        code, message = self.run_hook("gh pr merge 7 --merge")
        self.assertEqual(code, 2)
        self.assertIn("- `merge-method` : `ff-only`", message)


if __name__ == "__main__":
    unittest.main()
