"""factory_slo.py status: la date de révision des objectifs (clé `slo-review-date`, ticket #76)."""

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

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
SLO = "- `slo` : `accept-round-1 | >= 5 % | 31`\n"


class Revision(unittest.TestCase):
    """La date que `status` signale une fois passée ; une clé absente reste « sans objet »."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "vide"))
        self.world = build(Path(self.tmp.name))

    def declare(self, *lines: str) -> None:
        text = USINE + SLO + "".join(f"- `slo-review-date` : `{line}`\n" for line in lines)
        (self.world.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def status(self, *extra: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["status", str(self.world.root), *extra], run=self.world.runner, now=NOW)
        return code, out.getvalue(), err.getvalue()

    def state_file(self) -> Path:
        common = Path(self.world.git("rev-parse", "--path-format=absolute", "--git-common-dir"))
        return common / "forge" / "slo-status.json"

    def test_a_past_review_date_is_flagged_by_status(self) -> None:
        """Ticket #76 : une fois la date passée, `status` le dit, dans le tableau et dans le JSON."""
        self.declare("2026-10-31")
        code, out, _ = self.status()
        self.assertEqual(code, 0)
        self.assertIn("Révision des objectifs : passée, prévue le 2026-10-31", out)
        self.assertIn("2026-10-31", out)
        _, as_json, _ = self.status("--json")
        self.assertEqual(json.loads(as_json)["revision"], {"date": "2026-10-31", "passee": True})

    def test_a_future_review_date_is_shown_and_not_flagged(self) -> None:
        self.declare("2026-12-16")
        _, out, _ = self.status()
        self.assertIn("Révision des objectifs : prévue le 2026-12-16", out)
        self.assertNotIn("passée", out)
        _, as_json, _ = self.status("--json")
        self.assertEqual(json.loads(as_json)["revision"], {"date": "2026-12-16", "passee": False})

    def test_the_day_itself_is_not_yet_passed(self) -> None:
        """La date est celle du jour (UTC) : la révision est due, pas encore en retard."""
        self.declare("2026-11-01")
        _, as_json, _ = self.status("--json")
        self.assertIs(json.loads(as_json)["revision"]["passee"], False)

    def test_an_absent_key_is_sans_objet_without_a_guessed_date(self) -> None:
        """Ticket #76 : clé absente, « sans objet (clé `slo-review-date` absente) », aucune valeur par défaut."""
        self.declare()
        _, out, _ = self.status()
        self.assertIn("sans objet (clé `slo-review-date` absente)", out)
        _, as_json, _ = self.status("--json")
        revision = json.loads(as_json)["revision"]
        self.assertEqual(revision["statut"], "sans objet")
        self.assertNotIn("date", revision)

    def test_an_unreadable_date_fails_status_and_writes_nothing(self) -> None:
        """Une date qui n'est pas AAAA-MM-JJ, ou une clé répétée, fait échouer la commande : jamais ignorée en silence."""
        for lines in (("16/12/2026",), ("2026-13-45",), ("2026-12-16", "2027-01-16")):
            with self.subTest(lines=lines):
                self.declare(*lines)
                code, _, err = self.status()
                self.assertEqual(code, 1)
                self.assertIn("slo-review-date", err)
                self.assertFalse(self.state_file().exists())


class DepotConfiguration(unittest.TestCase):
    """La configuration réelle de ce dépôt (`docs/agents/usine.md`), lue par `status` sur le monde fictif."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "vide"))
        self.world = build(Path(self.tmp.name))
        real = support.REPO_ROOT / "docs" / "agents" / "usine.md"
        (self.world.root / "docs" / "agents" / "usine.md").write_text(real.read_text(encoding="utf-8"), encoding="utf-8")

    def run_command(self, command: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([command, str(self.world.root), "--json"], run=self.world.runner, now=NOW)
        return code, out.getvalue(), err.getvalue()

    def test_status_reads_this_repository_configuration_without_error(self) -> None:
        """Ticket #76 : `status` lit les objectifs et la date de révision de ce dépôt, sans erreur."""
        code, out, err = self.run_command("status")
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("sans objet (clé `slo` absente)", out)
        document = json.loads(out)
        labels = {f"{item['sli']} {item['statistique']}" if item["statistique"] else item["sli"] for item in document["objectifs"]}
        self.assertEqual(labels, {"release-lag p90", "escaped-defects", "false-accept", "main-green"})
        self.assertEqual(document["revision"], {"date": "2026-12-16", "passee": False})

    def test_budget_reads_this_repository_actions_on_declared_objectives(self) -> None:
        """Ticket #76 : chaque ligne de `budget-action` de ce dépôt nomme un objectif de `slo` (sinon `budget` échoue)."""
        code, out, err = self.run_command("budget")
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("sans objet (clé `budget-action` absente)", out)
        self.assertEqual(len(json.loads(out)["actions"]), 4)


if __name__ == "__main__":
    unittest.main()
