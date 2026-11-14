"""PreToolUse hook on agent launches: `forge:coder` runs on sonnet unless its prompt earns another model.

Decision of 2026-11-14, common to the projects that adopt forge: tokens count as much as time, so the
coder starts on the cheapest model that does the work. `agents/coder.md` holds `model: sonnet` and
`effort: high`; a launch may pass, for `forge:coder` or `coder`:

- no `model` nor `effort`: the frontmatter applies, before the main conversation's model;
- `model: sonnet`;
- `model: opus` only with a prompt line `ESCALATION: #<n> round 3`;
- `model: haiku` only with a prompt line `MODE: sync`;
- `effort`, when given, `high`.

Any other model, `fable` included, is refused with exit code 2. The rule holds on an `Agent` call
(old name `Task`), and on a `Workflow` whose script (inline, `scriptPath`, or a workflow saved under
`.claude/workflows/` of the project or of the user) calls `agent(prompt, {agentType: 'forge:coder',
...})`, child workflows (`workflow(...)`) included. In a script that names a coder (the word `coder`
in the script or in `args`), an `agent()` call whose options the guard cannot read is refused: a
variable, a spread, an `agentType`, `model` or `effort` that is not a string literal, a prompt that
is not one when the model needs a line; and a `workflow()` call whose script it cannot name. A
workflow name the guard does not find (built-in, or another plugin's) passes. The standard library
only.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from functools import partial
from pathlib import Path

from usine import project_root

REFUSED = 2
CODER = frozenset({"forge:coder", "coder"})
EFFORT = "high"
# Each model a launch may name, and the prompt line it needs (None: none).
MODELS: dict[str, tuple[re.Pattern[str], str] | None] = {
    "sonnet": None,
    "opus": (re.compile(r"^ESCALATION: #\d+ round 3$", re.MULTILINE), "ESCALATION: #<n> round 3"),
    "haiku": (re.compile(r"^MODE: sync$", re.MULTILINE), "MODE: sync"),
}
NAMES_CODER = re.compile(r"\bcoder\b")
CALL = re.compile(r"(?<![\w$])(agent|workflow)\s*\(")
LITERAL = re.compile(r"""^(?:'([^'\\]*)'|"([^"\\]*)"|`([^`\\$]*)`)$""")
KEY = re.compile(r"""^\s*(?:([A-Za-z_$][\w$]*)|'([^']*)'|"([^"]*)")\s*:(.*)$""", re.DOTALL)
OPEN, CLOSE = "([{", ")]}"


class Unreadable(Exception):
    """A script, or an `agent()` call in it, that the guard cannot read: refused."""


def _values(model: object, effort: object, where: str, prompt: Callable[[], str]) -> list[str]:
    """What breaks the rule; `prompt` reads the prompt only when the model needs a line."""
    problems = []
    if model is not None:
        if model not in MODELS:
            problems.append(f"{where} sets `model: {model}`: forge:coder runs on `sonnet`, `opus` or `haiku`")
        elif (need := MODELS[str(model)]) is not None and not need[0].search(prompt().replace("\r\n", "\n")):
            problems.append(f"{where} sets `model: {model}` without the prompt line `{need[1]}`")
    if effort is not None and effort != EFFORT:
        problems.append(f"{where} sets `effort: {effort}`: forge:coder runs at `{EFFORT}`")
    return problems


def _code(text: str) -> str:
    """The script with its comments and the content of its strings blanked, offsets kept."""
    out = list(text)
    index = 0
    while index < len(text):
        char = text[index]
        if text.startswith("//", index) or text.startswith("/*", index):
            end = text.find("\n" if char == "/" and text[index + 1] == "/" else "*/", index + 2)
            end = len(text) if end < 0 else end + (0 if text[index + 1] == "/" else 2)
            out[index:end] = " " * (end - index)
            index = end
        elif char in "'\"`":
            start = index
            index += 1
            while index < len(text) and text[index] != char:
                index += 2 if text[index] == "\\" else 1
            if index >= len(text):
                raise Unreadable("a string is not closed")
            out[start + 1 : index] = "_" * (index - start - 1)
            index += 1
        else:
            index += 1
    return "".join(out)


def _arguments(text: str, code: str, start: int) -> list[str]:
    """The top-level arguments of the call whose `(` is at `start`, read from the original text."""
    depth, begin, found = 0, start + 1, []
    for index in range(start + 1, len(code)):
        char = code[index]
        if char in OPEN:
            depth += 1
        elif char in CLOSE:
            if depth == 0:
                found.append(text[begin:index].strip())
                return [argument for argument in found if argument]
            depth -= 1
        elif char == "," and depth == 0:
            found.append(text[begin:index].strip())
            begin = index + 1
    raise Unreadable("a call is not closed")


def _literal(value: str) -> str | None:
    match = LITERAL.match(value.strip())
    return next((group for group in match.groups() if group is not None), None) if match else None


ESCAPES = {"n": "\n", "t": "\t", "r": "\r"}


def _prompt(value: str) -> str:
    """The text of a string literal prompt, its escapes read; `Unreadable` for anything else."""
    text = value.strip()
    quote = text[:1]
    if len(text) < 2 or quote not in "'\"`" or text[-1] != quote:
        raise Unreadable(f"the prompt `{text[:30]}` is not a string literal")
    out: list[str] = []
    index = 1
    while index < len(text) - 1:
        char = text[index]
        if char == "\\" and index + 1 < len(text) - 1:
            out.append(ESCAPES.get(text[index + 1], text[index + 1]))
            index += 2
            continue
        if char == quote or (quote == "`" and text.startswith("${", index)):
            raise Unreadable(f"the prompt `{text[:30]}` is not a string literal")
        out.append(char)
        index += 1
    return "".join(out)


