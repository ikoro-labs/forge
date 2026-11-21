"""Chaque `protected-path` de ce dépôt a un propriétaire du code dans `.github/CODEOWNERS` (#74).

Le ruleset de `main` exige l'approbation d'un propriétaire du code : sans ligne, un chemin protégé
ne serait gardé que par `guard_git`, qu'une session hors plugin ne charge pas.
"""

import unittest

import support
from usine import load

CODEOWNERS = support.REPO_ROOT / ".github" / "CODEOWNERS"


def owned_patterns() -> dict[str, list[str]]:
    """Each pattern of CODEOWNERS and its owners, comments and blank lines left out."""
    owned: dict[str, list[str]] = {}
    for line in CODEOWNERS.read_text(encoding="utf-8").splitlines():
        words = line.split("#", 1)[0].split()
        if words:
            owned[words[0]] = words[1:]
    return owned


def pattern_for(protected: str) -> str:
    """The CODEOWNERS pattern of a `protected-path`: a folder as is, a name prefix with `*`."""
    return "/" + protected if protected.endswith("/") else "/" + protected + "*"


class EveryProtectedPathHasACodeOwner(unittest.TestCase):
    def test_each_protected_path_has_its_pattern_and_an_owner(self) -> None:
        protected = load(support.REPO_ROOT).get("protected-path", [])
        self.assertTrue(protected, "docs/agents/usine.md declares no protected-path")
        owned = owned_patterns()
        for path in protected:
            with self.subTest(path=path):
                pattern = pattern_for(path)
                self.assertIn(pattern, owned, f"{pattern} missing from .github/CODEOWNERS")
                self.assertTrue(owned[pattern], f"{pattern} has no owner")


class TheDocsSayWhatTheProtectedPathsDoNotCover(unittest.TestCase):
    def test_the_pin_is_delegated_to_the_agent_and_the_docs_say_so(self) -> None:
        """Ticket #280 : l'épingle choisit les gardes chargés ; hors des chemins protégés, la doc le dit."""
        self.assertNotIn(".claude/settings.json", load(support.REPO_ROOT).get("protected-path", []))
        for name in ("usine.md", "decisions.md"):
            text = " ".join((support.REPO_ROOT / "docs" / "agents" / name).read_text(encoding="utf-8").split())
            with self.subTest(file=name):
                self.assertIn("l'épingle de ce dépôt", text)
                self.assertRegex(text, r"(déléguée à l'agent|Délégué par l'humain)")
