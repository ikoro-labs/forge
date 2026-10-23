import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from usine import load, parse, project_root, split_value

TEMPLATE = support.PLUGIN / "templates" / "usine.md"


class Config(unittest.TestCase):
    def test_entries_are_read_and_prose_ignored(self) -> None:
        text = (
            "# Usine\n\nProse that mentions `install` : `nothing`.\n"
            "- `install`: `uv sync --locked`\n"
            "* `install` : `pnpm install --frozen-lockfile`\n"
            "- `review-grid`: `.claude/skills/reviewer/SKILL.md`\n"
        )
        self.assertEqual(
            parse(text),
            {
                "install": ["uv sync --locked", "pnpm install --frozen-lockfile"],
                "review-grid": [".claude/skills/reviewer/SKILL.md"],
            },
        )

    def test_a_missing_file_is_an_empty_config(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(load(Path(root)), {})

    def test_the_project_root_prefers_claude_project_dir(self) -> None:
        with mock.patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": "/p"}):
            self.assertEqual(project_root({"cwd": "/c"}), Path("/p"))
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(project_root({"cwd": "/c"}), Path("/c"))
            self.assertEqual(project_root(None), Path("."))

    def test_a_value_is_cut_at_its_first_separators_and_the_last_part_keeps_the_rest(self) -> None:
        self.assertEqual(
            split_value("**/*.py | uv run ruff format", 2), ["**/*.py", "uv run ruff format"]
        )
        self.assertEqual(split_value("a | b | c | d", 2), ["a", "b | c | d"])
        self.assertEqual(split_value("a | b | c | d", 3), ["a", "b", "c | d"])
        self.assertEqual(split_value("solo", 1), ["solo"])

    def test_a_value_missing_a_part_is_reported_never_completed(self) -> None:
        self.assertIsNone(split_value("**/*.py", 2))
        self.assertIsNone(split_value("a | b", 3))
        self.assertIsNone(split_value("a |b", 2))
        self.assertIsNone(split_value("a | ", 2))
        self.assertIsNone(split_value(" | b", 2))

    def test_the_template_documents_every_key_the_plugin_reads(self) -> None:
        """The agents and skills cite a key as "clé `name`"; the hooks hold theirs in strings."""
        documented = set(parse(TEMPLATE.read_text(encoding="utf-8")))
        cited: dict[str, str] = {}
        for path in support.PLUGIN.rglob("*.md"):
            if "templates" not in path.parts:
                for key in CITED.findall(path.read_text(encoding="utf-8")):
                    cited.setdefault(key, str(path.relative_to(support.PLUGIN)))
        for name in ("after_write", "guard_readonly"):
            text = (support.PLUGIN / "hooks" / f"{name}.py").read_text(encoding="utf-8")
            for key in HOOK_KEY.findall(text):
                cited.setdefault(key, f"hooks/{name}.py")
        self.assertGreater(len(cited), 10)
        missing = {key: where for key, where in cited.items() if key not in documented}
        self.assertEqual(missing, {})


CITED = re.compile(r"clé `([a-z0-9-]+)`")
HOOK_KEY = re.compile(r'(?:KEY = |config\.get\()"([a-z0-9-]+)"')


if __name__ == "__main__":
    unittest.main()
