"""ikoro-labs/forge#345 B5 : every key of the template `usine.md` is classified.

A key either bounds the agent's powers (`usine.SENSITIVE_KEYS`: read in `usine-gardes.md`, as
`origin/main` holds it) or is free (`FREE_KEYS` below: read in `usine.md`). A key added to the template
without a class would be free by default, and a guard key would then be one the agent can write: this
test fails until the new key is put on one side.
"""

import unittest

import support
from usine import SENSITIVE_KEYS, parse

TEMPLATE = support.PLUGIN / "templates" / "usine.md"

# The keys of the template that do not bound the agent: `usine.md` holds them, and a change to them
# is an ordinary PR. To add a key to the template, add it here, or to `usine.SENSITIVE_KEYS`.
FREE_KEYS = frozenset(
    {
        "agent-cache-dir", "architecture-check", "baselines", "browser-drive", "ci-replay",
        "ci-replay-light",
        "completion-column", "computer-use-host", "decision-matrix", "dependency-min-age", "doc-cap",
        "doc-frontmatter", "doc-index", "domain-arbiter", "domain-owner", "domain-rules",
        "domain-skill", "e2e-budget-usd", "e2e-command", "e2e-repo", "em-dash-allowances",
        "entry-gate", "feature-catalog-command", "feature-dir", "feature-gate", "feature-state",
        "format-on-write", "git-rules", "glossary", "incident-dir", "install", "journey-paths",
        "journey-replay", "lever-peers", "lint-on-write", "lockfile", "merge-method",
        "output-agent-format", "output-extra-keys", "output-template", "output-words-comment",
        "output-words-paragraph", "output-words-pr", "output-words-report-mail",
        "output-words-session-reply", "output-words-subagent-return", "output-words-ticket",
        "pr-template", "product-source", "property-test-lib", "question-default-delay",
        "recording-command", "recurring-finding", "red-replay", "release-tag", "release-trigger",
        "report-attention-label", "report-digest-hour", "report-host", "report-host-floor",
        "report-host-probe", "report-main-workflow", "report-repo", "required-contexts",
        "rescue-bundle-dir", "review-grid", "screenshot-command", "security-rules", "shared-doc",
        "shared-resource", "size-check", "sla", "slo-issue", "slo-review-date", "source-author",
        "speed-label", "stack", "test-path", "test-skill", "ticket-skill", "trace-check", "trace-replay",
        "trimmed-command", "ui-forbidden-word", "ui-labels", "validation-cases",
    }
)  # fmt: skip


def unclassified(template: str) -> list[str]:
    """The keys of `template` that are neither sensitive nor free."""
    return sorted(set(parse(template)) - SENSITIVE_KEYS - FREE_KEYS)


class EveryTemplateKeyIsClassified(unittest.TestCase):
    def test_b5_no_key_of_the_template_is_left_unclassified(self) -> None:
        """#345 B5: the template as it stands has a class for each of its keys."""
        left = unclassified(TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(left, [], f"classify in tests/test_usine_keys_classified.py or usine.SENSITIVE_KEYS: {left}")

    def test_b5_a_key_added_to_the_template_without_a_class_fails(self) -> None:
        """#345 B5: the check itself: a new key line is reported, a classified one is not."""
        added = TEMPLATE.read_text(encoding="utf-8") + "\n- `brand-new-key` : `<valeur>`\n- `merge-method` : `<squash>`\n"
        self.assertEqual(unclassified(added), ["brand-new-key"])

    def test_b5_a_key_is_on_one_side_only(self) -> None:
        """#345 B5: no key is both sensitive and free."""
        self.assertEqual(sorted(SENSITIVE_KEYS & FREE_KEYS), [])

    def test_b5_every_classified_key_is_in_the_template(self) -> None:
        """#345 B5: a key removed from the template leaves the lists too, so they stay the template's map."""
        keys = set(parse(TEMPLATE.read_text(encoding="utf-8")))
        self.assertEqual(sorted((SENSITIVE_KEYS | FREE_KEYS) - keys), [])

    def test_b5_the_key_that_overrides_run_limits_is_sensitive(self) -> None:
        """#345 B5 (MINOR of #361 and #362): `e2e-run-limits` replaces the bound of `run-limits` for the trial launch, so it bounds the agent as `run-limits` does."""
        self.assertIn("run-limits", SENSITIVE_KEYS)
        self.assertIn("e2e-run-limits", SENSITIVE_KEYS)
        self.assertNotIn("e2e-run-limits", FREE_KEYS)
