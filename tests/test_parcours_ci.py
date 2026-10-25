"""Ticket #99: le parcours voulu rejoué en CI, captures jointes à toute PR qui touche le parcours."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support
from preuves_ecran import main
from usine import parse

TEMPLATE = support.PLUGIN / "templates" / "usine.md"
SCRATCH = Path.home() / ".cache" / "forge-tmp"
REPLAY = "- `journey-replay` : `parcours (ubuntu-latest) | pnpm --filter <app> e2e e2e/parcours.spec.ts --output {out}`\n"
CONTEXT = "- `required-contexts` : `parcours (ubuntu-latest)`\n"
PATHS = "- `journey-paths` : `apps/web/`\n- `journey-paths` : `apps/api/routes/`\n"
HEADER = "| Identifiant | Lot | Ticket | Test | Écran | Capture | État | Jugé le |\n|---|---|---|---|---|---|---|---|\n"
MATRIX = "# matrice\n\n" + HEADER + "| EXI-01 | L1 | #99 | t.py::a | Écran 1 | | partiel | 2026-10-25 |\n"
BODY_WITH = "## Preuves\n\n![écran 1](captures/e1.png)\n"
BODY_WITHOUT = "## Preuves\n\nrien\n"


def run(usine: str, body: str = "", matrice: str | None = None, files: str | None = None, ticket: str | None = None):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=SCRATCH) as root:
        folder = Path(root)
        (folder / "usine.md").write_text(usine, encoding="utf-8")
        (folder / "body.md").write_text(body, encoding="utf-8")
        argv = ["--usine", str(folder / "usine.md"), str(folder / "body.md")]
        if matrice is not None:
            (folder / "matrice.md").write_text(matrice, encoding="utf-8")
            argv = ["--matrice", str(folder / "matrice.md")] + argv
        if files is not None:
            (folder / "files.txt").write_text(files, encoding="utf-8")
            argv = ["--files", str(folder / "files.txt")] + argv
        if ticket:
            argv = ["--ticket", ticket] + argv
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()


class Key(unittest.TestCase):
    def test_the_key_is_declared_with_its_context_and_its_command(self) -> None:
        """No F-NNNN: ticket #99, A1: journey-replay dit le contexte de CI et la commande qui joue le parcours."""
        code, out, _ = run(REPLAY + CONTEXT)
        self.assertEqual(code, 0)
        self.assertIn(
            "CAPACITE\tjourney-replay\tparcours (ubuntu-latest) | pnpm --filter <app> e2e e2e/parcours.spec.ts --output {out}\tcommande du projet, rejouée en CI",
            out,
        )

    def test_a_value_without_context_or_without_out_is_refused(self) -> None:
        """No F-NNNN: ticket #99, A1: sans contexte nommé ni {out}, le parcours ne peut être exigé ni ses captures rangées."""
        code, _out, err = run("- `journey-replay` : `pnpm e2e e2e/parcours.spec.ts --output {out}`\n")
        self.assertEqual(code, 2)
        self.assertIn("journey-replay", err)
        code, _out, err = run("- `journey-replay` : `parcours | pnpm e2e e2e/parcours.spec.ts`\n")
        self.assertEqual(code, 2)
        self.assertIn("{out}", err)

    def test_the_context_must_be_a_required_one(self) -> None:
        """No F-NNNN: ticket #99, A1: un parcours cassé bloque la PR seulement si son contexte est requis."""
        code, out, _ = run(REPLAY + "- `required-contexts` : `validate`\n")
        self.assertEqual(code, 1)
        self.assertIn("CONTEXTE-NON-REQUIS\tparcours (ubuntu-latest)", out)
        code, out, _ = run(REPLAY + CONTEXT)
        self.assertEqual(code, 0)
        self.assertNotIn("CONTEXTE-NON-REQUIS", out)

    def test_without_required_contexts_the_check_is_sans_objet(self) -> None:
        """No F-NNNN: ticket #99, A1: sans la clé required-contexts, la mesure est sans objet et jamais un succès."""
        code, out, _ = run(REPLAY)
        self.assertEqual(code, 0)
        self.assertIn("sans objet (clé required-contexts absente)", out)
        self.assertNotIn("PASS", out)


