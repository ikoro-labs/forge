"""Ticket #61, critère 1 : le skill `forge:incident` dit comment écrire une revue sans blâme.

Chaque phrase gardée ici est une règle de l'usine : le skill la perd, la revue d'un incident cesse
de finir sur un contrôle.
"""

import re
import unittest

import support
from test_plugin_content import frontmatter

SKILL = support.PLUGIN / "skills" / "incident" / "SKILL.md"


def prose() -> str:
    """The skill on one line per paragraph, so a sentence wrapped by the editor still matches."""
    return " ".join(SKILL.read_text(encoding="utf-8").split())


class IncidentSkill(unittest.TestCase):
    def test_the_skill_is_a_skill_named_incident(self) -> None:
        """Ticket #61, critère 1 : le skill existe, sous le nom `forge:incident`."""
        fields = frontmatter(SKILL)
        self.assertEqual(fields.get("name"), "incident")
        self.assertTrue(fields.get("description"))

    def test_it_runs_for_every_sev1_sev2_and_every_incident_of_the_factory(self) -> None:
        """Ticket #61, critère 1 : la portée du skill, dite dans sa description."""
        description = frontmatter(SKILL)["description"]
        for word in ("sev1", "sev2", "usine"):
            with self.subTest(word=word):
                self.assertIn(word, description)

    def test_it_writes_the_blameless_review_the_template_gives(self) -> None:
        """Ticket #61, critère 1 : faits datés, cause, ce qui l'a laissé passer, correctif, sans blâme."""
        text = prose()
        self.assertIn("templates/incident.md", text)
        self.assertIn("sans blâme", text)
        for word in ("faits datés", "cause", "ce qui l'a laissé passer", "classe du correctif"):
            with self.subTest(word=word):
                self.assertIn(word, text)

    def test_it_names_the_two_classes_and_what_each_one_produces(self) -> None:
        """Ticket #61, critère 1 : `mécanique` donne un ticket et son test, `jugement` un cas du jeu de référence."""
        text = prose()
        self.assertRegex(text, r"`mécanique`.{0,200}ticket.{0,120}test")
        self.assertRegex(text, r"`jugement`.{0,200}cas.{0,120}jeu de référence")

    def test_a_guideline_or_a_memory_note_alone_is_never_a_fix(self) -> None:
        """Ticket #61, critère 2 : le skill répète le refus."""
        self.assertRegex(prose(), r"consigne seule[^.]*mémoire seule[^.]*jamais un correctif")

    def test_it_runs_the_check_and_stops_on_a_refusal(self) -> None:
        """Ticket #61, critère 2 : `incident.py check` valide la revue avant le dépôt."""
        text = prose()
        self.assertIn('scripts/incident.py" check', text)
        self.assertIn("--projet", text)
        self.assertRegex(text, r"sortie non nulle[^.]*(corrige|arrête)")

    def test_it_looks_for_an_existing_control_before_proposing_a_new_one(self) -> None:
        """Ticket #61 : avant un nouveau contrôle, vérifier qu'il n'existe pas déjà (garde, script, test)."""
        self.assertRegex(prose(), r"(?i)avant de proposer un (nouveau )?contrôle[^.]*existe déjà")

    def test_without_the_key_it_says_sans_objet_and_writes_nothing(self) -> None:
        """Ticket #61, critère 4 : sans `incident-dir`, « sans objet (clé `incident-dir` absente) »."""
        text = prose()
        self.assertIn("clé `incident-dir`", text)
        self.assertIn("sans objet (clé `incident-dir` absente)", text)
        self.assertIn('scripts/incident.py" dir', text)

    def test_it_counts_the_reviews_by_class(self) -> None:
        """Ticket #61, critère 5 : le décompte par classe se lit par `factory_slo.py incidents`."""
        self.assertIn('scripts/factory_slo.py" incidents', prose())

    def test_the_fix_ticket_follows_the_rules_of_the_project_and_cites_the_review(self) -> None:
        """Ticket #61, critère 4 : le ticket de correctif cite la revue, et naît sous les règles du projet."""
        text = prose()
        self.assertRegex(text, r"ticket de correctif[^.]*cite la revue")
        self.assertRegex(text, r"`Motif :`[^.]*(admet|admis)")

    def test_it_keeps_names_and_private_notes_out_of_the_review(self) -> None:
        """Ticket #61 : un dépôt public, la revue ne nomme pas de personne et ne cite pas une mémoire privée."""
        text = prose()
        self.assertRegex(text, r"aucun nom de personne")
        self.assertRegex(text, r"mémoire privée")

    def test_the_skill_has_no_em_dash_and_names_no_project_path(self) -> None:
        """Ticket #61 : le contenu du plugin reste générique et sans tiret cadratin."""
        text = SKILL.read_text(encoding="utf-8")
        self.assertNotIn(chr(0x2014), text)
        self.assertIsNone(re.search(r"(?<![\w$/{}.-])(docs|plugins|tests)/[\w-]+", text.replace("${CLAUDE_PLUGIN_ROOT}", "")))


if __name__ == "__main__":
    unittest.main()
