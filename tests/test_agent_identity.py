"""F-0003 A11, A16 (ticket #401, part a): the identity of the agents, as `agent_identity` judges it.

Pure functions, no process: the configuration and the environment are values the test hands over.
"""

import unittest

import support  # noqa: F401  met les hooks sur le chemin d'import
from agent_identity import LOGIN_KEY, TOKEN_KEY, is_agent_token, mcp_refusal, write_refusal

KEYS = {TOKEN_KEY: ["python app_token.py"], LOGIN_KEY: ["forge-agents[bot]"]}
INSTALLATION = "ghs_" + "x" * 12
HUMANS = "ghp_" + "h" * 12


class AnInstallationTokenIsTheOneThatCounts(unittest.TestCase):
    def test_a11_only_a_token_that_starts_with_ghs_is_an_installation_token(self) -> None:
        """F-0003 A11 (C02): `GH_TOKEN` or `GITHUB_TOKEN`, by the prefix `ghs_` and nothing else."""
        self.assertTrue(is_agent_token({"GH_TOKEN": INSTALLATION}))
        self.assertTrue(is_agent_token({"GITHUB_TOKEN": INSTALLATION}))
        self.assertTrue(is_agent_token({"GH_TOKEN": "ghs_"}))
        for env in ({}, {"GH_TOKEN": ""}, {"GH_TOKEN": HUMANS}, {"GITHUB_TOKEN": "gho_x"}, {"GH_TOKEN": "xghs_x"}):
            with self.subTest(env=env):
                self.assertFalse(is_agent_token(env))

    def test_a11_gh_reads_gh_token_first_so_it_decides(self) -> None:
        """F-0003 A11: a human's `GH_TOKEN` beside an installation `GITHUB_TOKEN` is what `gh` sends: not an agent's."""
        self.assertFalse(is_agent_token({"GH_TOKEN": HUMANS, "GITHUB_TOKEN": INSTALLATION}))
        self.assertTrue(is_agent_token({"GH_TOKEN": INSTALLATION, "GITHUB_TOKEN": HUMANS}))
        self.assertTrue(is_agent_token({"GH_TOKEN": "", "GITHUB_TOKEN": INSTALLATION}))


class AWriteWithoutTheTokenIsRefused(unittest.TestCase):
    def test_a11_it_names_the_gesture_the_keys_and_never_offers_the_humans_token(self) -> None:
        """F-0003 A11, A12: the reason says the write is made under the identity of the agents, and by which key's command."""
        reason = write_refusal(KEYS, {}, "gh pr create")
        assert reason is not None
        self.assertIn("`gh pr create`", reason)
        self.assertIn("the identity of the agents", reason)
        self.assertIn(f"`{TOKEN_KEY}`", reason)
        self.assertIn("forge-agents[bot]", reason)
        self.assertIn("never taken in its place", reason)

    def test_a11_an_installation_token_in_the_environment_lets_the_write_through(self) -> None:
        """F-0003 A11: `GH_TOKEN` or `GITHUB_TOKEN` starting with `ghs_`."""
        self.assertIsNone(write_refusal(KEYS, {"GH_TOKEN": INSTALLATION}, "git push"))
        self.assertIsNone(write_refusal(KEYS, {"GITHUB_TOKEN": INSTALLATION}, "git push"))

    def test_a12_the_humans_token_is_no_substitute_and_is_never_echoed(self) -> None:
        """F-0003 A12, T10: a token of the human's refuses like none, and the reason does not hold it."""
        reason = write_refusal(KEYS, {"GH_TOKEN": HUMANS}, "git push")
        assert reason is not None
        self.assertNotIn(HUMANS, reason)
        self.assertNotIn("python app_token.py", reason)  # the command is named by its key, never by its text

    def test_a11_a_key_that_takes_one_line_and_has_two_refuses_and_cites_the_lines(self) -> None:
        """F-0003 A11: closed by default, as the other keys of the guard file."""
        for config in (
            {**KEYS, LOGIN_KEY: ["a[bot]", "b[bot]"]},
            {**KEYS, TOKEN_KEY: ["one", "two"]},
        ):
            with self.subTest(config=config):
                reason = write_refusal(config, {"GH_TOKEN": INSTALLATION}, "git push")
                assert reason is not None
                self.assertIn("takes one line, and has 2", reason)
                self.assertIn("the identity of the agents", reason)

    def test_a11_a_key_with_an_empty_value_refuses(self) -> None:
        """F-0003 A11: an empty `agent-login` names no identity."""
        reason = write_refusal({**KEYS, LOGIN_KEY: [""]}, {"GH_TOKEN": INSTALLATION}, "git push")
        assert reason is not None
        self.assertIn(f"`{LOGIN_KEY}`", reason)


class WithoutTheKeysNothingChanges(unittest.TestCase):
    def test_a16_a_missing_key_refuses_nothing_whatever_the_environment(self) -> None:
        """F-0003 A16: `agent-token-command` or `agent-login` absent: no write is refused for the identity."""
        for config in ({}, {TOKEN_KEY: ["cmd"]}, {LOGIN_KEY: ["x[bot]"]}, {"agent-slots": ["2"]}):
            for env in ({}, {"GH_TOKEN": HUMANS}, {"GH_TOKEN": INSTALLATION}):
                with self.subTest(config=config, env=env):
                    self.assertIsNone(write_refusal(config, env, "git push"))
                    self.assertIsNone(mcp_refusal(config, "mcp__github__issue_write"))


class AGithubWriteByAnMcpToolIsRefusedClosed(unittest.TestCase):
    def test_a11_the_mcp_server_holds_its_own_token_so_the_write_is_refused_even_with_the_agents_token(self) -> None:
        """F-0003 A11 (Q4): with both keys present, a write by an MCP GitHub tool is refused, token or not."""
        reason = mcp_refusal(KEYS, "mcp__github__issue_write")
        assert reason is not None
        self.assertIn("`mcp__github__issue_write`", reason)
        self.assertIn("the identity of the agents", reason)
        self.assertIn("`gh`", reason)
