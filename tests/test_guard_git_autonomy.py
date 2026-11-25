"""ikoro-labs/forge#280: `guard_git` holds the key `agent-autonomy` for the merge and the `forge--v*` tag.

The key is read in `origin/main`, never in the working tree an agent can edit. Every repository here
is a temporary one, under a temporary `HOME`; none of the session's `CLAUDE_` or `GIT_` variables
reaches git, and the real `~/.claude` is never read nor written.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import support  # noqa: F401  met les hooks sur le chemin d'import
from guard_git import RULES, UNKNOWN, autonomy_refusal, local_tag_exists, refusal
from refusal_journal import rule_of
from usine import load

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


CREATING_OR_CHANGING_TAGS = (
    "git tag forge--v1.20.0",
    "git tag -a forge--v1.20.0 -m 'forge 1.20.0'",
    "git tag -am 'forge 1.20.0' forge--v1.20.0",
    "git tag -s forge--v1.20.0",
    "git tag -f forge--v1.20.0 HEAD",
    "git tag -d forge--v1.20.0",
    "git tag --delete forge--v1.20.0",
    "git tag --annotate --message=x forge--v1.20.0",
    "git tag -- forge--v1.20.0",
    "git -C /work/depot tag forge--v1.20.0",
    "cd /work/depot && git tag v1",
    "git tag v1 && git push origin v1",
)
READING_TAGS = (
    "git tag",
    "git tag -l",
    "git tag --list 'forge--v*'",
    "git tag -l 'forge--v*' --sort=-version:refname",
    "git tag -n",
    "git tag -n5 -l",
    "git tag --contains HEAD",
    "git tag --points-at HEAD",
    "git tag --merged main",
    "git tag --sort=-creatordate",
    "git tag -v forge--v1.20.0",
    "git -C /work/depot tag -l",
)
PUSHING_TAGS = (
    "git push --tags",
    "git push origin --tags",
    "git push --follow-tags origin feat/x",
    "git push origin forge--v1.20.0 --tags",
    "git push origin tag forge--v1.20.0",
    "git push origin refs/tags/forge--v1.20.0",
    "git push origin HEAD:refs/tags/forge--v1.20.0",
    "git push origin :refs/tags/forge--v1.20.0",
    "git push origin refs/tags/*:refs/tags/*",
    "git -C /work/depot push origin --tags",
)
PUSHING_BRANCHES = (
    "git push origin feat/x",
    "git push origin HEAD:feat/x",
    "git push --force-with-lease origin feat/x",
    "git push origin feat/tags",
    "git push origin feat/autonomy-tag",
)


class TheTagFollowsTheKey(unittest.TestCase):
    def asked(self, command: str, answer: str | None) -> tuple[str | None, list[str]]:
        asked = Asked(answer)
        return judged(command, asked), asked.gestures

    def test_creating_changing_or_deleting_a_tag_is_refused_when_the_key_is_not_on(self) -> None:
        """#280: `git tag` that writes, whatever its form, is refused with the key's reason."""
        for command in CREATING_OR_CHANGING_TAGS:
            with self.subTest(command=command):
                reason, gestures = self.asked(command, CLOSED)
                self.assertEqual(reason, CLOSED)
                self.assertEqual(gestures[:1], ["tag"])

    def test_pushing_a_tag_is_refused_when_the_key_is_not_on(self) -> None:
        """#280: `--tags`, `--follow-tags`, `--mirror`, a `refs/tags/` refspec, the `tag <name>` form."""
        for command in PUSHING_TAGS:
            with self.subTest(command=command):
                reason, gestures = self.asked(command, CLOSED)
                self.assertEqual(reason, CLOSED)
                self.assertEqual(gestures[:1], ["tag"])

    def test_tag_gestures_pass_when_the_key_is_on(self) -> None:
        """#280: with `on`, the tag and its push are not refused for the key."""
        for command in (*CREATING_OR_CHANGING_TAGS, *PUSHING_TAGS):
            with self.subTest(command=command):
                self.assertIsNone(self.asked(command, None)[0])

    def test_reading_the_tags_never_asks_for_the_key(self) -> None:
        """#280: a listing, a verification, a filter by commit are readings."""
        for command in READING_TAGS:
            with self.subTest(command=command):
                self.assertEqual(self.asked(command, CLOSED), (None, []))

    def test_pushing_a_branch_never_asks_for_the_key(self) -> None:
        """#280: the push of a branch, whatever its name, is not a tag push."""
        for command in PUSHING_BRANCHES:
            with self.subTest(command=command):
                self.assertEqual(self.asked(command, CLOSED), (None, []))

    def test_the_other_rules_of_a_push_still_hold_with_the_key_on(self) -> None:
        """#280: `on` does not open a force push nor a push to main."""
        self.assertIn("force push", str(self.asked("git push --force origin feat/x", None)[0]))
        self.assertIn("push to main", str(self.asked("git push origin main", None)[0]))


