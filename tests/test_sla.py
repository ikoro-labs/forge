"""sla.py : la clé `sla`, les échéances, les dépassements et le tri de la file (ticket #60)."""

import unittest
from datetime import datetime, timedelta, timezone

import support  # noqa: F401  met les hooks sur le chemin d'import

import sla

OPENED = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
LINES = ["sev1 | 4 h | 24 h | 3 j", "sev2 | 2 j | 7 j | 14 j", "sev3 | 7 j | 30 j | 60 j"]


class Key(unittest.TestCase):
    def test_a_line_gives_one_delay_per_stage(self) -> None:
        """Ticket #60, critère 2 : la clé `sla` donne trois délais par gravité, en heures ou en jours."""
        rules, errors = sla.parse(LINES)
        self.assertEqual(errors, [])
        first = rules["sev1"]
        self.assertEqual((first.take, first.merge, first.publish), (timedelta(hours=4), timedelta(hours=24), timedelta(days=3)))

    def test_a_malformed_key_is_reported_never_completed(self) -> None:
        for line, word in (
            ("sev1 | 4 h | 24 h", "attendu"),
            ("sev9 | 4 h | 24 h | 3 j", "sev9"),
            ("sev1 | 4 | 24 h | 3 j", "4"),
            ("sev1 | 0 h | 24 h | 3 j", "0 h"),
            ("sev1 | 4 h | 24 h | 3 j", "répétée"),
        ):
            values = [LINES[0], line] if word == "répétée" else [line]
            _, errors = sla.parse(values)
            self.assertEqual(len(errors), 1, line)
            self.assertIn(word, errors[0])

    def test_deadlines_count_from_the_opening_of_the_ticket(self) -> None:
        """Ticket #60 : l'échéance de chaque étape est l'ouverture du ticket plus son délai."""
        rule = sla.parse(LINES)[0]["sev1"]
        self.assertEqual(
            sla.deadlines(rule, OPENED),
            {
                "prise en charge": OPENED + timedelta(hours=4),
                "correctif fusionné": OPENED + timedelta(hours=24),
                "correctif publié": OPENED + timedelta(days=3),
            },
        )

    def test_the_severity_is_read_from_the_labels(self) -> None:
        self.assertEqual(sla.severity_of({"bug", "sev2"}), "sev2")
        self.assertEqual(sla.severity_of({"sev3", "sev1"}), "sev1")
        self.assertIsNone(sla.severity_of({"bug"}))


if __name__ == "__main__":
    unittest.main()
