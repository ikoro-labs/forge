"""Ticket #154, part 1: a script plants one known defect, from a spec, in a frozen `accept-` case.

No test here calls a model: the planted case is a folder of text, built from a temporary copy of the
frozen cases and compared with them.
"""

import difflib
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

import support
from plant_defect import SpecError, parse_diff, plant, totals

EVALS = support.PLUGIN / "evals"
SOURCE = "accept-pr238-tour1"
# The `+` line of PR 238's tests that proves A1.1 (key absent: the label).
LABEL_ASSERT = '        self.assertIn("pose `needs-your-attention`", step)'
HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def tree(folder: Path) -> dict[str, bytes]:
    return {str(path.relative_to(folder)): path.read_bytes() for path in sorted(folder.rglob("*")) if path.is_file()}


def changes(before: str, after: str) -> tuple[list[str], list[str]]:
    """The lines that leave and the lines that enter between two texts, nothing else."""
    removed, added = [], []
    for line in difflib.ndiff(before.splitlines(), after.splitlines()):
        if line.startswith("- "):
            removed.append(line[2:])
        elif line.startswith("+ "):
            added.append(line[2:])
    return removed, added


def hunks_are_consistent(diff: str) -> bool:
    """Every `@@` header counts the lines of its body."""
    lines = diff.splitlines()
    index = 0
    while index < len(lines):
        found = HEADER.match(lines[index])
        index += 1
        if not found:
            continue
        old = int(found.group(2) if found.group(2) is not None else 1)
        new = int(found.group(4) if found.group(4) is not None else 1)
        while (old or new) and index < len(lines):
            kind = lines[index][:1]
            if kind == " ":
                old, new = old - 1, new - 1
            elif kind == "-":
                old -= 1
            elif kind == "+":
                new -= 1
            elif kind != "\\":
                return False
            index += 1
        if old or new:
            return False
    return True


def headless(diff: str) -> str:
    """The diff with every `@@` header blanked: what is left is the lines, whatever their counts."""
    return "\n".join("@@" if HEADER.match(line) else line for line in diff.split("\n"))


def replaced(diff: str, old: list[str], new: list[str]) -> str:
    """The diff with a block of added lines replaced by another, by plain text."""
    block = "".join(f"+{line}\n" for line in old)
    assert diff.count(block) == 1
    return diff.replace(block, "".join(f"+{line}\n" for line in new))


def weakened(**changed: Any) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "name": "trap-weakened-test-pr238-sample",
        "class": "weakened-test",
        "source": SOURCE,
        "summary": "the assertion that the label is posed is removed from the test of the absent key",
        "defect": "Le verdict signale que le test de la clé absente ne vérifie plus l'étiquette `needs-your-attention`.",
        "edits": [{"file": "tests/test_plugin_content.py", "old": [LABEL_ASSERT], "new": []}],
    }
    spec.update(changed)
    return spec


class Plant(unittest.TestCase):
    """The planted case is a temporary copy of a frozen case with one change, and nothing else."""

    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.evals = self.root / "evals"
        shutil.copytree(EVALS / SOURCE, self.evals / SOURCE)
        self.out = self.root / "out"

    def plant(self, spec: dict[str, Any]) -> Path:
        return plant(spec, self.evals, self.out)

    def read(self, folder: Path, name: str) -> str:
        return (folder / name).read_text(encoding="utf-8")


