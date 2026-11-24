"""F-0002 C01 (ticket #306): `stack_check.py` lists the direct dependencies a PR adds and compares them to `stack`.

Every test runs on a throwaway git repository with two commits. The locks are produced by the real
`uv lock` and `npm install --package-lock-only`, not written by hand; a test whose tool is missing, or
cannot reach its registry, is skipped with the reason (never a pass that proved nothing). Nothing here
writes in the real HOME: each tool gets a throwaway one.
"""

import functools
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from stack_check import main

_CACHES = tempfile.TemporaryDirectory()  # the tools' package caches, shared by the tests of this module


def tearDownModule() -> None:
    _CACHES.cleanup()


def _tool_env(home: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("CLAUDE_")}
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        UV_CACHE_DIR=str(Path(_CACHES.name) / "uv"),
        NPM_CONFIG_CACHE=str(Path(_CACHES.name) / "npm"),
    )
    return env


def _generate(command: list[str], files: dict[str, str], produced: str) -> str:
    """Run `command` in a throwaway folder holding `files`, and return the text of `produced`."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        home = root / "home"
        home.mkdir()
        project = root / "project"
        for name, text in files.items():
            (project / name).parent.mkdir(parents=True, exist_ok=True)
            (project / name).write_text(text, encoding="utf-8")
        try:
            done = subprocess.run(command, cwd=project, env=_tool_env(home), capture_output=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise unittest.SkipTest(f"`{command[0]}` ne tourne pas : {error}") from error
        if done.returncode != 0:
            tail = done.stderr.decode("utf-8", "replace").strip().splitlines()[-1:]
            raise unittest.SkipTest(f"`{' '.join(command)}` a échoué (registre injoignable ?) : {tail}")
        return (project / produced).read_text(encoding="utf-8")


def _pyproject(name: str, dependencies: tuple[str, ...], extra: str = "") -> str:
    listed = ", ".join(f'"{dependency}"' for dependency in dependencies)
    return f'[project]\nname = "{name}"\nversion = "0.1.0"\nrequires-python = ">=3.10"\ndependencies = [{listed}]\n{extra}'


@functools.cache
def uv_lock(*dependencies: str) -> str:
    """A `uv.lock` made by `uv lock` for one project that declares `dependencies`."""
    return _generate(["uv", "lock", "--no-progress"], {"pyproject.toml": _pyproject("app", dependencies)}, "uv.lock")


@functools.cache
def npm_lock(dependencies: tuple[tuple[str, str], ...] = ()) -> str:
    """A `package-lock.json` made by `npm install --package-lock-only` for one project."""
    npm = shutil.which("npm")
    if npm is None:
        raise unittest.SkipTest("`npm` n'est pas installé")
    package = {"name": "app", "version": "1.0.0", "private": True, "dependencies": dict(dependencies)}
    command = [npm, "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund"]
    return _generate(command, {"package.json": json.dumps(package)}, "package-lock.json")


class StackCase(unittest.TestCase):
    """A throwaway repository with a base commit and a head commit."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        home = self.tmp / "home"
        home.mkdir()
        env = {"HOME": str(home), "USERPROFILE": str(home), "GIT_CONFIG_NOSYSTEM": "1"}
        patcher = unittest.mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.git("init", "--quiet")

    def git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
            cwd=self.repo, check=True, capture_output=True,
        )
        return done.stdout.decode("utf-8").strip()

    def commit(self, files: dict[str, str]) -> str:
        """Replace the tracked files by `files`, commit, and return the commit's sha."""
        for child in self.repo.iterdir():
            if child.name != ".git":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
        for name, text in files.items():
            (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / name).write_text(text, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "--quiet", "--allow-empty", "-m", "state")
        return self.git("rev-parse", "HEAD")

    def usine(self, *lines: str) -> Path:
        path = self.tmp / "usine.md"
        path.write_text("# usine\n\n" + "\n".join(f"- {line}" for line in lines) + "\n", encoding="utf-8")
        return path

    def run_check(self, usine: Path | None, base: str, head: str) -> tuple[int, list[str], str]:
        """The exit code, the output lines and the error output of the check (`usine` None: read on the base)."""
        args = ["--root", str(self.repo), "--base", base, "--head", head]
        if usine is not None:
            args += ["--usine", str(usine)]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(args)
        return code, out.getvalue().splitlines(), err.getvalue()


