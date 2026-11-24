"""Ticket #155: the dependency age probe is documented, run by the gate and judged by `forge:qc-conf`."""

import unittest

import support


def read(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


def read_root(*parts: str) -> str:
    return " ".join(support.REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8").split())


class TemplateDocumentsTheKeys(unittest.TestCase):
    def test_lockfile_is_one_path_per_line_with_its_ecosystem(self) -> None:
        """Ticket #155: the key is `<path> | <ecosystem>`, `pypi` reads a uv.lock, `npm` a package-lock.json."""
        template = read("templates", "usine.md")
        self.assertIn("`lockfile` : `<", template)
        self.assertIn("<chemin> | <écosystème>", template)
        for text in ("`pypi`", "`npm`", "uv.lock", "package-lock.json", "clé `lockfile` absente"):
            self.assertIn(text, template)

    def test_the_threshold_key_has_no_default_and_counts_days(self) -> None:
        """Ticket #155: `dependency-min-age` is a number of days, with no default value."""
        template = read("templates", "usine.md")
        self.assertIn("`dependency-min-age` : `<", template)
        section = template[template.index("`dependency-min-age`"):]
        self.assertIn("jours", section[:1500])
        self.assertIn("aucune valeur par défaut", template)
        self.assertIn("clé `dependency-min-age` absente", template)

    def test_the_template_says_the_probe_reaches_the_network_and_what_an_unreachable_registry_gives(self) -> None:
        """Ticket #155: public registries are read over the network, a silent one is `NOT RUN`."""
        template = read("templates", "usine.md")
        section = template[template.index("`lockfile`"):]
        for text in ("réseau", "registre", "`NOT RUN`", "jamais `PASS`", "scripts/lockfile_age.py"):
            self.assertIn(text, section)


class GateRunsTheProbe(unittest.TestCase):
    def test_the_gate_runs_the_script_on_the_refs_with_the_keys_of_the_base(self) -> None:
        """Ticket #155: the threshold comes from the base, so a PR cannot lower the one it is judged by."""
        gate = read("agents", "qc-gate.md")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/lockfile_age.py", gate)
        self.assertIn("--base origin/<base>", gate)
        self.assertIn("--head <tête>", gate)
        self.assertIn("--usine usine-base.md", gate)

    def test_the_gate_says_what_it_renders_for_each_outcome(self) -> None:
        """Ticket #155: absent key, registry that does not answer, and a probe it does not judge."""
        gate = read("agents", "qc-gate.md")
        section = gate[gate.index("**Âge des dépendances.**"):]
        section = section[: section.index("Aux tours 2 et 3")]
        for text in (
            "sans objet (clé lockfile absente)", "sans objet (clé dependency-min-age absente)",
            "`NOT RUN`", "jamais `PASS`", "`YOUNG`", "`NOT FOUND`", "verbatim", "réseau",
        ):
            self.assertIn(text, section)

    def test_the_verbatim_list_of_the_output_names_the_probe(self) -> None:
        """Ticket #155: the table's verbatim lines include the probe, or `forge:qc-conf` never sees them."""
        gate = read("agents", "qc-gate.md")
        tail = gate[gate.index("## Sortie"):]
        self.assertRegex(tail, r"sondes 2, 5, 6, 7, 10, 11, 12, 13, 14, 15, 16 et 17")


class JudgeReadsTheProbe(unittest.TestCase):
    def test_a_young_or_unknown_package_is_a_blocker_under_a_socle_rule(self) -> None:
        """Ticket #155: `YOUNG` and `NOT FOUND` are `BLOCKER`, and the finding cites a rule id."""
        judge = read("agents", "qc-conf.md")
        section = judge[judge.index("## Âge des dépendances"):]
        section = section[: section.index("\n## ") if "\n## " in section else None]
        for text in ("`YOUNG`", "`NOT FOUND`", "`BLOCKER`", "`F-27`", "dependency-age"):
            self.assertIn(text, section)
        socle = read("socle.md")
        self.assertRegex(socle, r"\| F-27 \| code \|.*lockfile_age\.py")

    def test_a_probe_that_did_not_run_is_said_in_gates_and_never_read_as_none(self) -> None:
        """Ticket #155: `NOT RUN` and `INVALID` go to `GATES`; a missing key is `sans objet`."""
        judge = read("agents", "qc-conf.md")
        section = judge[judge.index("## Âge des dépendances"):]
        for text in ("`NOT RUN`", "`INVALID`", "dependency-age : sans objet", "jamais lue comme « aucune »"):
            self.assertIn(text, section)

    def test_a_source_outside_the_registry_is_judged_on_the_provenance_rule(self) -> None:
        """Ticket #155: `NOT CHECKED` is not dated, so the PR's provenance line (F-8) is what is read."""
        judge = read("agents", "qc-conf.md")
        section = judge[judge.index("## Âge des dépendances"):]
        self.assertIn("`NOT CHECKED`", section)
        self.assertIn("`F-8`", section)


class ProjectPages(unittest.TestCase):
    def test_the_configuration_page_describes_the_probe_the_keys_and_what_was_tried(self) -> None:
        """Ticket #155: `docs/installation.md` says it reads the network and what was not tried."""
        page = read_root("docs", "installation.md")
        self.assertIn("lockfile_age.py", page)
        for text in ("`lockfile`", "`dependency-min-age`", "pypi.org", "registry.npmjs.org", "`NOT RUN`"):
            self.assertIn(text, page)
        paragraph = page[page.index("lockfile_age.py"):]
        self.assertRegex(paragraph[:3000], r"(?i)éprouvé")

    def test_the_readme_summarises_it_and_points_to_the_page(self) -> None:
        readme = read_root("README.md")
        self.assertIn("`dependency-min-age`", readme)


if __name__ == "__main__":
    unittest.main()
