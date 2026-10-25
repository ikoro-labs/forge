"""Ticket #101: la revue de bout en bout en boucle, déclenchée par la fusion, ses écarts repartis en construction."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support
from revue_boucle import main

USINE = "- `journey-paths` : `apps/web/`\n- `journey-paths` : `apps/api/routes/`\n"
HEADER = "| Identifiant | Lot | Ticket | Test | Écran | Capture | État | Jugé le |\n|---|---|---|---|---|---|---|---|\n"
MATRICE = HEADER + (
    "| EXI-01 | L1 | #5 | t1 | Écran 1 | | tenu | 2026-10-01 |\n"
    "| EXI-02 | L1 | #6 | t2 | Écran 2 | | absent | |\n"
    "| C01 | L2 | #6 | t3 | Écran 2 | | absent | |\n"
    "| EXI-03 | L2 | #7 | t4 | | | absent | |\n"
)


def run(argv: list[str], files: dict[str, str]) -> tuple[int, str]:
    """Run the script on a project copy; `{root}` in an argument is that copy. Exit code and standard output."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for name, text in files.items():
            (root / name).write_text(text, encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = main([part.replace("{root}", str(root)) for part in argv])
        return code, out.getvalue()


def declencher(changed: str, usine: str = USINE, *extra: str) -> tuple[int, str]:
    argv = ["declencher", "--files", "{root}/fichiers.txt", "--usine", "{root}/usine.md", *extra]
    return run(argv, {"fichiers.txt": changed, "usine.md": usine, "matrice.md": MATRICE})


class Trigger(unittest.TestCase):
    def test_a_merged_diff_that_touches_the_journey_triggers_the_review(self) -> None:
        """No F-NNNN: ticket #101, le déclenchement sur un diff qui touche le parcours (front ou API qu'il consomme)."""
        code, out = declencher("apps/web/src/saisie.tsx\ndocs/notes.md\n")
        self.assertEqual(code, 0)
        self.assertIn("PARCOURS-TOUCHE\tapps/web/src/saisie.tsx", out)
        self.assertIn("REVUE\tdeclenchee", out)
        code, out = declencher("apps/api/routes/releves.py\n")
        self.assertEqual(code, 0)
        self.assertIn("REVUE\tdeclenchee", out)

    def test_a_diff_that_leaves_the_journey_alone_does_not_trigger_it(self) -> None:
        """No F-NNNN: ticket #101, le déclenchement n'a pas lieu sur un diff qui ne touche pas le parcours."""
        code, out = declencher("docs/notes.md\nplugins/x.py\n")
        self.assertEqual(code, 1)
        self.assertIn("REVUE\tnon declenchee", out)
        self.assertNotIn("PARCOURS-TOUCHE", out)

    def test_without_journey_paths_nothing_is_guessed(self) -> None:
        """No F-NNNN: ticket #101, une clé absente rend l'étape sans objet, jamais un déclenchement deviné."""
        code, out = declencher("apps/web/src/saisie.tsx\n", usine="")
        self.assertEqual(code, 1)
        self.assertIn("sans objet (clé journey-paths absente)", out)
        self.assertNotIn("REVUE\tdeclenchee", out)

    def test_the_screens_to_play_are_those_of_the_merged_ticket(self) -> None:
        """No F-NNNN: ticket #101, la revue d'après fusion porte sur les écrans touchés : ceux que la matrice relie au ticket."""
        code, out = declencher("apps/web/a.tsx\n", USINE, "--matrice", "{root}/matrice.md", "--ticket", "#6")
        self.assertEqual(code, 0)
        self.assertIn("ECRAN\tÉcran 2\tEXI-02, C01", out)
        self.assertNotIn("Écran 1", out)

    def test_a_ticket_with_no_screen_row_is_reviewed_on_the_whole_path(self) -> None:
        """No F-NNNN: ticket #101, sans ligne d'écran pour le ticket, la revue prend le parcours en entier."""
        code, out = declencher("apps/web/a.tsx\n", USINE, "--matrice", "{root}/matrice.md", "--ticket", "#7")
        self.assertEqual(code, 0)
        self.assertIn("ECRAN\ttous\t", out)


def compte_rendu(ecarts: str = "bloquant 0, majeur 0, mineur 2", portee: str = "entière") -> str:
    return (
        "RESULT: REVUE\nFEATURE: F-0001\nCOUVERTURE: 8/10, 80 %\n"
        f"ECARTS: {ecarts}\nTICKETS: publiés (#12)\nPORTEE: {portee}\nRAPPORT: recette.md\nSYSTEME: Linux\n"
    )


def porte(text: str) -> tuple[int, str]:
    return run(["porte", "{root}/revue.txt"], {"revue.txt": text})


class Gate(unittest.TestCase):
    def test_the_recette_opens_at_zero_blocking_and_zero_major(self) -> None:
        """No F-NNNN: ticket #101, la porte de recette : zéro bloquant et zéro majeur, les mineurs restent au rapport."""
        code, out = porte(compte_rendu())
        self.assertEqual(code, 0)
        self.assertIn("OUVERTE", out)
        self.assertIn("mineur 2", out)

    def test_a_blocking_or_a_major_gap_keeps_the_recette_closed(self) -> None:
        """No F-NNNN: ticket #101, un bloquant ou un majeur ferme la porte de recette."""
        for ecarts in ("bloquant 1, majeur 0, mineur 0", "bloquant 0, majeur 3, mineur 0"):
            code, out = porte(compte_rendu(ecarts))
            self.assertEqual(code, 1, ecarts)
            self.assertIn("FERMEE", out)

    def test_a_partial_review_never_opens_the_recette(self) -> None:
        """No F-NNNN: ticket #101, la revue en entier précède la recette : une revue sur écrans touchés ne l'ouvre pas."""
        code, out = porte(compte_rendu(portee="écrans touchés"))
        self.assertEqual(code, 1)
        self.assertIn("FERMEE", out)

    def test_a_report_that_is_not_a_review_opens_nothing(self) -> None:
        """No F-NNNN: ticket #101, sans compte rendu de revue lisible, la porte reste fermée."""
        code, out = porte("RESULT: PR\nPR: #3\n")
        self.assertEqual(code, 1)
        self.assertIn("FERMEE", out)


def journal_run(*verdicts: str) -> tuple[int, str]:
    """Record each verdict as a round of the journal, then read the returns: the last call's code and output."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for text in verdicts:
            (root / "verdict.tsv").write_text(text, encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                main(["tour", str(root / "journal.tsv"), str(root / "verdict.tsv")])
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = main(["retours", str(root / "journal.tsv")])
        return code, out.getvalue()


def line(identifier: str, state: str) -> str:
    severity = "-" if state == "tenu" else "majeur"
    return f"ELEMENT\t{identifier}\t{state}\t{severity}\tÉcran 1\te1.png\tconstat\n"


class Loop(unittest.TestCase):
    def test_a_gap_seen_again_after_its_fix_is_a_return(self) -> None:
        """No F-NNNN: ticket #101, un écart encore non tenu au tour suivant revient une fois, la boucle continue."""
        code, out = journal_run(line("EXI-01", "absent"), line("EXI-01", "partiel"))
        self.assertEqual(code, 0)
        self.assertIn("RETOUR\tEXI-01\t1", out)
        self.assertNotIn("ARRET", out)

    def test_a_gap_that_returns_twice_stops_the_loop_and_goes_back_to_the_human(self) -> None:
        """No F-NNNN: ticket #101, l'arrêt sur un écart revenu deux fois, nommé par son identifiant de la source."""
        code, out = journal_run(line("EXI-01", "absent"), line("EXI-01", "partiel"), line("EXI-01", "absent"))
        self.assertEqual(code, 1)
        self.assertIn("ARRET\tEXI-01\t2", out)

    def test_a_fixed_gap_returns_nothing(self) -> None:
        """No F-NNNN: ticket #101, un écart repassé tenu ne revient pas et n'arrête rien."""
        code, out = journal_run(line("EXI-01", "absent"), line("EXI-01", "tenu"))
        self.assertEqual(code, 0)
        self.assertNotIn("RETOUR", out)

    def test_a_regression_counts_as_a_return(self) -> None:
        """No F-NNNN: ticket #101, un écart corrigé puis rouvert compte : l'identifiant, non le ticket, fait foi."""
        code, out = journal_run(line("EXI-01", "absent"), line("EXI-01", "tenu"), line("EXI-01", "contraire"), line("EXI-01", "tenu"))
        self.assertEqual(code, 0)
        self.assertIn("RETOUR\tEXI-01\t1", out)
        code, out = journal_run(line("EXI-01", "absent"), line("EXI-01", "tenu"), line("EXI-01", "contraire"),
                                line("EXI-01", "tenu"), line("EXI-01", "partiel"))
        self.assertEqual(code, 1)
        self.assertIn("ARRET\tEXI-01\t2", out)

    def test_another_element_is_counted_apart(self) -> None:
        """No F-NNNN: ticket #101, deux éléments différents ne s'additionnent pas."""
        code, out = journal_run(line("EXI-01", "absent") + line("C01", "tenu"), line("EXI-01", "tenu") + line("C01", "absent"))
        self.assertEqual(code, 0)
        self.assertNotIn("ARRET", out)

    def test_an_unreadable_verdict_never_enters_the_journal(self) -> None:
        """No F-NNNN: ticket #101, un verdict illisible n'entre pas au journal : le compte des retours reste fiable."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "verdict.tsv").write_text("n'importe quoi\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = main(["tour", str(root / "journal.tsv"), str(root / "verdict.tsv")])
            self.assertEqual(code, 1)
            self.assertFalse((root / "journal.tsv").exists())


def read(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


class Contents(unittest.TestCase):
    """Les skills disent la boucle que le script mesure."""

    def test_the_build_triggers_the_review_after_a_merge_with_no_timer_and_no_human_gesture(self) -> None:
        """No F-NNNN: ticket #101, le déclenchement par la fusion dans forge:feature-build, sur les écrans touchés."""
        skill = read("skills", "feature-build", "SKILL.md")
        for text in [
            "## 3 bis. La revue de bout en bout",
            'revue_boucle.py" declencher',
            "gh pr diff <n> --name-only",
            "Ni minuterie, ni geste humain",
            "forge:feature-review",
        ]:
            with self.subTest(text=text):
                self.assertIn(text, skill)

    def test_the_gaps_of_the_review_enter_the_passage_as_tickets_the_loop_publishes(self) -> None:
        """No F-NNNN: ticket #101, les tickets d'écart entrent dans le passage puis la revue rejoue le parcours."""
        build = read("skills", "feature-build", "SKILL.md")
        for text in ["sans accord de l'humain", "`ready-for-agent`", "sous-issues de l'issue de suivi", "rejoue le parcours"]:
            with self.subTest(text=text):
                self.assertIn(text, build)
        review = read("skills", "feature-review", "SKILL.md")
        self.assertIn("publie lui-même, sans accord de l'humain", review)
        self.assertNotIn("tant que la boucle de la revue", review)

    def test_the_recette_waits_for_the_gate_and_the_closure_for_the_whole_matrix(self) -> None:
        """No F-NNNN: ticket #101, la porte de recette de forge:feature-verify et la clôture à 100 % (#94)."""
        build = read("skills", "feature-build", "SKILL.md")
        self.assertIn('revue_boucle.py" porte', build)
        self.assertIn("zéro `bloquant` et zéro `majeur`", build)
        verify = read("skills", "feature-verify", "SKILL.md")
        self.assertIn("revue_boucle.py", verify)
        self.assertIn("zéro `bloquant` et zéro `majeur`", verify)
        self.assertIn("matrice.py --cloture", read("skills", "feature-close", "SKILL.md"))
        self.assertIn("PORTEE:", read("skills", "feature-review", "SKILL.md"))

    def test_the_caps_are_those_of_the_passage_and_the_stop_rests_on_a_measured_datum(self) -> None:
        """No F-NNNN: ticket #101, plafonds pris dans ceux du passage, arrêt sur un écart revenu deux fois."""
        build = read("skills", "feature-build", "SKILL.md")
        for text in [
            "aucun plafond de tours propre",
            "comptent dans `--max`",
            'revue_boucle.py" tour',
            'revue_boucle.py" retours',
            "identifiant de la source",
            "revenu deux fois",
            "`needs-your-attention`",
        ]:
            with self.subTest(text=text):
                self.assertIn(text, build)