class WeakenedTest(Plant):
    def test_one_assertion_of_the_test_is_removed_and_nothing_else_changes(self) -> None:
        """#154 A2.1: the assertion leaves the diff; the counts of its hunk follow; no other line moves."""
        case = self.plant(weakened())
        before = self.read(self.evals / SOURCE, "fixtures/pr.diff")
        after = self.read(case, "fixtures/pr.diff")
        removed, added = changes(before, after)
        self.assertEqual(len(removed), 2)
        self.assertTrue(removed[0].startswith("@@ -871,14 +871,46 @@"))
        self.assertEqual(removed[1], "+" + LABEL_ASSERT)
        self.assertEqual(len(added), 1)
        self.assertTrue(added[0].startswith("@@ -871,14 +871,45 @@"))
        self.assertTrue(hunks_are_consistent(after))

    def test_the_other_files_of_the_case_are_the_ones_of_the_frozen_case(self) -> None:
        """#154 A2.1: the ticket, the body, the rules, the prompt and the scaffold are copied byte for byte."""
        case = self.plant(weakened())
        frozen = tree(self.evals / SOURCE)
        planted = tree(case)
        names = ("ticket.txt", "pr-body.txt", "claude.txt", "rules-forge.txt", "rules-git.txt", "usine.txt")
        for name in ("prompt.md", "scaffold.sh", *(f"fixtures/{n}" for n in names)):
            with self.subTest(name=name):
                self.assertEqual(planted[name], frozen[name])
        self.assertEqual(case.name, "trap-weakened-test-pr238-sample")

    def test_a_loosened_assertion_replaces_the_line_and_keeps_the_counts(self) -> None:
        loosened = '        self.assertIn("needs-attention", step)'
        case = self.plant(weakened(edits=[
            {"file": "tests/test_plugin_content.py", "old": [LABEL_ASSERT], "new": [loosened]}]))
        removed, added = changes(self.read(self.evals / SOURCE, "fixtures/pr.diff"),
                                 self.read(case, "fixtures/pr.diff"))
        self.assertEqual((removed, added), (["+" + LABEL_ASSERT], ["+" + loosened]))

    def test_the_gate_table_follows_the_diff(self) -> None:
        """#154 A2.1: the counts of the `Base et diff` row are those of the planted diff (one line fewer)."""
        case = self.plant(weakened())
        before = self.read(self.evals / SOURCE, "fixtures/gate.txt")
        after = self.read(case, "fixtures/gate.txt")
        self.assertEqual(changes(before, after), (
            ["| Base et diff | 4 fichier(s) dans pr.diff, +50 -13 | diff de la base à la tête |"],
            ["| Base et diff | 4 fichier(s) dans pr.diff, +49 -13 | diff de la base à la tête |"]))

    def test_an_edit_that_does_not_find_its_line_is_refused(self) -> None:
        bad = weakened(edits=[{"file": "tests/test_plugin_content.py", "old": ["        self.assertTrue(False)"],
                               "new": []}])
        with self.assertRaises(SpecError):
            self.plant(bad)
        self.assertFalse(self.out.exists())

    def test_a_weakened_test_edits_a_test_and_never_adds_a_line(self) -> None:
        elsewhere = weakened(edits=[{"file": "plugins/forge/skills/qc/SKILL.md", "old": [], "new": []}])
        with self.assertRaises(SpecError):
            self.plant(elsewhere)
        longer = weakened(edits=[{"file": "tests/test_plugin_content.py", "old": [LABEL_ASSERT],
                                  "new": [LABEL_ASSERT, LABEL_ASSERT]}])
        with self.assertRaises(SpecError):
            self.plant(longer)

    def test_a_source_that_is_not_an_accept_case_is_refused(self) -> None:
        shutil.copytree(EVALS / "blocker-pr11-tour1", self.evals / "blocker-pr11-tour1")
        with self.assertRaises(SpecError):
            self.plant(weakened(source="blocker-pr11-tour1"))

    def test_the_name_carries_the_class(self) -> None:
        with self.assertRaises(SpecError):
            self.plant(weakened(name="trap-out-of-scope-pr238-sample"))
        with self.assertRaises(SpecError):
            self.plant(weakened(**{"class": "nonsense"}))


RULE_OLD = [
    "- Un test isole `HOME` et `USERPROFILE`, ne passe pas les variables `CLAUDE_` de la session qui le",
    "  lance, et n'écrit jamais dans le vrai `~/.claude`.",
]
RULE_NEW = ["- Un test isole `HOME` et `USERPROFILE`."]
# PR 238 added these lines to the skill (A1: the label and the `Attention` text when the key is absent).
SKILL_OLD = [
    "   sur son ACCEPT, pose `needs-your-attention`, écris dans `Attention` `fusion sans objet (clé",
    "   `merge-method` absente)` et `fusionnée par l'agent : non` dans `Verdict`, puis arrête-toi :",
    "   l'humain fusionne. Toujours avec un corps que tu écris : en `squash`, sans lui, GitHub",
]
SKILL_NEW = [
    "   sur son ACCEPT, et le compte rendu dit « fusion sans objet (clé",
    "   `merge-method` absente) ». Toujours avec un corps que tu écris : en `squash`, sans lui, GitHub",
]
# ... and this test, which proves A1.1.
TEST_OLD = [
    "    def test_qc_without_the_key_does_not_merge_and_asks_for_attention(self) -> None:",
    "        # ikoro-labs/forge#63 A1.1: key absent, no merge, the label and the Attention text.",
    '        skill = " ".join((support.PLUGIN / "skills" / "qc" / "SKILL.md").read_text(encoding="utf-8").split())',
    '        step = skill[skill.index("8. **Fusionner.**"):]',
    '        self.assertIn("Sans la clé `merge-method`, tu ne fusionnes pas", step)',
    '        self.assertIn("pose `needs-your-attention`", step)',
    '        self.assertIn("écris dans `Attention` `fusion sans objet (clé `merge-method` absente)`", step)',
    '        self.assertIn("`fusionnée par l\'agent : non` dans `Verdict`", step)',
    "",
]


