"""The billet (#227): the closed envelope two sessions of a host exchange by `SendMessage`.

Two seams. `output_check.deviations(text, "billet", config)` holds every rule of the format, one test
per deviation it names. `guard_output.outcome` on a `PreToolUse` event for `SendMessage` holds what
the hook adds: it judges a message to another session only, and a refused message does not leave.
"""

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import support
from guard_output import REFUSED, outcome
from output_check import deviations, required_fields
from test_guard_output import guard_output_hooks, isolated

TEMPLATE = support.PLUGIN / "templates" / "billet.md"
BILLET = (
    "from: forge-build\n"
    "type: claim\n"
    "resource: worktree-pool\n"
    "ticket: #227\n"
    "measure: load=1.25 memory=5200MB time=2026-11-16T14:13+01:00\n"
    "awaits: reply\n"
    "---\n"
    "I take the pool for the next hour. Tell me if you need it sooner.\n"
)


def billet(**changes: str | None) -> str:
    """`BILLET` with the value of a field replaced, or the field dropped when the value is None."""
    lines = []
    for line in BILLET.splitlines():
        key = line.split(":", 1)[0]
        if key in changes:
            if changes[key] is None:
                continue
            line = f"{key}: {changes[key]}"
        lines.append(line)
    return "\n".join(lines) + "\n"


class Template(unittest.TestCase):
    def test_a1_227_the_template_declares_the_six_fields(self) -> None:
        """#227 A1: `from`, `type`, `resource`, `ticket`, `measure` and `awaits`."""
        fields = [labels[0] for labels in required_fields(TEMPLATE.read_text(encoding="utf-8"))]
        self.assertEqual(fields, ["from", "type", "resource", "ticket", "measure", "awaits"])

    def test_a1_227_the_template_names_the_values_of_type_and_awaits(self) -> None:
        """#227 A1: the lists the guard enforces are the ones the template shows."""
        text = TEMPLATE.read_text(encoding="utf-8")
        for value in ("claim", "release", "info", "question", "reply", "nothing"):
            with self.subTest(value=value):
                self.assertIn(f"`{value}`", text)


class Prose(unittest.TestCase):
    def test_a1_227_a_billet_in_the_template_form_conforms(self) -> None:
        """#227 A1: the six fields, `---`, then a short prose."""
        self.assertEqual(deviations(BILLET, "billet"), [])

    def test_a1_227_sixty_words_of_prose_pass_and_sixty_one_are_refused(self) -> None:
        """#227 A1: 60 words of prose at most, counted after `---`."""
        sixty = " ".join(["word"] * 60)
        self.assertEqual(deviations(BILLET.split("---")[0] + f"---\n{sixty}\n", "billet"), [])
        found = deviations(BILLET.split("---")[0] + f"---\n{sixty} word\n", "billet")
        self.assertEqual(len(found), 1)
        self.assertIn("61 words of prose", found[0])
        self.assertIn("at most 60", found[0])


def measure(**parts: str) -> str:
    """A `measure` value: the three parts of the template, one replaced at a time."""
    values = {"load": "1.25", "memory": "5200MB", "time": "2026-11-16T14:13+01:00", **parts}
    return " ".join(f"{key}={value}" for key, value in values.items())


def current() -> str:
    """A `measure` whose time is the host clock's, as the hook (A5) reads it."""
    return measure(time=datetime.now(timezone.utc).astimezone().isoformat(timespec="minutes"))


class Lines(unittest.TestCase):
    def test_a1_227_the_line_cap_of_the_template_header_holds(self) -> None:
        """#227 A1: `max-lines` of `billet.md` (24, room for a handoff billet's seventh field)
        counts the written lines, blank ones excluded."""
        short_lines = "\n".join(["three words here"] * 18)
        found = deviations(BILLET.split("---")[0] + f"---\n{short_lines}\n", "billet")
        self.assertEqual(len(found), 1, found)
        self.assertIn("25 lines, at most 24", found[0])
        seventeen = "\n".join(["three words here"] * 17)
        self.assertEqual(deviations(BILLET.split("---")[0] + f"---\n\n{seventeen}\n", "billet"), [])


