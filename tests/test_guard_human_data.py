"""F-0003 EXI-17 (ticket #400): `guard_human_data` refuses an agent's write into the human's collections.

Every case runs the hook as Claude Code does, as a process fed an `ArtifactData` event on standard
input, in a temporary repository whose `origin/main` holds the keys, under a temporary `HOME` and
`USERPROFILE` and none of the session's `CLAUDE_` or `GIT_` variables: the real `~/.claude` is never
read nor written.
"""

import json
import subprocess
import sys
import unittest
from collections.abc import Mapping
from pathlib import Path

import support
from test_usine_guard_file import GUARD_PATH, USINE, entry, environment, project

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


if __name__ == "__main__":
    unittest.main()
