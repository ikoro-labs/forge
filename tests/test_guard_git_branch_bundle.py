"""#280 A5: `git branch -D` is allowed when a verified bundle holds every commit no remote holds.

Two seams. `refusal` takes the verdict on a bundle as a callable (the command's reading: which
forms, which directory, alone or not); `bundle_covers` and `main` run real git on throwaway
repositories (what a bundle must prove). A test that passes the verdict by hand proves the command
is read right, not that a bundle is; the real repositories prove the second.
"""

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import support  # noqa: F401  (puts the hooks on the import path)
from guard_git import BUNDLE_KEY, bundle_covers, main, refusal


def never_green(*_target: str | None) -> bool:
    return False


class Seen:
    """A verdict on bundles that records what the guard asked."""

    def __init__(self, covered: bool) -> None:
        self.covered = covered
        self.asked: list[tuple[str | None, list[str]]] = []

    def __call__(self, directory: str | None, names: list[str]) -> bool:
        self.asked.append((directory, names))
        return self.covered


def decided(command: str, covered: bool, cwd: str | None = "/work") -> tuple[str | None, Seen]:
    seen = Seen(covered)
    reason = refusal(command, "feat/x", never_green, cwd, branch_deletion_covered=seen)
    return reason, seen


class CommandReading(unittest.TestCase):
    def test_a_covered_deletion_passes_in_each_form_of_the_force(self) -> None:
        """#280 A5: -D, -Dq, -df, --delete --force, behind `-C` or a `cd`, name the branches asked."""
        for command in (
            "git branch -D feat/old",
            "git branch -Dq feat/old",
            "git branch -d -f feat/old",
            "git branch -df feat/old",
            "git branch --delete --force feat/old",
            "git branch feat/old -D",
            "git --no-pager branch -D feat/old",
            "cd /work && git branch -D feat/old",
        ):
            with self.subTest(command=command):
                reason, seen = decided(command, True)
                self.assertIsNone(reason)
                self.assertEqual([names for _directory, names in seen.asked], [["feat/old"]])

    def test_every_branch_named_is_asked_about(self) -> None:
        """#280 A5: one uncovered branch among several keeps the refusal (the verdict is on the list)."""
        reason, seen = decided("git branch -D feat/a feat/b", True)
        self.assertIsNone(reason)
        self.assertEqual(seen.asked[0][1], ["feat/a", "feat/b"])

    def test_the_directory_git_acts_on_is_the_one_asked(self) -> None:
        """#280 A5: `git -C <dir>` and `cd <dir>` move the repository whose bundles are read."""
        _reason, seen = decided("git -C /other branch -D feat/old", True)
        self.assertEqual(seen.asked[0][0], "/other")
        _reason, seen = decided("cd /elsewhere && git branch -D feat/old", True)
        self.assertEqual(seen.asked[0][0], "/elsewhere")

    def test_an_uncovered_deletion_stays_refused_and_says_what_to_do(self) -> None:
        """#280 A5: no verified bundle: the old refusal, now naming the bundle and the human's command."""
        reason, _seen = decided("git branch -D feat/old", False)
        text = reason or ""
        self.assertIn("forced branch deletion", text)
        self.assertIn("bundle", text)
        self.assertIn(BUNDLE_KEY, text)
        self.assertIn("ready to run", text)

    def test_without_a_verdict_the_deletion_is_refused(self) -> None:
        """#280 A5: a caller that gives no verdict (the default) never allows the deletion."""
        reason = refusal("git branch -D feat/old", "feat/x", never_green)
        self.assertIn("forced branch deletion", reason or "")

    def test_a_deletion_that_is_not_a_plain_local_one_is_refused_even_when_covered(self) -> None:
        """#280 A5: remote-tracking branches, renames, listings, no name, an option the guard does not know."""
        for command in (
            "git branch -D -r origin/feat/old",
            "git branch -rD origin/feat/old",
            "git branch --remotes -D origin/feat/old",
            "git branch -D",
            "git branch -D --",
            "git branch -D -- feat/old",
            "git branch -D -a feat/old",
            "git branch -D --list feat/old",
            "git branch -D -m feat/old",
            "git branch -D --unknown-option feat/old",
        ):
            with self.subTest(command=command):
                reason, _seen = decided(command, True)
                self.assertIn("forced branch deletion", reason or "")

    def test_a_deletion_that_does_not_run_alone_is_refused_even_when_covered(self) -> None:
        """#280 A5: a command before the deletion could change the branch after the bundle was read."""
        for command in (
            "git commit -m x && git branch -D feat/old",
            "git branch -D feat/old && git commit -m x",
            "git reset --soft HEAD~1; git branch -D feat/old",
            "bash -c 'git branch -D feat/old'",
            "echo go | git branch -D feat/old",
            "FOO=1 git branch -D feat/old",
        ):
            with self.subTest(command=command):
                reason, seen = decided(command, True)
                self.assertIn("forced branch deletion", reason or "")
                self.assertEqual(seen.asked, [])

    def test_an_unreadable_directory_is_refused_even_when_covered(self) -> None:
        """#280 A5: `cd ~` or `cd "$X"`: the guard does not know where git acts, so it does not read a bundle."""
        for command in ('cd ~ && git branch -D feat/old', 'cd "$X" && git branch -D feat/old'):
            with self.subTest(command=command):
                reason, seen = decided(command, True)
                self.assertIn("forced branch deletion", reason or "")
                self.assertEqual(seen.asked, [])

    def test_the_other_refusals_are_untouched_by_a_covered_deletion(self) -> None:
        """#280 A5: a covered branch deletion opens nothing but itself."""
        for command in ("git reset --hard", "git push --force origin feat/x", "git commit --no-verify -m x"):
            with self.subTest(command=command):
                reason, _seen = decided(command, True)
                self.assertIsNotNone(reason)


GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


class Repositories(unittest.TestCase):
    """A clone of a bare origin, a branch `feat/x` with two commits no remote holds, a rescue folder."""

    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        isolated = {
            **{k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "GIT_"))},
            **GIT_ENV,
            "HOME": str(self.scratch / "home"),
            "USERPROFILE": str(self.scratch / "home"),
        }
        patched = mock.patch.dict(os.environ, isolated, clear=True)
        patched.start()
        self.addCleanup(patched.stop)
        (self.scratch / "home").mkdir()
        self.rescue = self.scratch / "rescue"
        self.rescue.mkdir()
        self.work = self.scratch / "work"
        self.git("init", "-q", "--bare", "origin.git", cwd=self.scratch)
        self.git("clone", "-q", "origin.git", "work", cwd=self.scratch)
        self.git("commit", "-q", "--allow-empty", "-m", "base")
        self.git("branch", "-M", "trunk")
        self.git("push", "-q", "origin", "trunk")
        self.git("switch", "-q", "-c", "feat/x")
        self.git("commit", "-q", "--allow-empty", "-m", "c1")
        self.git("commit", "-q", "--allow-empty", "-m", "c2")

    def git(self, *args: str, cwd: Path | None = None) -> str:
        done = subprocess.run(
            ["git", *args], cwd=cwd or self.work, capture_output=True, text=True, check=False
        )
        self.assertEqual(done.returncode, 0, f"git {' '.join(args)}: {done.stderr}")
        return done.stdout.strip()

    def covered(self, *names: str, folders: list[str] | None = None) -> bool:
        where = [str(self.rescue)] if folders is None else folders
        return bundle_covers(str(self.work), list(names), where)


