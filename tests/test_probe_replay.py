"""Ticket #68: `probe_replay.py` replays the probe of each BLOCKER in a copy of the head, under the bound.

The probe is closed: the judge names a test file of the head, and the script runs it by the command of
the key `red-replay`, as the replay on the base does. Nothing the judge writes runs as a command.
"""

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
# The test file runs as a script: the command of the key prints what the file prints.
USINE = (
    "- `run-limits` : `2000 | 30`\n"
    "- `test-path` : `tests/`\n"
    f"- `red-replay` : `{PY} {{file}}`\n"
)


def blocker(name: str, expect: str, number: int = 1) -> str:
    """A blocker whose probe names the test file `name` and expects `expect` in what its run prints."""
    return f"- [BLOCKER] hook.py:{number} | F-25 | evasion {number} | probe: `{name}` => `{expect}`\n"


class Probe(unittest.TestCase):
    """A throwaway copy of the head, an isolated environment, and the script launched on a verdict."""

    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.copy = self.dir / "head"
        (self.copy / "tests").mkdir(parents=True)
        self.env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "HOME": str(self.dir),
            "USERPROFILE": str(self.dir),
            "TMPDIR": str(self.dir),
            "TEMP": str(self.dir),
            "TMP": str(self.dir),
        }

    def write_test(self, name: str, code: str) -> str:
        """A test file of the head, at `tests/<name>`; its path from the root of the copy."""
        (self.copy / "tests" / name).write_text(code + "\n", encoding="utf-8")
        return f"tests/{name}"

    def replay(
        self, *findings: str, usine: str = USINE, extra: tuple[str, ...] = (), accept: bool = False,
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
        name = self.write_test("test_sum.py", "print(40 + 2)")
        done = self.replay(blocker(name, "42"))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in self.rows(done)], [["CONFIRMED", "1"]])

    def test_a_probe_that_prints_something_else_is_not_reproduced(self) -> None:
        """No F-NNNN: ticket #68, critère 2: une sonde qui ne rend pas la sortie dite fait du BLOCKER un non reproduit."""
        name = self.write_test("test_fine.py", "print('nothing wrong')")
        done = self.replay(blocker(name, "evasion works"))
        rows = self.rows(done)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in rows], [["NOT REPRODUCED", "1"]])
        # The detail says what the probe printed, so the report can show it.
        self.assertIn("nothing wrong", rows[0][2])

    def test_a_probe_past_its_delay_is_killed_and_is_not_reproduced(self) -> None:
        """No F-NNNN: ticket #68, critère 2: une sonde qui dépasse le délai est tuée, et le BLOCKER n'est pas reproduit."""
        name = self.write_test("test_slow.py", "import time; time.sleep(60)")
        done = self.replay(blocker(name, "never printed"), usine=USINE.replace("2000 | 30", "2000 | 2"))
        rows = self.rows(done)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in rows], [["NOT REPRODUCED", "1"]])
        self.assertIn("délai de 2 s dépassé", rows[0][2])

    def test_the_output_of_the_error_stream_counts_too(self) -> None:
        """No F-NNNN: ticket #68, critère 2: la sortie dite peut venir de stderr, comme une traceback."""
        name = self.write_test("test_raise.py", "raise AssertionError('boom: refused')")
        done = self.replay(blocker(name, "AssertionError: boom: refused"))
        self.assertEqual([row[:2] for row in self.rows(done)], [["CONFIRMED", "1"]], done.stdout + done.stderr)

    def test_the_test_file_runs_in_the_copy_it_is_given(self) -> None:
        """No F-NNNN: ticket #68, critère 2: la sonde tourne dans la copie de la tête, pas dans le dépôt courant."""
        (self.copy / "marker.txt").write_text("in the copy", encoding="utf-8")
        name = self.write_test("test_marker.py", "print(open('marker.txt').read())")
        done = self.replay(blocker(name, "in the copy"))
        self.assertEqual([row[:2] for row in self.rows(done)], [["CONFIRMED", "1"]], done.stdout + done.stderr)

    def test_each_blocker_has_its_own_line_by_finding_number(self) -> None:
        """No F-NNNN: ticket #68, critère 2: une ligne par BLOCKER, numérotée comme son constat dans FINDINGS."""
        first = self.write_test("test_a.py", "print('a')")
        second = self.write_test("test_b.py", "print('b')")
        done = self.replay(
            "- [NOTE] wording\n",
            blocker(first, "a", 2),
            "- [BLOCKER] hook.py:9 | F-25 | read twice\n",
            blocker(second, "zzz", 4),
        )
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(
            [row[:2] for row in self.rows(done)],
            [["CONFIRMED", "2"], ["DEDUCED", "3"], ["NOT REPRODUCED", "4"]],
        )


