"""The factory report mail: built from the keys of `docs/agents/usine.md`, sent on events only.

    report_mail.py [--root <dir>] [--state-dir <dir>]     print the mail (HTML) on standard output
    report_mail.py [--root <dir>] [--state-dir <dir>] --sent   record the mail printed last as sent
    report_mail.py [--root <dir>] --line     print the "CI and runners" part in one line (no state)
    report_mail.py [--root <dir>] --slots    print the free slots in one line (no state)
    report_mail.py [--root <dir>] --features print the Features block in Markdown (no state)

Exit code: 0 when a mail is due (and for `--line`, `--slots` and `--features`, which print), 10 when
nothing happened since the last one sent (nothing is printed), 2 on a missing key or a usage error,
1 when `gh` fails (the survey of the mail, and of `--line`, `--slots` and `--features`). A mail is
due when, since the last send: a PR merged, a verdict was posted, the set of items under the attention label changed, the
last finished run of main changed or is red, an open PR changed (head, checks, mergeability), the
runners of a host changed (online count), or, with `report-digest-hour`, no mail went out yet this
UTC day and that hour has passed. The first run has no baseline: it sends one mail without a change
list. The mail keeps what changed since the last send, plus the present state of CI and runners.

Free slots: a host's slots are its free runners (online, not busy), across the repositories read.
A host with a `report-host-floor` gets none when its probe reads free memory or disk under the floor,
or when the probe fails or prints no `mem-free <GiB>` and `disk-free <GiB>`. The total is unknown
when the runners of a host still counted could not be read (a token without administrator rights).
`feature-build` reads `--slots` before each coder: 0, no coder starts.

Features: the mail lists each open feature of `feature-dir` (no `README.md`, `etat` not closed, as
`completion.py` selects them) in one line: its percent (`completion.percent`, closed over published,
tickets closed as not planned apart), the open PRs of the first `report-repo` whose body cites one of
its tickets (`Closes`, `Fixes`, `Resolves` or `Refs` `#n`), and its ready tickets (the boundary of
`feature-build`: open, `ready-for-agent`, nobody assigned, no open blocker). The tickets are the
sub-issues of the `issue:` of its `idee.md`, one `gh` call per feature, read in that first repository.
A feature `gh` cannot read says "tickets not read", never a guessed figure. With free slots N > 0,
"Awaiting you" proposes at most N ready tickets (features in folder order, tickets in sub-issue
order) and asks which to launch; with 0 or unknown slots the part says "no proposal" and why. The mail
launches nothing, and this part is never an event: it does not make a mail due.
`features_state` returns these as data, for any other rendering: besides the above, per feature its
blocked tickets (open, with an open blocker) and, with N free slots, up to N features that have a ready
ticket. `--features` renders that data as the field `Features` of the session's reply
(`templates/session-reply.md`, written by `features_block.py`, which the output guard also reads): a
line `Features:`, a table (`Feature | Closed / total | Open PRs | Blocked | Ready`, one row per open
feature, a feature `gh` cannot read saying "tickets not read"), then one line, `In parallel:`, that
names the ready tickets and the features that can start in the free slots, or says "no proposal" and
why. Without `report-repo`, or without `feature-dir`, or without an open feature, one line says so.

Keys read (no default; a key absent makes its part say so, except `report-repo`, which stops the
script): `report-repo` (repeatable), `report-attention-label`, `report-main-workflow`,
`report-host` (`<host> | <runner label>`), `report-host-probe` (`<host> | <command>`),
`report-digest-hour`, `report-host-floor` (`<host> | <memory GiB> | <disk GiB>`), and `feature-dir`
(read as `completion.py` reads it). The state lives in `--state-dir`, else in
`~/.claude/hooks/state/report-mail/<repository>`.
"""

from __future__ import annotations

import argparse
import functools
import html
import json
import os
import re
import statistics
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "hooks"))
sys.path.insert(0, str(PLUGIN / "scripts"))
import completion  # noqa: E402
import features_block  # noqa: E402
from guard_ticket_budget import feature_dir  # noqa: E402
from usine import load, project_root, split_value  # noqa: E402

