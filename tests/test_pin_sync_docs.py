"""ikoro-labs/forge#333 A4: the page of the install says when the install may run, and documents `pin_sync.py`
and the BEHIND notice of `pin_notice.py`; the README and the template of the key agree."""

import unittest

import support


def read(*parts: str) -> str:
    return " ".join(support.REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8").split())


class Installation(unittest.TestCase):
    def section(self, title: str, to: str) -> str:
        text = read("docs", "installation.md")
        start = text.index(title)
        return text[start : text.index(to, start)]

    def test_an_install_is_allowed_between_two_tickets_and_never_between_a_coder_and_the_verdict(self) -> None:
        """#333 A4: the paragraph that said `Jamais pendant un /forge:feature-build actif` says what holds now."""
        section = self.section("## Monter de version", "### Laisser la session ouvrir la PR")
        self.assertIn("entre deux tickets", section)
        self.assertIn("entre un coder et le verdict", section)
        self.assertNotIn("**Jamais pendant un `/forge:feature-build` actif.**", section)

    def test_the_page_documents_both_commands_of_the_script_and_what_stops_them(self) -> None:
        section = self.section("## Monter de version", "### Laisser la session ouvrir la PR")
        for word in (
            "pin_sync.py check --all",
            "pin_sync.py apply",
            "`OK`",
            "`BEHIND`",
            "`NOT RUN`",
            "`REFUSED`",
            "en_vol",
            "file_revue",
            "niveau utilisateur",
            "aucun fichier de réglages utilisateur",
        ):
            self.assertIn(word, section)

    def test_the_page_says_what_was_not_tried(self) -> None:
        section = self.section("## Monter de version", "### Laisser la session ouvrir la PR")
        self.assertIn("Éprouvé", section)
        self.assertIn("simulé", section)

    def test_the_page_describes_the_behind_notice_and_the_timeout_that_covers_it(self) -> None:
        text = read("docs", "installation.md")
        start = text.index("### Laisser la session ouvrir la PR")
        section = text[start : text.index("## Configurer", start)]
        self.assertIn("BEHIND", section)
        self.assertIn("pin_sync.py apply", section)
        self.assertIn("30 secondes au total", section)
        self.assertNotIn("20 secondes au total", section)

    def test_the_other_mention_of_the_two_commands_names_the_script(self) -> None:
        text = read("docs", "installation.md")
        self.assertIn("pin_sync.py apply", text[text.index("La montée d'épingle n'en est plus un") :][:900])


class Neighbours(unittest.TestCase):
    def test_the_readme_names_the_script_in_its_bump_paragraph_and_the_notice_in_its_hook_table(self) -> None:
        text = read("README.md")
        start = text.index("Pour **monter de version**")
        self.assertIn("pin_sync.py", text[start : start + 900])
        self.assertIn("BEHIND", text[text.index("| `pin_notice` |") :][:1200])

    def test_the_template_of_the_key_no_longer_leaves_the_gesture_to_the_human_alone(self) -> None:
        text = read("plugins", "forge", "templates", "usine.md")
        section = text[text.index("`pin-bump`") - 1500 : text.index("- `pin-bump` : `auto`")]
        self.assertIn("pin_sync.py", section)
        self.assertNotIn("reste à l'humain. Sans la clé", section)

    def test_the_bump_notice_points_at_the_script_not_at_the_human(self) -> None:
        import pin_notice

        text = pin_notice.notice_text("forge--v", (1, 20, 0), (1, 21, 0))
        self.assertIn("pin_sync.py", text)
        self.assertNotIn("l'humain.", text.split("Une fois la PR fusionnée")[1])


if __name__ == "__main__":
    unittest.main()
