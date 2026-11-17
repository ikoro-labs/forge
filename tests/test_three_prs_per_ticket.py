"""Ticket #249, sans feature : un ticket tient en trois PR au plus.

Le découpage (`feature-design`, `forge:product-owner`) taille chaque ticket pour trois PR, et le
coder ne rend pas de quatrième partie : il rend `BLOCKED`.
"""

import unittest
from pathlib import Path

import support

DESIGN = support.PLUGIN / "skills" / "feature-design" / "SKILL.md"
OWNER = support.PLUGIN / "agents" / "product-owner.md"
CODER = support.PLUGIN / "agents" / "coder.md"
BUILD = support.PLUGIN / "skills" / "feature-build" / "SKILL.md"


def prose(path: Path) -> str:
    """The file on one line, so a sentence wrapped by the editor still matches."""
    return " ".join(path.read_text(encoding="utf-8").split())


def step_six() -> str:
    """The text of step 6 (Découper) of `feature-design`, up to the end of the skill."""
    return prose(DESIGN).split("**Découper**", 1)[1]


class SplitTime(unittest.TestCase):
    def test_step_six_names_the_three_pr_cap(self) -> None:
        """Ticket #249, A1.1: step 6 sizes a ticket for three PRs at most."""
        text = step_six()
        self.assertRegex(text, r"trois PR au plus")
        self.assertRegex(text, r"coupé avant d'être publié")

    def test_the_product_owner_applies_it_when_it_cuts(self) -> None:
        """Ticket #249, A1: the product-owner holds the same cap when it cuts a feature."""
        self.assertRegex(prose(OWNER), r"trois PR au plus")


class CoderCap(unittest.TestCase):
    def test_a_fourth_part_is_a_blocked_not_a_pr(self) -> None:
        """Ticket #249, A2.1: a ticket with three PRs and a failing size-check is BLOCKED."""
        size = prose(CODER).split("**Taille**", 1)[1].split("## 5. Livrer", 1)[0]
        self.assertIn("gh pr list --state all", size)
        self.assertRegex(size, r"(?i)trois PR au plus par ticket")
        self.assertRegex(size, r"`RESULT: BLOCKED`")
        self.assertRegex(size, r"pas de quatrième")

    def test_feature_build_routes_that_blocked_to_a_decision(self) -> None:
        """Ticket #249, A2: the orchestrator reads the cap BLOCKED as a splitting decision."""
        self.assertRegex(prose(BUILD), r"plafond de trois PR[^|]{0,400}`forge:staff-engineer`")


if __name__ == "__main__":
    unittest.main()
