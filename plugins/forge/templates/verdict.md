<!-- template: verdict | max-lines: 30, this comment excluded | rules: socle.md -->
```text
VERDICT: ACCEPT | REJECT
ROUND: 1 | 2 | 3
HEAD: <full SHA of the judged head>
SOCLE: <full SHA of the main commit whose rules round 1 read>
GRANTED: <https link to the human's grant, only past round 3>
SPEC: #<ticket>: <n> criteria covered, <n> partial, <n> missing
FINDINGS:
- [BLOCKER] path:line | <A<n>.<k>, F-n, L-n or regression <test>> | <failure scenario>
- [BLOCKER] path:line | <security F-n or L-n> | <scenario> | proof: <path>::<test> or `<command>`
- [MINOR] path:line | <F-n or L-n of nature prose> | <what is wrong>
- [NOTE] path:line | out of diff: <defect> | <why it does not reject>
PROPOSAL: <input> | <expected result>, a case for the next tickets, never blocking
GATES: <one line on the qc-gate table>
```

- One `SPEC:` line per ticket; a PR without a ticket writes `SPEC: none (<reason>)`.
- `FINDINGS:` without a finding is `- none`. A REJECT has at least one `[BLOCKER]`, an ACCEPT none.
- Three rounds at most: a round past 3 carries `GRANTED:`, the https link to the human's grant.
  `ROUND:` holds the number alone.
- A blocker cites a case of the ticket's frozen list, a rule, or `regression <test>` (green on the
  base, red on the head); a security rule adds its proof. `guard_cases` refuses any other.
- Rounds 2 and 3 copy the round 1 `SOCLE`. They judge the previous round's blockers, then only the
  lines the correction changed.
