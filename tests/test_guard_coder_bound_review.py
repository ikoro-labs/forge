"""Ticket #61, part 2, A3: the incident review of the red test names `guard_coder` as its fix."""

import unittest

import support
from incident import read


class Incident(unittest.TestCase):
    def test_the_review_of_the_red_test_incident_names_this_guard_as_its_fix(self) -> None:
        """Ticket #61, A3: the review `memoire-epuisee-par-un-test-rouge` cites `guard_coder` and its test."""
        path = support.REPO_ROOT / "docs" / "incidents" / "2026-10-24-memoire-epuisee-par-un-test-rouge.md"
        text = path.read_text(encoding="utf-8")
        review, errors = read(text, support.REPO_ROOT)
        self.assertEqual(errors, [])
        self.assertIn("existant : plugins/forge/hooks/guard_coder.py ; tests/test_guard_coder_bound.py", text)
        self.assertEqual(review.klass, "mécanique")
        self.assertNotIn("aucun garde ne refuse une commande de test lancée sans le lanceur", text)


if __name__ == "__main__":
    unittest.main()
