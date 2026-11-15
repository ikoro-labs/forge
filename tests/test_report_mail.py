"""The factory report mail: built from `usine.md` keys alone, sent on events, and short (forge#181)."""

import contextlib
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import support
from report_mail import main

SCRIPT = support.PLUGIN / "scripts" / "report_mail.py"
NOW = datetime(2030, 1, 2, 10, 0, tzinfo=timezone.utc)
LAST = "2030-01-02T08:00:00Z"
CONFIG = """# Usine

- `report-repo` : `acme/widgets`
- `report-attention-label` : `needs-human`
- `report-main-workflow` : `ci.yml`
- `report-host` : `pc | pc-label`
- `report-host` : `vps | vps-label`
- `report-host-probe` : `pc | echo mem 3/16G disk 40/200G`
"""
RUNNERS = {"runners": [
    {"name": "r1", "status": "online", "busy": True, "labels": [{"name": "pc-label"}]},
    {"name": "r2", "status": "online", "busy": False, "labels": [{"name": "pc-label"}]},
    {"name": "r3", "status": "offline", "busy": False, "labels": [{"name": "vps-label"}]},
    {"name": "r4", "status": "online", "busy": False, "labels": [{"name": "other"}]},
]}
OLD_PR = {"number": 1, "title": "old change", "createdAt": "2030-01-01T10:00:00Z",
          "mergedAt": "2030-01-01T10:30:00Z", "comments": []}
NEW_PR = {"number": 2, "title": "new change", "createdAt": "2030-01-02T08:10:00Z",
          "mergedAt": "2030-01-02T08:40:00Z",
          "comments": [{"body": "VERDICT: REJECT\nx"}, {"body": "VERDICT: ACCEPT\ny"}]}


class Fake:
    """Stands for `gh`: answers by the shape of the call, records every call."""

    def __init__(self, merged=(), main="success", main_sha="abc1234def", runners=RUNNERS,
                 verdicts=(), attention=(), open_prs=(), subs=None) -> None:
        self.merged, self.main, self.sha = list(merged), main, main_sha
        self.runners, self.verdicts, self.attention = runners, list(verdicts), list(attention)
        self.open_prs, self.subs = list(open_prs), subs or {}
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        line = " ".join(args)
        if line.startswith("pr list") and "--state merged" in line:
            return json.dumps(self.merged)
        if line.startswith("pr list") and "--state open" in line and "--label" not in line:
            return json.dumps(self.open_prs)
        if line.startswith(("pr list", "issue list")) and "--label" in line:
            return json.dumps(self.attention)
        if line.startswith("run list") and "--status completed" in line:
            return json.dumps([{"headSha": self.sha, "conclusion": self.main}])
        if line.startswith("run list") and "--status queued" in line:
            return json.dumps([{"databaseId": 1}])
        if line.startswith("run list"):
            return json.dumps([{"databaseId": 2}, {"databaseId": 3}])
        if "actions/runners" in line:
            if isinstance(self.runners, Exception):
                raise self.runners
            return json.dumps(self.runners)
        if "issues/comments" in line:
            return json.dumps(self.verdicts)
        if line.startswith("api repos/") and line.split()[1].endswith("/sub_issues"):
            rows = self.subs.get(int(line.split()[1].split("/")[-2]), [])
            if isinstance(rows, Exception):
                raise rows
            return "".join("\t".join(map(str, row)) + "\n" for row in rows)
        raise AssertionError(f"unexpected gh call: {line}")


@contextlib.contextmanager
def project(config: str = CONFIG) -> Iterator[tuple[Path, Path]]:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / "project"
        (root / "docs" / "agents").mkdir(parents=True)
        (root / "docs" / "agents" / "usine.md").write_text(config, encoding="utf-8")
        state = Path(folder) / "state"
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
        env.update(HOME=folder, USERPROFILE=folder)
        with mock.patch.dict("os.environ", env, clear=True):
            yield root, state


