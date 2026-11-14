"""The factory report mail: built from the keys of `docs/agents/usine.md`, sent on events only.

    report_mail.py [--root <dir>] [--state-dir <dir>]     print the mail (HTML) on standard output
    report_mail.py [--root <dir>] [--state-dir <dir>] --sent   record the mail printed last as sent

Exit code: 0 when a mail is due, 10 when nothing happened since the last one sent (nothing is
printed), 2 on a missing key or a usage error, 1 when `gh` fails. A mail is due when, since the
last send: a PR merged, a verdict was posted, the set of items under the attention label changed, the
last finished run of main changed or is red, an open PR changed (head, checks, mergeability), the
or, with `report-digest-hour`, no mail went out yet this
UTC day and that hour has passed. The first run has no baseline: it sends one mail without a change
list. The mail keeps what changed since the last send.

Keys read (no default; a key absent makes its part say so, except `report-repo`, which stops the
script): `report-repo` (repeatable), `report-attention-label`, `report-main-workflow`,
`report-digest-hour`. The state lives in `--state-dir`, else in
`~/.claude/hooks/state/report-mail/<repository>`.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import statistics
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "hooks"))
from usine import load, project_root  # noqa: E402

NOTHING_CHANGED = 10
STATE_FILE = "state.json"
PENDING_FILE = "pending.json"
MAIL_FILE = "mail.html"

Gh = Callable[[list[str]], str]


def _gh(args: list[str]) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout




def state_dir(config: Mapping[str, list[str]], override: str | None = None) -> Path:
    """Where the state of this project's report lives: `override`, else a folder named by its repos."""
    if override:
        return Path(override)
    name = "+".join(config.get("report-repo", [])).replace("/", "-") or "unconfigured"
    return Path.home() / ".claude" / "hooks" / "state" / "report-mail" / name


def _verdicts(body: str) -> list[str]:
    return [
        line.split()[1]
        for line in body.splitlines()
        if line.startswith("VERDICT:") and len(line.split()) > 1
    ]


