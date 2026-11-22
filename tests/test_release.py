"""release.py : le déclencheur et les conditions de la publication continue (ticket #71).

Les tests simulent `gh` par des réponses fictives, `git` par des dépôts jetables dans un dossier
temporaire, et l'essai de bout en bout par un faux script : rien ne publie, ne pose de tag ni ne
lance le vrai essai.
"""

import io
import json
import tempfile
import unittest
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import support  # noqa: F401  met le plugin sur le chemin d'import
from release import main
from test_factory_slo import USINE, World, isolate, pr

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate(self, self.tmp.name, CLAUDE_CONFIG_DIR=str(Path(self.tmp.name) / "vide"))
        self.world = World(Path(self.tmp.name))
        self.world.answers = {"repo view": {"nameWithOwner": "o/r", "defaultBranchRef": {"name": "main"}}}
        self.runner: Callable[[list[str], Path], str] = self.world.runner

    def configure(self, *lines: str) -> None:
        text = USINE + "".join(f"- {line}\n" for line in lines)
        (self.world.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def run_main(self, *words: str) -> tuple[int, str, str]:
        """`main` avec la commande et ses mots ; le projet vient juste après la commande, ou après le nom de la condition."""
        out, err = io.StringIO(), io.StringIO()
        command, *rest = words
        if command == "condition":
            argv = [command, rest[0], str(self.world.root), *rest[1:]]
        else:
            argv = [command, str(self.world.root), *rest]
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv, run=self.runner, now=NOW)
        return code, out.getvalue(), err.getvalue()

    def state_file(self) -> Path:
        common = Path(self.world.git("rev-parse", "--path-format=absolute", "--git-common-dir"))
        return common / "forge" / "slo-status.json"

    def write_state(self, etats: dict[str, str], minutes: int = 30, **extra: object) -> None:
        """Le fichier d'état que `factory_slo.py status` écrit, calculé il y a `minutes` minutes."""
        objectifs = [
            {"sli": sli, "statistique": None, "fenetre_jours": 30, "statut": "sans objet" if etat == "sans objet" else "calculé",
             **({} if etat == "sans objet" else {"etat": etat})}
            for sli, etat in etats.items()
        ]
        document = {"calcule_le": (NOW - timedelta(minutes=minutes)).isoformat(), "objectifs": objectifs, **extra}
        self.state_file().parent.mkdir(parents=True, exist_ok=True)
        self.state_file().write_text(json.dumps(document), encoding="utf-8")


