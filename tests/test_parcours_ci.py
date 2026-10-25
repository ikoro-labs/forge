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


if __name__ == "__main__":
    unittest.main()