def run(root: Path, state: Path, fake: Fake, *extra: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    argv = ["--root", str(root), "--state-dir", str(state), *extra]
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, gh=fake, now=NOW)
    return code, out.getvalue(), err.getvalue()


def seed(state: Path, main: str = "success abc1234") -> None:
    state.mkdir(parents=True, exist_ok=True)
    (state / "state.json").write_text(json.dumps({
        "last_sent": LAST, "digest_date": "2030-01-02",
        "fingerprint": {"acme/widgets": {"main": main, "attention": [], "open": {}, "runners": {}}},
    }), encoding="utf-8")


class ReportMailTests(unittest.TestCase):
    def test_a1_the_script_names_no_repository_and_no_date(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for word in ("ikoro", "shipyard", "meridianre", "sunderland"):
            self.assertNotIn(word, source.lower())
        self.assertIsNone(re.search(r"\b20\d\d-\d\d-\d\d\b", source))

    def test_a1_the_repository_comes_from_the_key(self) -> None:
        with project() as (root, state):
            fake = Fake()
            code, out, _ = run(root, state, fake)
            self.assertEqual(code, 0)
            self.assertIn("acme/widgets", out)
            repos = {a[a.index("-R") + 1] for a in fake.calls if "-R" in a}
            self.assertEqual(repos, {"acme/widgets"})

    def test_a1_without_the_repository_key_the_script_stops_and_names_it(self) -> None:
        with project("- `report-host` : `pc | pc-label`\n") as (root, state):
            fake = Fake()
            code, out, err = run(root, state, fake)
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("`report-repo`", err)
            self.assertEqual(fake.calls, [])

    def test_a2_1_nothing_happened_since_the_last_send_exits_10_without_a_mail(self) -> None:
        with project() as (root, state):
            seed(state)
            code, out, _ = run(root, state, Fake(merged=[OLD_PR]))
            self.assertEqual(code, 10)
            self.assertEqual(out, "")

    def test_a2_a_merge_makes_a_mail_due_and_sent_closes_the_round(self) -> None:
        with project() as (root, state):
            seed(state)
            code, out, _ = run(root, state, Fake(merged=[OLD_PR, NEW_PR]))
            self.assertEqual(code, 0)
            self.assertIn("#2", out)
            self.assertEqual(run(root, state, Fake(merged=[OLD_PR, NEW_PR]), "--sent")[0], 0)
            self.assertEqual(run(root, state, Fake(merged=[OLD_PR, NEW_PR]))[0], 10)

    def test_a2_a_verdict_or_a_main_change_makes_a_mail_due(self) -> None:
        with project() as (root, state):
            seed(state)
            verdict = {"issue_url": "x/acme/widgets/issues/7", "created_at": "2030-01-02T09:00:00Z",
                       "body": "VERDICT: REJECT\nwhy"}
            code, out, _ = run(root, state, Fake(verdicts=[verdict]))
            self.assertEqual(code, 0)
            self.assertIn("REJECT", out)
            self.assertEqual(run(root, state, Fake(main="failure"))[0], 0)

    def test_a2_no_baseline_sends_a_first_mail_without_a_change_list(self) -> None:
        with project() as (root, state):
            code, out, _ = run(root, state, Fake(merged=[OLD_PR]))
            self.assertEqual(code, 0)
            self.assertNotIn("#1", out)

    def test_a2_the_digest_is_due_only_with_its_key_and_after_its_hour(self) -> None:
        with project() as (root, state):
            seed(state)
            path = state / "state.json"
            data = json.loads(path.read_text())
            data["digest_date"] = "2030-01-01"
            path.write_text(json.dumps(data))
            self.assertEqual(run(root, state, Fake())[0], 10)  # no key: no digest
        with project(CONFIG + "- `report-digest-hour` : `7`\n") as (root, state):
            seed(state)
            path = state / "state.json"
            data = json.loads(path.read_text())
            data["digest_date"] = "2030-01-01"
            path.write_text(json.dumps(data))
            self.assertEqual(run(root, state, Fake())[0], 0)

    def test_a5_runners_are_grouped_by_host_with_the_probe_line(self) -> None:
        with project() as (root, state):
            seed(state)
            _, out, _ = run(root, state, Fake(merged=[NEW_PR]))
            self.assertIn("CI and runners", out)
            self.assertRegex(out, r"pc.*2 online.*1 busy")
            self.assertRegex(out, r"vps.*0 online")
            self.assertIn("mem 3/16G disk 40/200G", out)
            self.assertIn("no probe named for host vps", out)
            self.assertIn("r4", out)  # a runner no host claims is listed, not dropped
            self.assertRegex(out, r"queued.*1")
            self.assertRegex(out, r"in progress.*2")
            self.assertIn("abc1234", out)

    def test_a5_a_failing_probe_does_not_fail_the_script(self) -> None:
        def broken(command: str) -> str:
            raise OSError("no route")

        with project() as (root, state):
            seed(state)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["--root", str(root), "--state-dir", str(state)],
                                        gh=Fake(merged=[NEW_PR]), probe=broken, now=NOW)
            self.assertEqual(code, 0)
            self.assertIn("probe for host pc failed", out.getvalue())

    def test_a5_unreadable_runners_do_not_fail_the_mail(self) -> None:
        refused = subprocess.CalledProcessError(1, ["gh", "api", "actions/runners"])
        with project() as (root, state):
            seed(state)
            code, out, _ = run(root, state, Fake(merged=[NEW_PR], runners=refused))
            self.assertEqual(code, 0)
            self.assertIn("runners not read", out)
            self.assertIn("#2", out)
            code, out, _ = run(root, state, Fake(runners=refused), "--line")
            self.assertEqual(code, 0)
            self.assertIn("acme/widgets: runners not read", out)

    def test_a5_without_a_host_key_the_part_says_so(self) -> None:
        with project("- `report-repo` : `acme/widgets`\n") as (root, state):
            seed(state)
            _, out, _ = run(root, state, Fake(merged=[NEW_PR]))
            self.assertIn("key `report-host` absent", out)

    def test_a7_the_mail_keeps_only_what_changed_since_the_last_send(self) -> None:
        with project() as (root, state):
            seed(state)
            _, out, _ = run(root, state, Fake(merged=[OLD_PR, NEW_PR]))
            self.assertIn("#2", out)
            self.assertNotIn("old change", out)
            self.assertLess(len(out.split()), 400)