class Measure(unittest.TestCase):
    def test_a2_227_time_in_iso_8601_with_its_offset_passes(self) -> None:
        """#227 A2: an offset, a `Z`, with or without seconds."""
        for value in ("2026-11-16T14:13+01:00", "2026-11-16T13:13:07Z", "2026-11-16T08:13-05:00"):
            with self.subTest(time=value):
                self.assertEqual(deviations(billet(measure=measure(time=value)), "billet"), [])

    def test_a2_227_time_without_its_offset_is_refused(self) -> None:
        """#227 A2: the second trial wrote `13:12` in UTC while the other session wrote CET."""
        for value in ("13:12", "2026-11-16T14:13", "2026-11-16 14:13+01:00", "14h13", "2026-11-16T14:13+0100"):
            with self.subTest(time=value):
                found = deviations(billet(measure=measure(time=value)), "billet")
                self.assertEqual(len(found), 1, found)
                self.assertIn(f"`time={value}`", found[0])
                self.assertIn("ISO 8601 with its offset", found[0])

    def test_a2_227_an_impossible_date_is_refused(self) -> None:
        """#227 A2: a well-shaped time that is no instant (month 13)."""
        found = deviations(billet(measure=measure(time="2026-13-16T14:13+01:00")), "billet")
        self.assertEqual(len(found), 1, found)
        self.assertIn("ISO 8601 with its offset", found[0])

    def test_a2_227_a_measure_in_prose_names_what_it_lacks(self) -> None:
        """#227 trial 1: `mesure` written in prose, with a decimal comma, instead of the three parts."""
        found = deviations(billet(measure="load is 1,25, memory fine, since 14h"), "billet")
        self.assertTrue(any("`measure` must be `load=" in line for line in found), found)


class Format(unittest.TestCase):
    def test_a3_227_each_missing_field_is_named(self) -> None:
        """#227 A3: a field short of the six."""
        for name in ("from", "type", "resource", "ticket", "measure", "awaits"):
            with self.subTest(field=name):
                found = deviations(billet(**{name: None}), "billet")
                self.assertEqual(found, [f"the field `{name}` is missing (template `billet`)"])

    def test_a3_227_an_empty_field_is_named(self) -> None:
        """#227 A3: `ticket:` with nothing after it."""
        self.assertEqual(deviations(billet(ticket=""), "billet"), ["the field `ticket` is empty"])

    def test_a3_227_a_billet_without_the_separator_is_refused(self) -> None:
        """#227 A3: no `---` line between the fields and the prose."""
        found = deviations(BILLET.replace("---\n", ""), "billet")
        self.assertEqual(len(found), 1, found)
        self.assertIn("no `---` line", found[0])

    def test_a3_227_a_value_outside_its_list_is_named_with_the_list(self) -> None:
        """#227 A3: trial 1 wrote `attend: aucune` where the list says `nothing`."""
        found = deviations(billet(awaits="none", type="grab"), "billet")
        self.assertEqual(len(found), 2, found)
        self.assertIn("`type: grab` is not one of claim, release, info, question, reply", found[0])
        self.assertIn("`awaits: none` is not one of nothing, reply", found[1])

    def test_a3_227_every_deviation_is_named_at_once(self) -> None:
        """#227 A3: a missing field, a bad value and a long prose come back together."""
        text = billet(type="grab", resource=None) + " ".join(["word"] * 61) + "\n"
        found = deviations(text, "billet")
        self.assertEqual(len(found), 3, found)

    def test_a3_227_a_field_the_template_does_not_declare_is_refused(self) -> None:
        """#227 A3: the set of fields is closed, so no session invents a variant."""
        found = deviations(billet().replace("---\n", "mood: calm\n---\n"), "billet")
        self.assertEqual(len(found), 1, found)
        self.assertTrue(
            found[0].startswith("`mood` is not a field of the billet: from, type, resource, ticket, measure, awaits"),
            found,
        )

    def test_a3_227_a_field_given_twice_is_refused(self) -> None:
        """#227 A3: the second `type` would be ignored in silence."""
        found = deviations(billet().replace("---\n", "type: info\n---\n"), "billet")
        self.assertEqual(found, ["the field `type` appears twice"])

    def test_a3_227_a_line_that_is_no_field_before_the_separator_is_named(self) -> None:
        """#227 A3: prose written where the fields go."""
        found = deviations(billet().replace("---\n", "Hello there\n---\n"), "billet")
        self.assertEqual(found, ["`Hello there` is not a `key: value` line"])


