"""Ticket #67: the reference set that measures the judge `forge:qc-conf`, and the two measures it gives.

No test here calls a model: the result of a run is a made-up `aggregate-result.json`, and the launch of
`claude plugin eval` is replaced at the process boundary.
"""

import io
import json
import re
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import support
from eval_reference import command, main, measure
from factory_slo import reference
from plant_defect import parse_diff, plant, totals

EVALS = support.PLUGIN / "evals"
BLOCKERS = {"blocker-pr11-tour1", "blocker-pr13-tour1", "blocker-pr28-tour1", "blocker-pr30-tour1",
            "blocker-pr51-tour1"}
FALSE_ACCEPTS = {"faux-accept-pr13-tour2", "faux-accept-pr14-tour1", "faux-accept-pr23-tour1"}
# The two cases whose missed defect was only a MINOR: they carry no `no-false-accept`, so an ACCEPT there is not counted.
MINOR_ONLY = {"faux-accept-pr13-tour2", "faux-accept-pr23-tour1"}
# PR accepted at round 1, merged, never fixed since: the head and the base the judge saw at round 1.
ACCEPTS = {
    "accept-pr226-tour1": ("ad904b756aa76913e7a42e2d9288d386077eafd8", "d972447662d60b530d64134145a46071fe36529f"),
    "accept-pr228-tour1": ("76b372830b04f4af363a7f558e3475b5ebe25975", "0d51e8a299f7fd7bd79f9084f00261d19ad6a4b9"),
    "accept-pr238-tour1": ("be73972256e90b55101353c5c823b1f3fd3945dc", "8a6a4ce22fd5024f7488fd52b88492621fd34775"),
}
# Ticket #154: the trapped cases, three per class, each built on a frozen `accept-` case by `plant_defect.py`.
TRAPS = {
    "weakened-test": ("trap-weakened-test-pr238-label", "trap-weakened-test-pr228-sha",
                      "trap-weakened-test-pr228-keywords"),
    "out-of-scope": ("trap-out-of-scope-pr226-rule", "trap-out-of-scope-pr228-threshold",
                     "trap-out-of-scope-pr238-test-rule"),
    "unmet-criterion": ("trap-unmet-criterion-pr226-sev3", "trap-unmet-criterion-pr228-fail-open",
                        "trap-unmet-criterion-pr238-attention"),
}
TRAPPED = {name for names in TRAPS.values() for name in names}
SPECS = support.PLUGIN / "eval-traps"
FIXTURES = ("ticket.txt", "pr-body.txt", "pr.diff", "gate.txt", "claude.txt", "rules-forge.txt",
            "rules-git.txt", "usine.txt")


def run(verdict: str | None, error: str | None = None) -> dict[str, Any]:
    """One run of a case, as `aggregate-result.json` holds it: the two graders on the verdict line."""
    return {
        "score": 0.0, "error": error, "costUsd": 0.5,
        "graders": [] if error else [
            {"name": "rejects", "passed": verdict == "REJECT", "weight": 1, "explanation": "", "withOnly": False},
            {"name": "no-false-accept", "passed": verdict != "ACCEPT", "weight": 1, "explanation": "",
             "withOnly": False},
        ],
    }


def minor_run(verdict: str | None, error: str | None = None) -> dict[str, Any]:
    """One run of a case whose missed defect was a MINOR: the `rejects` grader only, no `no-false-accept`."""
    return {
        "score": 0.0, "error": error, "costUsd": 0.5,
        "graders": [] if error else [{"name": "rejects", "passed": verdict == "REJECT", "weight": 1, "explanation": "",
                     "withOnly": False}],
    }


def accept_run(verdict: str | None, error: str | None = None) -> dict[str, Any]:
    """One run of an `accept-` case: `accepts` (a line `VERDICT: ACCEPT`) and `no-false-reject`."""
    return {
        "score": 0.0, "error": error, "costUsd": 0.5,
        "graders": [] if error else [
            {"name": "accepts", "passed": verdict == "ACCEPT", "weight": 1, "explanation": "", "withOnly": False},
            {"name": "no-false-reject", "passed": verdict != "REJECT", "weight": 1, "explanation": "",
             "withOnly": False},
        ],
    }


def case(name: str, *verdicts: str | None, error: str | None = None) -> dict[str, Any]:
    make = accept_run if name.startswith("accept-") else minor_run if "-minor" in name else run
    return {"name": name, "arms": {"with": [make(v, error) for v in verdicts]}}


def result(*cases: dict[str, Any], partial: bool = False) -> dict[str, Any]:
    return {"schemaVersion": 1, "partial": partial, "cases": list(cases)}


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    head = text.split("---\n", 2)[1]
    return dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)


