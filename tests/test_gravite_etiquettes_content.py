"""No F-NNNN: ticket #102 A7 : les étiquettes `gravite:*` de la boucle de revue sont décrites pour le projet, et les skills s'y tiennent."""

import unittest

import support

LABELS = ("`gravite:bloquant`", "`gravite:majeur`", "`gravite:mineur`")


def squash(path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class Etiquettes(unittest.TestCase):
    def test_the_installation_page_says_the_labels_must_exist_and_who_creates_them(self) -> None:
        """No F-NNNN: ticket #102 A7 : la page de la boucle dit que les trois étiquettes doivent exister, que l'agent ne les crée pas, et ce que fait la boucle."""
        page = squash(support.REPO_ROOT / "docs" / "installation.md")
        for label in LABELS:
            self.assertIn(label, page)
        self.assertIn("doivent exister sur le dépôt", page)
        self.assertIn("l'agent ne les crée pas", page)
        self.assertIn("propriétaire du dépôt", page)
        self.assertIn("la boucle s'arrête", page)
        self.assertIn("avant de publier", page)

    def test_the_skills_check_the_labels_before_publishing_a_gap_ticket(self) -> None:
        """No F-NNNN: ticket #102 A7 : la revue et la boucle vérifient les trois étiquettes avant de publier, et s'arrêtent en le disant."""
        for skill in ("feature-review", "feature-build"):
            text = squash(support.PLUGIN / "skills" / skill / "SKILL.md")
            self.assertIn("gh label list", text, skill)
            for name in ("bloquant", "majeur", "mineur"):
                self.assertIn(name, text, skill)
            self.assertIn("ne les crée pas", text, skill)
            self.assertIn("docs/installation.md", text, skill)

    def test_the_readme_points_to_the_page(self) -> None:
        """No F-NNNN: ticket #102 A7 : le README renvoie à la page qui décrit les étiquettes."""
        readme = squash(support.REPO_ROOT / "README.md")
        self.assertIn("gravite:", readme)
        self.assertIn("docs/installation.md", readme)


if __name__ == "__main__":
    unittest.main()
