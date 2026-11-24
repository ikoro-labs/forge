"""Compare the plugin a workstation installed with the `ref` a project pins (ikoro-labs/forge#333).

    python pin_sync.py check (--all | <project>...)
    python pin_sync.py apply <project> [--passation <handoff>]

A pin raise edits `.claude/settings.json` only: the install stays old until `claude plugin marketplace
add` and `claude plugin update` run on the workstation. `check` reads both and writes nothing. The pin
is the `ref` of `forge@<marketplace>` in `.claude/settings.json` as `origin/main` has it (what
`git fetch` last brought: `check` opens no network access), the installed version is the entry of
`claude plugin list --json` whose `projectPath` is the project. `--all` takes the projects of that
list (the plugin, scope `project`).

One line per project, `<status>`, `<project>` and `<detail>` separated by tabs. The status is OK (the
installed version is the pinned one), BEHIND (it differs: not installed, or another version, the detail
says which way) or NOT RUN (a pin, the list or a version could not be read, or the user's own settings
pin the marketplace at another `ref` than the project, so that `claude plugin marketplace add` is refused;
the detail says what, and no settings file of the user is ever edited). Exit code 0 when every line is OK,
1 when a line is BEHIND and none is NOT RUN, 2 when a line is NOT RUN or the call is wrong.

`apply` is the gesture of the session between two tickets, never between a coder and the verdict of the
review. It refuses (a REFUSED line, exit 3, nothing run, not even `git fetch`) while an agent of the
repository is alive (`handoff_header.live_agents`, the worktrees locked by a running session) or, with
`--passation`, while `en_vol` or `file_revue` of the handoff header is not empty: the facts the relay
refuses on. Else it runs `git fetch origin main` (the only network access of the script besides the
installs), then, for a project that is BEHIND, from its root, `claude plugin marketplace add <repo>@<ref>
--scope project` and `claude plugin update <plugin> --scope project` (`install` when the workstation lists
no install for the project), each said on stderr first, and ends on `check`, whose line and exit code are
its own: an install that left the version old ends on BEHIND, never on OK. A project already OK runs
nothing. When `marketplace add` is refused because the user's settings pin the marketplace at another
`ref`, the line is NOT RUN with that reason (said before any command when the user settings show it, and
after the command's own refusal when they do not, as with managed settings); no settings file is edited.
It never runs without being called: the hook `pin_notice.py` only says the command. Exit code 3 for a
REFUSED line, else those of `check`. The standard library only.
"""

from __future__ import annotations

import argparse
import functools
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import handoff_header  # noqa: E402  the live agents and the header of a handoff, as the relay reads them
import pin_state  # noqa: E402  hooks/ is not importable until the path insertion above
from pin_state import Result, Run  # noqa: E402
from utf8_stdio import use_utf8  # noqa: E402  the project's lines carry accents, and Windows defaults to its code page

EXIT = {"OK": 0, "BEHIND": 1, "NOT RUN": 2, "REFUSED": 3}
# `marketplace add` clones the repository and `update` copies the plugin: far longer than a read.
APPLY_SECONDS = 300
# What `claude plugin marketplace add` says when the user's or managed settings pin the marketplace elsewhere.
USER_PIN_REFUSAL = "doesn't match its extraKnownMarketplaces entry"


def worst(results: list[Result]) -> int:
    return max((EXIT[result.status] for result in results), default=2)


def cmd_check(args: argparse.Namespace, run: Run) -> int:
    if args.all == bool(args.projects):
        print("pin_sync.py check : donner `--all` ou au moins un projet, pas les deux", file=sys.stderr)
        return 2
    results: list[Result] = []
    if args.all:
        try:
            entries = pin_state.installed_entries(run, Path.cwd())
        except pin_state.NotRun as why:
            results.append(Result("NOT RUN", "-", str(why)))
        else:
            found = pin_state.projects(entries)
            results.extend(pin_state.compare(project, entries, run) for project in found)
            if not found:
                results.append(Result("NOT RUN", "-", f"`claude plugin list --json` ne liste aucun projet où `{pin_state.PLUGIN}` est installé"))
    else:
        results.extend(pin_state.check(Path(project), run) for project in args.projects)
    for result in results:
        print(result.line)
    return worst(results)


