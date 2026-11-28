"""ikoro-labs/forge#345 : `usine.load` reads the keys that bound the agent in `usine-gardes.md`.

The file is read as `refs/remotes/origin/main` holds it (`git ls-tree` then `git cat-file`), never in the working tree an
agent can edit. Every repository here is a temporary one, under a temporary `HOME`; none of the
session's `CLAUDE_` or `GIT_` variables reaches git, and the real `~/.claude` is never read nor
written.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import support
from guard_git import autonomy_refusal
from usine import GUARD_PATH, SENSITIVE_KEYS, load, load_checked

USINE = Path("docs") / "agents" / "usine.md"


def entry(key: str, value: str) -> str:
    return f"- `{key}` : `{value}`\n"


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


def write(where: Path, files: Mapping[Path, str]) -> None:
    for relative, text in files.items():
        (where / relative).parent.mkdir(parents=True, exist_ok=True)
        (where / relative).write_text(text, encoding="utf-8")


@contextmanager
def project(on_main: Mapping[Path, str], in_tree: Mapping[Path, str] | None = None) -> Iterator[Path]:
    """A repository whose `origin/main` holds the files `on_main`, and whose working tree then
    holds `in_tree` on top of them."""
    with tempfile.TemporaryDirectory() as folder:
        home = Path(folder) / "home"
        where = Path(folder) / "depot"
        home.mkdir()
        where.mkdir()
        git(where, home, "init", "-q", "-b", "feat/x")
        write(where, {Path("README.md"): "x\n", **on_main})
        git(where, home, "add", "-A")
        git(where, home, "commit", "-q", "-m", "init")
        git(where, home, "update-ref", "refs/remotes/origin/main", "HEAD")
        write(where, in_tree or {})
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


class ASensitiveKeyInUsineMdIsDroppedAndReported(unittest.TestCase):
    def test_b2_a_sensitive_key_written_in_usine_md_does_not_count_and_is_reported(self) -> None:
        """#345 B2: `ticket-pr-cap` only in `usine.md`: the guard file is on `origin/main`, the key is dropped."""
        on_main = {GUARD_PATH: entry("run-limits", "2000 | 300"), USINE: "# Usine\n"}
        with project(on_main, in_tree={USINE: entry("ticket-pr-cap", "99") + entry("merge-method", "merge")}) as where:
            loaded = load_checked(where)
        self.assertNotIn("ticket-pr-cap", loaded.config)
        self.assertEqual(loaded.config["merge-method"], ["merge"])
        self.assertEqual(len(loaded.notices), 1)
        self.assertIn("`ticket-pr-cap` in docs/agents/usine.md is dropped", loaded.notices[0])

    def test_b2_the_guard_file_wins_over_the_same_key_in_usine_md(self) -> None:
        """#345 B2: the key is in both files: the guard file's value stays, `usine.md`'s is dropped."""
        on_main = {GUARD_PATH: entry("ticket-pr-cap", "3"), USINE: "# Usine\n"}
        with project(on_main, in_tree={USINE: entry("ticket-pr-cap", "99")}) as where:
            loaded = load_checked(where)
        self.assertEqual(loaded.config["ticket-pr-cap"], ["3"])
        self.assertEqual(len(loaded.notices), 1)

    def test_b2_every_sensitive_key_is_dropped_by_the_one_set(self) -> None:
        """#345 B2: each of `SENSITIVE_KEYS` written in `usine.md` is dropped, none is reported twice."""
        text = "".join(entry(key, "x") for key in sorted(SENSITIVE_KEYS))
        with project({GUARD_PATH: "# Gardes\n", USINE: "# Usine\n"}, in_tree={USINE: text}) as where:
            loaded = load_checked(where)
        self.assertEqual(loaded.config, {})
        self.assertEqual(len(loaded.notices), len(SENSITIVE_KEYS))

    def test_b2_a_free_key_in_the_guard_file_is_ignored_and_reported(self) -> None:
        """#345 B2: the guard file speaks for the sensitive keys only; `merge-method` there is ignored."""
        on_main = {GUARD_PATH: entry("merge-method", "squash") + entry("run-limits", "2000 | 300")}
        with project(on_main) as where:
            loaded = load_checked(where)
        self.assertNotIn("merge-method", loaded.config)
        self.assertEqual(loaded.config["run-limits"], ["2000 | 300"])
        self.assertEqual(len(loaded.notices), 1)
        self.assertIn("`merge-method` in docs/agents/usine-gardes.md is ignored", loaded.notices[0])