class Measures(unittest.TestCase):
    """#67 point 1: `judge-recall` and `false-accept` from a made-up result (ticket #67)."""

    def made_up(self) -> dict[str, Any]:
        return result(
            case("blocker-a", "REJECT", "REJECT", "ACCEPT"),
            case("blocker-b", "REJECT", "REJECT", "REJECT"),
            case("faux-accept-c", "REJECT", "ACCEPT", "ACCEPT"),
        )

    def test_recall_is_the_share_of_blocker_runs_that_returned_reject(self) -> None:
        # 6 runs of `blocker-` cases, 5 of them REJECT.
        self.assertAlmostEqual(measure(self.made_up()).reference()["judge-recall"], 5 / 6)

    def test_false_accept_is_the_share_of_all_runs_that_returned_accept(self) -> None:
        # 9 runs in all, 3 ACCEPT (one in `blocker-a`, two in `faux-accept-c`).
        self.assertAlmostEqual(measure(self.made_up()).reference()["false-accept"], 3 / 9)

    def test_a_run_without_a_verdict_is_a_miss_but_not_a_false_accept(self) -> None:
        counts = measure(result(case("blocker-a", None, "REJECT")))
        self.assertEqual(counts.reference(), {"judge-recall": 0.5, "false-accept": 0.0})

    def test_a_run_in_error_is_left_out_of_both_shares_and_counted(self) -> None:
        counts = measure(result(case("blocker-a", "REJECT", "REJECT"), case("blocker-b", None, error="API error")))
        self.assertEqual(counts.reference(), {"judge-recall": 1.0, "false-accept": 0.0})
        self.assertEqual(counts.errors, 1)

    def test_a_measure_with_no_run_behind_it_is_left_out(self) -> None:
        """Without a `blocker-` case there is no recall: "sans objet", never 0 and never 1."""
        self.assertEqual(measure(result(case("faux-accept-c", "ACCEPT"))).reference(), {"false-accept": 1.0})
        self.assertEqual(measure(result()).reference(), {})

    def test_a_bare_report_with_runs_at_the_top_of_the_case_is_read_too(self) -> None:
        bare = {"cases": [{"name": "blocker-a", "runs": [run("REJECT"), run("ACCEPT")]}]}
        self.assertEqual(measure(bare).reference(), {"judge-recall": 0.5, "false-accept": 0.5})

    def test_the_result_says_when_it_is_partial(self) -> None:
        self.assertTrue(measure(result(case("blocker-a", "REJECT"), partial=True)).partial)


class MinorOnly(unittest.TestCase):
    """#67 part 3 A1: a case whose missed defect was only a MINOR does not count toward `false-accept`."""

    def test_a_minor_only_case_judged_accept_is_not_a_false_accept(self) -> None:
        """#67 A1.1: the ACCEPT of a MINOR-only case leaves `false-accept` at 0."""
        counts = measure(result(case("blocker-a", "REJECT", "REJECT"), case("faux-accept-c-minor", "ACCEPT", "ACCEPT")))
        self.assertEqual(counts.reference(), {"judge-recall": 1.0, "false-accept": 0.0})

    def test_a_blocker_case_judged_accept_is_still_counted(self) -> None:
        """#67 A1.2: next to a MINOR-only case judged ACCEPT, the ACCEPT of a BLOCKER case counts."""
        counts = measure(result(case("blocker-a", "ACCEPT", "REJECT"), case("faux-accept-c-minor", "ACCEPT")))
        self.assertEqual((counts.accepted, counts.runs), (1, 2))
        self.assertAlmostEqual(counts.reference()["false-accept"], 0.5)

    def test_a_blocker_faux_accept_case_judged_accept_is_still_counted(self) -> None:
        """#67 A1.2: a `faux-accept-` case that carries `no-false-accept` keeps counting."""
        counts = measure(result(case("faux-accept-d", "ACCEPT", "REJECT"), case("faux-accept-c-minor", "ACCEPT")))
        self.assertEqual(counts.reference(), {"false-accept": 0.5})

    def test_only_a_minor_only_case_leaves_false_accept_without_a_measure(self) -> None:
        """Without any run behind it, `false-accept` is "sans objet", never 0."""
        self.assertEqual(measure(result(case("faux-accept-c-minor", "ACCEPT"))).reference(), {})

    def test_the_two_weak_cases_carry_no_no_false_accept_grader_and_the_others_keep_it(self) -> None:
        """#67 A1: the data says it: PR 13 round 2 and PR 23 leave `false-accept`, PR 14 and the blockers stay."""
        for folder in sorted(path for path in EVALS.iterdir() if path.is_dir()):
            if folder.name in ACCEPTS:
                continue
            with self.subTest(case=folder.name):
                grader = folder / "graders" / "no-false-accept.md"
                self.assertEqual(grader.is_file(), folder.name not in MINOR_ONLY)
                self.assertTrue((folder / "graders" / "rejects.md").is_file())

    def test_the_two_weak_cases_say_in_their_description_that_they_are_left_out_of_false_accept(self) -> None:
        for name in MINOR_ONLY:
            with self.subTest(case=name):
                text = (EVALS / name / "case.yaml").read_text(encoding="utf-8")
                self.assertIn("MINOR", text)
                self.assertIn("hors de `false-accept`", text)

    def test_the_script_says_why_those_cases_leave_false_accept(self) -> None:
        import eval_reference
        doc = eval_reference.__doc__ or ""
        self.assertIn("only a MINOR", doc)
        self.assertIn("not counted in `false-accept`", doc)


