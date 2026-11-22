"""Say how old each dependency a PR adds is on its public registry.

    python lockfile_age.py [--usine FILE] [--root DIR] --base REF --head REF

Run from a clone of the project (`--root`, the current directory by default). The script reads
each lockfile of the `lockfile` key of `docs/agents/usine.md` at `--base` and at `--head` by
`git show`, and prints one line per package the head adds or whose version it changes, with the
date of the package's first publication and the date of that version, read on the registry. It
launches no command the project declares. Each `lockfile` entry is `<path> | <ecosystem>`:

    uv.lock | pypi
    package-lock.json | npm

`pypi` reads a `uv.lock`, `npm` a `package-lock.json` (lockfileVersion 2 or 3). One line per
package, `<status>`, `<lockfile>`, `<package> <version>` and `<detail>` separated by tabs, the
status being OLD (the version is at least `dependency-min-age` days old), YOUNG (younger), NOT
FOUND (the registry has no such package or version), NOT CHECKED (the package does not come from
the public registry, the script cannot date it), NOT RUN (the registry did not answer: never a
pass), NONE (the lockfile adds nothing) or INVALID (a malformed entry or lockfile). Exit code 0
when no package is YOUNG, NOT FOUND or NOT CHECKED, 1 when one is, 2 when one line is NOT RUN or
INVALID, or the call is wrong. Without the `lockfile` key or the `dependency-min-age` key (a number
of days, no default), the step is "sans objet" and the exit code is 0.

The keys are read from `--usine` (`git show origin/<base>:docs/agents/usine.md`): a PR cannot lift
the threshold it is judged by. The standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402

LOCKFILE_KEY = "lockfile"
AGE_KEY = "dependency-min-age"
DEFAULT_REGISTRIES = {"pypi": "https://pypi.org/pypi", "npm": "https://registry.npmjs.org"}
TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class Package:
    name: str
    version: str


@dataclass(frozen=True)
class Dates:
    package: datetime  # the first publication of the package
    version: datetime  # the publication of the version


def _quoted(value: str) -> str | None:
    match = re.search(r'"([^"]*)"', value)
    return match.group(1) if match else None


def parse_uv_lock(text: str) -> list[Package]:
    """The `[[package]]` blocks of a `uv.lock`."""
    blocks: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        if line.startswith("["):
            current = {} if line.strip() == "[[package]]" else None
            if current is not None:
                blocks.append(current)
        elif current is not None and (field := re.match(r"^(name|version|source)\s*=\s*(.*)$", line)):
            current[field.group(1)] = field.group(2)
    packages = []
    for block in blocks:
        name, version = _quoted(block.get("name", "")), _quoted(block.get("version", ""))
        if name is None or version is None:
            continue
        packages.append(Package(re.sub(r"[-_.]+", "-", name).lower(), version))
    return packages


def read_at(root: Path, ref: str, path: str) -> str | None:
    """The text of `path` at `ref`, or None when the file does not exist there."""
    exists = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{ref}:{path}"], capture_output=True)
    if exists.returncode != 0:
        return None
    done = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{path}"], capture_output=True, check=True)
    return done.stdout.decode("utf-8")


def added_packages(before: list[Package], after: list[Package]) -> list[tuple[Package, str]]:
    """The packages `after` adds, or whose version it changes, each with what changed."""
    known: dict[str, set[str]] = {}
    for package in before:
        known.setdefault(package.name, set()).add(package.version)
    seen: set[Package] = set()
    changes = []
    for package in after:
        if package in seen or package.version in known.get(package.name, set()):
            continue
        seen.add(package)
        if package.name in known:
            changes.append((package, f"version {', '.join(sorted(known[package.name]))} -> {package.version}"))
        else:
            changes.append((package, "ajouté"))
    return changes


def parse_time(text: str) -> datetime:
    """A registry timestamp (`2021-05-05T14:18:17.237677Z`) as an aware datetime."""
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?", text)
    if match is None:
        raise ValueError(f"date illisible : {text}")
    stamp, fraction, zone = match.groups()
    fraction = (fraction or "0")[:6].ljust(6, "0")
    zone = "+00:00" if zone in (None, "Z") else zone
    return datetime.fromisoformat(f"{stamp}.{fraction}{zone}")


def fetch_json(url: str) -> dict[str, dict[str, list[dict[str, str]]]]:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "forge-lockfile-age"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        document: dict[str, dict[str, list[dict[str, str]]]] = json.loads(response.read().decode("utf-8"))
        return document


def pypi_dates(api: str, package: Package) -> Dates:
    releases = fetch_json(f"{api.rstrip('/')}/{package.name}/json")["releases"]
    published = {
        version: [parse_time(file["upload_time_iso_8601"]) for file in files] for version, files in releases.items()
    }
    return Dates(min(time for times in published.values() for time in times), min(published[package.version]))


def evaluate(root: Path, entry: str, base: str, head: str, apis: dict[str, str], threshold: int) -> list[str]:
    parts = usine.split_value(entry, 2)
    assert parts is not None
    path, _ecosystem = parts
    before, after = read_at(root, base, path), read_at(root, head, path)
    changes = added_packages(parse_uv_lock(before or ""), parse_uv_lock(after or ""))
    now = datetime.now(timezone.utc)
    lines = []
    for package, what in changes:
        dates = pypi_dates(apis["pypi"], package)
        detail = (
            f"{what} ; paquet publié le {dates.package:%Y-%m-%d} ({(now - dates.package).days} j)"
            f" ; version publiée le {dates.version:%Y-%m-%d} ({(now - dates.version).days} j)"
            f" ; seuil {threshold} j"
        )
        status = "YOUNG" if now - dates.version < timedelta(days=threshold) else "OLD"
        lines.append(f"{status}\t{path}\t{package.name} {package.version}\t{detail}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--base", required=True, help="the git ref the PR starts from")
    parser.add_argument("--head", required=True, help="the git ref of the PR's head")
    parser.add_argument("--root", default=".", help="a clone of the project (default: the current directory)")
    parser.add_argument("--usine", help="the usine.md to read (default: docs/agents/usine.md under --root)")
    parser.add_argument(
        "--registry", action="append", default=[], metavar="ECOSYSTEM=URL",
        help="the API root of an ecosystem's registry, for a mirror or a simulated registry",
    )
    args = parser.parse_args(argv)
    config_file = Path(args.usine) if args.usine else Path(args.root) / usine.CONFIG_PATH
    try:
        config = usine.parse(config_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        config = {}
    except (OSError, UnicodeDecodeError) as error:
        print(f"lockfile_age: {error}", file=sys.stderr)
        return 2
    if not config.get(LOCKFILE_KEY):
        print(f"sans objet (clé {LOCKFILE_KEY} absente)")
        return 0
    if not config.get(AGE_KEY):
        print(f"sans objet (clé {AGE_KEY} absente)")
        return 0
    apis = dict(DEFAULT_REGISTRIES)
    for override in args.registry:
        ecosystem, _, url = override.partition("=")
        apis[ecosystem] = url
    threshold = int(config[AGE_KEY][0])
    lines: list[str] = []
    for entry in config[LOCKFILE_KEY]:
        lines += evaluate(Path(args.root), entry, args.base, args.head, apis, threshold)
    for line in lines:
        print(line)
    return 1 if any(line.startswith("YOUNG\t") for line in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
