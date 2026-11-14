"""Read what the end-to-end review loop leaves behind: its matrices and its journals.

The helpers of the indicators `factory_slo.py` adds to its report (`matrix-coverage`,
`review-regressions`). Nothing here asks a model or the network: a feature is a folder of the key
`feature-dir`. The standard library only. A review opens no ticket, so no indicator reads tickets.

- A **feature** is a folder `<feature-dir>/NNNN-<slug>/`; `F-NNNN` names it by its number. Its matrix is
  `matrice.md`, its journal `revue/boucle.tsv`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import matrice  # noqa: E402

FEATURE_KEY = "feature-dir"


@dataclass(frozen=True)
class Feature:
    number: str
    matrice: Path
    journal: Path


def features(project: Path, directories: list[str]) -> list[Feature]:
    """The features under the folders of the key `feature-dir`, in the order of their numbers."""
    found: list[Feature] = []
    for directory in directories:
        for folder in sorted((project / directory).glob("[0-9]*-*")):
            number = folder.name.split("-", 1)[0]
            if folder.is_dir() and number.isdigit():
                found.append(Feature(number, folder / "matrice.md", folder / "revue" / "boucle.tsv"))
    return found


def coverage_of(found: list[Feature]) -> tuple[int, int, list[str]]:
    """Rows held (`tenu` or `écarté`), total rows, and the matrices that cannot be read, over the features."""
    held = total = 0
    unreadable: list[str] = []
    for feature in found:
        if not feature.matrice.is_file():
            continue
        try:
            rows = matrice.parse(feature.matrice.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            unreadable.append(feature.number)
            continue
        covered, count = matrice.coverage(rows)
        held, total = held + covered, total + count
    return held, total, unreadable
