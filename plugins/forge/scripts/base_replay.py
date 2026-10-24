"""Replay on a copy of the base the test files a PR adds or changes: each must fail there.

    python base_replay.py --base <ref> --head <ref> [--usine FILE] [--memory-mb N] [--timeout S]

Run from a clone of the project. The script takes the files the PR adds or changes under a
`test-path` prefix (`git diff <base>...<head>`), extracts the merge base of the two refs into a
temporary folder (`git archive`: nothing is written to the repository, its configuration included),
lays those files there as the head has them, runs each `install` command, then the `red-replay`
command once per file, and deletes the folder.

`red-replay` is a command line in which `{file}` (the test file, relative to the root of the
repository) or `{name}` (its base name) is replaced by the file to replay, quoted. A command exiting
with 0 means the file passes on the base: its tests prove nothing of the change. One line per file
is printed, the status, the file and a detail separated by tabs:

    PASSES   the command exits 0 on the base (the detail is the end of its output)
    RED      the command fails on the base, as a test of a change should (the detail is its code)
    NOT RUN  the replay could not run (the detail is the command and why: delay, limit, install...)

`PASSES` is judged at the grain of the file: the command runs on the whole file, so a file with a
passing test beside a failing one is `RED`. A line `NONE` says no test file was added or changed.
Exit code 0 when no file passes on the base, 1 when one does, 2 when a replay could not run or the
call is wrong. Without the key `test-path` or `red-replay`, the step is "sans objet (clé <nom>
absente)" and the exit code is 0.

Bounds. Each command (install ones included) runs under a memory limit (`--memory-mb`, 2000 by
default) and a delay (`--timeout`, 300 s by default), because it runs test code against code that
does not expect it. On Linux the limit is `RLIMIT_AS` and the process group is killed at the delay;
on Windows the command is put in a job object with a per-process memory limit that kills what is
left when it closes. The Linux side was run on a Linux workstation; the Windows side is written from
the Win32 documentation and runs in the CI of this repository only, and macOS is not covered. A
command whose limit cannot be set is `NOT RUN`, never run unbounded.

The entries are read from the base (`--usine`, `git show origin/<base>:docs/agents/usine.md`), so a
PR cannot lift the guard it is judged by. The standard library only.
"""

from __future__ import annotations

import argparse
import io
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402

PASSES, RED, NOT_RUN, NONE = "PASSES", "RED", "NOT RUN", "NONE"
TAIL_LINES = 15


def git(*args: str, cwd: Path | None = None) -> bytes:
    done = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=cwd, capture_output=True)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.decode('utf-8', 'replace').strip()}")
    return done.stdout


def test_files(base: str, head: str, prefixes: list[str]) -> list[str]:
    """The files added or changed between the merge base and the head, under a test path."""
    raw = git("diff", "--name-only", "--no-renames", "--diff-filter=AM", "-z", f"{base}...{head}")
    paths = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    return [path for path in paths if any(path.startswith(prefix) for prefix in prefixes)]


