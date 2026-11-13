<!-- template: verdict | max-lines: 30, this comment excluded | rules: socle.md -->
```text
VERDICT: ACCEPT | REJECT
ROUND: 1 | 2 | 3
HEAD: <full SHA of the judged head>
SOCLE: <full SHA of the main commit whose rules round 1 read>
SPEC: #<ticket>: <n> criteria covered, <n> partial, <n> missing
FINDINGS:
- [BLOCKER] path:line | <F-n, L-n, A<n> or tests/<path>::<name>> | <failure scenario>
- [MINOR] path:line | <F-n or L-n of nature prose> | <what is wrong>
- [NOTE] path:line | out of diff: <defect> | <why it does not reject>
GATES: <one line on the qc-gate table>
```

- One `SPEC:` line per ticket; a PR without a ticket writes `SPEC: none (<reason>)`.
- `FINDINGS:` without a finding is `- none`. A REJECT has at least one `[BLOCKER]`, an ACCEPT none.
- Rounds 2 and 3 copy the round 1 `SOCLE`. They judge the previous round's blockers, then only the
  lines the correction changed.
