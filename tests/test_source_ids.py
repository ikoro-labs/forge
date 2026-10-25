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

    def test_identifiers_without_a_hyphen_are_elements_too(self) -> None:
        """No F-NNNN: ticket #92, A2 et A3: C01 et G0 en tête de ligne sont des éléments, listés absents, code 1."""
        source = "- EXI-01 : a\n- C01 : calcul\n| G0 | gabarit |\n"
        self.assertEqual(ids_of_source(source), ["EXI-01", "C01", "G0"])
        code, out = run({"source.md": source, "spec.md": "Reprend EXI-01.\n"})
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[:2], ["MISSING\tC01\tsource.md\t", "MISSING\tG0\tsource.md\t"])

    def test_an_ordinary_word_at_the_line_start_is_not_an_identifier(self) -> None:
        """No F-NNNN: ticket #92, A2: un mot, un nombre ou une phrase en tête de ligne n'est pas un identifiant."""
        source = "Note 3 : à lire\n- Phase 2 : essai\nTVA 20 % due\n- Contrôle C01x\n1. Étape\nCe C01 est cité en passant.\n"
        self.assertEqual(ids_of_source(source), [])


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


NON_GOALS = "## 3. Non-goals\n\n- Hors périmètre : CT-10\n\n## 4. Exigences\n\nSans objet.\n"


class NonGoals(unittest.TestCase):
    def test_an_identifier_cited_in_the_non_goals_without_agreement_is_refused(self) -> None:
        """No F-NNNN: ticket #93, A5: Hors périmètre : CT-10 sans ligne Écarté ni accord n'est pas une reprise."""
        code, out = run({"source.md": SOURCE, "spec.md": "Reprend EX-1, EX-2 et RG-3.1.\n\n" + NON_GOALS})
        lines = out.splitlines()
        self.assertEqual(code, 1)
        self.assertTrue(any(line.startswith("REFUSED\tCT-10\t") and "Non-goals" in line for line in lines))

    def test_an_element_taken_up_elsewhere_and_cited_in_the_non_goals_is_still_refused(self) -> None:
        """No F-NNNN: ticket #93, A5: l'élément repris puis déclaré hors périmètre est une contradiction, refusée."""
        code, out = run({"source.md": SOURCE, "spec.md": "Reprend EX-1, EX-2, CT-10, RG-3.1.\n\n" + NON_GOALS})
        self.assertEqual(code, 1)
        self.assertIn("REFUSED\tCT-10\t", out)

    def test_an_accepted_exclusion_may_be_cited_in_the_non_goals(self) -> None:
        """No F-NNNN: ticket #93, A5: avec une ligne Écarté et son accord, la mention dans les Non-goals est permise."""
        code, out = run({"source.md": SOURCE, "spec.md": SPEC_EXCLUDING + "\n" + NON_GOALS, "accord.md": "CT-10 écarté.\n"})
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "EXCLUDED\tCT-10\taccord.md\t2026-10-20 expert métier")

    def test_a_non_goals_section_without_source_identifier_changes_nothing(self) -> None:
        """No F-NNNN: ticket #93, A5: des Non-goals qui ne citent aucun identifiant de la source laissent le code à 0."""
        spec = SPEC_FULL + "\n## 3. Non-goals\n\n- Le paiement des factures.\n"
        code, out = run({"source.md": SOURCE, "spec.md": spec})
        self.assertEqual((code, out.splitlines()[0].split("\t")[0]), (0, "NONE"))


EXAMPLES = Path(__file__).resolve().parent / "exemples"
TEMPLATE = Path(__file__).resolve().parent.parent / "plugins" / "forge" / "templates" / "features" / "spec.md"


def titles(text: str) -> list[str]:
    """The level-2 headings of a Markdown text, without their number or their parenthesis."""
    return [line[3:].split(". ", 1)[-1].split(" (")[0] for line in text.splitlines() if line.startswith("## ")]


class FilledExample(unittest.TestCase):
    """Ticket #93: a spec filled on the template passes the count of #92."""

    source = (EXAMPLES / "source.md").read_text(encoding="utf-8")
    spec = (EXAMPLES / "spec.md").read_text(encoding="utf-8")

    def test_the_filled_example_takes_up_every_element_of_its_source(self) -> None:
        """No F-NNNN: ticket #93, A3: l'exemple rempli passe le comptage, liste vide et code 0."""
        self.assertEqual(ids_of_source(self.source), ["EXI-01", "EXI-02", "EXI-03", "C01", "C02", "G1", "G2", "P1"])
        code, out = run({"source.md": self.source, "spec.md": self.spec})
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0].split("\t")[0], "NONE")

    def test_the_example_loses_the_count_when_an_element_is_dropped(self) -> None:
        """No F-NNNN: ticket #93, A3: sans les lignes qui citent C02, le comptage liste C02."""
        spec = "\n".join(line for line in self.spec.splitlines() if "C02" not in line)
        code, out = run({"source.md": self.source, "spec.md": spec})
        self.assertEqual(code, 1)
        self.assertIn("MISSING\tC02\tsource.md\t", out)

    def test_the_example_holds_every_section_of_the_template(self) -> None:
        """No F-NNNN: ticket #93, A3: l'exemple suit le gabarit, section par section, dans l'ordre."""
        template = titles(TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(titles(self.spec), template)


class Usage(unittest.TestCase):
    def test_a_missing_source_file_exits_two(self) -> None:
        """No F-NNNN: ticket #92, A1: une source déclarée et introuvable sort 2, elle n'est pas vide."""
        code, _ = run({"spec.md": SPEC_FULL})
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
