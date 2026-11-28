"""Ticket #377 : un ticket qui accélère l'usine passe devant la file, après `sev1` et avant tout autre."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import support  # noqa: F401  met les hooks sur le chemin d'import
from factory_slo import main
from sla import Ticket, order, parse
from test_factory_slo import USINE, World, isolate
from test_factory_slo_sla import ticket as issue_view
from test_usine_keys_classified import FREE_KEYS
from usine import SENSITIVE_KEYS

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
OPENED = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
LINES = ["sev1 | 4 h | 24 h | 3 j", "sev2 | 2 j | 7 j | 14 j", "sev3 | 7 j | 30 j | 60 j"]
LABEL = "factory-speed"


def ticket(number: int, labels: tuple[str, ...], opened: datetime = OPENED) -> Ticket:
    return Ticket(number, set(labels), opened)


class Order(unittest.TestCase):
    def numbers(self, tickets: list[Ticket], label: str | None = LABEL, lines: list[str] | None = LINES) -> list[int]:
        rules = parse(lines)[0] if lines is not None else {}
        return [item.number for item in order(tickets, rules, label)]

    def test_a_speed_ticket_goes_after_sev1_and_before_every_other_ticket(self) -> None:
        """Ticket #377, A2 : `sev1`, puis le ticket de vitesse, puis `sev2`, `sev3` et les tickets sans classe."""
        tickets = [ticket(1, ("sev3",)), ticket(2, ()), ticket(3, ("sev2",)), ticket(4, ("sev1",)), ticket(5, (LABEL,))]
        self.assertEqual(self.numbers(tickets), [4, 5, 3, 1, 2])


class Queue(unittest.TestCase):
    """`factory_slo.py queue` sur un dépôt d'essai : la clé `speed-label` de `usine.md` désigne l'étiquette."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "vide"))
        self.world = World(Path(self.tmp.name))
        self.world.answers = {
            "issue view 1 ": issue_view(1, "2026-10-01T00:00:00Z", ("sev3",)),
            "issue view 2 ": issue_view(2, "2026-10-02T00:00:00Z"),
            "issue view 3 ": issue_view(3, "2026-10-03T00:00:00Z", ("sev2",)),
            "issue view 4 ": issue_view(4, "2026-10-19T00:00:00Z", ("sev1",)),
            "issue view 5 ": issue_view(5, "2026-10-20T00:00:00Z", (LABEL,)),
        }

    def configure(self, extra: str) -> None:
        (self.world.root / "docs" / "agents" / "usine.md").write_text(USINE + extra, encoding="utf-8")

    def run_main(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["queue", str(self.world.root), *args], run=self.world.runner, now=NOW)
        return code, out.getvalue(), err.getvalue()

    def test_the_queue_ranks_the_labelled_ticket_after_sev1_and_before_the_rest(self) -> None:
        """Ticket #377, A2 : la commande `queue` rend `sev1`, le ticket de vitesse, puis tous les autres."""
        self.configure(f"- `speed-label` : `{LABEL}`\n")
        code, out, _ = self.run_main("1", "2", "3", "4", "5", "--json")
        self.assertEqual(code, 0)
        self.assertEqual([row["ticket"] for row in json.loads(out)["file"]], [4, 5, 3, 1, 2])
        _, text, _ = self.run_main("1", "2", "3", "4", "5")
        self.assertIn(f"#5 : sans gravité, étiquette {LABEL}", text)

    def test_without_the_key_the_order_is_unchanged_and_the_priority_is_sans_objet(self) -> None:
        """Ticket #377, A1 : clé absente, « sans objet (clé `speed-label` absente) », l'étiquette ne change rien."""
        self.configure("")
        _, out, _ = self.run_main("1", "2", "3", "4", "5", "--json")
        document = json.loads(out)
        self.assertEqual([row["ticket"] for row in document["file"]], [4, 3, 1, 2, 5])
        self.assertIn("sans objet (clé `speed-label` absente)", document["vitesse"])
        _, text, _ = self.run_main("1", "2")
        self.assertIn("sans objet (clé `speed-label` absente)", text)

    def test_a_repeated_key_fails_the_command(self) -> None:
        """Ticket #377, A1 : deux lignes de la clé ne se devinent pas, la commande s'arrête."""
        self.configure(f"- `speed-label` : `{LABEL}`\n- `speed-label` : `autre`\n")
        code, _, err = self.run_main("1")
        self.assertEqual(code, 1)
        self.assertIn("`speed-label`", err)


class Declaration(unittest.TestCase):
    def test_the_template_documents_the_key_and_says_absent_is_sans_objet(self) -> None:
        """Ticket #377, A1 : le gabarit porte la ligne de la clé `speed-label` et sa règle de clé absente."""
        text = " ".join((support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8").split())
        self.assertIn("- `speed-label` : `<", text)
        self.assertIn("sans objet (clé `speed-label` absente)", text)
        self.assertIn("après `sev1` et avant tout autre", text)

    def test_the_key_is_free_not_a_guard_key(self) -> None:
        """Ticket #377, A1 : l'étiquette ne borne aucun pouvoir de l'agent, elle se règle dans `usine.md`.

        Rouge sur la base : la clé n'y est pas encore rangée parmi les clés libres.
        """
        self.assertIn("speed-label", FREE_KEYS)
        self.assertNotIn("speed-label", SENSITIVE_KEYS)

    def test_this_repository_declares_the_key(self) -> None:
        """Ticket #377, A4 : `docs/agents/usine.md` déclare l'étiquette de vitesse de l'usine."""
        self.assertEqual(support.repo_usine().get("speed-label"), [LABEL])


def prose(*parts: str) -> str:
    """A file of the repository on one line, so a sentence wrapped by the editor still matches."""
    return " ".join(support.REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8").split())


class Skills(unittest.TestCase):
    def test_the_skills_that_open_a_ticket_add_the_label_for_a_lead_time_goal(self) -> None:
        """Ticket #377, A3 : `feature-build`, `qc` et `incident` posent l'étiquette de la clé quand le but du ticket est le délai de l'usine."""
        for skill in ("feature-build", "qc", "incident"):
            with self.subTest(skill=skill):
                text = prose("plugins", "forge", "skills", skill, "SKILL.md")
                self.assertRegex(
                    text,
                    r"(label of the key `speed-label`|étiquette de la clé `speed-label`)[^|]{0,200}\(`--label`\)"
                    r"|`speed-label` \(`--label`\)",
                )
                self.assertRegex(text, r"délai de l'usine elle-même|lead time of the factory itself")
                self.assertIn("sans objet (clé `speed-label` absente)", text)
                self.assertRegex(text, r"ne la crée pas|ne la crées pas")

    def test_the_frontier_order_names_the_speed_class(self) -> None:
        """Ticket #377, A2 : la frontière de `feature-build` se prend `sev1`, puis la vitesse, puis `sev2`."""
        text = prose("plugins", "forge", "skills", "feature-build", "SKILL.md")
        self.assertRegex(text, r"classes `sev1`, les tickets de la clé `speed-label`, `sev2`, `sev3`")

    def test_the_severity_page_says_where_the_speed_class_sits(self) -> None:
        """Ticket #377, A2 : la page de la file de `docs/gravite-et-sla.md` nomme la classe de vitesse."""
        self.assertRegex(prose("docs", "gravite-et-sla.md"), r"`sev1`, puis[^.]{0,80}`speed-label`[^.]{0,80}`sev2`")


if __name__ == "__main__":
    unittest.main()
