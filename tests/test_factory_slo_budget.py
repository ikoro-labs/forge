"""factory_slo.py budget : les actions du budget d'erreur au début d'un passage (ticket #59)."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import support  # noqa: F401  met le plugin sur le chemin d'import
from factory_slo import main
from test_factory_slo import USINE, build, isolate

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
# Sur ce monde : `accept-round-1` est tenu (33,33 % >= 5 %) et `main-green` est épuisé (>= 90 %).


class Budget(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "vide"))
        self.world = build(Path(self.tmp.name))

    def configure(self, slo: list[str], actions: list[str]) -> None:
        text = USINE + "".join(f"- `slo` : `{line}`\n" for line in slo)
        text += "".join(f"- `budget-action` : `{line}`\n" for line in actions)
        (self.world.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def budget(self, *extra: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["budget", str(self.world.root), *extra], run=self.world.runner, now=NOW)
        return code, out.getvalue(), err.getvalue()

    def state_file(self) -> Path:
        common = Path(self.world.git("rev-parse", "--path-format=absolute", "--git-common-dir"))
        return common / "forge" / "slo-status.json"

    def test_the_absent_key_is_sans_objet_and_computes_nothing(self) -> None:
        """Ticket #59 : clé absente, « sans objet », aucune action."""
        code, out, _ = self.budget()
        self.assertEqual(code, 0)
        self.assertIn("sans objet (clé `budget-action` absente)", out)
        self.assertFalse(self.state_file().exists())

    def test_it_recalculates_the_state_and_names_each_action_active_or_not(self) -> None:
        """Ticket #59 : l'état est recalculé au début du passage ; chaque action, active ou inactive."""
        self.configure(
            ["accept-round-1 | >= 5 % | 31", "main-green | >= 90 % | 31"],
            ["main-green | human-merge", "main-green | feature-freeze", "main-green | alert", "accept-round-1 | human-merge"],
        )
        code, out, _ = self.budget("--json")
        self.assertEqual(code, 0)
        self.assertTrue(self.state_file().exists())
        found = {(item["sli"], item["action"]): item["active"] for item in json.loads(out)["actions"]}
        self.assertEqual(found, {
            ("main-green", "human-merge"): True, ("main-green", "feature-freeze"): True,
            ("main-green", "alert"): True, ("accept-round-1", "human-merge"): False,
        })

    def test_the_text_says_active_and_inactive(self) -> None:
        self.configure(["accept-round-1 | >= 5 % | 31", "main-green | >= 90 % | 31"],
                       ["main-green | human-merge", "accept-round-1 | feature-freeze"])
        _, out, _ = self.budget()
        self.assertIn("ACTIVE : `human-merge` sur `main-green`", out)
        self.assertIn("inactive : `feature-freeze` sur `accept-round-1`", out)

    def test_the_return_to_tenu_is_reported_and_the_action_ends(self) -> None:
        """Ticket #59 : quand le SLO repasse à `tenu`, l'action cesse au calcul suivant, et le rapport le dit."""
        self.configure(["main-green | >= 90 % | 31"], ["main-green | human-merge"])
        self.assertIn("ACTIVE", self.budget()[1])
        self.configure(["main-green | >= 5 % | 31"], ["main-green | human-merge"])
        code, out, _ = self.budget()
        self.assertEqual(code, 0)
        self.assertIn("inactive : `human-merge` sur `main-green`", out)
        self.assertIn("autonomie rendue", out)
        self.assertNotIn("autonomie rendue", self.budget()[1])

    def test_the_action_is_held_while_the_objective_is_menace_and_the_autonomy_returns_at_tenu(self) -> None:
        """Ticket #59 : `épuisé`, puis `menacé` (80 % consommés), puis `tenu` : « autonomie rendue » seulement au dernier."""
        actions = ["main-green | human-merge"]
        # main-green vaut 66,67 % : la cible 90 % l'épuise, 60 % le laisse menacé (83 %), 50 % le tient (67 %).
        for target, active, returned in ((90, True, False), (60, True, False), (60, True, False), (50, False, True), (50, False, False)):
            with self.subTest(target=target, active=active, returned=returned):
                self.configure([f"main-green | >= {target} % | 31"], actions)
                code, out, _ = self.budget()
                self.assertEqual(code, 0)
                self.assertEqual("ACTIVE : `human-merge`" in out, active)
                self.assertEqual("autonomie rendue" in out, returned)
        self.configure(["main-green | >= 60 % | 31"], actions)
        self.assertIn("inactive", self.budget()[1])

    def test_status_keeps_the_memory_of_the_action_in_the_state_file(self) -> None:
        """La commande que donne le message du garde réécrit le fichier : elle garde ce qu'il retient."""
        self.configure(["main-green | >= 90 % | 31"], ["main-green | human-merge"])
        self.budget()
        self.configure(["main-green | >= 60 % | 31"], ["main-green | human-merge"])
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            main(["status", str(self.world.root)], run=self.world.runner, now=NOW)
        self.assertEqual(json.loads(self.state_file().read_text(encoding="utf-8"))["epuises"], ["main-green / 31 j"])

    def test_a_malformed_line_or_an_unknown_objective_fails(self) -> None:
        self.configure(["main-green | >= 90 % | 31"], ["main-green | geler"])
        code, _, err = self.budget()
        self.assertEqual(code, 1)
        self.assertIn("geler", err)
        self.configure(["main-green | >= 90 % | 31"], ["accept-round-1 | alert"])
        code, _, err = self.budget()
        self.assertEqual(code, 1)
        self.assertIn("accept-round-1", err)

    def test_actions_without_objectives_fail_rather_than_pass(self) -> None:
        self.configure([], ["main-green | human-merge"])
        code, _, err = self.budget()
        self.assertEqual(code, 1)
        self.assertIn("clé `slo`", err)


if __name__ == "__main__":
    unittest.main()