def send(to: object, message: object) -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "SendMessage",
        "tool_input": {"to": to, "message": message, "summary": "a message"},
    }


def register(home: Path, pid: int, **fields: object) -> None:
    """A session as Claude Code's registry lists it (`~/.claude/sessions/<pid>.json`)."""
    folder = home / ".claude" / "sessions"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{pid}.json").write_text(json.dumps({"pid": pid, **fields}), encoding="utf-8")


PROSE = "Hey, are you still using the worktree pool? I would like it for an hour."


class Hook(unittest.TestCase):
    def test_a3_227_a_message_to_a_session_that_is_no_billet_does_not_leave(self) -> None:
        """#227 A3: exit REFUSED (the 2 that blocks), and every deviation on stderr."""
        with isolated() as project:
            register(project.parent / "home", 4242, sessionId="e1ae680a-d488", name="shipyard-f6", cwd="/x")
            result = outcome(json.dumps(send("shipyard-f6", PROSE)))
        self.assertEqual(result.code, REFUSED)
        self.assertIn("`templates/billet.md`", result.stderr)
        for name in ("from", "type", "resource", "ticket", "measure", "awaits"):
            self.assertIn(f"the field `{name}` is missing", result.stderr)
        self.assertIn("no `---` line", result.stderr)

    def test_a3_227_a_conforming_billet_to_a_session_leaves(self) -> None:
        """#227 A3: the same recipient, the prose is refused and the billet in the template form leaves."""
        with isolated() as project:
            register(project.parent / "home", 4242, sessionId="e1ae680a-d488", name="shipyard-f6", cwd="/x")
            refused = outcome(json.dumps(send("shipyard-f6", PROSE)))
            sent = outcome(json.dumps(send("shipyard-f6", billet(measure=current()))))
        self.assertEqual(refused.code, REFUSED)
        self.assertEqual((sent.code, sent.stderr, sent.stdout), (0, "", ""))

    def test_a3_227_a_session_is_found_by_its_id_or_by_an_address(self) -> None:
        """#227 A3: the registry's `sessionId`, a `uds:` socket and a `bridge:` id are sessions too."""
        with isolated() as project:
            register(project.parent / "home", 4242, sessionId="e1ae680a-d488-4e29", name="shipyard-f6", cwd="/x")
            for target in ("e1ae680a-d488-4e29", "uds:/run/user/1000/cc-socks/4242.sock", "bridge:session_01abc"):
                with self.subTest(to=target):
                    self.assertEqual(outcome(json.dumps(send(target, PROSE))).code, REFUSED)

    def test_a3_227_a_refused_message_is_refused_every_time(self) -> None:
        """#227 A3: unlike a subagent's output, a message is not let through at the second try."""
        with isolated() as project:
            register(project.parent / "home", 4242, sessionId="e1ae680a", name="shipyard-f6", cwd="/x")
            codes = [outcome(json.dumps(send("shipyard-f6", PROSE))).code for _ in range(3)]
        self.assertEqual(codes, [REFUSED] * 3)

    def test_a3_227_a_message_to_an_agent_of_the_session_is_free_prose(self) -> None:
        """#227 A3: `researcher` and `main` are agents of this session: the prose a session would
        be refused for goes through to them."""
        with isolated() as project:
            register(project.parent / "home", 4242, sessionId="e1ae680a", name="shipyard-f6", cwd="/x")
            self.assertEqual(outcome(json.dumps(send("shipyard-f6", PROSE))).code, REFUSED)
            for target in ("researcher", "main", "a1b2c3d4e5f6"):
                with self.subTest(to=target):
                    self.assertEqual(outcome(json.dumps(send(target, PROSE))).code, 0)

    def test_a3_227_a_structured_message_is_not_judged(self) -> None:
        """#227 A3: a protocol object (a shutdown answer) is no prose to hold to the billet, though
        the same recipient is refused a prose message."""
        with isolated() as project:
            register(project.parent / "home", 4242, sessionId="e1ae680a", name="shipyard-f6", cwd="/x")
            answer = {"type": "shutdown_response", "request_id": "r1", "approve": True}
            self.assertEqual(outcome(json.dumps(send("shipyard-f6", PROSE))).code, REFUSED)
            self.assertEqual(outcome(json.dumps(send("shipyard-f6", answer))).code, 0)