NOTHING_CHANGED = 10
PROBE_TIMEOUT = 20
PROBE_MAX_CHARS = 200
STATE_FILE = "state.json"
PENDING_FILE = "pending.json"
MAIL_FILE = "mail.html"

Gh = Callable[[list[str]], str]
Probe = Callable[[str], str]


def _gh(args: list[str]) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def _probe(command: str) -> str:
    done = subprocess.run(
        command, shell=True, check=True, capture_output=True, text=True, timeout=PROBE_TIMEOUT
    )
    return done.stdout


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


def _pairs(config: Mapping[str, list[str]], key: str) -> dict[str, str]:
    """The `<a> | <b>` values of `key` as a mapping; a value short of a part is left out."""
    parts = (split_value(value, 2) for value in config.get(key, []))
    return {pair[0]: pair[1] for pair in parts if pair}


def _host_of(labels: Sequence[str], hosts: Mapping[str, str]) -> str | None:
    for host, label in hosts.items():
        if label in labels:
            return host
    return None


def _runners(gh: Gh, repo: str, hosts: Mapping[str, str]) -> dict[str, list[tuple[str, bool, bool]]] | None:
    """Each host's runners as `(name, online, busy)`; the runners no host claims go under `""`.

    None when `gh` cannot read them: the runner list needs an administrator token, which an agent
    token may lack, and the rest of the mail must still go out.
    """
    try:
        data = _json(gh, ["api", f"repos/{repo}/actions/runners?per_page=100"])
    except subprocess.CalledProcessError:
        return None
    found: dict[str, list[tuple[str, bool, bool]]] = {}
    items = data.get("runners", []) if isinstance(data, dict) else []
    for item in items:
        labels = [label["name"] for label in item.get("labels", [])]
        host = _host_of(labels, hosts) or ""
        found.setdefault(host, []).append(
            (item["name"], item.get("status") == "online", bool(item.get("busy")))
        )
    return found


def _count(gh: Gh, repo: str, status: str) -> int:
    runs = _json(gh, ["run", "list", "-R", repo, "--status", status, "--limit", "100", "--json", "databaseId"])
    return len(runs) if isinstance(runs, list) else 0


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
                          "number,title,headRefOid,mergeStateStatus,statusCheckRollup,isDraft,body"])
    verdicts: list[tuple[str, str]] = []
    if since:
        comments = _json(gh, ["api", f"repos/{repo}/issues/comments?since={since}&per_page=100"])
        verdicts = [
            (c["issue_url"].rsplit("/", 1)[-1], v)
            for c in comments
            if c["created_at"] >= since
            for v in _verdicts(c["body"])
        ]
    hosts = _pairs(config, "report-host")
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
        "prs": [{"number": p["number"], "body": p.get("body") or ""} for p in open_prs],
        "runners": _runners(gh, repo, hosts),
        "queued": _count(gh, repo, "queued"),
        "running": _count(gh, repo, "in_progress"),
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
    for host, count in _online(now).items():
        if host in old.get("runners", {}) and old["runners"][host] != count:
            found.append(f"{repo}: runners of {host or 'no host'} are now {count}.")
    return found


def _online(survey: Mapping) -> dict[str, str]:
    return {
        host: f"{sum(r[1] for r in rows)}/{len(rows)} online"
        for host, rows in (survey["runners"] or {}).items()
    }


