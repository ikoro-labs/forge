"""Compare the plugin a workstation installed with the `ref` a project pins (ikoro-labs/forge#333).

    python pin_sync.py check (--all | <project>...)

A pin raise edits `.claude/settings.json` only: the install stays old until `claude plugin marketplace
add` and `claude plugin update` run on the workstation. `check` reads both and writes nothing. The pin
is the `ref` of `forge@<marketplace>` in `.claude/settings.json` as `origin/main` has it (what
`git fetch` last brought: the script opens no network access), the installed version is the entry of
`claude plugin list --json` whose `projectPath` is the project. `--all` takes the projects of that
list (the plugin, scope `project`).

One line per project, `<status>`, `<project>` and `<detail>` separated by tabs. The status is OK (the
installed version is the pinned one), BEHIND (it differs: not installed, or another version, the detail
says which way) or NOT RUN (a pin, the list or a version could not be read, or the user's own settings
pin the marketplace at another `ref` than the project, so that `claude plugin marketplace add` is refused;
the detail says what, and no settings file of the user is ever edited). Exit code 0 when every line is OK,
1 when a line is BEHIND and none is NOT RUN, 2 when a line is NOT RUN or the call is wrong. The standard
library only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import pin_state  # noqa: E402  hooks/ is not importable until the path insertion above
from pin_state import Result, Run  # noqa: E402
from utf8_stdio import use_utf8  # noqa: E402  the project's lines carry accents, and Windows defaults to its code page

EXIT = {"OK": 0, "BEHIND": 1, "NOT RUN": 2}


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


def main(argv: list[str] | None = None, run: Run = pin_state.run_command) -> int:
    parser = argparse.ArgumentParser(prog="pin_sync.py", description=__doc__.splitlines()[0] if __doc__ else None)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="compare the pinned ref with the installed version, per project")
    check.add_argument("projects", nargs="*", metavar="project")
    check.add_argument("--all", action="store_true", help="every project `claude plugin list --json` lists")
    check.set_defaults(handler=cmd_check)
    args = parser.parse_args(argv)
    return int(args.handler(args, run))


if __name__ == "__main__":
    use_utf8()
    sys.exit(main())