POOL = {"shared-resource": ["worktree-pool", "ci-runner"]}


class Resource(unittest.TestCase):
    def test_a4_227_a_value_of_the_key_passes(self) -> None:
        """#227 A4: each `shared-resource` line of `usine.md` is a value of `resource`."""
        for value in ("worktree-pool", "ci-runner"):
            with self.subTest(resource=value):
                self.assertEqual(deviations(billet(resource=value), "billet", POOL), [])

    def test_a4_227_a_value_outside_the_key_is_named_with_the_values(self) -> None:
        """#227 A4: `resource` cannot name a thing the project did not declare."""
        found = deviations(billet(resource="the-database"), "billet", POOL)
        self.assertEqual(
            found,
            ["`resource: the-database` is not a value of the key `shared-resource`: worktree-pool, ci-runner, none"],
        )

    def test_a4_227_none_is_always_a_value(self) -> None:
        """#227 A4: a question or an info that concerns no resource says `none`."""
        self.assertEqual(deviations(billet(resource="none"), "billet", POOL), [])

    def test_a4_227_without_the_key_the_check_is_not_applicable(self) -> None:
        """#227 A4: no key, no list: any non-empty value passes (`sans objet`), the field stays required."""
        self.assertEqual(deviations(billet(resource="anything-at-all"), "billet", {}), [])
        self.assertEqual(
            deviations(billet(resource=None), "billet", {}), ["the field `resource` is missing (template `billet`)"]
        )

    def test_a4_227_the_hook_reads_the_key_in_the_project_usine(self) -> None:
        """#227 A4: the guard loads `docs/agents/usine.md` of the project that sends."""
        with isolated() as project:
            register(project.parent / "home", 4242, sessionId="e1ae680a", name="shipyard-f6", cwd="/x")
            page = project / "docs" / "agents" / "usine.md"
            page.parent.mkdir(parents=True)
            page.write_text("- `shared-resource` : `worktree-pool`\n", encoding="utf-8")
            refused = outcome(json.dumps(send("shipyard-f6", billet(resource="the-database", measure=current()))))
            allowed = outcome(json.dumps(send("shipyard-f6", billet(resource="worktree-pool", measure=current()))))
        self.assertEqual(refused.code, REFUSED)
        self.assertIn("`resource: the-database` is not a value of the key `shared-resource`", refused.stderr)
        self.assertEqual((allowed.code, allowed.stderr), (0, ""))

    def test_a4_227_the_template_documents_the_key(self) -> None:
        """#227 A4: the key is documented in the `usine.md` template, as any new key must be."""
        text = (support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8")
        self.assertIn("`shared-resource`", text)
        self.assertIn("sans objet", text[text.index("`shared-resource`") :][:1500])


class HooksJson(unittest.TestCase):
    def test_a3_227_send_message_reaches_the_guard_that_blocks_on_exit_3(self) -> None:
        """#227 A3: the `PreToolUse` entry of `guard_output` names `SendMessage`, in the command that
        turns the refusal code 3 alone into the 2 that blocks (`test_only_the_refusal_code_blocks`)."""
        pre = next(hook for hook in guard_output_hooks()["PreToolUse"] if "SendMessage" in str(hook["matcher"]))
        self.assertIn("SendMessage", str(pre["matcher"]).split("|"))
        self.assertIn("[ $? -eq 3 ] && exit 2", str(pre["command"]))


if __name__ == "__main__":
    unittest.main()
