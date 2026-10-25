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
REPLAY = "- `journey-replay` : `parcours (ubuntu-latest) | pnpm --filter <app> e2e e2e/parcours.spec.ts --output {out}`\n"
CONTEXT = "- `required-contexts` : `parcours (ubuntu-latest)`\n"
PATHS = "- `journey-paths` : `apps/web/`\n- `journey-paths` : `apps/api/routes/`\n"
HEADER = "| Identifiant | Lot | Ticket | Test | Écran | Capture | État | Jugé le |\n|---|---|---|---|---|---|---|---|\n"
MATRIX = "# matrice\n\n" + HEADER + "| EXI-01 | L1 | #99 | t.py::a | Écran 1 | | partiel | 2026-10-25 |\n"
BODY_WITH = "## Preuves\n\n![écran 1](captures/e1.png)\n"
BODY_WITHOUT = "## Preuves\n\nrien\n"


def run(usine: str, body: str = "", matrice: str | None = None, files: str | None = None, ticket: str | None = None, tete: str | None = None):
    with tempfile.TemporaryDirectory() as root:
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
        if tete is not None:
            (folder / "usine-tete.md").write_text(tete, encoding="utf-8")
            argv = ["--usine-tete", str(folder / "usine-tete.md")] + argv
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

    def test_a_journey_introduced_by_the_pr_with_a_context_not_required_is_found_on_the_head(self) -> None:
        """No F-NNNN: ticket #99, A1: la base sans la clé, la tête qui l'ajoute sans requérir son contexte : CONTEXTE-NON-REQUIS."""
        base = "- `required-contexts` : `validate`\n"
        code, out, _ = run(base)
        self.assertNotIn("CONTEXTE-NON-REQUIS", out)
        code, out, _ = run(base, tete=REPLAY + base)
        self.assertEqual(code, 1)
        self.assertIn("CONTEXTE-NON-REQUIS\tparcours (ubuntu-latest)", out)
        code, out, _ = run(base, tete=REPLAY + CONTEXT + base)
        self.assertEqual(code, 0)
        self.assertNotIn("CONTEXTE-NON-REQUIS", out)

    def test_the_head_cannot_lift_the_rule_by_removing_the_key(self) -> None:
        """No F-NNNN: ticket #99, A1: la tête qui retire la clé ou le contexte ne lève pas le constat de la base."""
        base = REPLAY + "- `required-contexts` : `validate`\n"
        code, out, _ = run(base, tete="- `required-contexts` : `validate`\n")
        self.assertEqual(code, 1)
        self.assertIn("CONTEXTE-NON-REQUIS", out)

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


class Carried(unittest.TestCase):
    def test_an_empty_value_is_sans_objet_and_not_an_error(self) -> None:
        """No F-NNNN: ticket #99, A4 (MINOR de #113): une valeur vide ne nomme rien, la clé reste sans objet."""
        for key in ("screenshot-command", "recording-command", "browser-drive", "journey-replay"):
            code, out, err = run(f"- `{key}` : ``\n")
            self.assertEqual(code, 0, key)
            self.assertEqual(err, "", key)
            self.assertIn(f"sans objet (clé {key} absente)", out)

    def test_without_a_matrix_the_probe_says_it_looked_for_no_screen_criterion(self) -> None:
        """No F-NNNN: ticket #99, A2 (MINOR de #113): sans matrice, la sonde ne rend pas 0 comme si elle avait cherché."""
        _code, out, _ = run("- `screenshot-command` : `pnpm e2e e2e/a.spec.ts --output {out}`\n", BODY_WITHOUT)
        self.assertIn("sans objet (aucune matrice fournie : critères d'écran non cherchés)", out)
        _code, out, _ = run("# vide\n", BODY_WITHOUT)
        self.assertNotIn("aucune matrice", out)


