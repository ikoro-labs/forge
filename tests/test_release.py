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
from test_factory_slo import USINE, World, isolate, pr

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
    def merges(self, *dates: str, released: int = 0) -> None:
        """Des PR fusionnées aux dates données, dont les `released` premières sont dans un tag de version."""
        listed = []
        for index, merged in enumerate(dates):
            oid = self.world.commit(f"feat: {index}", merged)
            listed.append(pr(index + 1, merged, state="MERGED", mergedAt=merged, mergeCommit={"oid": oid}))
            if index == released - 1:
                self.world.git("tag", "-a", "-m", "v", "forge--v1.0.0", oid, when=merged)
        self.world.answers["pr list"] = listed

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

    def test_the_number_of_merges_waiting_for_a_tag_triggers_a_version(self) -> None:
        """Ticket #71 : N fusions hors de tout tag de version déclenchent, la borne comprise."""
        self.configure("`release-trigger` : `3 | 30 j`")
        self.merges("2026-11-10T10:00:00Z", "2026-11-12T10:00:00Z", "2026-11-13T10:00:00Z",
                    "2026-11-14T10:00:00Z", released=1)
        code, out, _ = self.run_main("trigger")
        self.assertEqual(code, 0)
        self.assertIn("DECLENCHEUR: atteint par le nombre : 3 fusions en attente pour 3 demandées", out)

    def test_below_both_bounds_nothing_is_due(self) -> None:
        """Ticket #71 : deux fusions de 2 jours, pour 3 fusions ou 7 jours : pas de version."""
        self.configure("`release-trigger` : `3 | 7 j`")
        self.merges("2026-11-14T10:00:00Z", "2026-11-14T11:00:00Z")
        _, out, _ = self.run_main("trigger")
        self.assertIn("DECLENCHEUR: non atteint : 2 fusions en attente pour 3 demandées, la plus ancienne depuis 2 j pour 7 j", out)

    def test_the_oldest_waiting_merge_triggers_by_delay_even_with_few_merges(self) -> None:
        """Ticket #71 : une seule fusion qui attend depuis plus que le délai déclenche, au délai près."""
        self.configure("`release-trigger` : `10 | 7 j`")
        self.merges("2026-11-09T12:00:00Z")
        code, out, _ = self.run_main("trigger")
        self.assertEqual(code, 0)
        self.assertIn("DECLENCHEUR: atteint par le délai : la plus ancienne attend depuis 7 j pour 7 j", out)
        self.merges("2026-11-09T12:00:01Z")
        self.assertIn("DECLENCHEUR: non atteint", self.run_main("trigger")[1])

    def test_nothing_waiting_never_triggers(self) -> None:
        """Ticket #71 : tout est déjà dans un tag, rien à publier, quel que soit le temps écoulé."""
        self.configure("`release-trigger` : `1 | 1 h`")
        self.merges("2026-10-01T10:00:00Z", released=1)
        _, out, _ = self.run_main("trigger")
        self.assertIn("DECLENCHEUR: non atteint : aucune fusion n'attend de version", out)

    def test_only_a_tag_of_the_release_tag_pattern_publishes_a_merge(self) -> None:
        """Ticket #71 : le motif du tag vient de la clé `release-tag` ; un autre tag ne publie rien."""
        self.configure("`release-trigger` : `1 | 30 j`")
        self.merges("2026-11-14T10:00:00Z")
        oid = self.world.git("rev-parse", "HEAD")
        self.world.git("tag", "-a", "-m", "v", "autre-v9", oid)
        self.assertIn("atteint par le nombre : 1 fusion en attente pour 1 demandée", self.run_main("trigger")[1])
        self.world.git("tag", "-a", "-m", "v", "forge--v1.0.1", oid)
        self.assertIn("non atteint : aucune fusion", self.run_main("trigger")[1])

    def test_without_the_release_tag_key_the_count_is_sans_objet(self) -> None:
        """Ticket #71 : sans `release-tag`, aucun motif de tag à lire : « sans objet », rien ne se déclenche."""
        (self.world.root / "docs" / "agents" / "usine.md").write_text(
            "- `release-trigger` : `1 | 1 h`\n", encoding="utf-8")
        self.merges("2026-11-14T10:00:00Z")
        code, out, _ = self.run_main("trigger")
        self.assertEqual(code, 0)
        self.assertIn("DECLENCHEUR: sans objet (clé `release-tag` absente)", out)


if __name__ == "__main__":
    unittest.main()
