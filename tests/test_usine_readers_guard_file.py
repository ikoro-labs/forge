"""ikoro-labs/forge#345 B1 : every script that reads `usine.md` reads `usine-gardes.md` too.

Each script is launched as a process, as Claude Code launches it, on a temporary repository under a
temporary `HOME`; none of the session's `CLAUDE_` or `GIT_` variables reaches it. Two cases hold for all
of them: a guard file git cannot read refuses (the script says so and does not go on with the keys of
`usine.md` alone), and a sensitive key held only by the guard file on `origin/main` is read. The keys of
the scripts that bound or judge the agent (`run-limits`, `run-budget`, `never-weaken`) are checked on
their own, in the script that reads them.
"""

import subprocess
import sys
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import support
from test_usine_guard_file import USINE, entry, environment, project
from usine import GUARD_PATH

SCRIPTS = support.PLUGIN / "scripts"
# A path named like the guard file but holding a directory is a file git cannot read as a file: unreadable.
UNREADABLE = {GUARD_PATH / "x": "not a file\n", USINE: entry("merge-method", "merge")}
GATE_REF = ["--base", "HEAD", "--head", "HEAD"]


def launch(
    script: str, where: Path, *argv: str, encoding: str | None = None
) -> subprocess.CompletedProcess[str]:
    """`script` in the repository `where`, as the project's directory, with a clean environment.

    Its output is read in the code page of the pipe, as most scripts write it; `encoding="utf-8"` for a
    script that sets its own output to UTF-8 (`e2e_trial`), whose accents a Windows pipe would misread."""
    home = where.parent / "home"
    env = environment(home)
    env["CLAUDE_PROJECT_DIR"] = str(where)
    return subprocess.run(  # noqa: S603 - the plugin's own script, argv built here
        [sys.executable, str(SCRIPTS / f"{script}.py"), *argv],
        cwd=where, env=env, capture_output=True, text=True, encoding=encoding, timeout=120, check=False,
    )


@contextmanager
def files(where: Path, **contents: str) -> Iterator[dict[str, str]]:
    """Write `contents` in a folder next to the repository; yield the path of each, by name."""
    with tempfile.TemporaryDirectory() as folder:
        paths = {}
        for name, text in contents.items():
            (Path(folder) / name).write_text(text, encoding="utf-8")
            paths[name] = str(Path(folder) / name)
        yield paths


DIFF = "diff --git a/x.txt b/x.txt\n--- a/x.txt\n+++ b/x.txt\n@@ -1 +1 @@\n-a\n+b\n"
VERDICT = (
    "VERDICT: REJECT\nROUND: 1\nHEAD: 3f2a9c1\nSPEC: #1: 0 criteria covered, 0 partial, 1 missing\nFINDINGS:\n"
    "- [BLOCKER] hook.py:1 | F-25 | x | probe: `tests/test_x.py` => `42`\nGATES: green\n"
)


class EveryReaderRefusesAnUnreadableGuardFile(unittest.TestCase):
    def test_b1_each_script_refuses_and_names_the_guard_file(self) -> None:
        """#345 B1: not a silent fallback on `usine.md`, whose sensitive keys the guard file now holds."""
        with project(UNREADABLE) as where, files(
            where, diff=DIFF, spec="# Spec\n", matrice="| Identifiant |\n", parcours="# Parcours\n",
            body="body\n", changed="a.txt\n", verdict=VERDICT,
        ) as f:
            root = ["--root", str(where)]
            calls = {
                "bounded_run": ["--check"],
                "commit_replay": ["--base", "HEAD", "--head", "HEAD"],
                "base_replay": ["--base", "HEAD", "--head", "HEAD"],
                "never_weaken": [f["diff"]],
                "source_ids": [f["spec"], *root],
                "ui_labels": [f["diff"], *root],
                "matrice": [f["matrice"], *root],
                "parcours": [f["parcours"], *root],
                "preuves_ecran": [f["body"], *root],
                "revue_boucle": ["declencher", "--files", f["changed"], *root],
                "lockfile_age": [*GATE_REF, *root],
                "stack_check": [*GATE_REF, *root],
                "probe_replay": [f["verdict"], *root],
                "e2e_trial": ["--projet", str(where)],
            }
            for script, argv in calls.items():
                with self.subTest(script=script):
                    done = launch(script, where, *argv)
                    self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
                    self.assertIn("usine-gardes.md", done.stdout + done.stderr)

    def test_b1_a_script_given_a_file_does_not_ask_the_repository(self) -> None:
        """#345 B1: `--usine usine-base.md` is what `forge:qc-gate` wrote from the base: read as it is."""
        with project(UNREADABLE) as where, files(where, diff=DIFF, base="") as f:
            done = launch("never_weaken", where, "--usine", f["base"], f["diff"])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("sans objet (clé never-weaken absente)", done.stdout)


