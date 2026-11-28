"""F-0003 A11 (ticket #401, part a): a `gh` group the lists of verbs do not name is closed by default.

`gh secret set`, `gh variable set`, `gh ssh-key add`, `gh gpg-key add` and `gh codespace create` write on
GitHub under the human's token like a `gh pr create`; the identity check must ask for them, and keep
passing the readings of the same groups. Judged by `refusal` with an `identity` reader injected, as in
`test_guard_git_identity.py`.
"""

import unittest
from importlib import import_module

import support  # noqa: F401  met les hooks sur le chemin d'import
from guard_git import GH_GROUPS, GH_READ_VERBS, GH_WRITE_VERBS, refusal

CLOSED = "no installation token"


class Asked:
    """An `identity` reader that notes the gestures it is asked about, and answers `answer`."""

    def __init__(self, answer: str | None) -> None:
        self.answer = answer
        self.gestures: list[str] = []

    def __call__(self, gesture: str) -> str | None:
        self.gestures.append(gesture)
        return self.answer


def never_write() -> dict[str, str]:
    """`GH_NEVER_WRITE`, read by name so that a test, not the whole file, fails when it is absent."""
    return getattr(import_module("guard_git"), "GH_NEVER_WRITE", {})


def judged(command: str, identity: Asked) -> str | None:
    return refusal(command, "feat/x", lambda *_target: True, merge_method=["merge"], identity=identity)


UNLISTED_WRITES = (
    "gh secret set X",
    "gh secret delete X",
    "gh variable set X",
    "gh variable delete X",
    "gh ssh-key add k.pub",
    "gh ssh-key delete 1",
    "gh gpg-key add k",
    "gh gpg-key delete 1",
    "gh codespace create",
    "gh cs delete",
    "gh codespace edit",
    "gh codespace rebuild",
    "gh codespace stop",
    "gh agent-task create fix it",
    "gh discussion create -t t",
    "gh discussion comment 3 -b x",
    "gh discussion edit 3",
    "gh skill publish",
    "gh -R o/r secret set X",
    "gh some-extension-command run",
)
# Per group: a reading that keeps passing, and a write of the same group that is asked for.
UNLISTED_READS = (
    ("gh secret list", "gh secret set X"),
    ("gh variable list", "gh variable set X"),
    ("gh variable get X", "gh variable delete X"),
    ("gh ssh-key list", "gh ssh-key add k.pub"),
    ("gh gpg-key list", "gh gpg-key add k"),
    ("gh codespace list", "gh codespace create"),
    ("gh cs view", "gh cs delete"),
    ("gh codespace logs", "gh codespace stop"),
    ("gh agent-task list", "gh agent-task create x"),
    ("gh agent-task view 3", "gh agent-task create x"),
    ("gh discussion list", "gh discussion create -t t"),
    ("gh discussion view 3", "gh discussion comment 3 -b x"),
    ("gh skill list", "gh skill publish"),
    ("gh skill search x", "gh skill publish"),
    ("gh skill preview o/r x", "gh skill publish"),
)
NEVER_WRITING = (
    "gh help pr",
    "gh completion -s bash",
    "gh config set editor vim",
    "gh alias set co 'pr checkout'",
    "gh auth login",
    "gh auth refresh",
    "gh auth switch",
    "gh browse",
    "gh search issues x",
    "gh status",
    "gh licenses",
    "gh extension install o/gh-x",
    "gh ext upgrade --all",
    "gh preview prompter",
    "gh org list",
    "gh ruleset list",
    "gh rs view 3",
    "gh ruleset check main",
    "gh attestation verify a.tgz --owner o",
    "gh attestation download a.tgz --owner o",
    "gh attestation trusted-root",
)


class AGroupOfGhTheListsDoNotNameIsClosedByDefault(unittest.TestCase):
    def test_a11_a_write_of_a_group_no_list_names_asks_the_reader_and_is_refused(self) -> None:
        """F-0003 A11: `gh secret set`, `gh ssh-key add`, `gh codespace create`... write under the human's token."""
        for command in UNLISTED_WRITES:
            with self.subTest(command=command):
                asked = Asked(CLOSED)
                self.assertEqual(judged(command, asked), CLOSED)
                self.assertEqual(len(asked.gestures), 1)

    def test_a11_the_gesture_of_such_a_write_is_named_as_the_agent_typed_it(self) -> None:
        """F-0003 A11: the refusal names the group and the verb, behind a `-R`."""
        asked = Asked(CLOSED)
        judged("gh -R o/r ssh-key add k.pub", asked)
        self.assertEqual(asked.gestures, ["gh ssh-key add"])

    def test_a11_a_reading_of_those_groups_never_asks_the_reader_and_the_write_beside_it_does(self) -> None:
        """F-0003 A11: a list, a view, a get write nothing and keep passing; a write of the group is asked."""
        for reading, writing in UNLISTED_READS:
            with self.subTest(reading=reading, writing=writing):
                asked = Asked(CLOSED)
                self.assertIsNone(judged(reading, asked))
                self.assertEqual(asked.gestures, [])
                self.assertEqual(judged(writing, asked), CLOSED)

    def test_a11_a_group_that_never_writes_on_github_is_named_so_and_never_asks_the_reader(self) -> None:
        """F-0003 A11: help, config, alias, auth, browse, search, extension, attestation... act here or read."""
        for command in NEVER_WRITING:
            with self.subTest(command=command):
                asked = Asked(CLOSED)
                self.assertIn(command.split()[1], never_write())
                self.assertIsNone(judged(command, asked))
                self.assertEqual(asked.gestures, [])

    def test_a11_every_group_gh_runs_itself_is_named_in_exactly_one_place(self) -> None:
        """F-0003 A11: a group added to `GH_GROUPS` without a decision is a hole the check cannot see."""
        never = never_write()
        for group in sorted(GH_GROUPS - {"api"}):
            places = [
                name
                for name, table in (
                    ("read", GH_READ_VERBS),
                    ("write", GH_WRITE_VERBS),
                    ("never", never),
                )
                if group in table
            ]
            with self.subTest(group=group):
                self.assertEqual(len(places), 1, places)

    def test_a11_each_group_that_never_writes_says_why(self) -> None:
        """F-0003 A11: the reason is written beside the group, not guessed later."""
        never = never_write()
        self.assertTrue(never)
        for group, reason in never.items():
            with self.subTest(group=group):
                self.assertTrue(reason.strip())
