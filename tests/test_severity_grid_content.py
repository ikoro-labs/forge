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
                f"- [BLOCKER] a.py:1 | {rule} | x | probe: `tests/test_a.py` => `a.py`\nGATES: ok\n"
            )
            with self.subTest(rule=rule):
                self.assertEqual(verdict_problems(text, pr, [], datetime(2026, 11, 1).date(), {}, known), [])


class Probe(unittest.TestCase):
    def sonde(self) -> str:
        return section(read("agents", "qc-conf.md"), "## Sonde d'un BLOCKER")

    def test_a_blocker_that_rests_on_an_execution_carries_its_probe(self) -> None:
        """No F-NNNN: ticket #68, critère 2: le fichier de test et la sortie attendue, en dernier champ du constat."""
        sonde = self.sonde()
        self.assertIn("probe: `<fichier de test de la tête>` => `<sortie attendue>`", sonde)
        self.assertIn("dernier champ", sonde)
        self.assertIn("Le code de sortie n'est pas lu", sonde)

    def test_the_probe_is_a_test_file_run_by_the_key_never_a_command(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: la sonde nomme un fichier de test de la tête, lancé par red-replay ; rien du juge n'est exécuté."""
        sonde = self.sonde()
        self.assertIn("clé `red-replay`", sonde)
        self.assertIn("clé `test-path`", sonde)
        self.assertIn("Rien de ce que tu écris n'est exécuté comme commande", sonde)
        self.assertIn("refusé et rapporté, jamais lancé", sonde)
        for refused in ("chemin absolu", "`..`", "caractère de shell"):
            with self.subTest(refused=refused):
                self.assertIn(refused, sonde)
        self.assertNotIn("commande exacte", sonde)

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
        self.assertIn("probe: `<fichier de test de la tête>` => `<sortie attendue>`", output)


class Gate(unittest.TestCase):
    def mode(self) -> str:
        return section(read("agents", "qc-gate.md"), "## Mode rejeu des sondes")

    def test_the_gate_replays_the_probes_under_the_bounded_launcher_in_a_copy_of_the_head(self) -> None:
        """No F-NNNN: ticket #68, critère 2: le mode sondes lance probe_replay.py dans une copie de la tête, bornes lues sur la base."""
        mode = self.mode()
        self.assertIn("`MODE: probes`", mode)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/probe_replay.py", mode)
        self.assertIn('--usine "<scratchpad>/usine-base.md"', mode)
        self.assertIn("--root", mode)
        self.assertIn("copie de la tête", mode)
        self.assertIn("bounded_run.py", mode)

    def test_the_gate_copies_the_lines_and_judges_nothing(self) -> None:
        """No F-NNNN: ticket #68, critère 2: les lignes du script sont recopiées verbatim, avec leur code de sortie."""
        mode = self.mode()
        self.assertIn("verbatim", mode)
        for status in ("`CONFIRMED`", "`NOT REPRODUCED`", "`REFUSED`", "`NOT RUN`", "`DEDUCED`"):
            with self.subTest(status=status):
                self.assertIn(status, mode)
        self.assertIn("Tu ne juges pas une sonde", mode)
        self.assertIn("jamais `CONFIRMED`", mode)

    def test_the_other_probes_do_not_run_in_that_mode(self) -> None:
        """No F-NNNN: ticket #68, critère 2: ce mode ne refait aucune des autres sondes, il ne rend aucun tableau."""
        mode = self.mode()
        self.assertIn("aucune autre sonde", mode)
        self.assertIn("pas de tableau", mode)


class Skill(unittest.TestCase):
    def skill(self) -> str:
        return read("skills", "qc", "SKILL.md")

    def test_qc_has_the_gate_replay_the_probes_then_counts_the_blockers(self) -> None:
        """No F-NNNN: ticket #68, critère 2 et 4: forge:qc rejoue les sondes par forge:qc-gate, puis applique la règle de comptage."""
        skill = self.skill()
        step = skill[skill.index("4. **Lire le verdict.**"):skill.index("5. **Poster.**")]
        self.assertIn("`probe:`", step)
        self.assertIn("`MODE: probes`", step)
        self.assertIn("parse_output.py", step)
        self.assertIn("--replay", step)
        self.assertIn("--rewrite", step)
        self.assertIn("poste le verdict qui tient", step)

    def test_an_unsettled_probe_stops_the_review_without_a_verdict(self) -> None:
        """No F-NNNN: ticket #68, critère 2: un code 3 (sonde NOT RUN) ne fusionne pas et ne poste pas : needs-your-attention."""
        skill = self.skill()
        step = skill[skill.index("4. **Lire le verdict.**"):skill.index("5. **Poster.**")]
        self.assertIn("Code 3", step)
        self.assertIn("ne fusionne pas", step)
        self.assertIn("needs-your-attention", step)

    def test_a_refused_probe_sends_the_verdict_back_to_the_judge(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: une sonde refusée (`REFUSED`) sort en 1, et le juge est relancé une fois."""
        skill = self.skill()
        step = skill[skill.index("4. **Lire le verdict.**"):skill.index("5. **Poster.**")]
        self.assertIn("`REFUSED`", step)
        self.assertIn("Code 1 : une sonde est mal formée ou refusée", step)

    def test_the_one_pass_review_replays_the_probes_too(self) -> None:
        """No F-NNNN: ticket #68, critère 2: une PR de prose, en une passe, a ses sondes rejouées elle aussi."""
        skill = self.skill()
        passes = section(skill, "## Une passe ou deux")
        self.assertIn("`MODE: probes`", passes)

    def test_the_report_marks_deduced_and_not_reproduced_blockers(self) -> None:
        """No F-NNNN: ticket #68, critère 2 et 3: le rapport dit chaque BLOCKER déduit et chaque BLOCKER non reproduit."""
        skill = self.skill()
        report = skill[skill.index("## Rapport d'agent"):]
        self.assertIn("« déduit »", report)
        self.assertIn("« non reproduit »", report)
        self.assertIn("`REX`", report)


class Documentation(unittest.TestCase):
    def test_the_template_and_the_page_document_the_replay_and_what_was_not_tried(self) -> None:
        """No F-NNNN: ticket #68, critère 2: le gabarit et la page de configuration disent la sonde, sa borne et ce qui n'est pas éprouvé."""
        template = read("templates", "usine.md")
        self.assertIn("probe_replay.py", template)
        self.assertIn("sans objet (clé `run-limits` absente)", template[template.index("probe_replay.py"):])
        page = " ".join((support.REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8").split())
        part = page[page.index("probe_replay.py"):]
        self.assertIn("nom d'un fichier de test de la tête", part)
        self.assertIn("Éprouvé sous Linux seulement", part)


class Closed(unittest.TestCase):
    """Retour de revue : la sonde est fermée. Elle nomme un fichier de test de la tête, jamais une commande."""

    def texts(self) -> dict[str, str]:
        page = " ".join((support.REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8").split())
        template = read("templates", "usine.md")
        return {
            "qc-conf": section(read("agents", "qc-conf.md"), "## Sonde d'un BLOCKER"),
            "qc-gate": section(read("agents", "qc-gate.md"), "## Mode rejeu des sondes"),
            "qc": read("skills", "qc", "SKILL.md"),
            "usine": template[template.index("probe_replay.py"):template.index("Le rejeu des tests d'une PR sur sa base")],
            "installation": page[page.index("probe_replay.py"):page.index("Deux clés, `ui-labels`")],
        }

    def test_the_judge_and_the_gate_say_the_test_runs_in_a_copy_without_git(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: la copie de la tête est faite par `git archive`, sans `.git`."""
        texts = self.texts()
        self.assertIn("`git archive`", texts["qc-gate"])
        self.assertIn("sans `.git`", texts["qc-gate"])
        self.assertNotIn("worktree détaché", texts["qc-gate"])
        self.assertIn("sans `.git`", texts["qc-conf"])

    def test_every_text_says_the_probe_is_a_test_file_run_by_red_replay(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: chaque texte dit que la sonde est un fichier de test lancé par la clé red-replay."""
        for name, text in self.texts().items():
            with self.subTest(text=name):
                self.assertIn("`red-replay`", text)
                self.assertIn("fichier de test", text)

    def test_no_text_promises_an_isolation_the_probe_does_not_have(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: la prose de l'environnement vidé, fausse au tour 2, a disparu, et le reste est dit."""
        texts = self.texts()
        for name, text in texts.items():
            with self.subTest(text=name):
                self.assertNotIn("environnement vidé", text)
                self.assertNotIn("ne porte pas l'accès", text)
                self.assertNotIn("`SSH_AUTH_SOCK`", text)
        for name in ("qc-conf", "qc-gate", "installation"):
            with self.subTest(text=name):
                self.assertIn("droits de la session", texts[name])


if __name__ == "__main__":
    unittest.main()
