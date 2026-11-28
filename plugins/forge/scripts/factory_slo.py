"""Compute the service indicators (SLI) of the factory, without any model.

    python factory_slo.py sli <project> --depuis DATE [--jusqua DATE] [--json] [--reference FILE]
    python factory_slo.py status <project> [--json] [--reference FILE]
    python factory_slo.py budget <project> [--json] [--reference FILE]
    python factory_slo.py report <project> [--json] [--reference FILE] [--publier]
    python factory_slo.py changelog <project> --depuis DATE [--le DATE] [--reference FILE]
    python factory_slo.py queue <project> <ticket> [<ticket> ...] [--json]
    python factory_slo.py incidents <project> [--json]
    python factory_slo.py baseline <project> [--depuis DATE] [--jusqua DATE] [--essai DATE [--le DATE]] [--json]

`status` reads the `slo` key (`<sli> | <comparator> <target> | <window in days>`, one per line), computes
each objective on its sliding window, its error budget and its state (`tenu`, `menacé`, `épuisé`),
and writes them to `<git-common-dir>/forge/slo-status.json` with the date and the head of the base.
A line it cannot read, or that names an unknown SLI, fails the command and writes nothing. A key
`slo` absent is "sans objet". It also reads the key `slo-review-date` (`YYYY-MM-DD`, the day the
targets are due for review): the output says whether that date is past (`revision` in the state file),
an absent key is "sans objet", an unreadable or repeated date fails the command.

`budget` recalculates `status`, then says which actions of the `budget-action` key are active
(`human-merge`, `feature-freeze`, `alert`: an action is active once the objective of its SLI is
`épuisé`, and until it is back to `tenu`), and reports an action that was active in the previous
state file and ended. It is what
`forge:qc` and `forge:feature-build` run at the start of a pass. A key `budget-action` absent is
"sans objet" and computes nothing; a line it cannot read, an SLI the `slo` key does not hold, or
actions without the `slo` key fail the command (code 1).

`report` is `status` plus the trend against the previous window of the same length, and writes
nothing; with `--publier` it rewrites the report in one comment of the issue named by the key
`slo-issue` (found again by a hidden marker) and sets or removes `needs-your-attention` there as
objectives go `menacé` or `épuisé`, or all back to `tenu`. `changelog` prints the section "Objectifs
de service" of a release entry: the state of each objective at `--le` (now by default) and the
`escaped-defect` tickets opened since `--depuis`. A key `slo-issue` absent is "sans objet".

`queue` orders tickets (given in the order of the sub-issues) by class (`sev1`, then a ticket carrying the
label of the `speed-label` key, which marks a ticket whose goal is the factory's own lead time, then
`sev2`, `sev3`, then none), then by the nearest deadline to take them in charge according to the `sla` key,
then in the order given. A key `sla` absent is "sans objet": the severity still sorts, no deadline is
guessed. A key `speed-label` absent is "sans objet": the order is the one without it. A key repeated fails
the command.

`incidents` counts the blameless reviews of the folder the key `incident-dir` names (see `incident.py`)
by class of fix, `mécanique` and `jugement`, a class with no review counting 0. A review `incident.py`
refuses (no fix, a fix that does not match its class, a path that does not exist) is counted in no
class, listed with its faults, and the command exits 1. It reads the folder only, never GitHub. A key
`incident-dir` absent is "sans objet": no count, never 0; a folder not created yet holds no review.

`baseline` is the reading of story 18 of the autonomous factory, taken before the dispatcher: on one window
(30 days before `--jusqua`, now by default, unless `--depuis` says otherwise) the p90 lead time (the `lead-time`
indicator), the human's interventions per merged ticket and the tokens per merged PR (`tokens-per-merge`), each
with its window and its denominator. An intervention is a `needs-your-attention` label posed on a ticket
merged in the window or on a PR that closed it, plus a merge by a login of the key `accepting-human` (the
short identifier of its line, else its whole value) of a PR that does not carry `agent-merged`: the agent
merges under the human's account and labels what it merged. A key `accepting-human` absent leaves the merges
"sans objet" and counts the labels only. The markdown output is the text of the comment to post.

With `--essai DATE` (the first day of the trial) `baseline` reads a second window, [`--essai`, `--le`), `--le`
now by default, the base window then ending on `--essai` unless `--jusqua` says otherwise, and applies the rule
of the decision point: "oui" if and only if the p90 lead time of the trial is below the base's, the
interventions per ticket of the trial do not exceed the base's, and the dispatcher's trace of this host
(`~/.claude/hooks/state/dispatch/<day>.jsonl`, `event` `question`) holds no `post-default` on a case `H<n>` in
the trial; else "non", with each reason. A measure a window cannot give is a reason, never a "oui".

`baseline` also counts, whatever the windows, the tickets published after the key `ticket-size-max` entered
`docs/agents/usine.md` on the base branch (the date of the first commit that holds its line) that reached the
cap of the key `ticket-pr-cap`, the PRs of a ticket counted as `guard_pr_cap.py` counts them (target 0). A key
`ticket-size-max` or `ticket-pr-cap` absent, or a key line no commit of the base holds, is "sans objet".

The data come from GitHub (`gh ... --json`, run from the project folder, so `gh` finds the
repository itself), from git, from the logs `token_audit.py` reads, and from the journal of the
guards' refusals (`refusal_journal.py`), which lives on the host: `guard-refusals` is "sans objet"
without it, and counts the refusals of this host only. Prints a Markdown table, or
JSON with `--json`. The window is [depuis, jusqua), `jusqua` defaulting to now.

The end-to-end review has two indicators of its own (`matrix-coverage`, `review-regressions`, helpers in
`revue_indicateurs.py`), read from the `matrice.md` and the `revue/boucle.tsv` of the features under the key `feature-dir` (absent: "sans objet"); `report` prints them in
a section of its own.

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
import functools
import json
import math
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import budget  # noqa: E402  the hooks' reader of the `budget-action` key
import guard_pr_cap  # noqa: E402  the hooks' reader of the PR cap keys, and its way of citing a ticket
import incident  # noqa: E402  the reader of a blameless review and of the key `incident-dir`
import refusal_journal  # noqa: E402  the journal of the guards' refusals
import revue_boucle  # noqa: E402  the journal of the end-to-end review loop
import revue_indicateurs  # noqa: E402  the matrices and journals of that loop
import sla  # noqa: E402  the hooks' reader of the `sla` key and the severity classes
import token_audit  # noqa: E402  the sibling script, as base_replay.py imports `usine`
import usine  # noqa: E402

Runner = Callable[[list[str], Path], str]

ESCAPED = "escaped-defect"
READY = "ready-for-agent"
ATTENTION = "needs-your-attention"
SEVERITY = re.compile(r"^(?:gravite|gravité|severity):(.+)$")
VERDICT = re.compile(r"^VERDICT:[ \t]*(ACCEPT|REJECT)[ \t]*$", re.MULTILINE)
ROUND = re.compile(r"^ROUND:[ \t]*([1-9]\d*)[ \t]*$", re.MULTILINE)
ESCAPED_FROM = re.compile(r"Échappé de #(\d+)")
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
    def severe(self) -> list[dict]:
        """The tickets of a severity class that are open, or were opened in the window."""
        fields = "number,title,body,state,createdAt,closedAt,labels"
        found: dict[int, dict] = {}
        for name in sla.CLASSES:
            items = self.cached(
                f"severe-{name}",
                functools.partial(
                    self.gh, "issue", "list", "--state", "all", "--label", name, "--limit", "1000", "--json", fields
                ),
            )
            for item in cast("list[dict]", items):
                if str(item.get("state")).upper() != "CLOSED" or self.inside(when(item, "createdAt")):
                    found[int(item["number"])] = item
        return [found[number] for number in sorted(found)]

    @property
    def review_features(self) -> list[revue_indicateurs.Feature] | None:
        """The features of the key `feature-dir`, None when the key is absent."""
        directories = self.required(revue_indicateurs.FEATURE_KEY)
        return revue_indicateurs.features(self.project, directories) if directories else None

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


def closed_tickets_of(item: dict) -> set[int]:
    """Les tickets que la PR ferme (`Closes`), sans ceux qu'elle ne fait que citer par `Refs`."""
    return {int(ref["number"]) for ref in item.get("closingIssuesReferences") or []}


