"""Le contenu qui porte les classes de gravité et les engagements de délai (ticket #60)."""

import unittest

import support


def read(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


def read_doc(name: str) -> str:
    return " ".join((support.REPO_ROOT / "docs" / name).read_text(encoding="utf-8").split())


class Classes(unittest.TestCase):
    def test_the_docs_define_the_three_classes_and_their_labels(self) -> None:
        """Ticket #60, critère 1 : trois classes de gravité définies dans `docs/`, posées par `sev1`, `sev2`, `sev3`."""
        page = read_doc("gravite-et-sla.md")
        for label in ("`sev1`", "`sev2`", "`sev3`"):
            self.assertIn(label, page)
        self.assertIn("un garde contourné", page)
        self.assertIn("un chemin protégé fusionné sans humain", page)
        self.assertIn("une perte de données ou de travail", page)
        self.assertIn("la branche de base rouge", page)
        self.assertIn("un défaut échappé qui change un comportement", page)
        self.assertIn("la prose, la documentation ou un confort", page)

    def test_the_template_defines_the_same_classes(self) -> None:
        """Ticket #60, critère 1 : les classes sont aussi dans le gabarit de `usine.md`."""
        template = read("templates", "usine.md")
        for label in ("`sev1`", "`sev2`", "`sev3`"):
            self.assertIn(label, template)
        self.assertIn("un garde contourné", template)
        self.assertIn("la prose, la documentation ou un confort", template)

    def test_the_readme_points_to_the_page(self) -> None:
        readme = " ".join((support.REPO_ROOT / "README.md").read_text(encoding="utf-8").split())
        self.assertIn("docs/gravite-et-sla.md", readme)


if __name__ == "__main__":
    unittest.main()
