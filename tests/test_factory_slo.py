"""factory_slo.py: the SLI of the factory, on fake `gh` answers and throwaway git repositories."""

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest import mock

import support
from factory_slo import (
    Factory,
    compute,
    lead_time,
    main,
    percentile,
    release_lag,
    restore_time,
    run_command,
)
from test_token_audit import line

SINCE = datetime(2026, 10, 1, tzinfo=timezone.utc)
UNTIL = datetime(2026, 11, 1, tzinfo=timezone.utc)
USINE = """# Usine

- `release-tag` : `forge--v{version}`
- `required-contexts` : `tests`
- `protected-path` : `.github/`
"""


def isolate(case: unittest.TestCase, folder: str, **extra: str) -> None:
    """Pose `HOME`, `USERPROFILE` et git sans configuration, retire les `CLAUDE_` de la session lanceuse.

    `os.environ` est remplacé pour la durée du test : les `git` du runner et les sous-processus
    l'héritent, et le vrai `~/.claude` comme le vrai `~/.gitconfig` ne sont jamais lus.
    """
    env = {"HOME": folder, "USERPROFILE": folder, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, **extra}
    patcher = mock.patch.dict(os.environ, env)
    patcher.start()
    case.addCleanup(patcher.stop)
    for key in [name for name in os.environ if name.startswith("CLAUDE_") and name not in extra]:
        del os.environ[key]


def verdict(round_: int, result: str, when: str) -> dict:
    body = f"VERDICT: {result}\nROUND: {round_}\nHEAD: abcdef1\nSPEC: #1: 1 criteria covered\nFINDINGS:\n- none\nGATES: ok"
    return {"body": body, "createdAt": when}


def pr(number: int, created: str, **extra) -> dict:
    base = {
        "number": number, "title": f"PR {number}", "body": "", "state": "OPEN",
        "createdAt": created, "mergedAt": None, "closedAt": None, "labels": [],
        "mergeCommit": None, "closingIssuesReferences": [], "comments": [],
    }
    base.update(extra)
    return base


def issue(number: int, created: str, labels: tuple[str, ...] = (), body: str = "") -> dict:
    return {
        "number": number, "title": f"Ticket {number}", "body": body, "state": "OPEN",
        "createdAt": created, "closedAt": None, "labels": [{"name": name} for name in labels],
    }


def event(label: str, when: str) -> dict:
    return {"event": "labeled", "label": {"name": label}, "created_at": when}


class World:
    """A git repository on `main` and the GitHub answers that describe it."""

    def __init__(self, folder: Path) -> None:
        self.root = folder / "projet"
        self.root.mkdir()
        self.env = {
            **os.environ,
            "HOME": str(folder), "USERPROFILE": str(folder),
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
        }
        for key in [name for name in self.env if name.startswith("CLAUDE_")]:
            del self.env[key]
        self.git("init", "-q", "-b", "main")
        (self.root / "docs" / "agents").mkdir(parents=True)
        (self.root / "docs" / "agents" / "usine.md").write_text(USINE, encoding="utf-8")
        self.answers: dict[str, Any] = {}
        self.count = 0

    def git(self, *args: str, when: str | None = None) -> str:
        env = dict(self.env)
        if when:
            env.update(GIT_COMMITTER_DATE=when, GIT_AUTHOR_DATE=when)
        done = subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=self.root, env=env, capture_output=True, text=True, check=True,
        )
        return done.stdout.strip()

    def commit(self, message: str, when: str) -> str:
        self.count += 1
        (self.root / f"f{self.count}.txt").write_text(str(self.count), encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message, when=when)
        return self.git("rev-parse", "HEAD")

    def runner(self, cmd: list[str], cwd: Path) -> str:
        if cmd[0] != "gh":
            return run_command(cmd, cwd)
        key = " ".join(cmd[1:])
        for prefix, answer in self.answers.items():
            if key.startswith(prefix):
                return answer if isinstance(answer, str) else json.dumps(answer)
        raise AssertionError(f"unexpected gh call: {key}")