class SessionLineTests(unittest.TestCase):
    def test_a6_the_line_option_prints_the_ci_and_runners_part_in_one_line(self) -> None:
        with project() as (root, state):
            fake = Fake()
            code, out, _ = run(root, state, fake, "--line")
            self.assertEqual(code, 0)
            self.assertEqual(len(out.strip().splitlines()), 1)
            self.assertTrue(out.startswith("CI and runners:"))
            self.assertRegex(out, r"pc 2/2 online, 1 busy")
            self.assertIn("queued 1", out)
            self.assertIn("main success abc1234", out)
            self.assertFalse(state.exists())  # no state read for the mail, none written

    def test_a6_without_the_repository_key_the_line_says_not_applicable(self) -> None:
        with project("- `report-host` : `pc | pc-label`\n") as (root, state):
            code, out, _ = run(root, state, Fake(), "--line")
            self.assertEqual(code, 0)
            self.assertIn("not applicable (key `report-repo` absent)", out)


FLOORS = CONFIG + "- `report-host-floor` : `pc | 2 | 10`\n- `report-host-floor` : `vps | 1 | 5`\n"


def slots(config: str, readings: dict[str, str], fake: Fake | None = None) -> tuple[int, str]:
    """`--slots` with a probe that prints `readings[command]`, or fails when the command is absent."""
    def probe(command: str) -> str:
        if command not in readings:
            raise OSError("no route")
        return readings[command]

    with project(config) as (root, state):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main(["--root", str(root), "--state-dir", str(state), "--slots"],
                        gh=fake or Fake(), probe=probe, now=NOW)
        return code, out.getvalue()


PC_PROBE = "echo mem 3/16G disk 40/200G"