def rejected(item: dict) -> bool:
    """Whether a comment of the PR carries a `VERDICT: REJECT`, whatever its round."""
    return any("REJECT" in VERDICT.findall(str(comment.get("body") or "")) for comment in item.get("comments") or [])


def rework_rate(f: Factory) -> Sli:
    """The share of the PRs merged in the window that went through at least one `VERDICT: REJECT`."""
    merged = f.merged
    reworked = sum(rejected(item) for item in merged)
    return ratio("rework-rate", reworked, len(merged), "aucune PR fusionnée dans la fenêtre")


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


def first_tag_date(f: Factory, patterns: list[re.Pattern[str]], oid: str | None) -> datetime | None:
    """The date of the first version tag that holds the commit, None when it is in none."""
    out = f.git("tag", "--contains", oid, "--format=%(refname:short)\t%(creatordate:iso-strict)") if oid else None
    tags = []
    for row in (out or "").splitlines():
        name, _, date = row.partition("\t")
        if date and any(pattern.match(name) for pattern in patterns):
            tags.append(token_audit.parse_time(date))
    return min(tags) if tags else None


def release_lag(f: Factory) -> Sli:
    templates = f.required("release-tag")
    if not templates:
        return Sli("release-lag", reason="clé `release-tag` absente")
    patterns = [tag_pattern(template) for template in templates]
    samples: list[float] = []
    unpublished = 0
    for item in f.merged:
        published = first_tag_date(f, patterns, (item.get("mergeCommit") or {}).get("oid"))
        merged = when(item, "mergedAt")
        if published is not None and merged is not None:
            samples.append((published - merged).total_seconds())
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
        names = label_names(defect)
        severity = sla.severity_of(names) or next(
            (m.group(1) for name in sorted(names) if (m := SEVERITY.match(name))), "sans gravité"
        )
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


GUARDS = ("guard_git", "guard_coder", "guard_readonly")


def guard_refusals(f: Factory) -> Sli:
    """Refusals of the three guards per merged PR, from the journal of this host (`refusal_journal.py`).

    Only the lines of this project's repository count, and only those of `GUARDS`: the journal also
    holds the refusals of `after_write`, which this indicator leaves out. The journal is local: two
    hosts give two journals, which the indicator's text says.
    """
    merged = len(f.merged)
    if not merged:
        return Sli("guard-refusals", reason="aucune PR fusionnée dans la fenêtre")
    lines = refusal_journal.read(f.since, f.until)
    if lines is None:
        return Sli("guard-refusals", reason=f"pas de journal des refus : `{refusal_journal.journal_dir()}` n'existe pas sur ce poste")
    repo = refusal_journal.repo_of(str(f.project))
    ours = [line for line in lines if line.get("repo") == repo and line.get("guard") in GUARDS]
    def count(key: str) -> dict[str, int]:
        return dict(Counter(str(line.get(key, "")) for line in ours).most_common())

    value = round(len(ours) / merged, 2)
    return Sli(
        "guard-refusals",
        data={
            "numerateur": len(ours), "denominateur": merged, "valeur": value,
            "par_garde": count("guard"), "par_agent": count("agent"),
        },
        text=f"{value} refus par PR fusionnée ({len(ours)}/{merged}), journal de ce poste seulement",
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


ABSENT_FEATURE_DIR = f"sans objet (clé `{revue_indicateurs.FEATURE_KEY}` absente)"


def matrix_coverage(f: Factory) -> Sli:
    """The rows `tenu` or `écarté` over all the rows of the matrices of the features, as they stand."""
    name = "matrix-coverage"
    found = f.review_features
    if found is None:
        return Sli(name, reason=ABSENT_FEATURE_DIR)
    held, total, unreadable = revue_indicateurs.coverage_of(found)
    return ratio(name, held, total, "aucune matrice de feature à lire", illisibles=len(unreadable))


def review_regressions(f: Factory) -> Sli:
    """The identifiers that were a gap again after a fix, over those that were ever a gap in a round."""
    name = "review-regressions"
    found = f.review_features
    if found is None:
        return Sli(name, reason=ABSENT_FEATURE_DIR)
    returned: dict[str, int] = {}
    seen = 0
    for feature in found:
        if not feature.journal.is_file():
            continue
        count, gaps = revue_boucle.returns_of(feature.journal.read_text(encoding="utf-8").splitlines())
        seen += len(gaps)
        returned.update({f"F-{feature.number}/{identifier}": n for identifier, n in count.items()})
    return ratio(name, len(returned), seen, "aucun écart dans un journal de la boucle de revue", retours=returned)


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
        change_failure(f), restore_time(f), tokens_per_merge(f), guard_refusals(f), human_touch(f), main_green(f),
        reference("judge-recall", ref), reference("false-accept", ref),
        *review_slis(f),
    ]


def review_slis(f: Factory) -> list[Sli]:
    """The two indicators of the end-to-end review: they need the files, nothing else."""
    return [matrix_coverage(f), review_regressions(f)]


class SloError(ValueError):
    """A line of the `slo` key that cannot be read, or that names an unknown SLI."""


