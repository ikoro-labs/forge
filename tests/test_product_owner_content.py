"""`forge:product-owner` reads the business source before the agents' own documents (#95)."""

import re
import unittest

import support

AGENT = support.PLUGIN / "agents" / "product-owner.md"
TEMPLATE = support.PLUGIN / "templates" / "usine.md"


def reading_ranks():
    text = AGENT.read_text(encoding="utf-8")
    section = text.split("## Lecture, avant tout verdict", 1)[1].split("\n## ", 1)[0]
    return [m.group(2) for m in re.finditer(r"^(\d+)\. (.*(?:\n   .*)*)", section, re.MULTILINE)]


class ProductOwnerOrderTest(unittest.TestCase):
    def test_order_of_ranks(self):
        ranks = reading_ranks()
        self.assertEqual(len(ranks), 5, ranks)
        self.assertIn("La question", ranks[0])
        self.assertIn("CLAUDE.md", ranks[1])
        self.assertIn("matrice", ranks[1])
        self.assertIn("product-source", ranks[2])
        self.assertIn("expert métier", ranks[2])
        self.assertIn("feature-dir", ranks[3])
        self.assertIn("ticket", ranks[3])
        self.assertIn("PR", ranks[3])
        self.assertIn("ADR", ranks[4])

    def test_ticket_is_not_above_source(self):
        ranks = reading_ranks()
        self.assertNotIn("ticket", ranks[0])
        self.assertNotIn("ticket", ranks[1])

    def test_contradiction_is_a_gap_to_report(self):
        text = AGENT.read_text(encoding="utf-8")
        self.assertIn("REFERENTIAL_UPDATE", reading_ranks()[3])
        self.assertIn("écart", reading_ranks()[3])
        self.assertIn("en Markdown", text)

    def test_template_puts_domain_expert_first(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(text, r"expert métier[^\n]*en tête|en tête[^\n]*expert métier")


if __name__ == "__main__":
    unittest.main()
