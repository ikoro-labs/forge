"""F-0003 EXI-17 (ticket #400): `guard_human_data` refuses an agent's write into the human's collections.

Every case runs the hook as Claude Code does, as a process fed an `ArtifactData` event on standard
input, in a temporary repository whose `origin/main` holds the keys, under a temporary `HOME` and
`USERPROFILE` and none of the session's `CLAUDE_` or `GIT_` variables: the real `~/.claude` is never
read nor written. The calls have the shape of the real tool: the artifact is named by `url`, a
`collection` is a path of slashes (`boards/b1/columns`), and a `batch` carries `writes`, each with its
own `op`, `collection` and `doc_id`.
"""

import json
import subprocess
import sys
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
PAGE = "claude.ai/artifact/abc123"
LINE = f"{PAGE} | decisions"
KEYS = {GUARD_PATH: entry("human-collections", LINE), USINE: "# Usine\n"}
SHOWN = f"Blocked by the forge plugin (guard_human_data): {LINE}"


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


def call(action: str, url: str = PAGE, collection: str = "decisions", **more: object) -> dict[str, object]:
    return {"action": action, "url": url, "collection": collection, **more}


class Refuses(unittest.TestCase):
    def refused(self, done: subprocess.CompletedProcess[str], *shown: str) -> None:
        """The hook refused (exit 2) with its own message, so a missing script cannot pass for a refusal."""
        self.assertEqual(done.returncode, 2, done.stderr)
        for text in shown or (SHOWN,):
            self.assertIn(text, done.stderr)
        self.assertTrue(done.stderr.startswith("Blocked by the forge plugin (guard_human_data): "), done.stderr)


class AWriteIntoAHumanCollectionIsRefused(Refuses):
    def test_f_0003_a1_each_write_action_is_refused_with_the_page_and_the_collection(self) -> None:
        """F-0003 A1: `set`, `update`, `str_replace` and `delete` on the listed artifact and collection exit 2."""
        with project(KEYS) as where:
            for action in ("set", "update", "str_replace", "delete"):
                with self.subTest(action=action):
                    done = run(where, call(action, doc_id="d1", data={"secret": "CONTENU-DU-CLIC"}), "forge:coder")
                    self.refused(done, SHOWN, "only from the human")
                    self.assertNotIn("CONTENU-DU-CLIC", done.stderr)

    def test_f_0003_a1_the_artifact_is_told_by_its_id_whatever_the_form_of_the_url(self) -> None:
        """F-0003 A1: scheme, trailing slash, query and the `code/` form of the same id are the same artifact."""
        with project(KEYS) as where:
            for url in (
                f"https://{PAGE}",
                f"{PAGE}/",
                f"https://{PAGE}?tab=1#top",
                "claude.ai/code/artifact/abc123",
                "claude.ai/artifact/ABC123",
            ):
                with self.subTest(url=url):
                    self.refused(run(where, call("set", url=url, doc_id="d1")))

    def test_f_0003_a1_a_sub_collection_of_a_human_collection_is_refused_as_the_collection_is(self) -> None:
        """F-0003 A1: `decisions/d1/notes` is under `decisions` (a path of slashes): refused, at any depth."""
        with project(KEYS) as where:
            for collection in ("decisions/d1/notes", "decisions/d1/notes/n1/deep", "/decisions//d1/notes/"):
                with self.subTest(collection=collection):
                    self.refused(run(where, call("set", collection=collection, doc_id="x")))

    def test_f_0003_a1_a_human_collection_that_is_itself_a_sub_collection_is_told_by_its_segments(self) -> None:
        """F-0003 A1: the key lists `boards/b1/columns`: it and what is under it are refused, `boards/b1` is not."""
        line = f"{PAGE} | boards/b1/columns"
        with project({GUARD_PATH: entry("human-collections", line), USINE: "# Usine\n"}) as where:
            for collection in ("boards/b1/columns", "boards/b1/columns/c1/cards"):
                with self.subTest(refused=collection):
                    self.refused(run(where, call("set", collection=collection, doc_id="x")), line)
            for collection in ("boards", "boards/b1/cards", "boards/b2/columns"):
                with self.subTest(passes=collection):
                    self.assertEqual(run(where, call("set", collection=collection, doc_id="x")).returncode, 0)


