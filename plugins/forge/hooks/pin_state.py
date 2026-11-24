"""What a project pins and what the workstation installed, compared (ikoro-labs/forge#333).

The pin is the `ref` of `forge@<marketplace>` in `.claude/settings.json` as `origin/main` has it: the
file a merged bump changed, not the working tree. The installed version is the entry of
`claude plugin list --json` whose `projectPath` is the project (without `--json` the list shows one
entry per plugin, the last project installed). Both are read, nothing is written, and no settings file
of the user is ever edited: the user's own pin of the marketplace is only read, to say that
`claude plugin marketplace add` would be refused (the pin of the project differs from it).

One result per project, `OK`, `BEHIND` (the installed version differs from the pin: the detail says which
way) or `NOT RUN` (something could not be read, the detail says what). Never `OK` on a doubt. Shared by
`scripts/pin_sync.py` and the hook `pin_notice.py`. The standard library only.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PLUGIN = "forge"
SETTINGS = ".claude/settings.json"
BASE = "origin/main"
PIN = re.compile(r"(?P<prefix>.+--v)(?P<version>\d+\.\d+\.\d+)")
VERSION = re.compile(r"\d+\.\d+\.\d+")
# One external command at most this long; the hook's `timeout` in `hooks.json` bounds the whole.
SECONDS = 8

REFUSED_ADD = "l'entrée de marketplace de niveau utilisateur diffère de l'épingle"


@dataclass(frozen=True)
class Done:
    code: int
    out: str
    err: str


# A command runner: the finished command, or None when it is missing, cannot start or does not finish in time.
Run = Callable[[list[str], Path], "Done | None"]


class NotRun(Exception):
    """Something the comparison needs could not be read: the message is the reason."""


@dataclass(frozen=True)
class Pin:
    marketplace: str
    repo: str
    ref: str
    version: str

    @property
    def plugin_id(self) -> str:
        return f"{PLUGIN}@{self.marketplace}"


@dataclass(frozen=True)
class Result:
    status: str  # OK, BEHIND or NOT RUN
    project: str
    detail: str

    @property
    def line(self) -> str:
        return f"{self.status}\t{self.project}\t{self.detail}"


def run_command(argv: list[str], cwd: Path, seconds: float = SECONDS) -> Done | None:
    """The finished command, or None when it is not on the PATH, cannot start or does not finish in time."""
    program = shutil.which(argv[0])
    if program is None:
        return None
    try:
        # Fixed argv resolved by shutil.which, and arguments built by the callers.
        done = subprocess.run(  # noqa: S603
            [program, *argv[1:]], cwd=cwd, capture_output=True, encoding="utf-8", errors="replace",
            check=False, timeout=seconds,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return Done(done.returncode, done.stdout, done.stderr)


def last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "sans message"


def read_pin(project: Path, run: Run) -> Pin:
    """The pin of the project on origin/main; NotRun says what could not be read."""
    done = run(["git", "-C", str(project), "show", f"{BASE}:{SETTINGS}"], project)
    if done is None:
        raise NotRun(f"git n'a pas pu lire `{BASE}:{SETTINGS}` dans {project}")
    if done.code != 0:
        raise NotRun(f"`{BASE}:{SETTINGS}` illisible dans {project} : {last_line(done.err)}")
    try:
        data = json.loads(done.out)
        for plugin, enabled in data.get("enabledPlugins", {}).items():
            name, _, marketplace = plugin.partition("@")
            if name != PLUGIN or not enabled:
                continue
            source = data.get("extraKnownMarketplaces", {}).get(marketplace, {}).get("source", {})
            found = PIN.fullmatch(str(source.get("ref", "")))
            if source.get("source") == "github" and source.get("repo") and found:
                return Pin(marketplace, str(source["repo"]), str(source["ref"]), found["version"])
    except (ValueError, AttributeError, TypeError):
        raise NotRun(f"`{SETTINGS}` de `{BASE}` n'est pas un JSON de réglages lisible") from None
    raise NotRun(f"`{SETTINGS}` de `{BASE}` n'épingle pas `{PLUGIN}@<marketplace>` sur un tag `...--vX.Y.Z` d'une source github")


def installed_entries(run: Run, cwd: Path) -> list[dict[str, object]]:
    """The entries of `claude plugin list --json`; NotRun when the command or its answer is unusable."""
    done = run(["claude", "plugin", "list", "--json"], cwd)
    if done is None:
        raise NotRun("`claude plugin list --json` n'a pas répondu (absent, impossible à lancer ou trop long)")
    if done.code != 0:
        raise NotRun(f"`claude plugin list --json` a échoué : {last_line(done.err)}")
    try:
        data = json.loads(done.out)
    except ValueError:
        raise NotRun("`claude plugin list --json` n'a pas rendu du JSON") from None
    if not isinstance(data, list):
        raise NotRun("`claude plugin list --json` n'a pas rendu une liste")
    return [item for item in data if isinstance(item, dict)]


def same_path(left: object, right: Path) -> bool:
    return isinstance(left, str) and os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right))


def projects(entries: list[dict[str, object]]) -> list[Path]:
    """The projects the workstation installed the plugin for (scope `project`), in list order, once each."""
    found: list[Path] = []
    for item in entries:
        path = item.get("projectPath")
        name = str(item.get("id", "")).partition("@")[0]
        if name == PLUGIN and item.get("scope") == "project" and isinstance(path, str) and path:
            if not any(same_path(path, known) for known in found):
                found.append(Path(path))
    return found


def installed_version(entries: list[dict[str, object]], pin: Pin, project: Path) -> str | None:
    """The version installed for this project, None when the workstation lists none."""
    for item in entries:
        if item.get("id") == pin.plugin_id and item.get("scope") == "project" and same_path(item.get("projectPath"), project):
            return str(item.get("version", ""))
    return None


def user_pin(marketplace: str) -> tuple[str, str] | None:
    """The `(repo, ref)` the user's own settings pin for this marketplace, None when they pin nothing.

    Read only. An unreadable file pins nothing we can name: the refusal of `marketplace add` is then
    caught when it happens, by `refused_by_user_pin`.
    """
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    path = (Path(config) if config else Path.home() / ".claude") / "settings.json"
    try:
        source = json.loads(path.read_text(encoding="utf-8"))["extraKnownMarketplaces"][marketplace]["source"]
        return str(source["repo"]), str(source["ref"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def refused_by_user_pin(pin: Pin) -> str | None:
    """The reason `marketplace add` of this pin would be refused, None when the user's pin does not differ."""
    found = user_pin(pin.marketplace)
    if found is None or found == (pin.repo, pin.ref):
        return None
    return (
        f"{REFUSED_ADD} : le poste épingle `{found[1]}` ({found[0]}) dans ses réglages utilisateur, le projet "
        f"`{pin.ref}` ; `claude plugin marketplace add` serait refusé. Aucun fichier de réglages utilisateur n'est "
        "modifié : à l'humain d'aligner le sien"
    )


