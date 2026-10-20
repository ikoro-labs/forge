"""Count the tokens each role spent on a project, from the logs Claude Code already writes.

    python token_audit.py <project> [--depuis DATE] [--jusqua DATE] [--coupure DATE]

Reads `<config>/projects/*/**/*.jsonl`, `<config>` being CLAUDE_CONFIG_DIR or `~/.claude`. Each
reply of the model is a `type: assistant` line; one reply written on several lines counts once.
A line counts when its `cwd` is the project or a folder under it, worktrees included. Prints a
Markdown table by role, model and effort; with `--coupure`, one table before the date, one after,
and the tokens per agent launch of each role on both sides, since the amount of work differs from
one period to the next. No price: providers do not all publish one. The standard library only.

A line whose `stop_reason` is still empty was written while the reply streamed: its output count
is the one known at the start, far below the real one. Claude Code logs most subagent replies so.
Such a reply is counted as partial, and the report says how many there are.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MAIN_SESSION = "session principale"
SYNTHETIC = "<synthetic>"
USAGE = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


@dataclass(frozen=True)
class Call:
    """One reply of the model, as the log records it."""

    role: str
    model: str
    effort: str
    launch: str
    timestamp: datetime
    message: str
    tokens: tuple[int, int, int, int]
    final: bool = True


@dataclass(frozen=True)
class Row:
    role: str
    model: str
    effort: str
    launches: int
    replies: int
    tokens: tuple[int, int, int, int]
    partial: int = 0

    @property
    def per_launch(self) -> int:
        return round(sum(self.tokens) / self.launches)


@dataclass(frozen=True)
class Comparison:
    role: str
    before_launches: int
    before_per_launch: int | None
    after_launches: int
    after_per_launch: int | None


def config_dir() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured) if configured else Path.home() / ".claude"


def parse_time(text: str) -> datetime:
    """An ISO date or date-time; one without a zone is UTC, as the logs are."""
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _inside(cwd: str, project: str) -> bool:
    folder = os.path.normcase(os.path.normpath(cwd))
    return folder == project or folder.startswith(project.rstrip(os.sep) + os.sep)


def _tokens(counts: list[int]) -> tuple[int, int, int, int]:
    """Input, cache write, cache read, output."""
    return counts[0], counts[1], counts[2], counts[3]


def _call(entry: dict, path: Path) -> Call:
    """The reply on one line; KeyError, TypeError or ValueError when the line lacks a field."""
    message = entry["message"]
    usage = message["usage"]
    agent = entry.get("attributionAgent")
    session = str(entry["sessionId"])
    return Call(
        role=agent or MAIN_SESSION,
        model=str(message.get("model") or "-"),
        effort=str(entry.get("effort") or "-"),
        launch=str(entry.get("agentId") or f"{session}/{path.stem}") if agent else session,
        timestamp=parse_time(entry["timestamp"]),
        message=str(message["id"]),
        tokens=_tokens([int(usage.get(key) or 0) for key in USAGE]),
        final=message.get("stop_reason") is not None,
    )


def read_calls(
    config: Path, project: Path, since: datetime | None = None, until: datetime | None = None
) -> tuple[list[Call], int]:
    """The project's replies in [since, until), oldest first, and the count of unreadable lines."""
    root = os.path.normcase(os.path.normpath(os.path.abspath(project)))
    replies: dict[tuple[str, str], Call] = {}
    bad = 0
    for path in sorted((config / "projects").rglob("*.jsonl")):
        # A file last written before the period holds no line of it.
        if since is not None and path.stat().st_mtime < since.timestamp():
            continue
        with path.open(encoding="utf-8", errors="replace") as lines:
            for text in lines:
                if not text.strip():
                    continue
                try:
                    entry = json.loads(text)
                except ValueError:
                    bad += 1
                    continue
                if not isinstance(entry, dict) or entry.get("type") != "assistant":
                    continue
                if not isinstance(entry.get("cwd"), str) or not _inside(entry["cwd"], root):
                    continue
                try:
                    call = _call(entry, path)
                except (KeyError, TypeError, ValueError, AttributeError):
                    bad += 1
                    continue
                if call.model == SYNTHETIC:
                    continue
                if since is not None and call.timestamp < since:
                    continue
                if until is not None and call.timestamp >= until:
                    continue
                key = (call.message, str(entry.get("requestId")))
                # The line written at the end of the reply carries its whole output; keep it.
                if key not in replies or call.final or not replies[key].final:
                    replies[key] = call
    return sorted(replies.values(), key=lambda call: call.timestamp), bad