def _fields(options: str) -> dict[str, str]:
    """The `key: value` entries of an object literal; `Unreadable` on a spread or a shorthand."""
    inner = options.strip()[1:-1]
    entries = _arguments(f"({inner})", _code(f"({inner})"), 0)
    fields: dict[str, str] = {}
    for entry in entries:
        if entry.startswith("..."):
            raise Unreadable(f"a spread `{entry[:30]}` in the options")
        match = KEY.match(entry)
        if match is None:
            raise Unreadable(f"the option `{entry[:30]}` is a shorthand or a computed key")
        key = next(group for group in match.groups()[:3] if group is not None)
        fields[key] = match.group(4).strip()
    return fields


def _option(fields: Mapping[str, str], key: str) -> str | None:
    if key not in fields:
        return None
    value = _literal(fields[key])
    if value is None:
        raise Unreadable(f"`{key}: {fields[key][:30]}` is not a string literal")
    return value


def _workflow_file(root: Path, name: str) -> Path | None:
    """The saved workflow `name` of the project or of the user, None when neither holds it."""
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    for folder in (root / ".claude" / "workflows", home / "workflows"):
        for path in sorted(folder.glob("*.js")) if folder.is_dir() else []:
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.stem == name or re.search(rf"\bname\s*:\s*['\"]{re.escape(name)}['\"]", text):
                return path
    return None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise Unreadable(f"the script `{path}` cannot be read") from error


def script_problems(text: str, args: object, root: Path, here: Path, nested: bool = False) -> list[str]:
    """What keeps this workflow script from launching a coder off its model or effort."""
    strict = bool(NAMES_CODER.search(text) or NAMES_CODER.search(json.dumps(args, default=str)))
    try:
        code = _code(text)
    except Unreadable:
        if strict:
            raise
        return []
    problems: list[str] = []
    for match in CALL.finditer(code):
        arguments = _arguments(text, code, match.end() - 1)
        if match.group(1) == "workflow":
            problems += _child(arguments, root, here, nested)
            continue
        if len(arguments) < 2:
            continue
        options = arguments[1]
        if not (options.startswith("{") and options.endswith("}")):
            if strict:
                raise Unreadable(f"the options `{options[:30]}` of `agent()` are not an object literal")
            continue
        try:
            fields = _fields(options)
            kind = _option(fields, "agentType")
        except Unreadable:
            if strict:
                raise
            continue
        if kind in CODER:
            where = f"`agent(..., {{agentType: '{kind}'}})`"
            prompt = partial(_prompt, arguments[0])
            problems += _values(_option(fields, "model"), _option(fields, "effort"), where, prompt)
    return problems


def _child(arguments: list[str], root: Path, here: Path, nested: bool) -> list[str]:
    """The problems of the workflow a `workflow(...)` call runs."""
    if nested or not arguments:
        raise Unreadable("a `workflow(...)` call the guard cannot follow")
    target = arguments[0]
    name = _literal(target)
    if name is not None:
        path = _workflow_file(root, name)
        return script_problems(_read(path), None, root, here, True) if path else []
    if target.startswith("{") and target.endswith("}"):
        script_path = _option(_fields(target), "scriptPath")
        if script_path:
            return script_problems(_read(here / script_path), None, root, here, True)
    raise Unreadable(f"`workflow({target[:30]})` names no script the guard can read")


def outcome(event: Mapping[str, object]) -> tuple[int, str]:
    """`(0, "")` to let the launch run, or `(2, reason)`."""
    tool = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0, ""
    root = project_root(event)
    here = Path(str(event.get("cwd") or root))
    try:
        if tool in ("Agent", "Task"):
            kind = str(tool_input.get("subagent_type") or "").strip()
            prompt = str(tool_input.get("prompt") or "")
            where = f"`subagent_type: {kind}`"
            problems = _values(tool_input.get("model"), tool_input.get("effort"), where, lambda: prompt) if kind in CODER else []
        elif tool == "Workflow":
            text = None
            if tool_input.get("scriptPath"):
                text = _read(here / str(tool_input["scriptPath"]))
            elif isinstance(tool_input.get("script"), str):
                text = tool_input["script"]
            elif tool_input.get("name"):
                path = _workflow_file(root, str(tool_input["name"]))
                text = _read(path) if path else None
            problems = script_problems(text, tool_input.get("args"), root, here) if text is not None else []
        else:
            return 0, ""
    except Unreadable as error:
        problems = [f"{error}: write the coder's prompt and options as literals, `{{agentType: 'forge:coder'}}`"]
    if not problems:
        return 0, ""
    lines = "\n".join(f"- {problem}" for problem in problems)
    return REFUSED, (
        "Blocked by the forge plugin (guard_coder_model): forge:coder runs on `sonnet` at effort `high`,"
        " on `opus` only with a prompt line `ESCALATION: #<n> round 3`, on `haiku` only with a line"
        f" `MODE: sync` (decision of 2026-11-14). Drop `model` and `effort`, or fix each point:\n{lines}\n"
    )


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.stderr.write("Blocked by the forge plugin (guard_coder_model): the event cannot be read.\n")
        return REFUSED
    code, message = outcome(event if isinstance(event, dict) else {})
    if message:
        sys.stderr.write(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
