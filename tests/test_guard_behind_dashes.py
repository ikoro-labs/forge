"""#259 : un outil tiers réécrit une commande en `<programme> <chemin> <verbe> -- <commande>`.

Les quatre gardes (`guard_git`, `guard_infra`, `guard_coder`, `guard_readonly`) jugent les mots
après un `--` comme une commande, comme derrière `env` ou `sudo`. Les cas A1.1 à A3.1 sont ceux du
ticket ; les autres gardent ce qu'un `--` ordinaire (`git checkout -- fichier`) n'a pas à perdre.
"""

import io
import json
import unittest
from unittest import mock

import support  # noqa: F401  met les hooks sur le chemin d'import
from guard_coder import main as coder_main
from guard_coder import refusal as coder_refusal
from guard_git import refusal as git_refusal
from guard_infra import verdict
from guard_readonly import gate_refusal, reader_refusal
from guard_readonly import refusal as readonly_refusal

WRAPPER = "node /x/tool shrink --"


def never_green(*_target: str | None) -> bool:
    return False


def git_says(command: str) -> str | None:
    return git_refusal(command, "feat/x", never_green)


def infra_says(command: str) -> str | None:
    event = {"tool_name": "Bash", "tool_input": {"command": command}, "agent_id": "a1"}
    found = verdict(event, [], lambda _args: None, lambda _name: frozenset())
    return None if found is None else found[1]


def coder_says(command: str) -> str | None:
    return coder_refusal("Bash", {"command": command})


def run_coder(command: str, agent: str | None) -> int:
    event: dict[str, object] = {"tool_name": "Bash", "tool_input": {"command": command}}
    if agent is not None:
        event["agent_type"] = agent
    with mock.patch("sys.stdin", io.StringIO(json.dumps(event))), mock.patch("sys.stderr", io.StringIO()):
        return coder_main()


class GuardGit(unittest.TestCase):
    def test_a1_1_a_push_to_main_behind_dashes_is_refused(self) -> None:
        """F-0259 A1.1 : le garde juge `git push origin main` derrière le `--`, pas l'enveloppe."""
        verdict_text = git_says(f"{WRAPPER} git push origin main")
        assert verdict_text is not None
        self.assertIn("main", verdict_text)

    def test_a1_2_a_read_behind_dashes_is_allowed(self) -> None:
        """F-0259 A1.2 : ce qui est permis seul l'est encore derrière le `--`."""
        self.assertIsNone(git_says(f"{WRAPPER} git status"))

    def test_a3_1_a_merge_behind_dashes_keeps_its_alone_refusal(self) -> None:
        """F-0259 A3.1 : une fusion enveloppée n'est pas seule, le garde nomme la forme seule."""
        verdict_text = git_says(f"{WRAPPER} gh pr merge 5")
        assert verdict_text is not None
        self.assertIn("run the merge alone", verdict_text)

    def test_a_force_push_behind_dashes_is_refused(self) -> None:
        """#259 A1 : le ticket cite la poussée forcée, que la protection de `main` ne tient pas."""
        verdict_text = git_says(f"{WRAPPER} git push --force origin x")
        assert verdict_text is not None
        self.assertIn("force push", verdict_text)

    def test_a_wrapper_behind_sudo_and_env_is_read_too(self) -> None:
        """F-0259 A1 : `sudo` et `env` devant l'enveloppe ne la cachent pas."""
        self.assertIsNotNone(git_says(f"sudo env A=1 {WRAPPER} git push origin main"))

    def test_a_program_the_shell_names_behind_dashes_is_a_merge_not_run_alone(self) -> None:
        """#259 A3 : `-- $G pr merge 5` est lu comme `$G pr merge 5` nu, refusé comme fusion non seule."""
        verdict_text = git_says(f"{WRAPPER} $G pr merge 5")
        assert verdict_text is not None
        self.assertIn("run the merge alone", verdict_text)

    def test_a_setting_of_the_repository_behind_dashes_is_refused(self) -> None:
        """#259 A1 : `GIT_DIR=` derrière le `--` envoie les écritures de git ailleurs, comme nu."""
        verdict_text = git_says(f"{WRAPPER} GIT_DIR=/x git status")
        assert verdict_text is not None
        self.assertIn("GIT_DIR", verdict_text)

    def test_a_cd_behind_dashes_moves_nothing_after_it(self) -> None:
        """Non-régression, passe aussi sur la base. #259 A1 : le `cd` d'une commande derrière le `--` ne change pas le répertoire de la suivante."""
        calls: list[str | None] = []

        def branch_of(directory: str | None) -> str:
            calls.append(directory)
            return "feat/x"

        git_refusal(f"{WRAPPER} cd /elsewhere ; git status", branch_of, never_green, "/here")
        self.assertTrue(calls)
        self.assertNotIn("/elsewhere", str(calls))

    def test_an_ordinary_double_dash_loses_nothing(self) -> None:
        """F-0259 A1 : `git checkout -- fichier` et `git commit -- fichier` restent permis sur une branche."""
        for command in (
            "git checkout -- plugins/forge/hooks/guard_git.py",
            "git commit -m 'fix' -- plugins/forge/hooks/guard_git.py",
            "git log --oneline -- docs",
            "git add -- tests/test_x.py",
            'git add -- "$f"',
        ):
            with self.subTest(command=command):
                self.assertIsNone(git_says(command))