def batch(*writes: object, url: str = PAGE) -> dict[str, object]:
    """A `batch` call: the artifact once at the top, each write with its own `op`, `collection` and `doc_id`."""
    return {"action": "batch", "url": url, "writes": list(writes)}


def operation(op: str, collection: str, doc_id: str = "d1", **more: object) -> dict[str, object]:
    return {"op": op, "collection": collection, "doc_id": doc_id, **more}


class ABatchIsRefusedWhole(Refuses):
    def test_f_0003_a2_one_operation_on_the_listed_collection_refuses_the_whole_call_in_any_order(self) -> None:
        """F-0003 A2: a `batch` with one operation on the collection or under it exits 2, first or last."""
        with project(KEYS) as where:
            for bad in (operation("update", "decisions"), operation("delete", "decisions/d1/notes")):
                writes = [operation("set", "notes", data={"secret": "CONTENU-DU-CLIC"}), bad]
                for order in (writes, writes[::-1]):
                    with self.subTest(bad=bad["collection"], first=order[0]["collection"]):
                        done = run(where, batch(*order))
                        self.refused(done, SHOWN)
                        self.assertNotIn("CONTENU-DU-CLIC", done.stderr)

    def test_f_0003_a2_a_batch_that_spares_the_collection_passes(self) -> None:
        """F-0003 A2: every operation on another collection, or on the same collection of another artifact, exits 0."""
        with project(KEYS) as where:
            self.assertEqual(run(where, batch(operation("set", "notes"), operation("delete", "decisions2"))).returncode, 0)
            self.assertEqual(
                run(where, batch(operation("set", "decisions"), url="claude.ai/artifact/zzz999")).returncode, 0
            )

    def test_f_0003_a2_an_operation_that_names_no_readable_collection_refuses_the_call(self) -> None:
        """F-0003 A2: an operation the guard cannot read could be a write into the collection: refused whole."""
        with project(KEYS) as where:
            for unreadable in ({"op": "set", "doc_id": "d1"}, {"op": "set", "collection": 7}, "set", None):
                with self.subTest(operation=repr(unreadable)):
                    self.refused(run(where, batch(operation("set", "notes"), unreadable)))
            self.refused(run(where, {"action": "batch", "url": PAGE, "writes": "?"}))
            self.refused(run(where, {"action": "batch", "url": PAGE}))


class OtherCallsPass(unittest.TestCase):
    def test_f_0003_a3_every_read_of_the_collection_passes(self) -> None:
        """F-0003 A3: `get`, `list`, `query` and `profiles` on the listed collection, and under it, exit 0."""
        with project(KEYS) as where:
            for action in ("get", "list", "query", "profiles"):
                for collection in ("decisions", "decisions/d1/notes"):
                    with self.subTest(read=action, collection=collection):
                        self.assertEqual(run(where, call(action, collection=collection)).returncode, 0)

    def test_f_0003_a3_another_collection_and_another_artifact_pass(self) -> None:
        """F-0003 A3: a write into `notes`, into `decisions2` (not under `decisions`), or into `decisions` of another artifact exits 0."""
        with project(KEYS) as where:
            for name, tool_input in (
                ("another collection", call("set", collection="notes")),
                ("a name that starts the same", call("set", collection="decisions2")),
                ("a name that starts the same, deeper", call("set", collection="decisions-old/d1/notes")),
                ("the parent of the listed collection", call("set", collection="boards")),
                ("the same collection of another artifact", call("set", url="claude.ai/artifact/zzz999")),
                ("an id that only starts the same", call("set", url="claude.ai/artifact/abc1234")),
            ):
                with self.subTest(write=name):
                    self.assertEqual(run(where, tool_input).returncode, 0)


def keys(*values: str) -> dict[Path, str]:
    return {GUARD_PATH: "".join(entry("human-collections", value) for value in values), USINE: "# Usine\n"}