class SensitiveKeysAreReadInTheGuardFile(unittest.TestCase):
    def test_b1_a_sensitive_key_is_the_value_origin_main_holds_not_the_working_tree_one(self) -> None:
        """#345 B1: `ticket-pr-cap` is 3 in `usine-gardes.md` on `origin/main`; 9 on disk does not count."""
        on_main = {GUARD_PATH: entry("ticket-pr-cap", "3"), USINE: entry("merge-method", "merge")}
        with project(on_main, in_tree={GUARD_PATH: entry("ticket-pr-cap", "9")}) as where:
            config = load(where)
        self.assertEqual(config["ticket-pr-cap"], ["3"])

    def test_b1_a_free_key_still_comes_from_usine_md(self) -> None:
        """#345 B1: `merge-method` is free: `usine.md` keeps it, the guard file has no say."""
        on_main = {GUARD_PATH: entry("ticket-pr-cap", "3"), USINE: entry("merge-method", "merge")}
        with project(on_main) as where:
            config = load(where)
        self.assertEqual(config["merge-method"], ["merge"])

    def test_b1_every_listed_sensitive_key_is_read_from_the_guard_file(self) -> None:
        """#345 B1: the 24 keys (the 21 of the staff decision, `e2e-run-limits` of #359, `ticket-pr-cap-exempt` of #314 and `ticket-pr-cap-small` of #381), each read there, none from `usine.md`."""
        guard = "".join(entry(key, f"guard-{key}") for key in sorted(SENSITIVE_KEYS))
        with project({GUARD_PATH: guard, USINE: "# Usine\n"}) as where:
            config = load(where)
        self.assertEqual(len(SENSITIVE_KEYS), 24)
        self.assertEqual({key: config.get(key) for key in SENSITIVE_KEYS}, {key: [f"guard-{key}"] for key in SENSITIVE_KEYS})


def lose_the_guard_file(where: Path, home: Path) -> None:
    """Delete the object of the guard file: the ref lists it and git cannot read it."""
    sha = git(where, home, "rev-parse", f"refs/remotes/origin/main:{GUARD_PATH.as_posix()}").strip()
    loose = where / ".git" / "objects" / sha[:2] / sha[2:]
    loose.chmod(0o600)
    loose.unlink()


