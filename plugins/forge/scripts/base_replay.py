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

The grain is the file, and a `RED` line says so (`code 1 (grain du fichier : un test qui passe à
côté n'est pas vu)`): the command runs on the whole file, so a file with a passing test beside a
failing one is `RED`. A `RED` says only that the file, run on the base, exits non-zero; it does not
say that each test of the file is red. A line `NONE` says no test file was added or changed.

The grain is the test when `red-replay` also holds `{report}`, replaced by the path, quoted, of a file
where the command writes a JUnit XML report (`pytest {file} --junitxml={report}`). The script reads it
(`junit_report.py`), keeps the tests the PR adds or changes in the file (the lines of the diff against
the position of each test name in the head file: a reading of the text, which `junit_report.py` says the
limits of), and prints one line per test of them that passes or is skipped, and one `RED` line for the
file when some are red:

    PASSES   <file>::<test>   the test passes on the base
    SKIPPED  <file>::<test>   the test is skipped on the base, it proves nothing (no effect on the code)
    RED      <file>           n test(s) rouge(s) sur m ajouté(s) ou changé(s) (grain du test)
    NONE     <file>           the file changed, no test of it did (a change above its first test, an import)

A command that exits 0 without writing the report is `NOT RUN`, never `PASSES`; one that exits non-zero
without a report is `RED` at the grain of the file (it fails before its tests); a report that declares a
DOCTYPE or an entity, or is over 20 MB, is `NOT RUN`. Without `{report}` nothing changes: the grain is
the file. Exit code 0 when nothing passes on the base, 1 when something does, 2 when a replay could not
run or the call is wrong. Without the key `test-path` or `red-replay`, the step is "sans objet (clé
<nom> absente)" and the exit code is 0.

Bounds. Each command (install ones included) runs under a memory limit (`--memory-mb`, 2000 by
default) and a delay (`--timeout`, 300 s by default), because it runs test code against code that
does not expect it. The bound is `run_bounded` of `bounded_run.py`, which the launcher shares. On
Linux the limit is `RLIMIT_AS` and the process group is killed at the delay;
on Windows the command starts suspended (`ProcessGroup` of `handoff_header`) and runs only once a
job object with a per-process memory limit holds it, which kills what is left when it closes. The
Linux side was run on a Linux workstation. The Windows side has run in the CI of this repository
only, and its first run failed (the limit was not held, a process kept the folder); this form is
written from the Win32 documentation and is not yet seen to pass. macOS is not covered. A command
whose limit cannot be set is `NOT RUN`.

