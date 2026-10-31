"""factory_slo.py status: les objectifs de service (SLO) de `usine.md` et leur budget d'erreur (ticket #57)."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import support  # noqa: F401  met le plugin sur le chemin d'import
from factory_slo import Sli, SloError, evaluate, main, parse_slo
from test_factory_slo import USINE, build, isolate

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def ratio(name: str, percent: float) -> Sli:
    return Sli(name, data={"valeur": percent / 100})


def duration(name: str, p90: float) -> Sli:
    return Sli(name, data={"mediane_h": p90 / 2, "p90_h": p90})


def one(line: str):
    return parse_slo([line])[0]


class Budget(unittest.TestCase):
    """Le calcul du budget d'erreur, comparateur par comparateur."""

    def test_at_least_budget_is_the_gap_between_the_target_and_perfect(self) -> None:
        """Ticket #57 : `>= 80 %` laisse 20 points de marge ; 10 points perdus en consomment la moitié."""
        slo = one("accept-round-1 | >= 80 % | 30")
        result = evaluate(slo, ratio("accept-round-1", 90))
        self.assertEqual((result["valeur"], result["budget"], result["consomme"], result["etat"]), (90, 20, 0.5, "tenu"))
        self.assertEqual(result["reste"], 10)

    def test_at_most_budget_is_the_target_itself(self) -> None:
        """Ticket #57 : `<= 24 h` laisse 24 h de marge ; 12 h en consomment la moitié."""
        result = evaluate(one("lead-time p90 | <= 24 h | 30"), duration("lead-time", 12))
        self.assertEqual((result["valeur"], result["budget"], result["consomme"], result["etat"]), (12, 24, 0.5, "tenu"))

    def test_at_most_on_a_ratio(self) -> None:
        result = evaluate(one("escaped-defects | <= 5 % | 30"), ratio("escaped-defects", 2))
        self.assertEqual((result["budget"], result["consomme"], result["etat"]), (5, 0.4, "tenu"))

    def test_the_three_states_and_their_edges(self) -> None:
        """Ticket #57 : tenu jusqu'à 75 % consommés compris, menacé au-delà, épuisé à 100 % et plus."""
        slo = one("lead-time p90 | <= 24 h | 30")
        states = {value: evaluate(slo, duration("lead-time", value))["etat"] for value in (0, 18, 19, 23.9, 24, 30)}
        self.assertEqual(states, {0: "tenu", 18: "tenu", 19: "menacé", 23.9: "menacé", 24: "épuisé", 30: "épuisé"})
        self.assertEqual(evaluate(slo, duration("lead-time", 30))["consomme"], 1.25)

    def test_at_least_below_the_target_is_exhausted(self) -> None:
        result = evaluate(one("accept-round-1 | >= 80 % | 30"), ratio("accept-round-1", 70))
        self.assertEqual((result["consomme"], result["etat"]), (1.5, "épuisé"))

    def test_a_target_without_margin_is_held_or_exhausted_never_a_division_by_zero(self) -> None:
        slo = one("main-green | >= 100 % | 30")
        self.assertEqual(evaluate(slo, ratio("main-green", 100))["etat"], "tenu")
        self.assertEqual(evaluate(slo, ratio("main-green", 99))["etat"], "épuisé")

    def test_a_window_without_data_is_sans_objet_with_its_reason_never_tenu(self) -> None:
        """Ticket #57 : une fenêtre sans données n'est ni tenue ni épuisée."""
        result = evaluate(one("accept-round-1 | >= 80 % | 30"), Sli("accept-round-1", reason="aucune PR jugée"))
        self.assertEqual((result["statut"], result["raison"]), ("sans objet", "aucune PR jugée"))
        self.assertNotIn("etat", result)
        self.assertNotIn("valeur", result)

    def test_duration_statistic_picks_the_median_or_the_p90(self) -> None:
        sli = duration("lead-time", 20)
        self.assertEqual(evaluate(one("lead-time mediane | <= 24 h | 30"), sli)["valeur"], 10)
        self.assertEqual(evaluate(one("lead-time p90 | <= 24 h | 30"), sli)["valeur"], 20)


