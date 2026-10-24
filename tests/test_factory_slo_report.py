"""factory_slo.py report et changelog: le rapport des SLO, la section du CHANGELOG, l'issue de suivi (ticket #58)."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import support  # noqa: F401  met le plugin sur le chemin d'import
from test_factory_slo import USINE, build, isolate

from factory_slo import main

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
COMMENTS = "repos/{owner}/{repo}/issues/55/comments"
ATTENTION = "needs-your-attention"
HELD = ("accept-round-1 | >= 5 % | 31",)
THREATENED = ("accept-round-1 | >= 30 % | 31",)
EXHAUSTED = ("accept-round-1 | >= 30 % | 31", "main-green | >= 90 % | 31")


class Issue:
    """Un faux ticket de suivi : ses commentaires et ses étiquettes, et chaque écriture que `gh` en reçoit."""

    def __init__(self, world) -> None:
        self.world = world
        self.comments: list[dict] = []
        self.labels: set[str] = set()
        self.writes: list[list[str]] = []

    def __call__(self, cmd: list[str], cwd: Path) -> str:
        if cmd[0] != "gh":
            return self.world.runner(cmd, cwd)
        args = cmd[1:]
        if args[:2] == ["api", "--paginate"] and args[2] == COMMENTS:
            return json.dumps(self.comments)
        if args[:2] == ["issue", "view"]:
            return json.dumps({"labels": [{"name": name} for name in sorted(self.labels)]})
        if args[0] == "api" and args[1] == COMMENTS:
            self.writes.append(args)
            self.comments.append({"id": 700 + len(self.comments), "body": args[3].removeprefix("body=")})
            return "{}"
        if args[:3] == ["api", "-X", "PATCH"]:
            self.writes.append(args)
            ident = int(args[3].rsplit("/", 1)[1])
            next(c for c in self.comments if c["id"] == ident)["body"] = args[5].removeprefix("body=")
            return "{}"
        if args[:2] == ["issue", "edit"]:
            self.writes.append(args)
            (self.labels.add if args[3] == "--add-label" else self.labels.discard)(args[4])
            return ""
        if args[:2] == ["issue", "comment"]:
            self.writes.append(args)
            self.comments.append({"id": 700 + len(self.comments), "body": args[4]})
            return ""
        return self.world.runner(cmd, cwd)


class Report(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "vide"))
        self.world = build(Path(self.tmp.name))
        first = self.world.git("rev-list", "--max-parents=0", "HEAD")
        self.world.answers[f"api repos/{{owner}}/{{repo}}/commits/{first}/check-runs"] = {"check_runs": []}
        self.issue = Issue(self.world)

    def configure(self, slo: tuple[str, ...], issue: str | None = "55") -> None:
        text = USINE + "".join(f"- `slo` : `{line}`\n" for line in slo)
        if issue is not None:
            text += f"- `slo-issue` : `{issue}`\n"
        (self.world.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def run_main(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([*args[:1], str(self.world.root), *args[1:]], run=self.issue, now=NOW)
        return code, out.getvalue(), err.getvalue()

    def report(self, *extra: str) -> tuple[int, str, str]:
        return self.run_main("report", *extra)

    def attention_comments(self) -> list[str]:
        return [c["body"] for c in self.issue.comments if "forge-slo-report" not in c["body"]]

    def test_report_gives_value_remaining_budget_state_and_trend(self) -> None:
        """Ticket #58 : chaque SLO, sa valeur, son budget restant, son état et sa tendance."""
        self.configure(HELD)
        code, out, _ = self.report()
        self.assertEqual(code, 0)
        self.assertIn("| `accept-round-1` | >= 5 % | 31 j | 33.33 % | 28.33 % sur 95 % | tenu |", out)

    def test_trend_compares_with_the_previous_window_of_the_same_length(self) -> None:
        """Ticket #58 : la fenêtre précédente (ici 100 % de PR acceptées au premier tour) fait une dégradation."""
        self.configure(HELD)
        _, out, _ = self.report("--json")
        item = json.loads(out)["objectifs"][0]
        self.assertEqual((item["precedent"]["valeur"], item["tendance"]), (100, "dégradation"))
        _, text, _ = self.report()
        self.assertIn("dégradation (était 100 %)", text)

    def test_trend_without_data_in_the_previous_window_has_no_comparison(self) -> None:
        self.configure(("accept-round-1 | >= 5 % | 5",))
        _, out, _ = self.report("--json")
        item = json.loads(out)["objectifs"][0]
        self.assertEqual(item["statut"], "sans objet")
        self.assertEqual(item["tendance"], "sans objet")
        self.configure(("accept-round-1 | >= 5 % | 45",))
        _, out, _ = self.report("--json")
        self.assertEqual(json.loads(out)["objectifs"][0]["tendance"], "sans point de comparaison")

    def test_report_modifies_nothing(self) -> None:
        """Ticket #58 : le skill ne modifie rien ; sans `--publier`, aucune écriture sur GitHub ni de fichier d'état."""
        self.configure(THREATENED)
        self.report()
        self.assertEqual(self.issue.writes, [])
        common = Path(self.world.git("rev-parse", "--path-format=absolute", "--git-common-dir"))
        self.assertFalse((common / "forge" / "slo-status.json").exists())

    def test_missing_slo_key_is_sans_objet(self) -> None:
        code, out, _ = self.report("--publier")
        self.assertEqual(code, 0)
        self.assertIn("sans objet (clé `slo` absente)", out)
        self.assertEqual(self.issue.writes, [])

    def test_changelog_section_has_the_state_of_each_slo_and_the_escaped_defects_since(self) -> None:
        """Ticket #58 : l'état de chaque SLO à la date de la version, et les `escaped-defect` ouverts depuis la précédente."""
        self.configure(EXHAUSTED)
        code, out, _ = self.run_main("changelog", "--depuis", "2026-10-05")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("### Objectifs de service\n"))
        self.assertIn("État de chaque objectif au 2026-11-01.", out)
        self.assertIn("| `accept-round-1` | >= 30 % | 31 j | 33.33 % | 3.33 % sur 70 % | menacé |", out)
        self.assertIn("| `main-green` | >= 90 % | 31 j | 66.67 % | 0 % sur 10 % | épuisé |", out)
        self.assertIn("`escaped-defect` ouverts depuis le 2026-10-05 :", out)
        self.assertIn("- #4 Ticket 4 (ouvert)", out)

    def test_changelog_names_no_defect_opened_before_the_previous_release(self) -> None:
        self.configure(HELD)
        _, out, _ = self.run_main("changelog", "--depuis", "2026-10-11")
        self.assertIn("Aucun `escaped-defect` ouvert depuis le 2026-10-11.", out)
        self.assertNotIn("#4", out)

    def test_changelog_takes_the_date_of_the_version(self) -> None:
        self.configure(HELD)
        _, out, _ = self.run_main("changelog", "--depuis", "2026-10-05", "--le", "2026-10-31")
        self.assertIn("au 2026-10-31.", out)

    def test_publish_writes_one_comment_then_rewrites_it(self) -> None:
        """Ticket #58 : le rapport est réécrit dans le même commentaire de l'issue de suivi, jamais empilé."""
        self.configure(HELD)
        _, out, _ = self.report("--publier")
        self.assertIn("rapport posté dans un commentaire du ticket #55", out)
        self.assertEqual(len(self.issue.comments), 1)
        first = self.issue.comments[0]["body"]
        self.assertIn("forge-slo-report", first)
        self.assertIn("| `accept-round-1` |", first)
        _, out, _ = self.report("--publier")
        self.assertIn("rapport réécrit dans le commentaire 700", out)
        self.assertEqual(len(self.issue.comments), 1)

    def test_a_hash_before_the_issue_number_is_accepted(self) -> None:
        self.configure(HELD, issue="#55")
        code, _, _ = self.report("--publier")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.issue.comments), 1)

    def test_a_key_that_is_not_a_number_fails_and_writes_nothing(self) -> None:
        self.configure(HELD, issue="bientôt")
        code, _, err = self.report("--publier")
        self.assertEqual(code, 1)
        self.assertIn("slo-issue", err)
        self.assertEqual(self.issue.writes, [])

    def test_missing_slo_issue_key_is_sans_objet_and_posts_nothing(self) -> None:
        """Ticket #58 : clé `slo-issue` absente, « sans objet »."""
        self.configure(HELD, issue=None)
        code, out, _ = self.report("--publier")
        self.assertEqual(code, 0)
        self.assertIn("| `accept-round-1` |", out)
        self.assertIn("Publication : sans objet (clé `slo-issue` absente)", out)
        self.assertEqual(self.issue.writes, [])

    def test_a_threatened_slo_sets_the_label_with_its_reason(self) -> None:
        """Ticket #58 : un SLO `menacé` pose `needs-your-attention` sur l'issue, avec la raison."""
        self.configure(THREATENED)
        _, out, _ = self.report("--publier")
        self.assertIn(ATTENTION, self.issue.labels)
        self.assertIn("étiquette `needs-your-attention` posée sur #55", out)
        reason = self.attention_comments()[0]
        self.assertIn("accept-round-1 | >= 30 % | 31", reason)
        self.assertIn("menacé", reason)
        self.assertIn("95 % du budget consommé", reason)

    def test_an_exhausted_slo_sets_the_label_too(self) -> None:
        self.configure(("main-green | >= 90 % | 31",))
        self.report("--publier")
        self.assertIn(ATTENTION, self.issue.labels)
        self.assertIn("épuisé", self.attention_comments()[0])

    def test_a_held_slo_does_not_set_the_label(self) -> None:
        self.configure(HELD)
        self.report("--publier")
        self.assertEqual(self.issue.labels, set())
        self.assertEqual(self.attention_comments(), [])

    def test_the_reason_is_not_repeated_while_nothing_changes(self) -> None:
        self.configure(THREATENED)
        self.report("--publier")
        self.report("--publier")
        self.assertEqual(len(self.attention_comments()), 1)
        self.configure(EXHAUSTED)
        self.report("--publier")
        self.assertEqual(len(self.attention_comments()), 2)
        self.assertIn("main-green", self.attention_comments()[1])

    def test_the_label_is_removed_when_all_slo_are_back_to_tenu_and_the_comment_says_why(self) -> None:
        """Ticket #58 : l'étiquette est retirée quand tous les SLO repassent à `tenu`, et le commentaire dit pourquoi."""
        self.configure(THREATENED)
        self.report("--publier")
        self.configure(HELD)
        _, out, _ = self.report("--publier")
        self.assertNotIn(ATTENTION, self.issue.labels)
        self.assertIn("étiquette `needs-your-attention` retirée de #55", out)
        self.assertIn("tous les objectifs de service sont repassés à `tenu`", self.attention_comments()[-1])

    def test_a_label_a_human_put_for_another_reason_is_left_alone(self) -> None:
        self.configure(HELD)
        self.issue.labels.add(ATTENTION)
        self.report("--publier")
        self.assertIn(ATTENTION, self.issue.labels)
        self.assertEqual(self.attention_comments(), [])

    def test_a_still_threatened_slo_keeps_the_label(self) -> None:
        self.configure(THREATENED)
        self.report("--publier")
        self.configure(EXHAUSTED)
        self.report("--publier")
        self.assertIn(ATTENTION, self.issue.labels)


class Content(unittest.TestCase):
    def test_the_skill_runs_the_report_from_the_plugin_root_and_changes_nothing_by_default(self) -> None:
        """Ticket #58 : un skill `forge:slo` lance le rapport ; il ne publie que sur demande."""
        text = (support.PLUGIN / "skills" / "slo" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: slo", text)
        self.assertIn("disable-model-invocation: true", text)
        self.assertIn('uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/factory_slo.py" report', text)
        self.assertIn("Sans `--publier`, le script ne modifie rien", text)
        self.assertIn("sans objet (clé `slo-issue` absente)", text)

    def test_the_template_documents_the_slo_issue_key_and_its_absence(self) -> None:
        """Ticket #58 : la clé `slo-issue` est au gabarit, et sa clé absente est « sans objet »."""
        template = (support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8")
        self.assertIn("- `slo-issue` : `<55>`", template)
        self.assertIn("sans objet (clé `slo-issue` absente)", template)


if __name__ == "__main__":
    unittest.main()
