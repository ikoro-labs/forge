"""Ticket #61, part 3, critère 1 : `forge:feature-build` lance `forge:incident`.

Sans cette étape, le skill `incident` dit « à lancer » et rien ne le lance : un arrêt sur incident,
ou un ticket `sev1` ou `sev2` fusionné, se termine sans revue écrite.
"""

import unittest

import support

SKILL = support.PLUGIN / "skills" / "feature-build" / "SKILL.md"


def prose() -> str:
    """The skill on one line per paragraph, so a sentence wrapped by the editor still matches."""
    return " ".join(SKILL.read_text(encoding="utf-8").split())


class IncidentStep(unittest.TestCase):
    def test_a_stop_on_incident_runs_the_incident_skill(self) -> None:
        """Ticket #61 part 3, A1.1: the step of the stop on incident names `forge:incident`."""
        self.assertRegex(prose(), r"[Aa]rrêt sur incident[^|]{0,400}`forge:incident`")

    def test_a_merged_sev1_or_sev2_ticket_runs_it_too(self) -> None:
        """Ticket #61 part 3, A1: the merge of a PR that closes a `sev1` or `sev2` ticket runs it."""
        text = prose()
        self.assertRegex(text, r"`sev1` ou `sev2`[^|]{0,400}`forge:incident`")
        self.assertRegex(text, r"`forge:incident`[^|]{0,400}avant le compte rendu")

    def test_without_the_key_the_step_is_without_object(self) -> None:
        """Ticket #61 part 3, A1: no `incident-dir`, no review, and the report says so."""
        self.assertIn("sans objet (clé `incident-dir` absente)", prose())

    def test_the_report_names_the_review_written(self) -> None:
        """Ticket #61 part 3, A1: the report of step 6 carries the review each run wrote."""
        report = prose().split("## 6. Rendre compte", 1)[1]
        self.assertRegex(report, r"revue sans blâme|`forge:incident`")


if __name__ == "__main__":
    unittest.main()
