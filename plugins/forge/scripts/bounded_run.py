"""Run a command under a memory limit and a delay, and give back its exit code.

    bounded_run.py --memory-mb N --timeout S -- <command> [args...]

The standard library only.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

from handoff_header import ProcessGroup, group_options  # noqa: E402

TAIL_BYTES = 8192


class Outcome(NamedTuple):
    """How a bounded command ended: its exit code (None when it did not run), why not, and the kind
    of stop (`""` when it ran to its end, `"delay"` or `"bound"` otherwise)."""

    code: int | None
    why: str = ""
    kind: str = ""


def limit_posix(memory_mb: int):
    """A `preexec_fn` that caps the address space of the command and drops core dumps."""
    import resource

    def apply() -> None:
        limit = memory_mb * 1024 * 1024
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        if hard != resource.RLIM_INFINITY:
            limit = min(limit, hard)  # the session's own limit stays the ceiling
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return apply


def run_bounded(
    args: str | list[str], *, timeout: int, memory_mb: int, shell: bool = False,
    cwd: Path | None = None, stdout: Any = None, stderr: Any = None,
) -> Outcome:
    """Run `args` under a memory limit and a delay, and kill its process group at the delay.

    A limit that cannot be set is a command not run. The group is `ProcessGroup` of
    `handoff_header`: on Windows the command starts suspended and runs only once its job object
    holds it with the limit, so nothing escapes; on Linux the limit is `RLIMIT_AS` and the group is
    the command's own session, killed with `killpg`. Shared by `base_replay.py`.
    """
    try:
        options: dict[str, Any] = {"preexec_fn": limit_posix(memory_mb)} if os.name != "nt" else {}
        process = subprocess.Popen(
            args, shell=shell, cwd=cwd, stdout=stdout, stderr=stderr,
            **group_options(suspended=True), **options,
        )
    except (OSError, subprocess.SubprocessError, OverflowError) as error:
        return Outcome(None, f"limite non posée ou commande non lancée ({error})", "bound")
    group = ProcessGroup(process, memory_mb=memory_mb, suspended=True)
    try:
        if not group.limited:
            group.kill()
            return Outcome(None, "limite de mémoire non posée", "bound")
        group.start()
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            group.kill()
            return Outcome(None, f"délai de {timeout} s dépassé", "delay")
        group.kill()  # what the command left running
    finally:
        group.close()
    return Outcome(code)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    options, command = (argv[: argv.index("--")], argv[argv.index("--") + 1 :]) if "--" in argv else (argv, [])
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--memory-mb", type=int, help="memory limit, in MB")
    parser.add_argument("--timeout", type=int, help="delay, in seconds")
    args = parser.parse_args(options)
    outcome = run_bounded(command, timeout=args.timeout, memory_mb=args.memory_mb)
    return outcome.code if outcome.code is not None else 1


if __name__ == "__main__":
    sys.exit(main())
