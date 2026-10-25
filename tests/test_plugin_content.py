"""The agents and skills are well formed, and every `forge:<name>` the plugin cites exists."""

import hashlib
import json
import re
import unittest
from pathlib import Path

import support

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
FIELD = re.compile(r"^([a-zA-Z-]+):(.*)$")
# A name followed by "*" is a family (`/forge:feature-*`), not a citation.
CITED = re.compile(r"(?<![\w@-])/?forge:([a-z0-9-]+)(?![\w*-])")
# A plugin agent's frontmatter is read for these; Claude Code ignores hooks, permissionMode,
# mcpServers and initialPrompt there, so a guard written in them would never run.
AGENT_FIELDS = {"name", "description", "tools", "model", "effort", "omitClaudeMd", "color"}
SKILL_FIELDS = {
    "name", "description", "argument-hint", "allowed-tools", "model", "disable-model-invocation",
    "user-invocable",
}
AGENTS = sorted((support.PLUGIN / "agents").glob("*.md"))
# Each agent names a level, never a model ID: a poste maps the level to a model of any provider
# through ANTHROPIC_DEFAULT_<LEVEL>_MODEL. The cheapest level that does the work, the strongest
# only where a mistake costs.
LEVELS = {"fable", "opus", "sonnet", "haiku"}
AGENT_LEVELS = {
    "qc-gate": "haiku",
    "coder": "sonnet",
    "qc-conf": "opus",
    "staff-engineer": "opus",
    "product-owner": "opus",
}
# Thinking is billed as output: each agent thinks as long as its task needs, no longer.
AGENT_EFFORTS = {
    "qc-gate": "low",
    "coder": "medium",
    "qc-conf": "medium",
    "staff-engineer": "high",
    "product-owner": "medium",
}
# Only an agent that takes everything from its prompt and from `docs/agents/usine.md` starts
# without the project's CLAUDE.md files.
WITHOUT_CLAUDE_MD = {"qc-gate"}
SKILLS = sorted((support.PLUGIN / "skills").glob("*/SKILL.md"))


def frontmatter(path: Path) -> dict[str, str]:
    match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
    if match is None:
        raise AssertionError(f"{path}: no frontmatter between two `---` lines")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        field = FIELD.match(line)
        if field is None:
            raise AssertionError(f"{path}: `{line}` is not a `key: value` line")
        value = field.group(2).strip()
        quoted = len(value) > 1 and value[0] == value[-1] and value[0] in "\"'"
        if not quoted and ": " in value:
            raise AssertionError(f"{path}: `{field.group(1)}` holds an unquoted `: `, YAML breaks")
        fields[field.group(1)] = value.strip("\"'") if quoted else value
    return fields


def names() -> set[str]:
    return {path.stem for path in AGENTS} | {path.parent.name for path in SKILLS}


class Frontmatter(unittest.TestCase):
    def test_the_plugin_has_its_agents_and_skills(self) -> None:
        self.assertEqual(
            {path.stem for path in AGENTS},
            {"coder", "qc-gate", "qc-conf", "staff-engineer", "product-owner"},
        )
        self.assertIn("qc", names())
        self.assertIn("feature-build", names())

    def test_every_agent_reads_as_a_plugin_agent(self) -> None:
        for path in AGENTS:
            with self.subTest(agent=path.stem):
                fields = frontmatter(path)
                self.assertEqual(fields.get("name"), path.stem)
                self.assertTrue(fields.get("description"))
                self.assertTrue(fields.get("tools"))
                self.assertEqual(set(fields) - AGENT_FIELDS, set())

    def test_every_skill_reads_as_a_skill(self) -> None:
        for path in SKILLS:
            with self.subTest(skill=path.parent.name):
                fields = frontmatter(path)
                self.assertEqual(fields.get("name"), path.parent.name)
                self.assertTrue(fields.get("description"))
                self.assertEqual(set(fields) - SKILL_FIELDS, set())

    def test_the_judges_have_no_write_tool(self) -> None:
        for agent in ("qc-gate", "qc-conf", "staff-engineer", "product-owner"):
            with self.subTest(agent=agent):
                tools = {tool.strip() for tool in frontmatter(support.PLUGIN / "agents" / f"{agent}.md")["tools"].split(",")}
                self.assertEqual(tools & {"Edit", "Write", "MultiEdit", "NotebookEdit", "Agent"}, set())

    def test_every_agent_names_its_model_level(self) -> None:
        self.assertEqual(set(AGENT_LEVELS), {path.stem for path in AGENTS})
        for path in AGENTS:
            with self.subTest(agent=path.stem):
                model = frontmatter(path).get("model")
                self.assertIn(model, LEVELS)
                self.assertEqual(model, AGENT_LEVELS[path.stem])

    def test_every_agent_names_its_effort(self) -> None:
        self.assertEqual(set(AGENT_EFFORTS), {path.stem for path in AGENTS})
        for path in AGENTS:
            with self.subTest(agent=path.stem):
                self.assertEqual(frontmatter(path).get("effort"), AGENT_EFFORTS[path.stem])

    def test_only_the_gate_starts_without_claude_md(self) -> None:
        for path in AGENTS:
            with self.subTest(agent=path.stem):
                expected = "true" if path.stem in WITHOUT_CLAUDE_MD else None
                self.assertEqual(frontmatter(path).get("omitClaudeMd"), expected)

    def test_the_coder_cannot_launch_an_agent(self) -> None:
        tools = frontmatter(support.PLUGIN / "agents" / "coder.md")["tools"]
        self.assertNotIn("Agent", tools)
        self.assertNotIn("Task", tools)


class CoderReportsFormatFailures(unittest.TestCase):
    def test_the_coder_carries_format_on_write_failures_into_its_notes(self) -> None:
        text = (support.PLUGIN / "agents" / "coder.md").read_text(encoding="utf-8")
        self.assertIn("format-on-write: ", text)
        self.assertIn("failed on", text)
        self.assertIn("NOTES", text.split("format-on-write: ", 1)[1].split("\n## ", 1)[0])