def _fingerprint(survey: Mapping) -> dict:
    return {
        "main": survey["main"],
        "attention": survey["attention"],
        "open": survey["open"],
        "runners": _online(survey),
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
    for host, rows in (survey["runners"] or {}).items():
        down = [name for name, online, _ in rows if not online]
        if down:
            found.append(f"{repo}: runner(s) offline on {host or 'no host'}: {', '.join(down)}.")
    return found


def _probe_lines(config: Mapping[str, list[str]], hosts: Sequence[str], probe: Probe) -> list[str]:
    commands = _pairs(config, "report-host-probe")
    lines: list[str] = []
    for host in hosts:
        command = commands.get(host)
        if not command:
            lines.append(f"{host}: no probe named for host {host} (key `report-host-probe`).")
            continue
        try:
            text = " ".join(probe(command).split())[:PROBE_MAX_CHARS]
        except (OSError, subprocess.SubprocessError) as error:
            lines.append(f"{host}: probe for host {host} failed ({type(error).__name__}).")
            continue
        lines.append(f"{host}: {text or 'the probe printed nothing'}.")
    return lines


FREE = {"mem": re.compile(r"\bmem-free[ =:]*(\d+(?:\.\d+)?)"), "disk": re.compile(r"\bdisk-free[ =:]*(\d+(?:\.\d+)?)")}


def _under_floor(floor: Sequence[str], command: str | None, probe: Probe) -> str | None:
    """Why the host gets no slot under its floor `(mem, disk)`, or None when it is above it."""
    try:
        text = probe(command) if command else ""
    except (OSError, subprocess.SubprocessError):
        text = ""
    for (kind, pattern), minimum in zip(FREE.items(), floor):
        found = pattern.search(text)
        if not found:
            return "probe unreadable"
        if float(found.group(1)) < float(minimum):
            return f"under its floor ({kind}-free {found.group(1)} < {minimum})"
    return None


def free_slots(
    config: Mapping[str, list[str]], surveys: Mapping[str, dict], probe: Probe
) -> tuple[int | None, list[str]]:
    """The free slots, None when unknown, and one piece per host saying how the count came."""
    floors = {f[0]: f[1:] for f in (split_value(v, 3) for v in config.get("report-host-floor", [])) if f}
    commands = _pairs(config, "report-host-probe")
    hosts = list(_pairs(config, "report-host")) or [""]
    total: int | None = 0
    pieces: list[str] = []
    for host in hosts:
        why = _under_floor(floors[host], commands.get(host), probe) if host in floors else None
        name = host or "all runners"
        if why:
            pieces.append(f"{name} 0, {why}")
            continue
        if any(s["runners"] is None for s in surveys.values()):
            total = None
            pieces.append(f"{name} unknown, runners not read")
            continue
        free = sum(
            1
            for s in surveys.values()
            for h, rows in s["runners"].items()
            if h == host or not host
            for _, online, busy in rows
            if online and not busy
        )
        total = None if total is None else total + free
        pieces.append(f"{name} {free}")
    return total, pieces


def slots_line(config: Mapping[str, list[str]], surveys: Mapping[str, dict], probe: Probe) -> str:
    """The free slots in one line: `Free slots: <n|unknown> (<host> <n>[, why]; ...).`"""
    total, pieces = free_slots(config, surveys, probe)
    return f"Free slots: {'unknown' if total is None else total} ({'; '.join(pieces)})."


CITES = re.compile(r"\b(?:closes|fixes|resolves|refs)\s+#(\d+)", re.IGNORECASE)


def features_state(
    config: Mapping[str, list[str]], surveys: Mapping[str, dict], probe: Probe, root: Path, gh: Gh
) -> dict[str, Any]:
    """The open features of the project and what the human can launch, as data.

    `note` is the one line that says there is nothing to list; else `features` holds, per feature,
    `feature`, `label`, `percent` (`completion.percent`), `prs`, `blocked` (the open tickets with an
    open blocker), `ready` (numbers) and `error`, the reason its tickets were not read. `absent` names
    the key whose absence leaves nothing to list. `free` is the free slots (None unknown); `proposal`
    is up to `free` ready tickets as `(feature, number)`, `parallel` up to `free` features with a ready
    ticket, in folder order, and `why` says why there is none when it is empty for lack of slots.
    """
    state: dict[str, Any] = {
        "note": None, "absent": None, "features": [], "free": None, "proposal": [], "parallel": [],
        "why": None,
    }
    directory = feature_dir(config)
    repo = (config.get("report-repo") or [""])[0]
    if directory is None:
        state["note"] = "No feature list: key `feature-dir` absent."
        state["absent"] = "feature-dir"
        return state
    chosen = completion.open_features(root, config, directory)
    if not chosen:
        state["note"] = "No open feature."
        return state

    def run(argv: list[str], cwd: str | None) -> str | None:
        try:
            return gh([a.replace("{owner}/{repo}", repo) for a in argv])
        except (OSError, subprocess.SubprocessError):
            return None

    prs = (surveys.get(repo) or {}).get("prs", [])
    for feature, folder in chosen.items():
        header = completion.idea(folder)
        entry: dict[str, Any] = {
            "feature": feature, "label": completion.feature_label(feature, header),
            "percent": None, "prs": [], "blocked": [], "ready": [], "error": None,
        }
        state["features"].append(entry)
        tracking = header.get("issue", "")
        if not tracking.isdigit():
            entry["error"] = "no tracking issue, tickets not read"
            continue
        found = completion.sub_issues(tracking, root, run)
        if found is None:
            entry["error"] = "tickets not read"
            continue
        still_open, closed, _ = completion.tally(found)
        entry["percent"] = completion.percent(closed, len(still_open))
        entry["ready"] = [issue["number"] for issue in found if completion.is_ready(issue)]
        entry["blocked"] = [
            issue["number"] for issue in found
            if str(issue["state"]).upper() == "OPEN" and issue["blockedBy"] > 0
        ]
        entry["prs"] = [
            p["number"] for p in prs
            if {int(n) for n in CITES.findall(p["body"])} & {issue["number"] for issue in found}
        ]
    free, _ = free_slots(config, surveys, probe)
    state["free"] = free
    if not free:
        state["why"] = f"free slots {'unknown' if free is None else free}"
        return state
    ready = [(e["feature"], n) for e in state["features"] for n in e["ready"]]
    state["proposal"] = ready[:free]
    state["parallel"] = [e["feature"] for e in state["features"] if e["ready"]][:free]
    return state


def _features_part(state: Mapping[str, Any]) -> str:
    e = html.escape
    out = ["<h3>Features</h3>"]
    if state["note"]:
        out.append(f"<p>{e(state['note'])}</p>")
        return "".join(out)
    out.append("<ul>")
    for entry in state["features"]:
        text = entry["error"] or (
            f"{entry['percent']}; open PRs " + (", ".join(f"#{n}" for n in entry["prs"]) or "none")
            + "; ready " + (", ".join(f"#{n}" for n in entry["ready"]) or "none")
        )
        out.append(f"<li>{e(entry['label'])}: {e(text)}.</li>")
    out.append("</ul>")
    if state["why"]:
        out.append(f"<p>no proposal: {e(state['why'])}.</p>")
    return "".join(out)


def _ci_part(surveys: Mapping[str, dict], config: Mapping[str, list[str]], probe: Probe) -> str:
    e = html.escape
    out = ["<h3>CI and runners</h3>"]
    named = [v for v in config.get("report-host", []) if split_value(v, 2)]
    if not named:
        out.append("<p>Runners are listed per repository: key `report-host` absent, no grouping by host.</p>")
    rows: list[str] = []
    hosts: list[str] = []
    for repo, survey in surveys.items():
        if survey["runners"] is None:
            rows.append(f"<tr><td>{e(repo)}</td><td>-</td><td>runners not read</td></tr>")
            continue
        for host, runners in survey["runners"].items():
            name = host or "no host"
            if host and host not in hosts:
                hosts.append(host)
            on = sum(r[1] for r in runners)
            busy = sum(r[2] for r in runners)
            off = len(runners) - on
            listed = ", ".join(r[0] for r in runners) if not host else ""
            rows.append(
                f"<tr><td>{e(repo)}</td><td>{e(name)}</td><td>{on} online, {busy} busy, {off} offline"
                f"{' (' + e(listed) + ')' if listed else ''}</td></tr>"
            )
    out.append("<table><tr><td>Repository</td><td>Host</td><td>Runners</td></tr>" + "".join(rows) + "</table>")
    out.append("<ul>")
    for repo, survey in surveys.items():
        out.append(
            f"<li>{e(repo)}: queued runs {survey['queued']}, in progress {survey['running']},"
            f" last run of main {e(survey['main'])}.</li>"
        )
    hosts_listed = [h for h in (split_value(v, 2) for v in config.get("report-host", [])) if h]
    for line in _probe_lines(config, [h[0] for h in hosts_listed], probe):
        out.append(f"<li>{e(line)}</li>")
    out.append(f"<li>{e(slots_line(config, surveys, probe))}</li>")
    out.append("</ul>")
    return "".join(out)


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


def session_line(config: Mapping[str, list[str]], surveys: Mapping[str, dict], probe: Probe) -> str:
    """The "CI and runners" part of the mail in one line, for the session's reply to the human."""
    pieces: list[str] = []
    for repo, survey in surveys.items():
        hosts = "; ".join(
            f"{host or 'no host'} {sum(r[1] for r in rows)}/{len(rows)} online, {sum(r[2] for r in rows)} busy"
            for host, rows in (survey["runners"] or {}).items()
        )
        if survey["runners"] is None:
            hosts = "runners not read"
        pieces.append(
            f"{repo}: {hosts or 'no runner'}; queued {survey['queued']}, running {survey['running']},"
            f" main {survey['main']}"
        )
    named = [h[0] for h in (split_value(v, 2) for v in config.get("report-host", [])) if h]
    pieces += [line.rstrip(".") for line in _probe_lines(config, named, probe)]
    return "CI and runners: " + " | ".join(pieces) + "."


def build(
    config: Mapping[str, list[str]],
    surveys: Mapping[str, dict],
    old: Mapping | None,
    stamp: str,
    probe: Probe,
    features: Mapping[str, Any] | None = None,
) -> tuple[str, bool]:
    """The mail's HTML, and whether any event makes it due (the Features part is never an event)."""
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
    if features and features["proposal"]:
        waiting.append(
            "Free slots "
            + f"{features['free']}: ready to launch "
            + ", ".join(f"#{n} ({f})" for f, n in features["proposal"])
            + ". Which should I launch? This mail starts nothing."
        )
    out.append("<h3>Awaiting you</h3>")
    out.append(
        "<ul>" + "".join(f"<li>{e(w)}</li>" for w in waiting) + "</ul>" if waiting else "<p>Nothing.</p>"
    )
    if features is not None:
        out.append(_features_part(features))
    out.append(_ci_part(surveys, config, probe))
    out.append("<h3>Figures</h3>" + _figures(surveys))
    return "\n".join(out) + "\n", bool(changes)


def main(
    argv: Sequence[str],
    gh: Gh = _gh,
    probe: Probe = _probe,
    now: datetime | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="report_mail.py", add_help=True)
    parser.add_argument("--root")
    parser.add_argument("--state-dir")
    parser.add_argument("--sent", action="store_true")
    parser.add_argument("--line", action="store_true")
    parser.add_argument("--slots", action="store_true")
    parser.add_argument("--features", action="store_true")
    args = parser.parse_args(list(argv))
    probe = functools.cache(probe)  # the mail reads each probe for its line and for the floors
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
    if args.line and not repos:
        sys.stdout.write("CI and runners: not applicable (key `report-repo` absent).\n")
        return 0
    if args.slots and not repos:
        sys.stdout.write("Free slots: not applicable (key `report-repo` absent).\n")
        return 0
    if args.features and not repos:
        sys.stdout.write(features_block.not_applicable("report-repo"))
        return 0
    if not repos:
        sys.stderr.write("the report needs the key `report-repo` in docs/agents/usine.md: none set\n")
        return 2
    if args.line or args.slots or args.features:
        try:
            surveys = {repo: _survey(gh, repo, config, None) for repo in repos}
        except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as error:
            sys.stderr.write(f"gh failed: {error}\n")
            return 1
        if args.features:
            sys.stdout.write(features_block.render(features_state(config, surveys, probe, root, gh)))
            return 0
        line = slots_line(config, surveys, probe) if args.slots else session_line(config, surveys, probe)
        sys.stdout.write(line + "\n")
        return 0
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
    features = features_state(config, surveys, probe, root, gh)
    mail, due = build(config, surveys, old, stamp, probe, features)
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
