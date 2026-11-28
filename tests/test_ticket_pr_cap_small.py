"""Ticket #381: a ticket's PR cap leaves out the small PRs (`ticket-pr-cap-small`), gh simulated.

- A1: the guard key `ticket-pr-cap-small : <lines>`; `guard_pr_cap` does not count a PR whose diff changes
  fewer lines (additions plus deletions, `gh pr list --json additions,deletions`); key absent: every PR
  counts, no default;
- A2: `templates/usine.md` documents the key, and a cap of 6 while tickets are not sized at the cut, 3 once
  they are;
- A3: the ticket cut of `forge:feature-design` estimates each ticket's size and cuts one over 1,000 readable
  lines into parts (`Refs #n`);
- A4: this repository's `usine-gardes.md` sets `ticket-pr-cap : 6` and `ticket-pr-cap-small : 50`.

The seam is `guard_pr_cap.refusal` with `gh` answered from lists (the network is the boundary), as in
`test_guard_pr_cap.py`; the other criteria read the files they name.
"""

from __future__ import annotations

import re
import unittest
from collections.abc import Sequence

import support
from test_guard_pr_cap import SINCE, USINE, FakeGh, Project, pr_body
from usine import SENSITIVE_KEYS, parse

SMALL = "- `ticket-pr-cap-small` : `50`\n"
TEMPLATE = support.PLUGIN / "templates" / "usine.md"


def sized(prs: Sequence[tuple[str, str]], sizes: Sequence[tuple[object, object]], **kwargs: Sequence[str | None]) -> FakeGh:
    """gh lists `prs` with their `(additions, deletions)`; None leaves a field out."""
    return FakeGh(prs, sizes=sizes, **kwargs)  # type: ignore[arg-type]


def listed(*sizes: tuple[object, object], ticket: int = 5) -> FakeGh:
    """gh lists one merged PR per `(additions, deletions)`, each citing `ticket`."""
    return sized([("MERGED", pr_body(f"Refs #{ticket}")) for _ in sizes], sizes)


