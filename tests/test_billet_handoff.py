"""The billet of the session handoff (#227, part 2): A5 the clock, A6 the two handoff billets.

Same seams as `test_billet`: `output_check.deviations` holds the rules of the format (the clock
included, given as `now`), `guard_output.outcome` on a `SendMessage` event holds what needs the host
(its clock, the registry of sessions, the handoff file), and the text the plugin prints for a session
(`feature-build`, `handoff_trigger.py yield`) is run through the same check.
"""

import json
import re
import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import support
from guard_output import REFUSED, outcome
from handoff_trigger import handover
from output_check import billet_fields, deviations
from test_billet import BILLET, billet, current, measure, register, send
from test_guard_output import isolated

NOW = datetime(2026, 11, 16, 13, 13, tzinfo=timezone.utc)  # 14:13 in Paris, 13:13 in UTC


def at(minutes: float, zone: int = 1) -> str:
    """An ISO 8601 time `minutes` after `NOW`, written with the offset of `zone` hours."""
    local = (NOW + timedelta(minutes=minutes)).astimezone(timezone(timedelta(hours=zone)))
    return local.isoformat(timespec="minutes")


def in_minutes(minutes: float) -> str:
    return billet(measure=measure(time=at(minutes)))


class Clock(unittest.TestCase):
    def test_a5_227_a_time_within_five_minutes_of_the_clock_passes(self) -> None:
        """#227 A5: five minutes early, five late, and the same instant in another offset."""
        for minutes, zone in ((0, 1), (5, 1), (-5, 1), (-4, 0), (4, -5)):
            with self.subTest(minutes=minutes, zone=zone):
                text = billet(measure=measure(time=at(minutes, zone)))
                self.assertEqual(deviations(text, "billet", now=NOW), [])

    def test_a5_227_a_time_more_than_five_minutes_off_is_refused_with_both_instants(self) -> None:
        """#227 A5: trial of the day, a time written without reading the clock, 15 minutes wrong."""
        for minutes in (-15, -6, 6, 15, 60):
            with self.subTest(minutes=minutes):
                found = deviations(in_minutes(minutes), "billet", now=NOW)
                self.assertEqual(len(found), 1, found)
                self.assertIn(f"`time={at(minutes)}` is {abs(minutes)} minutes", found[0])
                self.assertIn("host clock", found[0])
                self.assertIn(NOW.isoformat(timespec="minutes"), found[0])
                self.assertIn("at most 5", found[0])

    def test_a5_227_the_same_wall_time_in_the_wrong_offset_is_refused(self) -> None:
        """#227 trial 2: `13:13` written as if it were CET when the host reads UTC is an hour off."""
        found = deviations(billet(measure=measure(time="2026-11-16T13:13+01:00")), "billet", now=NOW)
        self.assertEqual(len(found), 1, found)
        self.assertIn("is 60 minutes", found[0])

    def test_a5_227_a_time_that_is_no_instant_is_named_once(self) -> None:
        """#227 A5: a malformed time is A2's deviation; the clock has nothing to compare."""
        found = deviations(billet(measure=measure(time="14h13")), "billet", now=NOW)
        self.assertEqual(len(found), 1, found)
        self.assertIn("ISO 8601 with its offset", found[0])

    def test_a5_227_without_a_clock_the_time_is_not_compared(self) -> None:
        """#227 A5: `deviations` compares only when given the clock; the hook and the command give it."""
        self.assertEqual(deviations(BILLET, "billet"), [])


class ClockHook(unittest.TestCase):
    def test_a5_227_the_hook_refuses_a_stale_time_and_lets_a_fresh_one_leave(self) -> None:
        """#227 A5: the host clock decides, in the hook that blocks."""
        stale = datetime.now(timezone.utc).astimezone() - timedelta(minutes=15)
        old = billet(measure=measure(time=stale.isoformat(timespec="seconds")))
        with isolated() as project:
            register(project.parent / "home", 4242, sessionId="e1ae680a", name="shipyard-f6", cwd="/x")
            refused = outcome(json.dumps(send("shipyard-f6", old)))
            sent = outcome(json.dumps(send("shipyard-f6", billet(measure=current()))))
        self.assertEqual(refused.code, REFUSED)
        self.assertIn("15 minutes", refused.stderr)
        self.assertIn("host clock", refused.stderr)
        self.assertEqual((sent.code, sent.stderr), (0, ""))


SESSION = "e1ae680a-d488-4e29-9f3b-0a1b2c3d4e5f"
PATH = "/home/user/.claude/hooks/state/handoffs/forge/2026-11-16-r1.md"


def with_field(text: str, line: str, type_: str) -> str:
    """`text` as a billet of type `type_` that carries the extra field `line` after `type`."""
    return text.replace("type: claim\n", f"type: {type_}\n{line}\n")