def text(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


def page(name: str) -> str:
    return " ".join((support.REPO_ROOT / name).read_text(encoding="utf-8").split())


class Roles(unittest.TestCase):
    def test_the_gate_probe_passes_the_files_of_the_pr_and_renders_the_journey_lines(self) -> None:
        """No F-NNNN: ticket #99, A2: qc-gate dit si les captures du parcours sont jointes, sans les juger."""
        gate = text("agents", "qc-gate.md")
        probe = gate[gate.index("**Preuves d'écran.**"):]
        self.assertIn("--files", probe)
        self.assertIn("`PARCOURS-TOUCHE`", probe)
        self.assertIn("`CONTEXTE-NON-REQUIS`", probe)
        self.assertIn("`journey-replay`", probe)
        self.assertIn("`journey-paths`", probe)
        self.assertIn("aucune matrice fournie", probe)
        self.assertIn("--usine-tete", probe)

    def test_the_judge_and_the_page_say_the_head_is_read_too(self) -> None:
        """No F-NNNN: ticket #99, A1: la protection promise par la page est mesurée sur l'usine de la tête."""
        conf = text("agents", "qc-conf.md")
        section = conf[conf.index("## Lecture des preuves d'écran"):conf.index("## Lecture de la matrice")]
        self.assertIn("usine de la tête", section)
        self.assertIn("usine de la tête", page("docs/installation.md"))

    def test_the_judge_makes_missing_journey_captures_a_blocker(self) -> None:
        """No F-NNNN: ticket #99, A2: qc-conf fait un BLOCKER des captures du parcours manquantes."""
        conf = text("agents", "qc-conf.md")
        section = conf[conf.index("## Lecture des preuves d'écran"):conf.index("## Lecture de la matrice")]
        self.assertIn("`PARCOURS-TOUCHE`", section)
        self.assertIn("`journey-replay`", section)
        self.assertIn("`CONTEXTE-NON-REQUIS`", section)
        self.assertIn("`BLOCKER`", section[section.index("`PARCOURS-TOUCHE`"):])

    def test_the_coder_replays_the_journey_and_attaches_its_captures(self) -> None:
        """No F-NNNN: ticket #99, A2: le coder joue le parcours de la clé et joint ses captures réelles à Preuves."""
        coder = text("agents", "coder.md")
        self.assertIn("`journey-replay`", coder)
        self.assertIn("`journey-paths`", coder)
        self.assertIn("non retouchées", coder)

    def test_the_recette_reads_the_journey_key(self) -> None:
        """No F-NNNN: ticket #99, A2: feature-verify cite la clé du rejeu parmi les moyens de capture."""
        self.assertIn("`journey-replay`", text("skills", "feature-verify", "SKILL.md"))


class Docs(unittest.TestCase):
    def test_the_template_documents_the_keys_and_the_retention(self) -> None:
        """No F-NNNN: ticket #99, A1: le gabarit documente journey-replay, journey-paths et la rétention des artefacts."""
        raw = TEMPLATE.read_text(encoding="utf-8")
        documented = parse(raw)
        self.assertIn("journey-replay", documented)
        self.assertIn("journey-paths", documented)
        flat = " ".join(raw.split())
        self.assertIn("required-contexts", flat[flat.index("`journey-replay` :"):])
        self.assertIn("90 jours", flat)
        self.assertIn("pnpm --filter <app> e2e e2e/<spec>", flat)
        self.assertNotIn("e2e -- e2e/", flat)

    def test_the_installation_page_documents_real_captures_and_retention(self) -> None:
        """No F-NNNN: ticket #99, A3: captures réelles non retouchées, loading lazy retiré, rétention en geste du propriétaire."""
        doc = page("docs/installation.md")
        section = doc[doc.index("`journey-replay`"):]
        self.assertIn("non retouchées", section)
        self.assertIn('loading="lazy"', section)
        self.assertIn("pleine page", section)
        self.assertIn("90 jours", section)
        self.assertIn("retention-days", section)
        self.assertIn("artifact-and-log-retention", section)
        self.assertIn("geste du propriétaire", section)
        self.assertIn("avant le premier run", section)
        self.assertIn("Éprouvé sous Linux seulement", section)
        self.assertNotIn("e2e -- e2e/", doc)

    def test_the_readme_summarises_and_points_to_the_page(self) -> None:
        """No F-NNNN: ticket #99, A1: le README résume le rejeu du parcours et renvoie à la page."""
        readme = page("README.md")
        self.assertIn("journey-replay", readme)
        self.assertIn("docs/installation.md", readme)


if __name__ == "__main__":
    unittest.main()
