"""Ticket #66: `bounded_run.py` runs any test command under a memory limit, a delay and the budget of the post.

Every test names its ticket and its point (`No F-NNNN: ticket #66, critère N`), the ticket having no
feature. The bounds the tests set are tiny (tens of MB, a few seconds) and none reads an endless source.
"""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
import bounded_run

SCRIPT = support.PLUGIN / "scripts" / "bounded_run.py"

# Distinct exit codes of the launcher, documented in the script: a command's own code never hides them.
BUDGET, WRONG_CALL, REFUSED, MEMORY, DELAY, NOT_FOUND = 120, 121, 122, 123, 124, 127


class Runner:
    """Runs the launcher in a throwaway folder, isolated from the real HOME and the session's variables."""

    def __init__(self, test: unittest.TestCase) -> None:
        folder = tempfile.TemporaryDirectory()
        test.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "HOME": str(self.root),
            "USERPROFILE": str(self.root),
            "TMPDIR": str(self.root),
            "TEMP": str(self.root),
            "TMP": str(self.root),
        }

    def usine(self, text: str) -> str:
        path = self.root / "usine.md"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def run(self, *options: str, command: list[str] | None = None) -> subprocess.CompletedProcess:
        tail = ["--", *command] if command is not None else []
        return subprocess.run(
            [sys.executable, str(SCRIPT), *options, *tail],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=60,
        )


def python(source: str, *args: str) -> list[str]:
    return [sys.executable, "-c", source, *args]


class ExitCode(unittest.TestCase):
    def test_a_command_that_passes_returns_its_own_code(self) -> None:
        """No F-NNNN: ticket #66, critère 1: la commande qui passe rend son code, 0 comme un code non nul."""
        runner = Runner(self)
        limits = ("--memory-mb", "400", "--timeout", "20")
        passing = runner.run(*limits, command=python("print('vert')"))
        self.assertEqual(passing.returncode, 0, passing.stderr)
        self.assertIn("vert", passing.stdout)
        failing = runner.run(*limits, command=python("import sys; sys.exit(3)"))
        self.assertEqual(failing.returncode, 3, failing.stderr)

    @unittest.skipIf(os.name == "nt", "a signal exit code is a POSIX notion")
    def test_a_command_killed_by_a_signal_gives_128_plus_the_signal(self) -> None:
        """No F-NNNN: ticket #66, critère 1: un signal se rend comme un shell le rend, 128 plus le signal."""
        runner = Runner(self)
        done = runner.run(
            "--memory-mb", "400", "--timeout", "20",
            command=python("import os, signal; os.kill(os.getpid(), signal.SIGKILL)"),
        )
        self.assertEqual(done.returncode, 137, done.stderr)


class Bounds(unittest.TestCase):
    def test_a_command_over_its_delay_gets_the_delay_code_and_a_reason(self) -> None:
        """No F-NNNN: ticket #66, critère 2: le délai dépassé tue la commande, code distinct, raison sur stderr."""
        runner = Runner(self)
        done = runner.run("--memory-mb", "400", "--timeout", "2", command=python("import time; time.sleep(60)"))
        self.assertEqual(done.returncode, DELAY, done.stderr)
        self.assertIn("délai de 2 s dépassé", done.stderr)

    @unittest.skipUnless(
        sys.platform == "linux" or os.name == "nt",
        "the memory limit is set with RLIMIT_AS on Linux and a job object on Windows; macOS is not covered",
    )
    def test_a_command_over_its_memory_limit_gets_the_memory_code_and_a_reason(self) -> None:
        """No F-NNNN: ticket #66, critère 2: la mémoire dépassée donne un code distinct et sa raison sur stderr."""
        runner = Runner(self)
        # Tiny on Linux (the allocation fails, nothing is committed); a Windows Python needs more to start.
        limit, asked = ("64", 200) if sys.platform == "linux" else ("300", 800)
        done = runner.run(
            "--memory-mb", limit, "--timeout", "20", command=python(f"bytearray({asked} * 10**6)"),
        )
        self.assertEqual(done.returncode, MEMORY, done.stderr)
        self.assertIn("mémoire", done.stderr.splitlines()[-1])
        self.assertIn("MemoryError", done.stderr)  # the command's own error is still shown

    @unittest.skipUnless(
        sys.platform == "linux",
        "an impossible RLIMIT_AS is built by overflowing it; the Windows refusal is seen in CI only, never forced here",
    )
    def test_a_bound_that_cannot_be_set_refuses_to_run(self) -> None:
        """No F-NNNN: ticket #66, critère 3: une borne impossible à poser refuse de lancer, la commande ne tourne pas."""
        import resource

        if resource.getrlimit(resource.RLIMIT_AS)[1] != resource.RLIM_INFINITY:
            self.skipTest("the session's own limit caps the huge value instead of refusing it")
        runner = Runner(self)
        marker = runner.root / "ran"
        source = f"open({str(marker)!r}, 'w').close()"
        # 10**15 MB is past 2**64 bytes, the largest limit setrlimit takes: it overflows.
        done = runner.run("--memory-mb", str(10**15), "--timeout", "20", command=python(source))
        self.assertEqual(done.returncode, REFUSED, done.stderr)
        self.assertIn("limite non posée", done.stderr)
        self.assertFalse(marker.exists(), "the command ran without its bound")

    def test_a_command_that_does_not_exist_gets_the_not_found_code(self) -> None:
        """No F-NNNN: ticket #66, critère 1: une commande introuvable se dit, sans passer pour une borne."""
        runner = Runner(self)
        done = runner.run("--memory-mb", "400", "--timeout", "20", command=["no-such-command-forge-66"])
        self.assertEqual(done.returncode, NOT_FOUND, done.stderr)
        self.assertIn("no-such-command-forge-66", done.stderr)


