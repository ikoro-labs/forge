"""Replay the suite on each commit of a PR, alone: a commit that does not pass breaks `git bisect`.

    python commit_replay.py --base <ref> --head <ref> [--usine FILE] [--memory-mb N] [--timeout S]

Run from a clone of the project. The script lists the commits of the PR, oldest first
(`git rev-list --reverse <merge base>..<head>`, the merge base of the two refs), and for each one
extracts its tree into a temporary folder (`git archive`, as `base_replay.py` does: nothing is
written to the repository, its configuration included), runs each `install` command, then each
`ci-replay` command, and deletes the folder. One line per commit is printed, the status, the short
sha and a detail separated by tabs:

    PASS     every `ci-replay` command exits 0 on that commit alone
    FAIL     a command exits non-zero (the detail is the command, its code and the end of its output)
    NOT RUN  the replay could not run (the detail is why: copy not extracted, install, delay, limit,
             budget of the post)

The key `ci-replay-light`, optional, lists the commands replayed on every commit but the last: the
last commit, the head, replays every `ci-replay` command, and so does a commit when the key is absent
(or holds no command) and the sole commit of a one-commit PR. The suite is what costs, and a light list
of lints keeps the commits before the head cheap.

A line `NONE` says the PR has no commit. A `FAIL` is a measure, not an opinion: the project asks one
green commit per criterion, and the judge decides what a red one costs. Exit code 0 when every
commit passes, 1 when one fails, 2 when a replay could not run or the call is wrong. Without the key
`ci-replay`, the step is "sans objet (clé ci-replay absente)" and the exit code is 0; without the key
`run-limits` (and without `--memory-mb` and `--timeout`), "sans objet (clé run-limits absente)".

Bounds. Each command (install ones included) runs under the memory limit and the delay of the key
`run-limits`, by `run_bounded` of `bounded_run.py`, the function the launcher and `base_replay.py`
share. Before each commit the script reads the budget of the post (key `run-budget`, as the
launcher does) and waits for it up to the delay the key gives; out of budget, that commit and the
ones after it are `NOT RUN` and nothing is launched. Without the key `run-budget`, the budget is
"sans objet (clé run-budget absente)", said on stderr. The workers of pytest-xdist are not brought
down here: each command runs through a shell, where the launcher cannot see a `-n`. The delay is per
command, so a PR of n commits can take n times the suite. The Linux side was run on a Linux
workstation. The Windows side has not run: it rests on the same `run_bounded` as `base_replay.py`,
whose Windows form has run in the CI of this repository only. macOS is not covered.

The entries are read from the base (`--usine`, `usine_base.py --base origin/<base>`, both files of the base), so a
PR cannot lift the guard it is judged by. The standard library only.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402  the reader of `usine.md`, found through the `sys.path` set above
from base_replay import extract_base, git, run  # noqa: E402  the copy and the bound this replay shares with it
from bounded_run import Budget, key_budget, key_limits, positive, wait_for_budget  # noqa: E402  the launcher's limits and budget

PASS, FAIL, NOT_RUN, NONE = "PASS", "FAIL", "NOT RUN", "NONE"


def commits_of(base: str, head: str) -> list[str]:
    """The commits of the PR, oldest first: what the head has and its merge base with the base lacks."""
    merge_base = git("merge-base", base, head).decode().strip()
    raw = git("rev-list", "--reverse", f"{merge_base}..{head}").decode()
    return raw.split()


def replay_commands(config: dict[str, list[str]], is_head: bool) -> list[str]:
    """The `ci-replay` commands of a commit: the light list on an earlier one when the key declares it."""
    light = [command for command in config.get("ci-replay-light", []) if command]
    return config["ci-replay"] if is_head or not light else light


def replay_commit(
    sha: str, config: dict[str, list[str]], memory_mb: int, timeout: int, is_head: bool = True,
) -> tuple[str, str]:
    """The status and the detail of one commit, replayed alone in a copy that is deleted after."""
    folder = tempfile.mkdtemp(prefix="forge-commit-")
    try:
        root = Path(folder)
        try:
            extract_base(sha, root)
        except (RuntimeError, OSError, tarfile.TarError) as error:
            # One line per commit: git's message can hold several.
            return NOT_RUN, "copie non extraite : " + "\\n".join(str(error).splitlines())
        for command in config.get("install", []) + replay_commands(config, is_head):
            code, tail, why = run(command, root, timeout, memory_mb)
            if code is None:
                return NOT_RUN, f"{command} : {why}"
            if code != 0:
                return FAIL, f"{command} : code {code}, {tail}"
        return PASS, ""
    finally:
        # A process still holding the folder (WinError 32) must not cost the rows of the replay.
        try:
            shutil.rmtree(folder)
        except OSError:
            pass


def replay(
    shas: list[str], config: dict[str, list[str]], memory_mb: int, timeout: int, budget: Budget | None,
) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for index, sha in enumerate(shas):
        short = git("rev-parse", "--short", sha).decode().strip()
        if budget is not None and (reasons := wait_for_budget(budget)):
            reason = f"budget du poste non tenu : {'; '.join(reasons)}"
            rows.extend((NOT_RUN, git("rev-parse", "--short", rest).decode().strip(), reason) for rest in shas[index:])
            return rows
        status, detail = replay_commit(sha, config, memory_mb, timeout, index == len(shas) - 1)
        rows.append((status, short, detail))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--base", required=True, help="the base ref of the PR")
    parser.add_argument("--head", required=True, help="the head ref of the PR")
    parser.add_argument("--usine", help="the usine.md to read, as it is (default: docs/agents/usine.md with docs/agents/usine-gardes.md on origin/main)")
    parser.add_argument("--memory-mb", type=positive, help="memory limit of each command (else the key run-limits)")
    parser.add_argument("--timeout", type=positive, help="delay of each command (else the key run-limits)")
    args = parser.parse_args(argv)
    try:
        config = usine.read_config(args.usine, usine.project_root())
    except FileNotFoundError:
        config = {}
    except (OSError, UnicodeDecodeError) as error:
        print(f"commit_replay: {error}", file=sys.stderr)
        return 2
    if not config.get("ci-replay"):
        print("sans objet (clé ci-replay absente)")
        return 0
    try:
        key_memory, key_timeout = key_limits(config)
        parts = key_budget(config)
    except ValueError as error:
        print(f"{NOT_RUN}\t-\t{error}")
        return 2
    memory_mb, timeout = args.memory_mb or key_memory, args.timeout or key_timeout
    if not memory_mb or not timeout:
        print("sans objet (clé run-limits absente)")
        return 0
    budget = Budget(**parts) if parts else None
    if budget is None:
        print("commit_replay: budget du poste sans objet (clé `run-budget` absente)", file=sys.stderr)
    try:
        shas = commits_of(args.base, args.head)
        rows = replay(shas, config, memory_mb, timeout, budget) if shas else []
    except (RuntimeError, OSError) as error:
        print(f"{NOT_RUN}\t-\t{error}")
        return 2
    if not rows:
        print(f"{NONE}\t-\taucun commit propre à la PR")
        return 0
    for status, short, detail in rows:
        print(f"{status}\t{short}\t{detail}")
    statuses = {row[0] for row in rows}
    return 2 if NOT_RUN in statuses else 1 if FAIL in statuses else 0


if __name__ == "__main__":
    sys.exit(main())
