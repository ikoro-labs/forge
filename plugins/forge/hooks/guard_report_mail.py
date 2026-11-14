"""The report mail's guard: the send is recorded only for a mail that follows `templates/report-mail.md`.

`PreToolUse` on a shell call. A command that runs `report_mail.py` with `--sent` records the mail
printed last as sent; this hook reads that mail (`mail.html` in the state folder, `--state-dir` of
the command or the script's default one) and checks it with `scripts/output_check.py`, kind
`report-mail`. A mail that departs from the template exits `REFUSED` (3), which the command in
`hooks.json` turns into the 2 that blocks. Anything else passes: another command, a command that
prints the mail, an event or a mail it cannot read.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from output_check import deviations  # noqa: E402
from report_mail import MAIL_FILE, state_dir  # noqa: E402
from usine import load, project_root  # noqa: E402

REFUSED = 3
SEND = re.compile(r"report_mail\.py\b(?=[^;&|\n]*--sent\b)[^;&|\n]*")


class Outcome:
    """What the guard returns: its exit code and its stderr."""

    def __init__(self, code: int, stderr: str = "") -> None:
        self.code = code
        self.stderr = stderr


STATE_OPTION = re.compile(r"""--state-dir(?:=|\s+)("[^"]*"|'[^']*'|\S+)""")


def _state_option(segment: str) -> str | None:
    """The value of `--state-dir` in `segment`, read without shell unescaping.

    `shlex` in POSIX mode eats the backslashes of a Windows path, so the quotes are cut by hand.
    """
    match = STATE_OPTION.search(segment)
    return match.group(1).strip("\"'") if match else None


def outcome(raw: str) -> Outcome:
    """The guard's answer to the hook event `raw`."""
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return Outcome(0)
    tool_input = event.get("tool_input") if isinstance(event, dict) else None
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not (match := SEND.search(command)):
        return Outcome(0)
    root = project_root(event)
    config: Mapping[str, list[str]] = load(root)
    folder = state_dir(config, _state_option(match.group(0)))
    try:
        mail = (folder / MAIL_FILE).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return Outcome(0)  # no mail was printed: the script itself says so
    found = deviations(mail, "report-mail", config, root)
    if not found:
        return Outcome(0)
    listing = "".join(f"- {deviation}\n" for deviation in found)
    return Outcome(REFUSED, (
        "Blocked by the report mail guard (forge plugin): the mail printed last does not follow"
        f" `templates/report-mail.md`, so its send is not recorded. Fix each point:\n{listing}"
    ))


def main() -> int:
    result = outcome(sys.stdin.read())
    sys.stderr.write(result.stderr)
    return result.code


if __name__ == "__main__":
    raise SystemExit(main())
