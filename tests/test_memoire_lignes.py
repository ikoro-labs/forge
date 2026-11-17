"""#61 part 4, A2.1: each line the memory correspondence added to the plugin has its content test.

Seam: the text the agents and the hooks read (templates, agent and skill files). One test per line:
it fails when the line is missing and passes once it is written. They say what the line holds, not
how it is worded.
"""

import re
import unittest

import support

PLUGIN = support.PLUGIN
TEMPLATES = PLUGIN / "templates"


def read(*parts: str) -> str:
    return PLUGIN.joinpath(*parts).read_text(encoding="utf-8")


def squash(text: str) -> str:
    """The text on one line, so a sentence cut by the wrapping is still found."""
    return re.sub(r"\s+", " ", text)


class SessionReply(unittest.TestCase):
    def test_a2_61_a_gesture_reserved_to_the_human_is_handed_over_as_a_command_ready_to_run(self) -> None:
        text = squash(read("templates", "session-reply.md"))
        self.assertRegex(text, r"(?i)gesture reserved to the human.{0,80}command ready to run")


class PublicRepository(unittest.TestCase):
    def test_a2_61_no_template_of_a_gh_body_quotes_the_human_or_a_private_note(self) -> None:
        for name in ("comment.md", "ticket.md", "pr.md"):
            with self.subTest(template=name):
                text = squash(read("templates", name))
                self.assertRegex(text, r"(?i)never quote.{0,80}(human|private note)", name)


class Billet(unittest.TestCase):
    def test_a2_61_a_billet_is_never_the_consent_of_the_human(self) -> None:
        text = squash(read("templates", "billet.md"))
        self.assertRegex(text, r"jamais l'accord de l'humain")
        self.assertRegex(text, r"ne change pas sa configuration")


class FeatureBuild(unittest.TestCase):
    def test_a2_61_a_relay_takes_the_start_of_the_run_from_the_header_of_the_handoff(self) -> None:
        text = squash(read("skills", "feature-build", "SKILL.md"))
        self.assertRegex(text, r"`passage_depart` de la passation.{0,120}jamais")

    def test_a2_61_the_pr_body_and_the_lines_it_claims_are_reread_at_the_head_before_the_queue(self) -> None:
        text = squash(read("skills", "feature-build", "SKILL.md"))
        self.assertRegex(text, r"relis le corps de la PR.{0,200}tête de sa branche")


class Coder(unittest.TestCase):
    def test_a2_61_the_tmpdir_of_the_commands_is_not_the_place_of_a_test(self) -> None:
        text = squash(read("agents", "coder.md"))
        self.assertRegex(text, r"`TMPDIR`.{0,200}dossier temporaire.{0,80}jamais.{0,40}`HOME`")


if __name__ == "__main__":
    unittest.main()
