"""Ticket #92: the elements of a business source, counted in the spec by their identifier."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support  # noqa: F401
from source_ids import ids_of_source, main

SOURCE = """# Procédure

- EX-1 : saisir le dossier
- **EX-2** : contrôler les pièces
| CT-10 | Contrôle du total | oui |
## [RG-3.1] Règle de calcul
Une phrase qui cite EX-9 en passant n'est pas un élément.
```
- IN-1 : dans un bloc de code
```
"""

SPEC_FULL = "# Spec\n\nReprend EX-1, EX-2, CT-10 et RG-3.1.\n"
USINE = "- `product-source` : `source.md`\n- `source-author` : `expert métier`\n"
NO_AUTHOR = "- `product-source` : `source.md`\n"


def run(files: dict[str, str], usine: str = USINE) -> tuple[int, str]:
    """Run the script on a project copy holding `files`, as the spec skill does: code and output."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root / "usine.md").write_text(usine, encoding="utf-8")
        for name, text in files.items():
            (root / name).write_text(text, encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = main(["--usine", str(root / "usine.md"), "--root", str(root), str(root / "spec.md")])
        return code, out.getvalue()


class Counting(unittest.TestCase):
    def test_the_identified_elements_of_a_markdown_source_are_found(self) -> None:
        """No F-NNNN: ticket #92, A1: un élément identifié est une ligne qui commence par son identifiant."""
        self.assertEqual(ids_of_source(SOURCE), ["EX-1", "EX-2", "CT-10", "RG-3.1"])

    def test_a_complete_source_gives_an_empty_list(self) -> None:
        """No F-NNNN: ticket #92, A3: la spec reprend chaque identifiant, la liste des absents est vide, code 0."""
        code, out = run({"source.md": SOURCE, "spec.md": SPEC_FULL})
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "NONE\t\t\taucun identifiant de la source n'est absent de la spec")

    def test_an_identifier_missing_from_the_spec_is_listed(self) -> None:
        """No F-NNNN: ticket #92, A3: un identifiant absent de la spec est listé avec sa source, code 1."""
        code, out = run({"source.md": SOURCE, "spec.md": "Reprend EX-1, EX-2 et RG-3.1.\n"})
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[0], "MISSING\tCT-10\tsource.md\t")

    def test_a_longer_identifier_does_not_cover_a_shorter_one(self) -> None:
        """No F-NNNN: ticket #92, A3: EX-12 ou EX-1.2 dans la spec ne reprend pas EX-1."""
        code, out = run({"source.md": "- EX-1 : a\n", "spec.md": "EX-12, EX-1.2 et AEX-1\n"})
        self.assertEqual((code, out.split("\t")[:2]), (1, ["MISSING", "EX-1"]))


class Format(unittest.TestCase):
    def test_a_pdf_source_blocks_and_asks_for_a_markdown_export(self) -> None:
        """No F-NNNN: ticket #92, A1: une source en PDF est bloquée, aucune conversion, code 1."""
        usine = "- `product-source` : `source.pdf`\n- `source-author` : `expert métier`\n"
        code, out = run({"spec.md": SPEC_FULL}, usine)
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("BLOCKED\tsource.pdf\t"))
        self.assertIn("export Markdown", out)

    def test_docx_and_image_sources_block_too(self) -> None:
        """No F-NNNN: ticket #92, A1: .docx et image sont bloquées comme le PDF."""
        for name in ("source.docx", "capture.PNG"):
            code, out = run({"spec.md": SPEC_FULL}, f"- `product-source` : `{name}`\n")
            self.assertEqual((code, out.split("\t")[0]), (1, "BLOCKED"), name)

    def test_without_product_source_the_step_is_without_object(self) -> None:
        """No F-NNNN: ticket #92, A1: clé product-source absente, jamais PASS."""
        code, out = run({"spec.md": SPEC_FULL}, "- `source-author` : `expert métier`\n")
        self.assertEqual((code, out.strip()), (0, "sans objet (clé product-source absente)"))
        self.assertNotIn("PASS", out)


EXCLUSION = "Écarté : CT-10 | accord : accord.md | 2026-10-20 | expert métier\n"
SPEC_EXCLUDING = "Reprend EX-1, EX-2 et RG-3.1.\n\n- " + EXCLUSION


