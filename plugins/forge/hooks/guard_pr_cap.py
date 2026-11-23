"""PreToolUse hook: a ticket holds at most N PRs, N the key `ticket-pr-cap` of `docs/agents/usine.md`.

With the key declared, the hook refuses a PR whose body cites `Closes #n` or `Refs #n` when the
ticket #n already has N PRs, open or merged (a PR closed without a merge leaves its place). It reads
the body of each of these gestures, behind a wrapper, in `bash -c`, `eval` or a nested shell as
`gh_bodies.py` does:

- `gh pr create` (its body: `--body`, `--body-file`), and `gh api` POST on `repos/<o>/<r>/pulls`;
- `gh pr edit` and `gh api` PATCH on `repos/<o>/<r>/pulls/<n>`, for the tickets the body cites that
  the PR's current body did not: a PR already counted for a ticket is not a new one, so the report
  `forge:qc` writes into a PR's body is never refused;
- `gh api` on `repos/<o>/<r>/issues/<n>`, a PR being an issue: the hook asks `gh api` whether #n carries
  `pull_request`; a real ticket is not held, a PR is read as `gh pr edit` (a read it cannot make refuses).
  The other doors to the same edit are read the same way: `gh issue edit <n>` (gh resolves a PR number
  there), the issue tools of a GitHub MCP server (`update_issue`, `issue_write` with `method: update`),
  and a `curl` to `issues/<n>`, whose body the hook cannot read, so a PR there is refused;
- the pull request tools of a GitHub MCP server (`create_pull_request`, `update_pull_request`).

The PRs of a ticket are those `gh pr list --state all --search "<n> in:body"` finds whose body cites
the ticket by `Closes #n` or `Refs #n` (a regex, as `forge:coder` counts them), plus those this
hook let through in the last `RESERVATION_SECONDS` that GitHub's search may not show yet (the state
file of `guard_ticket_budget`, kind `pr`). A retry of the same body is the same PR: it counts once.

With the key `ticket-pr-cap-since` (a day, `AAAA-MM-JJ`) only the PRs created on that UTC day or after
it count (`createdAt` of `gh pr list`); the earlier ones are left out of the count. Without that key
the date step is not applicable (sans objet) and every PR counts, whatever its date: no date is
guessed. A value that is not one valid day, a repeated key, or a PR whose `createdAt` cannot be read
fails closed like the rest of the count.

A ticket already started before that day (at least one open or merged PR that cites it, created before
the day) finishes the PR in flight, then admits ONE last new PR, as a last resort: for such a ticket the
limit on the PRs created since the day is `LAST_PR` (1) instead of the cap. The PRs from before the day stay
out of the count, a PR closed without a merge does not start a ticket, and the limit is a constant, not a
key. Without the key `ticket-pr-cap-since` no ticket is a started one (there is no day to start before).

A refusal is the `BLOCKED` of the fourth PR (of the last PR for a started ticket): no PR, no new ticket;
the ticket is commented and takes `needs-your-attention`. Only the label `pr-cap-raised` raises the limit
(the cap, or the last PR's) to `RAISED_CAP`, and only
when the last event on that label is a `labeled` by a login of the key `pr-cap-raiser` (the
short identifier of its line, else its whole value; `accepting-human` is not read here: the agent's
account may sit in it): the guard reads the events of the ticket by
`gh api` and asks for them only when the count is at the cap.

Fails closed: a body it cannot read (a variable, a substitution, a pipe, an editor, `--fill`), a count
gh cannot make (absent, network, error), a key with no readable value, a GraphQL mutation that
opens or edits a PR and cites a ticket, and a `curl` to the pulls of api.github.com are all refused.
Without the key `ticket-pr-cap` the step is not applicable (sans objet) and the hook reads nothing;
the key has no default. `hooks.json` turns a crash into a refusal. The standard library only.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from collections.abc import Callable, Mapping
from datetime import date, datetime, timezone
from pathlib import Path

from gh_bodies import (
    UNREAD,
    Publication,
    Unreadable,
    commands,
    curls_github,
    heredocs,
    may_publish,
    publications,
)
from guard_git import CLOSING, REFS, UNKNOWN, _moved, gh_act
from guard_ticket_budget import SEARCH_LIMIT, State, run_gh, state_file, with_reservations
from usine import load, project_root
from utf8_stdio import use_utf8

KEY = "ticket-pr-cap"
SINCE_KEY = "ticket-pr-cap-since"
RAISER_KEY = "pr-cap-raiser"
RAISE_LABEL = "pr-cap-raised"
RAISED_CAP = 6
LAST_PR = 1  # the new PRs a ticket started before `ticket-pr-cap-since` still admits
KIND = "pr"
COUNTED_STATES = frozenset({"OPEN", "MERGED"})

PREFIX = "Blocked by the forge plugin (guard_pr_cap)"
BLOCKED = (
    "this is the BLOCKED of the fourth PR: open no PR and no new ticket; the ticket is commented"
    " and takes `needs-your-attention`"
)

Runner = Callable[[list[str], "str | None"], "str | None"]

# What `gh pr list --json createdAt` gives (`2026-11-23T08:00:00Z`); a fraction is dropped, an offset kept.
TIMESTAMP = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})")
PULLS = re.compile(r"^/?repos/([^/]+)/([^/]+)/pulls(?:/(\d+))?$")
# A PR is an issue: `gh api` on `issues/<n>` edits a PR's body when #n is one.
ISSUE = re.compile(r"^/?repos/([^/]+)/([^/]+)/issues/(\d+)$")
API_PULLS = re.compile(r"api\.github\.com/+(?:repos/[^/\s'\"]+/[^/\s'\"]+/pulls\b|graphql\b)")
# A `curl` word that names `issues/<n>` (not its comments, not the list of issues): the same door as `gh api`.
CURL_ISSUE = re.compile(r"api\.github\.com/+repos/([^/\s'\"]+)/([^/\s'\"]+)/issues/(\d+)/*(?:[?#]\S*)?$")
# `gh issue edit` names its issue by a number, `#number` or the URL of an issue or of a PR.
ISSUE_SELECTOR = re.compile(r"^#?(\d+)$|^(?:https?://)?[^/\s]+/([^/\s]+)/([^/\s]+)/(?:issues|pull)/(\d+)/*$")
CURL_ACT = ("curl", "issues")
# `gh pr edit` options that take the next word as their value (the selector is the first other word).
EDIT_VALUE_OPTIONS = frozenset(
    {"--title", "-t", "--body", "-b", "--body-file", "-F", "--base", "-B", "--milestone", "-m"}
    | {"--repo", "-R", "--add-assignee", "--remove-assignee", "--add-label", "--remove-label"}
    | {"--add-reviewer", "--remove-reviewer", "--add-project", "--remove-project"}
)


def cited(body: str) -> set[str]:
    """The tickets a PR body cites the way GitHub links them (`guard_git`'s `CLOSING` and `REFS`).

    `Closes #n`, `Closes: #n`, `Closes owner/repo#n`, `Fixes`, `Resolves`, `Refs #n`, `Refs #n, #m`.
    """
    found = set(CLOSING.findall(body))
    for group in REFS.findall(body):
        found.update(re.findall(r"\d+", group))
    return found


def cap_of(config: Mapping[str, list[str]]) -> tuple[int | None, str | None]:
    """`(cap, None)`, `(None, None)` when the key is absent, `(None, reason)` when it cannot be read."""
    values = config.get(KEY)
    if not values:
        return None, None
    if len(values) != 1 or not re.fullmatch(r"[1-9]\d*", values[0].strip()):
        return None, (
            f"the key `{KEY}` of docs/agents/usine.md is not one whole number above 0: the PR is"
            " refused as a precaution until it is fixed"
        )
    return int(values[0].strip()), None


def since_of(config: Mapping[str, list[str]]) -> tuple[date | None, str | None]:
    """`(day, None)`, `(None, None)` when the key is absent, `(None, reason)` when it cannot be read."""
    values = config.get(SINCE_KEY)
    if not values:
        return None, None
    text = values[0].strip() if len(values) == 1 else ""
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise ValueError(text)
        return date.fromisoformat(text), None
    except ValueError:
        return None, (
            f"the key `{SINCE_KEY}` of docs/agents/usine.md is not one valid day written AAAA-MM-JJ: the"
            " PR is refused as a precaution until it is fixed"
        )


def created_on(stamp: object) -> date | None:
    """The UTC day of a `createdAt` timestamp, None when it is not one."""
    match = TIMESTAMP.fullmatch(stamp) if isinstance(stamp, str) else None
    if match is None:
        return None
    try:
        moment = datetime.fromisoformat(match.group(1) + ("+00:00" if match.group(2) == "Z" else match.group(2)))
    except ValueError:
        return None
    return moment.astimezone(timezone.utc).date()


def _json(output: str | None) -> object:
    try:
        return json.loads(output) if output is not None else None
    except ValueError:
        return None


def _events(output: str | None) -> list[dict]:
    """The events `gh api --paginate` printed: one JSON array per page, read one after the other.

    Anything unreadable ends the list: the events then raise nothing, and the cap stays.
    """
    if output is None:
        return []
    decoder, position = json.JSONDecoder(), 0
    found: list[dict] = []
    while position < len(output):
        if output[position].isspace():
            position += 1
            continue
        try:
            page, position = decoder.raw_decode(output, position)
        except ValueError:
            return []
        if not isinstance(page, list):
            return []
        found.extend(item for item in page if isinstance(item, dict))
    return found


def count_prs(
    number: str, own: int | None, repo: str | None, cwd: str | None, run: Runner, since: date | None = None
) -> tuple[int, bool] | None:
    """`(count, started)` for ticket `number`, None when gh cannot say.

    `count` is the PRs, open or merged, that cite it (`own`, a PR being edited, left out), created on the
    day `since` or after it when it is given; `started` is whether at least one such PR was created before
    `since` (always False without `since`).
    """
    argv = ["pr", "list", "--state", "all", "--search", f"{number} in:body"]
    argv += ["--json", "number,state,body,createdAt", "--limit", SEARCH_LIMIT]
    if repo:
        argv += ["--repo", repo]
    listed = _json(run(argv, cwd))
    if not isinstance(listed, list):
        return None
    count, started = 0, False
    for item in listed:
        if not isinstance(item, dict):
            return None
        pr, state, body = item.get("number"), item.get("state"), item.get("body")
        if not isinstance(pr, int) or not isinstance(state, str) or not isinstance(body, str):
            return None
        if pr == own or state.upper() not in COUNTED_STATES or number not in cited(body):
            continue
        if since is not None:
            day = created_on(item.get("createdAt"))
            if day is None:
                return None
            if day < since:
                started = True
                continue
        count += 1
    return count, started


def current_pr(selector: str | None, repo: str | None, cwd: str | None, run: Runner) -> tuple[int, str] | None:
    """The number and the body of the PR `selector` names now (the current branch's without one)."""
    argv = ["pr", "view", *([selector] if selector else []), "--json", "number,body"]
    if repo:
        argv += ["--repo", repo]
    document = _json(run(argv, cwd))
    if not isinstance(document, dict):
        return None
    number, body = document.get("number"), document.get("body")
    return (number, body) if isinstance(number, int) and isinstance(body, str) else None


def _selector(args: list[str]) -> str | None:
    """The PR a `gh pr edit` names (number, branch or URL): its first word that is no option's value."""
    index = 0
    while index < len(args):
        word = args[index]
        if word == "--":
            return args[index + 1] if index + 1 < len(args) else None
        if not word.startswith("-"):
            return word
        index += 2 if word in EDIT_VALUE_OPTIONS else 1
    return None


def _token(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


class Check:
    """What one call needs to rule: the project, its cap, gh, and the state that remembers."""

    def __init__(
        self,
        root: Path,
        cap: int,
        config: Mapping[str, list[str]],
        run: Runner,
        state: State,
        since: date | None = None,
    ) -> None:
        self.root, self.cap, self.config, self.run, self.state, self.since = root, cap, config, run, state, since

    def raisers(self) -> set[str]:
        """The logins of the key `pr-cap-raiser`: the short identifier of each line, else its value."""
        found = set()
        for value in self.config.get(RAISER_KEY, []):
            login = value.rpartition(" | ")[2] if " | " in value else value
            if login.strip():
                found.add(login.strip().lower())
        return found

    def how_to_raise(self) -> str:
        if not self.raisers():
            return (
                f"The label `{RAISE_LABEL}` raises the cap to {RAISED_CAP} only when a login of the key"
                f" `{RAISER_KEY}` sets it, and that key is absent (sans objet, clé `{RAISER_KEY}` absente):"
                " nobody can raise it"
            )
        return (
            f"Only the label `{RAISE_LABEL}`, set by a login of the key `{RAISER_KEY}`, raises the cap"
            f" to {RAISED_CAP}"
        )

    def raised(self, number: str, repo: str | None, cwd: str | None) -> bool:
        """Whether the last event on the label `pr-cap-raised` of ticket `number` is a `labeled` by a raiser."""
        humans = self.raisers()
        if not humans:
            return False
        events = _events(self.run(["api", f"repos/{repo or '{owner}/{repo}'}/issues/{number}/events?per_page=100", "--paginate"], cwd))
        last = None
        for event in events:
            label = event.get("label")
            if event.get("event") in ("labeled", "unlabeled") and isinstance(label, dict) and label.get("name") == RAISE_LABEL:
                last = event
        if last is None or last.get("event") != "labeled":
            return False
        actor = last.get("actor")
        login = actor.get("login") if isinstance(actor, dict) else None
        return isinstance(login, str) and login.lower() in humans

    def ticket(self, number: str, own: int | None, repo: str | None, cwd: str | None, token: str) -> str | None:
        """Why one more PR may not cite ticket `number`, or None (the PR is then reserved)."""
        counted = count_prs(number, own, repo, cwd, self.run, self.since)
        if counted is None:
            return (
                f"the PRs of #{number} cannot be counted (gh absent, the network, or a gh error): the"
                " PR is refused as a precaution"
            )
        indexed, started = counted
        key = f"{self.root.resolve()}|#{number}"
        others = [item for item in self.state.reserved(key, KIND) if item.get("token") != token]
        count = with_reservations(indexed, others)
        limit = LAST_PR if started else self.cap  # a started ticket admits one last new PR
        if count >= limit < RAISED_CAP and self.raised(number, repo, cwd):
            limit = RAISED_CAP
        if count >= limit:
            since = f", created since {self.since.isoformat()} by the key `{SINCE_KEY}`" if self.since else ""
            last = (
                f"; #{number} was started before that day, so it admits {LAST_PR} new PR after the one in"
                " flight, as a last resort"
                if started and self.since
                else ""
            )
            return (
                f"#{number} already has {count} PRs for a cap of {limit} (key `{KEY}`, open or merged"
                f" PRs{since}{last}): {BLOCKED}. {self.how_to_raise()}"
            )
        self.state.reservations = [
            item
            for item in self.state.reservations
            if not ((item.get("key"), item.get("kind"), item.get("token")) == (key, KIND, token))
        ]
        self.state.reservations.append(
            {"key": key, "kind": KIND, "time": time.time(), "seen": indexed, "token": token}
        )
        self.state.changed = True
        return None

    def issue(self, endpoint: str, cwd: str | None) -> tuple[dict | None, str | None]:
        """What `gh api` says of the issue at `endpoint` (a PR is one), or why gh cannot say."""
        doc = _json(self.run(["api", endpoint.lstrip("/")], cwd))
        if isinstance(doc, dict):
            return doc, None
        return None, (
            f"the issue #{endpoint.rsplit('/', 1)[-1]} cannot be read (gh absent, the network, or a gh error), so"
            " whether it is a PR whose edit adds a ticket to the count is unknown: refused as a precaution"
        )

    def publication(self, found: Publication, cwd: str | None) -> str | None:
        """Why the PR `found` publishes may not go out, or None."""
        if found.act == CURL_ACT:
            doc, reason = self.issue(found.endpoint, cwd)
            if doc is not None and "pull_request" in doc:
                return (
                    f"a call to api.github.com outside gh could edit the PR #{found.endpoint.rsplit('/', 1)[-1]}"
                    " through `issues/<n>` unread; use gh"
                )
            return reason  # a real ticket (None) is not held
        tickets = cited(found.body)
        if not tickets:
            return None
        if found.endpoint == "graphql":
            return (
                "a PR is opened or edited with `gh pr create` or `gh pr edit`, where the hook reads the"
                f" tickets it cites against the cap of `{KEY}`: the mutation is refused"
            )
        pulls = PULLS.match(found.endpoint) if found.endpoint else None
        issue = ISSUE.match(found.endpoint) if found.endpoint and found.kind == "ticket" else None
        own: int | None = None
        if issue is not None:
            doc, reason = self.issue(found.endpoint, cwd)
            if doc is None:
                return reason
            if "pull_request" not in doc:
                return None  # a real ticket: its body is not a PR's
            own = int(issue.group(3))
            body = doc.get("body")
            tickets -= cited(body) if isinstance(body, str) else set()
        elif found.act == ("pr", "edit") or (pulls is not None and pulls.group(3)):
            selector = _selector(found.args) if pulls is None else pulls.group(3)
            current = current_pr(selector, found.repo, cwd, self.run)
            if current is None:
                return (
                    f"the PR `{selector or 'of the current branch'}` cannot be read (gh absent, the network,"
                    " or a gh error), so the tickets its edit adds cannot be counted: refused as a precaution"
                )
            own = current[0]
            tickets -= cited(current[1])
        for number in sorted(tickets, key=int):
            if reason := self.ticket(number, own, found.repo, cwd, _token(found.body)):
                return reason
        return None


def _repo_of_endpoint(endpoint: str) -> str | None:
    match = PULLS.match(endpoint) or ISSUE.match(endpoint)
    if match is None or "{" in match.group(1) or "{" in match.group(2):
        return None
    return f"{match.group(1)}/{match.group(2)}"


def _issue_edit(item: Publication) -> Publication:
    """`gh issue edit <n>` read as `gh api` on `issues/<n>`: gh resolves a PR number there too."""
    selector = _selector(item.args)
    match = ISSUE_SELECTOR.match(selector) if selector else None
    if match is None:
        raise Unreadable("`gh issue edit` names no issue number the hook can read")
    if match.group(1):
        repo = item.repo or "{owner}/{repo}"
        number = match.group(1)
    else:
        repo, number = f"{match.group(2)}/{match.group(3)}", match.group(4)
    return Publication("ticket", item.body, item.act, item.args, f"repos/{repo}/issues/{number}", item.repo)


def shell_publications(command: str, cwd: str | None) -> list[tuple[Publication, str | None]]:
    """Each PR body `command` publishes, with the directory it runs in; `Unreadable` if it cannot be read."""
    found: list[tuple[Publication, str | None]] = []
    docs = heredocs(command)
    here = cwd
    for words in commands(command, docs):
        if isinstance(words, str):
            continue
        if words[:1] == ["cd"] and len(words) > 1:
            here = _moved(here, words[1])
            continue
        local = None if here == UNKNOWN else here
        if curls_github(words):
            if API_PULLS.search(" ".join(words)):
                raise Unreadable("a call to api.github.com outside gh could open a PR unread; use gh")
            for word in words:
                if match := CURL_ISSUE.search(word):
                    owner, name, number = match.groups()
                    endpoint = f"repos/{owner}/{name}/issues/{number}"
                    found.append((Publication("ticket", "", act=CURL_ACT, endpoint=endpoint, repo=f"{owner}/{name}"), local))
            continue
        published = [
            item
            for item in publications(words, docs, local)
            if item.kind == "pr"
            or (item.kind == "ticket" and (item.act == ("issue", "edit") or (item.endpoint and ISSUE.match(item.endpoint))))
        ]
        act = gh_act(words)
        if act and act[:2] == ("pr", "create") and not published:
            raise Unreadable("`gh pr create` without `--body` or `--body-file`, its tickets unknown")
        for item in published:
            if item.act == ("issue", "edit"):
                item = _issue_edit(item)
            if item.endpoint and item.endpoint != "graphql":
                item = Publication(item.kind, item.body, item.act, item.args, item.endpoint, _repo_of_endpoint(item.endpoint))
            found.append((item, local))
    return found


def _mcp_issue_edit(tool: str, name: str, tool_input: Mapping[str, object]) -> list[Publication]:
    """The body an issue tool of a GitHub MCP server edits, read as `gh api` on `issues/<n>`: a PR is an issue."""
    if "comment" in name or not any(word in name for word in ("update", "write")):
        return []
    number = next((tool_input[k] for k in ("issue_number", "issueNumber", "number") if k in tool_input), None)
    editing = "update" in name or tool_input.get("method") == "update" or number is not None
    if not editing or "body" not in tool_input:
        return []  # opening a ticket, or an edit with no body: nothing a PR would count
    body = tool_input["body"]
    if not isinstance(body, str):
        raise Unreadable(f"the body of `{tool}` is no text")
    if isinstance(number, bool) or not isinstance(number, (int, str)) or not str(number).isdigit():
        raise Unreadable(f"the issue `{tool}` edits is not named")
    owner, repo = tool_input.get("owner"), tool_input.get("repo")
    named = f"{owner}/{repo}" if isinstance(owner, str) and isinstance(repo, str) else None
    endpoint = f"repos/{named or '{owner}/{repo}'}/issues/{number}"
    return [Publication("ticket", body, endpoint=endpoint, repo=named)]


def mcp_publications(tool: str, tool_input: Mapping[str, object]) -> list[Publication]:
    """The PR body a pull request tool of a GitHub MCP server publishes, or the body of an issue it edits
    (which may be a PR); none for any other tool."""
    name = tool.rsplit("__", 1)[-1].lower()
    if "issue" in name and "pull_request" not in name:
        return _mcp_issue_edit(tool, name, tool_input)
    if "pull_request" not in name or not any(word in name for word in ("create", "update", "write")):
        return []
    if "body" not in tool_input:
        return []
    body = tool_input["body"]
    if not isinstance(body, str):
        raise Unreadable(f"the body of `{tool}` is no text")
    owner, repo = tool_input.get("owner"), tool_input.get("repo")
    named = f"{owner}/{repo}" if isinstance(owner, str) and isinstance(repo, str) else None
    number = next((tool_input[k] for k in ("pullNumber", "pull_number", "number") if k in tool_input), None)
    method = tool_input.get("method")
    editing = "update" in name or method == "update"
    if editing and not isinstance(number, (int, str)):
        raise Unreadable(f"the PR `{tool}` edits is not named")
    endpoint = f"repos/{owner}/{repo}/pulls" + (f"/{number}" if editing else "")
    return [Publication(KIND, body, endpoint=endpoint, repo=named)]


def refusal(event: Mapping[str, object], run: Runner = run_gh) -> str | None:
    """Why the tool call of `event` may not run, or None."""
    tool, tool_input = event.get("tool_name"), event.get("tool_input")
    if not isinstance(tool_input, dict) or not isinstance(tool, str):
        return None
    root = project_root(event)
    config = load(root)
    cap, bad = cap_of(config)
    if bad is None and cap is None:
        return None  # sans objet (key `ticket-pr-cap` absent): nothing is read
    since = None
    if bad is None:
        since, bad = since_of(config)  # key `ticket-pr-cap-since` absent: no date step, every PR counts
    where = event.get("cwd")
    cwd = where if isinstance(where, str) else None
    try:
        if tool in ("Bash", "PowerShell"):
            command = tool_input.get("command")
            if not isinstance(command, str) or not may_publish(command):
                return None
            found = shell_publications(command, cwd)
        elif tool.startswith("mcp__"):
            found = [(item, cwd) for item in mcp_publications(tool, tool_input)]
        else:
            return None
    except Unreadable as error:
        return UNREAD.format(error)
    if bad is not None:
        return bad if any(cited(item.body) for item, _ in found) else None
    assert cap is not None
    with state_file() as state:
        check = Check(root, cap, config, run, state, since)
        for item, where in found:
            if reason := check.publication(item, where):
                state.changed = False  # the call is refused: nothing it would open is reserved
                return reason
    return None


def main() -> int:
    event = json.load(sys.stdin)
    reason = refusal(event if isinstance(event, dict) else {})
    if reason is None:
        return 0
    sys.stderr.write(f"{PREFIX}: {reason}.\n")
    return 2


def guarded_main() -> int:
    """`main`, failing closed: a crash of the guard refuses the call and says so."""
    try:
        return main()
    except Exception as error:  # noqa: BLE001 - any failure of the guard must refuse the call
        sys.stderr.write(
            f"guard_pr_cap failed ({type(error).__name__}: {error}): the call is refused as a"
            " precaution. This is not a rule of the repository; retry, and tell the human if it"
            " persists.\n"
        )
        return 2


if __name__ == "__main__":
    use_utf8()
    raise SystemExit(guarded_main())
