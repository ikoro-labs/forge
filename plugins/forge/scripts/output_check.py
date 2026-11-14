"""Check an exchange against its template and its word caps, and list every deviation.

    python output_check.py <kind> [<file> | -]

Kinds: the documents under `templates/` (`ticket`, `pr`, `comment`, `verdict`, `session-reply`,
`subagent-return`, `report-mail`) and the declared outputs of the plugin's agents (`coder`, `decider`, `gate`).
`exempt` checks nothing. Prints one deviation per line and exits 1 when there is one, 0 when the
text conforms, 2 on a usage error. The hook `guard_output.py` calls `deviations` for its three
events; a skill can run this command on a body before it posts it.

The rules, the same for every kind that has them:

- a word cap per kind (keys `output-words-<kind>` of `docs/agents/usine.md`, `0` for none) over the
  whole text, code blocks and table cells included, HTML comments left out; a span between
  backticks counts as one word;
- no prose paragraph over `output-words-paragraph` words; a list item is a paragraph of its own; a
  table line or a code block is no paragraph;
- each field the template names in the `required:` part of its header line, present and not empty;
- at most the `max-lines:` of that header line (`0` for none), in written lines: blank lines and HTML
  comments do not count.
  A project replaces a template with the key `output-template` (`<kind> | <path>`);
- a structured format (`verdict`, `coder`, `decider`) takes a closed set of keys: an unknown key is
  refused, unless the project names it with `output-extra-keys` (`<kind> | KEY, KEY`). The verdict
  and the coder's block are read by `parse_output.py`, their one source of rules.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from parse_output import OutputError, parse_result, parse_verdict

PLUGIN = Path(__file__).resolve().parents[1]
TEMPLATES = PLUGIN / "templates"

# The word caps when the project sets none, decided for every forge project.
DEFAULT_WORDS = {
    "ticket": 150,
    "comment": 150,
    "pr": 200,
    "session-reply": 150,
    "report-mail": 500,
    "subagent-return": 200,
}
DEFAULT_PARAGRAPH_WORDS = 60
WORDS_KEY = "output-words-{}"
PARAGRAPH_KEY = "output-words-paragraph"
TEMPLATE_KEY = "output-template"
AGENT_FORMAT_KEY = "output-agent-format"
EXTRA_KEYS_KEY = "output-extra-keys"


@dataclass(frozen=True)
class Kind:
    """What a kind of exchange is checked against."""

    template: str | None  # the file under `templates/` that names its required fields
    words: str | None  # the cap of `DEFAULT_WORDS` it takes, or None for no word cap
    paragraphs: bool = True


KINDS = {
    "ticket": Kind("ticket.md", "ticket"),
    "pr": Kind("pr.md", "pr"),
    "comment": Kind("comment.md", "comment"),
    # A verdict has no word cap: the review never shortens its findings to fit one. Its rules are
    # `parse_verdict`'s alone, the template's `required:` is not read for it.
    "verdict": Kind(None, None),
    "session-reply": Kind("session-reply.md", "session-reply"),
    "subagent-return": Kind("subagent-return.md", "subagent-return"),
    # The factory report mail is HTML: `_from_html` reads its headings, items and table rows.
    "report-mail": Kind("report-mail.md", "report-mail"),
    "coder": Kind(None, "subagent-return"),
    "decider": Kind(None, "subagent-return"),
    # The gate's table and the verbatim elements under it have no word cap.
    "gate": Kind(None, None),
    "exempt": Kind(None, None, paragraphs=False),
}
# The plugin's agents and the declared format of each (`agents/<name>.md`, section "Sortie").
# The end-to-end review's two agents write tab-separated lines that `revue_bout_en_bout.py`
# checks already: no Markdown paragraph applies to them.
# A project that copies an agent into `.claude/agents/` runs it under its bare name: `coder` is held
# to the format of `forge:coder`. A name under another plugin's prefix is not one of them.
FORGE_AGENTS = {
    "coder": "coder",
    "qc-conf": "verdict",
    "qc-gate": "gate",
    "staff-engineer": "decider",
    "product-owner": "decider",
    "review-judge": "exempt",
    "review-recheck": "exempt",
}
AGENT_FORMATS = frozenset({"coder", "verdict", "decider", "gate", "exempt", "subagent-return"})
DECIDER_KEYS = ("VERDICT", "DECISION")
# The keys of the deciders' block (`agents/staff-engineer.md` and `agents/product-owner.md`, "Sortie").
DECIDER_KNOWN = frozenset({
    "VERDICT", "QUESTION", "DECISION", "GROUND", "MATRIX_CELL", "REVERSIBLE", "USER_IMPACT", "VETO",
    "REFERENTIAL_UPDATE", "WRITE_TO", "READ",
})
GATE_MOST_TABLE_LINES = 30

HEADER = re.compile(r"<!--\s*template:(.*?)-->", re.DOTALL)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
FENCE = re.compile(r"^\s*(```|~~~)")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
HEADING = re.compile(r"^\s*#{1,6}\s")
MARKUP = re.compile(r"^[\s#>*_|`-]*")
WORD = re.compile(r"\S+")
# A span between backticks (a `path:line`, a command, a test id, a quotation) counts as one word.
CODE_SPAN = re.compile(r"`[^`\n]+`")
KEY_LINE = re.compile(r"^\s*[A-Z][A-Z_ ]*[A-Z]:")
# The kinds made of `KEY:` lines, which an agent often wraps in a code fence as its role shows it.
KEYED = frozenset({"verdict", "coder", "decider"})


def _integer(config: Mapping[str, list[str]], key: str, default: int) -> int:
    values = config.get(key, [])
    try:
        value = int(values[-1]) if values else default
    except ValueError:
        return default
    return value if value >= 0 else default


def word_cap(kind: str, config: Mapping[str, list[str]]) -> int | None:
    """The word cap of `kind` for this project, or None when it has none."""
    name = KINDS[kind].words
    if name is None:
        return None
    cap = _integer(config, WORDS_KEY.format(name), DEFAULT_WORDS[name])
    return cap or None


def agent_kind(agent_type: str, config: Mapping[str, list[str]]) -> str:
    """The format an agent's final output is checked against: its own, else the generic rule."""
    for value in config.get(AGENT_FORMAT_KEY, []):
        name, _, kind = (part.strip() for part in value.partition(" | "))
        if name == agent_type and kind in AGENT_FORMATS:
            return kind
    prefix, _, name = agent_type.rpartition(":")
    if prefix not in ("", "forge"):
        return "subagent-return"
    return FORGE_AGENTS.get(name, "subagent-return")


