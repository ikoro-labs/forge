"""Ticket #68: `probe_replay.py` replays the probe of each BLOCKER in a copy of the head, under the bound."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support
from parse_output import count_verdict, parse_replay

SCRIPT = support.PLUGIN / "scripts" / "probe_replay.py"
PY = f'"{sys.executable}"'
HEAD = "VERDICT: REJECT\nROUND: 1\nHEAD: 3f2a9c1\nSPEC: #68: 0 criteria covered, 0 partial, 1 missing\nFINDINGS:\n"


def blocker(code: str, expect: str, number: int = 1) -> str:
    """A blocker whose probe runs a line of Python and expects `expect` in what it prints."""
    return f"- [BLOCKER] hook.py:{number} | F-25 | evasion {number} | probe: `{PY} -c \"{code}\"` => `{expect}`\n"


class Probe(unittest.TestCase):
    """A throwaway copy of the head, an isolated environment, and the script launched on a verdict."""

    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.copy = self.dir / "head"
        self.copy.mkdir()
        self.env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "HOME": str(self.dir),
            "USERPROFILE": str(self.dir),
            "TMPDIR": str(self.dir),
            "TEMP": str(self.dir),
            "TMP": str(self.dir),
        }

    def replay(
        self, *findings: str, usine: str = "- `run-limits` : `2000 | 30`\n", extra: tuple[str, ...] = (),
        accept: bool = False,
    ) -> subprocess.CompletedProcess:
        head = HEAD.replace("REJECT", "ACCEPT") if accept else HEAD
        (self.dir / "verdict.txt").write_text(head + "".join(findings) + "GATES: green\n", encoding="utf-8")
        (self.dir / "usine-base.md").write_text(usine, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.dir / "verdict.txt"), "--root", str(self.copy),
             "--usine", str(self.dir / "usine-base.md"), *extra],
            cwd=self.dir, env=self.env, capture_output=True, text=True, timeout=120,
        )

    @staticmethod
    def rows(done: subprocess.CompletedProcess) -> list[list[str]]:
        return [line.split("\t") for line in done.stdout.splitlines() if line.strip()]


class Outcomes(Probe):
    def test_a_probe_that_prints_the_expected_output_is_confirmed(self) -> None:
        """No F-NNNN: ticket #68, critère 2: une sonde qui rend la sortie dite confirme le BLOCKER."""
        done = self.replay(blocker("print(40 + 2)", "42"))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in self.rows(done)], [["CONFIRMED", "1"]])

    def test_a_probe_that_prints_something_else_is_not_reproduced(self) -> None:
        """No F-NNNN: ticket #68, critère 2: une sonde qui ne rend pas la sortie dite fait du BLOCKER un non reproduit."""
        done = self.replay(blocker("print('nothing wrong')", "evasion works"))
        rows = self.rows(done)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in rows], [["NOT REPRODUCED", "1"]])
        # The detail says what the probe printed, so the report can show it.
        self.assertIn("nothing wrong", rows[0][2])

    def test_a_probe_past_its_delay_is_killed_and_is_not_reproduced(self) -> None:
        """No F-NNNN: ticket #68, critère 2: une sonde qui dépasse le délai est tuée, et le BLOCKER n'est pas reproduit."""
        done = self.replay(
            blocker("import time; time.sleep(60)", "never printed"),
            usine="- `run-limits` : `2000 | 2`\n",
        )
        rows = self.rows(done)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in rows], [["NOT REPRODUCED", "1"]])
        self.assertIn("délai de 2 s dépassé", rows[0][2])

    def test_the_output_of_the_error_stream_counts_too(self) -> None:
        """No F-NNNN: ticket #68, critère 2: la sortie dite peut venir de stderr, comme une traceback."""
        done = self.replay(blocker("import sys; sys.stderr.write('boom: refused')", "boom: refused"))
        self.assertEqual([row[:2] for row in self.rows(done)], [["CONFIRMED", "1"]], done.stdout + done.stderr)

    def test_the_probe_runs_in_the_copy_it_is_given(self) -> None:
        """No F-NNNN: ticket #68, critère 2: la sonde tourne dans la copie de la tête, pas dans le dépôt courant."""
        (self.copy / "marker.txt").write_text("in the copy", encoding="utf-8")
        done = self.replay(blocker("print(open('marker.txt').read())", "in the copy"))
        self.assertEqual([row[:2] for row in self.rows(done)], [["CONFIRMED", "1"]], done.stdout + done.stderr)

    def test_each_blocker_has_its_own_line_by_finding_number(self) -> None:
        """No F-NNNN: ticket #68, critère 2: une ligne par BLOCKER, numérotée comme son constat dans FINDINGS."""
        done = self.replay(
            "- [NOTE] wording\n",
            blocker("print('a')", "a", 2),
            "- [BLOCKER] hook.py:9 | F-25 | read twice\n",
            blocker("print('b')", "zzz", 4),
        )
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(
            [row[:2] for row in self.rows(done)],
            [["CONFIRMED", "2"], ["DEDUCED", "3"], ["NOT REPRODUCED", "4"]],
        )


