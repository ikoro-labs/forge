"""F-0002 C03: the gate's probe 17 replays the `architecture-check` command; a `FAIL` is a `BLOCKER` of the judge."""

import unittest

import support  # noqa: F401


def read(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


def probe_17(gate: str) -> str:
    section = gate[gate.index("17. **Contrôle d'architecture.**"):]
    return section[: section.index("Aux tours 2 et 3")]


class GateRunsTheArchitectureProbe(unittest.TestCase):
    def test_probe_17_runs_the_command_of_the_base_under_the_bounded_runner(self) -> None:
        """F-0002 A25: the command is read on the base, runs under `bounded_run.py` with `run-limits`, and yields three states."""
        section = probe_17(read("agents", "qc-gate.md"))
        for text in (
            "clé `architecture-check`", "usine-base.md", "sonde 10", "${CLAUDE_PLUGIN_ROOT}/scripts/bounded_run.py",
            "--usine usine-base.md --", "`run-limits`", "`PASS`", "`FAIL`", "`NOT RUN`", "verbatim",
        ):
            self.assertIn(text, section)

    def test_an_absent_key_is_not_applicable_and_never_pass(self) -> None:
        """F-0002 A26: without the key the probe says `sans objet`, and a run that did not happen is never `PASS`."""
        section = probe_17(read("agents", "qc-gate.md"))
        self.assertIn("sans objet (clé `architecture-check` absente)", section)
        self.assertIn("sans objet (clé `run-limits` absente)", section)
        self.assertIn("jamais `PASS`", section)

    def test_the_replay_mode_counts_seventeen_probes(self) -> None:
        """F-0002 A25: the sentence that lists the probes a replay does not redo stops at 17, not at 16."""
        gate = read("agents", "qc-gate.md")
        self.assertIn("les sondes 1 à 17, ni le tableau", gate)
        self.assertNotIn("les sondes 1 à 16", gate)

    def test_the_verbatim_list_of_the_output_names_probe_17(self) -> None:
        """F-0002 A25: the table's verbatim lines include the probe, or `forge:qc-conf` never sees them."""
        gate = read("agents", "qc-gate.md")
        tail = gate[gate.index("## Sortie"):]
        self.assertIn("les éléments verbatim des sondes 2, 5, 6, 7, 10, 11, 12, 13, 14, 15, 16 et 17", tail)


def judge_section() -> str:
    judge = read("agents", "qc-conf.md")
    section = judge[judge.index("## Contrôle d'architecture"):]
    return section[: section.index(" ## ")] if " ## " in section else section


class JudgeReadsTheArchitectureProbe(unittest.TestCase):
    def test_a_fail_is_a_blocker_under_f_15_that_cites_the_command_output(self) -> None:
        """F-0002 A27: a `FAIL` of the probe is a `BLOCKER` under rule `F-15`, with the command and its output as the scenario."""
        section = judge_section()
        for text in ("`FAIL`", "`BLOCKER`", "`F-15`", "recopie", "pas de `probe:`", "« déduit »"):
            self.assertIn(text, section)

    def test_not_run_and_an_absent_key_are_rendered_as_they_are(self) -> None:
        """F-0002 A27: `NOT RUN` goes to `GATES` as it is, never read as `PASS`; an absent key is `sans objet`, not none."""
        section = judge_section()
        for text in ("`NOT RUN`", "`GATES`", "architecture : sans objet", "jamais lue comme « aucune »", "jamais `PASS`"):
            self.assertIn(text, section)


if __name__ == "__main__":
    unittest.main()
