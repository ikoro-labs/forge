"""The billet (#227): the closed envelope two sessions of a host exchange by `SendMessage`.

Two seams. `output_check.deviations(text, "billet", config)` holds every rule of the format, one test
per deviation it names. `guard_output.outcome` on a `PreToolUse` event for `SendMessage` holds what
the hook adds: it judges a message to another session only, and a refused message does not leave.
"""

import unittest

import support
from output_check import deviations, required_fields

TEMPLATE = support.PLUGIN / "templates" / "billet.md"
BILLET = (
    "from: forge-build\n"
    "type: claim\n"
    "resource: worktree-pool\n"
    "ticket: #227\n"
    "measure: load=1.25 memory=5200MB time=2026-11-16T14:13+01:00\n"
    "awaits: reply\n"
    "---\n"
    "I take the pool for the next hour. Tell me if you need it sooner.\n"
)


def billet(**changes: str | None) -> str:
    """`BILLET` with the value of a field replaced, or the field dropped when the value is None."""
    lines = []
    for line in BILLET.splitlines():
        key = line.split(":", 1)[0]
        if key in changes:
            if changes[key] is None:
                continue
            line = f"{key}: {changes[key]}"
        lines.append(line)
    return "\n".join(lines) + "\n"


class Template(unittest.TestCase):
    def test_a1_227_the_template_declares_the_six_fields(self) -> None:
        """#227 A1: `from`, `type`, `resource`, `ticket`, `measure` and `awaits`."""
        fields = [labels[0] for labels in required_fields(TEMPLATE.read_text(encoding="utf-8"))]
        self.assertEqual(fields, ["from", "type", "resource", "ticket", "measure", "awaits"])

    def test_a1_227_the_template_names_the_values_of_type_and_awaits(self) -> None:
        """#227 A1: the lists the guard enforces are the ones the template shows."""
        text = TEMPLATE.read_text(encoding="utf-8")
        for value in ("claim", "release", "info", "question", "reply", "nothing"):
            with self.subTest(value=value):
                self.assertIn(f"`{value}`", text)


class Prose(unittest.TestCase):
    def test_a1_227_a_billet_in_the_template_form_conforms(self) -> None:
        """#227 A1: the six fields, `---`, then a short prose."""
        self.assertEqual(deviations(BILLET, "billet"), [])

    def test_a1_227_sixty_words_of_prose_pass_and_sixty_one_are_refused(self) -> None:
        """#227 A1: 60 words of prose at most, counted after `---`."""
        sixty = " ".join(["word"] * 60)
        self.assertEqual(deviations(BILLET.split("---")[0] + f"---\n{sixty}\n", "billet"), [])
        found = deviations(BILLET.split("---")[0] + f"---\n{sixty} word\n", "billet")
        self.assertEqual(len(found), 1)
        self.assertIn("61 words of prose", found[0])
        self.assertIn("at most 60", found[0])


def measure(**parts: str) -> str:
    """A `measure` value: the three parts of the template, one replaced at a time."""
    values = {"load": "1.25", "memory": "5200MB", "time": "2026-11-16T14:13+01:00", **parts}
    return " ".join(f"{key}={value}" for key, value in values.items())


class Measure(unittest.TestCase):
    def test_a2_227_time_in_iso_8601_with_its_offset_passes(self) -> None:
        """#227 A2: an offset, a `Z`, with or without seconds."""
        for value in ("2026-11-16T14:13+01:00", "2026-11-16T13:13:07Z", "2026-11-16T08:13-05:00"):
            with self.subTest(time=value):
                self.assertEqual(deviations(billet(measure=measure(time=value)), "billet"), [])

    def test_a2_227_time_without_its_offset_is_refused(self) -> None:
        """#227 A2: the second trial wrote `13:12` in UTC while the other session wrote CET."""
        for value in ("13:12", "2026-11-16T14:13", "2026-11-16 14:13+01:00", "14h13", "2026-11-16T14:13+0100"):
            with self.subTest(time=value):
                found = deviations(billet(measure=measure(time=value)), "billet")
                self.assertEqual(len(found), 1, found)
                self.assertIn(f"`time={value}`", found[0])
                self.assertIn("ISO 8601 with its offset", found[0])

    def test_a2_227_an_impossible_date_is_refused(self) -> None:
        """#227 A2: a well-shaped time that is no instant (month 13)."""
        found = deviations(billet(measure=measure(time="2026-13-16T14:13+01:00")), "billet")
        self.assertEqual(len(found), 1, found)
        self.assertIn("ISO 8601 with its offset", found[0])

    def test_a2_227_a_measure_in_prose_names_what_it_lacks(self) -> None:
        """#227 trial 1: `mesure` written in prose, with a decimal comma, instead of the three parts."""
        found = deviations(billet(measure="load is 1,25, memory fine, since 14h"), "billet")
        self.assertTrue(any("`measure` must be `load=" in line for line in found), found)


if __name__ == "__main__":
    unittest.main()
