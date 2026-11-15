"""The `SubagentStop` and `SessionStart` hook agent_cleanup.py: the cleanup after an agent, held by
a hook instead of prose (ikoro-labs/forge#199, point (c)).

The seam is the hook as Claude Code runs it: a process of its own, the event as JSON on stdin,
against throwaway git repositories (a bare one as `origin`). Every test runs under an isolated
HOME and USERPROFILE, without the CLAUDE_ variables of the session running the tests, and writes
nothing in the real ~/.claude or ~/.cache. The hook is never run against a real repository.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import handoff_header
import support

HOOK = support.PLUGIN / "hooks" / "agent_cleanup.py"
WINDOWS = sys.platform == "win32"
LINUX = sys.platform.startswith("linux")
HAS_GIT = shutil.which("git") is not None


def remove_tree(path: Path) -> None:
    """rmtree that also removes the read-only files git leaves under .git (Windows)."""

    def writable(function, target, _error) -> None:
        os.chmod(target, 0o700)
        function(target)

    shutil.rmtree(path, onerror=writable)


@unittest.skipUnless(HAS_GIT, "the hook works on git repositories")
class Cleanup(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(remove_tree, self.home)
        self.origin = self.home / "origin.git"
        self.repo = self.home / "demo"
        self.worktrees = self.repo / ".claude" / "worktrees"
        self.env = {key: value for key, value in os.environ.items() if not key.startswith(("CLAUDE_", "GIT_"))}
        self.env.update(
            HOME=str(self.home), USERPROFILE=str(self.home), GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t",
        )
        self.git_in(self.home, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.git_in(self.home, "init", "-q", "-b", "main", str(self.repo))
        self.commit("init")
        self.git("remote", "add", "origin", str(self.origin))
        self.git("push", "-q", "origin", "main")
        self.git("fetch", "-q", "origin")

    # --- a throwaway repository ----------------------------------------------------------------

    def git_in(self, folder: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(folder), *args], capture_output=True, text=True, env=self.env, check=False,
        )
        self.assertEqual(result.returncode, 0, f"git {' '.join(args)}: {result.stderr}")
        return result.stdout.strip()

    def git(self, *args: str) -> str:
        return self.git_in(self.repo, *args)

    def commit(self, message: str, folder: Path | None = None) -> str:
        """A commit on the current branch of `folder` (the main checkout by default), its sha."""
        folder = folder or self.repo
        (folder / f"{message.replace(' ', '-')}.txt").write_text(message, encoding="utf-8")
        self.git_in(folder, "add", "-A")
        self.git_in(folder, "commit", "-q", "-m", message)
        return self.git_in(folder, "rev-parse", "HEAD")

    def branches(self) -> list[str]:
        return self.git("for-each-ref", "--format=%(refname:short)", "refs/heads").split()

    def worktree_paths(self) -> list[Path]:
        listing = self.git("worktree", "list", "--porcelain")
        return [Path(line.removeprefix("worktree ")) for line in listing.splitlines() if line.startswith("worktree ")]

    def declare(self, **keys: str) -> None:
        """The project's `docs/agents/usine.md`, with the given keys (`agent_cache_dir` is `agent-cache-dir`)."""
        lines = [f"- `{key.replace('_', '-')}` : `{value}`" for key, value in keys.items()]
        path = self.repo / "docs" / "agents" / "usine.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Usine\n\n" + "\n".join(lines) + "\n", encoding="utf-8")

    # --- the hook as Claude Code runs it -------------------------------------------------------

    def event(self, name: str = "SubagentStop", **fields: object) -> dict[str, object]:
        base: dict[str, object] = {
            "session_id": "abcdef12-3456-7890-abcd-ef1234567890", "transcript_path": "", "cwd": str(self.repo),
            "hook_event_name": name,
        }
        if name == "SubagentStop":
            base.update(agent_id="a0123456789abcdef", agent_type="forge:coder", stop_hook_active=False)
        return {**base, **fields}

    def run_hook(
        self, event: object, folder: Path | None = None, env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        stdin = event if isinstance(event, str) else json.dumps(event)
        return subprocess.run(
            [sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True, env=env or self.env,
            cwd=folder or self.repo, timeout=120, check=False,
        )

    def message(self, result: subprocess.CompletedProcess[str]) -> str:
        """The one-line-per-element report the hook printed, "" when it said nothing."""
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["systemMessage"] if result.stdout.strip() else ""


    # --- agent worktrees, as Claude Code makes and locks them ----------------------------------

    def record_agent(
        self, agent_id: str, finished: object = True, silent_for: float | None = 2 * 3600,
        config_dir: Path | None = None,
    ) -> None:
        """What Claude Code keeps of a subagent under its config folder: `agent-<id>.meta.json` (with
        `finished` once the agent has returned) and `agent-<id>.jsonl`, its transcript, last written
        `silent_for` seconds ago. `finished=None` writes no `finished` field, `silent_for=None` no transcript."""
        folder = (config_dir or self.home / ".claude") / "projects" / "-demo" / "session-1" / "subagents"
        folder.mkdir(parents=True, exist_ok=True)
        meta: dict[str, object] = {"agentType": "forge:coder", "worktreePath": str(self.worktrees / f"agent-{agent_id}")}
        if finished is not None:
            meta["finished"] = finished
        (folder / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
        if silent_for is not None:
            transcript = folder / f"agent-{agent_id}.jsonl"
            transcript.write_text("{}\n", encoding="utf-8")
            written = time.time() - silent_for
            os.utime(transcript, (written, written))

    def agent_worktree(self, agent_id: str, detach: bool = False, recorded: bool = True) -> Path:
        """`<repo>/.claude/worktrees/agent-<id>` on branch `worktree-agent-<id>`, or on a detached head.
        By default the agent has returned long ago (`record_agent`): an unlocked worktree is removed only so."""
        if recorded:
            self.record_agent(agent_id)
        path = self.worktrees / f"agent-{agent_id}"
        if detach:
            self.git("worktree", "add", "-q", "--detach", str(path))
        else:
            self.git("worktree", "add", "-q", "-b", f"worktree-agent-{agent_id}", str(path))
        return path

    def lock(self, path: Path, pid: int, start: str | None = None) -> None:
        """Lock a worktree as Claude Code does: the session's pid, with its start time off Windows."""
        if not WINDOWS:
            start = handoff_header.process_start(pid) if start is None else start
        stamp = f" start {start}" if start else ""
        self.git("worktree", "lock", "--reason", f"claude agent {path.name} (pid {pid}{stamp})", str(path))

    def running_session(self) -> int:
        """A running process, standing for the session that holds the lock of a live agent."""
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return process.pid

    def gone_session(self) -> int:
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait()
        return process.pid


@unittest.skipUnless(HAS_GIT, "the hook works on git repositories")
class Worktrees(Cleanup):
    def test_a_finished_clean_worktree_is_removed_and_its_work_stays_on_its_branch(self) -> None:
        """#199 (c): a worktree no lock holds is an agent that finished; clean, it goes."""
        path = self.agent_worktree("a1")
        self.commit("work", folder=path)
        result = self.run_hook(self.event())
        self.assertFalse(path.exists())
        self.assertIn("agent-a1", self.message(result))
        self.assertIn("worktree-agent-a1", self.branches())

    def test_a_worktree_locked_by_a_dead_session_is_unlocked_then_removed(self) -> None:
        """#199 (c): the lock of a gone pid is a dead agent's; `git worktree unlock`, then `remove`."""
        path = self.agent_worktree("a1")
        pid = self.gone_session()
        self.lock(path, pid, start="1")
        result = self.run_hook(self.event())
        self.assertFalse(path.exists())
        self.assertIn("agent-a1", self.message(result))

    @unittest.skipIf(WINDOWS, "a Windows lock has no start time: a running pid is taken for its holder")
    def test_a_running_pid_with_another_start_time_counts_as_dead(self) -> None:
        """#199 (c): a pid reused by another process (its start time is not the lock's) held nothing."""
        path = self.agent_worktree("a1")
        pid = self.running_session()
        self.lock(path, pid, start=str(int(handoff_header.process_start(pid)) + 1))
        self.run_hook(self.event())
        self.assertFalse(path.exists())

    def test_a_worktree_held_by_a_live_session_stays_locked(self) -> None:
        """#199 (c): at SubagentStop the stopping agent's worktree is still locked by the living
        session; it stays, and goes at a later passage."""
        path = self.agent_worktree("a1")
        self.lock(path, self.running_session())
        result = self.run_hook(self.event())
        self.assertTrue(path.exists())
        self.assertEqual(self.message(result), "")
        self.assertIn("locked", self.git("worktree", "list", "--porcelain"))

    def test_a_dirty_worktree_is_left_and_reported(self) -> None:
        """#199 (c): untracked files, or a changed tracked file, are work: left, and said."""
        untracked = self.agent_worktree("a1")
        (untracked / "notes.txt").write_text("unsaved", encoding="utf-8")
        changed = self.agent_worktree("a2")
        (changed / "init.txt").write_text("edited", encoding="utf-8")
        message = self.message(self.run_hook(self.event()))
        self.assertTrue(untracked.exists() and changed.exists())
        self.assertIn("agent-a1", message)
        self.assertIn("agent-a2", message)
        self.assertEqual(len(message.splitlines()), 2)

    def test_a_detached_head_found_nowhere_else_is_left_and_reported(self) -> None:
        """#199 (c): removing a detached worktree whose commit no branch holds would lose it."""
        path = self.agent_worktree("a1", detach=True)
        self.commit("only here", folder=path)
        message = self.message(self.run_hook(self.event()))
        self.assertTrue(path.exists())
        self.assertIn("agent-a1", message)

    def test_a_detached_head_contained_in_main_or_a_remote_branch_is_removed(self) -> None:
        """#199 (c): the commit lives elsewhere (`main`, or a branch of the remote): safe to remove."""
        in_main = self.agent_worktree("a1", detach=True)
        pushed = self.agent_worktree("a2", detach=True)
        self.commit("pushed work", folder=pushed)
        self.git_in(pushed, "push", "-q", "origin", "HEAD:refs/heads/feature")
        self.git("fetch", "-q", "origin")
        self.run_hook(self.event())
        self.assertFalse(in_main.exists())
        self.assertFalse(pushed.exists())

    def test_only_agent_worktrees_under_the_repository_are_touched(self) -> None:
        """#199 (c): the convention is `<repo>/.claude/worktrees/agent-*`; any other worktree is left alone."""
        other = self.worktrees / "feature-x"
        self.git("worktree", "add", "-q", "-b", "feature-x", str(other))
        elsewhere = self.home / "agent-elsewhere"
        self.git("worktree", "add", "-q", "-b", "worktree-agent-elsewhere", str(elsewhere))
        result = self.run_hook(self.event())
        self.assertTrue(other.exists() and elsewhere.exists())
        self.assertEqual(self.message(result), "")

    def test_an_event_from_inside_a_worktree_cleans_the_main_checkout(self) -> None:
        """#199 (c): a subagent's cwd is its worktree; the hook acts on the main checkout it belongs to."""
        mine = self.agent_worktree("mine")
        self.lock(mine, self.running_session())
        finished = self.agent_worktree("done")
        self.run_hook(self.event(cwd=str(mine)), folder=mine)
        self.assertTrue(mine.exists())
        self.assertFalse(finished.exists())

    def test_a_repository_without_agent_worktrees_prints_nothing(self) -> None:
        """#199 (c): nothing removed, nothing left: nothing said."""
        result = self.run_hook(self.event())
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)


@unittest.skipUnless(HAS_GIT, "the hook works on git repositories")
class LivingAgents(Cleanup):
    """An agent woken by `SendMessage` works in its worktree without locking it: only what Claude Code
    records of the agent (`finished`, and a transcript silent for the grace delay) tells it from a finished one."""

    def test_a_clean_unlocked_worktree_of_an_agent_not_finished_stays_with_its_branch(self) -> None:
        """#199 (c): the meta says `finished: false`; the worktree is clean and its branch pushed, and it stays."""
        path = self.agent_worktree("a1", recorded=False)
        self.record_agent("a1", finished=False)
        sha = self.commit("pushed work", folder=path)
        self.git("push", "-q", "origin", f"{sha}:refs/heads/feature")
        self.git("fetch", "-q", "origin")
        result = self.run_hook(self.event())
        self.assertTrue(path.exists())
        self.assertIn("worktree-agent-a1", self.branches())
        self.assertEqual(self.message(result), "")

    def test_a_finished_agent_woken_again_keeps_its_worktree_while_its_transcript_is_fresh(self) -> None:
        """#199 (c): `finished: true`, but the transcript was written a minute ago: a `SendMessage` woke it."""
        path = self.agent_worktree("a1", recorded=False)
        self.record_agent("a1", finished=True, silent_for=60)
        self.run_hook(self.event())
        self.assertTrue(path.exists())
        self.assertIn("worktree-agent-a1", self.branches())

    def test_the_grace_delay_is_thirty_minutes(self) -> None:
        """#199 (c): 29 minutes of silence keep the worktree, 31 let it go."""
        recent = self.agent_worktree("a1", recorded=False)
        self.record_agent("a1", silent_for=29 * 60)
        quiet = self.agent_worktree("a2", recorded=False)
        self.record_agent("a2", silent_for=31 * 60)
        self.run_hook(self.event())
        self.assertTrue(recent.exists())
        self.assertFalse(quiet.exists())

    def test_a_finished_agent_silent_beyond_the_delay_is_removed(self) -> None:
        """#199 (c): `finished: true` and a transcript older than the delay: the agent is finished."""
        path = self.agent_worktree("a1", recorded=False)
        self.record_agent("a1", finished=True, silent_for=2 * 3600)
        message = self.message(self.run_hook(self.event()))
        self.assertFalse(path.exists())
        self.assertIn("agent-a1", message)

    def test_a_worktree_with_no_meta_stays_without_a_word(self) -> None:
        """#199 (c): no `agent-<id>.meta.json` found: the doubt keeps, and nothing is reported."""
        path = self.agent_worktree("a1", recorded=False)
        result = self.run_hook(self.event())
        self.assertTrue(path.exists())
        self.assertEqual(self.message(result), "")

    def test_an_unreadable_meta_or_a_missing_transcript_or_finished_field_keeps_the_worktree(self) -> None:
        """#199 (c): a meta that is not JSON, one without `finished`, one with a non-boolean, a transcript
        that is missing: each keeps its worktree, silently."""
        garbled = self.agent_worktree("a1", recorded=False)
        self.record_agent("a1")
        records = self.home / ".claude" / "projects" / "-demo" / "session-1" / "subagents"
        (records / "agent-a1.meta.json").write_text("{not json", encoding="utf-8")
        no_field = self.agent_worktree("a2", recorded=False)
        self.record_agent("a2", finished=None)
        text = self.agent_worktree("a3", recorded=False)
        self.record_agent("a3", finished="true")
        no_transcript = self.agent_worktree("a4", recorded=False)
        self.record_agent("a4", silent_for=None)
        result = self.run_hook(self.event())
        for path in (garbled, no_field, text, no_transcript):
            self.assertTrue(path.exists(), path)
        self.assertEqual(self.message(result), "")

    def test_the_config_folder_is_claude_config_dir_when_it_is_set(self) -> None:
        """#199 (c): the records are looked up under `CLAUDE_CONFIG_DIR`, else under `~/.claude`."""
        elsewhere = self.home / "elsewhere"
        path = self.agent_worktree("a1", recorded=False)
        self.record_agent("a1", config_dir=elsewhere)
        self.run_hook(self.event())
        self.assertTrue(path.exists(), "the default folder holds no record of the agent")
        self.run_hook(self.event(), env={**self.env, "CLAUDE_CONFIG_DIR": str(elsewhere)})
        self.assertFalse(path.exists())

    def test_a_dead_lock_holder_frees_a_worktree_whatever_the_records_say(self) -> None:
        """#199 (c): a locked worktree is judged by its holder alone, as before."""
        path = self.agent_worktree("a1", recorded=False)
        self.lock(path, self.gone_session(), start="1")
        self.run_hook(self.event())
        self.assertFalse(path.exists())


@unittest.skipUnless(HAS_GIT, "the hook works on git repositories")
class Branches(Cleanup):
    def branch_ahead(self, name: str) -> str:
        """A local branch one commit ahead of `main`, never pushed, with no worktree; its sha."""
        sha = self.git("commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", f"work of {name}")
        self.git("branch", name, sha)
        return sha

    def test_an_orphan_branch_contained_in_main_is_deleted(self) -> None:
        """#199 (c): no worktree, tip already in `main`: nothing to lose, `git branch -D`."""
        self.git("branch", "worktree-agent-a1")
        message = self.message(self.run_hook(self.event()))
        self.assertNotIn("worktree-agent-a1", self.branches())
        self.assertIn("worktree-agent-a1", message)

    def test_an_orphan_branch_with_unpushed_work_is_kept(self) -> None:
        """#199 (c): a tip found in no `main` and no remote branch would be lost."""
        self.branch_ahead("worktree-agent-a1")
        result = self.run_hook(self.event())
        self.assertIn("worktree-agent-a1", self.branches())
        self.assertEqual(self.message(result), "")

    def test_an_orphan_branch_pushed_to_a_remote_branch_is_deleted(self) -> None:
        """#199 (c): not merged into `main`, but on the remote: `-d` would refuse, the hook's `-D` does not."""
        sha = self.branch_ahead("worktree-agent-a1")
        self.git("push", "-q", "origin", f"{sha}:refs/heads/feature")
        self.git("fetch", "-q", "origin")
        self.run_hook(self.event())
        self.assertNotIn("worktree-agent-a1", self.branches())

    def test_a_branch_outside_the_agent_pattern_is_never_touched(self) -> None:
        """#199 (c): `worktree-agent-*` only, even for a branch contained in `main`."""
        for name in ("feature-y", "agent-a1", "my-worktree-agent-a1", "worktree-agents"):
            self.git("branch", name)
        result = self.run_hook(self.event())
        self.assertEqual(self.message(result), "")
        self.assertEqual(
            sorted(self.branches()), ["agent-a1", "feature-y", "main", "my-worktree-agent-a1", "worktree-agents"],
        )

    def test_a_branch_a_live_worktree_holds_is_kept(self) -> None:
        """#199 (c): the branch of the agent still running is not an orphan."""
        path = self.agent_worktree("a1")
        self.lock(path, self.running_session())
        self.run_hook(self.event())
        self.assertIn("worktree-agent-a1", self.branches())

    def test_a_branch_whose_worktree_was_just_removed_is_deleted_when_contained(self) -> None:
        """#199 (c): the worktree goes, then its branch, in one passage; a branch with work stays."""
        merged = self.agent_worktree("done")
        working = self.agent_worktree("busy")
        self.commit("unpushed", folder=working)
        message = self.message(self.run_hook(self.event()))
        self.assertFalse(merged.exists() or working.exists())
        self.assertEqual(sorted(self.branches()), ["main", "worktree-agent-busy"])
        self.assertEqual(len(message.splitlines()), 3)


@unittest.skipUnless(HAS_GIT, "the hook works on git repositories")
class Caches(Cleanup):
    def cache(self, name: str) -> Path:
        folder = self.home / "cache" / "agents" / name
        folder.mkdir(parents=True)
        (folder / "data.bin").write_text("cached", encoding="utf-8")
        return folder

    def transcript(self, *mentions: object) -> Path:
        """The transcript of the stopping agent: JSON lines whose text mentions the given paths."""
        path = self.home / "transcript.jsonl"
        lines = [json.dumps({"type": "assistant", "text": f"cache at {mention}/data.bin"}) for mention in mentions]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_the_cache_the_transcript_names_is_purged_and_its_neighbour_kept(self) -> None:
        """#199 (c): the agent that stops names its cache, by its path or by `~/...`; the folder next to
        it, even one whose name starts the same, is another agent's."""
        self.declare(agent_cache_dir="~/cache/agents")
        named, tilded = self.cache("abc"), self.cache("def")
        neighbour, lookalike = self.cache("ghi"), self.cache("abc-other")
        transcript = self.transcript(named, "~/cache/agents/def")
        message = self.message(self.run_hook(self.event(agent_transcript_path=str(transcript))))
        self.assertFalse(named.exists() or tilded.exists())
        self.assertTrue(neighbour.exists() and lookalike.exists())
        self.assertEqual(len(message.splitlines()), 2)

    def test_nothing_is_purged_at_session_start(self) -> None:
        """#199 (c): at SessionStart other sessions may have live agents in the same folder."""
        self.declare(agent_cache_dir="~/cache/agents")
        named = self.cache("abc")
        transcript = self.transcript(named)
        result = self.run_hook(self.event("SessionStart", agent_transcript_path=str(transcript)))
        self.assertTrue(named.exists())
        self.assertEqual(self.message(result), "")

    def test_without_the_key_no_cache_is_touched(self) -> None:
        """#199 (c): no `agent-cache-dir`, no default: the step is "sans objet"."""
        self.declare(rescue_bundle_dir="~/bundles")
        named = self.cache("abc")
        transcript = self.transcript(named)
        result = self.run_hook(self.event(agent_transcript_path=str(transcript)))
        self.assertTrue(named.exists())
        self.assertEqual(self.message(result), "")

    def test_a_transcript_that_cannot_be_read_purges_nothing(self) -> None:
        """#199 (c): the doubt keeps."""
        self.declare(agent_cache_dir="~/cache/agents")
        named = self.cache("abc")
        for fields in ({}, {"agent_transcript_path": str(self.home / "missing.jsonl")}, {"agent_transcript_path": 3}):
            with self.subTest(fields=fields):
                result = self.run_hook(self.event(**fields))
                self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)
                self.assertTrue(named.exists())

    def test_only_real_subfolders_are_purged(self) -> None:
        """#199 (c): a file or a symbolic link in the folder is not an agent's cache."""
        self.declare(agent_cache_dir="~/cache/agents")
        real = self.cache("abc")
        target = self.home / "precious"
        target.mkdir()
        (target / "keep.txt").write_text("keep", encoding="utf-8")
        link: Path | None = real.parent / "link"
        try:
            real.parent.joinpath("link").symlink_to(target, target_is_directory=True)
        except OSError:
            link = None  # Windows without the privilege to link
        stray = real.parent / "stray.txt"
        stray.write_text("file", encoding="utf-8")
        transcript = self.transcript(real, real.parent / "link", stray)
        self.run_hook(self.event(agent_transcript_path=str(transcript)))
        self.assertFalse(real.exists())
        self.assertTrue(stray.exists() and (target / "keep.txt").exists())
        self.assertTrue(link is None or link.is_symlink())

    def test_a_folder_that_holds_the_home_or_the_repository_is_never_purged(self) -> None:
        """#199 (c): a key pointing at `~` or at a parent of the repository would purge the user's own folders."""
        for value in ("~", str(self.home), str(self.home.parent)):
            with self.subTest(value=value):
                self.declare(agent_cache_dir=value)
                transcript = self.transcript(self.repo, self.origin)
                result = self.run_hook(self.event(agent_transcript_path=str(transcript)))
                self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)
                self.assertTrue(self.repo.exists() and self.origin.exists())


