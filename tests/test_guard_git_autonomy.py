"""ikoro-labs/forge#280: `guard_git` holds the key `agent-autonomy` for the merge and the `forge--v*` tag.

The key is read in `origin/main`, never in the working tree an agent can edit. Every repository here
is a temporary one, under a temporary `HOME`; none of the session's `CLAUDE_` or `GIT_` variables
reaches git, and the real `~/.claude` is never read nor written.
"""

import os
import subprocess
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import support  # noqa: F401  met les hooks sur le chemin d'import
from guard_git import RULES, autonomy_refusal, refusal
from refusal_journal import rule_of

USINE = Path("docs") / "agents" / "usine.md"
PROSE = "# Usine\n\nDu texte, puis la clé.\n\n"


def key(value: str) -> str:
    return f"- `agent-autonomy` : `{value}`\n"


def environment(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "GIT_"))}
    env.update(HOME=str(home), USERPROFILE=str(home), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    return env


def git(where: Path, home: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603, S607 - fixed argv in a temporary repository
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=where,
        env=environment(home),
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return done.stdout


@contextmanager
def project(on_main: str | None, in_tree: str | None = None) -> Iterator[Path]:
    """A repository whose `origin/main` holds `on_main` as `usine.md` (None: no file there), and
    whose working tree then holds `in_tree` (None: left as committed)."""
    with tempfile.TemporaryDirectory() as folder:
        home = Path(folder) / "home"
        where = Path(folder) / "depot"
        home.mkdir()
        where.mkdir()
        git(where, home, "init", "-q", "-b", "feat/x")
        (where / "README.md").write_text("x\n", encoding="utf-8")
        if on_main is not None:
            (where / USINE).parent.mkdir(parents=True)
            (where / USINE).write_text(on_main, encoding="utf-8")
        git(where, home, "add", "-A")
        git(where, home, "commit", "-q", "-m", "init")
        git(where, home, "update-ref", "refs/remotes/origin/main", "HEAD")
        if in_tree is not None:
            (where / USINE).parent.mkdir(parents=True, exist_ok=True)
            (where / USINE).write_text(in_tree, encoding="utf-8")
        old = {name: os.environ.get(name) for name in ("HOME", "USERPROFILE")}
        os.environ.update(HOME=str(home), USERPROFILE=str(home))
        try:
            yield where
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


class TheKeyIsReadInOriginMain(unittest.TestCase):
    def test_the_key_on_in_origin_main_opens_the_gesture(self) -> None:
        """#280: `agent-autonomy` : `on` in `origin/main`, the merge and the tag are not refused for it."""
        with project(PROSE + key("on")) as where:
            self.assertIsNone(autonomy_refusal(str(where), "merge"))
            self.assertIsNone(autonomy_refusal(str(where), "tag"))

    def test_the_key_absent_refuses_and_names_the_key_and_the_humans_gesture(self) -> None:
        """#280: no line in `origin/main`: refused, the gesture stays the human's."""
        with project(PROSE + "- `merge-method` : `merge`\n") as where:
            reason = autonomy_refusal(str(where), "merge")
        assert reason is not None
        self.assertIn("`agent-autonomy` key", reason)
        self.assertIn("not `on`", reason)
        self.assertIn("human", reason)

    def test_a_value_other_than_on_refuses_and_cites_the_line(self) -> None:
        """#280: `off`, `oui`, `On`, an empty value are not `on`."""
        for value in ("off", "oui", "true", "On", ""):
            with self.subTest(value=value), project(PROSE + key(value)) as where:
                reason = autonomy_refusal(str(where), "merge")
                assert reason is not None
                self.assertIn(f"- `agent-autonomy` : `{value}`", reason)

    def test_a_repeated_key_refuses_even_when_every_line_is_on(self) -> None:
        """#280: the key takes one line; two lines are not `on`."""
        with project(PROSE + key("on") + key("on")) as where:
            reason = autonomy_refusal(str(where), "merge")
        assert reason is not None
        self.assertIn("one line", reason)

    def test_a_key_set_only_in_the_working_tree_refuses(self) -> None:
        """#280: the agent edits the working tree; `origin/main` is what the human merged."""
        for on_main in (PROSE, PROSE + key("off"), None):
            with self.subTest(on_main=on_main), project(on_main, in_tree=PROSE + key("on")) as where:
                self.assertIsNotNone(autonomy_refusal(str(where), "merge"))
                self.assertIsNotNone(autonomy_refusal(str(where), "tag"))

    def test_a_key_removed_only_in_the_working_tree_still_opens_it(self) -> None:
        """#280: the working tree is not read at all, in either direction."""
        with project(PROSE + key("on"), in_tree=PROSE) as where:
            self.assertIsNone(autonomy_refusal(str(where), "merge"))

    def test_an_unreadable_origin_main_refuses(self) -> None:
        """#280: no `docs/agents/usine.md` on `origin/main`, no `origin/main`, no repository: refused."""
        with project(None, in_tree=PROSE + key("on")) as where:
            self.assertIsNotNone(autonomy_refusal(str(where), "merge"))
            git(where, where.parent / "home", "update-ref", "-d", "refs/remotes/origin/main")
            self.assertIsNotNone(autonomy_refusal(str(where), "merge"))
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNotNone(autonomy_refusal(folder, "merge"))
        self.assertIsNotNone(autonomy_refusal(None, "merge"))

    def test_the_reason_names_the_gesture_it_refuses(self) -> None:
        with project(PROSE) as where:
            merge = autonomy_refusal(str(where), "merge")
            tag = autonomy_refusal(str(where), "tag")
        assert merge is not None and tag is not None
        self.assertIn("merge", merge)
        self.assertIn("tag", tag)


CLOSED = "the `agent-autonomy` key is not `on` (stub)"


def always_green(*_target: str | None) -> bool:
    return True


class Asked:
    """An `autonomy` reader that says what it is asked, and answers `answer` (None: the key is `on`)."""

    def __init__(self, answer: str | None) -> None:
        self.answer = answer
        self.gestures: list[str] = []

    def __call__(self, gesture: str) -> str | None:
        self.gestures.append(gesture)
        return self.answer


def judged(command: str, autonomy: Asked | None, **keys: Any) -> str | None:
    return refusal(command, "feat/x", always_green, merge_method=["merge"], autonomy=autonomy, **keys)


MERGES = (
    "gh pr merge 5 --merge",
    "gh pr merge 5 --merge --delete-branch",
    "gh pr merge https://github.com/o/r/pull/5 --merge",
    "cd /work/depot && gh pr merge 5 --merge",
    "gh api -X PUT repos/o/r/pulls/5/merge -f merge_method=merge",
)


class TheMergeFollowsTheKey(unittest.TestCase):
    def test_every_form_of_a_merge_is_refused_when_the_key_is_not_on(self) -> None:
        """#280: `gh pr merge` and the REST merge, alone, behind `cd` or `sh -c`, refused with the key's reason."""
        for command in MERGES:
            with self.subTest(command=command):
                asked = Asked(CLOSED)
                self.assertEqual(judged(command, asked), CLOSED)
                self.assertEqual(asked.gestures, ["merge"])

    def test_every_form_of_a_merge_passes_when_the_key_is_on(self) -> None:
        """#280: with `on`, the guard's other rules apply as before and let this merge through."""
        for command in MERGES:
            with self.subTest(command=command):
                self.assertIsNone(judged(command, Asked(None)))

    def test_the_key_on_does_not_open_what_the_other_rules_refuse(self) -> None:
        """#280: `on` is not a pass: checks not green, a protected path, a wrong method still refuse."""
        red = refusal("gh pr merge 5 --merge", "feat/x", lambda *_t: False, merge_method=["merge"], autonomy=Asked(None))
        self.assertIn("checks not green", str(red))
        self.assertIn("merge-method", str(judged("gh pr merge 5 --squash", Asked(None))))
        held = judged("gh pr merge 5 --merge", Asked(None), protected_paths=["a/"], changed_files=lambda *_t: ["a/b"])
        self.assertIn("protected-path", str(held))

    def test_a_merge_behind_a_shell_or_beside_another_command_stays_refused_either_way(self) -> None:
        """#280: not run alone, it is refused for that, key `on` or not; the key never opens it."""
        for command in ("gh pr merge 5 --merge && ls", "sh -c 'gh pr merge 5 --merge'"):
            for answer in (CLOSED, None):
                with self.subTest(command=command, answer=answer):
                    self.assertIsNotNone(judged(command, Asked(answer)))

    def test_cancelling_an_auto_merge_merges_nothing_and_reads_no_key(self) -> None:
        """#280: `--disable-auto` alone is not a merge."""
        asked = Asked(CLOSED)
        self.assertIsNone(judged("gh pr merge 5 --disable-auto", asked))
        self.assertEqual(asked.gestures, [])

    def test_other_commands_do_not_read_the_key(self) -> None:
        """#280: a reading, a comment, a push of a branch: the key is not asked."""
        for command in ("gh pr view 5", "gh pr checks 5", "git status", "git push origin feat/x", "gh pr edit 5 --add-label x"):
            with self.subTest(command=command):
                asked = Asked(CLOSED)
                self.assertIsNone(judged(command, asked))
                self.assertEqual(asked.gestures, [])

    def test_the_refusal_has_its_name_in_the_journal(self) -> None:
        """#280: the journal names the rule `agent-autonomy`, never `other`."""
        with project(PROSE) as where:
            for gesture in ("merge", "tag"):
                reason = autonomy_refusal(str(where), gesture)
                self.assertEqual(rule_of(str(reason), RULES), "agent-autonomy")

    def test_a_caller_that_passes_no_reader_does_not_ask_for_the_check(self) -> None:
        """#280: like `merge_method`, `None` is `refusal`'s default for a caller that does not ask."""
        self.assertIsNone(judged("gh pr merge 5 --merge", None))


if __name__ == "__main__":
    unittest.main()
