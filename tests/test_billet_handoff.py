"""The billet of the session handoff (#227, part 2): A5 the clock, A6 the two handoff billets.

Same seams as `test_billet`: `output_check.deviations` holds the rules of the format (the clock
included, given as `now`), `guard_output.outcome` on a `SendMessage` event holds what needs the host
(its clock, the registry of sessions, the handoff file), and the text the plugin prints for a session
(`feature-build`, `handoff_trigger.py yield`) is run through the same check.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone

import support  # noqa: F401 - puts the hooks and the scripts on the import path
from guard_output import REFUSED, outcome
from output_check import deviations
from test_billet import BILLET, billet, current, measure, register, send
from test_guard_output import isolated

NOW = datetime(2026, 11, 16, 13, 13, tzinfo=timezone.utc)  # 14:13 in Paris, 13:13 in UTC


def at(minutes: float, zone: int = 1) -> str:
    """An ISO 8601 time `minutes` after `NOW`, written with the offset of `zone` hours."""
    local = (NOW + timedelta(minutes=minutes)).astimezone(timezone(timedelta(hours=zone)))
    return local.isoformat(timespec="minutes")


def in_minutes(minutes: float) -> str:
    return billet(measure=measure(time=at(minutes)))


class Clock(unittest.TestCase):
    def test_a5_227_a_time_within_five_minutes_of_the_clock_passes(self) -> None:
        """#227 A5: five minutes early, five late, and the same instant in another offset."""
        for minutes, zone in ((0, 1), (5, 1), (-5, 1), (-4, 0), (4, -5)):
            with self.subTest(minutes=minutes, zone=zone):
                text = billet(measure=measure(time=at(minutes, zone)))
                self.assertEqual(deviations(text, "billet", now=NOW), [])

    def test_a5_227_a_time_more_than_five_minutes_off_is_refused_with_both_instants(self) -> None:
        """#227 A5: trial of the day, a time written without reading the clock, 15 minutes wrong."""
        for minutes in (-15, -6, 6, 15, 60):
            with self.subTest(minutes=minutes):
                found = deviations(in_minutes(minutes), "billet", now=NOW)
                self.assertEqual(len(found), 1, found)
                self.assertIn(f"`time={at(minutes)}` is {abs(minutes)} minutes", found[0])
                self.assertIn("host clock", found[0])
                self.assertIn(NOW.isoformat(timespec="minutes"), found[0])
                self.assertIn("at most 5", found[0])

    def test_a5_227_the_same_wall_time_in_the_wrong_offset_is_refused(self) -> None:
        """#227 trial 2: `13:13` written as if it were CET when the host reads UTC is an hour off."""
        found = deviations(billet(measure=measure(time="2026-11-16T13:13+01:00")), "billet", now=NOW)
        self.assertEqual(len(found), 1, found)
        self.assertIn("is 60 minutes", found[0])

    def test_a5_227_a_time_that_is_no_instant_is_named_once(self) -> None:
        """#227 A5: a malformed time is A2's deviation; the clock has nothing to compare."""
        found = deviations(billet(measure=measure(time="14h13")), "billet", now=NOW)
        self.assertEqual(len(found), 1, found)
        self.assertIn("ISO 8601 with its offset", found[0])

    def test_a5_227_without_a_clock_the_time_is_not_compared(self) -> None:
        """#227 A5: `deviations` compares only when given the clock; the hook and the command give it."""
        self.assertEqual(deviations(BILLET, "billet"), [])


class ClockHook(unittest.TestCase):
    def test_a5_227_the_hook_refuses_a_stale_time_and_lets_a_fresh_one_leave(self) -> None:
        """#227 A5: the host clock decides, in the hook that blocks."""
        stale = datetime.now(timezone.utc).astimezone() - timedelta(minutes=15)
        old = billet(measure=measure(time=stale.isoformat(timespec="seconds")))
        with isolated() as project:
            register(project.parent / "home", 4242, sessionId="e1ae680a", name="shipyard-f6", cwd="/x")
            refused = outcome(json.dumps(send("shipyard-f6", old)))
            sent = outcome(json.dumps(send("shipyard-f6", billet(measure=current()))))
        self.assertEqual(refused.code, REFUSED)
        self.assertIn("15 minutes", refused.stderr)
        self.assertIn("host clock", refused.stderr)
        self.assertEqual((sent.code, sent.stderr), (0, ""))


if __name__ == "__main__":
    unittest.main()
