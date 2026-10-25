"""Ticket #96: a design led by guided questions with a business expert who is not a developer."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support
from matrice import main as matrice_main
from source_ids import ids_of_source
from source_ids import main as source_ids_main

SKILL = support.PLUGIN / "skills" / "feature-guide" / "SKILL.md"


def read(path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class Questions(unittest.TestCase):
    def test_the_skill_asks_one_question_at_a_time_in_the_words_of_the_trade(self) -> None:
        """No F-NNNN: ticket #96, A1: une question à la fois, dans les mots du métier, avec une rédaction à valider."""
        skill = read(SKILL)
        self.assertIn("Une seule question à la fois", skill)
        self.assertIn("Dans les mots du métier", skill)
        self.assertIn("jamais un terme de l'implémentation", skill)
        self.assertIn("Propose une rédaction à valider ou à corriger", skill)
        self.assertIn("jamais une page blanche", skill)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md", skill)


class LivingDocument(unittest.TestCase):
    def test_the_document_is_a_file_of_the_feature_folder_by_default(self) -> None:
        """No F-NNNN: ticket #96, A2: par défaut un fichier Markdown du dossier de la feature (clé feature-dir)."""
        skill = read(SKILL)
        template = read(support.PLUGIN / "templates" / "features" / "conception.md")
        self.assertIn("`conception.md`", skill)
        self.assertIn("dossier de la feature (clé `feature-dir`)", skill)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/templates/features/conception.md", skill)
        self.assertIn("document: conception", template)
        self.assertIn("| Identifiant | Proposition | État | Validé par | Le |", template)

    def test_the_validated_document_becomes_the_source(self) -> None:
        """No F-NNNN: ticket #96, A2: validé par l'expert, le fichier devient la source (clé product-source), en tête."""
        skill = read(SKILL)
        self.assertIn("devient la source", skill)
        self.assertIn("clé `product-source`", skill)
        self.assertIn("en tête", skill)
        self.assertIn("demande à l'humain de la clé `accepting-human`", skill)
        self.assertIn("pas avant", skill)


class SharedSupport(unittest.TestCase):
    def test_the_template_documents_the_key_of_the_shared_support(self) -> None:
        """No F-NNNN: ticket #96, A3: la clé shared-doc est documentée dans le gabarit de usine.md."""
        template = read(support.PLUGIN / "templates" / "usine.md")
        self.assertIn("- `shared-doc` : `<", template)
        self.assertIn("Le fichier du dépôt reste la référence", template)
        self.assertIn("sans objet (clé `shared-doc` absente)", template)
        self.assertIn("Forge ne câble aucun service", template)

    def test_the_skill_uses_the_shared_support_only_when_the_key_names_one(self) -> None:
        """No F-NNNN: ticket #96, A3: sans la clé, sans objet et seul le fichier sert ; avec elle, le fichier reste la référence."""
        skill = read(SKILL)
        self.assertIn("sans objet (clé `shared-doc` absente)", skill)
        self.assertIn("Seul le fichier du dépôt sert", skill)
        self.assertIn("Le fichier du dépôt reste la référence", skill)
        self.assertIn("recopie dans le fichier", skill)
        self.assertNotIn("valeur par défaut :", skill)


class Validation(unittest.TestCase):
    def test_an_agent_proposal_stays_marked_until_the_expert_validates_it(self) -> None:
        """No F-NNNN: ticket #96, A4: chaque proposition de l'agent reste marquée `proposé` tant que l'expert ne l'a pas validée."""
        skill = read(SKILL)
        template = read(support.PLUGIN / "templates" / "features" / "conception.md")
        self.assertIn("Chaque rédaction que tu écris porte l'état `proposé`", skill)
        self.assertIn("jusqu'au « oui » de l'expert", skill)
        self.assertIn("Une correction de l'expert réécrit la ligne", skill)
        self.assertIn("Seul le « oui » de l'expert le pose", template)

    def test_a_requirement_never_enters_validated_without_the_expert(self) -> None:
        """No F-NNNN: ticket #96, A4: une exigence n'entre jamais `validé` sans l'expert : son nom et la date."""
        skill = read(SKILL)
        self.assertIn("Une exigence n'entre jamais `validé` sans l'expert", skill)
        self.assertIn("son nom (clé `source-author`) et la date", skill)
        self.assertIn("Un silence n'est pas un accord", skill)
        self.assertIn("ni l'humain de la clé `accepting-human` ni un agent ne le remplacent", skill)
        self.assertIn("sans objet (clé `source-author` absente)", skill)


