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

EVALS = support.PLUGIN / "evals"
BLOCKERS = {"blocker-pr11-tour1", "blocker-pr13-tour1", "blocker-pr28-tour1", "blocker-pr30-tour1",
            "blocker-pr51-tour1"}
FALSE_ACCEPTS = {"faux-accept-pr13-tour2", "faux-accept-pr14-tour1", "faux-accept-pr23-tour1"}
# PR accepted at round 1, merged, never fixed since: the head and the base the judge saw at round 1.
ACCEPTS = {
    "accept-pr226-tour1": ("ad904b756aa76913e7a42e2d9288d386077eafd8", "d972447662d60b530d64134145a46071fe36529f"),
    "accept-pr228-tour1": ("76b372830b04f4af363a7f558e3475b5ebe25975", "0d51e8a299f7fd7bd79f9084f00261d19ad6a4b9"),
    "accept-pr238-tour1": ("be73972256e90b55101353c5c823b1f3fd3945dc", "8a6a4ce22fd5024f7488fd52b88492621fd34775"),
}
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
    make = accept_run if name.startswith("accept-") else run
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


class FalseReject(unittest.TestCase):
    """#67 A2: `false-reject`, the share of runs of the `accept-` cases that the judge rejected."""

    def test_one_of_three_accept_cases_judged_reject_counts_one_false_reject(self) -> None:
        """#67 A2.1: three `accept-` cases, one run each, one of them REJECT."""
        counts = measure(result(case("accept-a", "ACCEPT"), case("accept-b", "REJECT"), case("accept-c", "ACCEPT")))
        self.assertEqual((counts.false_rejected, counts.accept_runs), (1, 3))
        self.assertAlmostEqual(counts.reference()["false-reject"], 1 / 3)

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

    def test_the_set_holds_the_five_blockers_the_three_false_accepts_and_the_three_accepts(self) -> None:
        self.assertEqual({path.name for path in self.cases()}, BLOCKERS | FALSE_ACCEPTS | set(ACCEPTS))

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
                accepts = frontmatter(folder / "graders" / "no-false-accept.md")
                self.assertEqual((rejects["type"], rejects["match"]), ("regex", "contains"))
                self.assertEqual((accepts["type"], accepts["match"]), ("regex", "not_contains"))
                self.assertTrue((folder / "graders" / "rejects.md").read_text(encoding="utf-8").endswith(
                    "^VERDICT: REJECT\\s*$\n"))
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
                self.assertEqual(grader.is_file(), folder.name in FALSE_ACCEPTS)
                if grader.is_file():
                    self.assertEqual(frontmatter(grader)["type"], "llm")

    def test_no_file_of_the_set_has_an_em_dash(self) -> None:
        for path in sorted(EVALS.rglob("*")):
            if path.is_file():
                with self.subTest(path=str(path.relative_to(EVALS))):
                    self.assertNotIn(chr(0x2014), path.read_text(encoding="utf-8"))


class Documented(unittest.TestCase):
    """#67 point 3: the page of `docs/` gives the launch command and its ceiling."""

    def test_the_page_gives_the_command_and_the_ceiling(self) -> None:
        text = (support.REPO_ROOT / "docs" / "jeu-de-reference.md").read_text(encoding="utf-8")
        self.assertIn("eval_reference.py run --max-cost-usd", text)
        self.assertIn("--scaffold", text)
        self.assertIn("judge-recall", text)
        self.assertIn("false-accept", text)

    def test_the_page_describes_false_reject_and_the_accept_family(self) -> None:
        """#67 A2: the third measure, the cases it reads and the graders they carry are on the page."""
        text = (support.REPO_ROOT / "docs" / "jeu-de-reference.md").read_text(encoding="utf-8")
        for word in ("false-reject", "`accept-`", "`accepts`", "`no-false-reject`"):
            self.assertIn(word, text)


if __name__ == "__main__":
    unittest.main()
