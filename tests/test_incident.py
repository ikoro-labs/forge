"""Ticket #61: `incident.py` lit la revue sans blâme d'un incident et refuse celle qui n'a pas de correctif.

Chaque test nomme son ticket et son critère (`ticket #61, critère N`), le ticket n'ayant pas de feature :

1. le gabarit de revue (`templates/incident.md`) et ses sections ;
2. une revue sans correctif est refusée, une consigne seule n'est pas un correctif ;
3. la classe du correctif, `mécanique` ou `jugement`, et la forme qu'elle exige.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import support
from incident import CLASSES, SECTIONS, check, main

TEMPLATE = support.PLUGIN / "templates" / "incident.md"


def review(
    klass: str = "mécanique",
    fixes: tuple[str, ...] = ("#64",),
    origin: str = "usine",
    facts: str = "- 2026-10-24 : un commit de branche ferme un ticket que la PR cite en `Refs`.",
    cause: str = "Le message d'un commit de branche arrive sur la base sans que rien le relise.",
) -> str:
    lines = [
        "# Un commit de branche ferme un ticket",
        "",
        "- Date : 2026-10-24",
        f"- Origine : {origin}",
        f"- Classe : {klass}",
        "",
        "## Faits",
        "",
        facts,
        "",
        "## Cause",
        "",
        cause,
        "",
        "## Ce qui l'a laissé passer",
        "",
        "Le garde ne lit que le corps de la PR et sa description.",
        "",
        "## Correctif",
        "",
        *[f"- Correctif : {fix}" for fix in fixes],
        "",
    ]
    return "\n".join(lines)


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = main(list(argv))
    return code, out.getvalue()


class Template(unittest.TestCase):
    def test_the_template_holds_each_section_the_reader_requires(self) -> None:
        """Ticket #61, critère 1 : le gabarit porte les faits datés, la cause, ce qui l'a laissé passer, le correctif."""
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertEqual(SECTIONS, ("Faits", "Cause", "Ce qui l'a laissé passer", "Correctif"))
        for section in SECTIONS:
            with self.subTest(section=section):
                self.assertIn(f"\n## {section}\n", text)
        for field in ("Date", "Origine", "Classe"):
            self.assertIn(f"- {field} :", text)

    def test_the_template_names_both_classes_and_the_three_forms_of_fix(self) -> None:
        """Ticket #61, critère 1 : le gabarit dit les deux classes et ce que chacune accepte comme correctif."""
        text = TEMPLATE.read_text(encoding="utf-8")
        for word in ("mécanique", "jugement", "#<n>", "existant :", "cas :"):
            with self.subTest(word=word):
                self.assertIn(word, text)

    def test_the_template_left_unfilled_is_refused(self) -> None:
        """Ticket #61, critère 1 : un gabarit dont les `<...>` n'ont pas été remplis n'est pas une revue."""
        errors = check(TEMPLATE.read_text(encoding="utf-8"), None)
        self.assertTrue(any("gabarit" in error for error in errors), errors)

    def test_a_filled_review_is_read(self) -> None:
        """Ticket #61, critère 1 : une revue complète passe, sans aucune erreur."""
        self.assertEqual(check(review(), None), [])

    def test_a_review_without_a_dated_fact_is_refused(self) -> None:
        """Ticket #61, critère 1 : les faits sont datés, un récit sans date est refusé."""
        errors = check(review(facts="- Un commit a fermé un ticket."), None)
        self.assertTrue(any("fait daté" in error for error in errors), errors)

    def test_a_review_missing_a_section_or_a_field_is_refused(self) -> None:
        """Ticket #61, critère 1 : chaque section et chaque champ manquant est dit par son nom."""
        text = review().replace("## Cause\n", "## Autre chose\n").replace("- Date : 2026-10-24\n", "- Date : hier\n")
        errors = " ".join(check(text, None))
        self.assertIn("Cause", errors)
        self.assertIn("Date", errors)

    def test_the_origin_is_a_severity_or_the_factory(self) -> None:
        """Ticket #61, critère 1 : `sev1`, `sev2` ou `usine`, ce que le skill traite."""
        for origin in ("sev1", "sev2", "usine"):
            with self.subTest(origin=origin):
                self.assertEqual(check(review(origin=origin), None), [])
        self.assertTrue(any("Origine" in error for error in check(review(origin="sev3"), None)))


