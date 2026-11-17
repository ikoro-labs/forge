"""Ticket #156, A3: the SLI `guard-refusals`, refusals of the guards per merged PR, on a fake journal."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import support  # noqa: F401
from factory_slo import Factory, guard_refusals, main, markdown
from test_factory_slo import SINCE, UNTIL, USINE, World, build, isolate, pr

import refusal_journal  # isort: skip - after `support`, which puts the hooks on the import path


def entry(date: str, guard: str, agent: str, repo: str = "projet") -> dict[str, str]:
    return {
        "date": date, "guard": guard, "rule": "force-push", "agent": agent,
        "repo": repo, "branch": "feat/x", "verb": "git push",
    }


class GuardRefusals(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.world = World(Path(self.tmp.name))
        self.world.answers = {
            "repo view": {"nameWithOwner": "o/r", "defaultBranchRef": {"name": "main"}},
            "pr list": [
                pr(1, "2026-10-02T00:00:00Z", state="MERGED", mergedAt="2026-10-03T10:00:00Z", mergeCommit={"oid": "a" * 40}),
                pr(2, "2026-10-05T00:00:00Z", state="MERGED", mergedAt="2026-10-06T10:00:00Z", mergeCommit={"oid": "b" * 40}),
                pr(3, "2026-10-07T00:00:00Z"),
            ],
            "issue list": [],
        }
        isolate(self, self.tmp.name)
        self.journal = Path(self.tmp.name) / "refusals"
        patcher = mock.patch.object(refusal_journal, "journal_dir", lambda: self.journal)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, day: str, *lines: dict[str, str]) -> None:
        self.journal.mkdir(exist_ok=True)
        (self.journal / f"{day}.jsonl").write_text(
            "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
        )

    def sli(self) -> dict:
        return guard_refusals(Factory(self.world.root, SINCE, UNTIL, self.world.runner)).to_dict()

    def test_refusals_per_merged_pr_with_the_detail_by_guard_and_agent(self) -> None:
        """#156 A3.1: 4 refusals and 2 merged PRs give 2.0; a line outside the window is not counted."""
        self.write("2026-10-04", entry("2026-10-04T08:00:00+00:00", "guard_git", "main"),
                   entry("2026-10-04T09:00:00+00:00", "guard_git", "main"))
        self.write("2026-10-10", entry("2026-10-10T08:00:00+00:00", "guard_coder", "forge:coder"),
                   entry("2026-10-10T09:00:00+00:00", "guard_readonly", "forge:qc-conf"),
                   entry("2026-10-10T10:00:00+00:00", "guard_git", "main", repo="autre"))
        self.write("2026-09-30", entry("2026-09-30T08:00:00+00:00", "guard_git", "main"))
        self.write("2026-11-01", entry("2026-11-01T00:00:00+00:00", "guard_git", "main"))
        result = self.sli()
        self.assertEqual(result["statut"], "calculé")
        self.assertEqual((result["numerateur"], result["denominateur"], result["valeur"]), (4, 2, 2.0))
        self.assertEqual(result["par_garde"], {"guard_git": 2, "guard_coder": 1, "guard_readonly": 1})
        self.assertEqual(result["par_agent"], {"main": 2, "forge:coder": 1, "forge:qc-conf": 1})

    def test_without_a_journal_the_indicator_is_sans_objet_and_says_why(self) -> None:
        """#156 A3.1: no journal on this host: "sans objet", never 0."""
        result = self.sli()
        self.assertEqual(result["statut"], "sans objet")
        self.assertIn("journal", result["raison"])

    def test_a_journal_without_a_refusal_in_the_window_is_zero_not_sans_objet(self) -> None:
        self.write("2026-09-30", entry("2026-09-30T08:00:00+00:00", "guard_git", "main"))
        result = self.sli()
        self.assertEqual((result["numerateur"], result["valeur"]), (0, 0.0))

    def test_an_unreadable_line_is_left_out(self) -> None:
        self.journal.mkdir()
        good = json.dumps(entry("2026-10-04T08:00:00+00:00", "guard_git", "main"))
        (self.journal / "2026-10-04.jsonl").write_text(f"pas du json\n{good}\n[1]\n", encoding="utf-8")
        self.assertEqual(self.sli()["numerateur"], 1)

    def test_the_indicator_is_computed_with_the_others_and_says_it_is_per_host(self) -> None:
        """#156 A3.1, A4: the table lists it, and its text names the limit (one journal per host)."""
        self.write("2026-10-04", entry("2026-10-04T08:00:00+00:00", "guard_git", "main"))
        factory = Factory(self.world.root, SINCE, UNTIL, self.world.runner)
        table = markdown([guard_refusals(factory)], self.world.root, SINCE, UNTIL)
        line = next(row for row in table.splitlines() if row.startswith("| `guard-refusals`"))
        self.assertIn("0.5", line)
        self.assertIn("poste", line)


NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


class GuardRefusalsInTheReport(unittest.TestCase):
    """#156 A3: `factory_slo.py report` itself shows the refusals, with the detail by guard and by agent."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.world = build(Path(self.tmp.name))
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "claude"))
        usine = USINE + "- `slo` : `accept-round-1 | >= 5 % | 31`\n"
        (self.world.root / "docs" / "agents" / "usine.md").write_text(usine, encoding="utf-8")
        self.journal = Path(self.tmp.name) / "refusals"
        patcher = mock.patch.object(refusal_journal, "journal_dir", lambda: self.journal)
        patcher.start()
        self.addCleanup(patcher.stop)

    def runner(self, cmd: list[str], cwd: Path) -> str:
        if cmd[:2] == ["gh", "api"] and cmd[2].endswith("/check-runs") and cmd[2] not in self.world.answers:
            return json.dumps({"check_runs": []})
        return self.world.runner(cmd, cwd)

    def report(self, *extra: str) -> str:
        out = io.StringIO()
        with redirect_stdout(out):
            main(["report", str(self.world.root), *extra], run=self.runner, now=NOW)
        return out.getvalue()

    def test_the_report_shows_the_value_and_the_detail_by_guard_and_agent(self) -> None:
        """#156 A3: 3 refusals over 3 PRs merged in the 30 days give 1.0, detailed by guard and by agent."""
        self.journal.mkdir()
        lines = [
            entry("2026-10-04T08:00:00+00:00", "guard_git", "main"),
            entry("2026-10-04T09:00:00+00:00", "guard_git", "main"),
            entry("2026-10-10T08:00:00+00:00", "guard_coder", "forge:coder"),
            entry("2026-10-10T09:00:00+00:00", "guard_git", "main", repo="autre"),
        ]
        (self.journal / "2026-10-04.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
        text = self.report()
        section = text[text.index("Refus des gardes"):]
        self.assertIn("`guard-refusals`", section)
        self.assertIn("1.0 refus par PR fusionnée (3/3)", section)
        self.assertIn("guard_git : 2", section)
        self.assertIn("guard_coder : 1", section)
        self.assertIn("main : 2", section)
        self.assertIn("forge:coder : 1", section)

    def test_the_report_says_sans_objet_without_a_journal(self) -> None:
        """#156 A3: no journal on this host: the section says "sans objet" and why, never 0."""
        text = self.report()
        section = text[text.index("Refus des gardes"):]
        self.assertIn("sans objet", section)
        self.assertIn("journal", section)

    def test_the_json_report_carries_the_same_section(self) -> None:
        """#156 A3: `report --json` has the refusals under `refus`, with the detail."""
        self.journal.mkdir()
        (self.journal / "2026-10-04.jsonl").write_text(
            json.dumps(entry("2026-10-04T08:00:00+00:00", "guard_git", "main")) + "\n", encoding="utf-8"
        )
        document = json.loads(self.report("--json"))
        self.assertEqual(document["refus"]["par_garde"], {"guard_git": 1})
        self.assertEqual(document["refus"]["par_agent"], {"main": 1})


if __name__ == "__main__":
    unittest.main()
