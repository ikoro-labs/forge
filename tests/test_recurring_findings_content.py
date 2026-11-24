"""F-0002 C04 and T1: `forge:qc` calls `recurring_findings.py`, and the template documents the key `recurring-finding`."""

import unittest

import support


def read(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


def template_paragraph() -> str:
    template = read("templates", "usine.md")
    section = template[template.index("`recurring-finding` : le seuil"):]
    return section[: section.index(" ## ")] if " ## " in section else section


def skill_section() -> str:
    skill = read("skills", "qc", "SKILL.md")
    section = skill[skill.index("## Constats récurrents"):]
    return section[: section.index(" ## ", 5)] if " ## " in section[5:] else section


class TemplateDocumentsTheRecurringFindingKey(unittest.TestCase):
    def test_the_key_is_two_numbers_and_has_no_default(self) -> None:
        """F-0002 T1: `recurring-finding` is `<threshold> | <days>`, absent by default, `sans objet` without it or without `slo-issue`."""
        section = template_paragraph()
        self.assertIn("- `recurring-finding` : `<3 | 30>`", section)
        for text in (
            "`<seuil> | <jours>`", "sans objet (clé `recurring-finding` absente)", "sans objet (clé `slo-issue` absente)",
            "aucune valeur par défaut",
        ):
            self.assertIn(text, section)

    def test_the_template_says_what_is_counted_and_where_it_is_written(self) -> None:
        """F-0002 T1: distinct PRs per `F-n` or `L-n`, one comment of the `slo-issue` ticket found by its marker, never a ticket."""
        section = template_paragraph()
        for text in (
            "PR distinctes", "`F-n`", "`L-n`", "`slo-issue`", "<!-- forge-recurring-findings -->", "jamais un ticket",
            "`scripts/recurring_findings.py`", "`forge:qc`",
        ):
            self.assertIn(text, section)


class QcSkillRunsTheScript(unittest.TestCase):
    def test_the_skill_runs_the_script_after_the_verdict_is_posted(self) -> None:
        """F-0002 C04: `forge:qc` runs `recurring_findings.py` on the project after posting a verdict, and an absent key stops nothing."""
        section = skill_section()
        for text in (
            '"${CLAUDE_PLUGIN_ROOT}/scripts/recurring_findings.py" <projet>', "Après chaque verdict posté",
            "sans objet (clé `<nom>` absente)", "n'ouvre aucun ticket",
        ):
            self.assertIn(text, section)

    def test_step_5_points_to_the_section(self) -> None:
        """F-0002 C04: the step that posts the verdict names the section, so the call is not forgotten."""
        skill = read("skills", "qc", "SKILL.md")
        step = skill[skill.index("5. **Poster.**"):skill.index("6. **Rapporter.**")]
        self.assertIn("Constats récurrents", step)


if __name__ == "__main__":
    unittest.main()
