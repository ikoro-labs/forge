"""Run a command under a memory limit and a delay, and give back its exit code.

    bounded_run.py --memory-mb N --timeout S -- <command> [args...]

The standard library only.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

from handoff_header import ProcessGroup, group_options  # noqa: E402

TAIL_BYTES = 8192
# What a command prints when an allocation fails under the limit (Python, C and C++ runtimes, Windows).
MEMORY_FAILURE = re.compile(
    r"MemoryError|Cannot allocate memory|bad_alloc|out of memory|not enough memory|failed to allocate",
    re.IGNORECASE,
)

# Exit codes of the launcher, in the range `timeout(1)` uses for its own, apart from the command's.
BUDGET, WRONG_CALL, REFUSED, MEMORY, DELAY, NOT_FOUND = 120, 121, 122, 123, 124, 127


class Tail:
    """Forwards a command's stderr as it comes and keeps its last bytes, to read why it failed."""

    def __init__(self) -> None:
        self.data = b""
        self.thread: threading.Thread | None = None

    def follow(self, stream: Any) -> None:
        def pump() -> None:
            while chunk := stream.read1(4096):
                sys.stderr.buffer.write(chunk)
                sys.stderr.buffer.flush()
                self.data = (self.data + chunk)[-TAIL_BYTES:]

        self.thread = threading.Thread(target=pump, daemon=True)
        self.thread.start()

    def finish(self) -> str:
        if self.thread:
            self.thread.join(timeout=5)
        return self.data.decode("utf-8", errors="replace")


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
    cwd: Path | None = None, stdout: Any = None, stderr: Any = None, tail: Tail | None = None,
) -> Outcome:
    """Run `args` under a memory limit and a delay, and kill its process group at the delay.

    A limit that cannot be set is a command not run. The group is `ProcessGroup` of
    `handoff_header`: on Windows the command starts suspended and runs only once its job object
    holds it with the limit, so nothing escapes; on Linux the limit is `RLIMIT_AS` and the group is
    the command's own session, killed with `killpg`. With `tail`, stderr is piped through it.
    Shared by `base_replay.py`.
    """
    try:
        options: dict[str, Any] = {"preexec_fn": limit_posix(memory_mb)} if os.name != "nt" else {}
        process = subprocess.Popen(
            args, shell=shell, cwd=cwd, stdout=stdout, stderr=subprocess.PIPE if tail else stderr,
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
        if tail and process.stderr:
            tail.follow(process.stderr)
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
    if not command:
        print("bounded_run: aucune commande après --", file=sys.stderr)
        return WRONG_CALL
    if not shutil.which(command[0]):
        print(f"bounded_run: commande introuvable ({command[0]})", file=sys.stderr)
        return NOT_FOUND
    tail = Tail()
    outcome = run_bounded(command, timeout=args.timeout, memory_mb=args.memory_mb, tail=tail)
    seen = tail.finish()
    if outcome.code is None:
        print(f"bounded_run: {outcome.why}", file=sys.stderr)
        return DELAY if outcome.kind == "delay" else REFUSED
    if outcome.code != 0 and MEMORY_FAILURE.search(seen):
        print(
            f"bounded_run: borne de mémoire de {args.memory_mb} Mo probablement atteinte "
            "(un échec d'allocation est dans la sortie d'erreur de la commande)",
            file=sys.stderr,
        )
        return MEMORY
    return outcome.code


if __name__ == "__main__":
    sys.exit(main())
