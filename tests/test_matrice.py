"""Ticket #94: la matrice de traçabilité d'une feature, une ligne par identifiant de la source."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support  # noqa: F401  met les hooks sur le chemin d'import
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


class Identifiers(unittest.TestCase):
    def test_an_identifier_the_source_does_not_hold_is_unknown(self) -> None:
        """No F-NNNN: ticket #94, A3: un identifiant absent de la source est UNKNOWN."""
        code, out = run(matrix(ROWS + "| EXI-99 | L2 | #14 | | | | absent | |\n"))
        self.assertEqual(code, 1)
        self.assertIn("UNKNOWN\tEXI-99", out)

    def test_a_duplicate_is_refused(self) -> None:
        """No F-NNNN: ticket #94, A3: deux lignes pour le même identifiant sont refusées."""
        code, out = run(matrix(ROWS + "| EXI-02 | L1 | #12 | t::z | | | tenu | 2026-10-22 |\n"))
        self.assertEqual(code, 1)
        self.assertIn("DUPLICATE\tEXI-02", out)

    def test_an_identifier_of_the_source_with_no_row_is_missing(self) -> None:
        """No F-NNNN: ticket #94, A3: un identifiant de la source sans ligne est MISSING."""
        code, out = run(matrix(ROWS.replace("| C01 | L2 | #13 | | | | absent | |\n", "")))
        self.assertEqual(code, 1)
        self.assertIn("MISSING\tC01", out)

    def test_without_the_source_key_nothing_is_checked(self) -> None:
        """No F-NNNN: ticket #94, A3: sans clé product-source, « sans objet » et jamais une valeur par défaut."""
        code, out = run(matrix(ROWS + "| EXI-99 | L2 | #14 | | | | absent | |\n"), usine="")
        self.assertEqual(code, 0, out)
        self.assertIn("sans objet (clé product-source absente)", out)
        self.assertNotIn("UNKNOWN", out)

    def test_a_source_that_is_not_markdown_blocks(self) -> None:
        """No F-NNNN: ticket #94, A3: une source qui n'est pas en Markdown bloque."""
        code, out = run(matrix(), usine="- `product-source` : `source.pdf`\n")
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED\tsource.pdf", out)


class Coverage(unittest.TestCase):
    def test_the_remaining_is_listed_per_batch_and_per_state(self) -> None:
        """No F-NNNN: ticket #94, A4: la commande dit ce qui reste, par lot et par état, et la couverture."""
        code, out = run(matrix(), "--reste")
        self.assertEqual(code, 0, out)
        self.assertIn("RESTE\tL1\tpartiel\tEXI-02", out)
        self.assertIn("RESTE\tL2\tabsent\tC01", out)
        self.assertNotIn("EXI-01", out)
        self.assertIn("COUVERTURE\t1/3\t33 %", out)

    def test_a_row_with_no_batch_is_listed_apart(self) -> None:
        """No F-NNNN: ticket #94, A4: une ligne sans lot se range sous « sans lot »."""
        code, out = run(matrix(ROWS.replace("| L2 |", "| |")), "--reste")
        self.assertIn("RESTE\tsans lot\tabsent\tC01", out)

    def test_an_excluded_row_counts_as_covered(self) -> None:
        """No F-NNNN: ticket #94, A4: écarté, sur accord cité, compte dans la couverture."""
        rows = ROWS.replace("| absent | |", "| écarté | 2026-10-20 |")
        extra = "\nÉcarté : C01 | accord : accord.md | 2026-10-20 | expert-metier\n"
        code, out = run(matrix(rows, extra), "--reste")
        self.assertIn("COUVERTURE\t2/3\t66 %", out)
        self.assertNotIn("C01", out.split("COUVERTURE")[0])


