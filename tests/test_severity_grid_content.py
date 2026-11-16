"""Ticket #68: the judge's severity is fixed by class, and a BLOCKER that rests on an execution is replayed."""

import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import support
from cases import PullRequest, rules, verdict_problems
from parse_output import parse_verdict


def read(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


def section(text: str, title: str) -> str:
    start = text.index(title)
    end = text.find(" ## ", start + len(title))
    return text[start:end] if end != -1 else text[start:]


class Grid(unittest.TestCase):
    def grid(self) -> str:
        return section(read("agents", "qc-conf.md"), "## Gravité par classe")

    def test_the_judge_does_not_choose_the_severity_of_three_classes(self) -> None:
        """No F-NNNN: ticket #68, critère 1: la gravité de trois classes est fixée, sans choix du juge."""
        grid = self.grid()
        self.assertIn("n'est pas à ton choix", grid)
        self.assertIn("tu ne la baisses pas", grid)
        self.assertGreaterEqual(grid.count("`BLOCKER`"), 3)

    def test_an_evasion_of_a_guard_is_a_blocker_even_partial_and_beside_the_ticket(self) -> None:
        """No F-NNNN: ticket #68, critère 1: toute évasion d'un garde, de never-weaken ou d'un chemin protégé est un BLOCKER."""
        grid = self.grid()
        for text in ("garde", "`never-weaken`", "chemin protégé", "Même partielle", "même à côté du périmètre du ticket", "`F-25`"):
            with self.subTest(text=text):
                self.assertIn(text, grid)
        self.assertIn("`NOTE` `out of diff`", grid)

    def test_a_test_that_cannot_fail_on_the_old_code_is_a_blocker(self) -> None:
        """No F-NNNN: ticket #68, critère 1: un test qui ne peut pas échouer sur l'ancien code est un BLOCKER."""
        grid = self.grid()
        self.assertIn("ne peut pas échouer sur l'ancien code", grid)
        self.assertIn("`PASSES`", grid)
        self.assertIn("tautologique", grid)
        self.assertIn("`F-9`", grid)
        self.assertIn("`F-10`", grid)
        self.assertIn("Même quand un autre test prouve le critère", grid)

    def test_a_sentence_of_the_pr_proved_false_is_a_blocker(self) -> None:
        """No F-NNNN: ticket #68, critère 1: une phrase de la PR prouvée fausse est un BLOCKER, corrigée avant la fusion."""
        grid = self.grid()
        for text in ("prouvée fausse", "documentation", "docstring", "Preuves", "avant la fusion", "`F-26`"):
            with self.subTest(text=text):
                self.assertIn(text, grid)

    def test_the_two_readings_of_a_test_agree_with_the_grid(self) -> None:
        """No F-NNNN: ticket #68, critère 1: les sections de lecture des tests ne rebaissent pas ce que la grille fixe."""
        judge = read("agents", "qc-conf.md")
        reading = section(judge, "## Lecture des tests")
        self.assertIn("un test **tautologique** est un `BLOCKER`", reading)
        replay = section(judge, "## Lecture du rejeu sur la base")
        self.assertIn("`BLOCKER`", replay)
        self.assertNotIn("`MINOR` sinon", replay)

    def test_the_other_sections_keep_their_own_severity(self) -> None:
        """No F-NNNN: ticket #68, critère 1: le reste de la gravité reste au juge, sur les règles citées."""
        grid = self.grid()
        self.assertIn("Tout le reste", grid)
        self.assertIn("socle", grid)

    def test_the_judge_stays_generic(self) -> None:
        """No F-NNNN: ticket #68, critère 1: aucun numéro de ticket, nom de projet ou de personne dans les textes du plugin."""
        for parts in (("agents", "qc-conf.md"), ("agents", "qc-gate.md"), ("skills", "qc", "SKILL.md"), ("socle.md",)):
            with self.subTest(file="/".join(parts)):
                self.assertIsNone(re.search(r"#\d+", read(*parts)))


class Socle(unittest.TestCase):
    def test_the_socle_holds_the_two_rules_the_grid_cites(self) -> None:
        """No F-NNNN: ticket #68, critère 1: F-25 et F-26 existent au socle, avec la sonde qui les mesure."""
        text = (support.PLUGIN / "socle.md").read_text(encoding="utf-8")
        row25 = next(line for line in text.splitlines() if line.startswith("| F-25 |"))
        row26 = next(line for line in text.splitlines() if line.startswith("| F-26 |"))
        self.assertIn("| code |", row25)
        self.assertIn("`never-weaken`", row25)
        self.assertIn("`protected-path`", row25)
        self.assertIn("probe_replay.py", row25)
        self.assertIn("| prose |", row26)
        self.assertIn("probe_replay.py", row26)

    def test_the_one_prose_rule_that_rejects_is_named(self) -> None:
        """No F-NNNN: ticket #68, critère 1: F-26 est la seule règle de prose qui rejette, et le socle le dit."""
        text = " ".join((support.PLUGIN / "socle.md").read_text(encoding="utf-8").split())
        self.assertIn("is a `MINOR` and does not reject, except F-26", text)

    def test_a_verdict_citing_them_passes_the_guard_of_the_cases(self) -> None:
        """No F-NNNN: ticket #68, critère 1: un BLOCKER qui cite F-25 ou F-26 n'est pas refusé par guard_cases."""
        known = rules(Path(support.REPO_ROOT), {})
        self.assertEqual(known["F-25"], "code")
        pr = PullRequest(7, "Refs #1", datetime(2026, 11, 16, tzinfo=timezone.utc))
        for rule in ("F-25", "F-26"):
            text = (
                "VERDICT: REJECT\nROUND: 1\nHEAD: abcdef1\nSPEC: none (a reason)\nFINDINGS:\n"
                f"- [BLOCKER] a.py:1 | {rule} | x | probe: `ls` => `a.py`\nGATES: ok\n"
            )
            with self.subTest(rule=rule):
                self.assertEqual(verdict_problems(text, pr, [], datetime(2026, 11, 1).date(), {}, known), [])


class Probe(unittest.TestCase):
    def sonde(self) -> str:
        return section(read("agents", "qc-conf.md"), "## Sonde d'un BLOCKER")

    def test_a_blocker_that_rests_on_an_execution_carries_its_probe(self) -> None:
        """No F-NNNN: ticket #68, critère 2: la commande exacte et la sortie attendue, en dernier champ du constat."""
        sonde = self.sonde()
        self.assertIn("probe: `<commande exacte>` => `<sortie attendue>`", sonde)
        self.assertIn("dernier champ", sonde)
        self.assertIn("sans backtick", sonde)
        self.assertIn("Le code de sortie n'est pas lu", sonde)

    def test_the_gate_replays_it_before_the_blocker_counts(self) -> None:
        """No F-NNNN: ticket #68, critère 2: forge:qc la fait rejouer par forge:qc-gate avant que le BLOCKER compte."""
        sonde = self.sonde()
        self.assertIn("`forge:qc` fait rejouer", sonde)
        self.assertIn("`forge:qc-gate`", sonde)
        self.assertIn("avant que le `BLOCKER` compte", sonde)
        self.assertIn("`NOTE` « non reproduit »", sonde)
        self.assertIn("le rapport le dit", sonde)

    def test_a_blocker_without_an_execution_counts_and_is_marked_deduced(self) -> None:
        """No F-NNNN: ticket #68, critère 3: lecture du code seule : le BLOCKER compte, et le rapport le marque « déduit »."""
        sonde = self.sonde()
        self.assertIn("lecture du code seule", sonde)
        self.assertIn("compte", sonde)
        self.assertIn("« déduit »", sonde)
        self.assertIn("n'inventes pas de sonde", sonde)

    def test_the_example_the_judge_is_given_is_one_the_parser_reads(self) -> None:
        """No F-NNNN: ticket #68, critère 4: l'exemple de constat à sonde du prompt est lu par parse_output.py."""
        judge = (support.PLUGIN / "agents" / "qc-conf.md").read_text(encoding="utf-8")
        example = next(line for line in judge.splitlines() if line.startswith("- [BLOCKER]") and "probe:" in line)
        text = f"VERDICT: REJECT\nROUND: 1\nHEAD: 3f2a9c1\nSPEC: none (a reason)\nFINDINGS:\n{example}\nGATES: ok\n"
        finding = cast("list[dict[str, Any]]", parse_verdict(text)["FINDINGS"])[0]
        self.assertIsNotNone(finding["probe"])
        self.assertEqual(finding["mark"], "")

    def test_the_output_section_of_the_judge_shows_the_probe_field(self) -> None:
        """No F-NNNN: ticket #68, critère 2: la forme de sortie dit que le BLOCKER peut porter sa sonde."""
        judge = read("agents", "qc-conf.md")
        output = judge[judge.index("## Sortie"):]
        self.assertIn("probe: `<commande exacte>` => `<sortie attendue>`", output)


if __name__ == "__main__":
    unittest.main()
