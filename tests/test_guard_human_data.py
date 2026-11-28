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
from test_usine_guard_file import GUARD_PATH, USINE, entry, environment, project

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


if __name__ == "__main__":
    unittest.main()