RATIO, DURATION, COUNT = "ratio", "durée", "compte"
KINDS = {
    "accept-round-1": RATIO, "rework-rate": RATIO, "escaped-defects": RATIO, "change-failure": RATIO,
    "human-touch": RATIO, "main-green": RATIO, "judge-recall": RATIO, "false-accept": RATIO,
    "matrix-coverage": RATIO, "review-regressions": RATIO,
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


REVISION_KEY = "slo-review-date"


def revision_date(project: Path, now: datetime) -> dict:
    """The review date of the objectives (key `slo-review-date`, `YYYY-MM-DD`), and whether it is past.

    The date itself is not past yet: the review is due that day (UTC), late the day after. An absent
    key is "sans objet", no date is guessed; an unreadable or repeated date fails like a bad `slo` line.
    """
    values = usine.load(project).get(REVISION_KEY)
    if not values:
        return {"statut": "sans objet", "raison": f"clé `{REVISION_KEY}` absente"}
    if len(values) > 1:
        raise SloError(f"`{REVISION_KEY}` : une seule date attendue, {len(values)} lignes déclarées")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", values[0]):
        raise SloError(f"`{REVISION_KEY}` : `{values[0]}` : attendu une date `AAAA-MM-JJ`")
    try:
        due = date.fromisoformat(values[0])
    except ValueError:
        raise SloError(f"`{REVISION_KEY}` : `{values[0]}` n'est pas une date du calendrier") from None
    return {"date": values[0], "passee": due < now.astimezone(timezone.utc).date()}


def revision_markdown(revision: dict) -> str:
    if revision.get("statut") == "sans objet":
        return f"Révision des objectifs : sans objet ({revision['raison']})."
    if revision["passee"]:
        return f"Révision des objectifs : passée, prévue le {revision['date']}. Les cibles sont à réviser."
    return f"Révision des objectifs : prévue le {revision['date']}."


def status(project: Path, now: datetime, run: Runner = run_command, ref: Path | None = None) -> dict | None:
    """The state of every `slo` objective of the project, or None when the key is absent."""
    lines = usine.load(project).get("slo")
    if not lines:
        return None
    objectives = parse_slo(lines)
    revision = revision_date(project, now)
    windows: dict[int, dict[str, Sli]] = {}
    for days in sorted({slo.days for slo in objectives}):
        results = compute(project, now - timedelta(days=days), now, run, ref)
        windows[days] = {item.name: item for item in results}
    base = Factory(project, now - timedelta(days=1), now, run)
    base_ref = base.base_ref()
    head = run(["git", "rev-parse", "--verify", base_ref], project).strip()
    return {
        "projet": str(project), "calcule_le": now.isoformat(), "base": base.base, "tete_base": head,
        "revision": revision,
        "objectifs": [evaluate(slo, windows[slo.days][slo.sli]) for slo in objectives],
    }


def state_path(project: Path, run: Runner = run_command) -> Path:
    common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], project).strip()
    return Path(common) / "forge" / "slo-status.json"


def write_state(path: Path, document: dict) -> None:
    """Write the state file, keeping from the previous one which budget actions are still held."""
    previous, unreadable = None, False
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
        unreadable = not isinstance(previous, dict)
    except FileNotFoundError:
        pass  # a first calculation: there is nothing to keep
    except (OSError, ValueError):
        unreadable = True  # the file exists and says nothing: `carry` keeps every action it cannot rule out
    budget.carry(previous, document, unreadable)
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
    if "revision" in document:
        lines += ["", revision_markdown(document["revision"])]
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
    document["sla"] = sla_check(project, now, run)
    document["revue"] = review_check(project, now, run)
    document["refus"] = refusal_check(project, now, run)
    return document


REFUSAL_DAYS = 30


def refusal_check(project: Path, now: datetime, run: Runner = run_command) -> dict:
    """`guard-refusals` over the last `REFUSAL_DAYS` days, with its detail by guard and by agent, or "sans objet" and why."""
    item = guard_refusals(Factory(project, now - timedelta(days=REFUSAL_DAYS), now, run))
    return {**item.to_dict(), "texte": item.text, "fenetre_jours": REFUSAL_DAYS}


def refusal_markdown(document: dict) -> str:
    """The section « Refus des gardes » of the report."""
    lines = [f"Refus des gardes, sur {document['fenetre_jours']} jours.", "", "| Indicateur | Valeur | Détail |", "|---|---|---|"]
    if document["statut"] == "sans objet":
        lines.append(f"| `{document['nom']}` | sans objet | {document['raison']} |")
    else:
        detail = " ; ".join(
            f"{label} : " + ", ".join(f"{name} : {n}" for name, n in document[key].items())
            for label, key in (("par garde", "par_garde"), ("par agent", "par_agent"))
        )
        lines.append(f"| `{document['nom']}` | {document['texte']} | {detail} |")
    return "\n".join(lines)


REVIEW_DAYS = 30
REVIEW_SLIS = ("matrix-coverage", "review-regressions")


def review_check(project: Path, now: datetime, run: Runner = run_command) -> dict:
    """The indicators of the end-to-end review over the last `REVIEW_DAYS` days, each one or "sans objet" and why."""
    results = {item.name: item for item in review_slis(Factory(project, now - timedelta(days=REVIEW_DAYS), now, run))}
    return {"fenetre_jours": REVIEW_DAYS, "indicateurs": [results[name].to_dict() for name in REVIEW_SLIS]}


