"""Ticket #68: a BLOCKER that rests on an execution carries its probe, and the replay decides if it counts.

The probe is closed: it names a test file of the head, never a command.
"""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, cast

import support  # noqa: F401  met le plugin sur le chemin d'import
from parse_output import (
    OutputError,
    ReplayError,
    apply_replay,
    count_verdict,
    main,
    parse_replay,
    parse_verdict,
    probe_name_problem,
)

HEAD = "VERDICT: REJECT\nROUND: 1\nHEAD: 3f2a9c1\nSPEC: #68: 0 criteria covered, 0 partial, 1 missing\nFINDINGS:\n"
TAIL = "GATES: green\n"
PROBED = "- [BLOCKER] hook.py:12 | F-25 | a heredoc passes the guard | probe: `tests/test_hook.py` => `'allowed' != 'refused'`\n"
DEDUCED = "- [BLOCKER] hook.py:30 | F-25 | the path is read twice, the second read is unchecked\n"


def verdict(*findings: str) -> str:
    return HEAD + "".join(findings) + TAIL


def findings_of(parsed: dict[str, object]) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", parsed["FINDINGS"])


class Marks(unittest.TestCase):
    def test_a_probe_is_read_with_its_test_file_and_its_expected_output(self) -> None:
        """No F-NNNN: ticket #68, critère 2: un BLOCKER qui repose sur une exécution porte le fichier de test et la sortie attendue."""
        finding = findings_of(parse_verdict(verdict(PROBED)))[0]
        self.assertEqual(finding["probe"], {"file": "tests/test_hook.py", "expect": "'allowed' != 'refused'"})
        self.assertEqual(finding["mark"], "")

    def test_a_blocker_without_probe_counts_and_is_marked_deduced(self) -> None:
        """No F-NNNN: ticket #68, critère 3: un BLOCKER sans exécution possible compte, et il est marqué déduit."""
        parsed = parse_verdict(verdict(DEDUCED))
        self.assertEqual(parsed["VERDICT"], "REJECT")
        finding = findings_of(parsed)[0]
        self.assertEqual(finding["mark"], "déduit")
        self.assertIsNone(finding["probe"])

    def test_a_note_has_no_mark(self) -> None:
        """No F-NNNN: ticket #68, critère 3: seul un BLOCKER est marqué."""
        parsed = parse_verdict(verdict(DEDUCED, "- [NOTE] wording\n"))
        self.assertEqual(findings_of(parsed)[1]["mark"], "")

    def test_a_probe_missing_its_expected_output_is_refused(self) -> None:
        """No F-NNNN: ticket #68, critère 2: une sonde sans sortie attendue ne se rejoue pas, elle est refusée."""
        text = verdict("- [BLOCKER] a.py:1 | F-25 | evasion | probe: `tests/test_a.py`\n")
        with self.assertRaises(OutputError) as raised:
            parse_verdict(text)
        self.assertIn("probe: `<test file of the head>` => `<expected output>`", str(raised.exception))


