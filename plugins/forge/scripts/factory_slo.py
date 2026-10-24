"""Compute the service indicators (SLI) of the factory, without any model.

    python factory_slo.py sli <project> --depuis DATE [--jusqua DATE] [--json] [--reference FILE]

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
from datetime import datetime
from pathlib import Path

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
        return self.cached("prs", lambda: self.gh("pr", "list", "--state", "all", "--limit", "1000", "--json", fields))  # type: ignore[return-value]

    @property
    def defects(self) -> list[dict]:
        """The `escaped-defect` tickets opened in the window."""
        fields = "number,title,body,state,createdAt,closedAt,labels"
        found = self.cached(
            "defects",
            lambda: self.gh("issue", "list", "--state", "all", "--label", ESCAPED, "--limit", "1000", "--json", fields),
        )
        return [item for item in found if self.inside(when(item, "createdAt"))]  # type: ignore[union-attr]

    @property
    def created(self) -> list[dict]:
        return [item for item in self.prs if self.inside(when(item, "createdAt"))]

    @property
    def merged(self) -> list[dict]:
        return [item for item in self.prs if self.inside(when(item, "mergedAt"))]

    @property
    def base(self) -> str:
        info = self.cached("repo", lambda: self.gh("repo", "view", "--json", "nameWithOwner,defaultBranchRef"))
        return str(info[0]["defaultBranchRef"]["name"])  # type: ignore[index]

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
        return self.cached(key, lambda: self.gh("api", f"repos/{{owner}}/{{repo}}/issues/{ticket}/events", "--paginate"))  # type: ignore[return-value]

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
            if posed and posed[0] <= merged:  # type: ignore[operator]
                samples.append((merged - posed[0]).total_seconds())  # type: ignore[operator]
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
        if tags:
            samples.append((min(tags) - when(item, "mergedAt")).total_seconds())  # type: ignore[operator]
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
        severity = next((m.group(1) for name in sorted(label_names(defect)) if (m := SEVERITY.match(name))), "sans gravité")
        groups.setdefault(severity, []).append((fixed - when(defect, "createdAt")).total_seconds())  # type: ignore[operator]
    if not groups:
        return Sli("restore-time", reason="aucun `escaped-defect` de la fenêtre n'a encore de correctif fusionné")
    by = {
        name: {"echantillons": len(vals), "mediane_h": hours(median(vals)), "p90_h": hours(percentile(vals, 90))}
        for name, vals in sorted(groups.items())
    }
    text = ", ".join(f"{name} : médiane {v['mediane_h']} h ({v['echantillons']})" for name, v in by.items())
    return Sli("restore-time", data={"par_gravite": by, "ouverts": open_ones}, text=text + (f" ; {open_ones} sans correctif" if open_ones else ""))


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


def _date(text: str) -> datetime:
    try:
        return token_audit.parse_time(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"`{text}` n'est pas une date ISO (2026-10-20, en UTC sans zone)") from None


def main(argv: list[str] | None = None, run: Runner = run_command) -> int:
    parser = argparse.ArgumentParser(prog="factory_slo.py", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="commande", required=True)
    sli = commands.add_parser("sli", help="calcule les indicateurs de service")
    sli.add_argument("projet", type=Path, help="le dossier du projet")
    sli.add_argument("--depuis", type=_date, required=True, help="début de la fenêtre, inclus")
    sli.add_argument("--jusqua", type=_date, help="fin de la fenêtre, exclue (maintenant par défaut)")
    sli.add_argument("--json", action="store_true", help="rend du JSON au lieu d'un tableau Markdown")
    sli.add_argument("--reference", type=Path, help="le dernier résultat du jeu de référence (JSON)")
    args = parser.parse_args(argv)

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
