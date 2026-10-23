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


TOLERANCES = "config/tolerances.toml | raised-number | ^rel_tol = (\\S+)"


class RaisedNumber(unittest.TestCase):
    def test_a_raised_value_applies(self) -> None:
        text = diff("config/tolerances.toml", "-rel_tol = 0.01", "+rel_tol = 0.05")
        results = check([TOLERANCES], text)
        self.assertEqual([result.status for result in results], [APPLIES])
        self.assertIn("0.01", results[0].detail)
        self.assertIn("0.05", results[0].detail)

    def test_a_lowered_or_unchanged_value_does_not_apply(self) -> None:
        lowered = diff("config/tolerances.toml", "-rel_tol = 0.05", "+rel_tol = 0.01")
        same = diff("config/tolerances.toml", "-rel_tol = 0.01", "+rel_tol = 0.01")
        self.assertEqual(statuses([TOLERANCES], lowered), [NONE])
        self.assertEqual(statuses([TOLERANCES], same), [NONE])

    def test_a_line_the_pattern_does_not_match_is_ignored(self) -> None:
        text = diff("config/tolerances.toml", "-abs_tol = 1", "+abs_tol = 9")
        self.assertEqual(statuses([TOLERANCES], text), [NONE])

    def test_a_raised_value_in_another_file_does_not_apply(self) -> None:
        text = diff("config/other.toml", "-rel_tol = 0.01", "+rel_tol = 0.05")
        self.assertEqual(statuses([TOLERANCES], text), [NONE])

    def test_values_are_paired_in_order_within_the_file(self) -> None:
        text = diff(
            "config/tolerances.toml",
            "-rel_tol = 1", "-rel_tol = 2", "+rel_tol = 1", "+rel_tol = 3",
        )
        self.assertEqual(statuses([TOLERANCES], text), [APPLIES])
        text = diff(
            "config/tolerances.toml",
            "-rel_tol = 1", "-rel_tol = 2", "+rel_tol = 1", "+rel_tol = 2",
        )
        self.assertEqual(statuses([TOLERANCES], text), [NONE])

    def test_scientific_notation_and_a_directory_path_are_read(self) -> None:
        entry = "config/ | raised-number | tol=(\\S+)"
        text = diff("config/a.cfg", "-tol=1e-6", "+tol=1e-3")
        self.assertEqual(statuses([entry], text), [APPLIES])

    def test_an_unreadable_value_on_a_changed_line_is_not_taken_for_no_change(self) -> None:
        text = diff("config/tolerances.toml", "-rel_tol = 0.01", "+rel_tol = beaucoup")
        results = check([TOLERANCES], text)
        self.assertEqual([result.status for result in results], [APPLIES])
        self.assertIn("illisible", results[0].detail)

    def test_the_parameter_is_required_and_holds_one_group(self) -> None:
        text = diff("config/tolerances.toml", "-rel_tol = 1", "+rel_tol = 2")
        missing = "config/tolerances.toml | raised-number"
        no_group = "config/tolerances.toml | raised-number | ^rel_tol = \\S+"
        broken = "config/tolerances.toml | raised-number | ^rel_tol = ("
        self.assertEqual(statuses([missing, no_group, broken], text), [INVALID] * 3)


RANKED = "docs/fonctions/ | lowered-rank | statut | certifie > valide > brouillon"


class LoweredRank(unittest.TestCase):
    def test_a_lowered_rank_applies(self) -> None:
        text = diff("docs/fonctions/tva.md", "-statut: certifie", "+statut: brouillon")
        results = check([RANKED], text)
        self.assertEqual([result.status for result in results], [APPLIES])
        self.assertIn("certifie", results[0].detail)
        self.assertIn("brouillon", results[0].detail)

    def test_a_raised_or_unchanged_rank_does_not_apply(self) -> None:
        raised = diff("docs/fonctions/tva.md", "-statut: brouillon", "+statut: valide")
        same = diff("docs/fonctions/tva.md", "-statut: valide", "+statut: valide")
        self.assertEqual(statuses([RANKED], raised), [NONE])
        self.assertEqual(statuses([RANKED], same), [NONE])

    def test_a_rank_lowered_outside_the_path_or_on_another_field_does_not_apply(self) -> None:
        elsewhere = diff("docs/autre/tva.md", "-statut: certifie", "+statut: brouillon")
        other_field = diff("docs/fonctions/tva.md", "-niveau: certifie", "+niveau: brouillon")
        self.assertEqual(statuses([RANKED], elsewhere), [NONE])
        self.assertEqual(statuses([RANKED], other_field), [NONE])

    def test_the_field_is_read_with_quotes_bold_or_an_equal_sign(self) -> None:
        for before, after in (
            ('statut = "certifie"', 'statut = "valide"'),
            ("- **statut** : certifie", "- **statut** : valide"),
            ("  statut:   certifie  ", "  statut:   valide  "),
        ):
            with self.subTest(before=before):
                text = diff("docs/fonctions/tva.md", f"-{before}", f"+{after}")
                self.assertEqual(statuses([RANKED], text), [APPLIES])

    def test_a_field_name_is_matched_whole(self) -> None:
        text = diff("docs/fonctions/tva.md", "-statut_ancien: certifie", "+statut_ancien: brouillon")
        self.assertEqual(statuses([RANKED], text), [NONE])

    def test_a_value_outside_the_scale_is_not_taken_for_a_safe_change(self) -> None:
        text = diff("docs/fonctions/tva.md", "-statut: certifie", "+statut: obsolete")
        results = check([RANKED], text)
        self.assertEqual([result.status for result in results], [APPLIES])
        self.assertIn("obsolete", results[0].detail)

    def test_a_new_file_or_a_removed_field_is_not_a_lowered_rank(self) -> None:
        added = diff("docs/fonctions/tva.md", "+statut: brouillon")
        removed = diff("docs/fonctions/tva.md", "-statut: certifie")
        self.assertEqual(statuses([RANKED], added), [NONE])
        self.assertEqual(statuses([RANKED], removed), [NONE])

    def test_the_parameter_names_a_field_and_a_scale_of_two_ranks_at_least(self) -> None:
        text = diff("docs/fonctions/tva.md", "-statut: certifie", "+statut: brouillon")
        entries = [
            "docs/fonctions/ | lowered-rank",
            "docs/fonctions/ | lowered-rank | statut",
            "docs/fonctions/ | lowered-rank | statut | certifie",
            "docs/fonctions/ | lowered-rank | statut | certifie > > brouillon",
            "docs/fonctions/ | lowered-rank | statut | certifie > certifie",
        ]
        self.assertEqual(statuses(entries, text), [INVALID] * len(entries))


if __name__ == "__main__":
    unittest.main()
