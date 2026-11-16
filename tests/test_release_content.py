"""Ticket #71 : le skill `forge:release` et les pages qui disent la publication par l'agent et ses conditions.

Chaque phrase gardée ici est une règle de la publication continue : le skill ou la page la perd, et l'agent
publie sans condition, ou déplace un tag.
"""

import unittest
from pathlib import Path

import support
from test_plugin_content import frontmatter

SKILL = support.PLUGIN / "skills" / "release" / "SKILL.md"
SCRIPT = support.PLUGIN / "scripts" / "release.py"
CONTRIBUER = support.REPO_ROOT / "docs" / "contribuer.md"
GIT_RULES = support.REPO_ROOT / ".claude" / "rules" / "git.md"
README = support.REPO_ROOT / "README.md"


def prose(path: Path) -> str:
    """The file on one line per paragraph, so a sentence wrapped by the editor still matches."""
    return " ".join(path.read_text(encoding="utf-8").split())


class ReleaseSkill(unittest.TestCase):
    def test_the_skill_is_a_skill_named_release_that_the_model_does_not_start_alone(self) -> None:
        """Ticket #71 : le skill existe sous le nom `forge:release`, et il pose un tag : l'humain le lance."""
        fields = frontmatter(SKILL)
        self.assertEqual(fields.get("name"), "release")
        self.assertTrue(fields.get("description"))
        self.assertEqual(fields.get("disable-model-invocation"), "true")

    def test_it_names_the_four_conditions_and_the_four_keys_it_reads(self) -> None:
        """Ticket #71 : SLO tenus dans l'heure, budget, essai sur la tête de la base, aucun `sev1`."""
        text = prose(SKILL)
        for phrase in (
            "tous `tenu`", "calculé il y a moins d'une heure", "aucune action de la clé `budget-action`",
            "`RESULTAT: PASS` sur exactement la tête de la base", "aucun ticket `sev1` ouvert",
            "clé `release-trigger`", "clé `release-tag`",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_a_missing_condition_opens_the_version_pr_and_hands_it_to_the_human(self) -> None:
        """Ticket #71 : sinon, la PR de version s'ouvre, `needs-your-attention` dit la condition, l'humain reprend."""
        text = prose(SKILL)
        self.assertRegex(text, r"`humain`.{0,200}Ouvre quand même la PR de version")
        self.assertRegex(text, r"`needs-your-attention`.{0,120}chaque condition de `MANQUE:`")
        self.assertIn("la revue, la fusion et le tag reviennent à l'humain", text)

    def test_an_absent_key_is_sans_objet_and_nothing_is_published(self) -> None:
        """Ticket #71 : clé absente, « sans objet », l'agent ne publie rien."""
        text = prose(SKILL)
        self.assertIn("sans objet (clé `<nom>` absente)", text)
        self.assertRegex(text, r"`sans objet`.{0,120}L'agent ne publie rien")

    def test_the_tag_is_annotated_named_by_the_key_and_never_moved(self) -> None:
        """Ticket #71 : le tag annoté sur le commit de fusion, au motif de `release-tag`, jamais déplacé ni supprimé."""
        text = prose(SKILL)
        self.assertIn("tag **annoté** sur le commit de fusion", text)
        self.assertIn("motif de la clé `release-tag`", text)
        self.assertIn("**Un tag ne se déplace ni ne se supprime**", text)
        self.assertIn("ni `git tag -f`, ni `git push --force`, ni `git push --delete`", text)
        self.assertIn("Lance `/forge:qc` sur la PR de version : c'est lui qui juge et fusionne, jamais toi", text)

    def test_the_skill_and_the_script_cite_no_ticket_and_no_project(self) -> None:
        """Le contenu du plugin reste générique : aucun numéro de ticket, aucun nom de projet."""
        for path in (SKILL, SCRIPT):
            with self.subTest(file=path.name):
                self.assertNotRegex(path.read_text(encoding="utf-8"), r"#\d+|ikoro|Kevin")


class ReleasePages(unittest.TestCase):
    def test_the_contributing_page_says_the_agent_publishes_and_on_which_conditions(self) -> None:
        """Ticket #71 : `docs/contribuer.md` dit la publication par l'agent et ses quatre conditions."""
        text = prose(CONTRIBUER)
        for phrase in ("`/forge:release`", "`release-trigger`", "tous les SLO sont `tenu`", "aucun ticket `sev1` n'est ouvert", "essai de bout en bout"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertRegex(text, r"[Ss]inon.{0,160}`needs-your-attention`")

    def test_the_git_rules_say_the_agent_publishes_and_never_moves_a_tag(self) -> None:
        """Ticket #71 : `.claude/rules/git.md` dit la publication par l'agent, ses conditions et le tag."""
        text = prose(GIT_RULES)
        self.assertIn("L'agent publie seul", text)
        self.assertIn("`/forge:release`", text)
        self.assertRegex(text, r"Un tag ne se déplace ni ne se supprime")

    def test_the_readme_lists_the_skill(self) -> None:
        """Ticket #71 : la page d'accueil liste `/forge:release`."""
        self.assertRegex(prose(README), r"`/forge:release` \|")


if __name__ == "__main__":
    unittest.main()
