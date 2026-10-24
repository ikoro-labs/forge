"""Compute the service indicators (SLI) of the factory, without any model.

    python factory_slo.py sli <project> --depuis DATE [--jusqua DATE] [--json] [--reference FILE]
    python factory_slo.py status <project> [--json] [--reference FILE]
    python factory_slo.py report <project> [--json] [--reference FILE] [--publier]
    python factory_slo.py changelog <project> --depuis DATE [--le DATE] [--reference FILE]

`status` reads the `slo` key (`<sli> | <comparator> <target> | <window in days>`, one per line), computes
each objective on its sliding window, its error budget and its state (`tenu`, `menacé`, `épuisé`),
and writes them to `<git-common-dir>/forge/slo-status.json` with the date and the head of the base.
A line it cannot read, or that names an unknown SLI, fails the command and writes nothing. A key
`slo` absent is "sans objet".

`report` is `status` plus the trend against the previous window of the same length, and writes
nothing; with `--publier` it rewrites the report in one comment of the issue named by the key
`slo-issue` (found again by a hidden marker) and sets or removes `needs-your-attention` there as
objectives go `menacé` or `épuisé`, or all back to `tenu`. `changelog` prints the section "Objectifs
de service" of a release entry: the state of each objective at `--le` (now by default) and the
`escaped-defect` tickets opened since `--depuis`. A key `slo-issue` absent is "sans objet".

The data come from GitHub (`gh ... --json`, run from the project folder, so `gh` finds the
repository itself), from git, and from the logs `token_audit.py` reads. Prints a Markdown table, or
JSON with `--json`. The window is [depuis, jusqua), `jusqua` defaulting to now.

An indicator its data cannot give (no PR in the window, a key of `docs/agents/usine.md` absent) is
"sans objet" with its reason: never 0, never 100 %. Keys read: `release-tag` (the pattern of the
version tags, `{version}` standing for the version), `required-contexts` (the checks of the base
branch), `protected-path` (the paths whose attention label is not a human-touch). A verdict comment
that cannot be read is ignored, and counted. The standard library only.

`--reference` names a JSON file `{"judge-recall": 0.9, "false-accept": 0.05}`, the last result of
the reference set; without it both indicators are "sans objet".
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import token_audit  # noqa: E402  the sibling script, as base_replay.py imports `usine`
import usine  # noqa: E402

Runner = Callable[[list[str], Path], str]

REWORK = "agent-rework"
ESCAPED = "escaped-defect"
READY = "ready-for-agent"
ATTENTION = "needs-your-attention"
SEVERITY = re.compile(r"^(?:gravite|gravité|severity):(.+)$")
VERDICT = re.compile(r"^VERDICT:[ \t]*(ACCEPT|REJECT)[ \t]*$", re.MULTILINE)
ROUND = re.compile(r"^ROUND:[ \t]*([12])[ \t]*$", re.MULTILINE)
ESCAPED_FROM = re.compile(r"Échappé de #(\d+)")
TICKET_REF = re.compile(r"\b(?:Closes|Refs)\s+#(\d+)")
REVERTS = re.compile(r"This reverts commit ([0-9a-f]{7,40})")
ATTENTION_LINE = re.compile(r"\*\*Attention\s*:\*\*\s*(.*)")
FAILING = {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}


@dataclass
class Sli:
    """One indicator: a computed value, or "sans objet" and why."""

    name: str
    reason: str | None = None
    data: dict = field(default_factory=dict)
    text: str = ""

    def to_dict(self) -> dict:
        if self.reason is not None:
            return {"nom": self.name, "statut": "sans objet", "raison": self.reason}
        return {"nom": self.name, "statut": "calculé", **self.data}


def run_command(cmd: list[str], cwd: Path) -> str:
    """The standard output of `cmd` run in `cwd`; RuntimeError when it fails or is missing."""
    try:
        done = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"`{' '.join(cmd[:3])}` n'a pas pu tourner : {error}") from error
    if done.returncode != 0:
        raise RuntimeError(f"`{' '.join(cmd[:3])}` a échoué : {done.stderr.strip()[:300]}")
    return done.stdout


def percentile(values: list[float], percent: int) -> float:
    """The nearest-rank percentile."""
    ordered = sorted(values)
    return ordered[max(1, math.ceil(percent / 100 * len(ordered))) - 1]


def median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def parse_stream(text: str) -> list:
    """The items of one JSON document, or of several arrays printed one after the other (`--paginate`)."""
    decoder, index, items = json.JSONDecoder(), 0, []
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        value, index = decoder.raw_decode(text, index)
        items.extend(value) if isinstance(value, list) else items.append(value)
    return items


def hours(delta_seconds: float) -> float:
    return round(delta_seconds / 3600, 1)


def label_names(item: dict) -> set[str]:
    return {str(label.get("name")) for label in item.get("labels") or [] if isinstance(label, dict)}


def when(item: dict, key: str) -> datetime | None:
    value = item.get(key)
    return token_audit.parse_time(value) if value else None


def ratio(name: str, numerator: int, denominator: int, empty: str, **extra: object) -> Sli:
    if not denominator:
        return Sli(name, reason=empty)
    data = {"numerateur": numerator, "denominateur": denominator, "valeur": round(numerator / denominator, 4), **extra}
    text = f"{round(100 * numerator / denominator)} % ({numerator}/{denominator})"
    return Sli(name, data=data, text=text)


def durations(name: str, samples: list[float], empty: str, **extra: object) -> Sli:
    if not samples:
        return Sli(name, reason=empty)
    data = {"mediane_h": hours(median(samples)), "p90_h": hours(percentile(samples, 90)), "echantillons": len(samples), **extra}
    return Sli(name, data=data, text=f"médiane {data['mediane_h']} h, p90 {data['p90_h']} h ({len(samples)})")


class Factory:
    """The facts of one project and one window, fetched once and shared by the indicators."""

    def __init__(self, project: Path, since: datetime, until: datetime, run: Runner) -> None:
        self.project, self.since, self.until, self.run = project, since, until, run
        self.config = usine.load(project)
        self._cache: dict[str, object] = {}

    def inside(self, moment: datetime | None) -> bool:
        return moment is not None and self.since <= moment < self.until

    def gh(self, *args: str) -> list:
        return parse_stream(self.run(["gh", *args], self.project))

    def cached(self, key: str, make: Callable[[], object]) -> object:
        if key not in self._cache:
            self._cache[key] = make()
        return self._cache[key]

    @property
    def prs(self) -> list[dict]:
        fields = "number,title,body,state,createdAt,mergedAt,closedAt,labels,mergeCommit,closingIssuesReferences,comments"
        return cast("list[dict]", self.cached("prs", lambda: self.gh("pr", "list", "--state", "all", "--limit", "1000", "--json", fields)))

    @property
    def defects(self) -> list[dict]:
        """The `escaped-defect` tickets opened in the window."""
        fields = "number,title,body,state,createdAt,closedAt,labels"
        found = self.cached(
            "defects",
            lambda: self.gh("issue", "list", "--state", "all", "--label", ESCAPED, "--limit", "1000", "--json", fields),
        )
        return [item for item in cast("list[dict]", found) if self.inside(when(item, "createdAt"))]

    @property
    def created(self) -> list[dict]:
        return [item for item in self.prs if self.inside(when(item, "createdAt"))]

    @property
    def merged(self) -> list[dict]:
        return [item for item in self.prs if self.inside(when(item, "mergedAt"))]

    @property
    def base(self) -> str:
        info = self.cached("repo", lambda: self.gh("repo", "view", "--json", "nameWithOwner,defaultBranchRef"))
        return str(cast("list[dict]", info)[0]["defaultBranchRef"]["name"])

    def git(self, *args: str) -> str | None:
        try:
            return self.run(["git", *args], self.project)
        except RuntimeError:
            return None

    def base_ref(self) -> str:
        remote = f"origin/{self.base}"
        return remote if self.git("rev-parse", "--verify", "--quiet", remote) is not None else self.base

    def events(self, ticket: int) -> list[dict]:
        key = f"events{ticket}"
        return cast("list[dict]", self.cached(key, lambda: self.gh("api", f"repos/{{owner}}/{{repo}}/issues/{ticket}/events", "--paginate")))

    def required(self, key: str) -> list[str] | None:
        return self.config.get(key) or None


def accept_round_1(f: Factory) -> Sli:
    accepted = judged = unreadable = 0
    for item in f.prs:
        first = None
        for comment in sorted(item.get("comments") or [], key=lambda c: str(c.get("createdAt"))):
            body = str(comment.get("body") or "")
            if "VERDICT:" not in body:
                continue
            verdict, rnd = VERDICT.search(body), ROUND.search(body)
            if not (verdict and rnd):
                if f.inside(when(comment, "createdAt")):
                    unreadable += 1
                continue
            if rnd.group(1) == "1" and first is None:
                first = (verdict.group(1), when(comment, "createdAt"))
        if first and f.inside(first[1]):
            judged += 1
            accepted += first[0] == "ACCEPT"
    return ratio("accept-round-1", accepted, judged, "aucune PR jugée au tour 1 dans la fenêtre", illisibles=unreadable)


def tickets_of(item: dict) -> set[int]:
    cited = {int(ref["number"]) for ref in item.get("closingIssuesReferences") or []}
    return cited | {int(n) for n in TICKET_REF.findall(str(item.get("body") or ""))}


def closed_tickets_of(item: dict) -> set[int]:
    """Les tickets que la PR ferme (`Closes`), sans ceux qu'elle ne fait que citer par `Refs`."""
    return {int(ref["number"]) for ref in item.get("closingIssuesReferences") or []}


