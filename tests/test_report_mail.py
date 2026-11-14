"""The factory report mail: built from `usine.md` keys alone, sent on events, and short (forge#181)."""

import contextlib
import io
import json
import os
import re
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
"""
OLD_PR = {"number": 1, "title": "old change", "createdAt": "2030-01-01T10:00:00Z",
          "mergedAt": "2030-01-01T10:30:00Z", "comments": []}
NEW_PR = {"number": 2, "title": "new change", "createdAt": "2030-01-02T08:10:00Z",
          "mergedAt": "2030-01-02T08:40:00Z",
          "comments": [{"body": "VERDICT: REJECT\nx"}, {"body": "VERDICT: ACCEPT\ny"}]}


class Fake:
    """Stands for `gh`: answers by the shape of the call, records every call."""

    def __init__(self, merged=(), main="success", main_sha="abc1234def",
                 verdicts=(), attention=()) -> None:
        self.merged, self.main, self.sha = list(merged), main, main_sha
        self.verdicts, self.attention = list(verdicts), list(attention)
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> str:
        self.calls.append(args)
        line = " ".join(args)
        if line.startswith("pr list") and "--state merged" in line:
            return json.dumps(self.merged)
        if line.startswith("pr list") and "--state open" in line and "--label" not in line:
            return json.dumps([])
        if line.startswith(("pr list", "issue list")) and "--label" in line:
            return json.dumps(self.attention)
        if line.startswith("run list") and "--status completed" in line:
            return json.dumps([{"headSha": self.sha, "conclusion": self.main}])
        if "issues/comments" in line:
            return json.dumps(self.verdicts)
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
        "fingerprint": {"acme/widgets": {"main": main, "attention": [], "open": {}}},
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

    def test_a7_the_mail_keeps_only_what_changed_since_the_last_send(self) -> None:
        with project() as (root, state):
            seed(state)
            _, out, _ = run(root, state, Fake(merged=[OLD_PR, NEW_PR]))
            self.assertIn("#2", out)
            self.assertNotIn("old change", out)
            self.assertLess(len(out.split()), 400)


class TemplateTests(unittest.TestCase):
    def test_a1_the_usine_template_documents_every_key_the_script_reads(self) -> None:
        from usine import parse

        documented = set(parse((support.PLUGIN / "templates" / "usine.md").read_text(encoding="utf-8")))
        read = set(re.findall(r'(?:get\(|_pairs\(config, )"(report-[a-z-]+)"', SCRIPT.read_text(encoding="utf-8")))
        self.assertGreaterEqual(len(read), 4)
        self.assertEqual(sorted(read - documented), [])