def outside() -> dict[str, Any]:
    return {
        "name": "trap-out-of-scope-pr238-sample",
        "class": "out-of-scope",
        "source": SOURCE,
        "summary": "the rule that a test isolates HOME is cut short in `.claude/rules/forge.md`",
        "defect": "Le verdict signale que la PR change `.claude/rules/forge.md`, hors du ticket.",
        "outside": {"file": ".claude/rules/forge.md", "fixture": "rules-forge.txt", "old": RULE_OLD, "new": RULE_NEW},
    }


def unmet(delete_test: bool) -> dict[str, Any]:
    tests = [{"file": "tests/test_plugin_content.py", "old": TEST_OLD, "new": []}] if delete_test else []
    return {
        "name": "trap-unmet-criterion-pr238-sample",
        "class": "unmet-criterion",
        "source": SOURCE,
        "summary": "the skill no longer poses the label when the key is absent",
        "defect": "Le verdict signale que `skills/qc/SKILL.md` ne pose plus `needs-attention` sans la clé (A1).",
        "edits": [{"file": "plugins/forge/skills/qc/SKILL.md", "old": SKILL_OLD, "new": SKILL_NEW}, *tests],
    }


class OutOfScope(Plant):
    def test_one_file_outside_the_ticket_is_modified_and_nothing_else_changes(self) -> None:
        """#154 A2.2: a section for the file enters the diff, in path order; the frozen lines all stay."""
        case = self.plant(outside())
        before = self.read(self.evals / SOURCE, "fixtures/pr.diff")
        after = self.read(case, "fixtures/pr.diff")
        self.assertTrue(after.endswith(before))
        entered = after[: -len(before)]
        self.assertTrue(entered.startswith("diff --git a/.claude/rules/forge.md b/.claude/rules/forge.md\nindex "))
        self.assertIn("\n--- a/.claude/rules/forge.md\n+++ b/.claude/rules/forge.md\n@@ ", entered)
        self.assertEqual(totals(parse_diff(entered)), (1, 1, 2))
        self.assertTrue(hunks_are_consistent(after))
        self.assertEqual(changes(self.read(self.evals / SOURCE, "fixtures/ticket.txt"),
                                 self.read(case, "fixtures/ticket.txt")), ([], []))

    def test_the_gate_table_names_the_new_file_and_the_new_counts(self) -> None:
        case = self.plant(outside())
        removed, added = changes(self.read(self.evals / SOURCE, "fixtures/gate.txt"),
                                 self.read(case, "fixtures/gate.txt"))
        self.assertEqual(len(removed), 2)
        self.assertIn("| Base et diff | 5 fichier(s) dans pr.diff, +51 -15 | diff de la base à la tête |", added)
        self.assertIn("| Périmètre | à lire | fichiers de pr.diff : .claude/rules/forge.md, docs/installation.md, "
                      "plugins/forge/skills/qc/SKILL.md, plugins/forge/templates/usine.md, "
                      "tests/test_plugin_content.py |", added)

    def test_a_file_the_diff_already_changes_is_not_outside(self) -> None:
        inside = outside()
        inside["outside"] = {**inside["outside"], "file": "docs/installation.md"}
        with self.assertRaises(SpecError):
            self.plant(inside)

    def test_lines_the_fixture_does_not_hold_are_refused_and_nothing_is_written(self) -> None:
        wrong = outside()
        wrong["outside"] = {**wrong["outside"], "old": ["a line the rules never had"]}
        with self.assertRaises(SpecError):
            self.plant(wrong)
        self.assertFalse(self.out.exists())

    def test_an_out_of_scope_spec_edits_no_other_line(self) -> None:
        both = {**outside(), "edits": [{"file": "tests/test_plugin_content.py", "old": [LABEL_ASSERT], "new": []}]}
        with self.assertRaises(SpecError):
            self.plant(both)