def rework_rate(f: Factory) -> Sli:
    entrusted: set[int] = set()
    reworked: set[int] = set()
    for item in f.created:
        tickets = tickets_of(item)
        entrusted |= tickets
        if REWORK in label_names(item):
            reworked |= tickets
    return ratio("rework-rate", len(reworked), len(entrusted), "aucun ticket confié à un coder dans la fenêtre")


def escaped_defects(f: Factory) -> Sli:
    return ratio("escaped-defects", len(f.defects), len(f.merged), "aucune PR fusionnée dans la fenêtre")


def lead_time(f: Factory) -> Sli:
    samples: list[float] = []
    no_event = 0
    for item in f.merged:
        merged = when(item, "mergedAt")
        for ticket in sorted(closed_tickets_of(item)):
            posed = sorted(
                token_audit.parse_time(e["created_at"])
                for e in f.events(ticket)
                if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == READY
            )
            if posed and merged is not None and posed[0] <= merged:
                samples.append((merged - posed[0]).total_seconds())
            else:
                no_event += 1
    return durations("lead-time", samples, "aucun ticket fusionné avec une pose de `ready-for-agent`", sans_evenement=no_event)


def tag_pattern(template: str) -> re.Pattern[str]:
    return re.compile("^" + re.escape(template).replace(re.escape("{version}"), r"[0-9][^\s]*") + "$")


