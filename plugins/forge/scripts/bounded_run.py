"""Run a test command, a probe or a suite under a memory limit, a delay and the budget of the post.

    bounded_run.py [--memory-mb N] [--timeout S] [--min-available-mb N] [--max-load X]
                   [--max-workers N] [--wait S] [--usine FILE] -- <command> [args...]
    bounded_run.py [budget options] [--usine FILE] --check

Three things, in this order, before and while the command runs.

The budget of the post. A limit per command is not enough: a suite whose processes each stay small
can still empty the memory of the whole post when many run together. Before the launch the
launcher reads the post's available memory (`MemAvailable` of /proc/meminfo) and its 1 minute load
average. Out of budget, it waits, up to `--wait` seconds, for the post to come back within it, then
exits 120 with the reason on stderr and runs nothing. `--check` reads the budget and launches
nothing: it is what runs before a sub-agent that will run tests. The memory it cannot read counts
as out of budget. A system without a load average (Windows) is judged on its memory alone, and the
launcher says so. Windows reads the available physical memory through `GlobalMemoryStatusEx`.

The workers. When the command names pytest, the `-n` of pytest-xdist is brought down to
`--max-workers`, `-n auto` included (`clamp_workers`). A `-n` set by a configuration file or by
`PYTEST_ADDOPTS`, or hidden in a shell string (`sh -c "pytest -n 6"`), is not seen. A command that
does not name pytest is never touched.

The bound. The command runs under a memory limit and a delay: the `run_bounded` function shared with
`base_replay.py`. On Linux the limit is `RLIMIT_AS` and the process group is killed at the delay;
on Windows the command starts suspended (`ProcessGroup` of `handoff_header`) and runs only once a
job object with a per-process memory limit holds it, which kills what is left when it closes. A
bound that cannot be set refuses to launch. macOS is not covered. The Linux side was run on a Linux
workstation. The Windows side has run in the CI of this repository only: it is written from the
Win32 documentation, and its bound is not seen on a real workstation.

The values come from `docs/agents/usine.md` (`--usine` reads another file, as `forge:qc-gate` does
with the file of the base), and an option wins over its key. No value has a default:

    - `run-limits` : `<memory in MB> | <delay in seconds>`
    - `run-budget` : `<MB available at least> | <1 minute load at most> | <workers at most> | <wait at most in seconds>`

Without `run-limits`, both `--memory-mb` and `--timeout` are required. Without `run-budget` and
its options, the budget is "sans objet (clé `run-budget` absente)", said on stderr, and nothing is
held. A budget given by halves is a wrong call.

Exit codes. The command's own code when it ends by itself (a command killed by a signal gives
128 plus the signal, as a shell does). The launcher's own, in the range `timeout(1)` keeps for its
own, away from the codes of a test suite:

    120  the budget of the post is not held after the wait
    121  wrong call: bad option, key invalid or absent, no command
    122  the bound cannot be set: the command was not launched
    123  the memory limit was probably reached (see below)
    124  the delay passed and the command was killed
    127  the command does not exist

A memory limit on the address space cannot be seen from outside: the command fails by itself on an
allocation. The launcher forwards the command's stderr as it comes and keeps its end; a non-zero
exit whose end holds an allocation failure (`MemoryError`, `Cannot allocate memory`, `bad_alloc`...)
is reported with 123 and "probablement atteinte". A command that fails on its memory without
printing it keeps its own code.

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
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402
from handoff_header import ProcessGroup, _win32, group_options  # noqa: E402

TAIL_BYTES = 8192
POLL_SECONDS = 10
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
            try:
                while chunk := stream.read1(4096):
                    sys.stderr.buffer.write(chunk)
                    sys.stderr.buffer.flush()
                    self.data = (self.data + chunk)[-TAIL_BYTES:]
            finally:
                stream.close()

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


class Call(argparse.ArgumentParser):
    """Its usage errors exit with the launcher's own code: 2 is a test suite's."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"bounded_run: {message}", file=sys.stderr)
        raise SystemExit(WRONG_CALL)


def positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text} n'est pas un nombre positif")
    return value


def non_negative(text: str) -> int:
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"{text} est négatif")
    return value


def positive_float(text: str) -> float:
    value = float(text)
    if not value > 0:
        raise argparse.ArgumentTypeError(f"{text} n'est pas un nombre positif")
    return value


def read_config(path: str | None) -> dict[str, list[str]]:
    """The keys of `usine.md` (`--usine`, else the project's); empty when the file is absent."""
    config_file = Path(path) if path else usine.project_root() / usine.CONFIG_PATH
    try:
        return usine.parse(config_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"{config_file} illisible ({error})") from error


