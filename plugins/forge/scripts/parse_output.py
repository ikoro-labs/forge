"""Read the coder's RESULT block, qc-conf's verdict or the domain arbiter's answer, and say exactly
what is wrong with it.

    python parse_output.py result <file | ->
    python parse_output.py verdict <file | -> [--replay <file>] [--rewrite <file>]
    python parse_output.py domain <file | ->

On success, prints the block as JSON and exits 0. On failure, prints the first problem found
and exits 1: the skill that launched the agent relaunches it once with that sentence, then
reports FAILED. The standard library only, so it runs wherever the hooks run.

The counting rule of a `[BLOCKER]`. A blocker that rests on an execution carries its probe as a last
field, `probe: `<test file of the head>` => `<expected output>``, and `probe_replay.py` replays it by
the command of the key `red-replay`. The probe is a name, never a command: a path from the root of the
repository, made of ASCII letters, digits and `._/-`, that is not absolute, has no `..` part and does
not start with `-` or `.`. Any other name is refused here (exit code 1) and nothing runs. A blocker with
no probe rests on a reading of the code: it counts and is marked `déduit`. With `--replay <file>`
(the lines `probe_replay.py` printed), a probed blocker counts only once its probe was replayed:
`CONFIRMED` keeps it (`confirmé`), `NOT REPRODUCED` makes it a `[NOTE]` marked `non reproduit`, which
no longer rejects, `REFUSED` (the name is not a test file of the head) sends the verdict back to its
judge (exit code 1), and any other state (`NOT RUN`, no line) leaves it unsettled: exit code 3, the
verdict does not stand yet. `--rewrite <file>` writes the verdict as it stands after the replay, the
demoted blockers as notes and a `REJECT` left with no blocker as `ACCEPT`.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

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
VERDICT_OPTIONAL = ("SOCLE", "GRANTED", "BATTERY CORRECTION", "PROPOSAL")
# Three rounds at most; a later round names the human's grant by its https link.
MAX_ROUNDS = 3
ROUND = re.compile(r"^[1-9]\d*$")
GRANT = re.compile(r"^https://\S+$")
# A case proposed for the next tickets: `<input> | <expected result>`; it never blocks.
PROPOSAL = re.compile(r"^[^|]*\S[^|]*\|.*\S.*$")
REPEATED = frozenset({"SPEC", "PROPOSAL"})
# The domain arbiter's answer: the keys each `ANSWER:` takes after `QUESTION:`.
DOMAIN_KEYS = {
    "DECIDED": ("DECISION", "SOURCE"),
    "INFERRED": ("DECISION", "SOURCE"),
    "OPEN": ("OPTIONS", "RECOMMENDATION", "PRUDENT_PATH"),
    "NOT_DOMAIN": ("DECIDER",),
}


class OutputError(ValueError):
    """The block does not have the form its reader expects."""


class ReplayError(OutputError):
    """A probe of a blocker has no usable replay: the blocker cannot count yet (exit code 3)."""


# A blocker's probe, its last field: a test file of the head, then the output its run must print.
PROBE = re.compile(r"^probe:\s*`([^`]+)`\s*=>\s*`([^`]+)`$", re.IGNORECASE)
PROBE_FORM = "`probe: `<test file of the head>` => `<expected output>``"
# A probe name reaches a shell only as an argument of the `red-replay` command, quoted: still, only these
# characters pass, so that no name can carry a shell character, an option or a way out of the head.
PROBE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")
MARKS = {"deduced": "déduit", "confirmed": "confirmé", "demoted": "non reproduit"}
# The lines `probe_replay.py` prints, one per blocker: `<status>\t<finding number>\t<detail>`.
REPLAY_STATUSES = ("CONFIRMED", "NOT REPRODUCED", "REFUSED", "NOT RUN", "DEDUCED", "NONE")


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
        if match and match.group(1) not in known:
            # The set of keys is closed: a key the block does not take is refused, never folded
            # into the key above it.
            raise OutputError(f"`{match.group(1)}:` is not a key of this block")
        if match:
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


def parse_result(text: str, extra: tuple[str, ...] = ()) -> dict[str, str]:
    """The coder's block; `extra` names the further keys a project's coder writes."""
    known = {"RESULT", *(key for keys in RESULT_KEYS.values() for key in keys), *extra}
    fields = _fields(text, "RESULT", known)
    kind = fields["RESULT"][0]
    if kind not in RESULT_KEYS:
        raise OutputError(f"`RESULT: {kind}`: the value must be PR, BLOCKED or FAILED")
    expected = RESULT_KEYS[kind]
    for key in expected:
        if key not in fields or not fields[key][0]:
            raise OutputError(f"`RESULT: {kind}` needs a non-empty `{key}:` line")
    unexpected = sorted(set(fields) - {"RESULT", *expected, *extra})
    if unexpected:
        raise OutputError(f"`RESULT: {kind}` takes no `{unexpected[0]}:` line")
    ticket = fields["TICKET"][0]
    if not re.match(r"^#\d+\b", ticket):
        raise OutputError(f"`TICKET: {ticket}`: it must start with `#<number>`")
    if kind == "PR":
        if not re.fullmatch(r"#\d+", fields["PR"][0]):
            raise OutputError(f"`PR: {fields['PR'][0]}`: it must be `#<number>`")
        if not re.match(r"^#\d+\s+(closes|refs)\b", ticket):
            raise OutputError(f"`TICKET: {ticket}`: a PR result says `closes` or `refs`")
    return {"RESULT": kind, **{key: fields[key][0] for key in expected}}


def _sub_lines(values: list[str]) -> list[str]:
    """Each value of a repeated key, a value left empty and cut into `- <item>` lines giving one each.

    `SPEC:` reads one line per ticket, or an empty key followed by one `  - #<ticket>: ...` line per
    ticket, so that no line runs past the paragraph cap.
    """
    items: list[str] = []
    for value in values:
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        if lines and all(line.startswith("- ") for line in lines):
            items.extend(line[2:].strip() for line in lines)
        else:
            items.append(value)
    return items


def split_fields(text: str) -> list[str]:
    """The `|` fields of a finding; a `|` between backticks (a pipe in a command) does not split."""
    fields: list[str] = []
    current: list[str] = []
    quoted = False
    for char in text:
        if char == "`":
            quoted = not quoted
        if char == "|" and not quoted:
            fields.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    fields.append("".join(current).strip())
    return fields


def probe_name_problem(name: str) -> str:
    """Why `name` cannot be the test file a probe names, or `""` when it can.

    The name runs nowhere by itself: `probe_replay.py` gives it to the command of the key `red-replay`.
    Refused: an absolute path, a `..` part, and any character outside ASCII letters, digits and `._/-`
    (a space, a quote, `;`, `|`, `$`, `\\`, `:`, `~`, a wildcard...), or a leading `-` or `.`.
    """
    if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
        return "an absolute path"
    if PROBE_NAME.match(name) is None:
        return "a character outside ASCII letters, digits and `._/-`, or a leading `-` or `.`"
    if ".." in name.split("/"):
        return "a `..` part"
    return ""


def probe_of(text: str) -> dict[str, str] | None:
    """The probe a blocker carries, or None when it rests on a reading of the code."""
    for field in split_fields(text):
        if re.match(r"^probe:", field, re.IGNORECASE):
            match = PROBE.match(field)
            if match is None:
                raise OutputError(
                    f"finding `{text[:60]}`: a probe reads {PROBE_FORM}, the test file and the output in backticks"
                )
            problem = probe_name_problem(match.group(1))
            if problem:
                raise OutputError(
                    f"finding `{text[:60]}`: probe `{match.group(1)[:60]}` refused, never run ({problem}): "
                    f"a probe names a test file of the head, {PROBE_FORM}, never a command"
                )
            return {"file": match.group(1), "expect": match.group(2)}
    return None


def parse_replay(text: str) -> dict[int, str]:
    """The replay lines of `probe_replay.py`, the status of each finding by its number."""
    statuses: dict[int, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if parts[0] not in REPLAY_STATUSES:
            raise OutputError(f"replay line `{line[:60]}`: the status must be one of {', '.join(REPLAY_STATUSES)}")
        if parts[0] == "NONE":
            continue
        if len(parts) < 2 or not parts[1].isdigit():
            raise OutputError(f"replay line `{line[:60]}`: the finding number is missing")
        statuses[int(parts[1])] = parts[0]
    return statuses


def parse_verdict(text: str, extra: tuple[str, ...] = ()) -> dict[str, object]:
    """qc-conf's verdict; `extra` names the further optional keys a project's verdict writes."""
    fields = _fields(text, "VERDICT", {*VERDICT_KEYS, *VERDICT_OPTIONAL, *extra})
    for key in VERDICT_KEYS:
        if key not in fields:
            raise OutputError(f"the verdict needs a `{key}:` line")
    verdict, round_, head = fields["VERDICT"][0], fields["ROUND"][0], fields["HEAD"][0]
    if verdict not in ("ACCEPT", "REJECT"):
        raise OutputError(f"`VERDICT: {verdict}`: the value must be ACCEPT or REJECT")
    if not ROUND.match(round_):
        raise OutputError(f"`ROUND: {round_}`: the value is the round number alone, 1, 2 or 3")
    grant = fields.get("GRANTED", [""])[0]
    if "GRANTED" in fields and not GRANT.match(grant):
        raise OutputError(f"`GRANTED: {grant}`: it must be the https link to the human's grant")
    if int(round_) > MAX_ROUNDS and not grant:
        raise OutputError(
            f"`ROUND: {round_}`: past round {MAX_ROUNDS}, the verdict needs a `GRANTED: <https link>` line"
        )
    if not HEAD.match(head):
        raise OutputError(f"`HEAD: {head}`: it must be the hexadecimal SHA of the judged head")
    specs = _sub_lines(fields["SPEC"])
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
    findings: list[dict[str, Any]] = []
    for line in fields["FINDINGS"][0].splitlines():
        line = line.strip()
        if not line or line.lower() in ("none", "aucun", "- none", "- aucun"):
            continue
        match = FINDING.match(line)
        if match is None:
            raise OutputError(f"finding `{line}`: it must read `- [BLOCKER|MINOR|NOTE] ...`")
        severity = match.group(1)
        probe = probe_of(match.group(2)) if severity == "BLOCKER" else None
        mark = MARKS["deduced"] if severity == "BLOCKER" and probe is None else ""
        findings.append({"severity": severity, "text": match.group(2), "probe": probe, "mark": mark})
    socle = fields.get("SOCLE", [""])[0]
    if "SOCLE" in fields and not HEAD.match(socle):
        raise OutputError(f"`SOCLE: {socle}`: it must be the hexadecimal SHA, 7 to 40 characters, of the socle read")
    proposals = fields.get("PROPOSAL", [])
    for proposal in proposals:
        if not PROPOSAL.match(proposal):
            raise OutputError(f"`PROPOSAL: {proposal}`: it reads `<input> | <expected result>`")
    blockers = sum(finding["severity"] == "BLOCKER" for finding in findings)
    if verdict == "REJECT" and not blockers:
        raise OutputError("`VERDICT: REJECT` with no `[BLOCKER]` finding: only a blocker rejects")
    if verdict == "ACCEPT" and blockers:
        raise OutputError(f"`VERDICT: ACCEPT` with {blockers} `[BLOCKER]` finding(s)")
    return {
        "VERDICT": verdict,
        "JUDGED": verdict,
        "DEMOTED": [],
        "ROUND": int(round_),
        "HEAD": head,
        "SPEC": specs,
        "FINDINGS": findings,
        "GATES": fields["GATES"][0],
        "SOCLE": socle,
        "GRANTED": grant,
        "BATTERY CORRECTION": fields.get("BATTERY CORRECTION", [""])[0],
        "PROPOSAL": proposals,
    }


def count_verdict(text: str, replay: Mapping[int, str]) -> dict[str, object]:
    """The verdict as `parse_verdict` reads it, with the counting rule applied to its probes.

    A probed blocker counts once its probe is confirmed, becomes a `[NOTE]` marked `non reproduit`
    when it is not reproduced, and is unsettled otherwise (`ReplayError`). `VERDICT` is the verdict
    that stands, `JUDGED` the judge's, `DEMOTED` the numbers of the findings made notes.
    """
    parsed = parse_verdict(text)
    findings = cast("list[dict[str, Any]]", parsed["FINDINGS"])
    parsed["DEMOTED"] = _settle(findings, replay)
    parsed["VERDICT"] = "REJECT" if any(finding["severity"] == "BLOCKER" for finding in findings) else "ACCEPT"
    return parsed


def _settle(findings: list[dict[str, Any]], replay: Mapping[int, str]) -> list[int]:
    """Apply the replay to the probed blockers; the numbers demoted to notes.

    A probe the replay refused (`REFUSED`: its name is not a test file of the head) goes back to the
    judge (`OutputError`). A probed blocker whose probe was not replayed (`NOT RUN`, no line) is
    unsettled: it counts neither way, and the verdict does not stand yet.
    """
    demoted: list[int] = []
    refused: list[str] = []
    unsettled: list[str] = []
    for number, finding in enumerate(findings, 1):
        if finding["severity"] != "BLOCKER" or finding["probe"] is None:
            continue
        status = replay.get(number)
        if status == "CONFIRMED":
            finding["mark"] = MARKS["confirmed"]
        elif status == "NOT REPRODUCED":
            finding["severity"], finding["mark"] = "NOTE", MARKS["demoted"]
            demoted.append(number)
        elif status == "REFUSED":
            refused.append(f"finding {number} (`{finding['probe']['file']}`)")
        else:
            unsettled.append(f"finding {number} ({status or 'no replay line'})")
    if refused:
        raise OutputError(
            "probe refused, never run: " + ", ".join(refused) + ": a probe names a test file of the head, "
            "under a prefix of the key `test-path`"
        )
    if unsettled:
        raise ReplayError(
            "unsettled probe: " + ", ".join(unsettled) + ": the blocker cannot count until its probe is replayed"
        )
    return demoted


def apply_replay(text: str, replay: Mapping[int, str]) -> str:
    """The verdict as it stands after the replay: demoted blockers become `[NOTE] non reproduit :`
    notes, and a `REJECT` left with no blocker reads `ACCEPT`. A verdict nothing demotes is unchanged."""
    parsed = count_verdict(text, replay)
    demoted = set(cast("list[int]", parsed["DEMOTED"]))
    if not demoted:
        return text
    lines = text.splitlines(keepends=True)
    start = max(index for index, line in enumerate(lines) if line.startswith("VERDICT:"))
    number = 0
    in_findings = False
    for index in range(start, len(lines)):
        line = lines[index]
        if KEY.match(line.rstrip()):
            in_findings = line.startswith("FINDINGS:")
            if line.startswith("VERDICT:") and parsed["VERDICT"] != parsed["JUDGED"]:
                lines[index] = f"VERDICT: {parsed['VERDICT']}\n"
        elif in_findings and FINDING.match(line.strip()):
            number += 1
            if number in demoted:
                lines[index] = re.sub(r"\[BLOCKER\]\s*", f"[NOTE] {MARKS['demoted']} : ", line, count=1)
    return "".join(lines)


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


PARSERS: dict[str, Callable[[str], Mapping[str, object]]] = {"result": parse_result, "verdict": parse_verdict, "domain": parse_domain}


USAGE = (
    "usage: parse_output.py result|verdict|domain <file | ->\n"
    "       parse_output.py verdict <file | -> [--replay <file>] [--rewrite <file>]\n"
)


def main(argv: list[str]) -> int:
    args = list(argv)
    options: dict[str, str] = {}
    for flag in ("--replay", "--rewrite"):
        if flag in args:
            index = args.index(flag)
            if index + 1 >= len(args):
                sys.stderr.write(USAGE)
                return 2
            options[flag] = args[index + 1]
            del args[index : index + 2]
    if (
        len(args) != 2
        or args[0] not in PARSERS
        or (options and args[0] != "verdict")
        or ("--rewrite" in options and "--replay" not in options)
    ):
        sys.stderr.write(USAGE)
        return 2
    text = sys.stdin.read() if args[1] == "-" else Path(args[1]).read_text(encoding="utf-8")
    try:
        if "--replay" in options:
            replay = parse_replay(Path(options["--replay"]).read_text(encoding="utf-8"))
            parsed: Mapping[str, object] = count_verdict(text, replay)
            if "--rewrite" in options:
                Path(options["--rewrite"]).write_text(apply_replay(text, replay), encoding="utf-8")
        else:
            parsed = PARSERS[args[0]](text)
    except ReplayError as error:
        print(f"invalid {args[0]}: {error}")
        return 3
    except OutputError as error:
        print(f"invalid {args[0]}: {error}")
        return 1
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