def release_lag(f: Factory) -> Sli:
    templates = f.required("release-tag")
    if not templates:
        return Sli("release-lag", reason="clé `release-tag` absente")
    patterns = [tag_pattern(template) for template in templates]
    samples: list[float] = []
    unpublished = 0
    for item in f.merged:
        oid = (item.get("mergeCommit") or {}).get("oid")
        out = f.git("tag", "--contains", oid, "--format=%(refname:short)\t%(creatordate:iso-strict)") if oid else None
        tags = []
        for row in (out or "").splitlines():
            name, _, date = row.partition("\t")
            if date and any(pattern.match(name) for pattern in patterns):
                tags.append(token_audit.parse_time(date))
        merged = when(item, "mergedAt")
        if tags and merged is not None:
            samples.append((min(tags) - merged).total_seconds())
        else:
            unpublished += 1
    if not f.merged:
        return Sli("release-lag", reason="aucune PR fusionnée dans la fenêtre")
    return durations("release-lag", samples, "aucune fusion de la fenêtre n'est encore dans un tag de version", non_publiees=unpublished)


def change_failure(f: Factory) -> Sli:
    merged = f.merged
    log = f.git("log", f.base_ref(), f"--since={f.since.isoformat()}", f"--until={f.until.isoformat()}", "--format=%B%x1e") or ""
    reverted = {sha for entry in log.split("\x1e") for sha in REVERTS.findall(entry)}
    cited = {int(n) for defect in f.defects for n in ESCAPED_FROM.findall(str(defect.get("body") or ""))}
    failed = 0
    for item in merged:
        oid = str((item.get("mergeCommit") or {}).get("oid") or "")
        if item["number"] in cited or (oid and any(oid.startswith(sha) for sha in reverted)):
            failed += 1
    return ratio("change-failure", failed, len(merged), "aucune PR fusionnée dans la fenêtre")


def restore_time(f: Factory) -> Sli:
    defects = f.defects
    if not defects:
        return Sli("restore-time", reason="aucun `escaped-defect` ouvert dans la fenêtre")
    fixes: dict[int, datetime] = {}
    for item in f.prs:
        merged = when(item, "mergedAt")
        if merged:
            for ticket in closed_tickets_of(item):
                fixes[ticket] = min(merged, fixes.get(ticket, merged))
    groups: dict[str, list[float]] = {}
    open_ones = 0
    for defect in defects:
        fixed = fixes.get(int(defect["number"]))
        if fixed is None:
            open_ones += 1
            continue
        opened = when(defect, "createdAt")
        if opened is None:
            continue
        severity = next((m.group(1) for name in sorted(label_names(defect)) if (m := SEVERITY.match(name))), "sans gravité")
        groups.setdefault(severity, []).append((fixed - opened).total_seconds())
    if not groups:
        return Sli("restore-time", reason="aucun `escaped-defect` de la fenêtre n'a encore de correctif fusionné")
    by = {
        name: {"echantillons": len(vals), "mediane_h": hours(median(vals)), "p90_h": hours(percentile(vals, 90))}
        for name, vals in sorted(groups.items())
    }
    every = [value for values in groups.values() for value in values]
    text = ", ".join(f"{name} : médiane {v['mediane_h']} h ({v['echantillons']})" for name, v in by.items())
    return Sli("restore-time", data={"par_gravite": by, "ouverts": open_ones, "mediane_h": hours(median(every)), "p90_h": hours(percentile(every, 90)), "echantillons": len(every)}, text=text + (f" ; {open_ones} sans correctif" if open_ones else ""))


