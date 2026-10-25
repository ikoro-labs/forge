"""Ticket #54 (partie ligne de commande): les capacités de vérification du front que le projet active."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support
from preuves_ecran import main
from usine import parse

TEMPLATE = support.PLUGIN / "templates" / "usine.md"

KEYS = ("screenshot-command", "browser-drive", "computer-use-host", "recording-command")
HEADER = "| Identifiant | Lot | Ticket | Test | Écran | Capture | État | Jugé le |\n|---|---|---|---|---|---|---|---|\n"
BODY_WITH = "## Preuves\n\n![écran 1](captures/e1.png)\n"


def run(usine: str, body: str = "", matrice: str | None = None, ticket: str | None = None):
    with tempfile.TemporaryDirectory() as root:
        folder = Path(root)
        (folder / "usine.md").write_text(usine, encoding="utf-8")
        (folder / "body.md").write_text(body, encoding="utf-8")
        argv = ["--usine", str(folder / "usine.md"), str(folder / "body.md")]
        if matrice is not None:
            (folder / "matrice.md").write_text(matrice, encoding="utf-8")
            argv = ["--matrice", str(folder / "matrice.md")] + argv
        if ticket:
            argv = ["--ticket", ticket] + argv
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()


class Absent(unittest.TestCase):
    def test_every_absent_key_is_sans_objet_and_never_a_pass(self) -> None:
        """No F-NNNN: ticket #54, A1: une clé absente rend « sans objet (clé <nom> absente) », sans valeur par défaut."""
        code, out, _ = run("# Usine\n")
        self.assertEqual(code, 0)
        for key in KEYS:
            self.assertIn(f"sans objet (clé {key} absente)", out)
        self.assertNotIn("PASS", out)
        self.assertNotIn("JOINTE", out)

    def test_a_key_present_does_not_hide_the_others(self) -> None:
        """No F-NNNN: ticket #54, A1: chaque clé est indépendante."""
        code, out, _ = run("- `screenshot-command` : `pnpm --filter web e2e e2e/captures.spec.ts --output {out}`\n")
        self.assertEqual(code, 0)
        self.assertIn("CAPACITE\tscreenshot-command", out)
        for key in KEYS[1:]:
            self.assertIn(f"sans objet (clé {key} absente)", out)


class Declared(unittest.TestCase):
    def test_a_command_key_without_the_out_placeholder_is_refused(self) -> None:
        """No F-NNNN: ticket #54, A2: une commande sans {out} ne dit pas où écrire ses fichiers."""
        code, out, err = run("- `recording-command` : `pnpm --filter web e2e e2e/parcours.spec.ts`\n")
        self.assertEqual(code, 2)
        self.assertIn("recording-command", err)

    def test_the_driven_browser_names_its_tool_and_its_station(self) -> None:
        """No F-NNNN: ticket #54, A3: le navigateur piloté dit l'outil et le poste, et ne tourne jamais en CI."""
        code, out, err = run("- `browser-drive` : `outil seul`\n")
        self.assertEqual(code, 2)
        self.assertIn("browser-drive", err)
        code, out, _ = run("- `browser-drive` : `claude-in-chrome | poste-recette`\n")
        self.assertEqual(code, 0)
        self.assertIn("CAPACITE\tbrowser-drive\tclaude-in-chrome | poste-recette\tposte avec session ouverte, jamais en CI", out)

    def test_computer_use_names_a_dedicated_host_never_a_default(self) -> None:
        """No F-NNNN: ticket #54, A4: la commande de l'ordinateur ne vaut que sur le poste dédié que la clé nomme."""
        code, out, _ = run("- `computer-use-host` : `poste-dedie-recette`\n")
        self.assertEqual(code, 0)
        self.assertIn("CAPACITE\tcomputer-use-host\tposte-dedie-recette\tposte dédié, jamais le poste personnel d'un membre", out)


