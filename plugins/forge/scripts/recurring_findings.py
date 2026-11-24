"""Count the distinct PRs that cite one finding id, and write the recurring ones in a ticket comment.

    python recurring_findings.py <project>

`forge:qc` runs it after it posts a verdict. The key `recurring-finding` is `<threshold> | <days>`
(`3 | 30`): an id `F-n` or `L-n` that the verdict comments of at least `<threshold>` distinct PRs cite,
all judged in the last `<days>` days, is listed. A verdict comment is one with a `VERDICT:` line; its
findings are the lines `- [BLOCKER|MINOR|NOTE] <place> | <rule> | ...`, and only the rule field is read,
by the closed pattern `F-<number>` or `L-<number>`. A PR counts once whatever the number of rounds that
cite the id. A finding whose rule is neither is counted on its own line, never as an id.

The result is one comment of the ticket the key `slo-issue` names, found again by the hidden marker
`<!-- forge-recurring-findings -->` (not the marker of the SLO report), rewritten on every run and
never duplicated. It holds only ids, PR numbers and dates, never the text of a finding. No ticket is
opened. When no id is listed and no comment exists yet, nothing is written.

A key `recurring-finding` or `slo-issue` absent is "sans objet (clé `<nom>` absente)" and nothing is
written, no `gh` call made. A ticket `gh` cannot read, or a key that is badly formed, writes nothing and
exits 1. The PRs and the comments are read with `gh pr list --json` and `gh api --paginate`, as
`factory_slo.py` reads them; the comment is written by `gh api` (a POST on `issues/<n>/comments`), the
same call `factory_slo.py report --publier` makes. The standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import factory_slo  # noqa: E402  the marker style, the reader of `gh`, the key `slo-issue`
import usine  # noqa: E402
from factory_slo import Runner  # noqa: E402

KEY = "recurring-finding"
ISSUE_KEY = "slo-issue"
MARKER = "<!-- forge-recurring-findings -->"
FINDING = re.compile(r"^[ \t]*-[ \t]*\[(?:BLOCKER|MINOR|NOTE)\][ \t]*(.+)$", re.MULTILINE)
RULE = re.compile(r"^([FL])-([1-9]\d*)$")


@dataclass
class Tally:
    """What the verdict comments of a window cite: the PRs per id, and the findings that cite none."""

    prs_of: dict[str, set[int]] = field(default_factory=dict)
    loose: int = 0
    loose_prs: set[int] = field(default_factory=set)


def rule_of(finding: str) -> str | None:
    """The id `F-n` or `L-n` in the rule field (the second) of a finding, None when it holds neither."""
    fields = finding.split("|")
    if len(fields) < 2:
        return None
    found = RULE.match(fields[1].strip())
    return f"{found.group(1)}-{found.group(2)}" if found else None


def tally(prs: list[dict], since: datetime, until: datetime) -> Tally:
    """Count, per id, the distinct PRs whose verdict comments of the window cite it."""
    result = Tally()
    for item in prs:
        number = int(item["number"])
        for comment in item.get("comments") or []:
            body = str(comment.get("body") or "")
            moment = factory_slo.when(comment, "createdAt")
            if not factory_slo.VERDICT.search(body) or moment is None or not since <= moment < until:
                continue
            for finding in FINDING.findall(body):
                identifier = rule_of(finding)
                if identifier is None:
                    result.loose += 1
                    result.loose_prs.add(number)
                else:
                    result.prs_of.setdefault(identifier, set()).add(number)
    return result


def recurring(counted: Tally, threshold: int) -> list[tuple[str, list[int]]]:
    """The ids that at least `threshold` distinct PRs cite, `F-n` then `L-n`, each in numeric order."""
    listed = [(name, sorted(numbers)) for name, numbers in counted.prs_of.items() if len(numbers) >= threshold]
    return sorted(listed, key=lambda row: (row[0][0], int(row[0][2:])))


def parse_setting(values: list[str]) -> tuple[int, int]:
    """`(threshold, days)` of the key `recurring-finding` (`3 | 30`); RuntimeError when it is not two positive numbers."""
    parts = [part.strip() for part in values[0].split("|")]
    if len(parts) != 2 or not all(part.isdigit() and int(part) > 0 for part in parts):
        raise RuntimeError(f"`{KEY}` : `{values[0]}` : attendu `<seuil> | <jours>`, deux nombres entiers positifs (`3 | 30`)")
    return int(parts[0]), int(parts[1])


def comment_body(counted: Tally, threshold: int, since: datetime, until: datetime) -> str:
    days = (until - since).days
    lines = [
        MARKER,
        f"Constats récurrents du {since.date().isoformat()} au {until.date().isoformat()} ({days} jours) :"
        f" un identifiant cité par au moins {threshold} PR distinctes.",
        "",
    ]
    listed = recurring(counted, threshold)
    if listed:
        lines += ["| Identifiant | PR distinctes | PR |", "|---|---|---|"]
        lines += [f"| {name} | {len(numbers)} | {', '.join(f'#{n}' for n in numbers)} |" for name, numbers in listed]
    else:
        lines.append(f"Aucun identifiant n'est cité par {threshold} PR distinctes.")
    plural = "s" if len(counted.loose_prs) > 1 else ""
    lines += ["", f"Constats sans identifiant : {counted.loose}, sur {len(counted.loose_prs)} PR{plural} (ni `F-n` ni `L-n`, comptés à part)."]
    return "\n".join(lines)


def run_recurring(project: Path, run: Runner, now: datetime) -> list[str]:
    """Count, then write the comment of the ticket of the key `slo-issue`; what was done, or why nothing was."""
    config = usine.load(project)
    threshold, days = parse_setting(config[KEY])
    ticket = factory_slo.issue_number(project)
    since = now - timedelta(days=days)
    counted = tally(factory_slo.Factory(project, since, now, run).prs, since, now)
    path = f"repos/{{owner}}/{{repo}}/issues/{ticket}/comments"
    if not recurring(counted, threshold):
        return [f"Constat récurrent : aucun identifiant cité par {threshold} PR distinctes en {days} jours, rien n'est écrit."]
    body = comment_body(counted, threshold, since, now)
    run(["gh", "api", path, "-f", f"body={body}"], project)
    return [f"constats récurrents postés dans un commentaire du ticket #{ticket}"]


def main(argv: list[str] | None = None, run: Runner = factory_slo.run_command, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(prog="recurring_findings.py", description=__doc__.splitlines()[0])
    parser.add_argument("projet", type=Path, help="le dossier du projet")
    args = parser.parse_args(argv)
    try:
        for line in run_recurring(args.projet, run, now or datetime.now(tz=timezone.utc)):
            print(line)
    except (RuntimeError, ValueError, KeyError, IndexError, OSError, json.JSONDecodeError) as error:
        print(f"Calcul impossible : {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