def _when(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _minutes(start: str, end: str) -> float:
    return (_when(end) - _when(start)).total_seconds() / 60


def _checks(pr: Mapping[str, Any]) -> str:
    rollup = pr.get("statusCheckRollup") or []
    results = [c.get("conclusion") or c.get("status") for c in rollup if isinstance(c, dict)]
    if any(r in ("FAILURE", "CANCELLED", "TIMED_OUT") for r in results):
        return "red"
    if results and all(r in ("SUCCESS", "SKIPPED", "NEUTRAL") for r in results):
        return "green"
    return "pending"


def _json(gh: Gh, args: list[str]) -> Any:
    return json.loads(gh(args))










def _survey(gh: Gh, repo: str, config: Mapping[str, list[str]], since: str | None) -> dict:
    """What `gh` says about `repo` now, and what happened since `since` (None: no baseline)."""
    fields = "number,title,createdAt,mergedAt,comments"
    merged = _json(gh, ["pr", "list", "-R", repo, "--state", "merged", "--limit", "100", "--json", fields])
    label = (config.get("report-attention-label") or [""])[-1]
    attention: list[str] = []
    if label:
        for kind in ("issue", "pr"):
            listed = _json(gh, [kind, "list", "-R", repo, "--state", "open", "--label", label, "--json", "number"])
            attention += [f"#{item['number']}" for item in listed]
    run_args = ["run", "list", "-R", repo, "--branch", "main", "--status", "completed", "--limit", "1",
                "--json", "headSha,conclusion"]
    if config.get("report-main-workflow"):
        run_args += ["--workflow", config["report-main-workflow"][-1]]
    last_run = _json(gh, run_args)
    main = f"{last_run[0]['conclusion']} {last_run[0]['headSha'][:7]}" if last_run else "no run"
    open_prs = _json(gh, ["pr", "list", "-R", repo, "--state", "open", "--json",
                          "number,title,headRefOid,mergeStateStatus,statusCheckRollup,isDraft"])
    verdicts: list[tuple[str, str]] = []
    if since:
        comments = _json(gh, ["api", f"repos/{repo}/issues/comments?since={since}&per_page=100"])
        verdicts = [
            (c["issue_url"].rsplit("/", 1)[-1], v)
            for c in comments
            if c["created_at"] >= since
            for v in _verdicts(c["body"])
        ]
    return {
        "merged": [p for p in merged if since and p["mergedAt"] > since],
        "verdicts": verdicts,
        "attention": sorted(attention),
        "main": main,
        "open": {
            str(p["number"]): f"{p['headRefOid'][:7]} {_checks(p)} {p['mergeStateStatus']}"
            for p in open_prs
            if not p.get("isDraft")
        },
    }


def _changes(repo: str, now: Mapping, old: Mapping | None) -> list[str]:
    """The lines that say what changed since the fingerprint `old`; empty without a baseline."""
    if old is None:
        return []
    found: list[str] = []
    for pr in sorted(now["merged"], key=lambda p: p["mergedAt"]):
        rounds = [v for c in pr.get("comments", []) for v in _verdicts(c["body"])]
        turns = f"{rounds.count('REJECT') + 1} round(s)" if rounds else "no verdict"
        found.append(
            f"{repo}: merged #{pr['number']} {pr['title'][:70]}"
            f" ({turns}, {round(_minutes(pr['createdAt'], pr['mergedAt']))} min)."
        )
    if now["verdicts"]:
        tally: dict[str, list[str]] = {}
        for number, verdict in now["verdicts"]:
            tally.setdefault(verdict, []).append(f"#{number}")
        found.append(f"{repo}: verdicts " + "; ".join(
            f"{v} on {', '.join(sorted(set(ns)))}" for v, ns in tally.items()) + ".")
    if now["attention"] != old.get("attention", now["attention"]):
        found.append(f"{repo}: attention label on " + (", ".join(now["attention"]) or "nothing now") + ".")
    if now["main"] != old.get("main", now["main"]) or now["main"].startswith("failure"):
        found.append(f"{repo}: main CI is {now['main']}.")
    for number, state in now["open"].items():
        if old.get("open", {}).get(number) != state:
            found.append(f"{repo}: open PR #{number} is {state}.")
    for number in sorted(set(old.get("open", {})) - set(now["open"])):
        found.append(f"{repo}: PR #{number} closed or merged.")
    return found




def _fingerprint(survey: Mapping) -> dict:
    return {
        "main": survey["main"],
        "attention": survey["attention"],
        "open": survey["open"],
    }


def _waiting(repo: str, survey: Mapping) -> list[str]:
    found = [f"{repo}: {item} carries the attention label." for item in survey["attention"]]
    if survey["main"].startswith(("failure", "timed_out", "cancelled")):
        found.append(f"{repo}: main CI is {survey['main']}.")
    found += [
        f"{repo}: PR #{number} is green and unmerged."
        for number, state in survey["open"].items()
        if " green " in f" {state} "
    ]
    return found






def _figures(surveys: Mapping[str, dict]) -> str:
    rows = []
    for repo, survey in surveys.items():
        prs = survey["merged"]
        cycle = [_minutes(p["createdAt"], p["mergedAt"]) for p in prs]
        rounds = [
            [v for c in p.get("comments", []) for v in _verdicts(c["body"])].count("REJECT") + 1
            for p in prs
        ]
        median = f"{statistics.median(cycle):.0f}" if cycle else "-"
        rejected = f"{sum(r > 1 for r in rounds)}" if rounds else "-"
        rows.append(
            f"<tr><td>{html.escape(repo)}</td><td>{len(prs)}</td><td>{rejected}</td><td>{median}</td></tr>"
        )
    return (
        "<table><tr><td>Repository</td><td>Merged since the last mail</td>"
        "<td>With a REJECT</td><td>Median minutes, open to merge</td></tr>" + "".join(rows) + "</table>"
    )


def build(
    config: Mapping[str, list[str]],
    surveys: Mapping[str, dict],
    old: Mapping | None,
    stamp: str,
) -> tuple[str, bool]:
    """The mail's HTML, and whether any event makes it due."""
    e = html.escape
    changes: list[str] = []
    waiting: list[str] = []
    for repo, survey in surveys.items():
        changes += _changes(repo, survey, (old or {}).get(repo) if old is not None else None)
        waiting += _waiting(repo, survey)
    out = [f"<h2>Factory report, {e(', '.join(surveys))}, {stamp}</h2>"]
    since = old.get("since") if old else None
    out.append("<h3>What changed</h3>")
    if old is None:
        out.append("<p>First report: no earlier mail to compare with, so no change list.</p>")
    elif changes:
        out.append(f"<p>Since {e(str(since))}.</p><ul>" + "".join(f"<li>{e(c)}</li>" for c in changes) + "</ul>")
    else:
        out.append(f"<p>Since {e(str(since))}: nothing changed (digest).</p>")
    out.append("<h3>Awaiting you</h3>")
    out.append(
        "<ul>" + "".join(f"<li>{e(w)}</li>" for w in waiting) + "</ul>" if waiting else "<p>Nothing.</p>"
    )
    out.append("<h3>Figures</h3>" + _figures(surveys))
    return "\n".join(out) + "\n", bool(changes)


def main(
    argv: Sequence[str],
    gh: Gh = _gh,
    now: datetime | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="report_mail.py", add_help=True)
    parser.add_argument("--root")
    parser.add_argument("--state-dir")
    parser.add_argument("--sent", action="store_true")
    args = parser.parse_args(list(argv))
    root = Path(args.root) if args.root else project_root()
    config = load(root)
    folder = state_dir(config, args.state_dir)
    if args.sent:
        try:
            os.replace(folder / PENDING_FILE, folder / STATE_FILE)
        except OSError as error:
            sys.stderr.write(f"nothing to record as sent: {error}\n")
            return 1
        return 0
    repos = config.get("report-repo", [])
    if not repos:
        sys.stderr.write("the report needs the key `report-repo` in docs/agents/usine.md: none set\n")
        return 2
    moment = now or datetime.now(timezone.utc)
    try:
        saved = json.loads((folder / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    since = saved.get("last_sent")
    try:
        surveys = {repo: _survey(gh, repo, config, since) for repo in repos}
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as error:
        sys.stderr.write(f"gh failed: {error}\n")
        return 1
    old = None
    if since:
        old = {repo: saved.get("fingerprint", {}).get(repo, {}) for repo in repos}
        old["since"] = since
    stamp = moment.strftime("%Y-%m-%dT%H:%MZ")
    mail, due = build(config, surveys, old, stamp)
    digest_hour = (config.get("report-digest-hour") or [""])[-1]
    today = moment.strftime("%Y-%m-%d")
    if digest_hour.isdigit() and saved.get("digest_date") != today and moment.hour >= int(digest_hour):
        due = True
    due = due or old is None
    folder.mkdir(parents=True, exist_ok=True)
    pending = {
        "last_sent": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "digest_date": today,
        "fingerprint": {repo: _fingerprint(survey) for repo, survey in surveys.items()},
    }
    if not due:
        sys.stderr.write("nothing changed since the last mail\n")
        return NOTHING_CHANGED
    (folder / PENDING_FILE).write_text(json.dumps(pending), encoding="utf-8")
    (folder / MAIL_FILE).write_text(mail, encoding="utf-8")
    sys.stdout.write(mail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