class Exclusions(unittest.TestCase):
    def test_an_exclusion_without_agreement_does_not_cover_the_element(self) -> None:
        """No F-NNNN: ticket #92, A4: sans fichier d'accord, l'exclusion est refusée et l'élément reste absent."""
        code, out = run({"source.md": SOURCE, "spec.md": SPEC_EXCLUDING})
        lines = out.splitlines()
        self.assertEqual(code, 1)
        self.assertIn("MISSING\tCT-10\tsource.md\t", lines)
        self.assertTrue(any(line.startswith("REFUSED\tCT-10\t") and "accord.md" in line for line in lines))

    def test_an_agreement_that_does_not_name_the_element_is_refused(self) -> None:
        """No F-NNNN: ticket #92, A4: l'accord doit citer l'identifiant écarté."""
        code, out = run({"source.md": SOURCE, "spec.md": SPEC_EXCLUDING, "accord.md": "Rien d'écarté.\n"})
        self.assertEqual(code, 1)
        self.assertIn("REFUSED\tCT-10\t", out)

    def test_an_exclusion_with_a_written_agreement_covers_the_element(self) -> None:
        """No F-NNNN: ticket #92, A5: accord écrit qui cite l'identifiant, par le rôle de source-author, code 0."""
        code, out = run({"source.md": SOURCE, "spec.md": SPEC_EXCLUDING, "accord.md": "CT-10 écarté.\n"})
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "EXCLUDED\tCT-10\taccord.md\t2026-10-20 expert métier")

    def test_an_agreement_by_another_role_is_refused(self) -> None:
        """No F-NNNN: ticket #92, A4: seule la personne que désigne source-author peut écarter."""
        spec = SPEC_EXCLUDING.replace("| expert métier", "| développeur")
        code, out = run({"source.md": SOURCE, "spec.md": spec, "accord.md": "CT-10\n"})
        self.assertEqual(code, 1)
        self.assertIn("REFUSED\tCT-10\t", out)

    def test_an_invalid_date_is_refused(self) -> None:
        """No F-NNNN: ticket #92, A4: la date de l'accord est AAAA-MM-JJ."""
        spec = SPEC_EXCLUDING.replace("2026-10-20", "hier")
        code, out = run({"source.md": SOURCE, "spec.md": spec, "accord.md": "CT-10\n"})
        self.assertEqual(code, 1)
        self.assertIn("REFUSED\tCT-10\t", out)

    def test_the_exclusion_line_is_not_a_reprise_of_the_element(self) -> None:
        """No F-NNNN: ticket #92, A4: citer l'identifiant dans la ligne d'exclusion ne le reprend pas."""
        spec = "Reprend EX-1, EX-2 et RG-3.1.\n" + EXCLUSION
        _, out = run({"source.md": SOURCE, "spec.md": spec})
        self.assertIn("MISSING\tCT-10\t", out)

    def test_without_source_author_no_element_is_set_aside(self) -> None:
        """No F-NNNN: ticket #92, A6: clé source-author absente, aucun élément ne s'écarte, et la sortie le dit."""
        code, out = run({"source.md": SOURCE, "spec.md": SPEC_EXCLUDING, "accord.md": "CT-10\n"}, NO_AUTHOR)
        self.assertEqual(code, 1)
        self.assertIn("MISSING\tCT-10\t", out)
        self.assertIn("sans objet (clé source-author absente)", out)
        self.assertIn("aucun élément ne s'écarte", out)

    def test_without_source_author_a_complete_spec_passes_and_says_it(self) -> None:
        """No F-NNNN: ticket #92, A6: sans exclusion, la clé absente ne bloque pas mais est dite."""
        code, out = run({"source.md": SOURCE, "spec.md": SPEC_FULL}, NO_AUTHOR)
        self.assertEqual(code, 0)
        self.assertIn("sans objet (clé source-author absente)", out)


class Usage(unittest.TestCase):
    def test_a_missing_source_file_exits_two(self) -> None:
        """No F-NNNN: ticket #92, A1: une source déclarée et introuvable sort 2, elle n'est pas vide."""
        code, _ = run({"spec.md": SPEC_FULL})
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