def extract_base(base: str, root: Path) -> None:
    """The files of `base` into `root`: regular files and folders only, nothing outside `root`."""
    archive = git("archive", "--format=tar", base)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        for member in tar.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir()):
                continue
            target = root.joinpath(*name.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is not None:
                target.write_bytes(source.read())
                os.chmod(target, member.mode & 0o777 or 0o644)


def lay_head_file(head: str, path: str, root: Path) -> None:
    target = root.joinpath(*PurePosixPath(path).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(git("show", f"{head}:{path}"))


def quote(value: str) -> str:
    return subprocess.list2cmdline([value]) if os.name == "nt" else shlex.quote(value)


def command_for(template: str, path: str) -> str:
    return template.replace("{file}", quote(path)).replace("{name}", quote(PurePosixPath(path).name))


def _limit_windows(process: subprocess.Popen, memory_mb: int) -> object:
    """Put the process in a job object that caps the memory of each process and dies with its handle."""
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
        ]

    class Counters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", Basic), ("IoInfo", Counters), ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise OSError(f"CreateJobObject: erreur {ctypes.get_last_error()}")
    info = Extended()
    # JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    info.BasicLimitInformation.LimitFlags = 0x0100 | 0x2000
    info.ProcessMemoryLimit = memory_mb * 1024 * 1024
    ok = kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
    ok = ok and kernel.AssignProcessToJobObject(job, int(process._handle))  # type: ignore[attr-defined]
    if not ok:
        kernel.CloseHandle(job)
        raise OSError(f"limite de mémoire non posée: erreur {ctypes.get_last_error()}")
    return lambda: kernel.CloseHandle(job)  # closing the job kills every process left in it


def _limit_posix(memory_mb: int):
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


def run(command: str, cwd: Path, timeout: int, memory_mb: int) -> tuple[int | None, str, str]:
    """The exit code (None when the command did not run), the end of its output, and why not.

    The command runs under a memory limit and a delay, and its process group (a job object on
    Windows) is killed when the delay passes. A limit that cannot be set is a command not run.
    """
    with tempfile.TemporaryFile() as log:
        kill = None
        try:
            if os.name == "nt":
                process = subprocess.Popen(command, shell=True, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
                try:
                    kill = _limit_windows(process, memory_mb)
                except OSError:
                    process.kill()
                    raise
            else:
                process = subprocess.Popen(
                    command, shell=True, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True, preexec_fn=_limit_posix(memory_mb),
                )
        except (OSError, subprocess.SubprocessError) as error:
            return None, "", f"limite non posée ou commande non lancée ({error})"
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if kill:
                kill()
            elif os.name != "nt":
                os.killpg(process.pid, 9)
            process.kill()
            process.wait()
            return None, "", f"délai de {timeout} s dépassé"
        finally:
            if kill:
                kill()
            elif os.name != "nt":
                try:
                    os.killpg(process.pid, 9)  # what the command left running
                except ProcessLookupError:
                    pass
        log.seek(0)
        lines = log.read().decode("utf-8", errors="replace").splitlines()
    return code, "\\n".join(lines[-TAIL_LINES:]), ""


def replay(args: argparse.Namespace, config: dict[str, list[str]]) -> tuple[list[tuple[str, str, str]], int]:
    prefixes, commands = config["test-path"], config["red-replay"]
    if len(commands) != 1 or not ("{file}" in commands[0] or "{name}" in commands[0]):
        return [(NOT_RUN, "-", "la clé red-replay est une seule commande qui contient {file} ou {name}")], 2
    files = test_files(args.base, args.head, prefixes)
    if not files:
        return [(NONE, "-", "aucun fichier de test ajouté ou changé")], 0
    merge_base = git("merge-base", args.base, args.head).decode().strip()
    rows: list[tuple[str, str, str]] = []
    with tempfile.TemporaryDirectory(prefix="forge-base-") as folder:
        root = Path(folder)
        extract_base(merge_base, root)
        for path in files:
            lay_head_file(args.head, path, root)
        for install in config.get("install", []):
            code, tail, why = run(install, root, args.timeout, args.memory_mb)
            if code != 0:
                reason = why or f"code {code}, {tail}"
                return [(NOT_RUN, path, f"{install} : {reason}") for path in files], 2
        for path in files:
            command = command_for(commands[0], path)
            code, tail, why = run(command, root, args.timeout, args.memory_mb)
            if code is None:
                rows.append((NOT_RUN, path, f"{command} : {why}"))
            elif code == 0:
                rows.append((PASSES, path, tail))
            else:
                rows.append((RED, path, f"code {code}"))
    statuses = {row[0] for row in rows}
    return rows, 2 if NOT_RUN in statuses else 1 if PASSES in statuses else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--base", required=True, help="the base ref of the PR")
    parser.add_argument("--head", required=True, help="the head ref of the PR")
    parser.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md)")
    parser.add_argument("--memory-mb", type=int, default=2000, help="memory limit of each command, in MB")
    parser.add_argument("--timeout", type=int, default=300, help="delay of each command, in seconds")
    args = parser.parse_args(argv)
    config_file = Path(args.usine) if args.usine else usine.project_root() / usine.CONFIG_PATH
    try:
        config = usine.parse(config_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        config = {}
    except (OSError, UnicodeDecodeError) as error:
        print(f"base_replay: {error}", file=sys.stderr)
        return 2
    for key in ("test-path", "red-replay"):
        if not config.get(key):
            print(f"sans objet (clé {key} absente)")
            return 0
    try:
        rows, code = replay(args, config)
    except (RuntimeError, OSError, tarfile.TarError) as error:
        print(f"{NOT_RUN}\t-\t{error}")
        return 2
    for status, path, detail in rows:
        print(f"{status}\t{path}\t{detail}")
    return code


if __name__ == "__main__":
    sys.exit(main())
