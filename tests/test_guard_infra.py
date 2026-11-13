"""The infra guard (`guard_infra`) and the merge of a PR that changes it (`guard_git`).

A guarded command is refused to a subagent and asked in the main session; the read list is the
only thing admitted on a host of the `infra-hosts` key. A PR whose diff touches the infra guard or
these tests is merged by the owner, by hand: removing the refusal from `guard_git` turns these
tests red, and changing them is itself such a PR.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable, Mapping
from pathlib import Path
from unittest import mock

import support
from guard_git import guarded_main as git_guarded_main
from guard_git import pr_files_via_gh, refusal
from guard_infra import guarded_main, verdict

ADDRESS = "203.0.113.7"
DECLARED = [ADDRESS, "meridianre-ci"]
# The `infra-verify` key of a project: its own verify commands, admitted on its hosts.
VERIFY = ["/srv/runner/provision.sh verify", "infra/host/container.sh verify"]
# `ssh -G` as the fake prints it: aliases, a host behind a jump, a host it cannot print.
ALIASES = {"vps": ADDRESS, "elsewhere": "198.51.100.1", "box": "box.internal"}


def fake_ssh_config(args: list[str]) -> Mapping[str, str] | None:
    host = args[-1].rpartition("@")[2]
    if host == "broken":
        return None
    if host == "behind":
        return {"hostname": "198.51.100.9", "proxyjump": "vps"}
    if host.startswith("loop"):
        return {"hostname": "198.51.100.8", "proxyjump": f"{host}x"}
    return {"hostname": ALIASES.get(host, host)}


def fake_dns(name: str) -> frozenset[str] | None:
    if name == "slow.example":
        return None
    return {"ci.example": frozenset({ADDRESS})}.get(name, frozenset())


def judged(
    command: str,
    declared: list[str] | None = None,
    agent: bool = False,
    verify: list[str] | None = None,
) -> str | None:
    event: dict[str, object] = {"tool_input": {"command": command}}
    if agent:
        event["agent_id"] = "a1"
    hosts = DECLARED if declared is None else declared
    found = verdict(event, hosts, fake_ssh_config, fake_dns, verify=verify or [])
    return None if found is None else found[1]


class Case(unittest.TestCase):
    def guarded(
        self, *commands: str, declared: list[str] | None = None, verify: list[str] | None = None
    ) -> None:
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNotNone(judged(command, declared, verify=verify), command)

    def admitted(
        self, *commands: str, declared: list[str] | None = None, verify: list[str] | None = None
    ) -> None:
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNone(judged(command, declared, verify=verify), command)


class DenyList(Case):
    """One case per guarded verb, run locally, without the `infra-hosts` key."""

    def test_docker_verbs(self) -> None:
        for command, named in (
            ("docker rm web", "docker rm"),
            ("docker rmi image:1", "docker rmi"),
            ("docker kill web", "docker kill"),
            ("docker system prune -af", "docker system prune"),
            ("docker container prune", "docker container prune"),
            ("docker volume prune -f", "docker volume prune"),
            ("docker builder prune", "docker builder prune"),
            ("docker image prune -a", "docker image prune"),
            ("docker network prune", "docker network prune"),
            ("docker volume rm data", "docker volume rm"),
            ("docker network rm ci", "docker network rm"),
        ):
            with self.subTest(command=command):
                self.assertIn(f"`{named}`", judged(command, declared=[]) or "")

    def test_docker_aliases_and_global_options(self) -> None:
        self.guarded(
            "docker container rm web",
            "docker container kill web",
            "docker image rm x",
            "docker volume remove data",
            "docker buildx prune",
            "docker -H ssh://x rm web",
            "docker --context prod system prune",
            declared=[],
        )

    def test_docker_compose_down_with_volumes(self) -> None:
        self.guarded(
            "docker compose down -v",
            "docker compose down --volumes",
            "docker compose -f ci.yml -p e2e down -v --remove-orphans",
            "docker compose down -tv 5",
            "docker-compose down -v",
            declared=[],
        )

    def test_docker_compose_up_and_down_pass(self) -> None:
        self.admitted(
            "docker compose up -d --build",
            "docker compose down",
            "docker compose down --remove-orphans",
            "docker compose down --volumes=false",
            declared=[],
        )

    def test_systemctl_verbs(self) -> None:
        for verb in ("restart", "stop", "disable", "mask", "kill"):
            with self.subTest(verb=verb):
                found = judged(f"systemctl --user {verb} docker", declared=[])
                assert found is not None
                self.assertIn(f"`systemctl {verb}`", found)
        self.guarded(
            "systemctl try-restart x", "systemctl reboot", "reboot", "shutdown -h now", declared=[]
        )

    def test_lxc_verbs(self) -> None:
        for command in ("lxc config set ci limits.memory 4GB", "lxc config unset ci limits.memory"):
            with self.subTest(command=command):
                self.assertIn(
                    f"`{' '.join(command.split()[:3])}`", judged(command, declared=[]) or ""
                )
        for verb in ("delete", "stop", "restart"):
            with self.subTest(verb=verb):
                self.assertIn(
                    f"`lxc {verb}`", judged(f"lxc --project p {verb} ci", declared=[]) or ""
                )

    def test_networkctl_every_verb_but_the_reads(self) -> None:
        self.guarded(
            "networkctl reload", "networkctl reconfigure eth0", "networkctl down eth0", declared=[]
        )
        self.admitted(
            "networkctl", "networkctl status", "networkctl list", "networkctl lldp", declared=[]
        )

    def test_svc_sh_stop_and_uninstall(self) -> None:
        self.guarded("./svc.sh stop", "sudo /opt/runner/svc.sh uninstall", declared=[])
        self.admitted("./svc.sh status", declared=[])

    def test_reads_and_data_pass(self) -> None:
        self.admitted(
            "docker ps -a",
            "docker logs -f web",
            "systemctl status docker",
            "lxc list",
            "git commit -m 'docker rm web'",
            "echo 'systemctl restart docker'",
            'grep -rn "lxc delete" docs',
            "uv run pytest",
            declared=[],
        )


class Wrappers(Case):
    def test_one_case_per_wrapper(self) -> None:
        for command in (
            "sudo docker rm web",
            "sudo -u root -E docker rm web",
            "env DOCKER_HOST=x docker rm web",
            "env -i -u HOME docker rm web",
            "heavy-slot --timeout 540 -- docker rm web",
            "heavy-slot --label e2e docker rm web",
            "systemd-run --user --scope -q -p MemoryMax=3G -- docker rm web",
            "systemd-run --user --scope docker rm web",
            "timeout 30 docker rm web",
            "timeout -k 5 30 docker rm web",
            "nice -n 10 docker rm web",
            "nohup docker rm web",
            "exec docker rm web",
            "command docker rm web",
            "time docker rm web",
            "FOO=1 docker rm web",
            "sh -c 'docker rm web'",
            'bash -c "docker rm web"',
            "bash -lc 'cd /x && docker rm web'",
            "echo $(docker rm web)",
            'echo "$(docker rm web)"',
            "echo `docker rm web`",
            "diff <(docker rm web) x",
            "true; docker rm web",
            "true && docker rm web",
            "false || docker rm web",
            "docker ps -q | xargs docker rm",
            "docker ps -q | xargs -n 1 docker rm",
            "eval 'docker rm web'",
            "bash <<'EOF'\ndocker rm web\nEOF",
            "if true; then docker rm web; fi",
            "sudo sh -c 'timeout 5 env A=1 docker rm web'",
        ):
            with self.subTest(command=command):
                found = judged(command, declared=[])
                assert found is not None, command
                self.assertIn("`docker rm`", found)

    def test_a_newline_ends_a_command(self) -> None:
        self.assertIn("`docker rm`", judged("cd /srv\ndocker rm web", declared=[]) or "")

    def test_a_wrapper_around_a_read_passes(self) -> None:
        self.admitted(
            "sudo docker ps", "heavy-slot --timeout 540 -- docker compose up -d", declared=[]
        )

    def test_what_cannot_be_read_is_guarded(self) -> None:
        for command in (
            "docker rm 'web",
            "echo $(docker ps",
            "docker $VERB web",
            "systemctl $(echo restart) docker",
            "$(which docker) rm web",
            "echo 'docker ps' | bash",
            "heavy-slot --unknown -- docker ps",
            "env -S 'docker rm web'",
        ):
            with self.subTest(command=command):
                found = judged(command, declared=[])
                assert found is not None, command
                self.assertIn("cannot read", found)


class RealCommands(Case):
    def test_the_two_real_commands_are_admitted(self) -> None:
        commands = (
            "lxc exec meridianre-ci -- sh -c 'pgrep -fc \"[R]unner.Worker\" || true'",
            "lxc exec meridianre-ci -- systemctl show docker -p ActiveEnterTimestamp",
        )
        self.admitted(*commands)
        self.admitted(*commands, declared=[])

    def test_the_declared_verify_commands_are_admitted(self) -> None:
        commands = (
            "ssh vps bash /srv/runner/provision.sh verify",
            "ssh vps /srv/runner/provision.sh verify",
            "lxc exec meridianre-ci -- infra/host/container.sh verify",
        )
        self.admitted(*commands, verify=VERIFY)
        self.guarded(
            "ssh vps bash /srv/runner/provision.sh apply",
            "ssh vps bash /srv/runner/provision.sh verify --fix",
            "ssh vps bash /srv/runner/provision.sh",
            "ssh vps bash ./infra/host/container.sh verify",
            verify=VERIFY,
        )

    def test_without_the_infra_verify_key_no_verify_command_is_admitted(self) -> None:
        self.guarded(
            "ssh vps bash /srv/runner/provision.sh verify",
            "ssh vps bash /root/infra/runner/provision-local.sh verify",
            "lxc exec meridianre-ci -- infra/runner/host/lxd-container.sh verify",
        )

    def test_a_declared_verify_command_is_no_read_on_its_own(self) -> None:
        # The key admits a command on a declared host; it does not lift the deny list, there or here.
        self.guarded(
            "docker rm web",
            "ssh vps docker rm web",
            "lxc exec meridianre-ci -- systemctl restart docker",
            verify=["docker rm web", "systemctl restart docker"],
        )

    def test_the_plugin_cites_no_path_of_a_project(self) -> None:
        source = (support.PLUGIN / "hooks" / "guard_infra.py").read_text(encoding="utf-8")
        for path in ("/root/infra", "provision-local.sh", "lxd-container.sh"):
            with self.subTest(path=path):
                self.assertNotIn(path, source)


class DeclaredHost(Case):
    def test_a_read_is_admitted(self) -> None:
        self.admitted(
            f"ssh root@{ADDRESS} docker ps",
            "ssh vps 'docker logs --tail 50 web 2>&1'",
            "ssh vps 'docker inspect web; docker images; docker stats --no-stream'",
            "ssh vps 'df -h && free -m && uptime'",
            "ssh vps 'systemctl is-active docker || true'",
            "ssh vps journalctl -u docker -n 100",
            "ssh vps 'ps aux; pgrep -f runner'",
            "ssh vps cat /proc/meminfo /proc/loadavg",
            "ssh vps sudo docker ps",
            "ssh -p 22 -o ConnectTimeout=5 vps docker ps",
            "ssh ci.example uptime",
            "ssh vps 'docker ps 2>/dev/null'",
            "lxc exec meridianre-ci -- lxc list",
            "lxc exec local:meridianre-ci -- lxc info",
            "lxc exec meridianre-ci -- lxc config show",
        )

    def test_a_write_is_guarded(self) -> None:
        for command in (
            "ssh vps touch /tmp/x",
            "ssh vps 'docker ps; rm -rf /srv'",
            "ssh vps 'docker ps > /root/out'",
            "ssh vps docker stats",
            "ssh vps cat /etc/shadow",
            "ssh vps cat /proc/../etc/shadow",
            "ssh vps journalctl --vacuum-size=1M",
            "ssh vps bash -s",
            "ssh vps",
            "scp build.tar vps:/srv/",
            "scp vps:/etc/hosts .",
            "rsync -a dist/ vps:/srv/",
            "ssh behind docker ps; ssh behind touch /x",
            "lxc exec meridianre-ci -- rm -rf /tmp/x",
            "lxc exec meridianre-ci -- sh -c 'pgrep x || reboot'",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(judged(command), command)
        self.assertIn("`touch /tmp/x`", judged("ssh vps touch /tmp/x") or "")

    def test_a_declared_name_is_matched_through_ssh_config_without_dns(self) -> None:
        # `box` is an alias of `box.internal`, which the resolver does not know.
        self.assertIsNotNone(judged("ssh box touch /x", declared=["box.internal"]))
        self.assertIsNone(judged("ssh box uptime", declared=["box.internal"]))

    def test_an_instance_is_matched_with_or_without_its_remote(self) -> None:
        self.assertIsNotNone(judged("lxc exec local:meridianre-ci -- touch /x"))

    def test_an_unreadable_destination_is_guarded(self) -> None:
        for command in (
            "ssh $HOST docker ps",
            "ssh `host` docker ps",
            "ssh -F ./cfg vps docker ps",
            "ssh broken docker ps",
            "ssh slow.example docker ps",
            "ssh loop docker ps",
            "scp x $DEST:/srv",
            "scp build.tar $DEST",
            "lxc exec $CI -- docker ps",
        ):
            with self.subTest(command=command):
                found = judged(command)
                assert found is not None, command
                self.assertIn("cannot read", found)

    def test_another_host_meets_the_deny_list_only(self) -> None:
        self.admitted(
            "ssh elsewhere touch /tmp/x", "scp x elsewhere:/srv", "lxc exec other -- rm -rf /tmp"
        )
        self.guarded("ssh elsewhere 'docker rm web'", "lxc exec other -- docker rm web")

    def test_without_the_key_no_remote_host_is_guarded(self) -> None:
        self.admitted("ssh vps touch /tmp/x", "scp x vps:/srv", "ssh $HOST uptime", declared=[])
        self.guarded("ssh vps 'systemctl restart docker'", declared=[])


class TheHook(unittest.TestCase):
    """The real `main`: a subagent is refused, the main session is asked, the key is read."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        (self.root / "docs" / "agents").mkdir(parents=True)
        self.env = {
            **{key: value for key, value in os.environ.items() if not key.startswith("CLAUDE_")},
            "HOME": self.tmp.name,
            "USERPROFILE": self.tmp.name,
            "CLAUDE_PROJECT_DIR": str(self.root),
        }

    def run_hook(self, event: object) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch.dict(os.environ, self.env, clear=True),
            mock.patch("sys.stdin", io.StringIO(json.dumps(event))),
            mock.patch("sys.stdout", out),
            mock.patch("sys.stderr", err),
            mock.patch("guard_infra.ssh_config_via_ssh", lambda: fake_ssh_config),
            mock.patch("guard_infra.addresses_via_dns", fake_dns),
        ):
            return guarded_main(), out.getvalue(), err.getvalue()

    def test_a_subagent_is_refused_with_exit_2(self) -> None:
        code, out, err = self.run_hook(
            {"tool_input": {"command": "docker rm web"}, "agent_id": "a1"}
        )
        self.assertEqual((code, out), (2, ""))
        self.assertIn("Blocked by the forge plugin (guard_infra): `docker rm`", err)
        self.assertIn("! <command>", err)

    def test_the_main_session_is_asked(self) -> None:
        event = {"tool_input": {"command": "docker rm web"}, "agent_type": "forge:coder"}
        code, out, err = self.run_hook(event)
        self.assertEqual((code, err), (0, ""))
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "ask")
        self.assertEqual(decision["hookEventName"], "PreToolUse")
        self.assertIn("`docker rm`", decision["permissionDecisionReason"])

    def test_an_admitted_command_says_nothing(self) -> None:
        self.assertEqual(
            self.run_hook({"tool_input": {"command": "docker ps"}, "agent_id": "a1"}), (0, "", "")
        )

    def test_the_hosts_come_from_the_infra_hosts_key(self) -> None:
        event = {"tool_input": {"command": "ssh vps touch /x"}, "agent_id": "a1"}
        self.assertEqual(self.run_hook(event)[0], 0)
        (self.root / "docs" / "agents" / "usine.md").write_text(
            f"- `infra-hosts` : `{ADDRESS}`\n", encoding="utf-8"
        )
        self.assertEqual(self.run_hook(event)[0], 2)

    def test_the_verify_commands_come_from_the_infra_verify_key(self) -> None:
        command = "ssh vps bash /srv/runner/provision.sh verify"
        event = {"tool_input": {"command": command}, "agent_id": "a1"}
        usine = self.root / "docs" / "agents" / "usine.md"
        usine.write_text(f"- `infra-hosts` : `{ADDRESS}`\n", encoding="utf-8")
        self.assertEqual(self.run_hook(event)[0], 2)
        usine.write_text(
            f"- `infra-hosts` : `{ADDRESS}`\n"
            "- `infra-verify` : `/srv/runner/provision.sh verify`\n",
            encoding="utf-8",
        )
        self.assertEqual(self.run_hook(event)[0], 0)

    def test_an_unreadable_event_is_refused(self) -> None:
        self.assertEqual(self.run_hook(["not", "an", "event"])[0], 2)
        self.assertEqual(self.run_hook({"tool_input": "docker rm web"})[0], 2)

    def test_a_crash_refuses_and_says_it_failed(self) -> None:
        with mock.patch("guard_infra.verdict", side_effect=RuntimeError("boom")):
            code, _, err = self.run_hook({"tool_input": {"command": "docker rm web"}})
        self.assertEqual(code, 2)
        self.assertIn("guard_infra failed", err)

    def test_the_script_runs_as_claude_code_runs_it(self) -> None:
        event = json.dumps({"tool_input": {"command": "sudo docker rm web"}, "agent_id": "a1"})
        script = support.PLUGIN / "hooks" / "guard_infra.py"
        env = {key: value for key, value in self.env.items() if key != "PYTHONPATH"}
        done = subprocess.run(
            [sys.executable, str(script)],
            input=event,
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("`docker rm`", done.stderr)

    def test_hooks_json_runs_the_guard_on_every_shell_call_and_fails_closed(self) -> None:
        hooks = json.loads((support.PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        entries = [
            (group["matcher"], hook)
            for group in hooks["hooks"]["PreToolUse"]
            for hook in group["hooks"]
            if "guard_infra.py" in hook["command"]
        ]
        self.assertEqual(len(entries), 1)
        matcher, hook = entries[0]
        self.assertEqual(matcher, "Bash|PowerShell")
        self.assertTrue(hook["command"].endswith("|| exit 2"))
        self.assertEqual(hook.get("onFailure"), "block")


def always_green(_pr: str | None) -> bool:
    return True


def files(*paths: str) -> Callable[[str | None, str | None], list[str] | None]:
    return lambda _pr, _repository: list(paths)


def unreadable(_pr: str | None, _repository: str | None) -> list[str] | None:
    return None


def merge(
    command: str, pr_files: Callable[[str | None, str | None], list[str] | None]
) -> str | None:
    return refusal(command, "feat/x", always_green, pr_files=pr_files)


class MergeOfTheGuard(unittest.TestCase):
    """`guard_git` refuses to merge a PR that changes the infra guard: only the owner does, by hand."""

    def test_a_pr_that_touches_the_guard_or_its_tests_is_refused(self) -> None:
        for path in (
            "plugins/forge/hooks/guard_infra.py",
            "tests/test_guard_infra.py",
            "./tests\\test_guard_infra.py",
            # The refusal itself, and the registration that runs the guard.
            "plugins/forge/hooks/guard_git.py",
            "plugins/forge/hooks/hooks.json",
        ):
            with self.subTest(path=path):
                found = merge("gh pr merge 5 --merge", files("README.md", path))
                assert found is not None
                self.assertIn(
                    "this PR changes the infra guard: only the owner merges it, by hand", found
                )

    def test_another_pr_goes_through(self) -> None:
        self.assertIsNone(
            merge("gh pr merge 5 --merge", files("README.md", "plugins/forge/hooks/guard_coder.py"))
        )

    def test_an_unreadable_list_is_refused(self) -> None:
        found = merge("gh -R ikoro-labs/forge pr merge 5", unreadable)
        assert found is not None
        self.assertIn("only the owner merges it, by hand", found)
        self.assertIn("cannot be read", found)

    def test_the_number_and_the_repository_reach_the_reading(self) -> None:
        seen: list[tuple[str | None, str | None]] = []

        def recorded(pr: str | None, repository: str | None) -> list[str]:
            seen.append((pr, repository))
            return []

        for command in (
            "gh pr merge 5 -R ikoro-labs/forge",
            "gh --repo=o/r pr merge 6",
            "gh pr merge",
        ):
            merge(command, recorded)
        self.assertEqual(seen, [("5", "ikoro-labs/forge"), ("6", "o/r"), (None, None)])

    def test_a_merge_by_the_rest_api_is_judged_on_the_same_files(self) -> None:
        command = "gh api -X PUT repos/ikoro-labs/forge/pulls/5/merge -f merge_method=merge"
        self.assertIsNotNone(merge(command, files("plugins/forge/hooks/guard_infra.py")))
        self.assertIsNotNone(merge(command, unreadable))
        self.assertIsNone(merge(command, files("README.md")))
        self.assertIsNone(
            merge("gh api repos/ikoro-labs/forge/pulls/5/merge", unreadable)
        )  # a GET reads

    def test_a_merge_by_graphql_is_refused(self) -> None:
        command = "gh api graphql -f query='mutation { mergePullRequest(input: {pullRequestId: \"PR_x\"}) { clientMutationId } }'"
        found = merge(command, files("README.md"))
        assert found is not None
        self.assertIn("only the owner merges it, by hand", found)

    def test_the_reading_asks_gh_for_the_number_and_the_repository(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            # `gh` is played by Python, which runs the script `pr` of the command's folder.
            (Path(folder) / "pr").write_text(
                "import json, sys\nprint(json.dumps({'files': [{'path': ' '.join(sys.argv[1:])}]}))\n",
                encoding="utf-8",
            )
            with mock.patch("shutil.which", lambda _name: sys.executable):
                self.assertEqual(
                    pr_files_via_gh(folder)("5", "ikoro-labs/forge"),
                    ["view 5 -R ikoro-labs/forge --json files"],
                )
            (Path(folder) / "pr").write_text("import sys; sys.exit(1)\n", encoding="utf-8")
            with mock.patch("shutil.which", lambda _name: sys.executable):
                self.assertIsNone(pr_files_via_gh(folder)("5", None))
        with mock.patch("shutil.which", lambda _name: None):
            self.assertIsNone(pr_files_via_gh(None)("5", None))

    def test_the_hook_reads_the_files_of_the_pr_it_merges(self) -> None:
        def run_hook(
            pr_files: Callable[[str | None, str | None], list[str] | None],
        ) -> tuple[int, str]:
            event = {
                "tool_input": {"command": "gh pr merge 5 -R ikoro-labs/forge"},
                "cwd": ".",
                "agent_id": "a1",
            }
            err = io.StringIO()
            with tempfile.TemporaryDirectory() as home:
                environment = {
                    key: value for key, value in os.environ.items() if not key.startswith("CLAUDE_")
                }
                with (
                    mock.patch.dict(
                        os.environ, {**environment, "HOME": home, "USERPROFILE": home}, clear=True
                    ),
                    mock.patch("sys.stdin", io.StringIO(json.dumps(event))),
                    mock.patch("sys.stderr", err),
                    mock.patch("guard_git.project_root", lambda _event: Path(home)),
                    mock.patch("guard_git.current_branch", lambda _cwd: "feat/x"),
                    mock.patch("guard_git.checks_green_via_gh", lambda _cwd: always_green),
                    mock.patch("guard_git.description_via_gh", lambda _cwd: lambda _pr: ""),
                    mock.patch("guard_git.pr_files_via_gh", lambda _cwd: pr_files),
                ):
                    return git_guarded_main(), err.getvalue()

        code, message = run_hook(files("plugins/forge/hooks/guard_infra.py"))
        self.assertEqual(code, 2)
        self.assertIn("only the owner merges it, by hand", message)
        self.assertEqual(run_hook(unreadable)[0], 2)
        self.assertEqual(run_hook(files("README.md"))[0], 0)


if __name__ == "__main__":
    unittest.main()
