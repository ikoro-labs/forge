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
- [BLOCKER] path:line | <F-n, L-n, A<n> or tests/<path>::<name>> | <failure scenario>
- [MINOR] path:line | <F-n or L-n of nature prose> | <what is wrong>
- [NOTE] path:line | out of diff: <defect> | <why it does not reject>
GATES:
  - <measure>: <value>
```

- `SPEC:` and `GATES:` stay empty on their line: one sub-line per ticket, one per measure, each
  within 60 words. A PR without a ticket writes `SPEC: none (<reason>)`.
- A finding keeps one line, `- [SEV] path:line | rule | scenario`, within 60 words, with no
  sub-line. Paths, commands, test ids and quotations go between backticks: a span counts as one word.
- `FINDINGS:` without a finding is `- none`, or left empty on an ACCEPT. A REJECT has at least one `[BLOCKER]`, an ACCEPT none.
- Three rounds at most: a round past 3 carries `GRANTED:`, the https link to the human's grant.
  `ROUND:` holds the number alone.
- Rounds 2 and 3 copy the round 1 `SOCLE`. They judge the previous round's blockers, then only the
  lines the correction changed.
- The hook `guard_output` refuses a verdict comment that `scripts/parse_output.py` refuses, the
  one source of its rules: a missing or unknown key, a `ROUND:` with text, a REJECT without blocker.
