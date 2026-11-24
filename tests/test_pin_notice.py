"""The `SessionStart` hook pin_notice.py: with the key `pin-bump`, a consumer session is told that a
newer plugin tag exists than the pinned `ref` (ikoro-labs/forge#278).

The network and `gh` are always faked: a runner stands in for them, or the PATH is empty. Every
test runs in a throwaway project under an isolated HOME and USERPROFILE, without the CLAUDE_
variables of the session running the tests, and writes nothing in the real ~/.claude.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from pin_notice import SETTINGS, notice

HOOK = support.PLUGIN / "hooks" / "pin_notice.py"
TAG_LINES = "\n".join(
    f"refs/tags/{name}"
    for name in ("forge--v1.16.0", "forge--v1.17.0", "forge--v1.18.0", "forge--v1.19.0-rc1", "forge--v1.9.0")
)
SETTINGS_FILES = f"README.md\n{SETTINGS}\n"


def settings(ref: str = "forge--v1.16.0", plugin: str = "forge@ikoro-labs") -> str:
    return json.dumps({
        "enabledPlugins": {plugin: True},
        "extraKnownMarketplaces": {"ikoro-labs": {"source": {"source": "github", "repo": "ikoro-labs/forge", "ref": ref}}},
    })


class Remote:
    """A stand-in for `gh`: the tags of the marketplace repository and the files of the open PRs."""

    def __init__(self, tags: str | None = TAG_LINES, open_prs_files: str | None = "") -> None:
        self.tags = tags
        self.open_prs_files = open_prs_files
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], cwd: Path) -> str | None:
        self.calls.append(argv)
        if "api" in argv:
            return self.tags
        if "pr" in argv:
            return self.open_prs_files
        raise AssertionError(f"unexpected command {argv}")


class PinNotice(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.project = Path(os.path.realpath(self.dir.name))
        (self.project / ".claude").mkdir()
        (self.project / "docs" / "agents").mkdir(parents=True)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.project), "USERPROFILE": str(self.project)})
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in [key for key in os.environ if key.startswith("CLAUDE_")]:
            del os.environ[name]

    def configure(self, usine: str | None = "- `pin-bump` : `auto`\n", pin: str | None = None) -> None:
        if usine is not None:
            (self.project / "docs" / "agents" / "usine.md").write_text(usine, encoding="utf-8")
        (self.project / SETTINGS).write_text(pin if pin is not None else settings(), encoding="utf-8")

    def notice(self, remote: Remote, **event: object) -> str | None:
        return notice({"cwd": str(self.project), **event}, remote)

    def test_without_the_key_nothing_is_said_and_nothing_is_asked(self) -> None:
        """#278 A1.1: no key, a newer tag exists, no notice, and the network is not even asked."""
        self.configure(usine="- `release-tag` : `forge--v{version}`\n")
        remote = Remote()
        self.assertIsNone(self.notice(remote))
        self.assertEqual(remote.calls, [])

    def test_without_a_usine_file_nothing_is_said(self) -> None:
        self.configure(usine=None)
        self.assertIsNone(self.notice(Remote()))

    def test_a_value_other_than_auto_says_nothing(self) -> None:
        for value in ("on", "", "auto | 2 j"):
            with self.subTest(value=value):
                self.configure(usine=f"- `pin-bump` : `{value}`\n")
                self.assertIsNone(self.notice(Remote()))

    def test_a_repeated_key_says_nothing(self) -> None:
        self.configure(usine="- `pin-bump` : `auto`\n- `pin-bump` : `auto`\n")
        self.assertIsNone(self.notice(Remote()))

    def test_a_newer_tag_is_named_with_the_pin_and_the_consent_it_rests_on(self) -> None:
        """#278 A2.1: the key, pinned 1.16.0, remote 1.18.0: the notice names `forge--v1.18.0`."""
        self.configure()
        message = self.notice(Remote())
        assert message is not None
        self.assertIn("forge--v1.18.0", message)
        self.assertIn("forge--v1.16.0", message)
        self.assertIn(SETTINGS, message)
        self.assertIn("`pin-bump`", message)
        self.assertIn("protected-path", message)
        self.assertIn("human-merge", message)
        self.assertNotIn("forge--v1.19.0-rc1", message)

    def test_the_newest_is_compared_as_numbers_not_as_text(self) -> None:
        """1.9.0 is older than 1.16.0 : a text comparison would call it newer."""
        self.configure()
        self.assertIsNone(self.notice(Remote(tags="refs/tags/forge--v1.9.0\nrefs/tags/forge--v1.16.0")))

    def test_a_pin_on_the_newest_tag_says_nothing(self) -> None:
        self.configure(pin=settings(ref="forge--v1.18.0"))
        self.assertIsNone(self.notice(Remote()))

    def test_tags_of_the_plugin_only_are_compared(self) -> None:
        self.configure()
        self.assertIsNone(self.notice(Remote(tags="refs/tags/other--v9.0.0\nrefs/tags/forge--v1.16.0")))

    def test_the_tags_asked_are_those_of_the_marketplace_repository_by_the_pin_prefix(self) -> None:
        self.configure()
        remote = Remote()
        self.notice(remote)
        asked = " ".join(remote.calls[0])
        self.assertIn("repos/ikoro-labs/forge/git/matching-refs/tags/forge--v", asked)

    def test_network_down_says_nothing(self) -> None:
        """#278 A2.2: `gh` fails on the tags: no notice."""
        self.configure()
        self.assertIsNone(self.notice(Remote(tags=None)))

    def test_an_unreadable_open_pr_list_says_nothing(self) -> None:
        self.configure()
        self.assertIsNone(self.notice(Remote(open_prs_files=None)))

    def test_a_pin_that_is_not_a_version_tag_says_nothing(self) -> None:
        for pin in (settings(ref="main"), settings(ref="forge--v1.16"), "not json", "[]", "{}", ""):
            with self.subTest(pin=pin):
                self.configure(pin=pin)
                self.assertIsNone(self.notice(Remote()))

    def test_a_missing_settings_file_says_nothing(self) -> None:
        self.configure()
        (self.project / SETTINGS).unlink()
        self.assertIsNone(self.notice(Remote()))

    def test_a_marketplace_that_is_not_a_github_source_says_nothing(self) -> None:
        pin = json.dumps({
            "enabledPlugins": {"forge@ikoro-labs": True},
            "extraKnownMarketplaces": {"ikoro-labs": {"source": {"source": "directory", "path": "/x"}}},
        })
        self.configure(pin=pin)
        self.assertIsNone(self.notice(Remote()))

    def test_an_open_pin_pr_silences_the_notice(self) -> None:
        """#278 A3.1: the key, a newer tag, an open PR that changes the pin: no notice."""
        self.configure()
        self.assertIsNone(self.notice(Remote(open_prs_files=SETTINGS_FILES)))

    def test_an_open_pr_that_leaves_the_pin_alone_does_not_silence_it(self) -> None:
        self.configure()
        self.assertIsNotNone(self.notice(Remote(open_prs_files="README.md\ndocs/a.md\n")))

    def test_a_subagent_is_told_nothing(self) -> None:
        self.configure()
        remote = Remote()
        self.assertIsNone(self.notice(remote, agent_id="a1"))
        self.assertEqual(remote.calls, [])


