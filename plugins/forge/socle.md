# Common criteria

The one criteria text that the acceptance test author, the coder in self-review, `forge:qc-gate`,
`forge:qc-conf`, the security reviewer and `forge:staff-engineer` read. A repository adds its own
rules (see Local rules) and does not repeat these.

## How a finding rejects

- A `[BLOCKER]` cites, in its rule field, a rule id `F-n` or `L-n`, a ticket criterion `A<n>`, or
  an acceptance test `tests/<path>::<name>`. A finding that cites none of them is a `NOTE` and
  never rejects; it can become a PR that adds a rule, valid for the PRs that follow.
- A breach, in the diff, of a `security`, `code`, `test` or `architecture` rule is a `BLOCKER`.
  Comments, docstrings, log and error messages and test names are code. A breach of a `prose` rule
  outside code (a document, a PR body) is a `MINOR` and does not reject.
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

Each document an agent writes follows its template under `templates/`, within the line cap written
at its head: `ticket.md`, `pr.md`, `verdict.md`, `adr.md`, and `features/` for feature documents.
