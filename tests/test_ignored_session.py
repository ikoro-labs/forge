"""F-0003 A24 to A28: a session the key `ignored-session` names, held by a live dispatcher lock, is not
a live session of the repository (ikoro-labs/forge#403, part a, design Q1).

Every test runs on a stand-in registry under an isolated HOME and USERPROFILE, without the CLAUDE_ or
GIT_ variables of the session running the tests, and writes nothing in the real ~/.claude.
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import support
from handoff_header import main as header_main
from handoff_header import process_start

RELAY = support.PLUGIN / "hooks" / "handoff_relay.py"
NOTICE = support.PLUGIN / "hooks" / "sessions_notice.py"
KEY = "ignored-session"


def isolated_home(home: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith(("CLAUDE_", "GIT_"))}
    env.update(HOME=str(home), USERPROFILE=str(home), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    return env


class IgnoredSessions(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.repo = self.home / "demo"
        (self.repo / ".git").mkdir(parents=True)
        self.registry = self.home / ".claude" / "sessions"
        self.registry.mkdir(parents=True)
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in [key for key in os.environ if key.startswith(("CLAUDE_", "GIT_"))]:
            del os.environ[name]
        os.environ.update(HOME=str(self.home), USERPROFILE=str(self.home))

    def declare(self, *values: str) -> None:
        """The key `ignored-session` in the project's `usine.md`, one line per value."""
        folder = self.repo / "docs" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "usine.md").write_text("".join(f"- `{KEY}` : `{value}`\n" for value in values), encoding="utf-8")

    def sleeper(self) -> int:
        """A running process that is neither this one nor one of its ancestors."""
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return process.pid

    def register(self, pid: int, **fields: object) -> None:
        entry = {
            "pid": pid, "sessionId": "0801df0e-3c3b", "cwd": str(self.repo), "kind": "interactive",
            "name": "forge-dispatch-403", "procStart": process_start(pid), **fields,
        }
        (self.registry / f"{pid}.json").write_text(json.dumps(entry), encoding="utf-8")

    def lock(self, pid: int, ticket: str = "403", start: str | None = None) -> Path:
        """The dispatcher's lock of a ticket, as the design's data model writes it."""
        project = re.sub(r"[\\/:]", "-", str(self.repo))
        folder = self.home / ".claude" / "hooks" / "state" / "dispatch" / "locks" / project
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{ticket}.json"
        fields = {
            "ticket": ticket, "pid": pid, "start": process_start(pid) if start is None else start,
            "name": "forge-dispatch-403", "worktree": str(self.repo), "zones": [], "since": "2026-11-28T12:00:00Z",
        }
        path.write_text(json.dumps(fields), encoding="utf-8")
        return path

    def sessions(self) -> tuple[int, list[str]]:
        with redirect_stdout(io.StringIO()) as out:
            code = header_main(["handoff_header.py", "sessions", str(self.repo)])
        return code, out.getvalue().splitlines()

    def listed(self, pid: int, kind: str = "interactive", name: str = "forge-dispatch-403") -> str:
        return f"{pid} {kind} {name} ? {self.repo}"

    def test_a_named_session_behind_a_live_lock_is_not_listed(self) -> None:
        """F-0003 A24: the key, a matching name, a live dispatcher lock on its pid."""
        self.declare("forge-dispatch-*")
        pid = self.sleeper()
        self.register(pid)
        self.lock(pid)
        self.assertEqual(self.sessions(), (0, []))

    def test_an_exact_name_is_ignored_and_a_neighbour_is_not(self) -> None:
        """F-0003 A24: a name is exact, or a prefix that ends in `*`."""
        self.declare("forge-dispatch-q-9")
        kept, ignored = self.sleeper(), self.sleeper()
        self.register(ignored, name="forge-dispatch-q-9")
        self.register(kept, name="forge-dispatch-q-90")
        self.lock(ignored, "q-9")
        self.lock(kept, "q-90")
        self.assertEqual(self.sessions(), (6, [self.listed(kept, name="forge-dispatch-q-90")]))

    def test_the_relay_is_not_refused_for_an_ignored_session(self) -> None:
        """F-0003 A24: `handoff_relay.py` does not refuse with code 6 for it; the dry run reaches
        the step that would start the successor."""
        self.declare("forge-dispatch-*")
        pid = self.sleeper()
        self.register(pid)
        self.lock(pid)
        env = isolated_home(self.home)
        git = ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run([*git, "init", "-q"], check=True, env=env)
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True, env=env)
        handoff = self.home / "handoff.md"
        handoff.write_text(
            "---\nprojet: demo\nfeature: \npassage_depart: 1792494562\njetons_agents: 0\nen_vol: []\n"
            "file_revue: []\nsauvetage: []\nsuccesseur:\nhooks_version: forge@test\nseuil:\n"
            "contexte_passation: 151000\n---\n\n# Reprise\n",
            encoding="utf-8",
        )
        env.update(CLAUDE_HANDOFF_CLOSE_DRY_RUN="1", CLAUDE_PID="4242")
        result = subprocess.run(
            [sys.executable, str(RELAY), str(handoff)],
            cwd=self.repo, capture_output=True, encoding="utf-8", env=env, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry run, would run:", result.stdout)

    def test_the_session_start_notice_does_not_name_an_ignored_session(self) -> None:
        """F-0003 A24: `sessions_notice.py` does not signal it."""
        self.declare("forge-dispatch-*")
        pid = self.sleeper()
        self.register(pid)
        self.lock(pid)
        event = {"session_id": "abcdef12-3456", "cwd": str(self.repo), "hook_event_name": "SessionStart"}
        result = subprocess.run(
            [sys.executable, str(NOTICE)], input=json.dumps(event), capture_output=True, text=True,
            env=isolated_home(self.home), cwd=self.repo, timeout=60, check=False,
        )
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_a_named_session_without_a_lock_is_listed_even_when_interactive(self) -> None:
        """F-0003 A25: a session of the human is never behind a dispatcher lock; the launch mode
        can only add a refusal."""
        self.declare("forge-dispatch-*")
        pid = self.sleeper()
        self.register(pid)
        self.assertEqual(self.sessions(), (6, [self.listed(pid)]))

    def test_a_lock_whose_pid_was_reused_does_not_ignore_the_session(self) -> None:
        """F-0003 A25: only a lock held by the live process counts; a pid reused by another process
        carries another start time."""
        self.declare("forge-dispatch-*")
        pid = self.sleeper()
        self.register(pid)
        self.lock(pid, start="1")
        self.assertEqual(self.sessions(), (6, [self.listed(pid)]))

    def test_a_pass_whose_name_matches_no_line_is_listed_behind_its_lock(self) -> None:
        """F-0003 A26: a long `claude -p` pass is a real session."""
        self.declare("forge-dispatch-*")
        pid = self.sleeper()
        self.register(pid, name="relais-3-demo")
        self.lock(pid)
        self.assertEqual(self.sessions(), (6, [self.listed(pid, name="relais-3-demo")]))

    def test_an_unreadable_entry_or_lock_still_counts_as_live(self) -> None:
        """F-0003 A27: the prudent side, an unreadable registry entry or an unreadable lock."""
        self.declare("forge-dispatch-*")
        (self.registry / "4242.json").write_text("{pas du json", encoding="utf-8")
        pid = self.sleeper()
        self.register(pid)
        self.lock(pid).write_text("{pas du json", encoding="utf-8")
        code, lines = self.sessions()
        self.assertEqual(code, 6)
        self.assertEqual(len(lines), 2, lines)
        self.assertIn(self.listed(pid), lines)
        self.assertTrue(any(line.startswith("4242 ") and "unreadable" in line for line in lines), lines)

    def test_without_the_key_the_output_is_the_one_of_today(self) -> None:
        """F-0003 A28: no `ignored-session`, a lock on a live pid: the session is listed."""
        pid = self.sleeper()
        self.register(pid)
        self.lock(pid)
        self.assertEqual(self.sessions(), (6, [self.listed(pid)]))
        (self.repo / "docs" / "agents").mkdir(parents=True)
        (self.repo / "docs" / "agents" / "usine.md").write_text("- `install` : `uv sync`\n", encoding="utf-8")
        self.assertEqual(self.sessions(), (6, [self.listed(pid)]))


if __name__ == "__main__":
    unittest.main()
