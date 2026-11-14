<!-- template: session-reply | max-lines: 15, this comment excluded | required: Done or Fait, Measured or Measure or Mesure or Mesuré, Awaiting your decision or Attend ta décision or Attend votre décision, CI and runners or CI et runners | rules: socle.md -->
Done: <what was done, with its link or SHA; or nothing>

Measured: <each figure with its source, date and denominator; or nothing measured>

Awaiting your decision: <the point and its recommendation; or nothing>

CI and runners: <one line from `scripts/report_mail.py --line`; or `not applicable`>

- Free language: `Fait`, `Mesure`, `Attend ta décision` and `CI et runners` are the same four fields.
- More than two elements in a field go in a table, never in a list.
- At most 150 words of prose (key `output-words-session-reply`); tables and code blocks do not
  count. No paragraph over 60 words (key `output-words-paragraph`).
