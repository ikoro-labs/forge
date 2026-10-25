"""Ticket #98: the labels a PR adds on screen, checked against forbidden words by `ui_labels.py`."""

import unittest

import support  # noqa: F401
from ui_labels import FORBIDDEN, check

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


if __name__ == "__main__":
    unittest.main()
