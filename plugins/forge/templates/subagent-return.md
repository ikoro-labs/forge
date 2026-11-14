<!-- template: subagent-return | max-lines: 20, this comment excluded | required: none | rules: socle.md -->
RESULT: <done | blocked | failed>, <the answer in one line>

| Finding | Evidence |
|---|---|
| <one fact per row> | <path:line, command and its output, or URL> |

UNPROVEN: <what could not be checked, or none>

- An agent of the plugin returns the block its `agents/<name>.md` declares instead; a project maps
  its own agents to a format with the key `output-agent-format`.
- At most 200 words of prose (key `output-words-subagent-return`); tables and code blocks do not
  count. No paragraph over 60 words (key `output-words-paragraph`).
