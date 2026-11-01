"""Ticket #159 : le skill `tdd` dit quand et comment écrire un test par propriétés."""

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
        """No F-NNNN: ticket #159, section du skill (quand écrire, quand s'en passer)."""
        s = self.section()
        for cas in ("fonction pure de calcul", "aller-retour", "invariant", "implémentation de référence"):
            self.assertIn(cas, s)
        self.assertIn("interface", s)
        self.assertIn("effets de bord", s)

    def test_the_section_places_it_in_the_red_green_loop(self) -> None:
        """No F-NNNN: ticket #159, la propriété échoue d'abord, l'exemple minimal devient un test gardé."""
        s = self.section()
        self.assertIn("échoue d'abord", s)
        self.assertIn("exemple minimal", s)
        self.assertIn("test par exemple", s)

    def test_the_seed_and_example_go_into_the_proofs(self) -> None:
        """No F-NNNN: ticket #159, graine et exemple minimal recopiés dans les Preuves."""
        s = self.section()
        self.assertIn("graine", s)
        self.assertIn("**Preuves**", s)

    def test_the_section_is_gated_by_the_key(self) -> None:
        """No F-NNNN: ticket #159, clé absente : aucun test par propriétés demandé."""
        s = self.section()
        self.assertIn("`property-test-lib`", s)
        self.assertIn("absente", s)


class PropertyTestLibKey(unittest.TestCase):
    def test_the_template_documents_the_key(self) -> None:
        """No F-NNNN: ticket #159, la clé `property-test-lib` est dans le gabarit."""
        self.assertIn("- `property-test-lib` :", read("templates", "usine.md"))


class JudgeReadsPropertyTests(unittest.TestCase):
    def section(self) -> str:
        text = read("agents", "qc-conf.md")
        self.assertIn("\n## Relecture des tests par propriétés\n", text)
        return text.split("\n## Relecture des tests par propriétés\n", 1)[1].split("\n## ", 1)[0]

    def test_the_judge_flags_a_missing_seed_or_minimal_example(self) -> None:
        """No F-NNNN: ticket #159, le juge relève un échec sans graine ni exemple minimal."""
        s = self.section()
        self.assertIn("graine", s)
        self.assertIn("exemple minimal", s)
        self.assertIn("constat", s)

    def test_the_judge_does_not_require_one(self) -> None:
        """No F-NNNN: ticket #159, le juge n'exige pas de test par propriétés."""
        self.assertIn("n'exiges pas", self.section())


if __name__ == "__main__":
    unittest.main()