class Trigger(Base):
    def merges(self, *dates: str, released: int = 0) -> None:
        """Des PR fusionnées aux dates données, dont les `released` premières sont dans un tag de version."""
        listed = []
        for index, merged in enumerate(dates):
            oid = self.world.commit(f"feat: {index}", merged)
            listed.append(pr(index + 1, merged, state="MERGED", mergedAt=merged, mergeCommit={"oid": oid}))
            if index == released - 1:
                self.world.git("tag", "-a", "-m", "v", "forge--v1.0.0", oid, when=merged)
        self.world.answers["pr list"] = listed

    def test_an_absent_key_is_sans_objet_and_never_publishes(self) -> None:
        """Ticket #71 : sans `release-trigger`, « sans objet », aucune publication par l'agent."""
        code, out, _ = self.run_main("trigger")
        self.assertEqual(code, 0)
        self.assertIn("DECLENCHEUR: sans objet (clé `release-trigger` absente)", out)

    def test_a_key_that_cannot_be_read_fails_and_guesses_nothing(self) -> None:
        """Ticket #71 : une valeur illisible, répétée ou à moitié écrite fait échouer la commande."""
        for value in ("dix | 7 j", "0 | 7 j", "10 | 7", "10 | 0 j", "10", "10 |"):
            with self.subTest(value=value):
                self.configure(f"`release-trigger` : `{value}`")
                code, out, err = self.run_main("trigger")
                self.assertEqual(code, 2)
                self.assertIn("release-trigger", err)
                self.assertNotIn("DECLENCHEUR", out)
        self.configure("`release-trigger` : `10 | 7 j`", "`release-trigger` : `5 | 2 j`")
        self.assertEqual(self.run_main("trigger")[0], 2)

    def test_the_number_of_merges_waiting_for_a_tag_triggers_a_version(self) -> None:
        """Ticket #71 : N fusions hors de tout tag de version déclenchent, la borne comprise."""
        self.configure("`release-trigger` : `3 | 30 j`")
        self.merges("2026-11-10T10:00:00Z", "2026-11-12T10:00:00Z", "2026-11-13T10:00:00Z",
                    "2026-11-14T10:00:00Z", released=1)
        code, out, _ = self.run_main("trigger")
        self.assertEqual(code, 0)
        self.assertIn("DECLENCHEUR: atteint par le nombre : 3 fusions en attente pour 3 demandées", out)

    def test_below_both_bounds_nothing_is_due(self) -> None:
        """Ticket #71 : deux fusions de 2 jours, pour 3 fusions ou 7 jours : pas de version."""
        self.configure("`release-trigger` : `3 | 7 j`")
        self.merges("2026-11-14T10:00:00Z", "2026-11-14T11:00:00Z")
        _, out, _ = self.run_main("trigger")
        self.assertIn("DECLENCHEUR: non atteint : 2 fusions en attente pour 3 demandées, la plus ancienne depuis 2 j pour 7 j", out)

    def test_the_oldest_waiting_merge_triggers_by_delay_even_with_few_merges(self) -> None:
        """Ticket #71 : une seule fusion qui attend depuis plus que le délai déclenche, au délai près."""
        self.configure("`release-trigger` : `10 | 7 j`")
        self.merges("2026-11-09T12:00:00Z")
        code, out, _ = self.run_main("trigger")
        self.assertEqual(code, 0)
        self.assertIn("DECLENCHEUR: atteint par le délai : la plus ancienne attend depuis 7 j pour 7 j", out)
        self.merges("2026-11-09T12:00:01Z")
        self.assertIn("DECLENCHEUR: non atteint", self.run_main("trigger")[1])

    def test_nothing_waiting_never_triggers(self) -> None:
        """Ticket #71 : tout est déjà dans un tag, rien à publier, quel que soit le temps écoulé."""
        self.configure("`release-trigger` : `1 | 1 h`")
        self.merges("2026-10-01T10:00:00Z", released=1)
        _, out, _ = self.run_main("trigger")
        self.assertIn("DECLENCHEUR: non atteint : aucune fusion n'attend de version", out)

    def test_only_a_tag_of_the_release_tag_pattern_publishes_a_merge(self) -> None:
        """Ticket #71 : le motif du tag vient de la clé `release-tag` ; un autre tag ne publie rien."""
        self.configure("`release-trigger` : `1 | 30 j`")
        self.merges("2026-11-14T10:00:00Z")
        oid = self.world.git("rev-parse", "HEAD")
        self.world.git("tag", "-a", "-m", "v", "autre-v9", oid)
        self.assertIn("atteint par le nombre : 1 fusion en attente pour 1 demandée", self.run_main("trigger")[1])
        self.world.git("tag", "-a", "-m", "v", "forge--v1.0.1", oid)
        self.assertIn("non atteint : aucune fusion", self.run_main("trigger")[1])

    def test_without_the_release_tag_key_the_count_is_sans_objet(self) -> None:
        """Ticket #71 : sans `release-tag`, aucun motif de tag à lire : « sans objet », rien ne se déclenche."""
        (self.world.root / "docs" / "agents" / "usine.md").write_text(
            "- `release-trigger` : `1 | 1 h`\n", encoding="utf-8")
        self.merges("2026-11-14T10:00:00Z")
        code, out, _ = self.run_main("trigger")
        self.assertEqual(code, 0)
        self.assertIn("DECLENCHEUR: sans objet (clé `release-tag` absente)", out)


AUTONOMY = "`agent-autonomy` : `on`"
SLO = ("`slo` : `main-green | >= 90 % | 30`","`slo` : `accept-round-1 | >= 80 % | 30`")