class Touched(unittest.TestCase):
    ON = REPLAY + CONTEXT + PATHS

    def test_a_pr_touching_the_front_without_captures_is_missing(self) -> None:
        """No F-NNNN: ticket #99, A2: une PR qui touche le front sans capture jointe est MANQUE, sans avis."""
        code, out, _ = run(self.ON, BODY_WITHOUT, files="README.md\napps/web/src/page.tsx\n")
        self.assertEqual(code, 1)
        self.assertIn("PARCOURS-TOUCHE\tapps/web/src/page.tsx", out)
        self.assertNotIn("README.md", out)
        self.assertIn("MANQUE\tcorps de PR", out)

    def test_a_pr_touching_an_api_the_front_consumes_is_missing_too(self) -> None:
        """No F-NNNN: ticket #99, A2: une API que consomme le front, déclarée par journey-paths, ouvre la même attente."""
        code, out, _ = run(self.ON, BODY_WITHOUT, files="apps/api/routes/users.ts\n")
        self.assertEqual(code, 1)
        self.assertIn("PARCOURS-TOUCHE\tapps/api/routes/users.ts", out)

    def test_captures_attached_satisfy_the_expectation(self) -> None:
        """No F-NNNN: ticket #99, A2: la PR qui touche le parcours et joint ses captures ne manque de rien."""
        code, out, _ = run(self.ON, BODY_WITH, files="apps/web/src/page.tsx\n")
        self.assertEqual(code, 0)
        self.assertIn("JOINTE\tcorps de PR\t1", out)
        self.assertNotIn("MANQUE", out)

    def test_a_pr_elsewhere_expects_no_capture(self) -> None:
        """No F-NNNN: ticket #99, A2: une PR qui ne touche pas le parcours n'attend aucune capture."""
        code, out, _ = run(self.ON, BODY_WITHOUT, files="docs/a.md\nscripts/b.py\n")
        self.assertEqual(code, 0)
        self.assertNotIn("PARCOURS-TOUCHE", out)
        self.assertNotIn("MANQUE", out)

    def test_without_paths_or_files_the_probe_says_it_could_not_look(self) -> None:
        """No F-NNNN: ticket #99, A2: sans journey-paths ou sans liste de fichiers, la sonde le dit au lieu de rendre 0 en silence."""
        _code, out, _ = run(REPLAY + CONTEXT, BODY_WITHOUT, files="apps/web/a.ts\n")
        self.assertIn("sans objet (clé journey-paths absente)", out)
        _code, out, _ = run(self.ON, BODY_WITHOUT)
        self.assertIn("sans objet (liste des fichiers de la PR non fournie)", out)

    def test_the_replay_expects_the_matrix_screen_criteria_of_the_ticket(self) -> None:
        """No F-NNNN: ticket #99, A2: journey-replay ouvre aussi l'attente des critères d'écran de la matrice."""
        code, out, _ = run(self.ON, BODY_WITHOUT, MATRIX, files="docs/a.md\n", ticket="#99")
        self.assertEqual(code, 1)
        self.assertIn("SANS-CAPTURE\tEXI-01", out)
        self.assertIn("MANQUE\tcorps de PR", out)

    def test_an_absent_key_is_sans_objet_and_expects_nothing(self) -> None:
        """No F-NNNN: ticket #99, A4: sans journey-replay, sans objet, aucune attente de capture."""
        code, out, _ = run("# Usine\n" + PATHS, BODY_WITHOUT, files="apps/web/src/a.ts\n")
        self.assertEqual(code, 0)
        self.assertIn("sans objet (clé journey-replay absente)", out)
        self.assertNotIn("MANQUE", out)
        self.assertNotIn("PARCOURS-TOUCHE", out)


if __name__ == "__main__":
    unittest.main()