def review_markdown(document: dict) -> str:
    """The section « Revue de bout en bout » of the report."""
    lines = [
        f"Revue de bout en bout, sur {document['fenetre_jours']} jours (la couverture et les retours se lisent à l'état actuel des matrices et des journaux).",
        "",
        "| Indicateur | Valeur |",
        "|---|---|",
    ]
    for item in document["indicateurs"]:
        if item["statut"] == "sans objet":
            lines.append(f"| `{item['nom']}` | sans objet : {item['raison']} |")
        else:
            lines.append(f"| `{item['nom']}` | {round(100 * item['valeur'])} % ({item['numerateur']}/{item['denominateur']}) |")
    return "\n".join(lines)


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
    if "sla" in document:
        lines += ["", sla_markdown(document["sla"], False)]
    if "revue" in document:
        lines += ["", review_markdown(document["revue"])]
    if "refus" in document:
        lines += ["", refusal_markdown(document["refus"])]
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
POSED_MARKER = re.compile(r"<!-- forge-slo-pose: (oui|non) -->")
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
    change of the set), and removed only when a report of ours had set it (the hidden marker `forge-slo-pose`
    says so) and every objective is `tenu` (a comment says why). An objective "sans objet" is neither held
    nor spent: the label stays. A label that a human set is left alone, even when a later report finds an
    objective `menacé`. The comment is pinned when it is created; a refusal of `gh` is reported, not fatal.
    """
    ticket = issue_number(project)
    if ticket is None:
        return None

    def gh(*args: str) -> list:
        return parse_stream(run(["gh", *args], project))

    def gh_text(*args: str) -> None:
        # `gh issue edit` et `gh issue comment` impriment une URL, pas du JSON : seul leur échec compte.
        run(["gh", *args], project)

    comments = [c for c in gh("api", "--paginate", f"repos/{{owner}}/{{repo}}/issues/{ticket}/comments") if isinstance(c, dict)]
    mine = next((c for c in comments if MARKER in str(c.get("body"))), None)
    found = STATES_MARKER.search(str(mine.get("body"))) if mine else None
    before: dict[str, str] = json.loads(found.group(1)) if found else {}
    was_set = mine is not None and (m := POSED_MARKER.search(str(mine.get("body")))) is not None and m.group(1) == "oui"
    info = gh("issue", "view", str(ticket), "--json", "labels")
    posed = ATTENTION in label_names(info[0] if info else {})
    now_bad = bad_states(document)
    all_held = all(item.get("etat") == TENU for item in document["objectifs"])
    # Un objectif « sans objet » n'est ni tenu ni épuisé : l'ensemble reste ce qu'il était.
    states = json.dumps(now_bad if now_bad or all_held else before, ensure_ascii=False).replace("--", "\\u002d\\u002d")
    # Posée par un de nos rapports : posée par nous maintenant, ou déjà posée par nous et toujours là.
    set_by_us = (bool(now_bad) and not posed) or (was_set and posed and not all_held)
    body = f"{MARKER}\n<!-- forge-slo-etats: {states} -->\n<!-- forge-slo-pose: {'oui' if set_by_us else 'non'} -->\n{report_markdown(document)}"
    actions: list[str] = []
    if mine:
        gh("api", "-X", "PATCH", f"repos/{{owner}}/{{repo}}/issues/comments/{mine['id']}", "-f", f"body={body}")
        actions.append(f"rapport réécrit dans le commentaire {mine['id']} du ticket #{ticket}")
    else:
        created = gh("api", f"repos/{{owner}}/{{repo}}/issues/{ticket}/comments", "-f", f"body={body}")
        actions.append(f"rapport posté dans un commentaire du ticket #{ticket}")
        node = created[0].get("node_id") if created and isinstance(created[0], dict) else None
        try:
            if not node:
                raise RuntimeError("la réponse ne donne pas l'identifiant du commentaire")
            gh("api", "graphql", "-f", "query=mutation($id: ID!) { pinIssueComment(input: {issueCommentId: $id}) { clientMutationId } }", "-f", f"id={node}")
            actions.append("commentaire épinglé")
        except RuntimeError as error:
            actions.append(f"commentaire non épinglé : {error}")
    if now_bad:
        if not posed:
            gh_text("issue", "edit", str(ticket), "--add-label", ATTENTION)
            actions.append(f"étiquette `{ATTENTION}` posée sur #{ticket}")
        if now_bad != before:
            gh_text("issue", "comment", str(ticket), "--body", f"`{ATTENTION}` : des objectifs de service ne tiennent plus.\n\n{reasons(document)}")
            actions.append(f"raison commentée sur #{ticket}")
    elif posed and was_set and all_held:
        gh_text("issue", "edit", str(ticket), "--remove-label", ATTENTION)
        gh_text("issue", "comment", str(ticket), "--body", f"`{ATTENTION}` retirée : tous les objectifs de service sont repassés à `tenu`.")
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


def run_budget(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    values = usine.load(args.projet).get(budget.KEY)
    if not values:
        print(f"Budget d'erreur : sans objet (clé `{budget.KEY}` absente), aucune action.")
        return 0
    lines, errors = budget.parse_actions(values)
    if errors:
        print(f"Clé `{budget.KEY}` mal formée :\n" + "\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    path = state_path(args.projet, run)
    try:
        before = json.loads(path.read_text(encoding="utf-8"))
        was = {(v.sli, v.action) for v in budget.evaluate(lines, before) if v.active}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        was = set()
    document = status(args.projet, now, run, args.reference)
    if document is None:
        print(f"La clé `{budget.KEY}` est déclarée mais la clé `slo` est absente : aucun état à lire.", file=sys.stderr)
        return 1
    write_state(path, document)
    verdicts = budget.evaluate(lines, document)
    missing = [v for v in verdicts if v.unknown]
    if missing:
        print("\n".join(f"- {v.sli} | {v.action} : {v.reason}" for v in missing), file=sys.stderr)
        return 1
    if args.json:
        actions = [
            {"sli": v.sli, "action": v.action, "active": v.active, "raison": v.reason,
             "rendue": (v.sli, v.action) in was and not v.active}
            for v in verdicts
        ]
        print(json.dumps({"calcule_le": document["calcule_le"], "actions": actions}, ensure_ascii=False, indent=2))
        return 0
    print(f"Budget d'erreur, état calculé le {document['calcule_le']} :")
    for v in verdicts:
        state = "ACTIVE" if v.active else "inactive"
        returned = " ; autonomie rendue : l'objectif est revenu à `tenu`" if (v.sli, v.action) in was and not v.active else ""
        print(f"- {state} : `{v.action}` sur `{v.sli}` ({v.reason}){returned}")
    return 0


def run_report(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    document = report(args.projet, now, run, args.reference)
    if document is None:
        print("Objectifs de service : sans objet (clé `slo` absente).")
        return 0
    print(json.dumps(document, ensure_ascii=False, indent=2) if args.json else report_markdown(document))
    if args.publier:
        # Avec --json, la sortie standard reste un seul document JSON : la publication va sur l'erreur standard.
        out = sys.stderr if args.json else sys.stdout
        actions = publish(args.projet, document, run)
        if actions is None:
            print("\nPublication : sans objet (clé `slo-issue` absente).", file=out)
        else:
            print("\nPublication :\n" + "\n".join(f"- {action}" for action in actions), file=out)
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


def load_sla(project: Path) -> dict[str, sla.Rule] | None:
    """The rules of the `sla` key, None when the key is absent; SloError when a line cannot be read."""
    values = usine.load(project).get(sla.KEY)
    if not values:
        return None
    rules, errors = sla.parse(values)
    if errors:
        raise SloError(f"clé `{sla.KEY}` mal formée :\n" + "\n".join(f"- {error}" for error in errors))
    return rules


ABSENT_SLA = f"sans objet (clé `{sla.KEY}` absente)"
ABSENT_SPEED = f"sans objet (clé `{sla.SPEED_KEY}` absente)"


def load_speed_label(project: Path) -> str | None:
    """The label of the `speed-label` key, None when the key is absent; SloError when it is repeated."""
    label, errors = sla.speed_label(usine.load(project).get(sla.SPEED_KEY))
    if errors:
        raise SloError("\n".join(errors))
    return label


SLA_DAYS = 30
UNRATED = "sans objet"


def sla_check(project: Path, now: datetime, run: Runner = run_command, since: datetime | None = None) -> dict | None:
    """Every severity ticket against its deadlines, or None when the `sla` key is absent."""
    rules = load_sla(project)
    if rules is None:
        return None
    since = since or now - timedelta(days=SLA_DAYS)
    f = Factory(project, since, now, run)
    patterns = [tag_pattern(template) for template in f.required("release-tag") or []]
    fixes: dict[int, dict] = {}
    for item in f.prs:
        merged = when(item, "mergedAt")
        if merged:
            for number in closed_tickets_of(item):
                if number not in fixes or merged < fixes[number]["merged"]:
                    fixes[number] = {"merged": merged, "oid": (item.get("mergeCommit") or {}).get("oid")}
    unavailable = {} if patterns else {sla.STAGES[2]: "clé `release-tag` absente"}
    tickets, breached = [], []
    for item in f.severe:
        number = int(item["number"])
        severity = sla.severity_of(label_names(item))
        opened = when(item, "createdAt")
        if severity is None or opened is None:
            continue
        closed = str(item.get("state")).upper() == "CLOSED"
        closed_at = (when(item, "closedAt") or now) if closed else None
        row: dict = {"ticket": number, "titre": item.get("title"), "gravite": severity, "ouvert_le": opened.isoformat(), "ferme": closed}
        if severity not in rules:
            reason = f"gravité `{severity}` absente de la clé `{sla.KEY}`"
            row["etapes"] = [{"etape": name, "echeance": None, "atteinte": None, "etat": UNRATED, "raison": reason} for name in sla.STAGES]
            tickets.append(row)
            continue
        taken = sorted(
            token_audit.parse_time(e["created_at"]) for e in f.events(number)
            if e.get("event") == "assigned" or (e.get("event") == "labeled" and (e.get("label") or {}).get("name") == "agent-claimed")
        )
        fix = fixes.get(number)
        reached = {
            sla.STAGES[0]: taken[0] if taken else None,
            sla.STAGES[1]: fix["merged"] if fix else None,
            sla.STAGES[2]: first_tag_date(f, patterns, fix["oid"]) if fix and patterns else None,
        }
        stages = sla.assess(rules[severity], opened, reached, now, closed_at, unavailable)
        row["etapes"] = [
            {
                "etape": s.stage, "echeance": s.deadline.isoformat(), "atteinte": s.reached.isoformat() if s.reached else None,
                "etat": s.state, **({"raison": s.reason} if s.reason else {}),
            }
            for s in stages
        ]
        breached += [
            {"ticket": number, "gravite": severity, "etape": s.stage, "echeance": s.deadline.isoformat(),
             "atteinte": s.reached.isoformat() if s.reached else None}
            for s in sla.breaches(stages)
        ]
        tickets.append(row)
    return {
        "projet": str(project), "calcule_le": now.isoformat(), "depuis": since.isoformat(),
        "tickets": tickets, "depassements": breached,
    }


def sla_markdown(document: dict | None, with_table: bool) -> str:
    if document is None:
        return f"Engagements de délai : {ABSENT_SLA}."
    lines = [
        f"Engagements de délai, au {document['calcule_le']} : {len(document['tickets'])} tickets de gravité "
        f"(ouverts, ou ouverts depuis le {document['depuis']}), {len(document['depassements'])} dépassements.",
        "",
    ]
    if with_table:
        lines += ["| Ticket | Gravité | " + " | ".join(sla.STAGES) + " |", "|---|---|---|---|---|"]
        for row in document["tickets"]:
            cells = " | ".join(
                stage["etat"] if stage["etat"] != UNRATED else f"sans objet ({stage['raison']})" for stage in row["etapes"]
            )
            lines.append(f"| #{row['ticket']} | {row['gravite']} | {cells} |")
        lines.append("")
    if document["depassements"]:
        lines.append("Dépassements :")
        lines += [
            f"- #{b['ticket']} ({b['gravite']}) : {b['etape']}, échéance {b['echeance']}, "
            + (f"atteinte {b['atteinte']}" if b["atteinte"] else "pas encore atteinte")
            for b in document["depassements"]
        ]
    else:
        lines.append("Dépassements : aucun.")
    return "\n".join(lines)


def run_sla(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    document = sla_check(args.projet, now, run, args.depuis)
    if args.json:
        print(json.dumps(document if document is not None else {"sla": ABSENT_SLA}, ensure_ascii=False, indent=2))
    else:
        print(sla_markdown(document, True))
    return 0


def run_queue(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    rules = load_sla(args.projet)
    speed = load_speed_label(args.projet)
    tickets = []
    for number in args.tickets:
        info = parse_stream(run(["gh", "issue", "view", str(number), "--json", "number,labels,createdAt"], args.projet))[0]
        tickets.append(sla.Ticket(int(info["number"]), label_names(info), token_audit.parse_time(info["createdAt"])))
    rows = []
    for item in sla.order(tickets, rules or {}, speed):
        deadline = sla.take_deadline(item, rules or {})
        rows.append({
            "ticket": item.number, "gravite": sla.severity_of(item.labels),
            "vitesse": speed is not None and speed in item.labels,
            "echeance": deadline.isoformat() if deadline else None,
        })
    note = ABSENT_SLA if rules is None else None
    speed_note = ABSENT_SPEED if speed is None else None
    if args.json:
        print(json.dumps({"file": rows, "echeances": note, "vitesse": speed_note}, ensure_ascii=False, indent=2))
        return 0
    print("File des tickets, par gravité (`sev1` d'abord, puis l'étiquette de vitesse de l'usine) puis par échéance de prise en charge :")
    for row in rows:
        speed_text = f", étiquette {speed}" if row["vitesse"] else ""
        print(f"- #{row['ticket']} : {row['gravite'] or 'sans gravité'}{speed_text}, échéance {row['echeance'] or 'sans objet'}")
    if note:
        print(f"Échéances : {note}.")
    if speed_note:
        print(f"Priorité de vitesse : {speed_note}.")
    return 0


def incidents(project: Path) -> dict | None:
    """The reviews of the `incident-dir` folder counted by class, or None when the key is absent."""
    folder = incident.incident_dir(project)
    if folder is None:
        return None
    classes = {name: 0 for name in incident.CLASSES}
    refused = []
    for path in incident.review_files(folder):
        try:
            review, errors = incident.read(path.read_text(encoding="utf-8"), project)
        except (OSError, UnicodeDecodeError) as error:
            review, errors = incident.Review(), [f"lecture impossible : {error}"]
        if errors or review.klass is None:
            refused.append({"fichier": path.name, "erreurs": errors})
        else:
            classes[review.klass] += 1
    return {
        "projet": str(project), "dossier": folder.relative_to(project.resolve()).as_posix(),
        "total": sum(classes.values()), "classes": classes, "refusees": refused,
    }


def incidents_markdown(document: dict) -> str:
    total = document["total"]
    lines = [
        f"Revues d'incident de `{document['dossier']}` : {total} revue{'s' if total > 1 else ''}, par classe de correctif.",
        "",
        "| Classe | Revues |",
        "|---|---|",
        *[f"| {name} | {count} |" for name, count in document["classes"].items()],
    ]
    if document["refusees"]:
        lines += ["", "Revues refusées, comptées dans aucune classe :"]
        for item in document["refusees"]:
            lines += [f"- {item['fichier']}"] + [f"  - {fault}" for fault in item["erreurs"]]
    return "\n".join(lines)


def run_incidents(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    try:
        document = incidents(args.projet)
    except incident.IncidentError as error:
        raise RuntimeError(str(error)) from error
    if document is None:
        absent = {incident.KEY: incident.ABSENT}
        print(json.dumps(absent, ensure_ascii=False, indent=2) if args.json else f"Revues d'incident : {incident.ABSENT}.")
        return 0
    print(json.dumps(document, ensure_ascii=False, indent=2) if args.json else incidents_markdown(document))
    return 1 if document["refusees"] else 0


BASELINE_DAYS = 30
AGENT_MERGED = "agent-merged"
HUMAN_KEY = "accepting-human"
ABSENT_HUMAN = f"sans objet (clé `{HUMAN_KEY}` absente)"


def merged_ledger(f: Factory) -> list[dict]:
    """The PRs merged in the window, with who merged them (`mergedBy`), which `prs` does not fetch."""
    fields = "number,state,labels,mergedAt,mergedBy,closingIssuesReferences"
    listed = cast("list[dict]", f.cached("ledger", lambda: f.gh("pr", "list", "--state", "merged", "--limit", "1000", "--json", fields)))
    return [item for item in listed if f.inside(when(item, "mergedAt"))]


def human_logins(f: Factory) -> set[str] | None:
    """The GitHub logins of the key `accepting-human`, None when the key is absent."""
    values = f.required(HUMAN_KEY)
    if not values:
        return None
    return {value.rpartition(" | ")[2].strip().lower() for value in values if value.strip()}


def attention_posed(f: Factory, number: int) -> int:
    """How many times `needs-your-attention` was posed on the ticket or the PR `number`."""
    return sum(1 for e in f.events(number) if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == ATTENTION)


def human_interventions(f: Factory) -> Sli:
    """The human's interventions per ticket merged in the window (spec, section 22)."""
    name = "interventions"
    closing = [item for item in merged_ledger(f) if closed_tickets_of(item)]
    tickets = {ticket for item in closing for ticket in closed_tickets_of(item)}
    if not tickets:
        return Sli(name, reason="aucun ticket fermé par une PR fusionnée dans la fenêtre")
    labels = sum(attention_posed(f, n) for n in sorted(tickets | {int(item["number"]) for item in closing}))
    humans = human_logins(f)
    merges: int | str = ABSENT_HUMAN
    if humans is not None:
        merges = sum(
            1 for item in closing
            if str((item.get("mergedBy") or {}).get("login", "")).lower() in humans and AGENT_MERGED not in label_names(item)
        )
    total = labels + (merges if isinstance(merges, int) else 0)
    data = {
        "numerateur": total, "denominateur": len(tickets), "valeur": round(total / len(tickets), 2),
        "etiquettes": labels, "fusions_humain": merges,
    }
    return Sli(name, data=data, text=f"{str(data['valeur']).replace('.', ',')} par ticket fusionné ({total}/{len(tickets)})")