VALIDATED = """# Conception avec l'expert (F-0000)

| Identifiant | Proposition | État | Validé par | Le |
|---|---|---|---|---|
| EXI-01 | La date de relevé est obligatoire | validé | expert-metier | 2026-10-20 |
| EXI-02 | L'index ne décroît jamais | validé | expert-metier | 2026-10-20 |

| Identifiant | Proposition | État | Validé par | Le |
|---|---|---|---|---|
| C01 | Avertir si l'écart dépasse 5 % | validé | expert-metier | 2026-10-21 |
"""


class Outputs(unittest.TestCase):
    def test_the_skill_names_the_three_outputs_and_their_scripts(self) -> None:
        """No F-NNNN: ticket #96, A5: le document au grain de #93, le parcours voulu (#97) et la matrice initiale (#94)."""
        skill = read(SKILL)
        self.assertIn("section « Éléments de la source »", skill)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/templates/features/spec.md", skill)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/templates/features/parcours.md", skill)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/parcours.py", skill)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/templates/features/matrice.md", skill)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/matrice.py", skill)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/source_ids.py", skill)
        self.assertIn("une ligne `absent` par identifiant", skill)
        self.assertIn("sans ticket, sans date", skill)

    def test_the_identifiers_of_the_validated_document_are_those_of_the_source(self) -> None:
        """No F-NNNN: ticket #96, A5: les lignes du document validé sont des éléments identifiés pour le comptage."""
        self.assertEqual(ids_of_source(VALIDATED), ["EXI-01", "EXI-02", "C01"])

    def test_the_template_title_is_not_counted_as_an_element_of_the_source(self) -> None:
        """No F-NNNN: ticket #96, A5: le titre du gabarit, numéroté, ne devient pas un identifiant de la source."""
        template = (support.PLUGIN / "templates" / "features" / "conception.md").read_text(encoding="utf-8")
        self.assertEqual(ids_of_source(template.replace("F-NNNN", "F-0042")), [])

    def test_the_initial_matrix_the_skill_describes_passes_the_script(self) -> None:
        """No F-NNNN: ticket #96, A5: une ligne `absent` par identifiant, sans ticket ni date, passe matrice.py."""
        header = "| Identifiant | Lot | Ticket | Test | Écran | Capture | État | Jugé le |\n|---|---|---|---|---|---|---|---|\n"
        rows = "".join(f"| {i} | | | | | | absent | |\n" for i in ids_of_source(VALIDATED))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "usine.md").write_text("- `product-source` : `conception.md`\n", encoding="utf-8")
            (root / "conception.md").write_text(VALIDATED, encoding="utf-8")
            (root / "matrice.md").write_text("# F-0000 : matrice\n\n" + header + rows, encoding="utf-8")
            out = io.StringIO()
            argv = ["--usine", str(root / "usine.md"), "--root", str(root), str(root / "matrice.md")]
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = matrice_main(argv)
            self.assertEqual(code, 0, out.getvalue())
            self.assertTrue(out.getvalue().startswith("OK\t"), out.getvalue())


def filled(number: str) -> str:
    """The conception template for a feature, its example identifiers kept and the placeholders removed."""
    text = (support.PLUGIN / "templates" / "features" / "conception.md").read_text(encoding="utf-8")
    text = text.replace("F-NNNN", f"F-{number}").replace("NNNN", number)
    return text.replace("<", "").replace(">", "")


def spec_citing(identifiers: list[str]) -> str:
    return "# Spec\n\n## Éléments de la source\n\n" + "".join(f"- {i} repris\n" for i in identifiers)


