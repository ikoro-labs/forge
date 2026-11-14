"""guard_coder_model: `forge:coder` runs on sonnet, on opus only at round 3, on haiku only in sync mode."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from guard_coder_model import outcome


def agent(**fields: object) -> dict:
    return {"tool_name": "Agent", "tool_input": {"description": "d", "prompt": "p", **fields}}


def workflow(script: str, **fields: object) -> dict:
    return {"tool_name": "Workflow", "tool_input": {"script": script, **fields}}


META = "export const meta = { name: 'w', description: 'd' }\n"


ESCALATION = "Ticket #12.\nESCALATION: #12 round 3\n"
SYNC = "PR #40.\nMODE: sync\n"


class AgentTool(unittest.TestCase):
    def assert_refused(self, event: dict, *words: str) -> None:
        code, message = outcome(event)
        self.assertEqual(code, 2, message)
        for word in words:
            self.assertIn(word, message)

    def test_a_coder_without_model_nor_effort_passes(self) -> None:
        self.assertEqual(outcome(agent(subagent_type="forge:coder")), (0, ""))

    def test_a_coder_on_sonnet_high_passes(self) -> None:
        self.assertEqual(outcome(agent(subagent_type="forge:coder", model="sonnet", effort="high")), (0, ""))

    def test_opus_passes_only_with_the_escalation_line(self) -> None:
        self.assertEqual(outcome(agent(subagent_type="forge:coder", model="opus", prompt=ESCALATION)), (0, ""))
        for prompt in ("p", "ESCALATION: #12 round 2", "say ESCALATION: #12 round 3 inline", "ESCALATION: 12 round 3"):
            with self.subTest(prompt=prompt):
                self.assert_refused(agent(subagent_type="forge:coder", model="opus", prompt=prompt), "`model: opus`", "ESCALATION")

    def test_haiku_passes_only_with_the_sync_line(self) -> None:
        self.assertEqual(outcome(agent(subagent_type="forge:coder", model="haiku", prompt=SYNC)), (0, ""))
        for prompt in ("p", "MODE: build", "MODE: sync please"):
            with self.subTest(prompt=prompt):
                self.assert_refused(agent(subagent_type="forge:coder", model="haiku", prompt=prompt), "`model: haiku`", "MODE: sync")

    def test_any_other_model_is_refused(self) -> None:
        for model in ("fable", "claude-sonnet-5-5", "inherit", ""):
            with self.subTest(model=model):
                self.assert_refused(agent(subagent_type="forge:coder", model=model, prompt=ESCALATION + SYNC), f"`model: {model}`")

    def test_an_effort_other_than_high_is_refused(self) -> None:
        for effort in ("low", "medium", "xhigh", "max"):
            with self.subTest(effort=effort):
                self.assert_refused(agent(subagent_type="forge:coder", effort=effort), f"`effort: {effort}`", "high")

    def test_the_old_tool_name_and_the_bare_agent_name_are_held(self) -> None:
        self.assert_refused({"tool_name": "Task", "tool_input": {"subagent_type": "forge:coder", "model": "opus"}}, "opus")
        self.assert_refused(agent(subagent_type="coder", effort="medium"), "medium")

    def test_another_agent_keeps_its_choice(self) -> None:
        self.assertEqual(outcome(agent(subagent_type="forge:qc-gate", model="haiku", effort="low")), (0, ""))
        self.assertEqual(outcome(agent(subagent_type="forge:qc-conf", model="opus")), (0, ""))


class WorkflowTool(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        patch = mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root), "CLAUDE_CONFIG_DIR": str(self.root / "home")})
        patch.start()
        self.addCleanup(patch.stop)

    def assert_refused(self, event: dict, *words: str) -> None:
        code, message = outcome({**event, "cwd": str(self.root)})
        self.assertEqual(code, 2, message)
        for word in words:
            self.assertIn(word, message)

    def assert_passes(self, event: dict) -> None:
        self.assertEqual(outcome({**event, "cwd": str(self.root)}), (0, ""))

    def test_a_coder_without_override_passes(self) -> None:
        self.assert_passes(workflow(META + "await agent('code #12', {agentType: 'forge:coder', label: 'x'})"))
        self.assert_passes(workflow(META + 'await agent("t", {agentType: "forge:coder", model: "sonnet", effort: "high"})'))
        self.assert_passes(workflow(META + "await agent('PR #4\\nMODE: sync', {agentType: 'coder', model: 'haiku'})"))
        self.assert_passes(workflow(META + "await agent(`#4\nESCALATION: #4 round 3`, {agentType: 'coder', model: 'opus'})"))

    def test_a_coder_on_another_model_or_effort_is_refused(self) -> None:
        self.assert_refused(workflow(META + "await agent('t', {agentType: 'forge:coder', model: 'opus'})"), "ESCALATION")
        self.assert_refused(workflow(META + "await agent('t', {agentType: 'forge:coder', model: 'fable'})"), "fable")
        self.assert_refused(workflow(META + "await agent(`t ${x}`, {\n  effort: 'medium',\n  agentType: 'coder',\n})"), "medium")

    def test_a_coder_in_a_pipeline_stage_is_held(self) -> None:
        script = META + "await pipeline(items, i => agent('do', {agentType: 'forge:coder', model: 'haiku'}))"
        self.assert_refused(workflow(script), "haiku")

    def test_a_prompt_the_guard_cannot_read_is_refused_when_the_model_needs_a_line(self) -> None:
        for prompt in ("`MODE: sync ${i}`", "p", "'a' + 'MODE: sync'"):
            with self.subTest(prompt=prompt):
                self.assert_refused(workflow(META + f"await agent({prompt}, {{agentType: 'forge:coder', model: 'haiku'}})"), "prompt")
        self.assert_passes(workflow(META + "await agent(p, {agentType: 'forge:coder', model: 'sonnet'})"))

    def test_options_the_guard_cannot_read_are_refused_when_a_coder_may_run(self) -> None:
        cases = {
            "const o = {agentType: 'forge:coder'}\nawait agent('t', o)": "not an object literal",
            "await agent('t', {...base, agentType: 'forge:coder'})": "spread",
            "const t = 'forge:coder'\nawait agent('t', {agentType: t})": "agentType",
            "await agent('t', {agentType: 'forge:coder', model: pick()})": "model",
            "await agent('t', {agentType: 'forge:coder', model: `${m}`})": "model",
            "await agent('t', {agentType: 'forge:coder', effort})": "effort",
        }
        for body, word in cases.items():
            with self.subTest(body=body):
                self.assert_refused(workflow(META + body), word)

    def test_a_coder_named_in_args_makes_variables_unreadable(self) -> None:
        self.assert_refused(workflow(META + "await agent('t', {agentType: args.kind})", args={"kind": "forge:coder"}), "agentType")

    def test_a_script_that_names_no_coder_keeps_its_variables(self) -> None:
        self.assert_passes(workflow(META + "await parallel(T.map(t => () => agent('r', {agentType: t, model: 'sonnet'})))"))
        self.assert_passes(workflow(META + "// the coder is not here\nawait agent('r', {model: 'haiku'})"))

    def test_a_script_file_and_a_saved_workflow_are_read(self) -> None:
        path = self.root / "w.js"
        path.write_text(META + "await agent('t', {agentType: 'forge:coder', effort: 'low'})", encoding="utf-8")
        self.assert_refused({"tool_name": "Workflow", "tool_input": {"scriptPath": "w.js"}}, "low")
        saved = self.root / ".claude" / "workflows"
        saved.mkdir(parents=True)
        (saved / "build.js").write_text(META.replace("'w'", "'build'") + "await agent('t', {agentType: 'coder', model: 'opus'})", encoding="utf-8")
        self.assert_refused({"tool_name": "Workflow", "tool_input": {"name": "build"}}, "opus")

    def test_a_missing_script_file_is_refused_and_a_builtin_workflow_passes(self) -> None:
        self.assert_refused({"tool_name": "Workflow", "tool_input": {"scriptPath": "absent.js"}}, "cannot be read")
        self.assert_passes({"tool_name": "Workflow", "tool_input": {"name": "deep-research", "args": "q"}})

    def test_a_child_workflow_is_read_and_one_the_guard_cannot_name_is_refused(self) -> None:
        (self.root / "child.js").write_text(META + "await agent('t', {agentType: 'forge:coder', model: 'fable'})", encoding="utf-8")
        self.assert_refused(workflow(META + "await workflow({scriptPath: 'child.js'})"), "fable")
        self.assert_refused(workflow(META + "await workflow(which)"), "workflow(")

    def test_a_script_the_guard_cannot_scan_passes_only_without_a_coder(self) -> None:
        self.assert_passes(workflow(META + "const r = /it's/\nawait agent('r', {model: 'haiku'})"))
        self.assert_refused(workflow(META + "const r = /it's/\nawait agent('r', {agentType: 'forge:coder'})"), "string")

    def test_a_string_or_comment_does_not_open_a_call(self) -> None:
        self.assert_passes(workflow(META + "log('agent(x, y)')\n/* agent('t', {agentType: 'forge:coder', model: 'opus'}) */"))


class Wiring(unittest.TestCase):
    def test_hooks_json_runs_the_guard_on_agent_task_and_workflow(self) -> None:
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        entries = [e for e in hooks["hooks"]["PreToolUse"] if "guard_coder_model.py" in e["hooks"][0]["command"]]
        self.assertEqual([e["matcher"] for e in entries], ["Agent|Task|Workflow"])
        self.assertTrue(entries[0]["hooks"][0]["command"].endswith("|| exit 2"))


if __name__ == "__main__":
    unittest.main()
