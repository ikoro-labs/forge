"""La fusion d'une PR qui touche la clé `protected-path` est refusée à tout agent (ticket #62, suivi #55)."""

import io
import json
import os
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import support  # noqa: F401  met les hooks sur le chemin d'import
from guard_git import changed_files_via_gh, guarded_main, parse_changed_files, refusal

PROTECTED = [".github/", "plugins/forge/hooks/guard_", ".claude/settings.json"]


def always_green(_pr: str | None) -> bool:
    return True


def listing(*paths: str) -> Callable[[str | None], list[str] | None]:
    return lambda _pr: list(paths)


def unreadable(_pr: str | None) -> list[str] | None:
    return None


def merge(command: str, changed: Callable[[str | None], list[str] | None], protected: list[str] = PROTECTED) -> str | None:
    return refusal(command, "feat/x", always_green, protected_paths=protected, changed_files=changed)


class ProtectedPaths(unittest.TestCase):
    def test_a_file_under_a_protected_prefix_refuses_the_merge_and_names_file_and_prefix(self) -> None:
        verdict = merge("gh pr merge 5 --merge", listing("README.md", "plugins/forge/hooks/guard_git.py"))
        assert verdict is not None
        self.assertIn("plugins/forge/hooks/guard_git.py", verdict)
        self.assertIn("plugins/forge/hooks/guard_", verdict)
        self.assertIn("humain", verdict)

    def test_a_diff_without_a_protected_file_passes(self) -> None:
        self.assertIsNone(merge("gh pr merge 5 --merge", listing("README.md", "plugins/forge/hooks/budget.py")))

    def test_the_prefix_is_compared_word_for_word_on_a_posix_path(self) -> None:
        # Un préfixe est un début de chemin, pas un motif : `.github/` n'est pas `docs/.github/`.
        self.assertIsNone(merge("gh pr merge 5", listing("docs/.github/x.md", ".githubx/a")))
        self.assertIsNotNone(merge("gh pr merge 5", listing(".github/workflows/ci.yml")))
        self.assertIsNotNone(merge("gh pr merge 5", listing(".claude\\settings.json")))
        self.assertIsNotNone(merge("gh pr merge 5", listing("./.claude/settings.json")))

    def test_the_pr_number_is_passed_to_the_listing(self) -> None:
        seen: list[str | None] = []

        def changed(pr: str | None) -> list[str]:
            seen.append(pr)
            return []

        merge("gh pr merge 5 --squash", changed)
        merge("gh pr merge --squash", changed)
        self.assertEqual(seen, ["5", None])

    def test_without_the_key_nothing_is_refused_and_the_diff_is_not_read(self) -> None:
        def boom(_pr: str | None) -> list[str]:
            raise AssertionError("la liste des fichiers n'est pas lue sans la clé")

        self.assertIsNone(merge("gh pr merge 5", boom, protected=[]))

    def test_other_commands_do_not_read_the_diff(self) -> None:
        def boom(_pr: str | None) -> list[str]:
            raise AssertionError("seule une fusion lit la liste")

        self.assertIsNone(merge("gh pr view 5", boom))
        self.assertIsNone(merge("git status", boom))