class SloCondition(Base):
    """Tous les SLO sont `tenu` dans `slo-status.json`, calculé dans l'heure."""

    def condition(self) -> tuple[str, str]:
        code, out, _ = self.run_main("condition", "slo")
        self.assertEqual(code, 0)
        line = next(line for line in out.splitlines() if line.startswith("CONDITION: slo"))
        _, status, text = (part.strip() for part in line.split("|", 2))
        return status, text

    def test_every_objective_tenu_and_computed_within_the_hour_holds(self) -> None:
        """Ticket #71 : tous les SLO `tenu`, calculés il y a moins d'une heure : condition tenue."""
        self.configure(*SLO)
        self.write_state({"main-green": "tenu", "accept-round-1": "tenu"}, minutes=59)
        self.assertEqual(self.condition()[0], "tenue")

    def test_a_menaced_an_exhausted_or_a_sans_objet_objective_does_not_hold(self) -> None:
        """Ticket #71 : un objectif qui n'est pas `tenu` (menacé, épuisé, sans objet) manque la condition, nommé."""
        self.configure(*SLO)
        for etat in ("menacé", "épuisé", "sans objet"):
            with self.subTest(etat=etat):
                self.write_state({"main-green": "tenu", "accept-round-1": etat})
                status, text = self.condition()
                self.assertEqual(status, "non tenue")
                self.assertIn("accept-round-1", text)
                self.assertNotIn("main-green", text)

    def test_a_state_older_than_an_hour_cannot_be_verified(self) -> None:
        """Ticket #71 : calculé il y a 61 minutes : non vérifiable, avec la commande qui le recalcule."""
        self.configure(*SLO)
        self.write_state({"main-green": "tenu", "accept-round-1": "tenu"}, minutes=61)
        status, text = self.condition()
        self.assertEqual(status, "non vérifiable")
        self.assertIn("plus de 1 h", text)
        self.assertIn("factory_slo.py", text)

    def test_a_missing_or_unreadable_state_cannot_be_verified(self) -> None:
        """Ticket #71 : fichier absent ou illisible : non vérifiable, jamais « tenue »."""
        self.configure(*SLO)
        self.assertEqual(self.condition()[0], "non vérifiable")
        self.state_file().parent.mkdir(parents=True, exist_ok=True)
        self.state_file().write_text("{", encoding="utf-8")
        self.assertEqual(self.condition()[0], "non vérifiable")

    def test_without_the_slo_key_or_with_no_objective_it_cannot_be_verified(self) -> None:
        """Ticket #71 : clé `slo` absente, ou aucun objectif dans l'état : « sans objet », donc non vérifiable."""
        self.write_state({"main-green": "tenu"})
        status, text = self.condition()
        self.assertEqual(status, "non vérifiable")
        self.assertIn("clé `slo` absente", text)
        self.configure(*SLO)
        self.write_state({})
        self.assertEqual(self.condition()[0], "non vérifiable")


