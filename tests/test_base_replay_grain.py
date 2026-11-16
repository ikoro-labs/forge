"""Ticket #43, grain du test : `base_replay.py` rend chaque test ajouté ou changé qui passe sur la base.

La commande `red-replay` porte `{report}` : le script lit alors le rapport JUnit XML qu'elle y écrit,
repère les tests que la PR ajoute ou change par les lignes du diff, et juge chacun seul.
"""

import sys
import unittest

import support
from test_base_replay import Repo

# A stand-in for a project's runner with a JUnit writer (the standard library has none for unittest).
RUNNER = '''\
import sys
import unittest
import xml.etree.ElementTree as ET

path, report = sys.argv[1], sys.argv[2]
suite = unittest.defaultTestLoader.discover("tests", pattern=path.rsplit("/", 1)[-1], top_level_dir=".")
root = ET.Element("testsuite")


def case(test):
    return ET.SubElement(
        root, "testcase", classname=type(test).__module__ + "." + type(test).__name__, name=test._testMethodName
    )


def walk(tests):
    for item in tests:
        if isinstance(item, unittest.TestSuite):
            yield from walk(item)
        else:
            yield item


every = list(walk(suite))  # a suite empties itself while it runs
result = unittest.TestResult()
suite.run(result)
bad = {}
for test, _ in result.failures + result.errors:
    bad[id(test)] = "failure"
for test, _ in result.skipped:
    bad[id(test)] = "skipped"
for test in every:
    element = case(test)
    if id(test) in bad:
        ET.SubElement(element, bad[id(test)])
ET.ElementTree(root).write(report)
sys.exit(0 if result.wasSuccessful() else 1)
'''
CODE_V2 = "def value():\n    return 2\n\n\ndef other():\n    return 10\n"
CODE_BASE = "def value():\n    return 1\n\n\ndef other():\n    return 10\n"
HEADER = "import unittest\nimport code_under_test\n\n\nclass T(unittest.TestCase):\n"
OLD = "    def test_old(self):\n        self.assertEqual(code_under_test.other(), 10)\n\n"
KEPT = "    def test_kept(self):\n        self.assertEqual(code_under_test.other(), 10)\n\n"
NEW_RED = "    def test_new_red(self):\n        self.assertEqual(code_under_test.value(), 2)\n\n"
NEW_GREEN = "    def test_new_green(self):\n        self.assertEqual(code_under_test.other(), 10)\n\n"
REPORT_REPLAY = f'"{sys.executable}" junit_runner.py {{file}} {{report}}'


def usine(replay: str = REPORT_REPLAY) -> str:
    return f"- `test-path` : `tests/`\n- `red-replay` : `{replay}`\n"


def module(*parts: str) -> str:
    return (HEADER + "".join(parts)).rstrip("\n") + "\n"


def base_repo(test: unittest.TestCase, text: str | None = None) -> tuple[Repo, str]:
    repo = Repo(test)
    base = repo.commit(
        {
            "code_under_test.py": CODE_BASE,
            "tests/__init__.py": "",
            "junit_runner.py": RUNNER,
            "tests/test_mod.py": text if text is not None else module(OLD),
        }
    )
    return repo, base