def measure(project: Path, since: datetime, until: datetime, run: Runner) -> dict[str, Sli]:
    """The three measures of the baseline on the window [since, until)."""
    f = Factory(project, since, until, run)
    return {"delai": lead_time(f), "interventions": human_interventions(f), "jetons": tokens_per_merge(f)}


def measures_dict(since: datetime, until: datetime, found: dict[str, Sli]) -> dict:
    return {
        "depuis": since.isoformat(), "jusqua": until.isoformat(), "jours": (until - since).days,
        **{key: item.to_dict() for key, item in found.items()},
    }


def plural(count: int, word: str) -> str:
    """`count` and its noun, which takes an `s` above one, except the invariable `PR`."""
    return f"{count} {word}{'s' if count > 1 and word != 'PR' else ''}"


def measures_rows(found: dict[str, Sli]) -> list[str]:
    """The table rows of one window: the measure, its value, its denominator."""
    rows = []
    delay, touches, tokens = found["delai"], found["interventions"], found["jetons"]
    if delay.reason is not None:
        rows.append(f"| Délai p90 (`lead-time p90`) | sans objet | {delay.reason} |")
    else:
        count, apart = delay.data["echantillons"], delay.data["sans_evenement"]
        rows.append(
            f"| Délai p90 (`lead-time p90`) | p90 {number(delay.data['p90_h'])} h, médiane {number(delay.data['mediane_h'])} h"
            f" | {plural(count, 'ticket')} fusionnés avec une pose de `ready-for-agent` ({apart} sans pose, exclus) |"
        )
    if touches.reason is not None:
        rows.append(f"| Interventions de l'humain par ticket fusionné | sans objet | {touches.reason} |")
    else:
        merges = touches.data["fusions_humain"]
        said = plural(merges, "fusion") + " par l'humain" if isinstance(merges, int) else f"fusions par l'humain : {merges}"
        rows.append(
            f"| Interventions de l'humain par ticket fusionné | {touches.text}"
            f" | {plural(touches.data['denominateur'], 'ticket')} fusionnés ; {plural(touches.data['etiquettes'], 'étiquette')} `{ATTENTION}`, {said} |"
        )
    if tokens.reason is not None:
        rows.append(f"| Jetons par PR | sans objet | {tokens.reason} |")
    else:
        rows.append(
            f"| Jetons par PR | {tokens.data['valeur']} jetons par PR fusionnée ({tokens.data['jetons']}/{tokens.data['denominateur']})"
            f" | {plural(tokens.data['denominateur'], 'PR')} fusionnées, journaux de ce poste seulement |"
        )
    return rows


