"""ikoro-labs/forge#345 : `usine.load` reads the keys that bound the agent in `usine-gardes.md`.

The file is read as `refs/remotes/origin/main` holds it (`git show`), never in the working tree an
agent can edit. Every repository here is a temporary one, under a temporary `HOME`; none of the
session's `CLAUDE_` or `GIT_` variables reaches git, and the real `~/.claude` is never read nor
written.
"""

import os
import subprocess
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import support  # noqa: F401  met les hooks sur le chemin d'import
from usine import GUARD_PATH, SENSITIVE_KEYS, load

USINE = Path("docs") / "agents" / "usine.md"


def entry(key: str, value: str) -> str:
    return f"- `{key}` : `{value}`\n"


def environment(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "GIT_"))}
    env.update(HOME=str(home), USERPROFILE=str(home), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    return env


def git(where: Path, home: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603, S607 - fixed argv in a temporary repository
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=where,
        env=environment(home),
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return done.stdout


def write(where: Path, files: Mapping[Path, str]) -> None:
    for relative, text in files.items():
        (where / relative).parent.mkdir(parents=True, exist_ok=True)
        (where / relative).write_text(text, encoding="utf-8")


@contextmanager
def project(on_main: Mapping[Path, str], in_tree: Mapping[Path, str] | None = None) -> Iterator[Path]:
    """A repository whose `origin/main` holds the files `on_main`, and whose working tree then
    holds `in_tree` on top of them."""
    with tempfile.TemporaryDirectory() as folder:
        home = Path(folder) / "home"
        where = Path(folder) / "depot"
        home.mkdir()
        where.mkdir()
        git(where, home, "init", "-q", "-b", "feat/x")
        write(where, {Path("README.md"): "x\n", **on_main})
        git(where, home, "add", "-A")
        git(where, home, "commit", "-q", "-m", "init")
        git(where, home, "update-ref", "refs/remotes/origin/main", "HEAD")
        write(where, in_tree or {})
        old = {name: os.environ.get(name) for name in ("HOME", "USERPROFILE")}
        os.environ.update(HOME=str(home), USERPROFILE=str(home))
        try:
            yield where
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


class SensitiveKeysAreReadInTheGuardFile(unittest.TestCase):
    def test_b1_a_sensitive_key_is_the_value_origin_main_holds_not_the_working_tree_one(self) -> None:
        """#345 B1: `ticket-pr-cap` is 3 in `usine-gardes.md` on `origin/main`; 9 on disk does not count."""
        on_main = {GUARD_PATH: entry("ticket-pr-cap", "3"), USINE: entry("merge-method", "merge")}
        with project(on_main, in_tree={GUARD_PATH: entry("ticket-pr-cap", "9")}) as where:
            config = load(where)
        self.assertEqual(config["ticket-pr-cap"], ["3"])

    def test_b1_a_free_key_still_comes_from_usine_md(self) -> None:
        """#345 B1: `merge-method` is free: `usine.md` keeps it, the guard file has no say."""
        on_main = {GUARD_PATH: entry("ticket-pr-cap", "3"), USINE: entry("merge-method", "merge")}
        with project(on_main) as where:
            config = load(where)
        self.assertEqual(config["merge-method"], ["merge"])

    def test_b1_every_listed_sensitive_key_is_read_from_the_guard_file(self) -> None:
        """#345 B1: the 21 keys of the staff decision, each read there, none from `usine.md`."""
        guard = "".join(entry(key, f"guard-{key}") for key in sorted(SENSITIVE_KEYS))
        with project({GUARD_PATH: guard, USINE: "# Usine\n"}) as where:
            config = load(where)
        self.assertEqual(len(SENSITIVE_KEYS), 21)
        self.assertEqual({key: config.get(key) for key in SENSITIVE_KEYS}, {key: [f"guard-{key}"] for key in SENSITIVE_KEYS})
