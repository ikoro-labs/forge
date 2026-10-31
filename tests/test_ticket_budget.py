"""Le budget de jetons par ticket (ticket #72) : somme, dépassement, reprise, clé absente."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import support
import ticket_budget
from handoff_header import check as check_handoff

USINE = "- `ticket-budget` : `{}`\n"


def notification(tokens: int) -> str:
    return (
        "<task-notification>\n<status>completed</status>\n<result>RESULT: PR</result>\n"
        f"<usage>subagent_tokens: {tokens}\ntool_uses: 41\nduration_ms: 912000</usage>\n"
        "</task-notification>\n"
    )


class Run:
    """A project folder, a ledger and the CLI, with the session's CLAUDE_ variables kept out."""

    def __init__(self, test: unittest.TestCase, budget: str | None = None) -> None:
        self.dir = Path(tempfile.mkdtemp())
        test.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        self.project = self.dir / "projet"
        (self.project / "docs" / "agents").mkdir(parents=True)
        text = "# Usine\n" + (USINE.format(budget) if budget is not None else "")
        (self.project / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")
        self.config = self.dir / "config"
        (self.config / "projects").mkdir(parents=True)
        self.ledger = self.dir / "registre.tsv"

    def call(self, *args: str) -> tuple[int, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
        env.update(HOME=str(self.dir), USERPROFILE=str(self.dir), CLAUDE_CONFIG_DIR=str(self.config))
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), redirect_stdout(out), redirect_stderr(err):
            code = ticket_budget.main(list(args))
        return code, out.getvalue() + err.getvalue()

    def add(self, ticket: str, role: str, tokens: int) -> None:
        path = self.dir / f"n-{ticket.strip('#')}-{role}-{tokens}.txt"
        path.write_text(notification(tokens), encoding="utf-8")
        code, out = self.call("ajouter", str(self.ledger), "--ticket", ticket, "--role", role, "--notification", str(path))
        assert code == 0, out

    def control(self, ticket: str = "#18", *extra: str) -> tuple[int, str]:
        return self.call("controle", str(self.ledger), str(self.project), "--ticket", ticket, *extra)


class Template(unittest.TestCase):
    def test_the_template_documents_the_key_without_a_default(self) -> None:
        """Ticket #72, point 1 : le gabarit documente `ticket-budget`, une ligne, sans valeur par défaut."""
        template = " ".join((support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8").split())
        self.assertIn("- `ticket-budget` : `<", template)
        self.assertIn("sans objet (clé `ticket-budget` absente)", template)
        self.assertIn("aucun plafond", template)


class Sum(unittest.TestCase):
    def test_the_sum_adds_the_tokens_of_each_notification_of_the_ticket_only(self) -> None:
        """Ticket #72, point 2 : somme des `subagent_tokens` par ticket, détail par rôle."""
        run = Run(self, "1000000")
        run.add("#18", "coder", 200000)
        run.add("#18", "qc-gate", 30000)
        run.add("#18", "coder", 100000)
        run.add("#30", "coder", 999)
        code, out = run.control("#18")
        self.assertEqual(code, 0, out)
        self.assertIn("somme=330000", out)
        self.assertIn("DETAIL coder 300000", out)
        self.assertIn("DETAIL qc-gate 30000", out)
        self.assertNotIn("999", out)

    def test_a_notification_without_usage_is_refused(self) -> None:
        """Ticket #72, point 2 : une notification sans `subagent_tokens` n'est jamais comptée zéro."""
        run = Run(self, "1000")
        path = run.dir / "vide.txt"
        path.write_text("<task-notification>fini</task-notification>", encoding="utf-8")
        code, out = run.call("ajouter", str(run.ledger), "--ticket", "#18", "--role", "coder", "--notification", str(path))
        self.assertEqual(code, 2, out)
        self.assertIn("subagent_tokens", out)
        self.assertFalse(run.ledger.exists())

    def test_the_main_session_share_counts_from_the_ticket_start(self) -> None:
        """Ticket #72, point 2 : la part de la session principale, lue par `token_audit.py`, depuis le début du ticket."""
        run = Run(self, "1000000")
        run.add("#18", "coder", 1000)
        entries = []
        for n, when in enumerate(("2026-10-24T09:00:00", "2026-10-24T11:00:00")):
            entries.append(json.dumps({
                "type": "assistant", "cwd": str(run.project), "timestamp": when + ".000Z", "sessionId": "s1",
                "requestId": f"r{n}", "effort": "high",
                "message": {"id": f"m{n}", "model": "claude-opus-5-5", "stop_reason": "end_turn",
                            "usage": {"input_tokens": 1, "cache_creation_input_tokens": 10,
                                      "cache_read_input_tokens": 100, "output_tokens": 5}},
            }))
        (run.config / "projects" / "p.jsonl").write_text("\n".join(entries) + "\n", encoding="utf-8")
        code, out = run.control("#18", "--depuis", "2026-10-24T10:00")
        self.assertEqual(code, 0, out)
        self.assertIn("DETAIL session principale 116", out)
        self.assertIn("somme=1116", out)


class Overrun(unittest.TestCase):
    def test_a_sum_over_the_budget_stops_the_launch_and_reports_roles_and_verdict(self) -> None:
        """Ticket #72, point 3 : dépassement, code 1, somme, détail par rôle et dernier verdict."""
        run = Run(self, "300000")
        run.add("#18", "coder", 200000)
        run.add("#18", "qc-conf", 188375)
        code, out = run.control("#18", "--verdict", "REJECT au tour 1")
        self.assertEqual(code, 1, out)
        self.assertIn("BUDGET depasse #18", out)
        self.assertIn("somme=388375", out)
        self.assertIn("budget=300000", out)
        self.assertIn("DETAIL coder 200000", out)
        self.assertIn("DETAIL qc-conf 188375", out)
        self.assertIn("VERDICT REJECT au tour 1", out)

    def test_a_sum_equal_to_the_budget_still_launches(self) -> None:
        """Ticket #72, point 3 : le plafond est dépassé quand la somme lui est strictement supérieure."""
        run = Run(self, "5000")
        run.add("#18", "coder", 5000)
        self.assertEqual(run.control("#18")[0], 0)

    def test_a_malformed_key_refuses_instead_of_guessing(self) -> None:
        """Ticket #72, point 1 : une valeur qui n'est pas un nombre entier de jetons fait échouer le contrôle."""
        run = Run(self, "beaucoup")
        run.add("#18", "coder", 10)
        code, out = run.control("#18")
        self.assertEqual(code, 2, out)
        self.assertIn("ticket-budget", out)


class Absent(unittest.TestCase):
    def test_an_absent_key_is_not_applicable_and_sets_no_ceiling(self) -> None:
        """Ticket #72, point 1 : clé absente, « sans objet », aucun plafond, même pour une somme énorme."""
        run = Run(self)
        run.add("#18", "coder", 99_000_000)
        code, out = run.control("#18")
        self.assertEqual(code, 0, out)
        self.assertIn("sans objet (clé `ticket-budget` absente)", out)
        self.assertNotIn("depasse", out)


class Handoff(unittest.TestCase):
    def test_the_sum_written_in_a_handoff_is_resumed_by_the_relay(self) -> None:
        """Ticket #72, point 4 : `jetons_agents` porte la somme par ticket ; le relais la reprend au lieu de repartir de zéro."""
        first = Run(self, "300000")
        first.add("#18", "coder", 200000)
        first.add("#18", "qc-conf", 50000)
        first.add("#30", "coder", 7)
        code, lines = first.call("passation", str(first.ledger))
        self.assertEqual(code, 0, lines)
        handoff = first.dir / "2026-10-24-r1.md"
        handoff.write_text(
            "---\nprojet: demo\nfeature: F-0001\npassage_depart: 1792494562\n"
            f"jetons_agents:\n{lines}"
            "en_vol: []\nfile_revue: []\nsauvetage: []\nsuccesseur:\nhooks_version: forge@test\n"
            "seuil:\ncontexte_passation: 151000\n---\n\n# Reprise\n",
            encoding="utf-8",
        )
        self.assertEqual(len(check_handoff(handoff)["jetons_agents"]), 3)

        second = Run(self, "300000")
        code, out = second.call("reprendre", str(second.ledger), str(handoff))
        self.assertEqual(code, 0, out)
        second.add("#18", "coder", 60000)
        code, out = second.control("#18", "--verdict", "REJECT au tour 1")
        self.assertEqual(code, 1, out)
        self.assertIn("somme=310000", out)
        self.assertIn("DETAIL coder 260000", out)

    def test_an_old_handoff_with_a_bare_number_resumes_with_nothing_to_carry(self) -> None:
        """Ticket #72, point 4 : `jetons_agents: 0` (passation d'avant le budget) se reprend sans erreur ni invention."""
        run = Run(self, "300000")
        handoff = run.dir / "old.md"
        handoff.write_text(
            "---\nprojet: demo\nfeature:\npassage_depart: 1\njetons_agents: 0\nen_vol: []\nfile_revue: []\n"
            "sauvetage: []\nsuccesseur:\nhooks_version: x\nseuil:\ncontexte_passation: 1\n---\n",
            encoding="utf-8",
        )
        code, out = run.call("reprendre", str(run.ledger), str(handoff))
        self.assertEqual(code, 0, out)
        self.assertIn("somme=0", run.control("#18")[1])


class Skill(unittest.TestCase):
    def test_feature_build_holds_the_sum_and_flags_the_ticket_before_each_launch(self) -> None:
        """Ticket #72, points 2 et 3 : le skill appelle le script avant chaque lancement et pose l'étiquette sur le ticket et sa PR."""
        skill = " ".join((support.PLUGIN / "skills" / "feature-build" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("ticket_budget.py", skill)
        self.assertIn("ticket-budget", skill)
        self.assertIn("jetons_agents", skill)
        self.assertIn("sans objet (clé `ticket-budget` absente)", skill)
        self.assertIn("needs-your-attention", skill[skill.index("ticket_budget.py"):])


if __name__ == "__main__":
    unittest.main()