@unittest.skipUnless(HAS_GIT, "the hook works on git repositories")
class Bundles(Cleanup):
    def setUp(self) -> None:
        super().setUp()
        self.folder = self.home / "bundles"
        self.folder.mkdir()
        self.declare(rescue_bundle_dir="~/bundles")

    def bundle(self, name: str, *refs: str) -> Path:
        """A rescue bundle of the given refs of this repository."""
        path = self.folder / f"{name}.bundle"
        self.git("bundle", "create", "-q", str(path), *refs)
        return path

    def ahead(self, branch: str, pushed: bool) -> str:
        """A branch one commit ahead of `main`, pushed to the remote or not; its sha."""
        sha = self.git("commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", f"work of {branch}")
        self.git("branch", branch, sha)
        if pushed:
            self.git("push", "-q", "origin", f"{branch}:refs/heads/{branch}")
            self.git("fetch", "-q", "origin")
        return sha

    def test_a_bundle_whose_heads_are_in_main_or_a_remote_branch_is_deleted(self) -> None:
        """#199 (c): the rescue is redundant once its heads are in `main` or on a remote branch."""
        in_main = self.bundle("in-main", "main")
        self.ahead("rescued", pushed=True)
        on_remote = self.bundle("on-remote", "rescued")
        message = self.message(self.run_hook(self.event("SessionStart")))
        self.assertFalse(in_main.exists() or on_remote.exists())
        self.assertEqual(len(message.splitlines()), 2)

    def test_a_bundle_with_a_head_not_contained_yet_is_kept_silently(self) -> None:
        """#199 (c): the heads exist here but are on no `main` and no remote branch: still the only copy."""
        self.ahead("unpushed", pushed=False)
        self.ahead("pushed", pushed=True)
        both = self.bundle("both", "unpushed", "pushed")
        result = self.run_hook(self.event())
        self.assertTrue(both.exists())
        self.assertEqual(self.message(result), "")

    def test_a_bundle_with_an_unknown_head_is_kept_and_reported(self) -> None:
        """#199 (c): a head this repository lacks cannot be shown contained."""
        other = self.home / "other"
        self.git_in(self.home, "init", "-q", "-b", "main", str(other))
        self.commit("elsewhere", folder=other)
        foreign = self.folder / "foreign.bundle"
        self.git_in(other, "bundle", "create", "-q", str(foreign), "main")
        message = self.message(self.run_hook(self.event()))
        self.assertTrue(foreign.exists())
        self.assertIn("foreign.bundle", message)

    def test_an_unreadable_bundle_is_kept_and_reported(self) -> None:
        """#199 (c): the doubt keeps."""
        broken = self.folder / "broken.bundle"
        broken.write_text("not a bundle", encoding="utf-8")
        message = self.message(self.run_hook(self.event()))
        self.assertTrue(broken.exists())
        self.assertIn("broken.bundle", message)

    def test_only_bundle_files_are_considered(self) -> None:
        """#199 (c): `*.bundle` only."""
        note = self.folder / "notes.txt"
        note.write_text("keep", encoding="utf-8")
        self.run_hook(self.event())
        self.assertTrue(note.exists())

    def test_without_the_key_no_bundle_is_touched(self) -> None:
        """#199 (c): no `rescue-bundle-dir`, no default: the step is "sans objet"."""
        self.declare(agent_cache_dir="~/cache/agents")
        in_main = self.bundle("in-main", "main")
        result = self.run_hook(self.event())
        self.assertTrue(in_main.exists())
        self.assertEqual(self.message(result), "")


