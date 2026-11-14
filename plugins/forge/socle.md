# Common criteria

The one criteria text that the acceptance test author, the coder in self-review, `forge:qc-gate`,
`forge:qc-conf`, the security reviewer and `forge:staff-engineer` read. A repository adds its own
rules (see Local rules) and does not repeat these.

## How a finding rejects

- A `[BLOCKER]` cites, in its rule field, a case `A<n>.<k>` of the ticket's frozen list (see
  Validation cases), a rule id `F-n` or `L-n`, or `regression <test>`, a test green on the base and
  red on the head. A finding that cites none of them is a `NOTE` and never rejects; a missing case
  becomes a `PROPOSAL:` line for the next tickets, a missing rule a PR that adds it.
- A security `[BLOCKER]` cites a frozen case or a security rule, and a rule with its proof: a test
  or a command reproduced. The security rules are the `security` rows below, closed; a repository
  adds its own with the key `security-rules` (`L-n` ids of its local rules).
- A breach, in the diff, of a `security`, `code`, `test` or `architecture` rule is a `BLOCKER`.
  A breach of a `prose` rule, F-18 and F-19 included wherever the text sits, is a `MINOR` and does
  not reject.
- A repository may raise the severity of an `F-n` by a local rule `L-n`.
- A defect outside the diff is a `NOTE` that starts with `out of diff`, and never rejects.
- A rule that a required check enforces rejects through that check: the finding cites the failing
  check and the rule id.

## Rules

Proof: the mechanism that enforces the rule, or `reading` when only a reviewer can see it.

| Id | Nature | Rule | Proof |
|---|---|---|---|
| F-1 | security | No secret or personal data (token, key, credential, real user data) appears in the repository, an argv, a log, a trace, a prompt, an error message or a `repr`; code that handles a secret has a test that it does not leak. | secret scan in `required-contexts`; reading |
| F-2 | security | An error, a timeout, an unreachable service or a missing value refuses instead of letting through, and no exception is swallowed (`except Exception: pass` or its equivalent). | lint rule where the linter has one; reading |
| F-3 | security | Input from outside the trust boundary (user, ticket, cloned repository, agent, model output) is validated against a schema before use and never executed on the host; a model output that fails its schema is a failure. | reading |
| F-4 | security | Authorization is checked server-side on the object, refuses in doubt, and never rests on what a model decided. | test of F-12; reading |
| F-5 | security | No irreversible write tool is exposed to an agent, and no tool output raises a privilege. | reading |
| F-6 | security | The diff keeps the standard controls: TLS verification on, parameterized queries, no URL taken from input fetched, no home-made cryptography. | reading |
| F-7 | security | Every dependency is pinned: package by lockfile, image by digest, CI action by commit SHA, build backend by version. | reading |
| F-8 | code | An added dependency is justified in the PR body with its provenance and licence; a structural one also has an ADR. | reading |
| F-9 | test | Each ticket criterion `A<n>` has a test that fails on the base and passes on the head. | `qc-gate`, key `red-replay` |
| F-10 | test | Added or changed behaviour has a test that proves it, and each test asserts what its name says. | reading |
| F-11 | test | No test is deleted, skipped or weakened unless the ticket says so; acceptance tests keep the assertions of their acceptance commit. | `qc-gate`, key `never-weaken`; reading |
| F-12 | test | A security control (filter, permission, validation) has a test of its refusal, with at least one input that tries to bypass it. | reading |
| F-13 | code | Lint and type checks pass in strict mode; an escape hatch (`type: ignore`, `noqa`, a line added or raised in a baseline or allowlist) carries its reason on the same line. | checks in `required-contexts`; key `baselines` |
| F-14 | code | No prompt is hard-coded in application code. | reading |
| F-15 | architecture | Code follows the module map of the accepted design: a module is used only through its declared interface, and dependencies point inward (the domain imports no framework or I/O library). | import check where the repository has one; reading |
| F-16 | architecture | No business logic in an HTTP handler or a UI component. | reading |
| F-17 | code | A PR stays within the size that the key `size-check` allows; a larger change is split into parts of the same ticket. | `qc-gate`, key `size-check` |
| F-18 | prose | Identifiers, comments, docstrings, logs and messages that the diff adds or rewrites are in English. | reading |
| F-19 | prose | A comment, docstring, message or PR sentence says only what the code does, and what was not tried says so. | reading |
| F-20 | prose | No em dash in added text. | hook `after_write` |
| F-21 | prose | No third party used as a model, competitor or namesake is named, nor its people, repositories or identifiers: write "anonymous". Tools the project uses are named. | reading |
| F-22 | prose | Branch `<type>/<slug>` (`feat`, `fix`, `docs`, `test`, `chore`; slug in lowercase English with hyphens); PR title and commit subject `<type>(<scope>): <what changes>`, never "wip"; a commit body says why and ends with `Refs #n` or `Closes #n`, then the `Co-Authored-By` line. | reading of `git log` and the PR title |
| F-23 | prose | The PR body follows `templates/pr.md` and cites its ticket: `Closes #n`, or `Refs #n` with the points it delivers. | key `trace-check`; reading |

