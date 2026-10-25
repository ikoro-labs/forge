"""The actions of the error budget: the `budget-action` key of `docs/agents/usine.md`.

A line is `<sli> | <action>`, one per action. The action is `human-merge` (the agent no longer
merges), `feature-freeze` (only `bug` and `escaped-defect` tickets are handed to a coder) or `alert`
(the label on the tracking issue, nothing else). An action is active while the objective of its SLI
is `épuisé` in `slo-status.json`, which `scripts/factory_slo.py status` writes; it ends by itself at
the next calculation that finds the objective back to `tenu`.

Read by `guard_git.py` (the merge refusal) and by `scripts/factory_slo.py budget` (what `forge:qc`
and `forge:feature-build` run at the start of a pass). Standard library only. An absent key is
"sans objet" and has no default.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from usine import split_value

KEY = "budget-action"
ACTIONS = ("human-merge", "feature-freeze", "alert")
MAX_AGE = timedelta(hours=24)
EXHAUSTED = "épuisé"
STATUS_COMMAND = 'uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/factory_slo.py" status <projet>'
GIT_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class Line:
    sli: str
    action: str


@dataclass(frozen=True)
class Verdict:
    sli: str
    action: str
    active: bool
    reason: str
    unknown: bool = False


def parse_actions(values: list[str]) -> tuple[list[Line], list[str]]:
    """The readable lines of the key, and one message for each line that is not."""
    lines: list[Line] = []
    errors: list[str] = []
    for value in values:
        parts = split_value(value, 2)
        if parts is None:
            errors.append(f"`{value}` : attendu `<sli> | <action>`")
        elif parts[1] not in ACTIONS:
            errors.append(f"`{value}` : action inconnue `{parts[1]}` (attendu : {', '.join(ACTIONS)})")
        else:
            lines.append(Line(parts[0], parts[1]))
    return lines, errors


def _name(item: dict) -> tuple[str, str]:
    sli = str(item.get("sli"))
    stat = item.get("statistique")
    return sli, f"{sli} {stat}" if stat else sli


def evaluate(lines: list[Line], state: dict) -> list[Verdict]:
    """Whether each action is active in `state`. An SLI that the state does not hold is `unknown`."""
    verdicts: list[Verdict] = []
    for line in lines:
        found = [item for item in state["objectifs"] if line.sli in _name(item)]
        if not found:
            reason = f"l'objectif `{line.sli}` n'est pas dans le fichier d'état (clé `slo`)"
            verdicts.append(Verdict(line.sli, line.action, False, reason, unknown=True))
        elif any(item.get("etat") == EXHAUSTED and item.get("statut") == "calculé" for item in found):
            verdicts.append(Verdict(line.sli, line.action, True, "budget épuisé"))
        else:
            seen = "; ".join(str(item.get("etat") or "sans objet") for item in found)
            verdicts.append(Verdict(line.sli, line.action, False, f"budget non épuisé ({seen})"))
    return verdicts


def load_state(path: Path | None, now: datetime) -> tuple[dict | None, str | None]:
    """The state document, or None and the reason it cannot be used (absent, unreadable, over 24 h)."""
    if path is None:
        return None, "fichier d'état introuvable (le dossier git commun est illisible)"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"fichier d'état absent : {path}"
    except (OSError, ValueError):
        return None, f"fichier d'état illisible : {path}"
    if not isinstance(document, dict):
        return None, f"fichier d'état illisible (pas un objet) : {path}"
    objectives = document.get("objectifs")
    if not isinstance(objectives, list) or not all(isinstance(item, dict) for item in objectives):
        return None, f"fichier d'état illisible (objectifs) : {path}"
    try:
        computed = datetime.fromisoformat(str(document["calcule_le"]))
    except (KeyError, ValueError):
        return None, f"fichier d'état illisible (date du calcul) : {path}"
    if computed.tzinfo is None:
        return None, f"fichier d'état illisible (date sans fuseau) : {path}"
    if now - computed > MAX_AGE:
        return None, f"fichier d'état périmé (calculé le {computed.isoformat()}, plus de 24 h) : {path}"
    return document, None


def state_path(root: Path) -> Path | None:
    """`<git-common-dir>/forge/slo-status.json` of the project at `root`; None when git cannot say."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, git resolved by shutil.which
            [git, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=root, capture_output=True, encoding="utf-8", errors="replace", check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    common = done.stdout.strip()
    if done.returncode != 0 or not common:
        return None
    return Path(common) / "forge" / "slo-status.json"


def merge_refusal(config: dict[str, list[str]], path: Path | None, now: datetime) -> str | None:
    """Why an agent may not run `gh pr merge`, or None.

    Closed by default: a declared `human-merge` whose state is absent, stale, unreadable or silent
    on its SLI refuses, with the command to run. A line the key cannot be read from refuses too,
    because it may have been a `human-merge`. The other actions never refuse a merge.
    """
    values = config.get(KEY)
    if not values:
        return None
    lines, errors = parse_actions(values)
    if errors:
        return f"la clé `{KEY}` est mal formée, la fusion est refusée par précaution : " + " ; ".join(errors)
    merges = [line for line in lines if line.action == "human-merge"]
    if not merges:
        return None
    state, reason = load_state(path, now)
    if state is None:
        return (
            f"la clé `{KEY}` déclare `human-merge` et son état est inutilisable ({reason}) : la fusion est refusée"
            f" par précaution. Recalcule l'état : `{STATUS_COMMAND}`"
        )
    for verdict in evaluate(merges, state):
        if verdict.unknown:
            return f"la clé `{KEY}` déclare `{verdict.sli} | human-merge` mais {verdict.reason} : la fusion est refusée par précaution"
        if verdict.active:
            return (
                f"budget d'erreur épuisé pour `{verdict.sli}` (`{KEY}` : `human-merge`) : les fusions reviennent à"
                " l'humain tant que l'objectif n'est pas revenu à `tenu`. Pose `needs-your-attention`, l'humain fusionne"
            )
    return None
