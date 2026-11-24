"""F-0002 A34, A35 and T2: the rule base of the template, the complete `docs/` page and the README summary."""

import re
import shlex
import unittest

import support


def read(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


def template_lines() -> list[str]:
    return support.PLUGIN.joinpath("templates", "usine.md").read_text(encoding="utf-8").splitlines()


def ruff_line() -> str:
    """The `lint-on-write` example line that runs ruff, without its `- `key` : `<...>`` wrapping."""
    for line in template_lines():
        if line.startswith("- `lint-on-write` : `<") and "ruff check --preview" in line:
            return line[len("- `lint-on-write` : `<"):-len(">`")]
    raise AssertionError("no `lint-on-write` example line runs `ruff check --preview`")


class RuleBaseInTheTemplate(unittest.TestCase):
    def command(self) -> list[str]:
        """The command of the ruff line, split as `after_write` splits it (a POSIX shell, no shell run)."""
        pattern, command = ruff_line().split(" | ", 1)
        self.assertEqual(pattern, "**/*.py")
        return shlex.split(command)

    def test_f0002_a34_the_ruff_line_pins_the_version_and_turns_the_preview_on(self) -> None:
        """F-0002 A34: the example line pins ruff to an exact version and passes `--preview` (PLR1702 is in preview)."""
        words = self.command()
        self.assertTrue(any(re.fullmatch(r"ruff==\d+\.\d+\.\d+", word) for word in words), words)
        self.assertIn("--preview", words)
        self.assertEqual(words[words.index("ruff") + 1], "check")

    def test_f0002_a34_the_ruff_line_sets_complexity_10_parameters_5_and_nesting_5(self) -> None:
        """F-0002 A34: C901 at 10, PLR0913 at 5 and PLR1702 at 5, each threshold written in clear."""
        words = self.command()
        self.assertIn("C901,PLR0913,PLR1702", words)
        configs = [words[i + 1] for i, word in enumerate(words) if word == "--config"]
        for setting in (
            "lint.mccabe.max-complexity=10", "lint.pylint.max-args=5", "lint.pylint.max-nested-blocks=5",
        ):
            self.assertIn(setting, configs)

    def test_f0002_a34_no_example_line_caps_a_length(self) -> None:
        """F-0002 A34: the base selects no statement-count, line-length or file-length rule, and the template says so."""
        line = ruff_line()
        for rule in ("PLR0915", "PLR0912", "E501", "max-statements", "line-length", "max-lines"):
            self.assertNotIn(rule, line)
        paragraph = read("templates", "usine.md")
        self.assertIn("aucun plafond de lignes", paragraph[paragraph.index("`C901`"):])

    def test_f0002_a34_the_template_explains_the_three_thresholds_and_the_pin(self) -> None:
        """F-0002 A34: the paragraph names the three rules, why the version is pinned and what `--select` does."""
        template = read("templates", "usine.md")
        section = template[template.index("La base de règles de code"):template.index("Les documents que le projet tient par hook")]
        for text in ("`C901`", "`PLR0913`", "`PLR1702`", "aperçu", "épingle", "`--select`", "base de règles"):
            self.assertIn(text, section)

    def test_f0002_a34_the_template_gives_the_form_of_a_module_map_next_to_architecture_check(self) -> None:
        """F-0002 A34: the `architecture-check` example is followed by the form of the map the command reads."""
        template = read("templates", "usine.md")
        section = template[template.index("- `architecture-check` : `<"):]
        section = section[:section.index("## Essai de bout en bout")]
        for text in (
            "<module> | <interface publique> | <dépend de>", "carte des modules", "forge ne lit pas",
            "`never-weaken` : `<docs/agents/modules.md | removed-line>`",
        ):
            self.assertIn(text, section)

    def test_f0002_a34_the_template_gives_an_example_of_the_stack_file(self) -> None:
        """F-0002 A34: next to the `stack` key line, two lines of the file, one per ecosystem."""
        template = read("templates", "usine.md")
        section = template[template.index("- `stack` : `<"):]
        section = section[:section.index("La mesure de la carte des modules")]
        for text in ("pypi | ", "npm | ", "<écosystème> | <paquet> | <source>"):
            self.assertIn(text, section)


if __name__ == "__main__":
    unittest.main()
