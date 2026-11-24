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

import support
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
                child.unlink()
        for name, text in files.items():
            (self.repo / name).write_text(text, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "--quiet", "--allow-empty", "-m", "state")
        return self.git("rev-parse", "HEAD")

    def usine(self, *lines: str) -> Path:
        path = self.tmp / "usine.md"
        path.write_text("# usine\n\n" + "\n".join(f"- {line}" for line in lines) + "\n", encoding="utf-8")
        return path

    def run_check(self, usine: Path, base: str, head: str) -> tuple[int, list[str], str]:
        """The exit code, the output lines and the error output of the check."""
        args = ["--usine", str(usine), "--root", str(self.repo), "--base", base, "--head", head]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(args)
        return code, out.getvalue().splitlines(), err.getvalue()


STACK_AND_LOCK = ("`stack` : `stack.txt`", "`lockfile` : `uv.lock | pypi`")


class StackFile(StackCase):
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


if __name__ == "__main__":
    unittest.main()
