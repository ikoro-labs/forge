"""Le gabarit de PR du dépôt suit celui du plugin (#46, #231)."""

import re
import unittest

import support

REPO_TEMPLATE = support.REPO_ROOT / ".github" / "pull_request_template.md"
PLUGIN_TEMPLATE = support.PLUGIN / "templates" / "pr.md"
HEADING = re.compile(r"^(#{2,3}) (.+)$", re.MULTILINE)
# The repository template carries the plugin's headings, except the report that `/forge:qc`
# writes: its heading stays French (`.claude/rules/git.md`).
PLUGIN_TO_REPO_HEADING = {"Agent report": "Rapport d'agent"}


def headings(path):
    return [title.strip() for _, title in HEADING.findall(path.read_text(encoding="utf-8"))]


def section(path, title):
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^#{{2,3}} {re.escape(title)}\n(.*?)(?=^#{{2,3}} |\Z)", text, re.DOTALL | re.MULTILINE)
    assert match, f"section {title!r} absente de {path}"
    return " ".join(match.group(1).split())


class HeadingsFollowThePlugin(unittest.TestCase):
    def test_memes_titres_dans_le_meme_ordre(self):
        """Les titres du dépôt sont ceux du gabarit du plugin, dans son ordre (#231, A1)."""
        plugin = [PLUGIN_TO_REPO_HEADING.get(t, t) for t in headings(PLUGIN_TEMPLATE)]
        self.assertEqual(headings(REPO_TEMPLATE), plugin)

    def test_le_rapport_garde_son_titre_francais(self):
        """La section que `/forge:qc` écrit garde le titre `Rapport d'agent` (#231, A1)."""
        self.assertEqual(headings(REPO_TEMPLATE)[-1], "Rapport d'agent")
        self.assertIn("/forge:qc", section(REPO_TEMPLATE, "Rapport d'agent"))


class RepositoryAsksStay(unittest.TestCase):
    def test_vue_du_changement(self):
        """Change view invite à une vue : pseudo-code, arbre, diff (#46)."""
        body = section(REPO_TEMPLATE, "Change view")
        for kind in ("pseudo-code", "tree", "diff"):
            self.assertIn(kind, body)

    def test_porte(self):
        """Door nomme les deux sens (#46)."""
        body = section(REPO_TEMPLATE, "Door")
        for word in ("`two-way`", "`one-way`"):
            self.assertIn(word, body)

    def test_rayon_d_impact_dit_ce_qui_ne_change_pas(self):
        """Blast radius porte ce qu'un consommateur voit changer et ce qui ne change pas (#46, #231, A2)."""
        body = section(REPO_TEMPLATE, "Blast radius")
        for word in ("variable", "gesture", "hook", "does not change"):
            self.assertIn(word, body)

    def test_preuves(self):
        """Proofs demande le rouge avec sa raison, le vert, les commandes et le vrai poste (#46, #231, A2)."""
        body = section(REPO_TEMPLATE, "Proofs")
        for ask in ("red", "reason", "green", "unittest discover", "claude plugin validate", "real machine", "not yet"):
            self.assertIn(ask, body)

    def test_sans_tiret_cadratin(self):
        """Le gabarit reste sans tiret cadratin (#46)."""
        self.assertNotIn("\u2014", REPO_TEMPLATE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
