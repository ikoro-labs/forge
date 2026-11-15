<!-- template: session-reply | max-lines: 15, this comment excluded | required: Done or Fait, Measured or Measure or Mesure or Mesuré, Awaiting your decision or Attend ta décision or Attend votre décision, CI and runners or CI et runners, Features | rules: socle.md -->
Done: <what was done, with its link or SHA; or nothing>

Measured: <each figure with its source, date and denominator; or nothing measured>

Awaiting your decision: <the point and its recommendation; or nothing>

CI and runners: <one line from `scripts/report_mail.py --line`; or `not applicable`>

Features: <the output of `scripts/report_mail.py --features`, copied as printed, a table or one line>

- Free language: `Fait`, `Mesure`, `Attend ta décision` and `CI et runners` are the first four fields; `Features` is the same word in both.
- `Features` is the script's table (`Feature | Closed / total | Open PRs | Blocked | Ready`, then the `In parallel:` line) or its single line, never your words: the guard refuses the rest, and leaves the block out of the line and word caps.
- More than two elements in a field go in a table, never in a list.
- At most 150 words of prose (key `output-words-session-reply`); tables and code blocks do not count. No paragraph over 60 words (key `output-words-paragraph`).