class TagName(Base):
    """Le nom du tag vient du motif de la clé `release-tag` ; l'agent ne l'écrit pas à la main."""

    def tag(self, version: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["tag", str(self.world.root), version], run=self.runner, now=NOW)
        return code, out.getvalue(), err.getvalue()

    def test_the_version_fills_the_pattern_of_the_key(self) -> None:
        """Ticket #71 : `forge--v{version}` avec `1.15.0` donne `forge--v1.15.0` ; un autre motif, un autre nom."""
        code, out, _ = self.tag("1.15.0")
        self.assertEqual((code, out), (0, "TAG: forge--v1.15.0\n"))
        (self.world.root / "docs" / "agents" / "usine.md").write_text("- `release-tag` : `mon_plugin_{version}`\n", encoding="utf-8")
        self.assertEqual(self.tag("2.0.1")[1], "TAG: mon_plugin_2.0.1\n")

    def test_a_tag_that_exists_is_refused_because_a_tag_is_never_moved(self) -> None:
        """Ticket #71 : le tag existe déjà : refus (code 2), jamais un déplacement."""
        self.world.commit("feat: un", "2026-11-14T10:00:00Z")
        self.world.git("tag", "-a", "-m", "v", "forge--v1.15.0")
        code, out, err = self.tag("1.15.0")
        self.assertEqual(code, 2)
        self.assertNotIn("TAG:", out)
        self.assertIn("existe déjà", err)

    def test_an_unreadable_version_or_an_ambiguous_key_is_refused(self) -> None:
        """Ticket #71 : une version qui n'est pas un numéro, deux motifs, un motif sans `{version}` : code 2."""
        for version in ("v1.2", "1 2", "", "../1"):
            with self.subTest(version=version):
                self.assertEqual(self.tag(version)[0], 2)
        (self.world.root / "docs" / "agents" / "usine.md").write_text("- `release-tag` : `a-{version}`\n- `release-tag` : `b-{version}`\n", encoding="utf-8")
        self.assertEqual(self.tag("1.0.0")[0], 2)
        (self.world.root / "docs" / "agents" / "usine.md").write_text("- `release-tag` : `fixe`\n", encoding="utf-8")
        self.assertEqual(self.tag("1.0.0")[0], 2)

    def test_without_the_release_tag_key_it_is_sans_objet(self) -> None:
        """Ticket #71 : sans `release-tag`, aucun nom de tag n'est deviné."""
        (self.world.root / "docs" / "agents" / "usine.md").write_text("", encoding="utf-8")
        code, out, _ = self.tag("1.0.0")
        self.assertEqual(code, 0)
        self.assertIn("sans objet (clé `release-tag` absente)", out)
        self.assertNotIn("TAG:", out)


class EssaiCondition(Base):
    """L'essai de bout en bout passe sur la tête de la base : un faux script tient la place de l'essai."""

    def setUp(self) -> None:
        super().setUp()
        self.head = self.world.commit("feat: tête de la base", "2026-11-15T10:00:00Z")
        self.script = Path(self.tmp.name) / "faux_essai.py"

    def trial(self, stdout: str, code: int = 0, stderr: str = "") -> None:
        """Écrit le faux essai : il note ses arguments à côté de lui, imprime et sort avec `code`."""
        self.script.write_text(
            "import json\nimport sys\nfrom pathlib import Path\n"
            "sys.stdout.reconfigure(encoding='utf-8')\nsys.stderr.reconfigure(encoding='utf-8')\n"
            "Path(__file__).with_name('arguments.json').write_text(json.dumps(sys.argv[1:]))\n"
            f"print({stdout!r})\nprint({stderr!r}, file=sys.stderr)\nsys.exit({code})\n",
            encoding="utf-8",
        )

    def condition(self, *extra: str) -> tuple[str, str]:
        code, out, _ = self.run_main("condition", "essai", "--essai", str(self.script), *extra)
        self.assertEqual(code, 0)
        line = next(line for line in out.splitlines() if line.startswith("CONDITION: essai"))
        _, status, text = (part.strip() for part in line.split("|", 2))
        return status, text

    def test_a_pass_on_the_head_of_the_base_holds_and_the_script_gets_the_project_and_the_plugin(self) -> None:
        """Ticket #71 : `RESULTAT: PASS` sur la tête de la base : tenue ; le projet et le plugin sont transmis."""
        self.trial(f"RESULTAT: PASS\nTETE: {self.head}\nDEPOT: o/essai")
        status, text = self.condition("--plugin", "/plugin/a/essayer")
        self.assertEqual(status, "tenue")
        self.assertIn(self.head[:12], text)
        arguments = json.loads((self.script.with_name("arguments.json")).read_text(encoding="utf-8"))
        self.assertEqual(arguments, ["--projet", str(self.world.root), "--plugin", "/plugin/a/essayer"])

    def test_a_pass_on_another_commit_or_on_a_modified_tree_does_not_hold(self) -> None:
        """Ticket #71 : un PASS qui n'a pas porté sur la tête de la base, ou sur un arbre modifié, ne la prouve pas."""
        self.trial("RESULTAT: PASS\nTETE: " + "a" * 40)
        status, text = self.condition()
        self.assertEqual(status, "non tenue")
        self.assertIn("a" * 12, text)
        self.assertIn(self.head[:12], text)
        self.trial(f"RESULTAT: PASS\nTETE: {self.head} (arbre modifié)")
        status, text = self.condition()
        self.assertEqual(status, "non tenue")
        self.assertIn("arbre modifié", text)

    def test_a_fail_does_not_hold_and_names_the_step_and_the_reason(self) -> None:
        """Ticket #71 : `RESULTAT: FAIL` (exit 1) : non tenue, avec `ETAPE` et `RAISON`."""
        self.trial(f"RESULTAT: FAIL\nETAPE: checks\nRAISON: un check est rouge\nTETE: {self.head}", code=1)
        status, text = self.condition()
        self.assertEqual(status, "non tenue")
        self.assertIn("checks", text)
        self.assertIn("un check est rouge", text)

    def test_what_is_not_a_clear_result_cannot_be_verified(self) -> None:
        """Ticket #71 : sans objet, mauvais appel, sortie muette, PASS qui sort en erreur, script absent : non vérifiable."""
        cases = {
            "sans objet": ("SANS-OBJET (clé `e2e-command` absente)", 0),
            "mauvais appel": ("", 2),
            "sortie muette": ("rien d'utile", 0),
            "pass en erreur": (f"RESULTAT: PASS\nTETE: {self.head}", 1),
            "tête inconnue": ("RESULTAT: PASS\nTETE: inconnue (le plugin n'est pas dans un dépôt git)", 0),
        }
        for name, (stdout, code) in cases.items():
            with self.subTest(case=name):
                self.trial(stdout, code=code, stderr="e2e_trial: mauvais appel")
                self.assertEqual(self.condition()[0], "non vérifiable")
        self.trial("SANS-OBJET (clé `e2e-command` absente)")
        self.assertIn("clé `e2e-command` absente", self.condition()[1])
        self.script.unlink()
        self.assertEqual(self.condition()[0], "non vérifiable")