class CoderTestsAtDeclaredSeams(unittest.TestCase):
    """Ticket #41 : le coder teste aux coutures déclarées, une tranche à la fois."""

    @staticmethod
    def section(heading: str) -> str:
        text = (support.PLUGIN / "agents" / "coder.md").read_text(encoding="utf-8")
        return text.split(heading, 1)[1].split("\n## ", 1)[0]

    def test_tests_live_at_the_seams_the_design_declares(self) -> None:
        """No F-NNNN: ticket #41, critère 1 (couture du §6, puis ticket, puis choix écrit)."""
        step = self.section("## 3. Test-first")
        self.assertIn("Coutures de test", step)
        self.assertIn("§6", step)
        self.assertIn("ce qu'elle attrape", step)
        self.assertIn("ce qu'elle manque", step)

    def test_one_vertical_slice_at_a_time(self) -> None:
        """No F-NNNN: ticket #41, critère 2 (un test, son code, jamais un lot de tests)."""
        step = self.section("## 3. Test-first")
        self.assertIn("tranche verticale", step)
        self.assertIn("Jamais un lot de tests", step)

    def test_tests_to_avoid_and_mock_rule_stand_without_a_test_skill(self) -> None:
        """No F-NNNN: ticket #41, critère 3 (tests à éviter, mocks aux frontières)."""
        step = self.section("## 3. Test-first")
        self.assertIn("tautologique", step)
        self.assertIn("couplé à l'implémentation", step)
        self.assertIn("frontières du système", step)
        self.assertIn("`test-skill`", step)

    def test_proofs_copy_the_red_output_with_its_reason(self) -> None:
        """No F-NNNN: ticket #41, critère 4 (Preuves : sortie rouge et raison)."""
        self.assertIn("raison de l'échec", self.section("## 5. Livrer"))
        self.assertIn("raison de l'échec", self.section("## Mode correction"))


class FeatureHeaders(unittest.TestCase):
    """Ticket 6: the feature commands write the states, approvers and catalog the project declares."""

    @staticmethod
    def read(*parts: str) -> str:
        return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())

    def test_the_template_documents_the_three_keys_and_their_forms(self) -> None:
        template = self.read("templates", "usine.md")
        for role in ("active", "hors-perimetre", "abandonnee"):
            self.assertIn(f"`feature-state` : `<{role} | ", template)
        self.assertIn("`feature-catalog-command` : `<", template)
        self.assertIn("<user.name git du premier humain> | <identifiant court>", template)

    def test_a_declared_feature_state_key_must_declare_the_three_roles(self) -> None:
        protocol = self.read("templates", "features", "protocole.md")
        self.assertIn("clé `feature-state`", protocol)
        self.assertIn("un rôle manque", protocol)
        self.assertIn("la commande s'arrête", protocol)
        self.assertIn("Sans la clé, `active`, `hors-perimetre` et `abandonnee`", protocol)

    def test_the_commands_write_the_project_state_of_a_role_not_a_fixed_word(self) -> None:
        for name in ("feature-new", "feature-frame", "feature-status", "feature-brainstorm"):
            self.assertIn("clé `feature-state`", self.read("skills", name, "SKILL.md"), name)
        self.assertIn("valeur du projet", self.read("skills", "feature-frame", "SKILL.md"))
        for name in ("idee.md", "cadrage.md"):
            self.assertIn("clé `feature-state`", self.read("templates", "features", name), name)

    def test_accept_writes_the_short_identifier_when_the_key_gives_one(self) -> None:
        accept = self.read("skills", "feature-accept", "SKILL.md")
        self.assertIn("`<user.name git> | <identifiant court>`", accept)
        self.assertIn("identifiant court", accept.split("**Écrire**", 1)[1])
        self.assertIn("sans ` | `", accept)
        protocol = self.read("templates", "features", "protocole.md")
        self.assertIn("la partie gauche", protocol)
        new = self.read("skills", "feature-new", "SKILL.md")
        self.assertIn("identifiant court", new)

    def test_the_catalog_command_runs_after_each_header_write_and_before_the_push(self) -> None:
        protocol = self.read("templates", "features", "protocole.md")
        delivery = protocol.split("## 7. Livrer dans une PR", 1)[1]
        self.assertIn("clé `feature-catalog-command`", delivery)
        self.assertIn("racine du dépôt", delivery)
        self.assertIn("sans argument", delivery)
        self.assertIn("code non nul", delivery)
        self.assertIn("avant le commit", delivery)
        self.assertIn("sans objet (clé feature-catalog-command absente)", delivery)
        accept = self.read("skills", "feature-accept", "SKILL.md")
        self.assertIn("clé `feature-catalog-command`", accept)
        close = self.read("skills", "feature-close", "SKILL.md")
        self.assertIn("clé `feature-catalog-command`", close)
        self.assertLess(close.index("feature-catalog-command"), close.index("**L'issue de suivi**"))


class CitedNames(unittest.TestCase):
    def test_every_forge_name_the_plugin_cites_exists(self) -> None:
        known = names()
        texts = [
            path
            for path in support.REPO_ROOT.rglob("*")
            if path.suffix in (".md", ".py", ".json")
            and path.is_file()
            and ".git" not in path.parts
            and "tests" not in path.parts
        ]
        self.assertGreater(len(texts), 10)
        unknown = {}
        for path in texts:
            for name in CITED.findall(path.read_text(encoding="utf-8")):
                if name not in known:
                    unknown.setdefault(name, str(path.relative_to(support.REPO_ROOT)))
        self.assertEqual(unknown, {})

    def test_the_hooks_name_the_agents_the_plugin_ships(self) -> None:
        import guard_coder
        import guard_readonly

        for agent in (guard_coder.CODER, guard_readonly.GATE, *guard_readonly.READERS):
            with self.subTest(agent=agent):
                self.assertTrue((support.PLUGIN / "agents" / f"{agent.removeprefix('forge:')}.md").is_file())