class RefusalWithoutFix(unittest.TestCase):
    def test_a_review_without_a_fix_is_refused(self) -> None:
        """Ticket #61, critère 2 : une revue sans ligne `Correctif :` est refusée."""
        errors = check(review(fixes=()), None)
        self.assertTrue(any("correctif" in error.lower() for error in errors), errors)

    def test_a_guideline_or_a_memory_note_alone_is_not_a_fix(self) -> None:
        """Ticket #61, critère 2 : une consigne ou une entrée de mémoire seule n'est jamais un correctif suffisant."""
        for fix in ("rappeler aux agents de ne pas écrire Closes", "entrée de mémoire du poste", "à voir"):
            with self.subTest(fix=fix):
                errors = check(review(fixes=(fix,)), None)
                self.assertTrue(any("consigne" in error for error in errors), errors)

    def test_the_command_refuses_with_a_non_zero_code_and_says_why(self) -> None:
        """Ticket #61, critère 2 : `incident.py check` sort en 1 sur une revue sans correctif."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-10-24-sans-correctif.md"
            path.write_text(review(fixes=()), encoding="utf-8")
            code, output = run("check", str(path))
        self.assertEqual(code, 1)
        self.assertIn("correctif", output.lower())

    def test_the_command_accepts_a_review_with_a_fix(self) -> None:
        """Ticket #61, critère 2 : `incident.py check` sort en 0 et dit la classe."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2026-10-24-avec-correctif.md"
            path.write_text(review(), encoding="utf-8")
            code, output = run("check", str(path))
        self.assertEqual(code, 0)
        self.assertIn("mécanique", output)

    def test_an_unreadable_file_is_a_wrong_call(self) -> None:
        """Ticket #61, critère 2 : un fichier introuvable sort en 2, pas en 0."""
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = run("check", str(Path(tmp) / "absent.md"))
        self.assertEqual(code, 2)


class ClassOfTheFix(unittest.TestCase):
    def test_the_two_classes_are_mechanical_and_judgment(self) -> None:
        """Ticket #61, critère 3 : deux classes, ni plus ni moins."""
        self.assertEqual(CLASSES, ("mécanique", "jugement"))

    def test_a_mechanical_fix_is_a_ticket_or_an_existing_control_with_its_test(self) -> None:
        """Ticket #61, critère 3 : `#n`, ou `existant : <contrôle> ; <test>`."""
        for fix in ("#64", "existant : plugins/forge/hooks/guard_git.py ; tests/test_guard_git.py"):
            with self.subTest(fix=fix):
                self.assertEqual(check(review("mécanique", (fix,)), None), [])

    def test_an_existing_control_without_its_test_is_refused(self) -> None:
        """Ticket #61, critère 3 : un contrôle sans test n'est pas un correctif mécanique."""
        errors = check(review("mécanique", ("existant : plugins/forge/hooks/guard_git.py",)), None)
        self.assertTrue(any("test" in error for error in errors), errors)

    def test_a_judgment_fix_is_a_case_of_the_reference_set(self) -> None:
        """Ticket #61, critère 3 : `cas : <dossier du cas>`."""
        self.assertEqual(check(review("jugement", ("cas : plugins/forge/evals/blocker-pr99-tour1",)), None), [])

    def test_the_form_must_match_the_class(self) -> None:
        """Ticket #61, critère 3 : un cas n'est pas un correctif mécanique, un ticket n'en est pas un de jugement."""
        wrong = [
            review("mécanique", ("cas : plugins/forge/evals/blocker-pr99-tour1",)),
            review("jugement", ("#64",)),
            review("jugement", ("existant : a.py ; tests/test_a.py",)),
        ]
        for text in wrong:
            with self.subTest(text=text.splitlines()[4]):
                errors = check(text, None)
                self.assertTrue(any("classe" in error for error in errors), errors)

    def test_an_unknown_class_is_refused(self) -> None:
        """Ticket #61, critère 3 : une troisième classe n'existe pas."""
        errors = check(review("consigne", ("#64",)), None)
        self.assertTrue(any("Classe" in error for error in errors), errors)

    def test_the_class_is_read_without_its_accent(self) -> None:
        """Ticket #61, critère 3 : `mecanique` vaut `mécanique`, un clavier sans accent n'est pas une faute."""
        self.assertEqual(check(review("mecanique", ("#64",)), None), [])

    def test_cited_paths_must_exist_when_the_project_is_given(self) -> None:
        """Ticket #61, critère 3 : un contrôle ou un cas qui n'existe pas n'est pas un correctif."""
        existing = "existant : scripts/controle.py ; tests/test_controle.py"
        case = "cas : evals/mon-cas"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(check(review("mécanique", (existing,)), root))
            self.assertTrue(check(review("jugement", (case,)), root))
            for relative in ("scripts/controle.py", "tests/test_controle.py", "evals/mon-cas/case.yaml"):
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_text("", encoding="utf-8")
            self.assertEqual(check(review("mécanique", (existing,)), root), [])
            self.assertEqual(check(review("jugement", (case,)), root), [])

    def test_a_path_outside_the_project_is_refused(self) -> None:
        """Ticket #61, critère 3 : un chemin qui sort du projet ne prouve rien."""
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "dehors.py"
            outside.write_text("", encoding="utf-8")
            root = Path(tmp) / "projet"
            root.mkdir()
            for fix in ("existant : ../dehors.py ; ../dehors.py", f"existant : {outside} ; {outside}"):
                with self.subTest(fix=fix):
                    self.assertTrue(check(review("mécanique", (fix,)), root))


if __name__ == "__main__":
    unittest.main()
