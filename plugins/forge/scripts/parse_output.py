"""Read the coder's RESULT block, qc-conf's verdict or the domain arbiter's answer, and say exactly
what is wrong with it.

    python parse_output.py result <file | ->
    python parse_output.py verdict <file | ->
    python parse_output.py domain <file | ->

On success, prints the block as JSON and exits 0. On failure, prints the first problem found
and exits 1: the skill that launched the agent relaunches it once with that sentence, then
reports FAILED. The standard library only, so it runs wherever the hooks run.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

KEY = re.compile(r"^([A-Z][A-Z_ ]*[A-Z]):[ \t]?(.*)$")
FENCE = re.compile(r"^```[\w-]*\s*$")
FINDING = re.compile(r"^-\s*\[(BLOCKER|MINOR|NOTE)\]\s*(.+)$")
HEAD = re.compile(r"^[0-9a-f]{7,40}$")
NO_TICKET = re.compile(r"^none \(\s*\S.*\)$", re.DOTALL)
# Every refusal of a `SPEC:` line names both admitted forms: the relaunched judge fixes either one.
SPEC_FORMS = (
    "`SPEC:` reads one `#<ticket>: ...` line per ticket, "
    "or the one line `none (<reason>)` when the PR has no ticket"
)

RESULT_KEYS = {
    "PR": ("PR", "TICKET", "CRITERIA", "NOTES"),
    "BLOCKED": ("TICKET", "QUESTION", "RECOMMENDATION", "STATE"),
    "FAILED": ("TICKET", "COMMAND", "OUTPUT", "STATE"),
}
VERDICT_KEYS = ("VERDICT", "ROUND", "HEAD", "SPEC", "FINDINGS", "GATES")
VERDICT_OPTIONAL = ("BATTERY CORRECTION",)
REPEATED = frozenset({"SPEC"})
# The domain arbiter's answer: the keys each `ANSWER:` takes after `QUESTION:`.
DOMAIN_KEYS = {
    "DECIDED": ("DECISION", "SOURCE"),
    "INFERRED": ("DECISION", "SOURCE"),
    "OPEN": ("OPTIONS", "RECOMMENDATION", "PRUDENT_PATH"),
    "NOT_DOMAIN": ("DECIDER",),
}


class OutputError(ValueError):
    """The block does not have the form its reader expects."""


def _fields(text: str, first: str, known: set[str]) -> dict[str, list[str]]:
    """Key lines and their continuations, from the last line that starts with `first:` on."""
    lines = [line.rstrip() for line in text.strip().splitlines()]
    lines = [line for line in lines if not FENCE.match(line)]
    starts = [index for index, line in enumerate(lines) if line.startswith(f"{first}:")]
    if not starts:
        raise OutputError(f"no line starts with `{first}:`: the block is missing")
    # Prose the agent wrote before its block is not part of it; the last block is the answer.
    lines = lines[starts[-1] :]
    fields: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in lines:
        match = KEY.match(line)
        if match and match.group(1) in known:
            key, value = match.group(1), match.group(2).strip()
            if key in fields and key not in REPEATED:
                raise OutputError(f"`{key}:` appears twice")
            fields.setdefault(key, [])
            current = fields[key]
            current.append(value)
        elif current is None:
            raise OutputError(f"unexpected line before the first key: `{line}`")
        elif line.strip():
            current[-1] = f"{current[-1]}\n{line.strip()}".strip()
    return fields


def parse_result(text: str) -> dict[str, str]:
    known = {"RESULT", *(key for keys in RESULT_KEYS.values() for key in keys)}
    fields = _fields(text, "RESULT", known)
    kind = fields["RESULT"][0]
    if kind not in RESULT_KEYS:
        raise OutputError(f"`RESULT: {kind}`: the value must be PR, BLOCKED or FAILED")
    expected = RESULT_KEYS[kind]
    for key in expected:
        if key not in fields or not fields[key][0]:
            raise OutputError(f"`RESULT: {kind}` needs a non-empty `{key}:` line")
    extra = sorted(set(fields) - {"RESULT", *expected})
    if extra:
        raise OutputError(f"`RESULT: {kind}` takes no `{extra[0]}:` line")
    ticket = fields["TICKET"][0]
    if not re.match(r"^#\d+\b", ticket):
        raise OutputError(f"`TICKET: {ticket}`: it must start with `#<number>`")
    if kind == "PR":
        if not re.fullmatch(r"#\d+", fields["PR"][0]):
            raise OutputError(f"`PR: {fields['PR'][0]}`: it must be `#<number>`")
        if not re.match(r"^#\d+\s+(closes|refs)\b", ticket):
            raise OutputError(f"`TICKET: {ticket}`: a PR result says `closes` or `refs`")
    return {"RESULT": kind, **{key: fields[key][0] for key in expected}}


def parse_verdict(text: str) -> dict[str, object]:
    fields = _fields(text, "VERDICT", {*VERDICT_KEYS, *VERDICT_OPTIONAL})
    for key in VERDICT_KEYS:
        if key not in fields:
            raise OutputError(f"the verdict needs a `{key}:` line")
    verdict, round_, head = fields["VERDICT"][0], fields["ROUND"][0], fields["HEAD"][0]
    if verdict not in ("ACCEPT", "REJECT"):
        raise OutputError(f"`VERDICT: {verdict}`: the value must be ACCEPT or REJECT")
    if round_ not in ("1", "2"):
        raise OutputError(f"`ROUND: {round_}`: the value must be 1 or 2")
    if not HEAD.match(head):
        raise OutputError(f"`HEAD: {head}`: it must be the hexadecimal SHA of the judged head")
    specs = fields["SPEC"]
    # A PR with no ticket (a Dependabot bump, a pin bump) says so, and against what it was judged.
    if any(re.match(r"^none\b", spec) for spec in specs):
        if len(specs) > 1:
            raise OutputError(
                "`SPEC: none` stands alone: a verdict that judges a ticket has none. " + SPEC_FORMS
            )
        if not NO_TICKET.match(specs[0]):
            raise OutputError(
                f"`SPEC: {specs[0]}`: the reason is missing, it says what the PR was judged "
                "against. " + SPEC_FORMS
            )
    for spec in specs:
        if not re.match(r"^(#\d+\b|none\b)", spec):
            raise OutputError(
                f"`SPEC: {spec}`: the line starts with neither `#<ticket>` nor `none`. " + SPEC_FORMS
            )
    findings: list[dict[str, str]] = []
    for line in fields["FINDINGS"][0].splitlines():
        line = line.strip()
        if not line or line.lower() in ("none", "aucun", "- none", "- aucun"):
            continue
        match = FINDING.match(line)
        if match is None:
            raise OutputError(f"finding `{line}`: it must read `- [BLOCKER|MINOR|NOTE] ...`")
        findings.append({"severity": match.group(1), "text": match.group(2)})
    blockers = sum(finding["severity"] == "BLOCKER" for finding in findings)
    if verdict == "REJECT" and not blockers:
        raise OutputError("`VERDICT: REJECT` with no `[BLOCKER]` finding: only a blocker rejects")
    if verdict == "ACCEPT" and blockers:
        raise OutputError(f"`VERDICT: ACCEPT` with {blockers} `[BLOCKER]` finding(s)")
    return {
        "VERDICT": verdict,
        "ROUND": int(round_),
        "HEAD": head,
        "SPEC": fields["SPEC"],
        "FINDINGS": findings,
        "GATES": fields["GATES"][0],
        "BATTERY CORRECTION": fields.get("BATTERY CORRECTION", [""])[0],
    }


def parse_domain(text: str) -> dict[str, str]:
    known = {"ANSWER", "QUESTION", *(key for keys in DOMAIN_KEYS.values() for key in keys)}
    fields = _fields(text, "ANSWER", known)
    kind = fields["ANSWER"][0]
    if kind not in DOMAIN_KEYS:
        raise OutputError(f"`ANSWER: {kind}`: the value must be DECIDED, INFERRED, OPEN or NOT_DOMAIN")
    expected = ("QUESTION", *DOMAIN_KEYS[kind])
    for key in expected:
        if key not in fields or not fields[key][0]:
            raise OutputError(f"`ANSWER: {kind}` needs a non-empty `{key}:` line")
    extra = sorted(set(fields) - {"ANSWER", *expected})
    if extra:
        raise OutputError(f"`ANSWER: {kind}` takes no `{extra[0]}:` line")
    return {"ANSWER": kind, **{key: fields[key][0] for key in expected}}


PARSERS = {"result": parse_result, "verdict": parse_verdict, "domain": parse_domain}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in PARSERS:
        sys.stderr.write("usage: parse_output.py result|verdict|domain <file | ->\n")
        return 2
    text = sys.stdin.read() if argv[1] == "-" else Path(argv[1]).read_text(encoding="utf-8")
    try:
        parsed = PARSERS[argv[0]](text)
    except OutputError as error:
        print(f"invalid {argv[0]}: {error}")
        return 1
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