class BundleCoverage(Repositories):
    def test_a_full_bundle_of_the_branch_covers_it(self) -> None:
        """#280 A5: every commit no remote holds is in a bundle `git bundle verify` accepts."""
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x")
        self.assertTrue(self.covered("feat/x"))

    def test_a_bundle_of_only_what_no_remote_holds_covers_it(self) -> None:
        """#280 A5: `--not --remotes` leaves the pushed history out: it stays a prerequisite."""
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x", "--not", "--remotes")
        self.assertTrue(self.covered("feat/x"))

    def test_no_bundle_covers_nothing(self) -> None:
        """#280 A5: an empty folder, a missing folder and an absent key (no folder) all refuse."""
        self.assertFalse(self.covered("feat/x"))
        self.assertFalse(self.covered("feat/x", folders=[str(self.scratch / "missing")]))
        self.assertFalse(self.covered("feat/x", folders=[]))

    def test_a_relative_folder_is_not_read(self) -> None:
        """#280 A5: the key names an absolute folder; a relative one depends on the process, so it is ignored."""
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x")
        here = os.getcwd()
        os.chdir(self.scratch)
        self.addCleanup(os.chdir, here)
        self.assertFalse(self.covered("feat/x", folders=["rescue"]))

    def test_a_bundle_with_prerequisites_is_read_where_text_files_get_crlf(self) -> None:
        """#280 A5: on Windows `write_text` turns `\\n` into `\\r\\n`, and git reads `<path>\\r` in an alternates file.

        The thin bundle needs the alternates file (its prerequisites live in the real repository):
        the file must keep its `\\n`, whatever the platform does to text.
        """
        real = Path.write_text

        def windows_write_text(self: Path, data: str, encoding: str | None = None,
                               errors: str | None = None, newline: str | None = None) -> int:
            if newline is None:
                data = data.replace("\n", "\r\n")
            return real(self, data, encoding=encoding, errors=errors, newline="")

        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x", "--not", "--remotes")
        with mock.patch.object(Path, "write_text", windows_write_text):
            self.assertTrue(self.covered("feat/x"))

    def test_a_pushed_branch_still_needs_a_verified_bundle(self) -> None:
        """#280 A5: nothing is unpushed, and the rule is still a bundle: without one the refusal stays."""
        self.git("push", "-q", "origin", "feat/x")
        self.assertFalse(self.covered("feat/x"))
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x")
        self.assertTrue(self.covered("feat/x"))

    def test_a_bundle_older_than_the_branch_does_not_cover_it(self) -> None:
        """#280 A5: a commit made after the bundle is on no remote and in no bundle."""
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x")
        self.git("commit", "-q", "--allow-empty", "-m", "c3")
        self.assertFalse(self.covered("feat/x"))

    def test_a_bundle_that_misses_an_unpushed_commit_does_not_cover_it(self) -> None:
        """#280 A5: `git bundle verify` accepts this one (c1 is here) and it still lacks c1."""
        c1 = self.git("rev-parse", "feat/x~1")
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x", "--not", c1)
        self.assertFalse(self.covered("feat/x"))

    def test_a_truncated_bundle_does_not_cover_the_branch(self) -> None:
        """#280 A5: `git bundle verify` reads the header only and accepts a cut pack: the pack is read too."""
        target = self.rescue / "x.bundle"
        self.git("bundle", "create", str(target), "feat/x")
        target.write_bytes(target.read_bytes()[:-20])
        verify = subprocess.run(
            ["git", "bundle", "verify", str(target)], cwd=self.work, capture_output=True, check=False
        )
        self.assertEqual(verify.returncode, 0)  # the premise: verify alone is fooled
        self.assertFalse(self.covered("feat/x"))

    def test_a_bundle_whose_header_names_a_tip_its_pack_lacks_does_not_cover_it(self) -> None:
        """#280 A5: a header relabelled to the branch's tip, over the pack of an older commit."""
        self.git("branch", "old", "feat/x~1")
        target = self.rescue / "x.bundle"
        self.git("bundle", "create", str(target), "old")
        old, tip = self.git("rev-parse", "old"), self.git("rev-parse", "feat/x")
        target.write_bytes(target.read_bytes().replace(old.encode(), tip.encode(), 1))
        self.assertFalse(self.covered("feat/x"))

    def test_a_file_that_is_not_a_bundle_covers_nothing(self) -> None:
        """#280 A5: anything the guard cannot read refuses."""
        (self.rescue / "x.bundle").write_text("not a bundle", encoding="utf-8")
        self.assertFalse(self.covered("feat/x"))

    def test_only_files_ending_in_bundle_are_read(self) -> None:
        """#280 A5: the folder's convention is `*.bundle`, the one the cleanup of the same key uses."""
        self.git("bundle", "create", str(self.rescue / "x.dump"), "feat/x")
        self.assertFalse(self.covered("feat/x"))

    def test_each_branch_needs_its_own_cover(self) -> None:
        """#280 A5: two branches, one bundle for one of them: the pair is not covered."""
        self.git("branch", "feat/y", "feat/x")
        self.git("switch", "-q", "feat/y")
        self.git("commit", "-q", "--allow-empty", "-m", "y1")
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x")
        self.assertTrue(self.covered("feat/x"))
        self.assertFalse(self.covered("feat/x", "feat/y"))
        self.git("bundle", "create", str(self.rescue / "y.bundle"), "feat/y")
        self.assertTrue(self.covered("feat/x", "feat/y"))

    def test_a_branch_the_repository_does_not_have_is_not_covered(self) -> None:
        """#280 A5: a typo, a remote-tracking name, a full ref name, a rev expression and an option."""
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x")
        for name in ("feat/nope", "origin/trunk", "refs/heads/feat/x", "feat/x~1", "-D", "", "feat/x^{commit}"):
            with self.subTest(name=name):
                self.assertFalse(self.covered(name))

    def test_no_name_is_not_covered(self) -> None:
        """#280 A5: an empty list proves nothing."""
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x")
        self.assertFalse(self.covered())

    def test_a_directory_that_is_no_repository_covers_nothing(self) -> None:
        """#280 A5: the guard may be asked from anywhere: no repository, no cover, no crash."""
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x")
        nowhere = self.scratch / "nowhere"
        nowhere.mkdir()
        self.assertFalse(bundle_covers(str(nowhere), ["feat/x"], [str(self.rescue)]))
        self.assertFalse(bundle_covers(str(self.scratch / "absent"), ["feat/x"], [str(self.rescue)]))

    def test_the_bundle_is_read_from_a_linked_worktree_too(self) -> None:
        """#280 A5: a branch checked out elsewhere is judged from the worktree git acts in."""
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x")
        self.git("switch", "-q", "trunk")
        linked = self.scratch / "linked"
        self.git("worktree", "add", "-q", str(linked), "-b", "feat/z", "trunk")
        self.assertTrue(bundle_covers(str(linked), ["feat/x"], [str(self.rescue)]))

    def test_the_repository_is_left_as_it_was(self) -> None:
        """#280 A5: reading a bundle writes nothing in the repository (no object, no ref, no config)."""
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x", "--not", "--remotes")
        before = self.git("for-each-ref"), self.git("count-objects", "-v")
        self.assertTrue(self.covered("feat/x"))
        self.assertEqual((self.git("for-each-ref"), self.git("count-objects", "-v")), before)


