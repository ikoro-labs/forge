"""Ticket #61, critère 4 : la première application, les revues des incidents que le ticket constate.

Le dépôt déclare la clé `incident-dir`, et chaque revue de ce dossier passe `incident.py check` sur la
racine du dépôt : les chemins qu'elle cite existent. Le dépôt est public : aucune revue ne porte de
chemin de poste ni de renvoi à une mémoire privée.
"""

import re
import unittest

import support
from factory_slo import incidents
from incident import incident_dir, read, review_files
from usine import load

KEY_LINE = "docs/incidents"
NAMES = (
    "memoire-epuisee-par-un-test-rouge",
    "push-u-change-la-config-git-partagee",
    "coder-hors-de-son-worktree",
    "closes-dans-un-commit-de-branche",
)


class FirstApplication(unittest.TestCase):
    def reviews(self) -> list:
        folder = incident_dir(support.REPO_ROOT)
        self.assertIsNotNone(folder)
        return review_files(folder) if folder else []

    def test_the_repository_declares_the_key_incident_dir(self) -> None:
        """Ticket #61, critère 4 : ce dépôt déclare `incident-dir`."""
        self.assertEqual(load(support.REPO_ROOT).get("incident-dir"), [KEY_LINE])

    def test_one_review_per_incident_of_the_ticket(self) -> None:
        """Ticket #61, critère 4 : les quatre incidents du constat ont chacun leur revue."""
        names = [path.name for path in self.reviews()]
        for subject in NAMES:
            with self.subTest(subject=subject):
                self.assertEqual(len([name for name in names if name.endswith(f"-{subject}.md")]), 1)
        self.assertEqual(len(names), len(NAMES))

    def test_every_review_passes_the_check_on_this_repository(self) -> None:
        """Ticket #61, critère 4 : faits datés, cause, ce qui l'a laissé passer, correctif dont les chemins existent."""
        for path in self.reviews():
            with self.subTest(review=path.name):
                review, errors = read(path.read_text(encoding="utf-8"), support.REPO_ROOT)
                self.assertEqual(errors, [])
                self.assertIn(review.klass, ("mécanique", "jugement"))

    def test_the_four_incidents_are_counted_by_class(self) -> None:
        """Ticket #61, critère 5 : quatre revues mécaniques, aucune de jugement, aucune refusée."""
        document = incidents(support.REPO_ROOT)
        assert document is not None
        self.assertEqual(document["classes"], {"mécanique": 4, "jugement": 0})
        self.assertEqual(document["refusees"], [])

    def test_a_public_repository_holds_no_workstation_path_nor_private_note(self) -> None:
        """Ticket #61 : aucune revue ne porte de chemin de poste ni de renvoi à une mémoire privée."""
        forbidden = re.compile(r"/home/|/Users/|[A-Za-z]:\\|~/\.claude|MEMORY\.md|\.claude/projects")
        for path in self.reviews():
            with self.subTest(review=path.name):
                self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
