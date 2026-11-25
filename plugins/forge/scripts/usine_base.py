"""Write the configuration of the base, both files merged, for the scripts `forge:qc-gate` runs.

    python usine_base.py --base <ref> [--root DIR] <out-file>

`docs/agents/usine.md` and `docs/agents/usine-gardes.md` as `<ref>` holds them (`git ls-tree` then
`git cat-file`, never the working tree), merged by the loader's rule: the keys that bound the agent
come from the guard file, the free ones from `usine.md`, and a sensitive key left in `usine.md` is dropped
once the guard file is there (said on stderr). The result is the `usine-base.md` that the other scripts
read through `--usine`: a PR cannot lift a bound by changing the files it is judged by. A file the
ref lacks is empty. A ref or a file git cannot read refuses: exit code 2, the reason on stderr, and no
file written, so that no script goes on with half of the keys. `--root` is the clone to read (default:
the project's directory). The standard library only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import usine  # noqa: E402  hooks/ is not importable until the path insertion above


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("out", help="the file to write")
    parser.add_argument("--base", required=True, help="the git ref of the base, as `origin/<base>`")
    parser.add_argument("--root", help="the clone to read (default: the project directory)")
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else usine.project_root()
    try:
        loaded = usine.load_at(root, args.base)
        Path(args.out).write_text(usine.render(loaded.config), encoding="utf-8")
    except OSError as error:
        print(f"usine_base: {error}", file=sys.stderr)
        return 2
    for notice in loaded.notices:
        print(f"usine_base: {notice}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
