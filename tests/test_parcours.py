"""Ticket #97: the wanted path of a feature, screen by screen, with the exact words of the screen."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support
from parcours import labels_of, main

EXAMPLES = support.REPO_ROOT / "tests" / "exemples"
SOURCE = "- EXI-01 : date, numéro, index\n- EXI-02 : index décroissant refusé\n- C01 : avertissement\n"
USINE = "- `product-source` : `source.md`\n"

GOOD = """# F-0000 : parcours

## Écran 1 : Liste

- Voit : « Compteurs » ; « Saisir »
- Fait : choisit un compteur
- Suivant : Écran 2
- Source : EXI-01

## Écran 2 : Saisie

- Voit : « Index (m3) »
- Fait : saisit l'index
- Suivant : fin
- Source : EXI-02, C01
"""


def run(parcours: str, usine: str = USINE, source: str = SOURCE, spec: str | None = None) -> tuple[int, str]:
    """Run the script on a project copy, as the skills do: exit code and standard output."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root / "usine.md").write_text(usine, encoding="utf-8")
        (root / "source.md").write_text(source, encoding="utf-8")
        (root / "parcours.md").write_text(parcours, encoding="utf-8")
        argv = ["--usine", str(root / "usine.md"), "--root", str(root), str(root / "parcours.md")]
        if spec is not None:
            (root / "spec.md").write_text(spec, encoding="utf-8")
            argv = ["--spec", str(root / "spec.md")] + argv
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = main(argv)
        return code, out.getvalue()


class Format(unittest.TestCase):
    def test_a_well_formed_path_passes(self) -> None:
        """No F-NNNN: ticket #97, A1: chaque écran porte ce qu'il voit, ce qu'il fait, le suivant et ses identifiants."""
        code, out = run(GOOD)
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("OK\t"), out)

    def test_a_missing_field_is_invalid(self) -> None:
        """No F-NNNN: ticket #97, A2: un écran sans « Fait » est refusé et le message nomme l'écran et le champ."""
        code, out = run(GOOD.replace("- Fait : choisit un compteur\n", ""))
        self.assertEqual(code, 1)
        self.assertIn("INVALID\tÉcran 1\t", out)
        self.assertIn("Fait", out)

    def test_labels_are_quoted_with_guillemets(self) -> None:
        """No F-NNNN: ticket #97, A1: les libellés exacts s'écrivent entre guillemets français."""
        code, out = run(GOOD.replace("« Compteurs » ; « Saisir »", "Compteurs ; Saisir"))
        self.assertEqual(code, 1)
        self.assertIn("Voit", out)

    def test_screens_are_numbered_in_order(self) -> None:
        """No F-NNNN: ticket #97, A1: les écrans se suivent, de 1 sans trou."""
        code, out = run(GOOD.replace("## Écran 2 :", "## Écran 3 :").replace("Suivant : Écran 2", "Suivant : Écran 3"))
        self.assertEqual(code, 1)
        self.assertIn("numéro", out)

    def test_the_next_screen_exists_and_the_path_ends(self) -> None:
        """No F-NNNN: ticket #97, A1: le suivant est un écran du parcours ou « fin », et le dernier écran finit."""
        code, out = run(GOOD.replace("Suivant : Écran 2", "Suivant : Écran 7"))
        self.assertEqual(code, 1)
        self.assertIn("Écran 7", out)
        code, out = run(GOOD.replace("Suivant : fin", "Suivant : Écran 1"))
        self.assertEqual(code, 1)
        self.assertIn("fin", out)

    def test_a_file_without_screen_is_invalid(self) -> None:
        """No F-NNNN: ticket #97, A2: un parcours sans écran n'est pas un parcours."""
        code, out = run("# F-0000 : parcours\n")
        self.assertEqual(code, 1)
        self.assertIn("aucun écran", out)


class Identifiers(unittest.TestCase):
    def test_a_screen_without_identifier_is_invalid(self) -> None:
        """No F-NNNN: ticket #97, A2: chaque écran cite au moins un identifiant."""
        code, out = run(GOOD.replace("- Source : EXI-01", "- Source : aucun"))
        self.assertEqual(code, 1)
        self.assertIn("INVALID\tÉcran 1\t", out)
        self.assertIn("identifiant", out)

    def test_an_identifier_absent_from_the_source_is_unknown(self) -> None:
        """No F-NNNN: ticket #97, A2: l'identifiant cité existe dans la source de la clé product-source."""
        code, out = run(GOOD.replace("EXI-01", "EXI-99"))
        self.assertEqual(code, 1)
        self.assertIn("UNKNOWN\tÉcran 1\tEXI-99", out)

    def test_without_the_source_key_the_spec_is_the_reference(self) -> None:
        """No F-NNNN: ticket #97, A2: sans la clé, la spec donne les identifiants."""
        spec = "EXI-01 et EXI-02 et C01\n"
        code, out = run(GOOD, usine="", spec=spec)
        self.assertEqual(code, 0, out)
        code, out = run(GOOD.replace("EXI-02", "EXI-98"), usine="", spec=spec)
        self.assertEqual(code, 1)
        self.assertIn("UNKNOWN\tÉcran 2\tEXI-98", out)

    def test_without_key_nor_spec_the_check_is_not_applicable(self) -> None:
        """No F-NNNN: ticket #97, A2: ni clé ni spec, la correspondance est « sans objet », jamais validée."""
        code, out = run(GOOD, usine="")
        self.assertEqual(code, 0)
        self.assertIn("sans objet (clé product-source absente)", out)

    def test_a_hyphenless_identifier_counts(self) -> None:
        """No F-NNNN: ticket #97, A2: C01 et G0 sont des identifiants, au contrat de source_ids."""
        code, out = run(GOOD.replace("EXI-02, C01", "C01"))
        self.assertEqual(code, 0, out)


class Vocabulary(unittest.TestCase):
    def test_the_labels_of_the_path_are_listed_for_the_glossary(self) -> None:
        """No F-NNNN: ticket #97, A3: le vocabulaire de l'écran se relève, sans doublon, dans l'ordre."""
        self.assertEqual(labels_of(GOOD), ["Compteurs", "Saisir", "Index (m3)"])


class Example(unittest.TestCase):
    def test_the_example_passes_against_the_example_spec(self) -> None:
        """No F-NNNN: ticket #97, A2: l'exemple de parcours cite des identifiants que la spec d'exemple tient."""
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = main(["--spec", str(EXAMPLES / "spec.md"), "--root", str(EXAMPLES), str(EXAMPLES / "parcours.md")])
        self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
