"""Ticket #101: la revue de bout en bout en boucle, déclenchée par la fusion, ses écarts repartis en construction."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support
from revue_boucle import main

USINE = "- `journey-paths` : `apps/web/`\n- `journey-paths` : `apps/api/routes/`\n"
HEADER = "| Identifiant | Lot | Ticket | Test | Écran | Capture | État | Jugé le |\n|---|---|---|---|---|---|---|---|\n"
MATRICE = HEADER + (
    "| EXI-01 | L1 | #5 | t1 | Écran 1 | | tenu | 2026-10-01 |\n"
    "| EXI-02 | L1 | #6 | t2 | Écran 2 | | absent | |\n"
    "| C01 | L2 | #6 | t3 | Écran 2 | | absent | |\n"
    "| EXI-03 | L2 | #7 | t4 | | | absent | |\n"
)


def run(argv: list[str], files: dict[str, str]) -> tuple[int, str]:
    """Run the script on a project copy; `{root}` in an argument is that copy. Exit code and standard output."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for name, text in files.items():
            (root / name).write_text(text, encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = main([part.replace("{root}", str(root)) for part in argv])
        return code, out.getvalue()


def declencher(changed: str, usine: str = USINE, *extra: str) -> tuple[int, str]:
    argv = ["declencher", "--files", "{root}/fichiers.txt", "--usine", "{root}/usine.md", *extra]
    return run(argv, {"fichiers.txt": changed, "usine.md": usine, "matrice.md": MATRICE})


class Trigger(unittest.TestCase):
    def test_a_merged_diff_that_touches_the_journey_triggers_the_review(self) -> None:
        """No F-NNNN: ticket #101, le déclenchement sur un diff qui touche le parcours (front ou API qu'il consomme)."""
        code, out = declencher("apps/web/src/saisie.tsx\ndocs/notes.md\n")
        self.assertEqual(code, 0)
        self.assertIn("PARCOURS-TOUCHE\tapps/web/src/saisie.tsx", out)
        self.assertIn("REVUE\tdeclenchee", out)
        code, out = declencher("apps/api/routes/releves.py\n")
        self.assertEqual(code, 0)
        self.assertIn("REVUE\tdeclenchee", out)

    def test_a_diff_that_leaves_the_journey_alone_does_not_trigger_it(self) -> None:
        """No F-NNNN: ticket #101, le déclenchement n'a pas lieu sur un diff qui ne touche pas le parcours."""
        code, out = declencher("docs/notes.md\nplugins/x.py\n")
        self.assertEqual(code, 1)
        self.assertIn("REVUE\tnon declenchee", out)
        self.assertNotIn("PARCOURS-TOUCHE", out)

    def test_without_journey_paths_nothing_is_guessed(self) -> None:
        """No F-NNNN: ticket #101, une clé absente rend l'étape sans objet, jamais un déclenchement deviné."""
        code, out = declencher("apps/web/src/saisie.tsx\n", usine="")
        self.assertEqual(code, 1)
        self.assertIn("sans objet (clé journey-paths absente)", out)
        self.assertNotIn("REVUE\tdeclenchee", out)

    def test_the_screens_to_play_are_those_of_the_merged_ticket(self) -> None:
        """No F-NNNN: ticket #101, la revue d'après fusion porte sur les écrans touchés : ceux que la matrice relie au ticket."""
        code, out = declencher("apps/web/a.tsx\n", USINE, "--matrice", "{root}/matrice.md", "--ticket", "#6")
        self.assertEqual(code, 0)
        self.assertIn("ECRAN\tÉcran 2\tEXI-02, C01", out)
        self.assertNotIn("Écran 1", out)

    def test_a_ticket_with_no_screen_row_is_reviewed_on_the_whole_path(self) -> None:
        """No F-NNNN: ticket #101, sans ligne d'écran pour le ticket, la revue prend le parcours en entier."""
        code, out = declencher("apps/web/a.tsx\n", USINE, "--matrice", "{root}/matrice.md", "--ticket", "#7")
        self.assertEqual(code, 0)
        self.assertIn("ECRAN\ttous\t", out)