STACK_AND_LOCK = ("`stack` : `stack.txt`", "`lockfile` : `uv.lock | pypi`")


class StackFile(StackCase):
    def test_a1_well_formed_lines_give_no_invalid_and_a_lock_without_additions_says_none(self) -> None:
        """F-0002 A1: lines `<ecosystem> | <package> | <source>` of `pypi` and `npm` are not INVALID; nothing added is NONE."""
        stack = "pypi | requests | ADR-0001\nnpm | left-pad | session 2026-11-23 | with a bar\n"
        locks = {"uv.lock": uv_lock(), "package-lock.json": npm_lock()}
        usine = self.usine("`stack` : `stack.txt`", "`lockfile` : `uv.lock | pypi`", "`lockfile` : `package-lock.json | npm`")
        base = self.commit({**locks, "stack.txt": ""})
        head = self.commit({**locks, "stack.txt": stack})
        code, lines, _ = self.run_check(usine, base, head)
        self.assertEqual(code, 0)
        self.assertEqual(sorted({line.split("\t")[0] for line in lines}), ["ADDED", "NONE"])  # never INVALID
        self.assertEqual([line.split("\t")[:2] for line in lines if line.startswith("NONE")], [["NONE", "uv.lock"], ["NONE", "package-lock.json"]])

    def test_a2_a_malformed_line_is_invalid_with_its_number_and_never_completed(self) -> None:
        """F-0002 A2: an unknown ecosystem, a missing field or an empty name is `INVALID` at its line number."""
        stack = "pypi | requests | ADR-0001\nnpm | left-pad\ncargo | serde | ADR-0002\n\npypi |  | ADR-0003\n"
        base = self.commit({"uv.lock": uv_lock(), "stack.txt": ""})
        head = self.commit({"uv.lock": uv_lock(), "stack.txt": stack})
        code, lines, _ = self.run_check(self.usine(*STACK_AND_LOCK), base, head)
        invalid = [line.split("\t") for line in lines if line.startswith("INVALID")]
        self.assertEqual([entry[1] for entry in invalid], ["stack.txt:2", "stack.txt:3", "stack.txt:5"])
        self.assertIn("trois champs", invalid[0][3])
        self.assertIn("cargo", invalid[1][3])
        self.assertEqual(code, 2)
        self.assertFalse([line for line in lines if "left-pad" in line and not line.startswith("INVALID")])