class SmallPrsAreNotCounted(unittest.TestCase):
    """A1: a PR whose diff changes fewer lines than the key is left out of the count."""

    def test_a1_small_prs_leave_the_count(self) -> None:
        """Ticket #381, A1: two PRs of 49 lines do not fill a cap of 3; the same PRs counted fill it."""
        project = Project(self, USINE + SMALL)
        gh = listed((30, 19), (10, 0), (200, 40), (300, 10))
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))
        full = listed((30, 19), (200, 40), (300, 10), (60, 60))
        self.assertIn("#5 already has 3 PRs", project.create(pr_body("Closes #5"), full) or "")

    def test_a1_the_key_is_a_strict_threshold_on_additions_plus_deletions(self) -> None:
        """Ticket #381, A1: 49 lines is small, 50 is not; the sum of additions and deletions is the size."""
        project = Project(self, USINE + SMALL)
        self.assertIsNone(project.create(pr_body("Closes #5"), listed((49, 0), (0, 49), (25, 24), (25, 24))))
        for size in ((50, 0), (0, 50), (25, 25)):
            with self.subTest(size=size):
                gh = listed(size, size, size)
                self.assertIn("#5 already has 3 PRs", project.create(pr_body("Closes #5"), gh) or "")

    def test_a1_the_size_is_read_in_the_one_listing(self) -> None:
        """Ticket #381, A1: `additions` and `deletions` are fields of the `gh pr list --json` call the guard already makes."""
        project = Project(self, USINE + SMALL)
        gh = listed((1, 1))
        project.create(pr_body("Closes #5"), gh)
        calls = gh.asked("pr", "list")
        self.assertEqual(len(calls), 1)
        fields = calls[0][calls[0].index("--json") + 1].split(",")
        self.assertIn("additions", fields)
        self.assertIn("deletions", fields)

    def test_a1_without_the_key_every_pr_counts_and_no_size_is_asked(self) -> None:
        """Ticket #381, A1: key absent, no default threshold: three one-line PRs fill the cap, and gh is not asked for sizes."""
        project = Project(self, USINE)
        gh = listed((1, 0), (1, 0), (1, 0))
        self.assertIn("#5 already has 3 PRs", project.create(pr_body("Closes #5"), gh) or "")
        call = gh.asked("pr", "list")[0]
        self.assertNotIn("additions", call[call.index("--json") + 1])

    def test_a1_a_size_it_cannot_read_fails_closed(self) -> None:
        """Ticket #381, A1: a counted PR whose additions or deletions are missing or not whole numbers refuses the PR."""
        project = Project(self, USINE + SMALL)
        for size in ((None, 3), (3, None), ("3", 3), (True, 3), (-1, 3), (1.5, 3)):
            with self.subTest(size=size):
                reason = project.create(pr_body("Closes #5"), listed(size)) or ""
                self.assertIn("cannot be counted", reason)

    def test_a1_a_value_that_is_not_one_whole_number_refuses_every_pr_that_cites_a_ticket(self) -> None:
        """Ticket #381, A1: `fifty`, 0, a decimal, an empty value or a repeated key refuse as a precaution, naming the key."""
        for value in ("`fifty`", "`0`", "`5.5`", "``", "`-3`"):
            with self.subTest(value=value):
                project = Project(self, USINE + f"- `ticket-pr-cap-small` : {value}\n")
                self.assertIn("`ticket-pr-cap-small`", project.create(pr_body("Closes #5"), listed()) or "")
        repeated = Project(self, USINE + SMALL + "- `ticket-pr-cap-small` : `60`\n")
        self.assertIn("`ticket-pr-cap-small`", repeated.create(pr_body("Closes #5"), listed()) or "")
        project = Project(self, USINE + "- `ticket-pr-cap-small` : `fifty`\n")
        self.assertIsNone(project.create(pr_body("Closes the thing"), listed()))

    def test_a1_without_the_cap_the_key_is_not_read(self) -> None:
        """Ticket #381, A1: `ticket-pr-cap` absent is sans objet whatever the small key says: gh is not called."""
        project = Project(self, "- `ticket-pr-cap-small` : `fifty`\n")
        gh = listed((1, 1))
        self.assertIsNone(project.create(pr_body("Closes #5"), gh))
        self.assertEqual(gh.calls, [])

    def test_a1_a_small_pr_before_the_day_does_not_start_the_ticket(self) -> None:
        """Ticket #381, A1: a small PR created before `ticket-pr-cap-since` is left out and starts no ticket (no cap of 1)."""
        project = Project(self, USINE + SINCE + SMALL)
        old, new = "2026-11-20T08:00:00Z", "2026-11-24T08:00:00Z"
        small_old = sized([("MERGED", pr_body("Refs #5"))] * 2, [(3, 4), (300, 4)], created=[old, new])
        self.assertIsNone(project.create(pr_body("Closes #5"), small_old))
        big_old = sized([("MERGED", pr_body("Refs #5"))] * 2, [(300, 4), (300, 4)], created=[old, new])
        self.assertIn("for a cap of 1", project.create(pr_body("Closes #5"), big_old) or "")

    def test_a1_a_big_open_or_merged_pr_counts_as_before(self) -> None:
        """Ticket #381, A1: the key changes nothing for a PR it does not leave out: open and merged big PRs still count."""
        project = Project(self, USINE + SMALL)
        gh = sized(
            [("OPEN", pr_body("Refs #5")), ("MERGED", pr_body("Refs #5")), ("MERGED", pr_body("Refs #5"))],
            [(100, 0), (100, 0), (100, 0)],
        )
        self.assertIn("#5 already has 3 PRs", project.create(pr_body("Closes #5"), gh) or "")

    def test_a1_the_key_is_a_guard_key(self) -> None:
        """Ticket #381, A1: a key that loosens the cap is read in `usine-gardes.md` as `origin/main` holds it, like the cap."""
        self.assertIn("ticket-pr-cap-small", SENSITIVE_KEYS)


