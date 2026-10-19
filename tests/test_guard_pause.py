import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401
from guard_pause import main, paused_reason


class Pause(unittest.TestCase):
    def test_the_reason_is_the_file_text(self) -> None:
        self.assertIsNone(paused_reason(None))
        self.assertEqual(paused_reason("CI down\n"), "CI down")
        self.assertEqual(paused_reason("  \n"), "no reason given")

    def test_a_launch_is_refused_while_the_switch_exists(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            event = json.dumps({"tool_name": "Agent", "cwd": root})

            def run() -> tuple[int, str]:
                stderr = io.StringIO()
                with (
                    mock.patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": root}),
                    mock.patch("sys.stdin", io.StringIO(event)),
                    mock.patch("sys.stderr", stderr),
                ):
                    return main(), stderr.getvalue()

            self.assertEqual(run()[0], 0)
            (Path(root) / ".claude").mkdir()
            (Path(root) / ".claude" / "PAUSED").write_text("quota spent\n", encoding="utf-8")
            code, message = run()
            self.assertEqual(code, 2)
            self.assertIn("quota spent", message)


if __name__ == "__main__":
    unittest.main()
