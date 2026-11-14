<!-- template: verdict | max-lines: 30, this comment excluded | rules: socle.md -->
```text
VERDICT: ACCEPT | REJECT
ROUND: 1 | 2 | 3
HEAD: <full SHA of the judged head>
SOCLE: <full SHA of the main commit whose rules round 1 read>
GRANTED: <https link to the human's grant, only past round 3>
SPEC:
  - #<ticket>: <n> criteria covered, <n> partial, <n> missing
FINDINGS:
- [BLOCKER] path:line | <A<n>.<k>, F-n, L-n or regression <test>> | <failure scenario>
- [BLOCKER] path:line | <security F-n or L-n> | <scenario> | proof: <path>::<test> or `<command>`
- [MINOR] path:line | <F-n or L-n of nature prose> | <what is wrong>
- [NOTE] path:line | out of diff: <defect> | <why it does not reject>
PROPOSAL: <input> | <expected result>, a case for the next tickets, never blocking
GATES:
  - <measure>: <value>
```

- `SPEC:` and `GATES:` stay empty on their line: one sub-line per ticket, one per measure, each
  within 60 words. A PR without a ticket writes `SPEC: none (<reason>)`. No line stands outside
  the keys: a free line stuck to the `GATES:` paragraph belongs to that paragraph.
- A finding keeps one line, `- [SEV] path:line | rule | scenario`, within 60 words, no sub-line.
  Paths, commands, test ids and quotations go between backticks: a span counts as one word.
- `FINDINGS:` without a finding is `- none`, or empty on an ACCEPT. A REJECT has a `[BLOCKER]`, an ACCEPT none.
- Three rounds at most: past 3, `GRANTED:` links the human's grant. `ROUND:` holds the number alone.
- A blocker cites a case of the ticket's frozen list, a rule, or `regression <test>` (green on the
  base, red on the head); a security rule adds its proof. `guard_cases` refuses any other.
- Rounds 2 and 3 copy the round 1 `SOCLE`, judge the last blockers, then the lines changed since.
- The hook `guard_output` refuses a verdict comment that `scripts/parse_output.py` refuses, the
  one source of its rules: a missing or unknown key, a `ROUND:` with text, a REJECT without blocker.
