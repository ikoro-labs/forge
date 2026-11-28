"""F-0003 A11 (ticket #401, part a): `guard_git` holds the identity of the agents for every write on GitHub.

The first class judges the gesture of a command (`refusal` with an `identity` reader injected, as
`autonomy` is); the next ones are in `test_guard_git_identity_keys.py`, the hook played as a process.
"""

import unittest
from typing import Any

import support  # noqa: F401  met les hooks sur le chemin d'import
from guard_git import refusal

CLOSED = "no installation token"


class Asked:
    """An `identity` reader that notes the gestures it is asked about, and answers `answer`."""

    def __init__(self, answer: str | None) -> None:
        self.answer = answer
        self.gestures: list[str] = []

    def __call__(self, gesture: str) -> str | None:
        self.gestures.append(gesture)
        return self.answer


def judged(command: str, identity: Asked | None, **keys: Any) -> str | None:
    return refusal(command, "feat/x", lambda *_target: True, merge_method=["merge"], identity=identity, **keys)


WRITES = (
    "git push origin feat/x",
    "git push --force-with-lease origin feat/x",
    "git -C /tmp/work push origin HEAD:feat/x",
    "cd /work/depot && git push origin feat/x",
    "sh -c 'git push origin feat/x'",
    "gh pr create --title t --body b",
    "gh pr comment 5 --body x",
    "gh pr edit 5 --add-label x",
    "gh pr close 5",
    "gh pr review 5 --approve",
    "gh pr merge 5 --merge",
    "gh issue create -t t -b b",
    "gh issue comment 3 -b x",
    "gh issue close 3",
    "gh issue edit 3 --add-label x",
    "gh -R o/r issue comment 3 -b x",
    "GH_REPO=o/r gh issue close 3",
    "gh api -X POST repos/o/r/issues/3/comments -f body=x",
    "gh api repos/o/r/issues/3/comments -f body=x",
    "gh api -X DELETE repos/o/r/issues/3/labels/x",
    "gh api -X PUT repos/o/r/pulls/5/merge -f merge_method=merge",
    "gh api graphql -f query='mutation { addComment(input: {}) { clientMutationId } }'",
    "gh release create v1 --notes x",
    "gh label create x",
    "gh workflow run ci.yml",
    "gh run rerun 5",
)
READS = (
    "git status",
    "git fetch origin",
    "git pull",
    "git log --oneline",
    "git push --dry-run origin feat/x",
    "git push -n origin feat/x",
    "gh pr view 5",
    "gh pr list",
    "gh pr checks 5",
    "gh pr diff 5",
    "gh pr status",
    "gh pr checkout 5",
    "gh issue view 3",
    "gh issue list",
    "gh api repos/o/r/pulls/5",
    "gh api -X GET repos/o/r/issues -f state=open",
    "gh api graphql -f query='query { viewer { login } }'",
    "gh run list",
    "gh release view v1",
    "gh repo view",
    "gh auth status",
    "gh workflow list",
    "echo gh pr create",
)


class AWriteOnGithubIsJudgedForTheIdentityOfTheAgents(unittest.TestCase):
    def test_a11_every_form_of_a_write_asks_the_reader_and_is_refused_with_its_reason(self) -> None:
        """F-0003 A11: `git push`, `gh pr`, `gh issue`, `gh api` in write, behind `cd`, `-C`, `-R` or `sh -c`."""
        for command in WRITES:
            with self.subTest(command=command):
                asked = Asked(CLOSED)
                self.assertEqual(judged(command, asked), CLOSED)
                self.assertEqual(len(asked.gestures), 1)

    def test_a11_every_form_of_a_write_passes_when_the_reader_allows_it(self) -> None:
        """F-0003 A11: with an installation token the reader answers None, and no write is refused for it."""
        for command in WRITES:
            with self.subTest(command=command):
                self.assertIsNone(judged(command, Asked(None)))

    def test_a11_a_reading_never_asks_the_reader(self) -> None:
        """F-0003 A11: fetching, listing, viewing, a GET, a GraphQL query and a dry-run push write nothing."""
        for command in READS:
            with self.subTest(command=command):
                asked = Asked(CLOSED)
                self.assertIsNone(judged(command, asked))
                self.assertEqual(asked.gestures, [])

    def test_a11_the_gesture_is_named_as_the_agent_typed_it(self) -> None:
        """F-0003 A11: the reader is told which gesture, so the refusal can name it."""
        for command, gesture in (
            ("git push origin feat/x", "git push"),
            ("gh pr create --title t", "gh pr create"),
            ("gh -R o/r issue comment 3 -b x", "gh issue comment"),
            ("gh api -X POST repos/o/r/issues/3/comments -f body=x", "gh api POST repos/o/r/issues/3/comments"),
            ("gh api graphql -f query='mutation { x }'", "gh api graphql (mutation)"),
        ):
            with self.subTest(command=command):
                asked = Asked(CLOSED)
                judged(command, asked)
                self.assertEqual(asked.gestures, [gesture])

    def test_a11_a_graphql_call_the_guard_cannot_read_is_a_write(self) -> None:
        """F-0003 A11: a query fed by a variable or a pipe may hold a mutation: judged as one."""
        for command in (
            'gh api graphql -f query="$QUERY"',
            "echo '{}' | gh api graphql --input -",
        ):
            with self.subTest(command=command):
                asked = Asked(CLOSED)
                self.assertEqual(judged(command, asked), CLOSED)

    def test_a11_a_caller_that_passes_no_reader_does_not_ask_for_the_check(self) -> None:
        """F-0003 A11: like `autonomy`, `None` is the default of a caller that does not ask."""
        for command in WRITES:
            with self.subTest(command=command):
                self.assertIsNone(refusal(command, "feat/x", lambda *_target: True, merge_method=["merge"]))

    def test_a11_the_other_rules_still_hold_before_the_identity(self) -> None:
        """F-0003 A11: a push to main is refused for main, not for the identity."""
        reason = judged("git push origin main", Asked(None))
        self.assertIn("push to main", str(reason))
