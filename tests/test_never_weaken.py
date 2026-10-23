"""Ticket #5: the `never-weaken` entries, checked on a unified diff by `never_weaken.py`."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support  # noqa: F401
from never_weaken import APPLIES, INVALID, NONE, check, main


def diff(path: str, *hunk: str, old: str | None = None) -> str:
    """A `git diff` of one file; `hunk` lines carry their ` `, `-` or `+` prefix."""
    old = old or path
    body = "\n".join(hunk)
    return (
        f"diff --git a/{old} b/{path}\nindex 111..222 100644\n--- a/{old}\n+++ b/{path}\n"
        f"@@ -1,{len(hunk)} +1,{len(hunk)} @@\n{body}\n"
    )


def deleted(path: str, *lines: str) -> str:
    body = "\n".join(f"-{line}" for line in lines)
    return (
        f"diff --git a/{path} b/{path}\ndeleted file mode 100644\nindex 111..000\n"
        f"--- a/{path}\n+++ /dev/null\n@@ -1,{len(lines)} +0,0 @@\n{body}\n"
    )


def statuses(entries: list[str], text: str) -> list[str]:
    return [result.status for result in check(entries, text)]


WORKFLOWS = ".github/workflows/ | removed-line"


class RemovedLine(unittest.TestCase):
    def test_a_line_removed_under_the_path_applies(self) -> None:
        text = diff(".github/workflows/tests.yml", " jobs:", "-  lint:", "   test:")
        results = check([WORKFLOWS], text)
        self.assertEqual([result.status for result in results], [APPLIES])
        self.assertIn(".github/workflows/tests.yml", results[0].detail)
        self.assertIn("-  lint:", results[0].detail)

    def test_a_line_only_added_under_the_path_does_not_apply(self) -> None:
        text = diff(".github/workflows/tests.yml", " jobs:", "+  lint:")
        self.assertEqual(statuses([WORKFLOWS], text), [NONE])

    def test_a_line_removed_outside_the_path_does_not_apply(self) -> None:
        text = diff("README.md", "-old line", "+new line")
        self.assertEqual(statuses([WORKFLOWS], text), [NONE])

    def test_the_path_is_a_prefix_of_the_directory_not_of_a_sibling_name(self) -> None:
        text = diff(".github/workflows-old/x.yml", "-a")
        self.assertEqual(statuses([WORKFLOWS], text), [NONE])

    def test_a_single_file_path_matches_that_file_only(self) -> None:
        entry = "config/tolerances.toml | removed-line"
        self.assertEqual(statuses([entry], diff("config/tolerances.toml", "-a")), [APPLIES])
        self.assertEqual(statuses([entry], diff("config/tolerances.toml.bak", "-a")), [NONE])

    def test_a_deleted_file_under_the_path_applies(self) -> None:
        text = deleted(".github/workflows/lint.yml", "name: lint", "on: push")
        self.assertEqual(statuses([WORKFLOWS], text), [APPLIES])

    def test_a_removed_line_that_looks_like_a_file_header_is_still_a_removed_line(self) -> None:
        text = diff(".github/workflows/tests.yml", "--- a/not-a-header", "+++ b/x")
        self.assertEqual(statuses([WORKFLOWS], text), [APPLIES])

    def test_a_file_moved_out_of_the_path_applies(self) -> None:
        text = (
            "diff --git a/.github/workflows/lint.yml b/ci/lint.yml\nsimilarity index 100%\n"
            "rename from .github/workflows/lint.yml\nrename to ci/lint.yml\n"
        )
        self.assertEqual(statuses([WORKFLOWS], text), [APPLIES])

    def test_a_file_moved_inside_the_path_does_not_apply(self) -> None:
        text = (
            "diff --git a/.github/workflows/a.yml b/.github/workflows/b.yml\nsimilarity index 100%\n"
            "rename from .github/workflows/a.yml\nrename to .github/workflows/b.yml\n"
        )
        self.assertEqual(statuses([WORKFLOWS], text), [NONE])

    def test_each_entry_is_judged_on_its_own(self) -> None:
        text = diff("docs/a.md", "-x")
        entries = [WORKFLOWS, "docs/ | removed-line"]
        self.assertEqual(statuses(entries, text), [NONE, APPLIES])


if __name__ == "__main__":
    unittest.main()
