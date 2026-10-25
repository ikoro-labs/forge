"""Les actions du budget d'erreur (clé `budget-action`) et le garde de fusion de `guard_git` (ticket #59)."""

import io
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import support  # noqa: F401  met le plugin sur le chemin d'import

from budget import (
    MAX_AGE,
    evaluate,
    load_state,
    merge_refusal,
    parse_actions,
)
from guard_git import guarded_main

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def objective(sli: str, etat: str | None, statistique: str | None = None) -> dict:
    if etat is None:
        return {"sli": sli, "statistique": statistique, "statut": "sans objet", "raison": "aucune PR dans la fenêtre"}
    return {"sli": sli, "statistique": statistique, "statut": "calculé", "etat": etat}


def document(*objectives: dict, at: datetime = NOW) -> dict:
    return {"calcule_le": at.isoformat(), "objectifs": list(objectives)}


class Parsing(unittest.TestCase):
    def test_a_line_is_a_sli_and_an_action(self) -> None:
        """Ticket #59 : `<sli> | <action>`, une ligne par action."""
        lines, errors = parse_actions(["accept-round-1 | human-merge", "lead-time p90 | feature-freeze", "main-green | alert"])
        self.assertEqual(errors, [])
        self.assertEqual([(line.sli, line.action) for line in lines], [
            ("accept-round-1", "human-merge"), ("lead-time p90", "feature-freeze"), ("main-green", "alert"),
        ])

    def test_a_malformed_line_or_an_unknown_action_is_reported_never_ignored(self) -> None:
        lines, errors = parse_actions(["accept-round-1", "accept-round-1 | geler", " | human-merge", "main-green | alert"])
        self.assertEqual([(line.sli, line.action) for line in lines], [("main-green", "alert")])
        self.assertEqual(len(errors), 3)
        self.assertTrue(any("geler" in error for error in errors))


class Actions(unittest.TestCase):
    """Chaque action, active quand son SLO est épuisé, inactive sinon."""

    def test_each_action_is_active_on_an_exhausted_objective_and_inactive_otherwise(self) -> None:
        for action in ("human-merge", "feature-freeze", "alert"):
            lines, _ = parse_actions([f"accept-round-1 | {action}"])
            for etat, active in (("épuisé", True), ("menacé", False), ("tenu", False), (None, False)):
                with self.subTest(action=action, etat=etat):
                    verdicts = evaluate(lines, document(objective("accept-round-1", etat)))
                    self.assertEqual([(v.action, v.active) for v in verdicts], [(action, active)])

    def test_a_statistic_is_part_of_the_name_but_the_bare_sli_matches_too(self) -> None:
        document_ = document(objective("lead-time", "épuisé", "p90"))
        for name in ("lead-time p90", "lead-time"):
            with self.subTest(name=name):
                lines, _ = parse_actions([f"{name} | human-merge"])
                self.assertTrue(evaluate(lines, document_)[0].active)

    def test_the_return_to_tenu_ends_the_action_at_the_next_calculation(self) -> None:
        """Ticket #59 : l'autonomie revient d'elle-même quand le SLO repasse à `tenu`."""
        lines, _ = parse_actions(["accept-round-1 | human-merge"])
        before = evaluate(lines, document(objective("accept-round-1", "épuisé")))
        after = evaluate(lines, document(objective("accept-round-1", "tenu")))
        self.assertTrue(before[0].active)
        self.assertFalse(after[0].active)
        self.assertIn("tenu", after[0].reason)

    def test_an_objective_absent_from_the_state_is_a_problem_not_a_pass(self) -> None:
        lines, _ = parse_actions(["accept-round-1 | human-merge"])
        verdict = evaluate(lines, document(objective("main-green", "tenu")))[0]
        self.assertTrue(verdict.unknown)