class BaseReplayProbe(unittest.TestCase):
    """Ticket #43: the gate replays the added tests on the base, where each must fail."""

    @staticmethod
    def read(*parts: str) -> str:
        return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())

    def test_the_gate_runs_the_script_with_the_keys_of_the_base(self) -> None:
        """No F-NNNN: ticket #43, critère 1: une sonde lance le script du plugin, clés lues sur la base."""
        gate = self.read("agents", "qc-gate.md")
        section = gate[gate.index("**Rejeu des tests sur la base.**"):]
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/base_replay.py", section)
        self.assertIn("--base origin/<base> --head <tête>", section)
        self.assertIn("--usine usine-base.md", section)
        self.assertIn("chaque ligne `PASSES`", section)
        self.assertIn("verbatim", section)

    def test_the_gate_and_the_judge_read_the_grain_of_the_file(self) -> None:
        """No F-NNNN: ticket #43, décision du grain: un RED de fichier ne prouve pas que chaque test était rouge."""
        gate = self.read("agents", "qc-gate.md")
        section = gate[gate.index("**Rejeu des tests sur la base.**"):]
        self.assertIn("grain du fichier", section)
        self.assertIn("pas que chaque test", section)
        conf = self.read("agents", "qc-conf.md")
        section = conf[conf.index("## Lecture du rejeu sur la base"):]
        self.assertIn("grain du fichier", section)
        self.assertIn("ne prouve pas que chaque test ajouté du fichier était rouge", section)

    def test_an_impossible_replay_is_not_run_with_its_command_and_never_pass(self) -> None:
        """No F-NNNN: ticket #43, critère 1: un rejeu impossible se rend NOT RUN avec sa commande, jamais PASS."""
        gate = self.read("agents", "qc-gate.md")
        section = gate[gate.index("**Rejeu des tests sur la base.**"):]
        self.assertIn("`NOT RUN` avec sa commande", section)
        self.assertIn("jamais `PASS`", section)
        self.assertIn("sans objet (clé test-path absente)", section)
        self.assertIn("sans objet (clé red-replay absente)", section)

    def test_the_output_hands_the_probe_lines_to_the_judge(self) -> None:
        """No F-NNNN: ticket #43, critère 1: les lignes de la sonde figurent verbatim sous le tableau."""
        gate = self.read("agents", "qc-gate.md")
        self.assertIn("les éléments verbatim des sondes 2, 5, 6, 7, 10, 11 et 12", gate)

    def test_the_template_documents_the_two_keys(self) -> None:
        """No F-NNNN: ticket #43, critère 3: test-path et red-replay sont documentées dans le gabarit."""
        template = self.read("templates", "usine.md")
        self.assertIn("- `test-path` : `<tests/>`", template)
        self.assertIn("une ligne par préfixe", template)
        self.assertIn("- `red-replay` : `<", template)
        self.assertIn("{name}", template)
        self.assertIn("{file}", template)
        self.assertIn("sans objet (clé `test-path` absente)", template)
        self.assertIn("mémoire", template)
        self.assertIn("délai", template)

    def test_the_configuration_page_names_the_keys_and_the_limits(self) -> None:
        """No F-NNNN: ticket #43, critère 3: la page de docs qui décrit les clés cite les deux clés."""
        page = " ".join((support.REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8").split())
        self.assertIn("`test-path`", page)
        self.assertIn("`red-replay`", page)
        self.assertIn("base_replay.py", page)
        self.assertIn("éprouvé sous Linux seulement", page)

    def test_this_repository_declares_the_two_keys(self) -> None:
        """No F-NNNN: ticket #43, critère 4: docs/agents/usine.md déclare tests/ et la commande de la suite."""
        from usine import load

        config = load(support.REPO_ROOT)
        self.assertEqual(config["test-path"], ["tests/"])
        self.assertEqual(len(config["red-replay"]), 1)
        self.assertIn("unittest discover -s tests", config["red-replay"][0])
        self.assertIn("{name}", config["red-replay"][0])

    def test_the_judge_reads_the_probe(self) -> None:
        """No F-NNNN: ticket #43, critère 2: un test de critère qui passe sur la base sans justification est un constat."""
        judge = self.read("agents", "qc-conf.md")
        section = judge[judge.index("## Lecture du rejeu sur la base"):]
        section = section[: section.index("## Forme d'un constat")]
        self.assertIn("`PASSES`", section)
        self.assertIn("test de caractérisation", section)
        self.assertIn("refonte à comportement égal", section)
        self.assertIn("`BLOCKER` quand il est la seule preuve d'un critère de comportement nouveau", section)
        self.assertIn("`MINOR` sinon", section)
        self.assertIn("`NOT RUN`", section)
        self.assertIn("sans objet", section)

    def test_the_judge_section_sits_apart_from_the_reading_of_the_tests(self) -> None:
        """No F-NNNN: ticket #43, hors périmètre: la lecture de qualité des tests (#42) garde sa section."""
        judge = self.read("agents", "qc-conf.md")
        self.assertLess(judge.index("## Lecture des tests"), judge.index("## Lecture du rejeu sur la base"))
        self.assertEqual(judge.count("## Lecture des tests"), 1)


class GateProbes(unittest.TestCase):
    def test_the_gate_reads_the_protection_in_rulesets_and_in_branch_protection(self) -> None:
        # A branch that only a ruleset protects has no contexts in its branch protection: the
        # gate reading that source alone would report every required check as missing.
        gate = (support.PLUGIN / "agents" / "qc-gate.md").read_text(encoding="utf-8")
        self.assertIn("gh api repos/<dépôt>/rules/branches/<base>", gate)
        self.assertIn(".parameters.required_status_checks[].context", gate)
        self.assertIn("gh api repos/<dépôt>/branches/<base>", gate)
        self.assertIn(".protection.required_status_checks.contexts", gate)


class JudgeOutput(unittest.TestCase):
    def test_the_judge_knows_the_spec_line_of_a_pr_without_ticket(self) -> None:
        # parse_output.py refuses any other SPEC line than `#<ticket>` or this one: a judge that
        # does not know it would hang a ticketless PR on a ticket it does not cite.
        judge = (support.PLUGIN / "agents" / "qc-conf.md").read_text(encoding="utf-8")
        self.assertIn("`SPEC: none (<raison>)`", judge)

    def test_the_judge_weighs_a_pr_that_delivers_no_criterion_against_the_project_rules(self) -> None:
        # Ticket #28. A release PR cites the tickets it ships, but the earlier PRs delivered their
        # criteria: a judge with no rule for it hangs a SPEC line on each ticket, or on none.
        from parse_output import parse_verdict

        judge = " ".join((support.PLUGIN / "agents" / "qc-conf.md").read_text(encoding="utf-8").split())
        self.assertIn("cite des tickets sans en livrer aucun critère", judge)
        self.assertIn("se juge contre les règles du projet qui décrivent ce type de PR", judge)
        example = re.search(r"`(SPEC: none \(<règles>[^`]*\))`", judge)
        self.assertIsNotNone(example)
        spec = example.group(1) if example else ""
        for count in ("couverts", "partiels", "absents"):
            self.assertIn(count, spec)
        # The example the role gives is one parse_output.py admits.
        verdict = f"VERDICT: ACCEPT\nROUND: 1\nHEAD: 3f2a9c1\n{spec}\nFINDINGS:\n- none\nGATES: vertes\n"
        self.assertEqual(parse_verdict(verdict)["SPEC"], [spec.removeprefix("SPEC: ")])
        # The role stays generic: no rules file of a given project.
        self.assertNotIn("git.md", judge)


class JudgeReadsTests(unittest.TestCase):
    """Ticket #42: the judge reads the tests the diff adds or changes, not only their citation."""

    def judge(self) -> str:
        return " ".join((support.PLUGIN / "agents" / "qc-conf.md").read_text(encoding="utf-8").split())

    def test_the_judge_reads_every_test_the_diff_adds_or_changes(self) -> None:
        """No F-NNNN: ticket #42, critère 1: chaque test ajouté ou changé est lu."""
        judge = self.judge()
        self.assertIn("## Lecture des tests", judge)
        self.assertIn("Chaque test ajouté ou changé par le diff est lu", judge)
        self.assertIn("un test qui cite un critère ne le prouve pas pour autant", judge)

    def test_the_three_cases_are_findings(self) -> None:
        """No F-NNNN: ticket #42, critère 2: tautologique, couplé à l'implémentation, hors couture."""
        judge = self.judge()
        for text in [
            "**Tautologique**",
            "la valeur attendue est dérivée comme dans le code",
            "littéral connu, d'un exemple travaillé ou de la spec",
            "**Couplé à l'implémentation**",
            "mocke un collaborateur interne",
            "l'ordre ou le nombre des appels",
            "par un autre chemin que l'interface",
            "**Hors couture**",
            "§6 du design",
        ]:
            with self.subTest(text=text):
                self.assertIn(text, judge)

    def test_the_finding_names_the_rule_and_a_failure_scenario(self) -> None:
        """No F-NNNN: ticket #42, critère 3: règle (clé test-skill, sinon ce rôle) et scénario d'échec."""
        judge = self.judge()
        self.assertIn("le skill de la clé `test-skill` quand elle est déclarée, sinon ce rôle", judge)
        self.assertIn("la mauvaise implémentation que le test laisserait passer", judge)
        self.assertIn("la refonte sans changement de comportement qui le ferait casser", judge)

    def test_severity_is_blocker_when_the_test_is_the_only_proof_of_a_criterion(self) -> None:
        """No F-NNNN: ticket #42, critère 4: BLOCKER si seule preuve (critère absent), sinon MINOR."""
        from parse_output import parse_verdict

        judge = self.judge()
        self.assertIn("`BLOCKER` quand ce test est la seule preuve d'un critère", judge)
        self.assertIn("ce critère compte alors pour absent dans `SPEC`", judge)
        self.assertIn("`MINOR` sinon", judge)
        # The output keys and severities parse_output.py reads stay as they were.
        for key in ("VERDICT:", "ROUND:", "HEAD:", "SPEC:", "FINDINGS:", "GATES:"):
            self.assertIn(key, judge)
        verdict = (
            "VERDICT: REJECT\nROUND: 1\nHEAD: 3f2a9c1\nSPEC: #42: 0 criteria covered, 0 partial, 1 missing\n"
            "FINDINGS:\n- [BLOCKER] a.py:1 | tautologique | passe sur une mauvaise implémentation\nGATES: vertes\n"
        )
        self.assertEqual(parse_verdict(verdict)["VERDICT"], "REJECT")

    def test_the_role_stays_generic(self) -> None:
        """No F-NNNN: ticket #42, critère 5: aucune personne ni aucun projet cité."""
        judge = self.judge()
        self.assertNotIn("mattpocock", judge)


class DomainOwner(unittest.TestCase):
    """Ticket 4: an open domain question notifies the owner and follows the prudent path."""

    @staticmethod
    def read(*parts: str) -> str:
        return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())

    def test_the_template_documents_the_domain_owner_key(self) -> None:
        template = self.read("templates", "usine.md")
        self.assertIn("`domain-owner`", template)
        self.assertIn("sans `@`", template)

    def test_feature_build_notifies_the_owner_and_follows_the_prudent_path_without_stopping(self) -> None:
        skill = self.read("skills", "feature-build", "SKILL.md")
        for text in [
            "ANSWER: DECIDED | INFERRED | OPEN | NOT_DOMAIN",
            "parse_output.py\" domain",
            "`OPEN` : commente le ticket avec la question, les options, la recommandation et la voie prudente",
            "mentionne `@` suivi du compte de la clé `domain-owner`",
            "voie prudente en attendant le référent",
            "Le chiffre n'est pas produit",
            "Sur `INFERRED`, pose `needs-your-attention` sur le ticket, sans arrêter le passage",
            "un second renvoi pose `needs-info`",
            "Sans la clé `domain-owner`, la question va à un humain par `ready-for-human`",
            "liste les questions notifiées",
            "ouvre le ticket de levée",
        ]:
            with self.subTest(text=text):
                self.assertIn(text, skill)

    def test_the_decision_journal_is_written_without_reopening_the_design(self) -> None:
        skill = self.read("skills", "feature-build", "SKILL.md")
        self.assertIn("sans rouvrir le design", skill)
        self.assertIn("corps de la PR et commentaire du ticket", skill)
        self.assertIn("ne crée jamais de design", skill)
        protocol = self.read("templates", "features", "protocole.md")
        self.assertIn("Exception", protocol)
        self.assertIn("section 9", protocol)

    def test_the_judge_counts_a_prudent_path_as_a_justified_partial(self) -> None:
        judge = self.read("agents", "qc-conf.md")
        self.assertIn("voie prudente", judge)
        self.assertIn("partiel justifié", judge)


class NeverWeaken(unittest.TestCase):
    """Ticket #5: a change `never-weaken` names stops the agent's merge, as a protected path does."""

    @staticmethod
    def read(*parts: str) -> str:
        return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())

    def test_the_template_documents_the_key_its_form_and_its_three_types(self) -> None:
        template = self.read("templates", "usine.md")
        self.assertIn("`never-weaken` : `<", template)
        self.assertIn("<chemin> | <type> [| <paramètre>]", template)
        for kind in ("removed-line", "raised-number", "lowered-rank"):
            self.assertIn(f"`{kind}`", template)

    def test_the_gate_runs_the_script_on_the_diff_with_the_entries_of_the_base(self) -> None:
        gate = self.read("agents", "qc-gate.md")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/never_weaken.py", gate)
        self.assertIn("--usine", gate)
        self.assertIn("-c core.quotePath=false diff origin/<base>...<tête> > pr.diff", gate)
        self.assertIn("git show origin/<base>:docs/agents/usine.md", gate)
        self.assertIn("clé never-weaken absente", gate)

    def test_the_judge_names_the_entry_that_applies_in_the_gates_line(self) -> None:
        judge = self.read("agents", "qc-conf.md")
        self.assertIn("never-weaken", judge)
        self.assertIn("GATES", judge)
        self.assertIn("une entrée qui s'applique", judge)

    def test_qc_stops_the_merge_on_accept_and_writes_the_reason(self) -> None:
        skill = self.read("skills", "qc", "SKILL.md")
        self.assertIn("clé `never-weaken`", skill)
        section = skill[skill.index("## Chemins protégés"):]
        self.assertIn("never-weaken", section)
        self.assertIn("même sur ACCEPT", section)
        self.assertIn("`Attention`", section)

    def test_the_readme_tells_it(self) -> None:
        readme = " ".join((support.REPO_ROOT / "README.md").read_text(encoding="utf-8").split())
        self.assertIn("`never-weaken`", readme)


