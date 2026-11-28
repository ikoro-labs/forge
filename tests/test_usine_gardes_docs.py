"""ikoro-labs/forge#345 B6 : the template and the pages of `docs/` say where the sensitive keys are.

The list of `usine.SENSITIVE_KEYS` is the source: each page that lists the keys lists all of them, the
count in words follows, and this repository's own pages say its keys moved.
"""

import re
import unittest
from pathlib import Path

import support
from test_usine_gardes_repo import DECLARED
from usine import SENSITIVE_KEYS

TEMPLATE = support.PLUGIN / "templates" / "usine.md"
INSTALLATION = support.REPO_ROOT / "docs" / "installation.md"
CONTRIBUER = support.REPO_ROOT / "docs" / "contribuer.md"
DECISIONS = support.REPO_ROOT / "docs" / "agents" / "decisions.md"

COUNT = "Vingt-sept clés"


def section(path: Path, heading: str) -> str:
    """The text of the `## heading` section of `path`, up to the next `## ` heading, on one line."""
    text = path.read_text(encoding="utf-8")
    start = text.index(f"## {heading}")
    end = re.search(r"^## ", text[start + 3 :], re.M)
    body = text[start : start + 3 + end.start()] if end else text[start:]
    return " ".join(body.split())


class TheTemplateListsEverySensitiveKey(unittest.TestCase):
    def test_b6_the_section_of_the_protected_keys_names_each_one_and_counts_them(self) -> None:
        """#345 B6: 27 keys, `e2e-run-limits`, `ticket-pr-cap-exempt`, `ticket-pr-cap-small`, `human-collections`, `agent-token-command` and `agent-login` among them, each named in the template's section."""
        text = section(TEMPLATE, "Clés protégées")
        self.assertIn(COUNT, text)
        for key in sorted(SENSITIVE_KEYS):
            with self.subTest(key=key):
                self.assertIn(f"`{key}`", text)

    def test_b6_the_e2e_run_limits_key_says_it_is_protected(self) -> None:
        """#345 B6: where the template explains `e2e-run-limits`, it says a project writes the key in the guard file."""
        text = " ".join(TEMPLATE.read_text(encoding="utf-8").split())
        explanation = text[text.index("`e2e-run-limits` : clé facultative") :][:1800]
        self.assertIn(
            "elle borne l'agent : un projet l'écrit dans `docs/agents/usine-gardes.md`, avec les autres clés protégées",
            explanation,
        )


class TheInstallationPageSaysWhatMoved(unittest.TestCase):
    def test_b6_the_page_lists_each_sensitive_key_and_counts_them(self) -> None:
        text = section(INSTALLATION, "Le fichier des clés protégées")
        self.assertIn(COUNT, text)
        for key in sorted(SENSITIVE_KEYS):
            with self.subTest(key=key):
                self.assertIn(f"`{key}`", text)

    def test_b6_the_page_says_this_repository_moved_its_keys_and_that_the_scripts_follow(self) -> None:
        """#345 B6: the move is no longer « une PR à part » and the scripts are no longer said to read `usine.md` alone."""
        text = section(INSTALLATION, "Le fichier des clés protégées")
        self.assertNotIn("est une PR à part", text)
        self.assertNotIn("Non tenu ici : les scripts", text)
        self.assertIn("Ce dépôt a déplacé ses clés", text)
        self.assertIn("`bounded_run.py`", text)
        self.assertIn("`usine.read_config`", text)

    def test_b6_the_page_names_each_key_this_repository_moved_and_counts_them(self) -> None:
        """#345 B6: the sentence on the move lists the keys `usine-gardes.md` holds, and their count in words."""
        text = section(INSTALLATION, "Le fichier des clés protégées")
        moved = text.split("Ce dépôt a déplacé ses clés", 1)[1].split("Non tenu ici", 1)[0]
        for key in sorted(DECLARED):
            with self.subTest(key=key):
                self.assertIn(f"`{key}`", moved)
        self.assertIn("les douze qu'il déclare", moved)
        self.assertEqual(len(DECLARED), 12)

    def test_b6_the_protected_path_paragraph_names_the_guard_file(self) -> None:
        """#345 B6: the paragraph on this repository's `protected-path` names `usine-gardes.md`, not `usine.md`."""
        page = " ".join(INSTALLATION.read_text(encoding="utf-8").split())
        self.assertIn("`docs/agents/usine-gardes.md` est un `protected-path` de ce dépôt", page)
        self.assertNotIn("`docs/agents/usine.md` est un `protected-path` de ce dépôt", page)


class TheOtherPagesFollow(unittest.TestCase):
    def test_b6_the_tree_of_contribuer_lists_the_guard_file(self) -> None:
        text = CONTRIBUER.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^docs/agents/usine-gardes\.md +ses clés protégées")

    def test_b6_the_matrix_reserves_the_merge_of_a_change_of_the_guard_file(self) -> None:
        """#345 B6: `H1` names the file the key `protected-path` now lists."""
        text = " ".join(DECISIONS.read_text(encoding="utf-8").split())
        self.assertIn("un `protected-path` de `usine-gardes.md`", text)
        self.assertNotIn("un `protected-path` de `usine.md`", text)
