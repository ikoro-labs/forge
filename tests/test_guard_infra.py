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
from guard_infra import docker_context_via_docker, guarded_main, verdict

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
    found = {"ci.example": ADDRESS, "mapped.example": f"::ffff:{ADDRESS}"}.get(name)
    return frozenset({found}) if found else frozenset()


# `docker context inspect` as the fake answers it, by context name (None: the current one).
CONTEXTS: dict[str | None, str] = {
    None: "unix:///var/run/docker.sock",
    "local": "unix:///var/run/docker.sock",
    "prod": "ssh://root@vps",
    "tcpctx": f"tcp://{ADDRESS}:2376",
}


def fake_docker_context(name: str | None) -> str | None:
    return CONTEXTS.get(name)


def judged(
    command: str,
    declared: list[str] | None = None,
    agent: bool = False,
    verify: list[str] | None = None,
    docker_context: Callable[[str | None], str | None] = fake_docker_context,
    tool: str = "Bash",
) -> str | None:
    event: dict[str, object] = {"tool_input": {"command": command}, "tool_name": tool}
    if agent:
        event["agent_id"] = "a1"
    hosts = DECLARED if declared is None else declared
    found = verdict(
        event, hosts, fake_ssh_config, fake_dns, verify=verify or [], docker_context=docker_context
    )
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

    def test_lxc_verbs_beyond_the_spec(self) -> None:
        for command, named in (
            ("lxc config edit ci", "`lxc config edit`"),
            ("lxc config device remove ci eth0", "`lxc config device remove`"),
            ("lxc restore ci snap0", "`lxc restore`"),
            ("lxc pause ci", "`lxc pause`"),
        ):
            with self.subTest(command=command):
                self.assertIn(named, judged(command, declared=[]) or "")
        self.admitted("lxc config device show ci", "lxc config show ci", declared=[])

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


