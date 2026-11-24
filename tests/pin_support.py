"""Stand-ins and throwaway projects for the tests of `pin_sync.py` and of the hook `pin_notice.py`
(ikoro-labs/forge#333).

A project is a real git repository whose `origin/main` carries `.claude/settings.json` with the pinned
`ref`, so the pin is read the way the script reads it. The real `claude` is never run: `FakeClaude`
answers every `claude ...` command and hands every other command (git) to the real runner. The user
settings live in a throwaway HOME; nothing here writes in the real `~/.claude`.
"""

import json
import os
import subprocess
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pin_state
import support  # noqa: F401  puts the hooks and the scripts of the plugin on the import path

SETTINGS = ".claude/settings.json"
IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false"]


def settings(ref: str, marketplace: str = "ikoro-labs", repo: str = "ikoro-labs/forge") -> str:
    return json.dumps({
        "enabledPlugins": {f"forge@{marketplace}": True},
        "extraKnownMarketplaces": {marketplace: {"source": {"source": "github", "repo": repo, "ref": ref}}},
    }, indent=2) + "\n"


def entry(project: Path, version: str, plugin: str = "forge@ikoro-labs", scope: str = "project") -> dict[str, object]:
    found: dict[str, object] = {"id": plugin, "version": version, "scope": scope, "enabled": True}
    if scope == "project":
        found.update(projectPath=str(project), projectEnabled=True)
    return found


def git(cwd: Path, *argv: str) -> str:
    env = {key: value for key, value in os.environ.items() if not key.startswith(("CLAUDE_", "GIT_"))}
    env.update(HOME=str(cwd), USERPROFILE=str(cwd), GIT_CONFIG_NOSYSTEM="1")
    done = subprocess.run(
        ["git", *IDENTITY, *argv], cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=60,
    )
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(argv)} failed: {done.stderr}")
    return done.stdout


class FakeClaude:
    """The `claude` command, simulated; any other command runs for real."""

    def __init__(
        self,
        entries: list[dict[str, object]] | None = None,
        *,
        available: bool = True,
        fail: dict[str, tuple[int, str]] | None = None,
        on_success: "dict[str, Callable[[list[str], Path], None]] | None" = None,
    ) -> None:
        self.entries = entries if entries is not None else []
        self.available = available
        self.fail = fail or {}
        self.on_success = on_success or {}
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(self, argv: list[str], cwd: Path) -> "pin_state.Done | None":
        if argv[0] != "claude":
            return pin_state.run_command(argv, cwd)
        self.calls.append((argv, cwd))
        if not self.available:
            return None
        key = " ".join(argv[2:4]) if argv[2] == "marketplace" else argv[2]  # `marketplace add`, `update`, `install`
        if key in self.fail:
            code, text = self.fail[key]
            return pin_state.Done(code, "", text)
        if argv[1:4] == ["plugin", "list", "--json"]:
            return pin_state.Done(0, json.dumps(self.entries), "")
        if key in self.on_success:
            self.on_success[key](argv, cwd)
        return pin_state.Done(0, "", "")

    def commands(self) -> list[str]:
        """The `claude` commands run, without the list the check reads."""
        return [" ".join(argv) for argv, _ in self.calls if argv[1:4] != ["plugin", "list", "--json"]]


class PinCase(unittest.TestCase):
    """A throwaway workstation: a HOME with user settings, and projects that pin a `ref` on origin/main."""

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(os.path.realpath(self.dir.name))
        self.home = self.root / "home"
        (self.home / ".claude").mkdir(parents=True)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in [key for key in os.environ if key.startswith("CLAUDE_")]:
            del os.environ[name]

    def user_settings(self, ref: str | None, marketplace: str = "ikoro-labs", repo: str = "ikoro-labs/forge") -> Path:
        """Pin the marketplace at user level (or, with None, write a user file that pins nothing)."""
        path = self.home / ".claude" / "settings.json"
        data: dict[str, object] = {"enabledPlugins": {"other@elsewhere": False}}
        if ref is not None:
            data["extraKnownMarketplaces"] = {marketplace: {"source": {"source": "github", "repo": repo, "ref": ref}}}
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def project(self, name: str, ref: str | None = "forge--v1.21.0", text: str | None = None) -> Path:
        """A clone whose `origin/main` carries the settings that pin `ref` (or `text`, or no file at all)."""
        origin = self.root / f"{name}-origin.git"
        project = self.root / name
        origin.mkdir()
        git(origin, "init", "--bare", "--initial-branch=main")
        project.mkdir()
        git(project, "init", "--initial-branch=main")
        git(project, "remote", "add", "origin", str(origin))
        content = text if text is not None else (settings(ref) if ref is not None else None)
        if content is not None:
            (project / SETTINGS).parent.mkdir(exist_ok=True)
            (project / SETTINGS).write_text(content, encoding="utf-8")
            git(project, "add", SETTINGS)
        else:
            (project / "README.md").write_text("x\n", encoding="utf-8")
            git(project, "add", "README.md")
        git(project, "commit", "-m", "init")
        git(project, "push", "origin", "main")
        git(project, "fetch", "origin")
        return project

    def push_pin(self, project: Path, ref: str) -> None:
        """A newer pin lands on origin/main (the PR of the bump is merged), the clone not yet fetched."""
        (project / SETTINGS).write_text(settings(ref), encoding="utf-8")
        git(project, "add", SETTINGS)
        git(project, "commit", "-m", f"pin {ref}")
        git(project, "push", "origin", "main")
