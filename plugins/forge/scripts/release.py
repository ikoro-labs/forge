"""The conditions of a continuous release: when a version is due, and whether the agent may publish it.

    python release.py trigger <project>
    python release.py condition <slo|budget|sev1|essai> <project> [--plugin DIR] [--essai SCRIPT]
    python release.py check <project> [--json] [--plugin DIR] [--essai SCRIPT]
    python release.py tag <project> <version>

`trigger` reads the key `release-trigger` of `docs/agents/usine.md`, one line
`<merges> | <longest wait>` (`10 | 7 j`: the wait is a number followed by `h` or `j`, as in the key
`sla`). A version is due when that many pull requests merged on the base wait for a tag of the key
`release-tag` (their merge commit is in no such tag), or when the oldest of them has waited that long:
the first bound reached triggers, the bound itself included, and nothing waiting never triggers. A key
absent, `release-trigger` or `release-tag`, is "sans objet": the agent publishes nothing, and no value
is guessed. A line it cannot read (a count that is not a whole number above zero, a wait it cannot
read, a missing part, a repeated key) fails the command with code 2 and prints no state: it is never
completed.

`condition` prints one of the four conditions the agent publishes on, each `tenue`, `non tenue` or
`non vérifiable`. A condition missing from the project (a key absent, a file unreadable or older than an
hour, a label that does not exist, a `gh` that fails) is never `tenue`:

    - `slo`: every objective of `slo-status.json` is `tenu`, computed within the hour;
    - `budget`: no action of the key `budget-action` is active (`alert` included), same state;
    - `sev1`: no open ticket carries the `sev1` label, which the repository must hold;
    - `essai`: the end-to-end trial (`e2e_trial.py`, or `--essai`) passes, `RESULTAT: PASS`, on exactly
      the head of the base with an unmodified tree. `--plugin` is the plugin it tries: run this from a
      checkout of the head of the base and name its plugin.

`check` gives the decision: `sans objet` (a key absent), `rien` (no version is due), `publier` (due, the
four conditions `tenue`) or `humain` (due, one or more missing: `MANQUE:` names them). It reads the
three cheap conditions first and launches the trial, which costs real model calls, only when they all
hold; otherwise the trial counts as not held and says it was not launched. It never publishes, tags or
opens anything: the skill `release` does, on the decision. `--json` prints one document.

`tag` prints the name of the tag of a version, the pattern of the key `release-tag` with `{version}` filled
in, and refuses (code 2) a version that is not a number, a key with several patterns or none with
`{version}`, and a tag that already exists: a tag is never moved or deleted. No key: "sans objet".

The output is one fact per line, in French, on standard output. The standard library only.
"""

from __future__ import annotations

import argparse
import functools
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import budget  # noqa: E402  the hooks' reader of `slo-status.json` and of the key `budget-action`
import factory_slo  # noqa: E402  the indicators of the factory, whose runner and base this script reuses
import sla  # noqa: E402  the hooks' reader of a delay (`4 h`, `3 j`)
import usine  # noqa: E402  the reader of `usine.md`

Runner = Callable[[list[str], Path], str]

TRIGGER_KEY = "release-trigger"
TAG_KEY = "release-tag"
REACHED, NOT_REACHED, ABSENT = "atteint", "non atteint", "sans objet"
MET, NOT_MET, UNVERIFIABLE = "tenue", "non tenue", "non vérifiable"
STATE_MAX_AGE = timedelta(hours=1)
SEV1 = "sev1"
TRIAL_SCRIPT = Path(__file__).resolve().parent / "e2e_trial.py"
TRIAL_TIMEOUT_SECONDS = 3600
TRIAL_KEYS = ("RESULTAT", "TETE", "ETAPE", "RAISON")
HEX_SHA = re.compile(r"[0-9a-f]{40}")
VERSION_MARK = "{version}"
VERSION = re.compile(r"[0-9][0-9A-Za-z.+-]*")
WRONG_CALL = 2


class ReleaseError(ValueError):
    """A key the script cannot read: the command fails and guesses nothing."""


@dataclass(frozen=True)
class Trigger:
    merges: int
    wait: timedelta
    wait_text: str


