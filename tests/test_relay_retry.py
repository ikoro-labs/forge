"""F-0003 A29 to A33: a relay refused in code 6 retries by a detached copy of itself, with a capped backoff
and a bound that CLAUDE_HANDOFF_RETRY_MINUTES sets (ikoro-labs/forge#403, part b, design Q2).

The relay and its detached copy run in this process, on a stand-in registry under an isolated HOME and
USERPROFILE, without the CLAUDE_ or GIT_ variables of the session running the tests. `claude` is a stub on
PATH, the clock and the jitter are replaced, and `spawn` records the copy instead of starting it: no
detached process survives a test and nothing is written in the real ~/.claude. The one test that really
detaches (Linux only) kills the copy it started.
"""

import contextlib
import datetime
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from handoff_header import process_start
from handoff_relay import WINDOWS, backoff
from handoff_relay import main as relay_main

RELAY = support.PLUGIN / "hooks" / "handoff_relay.py"

HANDOFF = (
    "---\nprojet: demo\nfeature: \npassage_depart: 1792494562\njetons_agents: 0\nen_vol: []\n"
    "file_revue: []\nsauvetage: []\nsuccesseur:\nhooks_version: forge@test\nseuil:\n"
    "contexte_passation: 151000\n---\n\n# Reprise\n"
)
OTHER_ENDS = 240


class Clock:
    """Replaces `handoff_relay.pause`: time only moves when the copy waits, and the other session ends
    during the first wait that reaches `end_at`."""

    def __init__(self, victim: subprocess.Popen | None = None, end_at: int = OTHER_ENDS) -> None:
        self.now: float = 0
        self.waits: list[int] = []
        self.victim = victim
        self.end_at = end_at

    def pause(self, seconds: float) -> None:
        self.waits.append(int(seconds))
        self.now += seconds
        if self.victim is not None and self.now >= self.end_at:
            self.victim.kill()
            self.victim.wait()
            self.victim = None


