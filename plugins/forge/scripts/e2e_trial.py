"""Try the factory end to end on a trial repository, before a version is published.

    e2e_trial.py [--projet DIR] [--plugin DIR] [--usine FILE] [--memory-mb N] [--timeout S]
                 [--wait-checks S] [--poll-seconds S] [--id NAME]

The tests of `tests/` prove each hook and each script alone. This script proves the chain: a coder
that opens its pull request, a guard that lets a legitimate gesture through. It builds a throwaway
project, launches `claude -p` on it with the plugin under test, reads what the run left on the trial
repository, and cleans up. It reads three keys of `docs/agents/usine.md` (`--usine` reads another
file), none of which has a default:

    - `e2e-repo` : `<owner>/<name>`, the trial repository on GitHub
    - `e2e-command` : the command line launched in the throwaway project
    - `e2e-budget-usd` : the ceiling of the run, a positive number of dollars

A key that is absent makes the trial "sans objet (clé `<nom>` absente)": the script prints
`SANS-OBJET (clé `<nom>` absente)` and exits 0, and it never prints `PASS`. The launch is bounded by
`bounded_run.py` (ticket #66): the key `run-limits` of the project, or `--memory-mb` and `--timeout`,
which win. Without either, the bound is "sans objet (clé `run-limits` absente)".

`e2e-command` is split into words as a POSIX shell does, then each word has its markers replaced (no
shell runs it): `{plugin}` (the plugin under test, `--plugin`, the plugin that holds this script by
default) and `{budget}` (the key `e2e-budget-usd`) are required, so that a command cannot try the
pinned plugin by mistake, and `{feature}`, `{ticket}` and `{base}` are optional. Any other marker is
refused.

Exit codes: 0 for `PASS` and for `SANS-OBJET`, 1 for `FAIL`, 2 for a wrong call (an ill-formed key,
an unreadable file).

The standard library only.
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path
from typing import NamedTuple, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import bounded_run  # noqa: E402  the bounded launcher of ticket #66, next to this script
import usine  # noqa: E402  the reader of `usine.md`, found through the `sys.path` set above

REPO_KEY, COMMAND_KEY, BUDGET_KEY, LIMITS_KEY = "e2e-repo", "e2e-command", "e2e-budget-usd", "run-limits"
E2E_KEYS = (REPO_KEY, COMMAND_KEY, BUDGET_KEY)
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
MARKER = re.compile(r"\{(\w+)\}")
REQUIRED_MARKERS = ("plugin", "budget")
MARKERS = (*REQUIRED_MARKERS, "feature", "ticket", "base")
WRONG_CALL = 2


class Settings(NamedTuple):
    """The keys of the trial, read and checked."""

    repo: str
    command: list[str]
    budget: str


class Call(argparse.ArgumentParser):
    """Its usage errors exit with the call's own code, 2."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"e2e_trial: {message}", file=sys.stderr)
        raise SystemExit(WRONG_CALL)


def absent_message(key: str) -> str:
    return f"SANS-OBJET (clé `{key}` absente)"


def single(config: dict[str, list[str]], key: str) -> str | None:
    """The one value of `key`, None when it is absent; a repeated key has no single value."""
    values = config.get(key)
    if not values:
        return None
    if len(values) > 1:
        raise ValueError(f"la clé `{key}` est répétée : elle vaut une seule ligne")
    return values[0]


def read_settings(config: dict[str, list[str]], *, bounded: bool) -> Settings | list[str]:
    """The settings of the trial, or the `SANS-OBJET` lines of the keys that are absent.

    `bounded` says the bound of the launch is given by the options: `run-limits` is then not needed.
    A key present and ill-formed raises `ValueError`: nothing is completed with a guess.
    """
    values = {key: single(config, key) for key in E2E_KEYS}
    absent = [absent_message(key) for key, value in values.items() if value is None]
    if not bounded and single(config, LIMITS_KEY) is None:
        absent.append(absent_message(LIMITS_KEY))
    if absent:
        return absent
    repo, command, budget = values[REPO_KEY], values[COMMAND_KEY], values[BUDGET_KEY]
    assert repo is not None and command is not None and budget is not None
    if not REPO.fullmatch(repo):
        raise ValueError(f"la clé `{REPO_KEY}` vaut `<propriétaire>/<nom>`, pas `{repo}`")
    try:
        if not float(budget) > 0:
            raise ValueError
    except ValueError:
        raise ValueError(f"la clé `{BUDGET_KEY}` vaut un nombre de dollars positif, pas `{budget}`") from None
    try:
        words = shlex.split(command)
    except ValueError as error:
        raise ValueError(f"la clé `{COMMAND_KEY}` est illisible ({error})") from None
    used = set(MARKER.findall(command))
    if unknown := sorted(used - set(MARKERS)):
        raise ValueError(
            f"la clé `{COMMAND_KEY}` cite des marques inconnues : {', '.join('{' + name + '}' for name in unknown)} "
            f"(admises : {', '.join('{' + name + '}' for name in MARKERS)})"
        )
    if lacking := [name for name in REQUIRED_MARKERS if name not in used]:
        raise ValueError(
            f"la clé `{COMMAND_KEY}` doit citer {', '.join('{' + name + '}' for name in lacking)} : "
            "sans elles l'essai ne porterait pas sur le plugin à essayer, sous le plafond"
        )
    return Settings(repo, words, budget)


def main(argv: list[str] | None = None) -> int:
    parser = Call(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--projet", default=".", help="the project that runs the trial (default: .)")
    parser.add_argument("--plugin", help="the plugin to try (default: the one that holds this script)")
    parser.add_argument("--usine", help="the usine.md to read (default: <projet>/docs/agents/usine.md)")
    parser.add_argument("--memory-mb", dest="memory_mb", type=bounded_run.positive, help="memory limit, in MB")
    parser.add_argument("--timeout", type=bounded_run.positive, help="delay of the launch, in seconds")
    parser.add_argument("--wait-checks", dest="wait_checks", type=bounded_run.non_negative, default=600,
                        help="seconds to wait for the checks of the pull request (default: 600)")
    parser.add_argument("--poll-seconds", dest="poll_seconds", type=bounded_run.positive_float, default=15,
                        help="seconds between two reads of the checks (default: 15)")
    parser.add_argument("--id", help="the name of the trial (default: the time and a random part)")
    args = parser.parse_args(argv)
    project = Path(args.projet)
    usine_file = Path(args.usine) if args.usine else project / usine.CONFIG_PATH
    try:
        config = bounded_run.read_config(str(usine_file))
        settings = read_settings(config, bounded=bool(args.memory_mb and args.timeout))
    except ValueError as error:
        print(f"e2e_trial: {error}", file=sys.stderr)
        return WRONG_CALL
    if isinstance(settings, list):
        print("\n".join(settings))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
