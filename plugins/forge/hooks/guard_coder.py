"""PreToolUse hook of the `forge:coder` agent: the acts that belong to the orchestrator.

Plugin hooks run for every agent, so this one first reads `agent_type` and lets any other
agent through. For the coder, it refuses, with the reason on stderr and exit code 2:

- `gh pr merge` and `gh pr review`: qc judges and merges, through two agents the coder cannot
  launch;
- `gh issue close` and `gh issue edit`: the ticket's state, labels and assignees are
  `/forge:feature-build`'s, which is how it tells its claim from a human's (`agent-claimed`);
- the qc skill, under its plugin name `forge:qc` as under a bare `qc`, which the coder would
  otherwise run as the last step of opening a PR.

The command is parsed with `guard_git`'s splitter, so a commit message that says
`gh pr merge` is data. As there, this guards against an accident, not against intent: a wrapper
(`env gh`, `gh.exe`) or `gh api` on the same endpoint is intent and is left alone.
An event the hook cannot read is refused, and `hooks.json` turns any crash into a refusal.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping

from guard_git import gh_act, segments

CODER = "forge:coder"
REFUSED_GH = {
    ("pr", "merge"): "`gh pr merge`: qc merges, once its two agents have judged the PR",
    ("pr", "review"): "`gh pr review`: qc judges, never the agent that coded the PR",
    ("issue", "close"): "`gh issue close`: the ticket's state is the orchestrator's",
    ("issue", "edit"): "`gh issue edit`: the ticket's labels and assignees are the orchestrator's",
}
QC_SKILLS = frozenset({"qc", "forge:qc"})
REFUSED_SKILL = (
    "the qc skill: the coder cannot launch qc-gate and qc-conf, so it would judge and merge its"
    " own PR alone; the orchestrator runs qc"
)


def refusal(tool_name: str, tool_input: Mapping[str, object]) -> str | None:
    """Why the coder may not make this call, or None when it may."""
    if tool_name == "Skill":
        skill = str(tool_input.get("skill", "")).strip().lstrip("/")
        return REFUSED_SKILL if skill in QC_SKILLS else None
    for words in segments(str(tool_input.get("command", ""))):
        act = gh_act(words)
        if act is not None and (reason := REFUSED_GH.get(act[:2])):
            return reason
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        event = None
    tool_input = event.get("tool_input") if isinstance(event, dict) else None
    if not isinstance(event, dict) or not isinstance(tool_input, dict):
        # Fail closed: an event this hook cannot read is a call it cannot clear.
        reason: str | None = "the hook could not read the tool call it was given"
    elif event.get("agent_type") != CODER:
        return 0
    else:
        reason = refusal(str(event.get("tool_name", "")), tool_input)
    if reason is None:
        return 0
    sys.stderr.write(f"Blocked by the coder's guard (forge plugin): {reason}.\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