class Closed(Probe):
    """Revue, tour 2 : la sonde n'est plus une commande. Seule la commande de la clé `red-replay` tourne."""

    def test_the_command_that_runs_is_the_one_of_the_key_with_the_file_named(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: la commande lancée est celle de la clé red-replay, {file} remplacé par le nom."""
        name = self.write_test("test_named.py", "")
        usine = USINE.replace(f"{PY} {{file}}", f"{PY} -c \"import sys; print('key', sys.argv[1:])\" {{file}}")
        done = self.replay(blocker(name, "key ['tests/test_named.py']"), usine=usine)
        self.assertEqual([row[:2] for row in self.rows(done)], [["CONFIRMED", "1"]], done.stdout + done.stderr)

    def test_the_base_name_is_given_for_name(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: {name} reçoit le nom du fichier, comme au rejeu sur la base."""
        name = self.write_test("test_base_name.py", "")
        usine = USINE.replace(f"{PY} {{file}}", f"{PY} -c \"import sys; print('name', sys.argv[1:])\" {{name}}")
        done = self.replay(blocker(name, "name ['test_base_name.py']"), usine=usine)
        self.assertEqual([row[:2] for row in self.rows(done)], [["CONFIRMED", "1"]], done.stdout + done.stderr)

    def test_a_report_placeholder_gets_a_path_and_is_not_left_as_is(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: un {report} de red-replay reçoit un chemin, la commande tourne quand même."""
        name = self.write_test("test_report.py", "import sys; print('report', '{' not in sys.argv[1], sys.argv[1].endswith('.xml'))")
        usine = USINE.replace(f"{PY} {{file}}", f"{PY} {{file}} {{report}}")
        done = self.replay(blocker(name, "report True True"), usine=usine)
        self.assertEqual([row[:2] for row in self.rows(done)], [["CONFIRMED", "1"]], done.stdout + done.stderr)

    def test_a_file_absent_from_the_head_is_refused_and_never_run(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: un nom hors de la tête est refusé et rapporté, jamais lancé."""
        done = self.replay(blocker("tests/test_absent.py", "anything"))
        rows = self.rows(done)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in rows], [["REFUSED", "1"]])
        self.assertIn("jamais lancé", rows[0][2])

    def test_a_file_outside_the_test_path_is_refused(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: un fichier de la tête hors de la clé test-path n'est pas un fichier de test."""
        marker = self.dir / "ran.txt"
        (self.copy / "hook.py").write_text(f"open(r'{marker}', 'w').write('x')\n", encoding="utf-8")
        done = self.replay(blocker("hook.py", "anything"))
        self.assertEqual([row[:2] for row in self.rows(done)], [["REFUSED", "1"]], done.stdout + done.stderr)
        self.assertIn("test-path", self.rows(done)[0][2])
        self.assertFalse(marker.exists())

    def test_a_folder_is_refused(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: un dossier n'est pas un fichier de test."""
        (self.copy / "tests" / "sub").mkdir()
        done = self.replay(blocker("tests/sub", "anything"))
        self.assertEqual([row[:2] for row in self.rows(done)], [["REFUSED", "1"]], done.stdout + done.stderr)

    def test_a_link_that_leaves_the_copy_is_refused(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: un lien qui mène hors de la copie de la tête est refusé."""
        outside = self.dir / "outside.py"
        outside.write_text("print('outside')\n", encoding="utf-8")
        try:
            (self.copy / "tests" / "test_link.py").symlink_to(outside)
        except OSError as error:
            self.skipTest(f"no symbolic link on this system: {error}")
        done = self.replay(blocker("tests/test_link.py", "outside"))
        self.assertEqual([row[:2] for row in self.rows(done)], [["REFUSED", "1"]], done.stdout + done.stderr)

    def test_the_shell_probe_of_the_review_is_refused_and_never_run(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: la sonde shell du tour 2 (`gh auth status`) n'est plus lancée."""
        marker = self.dir / "ran.txt"
        line = (
            "- [BLOCKER] hook.py:1 | F-5 | leak | probe: "
            f"`sh -c 'touch {marker}; gh auth status 2>&1'` => `Logged in`\n"
        )
        done = self.replay(line)
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertTrue(done.stdout.startswith("NOT RUN\t-\tverdict illisible"), done.stdout)
        self.assertIn("refused", done.stdout)
        self.assertFalse(marker.exists())

    def test_a_climb_out_of_the_copy_is_refused(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: un nom avec `..` ou un chemin absolu n'est jamais lancé."""
        for name in ("tests/../../outside.py", "/etc/passwd"):
            with self.subTest(name=name):
                done = self.replay(blocker(name, "anything"))
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertTrue(done.stdout.startswith("NOT RUN\t-\tverdict illisible"), done.stdout)


class NotRun(Probe):
    def test_a_post_out_of_budget_runs_nothing(self) -> None:
        """No F-NNNN: ticket #68, critère 2: hors budget du poste, la sonde est NOT RUN et la commande ne part pas."""
        marker = self.dir / "ran.txt"
        name = self.write_test("test_mark.py", f"open(r'{marker}', 'w').write('x'); print('1')")
        done = self.replay(blocker(name, "1"), usine=USINE + "- `run-budget` : `99999999 | 12 | 2 | 0`\n")
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in self.rows(done)], [["NOT RUN", "1"]])
        self.assertIn("budget du poste non tenu", self.rows(done)[0][2])
        self.assertFalse(marker.exists())

    def test_without_run_limits_the_probe_is_not_run_and_never_unbounded(self) -> None:
        """No F-NNNN: ticket #68, critère 2: sans la clé run-limits, aucune commande ne tourne sans borne."""
        marker = self.dir / "ran.txt"
        name = self.write_test("test_mark.py", f"open(r'{marker}', 'w').write('x'); print('1')")
        done = self.replay(blocker(name, "1"), usine=USINE.replace("- `run-limits` : `2000 | 30`\n", ""))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in self.rows(done)], [["NOT RUN", "1"]])
        self.assertIn("sans objet (clé `run-limits` absente)", self.rows(done)[0][2])
        self.assertFalse(marker.exists())

    def test_without_red_replay_or_test_path_nothing_runs(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: sans la clé red-replay ou test-path, aucune sonde ne tourne."""
        marker = self.dir / "ran.txt"
        name = self.write_test("test_mark.py", f"open(r'{marker}', 'w').write('x'); print('1')")
        for key in ("red-replay", "test-path"):
            with self.subTest(key=key):
                usine = "".join(line + "\n" for line in USINE.splitlines() if f"`{key}`" not in line)
                done = self.replay(blocker(name, "1"), usine=usine)
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertEqual([row[:2] for row in self.rows(done)], [["NOT RUN", "1"]])
                self.assertIn(f"sans objet (clé `{key}` absente)", self.rows(done)[0][2])
        self.assertFalse(marker.exists())

    def test_a_verdict_it_cannot_read_is_not_run(self) -> None:
        """No F-NNNN: ticket #68, critère 2: un verdict illisible ne donne pas de ligne CONFIRMED."""
        (self.dir / "verdict.txt").write_text("nothing here\n", encoding="utf-8")
        (self.dir / "usine-base.md").write_text(USINE, encoding="utf-8")
        done = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.dir / "verdict.txt"), "--root", str(self.copy),
             "--usine", str(self.dir / "usine-base.md")],
            cwd=self.dir, env=self.env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(done.returncode, 2)
        self.assertTrue(done.stdout.startswith("NOT RUN"), done.stdout)

    def test_a_copy_that_is_not_a_folder_is_not_run(self) -> None:
        """No F-NNNN: ticket #68, critère 2: sans copie de la tête où la lancer, la sonde ne part pas."""
        done = self.replay(blocker("tests/test_x.py", "1"), extra=("--root", str(self.dir / "absent")))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertTrue(done.stdout.startswith("NOT RUN"), done.stdout)

    def test_a_copy_that_has_a_git_folder_is_not_run(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: une copie qui porte un `.git` partagerait le vrai dépôt, la sonde ne part pas."""
        marker = self.dir / "ran.txt"
        name = self.write_test("test_mark.py", f"open(r'{marker}', 'w').write('x'); print('1')")
        (self.copy / ".git").mkdir()
        done = self.replay(blocker(name, "1"))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in self.rows(done)], [["NOT RUN", "1"]])
        self.assertIn(".git", self.rows(done)[0][2])
        self.assertFalse(marker.exists())

    def test_a_git_file_of_a_linked_worktree_is_refused_too(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: le fichier `.git` d'un worktree lié renvoie au vrai dépôt, il est refusé."""
        name = self.write_test("test_one.py", "print(1)")
        (self.copy / ".git").write_text("gitdir: /somewhere/.git/worktrees/x\n", encoding="utf-8")
        done = self.replay(blocker(name, "1"))
        self.assertEqual([row[:2] for row in self.rows(done)], [["NOT RUN", "1"]], done.stdout + done.stderr)


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
        name = self.write_test("test_guard.py", "print('fine')")
        text = HEAD + blocker(name, "evasion works") + "GATES: green\n"
        done = self.replay(blocker(name, "evasion works"))
        counted = count_verdict(text, parse_replay(done.stdout))
        self.assertEqual(counted["VERDICT"], "ACCEPT")
        self.assertEqual(counted["DEMOTED"], [1])

        self.write_test("test_guard.py", "print('evasion works')")
        done = self.replay(blocker(name, "evasion works"))
        self.assertEqual(count_verdict(text, parse_replay(done.stdout))["VERDICT"], "REJECT")


if __name__ == "__main__":
    unittest.main()