@contextlib.contextmanager
def run_hook(command: str, root: Path, cwd: Path, key: str | None) -> Iterator[tuple[int, str]]:
    """The real `main`, with its key read from the project's `usine.md`, on real git."""
    config = root / "docs" / "agents"
    config.mkdir(parents=True, exist_ok=True)
    (config / "usine.md").write_text(f"- `{BUNDLE_KEY}` : `{key}`\n" if key else "", encoding="utf-8")
    event = json.dumps({"tool_input": {"command": command}, "cwd": str(cwd)})
    err = io.StringIO()
    with (
        mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(root)}),
        mock.patch("sys.stdin", io.StringIO(event)),
        mock.patch("sys.stderr", err),
    ):
        yield main(), err.getvalue()


class Hook(Repositories):
    def test_the_hook_allows_the_deletion_once_the_folder_of_the_key_holds_a_bundle(self) -> None:
        """#280 A5: the key `rescue-bundle-dir` gives the folder; the bundle makes the gesture pass."""
        self.git("switch", "-q", "trunk")
        command = "git branch -D feat/x"
        with run_hook(command, self.work, self.work, str(self.rescue)) as (code, message):
            self.assertEqual(code, 2)
            self.assertIn("forced branch deletion", message)
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x", "--not", "--remotes")
        with run_hook(command, self.work, self.work, str(self.rescue)) as (code, message):
            # This repository has no `origin/main`: the guard says on stderr that it read its keys from `usine.md`.
            self.assertEqual(code, 0)
            self.assertNotIn("Blocked by the forge plugin", message)

    def test_the_hook_without_the_key_keeps_the_refusal(self) -> None:
        """#280 A5: key absent: step without object, no default folder, the refusal stays."""
        self.git("switch", "-q", "trunk")
        self.git("bundle", "create", str(self.rescue / "x.bundle"), "feat/x")
        with run_hook("git branch -D feat/x", self.work, self.work, None) as (code, message):
            self.assertEqual(code, 2)
            self.assertIn(BUNDLE_KEY, message)


if __name__ == "__main__":
    unittest.main()
