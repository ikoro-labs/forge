"""SessionStart hook: two notices about the pin of the plugin, each independent of the other.

The bump notice (ikoro-labs/forge#278): with the key `pin-bump`, tell a consumer session that the plugin
has a newer tag than the `ref` its `.claude/settings.json` pins.

The key `pin-bump` of `docs/agents/usine.md`, with its only value `auto`, is the human's consent for the
session to open the pin PR; without it the hook asks nothing and says nothing. The pin is read where
Claude Code reads it: the marketplace of the enabled `forge@<marketplace>` plugin, a `github` source whose
`ref` is `<prefix>X.Y.Z`. The newer tag is the highest `<prefix>X.Y.Z` that `gh api` lists on the
marketplace repository, compared as numbers.

It says nothing when the pin is the newest tag, when a PR that changes `.claude/settings.json` is already
open, nor for a subagent. It does not decide the merge: `protected-path` and `human-merge` stay the rules
of `forge:qc` and of `guard_git`.

The BEHIND notice (ikoro-labs/forge#333), with no key: a merged bump changes `.claude/settings.json` and
nothing else, so the install stays old until `claude plugin marketplace add` and `claude plugin update`
run. `pin_state.check`, the verdict of `pin_sync.py check`, compares the `ref` on `origin/main` with the
version `claude plugin list --json` lists for this project (its main checkout, a worktree or a subfolder
included). On BEHIND, the session is told both versions and the command, `pin_sync.py apply <project>`,
which the hook never runs. OK says nothing, and so does NOT RUN (a `claude` that does not answer, no pin
to read, a pin of the user's own settings that makes `marketplace add` refuse): only a proved lag is said.
It asks nothing of the network.

Neither notice blocks: a command that is missing, fails or exceeds its delay, a settings file or an
event it cannot read, any error at all, exits 0 and says nothing, and one notice failing costs only itself.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

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


def behind_notice_text(project: Path, detail: str) -> str:
    script = Path(__file__).resolve().parent.parent / "scripts" / "pin_sync.py"
    return (
        f"Le plugin installé sur ce poste pour ce projet n'est pas celui que `{SETTINGS}` épingle sur `origin/main` "
        f"({detail}) : une PR de montée ne change que ce fichier, l'installation reste à faire. Entre deux "
        f"tickets, lance `uv run --no-project --quiet python \"{script}\" apply \"{project}\"`. Elle refuse tant "
        "qu'un coder ou un tour de `forge:qc` est en vol (jamais entre un coder et le verdict de la revue, donc "
        "pas pendant un `/forge:feature-build` actif entre les deux), rend `NOT RUN` avec la raison quand les "
        "réglages utilisateur épinglent la marketplace à un autre `ref`, et ne modifie aucun réglage utilisateur."
    )


def behind_notice(event: dict, run: Callable[..., Any] | None = None) -> str | None:
    """The context for this session when the install lags the pin, else None: OK, NOT RUN, a subagent."""
    if event.get("agent_id"):
        return None
    # Imported here, so that a broken sibling costs only this notice.
    import handoff_header
    import pin_state
    import usine

    project = Path(handoff_header.main_checkout(usine.project_root(event)))
    result = pin_state.check(project, run or pin_state.run_command)
    return behind_notice_text(project, result.detail) if result.status == "BEHIND" else None


def safely(make: Callable[[dict], str | None], event: dict) -> str | None:
    """One notice or None: whatever goes wrong inside a notice costs that notice only."""
    try:
        return make(event)
    except Exception:  # noqa: BLE001 - an observing hook never blocks the session
        return None


def main(stdin) -> int:
    try:
        event = json.load(stdin)
        if not isinstance(event, dict) or not isinstance(event.get("cwd", ""), str):
            return 0
        messages = [text for make in (notice, behind_notice) if (text := safely(make, event)) is not None]
        if messages:
            context = "\n\n".join(messages)
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}))
    except Exception:  # noqa: BLE001 - an observing hook never blocks the session
        pass
    return 0


if __name__ == "__main__":
    use_utf8()
    sys.exit(main(sys.stdin))