class Closed(unittest.TestCase):
    """Revue, tour 2 : la sonde n'est plus du shell, seulement le nom d'un fichier de test de la tête."""

    def test_the_shell_probe_of_the_review_is_refused(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: une sonde écrite en commande shell est refusée, jamais lue comme un nom."""
        line = (
            "- [BLOCKER] a.py:1 | F-5 | leak | probe: "
            "`sh -c 'HOME=$(getent passwd $(id -u) | cut -d: -f6) gh auth status 2>&1'` => `Logged in`\n"
        )
        with self.assertRaises(OutputError) as raised:
            parse_verdict(verdict(line))
        self.assertIn("refused", str(raised.exception))

    def test_a_name_that_could_leave_the_head_or_reach_a_shell_is_refused(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: chemin absolu, `..`, caractère de shell : le nom est refusé."""
        for name in (
            "/etc/passwd", "C:/Windows/x.py", "tests/../../x.py", "..", "tests\\x.py", "tests/x.py;id",
            "tests/$(id).py", "tests/x y.py", "tests/x.py|sh", "tests/x*.py", "-p", "tests/x.py&", "~/x.py",
        ):
            with self.subTest(name=name):
                self.assertNotEqual(probe_name_problem(name), "")

    def test_a_plain_relative_name_is_accepted(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: un chemin relatif fait de lettres, chiffres et `._/-` est un nom."""
        for name in ("tests/test_hook.py", "apps/web/src/__tests__/guard.test.ts", "test-x.py"):
            with self.subTest(name=name):
                self.assertEqual(probe_name_problem(name), "")


class Replay(unittest.TestCase):
    def test_a_reproduced_probe_keeps_the_blocker(self) -> None:
        """No F-NNNN: ticket #68, critère 2: une sonde qui rend la sortie dite confirme le BLOCKER, qui rejette."""
        parsed = count_verdict(verdict(PROBED), parse_replay("CONFIRMED\t1\tok\n"))
        self.assertEqual(parsed["VERDICT"], "REJECT")
        self.assertEqual(findings_of(parsed)[0]["severity"], "BLOCKER")
        self.assertEqual(findings_of(parsed)[0]["mark"], "confirmé")

    def test_a_probe_that_does_not_reproduce_makes_the_blocker_a_note(self) -> None:
        """No F-NNNN: ticket #68, critère 2: une sonde qui ne rend pas la sortie dite fait du BLOCKER un NOTE non reproduit."""
        parsed = count_verdict(verdict(PROBED), parse_replay("NOT REPRODUCED\t1\tgot: 0\n"))
        self.assertEqual(findings_of(parsed)[0]["severity"], "NOTE")
        self.assertEqual(findings_of(parsed)[0]["mark"], "non reproduit")
        # Nothing blocks any more: the judge's REJECT does not stand.
        self.assertEqual(parsed["VERDICT"], "ACCEPT")
        self.assertEqual(parsed["JUDGED"], "REJECT")
        self.assertEqual(parsed["DEMOTED"], [1])

    def test_a_deduced_blocker_beside_a_demoted_one_still_rejects(self) -> None:
        """No F-NNNN: ticket #68, critère 3: un BLOCKER déduit compte même quand une sonde voisine ne se reproduit pas."""
        parsed = count_verdict(verdict(PROBED, DEDUCED), parse_replay("NOT REPRODUCED\t1\tgot: 0\n"))
        self.assertEqual(parsed["VERDICT"], "REJECT")
        self.assertEqual([item["severity"] for item in findings_of(parsed)], ["NOTE", "BLOCKER"])
        self.assertEqual(findings_of(parsed)[1]["mark"], "déduit")

    def test_a_probe_that_did_not_run_leaves_the_blocker_unsettled(self) -> None:
        """No F-NNNN: ticket #68, critère 2: une sonde NOT RUN ne confirme ni ne rétrograde : le BLOCKER ne compte pas encore."""
        with self.assertRaises(ReplayError) as raised:
            count_verdict(verdict(PROBED), parse_replay("NOT RUN\t1\tbudget\n"))
        self.assertIn("finding 1", str(raised.exception))

    def test_a_probe_with_no_replay_line_leaves_the_blocker_unsettled(self) -> None:
        """No F-NNNN: ticket #68, critère 2: un BLOCKER à sonde que personne n'a rejoué ne compte pas."""
        with self.assertRaises(ReplayError):
            count_verdict(verdict(PROBED), parse_replay(""))

    def test_a_refused_probe_sends_the_verdict_back_to_the_judge(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: un fichier refusé par le rejeu rend le verdict illisible (code 1), le juge est relancé."""
        with self.assertRaises(OutputError) as raised:
            count_verdict(verdict(PROBED), parse_replay("REFUSED\t1\ttests/test_hook.py : absent\n"))
        self.assertNotIsInstance(raised.exception, ReplayError)
        self.assertIn("finding 1", str(raised.exception))

    def test_the_replay_lines_are_read_by_finding_number(self) -> None:
        """No F-NNNN: ticket #68, critère 2: le rejeu rend une ligne `<statut>\\t<n>\\t<détail>` par BLOCKER."""
        self.assertEqual(
            parse_replay("CONFIRMED\t2\tok\nDEDUCED\t3\t-\nNOT REPRODUCED\t1\tgot: 0\nREFUSED\t4\tx\n"),
            {1: "NOT REPRODUCED", 2: "CONFIRMED", 3: "DEDUCED", 4: "REFUSED"},
        )
        with self.assertRaises(OutputError):
            parse_replay("FINE\t1\tok\n")


class Rewrite(unittest.TestCase):
    def test_the_rewritten_verdict_is_the_one_that_stands(self) -> None:
        """No F-NNNN: ticket #68, critère 2: le verdict réécrit passe le parseur seul, sans rejeu."""
        text = verdict(PROBED)
        rewritten = apply_replay(text, parse_replay("NOT REPRODUCED\t1\tgot: 0\n"))
        self.assertIn("- [NOTE] non reproduit : hook.py:12 | F-25 |", rewritten)
        self.assertIn("VERDICT: ACCEPT", rewritten)
        parsed = parse_verdict(rewritten)
        self.assertEqual(parsed["VERDICT"], "ACCEPT")
        self.assertEqual(findings_of(parsed)[0]["severity"], "NOTE")

    def test_a_demotion_beside_a_deduced_blocker_keeps_the_reject(self) -> None:
        """No F-NNNN: ticket #68, critère 3: le verdict réécrit garde REJECT tant qu'un BLOCKER déduit reste."""
        text = verdict(PROBED, DEDUCED)
        rewritten = apply_replay(text, parse_replay("NOT REPRODUCED\t1\tgot: 0\n"))
        self.assertIn("VERDICT: REJECT", rewritten)
        parsed = parse_verdict(rewritten)
        self.assertEqual([item["severity"] for item in findings_of(parsed)], ["NOTE", "BLOCKER"])

    def test_a_confirmed_verdict_is_unchanged(self) -> None:
        """No F-NNNN: ticket #68, critère 2: une sonde confirmée ne change rien au texte du juge."""
        text = verdict(PROBED)
        self.assertEqual(apply_replay(text, parse_replay("CONFIRMED\t1\tok\n")), text)


class Command(unittest.TestCase):
    def run_main(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(list(args))
        return code, out.getvalue()

    def test_the_command_counts_with_the_replay_and_writes_the_verdict_that_stands(self) -> None:
        """No F-NNNN: ticket #68, critère 4: `parse_output.py verdict --replay` applique la règle de comptage."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "verdict.txt").write_text(verdict(PROBED), encoding="utf-8")
            (root / "replay.txt").write_text("NOT REPRODUCED\t1\tgot: 0\n", encoding="utf-8")
            code, out = self.run_main(
                "verdict", str(root / "verdict.txt"), "--replay", str(root / "replay.txt"),
                "--rewrite", str(root / "stands.txt"),
            )
            self.assertEqual(code, 0, out)
            self.assertIn('"VERDICT": "ACCEPT"', out)
            self.assertIn("VERDICT: ACCEPT", (root / "stands.txt").read_text(encoding="utf-8"))

    def test_an_unsettled_probe_exits_with_its_own_code(self) -> None:
        """No F-NNNN: ticket #68, critère 2: un rejeu incomplet sort en 3, que `forge:qc` ne lit pas comme un verdict illisible (1)."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "verdict.txt").write_text(verdict(PROBED), encoding="utf-8")
            (root / "replay.txt").write_text("NOT RUN\t1\tbudget\n", encoding="utf-8")
            code, out = self.run_main("verdict", str(root / "verdict.txt"), "--replay", str(root / "replay.txt"))
            self.assertEqual(code, 3, out)
            self.assertIn("unsettled", out)

    def test_a_refused_probe_exits_like_a_verdict_to_relaunch(self) -> None:
        """No F-NNNN: ticket #68, retour de revue: un fichier refusé sort en 1, et `forge:qc` relance le juge une fois."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "verdict.txt").write_text(verdict(PROBED), encoding="utf-8")
            (root / "replay.txt").write_text("REFUSED\t1\ttests/test_hook.py : absent\n", encoding="utf-8")
            code, out = self.run_main("verdict", str(root / "verdict.txt"), "--replay", str(root / "replay.txt"))
            self.assertEqual(code, 1, out)
            self.assertIn("refused", out)


if __name__ == "__main__":
    unittest.main()