class Check(Base):
    """`check` : le déclencheur, les trois conditions qui bloquent, l'état des objectifs cité, et la décision."""

    def setUp(self) -> None:
        super().setUp()
        self.script = Path(self.tmp.name) / "faux_essai.py"
        self.configure(*SLO, "`budget-action` : `main-green | human-merge`", "`release-trigger` : `1 | 30 j`", AUTONOMY)
        oid = self.world.commit("feat: une fusion qui attend", "2026-11-14T10:00:00Z")
        self.world.answers["pr list"] = [pr(1, "2026-11-14T10:00:00Z", state="MERGED", mergedAt="2026-11-14T10:00:00Z", mergeCommit={"oid": oid})]
        self.world.answers["label list"] = [{"name": "sev1"}]
        self.world.answers["issue list"] = []
        self.write_state({"main-green": "tenu", "accept-round-1": "tenu"})
        self.trial(f"RESULTAT: PASS\nTETE: {oid}\nDEPOT: o/essai")

    def trial(self, stdout: str, code: int = 0) -> None:
        self.script.write_text(
            "import json\nimport sys\nfrom pathlib import Path\n"
            "sys.stdout.reconfigure(encoding='utf-8')\n"
            "Path(__file__).with_name('arguments.json').write_text(json.dumps(sys.argv[1:]))\n"
            f"print({stdout!r})\nsys.exit({code})\n",
            encoding="utf-8",
        )
        self.script.with_name("arguments.json").unlink(missing_ok=True)

    def launched(self) -> bool:
        return self.script.with_name("arguments.json").exists()

    def check(self, *extra: str) -> tuple[int, str]:
        code, out, _ = self.run_main("check", "--essai", str(self.script), *extra)
        return code, out

    def test_everything_held_publishes(self) -> None:
        """Ticket #280 A1 : déclencheur atteint, clé `on`, aucun `sev1`, essai vert : l'agent publie seul."""
        code, out = self.check()
        self.assertEqual(code, 0)
        self.assertIn("DECISION: publier", out)
        for name in ("autonomie", "sev1", "essai"):
            self.assertIn(f"CONDITION: {name} | tenue |", out)
        self.assertNotIn("MANQUE", out)
        self.assertTrue(self.launched())

    def test_exhausted_slo_and_an_active_budget_action_are_cited_and_do_not_block(self) -> None:
        """Ticket #280 A1.2 : SLO épuisé, essai vert : `publier`, et l'état des objectifs est cité."""
        self.write_state({"main-green": "épuisé", "accept-round-1": "menacé"}, epuises=["main-green / 30 j"])
        code, out = self.check()
        self.assertEqual(code, 0)
        self.assertIn("DECISION: publier", out)
        self.assertNotIn("MANQUE", out)
        self.assertIn("ETAT: slo | non tenue |", out)
        self.assertIn("main-green (épuisé)", out)
        self.assertIn("ETAT: budget | non tenue |", out)
        self.assertNotIn("CONDITION: slo", out)
        self.assertNotIn("CONDITION: budget", out)
        self.assertTrue(self.launched())

    def test_an_unreadable_slo_state_is_cited_and_does_not_block_either(self) -> None:
        """Ticket #280 A1 : un état des SLO périmé se dit (`non vérifiable`) sans arrêter la publication."""
        self.write_state({"main-green": "tenu", "accept-round-1": "tenu"}, minutes=90)
        _, out = self.check()
        self.assertIn("DECISION: publier", out)
        self.assertIn("ETAT: slo | non vérifiable |", out)

    def test_a_key_absent_opens_only_the_version_pr_and_does_not_launch_the_trial(self) -> None:
        """Ticket #280 A2.2 : clé `agent-autonomy` absente, déclencheur atteint : `humain`, la PR de version seule."""
        self.configure(*SLO, "`release-trigger` : `1 | 30 j`")
        code, out = self.check()
        self.assertEqual(code, 0)
        self.assertIn("DECISION: humain", out)
        self.assertIn("CONDITION: autonomie | non vérifiable | sans objet (clé `agent-autonomy` absente)", out)
        self.assertIn("MANQUE: autonomie, essai\n", out)
        self.assertNotIn("DECISION: publier", out)
        self.assertFalse(self.launched())

    def test_a_value_other_than_on_is_not_the_key_open(self) -> None:
        """Ticket #280 A2 : une valeur autre que `on` ne publie pas, et la ligne fautive est citée."""
        self.configure(*SLO, "`release-trigger` : `1 | 30 j`", "`agent-autonomy` : `oui`")
        _, out = self.check()
        self.assertIn("DECISION: humain", out)
        self.assertIn("CONDITION: autonomie | non tenue |", out)
        self.assertIn("`oui`", out)

    def test_each_missing_condition_hands_the_release_back_to_the_human_and_names_it(self) -> None:
        """Ticket #280 A2.2 : une condition manquante, seule (clé `agent-autonomy` comprise), rend la publication à l'humain, nommée."""
        def autonomie() -> None:
            self.configure(*SLO, "`budget-action` : `main-green | human-merge`", "`release-trigger` : `1 | 30 j`")

        def sev1() -> None:
            self.world.answers["issue list"] = [{"number": 7, "title": "garde contourné"}]

        def essai() -> None:
            self.trial("RESULTAT: FAIL\nETAPE: pr\nRAISON: aucune PR", code=1)

        for name, break_it in (("autonomie", autonomie), ("sev1", sev1), ("essai", essai)):
            with self.subTest(condition=name):
                self.setUp()
                break_it()
                code, out = self.check()
                self.assertEqual(code, 0)
                self.assertIn("DECISION: humain", out)
                # L'essai ne part pas quand une condition moins chère manque : il est alors non tenu, lui aussi.
                self.assertIn("MANQUE: " + (name if name == "essai" else f"{name}, essai") + "\n", out)
                self.assertNotIn("DECISION: publier", out)

    def test_several_missing_conditions_are_all_named(self) -> None:
        """Ticket #71 : toutes les conditions manquantes sont nommées, pas seulement la première."""
        self.configure(*SLO, "`release-trigger` : `1 | 30 j`")
        self.world.answers["issue list"] = [{"number": 7, "title": "x"}]
        _, out = self.check()
        self.assertIn("MANQUE: autonomie, sev1, essai\n", out)

    def test_the_trial_is_not_launched_while_a_cheaper_condition_is_already_missing(self) -> None:
        """Ticket #71 : l'essai coûte de vrais appels de modèle : il ne part pas quand une autre condition manque."""
        self.world.answers["issue list"] = [{"number": 7, "title": "x"}]
        _, out = self.check()
        self.assertFalse(self.launched())
        self.assertIn("CONDITION: essai | non vérifiable | essai non lancé", out)

    def test_a_trigger_not_reached_is_nothing_to_do_and_checks_nothing(self) -> None:
        """Ticket #71 : sans version due, `rien` : aucune condition n'est lue, l'essai ne part pas."""
        self.configure(*SLO, "`release-trigger` : `2 | 30 j`")
        code, out = self.check()
        self.assertEqual(code, 0)
        self.assertIn("DECISION: rien", out)
        self.assertNotIn("CONDITION", out)
        self.assertFalse(self.launched())

    def test_without_the_trigger_key_the_decision_is_sans_objet(self) -> None:
        """Ticket #71 : clé `release-trigger` absente : « sans objet », aucune publication, aucune condition lue."""
        self.configure(*SLO)
        code, out = self.check()
        self.assertEqual(code, 0)
        self.assertIn("DECISION: sans objet", out)
        self.assertIn("clé `release-trigger` absente", out)
        self.assertNotIn("DECISION: publier", out)
        self.assertFalse(self.launched())

    def test_a_malformed_trigger_fails_and_publishes_nothing(self) -> None:
        """Ticket #71 : une clé illisible fait échouer `check` (code 2), sans décision."""
        self.configure("`release-trigger` : `bientôt | 7 j`")
        code, out = self.check()
        self.assertEqual(code, 2)
        self.assertNotIn("DECISION", out)

    def test_json_carries_the_decision_the_trigger_each_condition_and_the_cited_states(self) -> None:
        """Ticket #71 : `--json` rend un seul document : décision, déclencheur, conditions, manque, états cités."""
        self.world.answers["issue list"] = [{"number": 7, "title": "x"}]
        code, out = self.check("--json")
        self.assertEqual(code, 0)
        document = json.loads(out)
        self.assertEqual(document["decision"], "humain")
        self.assertEqual(document["declencheur"]["statut"], "atteint")
        self.assertEqual(document["declencheur"]["fusions_en_attente"], 1)
        self.assertEqual([item["nom"] for item in document["conditions"]], ["autonomie", "sev1", "essai"])
        self.assertEqual([item["nom"] for item in document["etats"]], ["slo", "budget"])
        self.assertEqual(document["manque"], ["sev1", "essai"])

    def test_the_default_trial_is_the_script_of_the_plugin_and_is_never_run_here(self) -> None:
        """Ticket #71 : sans `--essai`, c'est `e2e_trial.py` du plugin qui part ; ce test ne le lance pas."""
        from release import TRIAL_SCRIPT

        self.assertEqual(TRIAL_SCRIPT, support.PLUGIN / "scripts" / "e2e_trial.py")
        self.assertTrue(TRIAL_SCRIPT.is_file())