class GuardInfra(unittest.TestCase):
    def test_a2_a_docker_rm_behind_dashes_is_guarded(self) -> None:
        """F-0259 A2 : `guard_infra` juge `docker rm` derrière le `--`."""
        verdict_text = infra_says(f"{WRAPPER} docker rm web")
        assert verdict_text is not None
        self.assertIn("docker", verdict_text)

    def test_a_read_behind_dashes_is_not_guarded(self) -> None:
        """Non-régression, passe aussi sur la base. F-0259 A2 : un `docker ps` enveloppé passe comme seul."""
        self.assertIsNone(infra_says(f"{WRAPPER} docker ps"))

    def test_an_ordinary_double_dash_with_a_variable_is_not_guarded(self) -> None:
        """F-0259 A2 : `git add -- "$f"` n'est pas une commande que le garde ne sait pas lire."""
        for command in ('git add -- "$f"', "rm -- $f", "grep -- $pattern file"):
            with self.subTest(command=command):
                self.assertIsNone(infra_says(command))


class GuardCoder(unittest.TestCase):
    def test_a2_1_the_coder_is_refused_a_wrapped_merge(self) -> None:
        """F-0259 A2.1 : le coder ne fusionne pas, enveloppe ou non."""
        verdict_text = coder_says(f"{WRAPPER} gh pr merge 5")
        assert verdict_text is not None
        self.assertIn("qc merges", verdict_text)

    def test_a_wrapped_git_act_is_judged_like_the_bare_one(self) -> None:
        """F-0259 A2 : `push -u` enveloppé est refusé comme nu."""
        verdict_text = coder_says(f"{WRAPPER} git push -u origin HEAD")
        assert verdict_text is not None
        self.assertIn("push -u", verdict_text)

    def test_a_wrapped_suite_without_the_bound_is_refused(self) -> None:
        """F-0259 A2 : une suite lancée derrière le `--` passe par le lanceur borné."""
        verdict_text = coder_says(f"{WRAPPER} python -m pytest tests")
        assert verdict_text is not None
        self.assertIn("without the bound", verdict_text)

    def test_the_bounded_form_and_the_ordinary_double_dash_pass(self) -> None:
        """F-0259 A2 : `bounded_run.py -- pytest` reste la forme permise, et `git add -- f` aussi."""
        for command in (
            "uv run --no-project python scripts/bounded_run.py -- python -m pytest tests",
            f"{WRAPPER} uv run --no-project python scripts/bounded_run.py -- python -m pytest tests",
            "git add -- tests/test_x.py",
            "git checkout -- tests/test_x.py",
        ):
            with self.subTest(command=command):
                self.assertIsNone(coder_says(command))

    def test_the_filter_names_the_prefixed_coder_only(self) -> None:
        """F-0259 A2 : le filtre de rôle du coder tient pour la commande enveloppée."""
        command = f"{WRAPPER} gh pr merge 5"
        self.assertEqual(run_coder(command, "forge:coder"), 2)
        self.assertEqual(run_coder(command, "coder"), 0)
        self.assertEqual(run_coder(command, "forge:qc-gate"), 0)
        self.assertEqual(run_coder(command, None), 0)