class Boundaries(unittest.TestCase):
    """The hook as a process, and its two outer boundaries: `gh` missing, and the delay."""

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.project = Path(os.path.realpath(self.dir.name))
        (self.project / ".claude").mkdir()
        (self.project / "docs" / "agents").mkdir(parents=True)
        (self.project / "docs" / "agents" / "usine.md").write_text("- `pin-bump` : `auto`\n", encoding="utf-8")
        (self.project / SETTINGS).write_text(settings(), encoding="utf-8")
        self.empty = self.project / "empty-bin"
        self.empty.mkdir()

    def run_hook(self, stdin: str, path: str) -> subprocess.CompletedProcess[str]:
        env = {key: value for key, value in os.environ.items() if not key.startswith("CLAUDE_")}
        env.update(HOME=str(self.project), USERPROFILE=str(self.project), PATH=path)
        return subprocess.run(
            [sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True,
            env=env, cwd=self.project, timeout=60, check=False,
        )

    def test_without_gh_the_process_is_silent_and_exits_zero(self) -> None:
        """#278 A2.2: no `gh` on the PATH."""
        result = self.run_hook(json.dumps({"cwd": str(self.project)}), str(self.empty))
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    def test_an_unreadable_event_is_silent_and_exits_zero(self) -> None:
        for stdin in ("", "not json", "[]", json.dumps({"cwd": 3})):
            with self.subTest(stdin=stdin):
                result = self.run_hook(stdin, str(self.empty))
                self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    @unittest.skipIf(os.name == "nt", "the stand-in `gh` is a POSIX shell script")
    def test_a_gh_that_fails_is_silent_and_exits_zero(self) -> None:
        """#278 A2.2: `gh` is found but the network is down, so it exits 1."""
        gh = self.empty / "gh"
        gh.write_text("#!/bin/sh\necho 'dial tcp: no route to host' >&2\nexit 1\n", encoding="utf-8")
        gh.chmod(0o755)
        result = self.run_hook(json.dumps({"cwd": str(self.project)}), str(self.empty))
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    @unittest.skipIf(os.name == "nt", "the stand-in `gh` is a POSIX shell script")
    def test_a_gh_that_answers_makes_the_hook_print_the_notice_as_additional_context(self) -> None:
        gh = self.empty / "gh"
        script = (
            "#!/bin/sh\n"
            'case "$*" in\n'
            "  *matching-refs*) echo refs/tags/forge--v1.18.0 ;;\n"
            "  *) ;;\n"
            "esac\n"
        )
        gh.write_text(script, encoding="utf-8")
        gh.chmod(0o755)
        result = self.run_hook(json.dumps({"cwd": str(self.project)}), str(self.empty))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "SessionStart")
        self.assertIn("forge--v1.18.0", output["additionalContext"])

    def test_every_call_to_gh_is_bounded_in_time(self) -> None:
        import pin_notice

        seen: dict[str, object] = {}

        def fake(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            seen.update(kwargs)
            raise subprocess.TimeoutExpired(argv, 1)

        with mock.patch("shutil.which", return_value="/usr/bin/gh"), mock.patch("subprocess.run", fake):
            self.assertIsNone(pin_notice.run_gh(["gh", "api", "x"], self.project))
        timeout = seen.get("timeout")
        self.assertIsInstance(timeout, (int, float))
        self.assertTrue(0 < float(str(timeout)) <= 8)

    def test_a_missing_gh_is_none_not_an_error(self) -> None:
        import pin_notice

        with mock.patch("shutil.which", return_value=None):
            self.assertIsNone(pin_notice.run_gh(["gh", "api", "x"], self.project))


class Declaration(unittest.TestCase):
    def test_hooks_json_binds_the_hook_to_session_start_as_an_observer_that_never_blocks(self) -> None:
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        found = [
            hook for group in hooks["SessionStart"] for hook in group["hooks"]
            if "pin_notice.py" in hook.get("command", "")
        ]
        self.assertEqual(len(found), 1, found)
        command = str(found[0]["command"])
        self.assertEqual(command, 'uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/hooks/pin_notice.py"; exit 0')
        self.assertNotIn("onFailure", found[0])
        # Two `gh` calls and the two commands of the BEHIND notice (#333), each bounded: see test_pin_notice_behind.py.
        self.assertTrue(0 < int(str(found[0]["timeout"])) <= 30)

    def test_the_hook_is_bound_nowhere_else(self) -> None:
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        for event, groups in hooks.items():
            if event == "SessionStart":
                continue
            for group in groups:
                for hook in group["hooks"]:
                    self.assertNotIn("pin_notice.py", hook.get("command", ""), event)


if __name__ == "__main__":
    unittest.main()