class TestGrain(unittest.TestCase):
    def test_a_passing_added_test_is_rendered_beside_a_red_one(self) -> None:
        """No F-NNNN: ticket #43, grain du test: un test ajouté qui passe est rendu, son voisin rouge ne l'est pas."""
        repo, base = base_repo(self)
        head = repo.commit({"code_under_test.py": CODE_V2, "tests/test_mod.py": module(OLD, NEW_RED, NEW_GREEN)})
        done = repo.replay(base, head, usine())
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^PASSES\ttests/test_mod\.py::tests\.test_mod\.T\.test_new_green\t")
        self.assertNotIn("test_new_red\t", done.stdout)
        self.assertRegex(
            done.stdout, r"(?m)^RED\ttests/test_mod\.py\t1 test\(s\) rouge\(s\) sur 2 ajouté\(s\) ou changé\(s\)"
        )

    def test_an_unchanged_test_that_passes_is_not_rendered(self) -> None:
        """No F-NNNN: ticket #43, grain du test: un test que la PR ne touche pas n'est pas rendu."""
        repo, base = base_repo(self)
        head = repo.commit({"code_under_test.py": CODE_V2, "tests/test_mod.py": module(OLD, NEW_RED, NEW_GREEN)})
        done = repo.replay(base, head, usine())
        self.assertNotIn("test_old", done.stdout)

    def test_a_changed_test_that_passes_on_the_base_is_rendered(self) -> None:
        """No F-NNNN: ticket #43, grain du test: un test dont le corps change et qui passe sur la base est rendu."""
        repo, base = base_repo(self, module(OLD, KEPT))
        changed = OLD.replace("10)", "10)\n        self.assertTrue(True)")
        head = repo.commit({"tests/test_mod.py": module(changed, KEPT)})
        done = repo.replay(base, head, usine())
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^PASSES\ttests/test_mod\.py::tests\.test_mod\.T\.test_old\t")
        self.assertNotIn("test_kept", done.stdout)

    def test_every_added_test_red_gives_one_red_line_and_exit_zero(self) -> None:
        """No F-NNNN: ticket #43, grain du test: tous les tests ajoutés rouges, une ligne RED qui dit le grain."""
        repo, base = base_repo(self)
        head = repo.commit({"code_under_test.py": CODE_V2, "tests/test_mod.py": module(OLD, NEW_RED)})
        done = repo.replay(base, head, usine())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("PASSES", done.stdout)
        self.assertRegex(
            done.stdout,
            r"(?m)^RED\ttests/test_mod\.py\t1 test\(s\) rouge\(s\) sur 1 ajouté\(s\) ou changé\(s\) \(grain du test\)",
        )

    def test_a_new_file_is_all_added(self) -> None:
        """No F-NNNN: ticket #43, grain du test: dans un fichier ajouté, chaque test est ajouté."""
        repo, base = base_repo(self)
        head = repo.commit({"code_under_test.py": CODE_V2, "tests/test_fresh.py": module(NEW_RED, NEW_GREEN)})
        done = repo.replay(base, head, usine())
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^PASSES\ttests/test_fresh\.py::tests\.test_fresh\.T\.test_new_green\t")
        self.assertNotIn("test_new_red\t", done.stdout)

    def test_a_changed_file_with_no_test_touched_says_so(self) -> None:
        """No F-NNNN: ticket #43, grain du test: un fichier changé hors de ses tests ne rend rien."""
        repo, base = base_repo(self)
        head = repo.commit({"tests/test_mod.py": "# a comment above the tests\n" + module(OLD)})
        done = repo.replay(base, head, usine())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("PASSES", done.stdout)
        self.assertRegex(done.stdout, r"(?m)^NONE\ttests/test_mod\.py\taucun test ajouté ou changé dans ce fichier")

    def test_a_skipped_test_is_not_a_pass_and_not_a_failure(self) -> None:
        """No F-NNNN: ticket #43, grain du test: un test ignoré sur la base est dit SKIPPED, sans effet sur le code."""
        skipped = "    @unittest.skip('later')\n    def test_new_skipped(self):\n        self.assertTrue(True)\n\n"
        repo, base = base_repo(self)
        head = repo.commit({"tests/test_mod.py": module(OLD, skipped)})
        done = repo.replay(base, head, usine())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^SKIPPED\ttests/test_mod\.py::tests\.test_mod\.T\.test_new_skipped\t")
        self.assertNotIn("PASSES", done.stdout)


