"""Le gabarit de PR du dépôt porte une vue, l'avant et l'après, la porte et le rayon d'impact (#46)."""

import re
import unittest

import support

REPO_TEMPLATE = support.REPO_ROOT / ".github" / "pull_request_template.md"
PLUGIN_TEMPLATE = support.PLUGIN / "templates" / "pr.md"
HEADING = re.compile(r"^(#{2,3}) (.+)$", re.MULTILINE)


def headings(path):
    return [title.strip() for _, title in HEADING.findall(path.read_text(encoding="utf-8"))]


def section(path, title):
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^#{{2,3}} {re.escape(title)}\n(.*?)(?=^#{{2,3}} |\Z)", text, re.DOTALL | re.MULTILINE)
    assert match, f"section {title!r} absente de {path}"
    return match.group(1)


class SummaryInvitesAView(unittest.TestCase):
    def test_vue_du_changement_sous_resume(self):
        """Le gabarit du dépôt invite à une vue du changement sous Résumé (#46)."""
        titles = headings(REPO_TEMPLATE)
        self.assertIn("Vue du changement", titles)
        self.assertLess(titles.index("Résumé"), titles.index("Vue du changement"))
        self.assertLess(titles.index("Vue du changement"), titles.index("Porte"))
        body = " ".join(section(REPO_TEMPLATE, "Vue du changement").split())
        for kind in ("pseudo-code", "arbre", "diff"):
            self.assertIn(kind, body)


class ProofsShowBeforeAndAfter(unittest.TestCase):
    def test_preuves_avant_rouge_et_apres_vert(self):
        """Preuves a une ligne avant (rouge, avec la raison) et une ligne après (vert) (#46)."""
        body = section(REPO_TEMPLATE, "Preuves")
        self.assertRegex(body, r"(?m)^- Avant \(rouge\)")
        self.assertRegex(body, r"(?m)^- Après \(vert\)")
        self.assertIn("raison", body)
        # Les trois lignes d'origine restent.
        self.assertIn("unittest discover", body)
        self.assertIn("claude plugin validate", body)
        self.assertIn("vrai poste", body)


class GateAndBlastRadius(unittest.TestCase):
    def test_porte_et_rayon_d_impact_sont_deux_sections(self):
        """Porte et Rayon d'impact suivent les noms du gabarit du plugin (#46)."""
        titles = headings(REPO_TEMPLATE)
        self.assertIn("Porte", titles)
        self.assertIn("Rayon d'impact", titles)
        porte = " ".join(section(REPO_TEMPLATE, "Porte").split())
        for word in ("double sens", "sens unique"):
            self.assertIn(word, porte)
        rayon = " ".join(section(REPO_TEMPLATE, "Rayon d'impact").split())
        for word in ("variable", "geste", "hook"):
            self.assertIn(word, rayon)

    def test_sections_du_gabarit_du_plugin_toutes_presentes(self):
        """Chaque section du gabarit du plugin existe dans celui du dépôt, dans le même ordre (#46)."""
        repo = headings(REPO_TEMPLATE)
        plugin = [title for title in headings(PLUGIN_TEMPLATE)]
        self.assertTrue(set(plugin) <= set(repo), set(plugin) - set(repo))
        self.assertEqual([t for t in repo if t in plugin], plugin)

    def test_sections_propres_au_depot_conservees(self):
        """Ce que le gabarit du dépôt a en propre reste (#46)."""
        titles = headings(REPO_TEMPLATE)
        for title in ("Ce qui ne change pas", "Suite"):
            self.assertIn(title, titles)

    def test_sans_tiret_cadratin(self):
        """Le gabarit reste sans tiret cadratin (#46)."""
        self.assertNotIn("—", REPO_TEMPLATE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