def key_limits(config: dict[str, list[str]]) -> tuple[int | None, int | None]:
    """The memory (MB) and the delay (s) of the key `run-limits`, None for both when it is absent."""
    values = config.get("run-limits")
    if not values:
        return None, None
    parts = usine.split_value(values[0], 2) if len(values) == 1 else None
    try:
        if parts:
            return positive(parts[0]), positive(parts[1])
    except (ValueError, argparse.ArgumentTypeError):
        pass
    raise ValueError(
        "la clé `run-limits` vaut une seule ligne `<mémoire en Mo> | <délai en secondes>`, deux nombres positifs"
    )


class Budget(NamedTuple):
    """What the post must have free before a launch, and the ceiling of parallel workers."""

    min_available_mb: int
    max_load: float
    max_workers: int
    wait: int


BUDGET_PARTS = (
    ("min_available_mb", positive), ("max_load", positive_float), ("max_workers", positive), ("wait", non_negative),
)


def key_budget(config: dict[str, list[str]]) -> dict[str, Any]:
    """The parts of the key `run-budget`, by name; empty when the key is absent."""
    values = config.get("run-budget")
    if not values:
        return {}
    parts = usine.split_value(values[0], len(BUDGET_PARTS)) if len(values) == 1 else None
    try:
        if parts:
            return {name: kind(part) for (name, kind), part in zip(BUDGET_PARTS, parts)}
    except (ValueError, argparse.ArgumentTypeError):
        pass
    raise ValueError(
        "la clé `run-budget` vaut une seule ligne `<Mo disponibles au moins> | <charge à 1 min au plus> | "
        "<workers au plus> | <attente au plus en secondes>`, quatre nombres"
    )


def resolve_budget(args: argparse.Namespace, config: dict[str, list[str]]) -> Budget | None:
    """The budget the key declares, each part overridden by its option; None when nothing declares it.

    A budget said by halves is an error: no threshold is ever completed with a guess.
    """
    parts = key_budget(config)
    parts.update({name: getattr(args, name) for name, _ in BUDGET_PARTS if getattr(args, name) is not None})
    if not parts:
        return None
    missing = [name for name, _ in BUDGET_PARTS if name not in parts]
    if missing:
        raise ValueError(f"budget du poste incomplet (clé `run-budget` ou options), il manque : {', '.join(missing)}")
    return Budget(**parts)


def system_state() -> tuple[int | None, float | None]:
    """The post's available memory (MB) and its 1 minute load; None for what cannot be read.

    Linux: `MemAvailable` of /proc/meminfo and the load average. Windows: the available physical
    memory (`GlobalMemoryStatusEx`); Windows has no load average, so its load is None.
    """
    available: int | None = None
    if sys.platform.startswith("linux"):
        try:
            for line in Path("/proc/meminfo").read_text(encoding="ascii", errors="replace").splitlines():
                if line.startswith("MemAvailable:"):
                    available = int(line.split()[1]) // 1024  # kB to MB
        except (OSError, ValueError, IndexError):
            available = None
    elif sys.platform == "win32":
        available = _windows_available_mb()
    try:
        load: float | None = os.getloadavg()[0]
    except (OSError, AttributeError):
        load = None
    return available, load


