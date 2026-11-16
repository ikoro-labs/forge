"""Ticket #68: `probe_replay.py` replays the probe of each BLOCKER in a copy of the head, under the bound."""

import os
import shutil
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


class Isolation(Probe):
    """The probe is a command the judge wrote from a PR: it must not carry the session's access."""

    SECRETS = {
        "GH_TOKEN": "ghp_secret123", "GITHUB_TOKEN": "ghp_secret456", "GIT_ASKPASS": "/bin/askpass",
        "SSH_AUTH_SOCK": "/tmp/agent.sock", "CLAUDE_CODE_OAUTH_TOKEN": "sk-secret", "AWS_SECRET_ACCESS_KEY": "aws-secret",
    }

    def test_the_credential_variables_of_the_session_do_not_reach_the_probe(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: la sonde ne voit aucune variable d'identifiants de la session."""
        self.env.update(self.SECRETS)
        code = (
            f"import os; print('leak', sorted(k for k in os.environ if k in {tuple(self.SECRETS)!r} "
            "or k.startswith(('GH_', 'GITHUB_', 'GIT_', 'CLAUDE'))))"
        )
        done = self.replay(blocker(code, "leak []"))
        self.assertEqual([row[:2] for row in self.rows(done)], [["CONFIRMED", "1"]], done.stdout + done.stderr)

    def test_home_and_the_config_folders_point_to_an_empty_throwaway_folder(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: HOME est un dossier vide et jetable, pas celui de la session."""
        self.env["XDG_CONFIG_HOME"] = str(self.dir)
        (self.dir / "gh-hosts.yml").write_text("token: leaked", encoding="utf-8")
        code = (
            "import os; h = os.environ['HOME']; "
            f"print('home', os.listdir(h), h == r'{self.dir}', os.environ.get('XDG_CONFIG_HOME') == r'{self.dir}', "
            "os.environ['USERPROFILE'] == h, os.environ['TMPDIR'] == h)"
        )
        done = self.replay(blocker(code, "home [] False False True True"))
        self.assertEqual([row[:2] for row in self.rows(done)], [["CONFIRMED", "1"]], done.stdout + done.stderr)

    @unittest.skipUnless(
        shutil.which("gh") and shutil.which("grep") and os.name != "nt", "needs the `gh` and `grep` programs on a POSIX shell",
    )
    def test_gh_auth_token_finds_nothing(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: `gh auth token` lancé par la sonde ne rend pas le jeton de la session."""
        self.env.update({"GH_TOKEN": "ghp_secret123", "GITHUB_TOKEN": "ghp_secret456"})
        line = "- [BLOCKER] hook.py:1 | F-25 | leak | probe: `sh -c 'gh auth token 2>&1 | grep -c ghp_secret; true'` => `0`\n"
        done = self.replay(line)
        self.assertEqual([row[:2] for row in self.rows(done)], [["CONFIRMED", "1"]], done.stdout + done.stderr)

    def test_a_copy_that_has_a_git_folder_is_not_run(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: une copie qui porte un `.git` partagerait le vrai dépôt, la sonde ne part pas."""
        marker = self.dir / "ran.txt"
        (self.copy / ".git").mkdir()
        done = self.replay(blocker(f"open(r'{marker}', 'w').write('x'); print('1')", "1"))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertEqual([row[:2] for row in self.rows(done)], [["NOT RUN", "1"]])
        self.assertIn(".git", self.rows(done)[0][2])
        self.assertFalse(marker.exists())

    def test_a_git_file_of_a_linked_worktree_is_refused_too(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: le fichier `.git` d'un worktree lié renvoie au vrai dépôt, il est refusé."""
        (self.copy / ".git").write_text("gitdir: /somewhere/.git/worktrees/x\n", encoding="utf-8")
        done = self.replay(blocker("print(1)", "1"))
        self.assertEqual([row[:2] for row in self.rows(done)], [["NOT RUN", "1"]], done.stdout + done.stderr)


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