def extra_keys(kind: str, config: Mapping[str, list[str]]) -> tuple[str, ...]:
    """The keys a project adds to the structured format `kind` (key `output-extra-keys`)."""
    keys: list[str] = []
    for value in config.get(EXTRA_KEYS_KEY, []):
        name, _, listed = (part.strip() for part in value.partition(" | "))
        if name == kind:
            keys += [key.strip() for key in listed.split(",") if key.strip()]
    return tuple(keys)


def required_fields(template: str) -> list[list[str]]:
    """The fields the header of `template` names, each with its accepted spellings.

    The header reads `required: <field>, <field>`, a field `A or B` when two labels say it (a reply
    in either language), and `required: none` when the template imposes no field.
    """
    value = _header(template, "required")
    fields = [field.strip() for field in (value or "").split(",") if field.strip()]
    if fields in ([], ["none"]):
        return []
    return [[label.strip() for label in field.split(" or ")] for field in fields]


def line_cap(template: str) -> int | None:
    """The `max-lines: <n>` of the header of `template`; None when it declares none or `0`.

    `0` lifts the cap, as `0` does for a word cap (`output-words-<kind>`).
    """
    match = re.match(r"\s*(\d+)", _header(template, "max-lines") or "")
    return int(match.group(1)) or None if match else None


def _header(template: str, key: str) -> str | None:
    """The value of the part `key:` in the header line of `template`."""
    match = HEADER.search(template)
    for part in match.group(1).split("|") if match else []:
        name, _, value = part.partition(":")
        if name.strip() == key:
            return value
    return None