class Probe(unittest.TestCase):
    ONE = "- `screenshot-command` : `pnpm --filter web e2e e2e/captures.spec.ts --output {out}`\n"
    MATRIX = (
        "# matrice\n\n" + HEADER
        + "| EXI-01 | L1 | #54 | t.py::a | Écran 1 | captures/e1.png | tenu | 2026-10-25 |\n"
        "| EXI-02 | L1 | #54 | t.py::b | Écran 2 | | partiel | 2026-10-25 |\n"
        "| EXI-03 | L1 | #55 | t.py::c | Écran 3 | | partiel | 2026-10-25 |\n"
        "| EXI-04 | L1 | #54 | t.py::d | | | tenu | 2026-10-25 |\n"
    )

    def test_a_screen_criterion_without_capture_is_reported_without_opinion(self) -> None:
        """No F-NNNN: ticket #54, A5: la sonde dit si la preuve attendue est jointe, ligne à ligne, sans avis."""
        code, out, _ = run(self.ONE, BODY_WITH, self.MATRIX, ticket="#54")
        self.assertEqual(code, 1)
        self.assertIn("LIEE\tEXI-01", out)
        self.assertIn("SANS-CAPTURE\tEXI-02", out)
        self.assertNotIn("EXI-03", out)
        self.assertNotIn("EXI-04", out)
        self.assertIn("JOINTE\tcorps de PR\t1", out)

    def test_expected_proof_with_nothing_attached_is_missing(self) -> None:
        """No F-NNNN: ticket #54, A5: aucune capture dans le corps alors qu'un écran est couvert."""
        code, out, _ = run(self.ONE, "## Preuves\n\nrien\n", self.MATRIX, ticket="#55")
        self.assertEqual(code, 1)
        self.assertIn("MANQUE\tcorps de PR", out)

    def test_no_capability_means_no_proof_expected(self) -> None:
        """No F-NNNN: ticket #54, A1: sans aucune clé, rien n'est attendu et rien n'est dit joint."""
        code, out, _ = run("# vide\n", "", self.MATRIX, ticket="#55")
        self.assertEqual(code, 0)
        self.assertNotIn("MANQUE", out)
        self.assertNotIn("SANS-CAPTURE", out)

    def test_a_station_key_alone_opens_no_expectation_for_a_pr_elsewhere(self) -> None:
        """No F-NNNN: ticket #54, A5: le navigateur piloté et le poste dédié ne servent pas là où tourne la PR."""
        for line in (
            "- `browser-drive` : `claude-in-chrome | poste-recette`\n",
            "- `computer-use-host` : `poste-dedie-recette`\n",
        ):
            code, out, _ = run(line, "## Preuves\n\nrien\n", self.MATRIX, ticket="#54")
            self.assertEqual(code, 0, line)
            self.assertIn("CAPACITE\t" + line.split("`")[1], out)
            self.assertNotIn("SANS-CAPTURE", out)
            self.assertNotIn("MANQUE", out)

    def test_an_empty_host_value_is_not_a_declared_capability(self) -> None:
        """No F-NNNN: ticket #54, A4: une valeur vide ne nomme aucun poste, la capacité reste sans objet."""
        code, out, _ = run("- `computer-use-host` : ``\n", "", self.MATRIX, ticket="#54")
        self.assertEqual(code, 0)
        self.assertIn("sans objet (clé computer-use-host absente)", out)
        self.assertNotIn("CAPACITE\tcomputer-use-host", out)

    def test_a_command_key_next_to_a_station_key_still_expects_the_proof(self) -> None:
        """No F-NNNN: ticket #54, A5: screenshot-command garde l'attente même avec un poste déclaré."""
        code, out, _ = run(self.ONE + "- `browser-drive` : `claude-in-chrome | poste-recette`\n", "", self.MATRIX, ticket="#54")
        self.assertEqual(code, 1)
        self.assertIn("MANQUE\tcorps de PR", out)

    def test_a_video_or_a_gif_counts_as_attached(self) -> None:
        """No F-NNNN: ticket #54, A5: une vidéo ou un GIF joint compte comme une capture."""
        _code, out, _ = run(self.ONE, "[parcours](preuves/parcours.mp4)\n![g](preuves/p.gif)\n", self.MATRIX, ticket="#55")
        self.assertNotIn("MANQUE", out)
        self.assertIn("JOINTE\tcorps de PR\t2", out)