SIZE_KEY = "ticket-size-max"


def size_key_day(f: Factory) -> datetime | None:
    """When the line of the key `ticket-size-max` first entered `usine.md` on the base branch, None if never."""
    line = f"- `{SIZE_KEY}` : `"
    out = f.git("log", f.base_ref(), "--reverse", "--format=%cI", "-S", line, "--", usine.CONFIG_PATH.as_posix())
    first = (out or "").split()
    return token_audit.parse_time(first[0]) if first else None


def tickets_at_cap(f: Factory) -> Sli:
    """The tickets published after the key `ticket-size-max` that reached the PR cap (target 0).

    The PRs of a ticket are counted as `guard_pr_cap` counts them: open or merged, citing it by `Closes` or
    `Refs`, leaving out the exempt titles, those under `ticket-pr-cap-small` lines and those created before
    `ticket-pr-cap-since`. It does not apply the guard's one last PR for a ticket started before that day.
    """
    name = "ticket-pr-cap-reached"
    if not f.required(SIZE_KEY):
        return Sli(name, reason=f"clé `{SIZE_KEY}` absente")
    cap, cap_fault = guard_pr_cap.cap_of(f.config)
    since_day, since_fault = guard_pr_cap.since_of(f.config)
    exempt, exempt_fault = guard_pr_cap.exempt_of(f.config)
    small, small_fault = guard_pr_cap.small_of(f.config)
    for key, fault in ((guard_pr_cap.KEY, cap_fault), (guard_pr_cap.SINCE_KEY, since_fault), (guard_pr_cap.EXEMPT_KEY, exempt_fault), (guard_pr_cap.SMALL_KEY, small_fault)):
        if fault:
            raise ValueError(f"la clé `{key}` est illisible")
    if cap is None:
        return Sli(name, reason=f"clé `{guard_pr_cap.KEY}` absente")
    started = size_key_day(f)
    if started is None:
        return Sli(name, reason=f"aucun commit de `{f.base_ref()}` ne porte la clé `{SIZE_KEY}` : pas de date de départ")
    tickets = f.gh("issue", "list", "--state", "all", "--limit", "1000", "--json", "number,createdAt")
    published = {int(item["number"]) for item in tickets if (created := when(item, "createdAt")) is not None and created >= started}
    fields = "number,title,body,state,createdAt,additions,deletions"
    counts: Counter[int] = Counter()
    for item in f.gh("pr", "list", "--state", "all", "--limit", "1000", "--json", fields):
        if str(item.get("state")).upper() not in guard_pr_cap.COUNTED_STATES or str(item.get("title") or "").startswith(tuple(exempt)):
            continue
        if small is not None:
            added, removed = item.get("additions"), item.get("deletions")
            if type(added) is not int or type(removed) is not int:
                raise ValueError(f"PR #{item.get('number')} : `additions` ou `deletions` illisible")
            if added + removed < small:
                continue
        if since_day is not None:
            created_day = guard_pr_cap.created_on(item.get("createdAt"))
            if created_day is None:
                raise ValueError(f"PR #{item.get('number')} : `createdAt` illisible")
            if created_day < since_day:
                continue
        counts.update(int(ticket) for ticket in guard_pr_cap.cited(str(item.get("body") or "")))
    reached = sorted(ticket for ticket, count in counts.items() if ticket in published and count >= cap)
    data = {
        "numerateur": len(reached), "denominateur": sum(1 for ticket in counts if ticket in published),
        "tickets": reached, "cap": cap, "depuis": started.isoformat(),
    }
    return Sli(name, data=data, text=f"{len(reached)} (cible 0)")