class SourceIdentifiersWithoutRow(unittest.TestCase):
    ONE_ROW = "| C01 | L1 | #5 | t::a | | | tenu | 2026-10-20 |\n"

    def test_the_remaining_counts_an_identifier_with_no_row(self) -> None:
        """No F-NNNN: ticket #94, A4: un identifiant de la source sans ligne compte au dénominateur et reste à tenir."""
        code, out = run(matrix(self.ONE_ROW), "--reste")
        self.assertEqual(code, 0, out)
        self.assertIn("COUVERTURE\t1/3\t33 %", out)
        self.assertIn("RESTE\tsans lot\tabsent\tEXI-01, EXI-02", out)

    def test_no_ticket_lists_an_identifier_with_no_row(self) -> None:
        """No F-NNNN: ticket #94, A6: un identifiant de la source sans ligne n'a pas de ticket et est listé."""
        code, out = run(matrix(self.ONE_ROW), "--sans-ticket")
        self.assertEqual(code, 1, out)
        self.assertIn("SANS-TICKET\tEXI-01", out)
        self.assertIn("SANS-TICKET\tEXI-02", out)
        self.assertNotIn("NONE", out)

    def test_without_the_source_key_no_row_is_added(self) -> None:
        """No F-NNNN: ticket #94, A4: sans la clé product-source, rien n'est ajouté aux lignes de la matrice."""
        code, out = run(matrix(self.ONE_ROW), "--reste", usine="")
        self.assertIn("COUVERTURE\t1/1\t100 %", out)


class Closure(unittest.TestCase):
    def test_closing_under_100_percent_is_refused(self) -> None:
        """No F-NNNN: ticket #94, A5: sous 100 %, la clôture est refusée et nomme chaque ligne qui manque."""
        code, out = run(matrix(), "--cloture")
        self.assertEqual(code, 1)
        self.assertIn("REFUSE\tEXI-02\tpartiel", out)
        self.assertIn("REFUSE\tC01\tabsent", out)
        self.assertNotIn("CLORE", out)

    def test_closing_at_100_percent_is_allowed(self) -> None:
        """No F-NNNN: ticket #94, A5: chaque ligne tenue ou écartée, sans autre constat, la clôture passe."""
        rows = (
            "| EXI-01 | L1 | #11 | t::a | | | tenu | 2026-10-20 |\n"
            "| EXI-02 | L1 | #12 | t::b | | | tenu | 2026-10-20 |\n"
            "| C01 | L2 | | | | | écarté | 2026-10-20 |\n"
        )
        extra = "\nÉcarté : C01 | accord : accord.md | 2026-10-20 | expert-metier\n"
        code, out = run(matrix(rows, extra), "--cloture")
        self.assertEqual(code, 0, out)
        self.assertIn("CLORE\t3/3\t100 %", out)

    def test_a_full_matrix_with_a_finding_does_not_close(self) -> None:
        """No F-NNNN: ticket #94, A5: 100 % avec un tenu sans preuve ne clôt pas."""
        rows = "| EXI-01 | L1 | #11 | | | | tenu | 2026-10-20 |\n| EXI-02 | L1 | #12 | t::b | | | tenu | 2026-10-20 |\n| C01 | L2 | #13 | t::c | | | tenu | 2026-10-20 |\n"
        code, out = run(matrix(rows), "--cloture")
        self.assertEqual(code, 1)
        self.assertIn("INVALID\tEXI-01", out)

    def test_an_empty_matrix_does_not_close(self) -> None:
        """No F-NNNN: ticket #94, A5: une matrice sans ligne ne clôt rien."""
        code, out = run(matrix(""), "--cloture", usine="")
        self.assertEqual(code, 1)
        self.assertIn("REFUSE", out)


class Tickets(unittest.TestCase):
    def test_an_identifier_no_ticket_covers_is_listed(self) -> None:
        """No F-NNNN: ticket #94, A6: le découpage liste l'identifiant qu'aucun ticket ne couvre."""
        code, out = run(matrix(ROWS.replace("#13", "")), "--sans-ticket")
        self.assertEqual(code, 1)
        self.assertIn("SANS-TICKET\tC01", out)
        self.assertNotIn("EXI-01", out)

    def test_every_identifier_covered_lists_nothing(self) -> None:
        """No F-NNNN: ticket #94, A6: tous couverts, la commande dit NONE et sort à 0."""
        code, out = run(matrix(), "--sans-ticket")
        self.assertEqual(code, 0, out)
        self.assertIn("NONE", out)


if __name__ == "__main__":
    unittest.main()
