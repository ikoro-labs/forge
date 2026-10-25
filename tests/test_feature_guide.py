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


if __name__ == "__main__":
    unittest.main()
