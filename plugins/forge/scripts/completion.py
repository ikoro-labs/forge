"""Print the completion table of the open features, or of the features named.

    python completion.py [F-NNNN ...] [--root <project>]

One Markdown row per feature, the columns of `guard_completion.HEADERS`, and no total row: the
features' denominators do not add up. The tickets of a feature are the sub-issues of its
tracking issue (the `issue:` of its `idee.md`), read by `gh api .../sub_issues --paginate`. Without
`issue:`, they are those the ticket budget's search places in it (`to-tickets F-NNNN` and
`Feature: F-NNNN`, each body placed by its `Motif :` line). The `Relevé` cell names the source. A
ticket closed as not planned stands apart, out of the count; the others are open, or closed. `%` is closed over closed plus open, rounded, its denominator in the
cell, and `sans objet (aucun ticket publié)` without any; never over the budget, which a feature
may not fill. The budget is the `feature-tickets` of the feature's `design.md`, `?`
without one. `Suivi` is the `issue:` of its `idee.md`. Each row carries the UTC time it was read and
its source.

A feature is open while its folder has no `README.md` (the delivered feature) and the `etat` of its
`idee.md` is not the value of the role `hors-perimetre` or `abandonnee` (key `feature-state`, else
those words). The key `completion-column` (`<header> | <command>`) adds the project's own column:
its command runs from the project root, `{feature}` replaced by the feature, and its output fills
the cell. A feature gh cannot read stops the script (exit 2): a row is never guessed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

from guard_completion import HEADERS, extra_column  # noqa: E402
from guard_ticket_budget import (  # noqa: E402
    Runner,
    budget_of,
    counts_for,
    feature_dir,
    find_design,
    front_matter,
    released,
    run_gh,
    search_issues,
)
from usine import load, split_value  # noqa: E402

COLUMN_TIMEOUT = 60
CLOSED_ROLES = ("hors-perimetre", "abandonnee")
FOLDER = re.compile(r"^(\d{4})-")
SUB_ISSUES_SOURCE = "gh api sub_issues of"
SEARCH_SOURCE = "gh issue list --search (no issue: in idee.md)"
NO_TICKET = "sans objet (aucun ticket publié)"
Clock = Callable[[], datetime]


class CompletionError(ValueError):
    """A configuration or a count the table cannot trust."""


def _header(path: Path) -> dict[str, str]:
    try:
        return front_matter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return {}


def closed_states(config: Mapping[str, list[str]]) -> set[str]:
    """The `etat` values of a feature out of the table: its project's values and the bare words."""
    states = set(CLOSED_ROLES)
    for value in config.get("feature-state", []):
        parts = split_value(value, 2)
        if parts is not None and parts[0] in CLOSED_ROLES:
            states.add(parts[1])
    return states


