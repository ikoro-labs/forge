"""Ticket #159: the `tdd` skill says when and how to write a property-based test."""

import unittest

import support


def read(*parts: str) -> str:
    return support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8")


class PropertyTestsInTheTddSkill(unittest.TestCase):
    def section(self) -> str:
        text = read("skills", "tdd", "SKILL.md")
        self.assertIn("\n## Les tests par propriétés\n", text)
        return text.split("\n## Les tests par propriétés\n", 1)[1].split("\n## ", 1)[0]

    def test_the_section_says_when_to_write_and_when_to_skip(self) -> None:
        """No F-NNNN: ticket #159, section says when to write one and when to skip it."""
        s = self.section()
        for case in ("fonction pure de calcul", "aller-retour", "invariant", "implémentation de référence"):
            self.assertIn(case, s)
        self.assertIn("interface", s)
        self.assertIn("effets de bord", s)

    def test_the_section_places_it_in_the_red_green_loop(self) -> None:
        """No F-NNNN: ticket #159, the failing property comes first and the minimal example becomes a kept example test."""
        s = self.section()
        self.assertIn("échoue d'abord", s)
        self.assertIn("exemple minimal", s)
        self.assertIn("test par exemple", s)

    def test_the_seed_and_example_go_into_the_proofs(self) -> None:
        """No F-NNNN: ticket #159, seed and minimal example are copied into the proofs."""
        s = self.section()
        self.assertIn("graine", s)
        self.assertIn("**Preuves**", s)

    def test_the_section_is_gated_by_the_key(self) -> None:
        """No F-NNNN: ticket #159, an absent key means no property-based test is requested, said as not applicable."""
        s = self.section()
        self.assertIn("`property-test-lib`", s)
        self.assertIn("sans objet (clé `property-test-lib` absente)", s)


class PropertyTestLibKey(unittest.TestCase):
    def test_the_template_documents_the_key(self) -> None:
        """No F-NNNN: ticket #159, the template documents the `property-test-lib` key."""
        self.assertIn("- `property-test-lib` :", read("templates", "usine.md"))


class JudgeReadsPropertyTests(unittest.TestCase):
    def section(self) -> str:
        text = read("agents", "qc-conf.md")
        self.assertIn("\n## Relecture des tests par propriétés\n", text)
        return text.split("\n## Relecture des tests par propriétés\n", 1)[1].split("\n## ", 1)[0]

    def test_the_judge_flags_a_missing_seed_or_a_missing_minimal_example(self) -> None:
        """No F-NNNN: ticket #159, a finding when either the seed or the minimal example is missing."""
        s = self.section()
        self.assertIn("sans la graine ou sans l'exemple minimal", s)
        self.assertNotIn("sans la graine et sans l'exemple minimal", s)

    def test_the_kept_example_test_has_a_stated_severity(self) -> None:
        """No F-NNNN: ticket #159, the kept example test is a MINOR finding too."""
        s = " ".join(self.section().split())
        self.assertIn("sans lui, constat `MINOR` aussi", s)

    def test_the_judge_never_requires_one_and_the_finding_does_not_block(self) -> None:
        """No F-NNNN: ticket #159, no requirement, and the only severity is MINOR."""
        s = self.section()
        flat = " ".join(s.split())
        self.assertTrue(
            flat.startswith(
                "Tu n'exiges pas de test par propriétés : la clé `property-test-lib` dit si le projet en écrit,"
            ),
            flat[:120],
        )
        self.assertEqual(s.count("exiges"), 1)
        self.assertIn("`MINOR`", s)
        self.assertNotIn("BLOCKER", s)

    def test_the_judge_writes_the_skipped_step_in_gates(self) -> None:
        """No F-NNNN: ticket #159, absent key: no finding and the step is said in GATES."""
        s = self.section()
        self.assertIn("aucun constat", s)
        self.assertIn("`GATES`", s)
        self.assertIn("sans objet (clé `property-test-lib` absente)", s)


if __name__ == "__main__":
    unittest.main()