def build(folder: Path) -> World:
    world = World(folder)
    c0 = world.commit("avant", "2026-09-20T10:00:00Z")
    c1 = world.commit("feat: un", "2026-10-03T10:00:00Z")
    c2 = world.commit("feat: deux", "2026-10-06T10:00:00Z")
    world.git("tag", "-a", "-m", "v", "forge--v1.0.0", c2, when="2026-10-08T00:00:00Z")
    world.git("tag", "-a", "-m", "v", "autre-v9", c1, when="2026-10-04T00:00:00Z")
    c3 = world.commit("fix: trois", "2026-10-12T00:00:00Z")
    c4 = world.commit(f"Revert deux\n\nThis reverts commit {c2}.", "2026-10-15T00:00:00Z")
    prs = [
        pr(9, "2026-09-19T00:00:00Z", state="MERGED", mergedAt="2026-09-20T10:00:00Z",
           mergeCommit={"oid": c0}, comments=[verdict(1, "ACCEPT", "2026-09-19T12:00:00Z")]),
        pr(10, "2026-10-02T00:00:00Z", state="MERGED", mergedAt="2026-10-03T10:00:00Z",
           mergeCommit={"oid": c1}, closingIssuesReferences=[{"number": 1}],
           comments=[verdict(1, "ACCEPT", "2026-10-02T12:00:00Z")]),
        pr(11, "2026-10-05T00:00:00Z", state="MERGED", mergedAt="2026-10-06T10:00:00Z",
           mergeCommit={"oid": c2}, closingIssuesReferences=[{"number": 2}],
           comments=[verdict(1, "REJECT", "2026-10-05T12:00:00Z"), verdict(2, "ACCEPT", "2026-10-06T08:00:00Z")]),
        pr(12, "2026-10-07T00:00:00Z", state="CLOSED", closedAt="2026-10-08T00:00:00Z",
           labels=[{"name": "agent-rework"}], body="Refs #3",
           comments=[verdict(1, "REJECT", "2026-10-07T12:00:00Z"), verdict(2, "REJECT", "2026-10-08T00:00:00Z")]),
        pr(13, "2026-10-11T00:00:00Z", state="MERGED", mergedAt="2026-10-12T00:00:00Z",
           mergeCommit={"oid": c3}, closingIssuesReferences=[{"number": 4}],
           comments=[{"body": "VERDICT: PEUT-ETRE\nROUND: un", "createdAt": "2026-10-11T12:00:00Z"}]),
        pr(15, "2026-10-20T00:00:00Z", labels=[{"name": "needs-your-attention"}],
           body="## Rapport d'agent\n\n- **Attention :** un point demande un regard humain\n"),
        pr(16, "2026-10-21T00:00:00Z", labels=[{"name": "needs-your-attention"}],
           body="- **Attention :** chemin protégé `.github/workflows/tests.yml` touché"),
    ]
    world.answers = {
        "repo view": {"nameWithOwner": "o/r", "defaultBranchRef": {"name": "main"}},
        "pr list": prs,
        "issue list": [issue(4, "2026-10-10T00:00:00Z", ("escaped-defect", "gravite:haute"), "Échappé de #10")],
        "api repos/{owner}/{repo}/issues/1/events": [event("ready-for-agent", "2026-10-01T10:00:00Z")],
        "api repos/{owner}/{repo}/issues/2/events": [event("ready-for-agent", "2026-10-05T10:00:00Z")],
        "api repos/{owner}/{repo}/issues/4/events": [],
    }
    for sha, state in ((c1, "success"), (c2, "failure"), (c3, "success")):
        world.answers[f"api repos/{{owner}}/{{repo}}/commits/{sha}/check-runs"] = {
            "check_runs": [{"name": "tests", "conclusion": state}, {"name": "autre", "conclusion": "failure"}]
        }
    world.answers[f"api repos/{{owner}}/{{repo}}/commits/{c4}/check-runs"] = {"check_runs": []}
    return world


