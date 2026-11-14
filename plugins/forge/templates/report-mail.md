<!-- template: report-mail | max-lines: 150, this comment excluded | required: What changed or Ce qui a changé, Awaiting you or Ce qui t'attend, CI and runners or CI et runners | rules: socle.md -->
<h2>Factory report, <repositories>, <UTC time></h2>

<h3>What changed</h3>
<One line per event since the last mail sent: a merge, a verdict, the attention label, main's CI, an open PR, the runners of a host. Nothing else: no list of what an earlier mail already said.>

<h3>Awaiting you</h3>
<One line per thing only the human can do, or "Nothing.">

<h3>CI and runners</h3>
<A table of the runners by host, then one line each: queued and running runs, the last run of main, memory and disk of each host.>

<h3>Figures</h3>
<A table: each figure with its repository.>

- The mail is HTML, built by `scripts/report_mail.py`; this template says what the hook
  `guard_report_mail.py` checks before the send is recorded.
- Free language: `Ce qui a changé`, `Ce qui t'attend` and `CI et runners` are the same three parts.
- A table is required (a line that starts with `|` once the HTML is read); at most 500 words
  (key `output-words-report-mail`, `0` for none); no paragraph over 60 words
  (key `output-words-paragraph`).
