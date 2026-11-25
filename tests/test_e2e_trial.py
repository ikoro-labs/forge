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
import re
import subprocess
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
    import json, os, shutil, sys, time
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
        stdout, code = rule.get("stdout", ""), rule.get("code", 0)
        if isinstance(stdout, list):
            stdout = stdout[min(seen, len(stdout) - 1)]
        if isinstance(code, list):
            code = code[min(seen, len(code) - 1)]
        if rule.get("mkdir"):
            Path(args[-1]).mkdir(parents=True, exist_ok=True)
        time.sleep(rule.get("sleep", 0))
        if rule.get("snapshot"):
            target = state / "snapshot"
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(args[args.index("-C") + 1], target)
        sys.stdout.write(stdout)
        sys.stderr.write(rule.get("stderr", ""))
        sys.exit(code)
    """
)

REPO = "essai-labs/forge-essai"
TICKET_URL = f"https://github.com/{REPO}/issues/12\n"
posix_only = unittest.skipUnless(os.name == "posix", "les exécutables factices sont des scripts à shebang")


OWN_URL = "https://github.com/ikoro-labs/forge.git"  # the repository of the project that runs the trial


def remotes(*urls: str, name: str = "origin") -> str:
    """What `git remote -v` prints: a fetch and a push line for each URL."""
    return "".join(f"{name}\t{url} (fetch)\n{name}\t{url} (push)\n" for url in urls)


def pr(number: int = 13, body: str = "Closes #12", state: str = "OPEN", branch: str = "feat/essai") -> dict:
    return {"number": number, "title": "feat: écrire le fichier", "body": body, "state": state, "headRefName": branch}


def prs(*found: dict) -> str:
    """What `gh pr list --json` prints."""
    return json.dumps(list(found))


def checks(*found: tuple[str, str]) -> str:
    """What `gh pr checks --json name,bucket` prints."""
    return json.dumps([{"name": name, "bucket": bucket} for name, bucket in found])


def scenario(**changes: list[dict]) -> dict[str, list[dict]]:
    """The answers of the fake tools: a clone that works, a label, a ticket number 12. The rules of a
    test come first, so that they win."""
    base: dict[str, list[dict]] = {
        "gh": [
            {"has": ["repo", "clone"], "mkdir": True},
            {"has": ["label", "create"]},
            {"has": ["issue", "create"], "stdout": TICKET_URL},
            {"has": ["pr", "list"], "stdout": prs(pr())},
            {"has": ["pr", "checks"], "stdout": checks(("tests", "pass"), ("lint", "pass"))},
        ],
        "git": [
            {"has": ["remote", "-v"], "stdout": remotes(OWN_URL)},
            {"has": ["commit"], "snapshot": True},
            {"has": ["rev-parse", "HEAD"], "stdout": "0123abc\n"},
        ],
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
        self.bin = Path(folder.name) / "bin"
        if tools is not None:
            bin_dir = self.bin
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

    def test_the_template_documents_the_key_e2e_run_limits(self) -> None:
        """Ticket #359, A2 : le gabarit de `usine.md` documente `e2e-run-limits`, de la forme de `run-limits`."""
        text = USINE_TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^- `e2e-run-limits` : `<mémoire en Mo> \| <délai en secondes>`$")

    def test_an_ill_formed_e2e_run_limits_fails_the_call(self) -> None:
        """Ticket #359, A2 : une valeur de `e2e-run-limits` mal formée est une erreur d'appel (code 2), jamais devinée."""
        cases = ["500", "0 | 60", "500 | 0", "beaucoup | 60", "500 | longtemps", "500 | 60 | 1", "-5 | 60"]
        for value in cases:
            with self.subTest(value=value):
                code, out, err = Project(self, {**KEYS, "e2e-run-limits": value}).run()
                self.assertEqual(code, 2)
                self.assertNotIn("PASS", out)
                self.assertIn("e2e-run-limits", err)

    def test_a_repeated_e2e_run_limits_fails_the_call(self) -> None:
        """Ticket #359, A2 : `e2e-run-limits` répétée n'a pas une seule valeur : erreur d'appel."""
        project = Project(self, {**KEYS, "e2e-run-limits": "500 | 60"})
        usine = project.root / "docs" / "agents" / "usine.md"
        usine.write_text(usine.read_text(encoding="utf-8") + "- `e2e-run-limits` : `500 | 90`\n", encoding="utf-8")
        code, _, err = project.run()
        self.assertEqual(code, 2)
        self.assertIn("e2e-run-limits", err)

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