# The bare name of an existing tag: `git push <remote> <name>` sends a tag with no `refs/tags/` in the command.
BARE_TAG_PUSHES = (
    "git push origin forge--v1.20.0",
    "git push origin forge--v1.20.0:forge--v1.20.0",
    "git push origin feat/x forge--v1.20.0",
    "git push -o ci.skip origin forge--v1.20.0",
    "git push --push-option=ci.skip origin forge--v1.20.0",
    "git -C /work/depot push origin forge--v1.20.0",
    "cd /work/depot && git push origin forge--v1.20.0",
)


class TagsAre:
    """A reader of the repository's tags that knows `names`, and records where it was asked to look."""

    def __init__(self, *names: str) -> None:
        self.names = names
        self.looked: list[tuple[str | None, str]] = []

    def __call__(self, directory: str | None, name: str) -> bool | None:
        self.looked.append((directory, name))
        return name in self.names


def cannot_tell(_directory: str | None, _name: str) -> bool | None:
    return None


class TheBareNameOfATagFollowsTheKey(unittest.TestCase):
    """F-25: `git push <remote> <name>` sends the tag `<name>` when the repository has one."""

    def judged(self, command: str, answer: str | None, tags: Callable[[str | None, str], bool | None]) -> tuple[str | None, list[str]]:
        asked = Asked(answer)
        return judged(command, asked, tag_exists=tags), asked.gestures

    def test_pushing_an_existing_tag_by_its_bare_name_is_refused_when_the_key_is_not_on(self) -> None:
        """#280 F-25 (a): the name is a tag of the repository the command acts in: refused with the key's reason."""
        for command in BARE_TAG_PUSHES:
            with self.subTest(command=command):
                reason, gestures = self.judged(command, CLOSED, TagsAre("forge--v1.20.0"))
                self.assertEqual(reason, CLOSED)
                self.assertEqual(gestures[:1], ["tag"])

    def test_pushing_an_existing_tag_by_its_bare_name_passes_when_the_key_is_on(self) -> None:
        """#280 F-25 (a): with `on`, the push of the tag is not refused for the key."""
        for command in BARE_TAG_PUSHES:
            with self.subTest(command=command):
                self.assertIsNone(self.judged(command, None, TagsAre("forge--v1.20.0"))[0])

    def test_pushing_a_branch_is_not_held_when_the_name_is_no_tag(self) -> None:
        """#280 F-25 (a): a branch push, whatever its form, never asks for the key."""
        for command in (*PUSHING_BRANCHES, "git push origin HEAD", "git push", "git push origin", "git push -u origin feat/x"):
            with self.subTest(command=command):
                self.assertEqual(self.judged(command, CLOSED, TagsAre("forge--v1.20.0")), (None, []))

    def test_the_tags_are_read_where_git_acts(self) -> None:
        """#280 F-25 (a): `-C <dir>` and `cd <dir>` move the repository whose tags are read."""
        tags = TagsAre()
        self.judged("git -C /work/depot push origin v1", CLOSED, tags)
        self.judged("cd /elsewhere && git push origin v2", CLOSED, tags)
        self.assertEqual(tags.looked, [("/work/depot", "v1"), ("/elsewhere", "v2")])

    def test_a_push_whose_tags_cannot_be_read_is_refused_when_the_key_is_not_on(self) -> None:
        """#280 F-25 (a): closed when the guard cannot tell a tag from a branch."""
        reason, gestures = self.judged("git push origin feat/x", CLOSED, cannot_tell)
        self.assertEqual((reason, gestures[:1]), (CLOSED, ["tag"]))
        self.assertIsNone(self.judged("git push origin feat/x", None, cannot_tell)[0])

    def test_a_ref_outside_the_tags_namespace_is_no_tag_and_is_not_looked_up(self) -> None:
        """#280 F-25 (a): a `refs/heads/` ref and the options' values are not names of tags."""
        tags = TagsAre("origin", "ci.skip")
        for command in ("git push origin refs/heads/feat/x", "git push -o ci.skip origin feat/x"):
            with self.subTest(command=command):
                self.assertEqual(self.judged(command, CLOSED, tags), (None, []))
        self.assertNotIn("refs/heads/feat/x", [name for _directory, name in tags.looked])

    def test_the_other_rules_of_a_push_still_hold_with_the_key_on(self) -> None:
        """#280 F-25 (a): `on` opens the push of a tag, not a push to main."""
        reason, _ = self.judged("git push origin main", None, TagsAre("main"))
        self.assertIn("push to main", str(reason))

    def test_a_caller_that_passes_no_tag_reader_does_not_ask_for_the_check(self) -> None:
        """#280 F-25 (a): like `autonomy`, `None` is the default of a caller that does not ask."""
        asked = Asked(CLOSED)
        self.assertIsNone(judged("git push origin forge--v1.20.0", asked))
        self.assertEqual(asked.gestures, [])


