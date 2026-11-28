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


if __name__ == "__main__":
    unittest.main()