@posix_only
class OwnRepositoryGuard(unittest.TestCase):
    """Ticket #70, critère 5 : l'essai ne tourne jamais sur le dépôt du projet qui le lance.

    Il y crée un ticket, y pousse une branche et y ferme des objets : le garde refuse (code 2, rien créé) tout
    dépôt d'essai que les remotes du projet nomment, quelle que soit la forme de l'URL ou la casse, et refuse
    aussi quand il ne sait pas lire les remotes.
    """

    def run_with(self, remote_output: str, repo: str = REPO, code: int = 0) -> tuple[Project, int, str]:
        keys = {**KEYS, "e2e-repo": repo}
        project = Project(self, keys, scenario(git=[{"has": ["remote", "-v"], "stdout": remote_output, "code": code}]))
        exit_code, _, err = project.run()
        return project, exit_code, err

    def assert_refused(self, project: Project, code: int, err: str, *words: str) -> None:
        self.assertEqual(code, 2, err)
        for word in words:
            self.assertIn(word, err)
        self.assertEqual(project.calls("gh"), [], "rien n'est créé sur le dépôt")
        self.assertEqual([c for c in project.calls("git") if "push" in c["args"]], [])
        self.assertEqual(project.calls("claude"), [])

    def test_the_exact_name_is_refused(self) -> None:
        """Ticket #70, critère 5 : le nom exact du dépôt du projet est refusé."""
        project, code, err = self.run_with(remotes(f"git@github.com:{REPO}.git"))
        self.assert_refused(project, code, err, REPO)

    def test_a_different_case_is_refused_on_either_side(self) -> None:
        """Ticket #70, critère 5 : GitHub ignore la casse : `Essai-Labs/Forge-Essai` est le même dépôt."""
        project, code, err = self.run_with(remotes("https://github.com/ESSAI-LABS/Forge-Essai.git"))
        self.assert_refused(project, code, err)
        project, code, err = self.run_with(remotes(f"https://github.com/{REPO}.git"), repo="Essai-Labs/FORGE-essai")
        self.assert_refused(project, code, err)

    def test_an_ssh_host_alias_is_refused(self) -> None:
        """Ticket #70, critère 5 : un alias d'hôte SSH (`github-perso`) ne cache pas le dépôt."""
        for url in (
            f"git@github-perso:{REPO}.git",
            f"github-perso:{REPO}",
            f"ssh://git@github-perso/{REPO}.git",
            f"ssh://git@github.com:22/{REPO}.git",
        ):
            with self.subTest(url=url):
                project, code, err = self.run_with(remotes(url))
                self.assert_refused(project, code, err)

    def test_the_trailing_dot_git_and_slash_do_not_matter(self) -> None:
        """Ticket #70, critère 5 : `.git` final, `/` final ou aucun des deux : le même dépôt."""
        for url in (
            f"https://github.com/{REPO}.git",
            f"https://github.com/{REPO}",
            f"https://github.com/{REPO}/",
            f"https://github.com/{REPO}.git/",
        ):
            with self.subTest(url=url):
                project, code, err = self.run_with(remotes(url))
                self.assert_refused(project, code, err)

    def test_an_https_url_with_credentials_or_a_port_is_refused(self) -> None:
        """Ticket #70, critère 5 : une URL https avec identifiants ou port nomme le même dépôt."""
        for url in (
            f"https://user:jeton@github.com/{REPO}.git",
            f"https://github.com:443/{REPO}.git",
            f"HTTPS://GitHub.com/{REPO}.git",
        ):
            with self.subTest(url=url):
                project, code, err = self.run_with(remotes(url))
                self.assert_refused(project, code, err)

    def test_the_push_url_and_the_other_remotes_count_too(self) -> None:
        """Ticket #70, critère 5 : l'URL de poussée et un autre remote que `origin` nomment aussi le dépôt."""
        pushing = f"origin\t{OWN_URL} (fetch)\norigin\thttps://github.com/{REPO}.git (push)\n"
        project, code, err = self.run_with(pushing)
        self.assert_refused(project, code, err)
        project, code, err = self.run_with(remotes(OWN_URL) + remotes(f"git@github.com:{REPO}.git", name="upstream"))
        self.assert_refused(project, code, err)

    def test_a_remote_that_cannot_be_read_is_a_refusal(self) -> None:
        """Ticket #70, critère 5 : une origine illisible vaut refus, jamais passage."""
        cases = {
            "aucun remote": ("", 0),
            "git en échec": ("", 128),
            "chemin local": (remotes("/home/quelquun/forge"), 0),
            "chemin relatif": (remotes("../forge"), 0),
            "mot seul": (remotes("n-importe-quoi"), 0),
            "trop de niveaux": (remotes("https://gitlab.example/a/b/c.git"), 0),
            "ligne sans URL": ("origin\n", 0),
            "un remote lisible et un illisible": (remotes(OWN_URL) + remotes("?!", name="autre"), 0),
        }
        for label, (output, code) in cases.items():
            with self.subTest(case=label):
                project, exit_code, err = self.run_with(output, code=code)
                self.assert_refused(project, exit_code, err, "illisible")

    def test_another_repository_passes_whatever_its_form(self) -> None:
        """Ticket #70, critère 5 : un autre dépôt, lu sans doute, laisse l'essai tourner."""
        for url in (OWN_URL, "git@github-perso:ikoro-labs/forge.git", "https://tok@github.com/ikoro-labs/forge/"):
            with self.subTest(url=url):
                project, code, err = self.run_with(remotes(url))
                self.assertEqual(code, 0, err)
                self.assertTrue(project.calls("gh"))

    def test_a_prefix_of_the_name_is_not_the_same_repository(self) -> None:
        """Ticket #70, critère 5 : `essai-labs/forge-essai-2` n'est pas `essai-labs/forge-essai`."""
        project, code, err = self.run_with(remotes(f"https://github.com/{REPO}-2.git"))
        self.assertEqual(code, 0, err)


