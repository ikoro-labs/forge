"""#272: a coder's test containers never wait for the human to remove them.

`guard_infra` is unchanged: a subagent may stop a container and take down a compose stack (without
`-v`), but never `docker rm`. The coder's own instructions say how to start and stop its test
containers so that no removal is needed. These cases live apart from `test_guard_infra.py` (a file
the owner merges by hand): they prove the behaviour a coder relies on, not the guard itself.
"""

import unittest

import support
from test_guard_infra import judged


def squash(text: str) -> str:
    return " ".join(text.split())


class Instructions(unittest.TestCase):
    def test_a1_the_coder_starts_its_test_containers_to_remove_themselves_and_stops_them(self) -> None:
        """#272 A1.1: the rule is in `agents/coder.md`."""
        text = squash((support.PLUGIN / "agents" / "coder.md").read_text(encoding="utf-8"))
        self.assertRegex(text, r"`docker run --rm`.{0,40}`docker compose up`")
        self.assertRegex(text, r"avant de rendre la main.{0,200}`docker stop`.{0,60}`docker compose down`")
        self.assertRegex(text, r"sans `-v`")
        self.assertRegex(text, r"Tu nommes dans `NOTES` chaque conteneur resté")
        self.assertRegex(text, r"jamais.{0,20}`docker rm`")


class WhatASubagentMayDo(unittest.TestCase):
    def test_a2_stop_run_rm_and_compose_down_pass(self) -> None:
        """#272 A2.1: the gestures the coder's rule relies on are allowed to a subagent."""
        for command in (
            "docker stop x",
            "docker run --rm -d --name x postgres:16",
            "docker compose down",
            "docker compose -f ci.yml -p e2e down --remove-orphans",
        ):
            with self.subTest(command=command):
                self.assertIsNone(judged(command, declared=[], agent=True))

    def test_a3_docker_rm_stays_denied_to_a_subagent(self) -> None:
        """#272 A3.1: no removal is left to the coder."""
        for command in ("docker rm -f x", "docker rm x", "docker compose down -v"):
            with self.subTest(command=command):
                self.assertIn("`docker", judged(command, declared=[], agent=True) or "")


if __name__ == "__main__":
    unittest.main()