class TheGuardFileKeysAreRead(unittest.TestCase):
    def test_b1_bounded_run_takes_run_limits_from_the_guard_file(self) -> None:
        """#345 B1: without the merge it exits 2, `sans objet (clé run-limits absente)`."""
        on_main = {GUARD_PATH: entry("run-limits", "2000 | 60"), USINE: "# Usine\n"}
        with project(on_main) as where:
            done = launch("bounded_run", where, "--", sys.executable, "-c", "print(42)")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("42", done.stdout)

    def test_b1_bounded_run_takes_run_budget_from_the_guard_file(self) -> None:
        """#345 B1: without the merge there is no budget of the post: stderr says `sans objet`."""
        on_main = {GUARD_PATH: entry("run-budget", "1 | 100000 | 2 | 0"), USINE: "# Usine\n"}
        with project(on_main) as where:
            done = launch("bounded_run", where, "--check")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("sans objet (clé `run-budget` absente)", done.stderr)

    def test_b1_commit_replay_finds_run_limits_in_the_guard_file(self) -> None:
        """#345 B1: without the merge it prints `sans objet (clé run-limits absente)` and replays nothing."""
        on_main = {GUARD_PATH: entry("run-limits", "2000 | 60"), USINE: entry("ci-replay", "true")}
        with project(on_main) as where:
            done = launch("commit_replay", where, "--base", "HEAD", "--head", "HEAD")
        self.assertNotIn("run-limits absente", done.stdout)
        self.assertIn("aucun commit", done.stdout)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_b1_never_weaken_reads_its_entries_in_the_guard_file(self) -> None:
        """#345 B1: the `never-weaken` entry sits in `usine-gardes.md` only; without the merge it is `sans objet`."""
        on_main = {GUARD_PATH: entry("never-weaken", "x.txt | removed-line"), USINE: "# Usine\n"}
        with project(on_main) as where, files(where, diff=DIFF) as f:
            done = launch("never_weaken", where, f["diff"])
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("APPLIES\tx.txt | removed-line", done.stdout)

    def test_b1_a_sensitive_key_left_in_usine_md_does_not_count_once_the_guard_file_is_there(self) -> None:
        """#345 B1: the loader's rule holds for the scripts: `usine.md` cannot set `never-weaken` any more."""
        on_main = {GUARD_PATH: entry("run-limits", "2000 | 60"), USINE: "# Usine\n"}
        in_tree = {USINE: entry("never-weaken", "x.txt | removed-line")}
        with project(on_main, in_tree=in_tree) as where, files(where, diff=DIFF) as f:
            done = launch("never_weaken", where, f["diff"])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("sans objet (clé never-weaken absente)", done.stdout)

    def test_b1_without_a_guard_file_the_scripts_read_usine_md_as_before(self) -> None:
        """#345 B1: absent is not unreadable: every key stays in `usine.md` until the guard file exists."""
        with project({USINE: entry("never-weaken", "x.txt | removed-line")}) as where, files(where, diff=DIFF) as f:
            done = launch("never_weaken", where, f["diff"])
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)

    def test_b1_stack_check_reads_the_guard_file_of_the_base(self) -> None:
        """#345 B1: `--base` is read at that ref, both files: a guard file in the head only is not read."""
        on_main = {USINE: entry("stack", "docs/stack.md") + entry("lockfile", "uv.lock | uv")}
        with project(on_main) as where:
            done = launch("stack_check", where, *GATE_REF, "--root", str(where))
        self.assertNotIn("usine-gardes.md", done.stdout + done.stderr)


class TheTrialLaunchesWithTheMergedKeys(unittest.TestCase):
    def test_b1_e2e_trial_reads_run_limits_from_the_guard_file(self) -> None:
        """#345 B1: the bound of the launch is `run-limits` or `e2e-run-limits`, both sensitive: no `sans objet` for it."""
        on_main = {GUARD_PATH: entry("run-limits", "2000 | 60"), USINE: "# Usine\n"}
        with project(on_main) as where:
            done = launch("e2e_trial", where, "--projet", str(where), encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("SANS-OBJET (clé `e2e-repo` absente)", done.stdout)
        self.assertNotIn("run-limits", done.stdout)

    def test_b1_the_launcher_gets_a_file_with_both_files_merged_when_no_usine_is_given(self) -> None:
        """#345 B1: the launch runs in the clone, so the launcher cannot find the project: it gets the merged file."""
        import e2e_trial
        from usine import parse

        config = {"run-limits": ["2000 | 300"], "e2e-repo": ["a/b"]}
        with tempfile.TemporaryDirectory() as folder:
            given = e2e_trial.usine_for_launcher(None, config, Path(folder))
            self.assertEqual(given.parent, Path(folder))
            self.assertEqual(parse(given.read_text(encoding="utf-8")), config)
            explicit = Path(folder) / "mine.md"
            self.assertEqual(e2e_trial.usine_for_launcher(str(explicit), config, Path(folder)), explicit.resolve())


if __name__ == "__main__":
    unittest.main()
