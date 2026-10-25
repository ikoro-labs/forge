"""Ticket #96: a design led by guided questions with a business expert who is not a developer."""

import unittest

import support

SKILL = support.PLUGIN / "skills" / "feature-guide" / "SKILL.md"


def read(path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class Questions(unittest.TestCase):
    def test_the_skill_asks_one_question_at_a_time_in_the_words_of_the_trade(self) -> None:
        """No F-NNNN: ticket #96, A1: une question à la fois, dans les mots du métier, avec une rédaction à valider."""
        skill = read(SKILL)
        self.assertIn("Une seule question à la fois", skill)
        self.assertIn("Dans les mots du métier", skill)
        self.assertIn("jamais un terme de l'implémentation", skill)
        self.assertIn("Propose une rédaction à valider ou à corriger", skill)
        self.assertIn("jamais une page blanche", skill)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md", skill)


class LivingDocument(unittest.TestCase):
    def test_the_document_is_a_file_of_the_feature_folder_by_default(self) -> None:
        """No F-NNNN: ticket #96, A2: par défaut un fichier Markdown du dossier de la feature (clé feature-dir)."""
        skill = read(SKILL)
        template = read(support.PLUGIN / "templates" / "features" / "conception.md")
        self.assertIn("`conception.md`", skill)
        self.assertIn("dossier de la feature (clé `feature-dir`)", skill)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/templates/features/conception.md", skill)
        self.assertIn("document: conception", template)
        self.assertIn("| Identifiant | Proposition | État | Validé par | Le |", template)

    def test_the_validated_document_becomes_the_source(self) -> None:
        """No F-NNNN: ticket #96, A2: validé par l'expert, le fichier devient la source (clé product-source), en tête."""
        skill = read(SKILL)
        self.assertIn("devient la source", skill)
        self.assertIn("clé `product-source`", skill)
        self.assertIn("en tête", skill)
        self.assertIn("demande à l'humain de la clé `accepting-human`", skill)
        self.assertIn("pas avant", skill)


if __name__ == "__main__":
    unittest.main()