class AnUnreadableLineClosesEveryWrite(Refuses):
    BAD = (
        f"{PAGE} decisions",
        f"{PAGE} | ",
        " | decisions",
        "Tableau | decisions",
        f"{PAGE} | /",
    )

    def test_f_0003_a4_a_line_that_cannot_be_read_refuses_any_write_and_is_cited(self) -> None:
        """F-0003 A4: no separator, an empty part, a page that is no artifact URL: every write refused, the line cited."""
        for bad in self.BAD:
            with self.subTest(line=bad), project(keys(bad)) as where:
                done = run(where, call("set", url="claude.ai/artifact/zzz999", collection="notes"))
                self.refused(done, bad.strip(), "human-collections")
                self.assertEqual(run(where, batch(operation("set", "notes"), url="claude.ai/artifact/zzz999")).returncode, 2)

    def test_f_0003_a4_the_reads_still_pass(self) -> None:
        """F-0003 A4: with a line that cannot be read, a read of any artifact exits 0."""
        with project(keys("Tableau | decisions")) as where:
            self.assertEqual(run(where, call("get", url="claude.ai/artifact/zzz999", collection="notes")).returncode, 0)

    def test_f_0003_a4_one_good_line_does_not_hide_a_bad_one(self) -> None:
        """F-0003 A4: with a good line then a bad one, or the reverse, a write on another artifact is refused and cites the bad line."""
        for lines in ((LINE, "oups"), ("oups", LINE)):
            with self.subTest(lines=lines), project(keys(*lines)) as where:
                self.refused(run(where, call("set", url="claude.ai/artifact/zzz999", collection="notes")), "oups")


def refusals(where: Path) -> Path:
    return where.parent / "home" / ".claude" / "hooks" / "state" / "refusals"


def journal(where: Path) -> list[dict[str, str]]:
    return [
        json.loads(text)
        for path in sorted(refusals(where).glob("*.jsonl"))
        for text in path.read_text(encoding="utf-8").splitlines()
    ]


class ARefusalIsJournaled(unittest.TestCase):
    FIELDS = ("guard", "rule", "agent", "repo", "branch", "verb")

    def test_f_0003_a5_a_refusal_leaves_one_line_and_never_the_content(self) -> None:
        """F-0003 A5: guard, rule `human-collection`, agent, repo, branch and verb; nothing of the written data."""
        with project(KEYS) as where:
            tool_input = call("set", doc_id="DOC-SECRET-7", data={"secret": "CONTENU-DU-CLIC"})
            self.assertEqual(run(where, tool_input, "forge:coder").returncode, 2)
            lines = journal(where)
            self.assertEqual(len(lines), 1)
            self.assertEqual(
                {name: lines[0][name] for name in self.FIELDS},
                {
                    "guard": "guard_human_data",
                    "rule": "human-collection",
                    "agent": "forge:coder",
                    "repo": "depot",
                    "branch": "feat/x",
                    "verb": "ArtifactData write",
                },
            )
            written = "".join(path.read_text(encoding="utf-8") for path in refusals(where).glob("*.jsonl"))
            for secret in ("CONTENU-DU-CLIC", "DOC-SECRET-7", PAGE):
                self.assertNotIn(secret, written)

    def test_f_0003_a5_a_batch_and_an_unreadable_line_are_journaled_under_their_own_rule(self) -> None:
        """F-0003 A5: a refused batch is `human-collection`, a refusal on a line that cannot be read is `unreadable-key-line`."""
        with project(KEYS) as where:
            self.assertEqual(run(where, batch(operation("set", "decisions"))).returncode, 2)
            self.assertEqual([line["rule"] for line in journal(where)], ["human-collection"])
        with project(keys("oups")) as where:
            self.assertEqual(run(where, call("set")).returncode, 2)
            self.assertEqual([line["rule"] for line in journal(where)], ["unreadable-key-line"])

    def test_f_0003_a5_a_call_that_passes_leaves_no_line(self) -> None:
        """F-0003 A5: a read, and a write that spares the collection, leave no journal at all."""
        with project(KEYS) as where:
            self.assertEqual(run(where, call("get")).returncode, 0)
            self.assertEqual(run(where, call("set", collection="notes")).returncode, 0)
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


