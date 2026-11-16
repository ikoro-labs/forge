"""Replay the probe of each BLOCKER of a verdict, in a copy of the head, under the bound.

    python probe_replay.py <verdict file | -> --root <copy of the head> [--usine FILE]
                           [--memory-mb N] [--timeout S]

A `[BLOCKER]` that rests on an execution carries its probe as its last field, `probe: `<test file>` =>
`<expected output>`` (`parse_output.py` reads it). The probe is closed: it names a test file of the
head, and nothing the judge writes runs as a command. The script runs that file by the command of the
key `red-replay`, as the replay on the base does (`{file}` replaced by the name, `{name}` by its base
name, both quoted, `{report}` by a throwaway path outside the copy), in `--root`, and looks for the
expected output in what it printed, standard error included, spaces and line breaks folded. The exit
code is not read: a probe that proves a failure expects the failure's text. One line per BLOCKER is
printed, the status, the number of the finding in `FINDINGS:` (the one `parse_output.py --replay`
reads) and a detail, separated by tabs:

    CONFIRMED       the expected output is in what the run printed
    NOT REPRODUCED  it is not: the detail is the end of the output, or the delay when the run was
                    killed there. The BLOCKER becomes a `NOTE` marked `non reproduit`.
    REFUSED         the name is not a test file of the head: absent from the copy, a folder, a link,
                    outside every prefix of the key `test-path`. Nothing runs; the verdict goes back
                    to its judge.
    NOT RUN         the probe could not run (the detail is why: budget of the post, no bound, a key
                    absent, copy absent, verdict unreadable). The BLOCKER is neither confirmed nor
                    demoted.
    DEDUCED         the BLOCKER has no probe: it rests on a reading of the code, counts, and the
                    report marks it `déduit`. Nothing runs.

A name that is absolute, has a `..` part or holds a character outside ASCII letters, digits and `._/-`
is refused by `parse_output.py` before anything else: the verdict is unreadable, a `NOT RUN` line
says why, and nothing runs. A line `NONE` says the verdict has no BLOCKER. Exit code 0 when no probe
is `NOT REPRODUCED`, `REFUSED` or `NOT RUN`, 1 when one is `NOT REPRODUCED` or `REFUSED`, 2 when one
did not run or the call is wrong (a `NOT RUN` wins: the verdict cannot stand yet).

A delay passed is `NOT REPRODUCED`, not `NOT RUN`: the probe was launched and did not print what the
judge said it prints. A probe a hung test cannot settle must not hold a merge for ever.

What runs, and with what access. The command is the base's `red-replay`, never a text of the judge,
and the file is a test of the head: what runs is code of the PR, as in the replay on the base and in
the CI. It runs as the user of the session, with the session's environment, and reaches what that user
reaches (the network, the files, a keyring): the probe does not isolate a test of the PR from the post.
The copy of the head is made by `git archive`: a copy with a `.git` (a folder, or the file of a linked
worktree) is refused, `NOT RUN`, so the test does not run in the repository the PR is judged in.

Bounds. Each test file runs under the memory limit and the delay of the key `run-limits` by
`run_bounded` of `bounded_run.py`, after the budget of the post (key `run-budget`) is held, waiting for
it up to the delay the key gives. Without `run-limits` (and without `--memory-mb` and `--timeout`),
no probe runs: each is `NOT RUN`, none ever runs unbounded. Without `test-path` or `red-replay`, each
probe is `NOT RUN`, "sans objet (clé <nom> absente)". Without `run-budget`, the budget is "sans objet
(clé `run-budget` absente)", said on stderr. The command goes through a shell, where the launcher
cannot see a `-n` of pytest-xdist: the workers are not brought down here. The entries are read from the
base (`--usine`, `git show origin/<base>:docs/agents/usine.md`), so a PR cannot lift the bound it is
judged by, nor change the command its probes run by. The Linux side was run on a Linux workstation.
The Windows side has not run: it rests on the same `run_bounded` as `base_replay.py`, whose Windows
form has run in the CI of this repository only. macOS is not covered. The standard library only.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

from base_replay import command_for  # noqa: E402  the `red-replay` command, built as the replay on the base builds it
from bounded_run import (  # noqa: E402  the launcher's limits and budget, found through the `sys.path` set above
    Budget,
    key_budget,
    key_limits,
    positive,
    read_config,
    run_bounded,
    wait_for_budget,
)
from parse_output import OutputError, parse_verdict, probe_name_problem  # noqa: E402  the grammar of the probe, read in one place

CONFIRMED, NOT_REPRODUCED, REFUSED, NOT_RUN, DEDUCED, NONE = (
    "CONFIRMED", "NOT REPRODUCED", "REFUSED", "NOT RUN", "DEDUCED", "NONE",
)
READ_BYTES = 2_000_000
TAIL_CHARS = 400


def linked_to_a_repository(root: Path) -> bool:
    """A `.git` folder, or the `.git` file of a linked worktree, would give the test the real repository."""
    return (root / ".git").exists() or (root / ".git").is_symlink()


def one_line(text: str) -> str:
    return "\\n".join(text.strip().splitlines())


def refusal(name: str, root: Path, prefixes: list[str]) -> str:
    """Why `name` is not a test file of the head in `root`, or `""` when it is one."""
    problem = probe_name_problem(name)
    if problem:
        return problem
    if not any(name.startswith(prefix) for prefix in prefixes):
        return f"hors des préfixes de la clé `test-path` ({', '.join(prefixes)})"
    path = root.joinpath(*PurePosixPath(name).parts)
    if path.is_symlink() or not path.is_file():
        return "absent de la tête, ou pas un fichier"
    if root.resolve() not in path.resolve().parents:
        return "hors de la copie de la tête"
    return ""


def run_probe(template: str, name: str, root: Path, timeout: int, memory_mb: int) -> tuple[int | None, str, str, str]:
    """The exit code (None when it did not finish), what it printed, why not, and the kind of stop."""
    with tempfile.TemporaryFile() as log, tempfile.TemporaryDirectory() as reports:
        outcome = run_bounded(
            command_for(template, name, Path(reports) / "report.xml"), shell=True, cwd=root,
            timeout=timeout, memory_mb=memory_mb, stdout=log, stderr=subprocess.STDOUT,
        )
        log.seek(0)
        printed = log.read(READ_BYTES).decode("utf-8", errors="replace")
    return outcome.code, printed, outcome.why, outcome.kind


def replay(
    findings: list[dict[str, Any]], root: Path, config: dict[str, list[str]], memory_mb: int, timeout: int,
    budget: Budget | None,
) -> list[tuple[str, int, str]]:
    template, prefixes = config["red-replay"][0], config["test-path"]
    rows: list[tuple[str, int, str]] = []
    refused = ""
    for number, finding in enumerate(findings, 1):
        if finding["severity"] != "BLOCKER":
            continue
        probe = finding["probe"]
        if probe is None:
            rows.append((DEDUCED, number, "-"))
            continue
        name, expect = probe["file"], probe["expect"]
        if why_not := refusal(name, root, prefixes):
            rows.append((REFUSED, number, f"{name} : {why_not}, jamais lancé"))
            continue
        if not refused and budget is not None and (reasons := wait_for_budget(budget)):
            refused = f"budget du poste non tenu : {'; '.join(reasons)}"
        if refused:
            rows.append((NOT_RUN, number, f"{name} : {refused}"))
            continue
        code, printed, why, kind = run_probe(template, name, root, timeout, memory_mb)
        if code is None and kind == "delay":
            rows.append((NOT_REPRODUCED, number, f"{name} : {why}, sonde tuée"))
        elif code is None:
            rows.append((NOT_RUN, number, f"{name} : {why}"))
        elif " ".join(expect.split()) in " ".join(printed.split()):
            rows.append((CONFIRMED, number, name))
        else:
            rows.append((NOT_REPRODUCED, number, f"{name} : sortie sans `{expect}` : {one_line(printed[-TAIL_CHARS:])}"))
    return rows


def not_run(findings: list[dict[str, Any]], reason: str) -> list[tuple[str, int, str]]:
    """Every probe of the verdict is `NOT RUN` for one reason; a blocker with no probe stays `DEDUCED`."""
    rows: list[tuple[str, int, str]] = []
    for number, finding in enumerate(findings, 1):
        if finding["severity"] != "BLOCKER":
            continue
        if finding["probe"] is None:
            rows.append((DEDUCED, number, "-"))
        else:
            rows.append((NOT_RUN, number, f"{finding['probe']['file']} : {reason}"))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("verdict", help="the verdict of forge:qc-conf, a file or - for the standard input")
    parser.add_argument("--root", required=True, help="the copy of the head where each test file runs")
    parser.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md)")
    parser.add_argument("--memory-mb", type=positive, help="memory limit of each probe (else the key run-limits)")
    parser.add_argument("--timeout", type=positive, help="delay of each probe (else the key run-limits)")
    args = parser.parse_args(argv)
    try:
        text = sys.stdin.read() if args.verdict == "-" else Path(args.verdict).read_text(encoding="utf-8")
        findings = cast("list[dict[str, Any]]", parse_verdict(text)["FINDINGS"])
    except (OSError, UnicodeDecodeError, OutputError) as error:
        print(f"{NOT_RUN}\t-\tverdict illisible : {one_line(str(error))}")
        return 2
    if not any(finding["severity"] == "BLOCKER" for finding in findings):
        print(f"{NONE}\t-\taucun BLOCKER à rejouer")
        return 0
    rows: list[tuple[str, int, str]]
    root = Path(args.root)
    try:
        config = read_config(args.usine)
        key_memory, key_timeout = key_limits(config)
        parts = key_budget(config)
    except ValueError as error:
        rows = not_run(findings, one_line(str(error)))
    else:
        memory_mb, timeout = args.memory_mb or key_memory, args.timeout or key_timeout
        budget = Budget(**parts) if parts else None
        if budget is None:
            print("probe_replay: budget du poste sans objet (clé `run-budget` absente)", file=sys.stderr)
        absent = next((key for key in ("test-path", "red-replay") if not config.get(key)), "")
        commands = config.get("red-replay", [])
        if not memory_mb or not timeout:
            rows = not_run(findings, "sans objet (clé `run-limits` absente) : aucune sonde ne tourne sans borne")
        elif absent:
            rows = not_run(findings, f"sans objet (clé `{absent}` absente) : aucune sonde ne tourne")
        elif len(commands) != 1 or not ("{file}" in commands[0] or "{name}" in commands[0]):
            rows = not_run(findings, "la clé red-replay est une seule commande qui contient {file} ou {name}")
        elif not root.is_dir():
            rows = not_run(findings, f"copie de la tête absente ({root})")
        elif linked_to_a_repository(root):
            rows = not_run(findings, f"la copie de la tête porte un `.git` ({root}) : faire la copie par `git archive`")
        else:
            rows = replay(findings, root, config, memory_mb, timeout, budget)
    for status, number, detail in rows:
        print(f"{status}\t{number}\t{detail}")
    statuses = {row[0] for row in rows}
    return 2 if NOT_RUN in statuses else 1 if statuses & {NOT_REPRODUCED, REFUSED} else 0


if __name__ == "__main__":
    sys.exit(main())
