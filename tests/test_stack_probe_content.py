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
        self.assertIn("les sondes 1 à 16, ni le tableau", gate)
        self.assertNotIn("les sondes 1 à 14", gate)

    def test_the_verbatim_list_of_the_output_names_probe_16(self) -> None:
        """F-0002 A3: the table's verbatim lines include the probe, or `forge:qc-conf` never sees them."""
        gate = read("agents", "qc-gate.md")
        tail = gate[gate.index("## Sortie"):]
        self.assertIn("les éléments verbatim des sondes 2, 5, 6, 7, 10, 11, 12, 13, 14, 15 et 16", tail)


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