class Comparison(StackCase):
    def test_a5_a_direct_dependency_missing_from_the_list_is_unlisted_with_the_line_to_write(self) -> None:
        """F-0002 A5: an added direct dependency absent from the list is `UNLISTED`, the line to write and the file named."""
        base = self.commit({"uv.lock": uv_lock(), "stack.txt": ""})
        head = self.commit({"uv.lock": uv_lock("idna"), "stack.txt": ""})
        code, lines, _ = self.run_check(self.usine(*STACK_AND_LOCK), base, head)
        self.assertEqual(code, 1)
        self.assertEqual(len(lines), 1)
        status, lockfile, package, detail = lines[0].split("\t")
        self.assertEqual((status, lockfile, package), ("UNLISTED", "uv.lock", "pypi idna"))
        self.assertIn("pypi | idna | <ADR ou séance>", detail)
        self.assertIn("stack.txt", detail)

    def test_a6_a_listed_dependency_with_an_empty_source_is_no_source(self) -> None:
        """F-0002 A6: an added direct dependency whose list line has an empty source is `NO SOURCE`."""
        base = self.commit({"uv.lock": uv_lock(), "stack.txt": ""})
        head = self.commit({"uv.lock": uv_lock("idna"), "stack.txt": "pypi | idna |\n"})
        code, lines, _ = self.run_check(self.usine(*STACK_AND_LOCK), base, head)
        self.assertEqual(code, 1)
        self.assertEqual([line.split("\t")[:3] for line in lines if not line.startswith("ADDED")], [["NO SOURCE", "uv.lock", "pypi idna"]])

    def test_a7_a_listed_dependency_with_a_source_is_ok_and_each_added_list_line_is_added(self) -> None:
        """F-0002 A7: an added dependency listed with its source is `OK`; a list line the PR adds is `ADDED` with its source."""
        base = self.commit({"uv.lock": uv_lock(), "stack.txt": "pypi | requests | ADR-0001\n"})
        head = self.commit(
            {"uv.lock": uv_lock("idna"), "stack.txt": "pypi | requests | ADR-0001\npypi | idna | session 2026-11-23\n"}
        )
        code, lines, _ = self.run_check(self.usine(*STACK_AND_LOCK), base, head)
        self.assertEqual(code, 0)
        rows = [line.split("\t") for line in lines]
        self.assertEqual([row[:3] for row in rows], [["ADDED", "stack.txt:2", "pypi idna"], ["OK", "uv.lock", "pypi idna"]])
        self.assertIn("session 2026-11-23", rows[0][3])
        self.assertIn("session 2026-11-23", rows[1][3])

    def test_a8_an_indirect_dependency_is_not_compared(self) -> None:
        """F-0002 A8: a package only another package needs (here the ones `requests` pulls in) is not compared."""
        base = self.commit({"uv.lock": uv_lock(), "stack.txt": ""})
        head = self.commit({"uv.lock": uv_lock("requests"), "stack.txt": "pypi | requests | ADR-0001\n"})
        lock = uv_lock("requests")
        self.assertIn('name = "urllib3"', lock)  # the lock does hold indirect packages, or this proves nothing
        code, lines, _ = self.run_check(self.usine(*STACK_AND_LOCK), base, head)
        self.assertEqual(code, 0)
        self.assertEqual([line.split("\t")[:3] for line in lines if not line.startswith("ADDED")], [["OK", "uv.lock", "pypi requests"]])

    def test_a4_pypi_names_are_the_same_whatever_the_case_dash_underscore_or_dot(self) -> None:
        """F-0002 A4: `Foo_Bar` of a lock and `foo-bar` of the list are one pypi package."""
        base = self.commit({"uv.lock": uv_lock(), "stack.txt": ""})
        head = self.commit({"uv.lock": uv_lock("typing_extensions"), "stack.txt": "pypi | Typing.Extensions | ADR-0001\n"})
        code, lines, _ = self.run_check(self.usine(*STACK_AND_LOCK), base, head)
        self.assertEqual(code, 0)
        self.assertEqual([line.split("\t")[:3] for line in lines if not line.startswith("ADDED")], [["OK", "uv.lock", "pypi typing-extensions"]])

    def test_a4_npm_names_are_not_normalized(self) -> None:
        """F-0002 A4: an npm name is compared as written: `Left-Pad` of the list is not `left-pad` of the lock."""
        usine = self.usine("`stack` : `stack.txt`", "`lockfile` : `package-lock.json | npm`")
        base = self.commit({"package-lock.json": npm_lock(), "stack.txt": ""})
        lock = npm_lock((("left-pad", "1.3.0"),))
        shouted = self.commit({"package-lock.json": lock, "stack.txt": "npm | Left-Pad | ADR-0001\n"})
        _, lines, _ = self.run_check(usine, base, shouted)
        self.assertEqual([line.split("\t")[:3] for line in lines if not line.startswith("ADDED")], [["UNLISTED", "package-lock.json", "npm left-pad"]])
        exact = self.commit({"package-lock.json": lock, "stack.txt": "npm | left-pad | ADR-0001\n"})
        code, lines, _ = self.run_check(usine, base, exact)
        self.assertEqual(code, 0)
        self.assertEqual([line.split("\t")[:3] for line in lines if not line.startswith("ADDED")], [["OK", "package-lock.json", "npm left-pad"]])


