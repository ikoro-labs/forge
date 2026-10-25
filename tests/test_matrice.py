"""Ticket #94: la matrice de traçabilité d'une feature, une ligne par identifiant de la source."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support
from matrice import STATES, main, parse

SOURCE = "- EXI-01 : date\n- EXI-02 : index\n- C01 : avertissement\n"
USINE = "- `product-source` : `source.md`\n- `source-author` : `expert-metier`\n"
HEADER = "| Identifiant | Lot | Ticket | Test | Écran | Capture | État | Jugé le |\n|---|---|---|---|---|---|---|---|\n"
ROWS = (
    "| EXI-01 | L1 | #11 | tests/test_a.py::test_un | Écran 1 | captures/e1.png | tenu | 2026-10-20 |\n"
    "| EXI-02 | L1 | #12 | tests/test_a.py::test_deux | Écran 2 | | partiel | 2026-10-21 |\n"
    "| C01 | L2 | #13 | | | | absent | |\n"
)
AGREEMENT = "C01 : écarté, accord écrit de l'expert.\n"


def matrix(rows: str = ROWS, extra: str = "") -> str:
    return "# F-0000 : matrice\n\n" + HEADER + rows + extra


def run(text: str, *flags: str, usine: str = USINE, source: str = SOURCE) -> tuple[int, str]:
    """Run the script on a project copy, as the skills do: exit code and standard output."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root / "usine.md").write_text(usine, encoding="utf-8")
        (root / "source.md").write_text(source, encoding="utf-8")
        (root / "accord.md").write_text(AGREEMENT, encoding="utf-8")
        (root / "matrice.md").write_text(text, encoding="utf-8")
        argv = ["--usine", str(root / "usine.md"), "--root", str(root), *flags, str(root / "matrice.md")]
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = main(argv)
        return code, out.getvalue()


class Format(unittest.TestCase):
    def test_a_well_formed_matrix_passes(self) -> None:
        """No F-NNNN: ticket #94, A1: une ligne par identifiant, avec ticket, test, écran, capture, état et date."""
        code, out = run(matrix())
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("OK\t"), out)

    def test_each_row_is_read_with_its_columns(self) -> None:
        """No F-NNNN: ticket #94, A1: le parseur rend chaque colonne de chaque ligne."""
        rows = parse(matrix())
        self.assertEqual([r["Identifiant"] for r in rows], ["EXI-01", "EXI-02", "C01"])
        self.assertEqual(rows[0]["Capture"], "captures/e1.png")
        self.assertEqual(rows[1]["État"], "partiel")

    def test_a_missing_column_is_invalid(self) -> None:
        """No F-NNNN: ticket #94, A1: un en-tête sans colonne « Capture » est refusé."""
        text = matrix().replace(" Capture |", "")
        code, out = run(text)
        self.assertEqual(code, 1)
        self.assertIn("INVALID", out)
        self.assertIn("Capture", out)

    def test_no_table_is_invalid(self) -> None:
        """No F-NNNN: ticket #94, A1: un fichier sans tableau est refusé."""
        code, out = run("# F-0000 : matrice\n")
        self.assertEqual(code, 1)
        self.assertIn("INVALID", out)


class StateRule(unittest.TestCase):
    def test_the_five_states_are_the_only_ones(self) -> None:
        """No F-NNNN: ticket #94, A2: une règle d'état unique, cinq états."""
        self.assertEqual(set(STATES), {"tenu", "partiel", "absent", "contraire", "écarté"})

    def test_each_state_passes(self) -> None:
        """No F-NNNN: ticket #94, A2: chacun des cinq états est accepté, écarté sur accord cité."""
        rows = (
            "| EXI-01 | L1 | #11 | t::a | | | tenu | 2026-10-20 |\n"
            "| EXI-02 | L1 | #12 | t::b | | | partiel | 2026-10-20 |\n"
            "| C01 | L2 | | | | | écarté | 2026-10-20 |\n"
        )
        extra = "\nÉcarté : C01 | accord : accord.md | 2026-10-20 | expert-metier\n"
        code, out = run(matrix(rows, extra))
        self.assertEqual(code, 0, out)
        for state in ("absent", "contraire"):
            code, out = run(matrix(ROWS.replace("| absent | |", f"| {state} | 2026-10-22 |")))
            self.assertEqual(code, 0, out)

    def test_an_unknown_state_is_invalid(self) -> None:
        """No F-NNNN: ticket #94, A2: « fini » n'est pas un état."""
        code, out = run(matrix(ROWS.replace("partiel", "fini")))
        self.assertEqual(code, 1)
        self.assertIn("INVALID\tEXI-02", out)

    def test_tenu_without_proof_is_refused(self) -> None:
        """No F-NNNN: ticket #94, A2: un état tenu dont le test et la capture sont vides est refusé."""
        code, out = run(matrix(ROWS.replace("tests/test_a.py::test_un | Écran 1 | captures/e1.png", " | Écran 1 | ")))
        self.assertEqual(code, 1)
        self.assertIn("INVALID\tEXI-01", out)
        self.assertIn("preuve", out)

    def test_a_judged_state_needs_a_date(self) -> None:
        """No F-NNNN: ticket #94, A2: tenu, partiel, contraire et écarté portent la date de leur jugement, ISO."""
        code, out = run(matrix(ROWS.replace("2026-10-21", "demain")))
        self.assertEqual(code, 1)
        self.assertIn("INVALID\tEXI-02", out)

    def test_ecarte_needs_the_cited_agreement(self) -> None:
        """No F-NNNN: ticket #94, A2: écarté sans ligne d'accord acceptée est refusé."""
        rows = ROWS.replace("| absent | |", "| écarté | 2026-10-20 |")
        code, out = run(matrix(rows))
        self.assertEqual(code, 1)
        self.assertIn("INVALID\tC01", out)
        code, out = run(matrix(rows, "\nÉcarté : C01 | accord : accord.md | 2026-10-20 | stagiaire\n"))
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("INVALID\tC01", out)


if __name__ == "__main__":
    unittest.main()
