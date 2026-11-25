"""Ticket #355 : le modèle lance `feature-accept` et `release` quand le projet a ouvert l'autonomie.

La clé `agent-autonomy` de `usine.md` ouvre les deux skills au modèle ; sans elle, un lancement par le
modèle n'écrit rien et rend la commande exacte à l'humain. Une commande tapée s'exécute comme avant.
"""

import re
import unittest
from pathlib import Path

import support
from test_plugin_content import frontmatter

SKILLS = support.PLUGIN / "skills"
ACCEPT = SKILLS / "feature-accept" / "SKILL.md"
RELEASE = SKILLS / "release" / "SKILL.md"
RULE = support.PLUGIN / "autonomie.md"
PROTOCOLE = support.PLUGIN / "templates" / "features" / "protocole.md"
USINE_TEMPLATE = support.PLUGIN / "templates" / "usine.md"
README = support.REPO_ROOT / "README.md"
INSTALLATION = support.REPO_ROOT / "docs" / "installation.md"
RULE_REF = "${CLAUDE_PLUGIN_ROOT}/autonomie.md"


def prose(path: Path) -> str:
    """The file on one line per paragraph, so a sentence wrapped by the editor still matches."""
    return " ".join(path.read_text(encoding="utf-8").split())


class BothSkillsAreOpened(unittest.TestCase):
    def test_neither_skill_carries_the_flag_that_forbids_the_model(self) -> None:
        """Ticket #355 A1 : `feature-accept` et `release` perdent `disable-model-invocation`."""
        for path in (ACCEPT, RELEASE):
            with self.subTest(skill=path.parent.name):
                self.assertNotIn("disable-model-invocation", frontmatter(path))

    def test_each_skill_applies_the_rule_before_its_first_step(self) -> None:
        """Ticket #355 A1 : le skill lu seul renvoie à `autonomie.md` avant ses étapes numérotées."""
        for path, first_step in ((ACCEPT, "\n1. **"), (RELEASE, "\n## 1. ")):
            with self.subTest(skill=path.parent.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn(RULE_REF, text)
                self.assertLess(text.index(RULE_REF), text.index(first_step))

    def test_the_descriptions_no_longer_say_only_a_typed_command(self) -> None:
        """Ticket #355 A1 : la description d'`feature-accept` ne réserve plus l'acceptation à la frappe."""
        description = frontmatter(ACCEPT)["description"]
        self.assertNotIn("qui tape la commande", description)
        self.assertIn("agent-autonomy", description)
        self.assertIn("accepting-human", description)


class AModelStartWithoutTheKey(unittest.TestCase):
    def test_feature_accept_writes_nothing_and_hands_the_exact_command(self) -> None:
        """Ticket #355 A2 : `feature-accept` lancé par le modèle, clé absente : rien d'écrit, la commande à l'humain."""
        text = prose(ACCEPT)
        self.assertRegex(
            text,
            r"lancé par le modèle.{0,200}clé `agent-autonomy`.{0,200}absente.{0,200}n'écris rien.{0,200}n'ouvre ni branche ni PR"
            r".{0,200}commande exacte",
        )

    def test_release_writes_nothing_not_even_the_version_pr(self) -> None:
        """Ticket #355 A2 : `release` lancé par le modèle, clé absente : pas même la PR de version, la commande à l'humain."""
        text = prose(RELEASE)
        self.assertRegex(
            text,
            r"lancé par le modèle.{0,200}clé `agent-autonomy`.{0,200}absente.{0,200}n'écris rien.{0,200}"
            r"n'ouvre pas même la PR de version.{0,200}commande exacte",
        )

    def test_a_typed_release_without_the_key_still_opens_the_version_pr(self) -> None:
        """Ticket #355 A2 : tapé par l'humain, sans la clé, `release` ouvre la PR de version seule, comme avant."""
        self.assertRegex(prose(RELEASE), r"[Tt]apé par l'humain.{0,300}ouvre la PR de version")

    def test_the_rule_says_it_for_both_skills(self) -> None:
        """Ticket #355 A2 : l'étape 4 de la règle dit le lancement par le modèle, clé absente, des deux skills."""
        section = prose(RULE).split("## 4.", 1)[1]
        self.assertRegex(section, r"`feature-accept`.{0,400}clé absente.{0,200}n'écrit rien")
        self.assertRegex(section, r"`release`.{0,500}clé absente.{0,200}pas même la PR de version")
        self.assertRegex(prose(RULE), r"`release` n'ouvre que la PR de version \(lancé par l'humain")


class AModelAcceptance(unittest.TestCase):
    def test_a_model_acceptance_adds_the_via_field_and_keeps_the_short_id(self) -> None:
        """Ticket #355 A3 : le modèle écrit `accepte_par` et `accepte_via: agent-autonomy` dans l'en-tête."""
        step = prose(ACCEPT).split("**Écrire**", 1)[1].split("5. **Livrer.**", 1)[0]
        self.assertIn("`accepte_par: <l'identifiant court", step)
        self.assertRegex(step, r"[Ll]ancée? par le modèle.{0,200}`accepte_via: agent-autonomy`")

    def test_a_typed_acceptance_does_not_write_the_via_field(self) -> None:
        """Ticket #355 A3 : tapée par l'humain, l'acceptation n'écrit pas `accepte_via`."""
        step = prose(ACCEPT).split("**Écrire**", 1)[1].split("5. **Livrer.**", 1)[0]
        self.assertRegex(step, r"[Tt]apée.{0,200}n'écris pas `accepte_via`")

    def test_the_commit_and_the_pr_repeat_the_via_field(self) -> None:
        """Ticket #355 A3 : le commit et la PR d'une acceptation par le modèle répètent `accepte_via: agent-autonomy`."""
        delivery = prose(ACCEPT).split("5. **Livrer.**", 1)[1].split("6. **Dire la suite**", 1)[0]
        self.assertRegex(delivery, r"[Ll]ancée par le modèle.{0,300}commit.{0,150}`accepte_via: agent-autonomy`.{0,200}PR.{0,150}`accepte_via: agent-autonomy`")

    def test_a_model_start_needs_the_key_but_not_the_git_name(self) -> None:
        """Ticket #355 A3 : au premier pas, le modèle exige la clé `accepting-human` et ne compare pas `user.name`."""
        step = prose(ACCEPT).split("1. **Qui accepte**", 1)[1].split("2. **Quoi.**", 1)[0]
        self.assertRegex(step, r"[Ll]ancée? par le modèle.{0,300}clé `accepting-human`.{0,300}ne compare pas `git config user.name`")
        self.assertIn("le nom de l'humain", step)

    def test_no_script_or_hook_reads_the_via_field_or_trips_on_it(self) -> None:
        """Ticket #355 A3 : aucun lecteur de `accepte_par` ne casse sur le champ ajouté (rien ne le lit)."""
        for folder in ("hooks", "scripts"):
            for path in (support.PLUGIN / folder).glob("*.py"):
                with self.subTest(file=path.name):
                    self.assertNotIn("accepte_par", path.read_text(encoding="utf-8"))
                    self.assertNotIn("accepte_via", path.read_text(encoding="utf-8"))


class OpenPoints(unittest.TestCase):
    def test_the_model_writes_no_acceptance_while_a_point_is_open(self) -> None:
        """Ticket #355 A4 : des points ouverts, le modèle n'écrit pas `accepte` et passe chacun aux agents décideurs."""
        text = prose(ACCEPT)
        self.assertRegex(
            text,
            r"[Ll]ancée? par le modèle.{0,200}points ouverts.{0,200}n'écris pas `accepte`.{0,300}"
            r"`forge:product-owner`.{0,100}`forge:staff-engineer`",
        )

    def test_a_reserved_point_leaves_the_document_in_review_with_the_label(self) -> None:
        """Ticket #355 A4 : un point `RESERVED` laisse le document `en-revue`, avec `needs-your-attention`."""
        self.assertRegex(prose(ACCEPT), r"`RESERVED`.{0,300}`en-revue`.{0,200}`needs-your-attention`")

    def test_decided_points_are_written_by_the_document_skill_then_accept_runs_again(self) -> None:
        """Ticket #355 A4 : tous `DECIDED`, le skill du document les écrit, puis `feature-accept` se relance."""
        text = prose(ACCEPT)
        self.assertRegex(text, r"`DECIDED`.{0,300}skill du document.{0,300}relance `feature-accept`")
        for skill in ("feature-frame", "feature-spec", "feature-design", "feature-verify", "feature-close"):
            with self.subTest(skill=skill):
                self.assertIn(skill, text)


class TheThreePagesAgree(unittest.TestCase):
    def test_the_rule_opens_acceptance_and_publication_under_the_key(self) -> None:
        """Ticket #355 A5 : `autonomie.md` dit que la clé ouvre l'acceptation et la publication au modèle."""
        section = prose(RULE).split("## 4.", 1)[1]
        self.assertNotIn("garde `disable-model-invocation: true`", section)
        self.assertRegex(section, r"`feature-accept`.{0,400}`accepte_via: agent-autonomy`")
        self.assertRegex(section, r"`release`.{0,600}`release-trigger`")

    def test_the_protocol_no_longer_reserves_acceptance_to_the_typed_command(self) -> None:
        """Ticket #355 A5 : `protocole.md` dit l'acceptation tapée par un humain, ou lancée par le modèle sous la clé."""
        text = prose(PROTOCOLE)
        self.assertNotRegex(text, r"s'accepte par `/forge:feature-accept`, tapée par un humain\.")
        self.assertRegex(text, r"s'accepte par `/forge:feature-accept`.{0,200}`agent-autonomy`")
        self.assertRegex(text, r"\*\*Jamais `accepte`\*\*.{0,300}`agent-autonomy`")
        self.assertRegex(text, r"Savoir qui parle.{0,900}lancée? par le modèle.{0,200}`agent-autonomy`")

    def test_the_readme_says_the_model_can_start_both(self) -> None:
        """Ticket #355 A5 : le README ne dit plus `sauf feature-accept et release` ni `geste réservé à un humain`."""
        text = prose(README)
        self.assertNotIn("sauf `/forge:feature-accept` et `/forge:release`", text)
        self.assertNotIn("accepter un document, geste réservé à un humain", text)
        self.assertRegex(text, r"`/forge:feature-accept` \| accepter un document.{0,120}`agent-autonomy`")
        self.assertRegex(text, r"clé `agent-autonomy` laisse le modèle lancer lui-même ces commandes, `/forge:feature-accept` et `/forge:release` compris")

    def test_the_other_pages_no_longer_keep_the_flag_on_the_two_skills(self) -> None:
        """Ticket #355 A5 : la page d'installation et le gabarit `usine.md` disent les deux skills ouverts."""
        for path in (INSTALLATION, USINE_TEMPLATE):
            with self.subTest(file=path.name):
                text = prose(path)
                self.assertNotIn("`feature-accept` et `release` gardent le drapeau", text)
                self.assertNotIn("`feature-accept` reste tapé par un humain", text)
                self.assertNotIn("la clé n'ouvre pas ces deux skills au modèle", text)
                self.assertIsNotNone(re.search(r"`feature-accept`.{0,300}`accepte_via: agent-autonomy`", text))


if __name__ == "__main__":
    unittest.main()