class NeverOk(StackCase):
    """A11: what cannot be read is `INVALID` or `NOT RUN` with its reason, never `OK`."""

    def test_a11_a_package_lock_without_its_root_entry_is_invalid(self) -> None:
        """F-0002 A11: a `package-lock.json` whose `packages[""]` is missing says INVALID: the direct ones cannot be told."""
        lock = json.loads(npm_lock((("left-pad", "1.3.0"),)))
        del lock["packages"][""]
        usine = self.usine("`stack` : `stack.txt`", "`lockfile` : `package-lock.json | npm`")
        base = self.commit({"package-lock.json": npm_lock(), "stack.txt": ""})
        head = self.commit({"package-lock.json": json.dumps(lock), "stack.txt": "npm | left-pad | ADR-0001\n"})
        code, lines, _ = self.run_check(usine, base, head)
        self.assertEqual(code, 2)
        rows = [line.split("\t") for line in lines if not line.startswith("ADDED")]
        self.assertEqual([row[:2] for row in rows], [["INVALID", "package-lock.json"]])
        self.assertIn('packages[""]', rows[0][3])

    def test_a11_an_unreadable_lock_or_an_unknown_lockfile_ecosystem_is_invalid(self) -> None:
        """F-0002 A11: a lock that is not a lock, and a `lockfile` entry of another ecosystem, say INVALID with the reason."""
        base = self.commit({"uv.lock": uv_lock(), "stack.txt": ""})
        head = self.commit({"uv.lock": "this is not a lock\n", "stack.txt": "pypi | idna | ADR-0001\n"})
        code, lines, _ = self.run_check(self.usine(*STACK_AND_LOCK), base, head)
        self.assertEqual(code, 2)
        rows = [line.split("\t") for line in lines if not line.startswith("ADDED")]
        self.assertEqual([row[:2] for row in rows], [["INVALID", "uv.lock"]])
        self.assertIn("uv.lock", rows[0][3])
        usine = self.usine("`stack` : `stack.txt`", "`lockfile` : `Cargo.lock | cargo`")
        code, lines, _ = self.run_check(usine, base, head)
        self.assertEqual(code, 2)
        statuses = [line.split("\t")[:2] for line in lines if not line.startswith("ADDED")]
        self.assertEqual(statuses, [["INVALID", "Cargo.lock"], ["NOT RUN", "stack.txt"]])  # and the pypi line has no lock

    def test_a11_an_ecosystem_of_the_list_with_no_lockfile_is_not_run(self) -> None:
        """F-0002 A11: a list that holds npm packages while `lockfile` names only a uv.lock compares none of them: NOT RUN."""
        base = self.commit({"uv.lock": uv_lock(), "stack.txt": ""})
        head = self.commit({"uv.lock": uv_lock(), "stack.txt": "npm | left-pad | ADR-0001\n"})
        code, lines, _ = self.run_check(self.usine(*STACK_AND_LOCK), base, head)
        self.assertEqual(code, 2)
        rows = [line.split("\t") for line in lines if line.startswith("NOT RUN")]
        self.assertEqual(len(rows), 1)
        self.assertIn("npm", rows[0][1] + rows[0][3])
        self.assertIn("lockfile", rows[0][3])


def usine_text(stack_path: str) -> str:
    return f"# usine\n\n- `stack` : `{stack_path}`\n- `lockfile` : `uv.lock | pypi`\n"


class PathOnTheBase(StackCase):
    USINE = "docs/agents/usine.md"

    def test_a9_the_path_is_read_on_the_base_and_a_head_without_the_file_is_an_empty_list(self) -> None:
        """F-0002 A9: a PR that moves the `stack` path in usine.md is judged by the base's path; no file at the head is an empty list."""
        base = self.commit({self.USINE: usine_text("stack.txt"), "uv.lock": uv_lock(), "stack.txt": "pypi | idna | ADR-0001\n"})
        # The head points the key at a file that allows everything, and deletes the file the base names.
        head = self.commit(
            {self.USINE: usine_text("lenient.txt"), "uv.lock": uv_lock("idna"), "lenient.txt": "pypi | idna | ADR-0001\n"}
        )
        code, lines, _ = self.run_check(None, base, head)
        self.assertEqual(code, 1)
        self.assertEqual(
            [line.split("\t")[:3] for line in lines if not line.startswith("ADDED")], [["UNLISTED", "uv.lock", "pypi idna"]]
        )
        self.assertFalse([line for line in lines if line.startswith("INVALID")])


if __name__ == "__main__":
    unittest.main()
