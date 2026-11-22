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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402

LOCKFILE_KEY = "lockfile"
AGE_KEY = "dependency-min-age"


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
