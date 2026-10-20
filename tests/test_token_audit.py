import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import support
from token_audit import MAIN_SESSION, Call, compare, config_dir, main, read_calls, summarize

SCRIPT = support.PLUGIN / "scripts" / "token_audit.py"


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def line(
    cwd: Path,
    when: str,
    *,
    message: str,
    request: str = "",
    agent: str | None = None,
    session: str = "s1",
    agent_id: str | None = None,
    model: str = "claude-opus-5-5",
    effort: str = "high",
    usage: tuple[int, int, int, int] = (1, 10, 100, 5),
    stop: str | None = "end_turn",
) -> str:
    entry = {
        "type": "assistant",
        "cwd": str(cwd),
        "timestamp": f"{when}.000Z",
        "sessionId": session,
        "requestId": request or f"req-{message}",
        "effort": effort,
        "message": {
            "id": message,
            "model": model,
            "stop_reason": stop,
            "usage": dict(
                zip(
                    ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"),
                    usage,
                )
            ),
        },
    }
    if agent is not None:
        entry["attributionAgent"] = agent
    if agent_id is not None:
        entry["agentId"] = agent_id
    return json.dumps(entry)


class Logs(unittest.TestCase):
    """A fake Claude Code config: one folder per project, sessions, and their subagents."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.config = self.root / "config"
        self.project = self.root / "dev" / "forge"

    def write(self, folder: str, name: str, *lines: str) -> Path:
        path = self.config / "projects" / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{text}\n" for text in lines), encoding="utf-8")
        return path

    def calls(self, **period: datetime | None) -> tuple[list[Call], int]:
        return read_calls(self.config, self.project, **period)


class ReadCalls(Logs):
    def test_only_the_project_and_its_worktrees_count(self) -> None:
        worktree = self.project / ".claude" / "worktrees" / "x"
        self.write("p", "s1.jsonl", line(self.project, "2026-10-20T10:00:00", message="a"))
        self.write("w", "s2.jsonl", line(worktree, "2026-10-20T10:00:00", message="b"))
        self.write("q", "s3.jsonl", line(self.root / "dev" / "forge2", "2026-10-20T10:00:00", message="c"))
        self.write("r", "s4.jsonl", line(self.root / "dev", "2026-10-20T10:00:00", message="d"))
        calls, bad = self.calls()
        self.assertEqual(sorted(call.message for call in calls), ["a", "b"])
        self.assertEqual(bad, 0)

    def test_a_reply_written_on_several_lines_counts_once(self) -> None:
        reply = line(self.project, "2026-10-20T10:00:00", message="a", request="r1")
        other_request = line(self.project, "2026-10-20T10:00:01", message="a", request="r2")
        self.write("p", "s1.jsonl", reply, reply, reply, other_request)
        calls, _ = self.calls()
        self.assertEqual(len(calls), 2)

    def test_a_subagent_line_carries_its_role_and_launch(self) -> None:
        self.write(
            "p",
            "s1/subagents/agent-a1.jsonl",
            line(self.project, "2026-10-20T10:00:00", message="a", agent="forge:qc-gate", agent_id="a1"),
        )
        self.write("p", "s1.jsonl", line(self.project, "2026-10-20T10:00:00", message="b"))
        calls = {call.message: call for call in self.calls()[0]}
        self.assertEqual((calls["a"].role, calls["a"].launch), ("forge:qc-gate", "a1"))
        self.assertEqual((calls["b"].role, calls["b"].launch), (MAIN_SESSION, "s1"))

    def test_the_period_keeps_its_start_and_drops_its_end(self) -> None:
        self.write(
            "p",
            "s1.jsonl",
            line(self.project, "2026-10-19T23:59:59", message="before"),
            line(self.project, "2026-10-20T00:00:00", message="start"),
            line(self.project, "2026-10-20T23:59:59", message="inside"),
            line(self.project, "2026-10-21T00:00:00", message="end"),
        )
        calls, _ = self.calls(since=utc("2026-10-20T00:00:00"), until=utc("2026-10-21T00:00:00"))
        self.assertEqual([call.message for call in calls], ["start", "inside"])

    def test_a_file_untouched_since_before_the_period_is_not_read(self) -> None:
        path = self.write("p", "s1.jsonl", line(self.project, "2026-10-20T10:00:00", message="a"))
        old = utc("2026-01-01T00:00:00").timestamp()
        os.utime(path, (old, old))
        self.assertEqual(self.calls(since=utc("2026-10-01T00:00:00"))[0], [])
        self.assertEqual(len(self.calls()[0]), 1)

    def test_an_unreadable_line_is_counted_and_the_rest_is_read(self) -> None:
        self.write(
            "p",
            "s1.jsonl",
            '{"type": "assistant", "cwd": ',
            json.dumps({"type": "assistant", "cwd": str(self.project), "timestamp": "hier"}),
            line(self.project, "2026-10-20T10:00:00", message="a"),
        )
        calls, bad = self.calls()
        self.assertEqual([call.message for call in calls], ["a"])
        self.assertEqual(bad, 2)

    def test_other_lines_and_synthetic_replies_are_ignored(self) -> None:
        self.write(
            "p",
            "s1.jsonl",
            json.dumps({"type": "user", "cwd": str(self.project), "message": {"content": "assistant"}}),
            line(self.project, "2026-10-20T10:00:00", message="a", model="<synthetic>", usage=(0, 0, 0, 0)),
            line(self.project, "2026-10-20T10:00:00", message="b"),
        )
        calls, bad = self.calls()
        self.assertEqual([call.message for call in calls], ["b"])
        self.assertEqual(bad, 0)


class Summaries(Logs):
    def test_groups_by_role_model_and_effort_with_their_launches(self) -> None:
        self.write(
            "p",
            "s1/subagents/agent-a1.jsonl",
            line(self.project, "2026-10-20T10:00:00", message="a", agent="forge:qc-gate", agent_id="a1"),
            line(self.project, "2026-10-20T10:00:01", message="b", agent="forge:qc-gate", agent_id="a1"),
        )
        self.write(
            "p",
            "s1/subagents/agent-a2.jsonl",
            line(self.project, "2026-10-20T11:00:00", message="c", agent="forge:qc-gate", agent_id="a2"),
            line(
                self.project, "2026-10-20T11:00:01", message="d", agent="forge:qc-gate", agent_id="a2",
                model="claude-haiku-5-5", effort="low",
            ),
        )
        rows = {(row.role, row.model, row.effort): row for row in summarize(self.calls()[0])}
        opus = rows["forge:qc-gate", "claude-opus-5-5", "high"]
        self.assertEqual(opus.launches, 2)
        self.assertEqual(opus.replies, 3)
        self.assertEqual(opus.tokens, (3, 30, 300, 15))
        self.assertEqual(rows["forge:qc-gate", "claude-haiku-5-5", "low"].launches, 1)

    def test_a_reply_logged_before_its_end_is_counted_as_partial(self) -> None:
        early = line(self.project, "2026-10-20T10:00:00", message="a", request="r1", stop=None)
        final = line(self.project, "2026-10-20T10:00:01", message="a", request="r1", usage=(1, 10, 100, 50))
        self.write("p", "s1.jsonl", early, final, early)
        self.write("p", "s2.jsonl", line(self.project, "2026-10-20T11:00:00", message="b", session="s2", stop=None))
        calls = {call.message: call for call in self.calls()[0]}
        self.assertEqual((calls["a"].final, calls["a"].tokens[3]), (True, 50))
        [row] = summarize(list(calls.values()))
        self.assertEqual(row.partial, 1)

    def test_the_comparison_divides_by_launches_per_role(self) -> None:
        cut = "2026-10-20T12:00:00"
        self.write(
            "p",
            "s1/subagents/agent-a1.jsonl",
            line(self.project, "2026-10-20T10:00:00", message="a", agent="forge:qc-gate", agent_id="a1",
                 usage=(0, 100, 1000, 40)),
        )
        for number in (2, 3):
            self.write(
                "p",
                f"s1/subagents/agent-a{number}.jsonl",
                line(self.project, "2026-10-20T13:00:00", message=f"m{number}", agent="forge:qc-gate",
                     agent_id=f"a{number}", model="claude-haiku-5-5", effort="low", usage=(0, 10, 100, 4)),
            )
        calls = self.calls()[0]
        rows = {row.role: row for row in compare(calls, utc(cut))}
        gate = rows["forge:qc-gate"]
        self.assertEqual((gate.before_launches, gate.after_launches), (1, 2))
        self.assertEqual(gate.before_per_launch, 1140)
        self.assertEqual(gate.after_per_launch, 114)


class ConfigDir(unittest.TestCase):
    def test_claude_config_dir_wins_over_home(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            env = {"HOME": home, "USERPROFILE": home}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(config_dir(), Path(home) / ".claude")
            with mock.patch.dict(os.environ, {**env, "CLAUDE_CONFIG_DIR": str(Path(home) / "autre")}, clear=True):
                self.assertEqual(config_dir(), Path(home) / "autre")


class CommandLine(Logs):
    def setUp(self) -> None:
        super().setUp()
        self.write(
            "p",
            "s1/subagents/agent-a1.jsonl",
            line(self.project, "2026-10-20T10:00:00", message="a", agent="forge:qc-gate", agent_id="a1"),
        )
        self.write("p", "s1.jsonl", line(self.project, "2026-10-20T13:00:00", message="b"), "pas du json")

    def env(self) -> dict[str, str]:
        env = {key: value for key, value in os.environ.items() if not key.startswith("CLAUDE_")}
        env.update(HOME=str(self.root), USERPROFILE=str(self.root), CLAUDE_CONFIG_DIR=str(self.config))
        # The report is French: a Windows pipe would otherwise carry it in the ANSI code page.
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def run_main(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env(), clear=True), redirect_stdout(out):
            code = main([*args])
        return code, out.getvalue()

    def test_the_report_names_each_group_and_the_unreadable_lines(self) -> None:
        code, out = self.run_main(str(self.project))
        self.assertEqual(code, 0)
        self.assertIn("| forge:qc-gate | claude-opus-5-5 | high | 1 |", out)
        self.assertIn(f"| {MAIN_SESSION} | claude-opus-5-5 | high | 1 |", out)
        self.assertIn("1 ligne illisible", out)
        self.assertIn("| Sortie | Sortie partielle |", out)

    def test_the_cut_prints_before_and_after(self) -> None:
        code, out = self.run_main(str(self.project), "--coupure", "2026-10-20T12:00:00")
        self.assertEqual(code, 0)
        self.assertIn("| forge:qc-gate | 1 | 116 | 0 | - | - |", out)
        self.assertIn(f"| {MAIN_SESSION} | 0 | - | 1 | 116 | - |", out)

    def test_a_bad_date_is_refused_with_its_reason(self) -> None:
        err = io.StringIO()
        with mock.patch("sys.stderr", err), self.assertRaises(SystemExit) as raised:
            self.run_main(str(self.project), "--depuis", "hier")
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("hier", err.getvalue())

    def test_the_script_runs_alone_in_an_isolated_home(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.project), "--depuis", "2026-10-20"],
            capture_output=True, text=True, encoding="utf-8", env=self.env(), check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("forge:qc-gate", result.stdout)


class Skill(unittest.TestCase):
    def test_the_skill_runs_the_script_from_the_plugin_root(self) -> None:
        text = (support.PLUGIN / "skills" / "audit-jetons" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("disable-model-invocation: true", text)
        self.assertIn(
            'uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/token_audit.py"', text
        )


if __name__ == "__main__":
    unittest.main()