def tokens_per_merge(f: Factory) -> Sli:
    merged = len(f.merged)
    if not merged:
        return Sli("tokens-per-merge", reason="aucune PR fusionnée dans la fenêtre")
    config = token_audit.config_dir()
    if not (config / "projects").is_dir():
        return Sli("tokens-per-merge", reason=f"pas de journaux : `{config / 'projects'}` n'existe pas")
    calls, bad = token_audit.read_calls(config, f.project, since=f.since, until=f.until)
    total = sum(sum(call.tokens) for call in calls)
    value = round(total / merged)
    return Sli(
        "tokens-per-merge",
        data={"jetons": total, "denominateur": merged, "valeur": value, "lignes_illisibles": bad},
        text=f"{value} jetons ({total}/{merged})",
    )


def human_touch(f: Factory) -> Sli:
    protected = f.config.get("protected-path", [])
    touched = 0
    for item in f.created:
        report = ATTENTION_LINE.search(str(item.get("body") or ""))
        reason = report.group(1).strip() if report else ""
        said_none = reason.lower().startswith("aucune")
        if ATTENTION not in label_names(item) and (not report or said_none):
            continue
        if reason and any(path in reason for path in protected):
            continue
        touched += 1
    return ratio("human-touch", touched, len(f.created), "aucune PR ouverte dans la fenêtre")


def main_green(f: Factory) -> Sli:
    contexts = f.required("required-contexts")
    if not contexts:
        return Sli("main-green", reason="clé `required-contexts` absente")
    log = f.git("log", f.base_ref(), "--first-parent", f"--since={f.since.isoformat()}", f"--until={f.until.isoformat()}", "--format=%H")
    commits = (log or "").split()
    if not commits:
        return Sli("main-green", reason="aucun commit de la branche de base dans la fenêtre")
    green = red = unknown = 0
    for sha in commits:
        answer = f.gh("api", f"repos/{{owner}}/{{repo}}/commits/{sha}/check-runs")
        runs: dict[str, str] = {}
        for page in answer:
            for check in page.get("check_runs") or []:
                runs[str(check.get("name"))] = str(check.get("conclusion"))
        states = [runs.get(context) for context in contexts]
        if any(state in FAILING for state in states):
            red += 1
        elif all(state == "success" for state in states):
            green += 1
        else:
            unknown += 1
    return ratio("main-green", green, green + red, "aucun commit de la base n'a de résultat pour les checks exigés", inconnus=unknown)


def reference(name: str, path: Path | None) -> Sli:
    if path is None:
        return Sli(name, reason="aucun résultat du jeu de référence (option `--reference` absente)")
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get(name)
    except (OSError, ValueError, AttributeError):
        return Sli(name, reason=f"résultat du jeu de référence illisible : `{path}`")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return Sli(name, reason=f"`{name}` absent du résultat du jeu de référence")
    return Sli(name, data={"valeur": value}, text=f"{round(100 * value)} %")


def compute(project: Path, since: datetime, until: datetime, run: Runner = run_command, ref: Path | None = None) -> list[Sli]:
    f = Factory(project, since, until, run)
    return [
        accept_round_1(f), rework_rate(f), escaped_defects(f), lead_time(f), release_lag(f),
        change_failure(f), restore_time(f), tokens_per_merge(f), human_touch(f), main_green(f),
        reference("judge-recall", ref), reference("false-accept", ref),
    ]


class SloError(ValueError):
    """A line of the `slo` key that cannot be read, or that names an unknown SLI."""


RATIO, DURATION, COUNT = "ratio", "durée", "compte"
KINDS = {
    "accept-round-1": RATIO, "rework-rate": RATIO, "escaped-defects": RATIO, "change-failure": RATIO,
    "human-touch": RATIO, "main-green": RATIO, "judge-recall": RATIO, "false-accept": RATIO,
    "lead-time": DURATION, "release-lag": DURATION, "restore-time": DURATION,
    "tokens-per-merge": COUNT,
}
STATS = {"p90": "p90_h", "mediane": "mediane_h", "médiane": "mediane_h"}
UNITS = {RATIO: "%", DURATION: "h", COUNT: "jetons"}
TARGET = re.compile(r"^(>=|<=)\s*(\d+(?:[.,]\d+)?)\s*(%|h|jetons)?$")
TENU, MENACE, EPUISE = "tenu", "menacé", "épuisé"
THREATENED_ABOVE = 0.75


@dataclass(frozen=True)
class Slo:
    """One objective: the SLI (and its statistic, for a duration), a comparator, a target, a window."""

    line: str
    sli: str
    stat: str | None
    comparator: str
    target: float
    unit: str
    days: int

    @property
    def label(self) -> str:
        return f"{self.sli} {self.stat}" if self.stat else self.sli


