"""The agents and skills are well formed, and every `forge:<name>` the plugin cites exists."""

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


class Manifests(unittest.TestCase):
    def test_the_version_lives_in_plugin_json_only(self) -> None:
        plugin = json.loads((support.PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads(
            (support.REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(plugin["name"], "forge")
        self.assertRegex(plugin["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(marketplace["name"], "ikoro-labs")
        self.assertEqual([entry["name"] for entry in marketplace["plugins"]], ["forge"])
        self.assertEqual(marketplace["plugins"][0]["source"], "./plugins/forge")
        self.assertNotIn("version", marketplace["plugins"][0])
        self.assertNotIn("version", marketplace.get("metadata", {}))

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


if __name__ == "__main__":
    unittest.main()
