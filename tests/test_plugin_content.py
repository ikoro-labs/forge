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
                self.assertRegex(entry["source"]["ref"], r"^v\d+\.\d+\.\d+$")

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


if __name__ == "__main__":
    unittest.main()
