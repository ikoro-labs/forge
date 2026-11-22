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
import http.client
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
    origin: str | None = None  # where it comes from when that is not the public registry


@dataclass(frozen=True)
class Dates:
    package: datetime  # the first publication of the package
    version: datetime  # the publication of the version


class NotFound(Exception):
    """The registry answered, and has no such package or version."""


class Unreachable(Exception):
    """The registry did not give an answer that says anything about the package."""

    def __init__(self, reason: str, connection: bool = False) -> None:
        super().__init__(reason)
        self.connection = connection  # nobody answered at all: the other packages are not asked


def _quoted(value: str) -> str | None:
    match = re.search(r'"([^"]*)"', value)
    return match.group(1) if match else None


PUBLIC_INDEX = "https://pypi.org/simple"
PUBLIC_TARBALLS = "https://registry.npmjs.org/"
LOCAL_SOURCES = ("virtual", "editable", "directory", "path")  # the project's own code, not a download


def parse_uv_lock(text: str) -> list[Package]:
    """The `[[package]]` blocks of a `uv.lock` that are downloaded; ValueError when it is not one."""
    if not re.search(r"(?m)^version\s*=\s*[0-9]+\s*$", text):
        raise ValueError("pas de ligne `version = <n>` en tête : ce n'est pas un uv.lock")
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
        name, version, source = _quoted(block.get("name", "")), _quoted(block.get("version", "")), block.get("source")
        if name is None or version is None or source is None:
            raise ValueError("un bloc [[package]] sans name, version ou source : ce n'est pas un uv.lock")
        if re.match(rf"^\{{\s*({'|'.join(LOCAL_SOURCES)})\s*=", source):
            continue
        registry = re.match(r'^\{\s*registry\s*=\s*"([^"]*)"\s*\}', source)
        public = registry is not None and registry.group(1).rstrip("/") == PUBLIC_INDEX
        packages.append(Package(re.sub(r"[-_.]+", "-", name).lower(), version, None if public else source.strip()))
    return packages


def parse_package_lock(text: str) -> list[Package]:
    """The `packages` of a `package-lock.json` (lockfileVersion 2 or 3) that are downloaded."""
    entries = json.loads(text)["packages"]
    packages = []
    for key, entry in entries.items():
        if "node_modules/" not in key or entry.get("link") or entry.get("inBundle"):
            continue  # the root project, a workspace folder, a link or a package inside another's tarball
        name = entry.get("name") or key.rsplit("node_modules/", 1)[1]
        resolved = entry.get("resolved")
        public = resolved is None or str(resolved).startswith(PUBLIC_TARBALLS)
        packages.append(Package(name, entry["version"], None if public else str(resolved)))
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
    known: dict[str, set[Package]] = {}
    for package in before:
        known.setdefault(package.name, set()).add(package)
    seen: set[Package] = set()
    changes = []
    for package in after:
        if package in seen or package in known.get(package.name, set()):
            continue
        seen.add(package)
        old = known.get(package.name, set())
        if not old:
            changes.append((package, "ajouté"))
        elif package.version in {previous.version for previous in old}:
            changes.append((package, f"source changée (version {package.version} déjà dans le lockfile de base)"))
        else:
            changes.append((package, f"version {', '.join(sorted(p.version for p in old))} -> {package.version}"))
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


def fetch_json(url: str) -> Any:
    """The JSON document at `url`: NotFound on a 404, Unreachable on anything else that is not JSON."""
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "forge-lockfile-age"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise NotFound("paquet introuvable sur le registre") from error
        raise Unreachable(f"le registre répond HTTP {error.code}") from error
    except (OSError, http.client.HTTPException) as error:
        reason = getattr(error, "reason", None) or error
        raise Unreachable(str(reason), connection=True) from error
    except ValueError as error:  # includes a body that is not UTF-8 or not JSON
        raise Unreachable("réponse illisible") from error


def pypi_url(api: str, package: Package) -> str:
    return f"{api.rstrip('/')}/{package.name}/json"


def pypi_dates(document: Any, package: Package) -> Dates:
    """The dates of `package` in a PyPI JSON document (`releases`, each file with its upload time)."""
    try:
        published = {
            version: [parse_time(file["upload_time_iso_8601"]) for file in files]
            for version, files in document["releases"].items()
        }
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise Unreachable("réponse inattendue du registre") from error
    if not published.get(package.version):
        raise NotFound("version introuvable sur le registre")
    return Dates(min(time for times in published.values() for time in times), min(published[package.version]))


