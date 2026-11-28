"""F-0003 A47 to A50, A57, A59 (ikoro-labs/forge#406): a short agent leads one ticket with
`forge:feature-build F-NNNN --ticket <n>`, asks its question in the G5 format, and gets the ticket back
as ready once a default decision answers it.

`gh` is simulated, every test runs under an isolated HOME and USERPROFILE and without the CLAUDE_ variables
of the session running the tests, and nothing is written in the real ~/.claude.
"""

import unittest

from test_question_delay import STAFF, Gh, Project, issue, labeled, waiting


class ReadyAgain(unittest.TestCase):
    """A59: a `post-default` on a ticket puts `ready-for-agent` back."""

    def test_a_default_decision_on_a_ticket_that_waited_gives_ready_for_agent_back(self) -> None:
        """F-0003 A59: the ticket loses `needs-info` and regains `ready-for-agent`, with the decision comment."""
        project = Project(self)
        gh = waiting(["needs-info"], 30)
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertTrue(gh.bodies()[0].startswith("Décision (staff-engineer, P1) par défaut"))
        self.assertEqual(gh.removed(), ["needs-info"])
        self.assertEqual(gh.added(), ["labels[]=ready-for-agent"])

    def test_a_ticket_that_waited_on_a_human_gesture_label_is_ready_again_too(self) -> None:
        """F-0003 A59: `ready-for-human`, which the skill also sets on a ticket, is answered the same way."""
        project = Project(self)
        gh = waiting(["ready-for-human"], 30)
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.removed(), ["ready-for-human"])
        self.assertEqual(gh.added(), ["labels[]=ready-for-agent"])

    def test_a_pull_request_never_gets_the_ready_label(self) -> None:
        """F-0003 A59: the label is for a ticket (an issue); a pull request that waited keeps only its removal."""
        project = Project(self)
        gh = waiting(["needs-info"], 30, pull_request=True)
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.added(), [])

    def test_a_ticket_already_ready_is_not_labeled_twice(self) -> None:
        """F-0003 A59: a ticket that already carries `ready-for-agent` is left as it is."""
        project = Project(self)
        gh = Gh({12: issue(12, ["needs-info", "ready-for-agent"])}, {12: [labeled("needs-info", 30)]})
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.added(), [])

    def test_a_reminder_gives_no_ready_label(self) -> None:
        """F-0003 A59: a verdict that is not a default decision leaves the ticket with the human."""
        project = Project(self)
        gh = waiting(["needs-info"], 30)
        code, out = project.route(gh, "VERDICT: RESERVED\nDECISION: a human\nMATRIX_CELL: H1\nGROUND: x\n", "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.added(), ["labels[]=needs-your-attention"])

    def test_the_plan_without_apply_says_the_label_and_writes_nothing(self) -> None:
        """F-0003 A59: the printed plan lists `ready-for-agent` among the labels to add; `gh` gets no write."""
        project = Project(self)
        gh = waiting(["needs-info"], 30)
        code, out = project.route(gh, STAFF, "--json")
        self.assertEqual(code, 0, out)
        self.assertIn('"ready-for-agent"', out)
        self.assertEqual(gh.writes, [])


if __name__ == "__main__":
    unittest.main()