def run_guard(where: Path, event: Mapping[str, object]) -> subprocess.CompletedProcess[str]:
    """`guard_git.py` as a process, in `where`, under the temporary HOME of that project."""
    return subprocess.run(  # noqa: S603 - the interpreter running this suite, a fixed script
        [sys.executable, str(support.PLUGIN / "hooks" / "guard_git.py")],
        input=json.dumps({"cwd": str(where), **event}),
        env=environment(where.parent / "home"),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def bash(command: str) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


GITHUB_MERGE = {"tool_name": "mcp__github__merge_pull_request", "tool_input": {"pullNumber": 5}}


class AnUnreadableGuardFileRefusesTheMerge(unittest.TestCase):
    def test_b4_the_loader_says_why_the_guard_file_cannot_be_read(self) -> None:
        """#345 B4: the ref lists `usine-gardes.md` and git cannot read it: `unreadable` is set, the keys fall back."""
        on_main = {GUARD_PATH: entry("ticket-pr-cap", "3"), USINE: entry("merge-method", "merge")}
        with project(on_main) as where:
            lose_the_guard_file(where, where.parent / "home")
            loaded = load_checked(where)
        self.assertIsNotNone(loaded.unreadable)
        self.assertEqual(loaded.config["merge-method"], ["merge"])
        self.assertIn("cannot be read", loaded.notices[0])

    def test_b4_no_origin_main_and_no_repository_are_unreadable_too(self) -> None:
        """#345 B4: git cannot tell what the human merged: not "absent", unreadable."""
        with project({USINE: entry("merge-method", "merge")}) as where:
            git(where, where.parent / "home", "update-ref", "-d", "refs/remotes/origin/main")
            self.assertIsNotNone(load_checked(where).unreadable)
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNotNone(load_checked(Path(folder)).unreadable)

    def test_b4_a_merge_through_the_github_tool_is_refused_and_the_reason_names_the_guard_file(self) -> None:
        """#345 B4: `agent-autonomy` is `on` in `usine.md`, but the guard file cannot be read: refused."""
        on_main = {GUARD_PATH: entry("agent-autonomy", "on"), USINE: entry("agent-autonomy", "on")}
        with project(on_main) as where:
            lose_the_guard_file(where, where.parent / "home")
            done = run_guard(where, GITHUB_MERGE)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("docs/agents/usine-gardes.md cannot be read on origin/main", done.stderr)

    def test_b4_a_gh_merge_is_refused_the_same_way(self) -> None:
        """#345 B4: `gh pr merge` goes through the same reader."""
        on_main = {GUARD_PATH: entry("agent-autonomy", "on")}
        with project(on_main) as where:
            lose_the_guard_file(where, where.parent / "home")
            done = run_guard(where, bash("gh pr merge 5 --merge"))
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("docs/agents/usine-gardes.md cannot be read on origin/main", done.stderr)


class TheAutonomySwitchIsReadInTheGuardFile(unittest.TestCase):
    def test_the_switch_on_in_the_guard_file_opens_the_gesture(self) -> None:
        """#345 B1: `agent-autonomy` is a sensitive key: `on` in `usine-gardes.md` on `origin/main` opens it."""
        with project({GUARD_PATH: entry("agent-autonomy", "on"), USINE: "# Usine\n"}) as where:
            self.assertIsNone(autonomy_refusal(str(where), "merge"))
            self.assertIsNone(autonomy_refusal(str(where), "tag"))

    def test_the_guard_file_wins_over_usine_md_on_origin_main(self) -> None:
        """#345 B1: `off` in the guard file, `on` in `usine.md`: refused, the guard file speaks."""
        on_main = {GUARD_PATH: entry("agent-autonomy", "off"), USINE: entry("agent-autonomy", "on")}
        with project(on_main) as where:
            reason = autonomy_refusal(str(where), "merge")
        assert reason is not None
        self.assertIn("docs/agents/usine-gardes.md", reason)

    def test_the_switch_is_still_read_in_usine_md_while_the_guard_file_is_absent(self) -> None:
        """#345 B3: before the move, `usine.md` on `origin/main` holds the switch, as it did."""
        with project({USINE: entry("agent-autonomy", "on")}) as where:
            self.assertIsNone(autonomy_refusal(str(where), "merge"))

    def test_the_switch_in_the_working_tree_guard_file_does_not_count(self) -> None:
        """#345 B1: the agent edits the guard file on disk; `origin/main` says `off`."""
        with project({GUARD_PATH: entry("agent-autonomy", "off")}, in_tree={GUARD_PATH: entry("agent-autonomy", "on")}) as where:
            self.assertIsNotNone(autonomy_refusal(str(where), "merge"))


class TheOtherGuardKeysGoThroughTheLoader(unittest.TestCase):
    OWNER = entry("owner-gesture", "gh label delete | labels belong to the owner")

    def test_b1_a_guard_key_of_the_guard_file_is_applied_by_guard_git(self) -> None:
        """#345 B1: `owner-gesture` in the guard file refuses `gh label delete`, with the human's reason."""
        with project({GUARD_PATH: self.OWNER, USINE: "# Usine\n"}) as where:
            done = run_guard(where, bash("gh label delete bug"))
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("labels belong to the owner", done.stderr)

    def test_b2_the_same_key_written_in_usine_md_is_not_applied_and_the_notice_is_on_stderr(self) -> None:
        """#345 B2: dropped from `usine.md` once the guard file exists; the guard says so on stderr."""
        with project({GUARD_PATH: "# Gardes\n", USINE: self.OWNER}) as where:
            done = run_guard(where, bash("git status"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("`owner-gesture` in docs/agents/usine.md is dropped", done.stderr)

    def test_b3_before_the_guard_file_exists_usine_md_is_applied_and_a_notice_is_on_stderr(self) -> None:
        """#345 B3: the project that has not moved its keys keeps its guards, and the guard says why."""
        with project({USINE: self.OWNER}) as where:
            done = run_guard(where, bash("gh label delete bug"))
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("labels belong to the owner", done.stderr)
        self.assertIn("docs/agents/usine-gardes.md is absent on origin/main", done.stderr)


class WithoutAGuardFileOnOriginMainTheKeysComeFromUsineMd(unittest.TestCase):
    def test_b3_the_sensitive_keys_are_read_in_usine_md_with_a_notice(self) -> None:
        """#345 B3: no `usine-gardes.md` on `origin/main`: `usine.md` holds the keys, and the notice says so."""
        on_main = {USINE: entry("ticket-pr-cap", "3") + entry("merge-method", "merge")}
        with project(on_main) as where:
            loaded = load_checked(where)
        self.assertEqual(loaded.config["ticket-pr-cap"], ["3"])
        self.assertEqual(loaded.config["merge-method"], ["merge"])
        self.assertEqual(len(loaded.notices), 1)
        self.assertIn("docs/agents/usine-gardes.md is absent on origin/main", loaded.notices[0])
        self.assertIsNone(loaded.unreadable)

    def test_b3_a_guard_file_only_in_the_working_tree_does_not_count(self) -> None:
        """#345 B3: the agent writes `usine-gardes.md` on disk; `origin/main` still has none: `usine.md` it is."""
        on_main = {USINE: entry("ticket-pr-cap", "3")}
        with project(on_main, in_tree={GUARD_PATH: entry("ticket-pr-cap", "99")}) as where:
            loaded = load_checked(where)
        self.assertEqual(loaded.config["ticket-pr-cap"], ["3"])
        self.assertIsNone(loaded.unreadable)

    def test_b3_a_project_without_either_file_loads_empty(self) -> None:
        """#345 B3: nothing there, nothing invented."""
        with project({}) as where:
            loaded = load_checked(where)
        self.assertEqual(loaded.config, {})
        self.assertIsNone(loaded.unreadable)