def parse_trigger(values: list[str]) -> Trigger:
    """The trigger the key declares; ReleaseError when it is repeated or one of its parts is unreadable."""
    if len(values) > 1:
        raise ReleaseError(f"`{TRIGGER_KEY}` : une seule ligne attendue, {len(values)} lignes déclarées")
    value = values[0]
    parts = usine.split_value(value, 2)
    if parts is None:
        raise ReleaseError(f"`{TRIGGER_KEY}` : `{value}` : attendu `<N fusions> | <délai max>`, comme `10 | 7 j`")
    count, wait_text = parts
    if not count.isdigit() or int(count) == 0:
        raise ReleaseError(f"`{TRIGGER_KEY}` : `{value}` : le nombre de fusions est un entier au-dessus de 0")
    wait = sla.parse_delay(wait_text)
    if wait is None:
        raise ReleaseError(
            f"`{TRIGGER_KEY}` : `{value}` : délai illisible `{wait_text}` "
            "(attendu un nombre au-dessus de 0 suivi de `h` ou `j`, comme `7 j`)"
        )
    return Trigger(int(count), wait, wait_text)


def load_trigger(project: Path) -> Trigger | None:
    """The trigger of the project, None when the key is absent."""
    values = usine.load(project).get(TRIGGER_KEY)
    return parse_trigger(values) if values else None


@dataclass(frozen=True)
class Due:
    """Whether a version is due: `atteint`, `non atteint` or `sans objet`, and the sentence that says why."""

    status: str
    text: str
    waiting: int = 0
    oldest: datetime | None = None

    @property
    def reached(self) -> bool:
        return self.status == REACHED

    def line(self) -> str:
        return f"DECLENCHEUR: {self.text}"


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count > 1 else ''}"


