"""Ticket #70: `e2e_trial.py` essaie l'usine de bout en bout sur un dépôt d'essai, avant une version.

Chaque test nomme son ticket et son critère (`ticket #70, critère N`), le ticket n'ayant pas de feature :

1. les clés `e2e-repo`, `e2e-command` et `e2e-budget-usd` : documentées dans le gabarit de `usine.md`,
   « sans objet » quand l'une est absente, jamais `PASS`, aucune valeur par défaut ;
2. la préparation du projet jetable : un clone neuf, une `usine.md` minimale, un ticket fictif ;
3. le lancement de `claude -p`, sous le plafond de la clé et sous le lanceur borné de #66 ;
4. la lecture du résultat : `PASS`, ou `FAIL` avec l'étape qui a manqué, et la tête essayée ;
5. le nettoyage : la PR et le ticket de l'essai, leur branche, et rien d'autre ;
6. la consigne de la PR de version.

`claude`, `git` et `gh` sont des exécutables factices posés sur le `PATH` d'un dossier temporaire : aucun
appel réseau, aucun dépôt réel.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import support
from e2e_trial import main
from output_check import deviations
from usine import parse

USINE_TEMPLATE = support.PLUGIN / "templates" / "usine.md"

COMMAND = (
    "claude -p --plugin-dir {plugin} --max-budget-usd {budget} "
    "--append-system-prompt \"Le ticket de l'essai est le #{ticket}.\" "
    '"/forge:feature-build {feature} --base {base} --max 1"'
)
KEYS = {
    "e2e-repo": "essai-labs/forge-essai",
    "e2e-command": COMMAND,
    "e2e-budget-usd": "2.5",
    "run-limits": "500 | 60",
}


def usine_text(**keys: str) -> str:
    return "".join(f"- `{name}` : `{value}`\n" for name, value in keys.items())


# One program under the three names `git`, `gh` and `claude`: it logs its call, finds the first rule of
# the scenario whose words are all in its arguments, and answers as the rule says. It reaches nothing.
FAKE_TOOL = textwrap.dedent(
    """\
    #!{python}
    import json, os, shutil, sys
    from pathlib import Path

    state = Path(os.environ["E2E_FAKE_STATE"])
    tool, args = Path(sys.argv[0]).name, sys.argv[1:]
    with open(state / "calls.jsonl", "a", encoding="utf-8") as log:
        log.write(json.dumps({{"tool": tool, "args": args, "cwd": os.getcwd()}}) + "\\n")
    if "--body-file" in args:
        shutil.copy(args[args.index("--body-file") + 1], state / "body-file.txt")
    rules = json.loads((state / "scenario.json").read_text(encoding="utf-8")).get(tool, [])
    for index, rule in enumerate(rules):
        if not all(word in args for word in rule["has"]):
            continue
        counter = state / f"count-{{tool}}-{{index}}"
        seen = int(counter.read_text()) if counter.exists() else 0
        counter.write_text(str(seen + 1))
        stdout = rule.get("stdout", "")
        if isinstance(stdout, list):
            stdout = stdout[min(seen, len(stdout) - 1)]
        if rule.get("mkdir"):
            Path(args[-1]).mkdir(parents=True, exist_ok=True)
        if rule.get("snapshot"):
            target = state / "snapshot"
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(args[args.index("-C") + 1], target)
        sys.stdout.write(stdout)
        sys.stderr.write(rule.get("stderr", ""))
        sys.exit(rule.get("code", 0))
    """
)

REPO = "essai-labs/forge-essai"
TICKET_URL = f"https://github.com/{REPO}/issues/12\n"
posix_only = unittest.skipUnless(os.name == "posix", "les exécutables factices sont des scripts à shebang")


def scenario(**changes: list[dict]) -> dict[str, list[dict]]:
    """The answers of the fake tools: a clone that works, a label, a ticket number 12. The rules of a
    test come first, so that they win."""
    base: dict[str, list[dict]] = {
        "gh": [
            {"has": ["repo", "clone"], "mkdir": True},
            {"has": ["label", "create"]},
            {"has": ["issue", "create"], "stdout": TICKET_URL},
        ],
        "git": [{"has": ["commit"], "snapshot": True}],
        "claude": [],
    }
    return {tool: [*changes.get(tool, []), *rules] for tool, rules in base.items()}


class Project:
    """A throwaway project with its `usine.md`, and an environment isolated from the real HOME.

    With `tools` (a scenario), `git`, `gh` and `claude` are the fake tools above and the only programs on
    the `PATH`: the trial cannot reach the real ones.
    """

    def __init__(
        self, test: unittest.TestCase, keys: dict[str, str] | None = None, tools: dict[str, list[dict]] | None = None
    ) -> None:
        folder = tempfile.TemporaryDirectory()
        test.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / "projet"
        (self.root / "docs" / "agents").mkdir(parents=True)
        if keys is not None:
            (self.root / "docs" / "agents" / "usine.md").write_text(usine_text(**keys), encoding="utf-8")
        self.home = Path(folder.name) / "home"
        self.home.mkdir()
        self.state = Path(folder.name) / "state"
        self.state.mkdir()
        self.env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "TMPDIR": str(self.home),
            "TEMP": str(self.home),
        }
        if tools is not None:
            bin_dir = Path(folder.name) / "bin"
            bin_dir.mkdir()
            for name in ("git", "gh", "claude"):
                (bin_dir / name).write_text(FAKE_TOOL.format(python=sys.executable), encoding="utf-8")
                (bin_dir / name).chmod(0o755)
            (self.state / "scenario.json").write_text(json.dumps(tools), encoding="utf-8")
            self.env.update({"PATH": str(bin_dir), "E2E_FAKE_STATE": str(self.state)})

    def run(self, *options: str) -> tuple[int, str, str]:
        """The exit code, standard output and standard error of `main` on this project."""
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.dict(os.environ, self.env, clear=True),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = main(["--projet", str(self.root), "--id", "essai1", *options])
        return code, out.getvalue(), err.getvalue()

    def calls(self, tool: str | None = None) -> list[dict]:
        """What the fake tools were called with, in order."""
        log = self.state / "calls.jsonl"
        if not log.exists():
            return []
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        return [call for call in calls if tool is None or call["tool"] == tool]

    def snapshot(self, *parts: str) -> Path:
        """A file of the throwaway project as the last commit saw it."""
        return self.state.joinpath("snapshot", *parts)


class Keys(unittest.TestCase):
    def test_the_template_documents_the_three_keys_without_a_default(self) -> None:
        """Ticket #70, critère 1 : le gabarit de `usine.md` documente les trois clés et la règle sans valeur."""
        text = USINE_TEMPLATE.read_text(encoding="utf-8")
        for name in ("e2e-repo", "e2e-command", "e2e-budget-usd"):
            with self.subTest(key=name):
                self.assertRegex(text, rf"(?m)^- `{name}` : `<[^`]+>`$")
                self.assertIn(f"sans objet (clé `{name}` absente)", text)

    def test_an_absent_key_is_sans_objet_and_never_pass(self) -> None:
        """Ticket #70, critère 1 : chaque clé absente rend « sans objet (clé `<nom>` absente) », jamais `PASS`."""
        for missing in ("e2e-repo", "e2e-command", "e2e-budget-usd"):
            with self.subTest(missing=missing):
                keys = {name: value for name, value in KEYS.items() if name != missing}
                code, out, _ = Project(self, keys).run()
                self.assertEqual(code, 0)
                self.assertIn(f"SANS-OBJET (clé `{missing}` absente)", out)
                self.assertNotIn("PASS", out)

    def test_without_a_configuration_file_every_key_is_sans_objet(self) -> None:
        """Ticket #70, critère 1 : un projet sans `usine.md` n'a aucune des trois clés, et aucune n'a de valeur."""
        code, out, _ = Project(self).run()
        self.assertEqual(code, 0)
        for name in ("e2e-repo", "e2e-command", "e2e-budget-usd"):
            self.assertIn(f"SANS-OBJET (clé `{name}` absente)", out)
        self.assertNotIn("PASS", out)

    def test_without_run_limits_the_bound_is_sans_objet(self) -> None:
        """Ticket #70, critère 1 : sans `run-limits` ni options, le lancement borné est « sans objet »."""
        keys = {name: value for name, value in KEYS.items() if name != "run-limits"}
        code, out, _ = Project(self, keys).run()
        self.assertEqual(code, 0)
        self.assertIn("SANS-OBJET (clé `run-limits` absente)", out)
        self.assertNotIn("PASS", out)

    def test_a_key_that_is_ill_formed_fails_the_call(self) -> None:
        """Ticket #70, critère 1 : une valeur mal formée est une erreur d'appel (code 2), jamais devinée."""
        cases = {
            "depot sans propriétaire": {"e2e-repo": "forge-essai"},
            "depot avec une URL": {"e2e-repo": "https://github.com/a/b"},
            "plafond nul": {"e2e-budget-usd": "0"},
            "plafond négatif": {"e2e-budget-usd": "-1"},
            "plafond non numérique": {"e2e-budget-usd": "beaucoup"},
            "commande sans le plugin": {"e2e-command": "claude -p --max-budget-usd {budget} {ticket}"},
            "commande sans plafond": {"e2e-command": "claude -p --plugin-dir {plugin} {ticket}"},
            "marque inconnue": {"e2e-command": COMMAND + " {inconnue}"},
        }
        for label, change in cases.items():
            with self.subTest(case=label):
                code, out, err = Project(self, {**KEYS, **change}).run()
                self.assertEqual(code, 2)
                self.assertNotIn("PASS", out)
                self.assertTrue(err.strip())

    def test_a_repeated_key_fails_the_call(self) -> None:
        """Ticket #70, critère 1 : une clé répétée n'a pas une seule valeur : erreur d'appel."""
        project = Project(self, KEYS)
        usine = project.root / "docs" / "agents" / "usine.md"
        usine.write_text(usine.read_text(encoding="utf-8") + "- `e2e-repo` : `essai-labs/autre`\n", encoding="utf-8")
        code, _, err = project.run()
        self.assertEqual(code, 2)
        self.assertIn("e2e-repo", err)