@posix_only
class Launch(unittest.TestCase):
    def chdir(self, folder: Path) -> None:
        """Work from `folder` for the rest of the test (`contextlib.chdir` needs Python 3.11)."""
        before = os.getcwd()
        os.chdir(folder)
        self.addCleanup(os.chdir, before)

    def launch(self, *options: str, keys: dict[str, str] | None = None, **changes: list[dict]):
        project = Project(self, keys or KEYS, scenario(**changes))
        code, out, err = project.run(*options)
        return project, code, out, err

    def test_claude_runs_in_the_throwaway_project_with_the_plugin_under_test_and_the_ceiling(self) -> None:
        """Ticket #70, critère 3 : `claude -p` tourne dans le clone, avec `--plugin-dir` et `--max-budget-usd`."""
        project, _, _, _ = self.launch()
        (call,) = project.calls("claude")
        clone = next(c["args"][3] for c in project.calls("gh") if c["args"][:2] == ["repo", "clone"])
        self.assertEqual(os.path.realpath(call["cwd"]), os.path.realpath(clone))
        args = call["args"]
        self.assertEqual(args[0], "-p")
        self.assertEqual(args[args.index("--plugin-dir") + 1], str(support.PLUGIN))
        self.assertEqual(args[args.index("--max-budget-usd") + 1], "2.5")

    def test_the_markers_of_the_command_name_the_ticket_the_feature_and_the_base_of_the_trial(self) -> None:
        """Ticket #70, critère 3 : `{ticket}`, `{feature}` et `{base}` valent ce que l'essai a préparé."""
        project, _, _, _ = self.launch()
        (call,) = project.calls("claude")
        self.assertIn("Le ticket de l'essai est le #12.", call["args"])
        self.assertEqual(call["args"][-1], "/forge:feature-build F-9999 --base e2e/essai1 --max 1")

    def test_the_plugin_option_names_another_plugin_to_try(self) -> None:
        """Ticket #70, critère 3 : `--plugin` désigne le plugin à essayer, celui d'un autre arbre par exemple."""
        project, _, _, _ = self.launch("--plugin", "/un/autre/plugin")
        (call,) = project.calls("claude")
        self.assertEqual(call["args"][call["args"].index("--plugin-dir") + 1], "/un/autre/plugin")

    def test_the_launch_is_bounded_by_the_launcher_of_ticket_66(self) -> None:
        """Ticket #70, critère 3 : un `claude` qui dépasse le délai est tué par le lanceur borné : `FAIL` à `lancement`."""
        _, code, out, _ = self.launch("--timeout", "1", claude=[{"has": ["-p"], "sleep": 20}])
        self.assertEqual(code, 1)
        self.assertRegex(out, r"(?m)^ETAPE: lancement$")
        self.assertIn("délai", out)

    def test_the_bound_comes_from_the_key_run_limits_when_no_option_is_given(self) -> None:
        """Ticket #70, critère 3 : sans option, la borne est celle de la clé `run-limits` (ici 1 s)."""
        _, code, out, _ = self.launch(keys={**KEYS, "run-limits": "500 | 1"}, claude=[{"has": ["-p"], "sleep": 20}])
        self.assertEqual(code, 1)
        self.assertIn("délai", out)

    def test_the_key_e2e_run_limits_bounds_the_launch_and_wins_over_run_limits(self) -> None:
        """Ticket #359, A1 : `e2e-run-limits` (ici 1 s) borne le lancement, `run-limits` (60 s) ne compte pas."""
        keys = {**KEYS, "run-limits": "500 | 60", "e2e-run-limits": "500 | 1"}
        _, code, out, _ = self.launch(keys=keys, claude=[{"has": ["-p"], "sleep": 5}])
        self.assertEqual(code, 1)
        self.assertRegex(out, r"(?m)^ETAPE: lancement$")
        self.assertIn("délai", out)

    def test_a_wider_e2e_run_limits_lets_a_launch_through_that_run_limits_would_kill(self) -> None:
        """Ticket #359, A1 : `run-limits` à 1 s tuerait ce lancement de 3 s ; `e2e-run-limits` à 60 s le laisse finir."""
        keys = {**KEYS, "run-limits": "500 | 1", "e2e-run-limits": "500 | 60"}
        _, code, out, _ = self.launch(keys=keys, claude=[{"has": ["-p"], "sleep": 3}])
        self.assertEqual(code, 0, out)
        self.assertIn("RESULTAT: PASS", out)

    def test_the_options_win_over_e2e_run_limits(self) -> None:
        """Ticket #359, A1 : `--timeout 60` l'emporte sur le délai de `e2e-run-limits` (1 s), dont la mémoire borne le reste.

        Sans `run-limits`, seule la clé `e2e-run-limits` fournit la mémoire : l'option de délai complète la
        clé au lieu de la contredire, et le lancement de 3 s passe sous le délai de l'option, non celui de la clé.
        """
        keys = {name: value for name, value in KEYS.items() if name != "run-limits"}
        keys["e2e-run-limits"] = "500 | 1"
        _, code, out, _ = self.launch("--timeout", "60", keys=keys, claude=[{"has": ["-p"], "sleep": 3}])
        self.assertEqual(code, 0, out)
        self.assertIn("RESULTAT: PASS", out)

    def test_an_option_wins_part_by_part_the_other_part_comes_from_e2e_run_limits(self) -> None:
        """Ticket #359, A1 : `--memory-mb` seul laisse le délai de `e2e-run-limits` (1 s) tuer le lancement."""
        keys = {**KEYS, "run-limits": "500 | 60", "e2e-run-limits": "500 | 1"}
        _, code, out, _ = self.launch("--memory-mb", "700", keys=keys, claude=[{"has": ["-p"], "sleep": 5}])
        self.assertEqual(code, 1)
        self.assertIn("délai", out)

    def test_e2e_run_limits_alone_bounds_the_launch_when_run_limits_is_absent(self) -> None:
        """Ticket #359, A1 : sans `run-limits`, `e2e-run-limits` borne le lancement : pas de « sans objet »."""
        keys = {name: value for name, value in KEYS.items() if name != "run-limits"}
        _, code, out, _ = self.launch(keys={**keys, "e2e-run-limits": "500 | 60"})
        self.assertEqual(code, 0, out)
        self.assertIn("RESULTAT: PASS", out)

    def test_a_relative_projet_is_resolved_before_the_launch_runs_in_the_clone(self) -> None:
        """Ticket #359, A3 : `--projet` relatif ne fait pas lire au lanceur l'`usine.md` minimale du clone."""
        project = Project(self, KEYS, scenario())
        self.chdir(project.root.parent)
        code, out, _ = project.run("--projet", project.root.name)
        self.assertEqual(code, 0, out)
        self.assertIn("RESULTAT: PASS", out)

    def test_a_relative_usine_is_resolved_before_the_launch_runs_in_the_clone(self) -> None:
        """Ticket #359, A3 : `--usine` relatif désigne le fichier du projet, pas celui du clone."""
        project = Project(self, KEYS, scenario())
        self.chdir(project.root)
        code, out, _ = project.run("--usine", "docs/agents/usine.md")
        self.assertEqual(code, 0, out)
        self.assertIn("RESULTAT: PASS", out)

    def test_a_relative_plugin_is_resolved_before_the_launch_runs_in_the_clone(self) -> None:
        """Ticket #359, A3 : `--plugin` relatif, cité par `{plugin}`, désigne le même dossier dans le clone."""
        project = Project(self, KEYS, scenario())
        self.chdir(project.root)
        project.run("--plugin", "docs")
        (call,) = project.calls("claude")
        given = call["args"][call["args"].index("--plugin-dir") + 1]
        self.assertTrue(Path(given).is_absolute(), given)
        self.assertEqual(os.path.realpath(given), os.path.realpath(project.root / "docs"))

    def test_a_claude_that_fails_is_a_fail_at_lancement_with_its_code(self) -> None:
        """Ticket #70, critère 3 : un `claude` qui sort en 3 est `FAIL` à `lancement`, avec le code."""
        _, code, out, _ = self.launch(claude=[{"has": ["-p"], "code": 3, "stderr": "budget épuisé"}])
        self.assertEqual(code, 1)
        self.assertRegex(out, r"(?m)^ETAPE: lancement$")
        self.assertIn("3", out)
        self.assertIn("budget épuisé", out)

    def test_a_claude_that_is_not_installed_is_a_fail_at_lancement(self) -> None:
        """Ticket #70, critère 3 : sans `claude` sur le `PATH`, `FAIL` à `lancement`, commande introuvable."""
        project = Project(self, KEYS, scenario())
        (project.bin / "claude").unlink()
        code, out, _ = project.run()
        self.assertEqual(code, 1)
        self.assertRegex(out, r"(?m)^ETAPE: lancement$")
        self.assertIn("introuvable", out)

    def test_a_post_out_of_budget_creates_nothing_and_is_a_fail_at_budget(self) -> None:
        """Ticket #70, critère 3 : hors du budget du poste (`run-budget`), rien n'est créé : `FAIL` à `budget`."""
        project, code, out, _ = self.launch(keys={**KEYS, "run-budget": "99999999 | 1000 | 2 | 0"})
        self.assertEqual(code, 1)
        self.assertRegex(out, r"(?m)^ETAPE: budget$")
        self.assertEqual((project.calls("gh"), project.calls("claude")), ([], []))
        self.assertEqual([call for call in project.calls("git") if "push" in call["args"]], [])


