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


def read_root(*parts: str) -> str:
    return " ".join(support.REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8").split())


class CompletePage(unittest.TestCase):
    def page(self) -> str:
        return read_root("docs", "regles-de-code.md")

    def test_f0002_a35_a_table_names_every_key_with_the_format_of_its_line(self) -> None:
        """F-0002 A35: one list, every key of the feature, with the format of its line and what an absent key gives."""
        page = self.page()
        table = page[page.index("## Les clés, d'un coup d'oeil"):]
        table = table[:table.index(" ## ", 5)]
        for text in (
            "`stack`", "`lockfile`", "`never-weaken`", "`lint-on-write`", "`format-on-write`", "`architecture-check`",
            "`recurring-finding`", "`slo-issue`", "<écosystème> | <paquet> | <source>", "<chemin> | <écosystème>",
            "<chemin> | raised-entry", "<motif> | <commande>", "<seuil> | <jours>",
        ):
            self.assertIn(text, table)

    def test_f0002_a35_the_page_quotes_the_refusal_of_a_write_and_of_a_failed_architecture_check(self) -> None:
        """F-0002 A35: the message of a refused write, and the `BLOCKER` of a `FAIL` of the architecture probe."""
        page = self.page()
        section = page[page.index("## Les contrôles à l'écriture"):]
        section = section[:section.index(" ## ", 5)]
        for text in (
            "lint-on-write: <commande> failed on <chemin> (<raison>)", "code 2", "20 dernières lignes", "2000 octets",
            "30 s", "120 s", "ignorée", "`format-on-write`", "journal",
        ):
            self.assertIn(text, section)
        probe = page[page.index("## Le contrôle d'architecture"):]
        probe = probe[:probe.index(" ## ", 5)]
        for text in ("`PASS`", "`FAIL`", "`NOT RUN`", "`F-15`", "`BLOCKER`", "`removed-line`", "base"):
            self.assertIn(text, probe)

    def test_f0002_a35_the_page_says_how_a_recurring_finding_is_counted_and_where_it_goes(self) -> None:
        """F-0002 A35: distinct PRs per `F-n` or `L-n`, one comment of the `slo-issue` ticket, never a ticket."""
        page = self.page()
        section = page[page.index("## Le constat récurrent"):]
        section = section[:section.index(" ## ", 5)]
        for text in ("PR distinctes", "`F-n`", "`L-n`", "`slo-issue`", "jamais un ticket", "`recurring-finding`"):
            self.assertIn(text, section)

    def test_f0002_a35_the_page_gives_the_ruff_line_and_what_trying_it_on_forge_gave(self) -> None:
        """F-0002 A35: the rule base line, its three thresholds, the `--preview` pin, and the try on the forge repository."""
        page = self.page()
        section = page[page.index("## La base de règles"):]
        section = section[:section.index(" ## ", 5)]
        for text in (
            "`lint-on-write`", "ruff==0.17.3", "--preview", "`C901`", "`PLR0913`", "`PLR1702`", "10", "5",
            "aucun plafond de lignes", "essayés", "`plugins/forge`", "`tests`",
        ):
            self.assertIn(text, section)

    def test_f0002_a35_the_page_tells_what_is_proved_and_what_is_not_for_every_key(self) -> None:
        """F-0002 A35: the closing section names the tests that prove each key, and what was not tried."""
        page = self.page()
        section = page[page.index("## Ce qui est éprouvé"):]
        for text in (
            "tests/test_stack_check.py", "tests/test_never_weaken.py", "tests/test_after_write.py",
            "tests/test_recurring_findings.py", "Pas encore",
        ):
            self.assertIn(text, section)
        self.assertNotIn("viennent avec leurs tickets", section)


class ReadmeSummary(unittest.TestCase):
    def row(self) -> str:
        readme = support.REPO_ROOT.joinpath("README.md").read_text(encoding="utf-8")
        rows = [line for line in readme.splitlines() if line.startswith("| [`docs/regles-de-code.md`]")]
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def test_f0002_t2_the_readme_links_the_page_in_its_table_of_pages(self) -> None:
        """F-0002 T2: one row of "Aller plus loin" links `docs/regles-de-code.md`, and the file exists."""
        self.assertIn("](docs/regles-de-code.md)", self.row())
        self.assertTrue(support.REPO_ROOT.joinpath("docs", "regles-de-code.md").is_file())

    def test_f0002_t2_the_readme_summarises_the_keys_the_page_treats(self) -> None:
        """F-0002 T2: the row names every key of the page and the human gesture, in one line."""
        row = self.row()
        for key in (
            "stack", "lockfile", "never-weaken", "lint-on-write", "format-on-write", "architecture-check",
            "recurring-finding", "slo-issue",
        ):
            self.assertIn(f"`{key}`", row)
        self.assertIn("dépendance", row)


if __name__ == "__main__":
    unittest.main()