class SourceIdentifiers(unittest.TestCase):
    """Ticket #92: the spec takes up every element of the business source by its identifier."""

    @staticmethod
    def read(*parts: str) -> str:
        return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())

    def test_the_spec_skill_states_the_contract(self) -> None:
        """No F-NNNN: ticket #92, A2: le skill dit la forme de l'identifiant et le comptage."""
        skill = self.read("skills", "feature-spec", "SKILL.md")
        self.assertIn("`product-source`", skill)
        self.assertIn("export Markdown", skill)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/source_ids.py", skill)
        self.assertIn("avec ou sans tiret", skill)
        self.assertIn("`C01`, `G0`", skill)
        self.assertIn("ne remplace jamais un identifiant d'origine", skill)
        self.assertIn("`ready-for-human`", skill)
        self.assertIn("liste vide", skill)

    def test_the_spec_skill_forbids_an_agent_to_set_an_element_aside(self) -> None:
        """No F-NNNN: ticket #92, A4: seul l'auteur de la source écarte, par écrit, et la spec cite l'accord."""
        skill = self.read("skills", "feature-spec", "SKILL.md")
        self.assertIn("Un agent n'écarte jamais un élément", skill)
        self.assertIn("`source-author`", skill)
        self.assertIn("Écarté : <identifiant> | accord : <fichier> | <AAAA-MM-JJ> | <rôle>", skill)

    def test_the_spec_template_has_the_section_of_the_source_elements(self) -> None:
        """No F-NNNN: ticket #92, A2: le gabarit de spec porte les éléments de la source et leurs identifiants."""
        template = self.read("templates", "features", "spec.md")
        self.assertIn("Éléments de la source", template)
        self.assertIn("Écarté : <identifiant> | accord : <fichier> | <AAAA-MM-JJ> | <rôle>", template)

    def test_the_usine_template_documents_source_author(self) -> None:
        """No F-NNNN: ticket #92, A5: la clé source-author est dans le gabarit, clé absente comprise."""
        template = self.read("templates", "usine.md")
        self.assertIn("- `source-author` : `<", template)
        self.assertIn("aucun élément ne s'écarte", template)
        self.assertIn("sans objet (clé `source-author` absente)", template)

    def test_the_configuration_page_tells_it(self) -> None:
        """No F-NNNN: ticket #92, A5: la page de configuration cite la clé et le script."""
        page = " ".join((support.REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8").split())
        self.assertIn("`source-author`", page)
        self.assertIn("source_ids.py", page)


class UiLabels(unittest.TestCase):
    """Ticket #98: the labels a PR adds on screen are confronted with the glossary and forbidden words."""

    @staticmethod
    def read(*parts: str) -> str:
        return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())

    def test_the_template_documents_the_two_keys(self) -> None:
        """No F-NNNN: ticket #98, A1: ui-labels et ui-forbidden-word sont documentées dans le gabarit."""
        template = self.read("templates", "usine.md")
        self.assertIn("- `ui-labels` : `<", template)
        self.assertIn("- `ui-forbidden-word` : `<", template)
        self.assertIn("sans objet (clé `ui-labels` absente)", template)
        self.assertIn("sans objet (clé `ui-forbidden-word` absente)", template)

    def test_the_gate_runs_the_script_on_the_diff_with_the_keys_of_the_base(self) -> None:
        """No F-NNNN: ticket #98, A2: une sonde de qc-gate lance le script, sans avis."""
        gate = self.read("agents", "qc-gate.md")
        section = gate[gate.index("**Libellés de l'écran.**"):]
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/ui_labels.py", section)
        self.assertIn("usine-base.md", section)
        self.assertIn("pr.diff", section)
        self.assertIn("sans objet (clé ui-labels absente)", section)
        self.assertIn("verbatim", section)

    def test_the_gate_probe_points_at_the_scratchpad_where_the_files_are_kept(self) -> None:
        """No F-NNNN: ticket #106, A3: la commande de la sonde 12 vise le diff et usine-base.md du scratchpad."""
        gate = self.read("agents", "qc-gate.md")
        section = gate[gate.index("**Libellés de l'écran.**"):]
        command = section[section.index("ui_labels.py"):]
        command = command[:command.index("`")]
        self.assertIn('--usine "<scratchpad>/usine-base.md"', command)
        self.assertIn('"<scratchpad>/pr.diff"', command)
        self.assertIn("--root .", command)
        self.assertNotIn("--usine usine-base.md", command)

    def test_the_judge_looks_for_the_line_of_a_forbidden_label_in_the_diff(self) -> None:
        """No F-NNNN: ticket #106, A4: une ligne FORBIDDEN ne porte pas de numéro, qc-conf le cherche dans le diff."""
        judge = self.read("agents", "qc-conf.md")
        section = judge[judge.index("## Lecture des libellés de l'écran"):judge.index("## Forme d'un constat")]
        self.assertIn("ne porte pas de numéro de ligne", section)
        self.assertIn("cherche", section)
        self.assertIn("dans le diff", section)

    def test_the_judge_makes_a_forbidden_word_a_blocker(self) -> None:
        """No F-NNNN: ticket #98, A3: qc-conf rend un BLOCKER pour un mot refusé."""
        judge = self.read("agents", "qc-conf.md")
        section = judge[judge.index("## Lecture des libellés de l'écran"):]
        self.assertIn("`FORBIDDEN`", section)
        self.assertIn("`BLOCKER`", section)
        self.assertIn("`UNKNOWN`", section)
        self.assertIn("`MINOR`", section)

    def test_the_configuration_page_tells_it(self) -> None:
        """No F-NNNN: ticket #98, A1: la page de configuration cite les deux clés et le script."""
        page = " ".join((support.REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8").split())
        self.assertIn("`ui-labels`", page)
        self.assertIn("`ui-forbidden-word`", page)
        self.assertIn("ui_labels.py", page)


class ArchitectureDiagram(unittest.TestCase):
    def test_the_svg_export_carries_every_text_of_the_excalidraw_source(self) -> None:
        # Ticket 4: the diagram shows the domain arbiter and the owner notified on OPEN; the
        # export the README displays must not lag behind its source.
        docs = support.REPO_ROOT / "docs"
        source = json.loads((docs / "architecture.excalidraw").read_text(encoding="utf-8"))
        svg = (docs / "architecture.svg").read_text(encoding="utf-8")
        texts = [element["text"] for element in source["elements"] if element["type"] == "text"]
        self.assertIn("domain-arbiter", " ".join(texts))
        self.assertIn("domain-owner", " ".join(texts))
        for text in texts:
            for line in text.splitlines():
                with self.subTest(line=line):
                    self.assertIn(line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), svg)


    def test_the_diagram_shows_that_a_never_weaken_change_stops_the_merge_like_a_protected_path(self) -> None:
        # Ticket #5: the review box says a human merges, for a protected path or a never-weaken one.
        docs = support.REPO_ROOT / "docs"
        source = json.loads((docs / "architecture.excalidraw").read_text(encoding="utf-8"))
        boxes = [
            element["text"].replace("\n", " ")
            for element in source["elements"]
            if element["type"] == "text" and element.get("containerId") == "prot"
        ]
        self.assertEqual(len(boxes), 1)
        self.assertIn("chemin protégé", boxes[0])
        self.assertIn("never-weaken", boxes[0])
        self.assertIn("un humain fusionne", boxes[0])


class AttentionLabel(unittest.TestCase):
    def test_qc_removes_the_attention_label_once_its_reason_no_longer_holds(self) -> None:
        # Demande directe. A label left after its reason is gone (a FAILED review rerun and
        # merged) alerts the human for nothing; one taken off a protected path would let a PR
        # that a human must merge look settled.
        skill = " ".join((support.PLUGIN / "skills" / "qc" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertNotIn("Ne la retire jamais", skill)
        self.assertIn("Retire-la quand la raison écrite dans `Attention` ne tient plus", skill)
        self.assertIn("Sur une PR qui touche un chemin protégé, elle reste jusqu'à la fusion humaine", skill)
        self.assertIn("**Attention :** aucune | une raison par needs-your-attention | retirée : <raison>", skill)

    def test_qc_leaves_an_attention_label_no_agent_text_explains(self) -> None:
        # The agent acts under the human's account: the label's author on GitHub cannot tell
        # them apart, so an agent text giving the reason is the only mark of an agent's label.
        # Without that bound, a label the human set with a comment would read as "no reason
        # left" and be taken off before the human was read.
        skill = " ".join((support.PLUGIN / "skills" / "qc" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn(
            "Retire seulement une étiquette dont un agent a écrit la raison, dans la ligne `Attention` "
            "d'un `Rapport d'agent` ou dans un commentaire de revue `FAILED`",
            skill,
        )
        self.assertIn("Une étiquette dont aucun texte d'agent ne donne la raison vient d'un humain : elle reste", skill)


class OneSessionPerRepository(unittest.TestCase):
    """ikoro-labs/forge#4: one session acts on a repository at a time."""

    def test_feature_build_checks_the_registry_before_list_agents_then_hands_over_and_stops(self) -> None:
        # Critère 3. The registry sees every session of the repository, interactive ones
        # included; ListAgents comes second, then the request goes to the session in place.
        skill = (support.PLUGIN / "skills" / "feature-build" / "SKILL.md").read_text(encoding="utf-8")
        step = skill.split("## 0.", 1)[1].split("\n## ", 1)[0]
        point = re.search(r"^5\. (.*?)(?=^\d+\. )", step, re.DOTALL | re.MULTILINE)
        self.assertIsNotNone(point, "step 0 has no point 5")
        text = " ".join((point.group(1) if point else "").split())
        self.assertTrue(text.startswith("**Une seule session par projet.**"), text)
        command = 'uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/hooks/handoff_header.py" sessions'
        self.assertIn(command, text)
        for later in ("`ListAgents`", "`SendMessage`"):
            self.assertIn(later, text)
        self.assertLess(text.index(command), text.index("`ListAgents`"))
        self.assertLess(text.index("`ListAgents`"), text.index("`SendMessage`"))
        self.assertIn("code 6", text)
        self.assertIn("tu t'arrêtes", text[text.index("`SendMessage`"):])

    def test_feature_build_lets_the_interactive_session_take_over_from_a_background_one(self) -> None:
        # MINOR 1 of #36, decision 1: the background session drains then stops, and the user's
        # interactive session is its successor in effect; the background session's conduct is
        # in what projects load, not only in this repository's docs/sessions.md.
        skill = (support.PLUGIN / "skills" / "feature-build" / "SKILL.md").read_text(encoding="utf-8")
        step = skill.split("## 0.", 1)[1].split("\n## ", 1)[0]
        point = re.search(r"^5\. (.*?)(?=^\d+\. )", step, re.DOTALL | re.MULTILINE)
        text = " ".join((point.group(1) if point else "").split())
        hooks = 'uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/hooks/'
        own_kind = hooks + 'handoff_header.py" self'
        handover = hooks + 'handoff_trigger.py" yield'
        for expected in (own_kind, "`interactive <ton identifiant>`", "`bg`", handover, "successeur de fait", "`successor-ok`"):
            self.assertIn(expected, text)
        interactive = text[text.index(own_kind):]
        self.assertLess(interactive.index("`SendMessage`"), interactive.index(handover))
        background = text[text.index("**Tu es de fond et une session interactive te demande de céder**"):]
        for conduct in ("ne lances plus rien", "laisses finir tes agents", "passation", "t'arrêtes en le disant"):
            self.assertIn(conduct, background)
        # BLOCKER of round 1 on #37: the background session that yields is closed, after its
        # handoff names the interactive session and is sent to it, and the interactive side knows it.
        closing = "`handoff_relay.py --yield` arrête et supprime ta session"
        self.assertIn(closing, background)
        self.assertLess(background.index("`SendMessage`"), background.index(closing))
        self.assertIn("`CLAUDE_HANDOFF_CLOSE_DELAY`", interactive[: interactive.index("**Sinon**")])

    def test_the_sessions_doc_states_the_common_rule_and_the_relay_code_6(self) -> None:
        # Critère 4.
        readme = (support.REPO_ROOT / "docs" / "sessions.md").read_text(encoding="utf-8")
        self.assertIn("\n## Règles communes\n", readme)
        rules = " ".join(readme.split("\n## Règles communes\n", 1)[1].split("\n## ", 1)[0].split())
        for expected in (
            "**Une session par dépôt.**",
            "**Le premier geste**",
            "handoff_header.py sessions",
            "`ListAgents`",
            "`SendMessage`",
            "draine puis s'arrête",
            "successeur de fait",
            "`claude attach <id>`",
            "`claude agents --json`",
            "code 6",
            "Essayé sous Linux",
            "Windows",
        ):
            self.assertIn(expected, rules)
        relay = readme.split("\n## La passation drainée\n", 1)[1].split("\n## ", 1)[0]
        codes = re.findall(r"^\| (\d) \|", relay, re.MULTILINE)
        self.assertEqual(codes, ["0", "1", "2", "3", "4", "5", "6"])
        self.assertRegex(relay, r"\| 6 \| [^\n]*autre session")

    def test_the_sessions_doc_says_the_predecessor_of_a_handoff_does_not_count(self) -> None:
        # MINOR 2 of #36: the successor's `sessions` leaves out the `auteur` of its handoff.
        readme = (support.REPO_ROOT / "docs" / "sessions.md").read_text(encoding="utf-8")
        rules = " ".join(readme.split("\n## Règles communes\n", 1)[1].split("\n## ", 1)[0].split())
        for expected in ("l'`auteur` d'une passation du projet", "`CLAUDE_HANDOFF_CLOSE_DELAY`", "sans `auteur`"):
            self.assertIn(expected, rules)

    def test_the_sessions_doc_says_how_the_interactive_session_takes_over(self) -> None:
        # MINOR 1 of #36: docs/sessions.md follows the skill.
        readme = (support.REPO_ROOT / "docs" / "sessions.md").read_text(encoding="utf-8")
        rules = " ".join(readme.split("\n## Règles communes\n", 1)[1].split("\n## ", 1)[0].split())
        for expected in ("handoff_header.py self", "handoff_trigger.py yield", '"kind": "bg"', '"kind": "interactive"'):
            self.assertIn(expected, rules)
        # BLOCKER of round 1 on #37: docs/sessions.md says the background session is closed, and how.
        self.assertIn("`handoff_relay.py --yield <passation>`", rules)
        drained = " ".join(readme.split("\n## La passation drainée\n", 1)[1].split("\n## ", 1)[0].split())
        for expected in ("handoff_relay.py --yield [--force] <passation>", "`claude stop` puis `claude rm`", "sans le code 6"):
            self.assertIn(expected, drained)

    def test_the_plugin_names_no_project_and_no_person(self) -> None:
        # Critère 6: what projects load stays generic.
        # The names stay out of this public repo too: only their SHA-256 is kept, compared word by word.
        forbidden = {
            "0446597c56a0163e2afe9be46c51c889d7b6c0407408c0fcc859eae685d911d5",
            "e1025e9718b1aeb757262510352237eec3651a8f48e523325542b09954fd4bb9",
            "85f5e10431f69bc2a14046a13aabaefc660103b6de7a84f75c4b96181d03f0b5",
        }
        for path in sorted(support.PLUGIN.rglob("*")):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            words = {w for w in re.findall(r"[a-z0-9]+", text.lower())}
            found = [w for w in words if hashlib.sha256(w.encode()).hexdigest() in forbidden]
            with self.subTest(path=str(path.relative_to(support.PLUGIN))):
                self.assertEqual(found, [])


class Manifests(unittest.TestCase):
    def test_the_version_lives_in_plugin_json_only(self) -> None:
        plugin = json.loads((support.PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads(
            (support.REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plugin["name"], "forge")
        self.assertRegex(plugin["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(marketplace["name"], "ikoro-labs")
        entries = {entry["name"]: entry for entry in marketplace["plugins"]}
        self.assertEqual(entries["forge"]["source"], "./plugins/forge")
        for entry in marketplace["plugins"]:
            self.assertNotIn("version", entry)
        self.assertNotIn("version", marketplace.get("metadata", {}))

    def test_the_other_plugins_are_pinned_on_a_tag(self) -> None:
        # The other ikoro-labs plugins live in their own repo: the catalogue pins each one on a tag.
        marketplace = json.loads(
            (support.REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        for entry in marketplace["plugins"]:
            if entry["name"] == "forge":
                continue
            with self.subTest(plugin=entry["name"]):
                self.assertEqual(entry["source"]["source"], "github")
                self.assertTrue(entry["source"]["repo"].startswith("ikoro-labs/"))
                self.assertRegex(entry["source"]["ref"], rf"^{re.escape(entry['name'])}--v\d+\.\d+\.\d+$")

    def test_the_changelog_opens_on_the_plugin_version(self) -> None:
        version = json.loads((support.PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        changelog = (support.REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        first = re.search(r"^## \[?(\d+\.\d+\.\d+)", changelog, re.MULTILINE)
        self.assertIsNotNone(first)
        self.assertEqual(first.group(1) if first else None, version)

    def test_the_icon_is_a_square_png_the_plugin_directory_accepts(self) -> None:
        # The directory takes a PNG of 512 to 2048 px a side, under 2 MB, and no SVG.
        icon = (support.PLUGIN / ".claude-plugin" / "icon.png").read_bytes()
        self.assertEqual(icon[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(icon[12:16], b"IHDR")
        width, height = int.from_bytes(icon[16:20], "big"), int.from_bytes(icon[20:24], "big")
        self.assertEqual(width, height)
        self.assertTrue(512 <= width <= 2048, width)
        self.assertLess(len(icon), 2 * 1024 * 1024)
        self.assertTrue((support.REPO_ROOT / "docs" / "logo.svg").is_file())

    def test_the_repository_root_holds_the_mit_licence_the_manifest_names(self) -> None:
        # The plugin directory looks for the licence at the root of the git repository, not in
        # plugins/forge/; plugin.json names it by its SPDX id.
        licence = support.REPO_ROOT / "LICENSE"
        self.assertTrue(licence.is_file(), "no LICENSE at the repository root")
        text = licence.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("MIT License\n"), text[:40])
        self.assertIn("Copyright (c) 2026 ikoro-labs", text)
        self.assertIn("THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND", text)
        plugin = json.loads((support.PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin.get("license"), "MIT")


class TddSkill(unittest.TestCase):
    """No F-NNNN: ticket #40, the `forge:tdd` skill and its references."""

    SKILL = support.PLUGIN / "skills" / "tdd"

    def read(self, *parts: str) -> str:
        return self.SKILL.joinpath(*parts).read_text(encoding="utf-8")

    def test_the_skill_reads_as_a_plugin_skill_with_its_references(self) -> None:
        """No F-NNNN: ticket #40, critère « le skill se lit comme un skill du plugin »."""
        fields = frontmatter(self.SKILL / "SKILL.md")
        self.assertEqual(fields.get("name"), "tdd")
        self.assertTrue(fields.get("description"))
        self.assertEqual(set(fields) - SKILL_FIELDS, set())
        for reference in ("tests.md", "mocking.md"):
            with self.subTest(reference=reference):
                self.assertTrue((self.SKILL / "references" / reference).is_file())
                self.assertIn(f"references/{reference}", self.read("SKILL.md"))

    def test_the_skill_names_the_three_anti_patterns_and_the_loop(self) -> None:
        """No F-NNNN: ticket #40, critère « il nomme les trois anti-patterns »."""
        text = self.read("SKILL.md").lower()
        for term in ("couplé à l'implémentation", "tautologique", "tranches horizontales"):
            with self.subTest(term=term):
                self.assertIn(term, text)
        for term in ("rouge avant vert", "forge:codebase-design", "glossary", "seam"):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_the_skill_states_the_mock_rule(self) -> None:
        """No F-NNNN: ticket #40, critère « il nomme la règle des mocks »."""
        text = self.read("references", "mocking.md").lower()
        self.assertIn("frontières du système", text)
        self.assertIn("jamais un collaborateur interne", text)
        self.assertIn("injection de dépendance", text)
        self.assertIn("frontières du système", self.read("SKILL.md").lower())

    def test_the_template_offers_it_for_test_skill_without_making_it_a_default(self) -> None:
        """No F-NNNN: ticket #40, critère « le gabarit le cite pour test-skill »."""
        template = (support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8")
        block = template[template.index("Le skill qui dit comment le projet écrit ses tests") :]
        block = block[: block.index("Les règles git")]
        self.assertIn("forge:tdd", block)
        self.assertIn("test-skill", block)
        self.assertIn("sans objet", block)

    def test_the_docs_and_the_readme_cite_it(self) -> None:
        """No F-NNNN: ticket #40, critère « la page de docs et le README le citent »."""
        for path in (support.REPO_ROOT / "README.md", support.REPO_ROOT / "docs" / "contribuer.md"):
            with self.subTest(path=path.name):
                self.assertRegex(path.read_text(encoding="utf-8"), r"(?<![\w-])(/forge:)?tdd(?![\w-])")


class FeatureDesignSlicing(unittest.TestCase):
    """No F-NNNN: ticket #44, le découpage en tickets de `feature-design` et du gabarit de design."""

    @staticmethod
    def step() -> str:
        text = (support.PLUGIN / "skills" / "feature-design" / "SKILL.md").read_text(encoding="utf-8")
        return text.split("6. **Découper**", 1)[1].split("\nCommande suivante", 1)[0]

    @staticmethod
    def section7() -> str:
        text = (support.PLUGIN / "templates" / "features" / "design.md").read_text(encoding="utf-8")
        return text.split("## 7. Découpage en tickets", 1)[1].split("\n## 8.", 1)[0]

    def test_each_ticket_fits_one_fresh_context(self) -> None:
        """No F-NNNN: ticket #44, critère 1 (un ticket tient dans un contexte neuf de coder)."""
        for text in (self.step(), self.section7()):
            self.assertIn("contexte neuf", text)
            self.assertIn("forge:coder", text)

    def test_prerefactoring_comes_first_in_its_own_ticket(self) -> None:
        """No F-NNNN: ticket #44, critère 2 (prérefactoring d'abord, dans son propre ticket)."""
        for text in (self.step(), self.section7()):
            self.assertIn("prérefactoring", text)
            self.assertIn("son propre ticket", text)

    def test_wide_refactoring_goes_expand_migrate_contract(self) -> None:
        """No F-NNNN: ticket #44, critère 3 (refactoring large : expand, lots, contract, bloqués)."""
        for text in (self.step(), self.section7()):
            self.assertIn("refactoring large", text)
            for word in ("expand", "par lots", "contract", "bloqué"):
                self.assertIn(word, text)

    def test_the_slicing_skill_has_a_key_and_the_example_is_gone(self) -> None:
        """No F-NNNN: ticket #44, critère 4 (clé ticket-skill, absente = découpe à la main et le dit)."""
        step = self.step()
        self.assertIn("`ticket-skill`", step)
        self.assertIn("clé `ticket-skill` absente", step)
        self.assertNotIn("/to-tickets", step)
        template = (support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8")
        self.assertIn("- `ticket-skill` :", template)
        docs = (support.REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
        self.assertIn("`ticket-skill`", docs)

    def test_tdd_sends_refactoring_to_the_slicing_not_to_the_review(self) -> None:
        """No F-NNNN: ticket #44, MINOR de #49 (le refactoring ne relève pas de la revue)."""
        text = (support.PLUGIN / "skills" / "tdd" / "SKILL.md").read_text(encoding="utf-8")
        rule = text.split("**Le refactoring est hors de la boucle.**", 1)[1].split("\n", 1)[0]
        self.assertNotIn("relève de la revue", rule)
        self.assertIn("prérefactoring", rule)
        self.assertIn("feature-design", rule)


class PrShowsChangeDoorAndRadius(unittest.TestCase):
    """Ticket #45 : la description de PR montre le changement, dit sa porte et son rayon d'impact."""

    @staticmethod
    def read(*parts: str) -> str:
        return support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8")

    def test_the_coder_writes_a_view_a_door_and_a_radius(self) -> None:
        """No F-NNNN: ticket #45, critère 1 (§5 de coder.md)."""
        text = self.read("agents", "coder.md")
        step = text.split("## 5. Livrer", 1)[1].split("\n## ", 1)[0]
        self.assertIn("vue du changement", step)
        self.assertIn("quelques lignes", step)
        self.assertIn("`double sens`", step)
        self.assertIn("`sens unique`", step)
        self.assertIn("rayon d'impact", step)
        self.assertIn("même quand le gabarit", step)
        self.assertIn("fin du résumé", step)

    def test_a_template_carries_the_sections_and_usine_offers_it_without_defaulting(self) -> None:
        """No F-NNNN: ticket #45, critère 2 (gabarit dans templates/, valeur possible)."""
        template = self.read("templates", "pr.md")
        for heading in ("## Résumé", "## Porte", "## Rayon d'impact", "## Preuves"):
            self.assertIn(heading, template)
        self.assertIn("double sens", template)
        self.assertIn("sens unique", template)
        usine = self.read("templates", "usine.md")
        block = usine.split("Le modèle de description de PR", 1)[1].split("- `pr-template` :", 1)[0]
        self.assertIn("templates/pr.md", block)
        self.assertIn("pas une valeur par défaut", block)
        self.assertIn("- `pr-template` : `<.github/pull_request_template.md>`", usine)

    def test_the_judge_makes_an_undeclared_one_way_door_a_minor(self) -> None:
        """No F-NNNN: ticket #45, critère 3 (qc-conf : MINOR et scénario d'échec)."""
        text = self.read("agents", "qc-conf.md")
        section = text.split("## Porte à sens unique", 1)[1].split("\n## ", 1)[0]
        self.assertIn("`MINOR`", section)
        self.assertIn("scénario d'échec", section)
        self.assertIn("geste", section)
        self.assertIn("one-way-door", section)
        self.assertNotIn("`BLOCKER`", section)


    def test_qc_raises_needs_your_attention_on_a_one_way_door_without_stopping_the_merge(self) -> None:
        """No F-NNNN: ticket #45, critère 4 (qc : alerte sans arrêt de fusion)."""
        text = self.read("skills", "qc", "SKILL.md")
        section = text.split("## Porte à sens unique", 1)[1].split("\n## ", 1)[0]
        self.assertIn("`needs-your-attention`", section)
        self.assertIn("`Attention`", section)
        self.assertIn("one-way-door", section)
        self.assertIn("ne bloque pas la fusion", section)
        self.assertIn("chemins protégés", section)


if __name__ == "__main__":
    unittest.main()