class RelayRetry(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.repo = self.home / "demo"
        self.repo.mkdir()
        self.state = self.home / ".claude" / "hooks" / "state"
        self.registry = self.home / ".claude" / "sessions"
        self.registry.mkdir(parents=True)
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        self.log = self.home / "claude.log"
        stub = bin_dir / "stub_claude.py"
        stub.write_text(
            "import os, sys\n"
            f"with open({str(self.log)!r}, 'a', encoding='utf-8') as log:\n"
            "    log.write(' '.join(sys.argv[1:]) + '\\n')\n"
            "sys.stdout.reconfigure(encoding='utf-8')\n"
            "print('relais backgrounded · abcdef12 · claude attach abcdef12')\n",
            encoding="utf-8",
        )
        if WINDOWS:
            (bin_dir / "claude.cmd").write_text(f'@"{sys.executable}" "{stub}" %*\r\n', encoding="utf-8")
        else:
            launcher = bin_dir / "claude"
            launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{stub}" "$@"\n', encoding="utf-8")
            launcher.chmod(0o755)
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in [key for key in os.environ if key.startswith(("CLAUDE_", "GIT_"))]:
            del os.environ[name]
        os.environ.update(
            HOME=str(self.home), USERPROFILE=str(self.home), PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, CLAUDE_HANDOFF_CLOSE_DELAY="0",
            CLAUDE_HANDOFF_TERMINAL="off", CLAUDE_HANDOFF_RELAY_MAX="3",
        )
        git = ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        previous = Path.cwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, previous)
        self.handoff = self.home / "handoff.md"
        self.handoff.write_text(HANDOFF, encoding="utf-8")
        self.spawned: list[list[str]] = []
        spawner = mock.patch("handoff_relay.spawn", side_effect=self.spawned.append)
        spawner.start()
        self.addCleanup(spawner.stop)
        flat = re.sub(r"[\\/:]", "-", str(self.repo))
        self.counter = self.state / f"relay-{flat}-{datetime.date.today().isoformat()}.count"

    def other_session(self) -> subprocess.Popen:
        """A live session of the repository that is neither this process nor its ancestor."""
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        entry = {
            "pid": process.pid, "sessionId": "0801df0e-3c3b", "cwd": str(self.repo), "kind": "interactive",
            "name": "work", "procStart": process_start(process.pid),
        }
        (self.registry / f"{process.pid}.json").write_text(json.dumps(entry), encoding="utf-8")
        return process

    def relay(self, *flags: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = relay_main([*flags, str(self.handoff)])
        return code, out.getvalue(), err.getvalue()

    def copy(self, clock: Clock, jitter: float = 1.0) -> tuple[int, str, str]:
        """Run the detached copy the refused relay would have started, from the argv it was given."""
        self.assertEqual(len(self.spawned), 1, self.spawned)
        argv = self.spawned[0]
        out, err = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err),
            mock.patch("handoff_relay.pause", clock.pause),
            mock.patch("handoff_relay.jitter", return_value=jitter),
        ):
            code = relay_main(argv[argv.index("--retry"):])
        return code, out.getvalue(), err.getvalue()

    def launched(self) -> list[str]:
        """The `claude` calls that started a successor."""
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def test_a_refused_relay_starts_a_detached_copy_and_returns_at_once(self) -> None:
        """F-0003 A29: code 6 with the variable at 30: the relay is still refused, a copy is started, no
        successor yet and the counter has not moved."""
        self.other_session()
        os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = "30"
        code, out, err = self.relay()
        self.assertEqual(code, 6, err)
        self.assertIn("relay refused: another session is live", err)
        self.assertEqual(len(self.spawned), 1, self.spawned)
        self.assertIn("--retry", self.spawned[0])
        self.assertEqual(self.launched(), [])
        self.assertFalse(self.counter.exists())

    def test_the_copy_starts_the_successor_at_most_300_seconds_after_the_other_session_ends(self) -> None:
        """F-0003 A29: the other session ends after 4 minutes; whatever the jitter draws, the successor
        starts within 300 s of that end, and the counter moves once."""
        for jitter in (0.8, 1.0, 1.2):
            with self.subTest(jitter=jitter):
                self.spawned.clear()
                self.log.unlink(missing_ok=True)
                self.counter.unlink(missing_ok=True)
                other = self.other_session()
                os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = "30"
                self.assertEqual(self.relay()[0], 6)
                clock = Clock(other)
                code, out, err = self.copy(clock, jitter)
                self.assertEqual(code, 0, err)
                self.assertEqual(len(self.launched()), 1, self.launched())
                self.assertGreaterEqual(clock.now, OTHER_ENDS)
                self.assertLessEqual(clock.now - OTHER_ENDS, 300)
                self.assertEqual(self.counter.read_text(encoding="utf-8").strip(), "1")
                self.handoff.write_text(HANDOFF, encoding="utf-8")

    def test_the_waits_double_from_30_seconds_and_stop_growing_at_300(self) -> None:
        """F-0003 A29: 30 s, doubled, capped at 300 s, and the jitter never lifts a wait over the cap."""
        other = self.other_session()
        os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = "60"
        self.assertEqual(self.relay()[0], 6)
        clock = Clock(other, end_at=2000)
        self.copy(clock)
        self.assertEqual(clock.waits[:7], [30, 60, 120, 240, 300, 300, 300])
        for jitter in (0.8, 1.2):
            with self.subTest(jitter=jitter):
                self.assertEqual(backoff(0, jitter), round(30 * jitter))
                self.assertEqual(backoff(9, jitter), min(round(300 * jitter), 300))


    def test_the_copy_stops_at_the_bound_in_code_6_and_says_how_many_tries_and_how_long(self) -> None:
        """F-0003 A30: another session that never ends, 30 minutes: code 6, no successor, and the message
        names the number of tries and the time waited."""
        for jitter in (0.8, 1.0, 1.2):
            with self.subTest(jitter=jitter):
                self.spawned.clear()
                self.other_session()
                os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = "30"
                self.assertEqual(self.relay()[0], 6)
                clock = Clock()
                code, out, err = self.copy(clock, jitter)
                self.assertEqual(code, 6, err)
                self.assertEqual(clock.now, 30 * 60)
                self.assertEqual(self.launched(), [])
                self.assertFalse(self.counter.exists())
                self.assertIn(f"after {len(clock.waits)} tries and 1800 s waited", err)
                self.assertIn("CLAUDE_HANDOFF_RETRY_MINUTES=30", err)


if __name__ == "__main__":
    unittest.main()
