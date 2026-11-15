"""The documentation rules of `after_write`: `doc-frontmatter`, `doc-index` and `doc-cap` (#199).

The seam is the hook run as Claude Code runs it: a JSON event on stdin, a throwaway git
repository as the project, the factory file written to `docs/agents/usine.md`.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401

# isort: split
from after_write import main

KEPT_VARIABLES = ("PATH", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP")


class DocsCase(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        base = Path(folder.name).resolve()
        self.home = base / "home"
        self.home.mkdir()
        self.root = base / "project"
        self.root.mkdir()
        # No CLAUDE_ variable of the session that runs the tests, and a HOME of their own.
        self.env = {key: os.environ[key] for key in KEPT_VARIABLES if key in os.environ}
        self.env.update(
            HOME=str(self.home),
            USERPROFILE=str(self.home),
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CEILING_DIRECTORIES=str(base),
        )
        patcher = mock.patch.dict("os.environ", self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.root / "docs" / "agents").mkdir(parents=True)

    def git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.org", *args],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )
        return done.stdout

    def init_repo(self) -> None:
        self.git("init", "-q", "-b", "main")

    def commit_all(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")

    def configure(self, *entries: tuple[str, str]) -> None:
        """Each entry is `(key, value)`, written as a line of the factory file."""
        text = "".join(f"- `{key}` : `{value}`\n" for key, value in entries)
        (self.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        return path

    def run_hook(self, target: Path) -> tuple[int, str]:
        event = json.dumps({"tool_input": {"file_path": str(target)}, "cwd": str(self.root)})
        err = io.StringIO()
        env = dict(self.env, CLAUDE_PROJECT_DIR=str(self.root))
        with (
            mock.patch.dict("os.environ", env, clear=True),
            mock.patch("sys.stdin", io.StringIO(event)),
            mock.patch("sys.stderr", err),
        ):
            return main(), err.getvalue()


class Frontmatter(DocsCase):
    """The `doc-frontmatter` key: a written `.md` of the pattern opens with a `type`."""

    def setUp(self) -> None:
        super().setUp()
        self.configure(("doc-frontmatter", "docs/**/*.md"))

    def test_a_document_without_front_matter_is_refused_and_says_what_to_add(self) -> None:
        """#199 (a): the refusal names the file and the front matter to add."""
        target = self.write("docs/a.md", "# A\n\nbody\n")
        code, err = self.run_hook(target)
        self.assertEqual(code, 2)
        self.assertIn("docs/a.md", err)
        self.assertIn("doc-frontmatter", err)
        self.assertIn("---\ntype: <kind>\n---", err)
        self.assertEqual(target.read_text(encoding="utf-8"), "# A\n\nbody\n")

    def test_the_script_run_as_claude_code_runs_it_exits_2_with_the_reason_on_stderr(self) -> None:
        """#199 (a): a real process, the event on stdin, the project from the environment."""
        target = self.write("docs/a.md", "# A\n")
        event = json.dumps({"tool_input": {"file_path": str(target)}, "cwd": str(self.root)})
        done = subprocess.run(
            [sys.executable, str(support.PLUGIN / "hooks" / "after_write.py")],
            input=event,
            env=dict(self.env, CLAUDE_PROJECT_DIR=str(self.root)),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(done.returncode, 2)
        self.assertIn("docs/a.md", done.stderr)
        self.assertEqual(done.stdout, "")

    def test_a_front_matter_that_is_never_closed_is_refused(self) -> None:
        """#199 (a)."""
        code, err = self.run_hook(self.write("docs/a.md", "---\ntype: adr\n\n# A\n"))
        self.assertEqual(code, 2)
        self.assertIn("never closed", err)

    def test_a_missing_or_empty_type_is_refused(self) -> None:
        """#199 (a): `type` is required and must not be empty, whatever the other keys."""
        for header in ("title: A", "type:", 'type: ""', "type: ''", "type:   ", "type: []"):
            with self.subTest(header=header):
                code, err = self.run_hook(self.write("docs/a.md", f"---\n{header}\n---\n# A\n"))
                self.assertEqual(code, 2)
                self.assertIn("type", err)

    def test_a_document_with_a_type_passes_whatever_its_other_keys(self) -> None:
        """#199 (a): flat `key: value` lines, hyphenated keys and quoted values included."""
        body = '---\ntitle: A\nlast-updated: 2026-11-15\ntype: "adr"\n---\n# A\n'
        self.assertEqual(self.run_hook(self.write("docs/a.md", body)), (0, ""))

    def test_a_byte_order_mark_does_not_hide_the_front_matter(self) -> None:
        """#199 (a)."""
        target = self.write("docs/a.md", "﻿---\ntype: adr\n---\n# A\n")
        self.assertEqual(self.run_hook(target), (0, ""))

    def test_a_file_the_pattern_does_not_cover_is_not_checked(self) -> None:
        """#199 (a): a path outside the pattern, and a covered path that is not Markdown."""
        self.assertEqual(self.run_hook(self.write("notes/a.md", "# A\n")), (0, ""))
        self.assertEqual(self.run_hook(self.write("docs/a.txt", "plain\n")), (0, ""))

    def test_the_check_only_judges_the_written_file(self) -> None:
        """#199 (a), cliquet: a tracked document without front matter blocks nothing."""
        self.init_repo()
        old = self.write("docs/old.md", "# Old, no front matter\n")
        self.commit_all()
        new = self.write("docs/new.md", "---\ntype: adr\n---\n# New\n")
        self.assertEqual(self.run_hook(new), (0, ""))
        self.assertEqual(self.run_hook(old)[0], 2)

    def test_without_the_key_nothing_is_checked(self) -> None:
        """#199 (a): no `doc-frontmatter`, step without object, no default pattern."""
        self.configure()
        self.assertEqual(self.run_hook(self.write("docs/a.md", "# A\n")), (0, ""))

    def test_a_line_that_is_not_a_pattern_is_reported_and_ignored(self) -> None:
        """#199 (a): an empty value is a typo to show, not a pattern to guess."""
        self.configure(("doc-frontmatter", ""), ("doc-frontmatter", "docs/*.md"))
        code, err = self.run_hook(self.write("docs/a.md", "---\ntype: adr\n---\n"))
        self.assertEqual(code, 2)
        self.assertIn("doc-frontmatter", err)
        self.assertIn("ignored", err)


class Index(DocsCase):
    """The `doc-index` key: the index of the covered documents, rebuilt on every covered write."""

    def setUp(self) -> None:
        super().setUp()
        self.configure(("doc-frontmatter", "docs/**/*.md"), ("doc-index", "docs/index.md"))
        self.index = self.root / "docs" / "index.md"
        self.init_repo()

    def test_the_index_lists_the_covered_typed_documents_sorted_by_path(self) -> None:
        """#199 (a): link relative to the index, type, title (`title`, else the first `# `)."""
        self.write("docs/zeta.md", "---\ntype: guide\ntitle: Zeta | the last\n---\n# Ignored\n")
        self.write("docs/adr/0002.md", "---\ntype: adr\n---\n\ntext\n\n# Second\n")
        self.write("docs/adr/0001.md", "---\ntype: adr\n---\n```\n# not a title\n```\n# First\n")
        self.write("docs/untyped.md", "# No front matter\n")
        self.write("docs/no-title.md", "---\ntype: note\n---\nbody only\n")
        self.write("notes/outside.md", "---\ntype: note\n---\n# Outside\n")
        self.commit_all()
        written = self.write("docs/new.md", "---\ntype: draft\n---\n# New, not tracked yet\n")
        self.assertEqual(self.run_hook(written), (0, ""))
        self.assertEqual(
            self.index.read_text(encoding="utf-8"),
            "---\n"
            "type: index\n"
            "---\n"
            "\n"
            "Generated by the `after_write` hook from `git ls-files`: do not edit by hand.\n"
            "\n"
            "| Document | Type | Title |\n"
            "| --- | --- | --- |\n"
            "| [adr/0001.md](adr/0001.md) | adr | First |\n"
            "| [adr/0002.md](adr/0002.md) | adr | Second |\n"
            "| [new.md](new.md) | draft | New, not tracked yet |\n"
            "| [no-title.md](no-title.md) | note |  |\n"
            "| [zeta.md](zeta.md) | guide | Zeta \\| the last |\n",
        )

    def test_the_index_never_lists_itself_and_a_hand_edit_is_undone(self) -> None:
        """#199 (a): the index holds a `type` and sits under the pattern, and is still left out."""
        doc = self.write("docs/a.md", "---\ntype: adr\n---\n# A\n")
        self.assertEqual(self.run_hook(doc), (0, ""))
        generated = self.index.read_text(encoding="utf-8")
        self.assertNotIn("index.md", generated.split("| --- | --- | --- |")[1])
        self.index.write_text("hand edited\n", encoding="utf-8")
        self.assertEqual(self.run_hook(self.index), (0, ""))
        self.assertEqual(self.index.read_text(encoding="utf-8"), generated)

    def test_the_index_is_written_only_when_its_content_changes(self) -> None:
        """#199 (a): a second write that changes nothing leaves the file alone."""
        doc = self.write("docs/a.md", "---\ntype: adr\n---\n# A\n")
        self.assertEqual(self.run_hook(doc), (0, ""))
        long_ago = 1_000_000_000
        os.utime(self.index, (long_ago, long_ago))
        self.assertEqual(self.run_hook(doc), (0, ""))
        self.assertEqual(self.index.stat().st_mtime, long_ago)
        doc.write_text("---\ntype: adr\n---\n# A, renamed\n", encoding="utf-8")
        self.assertEqual(self.run_hook(doc), (0, ""))
        self.assertNotEqual(self.index.stat().st_mtime, long_ago)
        self.assertIn("A, renamed", self.index.read_text(encoding="utf-8"))

    def test_a_refused_document_is_left_out_of_the_index_and_the_index_still_follows(self) -> None:
        """#199 (a): without a `type` the write is refused, and the row is not there."""
        good = self.write("docs/good.md", "---\ntype: adr\n---\n# Good\n")
        self.assertEqual(self.run_hook(good), (0, ""))
        bad = self.write("docs/bad.md", "# Bad\n")
        self.assertEqual(self.run_hook(bad)[0], 2)
        text = self.index.read_text(encoding="utf-8")
        self.assertIn("good.md", text)
        self.assertNotIn("bad.md", text)

    def test_a_file_the_pattern_does_not_cover_does_not_touch_the_index(self) -> None:
        """#199 (a)."""
        self.assertEqual(self.run_hook(self.write("notes/a.md", "# A\n")), (0, ""))
        self.assertFalse(self.index.exists())

    def test_without_the_index_key_no_index_is_written(self) -> None:
        """#199 (a): `doc-index` absent, step without object."""
        self.configure(("doc-frontmatter", "docs/**/*.md"))
        self.assertEqual(self.run_hook(self.write("docs/a.md", "---\ntype: adr\n---\n")), (0, ""))
        self.assertFalse(self.index.exists())

    def test_without_the_front_matter_key_no_index_is_written(self) -> None:
        """#199 (a): the index lists what `doc-frontmatter` covers; without it, nothing to list."""
        self.configure(("doc-index", "docs/index.md"))
        self.assertEqual(self.run_hook(self.write("docs/a.md", "---\ntype: adr\n---\n")), (0, ""))
        self.assertFalse(self.index.exists())

    def test_an_index_outside_the_project_is_refused_and_not_written(self) -> None:
        """#199 (a)."""
        self.configure(("doc-frontmatter", "docs/**/*.md"), ("doc-index", "../outside.md"))
        code, err = self.run_hook(self.write("docs/a.md", "---\ntype: adr\n---\n"))
        self.assertEqual(code, 2)
        self.assertIn("outside the project", err)
        self.assertFalse((self.root.parent / "outside.md").exists())

    def test_outside_a_git_repository_the_index_is_not_guessed(self) -> None:
        """#199 (a): without `git ls-files` the hook says so and leaves the index as it is."""
        (self.root / ".git").rename(self.root / "moved-git")
        code, err = self.run_hook(self.write("docs/a.md", "---\ntype: adr\n---\n"))
        self.assertEqual(code, 2)
        self.assertIn("git ls-files", err)
        self.assertFalse(self.index.exists())


if __name__ == "__main__":
    unittest.main()