class Sev1Condition(Base):
    """Aucun ticket `sev1` n'est ouvert."""

    def setUp(self) -> None:
        super().setUp()
        self.world.answers["label list"] = [{"name": "bug"}, {"name": "sev1"}]
        self.world.answers["issue list"] = []

    def condition(self) -> tuple[str, str]:
        code, out, _ = self.run_main("condition", "sev1")
        self.assertEqual(code, 0)
        line = next(line for line in out.splitlines() if line.startswith("CONDITION: sev1"))
        _, status, text = (part.strip() for part in line.split("|", 2))
        return status, text

    def test_no_open_sev1_holds(self) -> None:
        """Ticket #71 : l'étiquette existe et aucun ticket ouvert ne la porte : condition tenue."""
        self.assertEqual(self.condition()[0], "tenue")

    def test_an_open_sev1_does_not_hold_and_is_named(self) -> None:
        """Ticket #71 : un `sev1` ouvert manque la condition, son numéro dit."""
        self.world.answers["issue list"] = [{"number": 12, "title": "Un garde contourné"}, {"number": 15, "title": "Perte"}]
        status, text = self.condition()
        self.assertEqual(status, "non tenue")
        self.assertIn("#12", text)
        self.assertIn("#15", text)

    def test_a_repository_without_the_sev1_label_cannot_be_verified(self) -> None:
        """Ticket #71 : sans l'étiquette `sev1`, « aucun ticket » ne prouve rien : non vérifiable."""
        self.world.answers["label list"] = [{"name": "bug"}]
        status, text = self.condition()
        self.assertEqual(status, "non vérifiable")
        self.assertIn("étiquette `sev1`", text)

    def test_a_failing_gh_cannot_be_verified(self) -> None:
        """Ticket #71 : `gh` qui échoue : non vérifiable, jamais « tenue »."""
        def failing(cmd: list[str], cwd: Path) -> str:
            raise RuntimeError("`gh issue list` a échoué : pas de réseau")

        self.runner = failing
        status, text = self.condition()
        self.assertEqual(status, "non vérifiable")
        self.assertIn("pas de réseau", text)


