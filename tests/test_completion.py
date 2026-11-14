"""The completion table and the Stop hook that asks for it, gh and the transcript simulated."""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import support
from completion import CompletionError, main, table
from guard_completion import HEADERS, decision, has_table
from test_guard_ticket_budget import FakeGh, ticket

USINE = "# Usine\n\n- `feature-dir` : `docs/features`\n"
COLUMN = (
    "- `completion-column` : `Couverture | "
    f'"{sys.executable}" -c "import sys; print(sys.argv[1] + chr(32) + chr(111) + chr(107))"'
    " {feature}`\n"
)
DESIGN = (
    "---\nfeature: {feature}\ndocument: design\nstatut: accepte\nfeature-tickets: {budget}\n---\n"
)
IDEA = (
    "---\nfeature: {feature}\ndocument: idee\ntitre: {title}\netat: {state}\nissue: {issue}\n---\n"
)
NOW = datetime(2026, 11, 14, 9, 30, tzinfo=timezone.utc)
CLOSED = {"state": "CLOSED", "stateReason": "COMPLETED"}
OPEN = {"state": "OPEN", "stateReason": None}
DROPPED = {"state": "CLOSED", "stateReason": "NOT_PLANNED"}


class Project:
    """A project folder with its usine.md and feature folders."""

    def __init__(self, test: unittest.TestCase, usine: str = USINE) -> None:
        folder = tempfile.TemporaryDirectory()
        test.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "docs" / "agents").mkdir(parents=True)
        (self.root / "docs" / "agents" / "usine.md").write_text(usine, encoding="utf-8")

    def feature(
        self, number: int, budget: int = 5, state: str = "actif", issue: int = 1, done: bool = False
    ) -> str:
        name = f"F-{number:04d}"
        folder = self.root / "docs" / "features" / f"{number:04d}-demo"
        folder.mkdir(parents=True)
        idea = IDEA.format(feature=name, title="demo", state=state, issue=issue)
        (folder / "idee.md").write_text(idea, encoding="utf-8")
        design = DESIGN.format(feature=name, budget=budget)
        (folder / "design.md").write_text(design, encoding="utf-8")
        if done:
            (folder / "README.md").write_text("---\ndocument: livree\n---\n", encoding="utf-8")
        return name

    def table(self, gh: FakeGh, *wanted: str) -> str:
        return table(self.root, list(wanted), gh, lambda: NOW)


def rows(text: str) -> list[list[str]]:
    lines = [line for line in text.splitlines() if line.startswith("|")]
    return [[cell.strip() for cell in line.strip("|").split("|")] for line in lines[2:]]


class Table(unittest.TestCase):
    def test_a_feature_row_splits_closed_open_and_not_planned(self) -> None:
        project = Project(self)
        feature = project.feature(1, budget=6, issue=40)
        gh = FakeGh(
            [
                (ticket("to-tickets F-0001"), {"number": 41, **CLOSED}),
                (ticket("to-tickets F-0001"), {"number": 42, **CLOSED}),
                (ticket("to-tickets F-0001"), {"number": 43, **OPEN}),
                (ticket("fusion-bloquee", "F-0001"), {"number": 44, **OPEN}),
                (ticket("to-tickets F-0001"), {"number": 45, **DROPPED}),
                (ticket("to-tickets F-0002"), {"number": 46, **OPEN}),
                (ticket("main-rouge run 9", "F-0001"), {"number": 47, **OPEN}),
            ]
        )
        text = project.table(gh, feature)
        self.assertTrue(has_table(text, HEADERS), text)
        self.assertEqual(
            rows(text),
            [
                [
                    "F-0001 demo",
                    "#40",
                    "2 / 6",
                    "2",
                    "1",
                    "#43, #44",
                    "2026-11-14 09:30 UTC, gh issue list",
                ]
            ],
        )

    def test_every_open_feature_has_its_row_and_no_total_row(self) -> None:
        states = "- `feature-state` : `abandonnee | abandonne`\n"
        project = Project(self, USINE + states)
        project.feature(1)
        project.feature(2, budget=3)
        project.feature(3, done=True)
        project.feature(4, state="abandonne")
        project.feature(5, state="hors-perimetre")
        text = project.table(FakeGh([(ticket("to-tickets F-0002"), {"number": 9, **OPEN})]))
        self.assertEqual([cells[0] for cells in rows(text)], ["F-0001 demo", "F-0002 demo"])
        self.assertEqual([cells[2] for cells in rows(text)], ["0 / 5", "0 / 3"])
        self.assertNotIn("total", text.lower())

    def test_a_count_gh_cannot_make_stops_the_table(self) -> None:
        project = Project(self)
        feature = project.feature(1)
        with self.assertRaises(CompletionError):
            project.table(FakeGh(None), feature)

    def test_the_command_line_refuses_a_bad_name_and_an_unknown_feature(self) -> None:
        project = Project(self)
        with mock.patch("sys.stderr"):
            self.assertEqual(main(["F-1", "--root", project.root.as_posix()]), 2)
            self.assertEqual(main(["F-0009", "--root", project.root.as_posix()]), 2)


