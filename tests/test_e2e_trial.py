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
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from e2e_trial import main

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


class Project:
    """A throwaway project with its `usine.md`, and an environment isolated from the real HOME."""

    def __init__(self, test: unittest.TestCase, keys: dict[str, str] | None = None) -> None:
        folder = tempfile.TemporaryDirectory()
        test.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / "projet"
        (self.root / "docs" / "agents").mkdir(parents=True)
        if keys is not None:
            (self.root / "docs" / "agents" / "usine.md").write_text(usine_text(**keys), encoding="utf-8")
        self.home = Path(folder.name) / "home"
        self.home.mkdir()
        self.env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "TMPDIR": str(self.home),
            "TEMP": str(self.home),
        }

    def run(self, *options: str) -> tuple[int, str, str]:
        """The exit code, standard output and standard error of `main` on this project."""
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.dict(os.environ, self.env, clear=True),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = main(["--projet", str(self.root), *options])
        return code, out.getvalue(), err.getvalue()


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


if __name__ == "__main__":
    unittest.main()