def parse_slo(lines: list[str]) -> list[Slo]:
    """The objectives of the `slo` key; SloError names every faulty line, none is ignored."""
    objectives: list[Slo] = []
    faults: list[str] = []
    for line in lines:
        try:
            objectives.append(parse_one(line))
        except SloError as error:
            faults.append(f"`slo` : `{line}` : {error}")
    if faults:
        raise SloError("\n".join(faults))
    return objectives


def parse_one(line: str) -> Slo:
    parts = usine.split_value(line, 3)
    if parts is None:
        raise SloError("attendu `<sli> | <comparateur> <cible> | <fenêtre en jours>`")
    name_part, target_part, window_part = parts
    words = name_part.split()
    if len(words) > 2:
        raise SloError("le nom est un SLI, suivi au plus de `p90` ou `mediane`")
    sli, stat = words[0], (words[1] if len(words) == 2 else None)
    if sli not in KINDS:
        raise SloError(f"SLI inconnu `{sli}` (connus : {', '.join(sorted(KINDS))})")
    kind = KINDS[sli]
    if kind == DURATION and stat is None:
        raise SloError(f"`{sli}` est une durée : ajouter `p90` ou `mediane` après son nom")
    if kind != DURATION and stat is not None:
        raise SloError(f"`{sli}` n'a pas de statistique : retirer `{stat}`")
    if stat is not None and stat not in STATS:
        raise SloError(f"statistique inconnue `{stat}` (`p90` ou `mediane`)")
    found = TARGET.match(target_part)
    if not found:
        raise SloError("la cible est `>=` ou `<=`, un nombre et son unité")
    comparator, number, unit = found.group(1), float(found.group(2).replace(",", ".")), found.group(3)
    if kind != COUNT and unit != UNITS[kind]:
        raise SloError(f"`{sli}` se mesure en `{UNITS[kind]}` : la cible doit porter cette unité")
    if kind == COUNT and unit not in (None, "jetons"):
        raise SloError("`tokens-per-merge` se mesure en jetons, sans autre unité")
    if kind == RATIO and number > 100:
        raise SloError(f"un ratio ne dépasse pas 100 % : `{found.group(2)} %` est hors d'atteinte, sans doute une faute de frappe")
    if kind != RATIO and comparator == ">=":
        raise SloError(f"`>=` n'a pas de budget pour `{sli}` : une borne haute seule en donne un")
    if not window_part.isdigit() or int(window_part) < 1:
        raise SloError("la fenêtre est un nombre entier de jours, au moins 1")
    return Slo(line, sli, stat, comparator, number, UNITS[kind], int(window_part))


def measured(slo: Slo, sli: Sli) -> float:
    """The value the objective compares, in the unit of its target."""
    if KINDS[slo.sli] == RATIO:
        return round(100 * float(sli.data["valeur"]), 2)
    if KINDS[slo.sli] == DURATION and slo.stat is not None:
        return float(sli.data[STATS[slo.stat]])
    return float(sli.data["valeur"])


def evaluate(slo: Slo, sli: Sli) -> dict:
    """Value, error budget and state of one objective over the SLI computed on its window.

    The budget is the gap the target allows: from perfect (100 %) for a ratio `>=`, from zero for
    `<=`. The share consumed is what the value has already used of it; the state is `tenu` up to
    75 % consumed, `menacé` above, `épuisé` from 100 %.
    """
    base = {
        "ligne": slo.line, "sli": slo.sli, "statistique": slo.stat, "comparateur": slo.comparator,
        "cible": slo.target, "unite": slo.unit, "fenetre_jours": slo.days,
    }
    if sli.reason is not None:
        return {**base, "statut": "sans objet", "raison": sli.reason}
    value = measured(slo, sli)
    allowed = 100 - slo.target if slo.comparator == ">=" else slo.target
    used = max(0.0, 100 - value) if slo.comparator == ">=" else max(0.0, value)
    consumed = round(used / allowed, 4) if allowed > 0 else (0.0 if used == 0 else 1.0)
    state = EPUISE if consumed >= 1 else MENACE if consumed > THREATENED_ABOVE else TENU
    return {
        **base, "statut": "calculé", "valeur": value, "budget": round(allowed, 4),
        "consomme": consumed, "reste": round(max(0.0, allowed - used), 4), "etat": state,
    }


def status(project: Path, now: datetime, run: Runner = run_command, ref: Path | None = None) -> dict | None:
    """The state of every `slo` objective of the project, or None when the key is absent."""
    lines = usine.load(project).get("slo")
    if not lines:
        return None
    objectives = parse_slo(lines)
    windows: dict[int, dict[str, Sli]] = {}
    for days in sorted({slo.days for slo in objectives}):
        results = compute(project, now - timedelta(days=days), now, run, ref)
        windows[days] = {item.name: item for item in results}
    base = Factory(project, now - timedelta(days=1), now, run)
    base_ref = base.base_ref()
    head = run(["git", "rev-parse", "--verify", base_ref], project).strip()
    return {
        "projet": str(project), "calcule_le": now.isoformat(), "base": base.base, "tete_base": head,
        "objectifs": [evaluate(slo, windows[slo.days][slo.sli]) for slo in objectives],
    }