def folders(root: Path, directory: str) -> dict[str, Path]:
    """The feature folders under `directory`, by `F-NNNN`."""
    found: dict[str, Path] = {}
    base = root / directory
    if base.is_dir():
        for path in sorted(base.iterdir()):
            if path.is_dir() and (match := FOLDER.match(path.name)):
                found.setdefault(f"F-{match.group(1)}", path)
    return found


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def column_cell(command: str, feature: str, root: Path) -> str:
    """The project's own cell: the command's output on one line, or why it has none."""
    try:
        # The command is the project's own, declared in its usine.md, as the `ci-replay` keys are.
        done = subprocess.run(  # noqa: S602
            command.replace("{feature}", feature),
            shell=True,
            cwd=root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=COLUMN_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"erreur (plus de {COLUMN_TIMEOUT} s)"
    except OSError as error:
        return _cell(f"erreur ({error})")
    if done.returncode != 0:
        return f"erreur (code {done.returncode})"
    return _cell(done.stdout) or "vide"


def percent(closed: int, still_open: int) -> str:
    """Closed over published (closed plus open), not planned left out; its denominator written."""
    published = closed + still_open
    if published == 0:
        return NO_TICKET
    rounded = (200 * closed + published) // (2 * published)  # half up: 12.5 is 13, not 12
    return f"{rounded} % ({closed} / {published})"


def sub_issues(tracking: str, root: Path, run: Runner) -> list[dict] | None:
    """The sub-issues of the tracking issue, each with its number, state and reason; None if unread."""
    query = '.[] | [.number, .state, (.state_reason // "")] | @tsv'
    argv = ["api", f"repos/{{owner}}/{{repo}}/issues/{tracking}/sub_issues", "--paginate"]
    output = run([*argv, "--jq", query], str(root))
    if output is None:
        return None
    found: list[dict] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3 or not parts[0].isdigit():
            return None
        number, state, reason = parts
        found.append({"number": int(number), "state": state, "stateReason": reason or None})
    return found


def searched(feature: str, root: Path, run: Runner) -> list[dict] | None:
    """Without a tracking issue: the tickets the ticket budget's search places in `feature`."""
    issues = search_issues((f"to-tickets {feature}", f"Feature: {feature}"), None, str(root), run)
    if issues is None:
        return None
    return [issue for issue in issues.values() if counts_for(issue["body"]) == feature]


def row(
    feature: str, folder: Path, root: Path, directory: str, run: Runner, now: Clock
) -> list[str]:
    idea = _header(folder / "idee.md")
    designs = find_design(root, directory, feature)
    budget = budget_of(_header(designs[0])) if len(designs) == 1 else None
    tracking = idea.get("issue", "")
    if tracking.isdigit():
        found = sub_issues(tracking, root, run)
        source = f"{SUB_ISSUES_SOURCE} #{tracking}"
    else:
        found = searched(feature, root, run)
        source = SEARCH_SOURCE
    if found is None:
        raise CompletionError(f"gh cannot list the tickets of {feature}: no row is guessed")
    read_at = now()
    out = sorted(issue["number"] for issue in found if released(issue))
    counted = [issue for issue in found if not released(issue)]
    still_open = sorted(
        issue["number"] for issue in counted if str(issue.get("state", "")).upper() == "OPEN"
    )
    closed = len(counted) - len(still_open)
    title = idea.get("titre", "")
    return [
        _cell(f"{feature} {title}" if title and not title.startswith("<") else feature),
        f"#{tracking}" if tracking.isdigit() else "?",
        f"{closed} / {budget if budget is not None else '?'}",
        percent(closed, len(still_open)),
        str(len(still_open)),
        str(len(out)),
        ", ".join(f"#{number}" for number in still_open) or "aucun",
        f"{read_at.astimezone(timezone.utc):%Y-%m-%d %H:%M} UTC, {source}",
    ]


def table(root: Path, wanted: list[str], run: Runner = run_gh, now: Clock | None = None) -> str:
    """The Markdown table of the features `wanted`, or of every open one when it is empty."""
    clock = now or (lambda: datetime.now(timezone.utc))
    config = load(root)
    directory = feature_dir(config)
    if directory is None:
        raise CompletionError("the key `feature-dir` is absent: there is no feature folder")
    try:
        column = extra_column(config)
    except ValueError as error:
        raise CompletionError(str(error)) from None
    found = folders(root, directory)
    if wanted:
        missing = [feature for feature in wanted if feature not in found]
        if missing:
            raise CompletionError(f"no folder under `{directory}` for {', '.join(missing)}")
        chosen = {feature: found[feature] for feature in wanted}
    else:
        closed = closed_states(config)
        chosen = {
            feature: folder
            for feature, folder in found.items()
            if not (folder / "README.md").exists()
            and _header(folder / "idee.md").get("etat") not in closed
        }
    headers = HEADERS if column is None else (*HEADERS, column[0])
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for feature, folder in chosen.items():
        cells = row(feature, folder, root, directory, run, clock)
        if column is not None:
            cells.append(column_cell(column[1], feature, root))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="completion.py", description=__doc__.splitlines()[0])
    parser.add_argument("features", nargs="*", metavar="F-NNNN")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    bad = [name for name in args.features if not re.fullmatch(r"F-\d{4}", name)]
    if bad:
        print(f"completion.py: not a feature: {', '.join(bad)}", file=sys.stderr)
        return 2
    try:
        sys.stdout.write(table(args.root, args.features))
    except CompletionError as error:
        print(f"completion.py: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