class FalseReject(unittest.TestCase):
    """#67 A2: `false-reject`, the share of runs of the `accept-` cases that the judge rejected."""

    def test_one_of_three_accept_cases_judged_reject_counts_one_false_reject(self) -> None:
        """#67 A2.1: three `accept-` cases, one run each, one of them REJECT."""
        counts = measure(result(case("accept-a", "ACCEPT"), case("accept-b", "REJECT"), case("accept-c", "ACCEPT")))
        self.assertEqual((counts.false_rejected, counts.accept_runs), (1, 3))
        self.assertAlmostEqual(counts.reference()["false-reject"], 1 / 3)

    def test_the_json_holds_the_share_and_the_printed_line_the_count(self) -> None:
        """#67 part 3 A2.1: one ACCEPT case of three judged REJECT, JSON 0.333, line `1/3`."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "aggregate-result.json"
            path.write_text(json.dumps(result(case("accept-a", "ACCEPT"), case("accept-b", "REJECT"),
                                              case("accept-c", "ACCEPT"))), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                main(["score", str(path)])
        self.assertEqual(round(json.loads(out.getvalue())["false-reject"], 3), 0.333)
        self.assertIn("false-reject : 1/3", err.getvalue())

    def test_an_accept_case_judged_accept_is_not_a_false_accept(self) -> None:
        """#67 A2.1: the verdict an `accept-` case expects stays out of `false-accept`."""
        counts = measure(result(case("accept-a", "ACCEPT", "ACCEPT"), case("faux-accept-c", "REJECT")))
        self.assertEqual(counts.reference(), {"false-accept": 0.0, "false-reject": 0.0})

    def test_a_result_without_accept_cases_leaves_false_reject_out_and_says_so(self) -> None:
        """#67 A2.2: "sans objet", never 0: the key is absent and the summary names the measure."""
        counts = measure(result(case("blocker-a", "REJECT"), case("faux-accept-c", "REJECT")))
        self.assertNotIn("false-reject", counts.reference())
        self.assertIsNone(counts.false_reject)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "aggregate-result.json"
            path.write_text(json.dumps(result(case("blocker-a", "REJECT"))), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(["score", str(path)]), 0)
        self.assertNotIn("false-reject", json.loads(out.getvalue()))
        self.assertIn("false-reject : sans objet", err.getvalue())

    def test_a_run_without_a_verdict_or_in_error_is_not_a_false_reject(self) -> None:
        counts = measure(result(case("accept-a", None, "ACCEPT"), case("accept-b", None, error="API error")))
        self.assertEqual((counts.false_rejected, counts.accept_runs, counts.errors), (0, 2, 1))

    def test_the_summary_on_stderr_gives_the_false_reject_counts(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "aggregate-result.json"
            path.write_text(json.dumps(result(case("accept-a", "REJECT", "ACCEPT"))), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                main(["score", str(path)])
        self.assertIn("false-reject : 1/2", err.getvalue())
        self.assertEqual(json.loads(out.getvalue()), {"false-reject": 0.5})


class FormRead(unittest.TestCase):
    """#67 point 2: the JSON `score` prints is the one `factory_slo.py --reference` already reads."""

    def score(self, payload: Any) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "aggregate-result.json"
            path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["score", str(path)])
            return code, out.getvalue(), err.getvalue()

    def test_score_prints_the_two_keys_the_service_objectives_read(self) -> None:
        code, out, _ = self.score(result(case("blocker-a", "REJECT", "REJECT", "REJECT", "ACCEPT")))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"judge-recall": 0.75, "false-accept": 0.25})

    def test_factory_slo_reads_what_score_wrote(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "aggregate-result.json"
            source.write_text(json.dumps(result(case("blocker-a", "REJECT", "ACCEPT"))), encoding="utf-8")
            target = Path(folder) / "reference.json"
            with redirect_stderr(io.StringIO()):
                code = main(["score", str(source), "--output", str(target)])
            self.assertEqual(code, 0)
            recall, false_accept = reference("judge-recall", target), reference("false-accept", target)
        self.assertIsNone(recall.reason)
        self.assertEqual(recall.data, {"valeur": 0.5})
        self.assertEqual(recall.text, "50 %")
        self.assertEqual(false_accept.data, {"valeur": 0.5})

    def test_a_result_that_cannot_be_read_exits_2_and_prints_no_json(self) -> None:
        code, out, err = self.score("{not json")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("illisible", err)

    def test_a_result_without_any_graded_run_exits_1_and_prints_no_json(self) -> None:
        code, out, err = self.score(result())
        self.assertEqual((code, out), (1, ""))
        self.assertIn("sans objet", err)

    def test_the_summary_on_stderr_gives_the_counts(self) -> None:
        _, _, err = self.score(result(case("blocker-a", "REJECT", "ACCEPT")))
        self.assertIn("judge-recall : 1/2", err)
        self.assertIn("false-accept : 1/2", err)


class Ceiling(unittest.TestCase):
    """#67 point 3: a launch has a ceiling, or it does not happen."""

    def test_the_command_carries_the_ceiling_and_the_flags_the_set_needs(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            argv = command(7.5, Path(folder) / "out", runs=2, case="blocker-*")
        self.assertEqual(argv[:3], ["claude", "plugin", "eval"])
        self.assertEqual(argv[argv.index("--max-cost-usd") + 1], "7.5")
        self.assertEqual(argv[argv.index("--ablation") + 1], "none")
        self.assertEqual(argv[argv.index("--runs") + 1], "2")
        self.assertEqual(argv[argv.index("--case") + 1], "blocker-*")
        for flag in ("--scaffold", "--no-publish", "--output-dir"):
            self.assertIn(flag, argv)

    def test_a_ceiling_that_is_not_a_positive_number_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for bad in (0, -1, float("nan"), float("inf")):
                with self.subTest(ceiling=bad), self.assertRaises(ValueError):
                    command(bad, Path(folder))

    def test_results_inside_the_plugin_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            command(5, support.PLUGIN / "evals" / "results")

    def test_run_without_a_ceiling_does_not_start(self) -> None:
        with tempfile.TemporaryDirectory() as folder, unittest.mock.patch("subprocess.run") as spawn:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
                main(["run", "--output-dir", folder])
            self.assertEqual(stop.exception.code, 2)
            spawn.assert_not_called()

    def test_run_launches_under_the_ceiling_then_scores_the_result_it_finds(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"

            def eval_ran(argv: list[str], **_: Any) -> unittest.mock.Mock:
                (out / "aggregate-result.json").write_text(
                    json.dumps(result(case("blocker-a", "REJECT", "REJECT"))), encoding="utf-8")
                return unittest.mock.Mock(returncode=0)

            with unittest.mock.patch("subprocess.run", side_effect=eval_ran) as spawn, \
                    redirect_stderr(io.StringIO()):
                code = main(["run", "--max-cost-usd", "12", "--output-dir", str(out)])
            self.assertEqual(code, 0)
            argv = spawn.call_args.args[0]
            self.assertEqual(argv[argv.index("--max-cost-usd") + 1], "12")
            written = json.loads((out / "reference.json").read_text(encoding="utf-8"))
        self.assertEqual(written, {"judge-recall": 1.0, "false-accept": 0.0})

    def test_the_exit_code_of_a_run_that_hit_the_ceiling_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"

            def eval_stopped(argv: list[str], **_: Any) -> unittest.mock.Mock:
                (out / "aggregate-result.json").write_text(
                    json.dumps(result(case("blocker-a", "REJECT"), partial=True)), encoding="utf-8")
                return unittest.mock.Mock(returncode=2)

            with unittest.mock.patch("subprocess.run", side_effect=eval_stopped), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["run", "--max-cost-usd", "1", "--output-dir", str(out)]), 2)
            self.assertTrue((out / "reference.json").is_file())


class CaseForm(unittest.TestCase):
    """#67 point 4: every case replays a past review, in the same shape."""

    def cases(self) -> list[Path]:
        return sorted(path for path in EVALS.iterdir() if path.is_dir())

    def test_the_set_holds_the_five_blockers_the_three_false_accepts_the_three_accepts_and_the_nine_traps(self) -> None:
        self.assertEqual({path.name for path in self.cases()}, BLOCKERS | FALSE_ACCEPTS | set(ACCEPTS) | TRAPPED)

    def test_each_case_names_itself_after_its_folder_and_loads_its_frozen_data(self) -> None:
        for folder in self.cases():
            with self.subTest(case=folder.name):
                text = (folder / "case.yaml").read_text(encoding="utf-8")
                self.assertIn('schema_version: "1.0"', text)
                self.assertIn(f"\nname: {folder.name}\n", text)
                self.assertIn("scaffold_script: scaffold.sh", text)
                self.assertIn("/fixtures", (folder / "scaffold.sh").read_text(encoding="utf-8"))

    def test_each_case_has_its_fixtures_and_no_verdict_among_them(self) -> None:
        for folder in self.cases():
            for name in FIXTURES:
                with self.subTest(case=folder.name, fixture=name):
                    text = (folder / "fixtures" / name).read_text(encoding="utf-8")
                    self.assertTrue(text.strip())
                    self.assertIsNone(re.search(r"^VERDICT:", text, re.M))
                    # The grid (rules, usine) may name the section; the data of the PR must not hold its report.
                    if name in ("ticket.txt", "pr-body.txt", "gate.txt"):
                        self.assertNotIn("Rapport d'agent", text)

    def test_the_diff_is_a_diff_and_the_gate_table_a_table(self) -> None:
        for folder in self.cases():
            with self.subTest(case=folder.name):
                self.assertTrue((folder / "fixtures" / "pr.diff").read_text(encoding="utf-8").startswith("diff --git"))
                gate = (folder / "fixtures" / "gate.txt").read_text(encoding="utf-8")
                self.assertTrue(gate.startswith("| Sonde | Résultat | Détail |"))
                self.assertIn("| CI |", gate)

    def test_a_round_2_case_carries_the_blockers_of_round_1_and_the_others_do_not(self) -> None:
        for folder in self.cases():
            with self.subTest(case=folder.name):
                held = (folder / "fixtures" / "blockers-tour1.txt").is_file()
                self.assertEqual(held, folder.name.endswith("-tour2"))
                if held:
                    lines = (folder / "fixtures" / "blockers-tour1.txt").read_text(encoding="utf-8").splitlines()
                    self.assertTrue(lines and all(line.startswith("- [BLOCKER]") for line in lines))

    def test_the_prompt_asks_for_the_judge_with_read_tools_and_names_every_fixture_it_gives(self) -> None:
        for folder in self.cases():
            with self.subTest(case=folder.name):
                text = (folder / "prompt.md").read_text(encoding="utf-8")
                meta = frontmatter(folder / "prompt.md")
                self.assertIn("`forge:qc-conf`", text)
                self.assertEqual(meta["allowed_tools"], "[Agent, Read, Glob, Grep]")
                self.assertGreaterEqual(int(meta["runs"]), 3)
                for name in re.findall(r"`fixtures/([\w.-]+)`", text):
                    self.assertTrue((folder / "fixtures" / name).is_file(), name)
                for name in FIXTURES:
                    self.assertIn(f"fixtures/{name}", text)

    def test_each_case_grades_the_verdict_line_with_the_two_graders_the_script_reads(self) -> None:
        for folder in self.cases():
            if folder.name in ACCEPTS:
                continue
            with self.subTest(case=folder.name):
                self.assertFalse((folder / "graders" / "accepts.md").exists())
                rejects = frontmatter(folder / "graders" / "rejects.md")
                self.assertEqual((rejects["type"], rejects["match"]), ("regex", "contains"))
                self.assertTrue((folder / "graders" / "rejects.md").read_text(encoding="utf-8").endswith(
                    "^VERDICT: REJECT\\s*$\n"))
                if folder.name in MINOR_ONLY:
                    continue
                accepts = frontmatter(folder / "graders" / "no-false-accept.md")
                self.assertEqual((accepts["type"], accepts["match"]), ("regex", "not_contains"))
                self.assertTrue((folder / "graders" / "no-false-accept.md").read_text(encoding="utf-8").endswith(
                    "^VERDICT: ACCEPT\\s*$\n"))

    def test_a_case_expecting_accept_grades_the_verdict_line_with_the_inverse_graders(self) -> None:
        """#67 A1.1: `accepts` and `no-false-reject`, and neither grader of the REJECT families."""
        for name in ACCEPTS:
            folder = EVALS / name
            with self.subTest(case=name):
                accepts = frontmatter(folder / "graders" / "accepts.md")
                kept = frontmatter(folder / "graders" / "no-false-reject.md")
                self.assertEqual((accepts["type"], accepts["match"]), ("regex", "contains"))
                self.assertEqual((kept["type"], kept["match"]), ("regex", "not_contains"))
                self.assertTrue((folder / "graders" / "accepts.md").read_text(encoding="utf-8").endswith(
                    "^VERDICT: ACCEPT\\s*$\n"))
                self.assertTrue((folder / "graders" / "no-false-reject.md").read_text(encoding="utf-8").endswith(
                    "^VERDICT: REJECT\\s*$\n"))
                self.assertEqual(sorted(path.name for path in (folder / "graders").iterdir()),
                                 ["accepts.md", "no-false-reject.md"])

    def test_a_case_expecting_accept_says_so_and_replays_the_head_the_judge_saw_at_round_1(self) -> None:
        """#67 A1.1: the description gives the expected verdict, the prompt the head and the base of round 1."""
        for name, (head, base) in ACCEPTS.items():
            folder = EVALS / name
            with self.subTest(case=name):
                description = next(line for line in (folder / "case.yaml").read_text(encoding="utf-8").splitlines()
                                   if line.startswith("description:"))
                self.assertIn("Verdict attendu, ACCEPT", description)
                prompt = (folder / "prompt.md").read_text(encoding="utf-8")
                self.assertIn(f"La PR {name.split('-pr')[1].split('-')[0]} est jugée au tour 1", prompt)
                self.assertIn(f"`{head}`", prompt)
                self.assertIn(f"`{base}`", prompt)

    def test_a_false_accept_case_also_names_the_defect_the_judge_missed(self) -> None:
        for folder in self.cases():
            with self.subTest(case=folder.name):
                grader = folder / "graders" / "names-the-defect.md"
                self.assertEqual(grader.is_file(), folder.name in FALSE_ACCEPTS | TRAPPED)
                if grader.is_file():
                    self.assertEqual(frontmatter(grader)["type"], "llm")

    def test_no_file_of_the_set_has_an_em_dash(self) -> None:
        for path in sorted(EVALS.rglob("*")):
            if path.is_file():
                with self.subTest(path=str(path.relative_to(EVALS))):
                    self.assertNotIn(chr(0x2014), path.read_text(encoding="utf-8"))


class TrappedCases(unittest.TestCase):
    """#154 A1: three trapped cases per class, built on the frozen `accept-` cases, expecting REJECT and the defect."""

    def test_each_class_has_three_cases_that_expect_reject_and_name_the_defect(self) -> None:
        """#154 A1.1: the graders `rejects`, `no-false-accept` and `names-the-defect`, and no grader of the accept family."""
        for kind, names in TRAPS.items():
            self.assertGreaterEqual(len(names), 3)
            self.assertEqual({path.name for path in EVALS.glob(f"trap-{kind}-*")}, set(names))
            for name in names:
                folder = EVALS / name
                with self.subTest(case=name):
                    self.assertEqual(sorted(path.name for path in (folder / "graders").iterdir()),
                                     ["names-the-defect.md", "no-false-accept.md", "rejects.md"])
                    blocker = EVALS / "blocker-pr11-tour1" / "graders"
                    for grader in ("rejects.md", "no-false-accept.md"):
                        self.assertEqual((folder / "graders" / grader).read_bytes(), (blocker / grader).read_bytes())
                    names_it = frontmatter(folder / "graders" / "names-the-defect.md")
                    self.assertEqual((names_it["type"], names_it["weight"]), ("llm", "0.5"))
                    body = (folder / "graders" / "names-the-defect.md").read_text(encoding="utf-8").split("---\n", 2)[2]
                    self.assertTrue(body.strip())

    def test_each_case_is_built_on_a_frozen_accept_case_and_says_which_class_it_plants(self) -> None:
        for kind, names in TRAPS.items():
            for name in names:
                with self.subTest(case=name):
                    spec = json.loads((SPECS / f"{name}.json").read_text(encoding="utf-8"))
                    self.assertEqual((spec["name"], spec["class"]), (name, kind))
                    self.assertIn(spec["source"], ACCEPTS)
                    text = (EVALS / name / "case.yaml").read_text(encoding="utf-8")
                    self.assertIn(f"\nname: {name}\n", text)
                    self.assertIn(f"piégée ({kind})", text)
                    self.assertIn("Verdict attendu, REJECT", text)
                    self.assertIn(f"tags: [trap, {kind}, juge]", text)

    def test_each_case_is_what_its_spec_plants_byte_for_byte(self) -> None:
        """#154 A2.4: the committed case is the output of its spec, so a spec cannot drift from its case."""
        with tempfile.TemporaryDirectory() as folder:
            for name in sorted(TRAPPED):
                with self.subTest(case=name):
                    spec = json.loads((SPECS / f"{name}.json").read_text(encoding="utf-8"))
                    planted = plant(spec, EVALS, Path(folder))
                    committed = EVALS / name
                    files = sorted(path.relative_to(committed) for path in committed.rglob("*") if path.is_file())
                    self.assertEqual(files, sorted(path.relative_to(planted) for path in planted.rglob("*")
                                                   if path.is_file()))
                    for relative in files:
                        self.assertEqual((committed / relative).read_bytes(), (planted / relative).read_bytes(),
                                         str(relative))

    def test_each_case_differs_from_its_source_in_the_diff_and_at_most_the_gate_table(self) -> None:
        for names in TRAPS.values():
            for name in names:
                with self.subTest(case=name):
                    spec = json.loads((SPECS / f"{name}.json").read_text(encoding="utf-8"))
                    source, case = EVALS / spec["source"], EVALS / name
                    for fixture in FIXTURES:
                        same = (source / "fixtures" / fixture).read_bytes() == (case / "fixtures" / fixture).read_bytes()
                        if fixture == "pr.diff":
                            self.assertFalse(same, fixture)
                        elif fixture != "gate.txt":  # the gate table moves only when the counts or the files do
                            self.assertTrue(same, fixture)
                    self.assertEqual((source / "prompt.md").read_bytes(), (case / "prompt.md").read_bytes())
                    diff = (case / "fixtures" / "pr.diff").read_text(encoding="utf-8")
                    files, added, removed = totals(parse_diff(diff))
                    gate = (case / "fixtures" / "gate.txt").read_text(encoding="utf-8")
                    self.assertIn(f"| Base et diff | {files} fichier(s) dans pr.diff, +{added} -{removed} |", gate)


class TrappedMeasures(unittest.TestCase):
    """#154 A3: the top-level keys keep reading real cases only; trapped and per-class figures are nested."""

    def real(self) -> list[dict[str, Any]]:
        # 3 blocker runs (1 ACCEPT) and 2 accept runs (1 REJECT): recall 2/3, false-accept 1/3, false-reject 1/2.
        return [case("blocker-a", "REJECT", "REJECT", "ACCEPT"), case("accept-b", "ACCEPT", "REJECT")]

    def trapped(self) -> list[dict[str, Any]]:
        return [case("trap-weakened-test-pr1-a", "REJECT", "ACCEPT"), case("trap-out-of-scope-pr2-b", "ACCEPT", "ACCEPT"),
                case("trap-unmet-criterion-pr3-c", "REJECT", "REJECT")]

    def test_the_top_level_keys_cover_real_cases_only(self) -> None:
        """#154 A3.1: trapped runs, which carry the same graders, leave the keys `factory_slo.py` reads unchanged."""
        both = measure(result(*self.real(), *self.trapped())).reference()
        real = measure(result(*self.real())).reference()
        self.assertEqual({key: both[key] for key in ("judge-recall", "false-accept", "false-reject")}, real)
        self.assertAlmostEqual(both["judge-recall"], 2 / 3)
        self.assertAlmostEqual(both["false-accept"], 1 / 3)
        self.assertAlmostEqual(both["false-reject"], 1 / 2)

    def test_the_nested_keys_give_real_trapped_and_per_class_recall_and_false_accept(self) -> None:
        """#154 A3.2: 6 trapped runs, 3 REJECT and 3 ACCEPT; per class 1/2, 0 and 1 for the recall."""
        both = measure(result(*self.real(), *self.trapped())).reference()
        self.assertEqual(set(both), {"judge-recall", "false-accept", "false-reject", "real", "trapped", "per-class"})
        self.assertEqual(both["real"], {key: both[key] for key in ("judge-recall", "false-accept", "false-reject")})
        self.assertEqual(both["trapped"], {"judge-recall": 0.5, "false-accept": 0.5})
        self.assertEqual(both["per-class"], {
            "weakened-test": {"judge-recall": 0.5, "false-accept": 0.5},
            "out-of-scope": {"judge-recall": 0.0, "false-accept": 1.0},
            "unmet-criterion": {"judge-recall": 1.0, "false-accept": 0.0},
        })

    def test_a_result_without_trapped_runs_keeps_the_top_level_keys_as_they_were(self) -> None:
        """#154 A3.3: no nested key at all, the JSON of #67 as it was."""
        self.assertEqual(measure(result(*self.real())).reference(),
                         {"judge-recall": 2 / 3, "false-accept": 1 / 3, "false-reject": 1 / 2})
        only_errors = measure(result(case("trap-weakened-test-x", None, error="API error")))
        self.assertEqual(only_errors.reference(), {})

    def test_a_trapped_case_judged_accept_is_not_counted_in_the_real_false_accept(self) -> None:
        counts = measure(result(case("blocker-a", "REJECT"), case("trap-out-of-scope-x", "ACCEPT", "ACCEPT")))
        self.assertEqual((counts.reference()["false-accept"], counts.reference()["trapped"]["false-accept"]), (0.0, 1.0))

    def test_a_run_in_error_is_left_out_of_the_trapped_shares_and_counted(self) -> None:
        counts = measure(result(case("trap-weakened-test-x", "REJECT"), case("trap-weakened-test-y", None, error="boom")))
        self.assertEqual(counts.reference()["per-class"], {"weakened-test": {"judge-recall": 1.0, "false-accept": 0.0}})
        self.assertEqual(counts.errors, 1)

    def test_a_class_with_no_run_is_left_out_and_an_unknown_class_counts_only_as_trapped(self) -> None:
        counts = measure(result(case("trap-unmet-criterion-x", "REJECT"), case("trap-mystery-y", "ACCEPT")))
        reference = counts.reference()
        self.assertEqual(list(reference["per-class"]), ["unmet-criterion"])
        self.assertEqual(reference["trapped"], {"judge-recall": 0.5, "false-accept": 0.5})

    def test_score_prints_the_nested_figures_and_factory_slo_still_reads_the_top_level_ones(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "aggregate-result.json", Path(folder) / "reference.json"
            source.write_text(json.dumps(result(*self.real(), *self.trapped())), encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(main(["score", str(source), "--output", str(target)]), 0)
            recall, false_accept = reference("judge-recall", target), reference("false-accept", target)
            written = json.loads(target.read_text(encoding="utf-8"))
        self.assertAlmostEqual(recall.data["valeur"], 2 / 3)
        self.assertAlmostEqual(false_accept.data["valeur"], 1 / 3)
        self.assertEqual(written["per-class"]["out-of-scope"], {"judge-recall": 0.0, "false-accept": 1.0})
        self.assertIn("pièges : judge-recall 3/6", err.getvalue())
        self.assertIn("piège `out-of-scope` : judge-recall 0/2", err.getvalue())


class Documented(unittest.TestCase):
    def page(self) -> str:
        return (support.REPO_ROOT / "docs" / "jeu-de-reference.md").read_text(encoding="utf-8")

    def test_the_page_says_the_two_weak_cases_leave_false_accept_and_why(self) -> None:
        """#67 part 3 A1: the page states the rule and no longer claims every ACCEPT of a `faux-accept-` case counts."""
        text = self.page()
        self.assertIn("hors de `false-accept`", text)
        self.assertIn("PR 13 au tour 2 et de la PR 23", text)
        self.assertNotIn("des cas `blocker-` et `faux-accept-` dont le verdict est `ACCEPT`", text)

    def test_the_page_says_the_json_key_is_a_share_and_the_printed_line_a_count(self) -> None:
        """#67 part 3 A2: `false-reject` is 0.333 in the JSON and `1/3` on the line."""
        text = self.page()
        self.assertIn("0.333", text)
        self.assertIn("`1/3`", text)

    def test_the_page_states_whether_the_eval_command_exists_in_the_version_the_ci_pins(self) -> None:
        """#67 part 3 A3: the pinned version, how it was checked, and that no case was run there."""
        workflow = (support.REPO_ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        pinned = re.search(r"claude-code@([\d.]+)", workflow)
        self.assertIsNotNone(pinned)
        assert pinned is not None
        text = self.page()
        self.assertIn(f"`claude plugin eval` existe dans la version {pinned.group(1)}", text)
        self.assertIn("plugin eval --help", text)
    """#67 point 3: the page of `docs/` gives the launch command and its ceiling."""

    def test_the_page_gives_the_command_and_the_ceiling(self) -> None:
        text = (support.REPO_ROOT / "docs" / "jeu-de-reference.md").read_text(encoding="utf-8")
        self.assertIn("eval_reference.py run --max-cost-usd", text)
        self.assertIn("--scaffold", text)
        self.assertIn("judge-recall", text)
        self.assertIn("false-accept", text)

    def test_the_page_counts_eleven_cases_and_names_the_three_accept_prs(self) -> None:
        """#67 A1: the table of the page lists the `accept-` cases and the README summary counts the set."""
        text = (support.REPO_ROOT / "docs" / "jeu-de-reference.md").read_text(encoding="utf-8")
        self.assertIn("## Les onze cas", text)
        self.assertIn("| `accept-` | PR 226, 228 et 238, au tour 1 |", text)
        self.assertNotIn("huit", text)
        readme = (support.REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("les onze revues rejouées, les trois mesures", readme)

    def test_the_page_describes_false_reject_and_the_accept_family(self) -> None:
        """#67 A2: the third measure, the cases it reads and the graders they carry are on the page."""
        text = (support.REPO_ROOT / "docs" / "jeu-de-reference.md").read_text(encoding="utf-8")
        for word in ("false-reject", "`accept-`", "`accepts`", "`no-false-reject`"):
            self.assertIn(word, text)


if __name__ == "__main__":
    unittest.main()
