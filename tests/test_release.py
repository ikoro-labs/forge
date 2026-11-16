"""release.py : le déclencheur et les conditions de la publication continue (ticket #71).

Les tests simulent `gh` par des réponses fictives, `git` par des dépôts jetables dans un dossier
temporaire, et l'essai de bout en bout par un faux script : rien ne publie, ne pose de tag ni ne
lance le vrai essai.
"""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import support  # noqa: F401  met le plugin sur le chemin d'import
from release import main
from test_factory_slo import USINE, World, isolate

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "vide"))
        self.world = World(Path(self.tmp.name))
        self.world.answers = {"repo view": {"nameWithOwner": "o/r", "defaultBranchRef": {"name": "main"}}}

    def configure(self, *lines: str) -> None:
        text = USINE + "".join(f"- {line}\n" for line in lines)
        (self.world.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def run_main(self, command: str, *extra: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([command, str(self.world.root), *extra], run=self.world.runner, now=NOW)
        return code, out.getvalue(), err.getvalue()


class Trigger(Base):
    def test_an_absent_key_is_sans_objet_and_never_publishes(self) -> None:
        """Ticket #71 : sans `release-trigger`, « sans objet », aucune publication par l'agent."""
        code, out, _ = self.run_main("trigger")
        self.assertEqual(code, 0)
        self.assertIn("DECLENCHEUR: sans objet (clé `release-trigger` absente)", out)

    def test_a_key_that_cannot_be_read_fails_and_guesses_nothing(self) -> None:
        """Ticket #71 : une valeur illisible, répétée ou à moitié écrite fait échouer la commande."""
        for value in ("dix | 7 j", "0 | 7 j", "10 | 7", "10 | 0 j", "10", "10 |"):
            with self.subTest(value=value):
                self.configure(f"`release-trigger` : `{value}`")
                code, out, err = self.run_main("trigger")
                self.assertEqual(code, 2)
                self.assertIn("release-trigger", err)
                self.assertNotIn("DECLENCHEUR", out)
        self.configure("`release-trigger` : `10 | 7 j`", "`release-trigger` : `5 | 2 j`")
        self.assertEqual(self.run_main("trigger")[0], 2)


if __name__ == "__main__":
    unittest.main()
