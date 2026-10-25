"""Le contenu qui porte les actions du budget d'erreur : gabarit, skills, pages de docs (ticket #59)."""

import unittest

import support


def read(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


def read_doc(name: str) -> str:
    return " ".join((support.REPO_ROOT / "docs" / name).read_text(encoding="utf-8").split())


class Template(unittest.TestCase):
    def test_the_template_documents_the_key_its_actions_and_the_absent_key(self) -> None:
        """Ticket #59 : le gabarit documente `budget-action`, sans valeur par défaut."""
        template = read("templates", "usine.md")
        self.assertIn("- `budget-action` : `<", template)
        for action in ("human-merge", "feature-freeze", "alert"):
            self.assertIn(f"`{action}`", template)
        self.assertIn("sans objet (clé `budget-action` absente)", template)
        self.assertIn("`bug`", template)
        self.assertIn("`escaped-defect`", template)
        self.assertIn("24 h", template)


class Skills(unittest.TestCase):
    def test_qc_recalculates_at_the_start_and_hands_the_merge_to_the_human_when_human_merge_is_active(self) -> None:
        """Ticket #59 : `human-merge` actif, pas de fusion sur ACCEPT, `needs-your-attention` et le SLO dans `Attention`."""
        skill = read("skills", "qc", "SKILL.md")
        self.assertIn("factory_slo.py", skill)
        self.assertIn("budget", skill)
        section = skill[skill.index("## Budget d'erreur"):]
        self.assertIn("human-merge", section)
        self.assertIn("même sur ACCEPT", section)
        self.assertIn("needs-your-attention", section)
        self.assertIn("`Attention`", section)
        self.assertIn("fusionnée par l'agent : non", section)
        self.assertIn("autonomie rendue", section)
        self.assertIn("clé `budget-action` absente", section)

    def test_feature_build_recalculates_and_hands_only_bug_tickets_under_a_freeze(self) -> None:
        """Ticket #59 : `feature-freeze` actif, seuls `bug` et `escaped-defect` partent ; les autres attendent, dit au compte rendu."""
        skill = read("skills", "feature-build", "SKILL.md")
        self.assertIn("factory_slo.py", skill)
        section = skill[skill.index("feature-freeze"):]
        self.assertIn("`bug`", section)
        self.assertIn("`escaped-defect`", section)
        self.assertIn("attendent", section)
        self.assertIn("clé `budget-action` absente", skill)

    def test_the_alert_action_adds_nothing_beyond_the_label(self) -> None:
        for skill in (read("skills", "qc", "SKILL.md"), read("skills", "feature-build", "SKILL.md")):
            self.assertIn("`alert`", skill)


class Docs(unittest.TestCase):
    def test_the_service_indicators_page_describes_the_actions_and_the_guard(self) -> None:
        page = read_doc("indicateurs-de-service.md")
        self.assertIn("`budget-action`", page)
        for action in ("human-merge", "feature-freeze", "alert"):
            self.assertIn(f"`{action}`", page)
        self.assertIn("guard_git", page)
        self.assertIn("24 h", page)
        self.assertIn("factory_slo.py budget", page)
        self.assertIn("sans objet", page)


if __name__ == "__main__":
    unittest.main()
