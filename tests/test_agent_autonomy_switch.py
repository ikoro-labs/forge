"""ikoro-labs/forge#280: `agent-autonomy` is the one switch for merging and publishing alone.

The texts the agent reads are the seam: a skill, a rule, a template or a page that loses one of these
sentences changes who merges or publishes, without a test failing anywhere else.
"""

import unittest
from pathlib import Path

import support

INSTALLATION = support.REPO_ROOT / "docs" / "installation.md"
CONTRIBUER = support.REPO_ROOT / "docs" / "contribuer.md"
QC = support.PLUGIN / "skills" / "qc" / "SKILL.md"
RELEASE = support.PLUGIN / "skills" / "release" / "SKILL.md"
RULE = support.PLUGIN / "autonomie.md"
TEMPLATE = support.PLUGIN / "templates" / "usine.md"


def prose(path: Path) -> str:
    """The file on one line per paragraph, so a sentence wrapped by the editor still matches."""
    return " ".join(path.read_text(encoding="utf-8").split())


def section(text: str, heading: str) -> str:
    """The body of a `## heading` of a page, up to the next `## `."""
    start = text.index(f"## {heading}")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


class ConsumerPinIsNotAHumanGesture(unittest.TestCase):
    def test_the_human_gestures_no_longer_list_a_consumer_pin_bump(self) -> None:
        """#280 (decision 2026-11-21): raising a consumer's pin is a PR the agent opens and merges."""
        text = section(INSTALLATION.read_text(encoding="utf-8"), "Gestes humains")
        self.assertNotIn("À chaque montée d'épingle", text)
        self.assertNotRegex(text, r"(?s)montée d'épingle.{0,200}Monter de version")

    def test_the_pin_bump_section_says_the_agent_pins_and_merges(self) -> None:
        """#280: the page that documents `pin-bump` no longer says this repository's pin stays the human's."""
        text = prose(INSTALLATION)
        self.assertNotIn("sa propre épingle reste montée par l'humain", text)
        self.assertIn("L'épingle est déléguée à l'agent, projets consommateurs compris", text)
        self.assertIn("que l'agent fusionne sur ACCEPT", text)

    def test_the_pin_bump_of_this_repository_is_its_own_pr_not_the_version_pr(self) -> None:
        """#280: the pin bump is a PR apart, as `docs/contribuer.md` says; the page does not call it the version PR."""
        installation = prose(INSTALLATION)
        self.assertNotIn("son épingle se monte par la PR de version", installation)
        self.assertRegex(installation, r"son épingle se monte par une PR à part")
        self.assertRegex(prose(CONTRIBUER), r"c'est une PR à part, que l'agent fusionne sur ACCEPT")


if __name__ == "__main__":
    unittest.main()
