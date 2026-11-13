"""The review loop opens no ticket and needs no `gravite:*` label (decision of 2026-11-13)."""

import unittest

import support


def squash(path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class Etiquettes(unittest.TestCase):
    def test_the_installation_page_says_the_loop_comments_gaps_and_needs_no_label(self) -> None:
        """The page of the loop says a review opens no ticket, needs no label, and names the one exception."""
        page = squash(support.REPO_ROOT / "docs" / "installation.md")
        self.assertIn("A review opens no ticket", page)
        self.assertIn("The loop needs no label of its own", page)
        self.assertIn("Motif : fusion-bloquee #<pr>", page)
        self.assertNotIn("gravite:", page)

    def test_the_skills_comment_gaps_instead_of_publishing_gap_tickets(self) -> None:
        """A review opens no ticket (decision of 2026-11-13): its gaps are comments on existing tickets."""
        for skill in ("feature-review", "feature-build"):
            text = squash(support.PLUGIN / "skills" / skill / "SKILL.md")
            self.assertIn("A review opens no ticket", text, skill)
            self.assertIn("Motif : fusion-bloquee #<pr>", text, skill)
            self.assertNotIn("gh label list", text, skill)

    def test_the_readme_points_to_the_page(self) -> None:
        """The README says the loop opens no ticket and points to the page, without any `gravite:*` label."""
        readme = squash(support.REPO_ROOT / "README.md")
        self.assertIn("The review loop opens no ticket", readme)
        self.assertNotIn("gravite:", readme)
        self.assertIn("docs/installation.md", readme)

if __name__ == "__main__":
    unittest.main()