class SlotsTests(unittest.TestCase):
    def test_a8_free_runners_of_hosts_above_their_floor_are_the_free_slots(self) -> None:
        config = FLOORS + "- `report-host-probe` : `vps | probe-vps`\n"
        code, out = slots(config, {PC_PROBE: "mem-free 4 disk-free 50", "probe-vps": "mem-free 9 disk-free 80"})
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertTrue(out.startswith("Free slots: 1 "), out)  # r2 on pc; r1 busy, r3 offline
        self.assertIn("pc 1", out)
        self.assertIn("vps 0", out)

    def test_a8_a_host_under_its_floor_has_no_slot(self) -> None:
        code, out = slots(FLOORS, {PC_PROBE: "mem-free 1.5 disk-free 50"})
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("Free slots: 0 "), out)
        self.assertIn("pc 0, under its floor", out)

    def test_a8_a_disk_under_its_floor_has_no_slot(self) -> None:
        _, out = slots(FLOORS, {PC_PROBE: "mem-free 8 disk-free 0.5"})
        self.assertTrue(out.startswith("Free slots: 0 "), out)

    def test_a8_a_floor_without_a_readable_probe_gives_no_slot(self) -> None:
        _, out = slots(FLOORS, {PC_PROBE: "mem 3/16G"})
        self.assertIn("pc 0, probe unreadable", out)
        _, out = slots(FLOORS, {})
        self.assertIn("pc 0, probe unreadable", out)

    def test_a8_unreadable_runners_leave_the_count_unknown(self) -> None:
        refused = subprocess.CalledProcessError(1, ["gh", "api", "actions/runners"])
        _, out = slots(FLOORS, {PC_PROBE: "mem-free 4 disk-free 50"}, Fake(runners=refused))
        self.assertTrue(out.startswith("Free slots: unknown "), out)
        _, out = slots(FLOORS, {PC_PROBE: "mem-free 1 disk-free 50"}, Fake(runners=refused))
        self.assertIn("pc 0, under its floor", out)

    def test_a8_without_a_floor_a_host_counts_its_free_runners(self) -> None:
        _, out = slots(CONFIG, {})
        self.assertTrue(out.startswith("Free slots: 1 "), out)

    def test_a8_without_the_repository_key_slots_are_not_applicable(self) -> None:
        code, out = slots("- `report-host` : `pc | pc-label`\n", {})
        self.assertEqual(code, 0)
        self.assertIn("not applicable", out)


FEATURES = CONFIG + "- `feature-dir` : `docs/features`\n"
IDEA = "---\nfeature: F-{n:04d}\ntitre: demo {n}\netat: actif\nissue: {issue}\n---\n"
READY = "ready-for-agent"
CLOSED = "CLOSED\tCOMPLETED"
OPENED = "OPEN\t"
# One sub-issue as the sub_issues jq prints it: number, state, reason, labels, assignees, blockers.
SUBS = {40: [(11, CLOSED, "", 0, 0), (12, OPENED, READY, 0, 0), (13, OPENED, "", 0, 0)]}


def sub(row: tuple) -> tuple:
    number, state, labels, assignees, blocked = row
    return (number, *state.split("\t"), labels, assignees, blocked)


def with_features(test: unittest.TestCase, config: str, features: dict[int, int | str]) -> tuple[Path, Path]:
    cm = project(config)
    root, state = cm.__enter__()
    test.addCleanup(cm.__exit__, None, None, None)
    for number, issue in features.items():
        folder = root / "docs" / "features" / f"{number:04d}-demo"
        folder.mkdir(parents=True)
        (folder / "idee.md").write_text(IDEA.format(n=number, issue=issue), encoding="utf-8")
    return root, state


def features_of(subs: dict, **fake: object) -> Fake:
    return Fake(subs={k: [sub(r) for r in v] if isinstance(v, list) else v for k, v in subs.items()}, **fake)


def part(mail: str, title: str) -> str:
    return re.split(rf"<h3>{title}</h3>", mail)[1].split("<h3>")[0]


