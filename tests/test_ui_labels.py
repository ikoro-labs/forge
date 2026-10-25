"""Ticket #98: the labels a PR adds on screen, checked against forbidden words by `ui_labels.py`."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import support  # noqa: F401
from ui_labels import FORBIDDEN, check, main

LABELS = ["app/i18n/"]


def diff(path: str, *added: str) -> str:
    body = "\n".join(f"+{line}" for line in added)
    return (
        f"diff --git a/{path} b/{path}\nindex 111..222 100644\n--- a/{path}\n+++ b/{path}\n"
        f"@@ -1,1 +1,{len(added) + 1} @@\n context\n{body}\n"
    )


def kinds(text: str, forbidden: list[str], paths: list[str] = LABELS) -> list[str]:
    return [finding.status for finding in check(paths, forbidden, text)]


class ForbiddenWords(unittest.TestCase):
    def test_a_label_with_a_forbidden_word_is_reported(self) -> None:
        """No F-NNNN: ticket #98, A1: un libellé ajouté qui contient un mot refusé."""
        text = diff("app/i18n/fr.yml", '  save: "Enregistrer le commit"')
        findings = check(LABELS, ["commit"], text)
        self.assertEqual([f.status for f in findings], [FORBIDDEN])
        self.assertEqual(findings[0].path, "app/i18n/fr.yml")
        self.assertEqual(findings[0].label, "Enregistrer le commit")
        self.assertEqual(findings[0].detail, "commit")

    def test_the_word_is_matched_whole_and_without_case(self) -> None:
        """No F-NNNN: ticket #98, A1: un mot refusé ne vaut pas pour un mot qui le contient."""
        self.assertEqual(kinds(diff("app/i18n/fr.yml", "a: Le Commit est fait"), ["commit"]), [FORBIDDEN])
        self.assertEqual(kinds(diff("app/i18n/fr.yml", "a: Le comité se réunit"), ["comit"]), [])
        self.assertEqual(kinds(diff("app/i18n/fr.yml", "a: Le commissaire"), ["commit"]), [])

    def test_an_identifier_pattern_is_reported(self) -> None:
        """No F-NNNN: ticket #98, A2: un motif d'identifiant (F-0042, ADR-12, un renvoi §3)."""
        patterns = [r"F-\d{4}", r"ADR-\d+", r"§\s?\d+"]
        for label in ("Voir F-0042", "Décidé par ADR-12", "Voir le § 3"):
            self.assertEqual(kinds(diff("app/i18n/fr.yml", f"a: {label}"), patterns), [FORBIDDEN], label)

    def test_a_conforming_label_is_not_reported(self) -> None:
        """No F-NNNN: ticket #98, A3: un libellé conforme ne donne aucune ligne."""
        text = diff("app/i18n/fr.yml", 'save: "Enregistrer"', "cancel: Annuler")
        self.assertEqual(kinds(text, ["commit", r"F-\d{4}"]), [])

    def test_the_key_of_a_label_is_not_read_as_text(self) -> None:
        """No F-NNNN: ticket #98, A1: seule la valeur est un libellé, pas la clé qui la porte."""
        self.assertEqual(kinds(diff("app/i18n/fr.json", '"commit_button": "Valider"'), ["commit"]), [])

    def test_only_added_lines_under_the_label_files_are_read(self) -> None:
        """No F-NNNN: ticket #98, A1: une ligne retirée ou hors des fichiers de libellés est ignorée."""
        removed = (
            "diff --git a/app/i18n/fr.yml b/app/i18n/fr.yml\n--- a/app/i18n/fr.yml\n+++ b/app/i18n/fr.yml\n"
            "@@ -1,2 +1,1 @@\n-a: commit\n context\n"
        )
        self.assertEqual(kinds(removed, ["commit"]), [])
        self.assertEqual(kinds(diff("src/code.py", "a = 'commit'"), ["commit"]), [])

    def test_a_comment_or_a_blank_line_is_not_a_label(self) -> None:
        """No F-NNNN: ticket #98, A1: commentaires et lignes vides ne sont pas des libellés."""
        self.assertEqual(kinds(diff("app/i18n/fr.yml", "# commit", "", "// commit"), ["commit"]), [])


def run(usine: str, text: str) -> tuple[int, str]:
    """Run the script on a `usine.md` and a diff, as the gate does: the exit code and what it prints."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        (root / "usine.md").write_text(usine, encoding="utf-8")
        (root / "pr.diff").write_text(text, encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--usine", str(root / "usine.md"), "--root", str(root), str(root / "pr.diff")])
        return code, out.getvalue()


KEYS = "- `ui-labels` : `app/i18n/`\n- `ui-forbidden-word` : `commit`\n- `ui-forbidden-word` : `F-\\d{4}`\n"


class Keys(unittest.TestCase):
    def test_a_forbidden_word_exits_one_and_prints_the_label(self) -> None:
        """No F-NNNN: ticket #98, A1: la sortie dit le fichier, le libellé et le mot, code 1."""
        code, out = run(KEYS, diff("app/i18n/fr.yml", "a: Voir F-0042"))
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["FORBIDDEN\tapp/i18n/fr.yml\tVoir F-0042\tF-0042"])

    def test_a_conforming_label_exits_zero(self) -> None:
        """No F-NNNN: ticket #98, A3: un libellé conforme sort 0 et le dit."""
        code, out = run(KEYS, diff("app/i18n/fr.yml", "a: Enregistrer"))
        self.assertEqual((code, out.splitlines()), (0, ["NONE\t\t\taucun libellé refusé"]))

    def test_without_ui_labels_the_step_is_without_object_and_never_pass(self) -> None:
        """No F-NNNN: ticket #98, A4: clé ui-labels absente, même avec un mot refusé déclaré."""
        code, out = run("- `ui-forbidden-word` : `commit`\n", diff("app/i18n/fr.yml", "a: commit"))
        self.assertEqual((code, out.strip()), (0, "sans objet (clé ui-labels absente)"))
        self.assertNotIn("PASS", out)

    def test_without_forbidden_words_that_part_is_without_object(self) -> None:
        """No F-NNNN: ticket #98, A4: clé ui-forbidden-word absente, aucune valeur supposée."""
        code, out = run("- `ui-labels` : `app/i18n/`\n", diff("app/i18n/fr.yml", "a: commit"))
        self.assertEqual((code, out.strip()), (0, "sans objet (clé ui-forbidden-word absente)"))

    def test_without_the_usine_file_both_keys_are_absent(self) -> None:
        """No F-NNNN: ticket #98, A4: pas de docs/agents/usine.md, la sonde est sans objet."""
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "pr.diff").write_text(diff("app/i18n/fr.yml", "a: commit"), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["--usine", str(Path(folder) / "none.md"), str(Path(folder) / "pr.diff")])
        self.assertEqual((code, out.getvalue().strip()), (0, "sans objet (clé ui-labels absente)"))

    def test_an_invalid_pattern_exits_two_and_is_never_pass(self) -> None:
        """No F-NNNN: ticket #98, A2: un motif qui n'est pas une expression régulière sort 2."""
        usine = "- `ui-labels` : `app/i18n/`\n- `ui-forbidden-word` : `(ouvert`\n"
        code, out = run(usine, diff("app/i18n/fr.yml", "a: Enregistrer"))
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("INVALID\t"))


if __name__ == "__main__":
    unittest.main()