def _windows_available_mb() -> int | None:
    import ctypes

    try:
        kernel32 = _win32()[2]
    except (OSError, AttributeError):
        return None

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32), ("ullTotalPhys", ctypes.c_uint64),
            ("ullAvailPhys", ctypes.c_uint64), ("ullTotalPageFile", ctypes.c_uint64),
            ("ullAvailPageFile", ctypes.c_uint64), ("ullTotalVirtual", ctypes.c_uint64),
            ("ullAvailVirtual", ctypes.c_uint64), ("ullAvailExtendedVirtual", ctypes.c_uint64),
        ]

    try:
        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        kernel32.GlobalMemoryStatusEx.argtypes = (ctypes.c_void_p,)
        if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return int(status.ullAvailPhys // (1024 * 1024))
    except (OSError, AttributeError):
        return None


def unmet(budget: Budget, state: tuple[int | None, float | None]) -> list[str]:
    """Why the post is out of budget; empty when it is within. A load that cannot be read is not held."""
    available, load = state
    reasons = []
    if available is None:
        reasons.append("MemAvailable illisible")
    elif available < budget.min_available_mb:
        reasons.append(f"MemAvailable {available} Mo sous le seuil de {budget.min_available_mb} Mo")
    if load is not None and load > budget.max_load:
        reasons.append(f"charge à 1 min {load:.1f} au-dessus du seuil de {budget.max_load:g}")
    return reasons


def wait_for_budget(
    budget: Budget, *, state: Callable[[], tuple[int | None, float | None]] | None = None,
    sleep: Callable[[float], None] = time.sleep, now: Callable[[], float] = time.monotonic,
    say: Callable[[str], None] = lambda text: print(text, file=sys.stderr),
) -> list[str]:
    """Wait, up to `budget.wait` seconds, for the post to be within budget; the reasons it is not.

    `state` reads the post (`system_state` when absent); `sleep` and `now` are the clock.
    """
    read = state or system_state
    start = now()
    announced = False
    while True:
        reasons = unmet(budget, read())
        if not reasons or now() - start >= budget.wait:
            return reasons
        if not announced:
            announced = True
            say(f"bounded_run: budget du poste non tenu ({'; '.join(reasons)}), attente jusqu'à {budget.wait} s")
        sleep(min(POLL_SECONDS, budget.wait - (now() - start)))


def is_pytest(argv: list[str]) -> bool:
    names = ("pytest", "py.test")
    return any(os.path.basename(word.replace("\\", "/")).lower().removesuffix(".exe") in names for word in argv)


def clamp_workers(argv: list[str], ceiling: int) -> list[str]:
    """`argv` with the `-n` of pytest-xdist brought down to `ceiling`, `auto` and `logical` included.

    Only a command that names pytest is touched: `head -n 5` is not a number of workers. A count
    within the ceiling, and `-n 0` (no worker), stay. Forms: `-n N`, `-nN`, `--numprocesses N`,
    `--numprocesses=N`. A `-n` that a configuration file or `PYTEST_ADDOPTS` sets, or that a shell
    string (`sh -c "pytest -n 6"`) hides, is not seen.
    """
    if not is_pytest(argv):
        return argv

    def bring(value: str) -> str:
        if value in ("auto", "logical") or (value.isdigit() and int(value) > ceiling):
            return str(ceiling)
        return value

    out: list[str] = []
    words = iter(argv)
    for word in words:
        if word in ("-n", "--numprocesses"):
            out.append(word)
            value = next(words, None)
            if value is not None:
                out.append(bring(value))
        elif match := re.fullmatch(r"(-n|--numprocesses=)(\w+)", word):
            out.append(match.group(1) + bring(match.group(2)))
        else:
            out.append(word)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    options, command = (argv[: argv.index("--")], argv[argv.index("--") + 1 :]) if "--" in argv else (argv, [])
    parser = Call(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--memory-mb", type=positive, help="memory limit, in MB (else the key run-limits)")
    parser.add_argument("--timeout", type=positive, help="delay, in seconds (else the key run-limits)")
    parser.add_argument("--min-available-mb", dest="min_available_mb", type=positive, help="MB available to hold")
    parser.add_argument("--max-load", dest="max_load", type=positive_float, help="1 minute load not to pass")
    parser.add_argument("--max-workers", dest="max_workers", type=positive, help="ceiling of pytest-xdist workers")
    parser.add_argument("--wait", type=non_negative, help="seconds to wait for the budget (else the key run-budget)")
    parser.add_argument("--check", action="store_true", help="only read the budget, launch nothing")
    parser.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md)")
    args = parser.parse_args(options)
    try:
        config = read_config(args.usine)
        key_memory, key_timeout = key_limits(config)
        budget = resolve_budget(args, config)
    except ValueError as error:
        print(f"bounded_run: {error}", file=sys.stderr)
        return WRONG_CALL
    if budget is None:
        print("bounded_run: budget du poste sans objet (clé `run-budget` absente)", file=sys.stderr)
    else:
        if reasons := wait_for_budget(budget):
            print(f"bounded_run: budget du poste non tenu : {'; '.join(reasons)}", file=sys.stderr)
            return BUDGET
        if system_state()[1] is None:
            print("bounded_run: charge à 1 min : sans objet (pas de moyenne de charge ici)", file=sys.stderr)
    if args.check:
        return 0
    memory_mb = args.memory_mb or key_memory
    timeout = args.timeout or key_timeout
    if not memory_mb or not timeout:
        print(
            "bounded_run: sans objet (clé `run-limits` absente) : passe --memory-mb et --timeout, "
            "la borne n'a pas de valeur par défaut",
            file=sys.stderr,
        )
        return WRONG_CALL
    if not command:
        print("bounded_run: aucune commande après --", file=sys.stderr)
        return WRONG_CALL
    if not shutil.which(command[0]):
        print(f"bounded_run: commande introuvable ({command[0]})", file=sys.stderr)
        return NOT_FOUND
    if budget is not None and (clamped := clamp_workers(command, budget.max_workers)) != command:
        print(f"bounded_run: workers de pytest-xdist ramenés à {budget.max_workers} : {' '.join(clamped)}", file=sys.stderr)
        command = clamped
    tail = Tail()
    outcome = run_bounded(command, timeout=timeout, memory_mb=memory_mb, tail=tail)
    seen = tail.finish()
    if outcome.code is None:
        print(f"bounded_run: {outcome.why}", file=sys.stderr)
        return DELAY if outcome.kind == "delay" else REFUSED
    if outcome.code != 0 and MEMORY_FAILURE.search(seen):
        print(
            f"bounded_run: borne de mémoire de {memory_mb} Mo probablement atteinte "
            "(un échec d'allocation est dans la sortie d'erreur de la commande)",
            file=sys.stderr,
        )
        return MEMORY
    return outcome.code if outcome.code >= 0 else 128 - outcome.code


if __name__ == "__main__":
    sys.exit(main())
