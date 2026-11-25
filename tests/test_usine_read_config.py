"""ikoro-labs/forge#345 B1 : one reader of the factory configuration for the plugin's scripts.

`usine.read_config` is what every script calls instead of parsing `usine.md` alone: the free keys of
`usine.md`, the sensitive ones of `usine-gardes.md` as `origin/main` holds it (`usine.load_checked`),
or the file a caller gives, read as it is (`forge:qc-gate` builds that file from the base). A guard
file that git cannot read refuses (the loader's `unreadable`); an absent one falls back on `usine.md`.
Every repository here is a temporary one, under a temporary `HOME`; the real `~/.claude` is never read.
"""

import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401  (puts the plugin's hooks and scripts on the import path)
import usine
from test_usine_guard_file import USINE, entry, git, project
from usine import GUARD_PATH, ConfigUnreadable, read_config, read_config_at, render


class DefaultReadMergesTheGuardFile(unittest.TestCase):
    def test_b1_the_sensitive_keys_come_from_origin_main_and_the_free_ones_from_the_tree(self) -> None:
        """#345 B1: `run-limits` is read in `usine-gardes.md` on origin/main, `merge-method` in `usine.md`."""
        on_main = {GUARD_PATH: entry("run-limits", "2000 | 300"), USINE: "# Usine\n"}
        with project(on_main, in_tree={USINE: entry("merge-method", "merge") + entry("run-limits", "9 | 9")}) as where:
            config = read_config(None, where)
        self.assertEqual(config, {"run-limits": ["2000 | 300"], "merge-method": ["merge"]})

    def test_b1_without_a_guard_file_on_origin_main_every_key_comes_from_usine_md(self) -> None:
        """#345 B1: absent is not unreadable: the loader falls back on `usine.md`, as before the file existed."""
        with project({USINE: entry("run-limits", "2000 | 300")}) as where:
            self.assertEqual(read_config(None, where), {"run-limits": ["2000 | 300"]})

    def test_b1_a_guard_file_git_cannot_read_refuses_and_names_the_file(self) -> None:
        """#345 B1: no `origin/main`: git cannot tell what the human merged, so the read fails closed."""
        with project({USINE: entry("run-limits", "2000 | 300")}) as where:
            git(where, where.parent / "home", "update-ref", "-d", "refs/remotes/origin/main")
            with self.assertRaises(ConfigUnreadable) as caught:
                read_config(None, where)
        self.assertIsInstance(caught.exception, OSError)
        self.assertIn(GUARD_PATH.as_posix(), str(caught.exception))

    def test_b1_the_guard_file_alone_still_gives_its_keys_when_usine_md_is_missing(self) -> None:
        """#345 B1: a project whose `usine.md` is absent keeps the keys of its guard file."""
        with project({GUARD_PATH: entry("run-limits", "2000 | 300")}) as where:
            self.assertEqual(read_config(None, where), {"run-limits": ["2000 | 300"]})

    def test_b1_a_missing_working_file_with_no_guard_file_is_an_empty_configuration(self) -> None:
        with project({}) as where:
            self.assertEqual(read_config(None, where), {})


class AFileGivenByTheCallerIsReadAsItIs(unittest.TestCase):
    def test_b1_the_file_of_the_caller_is_parsed_whole_and_the_repository_is_not_asked(self) -> None:
        """#345 B1: `--usine usine-base.md` is the merged file `forge:qc-gate` wrote: no second merge."""
        with tempfile.TemporaryDirectory() as folder:
            given = Path(folder) / "usine-base.md"
            given.write_text(entry("run-limits", "2000 | 300") + entry("merge-method", "merge"), encoding="utf-8")
            self.assertEqual(
                read_config(str(given), Path(folder)), {"run-limits": ["2000 | 300"], "merge-method": ["merge"]}
            )

    def test_b1_a_missing_file_of_the_caller_is_left_to_the_caller(self) -> None:
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(FileNotFoundError):
            read_config(str(Path(folder) / "absent.md"), Path(folder))


class ReadAtARef(unittest.TestCase):
    def test_b1_both_files_of_a_ref_are_merged_and_the_working_tree_is_not_read(self) -> None:
        """#345 B1: `stack_check` reads the base: `usine.md` and `usine-gardes.md` as `<ref>` holds them."""
        on_main = {GUARD_PATH: entry("run-limits", "2000 | 300"), USINE: entry("merge-method", "merge")}
        in_tree = {GUARD_PATH: entry("run-limits", "9 | 9"), USINE: entry("merge-method", "squash")}
        with project(on_main, in_tree=in_tree) as where:
            config = read_config_at(where, "refs/remotes/origin/main")
        self.assertEqual(config, {"run-limits": ["2000 | 300"], "merge-method": ["merge"]})

    def test_b1_a_ref_git_cannot_read_refuses(self) -> None:
        with project({USINE: entry("merge-method", "merge")}) as where, self.assertRaises(ConfigUnreadable):
            read_config_at(where, "refs/remotes/origin/absent")

    def test_b1_a_ref_without_usine_md_is_empty(self) -> None:
        with project({}) as where:
            self.assertEqual(read_config_at(where, "refs/remotes/origin/main"), {})


class RenderWritesWhatParseReads(unittest.TestCase):
    def test_b1_a_configuration_rendered_then_parsed_is_the_same_configuration(self) -> None:
        config = {"ci-replay": ["a | b", "c"], "run-limits": ["2000 | 300"]}
        self.assertEqual(usine.parse(render(config)), config)


if __name__ == "__main__":
    unittest.main()