def npm_url(api: str, package: Package) -> str:
    return f"{api.rstrip('/')}/{package.name.replace('/', '%2F')}"


def npm_dates(document: Any, package: Package) -> Dates:
    """The dates of `package` in an npm document (`time`: `created`, then one time per version)."""
    try:
        times = document["time"]
        created = parse_time(times["created"])
        published = parse_time(times[package.version]) if package.version in times else None
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise Unreachable("réponse inattendue du registre") from error
    if published is None:
        raise NotFound("version introuvable sur le registre")
    return Dates(min(created, published), published)


@dataclass(frozen=True)
class Ecosystem:
    parse: Callable[[str], list[Package]]
    url: Callable[[str, Package], str]
    dates: Callable[[Any, Package], Dates]


ECOSYSTEMS = {
    "pypi": Ecosystem(parse_uv_lock, pypi_url, pypi_dates),
    "npm": Ecosystem(parse_package_lock, npm_url, npm_dates),
}


def invalid(subject: str, why: str) -> str:
    return f"INVALID\t{subject}\t-\t{why}"


def evaluate(root: Path, entry: str, base: str, head: str, apis: dict[str, str], threshold: int) -> list[str]:
    parts = usine.split_value(entry, 2)
    if parts is None:
        return [invalid(entry, f"il manque une partie à l'entrée de la clé {LOCKFILE_KEY} : `<chemin> | <écosystème>`")]
    path, name = parts
    if name not in ECOSYSTEMS:
        return [invalid(path, f"écosystème inconnu `{name}` ({', '.join(ECOSYSTEMS)})")]
    ecosystem = ECOSYSTEMS[name]
    try:
        before, after = read_at(root, base, path), read_at(root, head, path)
        changes = added_packages(ecosystem.parse(before) if before else [], ecosystem.parse(after) if after else [])
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        return [invalid(path, f"illisible comme un lockfile `{name}` ({type(error).__name__} : {error})")]
    if not changes:
        return [f"NONE\t{path}\t-\taucun paquet ajouté ni dont la version change"]
    now = datetime.now(timezone.utc)
    lines = []
    down: str | None = None
    for package, what in changes:
        url = ecosystem.url(apis[name], package)
        label = f"{path}\t{package.name} {package.version}"
        if package.origin is not None:
            lines.append(f"NOT CHECKED\t{label}\t{what} ; source hors du registre public : {package.origin}")
            continue
        if down is not None:
            lines.append(f"NOT RUN\t{label}\t{what} ; registre injoignable : {down} ; commande : GET {url}")
            continue
        try:
            dates = ecosystem.dates(fetch_json(url), package)
        except NotFound as error:
            lines.append(f"NOT FOUND\t{label}\t{what} ; {error} ; commande : GET {url}")
            continue
        except Unreachable as error:
            down = str(error) if error.connection else None
            lines.append(f"NOT RUN\t{label}\t{what} ; registre injoignable : {error} ; commande : GET {url}")
            continue
        detail = (
            f"{what} ; paquet publié le {dates.package:%Y-%m-%d} ({(now - dates.package).days} j)"
            f" ; version publiée le {dates.version:%Y-%m-%d} ({(now - dates.version).days} j)"
            f" ; seuil {threshold} j"
        )
        status = "YOUNG" if now - dates.version < timedelta(days=threshold) else "OLD"
        lines.append(f"{status}\t{label}\t{detail}")
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
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
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
    values = config[AGE_KEY]
    if len(values) != 1 or not re.fullmatch(r"[0-9]+", values[0]):
        print(invalid(AGE_KEY, f"un nombre entier de jours sur une seule ligne, lu : {' ; '.join(values)}"))
        return 2
    threshold = int(values[0])
    for ref in (args.base, args.head):
        found = subprocess.run(
            ["git", "-C", args.root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], capture_output=True
        )
        if found.returncode != 0:
            print(f"lockfile_age: la référence git `{ref}` est introuvable dans {args.root}", file=sys.stderr)
            return 2
    lines: list[str] = []
    for entry in config[LOCKFILE_KEY]:
        lines += evaluate(Path(args.root), entry, args.base, args.head, apis, threshold)
    for line in lines:
        print(line)
    statuses = {line.split("\t", 1)[0] for line in lines}
    if statuses & {"NOT RUN", "INVALID"}:
        return 2
    return 1 if statuses & {"YOUNG", "NOT FOUND", "NOT CHECKED"} else 0


if __name__ == "__main__":
    sys.exit(main())
