"""Ticket #331, A4: the key `ci-replay-light` is documented and set to ruff and mypy in this repo's `usine.md`."""

import unittest

import support
from test_ci_lint import MYPY, RUFF

KEY = "`ci-replay-light`"


def read(path: str) -> str:
    return " ".join(support.REPO_ROOT.joinpath(path).read_text(encoding="utf-8").split())


class KeyIsDocumented(unittest.TestCase):
    def test_the_template_says_the_key_is_optional_and_what_the_head_replays(self) -> None:
        """No F-NNNN: ticket #331, A4: le gabarit documente la clé, son absence et la dernière ligne."""
        template = read("plugins/forge/templates/usine.md")
        self.assertIn(f"- {KEY} : `<", template)
        at = template.index(KEY)
        # The prose comes before the example lines that carry the key.
        section = template[max(0, at - 900) : at + 300]
        for text in ("facultative", "sauf le dernier", "chaque commande de `ci-replay`", "Sans la clé"):
            self.assertIn(text, section)

    def test_the_gate_names_the_key_in_probe_14(self) -> None:
        """No F-NNNN: ticket #331, A4: la sonde 14 de qc-gate.md dit la liste légère et la tête rejouée en entier."""
        gate = read("plugins/forge/agents/qc-gate.md")
        probe = gate[gate.index("14. **Rejeu de chaque commit.**"):gate.index("15. **Âge des dépendances.**")]
        self.assertIn("ci-replay-light", probe)
        self.assertIn("la tête", probe)

    def test_the_installation_page_describes_the_light_list(self) -> None:
        """No F-NNNN: ticket #331, A4: docs/installation.md décrit la clé à l'endroit de la sonde de rejeu."""
        page = read("docs/installation.md")
        self.assertIn("ci-replay-light", page)
        section = page[page.index("Une sonde de plus rejoue la suite sur chaque commit"):]
        self.assertIn("ci-replay-light", section[:2500])


class ThisRepoSetsIt(unittest.TestCase):
    def test_usine_lists_ruff_and_mypy_as_the_light_commands(self) -> None:
        """No F-NNNN: ticket #331, A4: usine.md déclare ruff et mypy, et eux seuls, en `ci-replay-light`."""
        usine = support.REPO_ROOT.joinpath("docs/agents/usine.md").read_text(encoding="utf-8")
        lines = [line for line in usine.splitlines() if line.startswith(f"- {KEY} :")]
        self.assertEqual(lines, [f"- {KEY} : `{RUFF}`", f"- {KEY} : `{MYPY}`"])


if __name__ == "__main__":
    unittest.main()
