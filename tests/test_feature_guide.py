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


class SharedSupport(unittest.TestCase):
    def test_the_template_documents_the_key_of_the_shared_support(self) -> None:
        """No F-NNNN: ticket #96, A3: la clé shared-doc est documentée dans le gabarit de usine.md."""
        template = read(support.PLUGIN / "templates" / "usine.md")
        self.assertIn("- `shared-doc` : `<", template)
        self.assertIn("Le fichier du dépôt reste la référence", template)
        self.assertIn("sans objet (clé `shared-doc` absente)", template)
        self.assertIn("Forge ne câble aucun service", template)

    def test_the_skill_uses_the_shared_support_only_when_the_key_names_one(self) -> None:
        """No F-NNNN: ticket #96, A3: sans la clé, sans objet et seul le fichier sert ; avec elle, le fichier reste la référence."""
        skill = read(SKILL)
        self.assertIn("sans objet (clé `shared-doc` absente)", skill)
        self.assertIn("Seul le fichier du dépôt sert", skill)
        self.assertIn("Le fichier du dépôt reste la référence", skill)
        self.assertIn("recopie dans le fichier", skill)
        self.assertNotIn("valeur par défaut :", skill)


class Validation(unittest.TestCase):
    def test_an_agent_proposal_stays_marked_until_the_expert_validates_it(self) -> None:
        """No F-NNNN: ticket #96, A4: chaque proposition de l'agent reste marquée `proposé` tant que l'expert ne l'a pas validée."""
        skill = read(SKILL)
        template = read(support.PLUGIN / "templates" / "features" / "conception.md")
        self.assertIn("Chaque rédaction que tu écris porte l'état `proposé`", skill)
        self.assertIn("jusqu'au « oui » de l'expert", skill)
        self.assertIn("Une correction de l'expert réécrit la ligne", skill)
        self.assertIn("Seul le « oui » de l'expert le pose", template)

    def test_a_requirement_never_enters_validated_without_the_expert(self) -> None:
        """No F-NNNN: ticket #96, A4: une exigence n'entre jamais `validé` sans l'expert : son nom et la date."""
        skill = read(SKILL)
        self.assertIn("Une exigence n'entre jamais `validé` sans l'expert", skill)
        self.assertIn("son nom (clé `source-author`) et la date", skill)
        self.assertIn("Un silence n'est pas un accord", skill)
        self.assertIn("ni l'humain de la clé `accepting-human` ni un agent ne le remplacent", skill)
        self.assertIn("sans objet (clé `source-author` absente)", skill)


if __name__ == "__main__":
    unittest.main()