class ReportNotUsable(unittest.TestCase):
    def fixture(self) -> tuple[Repo, str, str]:
        repo, base = base_repo(self)
        head = repo.commit({"tests/test_mod.py": module(OLD, NEW_GREEN)})
        return repo, base, head

    def test_a_command_exiting_zero_without_a_report_is_not_run(self) -> None:
        """No F-NNNN: ticket #43, grain du test: sans rapport après une sortie 0, la sonde est NOT RUN, jamais PASS."""
        command = f'"{sys.executable}" -c "pass" {{file}} {{report}}'
        repo, base, head = self.fixture()
        done = repo.replay(base, head, usine(command))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^NOT RUN\ttests/test_mod\.py\t.*rapport")
        self.assertNotIn("PASSES", done.stdout)

    def test_a_command_failing_without_a_report_is_red_at_the_grain_of_the_file(self) -> None:
        """No F-NNNN: ticket #43, grain du test: un fichier qui échoue avant ses tests est RED au grain du fichier."""
        command = f'"{sys.executable}" -c "import sys; sys.exit(3)" {{file}} {{report}}'
        repo, base, head = self.fixture()
        done = repo.replay(base, head, usine(command))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^RED\ttests/test_mod\.py\tcode 3 \(grain du fichier")

    def test_a_report_with_a_doctype_is_not_read(self) -> None:
        """No F-NNNN: ticket #43, grain du test: un rapport à entité déclarée est refusé, la sonde est NOT RUN."""
        source = "import sys; open(sys.argv[2], 'w').write('<!DOCTYPE x [<!ENTITY a 1>]><testsuite/>')"
        command = f'"{sys.executable}" -c "{source}" {{file}} {{report}}'
        repo, base, head = self.fixture()
        done = repo.replay(base, head, usine(command))
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertRegex(done.stdout, r"(?m)^NOT RUN\ttests/test_mod\.py\t.*DOCTYPE")


class LocatingTheTestsAPrChanged(unittest.TestCase):
    def test_a_parametrized_name_is_found_by_its_bare_name(self) -> None:
        """No F-NNNN: ticket #43, grain du test: `test_x[1]` se repère à `test_x`, dans le texte de la tête."""
        import junit_report

        text = "import pytest\n\n\ndef test_a():\n    pass\n\n\ndef test_x(n):\n    assert n\n"
        cases = [junit_report.Case("m", "test_a", "pass"), junit_report.Case("m", "test_x[1]", "pass")]
        touched = junit_report.touched(cases, text, [range(9, 10)])
        self.assertEqual([case.name for case in touched], ["test_x[1]"])


class GrainIsDocumented(unittest.TestCase):
    """The consumers read the placeholder and the limits of the reading in the template, the page and the agents."""

    @staticmethod
    def read(*parts: str) -> str:
        return " ".join(support.REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8").split())

    def test_the_template_and_the_page_document_report_without_a_new_key(self) -> None:
        """No F-NNNN: ticket #43, grain du test: `{report}` est documenté dans le gabarit et la page, sans clé de plus."""
        template = self.read("plugins", "forge", "templates", "usine.md")
        self.assertIn("`{report}`, facultatif et sans clé de plus", template)
        self.assertIn("--junitxml={report}", template)
        self.assertIn("jamais `PASSES`", template)
        page = self.read("docs", "installation.md")
        self.assertIn("`{report}`", page)
        self.assertIn("junit_report.py", page)
        self.assertIn("un test qu'il ne place pas compte comme changé", page)
        self.assertIn("n'a pas été rejoué de bout en bout", page)

    def test_the_gate_and_the_judge_read_the_grain_of_the_test(self) -> None:
        """No F-NNNN: ticket #43, grain du test: la sonde et le juge lisent les lignes `(grain du test)`."""
        gate = self.read("plugins", "forge", "agents", "qc-gate.md")
        section = gate[gate.index("**Rejeu des tests sur la base.**"):]
        self.assertIn("**grain du test**", section)
        self.assertIn("`<fichier>::<test>`", section)
        self.assertIn("`SKIPPED`", section)
        conf = self.read("plugins", "forge", "agents", "qc-conf.md")
        section = conf[conf.index("## Lecture du rejeu sur la base"):]
        self.assertIn("`(grain du test)`", section)
        self.assertIn("une ligne `NONE` ne prouve pas", section)

    def test_the_script_names_the_placeholder_and_the_limits_of_the_reading(self) -> None:
        """No F-NNNN: ticket #43, grain du test: le script dit `{report}` et les limites du repérage."""
        script = self.read("plugins", "forge", "scripts", "base_replay.py")
        self.assertIn("{report}", script)
        self.assertIn("a reading of the text", script)
        helper = self.read("plugins", "forge", "scripts", "junit_report.py")
        self.assertIn("not of the language", helper)


if __name__ == "__main__":
    unittest.main()
