"""F-0002, ticket #308: the `stack` probe is run by the gate, judged by `forge:qc-conf` and documented."""

import unittest

import support


def read(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


def stack_paragraph() -> str:
    template = read("templates", "usine.md")
    section = template[template.index("`stack` : le fichier"):]
    return section[: section.index(" ## ")]


class TemplateDocumentsTheStackKey(unittest.TestCase):
    def test_the_key_names_one_file_of_three_field_lines(self) -> None:
        """F-0002 T1: `stack` is one path, and each line of that file is `<écosystème> | <paquet> | <source>`."""
        section = stack_paragraph()
        self.assertIn("- `stack` : `<", section)
        for text in ("<écosystème> | <paquet> | <source>", "`pypi`", "`npm`", "une seule ligne", "jamais complétée"):
            self.assertIn(text, section)

    def test_the_key_has_no_default_and_an_absent_key_is_not_applicable(self) -> None:
        """F-0002 T1: no default value, and the step is `sans objet` without the key."""
        section = stack_paragraph()
        self.assertIn("sans objet (clé `stack` absente)", section)
        self.assertIn("aucune valeur par défaut", section)

    def test_the_template_says_who_reads_it_and_what_the_judge_does(self) -> None:
        """F-0002 T1: the script, the base for the path, the head for the content, and the `BLOCKER`."""
        section = stack_paragraph()
        for text in ("scripts/stack_check.py", "base", "tête", "`UNLISTED`", "`NO SOURCE`", "`BLOCKER`", "`lockfile`"):
            self.assertIn(text, section)


if __name__ == "__main__":
    unittest.main()