class Limits(unittest.TestCase):
    def test_the_key_run_limits_gives_the_memory_and_the_delay(self) -> None:
        """No F-NNNN: ticket #66, critère 4: la clé run-limits pose mémoire et délai, sans option."""
        runner = Runner(self)
        usine = runner.usine("- `run-limits` : `400 | 2`\n")
        slept = runner.run("--usine", usine, command=python("import time; time.sleep(60)"))
        self.assertEqual(slept.returncode, DELAY, slept.stderr)
        self.assertIn("délai de 2 s dépassé", slept.stderr)
        fine = runner.run("--usine", usine, command=python("print('vert')"))
        self.assertEqual(fine.returncode, 0, fine.stderr)

    def test_an_option_wins_over_the_key(self) -> None:
        """No F-NNNN: ticket #66, critère 4: une option passe avant la clé."""
        runner = Runner(self)
        usine = runner.usine("- `run-limits` : `400 | 60`\n")
        done = runner.run(
            "--usine", usine, "--timeout", "2", command=python("import time; time.sleep(30)"),
        )
        self.assertEqual(done.returncode, DELAY, done.stderr)

    def test_without_the_key_both_options_are_required(self) -> None:
        """No F-NNNN: ticket #66, critère 4: sans clé run-limits, le lanceur exige ses deux options et la nomme."""
        runner = Runner(self)
        usine = runner.usine("- `ci-replay` : `autre`\n")
        for options in ([], ["--memory-mb", "400"], ["--timeout", "20"]):
            with self.subTest(options=options):
                done = runner.run("--usine", usine, *options, command=python("print('vert')"))
                self.assertEqual(done.returncode, WRONG_CALL, done.stderr)
                self.assertIn("clé `run-limits` absente", done.stderr)
                self.assertNotIn("vert", done.stdout)

    def test_a_malformed_key_or_a_non_positive_option_is_a_wrong_call(self) -> None:
        """No F-NNNN: ticket #66, critère 4: une valeur invalide est un appel faux, jamais une borne devinée."""
        runner = Runner(self)
        for text in ("- `run-limits` : `400`\n", "- `run-limits` : `beaucoup | 300`\n", "- `run-limits` : `0 | 300`\n"):
            with self.subTest(text=text):
                done = runner.run("--usine", runner.usine(text), command=python("print('vert')"))
                self.assertEqual(done.returncode, WRONG_CALL, done.stderr)
                self.assertIn("run-limits", done.stderr)
        done = runner.run("--memory-mb", "0", "--timeout", "20", command=python("print('vert')"))
        self.assertEqual(done.returncode, WRONG_CALL, done.stderr)