class State(unittest.TestCase):
    def write(self, folder: str, text: str) -> Path:
        path = Path(folder) / "slo-status.json"
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_fresh_file_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, json.dumps(document(objective("a", "tenu"))))
            state, reason = load_state(path, NOW + timedelta(hours=23))
        self.assertIsNone(reason)
        self.assertEqual(state["objectifs"][0]["sli"], "a")

    def test_a_missing_stale_or_unreadable_file_is_unusable_and_says_why(self) -> None:
        """Ticket #59 : fichier absent, périmé (plus de 24 h) ou illisible."""
        with tempfile.TemporaryDirectory() as folder:
            cases = {
                "absent": None,
                "périmé": json.dumps(document(objective("a", "tenu"))),
                "illisible": "{pas du json",
                "pas un objet": "[1, 2]",
                "sans date": json.dumps({"objectifs": []}),
                "date illisible": json.dumps({"calcule_le": "hier", "objectifs": []}),
                "date sans fuseau": json.dumps({"calcule_le": "2026-11-01T12:00:00", "objectifs": []}),
                "sans objectifs": json.dumps({"calcule_le": NOW.isoformat()}),
                "objectif illisible": json.dumps({"calcule_le": NOW.isoformat(), "objectifs": ["x"]}),
            }
            for name, text in cases.items():
                with self.subTest(name=name):
                    path = Path(folder) / "absent.json" if text is None else self.write(folder, text)
                    now = NOW + MAX_AGE + timedelta(seconds=1) if name == "périmé" else NOW
                    state, reason = load_state(path, now)
                    self.assertIsNone(state)
                    self.assertTrue(reason)
            _, reason = load_state(self.write(folder, json.dumps(document())), NOW + timedelta(hours=25))
            self.assertIn("24 h", reason)

    def test_exactly_one_day_old_is_still_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, json.dumps(document(objective("a", "tenu"))))
            state, _ = load_state(path, NOW + MAX_AGE)
        self.assertIsNotNone(state)


class MergeRefusal(unittest.TestCase):
    """`merge_refusal(config, path, now)` : pourquoi `gh pr merge` est refusé, ou None."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "slo-status.json"

    def put(self, *objectives: dict, at: datetime = NOW) -> None:
        self.path.write_text(json.dumps(document(*objectives, at=at)), encoding="utf-8")

    def refusal(self, *lines: str, now: datetime = NOW) -> str | None:
        return merge_refusal({"budget-action": list(lines)}, self.path, now)

    def test_an_exhausted_human_merge_refuses_and_names_the_slo(self) -> None:
        """Ticket #59 : `human-merge` actif, la fusion est refusée à l'agent."""
        self.put(objective("accept-round-1", "épuisé"))
        verdict = self.refusal("accept-round-1 | human-merge") or ""
        self.assertIn("accept-round-1", verdict)
        self.assertIn("human-merge", verdict)

    def test_a_human_merge_that_is_not_exhausted_lets_the_merge_through(self) -> None:
        for etat in ("tenu", "menacé", None):
            with self.subTest(etat=etat):
                self.put(objective("accept-round-1", etat))
                self.assertIsNone(self.refusal("accept-round-1 | human-merge"))

    def test_the_other_actions_never_refuse_a_merge_even_exhausted_or_without_state(self) -> None:
        self.put(objective("accept-round-1", "épuisé"))
        self.assertIsNone(self.refusal("accept-round-1 | feature-freeze", "accept-round-1 | alert"))
        self.path.unlink()
        self.assertIsNone(self.refusal("accept-round-1 | feature-freeze", "accept-round-1 | alert"))

    def test_an_absent_key_is_sans_objet_and_refuses_nothing(self) -> None:
        self.assertIsNone(merge_refusal({}, self.path, NOW))

    def test_a_missing_stale_or_unreadable_state_refuses_and_gives_the_command(self) -> None:
        """Ticket #59 : fermé par défaut, avec la commande à lancer dans le message."""
        line = "accept-round-1 | human-merge"
        for name in ("absent", "périmé", "illisible"):
            with self.subTest(name=name):
                self.path.unlink(missing_ok=True)
                now = NOW
                if name == "périmé":
                    self.put(objective("accept-round-1", "tenu"))
                    now = NOW + timedelta(hours=25)
                elif name == "illisible":
                    self.path.write_text("{", encoding="utf-8")
                verdict = self.refusal(line, now=now) or ""
                self.assertIn("factory_slo.py", verdict)
                self.assertIn("status", verdict)

    def test_a_malformed_line_refuses_rather_than_guessing(self) -> None:
        self.put(objective("accept-round-1", "tenu"))
        self.assertIn("budget-action", self.refusal("accept-round-1 | human-merge", "geler tout") or "")

    def test_a_human_merge_on_an_sli_the_state_does_not_know_refuses(self) -> None:
        self.put(objective("main-green", "tenu"))
        self.assertIn("accept-round-1", self.refusal("accept-round-1 | human-merge") or "")

    def test_the_autonomy_returns_when_the_objective_is_tenu_again(self) -> None:
        """Ticket #59 : au calcul suivant, la fusion repasse."""
        self.put(objective("accept-round-1", "épuisé"))
        self.assertIsNotNone(self.refusal("accept-round-1 | human-merge"))
        self.put(objective("accept-round-1", "tenu"))
        self.assertIsNone(self.refusal("accept-round-1 | human-merge"))