@posix_only
class Result(unittest.TestCase):
    def trial(self, *options: str, **changes: list[dict]) -> tuple[Project, int, str]:
        project = Project(self, KEYS, scenario(**changes))
        code, out, _ = project.run(*options)
        return project, code, out

    def assert_fail_at(self, out: str, stage: str, *words: str) -> None:
        self.assertRegex(out, r"(?m)^RESULTAT: FAIL$")
        self.assertRegex(out, rf"(?m)^ETAPE: {stage}$")
        self.assertNotIn("PASS", out)
        for word in words:
            self.assertIn(word, out)

    def test_an_open_pull_request_that_cites_the_ticket_with_green_checks_is_a_pass(self) -> None:
        """Ticket #70, critère 4 : une PR ouverte qui cite le ticket, aux checks verts, est `PASS`, avec la tête essayée."""
        _, code, out = self.trial()
        self.assertEqual(code, 0)
        self.assertRegex(out, r"(?m)^RESULTAT: PASS$")
        self.assertRegex(out, r"(?m)^TETE: 0123abc$")
        self.assertRegex(out, r"(?m)^PR: #13$")
        self.assertRegex(out, r"(?m)^TICKET: #12$")
        self.assertNotIn("FAIL", out)

    def test_a_merged_pull_request_is_a_pass_too(self) -> None:
        """Ticket #70, critère 4 : `forge:qc` fusionne sur ACCEPT : une PR citée et fusionnée vaut une PR ouverte."""
        _, code, out = self.trial(gh=[{"has": ["pr", "list"], "stdout": prs(pr(state="MERGED"))}])
        self.assertEqual(code, 0)
        self.assertRegex(out, r"(?m)^RESULTAT: PASS$")

    def test_the_pull_requests_are_looked_up_by_the_base_branch_of_the_trial(self) -> None:
        """Ticket #70, critère 4 : les PR de l'essai sont celles qui visent sa branche de base, ouvertes ou non."""
        project, _, _ = self.trial()
        listings = [c["args"] for c in project.calls("gh") if c["args"][:2] == ["pr", "list"]]
        self.assertEqual(len(listings), 2, "une lecture pour le résultat, une pour le nettoyage")
        for call in listings:
            self.assertEqual(call[call.index("--base") + 1], "e2e/essai1")
            self.assertEqual(call[call.index("--state") + 1], "all")

    def test_no_pull_request_is_a_fail_at_pr(self) -> None:
        """Ticket #70, critère 4 : aucune PR vers la base de l'essai : `FAIL` à l'étape `pr`."""
        _, code, out = self.trial(gh=[{"has": ["pr", "list"], "stdout": "[]"}])
        self.assertEqual(code, 1)
        self.assert_fail_at(out, "pr", "e2e/essai1")

    def test_a_pull_request_closed_without_a_merge_is_a_fail_at_pr(self) -> None:
        """Ticket #70, critère 4 : une PR fermée sans fusion n'est pas une PR ouverte : `FAIL` à `pr`."""
        _, code, out = self.trial(gh=[{"has": ["pr", "list"], "stdout": prs(pr(state="CLOSED"))}])
        self.assertEqual(code, 1)
        self.assert_fail_at(out, "pr", "#13")

    def test_a_pull_request_that_does_not_cite_the_ticket_is_a_fail_at_citation(self) -> None:
        """Ticket #70, critère 4 : une PR qui ne cite pas le ticket : `FAIL` à `citation`, `#123` n'est pas `#12`."""
        for body in ("rien", "Closes #99", "Closes #123", "Closes #1"):
            with self.subTest(body=body):
                _, code, out = self.trial(gh=[{"has": ["pr", "list"], "stdout": prs(pr(body=body))}])
                self.assertEqual(code, 1)
                self.assert_fail_at(out, "citation", "#13")

    def test_the_title_can_cite_the_ticket(self) -> None:
        """Ticket #70, critère 4 : la citation se lit dans le corps ou dans le titre."""
        cited = {**pr(body=""), "title": "feat: écrire le fichier (Refs #12)"}
        _, code, out = self.trial(gh=[{"has": ["pr", "list"], "stdout": prs(cited)}])
        self.assertEqual(code, 0)
        self.assertRegex(out, r"(?m)^RESULTAT: PASS$")

    def test_the_latest_pull_request_that_cites_the_ticket_is_the_one_judged(self) -> None:
        """Ticket #70, critère 4 : plusieurs PR citent le ticket (tours de correction) : la dernière est jugée."""
        found = prs(pr(number=13, state="CLOSED"), pr(number=14), pr(number=15, body="rien"))
        project, code, out = self.trial(gh=[{"has": ["pr", "list"], "stdout": found}])
        self.assertEqual(code, 0)
        self.assertRegex(out, r"(?m)^PR: #14$")
        (call,) = [c["args"] for c in project.calls("gh") if c["args"][:2] == ["pr", "checks"]]
        self.assertEqual(call[2], "14")

    def test_a_red_check_is_a_fail_at_checks_and_names_the_check(self) -> None:
        """Ticket #70, critère 4 : un check rouge : `FAIL` à `checks`, avec son nom."""
        red = checks(("tests", "pass"), ("lint", "fail"))
        _, code, out = self.trial(gh=[{"has": ["pr", "checks"], "stdout": red, "code": 1}])
        self.assertEqual(code, 1)
        self.assert_fail_at(out, "checks", "lint")

    def test_a_skipped_check_is_not_red(self) -> None:
        """Ticket #70, critère 4 : un check sauté ne fait pas échouer l'essai."""
        skipped = checks(("tests", "pass"), ("deploy", "skipping"))
        _, code, out = self.trial(gh=[{"has": ["pr", "checks"], "stdout": skipped}])
        self.assertEqual(code, 0)

    def test_a_pull_request_without_any_check_is_a_fail_at_checks(self) -> None:
        """Ticket #70, critère 4 : sans aucun check, rien ne dit que la PR est verte : `FAIL` à `checks`."""
        for answer in (
            {"has": ["pr", "checks"], "stdout": "[]"},
            {"has": ["pr", "checks"], "stdout": "", "stderr": "no checks reported on the 'feat/essai' branch", "code": 1},
        ):
            with self.subTest(answer=answer):
                _, code, out = self.trial(gh=[answer])
                self.assertEqual(code, 1)
                self.assert_fail_at(out, "checks", "aucun check")

    def test_pending_checks_are_awaited_until_they_pass(self) -> None:
        """Ticket #70, critère 4 : des checks en cours sont attendus (`--wait-checks`), puis lus."""
        running = checks(("tests", "pending"), ("lint", "pass"))
        done = checks(("tests", "pass"), ("lint", "pass"))
        project, code, out = self.trial(
            "--wait-checks", "30", "--poll-seconds", "0.05",
            gh=[{"has": ["pr", "checks"], "stdout": [running, running, done], "code": [8, 8, 0]}],
        )
        self.assertEqual(code, 0)
        self.assertRegex(out, r"(?m)^RESULTAT: PASS$")
        self.assertEqual(len([c for c in project.calls("gh") if c["args"][:2] == ["pr", "checks"]]), 3)

    def test_pending_checks_that_do_not_finish_in_time_are_a_fail_at_checks(self) -> None:
        """Ticket #70, critère 4 : des checks encore en cours après l'attente : `FAIL` à `checks`."""
        running = checks(("tests", "pending"))
        _, code, out = self.trial("--wait-checks", "0", gh=[{"has": ["pr", "checks"], "stdout": running}])
        self.assertEqual(code, 1)
        self.assert_fail_at(out, "checks", "en cours", "tests")

    def test_a_head_with_uncommitted_changes_says_so(self) -> None:
        """Ticket #70, critère 4 : la tête essayée dit quand l'arbre du plugin a des changements non commités."""
        _, _, out = self.trial(git=[{"has": ["status", "--porcelain"], "stdout": " M plugins/forge/x.py\n"}])
        self.assertRegex(out, r"(?m)^TETE: 0123abc \(arbre modifié\)$")

    def test_a_fail_carries_the_head_too(self) -> None:
        """Ticket #70, critère 4 : un `FAIL` porte aussi la tête essayée, que la PR de version recopie."""
        _, _, out = self.trial(gh=[{"has": ["pr", "list"], "stdout": "[]"}])
        self.assertRegex(out, r"(?m)^TETE: 0123abc$")