def summarize(calls: list[Call]) -> list[Row]:
    groups: dict[tuple[str, str, str], list[Call]] = {}
    for call in calls:
        groups.setdefault((call.role, call.model, call.effort), []).append(call)
    return [
        Row(
            role=role,
            model=model,
            effort=effort,
            launches=len({call.launch for call in group}),
            replies=len(group),
            tokens=_tokens([sum(column) for column in zip(*(call.tokens for call in group))]),
            partial=sum(not call.final for call in group),
        )
        for (role, model, effort), group in sorted(groups.items())
    ]


def _per_launch(calls: list[Call]) -> tuple[int, int | None]:
    launches = len({call.launch for call in calls})
    if not launches:
        return 0, None
    return launches, round(sum(sum(call.tokens) for call in calls) / launches)


def compare(calls: list[Call], cut: datetime) -> list[Comparison]:
    rows = []
    for role in sorted({call.role for call in calls}):
        mine = [call for call in calls if call.role == role]
        before = _per_launch([call for call in mine if call.timestamp < cut])
        after = _per_launch([call for call in mine if call.timestamp >= cut])
        rows.append(Comparison(role, before[0], before[1], after[0], after[1]))
    return rows


def _report(calls: list[Call]) -> list[str]:
    if not calls:
        return ["Aucune réponse du modèle sur cette période."]
    lines = [
        "| Rôle | Modèle | Effort | Lancements | Réponses | Entrée | Écriture cache | Lecture cache"
        " | Sortie | Sortie partielle | Total / lancement |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    rows = summarize(calls)
    for row in rows:
        cells = [
            row.role, row.model, row.effort, row.launches, row.replies, *row.tokens, row.partial, row.per_launch,
        ]
        lines.append("| " + " | ".join(str(cell) for cell in cells) + " |")
    partial = sum(row.partial for row in rows)
    if partial:
        lines += [
            "",
            f"Sortie partielle : {partial} réponse{'s' if partial > 1 else ''} notée{'s' if partial > 1 else ''}"
            " par Claude Code avant leur fin. Leur sortie est celle connue au début de la réponse : la"
            " colonne Sortie, et le total, sont sous-comptés d'autant.",
        ]
    return lines


def _comparison(calls: list[Call], cut: datetime) -> list[str]:
    lines = [
        "| Rôle | Lancements avant | Total / lancement avant | Lancements après"
        " | Total / lancement après | Écart |",
        "|---|---|---|---|---|---|",
    ]
    for row in compare(calls, cut):
        before, after = row.before_per_launch, row.after_per_launch
        change = f"{round(100 * (after - before) / before):+d} %" if before and after is not None else "-"
        cells = [
            row.role, row.before_launches, "-" if before is None else before,
            row.after_launches, "-" if after is None else after, change,
        ]
        lines.append("| " + " | ".join(str(cell) for cell in cells) + " |")
    return lines


def _date(text: str) -> datetime:
    try:
        return parse_time(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"`{text}` n'est pas une date ISO (2026-10-20 ou 2026-10-20T21:52, en UTC sans zone)"
        ) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="token_audit.py", description=__doc__.splitlines()[0])
    parser.add_argument("projet", type=Path, help="le dossier du projet, ses worktrees compris")
    parser.add_argument("--depuis", type=_date, help="début de la période, inclus")
    parser.add_argument("--jusqua", type=_date, help="fin de la période, exclue")
    parser.add_argument("--coupure", type=_date, help="sépare un avant d'un après")
    args = parser.parse_args(argv)

    config = config_dir()
    if not (config / "projects").is_dir():
        print(f"Pas de journaux : `{config / 'projects'}` n'existe pas.", file=sys.stderr)
        return 1
    calls, bad = read_calls(config, args.projet, since=args.depuis, until=args.jusqua)
    start = args.depuis.isoformat() if args.depuis else "le premier journal"
    end = args.jusqua.isoformat() if args.jusqua else "aujourd'hui"
    out = [f"Jetons de `{args.projet}`, de {start} à {end}, lus dans `{config / 'projects'}`.", ""]
    if args.coupure is None:
        out += _report(calls)
    else:
        cut = args.coupure.isoformat()
        out += [f"## Avant {cut}", ""] + _report([call for call in calls if call.timestamp < args.coupure])
        out += ["", f"## À partir de {cut}", ""]
        out += _report([call for call in calls if call.timestamp >= args.coupure])
        out += ["", "## Par lancement", ""] + _comparison(calls, args.coupure)
    out += ["", f"{bad} ligne{'s' if bad > 1 else ''} illisible{'s' if bad > 1 else ''}, ignorée{'s' if bad > 1 else ''}."]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
