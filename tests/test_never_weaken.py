"""Ticket #5: the `never-weaken` entries, checked on a unified diff by `never_weaken.py`."""

import io
import os
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support  # noqa: F401
from never_weaken import APPLIES, INVALID, NONE, check, main

SCRIPT = support.PLUGIN / "scripts" / "never_weaken.py"


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


def real_diff(before: dict[str, bytes], after: dict[str, bytes], *flags: str) -> str:
    """The `git diff` of two states of a throwaway repository, as `git` really prints it."""
    home = tempfile.mkdtemp()  # private: never the shared temporary folder itself
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "HOME": home,
        "USERPROFILE": home,
        "GIT_CONFIG_NOSYSTEM": "1",
    }

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
            cwd=folder, env=env, check=True, capture_output=True,
        )
        return done.stdout.decode("utf-8")

    def write(state: dict[str, bytes]) -> None:
        for child in Path(folder).iterdir():
            if child.name == ".git":
                continue
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        for name, data in state.items():
            target = Path(folder) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        git("add", "-A")
        git("commit", "-q", "--allow-empty", "-m", "state")

    try:
        with tempfile.TemporaryDirectory() as folder:
            git("init", "-q")
            write(before)
            write(after)
            return git(*flags, "diff", "HEAD~1", "HEAD")
    finally:
        shutil.rmtree(home, ignore_errors=True)


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