class ReleaseInstruction(unittest.TestCase):
    COMMAND_LINE = "uv run --no-project --quiet python plugins/forge/scripts/e2e_trial.py"

    def steps(self) -> str:
        text = (support.REPO_ROOT / "docs" / "contribuer.md").read_text(encoding="utf-8")
        return text.split("Publier une version :", 1)[1].split("## Le dépôt", 1)[0]

    def test_the_release_procedure_gives_the_command_that_runs_the_script(self) -> None:
        """Ticket #70, critère 6 : la consigne cite la commande exacte, et cette commande lance bien le script.

        Elle est lancée telle quelle depuis la racine (`uv run ... python` remplacé par l'interpréteur du test),
        sur un projet sans `usine.md` : le script lit lui-même ses trois clés et répond `SANS-OBJET` pour chacune,
        sans rien créer.
        """
        blocks = re.findall(r"```sh\n(.*?)```", self.steps(), re.DOTALL)
        command = next((line.strip() for block in blocks for line in block.splitlines() if "e2e_trial.py" in line), "")
        self.assertEqual(command, self.COMMAND_LINE)
        prefix = "uv run --no-project --quiet python "
        self.assertTrue(command.startswith(prefix))
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / "home"
            home.mkdir()
            project = Path(folder) / "projet"
            project.mkdir()
            env = {
                "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                "HOME": str(home),
                "USERPROFILE": str(home),
                "TMPDIR": str(home),
                "TEMP": str(home),
                # La page de code d'un tube sous Windows : sans la sortie en UTF-8 du script, ses accents
                # ne se lisent pas (échec vu en CI sous Windows, rejoué ici sous Linux).
                "PYTHONIOENCODING": "cp1252",
            }
            done = subprocess.run(
                [sys.executable, *command.removeprefix(prefix).split(), "--projet", str(project)],
                cwd=support.REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
            )
        self.assertEqual(done.returncode, 0, done.stderr)
        for key in ("e2e-repo", "e2e-command", "e2e-budget-usd"):
            self.assertIn(f"SANS-OBJET (clé `{key}` absente)", done.stdout)
        self.assertNotIn("PASS", done.stdout)

    def test_the_release_procedure_says_what_the_key_e2e_command_is(self) -> None:
        """Ticket #70, critère 6 : la clé est la ligne `claude` lancée dans le clone, que la consigne ne fait pas lancer."""
        steps = " ".join(self.steps().split())
        self.assertIn("la clé `e2e-command` est la ligne `claude` que le script lance dans le clone", steps)
        for marker in ("{plugin}", "{budget}"):
            self.assertIn(marker, steps)
        self.assertNotIn("lancer cette commande", steps)

    def test_the_release_procedure_copies_the_result_the_script_prints(self) -> None:
        """Ticket #70, critère 6 : la PR de version recopie les lignes que le script imprime, et le dit sans objet."""
        steps = self.steps()
        for word in ("RESULTAT", "TETE", "ETAPE", "RAISON", "chore(release)"):
            with self.subTest(word=word):
                self.assertIn(word, steps)
        self.assertIn("sans objet (clé `e2e-command` absente)", steps)

    def test_the_script_is_listed_in_the_tree_of_the_plugin(self) -> None:
        """Ticket #70, critère 6 : l'arbre de `docs/contribuer.md` cite le script."""
        text = (support.REPO_ROOT / "docs" / "contribuer.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^\s+scripts/e2e_trial\.py\s+\S")