class BudgetCondition(Base):
    """Aucune action de `budget-action` n'est active."""

    def condition(self) -> tuple[str, str]:
        code, out, _ = self.run_main("condition", "budget")
        self.assertEqual(code, 0)
        line = next(line for line in out.splitlines() if line.startswith("CONDITION: budget"))
        _, status, text = (part.strip() for part in line.split("|", 2))
        return status, text

    def test_no_active_action_holds(self) -> None:
        """Ticket #71 : un état frais où aucune action déclarée n'est active : condition tenue."""
        self.configure(*SLO, "`budget-action` : `main-green | human-merge`", "`budget-action` : `accept-round-1 | alert`")
        self.write_state({"main-green": "tenu", "accept-round-1": "tenu"})
        self.assertEqual(self.condition()[0], "tenue")

    def test_an_active_action_does_not_hold_even_when_it_is_only_an_alert(self) -> None:
        """Ticket #71 : un objectif `épuisé` rend son action active ; `alert` compte comme les autres."""
        for action in ("human-merge", "feature-freeze", "alert"):
            with self.subTest(action=action):
                self.configure(*SLO, f"`budget-action` : `main-green | {action}`")
                self.write_state({"main-green": "épuisé", "accept-round-1": "tenu"})
                status, text = self.condition()
                self.assertEqual(status, "non tenue")
                self.assertIn(f"main-green | {action}", text)

    def test_an_action_held_in_memory_while_the_objective_is_menaced_does_not_hold(self) -> None:
        """Ticket #71 : épuisé puis menacé, l'action reste active jusqu'au retour à `tenu` (mémoire `epuises`)."""
        self.configure(*SLO, "`budget-action` : `main-green | human-merge`")
        self.write_state({"main-green": "menacé", "accept-round-1": "tenu"}, epuises=["main-green / 30 j"])
        status, text = self.condition()
        self.assertEqual(status, "non tenue")
        self.assertIn("reconstitution", text)

    def test_without_the_key_or_a_usable_state_it_cannot_be_verified(self) -> None:
        """Ticket #71 : clé absente, état périmé ou absent, ligne illisible, objectif inconnu : non vérifiable."""
        self.configure(*SLO)
        self.write_state({"main-green": "tenu", "accept-round-1": "tenu"})
        status, text = self.condition()
        self.assertEqual(status, "non vérifiable")
        self.assertIn("clé `budget-action` absente", text)
        self.configure(*SLO, "`budget-action` : `main-green | human-merge`")
        self.write_state({"main-green": "tenu", "accept-round-1": "tenu"}, minutes=61)
        self.assertEqual(self.condition()[0], "non vérifiable")
        self.state_file().unlink()
        self.assertEqual(self.condition()[0], "non vérifiable")
        self.write_state({"main-green": "tenu"})
        self.configure(*SLO, "`budget-action` : `accept-round-1 | alert`")
        status, text = self.condition()
        self.assertEqual(status, "non vérifiable")
        self.assertIn("accept-round-1", text)
        self.configure(*SLO, "`budget-action` : `main-green | geler`")
        status, text = self.condition()
        self.assertEqual(status, "non vérifiable")
        self.assertIn("geler", text)


if __name__ == "__main__":
    unittest.main()
