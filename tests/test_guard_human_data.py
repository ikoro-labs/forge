"""F-0003 EXI-17 (ticket #400): `guard_human_data` refuses an agent's write into the human's collections.

Every case runs the hook as Claude Code does, as a process fed an `ArtifactData` event on standard
input, in a temporary repository whose `origin/main` holds the keys, under a temporary `HOME` and
`USERPROFILE` and none of the session's `CLAUDE_` or `GIT_` variables: the real `~/.claude` is never
read nor written.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path

import support
from test_usine_guard_file import (
    GUARD_PATH,
    USINE,
    entry,
    environment,
    lose_the_guard_file,
    project,
)
from usine import SENSITIVE_KEYS, load

HOOK = support.PLUGIN / "hooks" / "guard_human_data.py"
LINE = "Tableau | decisions"
KEYS = {GUARD_PATH: entry("human-collections", LINE), USINE: "# Usine\n"}


def run(where: Path, tool_input: Mapping[str, object], agent: str | None = None) -> subprocess.CompletedProcess[str]:
    """The hook, in `where`, fed one `ArtifactData` call."""
    event: dict[str, object] = {"tool_name": "ArtifactData", "tool_input": tool_input, "cwd": str(where)}
    if agent is not None:
        event["agent_type"] = agent
    return subprocess.run(  # noqa: S603 - the interpreter running this suite, a fixed script
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        env=environment(where.parent / "home"),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def call(action: str, page: str = "Tableau", collection: str = "decisions", **more: object) -> dict[str, object]:
    return {"action": action, "page": page, "collection": collection, **more}


class AWriteIntoAHumanCollectionIsRefused(unittest.TestCase):
    def test_f_0003_a1_each_write_action_is_refused_with_the_page_and_the_collection(self) -> None:
        """F-0003 A1: `set`, `update`, `str_replace` and `delete` on the listed page and collection exit 2."""
        with project(KEYS) as where:
            for action in ("set", "update", "str_replace", "delete"):
                with self.subTest(action=action):
                    done = run(where, call(action, doc="d1", data={"secret": "CONTENU-DU-CLIC"}), "forge:coder")
                    self.assertEqual(done.returncode, 2, done.stderr)
                    self.assertTrue(
                        done.stderr.startswith("Blocked by the forge plugin (guard_human_data): Tableau | decisions"),
                        done.stderr,
                    )
                    self.assertIn("only from the human", done.stderr)
                    self.assertNotIn("CONTENU-DU-CLIC", done.stderr)

    def test_f_0003_a2_one_operation_of_a_batch_refuses_the_whole_call(self) -> None:
        """F-0003 A2: a `batch` with one operation on the listed collection exits 2, whatever the others are."""
        with project(KEYS) as where:
            writes = [
                {"action": "set", "collection": "notes", "doc": "n1", "data": {}},
                {"action": "update", "collection": "decisions", "doc": "d1", "data": {}},
            ]
            for order in (writes, writes[::-1]):
                with self.subTest(first=order[0]["collection"]):
                    done = run(where, {"action": "batch", "page": "Tableau", "writes": order})
                    self.assertEqual(done.returncode, 2, done.stderr)
                    self.assertIn("Tableau | decisions", done.stderr)


class OtherCallsPass(unittest.TestCase):
    def test_f_0003_a3_reads_and_the_other_pages_and_collections_pass(self) -> None:
        """F-0003 A3: a read of the collection, a write of another collection and of the same name on another page exit 0."""
        with project(KEYS) as where:
            for action in ("get", "list", "query", "profiles"):
                with self.subTest(read=action):
                    self.assertEqual(run(where, call(action)).returncode, 0)
            with self.subTest(write="another collection"):
                self.assertEqual(run(where, call("set", collection="notes")).returncode, 0)
            with self.subTest(write="the same name on another page"):
                self.assertEqual(run(where, call("set", page="Autre")).returncode, 0)
            with self.subTest(write="a batch that spares the collection"):
                batch = {"action": "batch", "page": "Tableau", "writes": [{"action": "set", "collection": "notes"}]}
                self.assertEqual(run(where, batch).returncode, 0)


def keys(*values: str) -> dict[Path, str]:
    return {GUARD_PATH: "".join(entry("human-collections", value) for value in values), USINE: "# Usine\n"}


class AnUnreadableLineClosesEveryWrite(unittest.TestCase):
    def test_f_0003_a4_a_line_without_the_separator_or_with_an_empty_part_refuses_any_write_and_is_cited(self) -> None:
        """F-0003 A4: `Tableau decisions`, `Tableau |` and ` | decisions` close the writes of every page; reads pass."""
        for bad in ("Tableau decisions", "Tableau | ", " | decisions"):
            with self.subTest(line=bad), project(keys(bad)) as where:
                done = run(where, call("set", page="Autre", collection="notes"))
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn(bad.strip(), done.stderr)
                self.assertIn("human-collections", done.stderr)
                self.assertEqual(run(where, call("get", page="Autre", collection="notes")).returncode, 0)

    def test_f_0003_a4_one_good_line_does_not_hide_a_bad_one(self) -> None:
        """F-0003 A4: with a good line and a bad one, a write on another page is still refused."""
        with project(keys(LINE, "oups")) as where:
            self.assertEqual(run(where, call("set", page="Autre", collection="notes")).returncode, 2)
            self.assertEqual(run(where, call("set", collection="decisions")).returncode, 2)


def journal(where: Path) -> list[dict[str, str]]:
    folder = where.parent / "home" / ".claude" / "hooks" / "state" / "refusals"
    return [
        json.loads(text)
        for path in sorted(folder.glob("*.jsonl"))
        for text in path.read_text(encoding="utf-8").splitlines()
    ]


class ARefusalIsJournaled(unittest.TestCase):
    def test_f_0003_a5_a_refusal_leaves_one_line_and_never_the_content(self) -> None:
        """F-0003 A5: guard, rule `human-collection`, agent, repo, branch and verb; nothing of the written data."""
        with project(KEYS) as where:
            done = run(where, call("set", doc="d1", data={"secret": "CONTENU-DU-CLIC"}), "forge:coder")
            self.assertEqual(done.returncode, 2, done.stderr)
            lines = journal(where)
            self.assertEqual(len(lines), 1)
            self.assertEqual(
                {name: lines[0][name] for name in ("guard", "rule", "agent", "repo", "branch", "verb")},
                {
                    "guard": "guard_human_data",
                    "rule": "human-collection",
                    "agent": "forge:coder",
                    "repo": "depot",
                    "branch": "feat/x",
                    "verb": "ArtifactData write",
                },
            )
            folder = where.parent / "home" / ".claude" / "hooks" / "state" / "refusals"
            written = "".join(path.read_text(encoding="utf-8") for path in folder.glob("*.jsonl"))
            self.assertNotIn("CONTENU-DU-CLIC", written)
            self.assertNotIn("d1", written)

    def test_f_0003_a5_a_call_that_passes_leaves_no_line(self) -> None:
        """F-0003 A5: a read leaves no journal at all."""
        with project(KEYS) as where:
            self.assertEqual(run(where, call("get")).returncode, 0)
            self.assertEqual(journal(where), [])


def hook_entry() -> dict[str, object]:
    """The `PreToolUse` entry of `hooks.json` that runs the guard, with its matcher."""
    hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    found = [
        {**hook, "matcher": group["matcher"]}
        for group in hooks["hooks"]["PreToolUse"]
        for hook in group["hooks"]
        if "guard_human_data.py" in hook["command"]
    ]
    assert len(found) == 1, found
    return found[0]


class AFailingGuardRefuses(unittest.TestCase):
    def test_f_0003_a6_the_entry_filters_on_the_tool_and_turns_a_crash_or_a_timeout_into_a_refusal(self) -> None:
        """F-0003 A6: matcher `ArtifactData`, `|| exit 2`, `"onFailure": "block"` and a `timeout`."""
        entry_ = hook_entry()
        self.assertEqual(entry_["matcher"], "ArtifactData")
        command = str(entry_["command"])
        self.assertTrue(command.endswith("|| exit 2"), command)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/guard_human_data.py", command)
        self.assertEqual(entry_["onFailure"], "block")
        self.assertEqual(entry_["timeout"], 60)

    def test_f_0003_a6_a_missing_script_exits_2_through_the_command_of_the_entry(self) -> None:
        """F-0003 A6: the command as `hooks.json` writes it, with the script absent, still refuses (exit 2)."""
        with project(KEYS) as where:
            env = {**environment(where.parent / "home"), "CLAUDE_PLUGIN_ROOT": str(where.parent / "empty")}
            done = subprocess.run(  # noqa: S602 - the command line of hooks.json, as Claude Code runs it, in a shell
                str(hook_entry()["command"]),
                shell=True,
                input=json.dumps({"tool_name": "ArtifactData", "tool_input": call("set"), "cwd": str(where)}),
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            self.assertEqual(done.returncode, 2, done.stderr)

    def test_f_0003_a6_an_event_the_guard_cannot_read_is_refused_when_the_key_is_there(self) -> None:
        """F-0003 A6: not JSON, no `tool_input`, or no readable action: exit 2 and a line in the journal."""
        with project(KEYS) as where:
            env = environment(where.parent / "home")
            for text in ("not json", json.dumps({"cwd": str(where)}), json.dumps({"cwd": str(where), "tool_input": {}})):
                with self.subTest(event=text[:20]):
                    done = subprocess.run(  # noqa: S603 - the interpreter running this suite, a fixed script
                        [sys.executable, str(HOOK)],
                        input=text,
                        env={**env, "PWD": str(where)},
                        cwd=where,
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=60,
                    )
                    self.assertEqual(done.returncode, 2, done.stderr)
                    self.assertIn("guard_human_data", done.stderr)
            self.assertEqual(len(journal(where)), 3)


class TheKeyIsReadOnOriginMain(unittest.TestCase):
    def test_f_0003_a7_a_line_removed_in_the_working_tree_still_refuses(self) -> None:
        """F-0003 A7: the line is gone from the guard file on disk (the PR), still on `origin/main`: exit 2."""
        with project(KEYS, in_tree={GUARD_PATH: "# Gardes\n"}) as where:
            self.assertEqual(run(where, call("set")).returncode, 2)

    def test_f_0003_a7_a_line_added_in_the_working_tree_is_not_read(self) -> None:
        """F-0003 A7: a line only on disk, in either file, is not read: another collection passes."""
        line = entry("human-collections", "Tableau | notes")
        with project(KEYS, in_tree={GUARD_PATH: line, USINE: line}) as where:
            self.assertEqual(run(where, call("set", collection="notes")).returncode, 0)

    def test_f_0003_a7_while_the_guard_file_is_absent_the_key_is_read_in_usine_md_on_origin_main(self) -> None:
        """F-0003 A7: no guard file on `origin/main` yet: `usine.md` as `origin/main` holds it speaks, not the disk."""
        on_main = {USINE: entry("human-collections", LINE)}
        with project(on_main, in_tree={USINE: "# Usine\n"}) as where:
            self.assertEqual(run(where, call("set")).returncode, 2)

    def test_f_0003_a6_a_guard_file_that_cannot_be_read_refuses(self) -> None:
        """F-0003 A6: the ref lists the guard file and it cannot be read: the key cannot be told, exit 2."""
        with project(KEYS) as where:
            lose_the_guard_file(where, where.parent / "home")
            done = run(where, call("set", page="Autre", collection="notes"))
            self.assertEqual(done.returncode, 2, done.stderr)
            self.assertIn("cannot be read", done.stderr)


class TheKeyBoundsTheAgent(unittest.TestCase):
    def test_f_0003_a7_the_key_is_sensitive_so_usine_md_cannot_carry_it(self) -> None:
        """F-0003 A7: `human-collections` is in `SENSITIVE_KEYS`: the loader drops it from `usine.md`."""
        self.assertIn("human-collections", SENSITIVE_KEYS)
        with project({GUARD_PATH: "# Gardes\n", USINE: "# Usine\n"}, in_tree={USINE: entry("human-collections", LINE)}) as where:
            self.assertNotIn("human-collections", load(where))

    def test_f_0003_a8_the_template_gives_the_key_a_line_and_the_page_says_it_is_not_applicable_without_it(self) -> None:
        """F-0003 A8: the template of `usine.md` has the key line; `docs/usine-autonome.md` words the absent key."""
        template = (support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8")
        self.assertIn("- `human-collections` : `<", template)
        page = " ".join((support.REPO_ROOT / "docs" / "usine-autonome.md").read_text(encoding="utf-8").split())
        self.assertIn("sans objet (clé `human-collections` absente)", page)


class WithoutTheKeyNothingIsRefused(unittest.TestCase):
    def test_f_0003_a8_the_key_absent_every_write_passes_even_an_unreadable_call(self) -> None:
        """F-0003 A8: a guard file without the key (or no guard file, or no usine at all): exit 0."""
        for name, on_main in (
            ("guard file without the key", {GUARD_PATH: entry("agent-autonomy", "on"), USINE: "# Usine\n"}),
            ("no guard file", {USINE: entry("merge-method", "merge")}),
            ("no usine file", {}),
        ):
            with self.subTest(project=name), project(on_main) as where:
                self.assertEqual(run(where, call("set")).returncode, 0)
                self.assertEqual(run(where, {"action": "batch", "writes": "?"}).returncode, 0)
                self.assertEqual(run(where, {}).returncode, 0)
                self.assertEqual(journal(where), [])

    def test_f_0003_a8_outside_a_repository_nothing_is_refused(self) -> None:
        """F-0003 A8: a directory that is no repository and holds no usine file: exit 0."""
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / "home"
            home.mkdir()
            where = Path(folder) / "depot"
            where.mkdir()
            event = {"tool_name": "ArtifactData", "tool_input": call("set"), "cwd": str(where)}
            done = subprocess.run(  # noqa: S603 - the interpreter running this suite, a fixed script
                [sys.executable, str(HOOK)],
                input=json.dumps(event),
                env=environment(home),
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            self.assertEqual(done.returncode, 0, done.stderr)


if __name__ == "__main__":
    unittest.main()