def deleted(project: Project) -> list[str]:
    """The branches the trial deleted, from the `gh api -X DELETE` calls."""
    refs = [
        word.split("/git/refs/heads/", 1)[1]
        for call in project.calls("gh")
        if "DELETE" in call["args"]
        for word in call["args"]
        if "/git/refs/heads/" in word
    ]
    return sorted(refs)


def closed(project: Project, kind: str) -> list[str]:
    """The numbers of the pull requests (`pr`) or issues (`issue`) the trial closed."""
    return [call["args"][2] for call in project.calls("gh") if call["args"][:2] == [kind, "close"]]


@posix_only
class Cleanup(unittest.TestCase):
    def trial(self, *options: str, **changes: list[dict]) -> tuple[Project, int, str]:
        project = Project(self, KEYS, scenario(**changes))
        code, out, _ = project.run(*options)
        return project, code, out

    def test_the_open_pull_request_the_ticket_and_both_branches_are_cleaned_up_by_number(self) -> None:
        """Ticket #70, critère 5 : après l'essai, la PR ouverte et le ticket sont fermés, leur branche et la base supprimées."""
        project, code, out = self.trial()
        self.assertEqual(code, 0)
        self.assertEqual(closed(project, "pr"), ["13"])
        self.assertEqual(closed(project, "issue"), ["12"])
        self.assertEqual(deleted(project), ["e2e/essai1", "feat/essai"])
        self.assertRegex(out, r"(?m)^NETTOYAGE: .*#13")
        self.assertRegex(out, r"(?m)^NETTOYAGE: .*#12")

    def test_a_merged_pull_request_is_not_closed_but_its_branch_is_deleted(self) -> None:
        """Ticket #70, critère 5 : une PR fusionnée n'est pas refermée ; sa branche part avec l'essai."""
        project, _, _ = self.trial(gh=[{"has": ["pr", "list"], "stdout": prs(pr(state="MERGED"))}])
        self.assertEqual(closed(project, "pr"), [])
        self.assertEqual(deleted(project), ["e2e/essai1", "feat/essai"])

    def test_a_failed_trial_is_cleaned_up_too_and_finds_the_pull_request_the_run_left(self) -> None:
        """Ticket #70, critère 5 : un `claude` en échec laisse peut-être une PR : elle est fermée avec le ticket."""
        project, code, out = self.trial(claude=[{"has": ["-p"], "code": 3}])
        self.assertEqual(code, 1)
        self.assertRegex(out, r"(?m)^ETAPE: lancement$")
        self.assertEqual(closed(project, "pr"), ["13"])
        self.assertEqual(closed(project, "issue"), ["12"])
        self.assertIn("e2e/essai1", deleted(project))

    def test_nothing_is_cleaned_when_nothing_was_created(self) -> None:
        """Ticket #70, critère 5 : un clone refusé ne crée rien : aucun geste de nettoyage."""
        project, _, _ = self.trial(gh=[{"has": ["repo", "clone"], "code": 1, "stderr": "not found"}])
        gestures = [call for call in project.calls("gh") if call["args"][:2] != ["repo", "clone"]]
        self.assertEqual(gestures, [])

    def test_a_base_branch_that_was_never_pushed_is_not_deleted(self) -> None:
        """Ticket #70, critère 5 : si la poussée a échoué, le ticket est fermé et aucune branche n'est supprimée."""
        project, _, out = self.trial(git=[{"has": ["push"], "code": 1, "stderr": "denied"}])
        self.assertRegex(out, r"(?m)^ETAPE: preparation$")
        self.assertEqual(closed(project, "issue"), ["12"])
        self.assertEqual(deleted(project), [])

    def test_only_the_branches_of_the_trial_pull_requests_are_deleted_never_the_default_branch(self) -> None:
        """Ticket #70, critère 5 : une PR dont la tête est la branche par défaut ne fait supprimer que la base de l'essai."""
        for head in ("main", "master", "e2e/essai1"):
            with self.subTest(head=head):
                project, _, _ = self.trial(gh=[{"has": ["pr", "list"], "stdout": prs(pr(branch=head))}])
                self.assertEqual(deleted(project), ["e2e/essai1"])

    def test_the_default_branch_read_in_the_clone_is_never_deleted(self) -> None:
        """Ticket #70, critère 5 : la branche par défaut du clone, quel que soit son nom, n'est jamais supprimée."""
        project, _, _ = self.trial(
            git=[{"has": ["rev-parse", "--abbrev-ref"], "stdout": "develop\n"}],
            gh=[{"has": ["pr", "list"], "stdout": prs(pr(branch="develop"))}],
        )
        self.assertEqual(deleted(project), ["e2e/essai1"])

    def test_a_branch_already_gone_is_not_a_failure(self) -> None:
        """Ticket #70, critère 5 : une branche déjà supprimée (fusion, suppression automatique) n'est pas un échec."""
        gone = {"has": ["api"], "code": 1, "stderr": "Reference does not exist (HTTP 422)"}
        _, code, out = self.trial(gh=[gone])
        self.assertEqual(code, 0)
        self.assertRegex(out, r"(?m)^RESULTAT: PASS$")

    def test_a_cleanup_that_fails_turns_a_pass_into_a_fail_at_nettoyage_and_goes_on(self) -> None:
        """Ticket #70, critère 5 : un nettoyage en échec est dit (`ETAPE: nettoyage`) et le reste est tout de même fait."""
        project, code, out = self.trial(gh=[{"has": ["issue", "close"], "code": 1, "stderr": "forbidden"}])
        self.assertEqual(code, 1)
        self.assertRegex(out, r"(?m)^RESULTAT: FAIL$")
        self.assertRegex(out, r"(?m)^ETAPE: nettoyage$")
        self.assertRegex(out, r"(?m)^NETTOYAGE: ECHEC .*forbidden")
        self.assertIn("e2e/essai1", deleted(project))

    def test_a_cleanup_that_fails_does_not_hide_the_step_that_failed_first(self) -> None:
        """Ticket #70, critère 5 : l'étape qui a manqué reste celle que le résultat nomme."""
        _, _, out = self.trial(
            gh=[{"has": ["pr", "list"], "stdout": "[]"}, {"has": ["issue", "close"], "code": 1, "stderr": "forbidden"}]
        )
        self.assertRegex(out, r"(?m)^ETAPE: pr$")
        self.assertRegex(out, r"(?m)^NETTOYAGE: ECHEC .*forbidden")

    def test_the_cleanup_never_touches_anything_the_trial_did_not_name(self) -> None:
        """Ticket #70, critère 5 : chaque fermeture vise le ticket ou une PR de l'essai, chaque suppression une branche de l'essai."""
        project, _, _ = self.trial()
        for call in project.calls("gh"):
            args = call["args"]
            if args[1:2] == ["close"]:
                self.assertIn(args[2], ("12", "13"))
            if "DELETE" in args:
                self.assertTrue(any(word.startswith(f"repos/{REPO}/git/refs/heads/") for word in args), args)


if __name__ == "__main__":
    unittest.main()