def cap_line(found: Sli) -> str:
    head = f"Tickets publiés après `{SIZE_KEY}` au plafond de PR"
    if found.reason is not None:
        return f"{head} : sans objet ({found.reason})."
    data = found.data
    listed = "".join(f", #{ticket}" for ticket in data["tickets"])
    return (
        f"Tickets publiés après `{SIZE_KEY}` au plafond de {data['cap']} PR : {found.text}{listed} ;"
        f" sur {plural(data['denominateur'], 'ticket')} publiés depuis le {data['depuis'][:10]} qui ont une PR comptée."
    )


def window_section(label: str, since: datetime, until: datetime, found: dict[str, Sli]) -> list[str]:
    return [
        f"{label} : du {since:%Y-%m-%d} au {until:%Y-%m-%d} ({(until - since).days} jours), les fusions de la fenêtre.",
        "",
        "| Mesure | Valeur | Dénominateur |",
        "|---|---|---|",
        *measures_rows(found),
        "",
    ]


DISPATCH_EVENT = "question"
RESERVED_CASE = re.compile(r"H\d+")
DEFAULT_POSTED = "post-default"


def dispatch_dir() -> Path:
    """The folder of the dispatcher's trace (spec, G3), on this host: `<day>.jsonl`, one JSON line per event."""
    return Path.home() / ".claude" / "hooks" / "state" / "dispatch"


def reserved_gestures(project: Path, since: datetime, until: datetime) -> dict:
    """The default gestures the dispatcher took on a question of a reserved (`H`) case, in the window.

    A line of the trace counts when its `event` is `question`, its `project` is this project (the name of
    its repository, as `refusal_journal.repo_of` gives it, or its folder), its `date` is in the window, its
    `case` is `H<n>` and its `action` is `post-default`: a `remind-human` took no gesture. The trace lives on
    the host; a missing folder is said (`journal` false) and counts no gesture.
    """
    folder = dispatch_dir()
    if not folder.is_dir():
        return {"journal": False, "gestes": 0, "illisibles": 0}
    ours = {refusal_journal.repo_of(str(project)), str(project.resolve())} - {""}
    gestures = unreadable = 0
    for path in sorted(folder.glob("*.jsonl")):
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.strip():
                continue
            try:
                item = json.loads(raw)
                moment = token_audit.parse_time(item["date"])
            except (ValueError, KeyError, TypeError, AttributeError):
                unreadable += 1
                continue
            if item.get("event") != DISPATCH_EVENT or str(item.get("project")) not in ours or not since <= moment < until:
                continue
            if RESERVED_CASE.fullmatch(str(item.get("case"))) and item.get("action") == DEFAULT_POSTED:
                gestures += 1
    return {"journal": True, "gestes": gestures, "illisibles": unreadable}


def decide(base: dict[str, Sli], trial: dict[str, Sli], gestures: dict) -> dict:
    """The rule of the decision point (spec C11): "oui" if and only if no reason says "non".

    The p90 lead time must drop (strictly), the interventions per ticket must not rise, and the trace holds
    no default gesture of a reserved case. A measure one of the windows cannot give is a reason: it proves
    nothing.
    """
    reasons: list[str] = []
    for key, label in (("delai", "délai p90"), ("interventions", "interventions par ticket")):
        before, after = base[key], trial[key]
        missing = [f"{name} : {item.reason}" for name, item in (("base", before), ("essai", after)) if item.reason is not None]
        if missing:
            reasons.append(f"{label} : mesure sans objet ({' ; '.join(missing)})")
        elif key == "delai" and not after.data["p90_h"] < before.data["p90_h"]:
            reasons.append(f"le délai p90 ne baisse pas ({number(before.data['p90_h'])} h à {number(after.data['p90_h'])} h)")
        elif key == "interventions" and after.data["numerateur"] * before.data["denominateur"] > before.data["numerateur"] * after.data["denominateur"]:
            reasons.append(f"les interventions par ticket montent ({before.data['valeur']} à {after.data['valeur']})")
    if gestures["gestes"]:
        reasons.append(f"{plural(gestures['gestes'], 'geste')} d'une case `H` au journal des questions appliquées")
    return {"verdict": "non" if reasons else "oui", "raisons": reasons}