class GuardReadonly(unittest.TestCase):
    def test_the_gate_is_refused_a_wrapped_push(self) -> None:
        """F-0259 A2 : `forge:qc-gate` ne pousse pas, derrière le `--` non plus."""
        verdict_text = gate_refusal(f"{WRAPPER} git push origin main", None, "/p")
        assert verdict_text is not None
        self.assertIn("git push", verdict_text)

    def test_the_gate_is_refused_a_wrapped_gh_write(self) -> None:
        """F-0259 A2 : ni une écriture GitHub."""
        self.assertIsNotNone(gate_refusal(f"{WRAPPER} gh pr merge 5", None, "/p"))

    def test_the_gate_keeps_a_wrapped_read(self) -> None:
        """Non-régression, passe aussi sur la base. F-0259 A2 : une lecture enveloppée passe, et `git checkout -- f` hors de la copie aussi."""
        self.assertIsNone(gate_refusal(f"{WRAPPER} git status", None, "/p"))
        self.assertIsNone(gate_refusal("git log -- docs", None, "/p"))

    def test_a_reader_whose_prefix_is_allowed_is_refused_a_wrapped_write(self) -> None:
        """F-0259 A2 : le préfixe `readonly-command` d'un projet n'ouvre pas ce qui suit le `--`."""
        allowed = ["node /x/tool"]
        verdict_text = reader_refusal(f"{WRAPPER} git push origin main", allowed)
        assert verdict_text is not None
        self.assertIn("not a read", verdict_text)
        self.assertIsNotNone(reader_refusal(f"{WRAPPER} gh pr merge 5", allowed))

    def test_a_reader_whose_prefix_is_allowed_keeps_a_wrapped_read(self) -> None:
        """Non-régression, passe aussi sur la base. F-0259 A2 : et une lecture derrière le même `--` passe."""
        allowed = ["node /x/tool"]
        self.assertIsNone(reader_refusal(f"{WRAPPER} git status", allowed))
        self.assertIsNone(reader_refusal("git diff main -- docs", allowed))
        self.assertIsNone(reader_refusal("grep -n -- foo README.md", allowed))

    def test_a_reader_whose_prefix_is_allowed_is_refused_any_wrapped_non_read(self) -> None:
        """#259 A2 : le préfixe `readonly-command` d'un projet n'ouvre aucune commande après le `--`, pas seulement git et gh."""
        allowed = ["node /x/tool"]
        for tail in ("rm -rf docs", "sed -i s/a/b/ f", "/usr/bin/git push origin x", "touch f"):
            with self.subTest(tail=tail):
                verdict_text = reader_refusal(f"{WRAPPER} {tail}", allowed)
                assert verdict_text is not None
                self.assertIn("not a read", verdict_text)

    def test_a_reader_whose_prefix_is_allowed_keeps_any_wrapped_read(self) -> None:
        """Non-régression, passe aussi sur la base. #259 A2 : une lecture quelconque derrière le même `--` passe, comme seule."""
        allowed = ["node /x/tool"]
        for tail in ("cat README.md", "sed -n 1,5p f", "grep -rn foo docs", "git log --oneline"):
            with self.subTest(tail=tail):
                self.assertIsNone(reader_refusal(f"{WRAPPER} {tail}", allowed))

    def test_the_filter_names_the_gate_and_the_readers_only(self) -> None:
        """F-0259 A2 : le filtre de `guard_readonly` tient pour la commande enveloppée."""

        def event(agent: str | None) -> dict[str, object]:
            call: dict[str, object] = {
                "tool_name": "Bash",
                "tool_input": {"command": f"{WRAPPER} git push origin main"},
                "cwd": "/p",
            }
            if agent is not None:
                call["agent_type"] = agent
            return call

        self.assertIsNotNone(readonly_refusal(event("forge:qc-gate")))
        self.assertIsNone(readonly_refusal(event("gate")))
        self.assertIsNone(readonly_refusal(event(None)))


if __name__ == "__main__":
    unittest.main()