class Sli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.world = build(Path(self.tmp.name))
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "claude"))
        logs = Path(self.tmp.name) / "claude" / "projects" / "p"
        logs.mkdir(parents=True)
        calls = [
            line(self.world.root, "2026-10-10T10:00:00", message=f"m{n}", usage=(1, 10, 100, 5))
            for n in range(3)
        ] + [line(self.world.root, "2026-09-10T10:00:00", message="avant", usage=(1, 10, 100, 5))]
        (logs / "s.jsonl").write_text("\n".join(calls), encoding="utf-8")

    def sli(self, name: str) -> dict:
        results = compute(self.world.root, SINCE, UNTIL, self.world.runner)
        return {item.name: item for item in results}[name].to_dict()

    def test_accept_round_1_counts_first_verdicts_in_the_window_and_the_unreadable(self) -> None:
        """accept-round-1 : seul le verdict ROUND 1 compte, la fenêtre aussi, l'illisible est compté."""
        result = self.sli("accept-round-1")
        self.assertEqual((result["numerateur"], result["denominateur"]), (1, 3))
        self.assertEqual(result["illisibles"], 1)

    def test_rework_rate_is_the_share_of_tickets_ending_in_agent_rework(self) -> None:
        result = self.sli("rework-rate")
        self.assertEqual((result["numerateur"], result["denominateur"]), (1, 4))

    def test_escaped_defects_over_merged_prs(self) -> None:
        result = self.sli("escaped-defects")
        self.assertEqual((result["numerateur"], result["denominateur"]), (1, 3))

    def test_lead_time_from_ready_for_agent_to_merge(self) -> None:
        result = self.sli("lead-time")
        self.assertEqual((result["mediane_h"], result["p90_h"], result["echantillons"]), (36, 48, 2))
        self.assertEqual(result["sans_evenement"], 1)

    def partial_pr(self) -> None:
        """Ajoute une PR fusionnée qui ne fait que citer les tickets 1 et 4 par `Refs`."""
        self.world.answers["pr list"].append(
            pr(14, "2026-10-03T00:00:00Z", state="MERGED", mergedAt="2026-10-11T00:00:00Z",
               body="Refs #1 Refs #4"))

    def test_lead_time_ignores_a_partial_pr_that_only_refs_the_ticket(self) -> None:
        """Ticket #56, lead-time : seule la PR qui ferme le ticket compte, pas une PR `Refs`."""
        self.partial_pr()
        result = self.sli("lead-time")
        self.assertEqual((result["mediane_h"], result["p90_h"], result["echantillons"]), (36, 48, 2))

    def test_restore_time_ignores_a_partial_pr_that_only_refs_the_defect(self) -> None:
        """Ticket #56, restore-time : le correctif est la PR qui ferme le défaut, pas une PR `Refs`."""
        self.partial_pr()
        result = self.sli("restore-time")
        self.assertEqual(result["par_gravite"], {"haute": {"echantillons": 1, "mediane_h": 48, "p90_h": 48}})

    def test_release_lag_to_the_first_matching_tag(self) -> None:
        result = self.sli("release-lag")
        self.assertEqual((result["mediane_h"], result["p90_h"], result["echantillons"]), (74, 110, 2))
        self.assertEqual(result["non_publiees"], 1)

    def test_change_failure_counts_reverts_and_escaped_defects(self) -> None:
        result = self.sli("change-failure")
        self.assertEqual((result["numerateur"], result["denominateur"]), (2, 3))

    def test_restore_time_by_severity(self) -> None:
        result = self.sli("restore-time")
        self.assertEqual(result["par_gravite"], {"haute": {"echantillons": 1, "mediane_h": 48, "p90_h": 48}})
        self.assertEqual(result["ouverts"], 0)

    def test_tokens_per_merge_counts_every_role_inside_the_window(self) -> None:
        result = self.sli("tokens-per-merge")
        self.assertEqual((result["jetons"], result["denominateur"], result["valeur"]), (348, 3, 116))

    def test_human_touch_leaves_out_protected_paths(self) -> None:
        result = self.sli("human-touch")
        self.assertEqual((result["numerateur"], result["denominateur"]), (1, 6))

    def test_main_green_counts_required_contexts_only(self) -> None:
        result = self.sli("main-green")
        self.assertEqual((result["numerateur"], result["denominateur"]), (2, 3))
        self.assertEqual(result["inconnus"], 1)

    def test_reference_set_indicators_are_not_applicable_without_a_result(self) -> None:
        for name in ("judge-recall", "false-accept"):
            self.assertEqual(self.sli(name)["statut"], "sans objet")

    def test_reference_set_result_is_read_when_given(self) -> None:
        path = Path(self.tmp.name) / "reference.json"
        path.write_text(json.dumps({"judge-recall": 0.9}), encoding="utf-8")
        results = {i.name: i.to_dict() for i in compute(self.world.root, SINCE, UNTIL, self.world.runner, path)}
        self.assertEqual(results["judge-recall"]["valeur"], 0.9)
        self.assertEqual(results["false-accept"]["statut"], "sans objet")

    def test_json_and_markdown_outputs(self) -> None:
        for flag in ("--json", None):
            out = io.StringIO()
            args = ["sli", str(self.world.root), "--depuis", "2026-10-01", "--jusqua", "2026-11-01"]
            with redirect_stdout(out):
                code = main(args + ([flag] if flag else []), run=self.world.runner)
            self.assertEqual(code, 0)
            if flag:
                names = {item["nom"] for item in json.loads(out.getvalue())["sli"]}
                self.assertIn("accept-round-1", names)
            else:
                self.assertIn("| `accept-round-1` | 33 % (1/3)", out.getvalue())


