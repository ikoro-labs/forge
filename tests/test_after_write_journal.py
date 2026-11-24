"""F-0002 A23: a refusal of `after_write` for `lint-on-write` or `format-on-write` enters the journal.

Each case runs the hook as Claude Code does, as a process fed an event on standard input, with a
temporary `HOME` and `USERPROFILE` and none of the session's `CLAUDE_` or `GIT_` variables: the real
`~/.claude` is never read nor written.
"""

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import support

HOOK = support.PLUGIN / "hooks" / "after_write.py"
FIELDS = {"date", "guard", "rule", "agent", "repo", "branch", "verb"}
SECRET = "ghp_S3CR3T0123456789"
EM_DASH = chr(0x2014)


def environment(home: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "GIT_"))}
    env.update(HOME=str(home), USERPROFILE=str(home), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    return env


class RefusalJournal(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name).resolve() / "home"
        self.root = Path(folder.name).resolve() / "depot"
        self.home.mkdir()
        (self.root / "docs" / "agents").mkdir(parents=True)
        subprocess.run(  # noqa: S603, S607 - fixed argv in a temporary repository
            ["git", "init", "-q", "-b", "feat/essai", str(self.root)],
            env=environment(self.home),
            check=True,
        )
        self.python = shlex.quote(Path(sys.executable).as_posix())
        self.target = self.root / "a.txt"
        self.target.write_text("x", encoding="utf-8")
        self.journal = self.home / ".claude" / "hooks" / "state" / "refusals"

    def tool(self, name: str, body: str) -> str:
        """A command that runs `body`, then exits 1."""
        path = self.root / name
        path.write_text(f"import sys\n{body}\nsys.exit(1)\n", encoding="utf-8")
        return f"{self.python} {shlex.quote(path.as_posix())}"

    def configure(self, *entries: tuple[str, str]) -> None:
        text = "".join(f"- `{key}` : `{line}`\n" for key, line in entries)
        (self.root / "docs" / "agents" / "usine.md").write_text(text, encoding="utf-8")

    def run_hook(
        self, tool: str = "Write", agent: str | None = None, home: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        event: dict[str, object] = {
            "tool_name": tool,
            "tool_input": {"file_path": str(self.target)},
            "cwd": str(self.root),
        }
        if agent is not None:
            event["agent_type"] = agent
        return subprocess.run(  # noqa: S603 - the interpreter running this suite, a fixed script
            [sys.executable, str(HOOK)],
            input=json.dumps(event),
            env=environment(home or self.home),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )

    def lines(self) -> list[dict[str, str]]:
        if not self.journal.is_dir():
            return []
        return [
            json.loads(line)
            for path in sorted(self.journal.glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()
        ]

    def test_a_refused_lint_adds_one_line_with_the_fields_of_the_three_guards(self) -> None:
        """F-0002 A23: guard `after_write`, rule `lint-on-write`, the seven fields and nothing else."""
        self.configure(("lint-on-write", f"**/*.txt | {self.tool('lint.py', 'print(1)')}"))
        done = self.run_hook(tool="Write", agent="forge:coder")
        self.assertEqual(done.returncode, 2, done.stderr)
        found = self.lines()
        self.assertEqual(len(found), 1)
        line = found[0]
        self.assertEqual(set(line), FIELDS)
        self.assertEqual(line["guard"], "after_write")
        self.assertEqual(line["rule"], "lint-on-write")
        self.assertEqual(line["agent"], "forge:coder")
        self.assertEqual(line["repo"], "depot")
        self.assertEqual(line["branch"], "feat/essai")
        self.assertEqual(line["verb"], "Write")
        moment = datetime.fromisoformat(line["date"])
        self.assertLess(abs((datetime.now(timezone.utc) - moment).total_seconds()), 300)
        self.assertTrue((self.journal / f"{moment.astimezone(timezone.utc):%Y-%m-%d}.jsonl").is_file())

    def test_a_refused_format_names_its_own_rule_and_the_tool_that_wrote(self) -> None:
        """F-0002 A23: `format-on-write` is its own rule; the verb is the tool, `main` the main session."""
        self.configure(("format-on-write", f"**/*.txt | {self.tool('fmt.py', 'print(1)')}"))
        done = self.run_hook(tool="Edit")
        self.assertEqual(done.returncode, 2, done.stderr)
        found = self.lines()
        self.assertEqual(len(found), 1)
        self.assertEqual(
            (found[0]["guard"], found[0]["rule"], found[0]["agent"], found[0]["verb"]),
            ("after_write", "format-on-write", "main", "Edit"),
        )

    def test_the_journal_never_holds_the_command_nor_the_tool_output(self) -> None:
        """F-0002 A23: a tool that prints a secret and a command that names one leave neither."""
        command = self.tool("lint.py", f"print('{SECRET}')")
        self.configure(("lint-on-write", f"**/*.txt | {command} --token {SECRET}"))
        done = self.run_hook()
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn(SECRET, done.stderr)  # the agent still gets the tail
        found = self.lines()
        self.assertEqual(len(found), 1)
        written = "".join(path.read_text(encoding="utf-8") for path in self.journal.glob("*.jsonl"))
        self.assertNotIn(SECRET, written)
        self.assertNotIn("lint.py", written)
        self.assertNotIn(self.python, written)

    def test_a_write_that_passes_leaves_no_line_and_each_refusal_adds_one(self) -> None:
        """F-0002 A23: a write the commands accept writes nothing; two refused writes, two lines."""
        passing = self.root / "ok.py"
        passing.write_text("print('fine')\n", encoding="utf-8")
        failing = self.tool("lint.py", "print(1)")
        self.configure(
            ("lint-on-write", f"**/*.txt | {self.python} {shlex.quote(passing.as_posix())}"),
            ("lint-on-write", f"**/*.md | {failing}"),
        )
        self.assertEqual(self.run_hook().returncode, 0)
        self.assertFalse(self.journal.exists())
        self.configure(("lint-on-write", f"**/*.txt | {failing}"))
        self.assertEqual(self.run_hook().returncode, 2)
        self.assertEqual(self.run_hook().returncode, 2)
        self.assertEqual(len(self.lines()), 2)

    def test_a_refusal_that_is_no_lint_nor_format_failure_is_not_journaled(self) -> None:
        """F-0002 A23: an em dash, or a line the hook ignores, is no refusal of the two keys."""
        failing = self.tool("lint.py", "print(1)")
        self.target.write_text(f"x {EM_DASH} y", encoding="utf-8")
        self.configure(("lint-on-write", "**/*.txt"), ("lint-on-write", f"**/*.md | {failing}"))
        done = self.run_hook()
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertFalse(self.journal.exists())
        # The same write, with a command that does fail: only that failure enters the journal.
        self.configure(("lint-on-write", "**/*.txt"), ("lint-on-write", f"**/*.txt | {failing}"))
        done = self.run_hook()
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertEqual([line["rule"] for line in self.lines()], ["lint-on-write"])

    def test_both_keys_failing_in_one_write_give_one_line_each(self) -> None:
        """F-0002 A23: one line per key that refuses, in the order the hook runs them."""
        self.configure(
            ("lint-on-write", f"**/*.txt | {self.tool('lint.py', 'print(1)')}"),
            ("format-on-write", f"**/*.txt | {self.tool('fmt.py', 'print(2)')}"),
        )
        done = self.run_hook()
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertEqual([line["rule"] for line in self.lines()], ["format-on-write", "lint-on-write"])

    def test_a_journal_that_cannot_be_written_leaves_the_refusal_as_it_is(self) -> None:
        """F-0002 A23: `refusals` is a file, so no line can be added: same exit code, same message."""
        self.configure(("lint-on-write", f"**/*.txt | {self.tool('lint.py', 'print(1)')}"))
        clear = self.run_hook()
        self.assertEqual(len(self.lines()), 1)
        blocked = self.home / "bloque"
        (blocked / ".claude" / "hooks" / "state").mkdir(parents=True)
        (blocked / ".claude" / "hooks" / "state" / "refusals").write_text("un fichier", encoding="utf-8")
        done = self.run_hook(home=blocked)
        self.assertEqual((done.returncode, done.stderr), (2, clear.stderr))


class Documentation(unittest.TestCase):
    def test_the_indicators_page_says_what_after_write_adds_to_the_journal(self) -> None:
        """F-0002 A23: the guard, the two rules, the verb, and what never enters the journal."""
        text = (support.REPO_ROOT / "docs" / "indicateurs-de-service.md").read_text(encoding="utf-8")
        page = " ".join(text.split())  # the page wraps its lines
        for needle in (
            "`guard` `after_write`",
            "`lint-on-write` ou `format-on-write`",
            "le nom de l'outil qui a écrit",
            "Ni la commande ni la fin de sa sortie n'entrent au journal",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, page)


if __name__ == "__main__":
    unittest.main()