class Template(unittest.TestCase):
    def test_the_template_documents_the_four_keys_and_their_limits(self) -> None:
        """No F-NNNN: ticket #54, A6: chaque clé est documentée dans le gabarit, avec sa limite."""
        text = TEMPLATE.read_text(encoding="utf-8")
        documented = parse(text)
        for key in KEYS:
            self.assertIn(key, documented)
        flat = " ".join(text.split())
        self.assertIn("jamais en CI", flat)
        self.assertIn("jamais le poste personnel d'un membre", flat)
        self.assertIn("sans objet (clé `computer-use-host` absente)", flat)
        # Une commande d'exemple n'a pas de `--` avant le fichier de spec: Playwright ignorerait le filtre.
        self.assertNotIn("e2e -- e2e/", flat)
        self.assertIn("pnpm --filter <app> e2e e2e/<spec>", flat)


def text(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


class Roles(unittest.TestCase):
    def test_the_coder_attaches_the_proof_the_keys_allow_in_its_preuves(self) -> None:
        """No F-NNNN: ticket #54, A7: le coder prend les captures par les clés déclarées et les joint à Preuves."""
        coder = text("agents", "coder.md")
        for key in KEYS:
            self.assertIn(f"`{key}`", coder)
        self.assertIn("scripts/preuves_ecran.py", coder)
        self.assertIn("sans objet (clé `<nom>` absente)", coder)
        self.assertIn("jamais en CI", coder)
        self.assertIn("poste personnel", coder)

    def test_the_gate_probe_says_whether_the_expected_proof_is_attached_without_opinion(self) -> None:
        """No F-NNNN: ticket #54, A8: qc-gate lance la sonde et rend ses lignes verbatim, sans les juger."""
        gate = text("agents", "qc-gate.md")
        self.assertIn("scripts/preuves_ecran.py", gate)
        self.assertIn("**Preuves d'écran.**", gate)
        self.assertIn("sans objet (clé screenshot-command absente)", gate)
        self.assertIn("Tu ne juges pas une capture", gate)

    def test_the_judge_makes_a_missing_screen_proof_a_blocker(self) -> None:
        """No F-NNNN: ticket #54, A9: une preuve d'écran manquante pour un critère d'écran est un constat de qc-conf."""
        conf = text("agents", "qc-conf.md")
        self.assertIn("## Lecture des preuves d'écran", conf)
        self.assertIn("`SANS-CAPTURE`", conf)
        self.assertIn("`MANQUE`", conf)
        self.assertIn("`BLOCKER`", conf[conf.index("## Lecture des preuves d'écran"):])

    def test_the_recette_links_each_screen_criterion_to_its_capture_or_recording(self) -> None:
        """No F-NNNN: ticket #54, A10: feature-verify relie le critère à sa capture ou à son enregistrement."""
        verify = text("skills", "feature-verify", "SKILL.md")
        self.assertIn("sa capture ou son enregistrement", verify)
        self.assertIn("colonne `Capture`", verify)
        self.assertIn("sans objet (clé `<nom>` absente)", verify)


class Docs(unittest.TestCase):
    def test_the_installation_page_and_the_readme_describe_the_four_keys(self) -> None:
        """No F-NNNN: ticket #54, A11: la page des clés décrit les quatre capacités, le README les résume."""
        page = " ".join((support.REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8").split())
        readme = " ".join((support.REPO_ROOT / "README.md").read_text(encoding="utf-8").split())
        for key in KEYS:
            self.assertIn(f"`{key}`", page)
        self.assertIn("preuves_ecran.py", page)
        self.assertIn("jamais en CI", page)
        self.assertIn("jamais le poste personnel d'un membre", page)
        self.assertIn("Éprouvé sous Linux seulement", page[page.index("preuves_ecran.py"):])
        self.assertIn("captures", readme)
        self.assertIn("docs/installation.md", readme)


if __name__ == "__main__":
    unittest.main()