def state_path(project: Path, run: Runner = run_command) -> Path:
    common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], project).strip()
    return Path(common) / "forge" / "slo-status.json"


def write_state(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(path.name + ".tmp")
    scratch.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    scratch.replace(path)


def number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def status_markdown(document: dict) -> str:
    lines = [
        f"Objectifs de service de `{document['projet']}`, calculés le {document['calcule_le']}.",
        "",
        "| Objectif | Cible | Fenêtre | Valeur | Budget consommé | État |",
        "|---|---|---|---|---|---|",
    ]
    for item in document["objectifs"]:
        label = f"{item['sli']} {item['statistique']}" if item["statistique"] else item["sli"]
        unit = f" {item['unite']}" if item["unite"] != "jetons" else ""
        head = f"| `{label}` | {item['comparateur']} {number(item['cible'])}{unit} | {item['fenetre_jours']} j |"
        if item["statut"] == "sans objet":
            lines.append(f"{head} sans objet | {item['raison']} | sans objet |")
        else:
            lines.append(f"{head} {number(item['valeur'])}{unit} | {round(100 * item['consomme'])} % | {item['etat']} |")
    return "\n".join(lines)


def markdown(results: list[Sli], project: Path, since: datetime, until: datetime) -> str:
    lines = [
        f"Indicateurs de service de `{project}`, de {since.isoformat()} à {until.isoformat()}.",
        "",
        "| SLI | Valeur | Détail |",
        "|---|---|---|",
    ]
    for item in results:
        if item.reason is not None:
            lines.append(f"| `{item.name}` | sans objet | {item.reason} |")
            continue
        extra = {k: v for k, v in item.data.items() if k not in {"numerateur", "denominateur", "valeur", "mediane_h", "p90_h", "echantillons", "par_gravite", "jetons"}}
        detail = ", ".join(f"{k.replace('_', ' ')} : {v}" for k, v in extra.items())
        lines.append(f"| `{item.name}` | {item.text} | {detail} |")
    return "\n".join(lines)


def trend(current: dict, previous: dict) -> str:
    """How the share of budget consumed moved from the previous window to this one."""
    if current["statut"] == "sans objet":
        return "sans objet"
    if previous["statut"] == "sans objet":
        return "sans point de comparaison"
    gap = round(current["consomme"] - previous["consomme"], 4)
    return "stable" if gap == 0 else "dégradation" if gap > 0 else "amélioration"


def report(project: Path, now: datetime, run: Runner = run_command, ref: Path | None = None) -> dict | None:
    """`status` with, for each objective, the same window one length earlier and the trend between them."""
    document = status(project, now, run, ref)
    if document is None:
        return None
    windows: dict[int, dict[str, Sli]] = {}
    for days in sorted({item["fenetre_jours"] for item in document["objectifs"]}):
        results = compute(project, now - timedelta(days=2 * days), now - timedelta(days=days), run)
        windows[days] = {item.name: item for item in results}
    for item in document["objectifs"]:
        slo = parse_one(item["ligne"])
        item["precedent"] = evaluate(slo, windows[slo.days][slo.sli])
        item["tendance"] = trend(item, item["precedent"])
    return document


def label_of(item: dict) -> str:
    return f"{item['sli']} {item['statistique']}" if item["statistique"] else item["sli"]


def unit_of(item: dict) -> str:
    return "" if item["unite"] == "jetons" else f" {item['unite']}"


def objective_row(item: dict, with_trend: bool) -> str:
    unit = unit_of(item)
    head = f"| `{label_of(item)}` | {item['comparateur']} {number(item['cible'])}{unit} | {item['fenetre_jours']} j |"
    if item["statut"] == "sans objet":
        return f"{head} sans objet | {item['raison']} | sans objet |" + (" sans objet |" if with_trend else "")
    left = f"{number(item['reste'])}{unit} sur {number(item['budget'])}{unit}"
    row = f"{head} {number(item['valeur'])}{unit} | {left} | {item['etat']} |"
    if not with_trend:
        return row
    before = item.get("precedent") or {}
    was = f" (était {number(before['valeur'])}{unit})" if before.get("statut") == "calculé" else ""
    return f"{row} {item['tendance']}{was} |"


def table(document: dict, with_trend: bool) -> list[str]:
    head = "| Objectif | Cible | Fenêtre | Valeur | Budget restant | État |" + (" Tendance |" if with_trend else "")
    rule = "|---|---|---|---|---|---|" + ("---|" if with_trend else "")
    return [head, rule, *(objective_row(item, with_trend) for item in document["objectifs"])]


def report_markdown(document: dict) -> str:
    lines = [
        f"Objectifs de service de `{document['projet']}`, calculés le {document['calcule_le']}.",
        "",
        *table(document, True),
        "",
        "La tendance compare la part du budget consommée à celle de la fenêtre précédente, de même durée.",
    ]
    return "\n".join(lines)


def changelog_section(document: dict, defects: list[dict], since: datetime, at: datetime) -> str:
    lines = ["### Objectifs de service", "", f"État de chaque objectif au {at.date().isoformat()}.", "", *table(document, False), ""]
    if defects:
        lines += [f"`escaped-defect` ouverts depuis le {since.date().isoformat()} :", ""]
        lines += [f"- #{d['number']} {d['title']} ({'fermé' if str(d.get('state')).upper() == 'CLOSED' else 'ouvert'})" for d in defects]
    else:
        lines.append(f"Aucun `escaped-defect` ouvert depuis le {since.date().isoformat()}.")
    return "\n".join(lines)


MARKER = "<!-- forge-slo-report -->"
STATES_MARKER = re.compile(r"<!-- forge-slo-etats: (.*?) -->")
WORSE = (MENACE, EPUISE)


def issue_number(project: Path) -> int | None:
    """The tracking issue of the key `slo-issue` (`55` or `#55`), None when the key is absent."""
    values = usine.load(project).get("slo-issue")
    if not values:
        return None
    text = values[0].strip().lstrip("#")
    if not text.isdigit() or int(text) < 1:
        raise SloError(f"`slo-issue` : `{values[0]}` : attendu un numéro de ticket (`55` ou `#55`)")
    return int(text)


def bad_states(document: dict) -> dict[str, str]:
    return {item["ligne"]: item["etat"] for item in document["objectifs"] if item.get("etat") in WORSE}


def reasons(document: dict) -> str:
    return "\n".join(
        f"- `{item['ligne']}` : {item['etat']}, {round(100 * item['consomme'])} % du budget consommé"
        for item in document["objectifs"] if item.get("etat") in WORSE
    )


def publish(project: Path, document: dict, run: Runner = run_command) -> list[str] | None:
    """Rewrite the report comment of the tracking issue and keep its attention label true; the actions taken.

    The label is set when an objective goes `menacé` or `épuisé` (a comment gives the reason, once per
    change of the set), and removed only when the previous report had set it and no objective is worse
    than `tenu` any more (a comment says why). A label that no report of ours had justified is left alone.
    """
    ticket = issue_number(project)
    if ticket is None:
        return None

    def gh(*args: str) -> list:
        return parse_stream(run(["gh", *args], project))

    comments = [c for c in gh("api", "--paginate", f"repos/{{owner}}/{{repo}}/issues/{ticket}/comments") if isinstance(c, dict)]
    mine = next((c for c in comments if MARKER in str(c.get("body"))), None)
    found = STATES_MARKER.search(str(mine.get("body"))) if mine else None
    before: dict[str, str] = json.loads(found.group(1)) if found else {}
    now_bad = bad_states(document)
    states = json.dumps(now_bad, ensure_ascii=False).replace("--", "\\u002d\\u002d")
    body = f"{MARKER}\n<!-- forge-slo-etats: {states} -->\n{report_markdown(document)}"
    actions: list[str] = []
    if mine:
        gh("api", "-X", "PATCH", f"repos/{{owner}}/{{repo}}/issues/comments/{mine['id']}", "-f", f"body={body}")
        actions.append(f"rapport réécrit dans le commentaire {mine['id']} du ticket #{ticket}")
    else:
        gh("api", f"repos/{{owner}}/{{repo}}/issues/{ticket}/comments", "-f", f"body={body}")
        actions.append(f"rapport posté dans un commentaire du ticket #{ticket}")
    info = gh("issue", "view", str(ticket), "--json", "labels")
    posed = ATTENTION in label_names(info[0] if info else {})
    if now_bad:
        if not posed:
            gh("issue", "edit", str(ticket), "--add-label", ATTENTION)
            actions.append(f"étiquette `{ATTENTION}` posée sur #{ticket}")
        if now_bad != before:
            gh("issue", "comment", str(ticket), "--body", f"`{ATTENTION}` : des objectifs de service ne tiennent plus.\n\n{reasons(document)}")
            actions.append(f"raison commentée sur #{ticket}")
    elif posed and before:
        gh("issue", "edit", str(ticket), "--remove-label", ATTENTION)
        gh("issue", "comment", str(ticket), "--body", f"`{ATTENTION}` retirée : tous les objectifs de service sont repassés à `tenu`.")
        actions.append(f"étiquette `{ATTENTION}` retirée de #{ticket}, avec sa raison")
    return actions


def _date(text: str) -> datetime:
    try:
        return token_audit.parse_time(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"`{text}` n'est pas une date ISO (2026-10-20, en UTC sans zone)") from None


def run_status(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    document = status(args.projet, now, run, args.reference)
    if document is None:
        print("Objectifs de service : sans objet (clé `slo` absente).")
        return 0
    write_state(state_path(args.projet, run), document)
    print(json.dumps(document, ensure_ascii=False, indent=2) if args.json else status_markdown(document))
    return 0


def run_report(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    document = report(args.projet, now, run, args.reference)
    if document is None:
        print("Objectifs de service : sans objet (clé `slo` absente).")
        return 0
    print(json.dumps(document, ensure_ascii=False, indent=2) if args.json else report_markdown(document))
    if args.publier:
        actions = publish(args.projet, document, run)
        if actions is None:
            print("\nPublication : sans objet (clé `slo-issue` absente).")
        else:
            print("\nPublication :\n" + "\n".join(f"- {action}" for action in actions))
    return 0


def run_changelog(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    at = args.le or now
    if at <= args.depuis:
        print("`--le` doit suivre `--depuis`.", file=sys.stderr)
        return 1
    document = status(args.projet, at, run, args.reference)
    if document is None:
        print("Objectifs de service : sans objet (clé `slo` absente).")
        return 0
    defects = Factory(args.projet, args.depuis, at, run).defects
    print(changelog_section(document, defects, args.depuis, at))
    return 0


def main(argv: list[str] | None = None, run: Runner = run_command, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory_slo.py", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="commande", required=True)
    state = commands.add_parser("status", help="calcule les objectifs de service et leur budget d'erreur")
    state.add_argument("projet", type=Path, help="le dossier du projet")
    state.add_argument("--json", action="store_true", help="rend du JSON au lieu d'un tableau Markdown")
    state.add_argument("--reference", type=Path, help="le dernier résultat du jeu de référence (JSON)")
    rapport = commands.add_parser("report", help="rend le rapport des objectifs, avec la tendance ; --publier l'écrit dans l'issue de suivi")
    rapport.add_argument("projet", type=Path, help="le dossier du projet")
    rapport.add_argument("--json", action="store_true", help="rend du JSON au lieu d'un tableau Markdown")
    rapport.add_argument("--reference", type=Path, help="le dernier résultat du jeu de référence (JSON)")
    rapport.add_argument("--publier", action="store_true", help="réécrit le rapport dans l'issue de la clé `slo-issue` et tient son étiquette")
    notes = commands.add_parser("changelog", help="rend la section « Objectifs de service » d'une entrée du CHANGELOG")
    notes.add_argument("projet", type=Path, help="le dossier du projet")
    notes.add_argument("--depuis", type=_date, required=True, help="date de la version précédente, incluse")
    notes.add_argument("--le", type=_date, help="date de la version (maintenant par défaut)")
    notes.add_argument("--reference", type=Path, help="le dernier résultat du jeu de référence (JSON)")
    sli = commands.add_parser("sli", help="calcule les indicateurs de service")
    sli.add_argument("projet", type=Path, help="le dossier du projet")
    sli.add_argument("--depuis", type=_date, required=True, help="début de la fenêtre, inclus")
    sli.add_argument("--jusqua", type=_date, help="fin de la fenêtre, exclue (maintenant par défaut)")
    sli.add_argument("--json", action="store_true", help="rend du JSON au lieu d'un tableau Markdown")
    sli.add_argument("--reference", type=Path, help="le dernier résultat du jeu de référence (JSON)")
    args = parser.parse_args(argv)

    if args.commande in ("status", "report", "changelog"):
        try:
            handler = {"status": run_status, "report": run_report, "changelog": run_changelog}[args.commande]
            return handler(args, run, now or datetime.now(tz=timezone.utc))
        except (RuntimeError, ValueError, KeyError, IndexError, OSError) as error:
            print(f"Calcul impossible : {error}", file=sys.stderr)
            return 1
    until = args.jusqua or datetime.now(tz=args.depuis.tzinfo)
    if until <= args.depuis:
        print("`--jusqua` doit suivre `--depuis`.", file=sys.stderr)
        return 1
    try:
        results = compute(args.projet, args.depuis, until, run, args.reference)
    except (RuntimeError, ValueError, KeyError, IndexError) as error:
        print(f"Calcul impossible : {error}", file=sys.stderr)
        return 1
    if args.json:
        document = {
            "projet": str(args.projet), "depuis": args.depuis.isoformat(), "jusqua": until.isoformat(),
            "sli": [item.to_dict() for item in results],
        }
        print(json.dumps(document, ensure_ascii=False, indent=2))
    else:
        print(markdown(results, args.projet, args.depuis, until))
    return 0


if __name__ == "__main__":
    sys.exit(main())
