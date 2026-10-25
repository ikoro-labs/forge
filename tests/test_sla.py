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


def ticket(number: int, labels: tuple[str, ...], opened: datetime = OPENED) -> sla.Ticket:
    return sla.Ticket(number, set(labels), opened)


class Queue(unittest.TestCase):
    def numbers(self, tickets: list[sla.Ticket], lines: list[str] | None = LINES) -> list[int]:
        rules = sla.parse(lines)[0] if lines is not None else {}
        return [item.number for item in sla.order(tickets, rules)]

    def test_sev1_goes_before_every_ticket_not_yet_handed(self) -> None:
        """Ticket #60, critère 3 : un sev1 passe devant tout ticket, la gravité avant l'ordre des sous-issues."""
        tickets = [ticket(1, ("sev3",)), ticket(2, ()), ticket(3, ("sev2",)), ticket(4, ("sev1",))]
        self.assertEqual(self.numbers(tickets), [4, 3, 1, 2])

    def test_same_severity_goes_by_the_nearest_deadline(self) -> None:
        """Ticket #60, critère 3 : à gravité égale, l'échéance de prise en charge la plus proche passe d'abord."""
        late = ticket(5, ("sev2",), OPENED)
        early = ticket(6, ("sev2",), OPENED - timedelta(days=1))
        self.assertEqual(self.numbers([late, early]), [6, 5])

    def test_a_shorter_delay_of_a_class_does_not_outrank_a_higher_class(self) -> None:
        rules = ["sev1 | 9 j | 9 j | 9 j", "sev2 | 1 h | 2 h | 3 h"]
        tickets = [ticket(7, ("sev2",), OPENED - timedelta(days=5)), ticket(8, ("sev1",))]
        self.assertEqual(self.numbers(tickets, rules), [8, 7])

    def test_without_the_key_severity_still_sorts_and_the_deadline_is_sans_objet(self) -> None:
        """Ticket #60 : clé absente, aucune échéance devinée ; l'ordre des sous-issues départage."""
        tickets = [ticket(9, ("sev2",), OPENED), ticket(10, ("sev2",), OPENED - timedelta(days=3)), ticket(11, ("sev1",))]
        self.assertEqual(self.numbers(tickets, None), [11, 9, 10])
        self.assertEqual(sla.take_deadline(tickets[1], {}), None)

    def test_a_class_without_a_line_has_no_deadline_and_keeps_the_given_order(self) -> None:
        tickets = [ticket(13, ("sev2",)), ticket(12, ("sev2",), OPENED - timedelta(days=9))]
        self.assertEqual(self.numbers(tickets, ["sev2 | 2 j | 7 j | 14 j"]), [12, 13])
        self.assertEqual(self.numbers(tickets, ["sev1 | 2 j | 7 j | 14 j"]), [13, 12])


class Assess(unittest.TestCase):
    rule = sla.parse(LINES)[0]["sev1"]

    def states(self, reached: dict, now: datetime, closed: bool = False) -> list[str]:
        return [stage.state for stage in sla.assess(self.rule, OPENED, reached, now, closed)]

    def test_a_stage_reached_before_its_deadline_is_tenue_and_after_it_depassee(self) -> None:
        """Ticket #60, critère 4 : un dépassement est une étape atteinte après son échéance."""
        reached = {
            "prise en charge": OPENED + timedelta(hours=3),
            "correctif fusionné": OPENED + timedelta(hours=25),
            "correctif publié": OPENED + timedelta(days=3),
        }
        self.assertEqual(self.states(reached, OPENED + timedelta(days=9)), ["tenue", "dépassée", "tenue"])

    def test_a_stage_not_reached_is_depassee_once_its_deadline_has_passed(self) -> None:
        """Ticket #60, critère 4 : une échéance passée sans que l'étape soit atteinte est un dépassement."""
        self.assertEqual(self.states({}, OPENED + timedelta(hours=5)), ["dépassée", "en cours", "en cours"])
        self.assertEqual(self.states({}, OPENED + timedelta(days=4)), ["dépassée", "dépassée", "dépassée"])

    def test_the_deadline_itself_is_still_held(self) -> None:
        reached = {"prise en charge": OPENED + timedelta(hours=4)}
        self.assertEqual(self.states(reached, OPENED + timedelta(hours=4))[0], "tenue")

    def test_a_closed_ticket_without_a_stage_is_sans_objet_for_it(self) -> None:
        self.assertEqual(self.states({"prise en charge": OPENED}, OPENED + timedelta(days=9), closed=True), ["tenue", "sans objet", "sans objet"])

    def test_breaches_keep_only_the_late_stages(self) -> None:
        results = sla.assess(self.rule, OPENED, {}, OPENED + timedelta(hours=30))
        self.assertEqual([stage.stage for stage in sla.breaches(results)], ["prise en charge", "correctif fusionné"])


if __name__ == "__main__":
    unittest.main()