def _template_text(kind: str, config: Mapping[str, list[str]], root: Path | None) -> str:
    for value in config.get(TEMPLATE_KEY, []):
        name, _, path = (part.strip() for part in value.partition(" | "))
        if name == kind and path and root is not None:
            try:
                return (root / path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                break
    template = KINDS[kind].template
    if template is None:
        return ""
    try:
        return (TEMPLATES / template).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _structure(text: str) -> tuple[list[str], list[str]]:
    """All lines without HTML comments, and the prose lines: tables and code blocks blanked."""
    lines = HTML_COMMENT.sub("", text).splitlines()
    prose: list[str] = []
    fenced = False
    for line in lines:
        if FENCE.match(line):
            fenced = not fenced
            prose.append("")
        elif fenced or line.lstrip().startswith("|"):
            prose.append("")
        else:
            prose.append(line)
    return lines, prose


def _paragraphs(prose: list[str]) -> list[str]:
    """Prose paragraphs, a list item each on its own, headings left out."""
    paragraphs: list[list[str]] = []
    current: list[str] | None = None
    for line in prose:
        if not line.strip() or HEADING.match(line):
            current = None
            continue
        item = LIST_ITEM.match(line)
        if current is None or item or KEY_LINE.match(line):
            current = []
            paragraphs.append(current)
        current.append(line[item.end() :].strip() if item else line.strip())
    return [" ".join(paragraph) for paragraph in paragraphs]


def _unwrap(text: str) -> str:
    """`text` without the code fence that wraps it whole, so that its key lines are read as prose."""
    lines = text.strip().splitlines()
    if len(lines) >= 2 and FENCE.match(lines[0]):
        closing = next((i for i in range(len(lines) - 1, 0, -1) if FENCE.match(lines[i])), None)
        if closing is not None:
            return "\n".join(lines[1:closing] + lines[closing + 1 :])
    return text


def _label(line: str) -> str:
    return MARKUP.sub("", line).strip()


def _field_line(lines: list[str], labels: list[str]) -> int | None:
    """The index of the first line that opens one of `labels`, as a heading, a key or a row."""
    for index, line in enumerate(lines):
        text = _label(line)
        for label in labels:
            if text.lower().startswith(label.lower()):
                rest = text[len(label) :].lstrip("*_ ")
                if rest == "" or rest[0] in ":|":
                    return index
    return None


def _empty(lines: list[str], index: int, labels: list[str]) -> bool:
    """Whether the field at `index` holds nothing.

    A heading holds what follows it up to the next heading. A key holds the rest of its line, or,
    when that is empty, the list, table, code block or indented lines right under it.
    """
    text = _label(lines[index])
    label = next(lab for lab in labels if text.lower().startswith(lab.lower()))
    value = text[len(label) :].lstrip("*_ ").lstrip(":|").strip(" |*_")
    if value:
        return False
    heading = bool(HEADING.match(lines[index]))
    for line in lines[index + 1 :]:
        if not line.strip():
            continue
        if HEADING.match(line):
            return True
        if heading:
            return False
        nested = LIST_ITEM.match(line) or line.startswith((" ", "\t")) or FENCE.match(line)
        return not (nested or line.lstrip().startswith("|"))
    return True


def _keys(lines: list[str], first: str) -> dict[str, str]:
    """`KEY: value` lines of the last block that opens with `first:`, continuations joined."""
    starts = [i for i, line in enumerate(lines) if line.strip().startswith(f"{first}:")]
    if not starts:
        return {}
    fields: dict[str, str] = {}
    current: str | None = None
    for line in lines[starts[-1] :]:
        if FENCE.match(line):
            continue
        match = re.match(r"^([A-Z][A-Z_ ]*[A-Z]):[ \t]?(.*)$", line)
        if match:
            current = match.group(1)
            fields.setdefault(current, match.group(2).strip())
        elif current is not None and line.strip():
            fields[current] = f"{fields[current]}\n{line.strip()}".strip()
    return fields


def _parsed(parser: Callable[[str, tuple[str, ...]], object], text: str, extra: tuple[str, ...]) -> list[str]:
    try:
        parser(text, extra)
    except OutputError as error:
        return [str(error)]
    return []


def _decider(lines: list[str], extra: tuple[str, ...]) -> list[str]:
    fields = _keys(lines, "VERDICT")
    found = [f"the decision needs a non-empty `{key}:` line" for key in DECIDER_KEYS if not fields.get(key)]
    known = DECIDER_KNOWN | set(extra)
    found += [f"`{key}:` is not a key of this block" for key in fields if key not in known]
    return found


def _gate(lines: list[str]) -> list[str]:
    table = [line for line in lines if line.lstrip().startswith("|")]
    if not table:
        return ["the gate's output is a table: no line starts with `|`"]
    if len(table) > GATE_MOST_TABLE_LINES:
        return [f"the table has {len(table)} lines, at most {GATE_MOST_TABLE_LINES}"]
    return []


class _Flatten(HTMLParser):
    """The HTML of a mail as the Markdown the rules read: `#` headings, `-` items, `|` table rows."""

    HEADINGS = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### "}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.HEADINGS:
            self.parts.append("\n" + self.HEADINGS[tag])
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "tr":
            self.parts.append("\n|")
        elif tag in ("td", "th"):
            self.parts.append(" ")
        elif tag in ("p", "ul", "ol", "table", "div", "br"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self.parts.append(" |")
        elif tag in self.HEADINGS or tag in ("p", "ul", "ol", "table", "div"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _from_html(text: str) -> str:
    flat = _Flatten()
    flat.feed(text)
    return "".join(flat.parts)


def _list_runs(prose: list[str]) -> list[int]:
    """The lengths of the runs of list items that sit at the left margin."""
    runs: list[int] = []
    count = 0
    for line in prose:
        if LIST_ITEM.match(line) and not line.startswith((" ", "\t")):
            count += 1
        elif line.strip() and line.startswith((" ", "\t")) and count:
            continue  # an item's continuation
        else:
            if count:
                runs.append(count)
            count = 0
    if count:
        runs.append(count)
    return runs


def count_words(text: str) -> int:
    """The words of `text`, each span between backticks counted as one."""
    return len(WORD.findall(CODE_SPAN.sub("`span`", text)))


def _quote(paragraph: str) -> str:
    words = paragraph.split()
    return " ".join(words[:6]) + (" ..." if len(words) > 6 else "")


def deviations(
    text: str, kind: str, config: Mapping[str, list[str]] | None = None, root: Path | None = None
) -> list[str]:
    """Every way `text` departs from the rules of `kind`; empty when it conforms."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind `{kind}`: one of {', '.join(sorted(KINDS))}")
    config = config or {}
    if kind == "exempt":
        return []
    if kind == "report-mail":
        text = _from_html(text)
    lines, prose = _structure(_unwrap(text) if kind in KEYED else text)
    found: list[str] = []
    template = _template_text(kind, config, root)
    most_lines = line_cap(template)
    written = sum(1 for line in lines if line.strip())
    if most_lines is not None and written > most_lines:
        found.append(
            f"{written} lines, at most {most_lines} (template `{kind}`): blank lines and HTML"
            " comments do not count"
        )
    for labels in required_fields(template):
        index = _field_line(lines, labels)
        name = " or ".join(f"`{label}`" for label in labels)
        if index is None:
            found.append(f"the field {name} is missing (template `{kind}`)")
        elif _empty(lines, index, labels):
            found.append(f"the field {name} is empty")
    extra = extra_keys(kind, config)
    if kind == "coder":
        found += _parsed(parse_result, text, extra)
    elif kind == "verdict":
        found += _parsed(parse_verdict, text, extra)
    elif kind == "decider":
        found += _decider(lines, extra)
    elif kind == "gate":
        found += _gate(lines)
    elif kind == "session-reply":
        found += [
            f"a list of {run} items: more than two elements go in a table"
            for run in _list_runs(prose) if run > 2
        ]
    elif kind == "report-mail" and not any(line.lstrip().startswith("|") for line in lines):
        found.append("the mail needs a table: no table row found (template `report-mail`)")
    cap = word_cap(kind, config)
    words = sum(count_words(line) for line in lines if not FENCE.match(line))
    if cap is not None and words > cap:
        cap_name = KINDS[kind].words
        found.append(
            f"{words} words, at most {cap} (key `{WORDS_KEY.format(cap_name)}`): code blocks and"
            " tables count too"
        )
    if KINDS[kind].paragraphs:
        most = _integer(config, PARAGRAPH_KEY, DEFAULT_PARAGRAPH_WORDS)
        for paragraph in _paragraphs(prose):
            count = count_words(paragraph)
            if most and count > most:
                found.append(
                    f"a paragraph of {count} words, at most {most}: \"{_quote(paragraph)}\";"
                    " cut it into a list or a table"
                )
    return found


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2) or argv[0] not in KINDS:
        sys.stderr.write(f"usage: output_check.py <{'|'.join(KINDS)}> [<file> | -]\n")
        return 2
    try:
        if len(argv) == 1 or argv[1] == "-":
            text = sys.stdin.read()
        else:
            text = Path(argv[1]).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        sys.stderr.write(f"cannot read the text: {error}\n")
        return 2
    sys.path.insert(0, str(PLUGIN / "hooks"))
    from usine import load, project_root

    root = project_root()
    found = deviations(text, argv[0], load(root), root)
    for deviation in found:
        sys.stdout.write(f"- {deviation}\n")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