RELEASES_CREATED = (
    "gh release create forge--v1.20.0",
    "gh release create forge--v1.20.0 --notes 'x' --target main",
    "gh release create --generate-notes forge--v1.20.0",
    "gh -R o/r release create forge--v1.20.0",
    "gh --repo=o/r release create forge--v1.20.0",
    "gh release -R o/r create forge--v1.20.0",
    "cd /work/depot && gh release create forge--v1.20.0",
    "GH_REPO=o/r gh release create forge--v1.20.0",
)
RELEASES_READ_OR_EDITED = (
    "gh release list",
    "gh release view forge--v1.20.0",
    "gh release download forge--v1.20.0",
    "gh release edit forge--v1.20.0 --notes x",
    "gh release upload forge--v1.20.0 file.zip",
    "gh release delete-asset forge--v1.20.0 file.zip",
    "gh pr create --title x",
)


class TheReleaseFollowsTheKey(unittest.TestCase):
    """F-25: `gh release create` creates a tag as well, so it is the tag's gesture."""

    def test_creating_a_release_is_refused_when_the_key_is_not_on(self) -> None:
        """#280 F-25 (b): refused with the key's reason, whatever the form of the call."""
        for command in RELEASES_CREATED:
            with self.subTest(command=command):
                asked = Asked(CLOSED)
                self.assertEqual(judged(command, asked), CLOSED)
                self.assertEqual(asked.gestures[:1], ["release"])

    def test_creating_a_release_passes_when_the_key_is_on(self) -> None:
        """#280 F-25 (b): with `on`, the release is not refused for the key."""
        for command in RELEASES_CREATED:
            with self.subTest(command=command):
                self.assertIsNone(judged(command, Asked(None)))

    def test_reading_or_editing_a_release_never_asks_for_the_key(self) -> None:
        """#280 F-25 (b): only `create` makes a tag."""
        for command in RELEASES_READ_OR_EDITED:
            with self.subTest(command=command):
                asked = Asked(CLOSED)
                self.assertIsNone(judged(command, asked))
                self.assertEqual(asked.gestures, [])

    def test_the_refusal_names_the_release_and_has_its_name_in_the_journal(self) -> None:
        """#280 F-25 (b): the reason says which gesture it refuses; the journal rule stays `agent-autonomy`."""
        with project(PROSE) as where:
            reason = autonomy_refusal(str(where), "release")
        assert reason is not None
        self.assertIn("refuses the release", reason)
        self.assertEqual(rule_of(reason, RULES), "agent-autonomy")


GUARD = support.PLUGIN / "hooks" / "guard_git.py"
USINE_WITH_KEY = PROSE + "- `merge-method` : `merge`\n" + key("on")