class FailsClosed(unittest.TestCase):
    def test_an_unreadable_list_refuses_when_the_key_is_declared(self) -> None:
        verdict = merge("gh pr merge 5", unreadable)
        assert verdict is not None
        self.assertIn("protected-path", verdict)
        self.assertIn("humain", verdict)

    def test_the_text_of_gh_is_read_strictly(self) -> None:
        self.assertEqual(parse_changed_files('{"files":[{"path":"a/b"},{"path":"c"}]}'), ["a/b", "c"])
        self.assertEqual(parse_changed_files('{"files":[]}'), [])
        for text in ("", "not json", "[]", "{}", '{"files":null}', '{"files":["a"]}', '{"files":[{"name":"a"}]}', '{"files":[{"path":""}]}'):
            with self.subTest(text=text):
                self.assertIsNone(parse_changed_files(text))

    def run_gh(self, script: str) -> list[str] | None:
        """`gh` est joué par Python, qui exécute le script `pr` du dossier de la commande."""
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "pr").write_text(script, encoding="utf-8")
            with mock.patch("shutil.which", lambda _name: sys.executable):
                return changed_files_via_gh(folder)("5")

    def test_a_gh_that_prints_a_list_is_read(self) -> None:
        self.assertEqual(self.run_gh("print('{\"files\":[{\"path\":\"x/y.py\"}]}')"), ["x/y.py"])

    def test_a_gh_that_fails_is_an_unreadable_list(self) -> None:
        self.assertIsNone(self.run_gh("import sys; print('{\"files\":[]}'); sys.exit(1)"))

    def test_a_gh_that_prints_garbage_is_an_unreadable_list(self) -> None:
        self.assertIsNone(self.run_gh("print('pas du json')"))

    def test_a_gh_that_times_out_is_an_unreadable_list(self) -> None:
        with mock.patch("guard_git.TIMEOUT_SECONDS", 1):
            self.assertIsNone(self.run_gh("import time; time.sleep(30)"))

    def test_without_gh_the_list_is_unreadable(self) -> None:
        with mock.patch("shutil.which", lambda _name: None):
            self.assertIsNone(changed_files_via_gh(None)("5"))


class TheHook(unittest.TestCase):
    """Le vrai `main` de `guard_git`, sur un projet qui déclare la clé, pour tout nom d'agent."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "projet"
        (self.root / "docs" / "agents").mkdir(parents=True)
        self.env = {
            **{k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")},
            "HOME": self.tmp.name,
            "USERPROFILE": self.tmp.name,
        }

    def configure(self, text: str) -> None:
        (self.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def run_hook(self, command: str, agent_type: str | None, changed: Callable[[str | None], list[str] | None]) -> tuple[int, str]:
        event = {"tool_input": {"command": command}, "cwd": str(self.root)}
        if agent_type:
            event["agent_type"] = agent_type
        err = io.StringIO()
        with (
            mock.patch.dict(os.environ, {**self.env, "CLAUDE_PROJECT_DIR": str(self.root)}, clear=True),
            mock.patch("sys.stdin", io.StringIO(json.dumps(event))),
            mock.patch("sys.stderr", err),
            mock.patch("guard_git.current_branch", lambda _cwd: "feat/x"),
            mock.patch("guard_git.checks_green_via_gh", lambda _cwd: always_green),
            mock.patch("guard_git.description_via_gh", lambda _cwd: lambda _pr: ""),
            mock.patch("guard_git.changed_files_via_gh", lambda _cwd: changed),
        ):
            return guarded_main(), err.getvalue()

    def test_the_merge_is_refused_for_every_agent_name_and_none(self) -> None:
        self.configure("- `protected-path` : `.github/`\n")
        for agent in ("forge:qc-conf", "forge:coder", "qc-conf", "autre-agent", None):
            with self.subTest(agent=agent):
                code, message = self.run_hook("gh pr merge 7 --squash", agent, listing(".github/workflows/ci.yml"))
                self.assertEqual(code, 2)
                self.assertIn(".github/workflows/ci.yml", message)
                self.assertNotIn("guard_git failed", message)

    def test_a_clean_diff_goes_through(self) -> None:
        self.configure("- `protected-path` : `.github/`\n")
        self.assertEqual(self.run_hook("gh pr merge 7 --squash", "autre-agent", listing("README.md"))[0], 0)

    def test_an_unreadable_list_refuses_the_merge_through_the_hook(self) -> None:
        self.configure("- `protected-path` : `.github/`\n")
        code, message = self.run_hook("gh pr merge 7 --squash", None, unreadable)
        self.assertEqual(code, 2)
        self.assertIn("protected-path", message)

    def test_without_the_key_the_merge_goes_through_and_nothing_is_read(self) -> None:
        self.configure("# Usine\n")
        self.assertEqual(self.run_hook("gh pr merge 7 --squash", "forge:qc-conf", unreadable)[0], 0)


if __name__ == "__main__":
    unittest.main()