class NotRun(Probe):
    def test_a_post_out_of_budget_runs_nothing(self) -> None:
        """No F-NNNN: ticket #68, critère 2: hors budget du poste, la sonde est NOT RUN et la commande ne part pas."""
        marker = self.dir / "ran.txt"
        done = self.replay(
            blocker(f"open(r'{marker}', 'w').write('x'); print('1')", "1"),
            usine="- `run-limits` : `2000 | 30`\n- `run-budget` : `99999999 | 12 | 2 | 0`\n",
        )
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in self.rows(done)], [["NOT RUN", "1"]])
        self.assertIn("budget du poste non tenu", self.rows(done)[0][2])
        self.assertFalse(marker.exists())

    def test_without_run_limits_the_probe_is_not_run_and_never_unbounded(self) -> None:
        """No F-NNNN: ticket #68, critère 2: sans la clé run-limits, aucune commande ne tourne sans borne."""
        marker = self.dir / "ran.txt"
        done = self.replay(blocker(f"open(r'{marker}', 'w').write('x'); print('1')", "1"), usine="")
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in self.rows(done)], [["NOT RUN", "1"]])
        self.assertIn("sans objet (clé `run-limits` absente)", self.rows(done)[0][2])
        self.assertFalse(marker.exists())

    def test_a_verdict_it_cannot_read_is_not_run(self) -> None:
        """No F-NNNN: ticket #68, critère 2: un verdict illisible ne donne pas de ligne CONFIRMED."""
        (self.dir / "verdict.txt").write_text("nothing here\n", encoding="utf-8")
        (self.dir / "usine-base.md").write_text("- `run-limits` : `2000 | 30`\n", encoding="utf-8")
        done = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.dir / "verdict.txt"), "--root", str(self.copy),
             "--usine", str(self.dir / "usine-base.md")],
            cwd=self.dir, env=self.env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(done.returncode, 2)
        self.assertTrue(done.stdout.startswith("NOT RUN"), done.stdout)

    def test_a_copy_that_is_not_a_folder_is_not_run(self) -> None:
        """No F-NNNN: ticket #68, critère 2: sans copie de la tête où la lancer, la sonde ne part pas."""
        done = self.replay(blocker("print(1)", "1"), extra=("--root", str(self.dir / "absent")))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertTrue(done.stdout.startswith("NOT RUN"), done.stdout)


class WithoutProbe(Probe):
    def test_a_verdict_with_no_blocker_has_nothing_to_replay(self) -> None:
        """No F-NNNN: ticket #68, critère 2: sans BLOCKER, une ligne NONE et un code 0."""
        done = self.replay("- [MINOR] a.py:1 | F-18 | wording\n", accept=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual([row[0] for row in self.rows(done)], ["NONE"])

    def test_a_blocker_without_probe_is_deduced_and_runs_nothing(self) -> None:
        """No F-NNNN: ticket #68, critère 3: un BLOCKER sans sonde reste compté, marqué déduit."""
        done = self.replay("- [BLOCKER] hook.py:9 | F-25 | the second read is unchecked\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in self.rows(done)], [["DEDUCED", "1"]])


class WithTheCountingRule(Probe):
    def test_the_lines_feed_the_counting_rule_end_to_end(self) -> None:
        """No F-NNNN: ticket #68, critère 4: les lignes du rejeu sont celles que la règle de comptage lit."""
        text = HEAD + blocker("print('fine')", "evasion works") + "GATES: green\n"
        done = self.replay(blocker("print('fine')", "evasion works"))
        counted = count_verdict(text, parse_replay(done.stdout))
        self.assertEqual(counted["VERDICT"], "ACCEPT")
        self.assertEqual(counted["DEMOTED"], [1])

        done = self.replay(blocker("print('evasion works')", "evasion works"))
        self.assertEqual(count_verdict(text, parse_replay(done.stdout))["VERDICT"], "REJECT")


if __name__ == "__main__":
    unittest.main()