def compare(project: Path, entries: list[dict[str, object]], run: Run) -> Result:
    """The result for one project from the entries already listed."""
    try:
        pin = read_pin(project, run)
    except NotRun as why:
        return Result("NOT RUN", str(project), str(why))
    current = installed_version(entries, pin, project)
    if current is not None and not VERSION.fullmatch(current):
        return Result("NOT RUN", str(project), f"la version installée `{current}` n'est pas de la forme X.Y.Z")
    if current == pin.version:
        return Result("OK", str(project), f"{pin.plugin_id} {current} installé, épinglé `{pin.ref}`")
    seen = f"installé {current}" if current else "pas installé"
    summary = f"{seen}, épinglé {pin.version} (`{pin.ref}`)"
    refused = refused_by_user_pin(pin)
    if refused:
        return Result("NOT RUN", str(project), f"{summary} ; {refused}")
    if current is None:
        return Result("BEHIND", str(project), summary)
    way = "en retard" if tuple(map(int, current.split("."))) < tuple(map(int, pin.version.split("."))) else "en avance"
    return Result("BEHIND", str(project), f"{summary} ; le poste est {way} sur l'épingle")


def check(project: Path, run: Run) -> Result:
    """List the workstation and compare one project."""
    try:
        entries = installed_entries(run, project if project.is_dir() else Path.cwd())
    except NotRun as why:
        return Result("NOT RUN", str(project), str(why))
    return compare(project, entries, run)