def run_guard(where: Path, tool: str, tool_input: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    """`guard_git` as Claude Code runs it: a process fed the event, in `where`, under the temporary HOME."""
    event = {"tool_name": tool, "tool_input": tool_input, "cwd": str(where)}
    return subprocess.run(  # noqa: S603 - the interpreter running this suite, the plugin's script
        [sys.executable, str(GUARD)],
        input=json.dumps(event),
        env=environment(where.parent / "home"),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


MCP_MERGE = {"owner": "o", "repo": "r", "pullNumber": 5, "merge_method": "merge"}
MCP_MERGE_TOOLS = (
    "mcp__github__merge_pull_request",
    "mcp__plugin_github_github__merge_pull_request",
    "mcp__GITHUB__merge_pull_request",
)


class TheHookReadsTheKeyOfOriginMain(unittest.TestCase):
    """The hook as a process: the key is `origin/main`'s, the working tree's own `usine.md` is not read for it."""

    def test_a_tag_is_refused_without_the_key_in_origin_main_even_when_the_working_tree_has_it(self) -> None:
        """#280: the tree says `on`, `origin/main` does not: refused, exit 2, the reason on stderr."""
        with project(PROSE, in_tree=USINE_WITH_KEY) as where:
            done = run_guard(where, "Bash", {"command": "git tag forge--v1.20.0"})
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("Blocked by the forge plugin (guard_git)", done.stderr)
        self.assertIn("`agent-autonomy` key is not `on`", done.stderr)
        self.assertIn("human", done.stderr)

    def test_a_tag_and_its_push_pass_with_the_key_on_in_origin_main(self) -> None:
        """#280: `on` in `origin/main`: the same commands run."""
        with project(USINE_WITH_KEY, in_tree=PROSE) as where:
            for command in ("git tag forge--v1.20.0", "git push origin forge--v1.20.0 --tags"):
                with self.subTest(command=command):
                    done = run_guard(where, "Bash", {"command": command})
                    self.assertEqual(done.returncode, 0, done.stderr)

    def test_a_merge_is_refused_without_the_key_in_origin_main(self) -> None:
        """#280: `gh pr merge` with the tree's `on` and `origin/main` without it: refused for the key."""
        with project(PROSE, in_tree=USINE_WITH_KEY) as where:
            done = run_guard(where, "Bash", {"command": "gh pr merge 5 --merge"})
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("`agent-autonomy` key is not `on`", done.stderr)

    def test_the_refusal_is_journaled_under_its_name(self) -> None:
        """#280: the refusals journal of the temporary HOME names the rule `agent-autonomy`."""
        with project(PROSE) as where:
            run_guard(where, "Bash", {"command": "git tag v1"})
            folder = where.parent / "home" / ".claude" / "hooks" / "state" / "refusals"
            lines = [
                json.loads(line)
                for path in sorted(folder.glob("*.jsonl"))
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
        self.assertEqual([(line["rule"], line["verb"]) for line in lines], [("agent-autonomy", "git tag")])

    def test_a_reading_of_the_tags_runs_without_the_key(self) -> None:
        with project(PROSE) as where:
            done = run_guard(where, "Bash", {"command": "git tag -l"})
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_bare_name_of_a_tag_of_the_repository_is_refused_without_the_key(self) -> None:
        """#280 F-25 (a): the tag exists in the repository the hook runs in, the key is not `on`: exit 2."""
        with project(PROSE) as where:
            git(where, where.parent / "home", "tag", "forge--v1.20.0")
            done = run_guard(where, "Bash", {"command": "git push origin forge--v1.20.0"})
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("`agent-autonomy` key is not `on`", done.stderr)
        self.assertIn("refuses the tag", done.stderr)

    def test_the_bare_name_of_a_tag_passes_with_the_key_on_in_origin_main(self) -> None:
        """#280 F-25 (a): `on` in `origin/main`: the same push runs."""
        with project(USINE_WITH_KEY, in_tree=PROSE) as where:
            git(where, where.parent / "home", "tag", "forge--v1.20.0")
            done = run_guard(where, "Bash", {"command": "git push origin forge--v1.20.0"})
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_push_of_a_branch_runs_without_the_key_even_when_a_tag_exists(self) -> None:
        """#280 F-25 (a): a branch name that is no tag, `HEAD`, a refspec: never held."""
        with project(PROSE) as where:
            git(where, where.parent / "home", "tag", "forge--v1.20.0")
            for command in ("git push origin feat/x", "git push origin HEAD", "git push origin HEAD:feat/x"):
                with self.subTest(command=command):
                    done = run_guard(where, "Bash", {"command": command})
                    self.assertEqual(done.returncode, 0, done.stderr)

    def test_a_push_from_a_directory_that_is_no_repository_is_refused_without_the_key(self) -> None:
        """#280 F-25 (a): the tags cannot be read there: closed, the reason the key's."""
        with project(PROSE) as where, tempfile.TemporaryDirectory() as elsewhere:
            done = run_guard(where, "Bash", {"command": f"git -C {elsewhere} push origin feat/x"})
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("`agent-autonomy` key is not `on`", done.stderr)

    def test_a_directory_the_guard_does_not_know_leaves_the_tags_unread(self) -> None:
        """#280 F-25 (a): `cd "$VAR"` moves git somewhere unknown: closed, and no crash on the marker."""
        self.assertIsNone(local_tag_exists(UNKNOWN, "v1"))
        with project(PROSE) as where:
            done = run_guard(where, "Bash", {"command": 'cd "$SOMEWHERE" && git push origin feat/x'})
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("`agent-autonomy` key is not `on`", done.stderr)

    def test_a_release_is_refused_without_the_key_and_runs_the_guard_with_it(self) -> None:
        """#280 F-25 (b): `gh release create` as a process: exit 2 without the key, not refused for it with `on`."""
        command = {"command": "gh release create forge--v1.20.0 --notes x"}
        with project(PROSE, in_tree=USINE_WITH_KEY) as where:
            closed = run_guard(where, "Bash", command)
        self.assertEqual(closed.returncode, 2, closed.stderr)
        self.assertIn("`agent-autonomy` key is not `on`", closed.stderr)
        self.assertIn("refuses the release", closed.stderr)
        with project(USINE_WITH_KEY, in_tree=PROSE) as where:
            opened = run_guard(where, "Bash", command)
        self.assertEqual(opened.returncode, 0, opened.stderr)


class TheMcpMergeToolFollowsTheKey(unittest.TestCase):
    def test_the_merge_tool_of_a_github_server_is_refused_without_the_key(self) -> None:
        """#280: the MCP tool merges a PR without `gh`: refused, whatever the server's name."""
        with project(PROSE, in_tree=USINE_WITH_KEY) as where:
            for tool in MCP_MERGE_TOOLS:
                with self.subTest(tool=tool):
                    done = run_guard(where, tool, MCP_MERGE)
                    self.assertEqual(done.returncode, 2, done.stderr)
                    self.assertIn("`agent-autonomy` key is not `on`", done.stderr)

    def test_the_merge_tool_passes_with_the_key_on_in_origin_main(self) -> None:
        with project(USINE_WITH_KEY, in_tree=PROSE) as where:
            for tool in MCP_MERGE_TOOLS:
                with self.subTest(tool=tool):
                    self.assertEqual(run_guard(where, tool, MCP_MERGE).returncode, 0)

    def test_the_forms_of_the_tool_that_merge_are_refused_and_the_readings_are_not(self) -> None:
        """#280: the tool that merges as a method of a write tool, the auto-merge; never a reading."""
        with project(PROSE) as where:
            for tool, tool_input, code in (
                ("mcp__github__pull_request_write", {"method": "merge", "pullNumber": 5}, 2),
                ("mcp__github__enable_pull_request_auto_merge", {"pullNumber": 5}, 2),
                ("mcp__github__pull_request_write", {"method": "update_branch", "pullNumber": 5}, 0),
                ("mcp__github__get_pull_request", {"pullNumber": 5}, 0),
                ("mcp__github__list_pull_requests", {"owner": "o", "repo": "r"}, 0),
                ("mcp__github__update_pull_request_branch", {"pullNumber": 5}, 0),
                ("mcp__github__disable_pull_request_auto_merge", {"pullNumber": 5}, 0),
                ("mcp__other__merge_pull_request", MCP_MERGE, 0),
            ):
                with self.subTest(tool=tool, method=tool_input.get("method")):
                    self.assertEqual(run_guard(where, tool, tool_input).returncode, code)

    def test_hooks_json_runs_guard_git_on_the_mcp_tools_of_a_github_server(self) -> None:
        """#280: the matcher of `guard_git` names the MCP tools, or the filter would apply to none of them."""
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        groups = [g for g in hooks["hooks"]["PreToolUse"] if "guard_git.py" in g["hooks"][0]["command"]]
        self.assertEqual(len(groups), 1)
        matcher = groups[0]["matcher"]
        for name in ("Bash", "PowerShell", *MCP_MERGE_TOOLS):
            with self.subTest(name=name):
                self.assertIsNotNone(re.fullmatch(matcher, name))
        for name in ("Edit", "Write", "mcp__other__merge_pull_request", "Agent"):
            with self.subTest(name=name):
                self.assertIsNone(re.fullmatch(matcher, name))
        self.assertEqual(groups[0]["hooks"][0].get("onFailure"), "block")


class TheFileOfTheKeyIsTheHumansToMerge(unittest.TestCase):
    """The key is read in `origin/main`: a PR is the one way to change what `origin/main` holds."""

    def test_this_repository_protects_the_guard_file_so_that_no_agent_merges_a_change_of_the_key(self) -> None:
        """#280, moved by #345: `docs/agents/usine-gardes.md` is a `protected-path`, and a merge that touches it is refused."""
        protected = support.repo_usine().get("protected-path", [])
        self.assertIn("docs/agents/usine-gardes.md", protected)
        self.assertNotIn("docs/agents/usine.md", protected)
        reason = judged(
            "gh pr merge 5 --merge",
            Asked(None),
            protected_paths=protected,
            changed_files=lambda *_target: ["docs/agents/usine-gardes.md"],
        )
        self.assertIn("protected-path", str(reason))


def prose(path: Path) -> str:
    """The file on one line per paragraph, so a sentence wrapped by the editor still matches."""
    return " ".join(path.read_text(encoding="utf-8").split())


class TheTextsSayWhoHoldsTheKey(unittest.TestCase):
    """What the agent and the human read must say that the hook, not only the skill, holds the key."""

    def test_the_rule_says_guard_git_holds_the_merge_and_the_tag_from_origin_main(self) -> None:
        """#280: `autonomie.md` no longer leaves the merge switch to the skills alone."""
        text = prose(support.PLUGIN / "autonomie.md")
        self.assertIn("`guard_git` tient la même clé", text)
        self.assertIn("`origin/main`", text)
        self.assertIn("refuse la fusion et le tag", text)

    def test_the_template_says_the_hook_holds_the_key(self) -> None:
        """#280: the template of the key tells the project what a missing key now blocks, hook included."""
        text = prose(support.PLUGIN / "templates" / "usine.md")
        self.assertRegex(text, r"`guard_git` refuse alors la fusion et le tag.{0,200}`origin/main`")

    def test_the_installation_page_describes_the_guard_its_reading_and_its_limits(self) -> None:
        """#280: the page that treats the guards says what is refused, where the key is read, what is not held."""
        text = prose(support.REPO_ROOT / "docs" / "installation.md")
        for needle in (
            "## La clé `agent-autonomy` tenue par `guard_git`",
            "lue dans `origin/main`, jamais dans l'arbre de travail",
            "`git tag`",
            "`git push --tags`",
            "`git push <remote> <nom>`",
            "`gh release create`",
            "l'outil MCP",
            "`docs/agents/usine.md` est un `protected-path`",
            "ne sont pas tenus par le garde",
            "l'essai de bout en bout",
            "tests/test_guard_git_autonomy.py",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)

    def test_the_installation_page_no_longer_says_the_release_and_the_bare_push_pass(self) -> None:
        """#280 F-25: the list of what is not held names neither `gh release create` nor the push of a bare tag."""
        text = prose(support.REPO_ROOT / "docs" / "installation.md")
        limits = text[text.index("Ce que le garde ne tient pas") : text.index("Éprouvé par les tests de `tests/test_guard_git_autonomy.py`")]
        self.assertNotIn("`gh release create`", limits)
        self.assertIn("`git push origin :<tag>`", limits)

    def test_the_module_says_the_key_in_its_docstring(self) -> None:
        import guard_git  # noqa: PLC0415

        doc = " ".join((guard_git.__doc__ or "").split())
        self.assertIn("`agent-autonomy`", doc)
        self.assertIn("origin/main", doc)
        self.assertIn("`gh release create`", doc)
        self.assertIn("<remote> <name>", doc)
        self.assertNotIn("`gh release create` (it creates a tag) and `git push origin :<tag>` are not held", doc)


if __name__ == "__main__":
    unittest.main()