class ParsedTriggers(Case):
    """The guarded programs are found in the parsed words, not in the raw text."""

    def test_a_program_spelled_through_quotes_or_escapes_is_found(self) -> None:
        for command in (
            "dock''er rm -f x",
            "d\\ocker rm -f x",
            '"dock"er rm -f x',
            "sys'temctl' restart docker",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(judged(command, declared=[]), command)

    def test_a_program_named_by_a_variable_is_guarded(self) -> None:
        for command in (
            "D=dock; ${D}er rm x",
            "$CMD rm web",
            '"$TOOL" run x',
            "$(which python) -m pytest",
        ):
            with self.subTest(command=command):
                self.assertIn("cannot read", judged(command, declared=[]) or "")

    def test_ordinary_commands_pass(self) -> None:
        self.admitted(
            "echo hello",
            "uv run pytest -q",
            "git commit -m \"$(cat <<'EOF'\nfix: don't stop the runner\nEOF\n)\"",
            "python3 - <<'EOF'\nprint(\"it's\")\nEOF",
            "for f in a b; do echo $f; done",
            "VAR=$(git rev-parse HEAD) && echo $VAR",
            "cat <<'EOF'\nliteral $(docker rm x) don't\nEOF",
            declared=[],
        )

    def test_a_heredoc_hides_nothing(self) -> None:
        self.guarded(
            "cat <<EOF\n$(docker rm -f x)\nEOF",
            "cat <<EOF\nit's `docker rm -f x`\nEOF",
            declared=[],
        )
        found = judged("echo \"$(sh <<'EOF'\ndocker rm -f x\nEOF\n)\"", declared=[])
        self.assertIn("`docker rm`", found or "")  # read in the body, not held as unreadable
        self.assertIsNone(judged("cat <<EOF\nsee <(x for $5\nEOF", declared=[]))

    def test_a_command_the_lexer_cannot_split_is_held_only_when_it_may_hide_one(self) -> None:
        self.admitted("echo \"it's", declared=[])
        for command in (
            'docker rm x; echo "',
            "dock''er rm x; echo \"",
            'D=dock; ${D}er rm x\necho "',
        ):
            with self.subTest(command=command):
                self.assertIn("cannot read", judged(command, declared=[]) or "")

    def test_a_powershell_assignment_is_no_program(self) -> None:
        for command in ("$x = Get-Item foo", "$x=Get-Item foo", "$n += 1"):
            with self.subTest(command=command):
                self.assertIsNone(judged(command, declared=[], tool="PowerShell"))
        for command in ("$x = docker rm web", "$x=docker rm web"):
            with self.subTest(command=command):
                self.assertIn("`docker rm`", judged(command, declared=[], tool="PowerShell") or "")


class HostReachedOtherwise(Case):
    """A declared host reached by Docker's endpoint, `lxc` verbs, `sftp`, `sshpass`, IPv6."""

    def test_a_docker_endpoint_on_a_declared_host_admits_only_reads(self) -> None:
        self.guarded(
            "docker -H ssh://root@vps run x",
            "docker --host ssh://vps exec web sh",
            "docker -Hssh://vps run x",
            "docker --host=ssh://vps run x",
            f"docker -H tcp://{ADDRESS}:2376 run x",
            "DOCKER_HOST=ssh://vps docker run x",
            "env DOCKER_HOST=ssh://vps docker run x",
            "export DOCKER_HOST=ssh://vps; docker run x",
            "docker --context prod run x",
            "docker -c prod run x",
            "docker --context=tcpctx run x",
            "DOCKER_CONTEXT=prod docker run x",
            "docker --context broken ps",
            "docker --context $CTX ps",
        )
        self.admitted(
            "docker -H ssh://vps ps",
            "docker --context prod logs web",
            "docker -H ssh://elsewhere run x",
            "docker run x",
            "docker --context local run x",
            "docker -H unix://vps run x",
        )
        self.assertIsNone(judged("docker ps", docker_context=lambda _name: None))

    def test_a_context_chosen_earlier_in_the_command_counts(self) -> None:
        self.guarded(
            "docker context use prod && docker run x", "docker context use prod; docker rm -f web"
        )
        self.admitted("docker context use local && docker run x", "docker context use prod")

    def test_the_current_docker_context_counts(self) -> None:
        def current_on_the_host(name: str | None) -> str | None:
            return "ssh://vps" if name is None else fake_docker_context(name)

        self.assertIsNotNone(judged("docker run x", docker_context=current_on_the_host))
        self.assertIsNotNone(judged("docker run x", docker_context=lambda _name: None))

    def test_without_the_key_no_docker_context_is_read(self) -> None:
        def never(_name: str | None) -> str | None:
            raise AssertionError("read without the key")

        self.assertIsNone(judged("docker -H ssh://vps run x", declared=[], docker_context=never))

    def test_lxc_verbs_that_reach_a_declared_instance(self) -> None:
        self.guarded(
            "lxc shell meridianre-ci",
            "lxc console meridianre-ci",
            "lxc file push build.tar meridianre-ci/root/build.tar",
            "lxc file push -p --mode 0644 x local:meridianre-ci/etc/x",
            "lxc file edit meridianre-ci/etc/hosts",
            "lxc file delete meridianre-ci/tmp/x",
        )
        self.admitted(
            "lxc file pull meridianre-ci/etc/hosts .",
            "lxc shell other",
            "lxc file push x other/root/x",
            "lxc file push --mode 0644 --uid 0 x other/root/x",
        )
        self.admitted("lxc shell meridianre-ci", declared=[])

    def test_sftp_is_scp(self) -> None:
        self.guarded(
            "sftp vps",
            f"sftp root@{ADDRESS}:/srv",
            "sftp sftp://root@vps:22/srv",
            "sftp -P 22 -o ConnectTimeout=5 vps",
            "sftp -F ./cfg elsewhere",
            "sftp $HOST",
        )
        self.admitted("sftp elsewhere", "sftp -b batch.txt elsewhere")

    def test_sshpass_is_a_wrapper(self) -> None:
        self.guarded(
            "sshpass -p secret ssh vps touch /x",
            "sshpass -psecret ssh vps touch /x",
            "sshpass -f pass.txt scp x vps:/srv",
            "sshpass -e ssh vps",
            "sshpass -p secret docker rm web",
        )
        self.admitted("sshpass -p secret ssh vps uptime")

    def test_an_ipv4_mapped_address_is_its_ipv4(self) -> None:
        self.guarded(
            f"ssh ::ffff:{ADDRESS} touch /x",
            f"ssh root@::ffff:{ADDRESS} touch /x",
            f"sftp ::ffff:{ADDRESS}",
            "ssh mapped.example touch /x",
        )
        self.admitted(f"ssh ::ffff:{ADDRESS} uptime", "sftp ::ffff:198.51.100.9")


class Services(Case):
    def test_service_and_invoke_rc_d_stop_and_restart(self) -> None:
        for command in (
            "service docker stop",
            "service docker restart",
            "sudo service nginx stop",
            "invoke-rc.d docker stop",
            "invoke-rc.d --quiet docker restart",
        ):
            with self.subTest(command=command):
                self.assertIn(
                    "docker" if "nginx" not in command else "nginx",
                    judged(command, declared=[]) or "",
                )
        self.guarded("service docker $ACTION", declared=[])
        self.admitted(
            "service docker status",
            "service --status-all",
            "invoke-rc.d docker status",
            declared=[],
        )


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
            mock.patch("guard_infra.docker_context_via_docker", lambda: fake_docker_context),
        ):
            return guarded_main(), out.getvalue(), err.getvalue()

    def test_the_docker_contexts_are_read_by_the_hook(self) -> None:
        (self.root / "docs" / "agents" / "usine.md").write_text(
            f"- `infra-hosts` : `{ADDRESS}`\n", encoding="utf-8"
        )
        event = {"tool_input": {"command": "docker --context prod run x"}, "agent_id": "a1"}
        self.assertEqual(self.run_hook(event)[0], 2)
        event = {"tool_input": {"command": "docker --context local run x"}, "agent_id": "a1"}
        self.assertEqual(self.run_hook(event)[0], 0)

    def test_a_docker_context_is_read_by_docker_context_inspect(self) -> None:
        calls: list[list[str]] = []

        def run(argv: list[str], _cwd: str | None) -> subprocess.CompletedProcess[str] | None:
            calls.append(argv)
            out = {"prod": "ssh://root@vps\n", "gone": ""}.get(argv[-1], "unix:///x.sock\n")
            return subprocess.CompletedProcess(argv, 0 if out else 1, out, "")

        endpoint = docker_context_via_docker()
        with (
            mock.patch("guard_infra.shutil.which", lambda _name: "/usr/bin/docker"),
            mock.patch("guard_infra._run", run),
        ):
            self.assertEqual(endpoint("prod"), "ssh://root@vps")
            self.assertEqual(endpoint(None), "unix:///x.sock")
            self.assertIsNone(endpoint("gone"))
        self.assertEqual(
            calls[0],
            ["/usr/bin/docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]
            + ["--", "prod"],
        )
        self.assertEqual(calls[1][-1], "{{.Endpoints.docker.Host}}")
        with (
            mock.patch("guard_infra.shutil.which", lambda _name: None),
            mock.patch("guard_infra._run", lambda *_args: self.fail("ran without docker")),
        ):
            self.assertIsNone(endpoint("prod"))
        with (
            mock.patch("guard_infra.shutil.which", lambda _name: "/usr/bin/docker"),
            mock.patch("guard_infra._run", lambda *_args: None),
        ):
            self.assertIsNone(endpoint("prod"))  # timed out

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


PrFiles = Callable[[str | None, str | None, str | None], list[str] | None]
# A reading of the files of a PR, by number, repository and directory, as the guard asks for it.
Asked = tuple[str | None, str | None, str | None]


def files(*paths: str) -> PrFiles:
    return lambda _pr, _repository, _directory: list(paths)


def unreadable(_pr: str | None, _repository: str | None, _directory: str | None) -> None:
    return None


def merge(command: str, pr_files: PrFiles, cwd: str | None = None) -> str | None:
    return refusal(command, "feat/x", always_green, cwd, pr_files=pr_files)


def recorded(
    asked: list[Asked], guarded: Callable[[Asked], bool] = lambda _asked: False
) -> PrFiles:
    """A reading that records what it is asked, and finds the guard changed where `guarded` says."""

    def reading(pr: str | None, repository: str | None, directory: str | None) -> list[str]:
        asked.append((pr, repository, directory))
        return [GUARD if guarded((pr, repository, directory)) else "README.md"]

    return reading


GUARD = "plugins/forge/hooks/guard_infra.py"


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

        def recorded(pr: str | None, repository: str | None, _directory: str | None) -> list[str]:
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

    def test_a_merge_by_the_full_url_of_the_api_is_judged_too(self) -> None:
        asked: list[tuple[str | None, str | None]] = []

        def reading(pr: str | None, repository: str | None, _directory: str | None) -> list[str]:
            asked.append((pr, repository))
            return ["plugins/forge/hooks/guard_infra.py"]

        command = "gh api -X PUT https://api.github.com/repos/o/r/pulls/5/merge"
        self.assertIsNotNone(merge(command, reading))
        self.assertEqual(asked, [("5", "o/r")])

    def test_a_wrapped_merge_is_refused(self) -> None:
        for command in (
            "env gh pr merge 5",
            "env GH_TOKEN=x gh pr merge 5",
            "command gh pr merge 5",
            "/usr/bin/gh pr merge 5",
            "gh.exe pr merge 5",
            "sudo gh pr merge 5",
            "timeout 60 gh pr merge 5",
            "bash -c 'gh pr merge 5'",
            "sh -c 'cd /x && gh pr merge 5'",
            "echo 5 | xargs gh pr merge",
            "nohup gh pr merge 5",
            "sh <<'EOF'\ngh pr merge 5\nEOF",
            "sudo env timeout 60 gh api -X PUT repos/o/r/pulls/5/merge",
        ):
            with self.subTest(command=command):
                found = merge(command, files("plugins/forge/hooks/guard_infra.py"))
                self.assertIn("only the owner merges it, by hand", found or "")
        self.assertIsNone(merge("env gh pr merge 5", files("README.md")))

    def test_the_files_are_read_where_the_merge_runs(self) -> None:
        asked: list[Asked] = []
        merge("cd ../forgeclone && gh pr merge 5 --squash", recorded(asked), cwd="/w/forge")
        self.assertEqual(asked, [("5", None, "/w/forge/../forgeclone")])
        asked.clear()
        merge("cd /w/x && sh -c 'gh pr merge 5'", recorded(asked), cwd="/w/forge")
        merge("(cd /w/y) && gh pr merge 6", recorded(asked), cwd="/w/forge")
        merge("cd /w/x && (cd /w/y) && gh pr merge 7", recorded(asked), cwd="/w/forge")
        self.assertEqual(asked, [("5", None, "/w/x"), ("6", None, "/w/forge"), ("7", None, "/w/x")])
        found = merge(
            "cd ../forgeclone && gh pr merge 5", recorded([], lambda a: "clone" in (a[2] or ""))
        )
        self.assertIn("only the owner merges it, by hand", found or "")

    def test_a_directory_the_guard_cannot_read_is_refused(self) -> None:
        for command in (
            "cd $CLONE && gh pr merge 5",
            'cd "$(git rev-parse --show-toplevel)/../x" && gh pr merge 5',
            "cd - && gh pr merge 5",
            "cd $CLONE && sh -c 'gh pr merge 5'",
        ):
            with self.subTest(command=command):
                found = merge(command, files("README.md"), cwd="/w/forge")
                self.assertIn("only the owner merges it, by hand", found or "")

    def test_the_files_are_read_in_the_repository_the_merge_names(self) -> None:
        cases: list[tuple[str, list[tuple[str | None, str | None]]]] = [
            ("GH_REPO=o/forge gh pr merge 5", [("5", "o/forge")]),
            ("env GH_REPO=o/forge gh pr merge 5", [("5", "o/forge")]),
            ("export GH_REPO=o/forge; gh pr merge 5", [("5", None), ("5", "o/forge")]),
            ("export GH_REPO=o/forge && sh -c 'gh pr merge 5'", [("5", None), ("5", "o/forge")]),
            ("gh pr merge -R o/forge 5", [("5", "o/forge")]),
            ("gh pr merge --repo=o/forge --subject x 5", [("5", "o/forge")]),
            ("GH_REPO=o/other gh pr merge -R o/forge 5", [("5", "o/forge")]),
            (
                "gh pr merge https://github.com/o/forge/pull/5",
                [("https://github.com/o/forge/pull/5", None)],
            ),
            (
                "export GH_REPO=o/other; gh pr merge https://github.com/o/forge/pull/5",
                [("https://github.com/o/forge/pull/5", None)],
            ),
            (
                "GH_REPO=o/forge gh api -X PUT repos/{owner}/{repo}/pulls/5/merge",
                [("5", "o/forge")],
            ),
        ]
        for command, expected in cases:
            with self.subTest(command=command):
                asked: list[Asked] = []
                merge(command, recorded(asked))
                self.assertEqual([(pr, repository) for pr, repository, _ in asked], expected)
                found = merge(
                    command, recorded([], lambda a: a[1] == "o/forge" or "forge" in (a[0] or ""))
                )
                self.assertIn("only the owner merges it, by hand", found or "")

    def test_a_repository_the_guard_cannot_read_is_refused(self) -> None:
        for command in (
            "GH_REPO=$R gh pr merge 5",
            "export GH_REPO=$(cat repo); gh pr merge 5",
            "gh pr merge -R $R 5",
            "gh pr merge --repo=`cat repo` 5",
        ):
            with self.subTest(command=command):
                found = merge(command, files("README.md"))
                self.assertIn("only the owner merges it, by hand", found or "")

    def test_a_number_from_the_standard_input_or_a_variable_is_refused(self) -> None:
        for command in (
            "echo 5 | xargs gh pr merge --squash",
            "echo 5 | xargs -I{} gh pr merge {} --squash",
            "cat number | gh pr merge --squash",
            "gh pr merge --squash < number",
            "gh pr merge $N",
            "gh pr merge $(cat number)",
        ):
            with self.subTest(command=command):
                found = merge(command, files("README.md"))
                self.assertIn("only the owner merges it, by hand", found or "")
        for command in (
            "gh pr merge 5 --squash | tee log",
            "gh pr merge --squash",
            'gh pr merge --subject "$TITLE" 5',
            "echo ok | grep ok; gh pr merge 5",
        ):
            with self.subTest(command=command):
                self.assertIsNone(merge(command, files("README.md")))

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
                    pr_files_via_gh(folder)("5", "ikoro-labs/forge", None),
                    ["view 5 -R ikoro-labs/forge --json files"],
                )
                with tempfile.TemporaryDirectory() as event_folder:
                    # gh runs in the directory of the merge, not in the event's.
                    self.assertEqual(
                        pr_files_via_gh(event_folder)("6", None, folder),
                        ["view 6 --json files"],
                    )
            (Path(folder) / "pr").write_text("import sys; sys.exit(1)\n", encoding="utf-8")
            with mock.patch("shutil.which", lambda _name: sys.executable):
                self.assertIsNone(pr_files_via_gh(folder)("5", None, None))
        with mock.patch("shutil.which", lambda _name: None):
            self.assertIsNone(pr_files_via_gh(None)("5", None, None))

    def test_the_hook_reads_the_files_of_the_pr_it_merges(self) -> None:
        def run_hook(
            pr_files: PrFiles,
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