class AFailingGuardRefuses(Refuses):
    def test_f_0003_a6_the_entry_filters_on_the_tool_and_turns_a_crash_or_a_timeout_into_a_refusal(self) -> None:
        """F-0003 A6: matcher `ArtifactData`, `|| exit 2`, `"onFailure": "block"` and a `timeout`."""
        found = hook_entry()
        self.assertEqual(found["matcher"], "ArtifactData")
        command = str(found["command"])
        self.assertTrue(command.endswith("|| exit 2"), command)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/guard_human_data.py", command)
        self.assertEqual(found["onFailure"], "block")
        self.assertEqual(found["timeout"], 60)

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
        """F-0003 A6: not JSON, no `tool_input`, no readable action, not a mapping: exit 2 and a line in the journal."""
        with project(KEYS) as where:
            env = environment(where.parent / "home")
            events = (
                "not json",
                json.dumps({"cwd": str(where)}),
                json.dumps({"cwd": str(where), "tool_input": {}}),
                json.dumps({"cwd": str(where), "tool_input": {"action": ["set"]}}),
                json.dumps({"cwd": str(where), "tool_input": "set"}),
            )
            for text in events:
                with self.subTest(event=text[:30]):
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
                    self.refused(done, "could not read the tool call")
            self.assertEqual({line["rule"] for line in journal(where)}, {"unreadable-event"})
            self.assertEqual(len(journal(where)), len(events))

    def test_f_0003_a6_a_guard_file_that_cannot_be_read_refuses_a_write_and_lets_a_read_pass(self) -> None:
        """F-0003 A6: the ref lists the guard file and it cannot be read: the key cannot be told, a write exits 2."""
        with project(KEYS) as where:
            lose_the_guard_file(where, where.parent / "home")
            done = run(where, call("set", url="claude.ai/artifact/zzz999", collection="notes"))
            self.refused(done, "cannot be read", "cannot be told")
            self.assertEqual([line["rule"] for line in journal(where)], ["unreadable-key"])
            self.assertEqual(run(where, call("get")).returncode, 0)


class TheKeyIsReadOnOriginMain(Refuses):
    def test_f_0003_a7_a_line_removed_in_the_working_tree_still_refuses(self) -> None:
        """F-0003 A7: the line is gone from the guard file on disk (the PR), still on `origin/main`: refused with its message."""
        with project(KEYS, in_tree={GUARD_PATH: "# Gardes\n"}) as where:
            self.refused(run(where, call("set")))
        with project(KEYS, in_tree={GUARD_PATH: ""}) as where:
            (where / GUARD_PATH).unlink()
            self.refused(run(where, call("set")))

    def test_f_0003_a7_a_line_added_in_the_working_tree_is_not_read(self) -> None:
        """F-0003 A7: a line only on disk, in either file, is not read: another collection passes."""
        line = entry("human-collections", f"{PAGE} | notes")
        with project(KEYS, in_tree={GUARD_PATH: line, USINE: line}) as where:
            self.assertEqual(run(where, call("set", collection="notes")).returncode, 0)

    def test_f_0003_a7_while_the_guard_file_is_absent_the_key_is_read_in_usine_md_on_origin_main(self) -> None:
        """F-0003 A7: no guard file on `origin/main` yet: `usine.md` as `origin/main` holds it speaks, not the disk."""
        on_main = {USINE: entry("human-collections", LINE)}
        with project(on_main, in_tree={USINE: "# Usine\n"}) as where:
            self.refused(run(where, call("set")))
        with project({USINE: "# Usine\n"}, in_tree={USINE: entry("human-collections", LINE)}) as where:
            self.assertEqual(run(where, call("set")).returncode, 0)

    def test_f_0003_a7_the_key_is_sensitive_so_usine_md_cannot_carry_it(self) -> None:
        """F-0003 A7: `human-collections` is in `SENSITIVE_KEYS`: with a guard file on `origin/main`, `usine.md` cannot add it."""
        self.assertIn("human-collections", SENSITIVE_KEYS)
        on_main = {GUARD_PATH: "# Gardes\n", USINE: entry("human-collections", LINE)}
        with project(on_main) as where:
            self.assertEqual(run(where, call("set")).returncode, 0)
            self.assertNotIn("human-collections", load(where))


if __name__ == "__main__":
    unittest.main()