@posix_only
class Preparation(unittest.TestCase):
    def prepare(self, **changes: list[dict]) -> tuple[Project, int, str, str]:
        project = Project(self, KEYS, scenario(**changes))
        code, out, err = project.run()
        return project, code, out, err

    def test_the_throwaway_project_is_a_fresh_clone_of_the_trial_repository(self) -> None:
        """Ticket #70, critère 2 : un clone neuf du dépôt d'essai, hors du projet qui lance l'essai."""
        project, _, _, _ = self.prepare()
        (clone,) = [call for call in project.calls("gh") if call["args"][:2] == ["repo", "clone"]]
        self.assertEqual(clone["args"][2], REPO)
        target = Path(clone["args"][3])
        self.assertNotIn(project.root, (target, *target.parents))
        self.assertFalse(target.exists(), "le dossier jetable est supprimé à la fin")

    def test_the_project_gets_a_minimal_usine_and_a_ready_feature(self) -> None:
        """Ticket #70, critère 2 : `usine.md` minimale, et une feature dont la spec est acceptée."""
        project, _, _, _ = self.prepare()
        config = parse(project.snapshot("docs", "agents", "usine.md").read_text(encoding="utf-8"))
        self.assertEqual(config, {"feature-dir": ["docs/features"], "merge-method": ["merge"]})
        feature = project.snapshot("docs", "features", "F-9999")
        self.assertRegex(feature.joinpath("spec.md").read_text(encoding="utf-8"), r"(?m)^statut: accepte$")
        self.assertRegex(feature.joinpath("idee.md").read_text(encoding="utf-8"), r"(?m)^issue: 12$")

    def test_the_fictitious_ticket_is_ready_for_an_agent_and_has_a_simple_criterion(self) -> None:
        """Ticket #70, critère 2 : un ticket fictif `ready-for-agent`, un critère simple, au gabarit des tickets."""
        project, _, _, _ = self.prepare()
        (create,) = [call["args"] for call in project.calls("gh") if call["args"][:2] == ["issue", "create"]]
        self.assertEqual(create[create.index("--repo") + 1], REPO)
        self.assertEqual(create[create.index("--label") + 1], "ready-for-agent")
        body = (project.state / "body-file.txt").read_text(encoding="utf-8")
        self.assertRegex(body, r"(?m)^- A1: .+")
        self.assertRegex(body, r"(?m)^A1\.1 \| .+ \| .+")
        self.assertIn("Feature: F-9999", body)
        self.assertEqual(deviations(body, "ticket"), [])

    def test_the_base_branch_of_the_trial_carries_the_files_and_is_pushed_by_name(self) -> None:
        """Ticket #70, critère 2 : la base de l'essai est une branche à part, poussée sans `-u` ni `--force`."""
        project, _, _, _ = self.prepare()
        pushes = [call["args"] for call in project.calls("git") if "push" in call["args"]]
        self.assertEqual(len(pushes), 1)
        self.assertEqual(pushes[0][-2:], ["origin", "HEAD:e2e/essai1"])
        self.assertFalse({"-u", "--force", "-f", "--set-upstream"} & set(pushes[0]))
        commit = next(call["args"] for call in project.calls("git") if "commit" in call["args"])
        self.assertIn("user.name=forge-e2e", commit)

    def test_every_gh_call_names_the_trial_repository(self) -> None:
        """Ticket #70, critère 5 : aucun geste `gh` ne vise un autre dépôt que celui de la clé."""
        project, _, _, _ = self.prepare()
        self.assertTrue(project.calls("gh"))
        for call in project.calls("gh"):
            with self.subTest(call=call["args"]):
                self.assertTrue(any(REPO in word for word in call["args"]), call["args"])

    def test_the_project_that_runs_the_trial_is_left_untouched(self) -> None:
        """Ticket #70, critère 2 : le projet qui lance l'essai ne reçoit aucun fichier."""
        project = Project(self, KEYS, scenario())
        before = sorted(path.relative_to(project.root) for path in project.root.rglob("*"))
        project.run()
        self.assertEqual(sorted(path.relative_to(project.root) for path in project.root.rglob("*")), before)

    def test_a_clone_that_fails_is_a_fail_at_preparation_and_creates_nothing(self) -> None:
        """Ticket #70, critère 2 : un clone refusé est `FAIL` à l'étape `preparation`, sans ticket."""
        project, code, out, _ = self.prepare(
            gh=[{"has": ["repo", "clone"], "code": 1, "stderr": "repository not found"}]
        )
        self.assertEqual(code, 1)
        self.assertRegex(out, r"(?m)^RESULTAT: FAIL$")
        self.assertRegex(out, r"(?m)^ETAPE: preparation$")
        self.assertIn("repository not found", out)
        self.assertEqual([call for call in project.calls("gh") if "create" in call["args"]], [])

    def test_a_ticket_without_a_number_is_a_fail_at_ticket(self) -> None:
        """Ticket #70, critère 2 : sans adresse de ticket dans la sortie de `gh issue create`, `FAIL` à l'étape `ticket`."""
        _, code, out, _ = self.prepare(gh=[{"has": ["issue", "create"], "stdout": "créé\n"}])
        self.assertEqual(code, 1)
        self.assertRegex(out, r"(?m)^ETAPE: ticket$")

    def test_the_trial_repository_cannot_be_the_repository_that_runs_it(self) -> None:
        """Ticket #70, critère 5 : le dépôt d'essai n'est jamais le dépôt du projet qui lance l'essai."""
        project, code, _, err = self.prepare(
            git=[{"has": ["remote", "get-url"], "stdout": f"git@github.com:{REPO}.git\n"}]
        )
        self.assertEqual(code, 2)
        self.assertIn(REPO, err)
        self.assertEqual(project.calls("gh"), [])


if __name__ == "__main__":
    unittest.main()
