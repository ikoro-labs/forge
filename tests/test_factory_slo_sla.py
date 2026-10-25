"""factory_slo.py queue et sla : la file par gravité et les engagements de délai (ticket #60)."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import support  # noqa: F401  met les scripts sur le chemin d'import
from test_factory_slo import USINE, World, isolate

from factory_slo import main

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
SLA = "- `sla` : `sev1 | 4 h | 24 h | 3 j`\n- `sla` : `sev2 | 2 j | 7 j | 14 j`\n"


def ticket(number: int, created: str, labels: tuple[str, ...] = ()) -> dict:
    return {"number": number, "createdAt": created, "labels": [{"name": name} for name in labels]}


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "vide"))
        self.world = World(Path(self.tmp.name))

    def configure(self, extra: str) -> None:
        (self.world.root / "docs" / "agents" / "usine.md").write_text(USINE + extra, encoding="utf-8")

    def run_main(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([args[0], str(self.world.root), *args[1:]], run=self.world.runner, now=NOW)
        return code, out.getvalue(), err.getvalue()


class Queue(Base):
    def setUp(self) -> None:
        super().setUp()
        self.world.answers = {
            "issue view 1 ": ticket(1, "2026-10-01T00:00:00Z", ("sev3",)),
            "issue view 2 ": ticket(2, "2026-10-02T00:00:00Z"),
            "issue view 3 ": ticket(3, "2026-10-03T00:00:00Z", ("sev2",)),
            "issue view 4 ": ticket(4, "2026-10-19T00:00:00Z", ("sev1",)),
            "issue view 5 ": ticket(5, "2026-10-02T00:00:00Z", ("sev2",)),
        }

    def test_the_queue_takes_the_tickets_by_severity_then_by_deadline(self) -> None:
        """Ticket #60, critère 3 : sev1 devant tout, puis sev2 par échéance, sev3, puis sans gravité."""
        self.configure(SLA)
        code, out, _ = self.run_main("queue", "1", "2", "3", "4", "5", "--json")
        self.assertEqual(code, 0)
        rows = json.loads(out)["file"]
        self.assertEqual([row["ticket"] for row in rows], [4, 5, 3, 1, 2])
        self.assertEqual(rows[0]["gravite"], "sev1")
        self.assertEqual(rows[0]["echeance"], "2026-10-19T04:00:00+00:00")
        self.assertEqual(rows[1]["echeance"], "2026-10-04T00:00:00+00:00")

    def test_the_markdown_queue_names_each_ticket_in_order(self) -> None:
        self.configure(SLA)
        _, out, _ = self.run_main("queue", "1", "2", "3", "4", "5")
        positions = [out.index(f"#{n}") for n in (4, 5, 3, 1, 2)]
        self.assertEqual(positions, sorted(positions))

    def test_without_the_sla_key_the_deadline_is_sans_objet_and_severity_still_sorts(self) -> None:
        """Ticket #60 : clé absente, « sans objet (clé `sla` absente) », aucune échéance devinée."""
        self.configure("")
        _, out, _ = self.run_main("queue", "1", "2", "3", "4", "5", "--json")
        document = json.loads(out)
        self.assertEqual([row["ticket"] for row in document["file"]], [4, 3, 5, 1, 2])
        self.assertTrue(all(row["echeance"] is None for row in document["file"]))
        self.assertIn("sans objet (clé `sla` absente)", document["echeances"])
        _, text, _ = self.run_main("queue", "1", "2")
        self.assertIn("sans objet (clé `sla` absente)", text)

    def test_a_malformed_key_fails_the_command(self) -> None:
        self.configure("- `sla` : `sev1 | 4 | 24 h | 3 j`\n")
        code, _, err = self.run_main("queue", "1")
        self.assertEqual(code, 1)
        self.assertIn("`sla`", err)


if __name__ == "__main__":
    unittest.main()