def in_flight(project: Path, passation: Path | None) -> list[str]:
    """What stops an install: a live agent worktree, a handoff that lists agents or reviews, anything unreadable."""
    reasons: list[str] = []
    try:
        reasons += [f"l'agent de {path} ({branch}) tourne encore" for path, branch in handoff_header.live_agents(project)]
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        reasons.append(f"les worktrees d'agent de {project} ne se lisent pas ({error}), donc pas d'installation")
    if passation is not None:
        try:
            values = handoff_header.check(passation)
        except (OSError, ValueError) as error:
            reasons.append(f"la passation {passation} ne se lit pas ({error}), donc pas d'installation")
        else:
            reasons += [
                f"`{key}` de la passation {passation} n'est pas vide : {', '.join(values[key])}"
                for key in ("en_vol", "file_revue")
                if values[key]
            ]
    return reasons


def say(result: Result) -> int:
    print(result.line)
    return EXIT[result.status]


def cmd_apply(args: argparse.Namespace, run: Run) -> int:
    project = Path(args.project)
    reasons = in_flight(project, args.passation)
    if reasons:
        return say(Result("REFUSED", str(project), " ; ".join(reasons)))
    fetched = run(["git", "-C", str(project), "fetch", "origin", "main"], project)
    if fetched is None or fetched.code != 0:
        why = pin_state.last_line(fetched.err) if fetched else "pas de réponse"
        return say(Result("NOT RUN", str(project), f"`git fetch origin main` a échoué ({why}) : l'épingle de origin/main n'est pas à jour"))
    current = pin_state.check(project, run)
    if current.status != "BEHIND":
        return say(current)
    try:
        pin = pin_state.read_pin(project, run)
        entries = pin_state.installed_entries(run, project)
    except pin_state.NotRun as problem:
        return say(Result("NOT RUN", str(project), str(problem)))
    verb = "update" if pin_state.installed_version(entries, pin, project) else "install"
    commands = [
        ["claude", "plugin", "marketplace", "add", f"{pin.repo}@{pin.ref}", "--scope", "project"],
        ["claude", "plugin", verb, pin.plugin_id, "--scope", "project"],
    ]
    for command in commands:
        print(f"pin_sync.py : {' '.join(command)}", file=sys.stderr)
        done = run(command, project)
        if done is not None and done.code == 0:
            continue
        if done is None:
            why = "pas de réponse (commande absente, impossible à lancer ou trop longue)"
        elif USER_PIN_REFUSAL in done.err:
            why = f"{pin_state.REFUSED_ADD} ; `{command[2]} {command[3]}` refusé : {pin_state.last_line(done.err)}"
        else:
            why = f"`{' '.join(command)}` a échoué : {pin_state.last_line(done.err)}"
        return say(Result("NOT RUN", str(project), why))
    return say(pin_state.check(project, run))


def main(argv: list[str] | None = None, run: Run | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pin_sync.py", description=__doc__.splitlines()[0] if __doc__ else None)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="compare the pinned ref with the installed version, per project")
    check.add_argument("projects", nargs="*", metavar="project")
    check.add_argument("--all", action="store_true", help="every project `claude plugin list --json` lists")
    check.set_defaults(handler=cmd_check, seconds=pin_state.SECONDS)
    apply = sub.add_parser("apply", help="install the pinned version for a project, when nothing is in flight")
    apply.add_argument("project")
    apply.add_argument("--passation", type=Path, help="the handoff whose `en_vol` and `file_revue` must be empty")
    apply.set_defaults(handler=cmd_apply, seconds=APPLY_SECONDS)
    args = parser.parse_args(argv)
    runner = run if run is not None else functools.partial(pin_state.run_command, seconds=args.seconds)
    return int(args.handler(args, runner))


if __name__ == "__main__":
    use_utf8()
    sys.exit(main())
