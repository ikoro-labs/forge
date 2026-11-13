"""The templates of `plugins/forge/templates/`: each one holds its own `max-lines` cap, the verdict
example is read by `parse_output.parse_verdict`, and the prose of a template caps instead of padding."""

import re
import unittest

import support
from parse_output import parse_verdict

TEMPLATES = support.PLUGIN / "templates"
HEADER = re.compile(r"^<!-- template: (\w[\w-]*) \| max-lines: (\d+)")
QC_CONF = support.PLUGIN / "agents" / "qc-conf.md"


def capped() -> list[tuple[str, int, list[str]]]:
    """Each template whose first line declares a cap: name, cap, the lines after the header."""
    found = []
    for path in sorted(TEMPLATES.glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        match = HEADER.match(lines[0]) if lines else None
        if match:
            found.append((match.group(1), int(match.group(2)), lines[1:]))
    return found


def verdict_example(text: str) -> str:
    """The fenced example of a verdict template, with each placeholder given a value it allows."""
    block = text.split("```text\n", 1)[1].split("\n```", 1)[0]
    values = {
        "VERDICT": "REJECT",
        "ROUND": "3",
        "HEAD": "3f2a9c1",
        "SOCLE": "260522a7767bc437acc56c0bf5604582f13e6b33",
        "GRANTED": "https://github.com/o/r/pull/9#issuecomment-1",
    }
    lines = []
    for line in block.splitlines():
        key = line.split(":", 1)[0]
        if key in values:
            line = f"{key}: {values[key]}"
        lines.append(re.sub(r"<[^<>]*(<[^<>]*>[^<>]*)*>", "1", line))
    return "\n".join(lines) + "\n"


class Caps(unittest.TestCase):
    def test_every_capped_template_holds_its_own_cap(self) -> None:
        templates = capped()
        self.assertGreaterEqual(len(templates), 4)
        for name, cap, lines in templates:
            with self.subTest(template=name):
                self.assertLessEqual(len(lines), cap)

    def test_no_template_asks_for_a_minimum_length(self) -> None:
        for path in sorted(TEMPLATES.glob("*.md")):
            with self.subTest(template=path.name):
                self.assertNotRegex(path.read_text(encoding="utf-8"), r"(?i)(at least \w+ lines|\w+ lines at least)")

    def test_pr_and_adr_cap_their_explanation(self) -> None:
        for name in ("pr.md", "adr.md"):
            with self.subTest(template=name):
                self.assertRegex((TEMPLATES / name).read_text(encoding="utf-8"), r"in \w+ lines at most")


class VerdictExample(unittest.TestCase):
    def test_the_verdict_template_example_is_read_by_the_parser(self) -> None:
        parsed = parse_verdict(verdict_example((TEMPLATES / "verdict.md").read_text(encoding="utf-8")))
        self.assertEqual(parsed["HEAD"], "3f2a9c1")
        self.assertEqual(parsed["SOCLE"], "260522a7767bc437acc56c0bf5604582f13e6b33")

    def test_the_qc_conf_output_example_is_read_by_the_parser(self) -> None:
        text = QC_CONF.read_text(encoding="utf-8").split("## Sortie", 1)[1]
        parsed = parse_verdict(verdict_example(text))
        self.assertEqual(parsed["SOCLE"], "260522a7767bc437acc56c0bf5604582f13e6b33")

    def test_the_three_files_allow_three_rounds_and_a_grant(self) -> None:
        for path in (TEMPLATES / "verdict.md", QC_CONF):
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("ROUND: 1 | 2 | 3", text)
                self.assertIn("GRANTED:", text)


class Ticket(unittest.TestCase):
    def test_the_ticket_template_has_an_optional_feature_line(self) -> None:
        text = (TEMPLATES / "ticket.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^Feature: F-NNNN")
        self.assertIn("fusion-bloquee", text)


class QcConfLanguage(unittest.TestCase):
    def test_the_posted_verdict_is_in_english(self) -> None:
        text = QC_CONF.read_text(encoding="utf-8")
        self.assertNotIn("son texte libre est en français", text)
        self.assertIn("free text in English", text)


class QcRounds(unittest.TestCase):
    """`/forge:qc` holds three rounds at most (shipyard#193): the third REJECT leaves the PR open
    with `needs-your-attention`, and no round 4 runs without `GRANTED`."""

    SKILLS = support.PLUGIN / "skills"

    def test_the_qc_skill_holds_three_rounds(self) -> None:
        text = (self.SKILLS / "qc" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("three rounds at most", text)
        self.assertRegex(text, r"REJECT in round 3[^\n]*`needs-your-attention`")
        self.assertIn("GRANTED", text)
        self.assertNotIn("il n'y a pas de tour 3", text)
        self.assertNotIn("Une seule reprise par ticket", text)
        self.assertNotIn("ferme la PR avec l'étiquette `agent-rework`", text)

    def test_no_file_of_the_plugin_keeps_two_qc_rounds(self) -> None:
        pattern = re.compile(r"deux tours|2 tours|two rounds|une seule reprise|ROUND: 2|second REJECT")
        for path in sorted(support.PLUGIN.rglob("*.md")):
            if path.relative_to(support.PLUGIN).parts[:2] == ("skills", "feature-review"):
                continue  # its two rounds are the end-to-end review's re-reading, not `/forge:qc`
            with self.subTest(file=str(path.relative_to(support.PLUGIN))):
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")))



class SocleNamesTheCappedTemplates(unittest.TestCase):
    """`socle.md` names as capped exactly the templates whose head declares a cap."""

    def test_the_capped_list_matches_the_headers(self) -> None:
        socle = (support.PLUGIN / "socle.md").read_text(encoding="utf-8")
        sentence = socle.split("## Templates", 1)[1].split("\n\n", 2)[1]
        claim = next(part for part in re.split(r"\.\s", sentence) if "line cap" in part)
        named = {name.removesuffix(".md") for name in re.findall(r"`([\w./-]+)`", claim) if name != "templates/"}
        self.assertEqual(named, {name for name, _, _ in capped()})


if __name__ == "__main__":
    unittest.main()
