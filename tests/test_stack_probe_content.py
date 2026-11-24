"""F-0002, ticket #308: the `stack` probe is run by the gate, judged by `forge:qc-conf` and documented."""

import unittest

import support


def read(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


def read_root(*parts: str) -> str:
    return " ".join(support.REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8").split())


def probe_16(gate: str) -> str:
    section = gate[gate.index("16. **Dépendances permises.**"):]
    return section[: section.index("Aux tours 2 et 3")]


class GateRunsTheStackProbe(unittest.TestCase):
    def test_probe_16_runs_the_script_on_the_refs_with_the_keys_of_the_base(self) -> None:
        """F-0002 A3: the path of the `stack` key is read on the base, so a PR does not lift the list it is judged by."""
        section = probe_16(read("agents", "qc-gate.md"))
        for text in (
            "${CLAUDE_PLUGIN_ROOT}/scripts/stack_check.py", "--usine usine-base.md", "--base origin/<base>",
            "--head <tête>", "sonde 10", "clone du projet",
        ):
            self.assertIn(text, section)

    def test_an_absent_key_is_not_applicable_and_never_pass(self) -> None:
        """F-0002 A3: without the key `stack` the probe says so, and the failing cases are never `PASS`."""
        section = probe_16(read("agents", "qc-gate.md"))
        for text in (
            "sans objet (clé stack absente)", "sans objet (clé lockfile absente)", "jamais `PASS`", "verbatim",
            "`UNLISTED`", "`NO SOURCE`", "`ADDED`", "`NOT RUN`", "`INVALID`",
        ):
            self.assertIn(text, section)

    def test_the_replay_mode_counts_sixteen_probes(self) -> None:
        """F-0002 A3: the sentence that lists the probes a replay does not redo stops at 16, not at 14."""
        gate = read("agents", "qc-gate.md")
        self.assertIn("les sondes 1 à 17, ni le tableau", gate)
        self.assertNotIn("les sondes 1 à 14", gate)

    def test_the_verbatim_list_of_the_output_names_probe_16(self) -> None:
        """F-0002 A3: the table's verbatim lines include the probe, or `forge:qc-conf` never sees them."""
        gate = read("agents", "qc-gate.md")
        tail = gate[gate.index("## Sortie"):]
        self.assertIn("les éléments verbatim des sondes 2, 5, 6, 7, 10, 11, 12, 13, 14, 15, 16 et 17", tail)


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


def judge_section() -> str:
    judge = read("agents", "qc-conf.md")
    section = judge[judge.index("## Dépendances permises"):]
    return section[: section.index(" ## ")] if " ## " in section else section


class JudgeReadsTheStackProbe(unittest.TestCase):
    def test_an_unlisted_or_unsourced_package_is_a_blocker_that_cites_the_line_to_write(self) -> None:
        """F-0002 A10: `UNLISTED` and `NO SOURCE` are `BLOCKER`s under rule `F-8`, with the line to write as the scenario."""
        section = judge_section()
        for text in ("`UNLISTED`", "`NO SOURCE`", "`BLOCKER`", "`F-8`", "ligne à écrire", "pas de `probe:`","« déduit »"):
            self.assertIn(text, section)

    def test_not_run_and_invalid_are_rendered_as_they_are(self) -> None:
        """F-0002 A10: `NOT RUN` and `INVALID` go to `GATES`, never read as `OK` or as no dependency added."""
        section = judge_section()
        for text in ("`NOT RUN`", "`INVALID`", "`GATES`", "stack : sans objet", "jamais lue comme « aucune »", "jamais `OK`"):
            self.assertIn(text, section)

    def test_an_added_list_line_is_read_for_its_source(self) -> None:
        """F-0002 A10: an `ADDED` line is not a finding by itself; its source is read under `F-8`."""
        section = judge_section()
        self.assertIn("`ADDED`", section)
        self.assertIn("source", section[section.index("`ADDED`"):])


class ProjectPage(unittest.TestCase):
    """F-0002 A35 (start): the `docs/` page of the feature gives the `stack` format, the refusal and the human gesture."""

    def page(self) -> str:
        return read_root("docs", "regles-de-code.md")

    def test_the_page_gives_the_format_of_a_line_and_the_closed_ecosystems(self) -> None:
        """F-0002 A35: the key, the line `<écosystème> | <paquet> | <source>`, `pypi` and `npm`, and the absent key."""
        page = self.page()
        for text in (
            "`stack`", "<écosystème> | <paquet> | <source>", "`pypi`", "`npm`", "`INVALID`",
            "sans objet (clé `stack` absente)", "stack_check.py", "`lockfile`",
        ):
            self.assertIn(text, page)

    def test_the_page_quotes_the_refusal_message_with_the_line_to_write(self) -> None:
        """F-0002 A35: the first refusal gives the line to write and the path of the file, never a mute refusal."""
        page = self.page()
        for text in ("`UNLISTED`", "`NO SOURCE`", "ligne à écrire : `pypi | <paquet> | <ADR ou séance>` dans <chemin de la liste>", "`BLOCKER`"):
            self.assertIn(text, page)

    def test_the_page_says_what_the_human_does_to_accept_a_dependency(self) -> None:
        """F-0002 A35: the gesture that accepts a dependency, and why a PR cannot accept its own."""
        page = self.page()
        gesture = page[page.index("## Accepter une dépendance"):]
        for text in ("décision", "ADR", "séance", "`ADDED`", "base", "tête", "ligne"):
            self.assertIn(text, gesture)

    def test_the_page_says_what_was_tried_and_what_was_not(self) -> None:
        """F-0002 A35: a sentence says what is proved, and what was not tried."""
        self.assertRegex(self.page(), r"(?i)éprouvé")
        self.assertRegex(self.page(), r"(?i)pas encore")


if __name__ == "__main__":
    unittest.main()