def wait_text(delta: timedelta) -> str:
    """A wait in the unit of the key: days from two days on, hours below."""
    hours = int(delta.total_seconds() // 3600)
    return f"{hours // 24} j" if hours >= 48 or (hours >= 24 and hours % 24 == 0) else f"{hours} h"


def waiting_merges(f: factory_slo.Factory, patterns: list[re.Pattern[str]]) -> list[datetime]:
    """The merge dates of the pull requests on the base whose merge commit is in no version tag.

    A merge commit that git does not know (not fetched) is in no tag as far as git can say: it counts
    as waiting, so a version may fall due early, never late.
    """
    fields = "number,mergedAt,mergeCommit"
    merged = f.gh("pr", "list", "--state", "merged", "--base", f.base, "--limit", "1000", "--json", fields)
    waiting = []
    for item in merged:
        moment = factory_slo.when(item, "mergedAt")
        oid = (item.get("mergeCommit") or {}).get("oid")
        if moment is not None and factory_slo.first_tag_date(f, patterns, oid) is None:
            waiting.append(moment)
    return sorted(waiting)


def due(project: Path, run: Runner, now: datetime) -> Due:
    """The trigger of the key `release-trigger` against the merges waiting for a tag of `release-tag`."""
    trigger = load_trigger(project)
    if trigger is None:
        return Due(ABSENT, f"sans objet (clé `{TRIGGER_KEY}` absente), aucune publication par l'agent")
    f = factory_slo.Factory(project, now - timedelta(days=1), now, run)
    templates = f.required(TAG_KEY)
    if not templates:
        return Due(ABSENT, f"sans objet (clé `{TAG_KEY}` absente), aucune publication par l'agent")
    waiting = waiting_merges(f, [factory_slo.tag_pattern(template) for template in templates])
    if not waiting:
        return Due(NOT_REACHED, f"{NOT_REACHED} : aucune fusion n'attend de version")
    elapsed = now - waiting[0]
    count, wanted = plural(len(waiting), "fusion"), plural(trigger.merges, "demandée")
    if len(waiting) >= trigger.merges:
        return Due(REACHED, f"{REACHED} par le nombre : {count} en attente pour {wanted}", len(waiting), waiting[0])
    if elapsed >= trigger.wait:
        oldest = f"la plus ancienne attend depuis {wait_text(elapsed)} pour {trigger.wait_text}"
        return Due(REACHED, f"{REACHED} par le délai : {oldest}", len(waiting), waiting[0])
    oldest = f"la plus ancienne depuis {wait_text(elapsed)} pour {trigger.wait_text}"
    return Due(NOT_REACHED, f"{NOT_REACHED} : {count} en attente pour {wanted}, {oldest}", len(waiting), waiting[0])


def run_trigger(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    print(due(args.projet, run, now).line())
    return 0


@dataclass(frozen=True)
class Condition:
    """One condition of the release: `tenue`, `non tenue`, or `non vérifiable` (never read as `tenue`)."""

    name: str
    status: str
    text: str

    @property
    def held(self) -> bool:
        return self.status == MET

    def line(self) -> str:
        return f"CONDITION: {self.name} | {self.status} | {self.text}"


def objective_name(item: dict) -> str:
    sli, stat = str(item.get("sli")), item.get("statistique")
    return f"{sli} {stat}" if stat else sli


def state_of(project: Path, run: Runner, now: datetime) -> tuple[dict | None, str | None]:
    """The `slo-status.json` of the project, read as a state fresh within the hour, and why it is not usable."""
    try:
        path = factory_slo.state_path(project, run)
    except RuntimeError as error:
        return None, f"le dossier git commun est illisible ({error})"
    state, reason = budget.load_state(path, now, STATE_MAX_AGE)
    if state is None:
        return None, f"{reason}. Recalcule l'état : `{budget.STATUS_COMMAND}`"
    return state, None


def slo_condition(project: Path, run: Runner, now: datetime) -> Condition:
    """Every objective of the `slo` key is `tenu` in a state computed within the hour."""
    if not usine.load(project).get("slo"):
        return Condition("slo", UNVERIFIABLE, "sans objet (clé `slo` absente) : aucun objectif à lire")
    state, reason = state_of(project, run, now)
    if state is None:
        return Condition("slo", UNVERIFIABLE, str(reason))
    objectives = state["objectifs"]
    if not objectives:
        return Condition("slo", UNVERIFIABLE, "aucun objectif dans le fichier d'état")
    missing = [
        f"{objective_name(item)} ({item.get('etat') or 'sans objet'})"
        for item in objectives
        if item.get("statut") != "calculé" or item.get("etat") != budget.HELD
    ]
    if missing:
        return Condition("slo", NOT_MET, "objectifs qui ne sont pas `tenu` : " + ", ".join(missing))
    return Condition("slo", MET, f"{plural(len(objectives), 'objectif')} `tenu`, calculés dans l'heure")


def budget_condition(project: Path, run: Runner, now: datetime) -> Condition:
    """No action of the key `budget-action` is active in a state computed within the hour.

    Every action counts, `alert` included: the condition says the error budget is held, not that
    the agent is still allowed to merge.
    """
    values = usine.load(project).get(budget.KEY)
    if not values:
        return Condition("budget", UNVERIFIABLE, f"sans objet (clé `{budget.KEY}` absente) : aucune action à lire")
    lines, errors = budget.parse_actions(values)
    if errors:
        return Condition("budget", UNVERIFIABLE, f"clé `{budget.KEY}` mal formée : " + " ; ".join(errors))
    state, reason = state_of(project, run, now)
    if state is None:
        return Condition("budget", UNVERIFIABLE, str(reason))
    verdicts = budget.evaluate(lines, state)
    if unknown := [verdict for verdict in verdicts if verdict.unknown]:
        return Condition("budget", UNVERIFIABLE, " ; ".join(f"{v.sli} | {v.action} : {v.reason}" for v in unknown))
    if active := [verdict for verdict in verdicts if verdict.active]:
        return Condition("budget", NOT_MET, "actions actives : " + " ; ".join(f"{v.sli} | {v.action} ({v.reason})" for v in active))
    return Condition("budget", MET, f"{plural(len(verdicts), 'action')} déclarée{'s' if len(verdicts) > 1 else ''}, aucune active")


def sev1_condition(project: Path, run: Runner, now: datetime) -> Condition:
    """No open ticket carries the `sev1` label.

    A repository without that label proves nothing by an empty answer (the agent never creates it),
    and a `gh` that fails says nothing: both are "non vérifiable".
    """
    try:
        labels = factory_slo.parse_stream(run(["gh", "label", "list", "--limit", "1000", "--json", "name"], project))
        if SEV1 not in {str(label.get("name")) for label in labels}:
            return Condition("sev1", UNVERIFIABLE, f"l'étiquette `{SEV1}` n'existe pas sur le dépôt : un dépôt sans elle ne prouve rien (l'agent ne la crée pas)")
        found = factory_slo.parse_stream(
            run(["gh", "issue", "list", "--state", "open", "--label", SEV1, "--limit", "1000", "--json", "number,title"], project)
        )
    except (RuntimeError, ValueError) as error:
        return Condition("sev1", UNVERIFIABLE, f"GitHub n'a pas répondu : {error}")
    if found:
        return Condition("sev1", NOT_MET, f"tickets `{SEV1}` ouverts : " + ", ".join(f"#{item['number']}" for item in found))
    return Condition("sev1", MET, f"aucun ticket `{SEV1}` ouvert")


def trial_facts(stdout: str) -> dict[str, str]:
    """The `KEY: value` lines the trial prints (`RESULTAT`, `TETE`, `ETAPE`, `RAISON`); the first of each key."""
    facts: dict[str, str] = {}
    for line in stdout.splitlines():
        key, separator, value = line.partition(": ")
        if separator and key in TRIAL_KEYS:
            facts.setdefault(key, value.strip())
    return facts


def essai_condition(project: Path, run: Runner, now: datetime, script: Path, plugin: str | None) -> Condition:
    """The end-to-end trial passes on the head of the base.

    The trial is launched here, once, by `script` (the trial of the plugin by default, a stand-in in the
    tests). Only a `RESULTAT: PASS`, exit 0, on exactly the head of the base and on an unmodified tree
    holds; a `FAIL` does not; anything else (a key absent, a wrong call, no result line, a head it cannot
    read, a script that does not run) is "non vérifiable".
    """
    f = factory_slo.Factory(project, now - timedelta(days=1), now, run)
    base_head = f.git("rev-parse", "--verify", "--quiet", f.base_ref())
    if not base_head or not base_head.strip():
        return Condition("essai", UNVERIFIABLE, f"la tête de la base `{f.base_ref()}` est illisible")
    base_head = base_head.strip()
    command = [sys.executable, str(script), "--projet", str(project), *(["--plugin", plugin] if plugin else [])]
    try:
        done = subprocess.run(
            command, cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=TRIAL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return Condition("essai", UNVERIFIABLE, f"l'essai n'a pas pu tourner : {error}")
    facts = trial_facts(done.stdout)
    if "SANS-OBJET" in done.stdout and "RESULTAT" not in facts:
        return Condition("essai", UNVERIFIABLE, " ".join(done.stdout.split()))
    result = facts.get("RESULTAT")
    if result == "FAIL":
        return Condition("essai", NOT_MET, f"l'essai a échoué à l'étape {facts.get('ETAPE', '?')} : {facts.get('RAISON', 'raison non donnée')}")
    if done.returncode != 0 or result != "PASS":
        detail = (done.stderr.strip() or done.stdout.strip() or "aucune sortie")[:300]
        return Condition("essai", UNVERIFIABLE, f"l'essai n'a pas rendu de résultat net (sortie {done.returncode}) : {detail}")
    tried = facts.get("TETE", "")
    sha = tried.split()[0] if tried else ""
    if not HEX_SHA.fullmatch(sha):
        return Condition("essai", UNVERIFIABLE, f"la tête essayée est illisible : `{tried}`")
    if "arbre modifié" in tried:
        return Condition("essai", NOT_MET, f"l'essai a passé sur {sha[:12]} avec un arbre modifié : il ne prouve pas la tête de la base")
    if sha != base_head:
        return Condition("essai", NOT_MET, f"l'essai a passé sur {sha[:12]}, la tête de la base est {base_head[:12]}")
    return Condition("essai", MET, f"l'essai passe sur la tête de la base {base_head[:12]}")


CONDITIONS: dict[str, Callable[[Path, Runner, datetime], Condition]] = {
    "slo": slo_condition,
    "budget": budget_condition,
    "sev1": sev1_condition,
}
CONDITION_NAMES = (*CONDITIONS, "essai")


def conditions_for(args: argparse.Namespace) -> dict[str, Callable[[Path, Runner, datetime], Condition]]:
    """The four conditions, the trial bound to the script and the plugin of the call."""
    essai = functools.partial(essai_condition, script=args.essai or TRIAL_SCRIPT, plugin=args.plugin)
    return {**CONDITIONS, "essai": essai}


def run_tag(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    """The tag name of a version: the pattern of the key `release-tag` with the version in it.

    Never guessed: no key, or several patterns, or a pattern without `{version}`, or a version that is
    not a number is refused (code 2) or "sans objet". A tag that already exists is refused too, because a
    tag is never moved or deleted: the agent writes no tag name by hand.
    """
    templates = usine.load(args.projet).get(TAG_KEY)
    if not templates:
        print(f"sans objet (clé `{TAG_KEY}` absente), aucun nom de tag n'est deviné")
        return 0
    if len(templates) > 1:
        raise ReleaseError(f"`{TAG_KEY}` : {len(templates)} motifs déclarés, l'agent n'en choisit pas : la publication revient à l'humain")
    template = templates[0]
    if VERSION_MARK not in template:
        raise ReleaseError(f"`{TAG_KEY}` : `{template}` ne contient pas `{VERSION_MARK}`")
    if not VERSION.fullmatch(args.version):
        raise ReleaseError(f"la version `{args.version}` n'est pas un numéro de version (chiffres, lettres, `.`, `+`, `-`, en commençant par un chiffre)")
    name = template.replace(VERSION_MARK, args.version)
    f = factory_slo.Factory(args.projet, now - timedelta(days=1), now, run)
    if f.git("rev-parse", "--verify", "--quiet", f"refs/tags/{name}") is not None:
        raise ReleaseError(f"le tag `{name}` existe déjà : un tag ne se déplace ni ne se supprime")
    print(f"TAG: {name}")
    return 0


def run_condition(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    print(conditions_for(args)[args.name](args.projet, run, now).line())
    return 0


NOT_RUN = (
    "essai non lancé : il coûte de vrais appels de modèle et une autre condition manque déjà ; "
    "la publication revient à l'humain, qui l'essaiera à son geste de version"
)


def check(args: argparse.Namespace, run: Runner, now: datetime) -> dict:
    """The decision: `sans objet`, `rien` (nothing is due), `publier` or `humain`, with what it rests on.

    The conditions are read once the trigger is reached, the three cheap ones first; the trial, which
    costs real model calls, is launched only when they all hold.
    """
    trigger = due(args.projet, run, now)
    document: dict = {
        "declencheur": {
            "statut": trigger.status, "texte": trigger.text, "fusions_en_attente": trigger.waiting,
            "plus_ancienne": trigger.oldest.isoformat() if trigger.oldest else None,
        },
        "conditions": [],
        "manque": [],
    }
    if not trigger.reached:
        document["decision"] = "sans objet" if trigger.status == ABSENT else "rien"
        return document
    available = conditions_for(args)
    results = [available[name](args.projet, run, now) for name in CONDITIONS]
    if all(result.held for result in results):
        results.append(available["essai"](args.projet, run, now))
    else:
        results.append(Condition("essai", UNVERIFIABLE, NOT_RUN))
    document["conditions"] = [{"nom": r.name, "statut": r.status, "texte": r.text} for r in results]
    document["manque"] = [r.name for r in results if not r.held]
    document["decision"] = "humain" if document["manque"] else "publier"
    return document


def run_check(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    document = check(args, run, now)
    if args.json:
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return 0
    print(f"DECISION: {document['decision']}")
    print(f"DECLENCHEUR: {document['declencheur']['texte']}")
    for item in document["conditions"]:
        print(Condition(item["nom"], item["statut"], item["texte"]).line())
    if document["manque"]:
        print("MANQUE: " + ", ".join(document["manque"]))
    return 0


def main(argv: list[str] | None = None, run: Runner | None = None, now: datetime | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    trigger = commands.add_parser("trigger", help="whether a version is due")
    trigger.add_argument("projet", type=Path)
    condition = commands.add_parser("condition", help="one condition of the release")
    condition.add_argument("name", choices=CONDITION_NAMES)
    named = commands.add_parser("tag", help="the tag name of a version, from the key `release-tag`")
    named.add_argument("projet", type=Path)
    named.add_argument("version")
    whole = commands.add_parser("check", help="the trigger, the four conditions and the decision")
    whole.add_argument("--json", action="store_true")
    for sub in (condition, whole):
        sub.add_argument("projet", type=Path)
        sub.add_argument("--plugin", help="the plugin the trial tries (the checkout of the head of the base)")
        sub.add_argument("--essai", type=Path, help="the trial script (default: e2e_trial.py next to this script)")
    args = parser.parse_args(argv)
    run = run or factory_slo.run_command
    moment = now or datetime.now(timezone.utc)
    handlers = {"trigger": run_trigger, "condition": run_condition, "check": run_check, "tag": run_tag}
    try:
        return handlers[args.command](args, run, moment)
    except ReleaseError as error:
        print(f"release: {error}", file=sys.stderr)
        return WRONG_CALL


if __name__ == "__main__":
    sys.exit(main())