class UnmetCriterion(Plant):
    def test_the_code_of_a_criterion_is_removed_and_its_test_deleted(self) -> None:
        """#154 A2.3: the added lines of the skill go back to the text without the label, the test goes."""
        case = self.plant(unmet(delete_test=True))
        before = self.read(self.evals / SOURCE, "fixtures/pr.diff")
        after = self.read(case, "fixtures/pr.diff")
        expected = replaced(replaced(before, SKILL_OLD, SKILL_NEW), TEST_OLD, [])
        self.assertEqual(headless(after), headless(expected))
        self.assertTrue(hunks_are_consistent(after))
        self.assertEqual(totals(parse_diff(after)), (4, 50 - 3 - 9 + 2, 13))

    def test_the_test_can_be_kept_and_then_the_test_file_does_not_change(self) -> None:
        """#154 A2.3: only the code of the criterion goes; the test that proved it stays in the diff."""
        case = self.plant(unmet(delete_test=False))
        before, after = self.read(self.evals / SOURCE, "fixtures/pr.diff"), self.read(case, "fixtures/pr.diff")
        self.assertEqual(headless(after), headless(replaced(before, SKILL_OLD, SKILL_NEW)))
        self.assertIn("test_qc_without_the_key_does_not_merge_and_asks_for_attention", after)

    def test_the_criterion_is_removed_not_rewritten_and_the_test_is_deleted_not_rewritten(self) -> None:
        longer = unmet(delete_test=False)
        longer["edits"][0]["new"] = SKILL_OLD + ["more"]
        with self.assertRaises(SpecError):
            self.plant(longer)
        rewritten = unmet(delete_test=True)
        rewritten["edits"][1]["new"] = ["    pass"]
        with self.assertRaises(SpecError):
            self.plant(rewritten)
        only_tests = unmet(delete_test=True)
        del only_tests["edits"][0]
        with self.assertRaises(SpecError):
            self.plant(only_tests)


class Counts(unittest.TestCase):
    def test_the_counts_of_each_frozen_diff_are_the_ones_of_its_frozen_gate_table(self) -> None:
        """The way the script counts files and lines is the way the gate table did: a planted row can be trusted."""
        for folder in sorted(EVALS.glob("accept-*")):
            with self.subTest(case=folder.name):
                files, added, removed = totals(parse_diff((folder / "fixtures" / "pr.diff").read_text(encoding="utf-8")))
                gate = (folder / "fixtures" / "gate.txt").read_text(encoding="utf-8")
                self.assertIn(f"| Base et diff | {files} fichier(s) dans pr.diff, +{added} -{removed} |", gate)


class Deterministic(Plant):
    def test_the_same_spec_gives_the_same_bytes(self) -> None:
        """#154 A2.4: twice, into two folders and over the same folder, byte for byte."""
        for spec in (weakened(), outside(), unmet(delete_test=True), unmet(delete_test=False)):
            with self.subTest(name=spec["name"]):
                first = tree(plant(spec, self.evals, self.root / "one"))
                second = tree(plant(spec, self.evals, self.root / "two"))
                again = tree(plant(spec, self.evals, self.root / "one"))
                self.assertEqual(first, second)
                self.assertEqual(first, again)

    def test_the_case_holds_the_files_of_a_case_and_the_three_graders(self) -> None:
        case = self.plant(weakened())
        self.assertEqual(sorted(tree(case)), sorted([
            "case.yaml", "prompt.md", "scaffold.sh", "graders/rejects.md", "graders/no-false-accept.md",
            "graders/names-the-defect.md", *(f"fixtures/{n}" for n in (
                "ticket.txt", "pr-body.txt", "pr.diff", "gate.txt", "claude.txt", "rules-forge.txt",
                "rules-git.txt", "usine.txt"))]))
        self.assertTrue((case / "scaffold.sh").stat().st_mode & 0o111 == (self.evals / SOURCE / "scaffold.sh").stat().st_mode & 0o111)


if __name__ == "__main__":
    unittest.main()
