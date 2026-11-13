"""PreToolUse hook: a PR opens on agreed validation cases, and a verdict blocks only on them.

Once the project declares the `validation-cases` key (see `cases.py`), refused with exit code 2:

- `gh pr create` whose body closes or refers to a ticket of a feature that holds no case, no
  `AGREED:` line, or an `AGREED:` line short of a role; the PR's files (for the perimeters of the
  `validation-reviewer` key) come from `git diff --name-only <base>...<head>`;
- a verdict (a comment whose first line is `VERDICT:`) posted on a PR by `gh pr comment`,
  `gh pr review`, `gh issue comment` or `gh api` on the PR's comments or reviews, when a blocker
  stands on nothing the cases, the rules or a regression give, or a ticket of the PR was edited
  after the PR opened; a verdict through GraphQL, or an edit of a posted comment through `gh api`,
  is refused outright, since the guard does not resolve its PR;
- a body it cannot read before gh does, as the other guards refuse it, and a `gh pr create`
  without `--body` or `--body-file` (`--fill`, an editor), whose ticket cannot be read;
- a call to GitHub that fails or times out: the guard refuses rather than lets through.

The tickets and the PR are read with one GraphQL query each (`lastEditedAt` and `editor` give the
last edit of a body). Without the key the hook reads nothing and refuses nothing. The standard
library only.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from datetime import datetime

import cases
from gh_bodies import UNREAD, Publication, Unreadable, curls_github, opens_verdict, publications
from guard_git import UNKNOWN, _commands, _moved, gh_act, split_heredocs
from usine import load, project_root

REFUSED = 2
TIMEOUT_SECONDS = 20
Runner = Callable[[list[str], "str | None"], str]
POSITIONAL_SKIP = frozenset({"--body", "-b", "--body-file", "-F", "--repo", "-R", "--subject", "-t", "--comment", "-c"})
PR_URL = re.compile(r"/(?:pull|issues)/(\d+)(?:[/?#]|$)")
API_TARGET = re.compile(r"^(?:/?repos/([^/]+)/([^/]+)/)?(?:issues/(\d+)/comments|pulls/(\d+)/(?:comments|reviews))$")
API_EDIT = re.compile(r"/(?:issues|pulls)/comments/\d+$|/pulls/\d+/reviews/\d+$")
PR_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){"
    "issueOrPullRequest(number:$number){__typename ... on PullRequest{number createdAt body}}}}"
)
TICKET_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){"
    "issueOrPullRequest(number:$number){__typename ... on Issue{number body createdAt lastEditedAt editor{login}}}}}"
)


class GitHubError(RuntimeError):
    """A gh or git call that failed, timed out or answered something unreadable."""


def run_command(argv: list[str], cwd: str | None) -> str:
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise GitHubError(f"`{' '.join(argv[:3])}` did not run: {error}") from error
    if done.returncode != 0:
        raise GitHubError(f"`{' '.join(argv[:3])}` failed: {done.stderr.strip()[:300]}")
    return done.stdout


def _moment(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError as error:
        raise GitHubError(f"GitHub's date `{value}` cannot be read") from error


def _created(node: Mapping[str, object], number: int) -> datetime:
    moment = _moment(node.get("createdAt"))
    if moment is None:
        raise GitHubError(f"the creation date of #{number} cannot be read")
    return moment


class GitHub:
    """The PR and the tickets of one repository, read through gh."""

    def __init__(self, run: Runner, here: str | None, repo: str | None) -> None:
        self.run, self.here, self.repo = run, here, repo

    def _graphql(self, query: str, number: int) -> dict:
        owner, name = ("{owner}", "{repo}")
        if self.repo:
            parts = self.repo.rstrip("/").split("/")
            owner, name = parts[-2], parts[-1]
        argv = ["gh", "api", "graphql", "-f", f"query={query}", "-F", f"number={number}", "-F", f"owner={owner}", "-F", f"name={name}"]
        try:
            data = json.loads(self.run(argv, self.here))
            return data["data"]["repository"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise GitHubError(f"GitHub's answer for #{number} cannot be read") from error

    def pull_request(self, number: int) -> cases.PullRequest | None:
        node = self._graphql(PR_QUERY, number)["issueOrPullRequest"]
        if not node or node.get("__typename") != "PullRequest":
            return None
        return cases.PullRequest(number, str(node.get("body") or ""), _created(node, number))

    def ticket(self, number: int) -> cases.Ticket | None:
        """The ticket `#number`, None when the number is a PR's."""
        node = self._graphql(TICKET_QUERY, number)["issueOrPullRequest"]
        if not node:
            raise GitHubError(f"ticket #{number} cannot be read")
        if node.get("__typename") != "Issue":
            return None
        editor = node.get("editor") or {}
        return cases.Ticket(
            number, str(node.get("body") or ""), _created(node, number), _moment(node.get("lastEditedAt")), editor.get("login")
        )

    def tickets(self, body: str) -> list[cases.Ticket]:
        """The tickets a PR body closes or refers to; a PR it cites is not one."""
        found = (self.ticket(number) for number in cases.ticket_refs(body))
        return [ticket for ticket in found if ticket is not None]

    def selected(self, selector: str | None) -> int:
        """The number of the PR a `gh pr` selector names: a number, a URL, a branch, or the current one."""
        if selector and selector.isdigit():
            return int(selector)
        if selector and (match := PR_URL.search(selector)):
            return int(match.group(1))
        argv = ["gh", "pr", "view", *([selector] if selector else []), "--json", "number"]
        argv += ["--repo", self.repo] if self.repo else []
        try:
            return int(json.loads(self.run(argv, self.here))["number"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise GitHubError(f"the PR of `{selector or 'the current branch'}` cannot be read") from error


def _option(args: list[str], names: tuple[str, str]) -> str | None:
    long, short = names
    for index, word in enumerate(args):
        if word in names:
            return args[index + 1] if index + 1 < len(args) else None
        if word.startswith(long + "="):
            return word[len(long) + 1 :]
        if word.startswith(short) and not word.startswith("--") and len(word) > 2:
            return word[2:].removeprefix("=")
    return None


def _positional(args: list[str]) -> str | None:
    index = 0
    while index < len(args):
        word = args[index]
        if word == "--":
            return args[index + 1] if index + 1 < len(args) else None
        if not word.startswith("-"):
            return word
        index += 2 if word in POSITIONAL_SKIP else 1
    return None


def changed_files(run: Runner, here: str | None, args: list[str]) -> list[str]:
    """The files of the PR `gh pr create` would open: `<base>...<head>`, `origin/<base>` first."""
    base = _option(args, ("--base", "-B"))
    head = (_option(args, ("--head", "-H")) or "HEAD").split(":")[-1]
    base_ref = f"origin/{base}" if base else run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], here).strip()
    return [line for line in run(["git", "diff", "--name-only", f"{base_ref}...{head}"], here).splitlines() if line]