class Lines(unittest.TestCase):
    """Une ligne de `slo` : `<sli> | <comparateur> <cible> | <fenêtre en jours>`."""

    def test_documented_examples_parse(self) -> None:
        first, second = parse_slo(["accept-round-1 | >= 80 % | 30", "lead-time p90 | <= 24 h | 30"])
        self.assertEqual((first.sli, first.stat, first.comparator, first.target, first.unit, first.days), ("accept-round-1", None, ">=", 80.0, "%", 30))
        self.assertEqual((second.sli, second.stat, second.comparator, second.target, second.unit, second.days), ("lead-time", "p90", "<=", 24.0, "h", 30))

    def test_tokens_take_a_bare_number(self) -> None:
        self.assertEqual(one("tokens-per-merge | <= 500000 | 14").unit, "jetons")

    def test_a_malformed_line_fails_naming_the_line(self) -> None:
        """Ticket #57 : jamais un objectif ignoré en silence ; l'erreur cite la ligne fautive."""
        bad = [
            "accept-round-1 >= 80 % 30",
            "accept-round-1 | > 80 % | 30",
            "accept-round-1 | >= 80 | 30",
            "accept-round-1 | >= 80 h | 30",
            "accept-round-1 | >= 80 % | trente",
            "accept-round-1 | >= 80 % | 0",
            "accept-round-1 | >= 80 %",
            "lead-time | <= 24 h | 30",
            "lead-time p90 | >= 24 h | 30",
            "lead-time p50 | <= 24 h | 30",
            "accept-round-1 p90 | >= 80 % | 30",
        ]
        for line in bad:
            with self.assertRaises(SloError, msg=line) as caught:
                parse_slo([line])
            self.assertIn(line, str(caught.exception))

    def test_a_ratio_target_beyond_100_percent_fails_naming_the_line(self) -> None:
        """Revue de #79, reportée en #58 : `>= 120 %` (ou `>= 800 %` pour 80,0) n'est pas rendu `tenu` en silence."""
        for line in ("accept-round-1 | >= 120 % | 30", "accept-round-1 | >= 800 % | 30", "escaped-defects | <= 150 % | 30"):
            with self.assertRaises(SloError, msg=line) as caught:
                parse_slo([line])
            self.assertIn(line, str(caught.exception))
            self.assertIn("100", str(caught.exception))
        self.assertEqual(one("main-green | >= 100 % | 30").target, 100.0)

    def test_an_unknown_sli_fails_naming_the_line(self) -> None:
        with self.assertRaises(SloError) as caught:
            parse_slo(["bonheur | >= 80 % | 30"])
        self.assertIn("bonheur | >= 80 % | 30", str(caught.exception))
        self.assertIn("inconnu", str(caught.exception))

    def test_every_faulty_line_is_reported_at_once(self) -> None:
        with self.assertRaises(SloError) as caught:
            parse_slo(["accept-round-1 | >= 80 % | 30", "x | y", "z | w"])
        self.assertIn("x | y", str(caught.exception))
        self.assertIn("z | w", str(caught.exception))


class Status(unittest.TestCase):
    """La commande de bout en bout, sur les réponses `gh` fictives du monde de `test_factory_slo`."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "vide"))
        self.world = build(Path(self.tmp.name))

    def set_slo(self, *lines: str) -> None:
        text = USINE + "".join(f"- `slo` : `{line}`\n" for line in lines)
        (self.world.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def status(self, *extra: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["status", str(self.world.root), *extra], run=self.world.runner, now=NOW)
        return code, out.getvalue(), err.getvalue()

    def state_file(self) -> Path:
        common = Path(self.world.git("rev-parse", "--path-format=absolute", "--git-common-dir"))
        return common / "forge" / "slo-status.json"

    def test_status_computes_each_objective_over_its_own_window(self) -> None:
        """Ticket #57 : valeur, budget et état de chaque objectif, sur sa fenêtre glissante."""
        self.set_slo("accept-round-1 | >= 5 % | 31", "accept-round-1 | >= 5 % | 5")
        code, out, _ = self.status("--json")
        self.assertEqual(code, 0)
        by_window = {item["fenetre_jours"]: item for item in json.loads(out)["objectifs"]}
        self.assertEqual(by_window[31]["valeur"], 33.33)
        self.assertEqual(by_window[31]["etat"], "tenu")
        self.assertEqual(by_window[5]["statut"], "sans objet")

    def test_status_writes_the_state_file_with_date_and_base_head(self) -> None:
        """Ticket #57 : `<git-common-dir>/forge/slo-status.json`, avec la date du calcul et la tête de la base."""
        self.set_slo("accept-round-1 | >= 5 % | 31", "main-green | >= 90 % | 31")
        code, _, _ = self.status()
        self.assertEqual(code, 0)
        document = json.loads(self.state_file().read_text(encoding="utf-8"))
        self.assertEqual(document["calcule_le"], NOW.isoformat())
        self.assertEqual(document["tete_base"], self.world.git("rev-parse", "main"))
        self.assertEqual(document["base"], "main")
        states = {item["sli"]: item["etat"] for item in document["objectifs"]}
        self.assertEqual(states, {"accept-round-1": "tenu", "main-green": "épuisé"})

    def test_an_unreadable_line_fails_status_and_writes_nothing(self) -> None:
        self.set_slo("accept-round-1 | >= 5 % | 31", "accept-round-1 >= oups")
        code, _, err = self.status()
        self.assertEqual(code, 1)
        self.assertIn("accept-round-1 >= oups", err)
        self.assertFalse(self.state_file().exists())

    def test_an_unknown_sli_fails_status(self) -> None:
        self.set_slo("bonheur | >= 80 % | 30")
        code, _, err = self.status()
        self.assertEqual(code, 1)
        self.assertIn("bonheur", err)

    def test_missing_key_is_sans_objet_and_writes_nothing(self) -> None:
        """Ticket #57 : clé absente, « sans objet (clé `slo` absente) »."""
        code, out, _ = self.status()
        self.assertEqual(code, 0)
        self.assertIn("sans objet (clé `slo` absente)", out)
        self.assertFalse(self.state_file().exists())

    def test_markdown_table_names_the_state(self) -> None:
        self.set_slo("accept-round-1 | >= 5 % | 31")
        _, out, _ = self.status()
        self.assertIn("| `accept-round-1` | >= 5 % | 31 j | 33.33 % |", out)
        self.assertIn("tenu", out)

    def test_restore_time_objective_uses_every_severity(self) -> None:
        self.set_slo("restore-time p90 | <= 72 h | 31")
        _, out, _ = self.status("--json")
        item = json.loads(out)["objectifs"][0]
        self.assertEqual((item["valeur"], item["etat"]), (48, "tenu"))


if __name__ == "__main__":
    unittest.main()