class Command(unittest.TestCase):
    def run_main(self, usine_text: str | None, diff_text: str) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            args = [str(root / "pr.diff")]
            (root / "pr.diff").write_text(diff_text, encoding="utf-8")
            if usine_text is not None:
                (root / "usine.md").write_text(usine_text, encoding="utf-8")
                args = ["--usine", str(root / "usine.md"), *args]
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(args)
            return code, out.getvalue(), err.getvalue()

    def test_an_entry_that_applies_exits_1_and_is_named_with_its_detail(self) -> None:
        code, out, _ = self.run_main(
            f"- `never-weaken` : `{WORKFLOWS}`\n", diff(".github/workflows/t.yml", "-  lint:")
        )
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith(f"APPLIES\t{WORKFLOWS}\t"), out)

    def test_no_entry_applying_exits_0(self) -> None:
        code, out, _ = self.run_main(f"- `never-weaken` : `{WORKFLOWS}`\n", diff("README.md", "-a"))
        self.assertEqual((code, out.split("\t")[0]), (0, "NONE"))

    def test_a_malformed_entry_exits_2_even_when_another_one_applies(self) -> None:
        usine_text = f"- `never-weaken` : `{WORKFLOWS}`\n- `never-weaken` : `docs/ | removed-line | x`\n"
        code, out, _ = self.run_main(usine_text, diff(".github/workflows/t.yml", "-a"))
        self.assertEqual(code, 2)
        self.assertIn("APPLIES", out)
        self.assertIn("INVALID", out)

    def test_an_entry_missing_its_type_is_reported_never_completed(self) -> None:
        code, out, _ = self.run_main("- `never-weaken` : `docs/`\n", diff("docs/a.md", "-a"))
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("INVALID\tdocs/\t"), out)

    def test_without_the_key_the_step_is_without_object_and_names_the_key(self) -> None:
        code, out, _ = self.run_main("- `install` : `uv sync`\n", diff(".github/x", "-a"))
        self.assertEqual((code, out.strip()), (0, "sans objet (clé never-weaken absente)"))

    def test_a_missing_diff_exits_2_and_a_missing_usine_is_an_empty_config(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                code = main(["--usine", str(Path(folder) / "usine.md"), str(Path(folder) / "none.diff")])
            self.assertEqual(code, 2)
            self.assertIn("never_weaken:", err.getvalue())
            (Path(folder) / "pr.diff").write_text("", encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["--usine", str(Path(folder) / "usine.md"), str(Path(folder) / "pr.diff")])
            self.assertEqual((code, out.getvalue().strip()), (0, "sans objet (clé never-weaken absente)"))

    def test_a_pr_cannot_lift_the_guard_it_is_judged_by(self) -> None:
        usine_text = f"- `never-weaken` : `{WORKFLOWS}`\n"
        lifted = diff("docs/agents/usine.md", f"-- `never-weaken` : `{WORKFLOWS}`", "+- `install` : `x`")
        code, out, _ = self.run_main(usine_text, lifted)
        self.assertEqual(code, 1)
        self.assertIn("docs/agents/usine.md", out)
        other = diff("docs/agents/usine.md", "-- `install` : `a`", "+- `install` : `b`")
        self.assertEqual(self.run_main(usine_text, other)[0], 0)

    def test_the_diff_is_read_from_the_standard_input_with_a_dash(self) -> None:
        stdin = io.StringIO(diff(".github/workflows/t.yml", "-a"))
        with tempfile.TemporaryDirectory() as folder:
            usine_file = Path(folder) / "usine.md"
            usine_file.write_text(f"- `never-weaken` : `{WORKFLOWS}`\n", encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out), unittest.mock.patch("sys.stdin", stdin):
                code = main(["--usine", str(usine_file), "-"])
        self.assertEqual(code, 1)

    def test_the_script_runs_no_command(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for module in ("subprocess", "os.system", "os.popen", "shlex"):
            self.assertNotIn(module, source)


class RealGitDiffs(unittest.TestCase):
    """Ticket #5: diffs produced by `git diff` itself, where the hand-written ones are too kind."""

    def test_a_deleted_binary_file_under_the_path_applies(self) -> None:
        text = real_diff({"docs/signatures/ref.bin": b"\x00\x01\x02"}, {"README.md": b"x\n"})
        self.assertEqual(statuses(["docs/signatures/ | removed-line"], text), [APPLIES])

    def test_a_modified_binary_file_under_the_path_applies(self) -> None:
        text = real_diff({"docs/signatures/ref.bin": b"\x00\x01"}, {"docs/signatures/ref.bin": b"\x00\x02"})
        self.assertEqual(statuses(["docs/signatures/ | removed-line"], text), [APPLIES])

    def test_a_deleted_empty_file_under_the_path_applies(self) -> None:
        text = real_diff({"docs/signatures/ref.txt": b""}, {"README.md": b"x\n"})
        self.assertEqual(statuses(["docs/signatures/ | removed-line"], text), [APPLIES])

    def test_an_unreadable_diff_under_the_path_applies_for_the_other_types(self) -> None:
        text = real_diff({"config/tolerances.toml": b"\x00a"}, {"config/tolerances.toml": b"\x00b"})
        entries = [
            "config/tolerances.toml | raised-number | ^rel_tol = (\\S+)",
            "config/ | lowered-rank | statut | b > a",
        ]
        self.assertEqual(statuses(entries, text), [APPLIES, APPLIES])

    def test_a_binary_file_outside_the_path_does_not_apply(self) -> None:
        text = real_diff({"img/a.bin": b"\x00a"}, {"img/a.bin": b"\x00b"})
        self.assertEqual(statuses(["docs/signatures/ | removed-line"], text), [NONE])

    def test_a_non_ascii_path_is_matched_whatever_core_quotepath_says(self) -> None:
        before = {"docs/références/x.md": b"a\nb\n"}
        after = {"docs/références/x.md": b"a\n"}
        entries = ["docs/références/ | removed-line"]
        self.assertEqual(statuses(entries, real_diff(before, after)), [APPLIES])
        self.assertEqual(statuses(entries, real_diff(before, after, "-c", "core.quotePath=false")), [APPLIES])

    def test_a_non_ascii_file_entry_and_a_raised_number_are_matched(self) -> None:
        before = {"config/tolérances.toml": b"rel_tol = 1e-9\n"}
        after = {"config/tolérances.toml": b"rel_tol = 1e-3\n"}
        entry = "config/tolérances.toml | raised-number | ^rel_tol = (\\S+)"
        self.assertEqual(statuses([entry], real_diff(before, after)), [APPLIES])

    def test_a_renamed_or_removed_usine_md_lifts_the_guard(self) -> None:
        body = f"- `never-weaken` : `{WORKFLOWS}`\n".encode()
        for after in ({"docs/agents/usine-ancien.md": body}, {"usine.md": body}, {"README.md": b"x\n"}):
            text = real_diff({"docs/agents/usine.md": body}, after)
            with tempfile.TemporaryDirectory() as folder:
                (Path(folder) / "usine.md").write_bytes(body)
                (Path(folder) / "pr.diff").write_text(text, encoding="utf-8")
                with redirect_stdout(io.StringIO()):
                    code = main(["--usine", str(Path(folder) / "usine.md"), str(Path(folder) / "pr.diff")])
            self.assertEqual(code, 1, text)


class RenameKeepsItsPath(unittest.TestCase):
    """Ticket #16: `rename from` and `rename to` carry no `a/` or `b/` prefix to strip."""

    BODY = b"un\ndeux\ntrois\n"

    def test_a_root_folder_a_moved_unchanged_applies(self) -> None:
        text = real_diff({"a/seuils/ref.txt": self.BODY}, {"archive/ref.txt": self.BODY})
        self.assertIn("rename from a/seuils/ref.txt", text)
        self.assertEqual(statuses(["a/seuils/ | removed-line"], text), [APPLIES])

    def test_a_root_folder_b_moved_unchanged_applies(self) -> None:
        text = real_diff({"b/seuils/ref.txt": self.BODY}, {"archive/ref.txt": self.BODY})
        self.assertEqual(statuses(["b/seuils/ | removed-line"], text), [APPLIES])

    def test_a_file_renamed_into_a_root_folder_b_is_read_under_its_real_path(self) -> None:
        text = real_diff({"x/ref.txt": self.BODY}, {"b/y/ref.txt": self.BODY})
        self.assertEqual(statuses(["x/ | removed-line"], text), [APPLIES])
        self.assertEqual(statuses(["b/y/ | removed-line"], text), [NONE])

    def test_a_file_moved_unchanged_into_b_under_the_entry_applies(self) -> None:
        text = real_diff({"y/ref.txt": self.BODY}, {"b/y/ref.txt": self.BODY})
        self.assertEqual(statuses(["y/ | removed-line"], text), [APPLIES])


class RenameWithEdit(unittest.TestCase):
    """Ticket #16: a file leaving or entering the path while it changes is read under the entry."""

    TOLERANCES = b"[tol]\nrel_tol = 1e-3\nabs_tol = 1e-6\nname = 'seuils'\nother = 1\nmore = 2\n"
    RAISED = TOLERANCES.replace(b"1e-3", b"1e-2")
    NUMBER = "config/tolerances.toml | raised-number | ^rel_tol = (\\S+)"
    RANK = "docs/fonctions/ | lowered-rank | statut | certifie > valide > brouillon"
    FICHE = b"# Fonction\n\nstatut: certifie\nUne ligne\nUne autre\nEncore une\n"

    def test_a_renamed_file_with_a_raised_number_applies(self) -> None:
        text = real_diff({"config/tolerances.toml": self.TOLERANCES}, {"config/tol.toml": self.RAISED})
        self.assertIn("rename from config/tolerances.toml", text)
        self.assertEqual(statuses([self.NUMBER], text), [APPLIES])

    def test_a_renamed_file_with_a_lowered_rank_applies(self) -> None:
        after = {"docs/archive/f.md": self.FICHE.replace(b"certifie", b"brouillon")}
        text = real_diff({"docs/fonctions/f.md": self.FICHE}, after)
        self.assertEqual(statuses([self.RANK], text), [APPLIES])

    def test_a_file_entering_the_path_by_rename_is_still_read(self) -> None:
        text = real_diff({"x/tol.toml": self.TOLERANCES}, {"config/tolerances.toml": self.RAISED})
        self.assertEqual(statuses([self.NUMBER], text), [APPLIES])

    def test_a_renamed_file_without_a_raise_does_not_apply(self) -> None:
        text = real_diff({"config/tolerances.toml": self.TOLERANCES}, {"config/tol.toml": self.TOLERANCES})
        self.assertEqual(statuses([self.NUMBER], text), [NONE])


if __name__ == "__main__":
    unittest.main()