def gestures_line(gestures: dict) -> str:
    if not gestures["journal"]:
        return f"Journal des questions appliquées : aucun dossier `{dispatch_dir()}` sur ce poste, aucun geste lu."
    unread = f", {plural(gestures['illisibles'], 'ligne')} illisibles" if gestures["illisibles"] else ""
    return f"Journal des questions appliquées, de ce poste : {plural(gestures['gestes'], 'geste')} d'une case `H` dans l'essai{unread}."


def run_baseline(args: argparse.Namespace, run: Runner, now: datetime) -> int:
    trial_since, trial_until = args.essai, args.le or now
    if args.le and not args.essai:
        raise ValueError("`--le` ne va qu'avec `--essai`.")
    if trial_since and trial_until <= trial_since:
        raise ValueError("`--le` doit suivre `--essai`.")
    until = args.jusqua or trial_since or now
    since = args.depuis or until - timedelta(days=BASELINE_DAYS)
    if until <= since:
        raise ValueError("`--jusqua` doit suivre `--depuis`.")
    base = measure(args.projet, since, until, run)
    size = tickets_at_cap(Factory(args.projet, since, until, run))
    document: dict = {"projet": str(args.projet), "base": measures_dict(since, until, base), "taille": size.to_dict()}
    lines = [f"Relevé de l'usine pour `{args.projet.resolve().name}` (F-0003, story 18).", ""]
    if trial_since is None:
        lines += window_section("Fenêtre", since, until, base) + [cap_line(size)]
    else:
        trial = measure(args.projet, trial_since, trial_until, run)
        gestures = reserved_gestures(args.projet, trial_since, trial_until)
        verdict = decide(base, trial, gestures)
        document.update(essai=measures_dict(trial_since, trial_until, trial), journal_questions=gestures, verdict=verdict)
        lines += window_section("Base", since, until, base) + window_section("Essai", trial_since, trial_until, trial)
        lines += [gestures_line(gestures), "", cap_line(size), "", f"Point de décision : {verdict['verdict']}"]
        lines += [f"- {reason}" for reason in verdict["raisons"]]
    if args.json:
        print(json.dumps(document, ensure_ascii=False, indent=2))
    else:
        print("\n".join(lines).rstrip())
    return 0


def main(argv: list[str] | None = None, run: Runner = run_command, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory_slo.py", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="commande", required=True)
    state = commands.add_parser("status", help="calcule les objectifs de service et leur budget d'erreur")
    state.add_argument("projet", type=Path, help="le dossier du projet")
    state.add_argument("--json", action="store_true", help="rend du JSON au lieu d'un tableau Markdown")
    state.add_argument("--reference", type=Path, help="le dernier résultat du jeu de référence (JSON)")
    allowance = commands.add_parser("budget", help="recalcule l'état puis dit quelles actions de la clé `budget-action` sont actives")
    allowance.add_argument("projet", type=Path, help="le dossier du projet")
    allowance.add_argument("--json", action="store_true", help="rend du JSON au lieu de lignes")
    allowance.add_argument("--reference", type=Path, help="le dernier résultat du jeu de référence (JSON)")
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
    delays = commands.add_parser("sla", help="mesure les tickets de gravité contre les échéances de la clé `sla`")
    delays.add_argument("projet", type=Path, help="le dossier du projet")
    delays.add_argument("--depuis", type=_date, help=f"ouverture des tickets fermés à garder ({SLA_DAYS} jours avant maintenant par défaut)")
    delays.add_argument("--json", action="store_true", help="rend du JSON au lieu d'un tableau Markdown")
    file = commands.add_parser("queue", help="ordonne des tickets par gravité puis par échéance de prise en charge")
    file.add_argument("projet", type=Path, help="le dossier du projet")
    file.add_argument("tickets", type=int, nargs="+", help="les numéros de ticket, dans l'ordre des sous-issues")
    file.add_argument("--json", action="store_true", help="rend du JSON au lieu de lignes")
    count = commands.add_parser("incidents", help="compte les revues d'incident du dossier de la clé `incident-dir`, par classe de correctif")
    count.add_argument("projet", type=Path, help="le dossier du projet")
    count.add_argument("--json", action="store_true", help="rend du JSON au lieu d'un tableau Markdown")
    base = commands.add_parser("baseline", help="relève le délai p90, les interventions de l'humain par ticket et les jetons par PR")
    base.add_argument("projet", type=Path, help="le dossier du projet")
    base.add_argument("--depuis", type=_date, help=f"début de la fenêtre de base, inclus ({BASELINE_DAYS} jours avant `--jusqua` par défaut)")
    base.add_argument("--jusqua", type=_date, help="fin de la fenêtre de base, exclue (maintenant par défaut)")
    base.add_argument("--essai", type=_date, help="début de l'essai, inclus : relève aussi l'essai et rend le verdict du point de décision (la base finit là par défaut)")
    base.add_argument("--le", type=_date, help="fin de l'essai, exclue (maintenant par défaut), avec `--essai`")
    base.add_argument("--json", action="store_true", help="rend du JSON au lieu d'un tableau Markdown")
    sli =commands.add_parser("sli", help="calcule les indicateurs de service")
    sli.add_argument("projet", type=Path, help="le dossier du projet")
    sli.add_argument("--depuis", type=_date, required=True, help="début de la fenêtre, inclus")
    sli.add_argument("--jusqua", type=_date, help="fin de la fenêtre, exclue (maintenant par défaut)")
    sli.add_argument("--json", action="store_true", help="rend du JSON au lieu d'un tableau Markdown")
    sli.add_argument("--reference", type=Path, help="le dernier résultat du jeu de référence (JSON)")
    args = parser.parse_args(argv)

    if args.commande in ("status", "budget", "report", "changelog", "queue", "sla", "incidents", "baseline"):
        try:
            handler = {
                "status": run_status, "budget": run_budget, "report": run_report, "changelog": run_changelog,
                "queue": run_queue, "sla": run_sla, "incidents": run_incidents, "baseline": run_baseline,
            }[args.commande]
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