class RepositoryColumn(unittest.TestCase):
    def test_the_key_adds_a_column_its_command_fills(self) -> None:
        project = Project(self, USINE + COLUMN)
        feature = project.feature(1)
        text = project.table(FakeGh([]), feature)
        self.assertTrue(has_table(text, (*HEADERS, "Couverture")), text)
        self.assertEqual(rows(text)[0][-1], "F-0001 ok")

    def test_a_key_without_a_command_is_refused(self) -> None:
        project = Project(self, USINE + "- `completion-column` : `Couverture`\n")
        project.feature(1)
        with self.assertRaises(CompletionError):
            project.table(FakeGh([]))


def human(text: str) -> dict:
    return {
        "type": "user",
        "origin": {"kind": "human"},
        "message": {"role": "user", "content": text},
    }


def assistant(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


TOOL_RESULT = {
    "type": "user",
    "message": {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}],
    },
}
NOTIFICATION = {
    "type": "user",
    "origin": {"kind": "task-notification"},
    "message": {"role": "user", "content": "<task-notification>done</task-notification>"},
}
PEER = {
    "type": "user",
    "isMeta": True,
    "origin": {"kind": "peer"},
    "message": {"role": "user", "content": "What is the completion of F-0001?"},
}


class Guard(unittest.TestCase):
    def setUp(self) -> None:
        self.project = Project(self)
        self.project.feature(1)
        patcher = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": self.project.root.as_posix()})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.table = self.project.table(FakeGh([]))

    def judge(self, *entries: dict, active: bool = False) -> dict | None:
        path = self.project.root / "transcript.jsonl"
        lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        event = {
            "hook_event_name": "Stop",
            "transcript_path": path.as_posix(),
            "stop_hook_active": active,
        }
        return decision(event)

    def test_a_french_question_without_the_table_is_blocked(self) -> None:
        answer = self.judge(
            human("Quel est le % de complétion de F-0001 ?"), assistant("Environ 40 %.")
        )
        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertEqual(answer["decision"], "block")
        self.assertIn("completion.py", answer["reason"])
        self.assertIn("F-0001", answer["reason"])

    def test_an_english_question_without_the_table_is_blocked(self) -> None:
        answer = self.judge(human("What is the progress of the project?"), assistant("Going well."))
        self.assertEqual((answer or {}).get("decision"), "block")

    def test_a_percent_beside_a_feature_is_a_question_on_completion(self) -> None:
        answer = self.judge(human("On en est à quel % sur la feature ?"), assistant("Bientôt."))
        self.assertEqual((answer or {}).get("decision"), "block")

    def test_an_unrelated_question_passes(self) -> None:
        self.assertIsNone(self.judge(human("Merge the PR, please."), assistant("Merged.")))
        self.assertIsNone(self.judge(human("Le CPU est à 90 % ?"), assistant("Oui.")))

    def test_the_table_the_script_prints_passes(self) -> None:
        reply = f"Voici l'avancement :\n\n{self.table}\nSource ci-dessus."
        self.assertIsNone(self.judge(human("Où en est l'avancement ?"), assistant(reply)))

    def test_the_table_earlier_in_the_turn_passes(self) -> None:
        entries = (
            human("Quel est le pourcentage de complétion ?"),
            assistant(self.table),
            TOOL_RESULT,
            assistant("Je relance la CI."),
        )
        self.assertIsNone(self.judge(*entries))

    def test_a_table_missing_a_column_is_blocked(self) -> None:
        partial = "| Feature | Fermés (completed) / budget |\n|---|---|\n| F-0001 | 2 / 5 |\n"
        answer = self.judge(human("Completion of F-0001?"), assistant(partial))
        self.assertEqual((answer or {}).get("decision"), "block")

    def test_the_second_stop_passes_whatever_the_reply(self) -> None:
        self.assertIsNone(self.judge(human("Completion?"), assistant("No table."), active=True))

    def test_session_messages_are_not_the_human(self) -> None:
        entries = (human("Quel est l'avancement ?"), assistant("x"), TOOL_RESULT, NOTIFICATION)
        self.assertEqual((self.judge(*entries) or {}).get("decision"), "block")
        self.assertIsNone(self.judge(human("Merci"), assistant("x"), PEER, assistant("y")))

    def test_the_repository_column_is_required_when_declared(self) -> None:
        usine = self.project.root / "docs" / "agents" / "usine.md"
        usine.write_text(USINE + COLUMN, encoding="utf-8")
        answer = self.judge(human("Avancement ?"), assistant(self.table))
        self.assertEqual((answer or {}).get("decision"), "block")
        self.assertIn("Couverture", (answer or {}).get("reason", ""))
        wide = self.project.table(FakeGh([]))
        self.assertIsNone(self.judge(human("Avancement ?"), assistant(wide)))

    def test_an_unreadable_transcript_passes(self) -> None:
        missing = (self.project.root / "none.jsonl").as_posix()
        self.assertIsNone(decision({"transcript_path": missing, "stop_hook_active": False}))


class HookRegistration(unittest.TestCase):
    def test_the_hook_runs_on_stop(self) -> None:
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        commands = [
            hook["command"] for group in hooks["hooks"].get("Stop", []) for hook in group["hooks"]
        ]
        self.assertTrue(any("guard_completion.py" in command for command in commands), commands)


if __name__ == "__main__":
    unittest.main()