class TheTemplateDocumentsTheKey(unittest.TestCase):
    """A2: the template says the key, its absent case, and the cap of 6 then 3."""

    def text(self) -> str:
        return " ".join(TEMPLATE.read_text(encoding="utf-8").split())

    def test_a2_the_template_carries_the_key_line_and_its_absent_case(self) -> None:
        """Ticket #381, A2: a `ticket-pr-cap-small` line, its strict threshold, its sans objet and no default."""
        text = self.text()
        self.assertIn("- `ticket-pr-cap-small` : `<50>`", text)
        block = text.split("- `ticket-pr-cap-exempt` :", 1)[0].split("- `ticket-pr-cap-since` :", 1)[1]
        for phrase in (
            "additions",
            "sans objet (clé `ticket-pr-cap-small` absente)",
            "aucune valeur par défaut",
            "moins de lignes",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, block)

    def test_a2_the_template_gives_the_cap_of_6_then_3(self) -> None:
        """Ticket #381, A2: where the cap is explained, `6` while tickets are not sized at the cut, `3` once they are."""
        text = self.text()
        block = text.split("- `ticket-pr-cap` : `<3>`", 1)[0].rsplit("Le plafond de PR par ticket", 1)[1]
        self.assertIn("`6` tant que les tickets ne sont pas dimensionnés à la découpe", block)
        self.assertIn("`3` une fois qu'ils le sont", block)

    def test_a2_the_section_of_the_guard_keys_counts_24_and_names_the_key(self) -> None:
        """Ticket #381, A2: the key joins the guard keys, so the section that lists them counts and names it."""
        text = self.text()
        section = text.split("## Clés protégées", 1)[1].split("- Le chemin", 1)[0]
        self.assertIn("Vingt-quatre clés", section)
        self.assertIn("`ticket-pr-cap-small`", section)

    def test_a2_the_installation_page_describes_the_key(self) -> None:
        """Ticket #381, A2: the page that treats the cap says the small PRs, the fields read and the absent key."""
        page = " ".join((support.REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8").split())
        block = page.split("- **Small PRs.**", 1)[1].split("- **A ticket started before that day.**", 1)[0]
        for phrase in ("`ticket-pr-cap-small`", "`additions`", "`deletions`", "sans objet (clé `ticket-pr-cap-small` absente)"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, block)


class TheTicketCutSizesTheTickets(unittest.TestCase):
    """A3: `forge:feature-design` estimates each ticket's size at the cut."""

    def skill(self) -> str:
        return (support.PLUGIN / "skills" / "feature-design" / "SKILL.md").read_text(encoding="utf-8")

    def size_rule(self) -> str:
        cut = " ".join(self.skill().split("6. **Découper**", 1)[1].split("**The budget.**", 1)[0].split())
        self.assertIn("**La taille.**", cut)
        return cut.split("**La taille.**", 1)[1].split("- **", 1)[0]

    def test_a3_the_cut_estimates_the_size_and_cuts_over_1000_lines_into_parts(self) -> None:
        """Ticket #381, A3: each ticket's size is estimated; one over 1 000 readable lines is cut into parts (`Refs #n`)."""
        rule = self.size_rule()
        for phrase in ("estime la taille", "plus de 1 000 lignes lisibles", "parties", "`Refs #n`"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rule)

    def test_a3_tickets_not_started_are_recut_and_those_in_flight_keep_the_rules(self) -> None:
        """Ticket #381, A3: a ticket not started is re-cut to this rule; one in flight keeps the rules it began with."""
        rule = self.size_rule()
        for phrase in ("pas commencés", "redécoupés", "en cours", "gardent les règles"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, rule)

    def test_a3_the_text_has_no_em_dash(self) -> None:
        """Ticket #381, A3: French prose of the plugin, no em dash."""
        self.assertNotIn(chr(0x2014), self.skill())


class ThisRepositorySetsTheCap(unittest.TestCase):
    """A4: `docs/agents/usine-gardes.md` sets the cap of 6 and the small threshold of 50."""

    def test_a4_the_guard_file_sets_6_and_50_once_each(self) -> None:
        """Ticket #381, A4: `ticket-pr-cap : 6` and `ticket-pr-cap-small : 50`, each declared once."""
        text = (support.REPO_ROOT / "docs" / "agents" / "usine-gardes.md").read_text(encoding="utf-8")
        config = parse(text)
        self.assertEqual(config["ticket-pr-cap"], ["6"])
        self.assertEqual(config["ticket-pr-cap-small"], ["50"])
        self.assertEqual(len(re.findall(r"^- `ticket-pr-cap-small` :", text, re.MULTILINE)), 1)