def _pr_create(found: Publication, run: Runner, here: str | None, config: Mapping[str, list[str]]) -> list[str]:
    since = cases.adoption(config)
    assert since is not None
    github = GitHub(run, here, found.repo)
    tickets = github.tickets(found.body)
    return cases.pr_problems(tickets, since, config, lambda: changed_files(run, here, found.args))


def _verdict_target(found: Publication, github: GitHub) -> int | None | str:
    """The PR number a verdict goes to, None when it goes to a ticket, or why it is refused."""
    if found.endpoint:
        if found.endpoint == "graphql" or API_EDIT.search(found.endpoint):
            return "a verdict is posted as a new comment with `gh pr comment`, not through GraphQL or an edit"
        match = API_TARGET.search(found.endpoint)
        if match is None:
            return "the PR of this verdict cannot be read from its endpoint: post it with `gh pr comment`"
        if match.group(1) and match.group(1) != "{owner}":
            github.repo = f"{match.group(1)}/{match.group(2)}"
        return int(match.group(3) or match.group(4))
    selector = _positional(found.args)
    if found.act and found.act[0] == "issue":
        if not selector:
            return "the ticket or PR of this verdict cannot be read: name its number"
        match = PR_URL.search(selector)
        return int(match.group(1)) if match else int(selector) if selector.isdigit() else "unreadable selector"
    return github.selected(selector)


def _verdict(found: Publication, run: Runner, here: str | None, config: Mapping[str, list[str]], root) -> list[str]:
    since = cases.adoption(config)
    assert since is not None
    github = GitHub(run, here, found.repo)
    target = _verdict_target(found, github)
    if isinstance(target, str):
        return [target]
    if target is None:
        return []
    pr = github.pull_request(target)
    if pr is None:
        return []
    tickets = github.tickets(pr.body)
    return cases.verdict_problems(found.body, pr, tickets, since, config, cases.rules(root, config))


def _refused(text: str) -> tuple[int, str]:
    return REFUSED, f"Blocked by the forge plugin (guard_cases): {text}\n"


def outcome(event: Mapping[str, object], run: Runner = run_command) -> tuple[int, str]:
    """`(0, "")` to let the command run, or `(2, reason)`."""
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not ("gh" in command or "api.github.com" in command):
        return 0, ""
    root = project_root(event)
    config = load(root)
    if cases.KEY not in config:
        return 0, ""
    cwd = event.get("cwd")
    here: str | None = cwd if isinstance(cwd, str) else None
    heredoc = split_heredocs(command)[1]
    try:
        cases.adoption(config)
        for words in _commands(command):
            if isinstance(words, str):
                continue
            if words[:1] == ["cd"] and len(words) > 1:
                here = _moved(here, words[1])
                continue
            local = None if here == UNKNOWN else here
            if curls_github(words):
                return _refused("a call to api.github.com outside gh could publish a body unread; use gh")
            found = publications(words, heredoc, local)
            act = gh_act(words)
            if act and act[:2] == ("pr", "create") and not found:
                raise Unreadable("`gh pr create` without `--body` or `--body-file`, its ticket unknown")
            for item in found:
                problems: list[str] = []
                if item.act == ("pr", "create"):
                    problems = _pr_create(item, run, local, config)
                elif item.kind == "comment" and opens_verdict(item.body):
                    problems = _verdict(item, run, local, config, root)
                if problems:
                    return _refused("fix each point, then run the command again:\n" + "\n".join(f"- {p}" for p in problems))
    except Unreadable as error:
        return _refused(UNREAD.format(error))
    except cases.ConfigError as error:
        return _refused(f"{error} (docs/agents/usine.md)")
    except GitHubError as error:
        return _refused(f"{error}; refused rather than let through unchecked")
    return 0, ""


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.stderr.write("Blocked by the forge plugin (guard_cases): the event cannot be read.\n")
        return REFUSED
    code, message = outcome(event if isinstance(event, dict) else {})
    if message:
        sys.stderr.write(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