@unittest.skipUnless(HAS_GIT, "the hook works on git repositories")
class Reporting(Cleanup):
    def test_subagent_stop_reports_by_system_message_one_line_per_element(self) -> None:
        """#199 (c): the documented channel of SubagentStop is `systemMessage`, and it holds no `additionalContext`."""
        self.git("branch", "worktree-agent-a1")
        self.git("branch", "worktree-agent-a2")
        result = self.run_hook(self.event())
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(set(output), {"systemMessage"})
        lines = output["systemMessage"].splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(any("worktree-agent-a1" in line for line in lines))
        self.assertTrue(any("worktree-agent-a2" in line for line in lines))

    def test_session_start_reports_by_system_message_and_additional_context(self) -> None:
        """#199 (c): at SessionStart the same lines also reach the session as `additionalContext`."""
        self.git("branch", "worktree-agent-a1")
        result = self.run_hook(self.event("SessionStart", source="startup"))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        specific = output["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "SessionStart")
        self.assertIn("worktree-agent-a1", specific["additionalContext"])
        self.assertIn("worktree-agent-a1", output["systemMessage"])

    def test_an_event_other_than_the_two_it_serves_does_nothing(self) -> None:
        """#199 (c): wired by mistake on another event, it removes nothing."""
        self.git("branch", "worktree-agent-a1")
        result = self.run_hook(self.event("Stop"))
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)
        self.assertIn("worktree-agent-a1", self.branches())

    def test_a_key_naming_a_file_instead_of_a_folder_costs_nothing_and_the_other_steps_run(self) -> None:
        """#199 (c): a cache folder that is a file leaves the branch step to run."""
        self.declare(agent_cache_dir="~/cache-file", rescue_bundle_dir="~/cache-file")
        (self.home / "cache-file").write_text("a file, not a folder", encoding="utf-8")
        transcript = self.home / "transcript.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")
        self.git("branch", "worktree-agent-a1")
        result = self.run_hook(self.event(agent_transcript_path=str(transcript)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("worktree-agent-a1", self.branches())


class Declaration(unittest.TestCase):
    def hook_groups(self, event: str) -> list[dict[str, object]]:
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        return [
            hook for group in hooks.get(event, []) for hook in group["hooks"]
            if "agent_cleanup.py" in hook.get("command", "")
        ]

    def test_hooks_json_binds_the_hook_to_both_events_as_an_observer_that_never_blocks(self) -> None:
        """#199 (c): SubagentStop and SessionStart, `; exit 0` and no `exit 2` (which would hold the agent
        at SubagentStop), no `onFailure: block`, and a `timeout`."""
        for event in ("SubagentStop", "SessionStart"):
            with self.subTest(event=event):
                found = self.hook_groups(event)
                self.assertEqual(len(found), 1, found)
                hook = found[0]
                command = str(hook["command"])
                self.assertEqual(
                    command, 'uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/hooks/agent_cleanup.py"; exit 0',
                )
                self.assertNotIn("exit 2", command)
                self.assertNotIn("onFailure", hook)
                self.assertIsInstance(hook.get("timeout"), int)
                self.assertTrue(0 < int(str(hook["timeout"])) <= 60)

    def test_hooks_json_describes_the_cleanup(self) -> None:
        text = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["description"]
        self.assertIn("cleanup after a finished agent", text)

    def test_the_template_documents_both_keys_and_this_repository_declares_them_absent(self) -> None:
        template = (support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8")
        factory = (support.REPO_ROOT / "docs" / "agents" / "usine.md").read_text(encoding="utf-8")
        for key in ("agent-cache-dir", "rescue-bundle-dir"):
            with self.subTest(key=key):
                self.assertIn(f"- `{key}` : `<", template)
                self.assertIn(f"`{key}`", factory.split("## Clés absentes")[1])


@unittest.skipUnless(HAS_GIT, "the hook works on git repositories")
class FailsOpen(Cleanup):
    def test_an_event_it_cannot_read_exits_zero_and_says_nothing(self) -> None:
        """#199 (c): the hook never blocks, never exits 2, which would hold the agent at SubagentStop."""
        for stdin in ("", "not json", "[]", '{"cwd": 3}'):
            with self.subTest(stdin=stdin):
                result = self.run_hook(stdin)
                self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    def test_outside_a_git_repository_it_does_nothing(self) -> None:
        """#199 (c): no repository, nothing to clean, nothing printed."""
        folder = self.home / "plain"
        folder.mkdir()
        result = self.run_hook(self.event(cwd=str(folder)), folder)
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)
        self.assertTrue(self.repo.exists())


if __name__ == "__main__":
    unittest.main()