def count(sources: dict[str, str], spec: str) -> str:
    """The output of source_ids.py for a project whose product-source holds the given files."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        lines = "".join(f"- `product-source` : `{name}`\n" for name in sources)
        (root / "usine.md").write_text(lines, encoding="utf-8")
        for name, text in sources.items():
            (root / name).write_text(text, encoding="utf-8")
        (root / "spec.md").write_text(spec, encoding="utf-8")
        out = io.StringIO()
        argv = ["--usine", str(root / "usine.md"), "--root", str(root), str(root / "spec.md")]
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            source_ids_main(argv)
        return out.getvalue()


PROCEDURE = "# Procédure\n\n| Identifiant | Exigence |\n|---|---|\n| EXI-01 | Le relevé est daté |\n"


class Collision(unittest.TestCase):
    def test_two_conceptions_never_share_an_identifier(self) -> None:
        """No F-NNNN: ticket #96, A2: deux conceptions déclarées dans product-source ne se fondent pas en un élément."""
        first, second = ids_of_source(filled("0042")), ids_of_source(filled("0043"))
        self.assertTrue(first and second)
        self.assertEqual(set(first) & set(second), set())
        out = count({"a.md": filled("0042"), "b.md": filled("0043")}, spec_citing([first[0]]))
        for identifier in second:
            self.assertIn(f"MISSING\t{identifier}\t", out)
        self.assertEqual(sum(1 for line in out.splitlines() if line.startswith("MISSING")), len(first) + len(second) - 1)

    def test_a_conception_never_borrows_the_identifier_of_a_declared_source(self) -> None:
        """No F-NNNN: ticket #96, A2: l'identifiant neuf d'une conception ne se fond pas avec celui d'une source déclarée."""
        mine = ids_of_source(filled("0042"))
        self.assertNotIn("EXI-01", mine)
        out = count({"procedure.md": PROCEDURE, "conception.md": filled("0042")}, spec_citing(mine))
        self.assertIn("MISSING\tEXI-01\t", out)
        out = count({"procedure.md": PROCEDURE, "conception.md": filled("0042")}, spec_citing(mine + ["EXI-01"]))
        self.assertIn("NONE", out)

    def test_the_initial_matrix_of_a_conception_does_not_hide_a_declared_source_element(self) -> None:
        """No F-NNNN: ticket #96, A2: matrice.py voit l'élément d'une source déclarée même quand la conception en porte un du même rang."""
        mine = ids_of_source(filled("0042"))
        header = "| Identifiant | Lot | Ticket | Test | Écran | Capture | État | Jugé le |\n|---|---|---|---|---|---|---|---|\n"
        rows = "".join(f"| {i} | | | | | | absent | |\n" for i in mine)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "usine.md").write_text("- `product-source` : `conception.md`\n- `product-source` : `procedure.md`\n", encoding="utf-8")
            (root / "conception.md").write_text(filled("0042"), encoding="utf-8")
            (root / "procedure.md").write_text(PROCEDURE, encoding="utf-8")
            (root / "matrice.md").write_text("# F-0042 : matrice\n\n" + header + rows, encoding="utf-8")
            out = io.StringIO()
            argv = ["--usine", str(root / "usine.md"), "--root", str(root), str(root / "matrice.md")]
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                matrice_main(argv)
            self.assertIn("MISSING\tEXI-01", out.getvalue())

    def test_the_skill_and_the_page_say_the_reach_of_the_key_and_what_becomes_of_the_conception(self) -> None:
        """No F-NNNN: ticket #96, A2: la portée de product-source, le préfixe, la reprise de l'origine, le retrait de la clé."""
        skill = read(SKILL)
        self.assertIn("Cette clé vaut pour tout le projet", skill)
        self.assertIn("Numérote avec le numéro de la feature", skill)
        self.assertIn("reprends son identifiant d'origine", skill)
        self.assertIn("ne reste dans la clé que le temps de sa feature", skill)
        install = read(support.REPO_ROOT / "docs" / "installation.md")
        self.assertIn("La clé vaut pour toutes les features", install)
        self.assertIn("se retire de la clé quand sa feature est close", install)


class Reach(unittest.TestCase):
    def test_the_skill_runs_on_the_command_line_and_says_it_was_tried_with_no_expert(self) -> None:
        """No F-NNNN: ticket #96, A6: ligne de commande d'abord, cockpit (#33) ensuite ; aucun expert réel ne l'a essayé."""
        skill = read(SKILL)
        self.assertIn("ligne de commande", skill)
        self.assertIn("cockpit", skill)
        self.assertIn("Aucun expert métier réel n'a encore mené une conception avec ce skill", skill)

    def test_the_consumer_pages_describe_the_skill_and_the_key(self) -> None:
        """No F-NNNN: ticket #96, A6: la page du projet consommateur, le README et le protocole en parlent."""
        install = read(support.REPO_ROOT / "docs" / "installation.md")
        self.assertIn("`/forge:feature-guide`", install)
        self.assertIn("`shared-doc`", install)
        self.assertIn("aucun expert réel", install)
        readme = read(support.REPO_ROOT / "README.md")
        self.assertIn("-guide", readme)
        protocol = read(support.PLUGIN / "templates" / "features" / "protocole.md")
        self.assertIn("`conception.md`", protocol)
        self.assertIn("n'est pas une étape de la chaîne", protocol)


if __name__ == "__main__":
    unittest.main()