def request(**changes: str | None) -> str:
    """A `handoff-request` billet: the interactive session asks the background one to hand over."""
    return with_field(billet(awaits="reply", **changes), f"session: {SESSION}", "handoff-request")


def handoff(**changes: str | None) -> str:
    """A `handoff` billet: the background session sends the path of its handoff."""
    return with_field(billet(awaits="nothing", **changes), f"handoff: {PATH}", "handoff")


class Template(unittest.TestCase):
    def test_a6_227_the_template_names_the_two_types_their_field_and_their_check(self) -> None:
        """#227 A6: what the hook enforces is what the template tells the session."""
        text = (support.PLUGIN / "templates" / "billet.md").read_text(encoding="utf-8")
        for word in ("`handoff-request`", "`session:", "`handoff`", "`handoff:", "successor-ok", "registre"):
            with self.subTest(word=word):
                self.assertIn(word, text)

    def test_a6_227_the_template_still_declares_six_required_fields(self) -> None:
        """#227 A6: the two added fields depend on the type, so the header's `required:` stays at six."""
        header = (support.PLUGIN / "templates" / "billet.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("required: from, type, resource, ticket, measure, awaits |", header)


class Types(unittest.TestCase):
    def test_a6_227_a_handoff_request_with_a_session_conforms(self) -> None:
        """#227 A6: `type: handoff-request` and the field `session`, nothing else added."""
        self.assertEqual(deviations(request(), "billet"), [])

    def test_a6_227_a_handoff_with_a_path_conforms(self) -> None:
        """#227 A6: `type: handoff` and the field `handoff`."""
        self.assertEqual(deviations(handoff(), "billet"), [])

    def test_a6_227_the_added_field_is_required_by_its_type(self) -> None:
        """#227 A6: a request without `session`, a handoff without `handoff`, an empty value."""
        no_session = billet().replace("type: claim", "type: handoff-request")
        no_handoff = billet().replace("type: claim", "type: handoff")
        self.assertEqual(
            deviations(no_session, "billet"), ["the field `session` is missing (a billet of type `handoff-request`)"]
        )
        self.assertEqual(
            deviations(no_handoff, "billet"), ["the field `handoff` is missing (a billet of type `handoff`)"]
        )
        self.assertEqual(deviations(request().replace(SESSION, ""), "billet"), ["the field `session` is empty"])
        self.assertEqual(deviations(handoff().replace(PATH, ""), "billet"), ["the field `handoff` is empty"])

    def test_a6_227_the_added_field_belongs_to_its_type_alone(self) -> None:
        """#227 A6: `session` on a claim, `handoff` on a handoff request."""
        found = deviations(with_field(billet(), f"session: {SESSION}", "claim"), "billet")
        self.assertEqual(found, ["the field `session` belongs to a billet of type `handoff-request`, not `claim`"])
        crossed = request().replace("---\n", f"handoff: {PATH}\n---\n")
        self.assertEqual(
            deviations(crossed, "billet"),
            ["the field `handoff` belongs to a billet of type `handoff`, not `handoff-request`"],
        )

    def test_a6_227_the_message_for_an_unknown_field_names_the_two_handoff_fields(self) -> None:
        """#227 A6: the closed set of fields stays closed, and the refusal says what the types add."""
        found = deviations(billet().replace("---\n", "mood: calm\n---\n"), "billet")
        self.assertEqual(
            found,
            [
                "`mood` is not a field of the billet: from, type, resource, ticket, measure, awaits"
                " (and `session` or `handoff`, for the two handoff types)"
            ],
        )

    def test_a6_227_the_two_types_are_values_of_type(self) -> None:
        """#227 A6: the list in the refusal and the template show both."""
        found = deviations(billet(type="grab"), "billet")
        self.assertIn("claim, release, info, question, reply, handoff-request, handoff", found[0])


BACKGROUND = "9f3b7c21-5a64-4d0e-8c11-aa00bb11cc22"  # the id `claude --bg` gave the background session
INTERACTIVE = "e1ae680a-d488-4e29-9f3b-0a1b2c3d4e5f"  # the id of the user's interactive session


def registered(home: Path) -> None:
    """The two sessions of the exchange, as Claude Code's registry lists them."""
    register(home, 4242, sessionId=BACKGROUND, name="shipyard-bg", kind="bg", cwd="/x")
    register(home, 4343, sessionId=INTERACTIVE, name="shipyard-ui", kind="interactive", cwd="/x")


def write_handoff(folder: Path, successor: str | None) -> Path:
    """A handoff file with its header, naming `successor` or none (the header the relay and
    `set-successor` write; `successor-ok` reads it)."""
    path = folder / "2026-11-16-r1.md"
    path.write_text(
        "---\nprojet: demo\nfeature:\npassage_depart: 1792494562\njetons_agents: 0\nen_vol: []\n"
        f"file_revue: []\nsauvetage: []\nsuccesseur: {successor or ''}\nhooks_version: forge@test\n"
        "seuil:\ncontexte_passation: 151000\n---\nResume prompt.\n",
        encoding="utf-8",
    )
    return path


def sent(to: str, text: str) -> tuple[int, str]:
    result = outcome(json.dumps(send(to, text)))
    return result.code, result.stderr


class HandoffRequestHook(unittest.TestCase):
    def request(self, session: str) -> str:
        return with_field(billet(awaits="reply", measure=current()), f"session: {session}", "handoff-request")

    def test_a6_227_a_session_of_the_registry_may_ask_for_the_handoff(self) -> None:
        """#227 A6: the id is the one of the interactive session, in the registry; its short form too."""
        with isolated() as project:
            registered(project.parent / "home")
            for session in (INTERACTIVE, INTERACTIVE[:8]):
                with self.subTest(session=session):
                    self.assertEqual(sent("shipyard-bg", self.request(session)), (0, ""))

    def test_a6_227_an_id_outside_the_registry_does_not_leave(self) -> None:
        """#227 A6: an invented id, a name in place of an id, a prefix too short to name a session."""
        with isolated() as project:
            registered(project.parent / "home")
            for session in ("0123abcd-0000-4000-8000-000000000000", "shipyard-ui", INTERACTIVE[:6]):
                with self.subTest(session=session):
                    code, stderr = sent("shipyard-bg", self.request(session))
                    self.assertEqual(code, REFUSED)
                    self.assertIn(f"`session: {session}` is not the id of a session of the registry", stderr)


class HandoffHook(unittest.TestCase):
    def handoff(self, path: Path | str) -> str:
        return with_field(billet(awaits="nothing", measure=current()), f"handoff: {path}", "handoff")

    def test_a6_227_a_handoff_whose_header_names_the_receiver_leaves(self) -> None:
        """#227 A6: the file exists and its `successeur` names the interactive session, by its id or short id."""
        with isolated() as project:
            registered(project.parent / "home")
            for successor in (INTERACTIVE, INTERACTIVE[:8]):
                with self.subTest(successor=successor):
                    path = write_handoff(project, successor)
                    self.assertEqual(sent("shipyard-ui", self.handoff(path)), (0, ""))
                    self.assertEqual(sent(INTERACTIVE, self.handoff(path)), (0, ""))

    def test_a6_227_a_path_with_no_file_does_not_leave(self) -> None:
        """#227 A6: the session writes the handoff, then sends its path, not the other way round."""
        with isolated() as project:
            registered(project.parent / "home")
            code, stderr = sent("shipyard-ui", self.handoff(project / "never-written.md"))
        self.assertEqual(code, REFUSED)
        self.assertIn("is no file", stderr)

    def test_a6_227_a_header_that_names_another_session_does_not_leave(self) -> None:
        """#227 A6: `successor-ok` would send the receiver away; the hook stops the message instead."""
        with isolated() as project:
            registered(project.parent / "home")
            path = write_handoff(project, BACKGROUND)
            code, stderr = sent("shipyard-ui", self.handoff(path))
        self.assertEqual(code, REFUSED)
        self.assertIn(f"names `{BACKGROUND}` as its successor, not the receiver `shipyard-ui`", stderr)

    def test_a6_227_a_header_with_no_successor_does_not_leave(self) -> None:
        """#227 A6: `set-successor` has not run: the receiver would be told to confirm by hand."""
        with isolated() as project:
            registered(project.parent / "home")
            code, stderr = sent("shipyard-ui", self.handoff(write_handoff(project, None)))
        self.assertEqual(code, REFUSED)
        self.assertIn("names no successor", stderr)
        self.assertIn("set-successor", stderr)

    def test_a6_227_a_file_with_no_header_does_not_leave(self) -> None:
        """#227 A6: a file that is no handoff."""
        with isolated() as project:
            registered(project.parent / "home")
            notes = project / "notes.md"
            notes.write_text("just notes\n", encoding="utf-8")
            code, stderr = sent("shipyard-ui", self.handoff(notes))
        self.assertEqual(code, REFUSED)
        self.assertIn("has no readable header", stderr)

    def test_a6_227_a_receiver_with_no_id_in_the_registry_does_not_leave(self) -> None:
        """#227 A6: an address the registry does not resolve gives nothing to hold the header to."""
        with isolated() as project:
            registered(project.parent / "home")
            path = write_handoff(project, INTERACTIVE)
            code, stderr = sent("uds:/run/user/1000/cc-socks/9999.sock", self.handoff(path))
        self.assertEqual(code, REFUSED)
        self.assertIn("has no id in the registry", stderr)

    def test_a6_227_the_format_and_the_host_deviations_come_back_together(self) -> None:
        """#227 A6: a stale time and a missing file in one refusal."""
        old = measure(time="2026-11-16T14:13+01:00")
        with isolated() as project:
            registered(project.parent / "home")
            text = with_field(billet(awaits="nothing", measure=old), f"handoff: {project / 'no.md'}", "handoff")
            code, stderr = sent("shipyard-ui", text)
        self.assertEqual(code, REFUSED)
        self.assertIn("host clock", stderr)
        self.assertIn("is no file", stderr)


SKILL = support.PLUGIN / "skills" / "feature-build" / "SKILL.md"
BLOCK = re.compile(r"^[ \t]*```text\n(.*?)^[ \t]*```", re.DOTALL | re.MULTILINE)
PLACEHOLDER = re.compile(r"<[^<>]*>")


def billets(text: str) -> list[str]:
    """The fenced blocks of `text` that are billets (their first line is `from:`), dedented."""
    return [textwrap.dedent(block) for block in BLOCK.findall(text) if block.lstrip().startswith("from:")]


def filled(block: str) -> str:
    """A printed billet as a session sends it: each `<...>` of its fields given a value the template
    allows, the time read now. The prose of a printed billet has no placeholder."""
    values = {"from": "shipyard-bg", "session": INTERACTIVE, "handoff": PATH, "resource": "none", "ticket": "none"}
    lines = []
    for line in block.splitlines():
        key = line.split(":", 1)[0]
        if key == "measure":
            line = f"measure: {current()}"
        elif key in values and PLACEHOLDER.search(line):
            line = f"{key}: {values[key]}"
        lines.append(line)
    return "\n".join(lines) + "\n"


class Printed(unittest.TestCase):
    def test_a6_227_yield_prints_the_handoff_billet_in_place_of_the_prose(self) -> None:
        """#227 A6: step 6 of `handoff_trigger.py yield` is the `handoff` billet, with the path filled."""
        with isolated() as project:
            text = handover(INTERACTIVE, 45, project)
            home = project.parent / "home"
            found = billets(text)
            self.assertEqual(len(found), 1, text)
            sent_billet = filled(found[0])
            fields = billet_fields(sent_billet)
            self.assertEqual(deviations(sent_billet, "billet", now=datetime.now(timezone.utc)), [])
            self.assertEqual(fields["type"], "handoff")
            self.assertIn("Send the handoff path to the session " + INTERACTIVE + " by SendMessage", " ".join(text.split()))
            # The path the billet carries is the one step 4 writes: the whole exchange goes through the hook.
            path = Path(fields["handoff"])
            self.assertIn(f"at {path}", " ".join(text.split()))
            path.parent.mkdir(parents=True)
            write_handoff(path.parent, INTERACTIVE).rename(path)
            registered(home)
            self.assertEqual(sent(INTERACTIVE, sent_billet), (0, ""))

    def test_a6_227_the_skill_prints_the_two_billets_in_step_0(self) -> None:
        """#227 A6: `feature-build` step 0 shows the request and the handoff as billets, each of them
        a billet the hook lets through once its placeholders are filled."""
        text = SKILL.read_text(encoding="utf-8").split("## 1. ")[0]
        found = billets(text)
        types = sorted(billet_fields(filled(block))["type"] for block in found)
        self.assertEqual(types, ["handoff", "handoff-request"])
        for block in found:
            with self.subTest(type=billet_fields(block)["type"]):
                sent_billet = filled(block)
                self.assertEqual(deviations(sent_billet, "billet", now=datetime.now(timezone.utc)), [])

    def test_a6_227_the_pages_of_docs_describe_the_two_billets_and_the_clock(self) -> None:
        """#227 A5, A6: a change a consumer project sees is described in the page that covers it."""
        sessions = (support.REPO_ROOT / "docs" / "sessions.md").read_text(encoding="utf-8")
        installation = (support.REPO_ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
        for word in ("`handoff-request`", "`handoff`", "registre des sessions", "5 minutes", "successor-ok"):
            with self.subTest(page="sessions", word=word):
                self.assertIn(word, sessions)
        for word in ("`handoff-request`", "`handoff`", "5 minutes from it", "successor-ok"):
            with self.subTest(page="installation", word=word):
                self.assertIn(word, installation)

    def test_a6_227_the_skill_no_longer_asks_for_the_request_in_prose(self) -> None:
        """#227 A6: the sentence that asked for an identifier and a request by `SendMessage` is gone."""
        text = " ".join(SKILL.read_text(encoding="utf-8").split("## 1. ")[0].split())
        self.assertNotIn("ton identifiant et cette demande", text)
        self.assertIn("`handoff-request`", text)
        self.assertIn("`handoff`", text)


if __name__ == "__main__":
    unittest.main()