## Validation cases

Each ticket of a feature lists, in its body, the closed set of cases the review judges it on, one
line each, `A<n>.<k> | <input> | <expected result>`, and one line `AGREED: <roles>`.

- **Round 0**, before any code: the ticket cutting writes the cases; the test author, then
  `forge:qc-conf` (the body and the files it names, once, no diff, no replay) and each reviewer of
  the key `validation-reviewer` whose paths the ticket names read them once and add cases. The
  coder agrees when it takes the ticket. Round 0 is not a REJECT; its tokens count in the ticket's
  `ticket-budget`. Cost: one call per reader, not measured yet.
- **Freeze**: the last edit of the body comes before the PR opens. A list found wrong later is
  corrected in a next part of the ticket (a new PR `Refs #n`, opened after the edit), or by a login
  of the key `validation-owner`.
- **Transition**: on a ticket created before the date of the key `validation-cases`, a criterion
  `A<n>` is the case `A<n>.1`.
- **Held by `guard_cases`**: `gh pr create` needs the cases and a full `AGREED:` line (`test-author`,
  `coder`, `qc-conf`, each reviewer whose paths the diff touches); a verdict is refused when a
  blocker cites nothing above, a missing case or rule, a security rule without proof, or when a
  ticket body was edited after the PR opened by a login outside `validation-owner`. The hook reads
  gh behind `env`, `command`, a path, `bash -c`, `eval` or `$(...)`, and refuses a body it cannot
  read; a GitHub tool of an MCP server may comment, never open a PR nor post a verdict.
- **Not held by a hook**: that a role read the list before its name went on `AGREED:`; that a case
  is the right one; that a `regression` test is green on the base and red on the head (`qc-gate`
  replays it); that a finding is about security when it cites no security rule; that the editor
  login is the owner and not an agent sharing the owner's account.

## Local rules

A repository declares its own rules in `docs/agents/socle.md`, with the same table and ids `L-1`,
`L-2`..., no leading zero; its key `review-grid` points to that file. A local rule may be stricter
than an `F-n`, never looser: loosening one changes this file. A removed id is never reused.

## Freezing

The round 1 verdict carries `SOCLE: <sha>`, the full SHA of the repository's `main` commit whose
texts the judge read. That commit pins the forge version, so one SHA fixes both this file and the
local rules. Rounds 2 and 3 carry the same `SOCLE` and judge against the same texts; a rule merged
in between applies from the next PR.

## Templates

Each document an agent writes follows its template under `templates/`, and `features/` for feature
documents. Eight hold a line cap at their head: `ticket.md`, `pr.md`, `verdict.md`, `adr.md`,
`comment.md`, `subagent-return.md`, `session-reply.md`, `report-mail.md`; the feature templates hold none. The
hook `guard_output` holds a ticket, a PR, a comment, a subagent return, a session reply and a report mail to
that cap, in written lines; a verdict keeps every finding.
