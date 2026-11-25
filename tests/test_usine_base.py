"""ikoro-labs/forge#345 B1 : `usine_base.py` writes the `usine-base.md` that `forge:qc-gate` hands to the scripts.

The file holds both files of the base as `origin/<base>` has them, merged by the loader's rule (the
sensitive keys of `usine-gardes.md`, the free ones of `usine.md`), never the working tree: a PR cannot
lift a bound by changing the file it is judged by. A guard file git cannot read refuses: no file is
written, so no script can go on with half of the keys.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import support
from test_usine_guard_file import USINE, entry, environment, project
from usine import GUARD_PATH, parse

SCRIPT = support.PLUGIN / "scripts" / "usine_base.py"
PLUGIN_GATE = support.PLUGIN / "agents" / "qc-gate.md"


def run(where: Path, out: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    env = environment(where.parent / "home")
    return subprocess.run(  # noqa: S603 - the plugin's own script, argv built here
        [sys.executable, str(SCRIPT), "--base", "origin/main", "--root", str(where), *argv, str(out)],
        cwd=where, env=env, capture_output=True, text=True, timeout=120, check=False,
    )


class TheBaseFileMergesBothFiles(unittest.TestCase):
    def test_b1_the_file_holds_the_free_keys_of_usine_md_and_the_sensitive_keys_of_the_guard_file(self) -> None:
        """#345 B1: `bounded_run --usine usine-base.md` finds `run-limits` after the move of the keys."""
        on_main = {GUARD_PATH: entry("run-limits", "2000 | 300"), USINE: entry("merge-method", "merge")}
        in_tree = {GUARD_PATH: entry("run-limits", "9 | 9"), USINE: entry("merge-method", "squash")}
        with project(on_main, in_tree=in_tree) as where, tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "usine-base.md"
            done = run(where, out)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(parse(out.read_text(encoding="utf-8")), {"run-limits": ["2000 | 300"], "merge-method": ["merge"]})

    def test_b1_a_sensitive_key_still_in_usine_md_of_the_base_is_dropped_and_said(self) -> None:
        """#345 B1: the loader's rule: once the guard file is there, `usine.md` cannot set a bound."""
        on_main = {GUARD_PATH: entry("run-limits", "2000 | 300"), USINE: entry("run-limits", "99999 | 99999")}
        with project(on_main) as where, tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "usine-base.md"
            done = run(where, out)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(parse(out.read_text(encoding="utf-8")), {"run-limits": ["2000 | 300"]})
            self.assertIn("`run-limits` in docs/agents/usine.md is dropped", done.stderr)

    def test_b1_without_a_guard_file_on_the_base_the_file_is_usine_md(self) -> None:
        """#345 B1: before the keys move, the base has `usine.md` alone and the file is what `git show` gave."""
        with project({USINE: entry("run-limits", "2000 | 300")}) as where, tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "usine-base.md"
            done = run(where, out)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(parse(out.read_text(encoding="utf-8")), {"run-limits": ["2000 | 300"]})

    def test_b1_a_base_with_neither_file_gives_an_empty_file(self) -> None:
        """#345 B1: the scripts then say `sans objet` for each key, as they did for a base without `usine.md`."""
        with project({}) as where, tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "usine-base.md"
            done = run(where, out)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(out.read_text(encoding="utf-8"), "")


class AGuardFileGitCannotReadRefuses(unittest.TestCase):
    def test_b1_an_unreadable_guard_file_writes_nothing_and_names_the_file(self) -> None:
        """#345 B1: not a file `usine-base.md` with the free keys alone, which the gate would then take for the base."""
        on_main = {GUARD_PATH / "x": "a directory\n", USINE: entry("merge-method", "merge")}
        with project(on_main) as where, tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "usine-base.md"
            done = run(where, out)
            self.assertEqual(done.returncode, 2, done.stderr)
            self.assertIn("usine-gardes.md", done.stderr)
            self.assertFalse(out.exists())

    def test_b1_a_ref_git_cannot_read_writes_nothing(self) -> None:
        with project({USINE: entry("merge-method", "merge")}) as where, tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "usine-base.md"
            done = run(where, out, "--base", "origin/absent")
            self.assertEqual(done.returncode, 2, done.stderr)
            self.assertFalse(out.exists())


class TheGateBuildsItsFileFromBothFiles(unittest.TestCase):
    def test_b1_qc_gate_writes_usine_base_by_the_script_not_by_git_show_of_usine_md_alone(self) -> None:
        """#345 B1: every place that wrote `usine-base.md` from `usine.md` alone now calls the script."""
        text = PLUGIN_GATE.read_text(encoding="utf-8")
        self.assertFalse("git show origin/<base>:docs/agents/usine.md" in text)
        self.assertTrue('scripts/usine_base.py" --base origin/<base> usine-base.md' in text)
        self.assertTrue("docs/agents/usine-gardes.md" in text)


if __name__ == "__main__":
    unittest.main()