The entries are read from the base (`--usine`, `git show origin/<base>:docs/agents/usine.md`), so a
PR cannot lift the guard it is judged by. The standard library only.
"""

from __future__ import annotations

import argparse
import io
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import junit_report  # noqa: E402
import usine  # noqa: E402
from bounded_run import run_bounded  # noqa: E402

PASSES, RED, NOT_RUN, NONE, SKIPPED = "PASSES", "RED", "NOT RUN", "NONE", "SKIPPED"
TAIL_LINES = 15
GRAIN = "(grain du fichier : un test qui passe à côté n'est pas vu)"


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


def command_for(template: str, path: str, report: Path | None = None) -> str:
    command = template.replace("{file}", quote(path)).replace("{name}", quote(PurePosixPath(path).name))
    return command.replace("{report}", quote(str(report))) if report else command


def run(command: str, cwd: Path, timeout: int, memory_mb: int) -> tuple[int | None, str, str]:
    """The exit code (None when the command did not run), the end of its output, and why not.

    The command runs under the bound of `bounded_run.run_bounded`, shared with the launcher: a
    memory limit, a delay, the process group killed when the delay passes, and a command not run
    when its limit cannot be set. It is `cmd.exe` or `sh`, which starts the real command.
    """
    with tempfile.TemporaryFile() as log:
        outcome = run_bounded(
            command, shell=True, cwd=cwd, timeout=timeout, memory_mb=memory_mb,
            stdout=log, stderr=subprocess.STDOUT,
        )
        if outcome.code is None:
            return None, "", outcome.why
        log.seek(0)
        lines = log.read().decode("utf-8", errors="replace").splitlines()
    return outcome.code, "\\n".join(lines[-TAIL_LINES:]), ""


def replay_by_test(
    args: argparse.Namespace, template: str, path: str, root: Path, report: Path
) -> list[tuple[str, str, str]]:
    """The rows of one file replayed at the grain of the test, from the JUnit report the command writes."""
    command = command_for(template, path, report)
    code, _tail, why = run(command, root, args.timeout, args.memory_mb)
    if code is None:
        return [(NOT_RUN, path, f"{command} : {why}")]
    if not report.exists():
        if code == 0:
            return [(NOT_RUN, path, f"{command} : sortie 0 sans rapport JUnit à l'emplacement de {{report}}")]
        return [(RED, path, f"code {code} {GRAIN}")]
    try:
        cases = junit_report.parse(report)
    except junit_report.ReportError as error:
        return [(NOT_RUN, path, f"{command} : {error}")]
    diff = git("diff", "-U0", "--no-renames", f"{args.base}...{args.head}", "--", path).decode("utf-8", "replace")
    text = git("show", f"{args.head}:{path}").decode("utf-8", "replace")
    mine = junit_report.touched(cases, text, junit_report.changed_ranges(diff))
    if not mine:
        if code != 0 and not cases:
            return [(RED, path, f"code {code} {GRAIN}")]
        return [(NONE, path, "aucun test ajouté ou changé dans ce fichier (grain du test)")]
    rows = []
    for case in mine:
        if case.status == junit_report.PASS:
            rows.append((PASSES, f"{path}::{case.ident}", "passe sur la base (grain du test)"))
        elif case.status == junit_report.SKIPPED:
            rows.append((SKIPPED, f"{path}::{case.ident}", "ignoré sur la base : ne prouve rien (grain du test)"))
    failed = sum(case.status == junit_report.FAIL for case in mine)
    if failed:
        rows.append((RED, path, f"{failed} test(s) rouge(s) sur {len(mine)} ajouté(s) ou changé(s) (grain du test)"))
    return rows


def replay(args: argparse.Namespace, config: dict[str, list[str]]) -> tuple[list[tuple[str, str, str]], int]:
    prefixes, commands = config["test-path"], config["red-replay"]
    if len(commands) != 1 or not ("{file}" in commands[0] or "{name}" in commands[0]):
        return [(NOT_RUN, "-", "la clé red-replay est une seule commande qui contient {file} ou {name}")], 2
    files = test_files(args.base, args.head, prefixes)
    if not files:
        return [(NONE, "-", "aucun fichier de test ajouté ou changé")], 0
    merge_base = git("merge-base", args.base, args.head).decode().strip()
    rows: list[tuple[str, str, str]] = []
    folder = tempfile.mkdtemp(prefix="forge-base-")
    try:
        # The copy and the JUnit reports are apart: a report is not a file of the project under test.
        root = Path(folder) / "copy"
        reports = Path(folder) / "reports"
        root.mkdir()
        reports.mkdir()
        extract_base(merge_base, root)
        for path in files:
            lay_head_file(args.head, path, root)
        for install in config.get("install", []):
            code, tail, why = run(install, root, args.timeout, args.memory_mb)
            if code != 0:
                reason = why or f"code {code}, {tail}"
                return [(NOT_RUN, path, f"{install} : {reason}") for path in files], 2
        for number, path in enumerate(files):
            if "{report}" in commands[0]:
                rows.extend(replay_by_test(args, commands[0], path, root, reports / f"{number}.xml"))
                continue
            command = command_for(commands[0], path)
            code, tail, why = run(command, root, args.timeout, args.memory_mb)
            if code is None:
                rows.append((NOT_RUN, path, f"{command} : {why}"))
            elif code == 0:
                rows.append((PASSES, path, tail))
            else:
                rows.append((RED, path, f"code {code} {GRAIN}"))
    finally:
        # A process still holding the folder (WinError 32) must not cost the rows of the replay.
        try:
            shutil.rmtree(folder)
        except OSError:
            pass
    statuses = {row[0] for row in rows}
    return rows, 2 if NOT_RUN in statuses else 1 if PASSES in statuses else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--base", required=True, help="the base ref of the PR")
    parser.add_argument("--head", required=True, help="the head ref of the PR")
    parser.add_argument("--usine", help="the usine.md to read, as it is (default: docs/agents/usine.md with docs/agents/usine-gardes.md on origin/main)")
    parser.add_argument("--memory-mb", type=int, default=2000, help="memory limit of each command, in MB")
    parser.add_argument("--timeout", type=int, default=300, help="delay of each command, in seconds")
    args = parser.parse_args(argv)
    try:
        config = usine.read_config(args.usine, usine.project_root())
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
