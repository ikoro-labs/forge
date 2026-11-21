"""SessionStart hook: with the key `pin-bump`, tell a consumer session that the plugin has a newer tag
than the `ref` its `.claude/settings.json` pins (ikoro-labs/forge#278).

The key `pin-bump` of `docs/agents/usine.md`, with its only value `auto`, is the human's consent for the
session to open the pin PR; without it the hook asks nothing and says nothing. The pin is read where
Claude Code reads it: the marketplace of the enabled `forge@<marketplace>` plugin, a `github` source whose
`ref` is `<prefix>X.Y.Z`. The newer tag is the highest `<prefix>X.Y.Z` that `gh api` lists on the
marketplace repository, compared as numbers.

It says nothing when the pin is the newest tag, when a PR that changes `.claude/settings.json` is already
open, nor for a subagent. It never blocks: a `gh` that is missing, fails or exceeds its delay, a
settings file or an event it cannot read, any error at all, exits 0 and says nothing. It does not decide
the merge: `protected-path` and `human-merge` stay the rules of `forge:qc` and of `guard_git`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from utf8_stdio import use_utf8

KEY = "pin-bump"
SETTINGS = ".claude/settings.json"
PLUGIN = "forge"
# One call to `gh` at most this long; the hook's own `timeout` in `hooks.json` bounds the two together.
GH_SECONDS = 8
PIN = re.compile(r"(?P<prefix>.+--v)(?P<version>\d+\.\d+\.\d+)")

Runner = Callable[[list[str], Path], "str | None"]


def run_gh(argv: list[str], cwd: Path) -> str | None:
    """The standard output of `gh`, or None when it is missing, fails or does not finish in time."""
    gh = shutil.which("gh")
    if gh is None:
        return None
    try:
        # Fixed argv resolved by shutil.which, and arguments built here.
        completed = subprocess.run(  # noqa: S603
            [gh, *argv[1:]], cwd=cwd, capture_output=True, encoding="utf-8", errors="replace",
            check=False, timeout=GH_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def pinned(root: Path) -> tuple[str, str, tuple[int, ...]] | None:
    """The repository, the tag prefix and the version of the pinned `ref`, or None."""
    try:
        data = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
        for plugin, enabled in data.get("enabledPlugins", {}).items():
            name, _, marketplace = plugin.partition("@")
            if name != PLUGIN or not enabled:
                continue
            source = data.get("extraKnownMarketplaces", {}).get(marketplace, {}).get("source", {})
            found = PIN.fullmatch(str(source.get("ref", "")))
            if source.get("source") == "github" and source.get("repo") and found:
                return str(source["repo"]), found["prefix"], version(found["version"])
    except (OSError, ValueError, AttributeError, TypeError):
        # A settings file that is missing, is not JSON or has another shape pins nothing we can read.
        return None
    return None


def version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def newest(lines: str, prefix: str) -> tuple[int, ...] | None:
    """The highest `<prefix>X.Y.Z` among `refs/tags/...` lines; a pre-release or another plugin is skipped."""
    found = [
        version(match["version"])
        for line in lines.splitlines()
        if (match := PIN.fullmatch(line.strip().removeprefix("refs/tags/"))) and match["prefix"] == prefix
    ]
    return max(found, default=None)


def notice_text(prefix: str, current: tuple[int, ...], latest: tuple[int, ...]) -> str:
    tag = prefix + ".".join(map(str, latest))
    old = prefix + ".".join(map(str, current))
    return (
        f"Un tag plus récent du plugin existe : `{tag}`, et `{SETTINGS}` épingle `{old}`. La clé `{KEY}` "
        "(`auto`) de `docs/agents/usine.md` est l'accord de l'humain pour monter cette épingle, aucun "
        f"billet n'en tient lieu. Ouvre une PR `chore(release): pin {tag}` qui change le `ref` de "
        f"`{SETTINGS}` (et chaque mention de l'ancien tag dans la doc du projet), après lecture de l'entrée "
        "de ce tag au `CHANGELOG.md` du plugin ; `forge:qc` la juge, et la fusionne sur ACCEPT. Cette clé "
        "n'ouvre aucune fusion de plus : un chemin de `protected-path` dans le diff ou une action "
        "`human-merge` active arrête la fusion, et l'humain fusionne. Pas pendant un `/forge:feature-build` "
        "actif. Une fois la PR fusionnée, le geste sur chaque poste (`claude plugin marketplace add`, puis "
        "`claude plugin update`, voir « Monter de version » de la page d'installation du plugin) reste à "
        "l'humain."
    )


def notice(event: dict, run: Runner = run_gh) -> str | None:
    """The context for this session, or None: no key, a subagent, no newer tag, a pin PR open, any doubt."""
    if event.get("agent_id"):
        return None
    # Imported here, so that a broken sibling costs only the notice.
    import usine

    root = usine.project_root(event)
    if usine.load(root).get(KEY) != ["auto"]:
        return None
    pin = pinned(root)
    if pin is None:
        return None
    repository, prefix, current = pin
    listed = run(
        ["gh", "api", f"repos/{repository}/git/matching-refs/tags/{prefix}?per_page=100", "--paginate",
         "--jq", ".[].ref"],
        root,
    )
    latest = newest(listed, prefix) if listed is not None else None
    if latest is None or latest <= current:
        return None
    open_prs = run(["gh", "pr", "list", "--state", "open", "--limit", "100", "--json", "files",
                    "--jq", ".[].files[].path"], root)
    # A list that cannot be read counts as a PR already open: a second one is worse than a late notice.
    if open_prs is None or SETTINGS in (line.strip() for line in open_prs.splitlines()):
        return None
    return notice_text(prefix, current, latest)


def main(stdin) -> int:
    try:
        event = json.load(stdin)
        if not isinstance(event, dict) or not isinstance(event.get("cwd", ""), str):
            return 0
        message = notice(event)
        if message is not None:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": message}}))
    except Exception:  # noqa: BLE001 - an observing hook never blocks the session
        pass
    return 0


if __name__ == "__main__":
    use_utf8()
    sys.exit(main(sys.stdin))