PR_CITING = {"number": 77, "title": "t", "headRefOid": "abc1234def", "mergeStateStatus": "CLEAN",
             "statusCheckRollup": [], "isDraft": False, "body": "Does it.\n\nCloses #13\n"}
PR_OTHER = {**PR_CITING, "number": 78, "body": "Refs #999"}


def features_mail(
    test: unittest.TestCase, config: str, fake: Fake, features: dict | None = None, probe=None
) -> tuple[int, str, str]:
    root, state = with_features(test, config, features if features is not None else {1: 40})
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(["--root", str(root), "--state-dir", str(state)], gh=fake,
                    probe=probe or (lambda c: "mem-free 8 disk-free 50"), now=NOW)
    return code, out.getvalue(), err.getvalue()


class FeaturesTests(unittest.TestCase):
    def mail(self, config: str, fake: Fake, features: dict | None = None, probe=None) -> tuple[int, str, str]:
        return features_mail(self, config, fake, features, probe)

    def test_a7_1_an_open_feature_shows_its_percent_its_prs_and_its_ready_tickets(self) -> None:
        fake = features_of(SUBS, open_prs=[PR_CITING, PR_OTHER])
        code, mail, _ = self.mail(FEATURES, fake)
        self.assertEqual(code, 0)
        features = part(mail, "Features")
        self.assertIn("F-0001", features)
        self.assertIn("33 % (1 / 3)", features)
        self.assertIn("#77", features)
        self.assertNotIn("#78", features)
        self.assertRegex(features, r"ready[^<]*#12")
        self.assertNotRegex(features, r"ready[^<]*#13")
        subs_calls = [c for c in fake.calls if c[1].endswith("/sub_issues")]
        self.assertEqual(len(subs_calls), 1)
        self.assertIn("repos/acme/widgets/issues/40/sub_issues", subs_calls[0][1])

    def test_a7_the_percent_is_the_one_of_completion(self) -> None:
        from completion import percent

        subs = {40: [(1, CLOSED, "", 0, 0), (2, "CLOSED\tNOT_PLANNED", "", 0, 0), (3, OPENED, READY, 1, 0)]}
        _, mail, _ = self.mail(FEATURES, features_of(subs))
        self.assertIn(percent(1, 1), part(mail, "Features"))

    def test_a7_a_ready_ticket_is_open_labelled_unassigned_and_unblocked(self) -> None:
        subs = {40: [(1, OPENED, READY, 1, 0), (2, OPENED, READY, 0, 1), (3, CLOSED, READY, 0, 0),
                     (4, OPENED, "needs-info", 0, 0), (5, OPENED, f"x,{READY}", 0, 0)]}
        _, mail, _ = self.mail(FEATURES, features_of(subs))
        self.assertRegex(part(mail, "Features"), r"ready[^<]*#5")
        for number in "1234":
            self.assertNotRegex(part(mail, "Features"), rf"ready[^<]*#{number}\b")

    def test_a7_2_unreadable_sub_issues_say_tickets_not_read_and_the_mail_goes_out(self) -> None:
        fake = features_of({40: subprocess.CalledProcessError(1, "gh")})
        code, mail, _ = self.mail(FEATURES, fake)
        self.assertEqual(code, 0)
        self.assertIn("tickets not read", part(mail, "Features"))
        self.assertNotIn("%", part(mail, "Features"))
        self.assertIn("<h3>CI and runners</h3>", mail)

    def test_a7_without_a_tracking_issue_the_line_says_so(self) -> None:
        code, mail, _ = self.mail(FEATURES, features_of({}), {1: ""})
        self.assertEqual(code, 0)
        self.assertIn("tickets not read", part(mail, "Features"))
        self.assertIn("no tracking issue", part(mail, "Features"))

    def test_a7_without_the_key_or_without_an_open_feature_one_line_says_so(self) -> None:
        _, mail, _ = self.mail(CONFIG, features_of({}), {})
        self.assertRegex(part(mail, "Features"), r"(?i)no open feature|`feature-dir`")
        _, mail, _ = self.mail(FEATURES, features_of({}), {})
        self.assertRegex(part(mail, "Features"), "(?i)no open feature")

    def test_a7_a_delivered_feature_is_not_listed(self) -> None:
        root, state = with_features(self, FEATURES, {1: 40, 2: 40})
        (root / "docs" / "features" / "0002-demo" / "README.md").write_text("done", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            main(["--root", str(root), "--state-dir", str(state)], gh=features_of(SUBS), now=NOW,
                 probe=lambda c: "mem-free 8 disk-free 50")
        self.assertIn("F-0001", part(out.getvalue(), "Features"))
        self.assertNotIn("F-0002", part(out.getvalue(), "Features"))

    def test_a9_1_free_slots_propose_that_many_ready_tickets_and_ask_which_to_launch(self) -> None:
        subs = {40: [(12, OPENED, READY, 0, 0), (13, OPENED, READY, 0, 0), (14, OPENED, READY, 0, 0)]}
        runners = {"runners": [
            {"name": f"r{i}", "status": "online", "busy": False, "labels": [{"name": "pc-label"}]}
            for i in (1, 2)]}
        code, mail, _ = self.mail(FEATURES, features_of(subs, runners=runners))
        self.assertEqual(code, 0)
        waiting = part(mail, "Awaiting you")
        self.assertRegex(waiting, r"#12.*#13")
        self.assertNotIn("#14", waiting)
        self.assertRegex(waiting, r"(?i)which")
        self.assertRegex(waiting, r"(?i)starts? nothing|launch")

    def test_a9_1_no_ready_ticket_means_no_proposal(self) -> None:
        _, mail, _ = self.mail(FEATURES, features_of({40: [(13, OPENED, "", 0, 0)]}))
        self.assertNotRegex(part(mail, "Awaiting you"), r"(?i)which")

    def test_a9_2_unknown_slots_give_no_proposal_and_say_why(self) -> None:
        fake = features_of(SUBS, runners=subprocess.CalledProcessError(1, "gh"))
        _, mail, _ = self.mail(FEATURES, fake)
        self.assertIn("no proposal: free slots unknown", part(mail, "Features"))
        self.assertNotRegex(part(mail, "Awaiting you"), r"(?i)which")

    def test_a9_2_zero_slots_give_no_proposal_and_say_why(self) -> None:
        busy = {"runners": [{"name": "r1", "status": "online", "busy": True, "labels": [{"name": "pc-label"}]}]}
        _, mail, _ = self.mail(FEATURES, features_of(SUBS, runners=busy))
        self.assertIn("no proposal: free slots 0", part(mail, "Features"))
        self.assertNotRegex(part(mail, "Awaiting you"), r"(?i)which")

    def test_a9_3_the_features_part_does_not_make_the_mail_due(self) -> None:
        root, state = with_features(self, FEATURES, {1: 40})
        seed(state)
        fake = features_of(SUBS, open_prs=[], merged=[OLD_PR])
        code, out, _ = run(root, state, fake)
        self.assertEqual(code, 10)
        self.assertEqual(out, "")

    def test_a9_the_slots_line_and_the_proposal_use_the_same_count(self) -> None:
        import report_mail

        surveys = {"acme/widgets": {"runners": {"": [("r1", True, False)]}}}
        self.assertEqual(report_mail.free_slots({}, surveys, lambda c: "")[0], 1)
        self.assertIn("Free slots: 1 ", report_mail.slots_line({}, surveys, lambda c: ""))


BLOCK_SUBS = {40: [(11, CLOSED, "", 0, 0), (12, OPENED, READY, 0, 0), (13, OPENED, "", 0, 1)]}
HEADER_ROW = "| Feature | Closed / total | Open PRs | Blocked | Ready |"


class FeaturesBlockTests(unittest.TestCase):
    """F-0181 A11: `--features` prints the features table and what can start in parallel."""

    def block(self, config: str, fake: Fake, features: dict | None = None, probe=None) -> tuple[int, str, str]:
        root, state = with_features(self, config, features if features is not None else {1: 40})
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--root", str(root), "--state-dir", str(state), "--features"], gh=fake,
                        probe=probe or (lambda c: "mem-free 8 disk-free 50"), now=NOW)
        self.assertFalse(state.exists())  # no state read for the mail, none written
        return code, out.getvalue(), err.getvalue()

    def test_a11_the_option_prints_the_table_of_each_open_feature(self) -> None:
        fake = features_of(BLOCK_SUBS, open_prs=[PR_CITING, PR_OTHER])
        code, out, _ = self.block(FEATURES, fake)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0], "Features:")
        self.assertIn(HEADER_ROW, lines)
        self.assertIn("| F-0001 demo 1 | 33 % (1 / 3) | #77 | #13 | #12 |", lines)

    def test_a11_the_table_is_followed_by_the_line_of_what_runs_in_parallel(self) -> None:
        subs = {40: [(12, OPENED, READY, 0, 0), (13, OPENED, READY, 0, 0), (14, OPENED, READY, 0, 0)],
                41: [(21, OPENED, READY, 0, 0)], 42: [(31, OPENED, "", 0, 0)]}
        runners = {"runners": [
            {"name": f"r{i}", "status": "online", "busy": False, "labels": [{"name": "pc-label"}]}
            for i in (1, 2)]}
        _, out, _ = self.block(FEATURES, features_of(subs, runners=runners), {1: 40, 2: 41, 3: 42})
        last = out.strip().splitlines()[-1]
        self.assertTrue(last.startswith("In parallel:"), last)
        self.assertIn("free slots 2", last)
        self.assertRegex(last, r"tickets #12 \(F-0001\), #13 \(F-0001\)")
        self.assertNotIn("#14", last)
        self.assertRegex(last, r"features F-0001, F-0002\.$")  # F-0003 has no ready ticket

    def test_a11_the_features_launched_are_at_most_the_free_slots(self) -> None:
        subs = {40: [(12, OPENED, READY, 0, 0)], 41: [(21, OPENED, READY, 0, 0)]}
        runners = {"runners": [{"name": "r1", "status": "online", "busy": False, "labels": [{"name": "pc-label"}]}]}
        _, out, _ = self.block(FEATURES, features_of(subs, runners=runners), {1: 40, 2: 41})
        last = out.strip().splitlines()[-1]
        self.assertRegex(last, r"features F-0001\.$")

    def test_a11_blocked_counts_open_tickets_with_an_open_blocker_only(self) -> None:
        subs = {40: [(1, OPENED, READY, 0, 2), (2, CLOSED, "", 0, 1), (3, OPENED, "", 0, 0), (4, OPENED, "", 0, 1)]}
        _, out, _ = self.block(FEATURES, features_of(subs))
        row = next(line for line in out.splitlines() if line.startswith("| F-0001"))
        self.assertEqual([cell.strip() for cell in row.strip("|").split("|")][3], "#1, #4")

    def test_a11_a_feature_without_blocked_or_pr_says_none(self) -> None:
        _, out, _ = self.block(FEATURES, features_of({40: [(1, OPENED, "", 0, 0)]}))
        row = next(line for line in out.splitlines() if line.startswith("| F-0001"))
        self.assertEqual([c.strip() for c in row.strip("|").split("|")][2:], ["none", "none", "none"])

    def test_a11_unreadable_tickets_say_tickets_not_read_never_a_figure(self) -> None:
        fake = features_of({40: subprocess.CalledProcessError(1, "gh")})
        code, out, _ = self.block(FEATURES, fake)
        self.assertEqual(code, 0)
        row = next(line for line in out.splitlines() if line.startswith("| F-0001"))
        self.assertIn("tickets not read", row)
        self.assertNotIn("%", row)

    def test_a11_zero_or_unknown_slots_give_no_proposal_and_say_why(self) -> None:
        busy = {"runners": [{"name": "r1", "status": "online", "busy": True, "labels": [{"name": "pc-label"}]}]}
        _, out, _ = self.block(FEATURES, features_of(SUBS, runners=busy))
        self.assertEqual(out.strip().splitlines()[-1], "In parallel: no proposal, free slots 0.")
        unread = features_of(SUBS, runners=subprocess.CalledProcessError(1, "gh"))
        _, out, _ = self.block(FEATURES, unread)
        self.assertEqual(out.strip().splitlines()[-1], "In parallel: no proposal, free slots unknown.")

    def test_a11_free_slots_without_a_ready_ticket_say_so(self) -> None:
        _, out, _ = self.block(FEATURES, features_of({40: [(13, OPENED, "", 0, 0)]}))
        self.assertEqual(out.strip().splitlines()[-1], "In parallel: no proposal, no ready ticket.")

    def test_a11_the_state_and_the_mail_come_from_one_calculation(self) -> None:
        # The ready tickets of the table are the ones the mail proposes.
        subs = {40: [(12, OPENED, READY, 0, 0), (13, OPENED, READY, 0, 0)]}
        runners = {"runners": [{"name": "r1", "status": "online", "busy": False, "labels": [{"name": "pc-label"}]}]}
        _, out, _ = self.block(FEATURES, features_of(subs, runners=runners))
        _, mail, _ = features_mail(self, FEATURES, features_of(subs, runners=runners))
        self.assertIn("#12", out.strip().splitlines()[-1])
        self.assertRegex(part(mail, "Awaiting you"), r"#12")

    def test_a11_without_a_key_or_an_open_feature_one_line_says_so(self) -> None:
        # The key falls back to the plugin template's value: only a template without it leaves none.
        with mock.patch("guard_ticket_budget.TEMPLATE", Path("missing") / "usine.md"):
            _, out, _ = self.block(CONFIG, features_of({}), {})
        self.assertEqual(out, "Features: not applicable (key `feature-dir` absent).\n")
        _, out, _ = self.block(FEATURES, features_of({}), {})
        self.assertEqual(out, "Features: no open feature.\n")
        with project("- `feature-dir` : `docs/features`\n") as (root, state):
            code, out, _ = run(root, state, Fake(), "--features")
        self.assertEqual((code, out), (0, "Features: not applicable (key `report-repo` absent).\n"))

    def test_a11_a_gh_failure_exits_1_as_the_line_does(self) -> None:
        class Failing(Fake):
            def __call__(self, args: list[str]) -> str:
                raise subprocess.CalledProcessError(1, "gh")

        for option in ("--line", "--features"):
            with self.subTest(option=option), project(FEATURES) as (root, state):
                code, out, err = run(root, state, Failing(), option)
                self.assertEqual((code, out), (1, ""))
                self.assertIn("gh failed", err)

    def test_a11_the_reply_template_names_the_command_that_prints_the_field(self) -> None:
        text = (support.PLUGIN / "templates" / "session-reply.md").read_text(encoding="utf-8")
        self.assertIn("scripts/report_mail.py --features", text)

    def test_a11_the_mail_html_is_unchanged_by_the_new_data(self) -> None:
        subs = {40: [(12, OPENED, READY, 0, 0), (13, OPENED, "", 0, 1)]}
        _, mail, _ = features_mail(self, FEATURES, features_of(subs))
        self.assertNotIn("Blocked", mail)
        self.assertNotIn("In parallel", mail)


class FeatureBuildTests(unittest.TestCase):
    def test_a10_feature_build_reads_the_slots_before_each_coder(self) -> None:
        text = (support.PLUGIN / "skills" / "feature-build" / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"report_mail\.py\"? --slots")
        self.assertIn("Free slots: 0", text)


class TemplateTests(unittest.TestCase):
    def test_a1_the_usine_template_documents_every_key_the_script_reads(self) -> None:
        from usine import parse

        documented = set(parse((support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8")))
        read = set(re.findall(r'(?:get\(|_pairs\(config, )"(report-[a-z-]+)"', SCRIPT.read_text(encoding="utf-8")))
        self.assertGreaterEqual(len(read), 6)
        self.assertEqual(sorted(read - documented), [])
