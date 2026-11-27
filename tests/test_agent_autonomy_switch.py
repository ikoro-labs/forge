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


class TheMergeFollowsTheKey(unittest.TestCase):
    """`forge:qc` reads `agent-autonomy` at the merge: `on` merges an ACCEPT, absent hands it to the human."""

    def section(self) -> str:
        text = prose(QC)
        start = text.index("## Autonomie")
        end = text.find(" ## ", start + 1)
        return text[start : end if end != -1 else len(text)]

    def test_the_key_on_merges_an_accept_outside_the_protected_paths(self) -> None:
        """#280 A1.1 : clé `on`, ACCEPT : fusionné, hors `protected-path`."""
        text = self.section()
        self.assertRegex(text, r"`agent-autonomy` : `on`.{0,200}ACCEPT.{0,100}fusionne")

    def test_the_key_absent_posts_the_verdict_labels_and_never_merges(self) -> None:
        """#280 A2.1 : clé absente, ACCEPT : le verdict est posté, `needs-your-attention` posée, aucune fusion."""
        text = self.section()
        self.assertRegex(text, r"[Cc]lé absente.{0,400}ne fusionne jamais.{0,200}`needs-your-attention`")
        self.assertIn("fusion sans objet (clé `agent-autonomy` absente)", text)
        self.assertIn("`fusionnée par l'agent : non`", text)

    def test_a_value_other_than_on_is_the_key_absent(self) -> None:
        """#280 A2 : `oui`, `true` ou une clé répétée ne valent pas `on`."""
        self.assertRegex(self.section(), r"[Uu]ne valeur autre que `on`.{0,120}clé répétée.{0,120}absente")

    def test_who_typed_the_command_does_not_open_the_merge(self) -> None:
        """#280 A2 : même tapé par l'humain, `/forge:qc` ne fusionne pas sans la clé (l'humain fusionne lui-même)."""
        self.assertRegex(self.section(), r"[Mm]ême lancé par l'humain.{0,200}(ne fusionne pas|l'humain fusionne)")

    def test_the_protected_paths_and_human_merge_still_stop_the_merge_with_the_key_on(self) -> None:
        """#280 A4 : `protected-path`, `human-merge` et `never-weaken` arrêtent la fusion même clé `on`, même sur ACCEPT."""
        text = self.section()
        for phrase in ("`protected-path`", "`human-merge`", "`never-weaken`"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertRegex(text, r"valeur `on` ne lève aucun arrêt")
        qc = prose(QC)
        self.assertRegex(qc, r"ACCEPT : fusionne \(étape 8\), sauf ce que les règles \*\*Autonomie\*\*")


class BothWaysAreDescribed(unittest.TestCase):
    """#280 A3 : the rule, the template and the pages say what the key opens and what its absence leaves."""

    SETTINGS = (
        ("the rule", RULE),
        ("the template", TEMPLATE),
        ("the installation page", INSTALLATION),
        ("this repository's protected configuration", support.REPO_ROOT / "docs" / "agents" / "usine-gardes.md"),
    )

    def test_each_place_says_the_key_opens_the_merge_and_the_publication(self) -> None:
        for label, path in self.SETTINGS:
            with self.subTest(place=label):
                text = prose(path)
                start = text.index("interrupteur")
                around = text[max(0, start - 300) : start + 1200]
                self.assertRegex(around, r"interrupteur de la fusion")
                self.assertRegex(around, r"(et|ou) de la publication|publie")

    def test_each_place_says_what_the_absence_leaves_to_the_human(self) -> None:
        for label, path in self.SETTINGS[:3]:
            with self.subTest(place=label):
                text = prose(path)
                self.assertRegex(text, r"(Sans la clé|Clé absente|clé absente|sans la clé).{0,500}(ne fusionne|fusion sans objet|PR de version seule|ouvre la PR de version)")

    def test_the_rule_no_longer_says_the_key_leaves_the_release_alone(self) -> None:
        text = prose(RULE)
        self.assertNotIn("ni `agent-autonomy` ni son absence ne change quand l'agent publie", text)
        self.assertRegex(text, r"`release`.{0,300}`agent-autonomy`.{0,300}PR de version")

    def test_the_template_and_the_page_no_longer_say_release_stays_with_its_trigger_alone(self) -> None:
        for path in (TEMPLATE, INSTALLATION):
            with self.subTest(file=path.name):
                text = prose(path)
                self.assertNotIn("`release` reste commandé par la clé `release-trigger` : cette clé ne les ouvre pas", text)
                self.assertNotIn("la clé ne les ouvre pas, et `release` reste commandée par `release-trigger`", text)


if __name__ == "__main__":
    unittest.main()
