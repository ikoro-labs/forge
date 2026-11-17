## Summary

<!-- What the PR changes and why, in five lines at most. Cite the ticket: `Closes #n`, or
`Refs #n` with the points this PR delivers. -->

### Change view

<!-- The smallest view that is enough: pseudo-code, call tree, file tree, diff sketch or Mermaid
diagram. Leave out when the diff fits in a few lines. -->

## Door

<!-- `two-way`: going back costs little. `one-way`: a destructive gesture, a release, a data
migration, a decision hard to undo; name the gesture that cannot be undone. -->

## Blast radius

<!-- One word (none, local, consumers...) and one sentence on what a consumer project can see
change at the merge (a variable, a gesture, the behaviour of a hook), then what a reader could
believe touched and that does not change (version, other hooks, projects). -->

## Proofs

<!-- Per criterion test: the red output with the reason it fails, then the green output.
`uv run --no-project --quiet --with pytest==9.2.0 python -m pytest tests`, `claude plugin validate .`
and `claude plugin validate plugins/forge` with their result. Tried on a real machine (system,
Claude Code version), or "not yet". -->

## Rapport d'agent

<!-- Left empty: `/forge:qc` writes it, in French. -->