class TheHook(unittest.TestCase):
    """Le vrai `main` de `guard_git`, sur un vrai dépôt et un vrai fichier d'état."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "projet"
        (self.root / "docs" / "agents").mkdir(parents=True)
        self.env = {
            **{k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")},
            "HOME": self.tmp.name, "USERPROFILE": self.tmp.name,
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
        }
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], env=self.env, check=True)
        self.state = self.root / ".git" / "forge" / "slo-status.json"

    def configure(self, *lines: str) -> None:
        text = "".join(f"- `budget-action` : `{line}`\n" for line in lines)
        (self.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def put(self, etat: str, at: datetime | None = None) -> None:
        self.state.parent.mkdir(parents=True, exist_ok=True)
        fresh = at or datetime.now(tz=timezone.utc)
        self.state.write_text(json.dumps(document(objective("accept-round-1", etat), at=fresh)), encoding="utf-8")

    def run_hook(self, command: str, agent_type: str | None = "forge:qc-conf") -> tuple[int, str]:
        event = {"tool_input": {"command": command}, "cwd": str(self.root)}
        if agent_type:
            event["agent_type"] = agent_type
        err = io.StringIO()
        with (
            mock.patch.dict(os.environ, {**self.env, "CLAUDE_PROJECT_DIR": str(self.root)}, clear=True),
            mock.patch("sys.stdin", io.StringIO(json.dumps(event))),
            mock.patch("sys.stderr", err),
            mock.patch("guard_git.current_branch", lambda _cwd: "feat/x"),
            mock.patch("guard_git.checks_green_via_gh", lambda _cwd: lambda _pr: True),
            mock.patch("guard_git.description_via_gh", lambda _cwd: lambda _pr: ""),
        ):
            return guarded_main(), err.getvalue()

    def test_an_exhausted_human_merge_refuses_gh_pr_merge_for_every_agent_name(self) -> None:
        """Ticket #59 : le filtre ne s'attache pas au nom d'agent, préfixé ou non, ni à son absence."""
        self.configure("accept-round-1 | human-merge")
        self.put("épuisé")
        for agent in ("forge:qc-conf", "forge:qc-gate", "forge:coder", "qc-conf", None):
            with self.subTest(agent=agent):
                code, message = self.run_hook("gh pr merge 7 --squash", agent)
                self.assertEqual(code, 2)
                self.assertIn("accept-round-1", message)
                self.assertNotIn("guard_git failed", message)

    def test_the_merge_goes_through_when_the_objective_is_tenu(self) -> None:
        self.configure("accept-round-1 | human-merge")
        self.put("tenu")
        self.assertEqual(self.run_hook("gh pr merge 7 --squash")[0], 0)

    def test_other_commands_are_not_touched_by_the_budget(self) -> None:
        self.configure("accept-round-1 | human-merge")
        self.put("épuisé")
        self.assertEqual(self.run_hook("gh pr view 7")[0], 0)
        self.assertEqual(self.run_hook("git status")[0], 0)

    def test_a_missing_or_stale_state_refuses_the_merge_with_the_command(self) -> None:
        self.configure("accept-round-1 | human-merge")
        code, message = self.run_hook("gh pr merge 7 --squash")
        self.assertEqual(code, 2)
        self.assertIn("factory_slo.py", message)
        self.put("tenu", at=datetime.now(tz=timezone.utc) - timedelta(hours=25))
        code, message = self.run_hook("gh pr merge 7 --squash")
        self.assertEqual(code, 2)
        self.assertIn("24 h", message)

    def test_without_the_key_the_merge_is_not_a_budget_matter(self) -> None:
        (self.root / "docs" / "agents" / "usine.md").write_text("# Usine\n", encoding="utf-8")
        self.assertEqual(self.run_hook("gh pr merge 7 --squash")[0], 0)


if __name__ == "__main__":
    unittest.main()
