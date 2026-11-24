"""F-0002, ticket #309: the `raised-entry` type of `never-weaken` is documented in the template and in the `docs/` page."""

import unittest

import support


def read(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


def read_root(*parts: str) -> str:
    return " ".join(support.REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8").split())


class Template(unittest.TestCase):
    def test_f0002_t1_the_template_lists_raised_entry_as_a_type_and_gives_its_line(self) -> None:
        """F-0002 T1: the closed list of types names `raised-entry`, with its format, and an example entry."""
        template = read("templates", "usine.md")
        section = template[template.index("Les types sont fermés"):template.index("## Rapport")]
        for text in (
            "`raised-entry`", "Sans paramètre", "clé", "nombre", "`<clé>` seule", "`INVALID`",
            "`never-weaken` : `<scripts/baselines/types.txt | raised-entry>`",
        ):
            self.assertIn(text, section)


class ProjectPage(unittest.TestCase):
    def test_f0002_t1_the_page_gives_the_raised_entry_line_and_the_file_format(self) -> None:
        """F-0002 T1: the `docs/` page shows the `never-weaken` line, the lines of the file and what is refused."""
        page = read_root("docs", "regles-de-code.md")
        section = page[page.index("## La liste de référence"):]
        for text in (
            "`never-weaken`", "`<chemin> | raised-entry`", "`<nombre> <clé>`", "`<clé>` seule", "compte 1",
            "clé nouvelle", "nombre plus grand", "baisse", "`INVALID`", "paramètre",
        ):
            self.assertIn(text, section)


if __name__ == "__main__":
    unittest.main()
