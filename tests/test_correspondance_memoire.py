"""#61 part 4: the correspondence between the memory entries of a workstation and the repository.

Seam: `docs/correspondance-memoire.md` read as a table. A1.1 and A4.1 hold the rows (count, one class
each, every cited path exists), A3.1 holds that no workstation identity reached the plugin, and the
doc of contributors carries it.
"""

import re
import unittest
from pathlib import Path

import support

ROOT = support.REPO_ROOT
DOC = ROOT / "docs" / "correspondance-memoire.md"
CLASSES = ("plugin", "doc du projet", "sans règle")
ENTRIES = 21
HEADER = ("entrée", "ce qu'elle dit", "classe", "cible", "test", "raison")


def rows(text: str) -> list[list[str]]:
    """The cells of each data row of the table of `## La table`, header and separator left out."""
    found = []
    section = text.split("## La table", 1)[1].split("\n## ", 1)[0]
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0].lower() == HEADER[0] or set(cells[0]) <= {"-", ":", " "}:
            continue
        found.append(cells)
    return found


def cited(cell: str) -> list[str]:
    """The paths a cell cites, each one between backticks."""
    return re.findall(r"`([^`]+)`", cell)


def missing(table: list[list[str]], root: Path) -> list[str]:
    """Every cited path of the `cible` and `test` columns that is not in the repository."""
    return [path for cells in table for cell in cells[3:5] for path in cited(cell) if not (root / path).exists()]


class Table(unittest.TestCase):
    def setUp(self) -> None:
        self.text = DOC.read_text(encoding="utf-8")
        self.table = rows(self.text)

    def test_a1_1_61_the_table_has_one_row_per_memory_entry(self) -> None:
        self.assertEqual(len(self.table), ENTRIES)
        self.assertEqual(len({cells[0] for cells in self.table}), ENTRIES, "one row per entry")
        self.assertTrue(all(len(cells) == len(HEADER) for cells in self.table))

    def test_a1_1_61_each_row_has_one_class_and_a_reason(self) -> None:
        for cells in self.table:
            with self.subTest(entry=cells[0]):
                self.assertIn(cells[2], CLASSES)
                self.assertTrue(cells[5], "a row says why")

    def test_a1_1_61_a_plugin_row_cites_a_target_and_a_test_and_the_others_cite_no_plugin_path(self) -> None:
        for cells in self.table:
            with self.subTest(entry=cells[0]):
                if cells[2] == "plugin":
                    self.assertTrue(any(p.startswith("plugins/forge/") for p in cited(cells[3])))
                    self.assertTrue(any(p.startswith("tests/") for p in cited(cells[4])))
                else:
                    self.assertFalse(any(p.startswith("plugins/forge/") for p in cited(cells[3])))
                if cells[2] == "doc du projet":
                    self.assertTrue(any(p.startswith("docs/") for p in cited(cells[3])))
                if cells[2] == "sans règle":
                    self.assertEqual(cells[4], "sans objet")

    def test_a4_1_61_every_cited_path_exists(self) -> None:
        self.assertEqual(missing(self.table, ROOT), [])

    def test_a4_1_61_a_row_citing_a_missing_path_is_found(self) -> None:
        row = ["x", "y", "plugin", "`plugins/forge/hooks/no_such_guard.py`", "`tests/test_no_such.py`", "z"]
        self.assertEqual(missing([row], ROOT), ["plugins/forge/hooks/no_such_guard.py", "tests/test_no_such.py"])

    def test_a1_61_the_doc_names_no_other_project_and_is_dated(self) -> None:
        self.assertNotIn("shipyard", self.text.lower())
        self.assertIn("2026-11-17", self.text)

    def test_a1_61_the_readme_lists_the_doc(self) -> None:
        self.assertIn("docs/correspondance-memoire.md", (ROOT / "README.md").read_text(encoding="utf-8"))


class WorkstationIdentity(unittest.TestCase):
    # What names the account of a workstation: its noreply address, its numeric id.
    FORBIDDEN = ("336514991", "ikoro-labs@users.noreply.github.com")
    TEXT_SUFFIXES = {".md", ".py", ".json", ".txt", ".yml", ".yaml", ".diff"}

    def test_a3_1_61_no_account_or_noreply_address_is_under_the_plugin(self) -> None:
        found = []
        for path in sorted((ROOT / "plugins" / "forge").rglob("*")):
            if path.is_file() and path.suffix in self.TEXT_SUFFIXES:
                text = path.read_text(encoding="utf-8", errors="replace")
                found += [f"{path.relative_to(ROOT)}: {item}" for item in self.FORBIDDEN if item in text]
        self.assertEqual(found, [])

    def test_a3_61_the_contributors_doc_carries_the_git_identity_and_the_gh_account(self) -> None:
        text = (ROOT / "docs" / "contribuer.md").read_text(encoding="utf-8")
        self.assertIn("ikoro-labs@users.noreply.github.com", text)
        self.assertIn("git -c user.name=", text)
        self.assertIn("gh api user", text)


if __name__ == "__main__":
    unittest.main()