class Budget(unittest.TestCase):
    """Ticket #66, décision du 2026-11-15: the budget of the whole post, read before each launch."""

    def refuse(self, state: tuple[int | None, float | None], *options: str) -> tuple[int, str, bool]:
        """The launcher called in-process with the post in `state` (the only thing faked: the post).

        Returns its exit code, its stderr, and whether the command it was given ran."""
        runner = Runner(self)
        marker = runner.root / "ran"
        source = f"open({str(marker)!r}, 'w').close()"
        err = io.StringIO()
        with mock.patch.object(bounded_run, "system_state", return_value=state), contextlib.redirect_stderr(err):
            code = bounded_run.main(
                ["--memory-mb", "400", "--timeout", "20", "--min-available-mb", "4096", "--max-load", "12",
                 "--max-workers", "2", "--wait", "0", *options, "--", *python(source)]
            )
        return code, err.getvalue(), marker.exists()

    def test_available_memory_under_the_threshold_refuses_to_run(self) -> None:
        """No F-NNNN: ticket #66, critère 6: MemAvailable sous le seuil, le lanceur n'attend plus et ne lance pas."""
        code, stderr, ran = self.refuse((1000, 0.5))
        self.assertEqual(code, BUDGET, stderr)
        self.assertIn("MemAvailable 1000 Mo", stderr)
        self.assertIn("4096 Mo", stderr)
        self.assertFalse(ran, "the command ran with the post out of budget")

    def test_a_load_over_the_threshold_refuses_to_run(self) -> None:
        """No F-NNNN: ticket #66, critère 6: une charge à 1 min au-dessus du seuil refuse de lancer."""
        code, stderr, ran = self.refuse((9000, 35.0))
        self.assertEqual(code, BUDGET, stderr)
        self.assertIn("charge à 1 min 35.0", stderr)
        self.assertIn("12", stderr)
        self.assertFalse(ran)

    def test_an_unreadable_memory_refuses_to_run(self) -> None:
        """No F-NNNN: ticket #66, critère 6: une mémoire illisible refuse, jamais un budget supposé tenu."""
        code, stderr, ran = self.refuse((None, 0.5))
        self.assertEqual(code, BUDGET, stderr)
        self.assertIn("illisible", stderr)
        self.assertFalse(ran)

    def test_a_post_within_the_budget_runs_the_command(self) -> None:
        """No F-NNNN: ticket #66, critère 6: mémoire au seuil et charge au seuil, la commande tourne."""
        code, stderr, ran = self.refuse((4096, 12.0))
        self.assertEqual(code, 0, stderr)
        self.assertTrue(ran)

    def test_a_post_without_a_load_average_is_judged_on_its_memory(self) -> None:
        """No F-NNNN: ticket #66, critère 6: sans charge à 1 min (Windows), la mémoire juge seule, et le dit."""
        code, stderr, ran = self.refuse((9000, None))
        self.assertEqual(code, 0, stderr)
        self.assertIn("charge à 1 min : sans objet", stderr)
        self.assertTrue(ran)

    def test_it_waits_for_the_post_then_launches(self) -> None:
        """No F-NNNN: ticket #66, critère 6: hors seuil, le lanceur attend, puis lance quand le poste redescend."""
        states = iter([(1000, 40.0), (2000, 20.0), (8000, 3.0)])
        clock = [0.0]
        slept: list[float] = []

        def sleep(seconds: float) -> None:
            slept.append(seconds)
            clock[0] += seconds

        budget = bounded_run.Budget(min_available_mb=4096, max_load=12.0, max_workers=2, wait=600)
        unmet = bounded_run.wait_for_budget(
            budget, state=lambda: next(states), sleep=sleep, now=lambda: clock[0],
        )
        self.assertEqual(unmet, [])
        self.assertEqual(len(slept), 2)

    def test_it_gives_up_when_the_wait_is_over(self) -> None:
        """No F-NNNN: ticket #66, critère 6: à la fin de l'attente, le lanceur rend les raisons et ne lance rien."""
        clock = [0.0]

        def sleep(seconds: float) -> None:
            clock[0] += seconds

        budget = bounded_run.Budget(min_available_mb=4096, max_load=12.0, max_workers=2, wait=60)
        unmet = bounded_run.wait_for_budget(
            budget, state=lambda: (1000, 40.0), sleep=sleep, now=lambda: clock[0],
        )
        self.assertEqual(len(unmet), 2)
        self.assertGreaterEqual(clock[0], 60)

    def test_the_budget_is_declared_in_the_key_run_budget(self) -> None:
        """No F-NNNN: ticket #66, critère 6: la clé run-budget porte les quatre seuils, sans valeur par défaut."""
        runner = Runner(self)
        text = "- `run-limits` : `400 | 20`\n- `run-budget` : `1 | 100000 | 2 | 0`\n"
        done = runner.run("--usine", runner.usine(text), command=python("print('vert')"))
        self.assertEqual(done.returncode, 0, done.stderr)
        # Memory the post cannot have: the key is read, the budget applies, nothing runs.
        text = text.replace("`1 |", f"`{10**9} |")
        done = runner.run("--usine", runner.usine(text), command=python("print('vert')"))
        self.assertEqual(done.returncode, BUDGET, done.stderr)
        self.assertNotIn("vert", done.stdout)

    def test_a_partial_or_malformed_budget_is_a_wrong_call(self) -> None:
        """No F-NNNN: ticket #66, critère 6: un budget à moitié dit ou invalide est un appel faux."""
        runner = Runner(self)
        for text in ("- `run-budget` : `4096 | 12`\n", "- `run-budget` : `4096 | haute | 2 | 60`\n"):
            with self.subTest(text=text):
                usine = runner.usine("- `run-limits` : `400 | 20`\n" + text)
                done = runner.run("--usine", usine, command=python("print('vert')"))
                self.assertEqual(done.returncode, WRONG_CALL, done.stderr)
                self.assertIn("run-budget", done.stderr)

    def test_without_the_key_the_budget_is_sans_objet_and_the_command_runs(self) -> None:
        """No F-NNNN: ticket #66, critère 6: sans clé run-budget, l'étape est sans objet et dite, aucun seuil deviné."""
        runner = Runner(self)
        done = runner.run("--usine", runner.usine("- `run-limits` : `400 | 20`\n"), command=python("print('vert')"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("sans objet (clé `run-budget` absente)", done.stderr)

    def test_check_alone_reads_the_budget_and_launches_nothing(self) -> None:
        """No F-NNNN: ticket #66, critère 6: --check lit le budget avant un sous-agent, sans commande."""
        runner = Runner(self)
        usine = runner.usine("- `run-budget` : `1 | 100000 | 2 | 0`\n")
        self.assertEqual(runner.run("--usine", usine, "--check").returncode, 0)
        greedy = runner.usine(f"- `run-budget` : `{10**9} | 100000 | 2 | 0`\n")
        done = runner.run("--usine", greedy, "--check")
        self.assertEqual(done.returncode, BUDGET, done.stderr)


class Workers(unittest.TestCase):
    """Ticket #66, décision du 2026-11-15: the workers of pytest-xdist are brought down to the ceiling."""

    def test_a_count_over_the_ceiling_and_auto_are_brought_to_it(self) -> None:
        """No F-NNNN: ticket #66, critère 7: -n 6 et -n auto sont ramenés à 2, sous toutes leurs formes."""
        for before, after in [
            (["pytest", "-n", "6"], ["pytest", "-n", "2"]),
            (["pytest", "-n", "auto"], ["pytest", "-n", "2"]),
            (["pytest", "-n", "logical"], ["pytest", "-n", "2"]),
            (["pytest", "-n6"], ["pytest", "-n2"]),
            (["pytest", "-nauto"], ["pytest", "-n2"]),
            (["pytest", "--numprocesses", "6"], ["pytest", "--numprocesses", "2"]),
            (["pytest", "--numprocesses=auto"], ["pytest", "--numprocesses=2"]),
            (["uv", "run", "pytest", "tests", "-n", "8", "-q"], ["uv", "run", "pytest", "tests", "-n", "2", "-q"]),
            (["python", "-m", "pytest", "-n", "6"], ["python", "-m", "pytest", "-n", "2"]),
        ]:
            with self.subTest(before=before):
                self.assertEqual(bounded_run.clamp_workers(before, 2), after)

    def test_a_count_within_the_ceiling_and_other_commands_are_left_alone(self) -> None:
        """No F-NNNN: ticket #66, critère 7: -n 1, -n 2 et -n 0 restent ; `head -n 5` n'est pas un pytest."""
        for argv in (
            ["pytest", "-n", "1"], ["pytest", "-n", "2"], ["pytest", "-n", "0"], ["pytest", "-q"],
            ["head", "-n", "5", "file"], ["tail", "-n", "100"], ["python", "-m", "unittest", "-n"],
        ):
            with self.subTest(argv=argv):
                self.assertEqual(bounded_run.clamp_workers(argv, 2), argv)

    def test_the_command_that_runs_gets_the_ceiling(self) -> None:
        """No F-NNNN: ticket #66, critère 7: la commande lancée reçoit -n 2, pour -n 6 comme pour -n auto."""
        runner = Runner(self)
        usine = runner.usine("- `run-limits` : `400 | 20`\n- `run-budget` : `1 | 100000 | 2 | 0`\n")
        for asked in ("6", "auto"):
            with self.subTest(asked=asked):
                # The command only echoes its arguments: the word `pytest` makes it count as a pytest run.
                done = runner.run(
                    "--usine", usine, command=python("import sys; print(sys.argv[1:])", "pytest", "-n", asked),
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertIn("['pytest', '-n', '2']", done.stdout)
                self.assertIn("ramenés à 2", done.stderr)


class SharedBound(unittest.TestCase):
    def test_base_replay_holds_its_commands_with_the_same_bound(self) -> None:
        """No F-NNNN: ticket #66, critère 5: la borne de base_replay est celle du lanceur, une seule fonction."""
        replay = (support.PLUGIN / "scripts" / "base_replay.py").read_text(encoding="utf-8")
        self.assertNotIn("setrlimit", replay, "base_replay sets its own limit instead of sharing run_bounded")
        self.assertIn("from bounded_run import", replay)
        self.assertIn("setrlimit", SCRIPT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
