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
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import support
from agent_lock import read as read_lock
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

    def __init__(
        self, victim: subprocess.Popen | None = None, end_at: int = OTHER_ENDS,
        during: Callable[[int], None] | None = None,
    ) -> None:
        self.now: float = 0
        self.waits: list[int] = []
        self.victim = victim
        self.end_at = end_at
        self.during = during

    def pause(self, seconds: float) -> None:
        self.waits.append(int(seconds))
        self.now += seconds
        if self.during is not None:
            self.during(len(self.waits))
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
            "if os.environ.get('STUB_SILENT'):\n"
            "    sys.exit(0)\n"
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


    def test_a_refusal_in_code_2_3_4_or_5_is_not_retried(self) -> None:
        """F-0003 A31: the variable is set, the relay is refused for another reason than code 6."""
        os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = "30"
        invalid = self.home / "invalid.md"
        invalid.write_text("no front matter\n", encoding="utf-8")
        in_flight = self.home / "in_flight.md"
        in_flight.write_text(HANDOFF.replace("en_vol: []", "en_vol:\n  - coder #12"), encoding="utf-8")
        capped = {"counter": "3\n"}
        silent = {"STUB_SILENT": "1"}
        cases = [
            (2, invalid, {}), (3, self.handoff, capped), (4, self.handoff, silent), (5, in_flight, {}),
        ]
        for expected, path, extra in cases:
            with self.subTest(code=expected):
                self.counter.parent.mkdir(parents=True, exist_ok=True)
                self.counter.unlink(missing_ok=True)
                if "counter" in extra:
                    self.counter.write_text(extra["counter"], encoding="utf-8")
                with mock.patch.dict(os.environ, {k: v for k, v in extra.items() if k != "counter"}):
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        code = relay_main([str(path)])
                self.assertEqual(code, expected, err.getvalue())
                self.assertEqual(self.spawned, [])
                self.assertNotIn("retr", out.getvalue() + err.getvalue())

    def test_without_the_variable_a_refusal_in_code_6_is_not_retried(self) -> None:
        """F-0003 A32: the variable absent, the relay is refused as it is today."""
        self.other_session()
        code, out, err = self.relay()
        self.assertEqual(code, 6, err)
        self.assertEqual(self.spawned, [])
        self.assertNotIn("CLAUDE_HANDOFF_RETRY_MINUTES", out + err)

    def test_a_value_outside_1_to_1440_is_not_retried_and_is_reported_as_written(self) -> None:
        """F-0003 A32: not a number, 0, 1441, a sign or a fraction: no retry, and the value is named."""
        self.other_session()
        for value in ("0", "1441", "abc", "-5", "30.5", "1e2", "30 minutes"):
            with self.subTest(value=value):
                os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = value
                code, out, err = self.relay()
                self.assertEqual(code, 6, err)
                self.assertEqual(self.spawned, [])
                self.assertIn(f"CLAUDE_HANDOFF_RETRY_MINUTES={value} is not an integer from 1 to 1440", err)

    def test_the_variable_set_but_empty_is_the_variable_absent(self) -> None:
        """F-0003 A32: an empty value is not a bound and is not reported."""
        self.other_session()
        os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = ""
        code, out, err = self.relay()
        self.assertEqual((code, self.spawned), (6, []))
        self.assertNotIn("CLAUDE_HANDOFF_RETRY_MINUTES", out + err)

    def test_the_bounds_1_and_1440_are_valid(self) -> None:
        """F-0003 A32: the range is closed: 1 and 1440 start a copy."""
        self.other_session()
        for value in ("1", "1440"):
            with self.subTest(value=value):
                self.spawned.clear()
                os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = value
                self.assertEqual(self.relay()[0], 6)
                self.assertEqual(len(self.spawned), 1, self.spawned)

    def trace(self) -> list[dict[str, object]]:
        """The lines of the day's retry trace of the project, as written."""
        flat = re.sub(r"[\\/:]", "-", str(self.repo))
        path = self.state / f"relay-retry-{flat}-{datetime.date.today().isoformat()}.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_each_try_writes_one_trace_line_with_its_wait_and_its_code(self) -> None:
        """F-0003 A33: date, project, attempt number, wait and code, one line per try."""
        other = self.other_session()
        os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = "30"
        self.assertEqual(self.relay()[0], 6)
        clock = Clock(other)
        self.assertEqual(self.copy(clock)[0], 0)
        lines = self.trace()
        self.assertEqual(len(lines), len(clock.waits))
        self.assertEqual([line["attempt"] for line in lines], list(range(1, len(lines) + 1)))
        self.assertEqual([line["wait_s"] for line in lines], clock.waits)
        self.assertEqual([line["code"] for line in lines], [6] * (len(lines) - 1) + [0])
        for line in lines:
            self.assertEqual(set(line), {"date", "project", "attempt", "wait_s", "code"})
            self.assertEqual(line["project"], str(self.repo))
            self.assertEqual(datetime.datetime.fromisoformat(str(line["date"])).date(), datetime.date.today())

    def test_the_last_trace_line_at_the_bound_carries_the_message(self) -> None:
        """F-0003 A33 and A30: the line of the try that reaches the bound says the tries and the time waited."""
        self.other_session()
        os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = "30"
        self.assertEqual(self.relay()[0], 6)
        clock = Clock()
        code, out, err = self.copy(clock)
        self.assertEqual(code, 6)
        lines = self.trace()
        self.assertEqual(len(lines), len(clock.waits))
        self.assertEqual([line["code"] for line in lines], [6] * len(lines))
        message = str(lines[-1]["message"])
        self.assertIn(f"after {len(lines)} tries and 1800 s waited", message)
        self.assertTrue(all("message" not in line for line in lines[:-1]))
        self.assertIn(message, err)


    def lock_path(self) -> Path:
        flat = re.sub(r"[\\/:]", "-", str(self.repo))
        return self.state / f"relay-retry-{flat}.lock"

    def write_lock(self, pid: int, start: str) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        fields = {"ticket": "relay-retry", "pid": pid, "start": start, "name": "relay-retry"}
        self.lock_path().write_text(json.dumps(fields), encoding="utf-8")

    def test_the_handoff_is_read_again_at_each_try(self) -> None:
        """F-0003 A29 (design Q2): a handoff that changes between two tries is the one the next try reads."""
        self.other_session()
        os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = "30"
        self.assertEqual(self.relay()[0], 6)

        def spoil(wait_number: int) -> None:
            if wait_number == 2:
                self.handoff.write_text("no front matter\n", encoding="utf-8")

        code, out, err = self.copy(Clock(during=spoil))
        self.assertEqual(code, 2)
        self.assertEqual([line["code"] for line in self.trace()], [6, 2])

    def test_one_copy_waits_per_project(self) -> None:
        """F-0003 A29 (design Q2): while a live copy holds the project's lock, a refused relay starts no
        second one, and a second copy that is started anyway leaves without waiting."""
        holder = self.other_session()
        self.write_lock(holder.pid, process_start(holder.pid))
        os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = "30"
        code, out, err = self.relay()
        self.assertEqual((code, self.spawned), (6, []))
        self.assertIn("a retry already waits for this repository", out)
        self.spawned.append([sys.executable, str(RELAY), "--retry", json.dumps({
            "minutes": 30, "force": False, "handoff": str(self.handoff), "owner": "", "owner_start": "",
        })])
        clock = Clock()
        self.assertEqual(self.copy(clock)[0], 6)
        self.assertEqual(clock.waits, [])
        self.assertTrue(self.lock_path().exists())

    def test_the_lock_of_a_dead_copy_is_replaced_and_the_lock_is_released_at_the_end(self) -> None:
        """F-0003 A29 (design Q2): a lock whose holder is gone does not stop the retry; the copy frees it."""
        gone = subprocess.Popen([sys.executable, "-c", "pass"])
        gone.wait()
        self.write_lock(gone.pid, "1")
        other = self.other_session()
        os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = "30"
        self.assertEqual(self.relay()[0], 6)
        self.assertEqual(len(self.spawned), 1)
        self.assertEqual(self.copy(Clock(other))[0], 0)
        self.assertFalse(self.lock_path().exists())

    def test_the_lock_of_an_unreadable_copy_counts_as_held(self) -> None:
        """F-0003 A29 (design Q2): the prudent side, as for an unreadable agent lock."""
        self.other_session()
        self.state.mkdir(parents=True, exist_ok=True)
        self.lock_path().write_text("{pas du json", encoding="utf-8")
        os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = "30"
        code, out, err = self.relay()
        self.assertEqual((code, self.spawned), (6, []))

    def test_a_dry_run_starts_no_copy_and_says_what_it_would_start(self) -> None:
        """F-0003 A29: CLAUDE_HANDOFF_CLOSE_DRY_RUN prints the retry instead of starting it."""
        self.other_session()
        os.environ["CLAUDE_HANDOFF_RETRY_MINUTES"] = "30"
        os.environ["CLAUDE_HANDOFF_CLOSE_DRY_RUN"] = "1"
        code, out, err = self.relay()
        self.assertEqual((code, self.spawned), (6, []))
        self.assertIn("dry run, would start a detached retry for up to 30 minutes", out)

    def test_the_calling_session_is_closed_at_a_success_only_while_it_still_runs(self) -> None:
        """F-0003 A29: the copy outlives the session that called the relay; it closes that session only
        when the pid still runs it."""
        for alive in (True, False):
            with self.subTest(session_alive=alive):
                self.spawned.clear()
                os.environ.pop("CLAUDE_HANDOFF_CLOSE_DRY_RUN", None)
                caller, other = self.other_session(), self.other_session()
                os.environ.update(
                    CLAUDE_PID=str(caller.pid), CLAUDE_HANDOFF_RETRY_MINUTES="30",
                    CLAUDE_HANDOFF_CLOSE_DELAY="45",
                )
                self.assertEqual(self.relay()[0], 6)
                if not alive:
                    caller.kill()
                    caller.wait()
                # The copy only prints the closing it would run: no session is stopped by the test.
                os.environ["CLAUDE_HANDOFF_CLOSE_DRY_RUN"] = "1"
                code, out, err = self.copy(Clock(other))
                self.assertEqual(code, 0, err)
                self.assertEqual("would run in 45s" in out, alive, out)
                self.handoff.write_text(HANDOFF, encoding="utf-8")
                caller.kill()
                caller.wait()

    @unittest.skipIf(WINDOWS, "the copy is checked with os.getsid, which Windows has not")
    def test_the_relay_really_detaches_the_copy_and_returns_at_once(self) -> None:
        """F-0003 A29: run as a process, the refused relay returns code 6 without waiting, and the copy it
        started lives in a session of its own. The test ends the copy."""
        self.other_session()
        env = {key: value for key, value in os.environ.items() if not key.startswith(("CLAUDE_", "GIT_"))}
        env.update(CLAUDE_HANDOFF_RETRY_MINUTES="1", CLAUDE_HANDOFF_CLOSE_DELAY="0", CLAUDE_HANDOFF_TERMINAL="off")
        self.addCleanup(self.end_copy)
        result = subprocess.run(
            [sys.executable, str(RELAY), str(self.handoff)],
            cwd=self.repo, capture_output=True, encoding="utf-8", env=env, timeout=60, check=False,
        )
        self.assertEqual(result.returncode, 6, result.stderr)
        self.assertIn("no successor yet", result.stdout)
        pid = self.copy_pid(wait=10)
        self.assertIsNotNone(pid, "the copy took no lock")
        self.assertNotEqual(os.getsid(pid or 0), os.getsid(0))

    def copy_pid(self, wait: float = 0) -> int | None:
        """The pid in the project's lock, once the copy has written it."""
        deadline = time.monotonic() + wait
        while True:
            lock = read_lock(self.lock_path()) if self.lock_path().exists() else None
            if lock is not None or time.monotonic() >= deadline:
                return lock.pid if lock else None
            time.sleep(0.1)

    def end_copy(self) -> None:
        pid = self.copy_pid(wait=2)
        if pid:
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)


if __name__ == "__main__":
    unittest.main()
