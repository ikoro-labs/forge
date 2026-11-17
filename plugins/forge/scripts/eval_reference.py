"""Measure the judge `forge:qc-conf` with the reference set of `evals/`, and launch that set under a ceiling.

    python eval_reference.py score <aggregate-result.json> [--output FILE]
    python eval_reference.py run --max-cost-usd <usd> --output-dir <dir> [--runs <n>] [--case <glob>]

The reference set is the directory `evals/` of the plugin: one case per past review, each replaying the
diff and the ticket of a pull request, with a frozen `forge:qc-gate` table, in front of the judge, and a
grader that reads the verdict line. A case named `blocker-<...>` replays a pull request with a proven
BLOCKER: the judge must return `REJECT`. A case named `faux-accept-<...>` replays a pull request that was
accepted and later proved wrong: the judge should return `REJECT`, or at least name the missing defect.
Each case of those two families carries the regex grader `rejects` (a line `VERDICT: REJECT`) on the last
message, and `no-false-accept` (no line `VERDICT: ACCEPT`) unless its missed defect was only a MINOR: such
a case (its `case.yaml` says so) has no `no-false-accept`, because a judge that accepts there may be
right, so its `ACCEPT` is not counted in `false-accept`. It is read by hand. A case named
`accept-<...>` replays a pull request that was accepted at round 1, merged and never fixed afterwards: the
judge must return `ACCEPT`. It carries `accepts` (a line `VERDICT: ACCEPT`) and `no-false-reject` (no line
`VERDICT: REJECT`).

A case named `trap-<class>-<...>` is a frozen `accept-` case in which `plant_defect.py` planted one known
defect of a class (`weakened-test`, `out-of-scope` or `unmet-criterion`): the judge must return `REJECT` and
name the defect. It carries `rejects`, `no-false-accept` and the model-graded `names-the-defect`, and it
is counted apart (see below), never in the three real shares.

`score` reads the `aggregate-result.json` that `claude plugin eval` writes, and prints the JSON that
`factory_slo.py --reference` reads:

    {"judge-recall": 0.9, "false-accept": 0.05, "false-reject": 0.1}

- `judge-recall`: the share of runs of the `blocker-` cases whose verdict is `REJECT`.
- `false-accept`: the share of runs, among those of the cases that carry `no-false-accept` (the `blocker-`
  cases and the `faux-accept-` cases with a BLOCKER-grade defect), whose verdict is `ACCEPT`. Those cases
  replay a pull request that should not have been accepted, so each `ACCEPT` is a false one. A case whose
  missed defect was only a MINOR is left out.
- `false-reject`: the share of runs of the `accept-` cases whose verdict is `REJECT`: a judge that rejects
  everything scores a perfect recall, and this share is what shows it. `factory_slo.py` reads only the
  first two keys; this one is not an objective.

These three top-level keys cover the real cases only: a trapped run never enters them. When trapped cases
ran, the JSON adds nested keys, which `factory_slo.py` does not read:

    {"judge-recall": 0.9, "false-accept": 0.05, "false-reject": 0.1,
     "real": {"judge-recall": 0.9, "false-accept": 0.05, "false-reject": 0.1},
     "trapped": {"judge-recall": 0.8, "false-accept": 0.2},
     "per-class": {"weakened-test": {"judge-recall": 0.7, "false-accept": 0.3}, ...}}

- `trapped`: the share of runs of the `trap-` cases whose verdict is `REJECT`, and the share of runs of
  those that carry `no-false-accept` whose verdict is `ACCEPT`; `per-class` gives the same two shares for
  each class that ran. Without a run of a trapped case, no nested key is written and the JSON is the one above.

A run that ended on an error is left out of every share and counted on stderr, never as a miss. A measure
with no run behind it is left out of the JSON (the SLO reads it as "sans objet"), never written as 0 or 1.
The standard library only; the eval itself is `claude plugin eval`, and no call to a model is made here
except by that command, from `run`.

`run` refuses to start without `--max-cost-usd`: a launch has a ceiling or does not happen. It runs
`claude plugin eval` on the plugin with `--scaffold` (each case copies its frozen data into the run's
folder), without the no-plugin baseline arm (`--ablation none`, which would double the cost for a number
nobody reads here) and without publishing the report, writes the results in `--output-dir` (outside the
plugin, whose files Claude Code may load as components), then scores the result into
`<output-dir>/reference.json`.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PLUGIN = Path(__file__).resolve().parents[1]
FOUND = "rejects"
ACCEPTED = "no-false-accept"
KEPT = "no-false-reject"
BLOCKER_PREFIX = "blocker-"
ACCEPT_PREFIX = "accept-"
TRAP_PREFIX = "trap-"
CLASSES = ("weakened-test", "out-of-scope", "unmet-criterion")


@dataclass
class Tally:
    """The runs of the trapped cases of one class, or of all of them: the same two shares as the real cases."""

    found: int = 0
    rejecting: int = 0
    accepted: int = 0
    runs: int = 0

    @property
    def recall(self) -> float | None:
        return self.found / self.rejecting if self.rejecting else None

    @property
    def false_accept(self) -> float | None:
        return self.accepted / self.runs if self.runs else None

    def reference(self) -> dict[str, float]:
        shares = {"judge-recall": self.recall, "false-accept": self.false_accept}
        return {name: value for name, value in shares.items() if value is not None}


@dataclass
class Measure:
    """The three shares, and the counts they come from."""

    found: int = 0
    blocker_runs: int = 0
    accepted: int = 0
    runs: int = 0
    false_rejected: int = 0
    accept_runs: int = 0
    errors: int = 0
    partial: bool = False
    trapped: Tally = field(default_factory=Tally)
    classes: dict[str, Tally] = field(default_factory=dict)

    @property
    def recall(self) -> float | None:
        return self.found / self.blocker_runs if self.blocker_runs else None

    @property
    def false_accept(self) -> float | None:
        return self.accepted / self.runs if self.runs else None

    @property
    def false_reject(self) -> float | None:
        return self.false_rejected / self.accept_runs if self.accept_runs else None

    def reference(self) -> dict[str, Any]:
        """The JSON `factory_slo.py --reference` reads, without a measure that has no run.

        The top-level keys are those of the real cases. When trapped cases ran, `real` repeats them, `trapped`
        gives the two shares of all the trapped runs and `per-class` those of each class that ran.
        """
        shares = {"judge-recall": self.recall, "false-accept": self.false_accept, "false-reject": self.false_reject}
        out: dict[str, Any] = {name: value for name, value in shares.items() if value is not None}
        trapped = self.trapped.reference()
        if trapped:
            if out:
                out["real"] = dict(out)
            out["trapped"] = trapped
            out["per-class"] = {kind: self.classes[kind].reference() for kind in CLASSES
                                if kind in self.classes and self.classes[kind].reference()}
        return out


def runs_of(case: dict[str, Any]) -> list[dict[str, Any]]:
    """The runs of a case with the plugin loaded: `arms.with` of the result file, `runs` of a bare report."""
    arms = case.get("arms")
    runs = arms.get("with") if isinstance(arms, dict) else case.get("runs")
    return [run for run in runs or [] if isinstance(run, dict)]


def grader(run: dict[str, Any], name: str) -> dict[str, Any] | None:
    for entry in run.get("graders") or []:
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry
    return None


def measure(result: dict[str, Any]) -> Measure:
    """The recall and the false accepts of one `aggregate-result.json`."""
    out = Measure(partial=bool(result.get("partial")))
    for case in result.get("cases") or []:
        if not isinstance(case, dict):
            continue
        name = str(case.get("name", ""))
        blocker = name.startswith(BLOCKER_PREFIX)
        tallies = [out.trapped]
        if name.startswith(TRAP_PREFIX):
            kind = next((kind for kind in CLASSES if name.startswith(f"{TRAP_PREFIX}{kind}-")), None)
            if kind is not None:
                tallies.append(out.classes.setdefault(kind, Tally()))
        for run in runs_of(case):
            if run.get("error"):
                out.errors += 1
                continue
            rejects = grader(run, FOUND)
            accepts = grader(run, ACCEPTED)
            kept = grader(run, KEPT)
            if name.startswith(TRAP_PREFIX):
                # A trapped run never enters the real shares: the top-level keys stay what `factory_slo.py` read.
                for tally in tallies:
                    if rejects is not None:
                        tally.rejecting += 1
                        tally.found += bool(rejects.get("passed"))
                    if accepts is not None:
                        tally.runs += 1
                        tally.accepted += not accepts.get("passed")
                continue
            if blocker and rejects is not None:
                out.blocker_runs += 1
                out.found += bool(rejects.get("passed"))
            if accepts is not None:
                out.runs += 1
                out.accepted += not accepts.get("passed")
            if kept is not None:
                out.accept_runs += 1
                out.false_rejected += not kept.get("passed")
    return out


def summary(counts: Measure) -> list[str]:
    lines = [
        f"judge-recall : {counts.found}/{counts.blocker_runs} run(s) de cas `{BLOCKER_PREFIX}` en REJECT",
        f"false-accept : {counts.accepted}/{counts.runs} run(s) en ACCEPT, cas qui portent `no-false-accept`",
    ]
    if counts.accept_runs:
        lines.append(f"false-reject : {counts.false_rejected}/{counts.accept_runs} run(s) en REJECT, cas `{ACCEPT_PREFIX}`")
    else:
        lines.append(f"false-reject : sans objet (aucun run de cas `{ACCEPT_PREFIX}`)")
    if counts.trapped.rejecting or counts.trapped.runs:
        lines.append(f"pièges : judge-recall {counts.trapped.found}/{counts.trapped.rejecting}, "
                     f"false-accept {counts.trapped.accepted}/{counts.trapped.runs} (hors des trois mesures)")
        for kind in CLASSES:
            tally = counts.classes.get(kind)
            if tally is not None and (tally.rejecting or tally.runs):
                lines.append(f"piège `{kind}` : judge-recall {tally.found}/{tally.rejecting}, "
                             f"false-accept {tally.accepted}/{tally.runs}")
    if counts.errors:
        lines.append(f"{counts.errors} run(s) en erreur, laissés hors des trois mesures")
    if counts.partial:
        lines.append("résultat partiel (plafond atteint ou arrêt) : les cas non lancés ne comptent pas")
    return lines


def score(path: Path, output: Path | None = None) -> int:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"résultat illisible : `{path}` ({error})", file=sys.stderr)
        return 2
    if not isinstance(result, dict):
        print(f"résultat illisible : `{path}` n'est pas un objet JSON", file=sys.stderr)
        return 2
    counts = measure(result)
    print("\n".join(summary(counts)), file=sys.stderr)
    reference = counts.reference()
    if not reference:
        print("sans objet : aucun run noté dans ce résultat", file=sys.stderr)
        return 1
    text = json.dumps(reference, ensure_ascii=False)
    if output is None:
        print(text)
    else:
        output.write_text(text + "\n", encoding="utf-8")
    return 0


def command(max_cost_usd: float, output_dir: Path, runs: int | None = None, case: str | None = None,
            plugin: Path = PLUGIN) -> list[str]:
    """The `claude plugin eval` command line, always under a cost ceiling."""
    if not math.isfinite(max_cost_usd) or max_cost_usd <= 0:
        raise ValueError("`--max-cost-usd` must be a positive number: a launch has a ceiling")
    plugin, output_dir = plugin.resolve(), output_dir.resolve()
    if output_dir == plugin or plugin in output_dir.parents:
        raise ValueError(f"`--output-dir` must be outside the plugin (`{plugin}`): its files may be loaded")
    argv = [
        "claude", "plugin", "eval", str(plugin), "--scaffold", "--ablation", "none", "--no-publish",
        "--max-cost-usd", f"{max_cost_usd:g}", "--output-dir", str(output_dir),
    ]
    if runs is not None:
        argv += ["--runs", str(runs)]
    if case is not None:
        argv += ["--case", case]
    return argv


def positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"`{text}` is not a number") from None
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("the ceiling must be a positive number")
    return value


def run(args: argparse.Namespace) -> int:
    try:
        argv = command(args.max_cost_usd, args.output_dir, args.runs, args.case)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print("lancement : " + " ".join(argv), file=sys.stderr)
    try:
        code = subprocess.run(argv, check=False).returncode
    except OSError as error:
        print(f"`claude` ne se lance pas : {error}", file=sys.stderr)
        return 2
    result = args.output_dir / "aggregate-result.json"
    if not result.is_file():
        print(f"pas de `aggregate-result.json` dans `{args.output_dir}` (code {code})", file=sys.stderr)
        return 2
    scored = score(result, args.output_dir / "reference.json")
    return code or scored


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the judge with the reference set.")
    commands = parser.add_subparsers(dest="command", required=True)
    scoring = commands.add_parser("score", help="read an aggregate-result.json")
    scoring.add_argument("result", type=Path)
    scoring.add_argument("--output", type=Path, help="write the JSON here instead of printing it")
    running = commands.add_parser("run", help="launch the reference set under a cost ceiling")
    running.add_argument("--max-cost-usd", type=positive_float, required=True)
    running.add_argument("--output-dir", type=Path, required=True)
    running.add_argument("--runs", type=int)
    running.add_argument("--case")
    args = parser.parse_args(argv)
    if args.command == "score":
        return score(args.result, args.output)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
