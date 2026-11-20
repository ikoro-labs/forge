"""Ticket #266 : le modèle lance les skills de la chaîne quand le projet a ouvert l'autonomie.

La clé `agent-autonomy` de `usine.md` ouvre l'autonomie ; sans elle, le skill rend l'étape à l'humain.
`feature-accept` reste tapé par un humain, `release` garde la clé `release-trigger`.
"""

import unittest
from pathlib import Path

import support
from test_plugin_content import frontmatter
from usine import parse

SKILLS = support.PLUGIN / "skills"
TEMPLATE = support.PLUGIN / "templates" / "usine.md"
RULE = support.PLUGIN / "autonomie.md"
PROTOCOLE = support.PLUGIN / "templates" / "features" / "protocole.md"
HUMAN_ONLY = ("feature-accept", "release")
# The twelve skills that carried `disable-model-invocation: true` before #266, less the two above.
OPENED = (
    "audit-jetons", "feature-brainstorm", "feature-design", "feature-frame", "feature-guide",
    "feature-new", "feature-spec", "feature-status", "improve-codebase-architecture", "slo",
)


def prose(path: Path) -> str:
    """The file on one line per paragraph, so a sentence wrapped by the editor still matches."""
    return " ".join(path.read_text(encoding="utf-8").split())


class OpeningTheSkills(unittest.TestCase):
    def test_each_skill_but_two_can_be_started_by_the_model(self) -> None:
        """Ticket #266 A1 : dix des douze skills perdent le drapeau qui interdit le modèle."""
        for name in OPENED:
            with self.subTest(skill=name):
                self.assertNotIn("disable-model-invocation", frontmatter(SKILLS / name / "SKILL.md"))

    def test_each_opened_skill_applies_the_rule_before_its_steps(self) -> None:
        """Ticket #266 A1.1 : le skill lu seul renvoie à la règle qui rend l'étape à l'humain, clé absente."""
        for name in OPENED:
            with self.subTest(skill=name):
                self.assertIn("${CLAUDE_PLUGIN_ROOT}/autonomie.md", prose(SKILLS / name / "SKILL.md"))

    def test_a_model_start_without_the_key_hands_the_step_to_the_human(self) -> None:
        """Ticket #266 A1.1 : feature-frame sans la clé, rien n'est écrit et l'humain reçoit la commande."""
        text = prose(RULE)
        self.assertIn("clé `agent-autonomy`", text)
        self.assertRegex(text, r"sans objet \(clé `agent-autonomy` absente\).{0,300}N'écris rien")
        self.assertRegex(text, r"rends l'étape à l'humain.{0,200}commande")

    def test_a_command_typed_by_the_human_runs_whatever_the_key(self) -> None:
        """Ticket #266 A1 : la clé ne retire rien à l'humain, qui tape la commande."""
        self.assertRegex(prose(RULE), r"`<command-name>`.{0,300}sans lire la clé")

    def test_the_key_is_documented_in_the_template_and_read_as_a_line(self) -> None:
        """Ticket #266 A1 : le gabarit documente la clé, et sa ligne d'exemple se lit comme une entrée."""
        self.assertEqual(parse(TEMPLATE.read_text(encoding="utf-8")).get("agent-autonomy"), ["on"])


class QuestionsGoToTheDecisionAgents(unittest.TestCase):
    def test_a_question_goes_to_the_decision_agent_before_the_human(self) -> None:
        """Ticket #266 A2.1 : avec la clé, product-owner ou staff-engineer d'abord, la décision écrite."""
        text = prose(RULE)
        self.assertRegex(text, r"`forge:product-owner`.{0,200}`forge:staff-engineer`.{0,200}avant tout humain")
        self.assertRegex(text, r"section Décisions.{0,200}`MATRIX_CELL`")

    def test_a_reserved_cell_is_named_to_the_human(self) -> None:
        """Ticket #266 A2 : ce qu'un agent rend `RESERVED` reste à l'humain, avec la case nommée."""
        self.assertRegex(prose(RULE), r"`RESERVED`.{0,300}nomme la case")

    def test_the_protocol_applies_the_rule_to_the_questions_of_each_turn(self) -> None:
        """Ticket #266 A2 : le protocole commun renvoie à la règle à l'étape des questions."""
        self.assertRegex(prose(PROTOCOLE), r"Questionner par tours.{0,1500}autonomie\.md")


class WhatStaysWithTheHuman(unittest.TestCase):
    def test_feature_accept_and_release_keep_the_flag(self) -> None:
        """Ticket #266 A3.1 : le drapeau reste sur feature-accept et release."""
        for name in HUMAN_ONLY:
            with self.subTest(skill=name):
                self.assertEqual(frontmatter(SKILLS / name / "SKILL.md").get("disable-model-invocation"), "true")

    def test_the_rule_opens_neither_acceptance_nor_publication(self) -> None:
        """Ticket #266 A3 : la règle dit que l'autonomie n'accepte rien et que `release` garde `release-trigger`."""
        text = prose(RULE)
        self.assertRegex(text, r"`feature-accept`.{0,200}humain de la clé `accepting-human`")
        self.assertRegex(text, r"`release`.{0,200}clé `release-trigger`")


if __name__ == "__main__":
    unittest.main()