class NotApplicable(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.world = World(Path(self.tmp.name))
        self.world.answers = {
            "repo view": {"nameWithOwner": "o/r", "defaultBranchRef": {"name": "main"}},
            "pr list": [], "issue list": [],
        }
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "vide"))

    def results(self) -> dict:
        return {i.name: i.to_dict() for i in compute(self.world.root, SINCE, UNTIL, self.world.runner)}

    def test_no_pr_gives_sans_objet_with_a_reason_never_zero(self) -> None:
        for name, item in self.results().items():
            self.assertEqual(item["statut"], "sans objet", name)
            self.assertTrue(item["raison"], name)
            self.assertNotIn("valeur", item, name)

    def test_missing_keys_are_named(self) -> None:
        (self.world.root / "docs" / "agents" / "usine.md").write_text("# vide\n", encoding="utf-8")
        merged = pr(1, "2026-10-02T00:00:00Z", state="MERGED", mergedAt="2026-10-03T00:00:00Z",
                    mergeCommit={"oid": "a" * 40})
        self.world.answers["pr list"] = [merged]
        results = self.results()
        self.assertIn("clé `release-tag` absente", results["release-lag"]["raison"])
        self.assertIn("clé `required-contexts` absente", results["main-green"]["raison"])


class Helpers(unittest.TestCase):
    def test_percentile_is_nearest_rank(self) -> None:
        self.assertEqual(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90), 9)
        self.assertEqual(percentile([5], 90), 5)
        self.assertEqual(percentile([24, 48], 50), 24)

    def test_a_pr_without_merge_date_is_counted_apart_never_a_traceback(self) -> None:
        """Ticket #57 : un `mergedAt` absent n'est pas un `TypeError` hors du `except` de `main`."""
        with tempfile.TemporaryDirectory() as folder:
            world = World(Path(folder))
            world.answers = {"api repos/{owner}/{repo}/issues/7/events": [event("ready-for-agent", "2026-10-01T00:00:00Z")]}
            open_pr = pr(5, "2026-10-02T00:00:00Z", closingIssuesReferences=[{"number": 7}], mergeCommit={"oid": "a" * 40})
            factory = Factory(world.root, SINCE, UNTIL, world.runner)
            with mock.patch.object(Factory, "merged", new_callable=mock.PropertyMock, return_value=[open_pr]):
                self.assertEqual(lead_time(factory).to_dict()["statut"], "sans objet")
                self.assertEqual(release_lag(factory).to_dict()["statut"], "sans objet")

    def test_a_defect_without_creation_date_does_not_raise(self) -> None:
        """Ticket #57 : `restore-time` ignore un défaut sans `createdAt` au lieu de lever."""
        with tempfile.TemporaryDirectory() as folder:
            world = World(Path(folder))
            defect = issue(4, "2026-10-02T00:00:00Z", ("escaped-defect",))
            del defect["createdAt"]
            fixed = pr(6, "2026-10-02T00:00:00Z", mergedAt="2026-10-03T00:00:00Z", closingIssuesReferences=[{"number": 4}])
            world.answers = {"pr list": [fixed]}
            factory = Factory(world.root, SINCE, UNTIL, world.runner)
            with mock.patch.object(Factory, "defects", new_callable=mock.PropertyMock, return_value=[defect]):
                self.assertEqual(restore_time(factory).to_dict()["statut"], "sans objet")

    def test_script_runs_from_the_command_line(self) -> None:
        script = support.PLUGIN / "scripts" / "factory_slo.py"
        with tempfile.TemporaryDirectory() as folder:
            isolate(self, folder)
            done = subprocess.run(
                ["uv", "run", "--no-project", "--quiet", "python", str(script), "--help"],
                capture_output=True, text=True, env=dict(os.environ),
            )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("sli", done.stdout)


if __name__ == "__main__":
    unittest.main()
