"""The documentation of the key `pin-bump` and of the hook pin_notice.py (ikoro-labs/forge#278, A1, A4, A5)."""

import unittest

import support


class Documentation(unittest.TestCase):
    def read(self, *parts: str) -> str:
        return " ".join((support.PLUGIN.joinpath(*parts)).read_text(encoding="utf-8").split())

    def test_the_template_documents_the_key_its_only_value_and_what_still_stops_the_merge(self) -> None:
        """#278 A1 and A4."""
        text = self.read("templates", "usine.md")
        self.assertIn("- `pin-bump` : `auto`", text)
        self.assertIn("Sans la clé", text)
        start = text.index("(clé `pin-bump` absente)")  # the key's own paragraph, not the list of guard keys above it
        section = text[start - 1500 : start + 1500]
        for word in ("protected-path", "human-merge", "SessionStart", "forge--v"):
            self.assertIn(word, section)

    def test_the_billet_says_the_key_not_a_billet_is_the_consent(self) -> None:
        """#278 A5."""
        text = self.read("templates", "billet.md")
        self.assertIn("`pin-bump`", text)
        self.assertIn("accord", text)
        self.assertIn("n'est jamais l'accord de l'humain", text)

    def test_the_consumer_page_and_the_readme_name_the_hook_and_the_key(self) -> None:
        for path in (support.REPO_ROOT / "docs" / "installation.md", support.REPO_ROOT / "README.md"):
            text = " ".join(path.read_text(encoding="utf-8").split())
            self.assertIn("pin_notice", text, path)
            self.assertIn("`pin-bump`", text, path)

    def test_this_repository_does_not_declare_the_key(self) -> None:
        """Out of scope of #278: this repository's pin stays a human gesture."""
        factory = (support.REPO_ROOT / "docs" / "agents" / "usine.md").read_text(encoding="utf-8")
        self.assertNotIn("`pin-bump` :", factory)


if __name__ == "__main__":
    unittest.main()
