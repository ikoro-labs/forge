"""ikoro-labs/forge#345 B6 : this repository holds its sensitive keys in `usine-gardes.md`, not in `usine.md`.

`usine.md` is then free: an ordinary PR changes it. `usine-gardes.md` is the protected path, in the key
`protected-path` and in `.github/CODEOWNERS`. These tests read the two files of this repository as the PR
holds them; the loader's reading on `origin/main` is played in a throwaway repository.
"""

import unittest
from pathlib import Path

import support
from test_codeowners import owned_patterns
from test_usine_guard_file import GUARD_PATH, USINE, project
from usine import SENSITIVE_KEYS, load_checked, parse

FREE_FILE = support.REPO_ROOT / "docs" / "agents" / "usine.md"
GUARD_FILE = support.REPO_ROOT / "docs" / "agents" / "usine-gardes.md"

# What this repository declares among the sensitive keys; a key it does not declare is listed in the
# section "Clés absentes" of the guard file, with its reason.
DECLARED = {
    "accepting-human", "agent-autonomy", "budget-action", "e2e-run-limits", "protected-path",
    "run-budget", "run-limits", "slo", "ticket-pr-cap", "ticket-pr-cap-exempt", "ticket-pr-cap-small",
    "ticket-pr-cap-since",
}  # fmt: skip


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class UsineMdIsFree(unittest.TestCase):
    def test_b6_usine_md_holds_no_sensitive_key(self) -> None:
        """#345 B6: not one line of `usine.md` is a key the loader would drop."""
        self.assertEqual(sorted(set(parse(read(FREE_FILE))) & SENSITIVE_KEYS), [])


class TheGuardFileHoldsTheSensitiveKeys(unittest.TestCase):
    def test_b6_the_guard_file_holds_sensitive_keys_only_and_each_one_this_repository_declares(self) -> None:
        """#345 B6: no free key in `usine-gardes.md` (it would be ignored and reported), and none missing."""
        self.assertTrue(GUARD_FILE.is_file(), "docs/agents/usine-gardes.md is missing")
        held = set(parse(read(GUARD_FILE)))
        self.assertEqual(sorted(held - SENSITIVE_KEYS), [])
        self.assertEqual(sorted(DECLARED - held), [])
        self.assertEqual(sorted(held - DECLARED), [])

    def test_b6_a_sensitive_key_this_repository_leaves_out_is_named_with_its_reason(self) -> None:
        """#345 B6: an absent key is a decision (the step is « sans objet »), so the protected file says why."""
        absent = read(GUARD_FILE).split("## Clés absentes", 1)[-1]
        for key in sorted(SENSITIVE_KEYS - DECLARED):
            with self.subTest(key=key):
                self.assertIn(f"`{key}`", absent)

    def test_b6_a_loader_reading_origin_main_gets_the_values_of_the_staff_decision(self) -> None:
        """#345 B6: the two files as `origin/main` would hold them give the keys, with no notice."""
        on_main = {GUARD_PATH: read(GUARD_FILE), USINE: read(FREE_FILE)}
        with project(on_main) as where:
            loaded = load_checked(where)
        self.assertEqual((loaded.notices, loaded.unreadable), ([], None))
        config = loaded.config
        self.assertEqual(config["ticket-pr-cap"], ["6"])
        self.assertEqual(config["ticket-pr-cap-small"], ["50"])
        self.assertEqual(config["ticket-pr-cap-exempt"], ["chore(pin)", "chore(release)"])
        self.assertEqual(config["ticket-pr-cap-since"], ["2026-11-23"])
        self.assertEqual(config["run-limits"], ["2000 | 300"])
        self.assertEqual(config["run-budget"], ["4096 | 12 | 2 | 300"])
        self.assertEqual(config["e2e-run-limits"], ["2000 | 1800"])
        self.assertEqual(config["agent-autonomy"], ["on"])
        self.assertEqual(config["accepting-human"], ["kevin_simo | ikoro-labs"])
        self.assertEqual(len(config["slo"]), 9)
        self.assertEqual(config["budget-action"], [f"{line.split(' | ')[0]} | alert" for line in config["slo"]])
        self.assertEqual(config["merge-method"], ["merge"])


class TheGuardFileIsTheProtectedPath(unittest.TestCase):
    def test_b6_protected_path_names_the_guard_file_and_no_longer_usine_md(self) -> None:
        """#345 B6: the key lists the guard file, not `usine.md`, beside the three paths it already held."""
        protected = parse(read(GUARD_FILE)).get("protected-path", [])
        self.assertIn("docs/agents/usine-gardes.md", protected)
        self.assertNotIn("docs/agents/usine.md", protected)
        self.assertEqual(
            sorted(set(protected) - {"docs/agents/usine-gardes.md"}),
            [".github/CODEOWNERS", "plugins/forge/hooks/guard_", "plugins/forge/hooks/hooks.json"],
        )

    def test_b6_codeowners_holds_the_guard_file_and_no_longer_usine_md(self) -> None:
        """#345 B6: one CODEOWNERS line for the guard file, none left for `usine.md`."""
        owned = owned_patterns()
        self.assertEqual(owned.get("/docs/agents/usine-gardes.md*"), ["@sunderland-labs"])
        self.assertNotIn("/docs/agents/usine.md*", owned)
