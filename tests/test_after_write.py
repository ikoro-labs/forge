import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401
from after_write import EM_DASH, em_dash_problem, load_allowances, main, parse_allowances


class EmDash(unittest.TestCase):
    def test_an_em_dash_beyond_the_allowance_is_reported(self) -> None:
        self.assertIsNone(em_dash_problem("a.md", "plain, text", {}))
        problem = em_dash_problem("a.md", f"one {EM_DASH} two {EM_DASH}", {})
        self.assertEqual(
            problem, "a.md holds 2 em dash: replace each with a comma, a colon or parentheses"
        )
        self.assertIsNone(em_dash_problem("a.md", f"one {EM_DASH} two", {"a.md": 1}))

    def test_the_allowances_file_is_read_line_by_line(self) -> None:
        text = "# count path\n3 docs/legacy.md\n\nx not-a-count\n1 notes/a b.md\n"
        self.assertEqual(parse_allowances(text), {"docs/legacy.md": 3, "notes/a b.md": 1})

    def test_the_allowances_come_from_the_key_the_config_names(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(load_allowances(root), {})
            (root / "docs" / "agents").mkdir(parents=True)
            (root / "docs" / "agents" / "usine.md").write_text(
                "- `em-dash-allowances`: `docs/agents/em-dash.txt`\n", encoding="utf-8"
            )
            self.assertEqual(load_allowances(root), {})
            (root / "docs" / "agents" / "em-dash.txt").write_text("2 a.md\n", encoding="utf-8")
            self.assertEqual(load_allowances(root), {"a.md": 2})

    def test_main_reports_a_written_file_of_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "a.md"
            target.write_text(f"x {EM_DASH} y", encoding="utf-8")

            def run(path: Path) -> int:
                event = json.dumps({"tool_input": {"file_path": str(path)}, "cwd": str(root)})
                with (
                    mock.patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": str(root)}),
                    mock.patch("sys.stdin", io.StringIO(event)),
                    mock.patch("sys.stderr", io.StringIO()),
                ):
                    return main()

            self.assertEqual(run(target), 2)
            target.write_text("x, y", encoding="utf-8")
            self.assertEqual(run(target), 0)
            with tempfile.TemporaryDirectory() as elsewhere:
                outside = Path(elsewhere) / "b.md"
                outside.write_text(EM_DASH, encoding="utf-8")
                self.assertEqual(run(outside), 0)


if __name__ == "__main__":
    unittest.main()
