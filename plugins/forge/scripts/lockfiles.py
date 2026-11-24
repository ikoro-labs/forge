"""Read the packages a lockfile lists, at a git ref, without judging them.

The reading `lockfile_age.py` and `stack_check.py` share: `parse_uv_lock` (a `uv.lock`),
`parse_package_lock` (a `package-lock.json`, lockfileVersion 2 or 3) and `read_at` (a file at a
ref, by `git show`). A package that does not come from the public registry keeps its `origin`.
The standard library only.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    origin: str | None = None  # where it comes from when that is not the public registry


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
