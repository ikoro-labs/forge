"""Ticket #155: the age of each dependency a PR adds, read on its registry by `lockfile_age.py`.

Every test runs on a throwaway git repository and a registry simulated by a local HTTP server:
this repository has no lockfile, and no test reaches a public registry.
"""

import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import support  # noqa: F401
from lockfile_age import main


def iso(days_ago: float) -> str:
    """A registry timestamp `days_ago` days before now."""
    moment = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def uv_lock(*packages: tuple[str, str]) -> str:
    """A `uv.lock` listing the (name, version) pairs, each from the public index."""
    blocks = ['version = 1\nrevision = 3\nrequires-python = ">=3.10"\n']
    for name, version in packages:
        blocks.append(
            f'[[package]]\nname = "{name}"\nversion = "{version}"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            f'wheels = [\n    {{ url = "https://files.example/{name}.whl", size = 1 }},\n]\n'
        )
    return "\n".join(blocks)


def package_lock(*packages: tuple[str, str]) -> str:
    """A `package-lock.json` (lockfileVersion 3) listing the (name, version) pairs."""
    entries: dict[str, object] = {"": {"name": "app", "version": "1.0.0"}}
    for name, version in packages:
        entries[f"node_modules/{name}"] = {
            "version": version,
            "resolved": f"https://registry.npmjs.org/{name}/-/{name.split('/')[-1]}-{version}.tgz",
            "integrity": "sha512-x",
        }
    return json.dumps({"name": "app", "lockfileVersion": 3, "packages": entries}, indent=2)


class FakeRegistry:
    """A local HTTP server that answers like PyPI (`/pypi/<name>/json`) and npm (`/<name>`)."""

    def __init__(self) -> None:
        self.pages: dict[str, tuple[int, str]] = {}
        self.requests: list[str] = []
        registry = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (the name http.server calls)
                registry.requests.append(self.path)
                status, body = registry.pages.get(self.path, (404, '{"message": "not found"}'))
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def pypi(self, name: str, first: float, releases: dict[str, float]) -> None:
        """`first` is the age in days of the oldest file; `releases` maps a version to its age."""
        files = {version: [{"upload_time_iso_8601": iso(age)}] for version, age in releases.items()}
        files["0.0.1"] = [{"upload_time_iso_8601": iso(first)}]
        body = {"info": {"name": name}, "releases": files}
        self.pages[f"/pypi/{name}/json"] = (200, json.dumps(body))

    def npm(self, name: str, created: float, versions: dict[str, float]) -> None:
        time = {"created": iso(created), "modified": iso(0)}
        time.update({version: iso(age) for version, age in versions.items()})
        quoted = name.replace("/", "%2F")
        self.pages[f"/{quoted}"] = (200, json.dumps({"name": name, "time": time}))


class LockfileAgeCase(unittest.TestCase):
    """A throwaway repository with a base commit and a head commit, and a simulated registry."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        home = self.tmp / "home"
        home.mkdir()
        env = {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "NO_PROXY": "127.0.0.1",
            "no_proxy": "127.0.0.1",
        }
        patcher = unittest.mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "CLAUDE_PROJECT_DIR"):
            os.environ.pop(name, None)
        self.git("init", "--quiet")
        self.registry = FakeRegistry()
        self.addCleanup(self.registry.close)

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

    def run_probe(
        self, usine: Path, base: str, head: str, *extra: str
    ) -> tuple[int, list[str], str]:
        """The exit code, the output lines and the error output of the probe."""
        args = [
            "--usine", str(usine), "--root", str(self.repo), "--base", base, "--head", head,
            "--registry", f"pypi={self.registry.url}/pypi", "--registry", f"npm={self.registry.url}",
            *extra,
        ]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(args)
        return code, out.getvalue().splitlines(), err.getvalue()


class KeysAbsent(LockfileAgeCase):
    def test_without_the_lockfile_key_the_step_is_sans_objet(self) -> None:
        """Ticket #155: no `lockfile` key, the probe says so and reads nothing."""
        base = self.commit({"uv.lock": uv_lock(("requests", "2.31.0"))})
        head = self.commit({"uv.lock": uv_lock(("requests", "2.32.0"))})
        usine = self.usine("`dependency-min-age` : `7`")
        code, lines, _ = self.run_probe(usine, base, head)
        self.assertEqual(lines, ["sans objet (clé lockfile absente)"])
        self.assertEqual(code, 0)
        self.assertEqual(self.registry.requests, [])

    def test_without_the_threshold_key_the_step_is_sans_objet_and_no_value_is_guessed(self) -> None:
        """Ticket #155: `dependency-min-age` has no default; without it the registry is not asked."""
        base = self.commit({"uv.lock": uv_lock(("requests", "2.31.0"))})
        head = self.commit({"uv.lock": uv_lock(("requests", "2.32.0"))})
        usine = self.usine("`lockfile` : `uv.lock | pypi`")
        code, lines, _ = self.run_probe(usine, base, head)
        self.assertEqual(lines, ["sans objet (clé dependency-min-age absente)"])
        self.assertEqual(code, 0)
        self.assertEqual(self.registry.requests, [])


if __name__ == "__main__":
    unittest.main()
