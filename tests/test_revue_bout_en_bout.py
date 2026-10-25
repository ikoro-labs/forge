"""Ticket #100: la revue de bout en bout d'une feature, jugée contre la source sur des captures réelles."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import support
from revue_bout_en_bout import main

PARCOURS = """# F-0000 : parcours

## Écran 1 : Liste

- Voit : « Compteurs » ; « Saisir »
- Fait : choisit un compteur
- Suivant : Écran 2
- Source : EXI-01

## Écran 2 : Saisie

- Voit : « Index (m3) »
- Fait : saisit l'index
- Suivant : fin
- Source : EXI-02, C01
"""

VARIANTS = [(theme, size) for theme in ("clair", "sombre") for size in ("bureau", "mobile")]


def manifest(*, skip: tuple[str, ...] = (), extra: str = "", system: bool = True) -> str:
    lines = ["ENVIRONNEMENT\tsystème\tLinux, navigateur sans écran"] if system else []
    for number in (1, 2):
        for theme, size in VARIANTS:
            name = f"e{number}-{theme}-{size}.png"
            if name not in skip:
                lines.append(f"CAPTURE\t{name}\tÉcran {number}\t{theme}\t{size}")
    return "\n".join(lines) + "\n" + extra


def run(argv_after: list[str], files: dict[str, str], captures: tuple[str, ...] = ()) -> tuple[int, str]:
    """Run the script on a project copy: exit code and standard output."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for name, text in files.items():
            (root / name).write_text(text, encoding="utf-8")
        (root / "captures").mkdir()
        for name in captures:
            (root / "captures" / name).write_bytes(b"png")
        argv = [part.replace("{root}", str(root)) for part in argv_after]
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = main(argv)
        return code, out.getvalue()


def manifeste(text: str, captures: tuple[str, ...] | None = None, parcours: str = PARCOURS) -> tuple[int, str]:
    argv = ["manifeste", "{root}/parcours.md", "{root}/manifeste.tsv"]
    if captures is not None:
        argv += ["--captures", "{root}/captures"]
    return run(argv, {"parcours.md": parcours, "manifeste.tsv": text}, captures or ())


class Execution(unittest.TestCase):
    def test_every_screen_in_light_and_dark_on_desktop_and_mobile_is_covered(self) -> None:
        """No F-NNNN: ticket #100, A1: chaque écran du parcours capturé en clair, en sombre, sur bureau et sur mobile."""
        code, out = manifeste(manifest())
        self.assertEqual(code, 0)
        self.assertEqual(out.count("COUVERT\t"), 8)
        self.assertNotIn("MANQUE", out)

    def test_a_missing_variant_is_named_and_blocks(self) -> None:
        """No F-NNNN: ticket #100, A1: une variante sans capture ni raison est dite, le jugement ne la devine pas."""
        code, out = manifeste(manifest(skip=("e2-sombre-mobile.png",)))
        self.assertEqual(code, 1)
        self.assertIn("MANQUE\tÉcran 2\tsombre\tmobile", out)

    def test_a_screen_not_played_says_why_and_is_not_missing(self) -> None:
        """No F-NNNN: ticket #100, A1: un écran non joué porte sa raison, et la revue la rapporte."""
        skip = tuple(f"e2-{t}-{s}.png" for t, s in VARIANTS)
        code, out = manifeste(manifest(skip=skip, extra="NON-JOUE\tÉcran 2\tl'application refuse l'index sans compteur\n"))
        self.assertEqual(code, 0)
        self.assertIn("NON-JOUE\tÉcran 2\tl'application refuse l'index sans compteur", out)
        self.assertNotIn("MANQUE", out)

    def test_a_non_played_screen_without_a_reason_is_invalid(self) -> None:
        """No F-NNNN: ticket #100, A1: « non joué » sans raison ne dit rien."""
        skip = tuple(f"e2-{t}-{s}.png" for t, s in VARIANTS)
        code, out = manifeste(manifest(skip=skip, extra="NON-JOUE\tÉcran 2\t\n"))
        self.assertEqual(code, 1)
        self.assertIn("INVALID", out)

    def test_a_capture_the_run_never_wrote_is_invalid(self) -> None:
        """No F-NNNN: ticket #100, A1: une capture citée dont le fichier n'existe pas ne prouve rien."""
        names = tuple(f"e{n}-{t}-{s}.png" for n in (1, 2) for t, s in VARIANTS)
        code, out = manifeste(manifest(), captures=names[:-1])
        self.assertEqual(code, 1)
        self.assertIn("INVALID\te2-sombre-mobile.png", out)

    def test_the_system_the_run_used_is_stated(self) -> None:
        """No F-NNNN: ticket #100, A7: ce qui n'a tourné que sur un système le dit, sans quoi le rapport se tait."""
        code, out = manifeste(manifest(system=False))
        self.assertEqual(code, 1)
        self.assertIn("SANS-ENVIRONNEMENT", out)
        code, out = manifeste(manifest())
        self.assertIn("ENVIRONNEMENT\tsystème\tLinux", out)

    def test_a_screen_the_path_does_not_hold_is_invalid(self) -> None:
        """No F-NNNN: ticket #100, A1: une capture d'un écran absent du parcours voulu est refusée."""
        code, out = manifeste(manifest(extra="CAPTURE\te9.png\tÉcran 9\tclair\tbureau\n"))
        self.assertEqual(code, 1)
        self.assertIn("INVALID", out)
        self.assertIn("Écran 9", out)


SOURCE = "- EXI-01 : date, numéro, index\n- EXI-02 : index décroissant refusé\n- C01 : avertissement\n"
USINE = "- `product-source` : `source.md`\n"
HEADER = "| Identifiant | Lot | Ticket | Test | Écran | Capture | État | Jugé le |\n|---|---|---|---|---|---|---|---|\n"
ROWS = (
    "| EXI-01 | L1 | #5 | tests/a.py::t1 | Écran 1 | | absent | |\n"
    "| EXI-02 | L1 | #6 | tests/a.py::t2 | Écran 2 | | absent | |\n"
    "| C01 | L2 | #7 | tests/a.py::t3 | Écran 2 | | absent | |\n"
)
MATRICE = "# F-0000 : matrice\n\n" + HEADER + ROWS
CAPTURES = ("e1-clair-bureau.png", "e2-clair-bureau.png", "e2-sombre-mobile.png")


def element(identifier: str, state: str, severity: str, screen: str, capture: str, finding: str) -> str:
    return "\t".join(("ELEMENT", identifier, state, severity, screen, capture, finding)) + "\n"


LINE_EXI01 = element("EXI-01", "tenu", "-", "Écran 1", "e1-clair-bureau.png", "la ligne porte date, numéro et index")
LINE_EXI02 = element("EXI-02", "contraire", "bloquant", "Écran 2", "e2-clair-bureau.png", "un index inférieur est accepté")
LINE_C01 = element("C01", "partiel", "majeur", "Écran 2", "e2-sombre-mobile.png", "l'avertissement n'apparaît qu'au bureau")
GOOD_VERDICT = LINE_EXI01 + LINE_EXI02 + LINE_C01
READING = "LECTURE\tEXI-01\tconfirmé\tla capture montre les trois champs\n"


def verdict(text: str, *extra: str, matrice: str = MATRICE, files: dict[str, str] | None = None) -> tuple[int, str]:
    argv = ["verdict", "{root}/verdict.tsv", "--matrice", "{root}/matrice.md", "--usine", "{root}/usine.md"]
    argv += ["--root", "{root}", "--captures", "{root}/captures", *extra]
    base = {"verdict.tsv": text, "matrice.md": matrice, "usine.md": USINE, "source.md": SOURCE,
            "relecture.tsv": READING, "manifeste.tsv": manifest()}
    return run(argv, {**base, **(files or {})}, CAPTURES)


class Judgment(unittest.TestCase):
    def test_a_complete_verdict_on_real_captures_passes(self) -> None:
        """No F-NNNN: ticket #100, A3: chaque élément de la source reçoit un état de la règle unique, preuve à l'appui."""
        code, out = verdict(GOOD_VERDICT, "--relecture", "{root}/relecture.tsv")
        self.assertEqual(code, 0, out)
        self.assertIn("OK", out)

    def test_an_element_nobody_judged_blocks(self) -> None:
        """No F-NNNN: ticket #100, A3: la revue juge chaque élément, aucun n'est laissé au silence."""
        code, out = verdict(LINE_EXI01 + LINE_EXI02)
        self.assertEqual(code, 1)
        self.assertIn("NON-JUGE\tC01", out)

    def test_only_the_four_judged_states_exist(self) -> None:
        """No F-NNNN: ticket #100, A3: l'état suit la règle unique ; « écarté » est à l'auteur de la source, jamais au juge."""
        for state in ("écarté", "ok", "tenu partiellement"):
            with self.subTest(state=state):
                code, out = verdict(element("EXI-01", state, "mineur", "Écran 1", "e1-clair-bureau.png", "x") + LINE_EXI02 + LINE_C01)
                self.assertEqual(code, 1)
                self.assertRegex(out, r"(INVALID|REFUSED)\tEXI-01")

    def test_a_gap_carries_one_of_the_three_severities(self) -> None:
        """No F-NNNN: ticket #100, A4: bloquant, majeur ou mineur, rien d'autre ; un tenu n'en porte pas."""
        for severity in ("-", "critique", ""):
            with self.subTest(severity=severity):
                code, out = verdict(GOOD_VERDICT.replace("contraire\tbloquant", f"contraire\t{severity}"))
                self.assertEqual(code, 1)
                self.assertIn("INVALID\tEXI-02", out)
        code, out = verdict(GOOD_VERDICT.replace("tenu\t-", "tenu\tmineur"))
        self.assertEqual(code, 1)
        self.assertIn("INVALID\tEXI-01", out)

    def test_a_tenu_without_a_capture_is_refused(self) -> None:
        """No F-NNNN: ticket #100, A3: « tenu » exige la capture qui le montre, jugé sur l'écran réel."""
        code, out = verdict(GOOD_VERDICT.replace("e1-clair-bureau.png", "-", 1))
        self.assertEqual(code, 1)
        self.assertIn("INVALID\tEXI-01", out)

    def test_a_capture_that_is_not_a_file_is_refused(self) -> None:
        """No F-NNNN: ticket #100, A3: le juge ne cite que des captures prises."""
        code, out = verdict(GOOD_VERDICT.replace("e2-sombre-mobile.png", "inventee.png"))
        self.assertEqual(code, 1)
        self.assertIn("SANS-FICHIER\tC01", out)

    def test_a_capture_the_run_did_not_take_is_refused(self) -> None:
        """No F-NNNN: ticket #100, A3: la capture citée figure au manifeste de l'exécution."""
        extra = {"manifeste.tsv": manifest(skip=("e2-sombre-mobile.png",))}
        code, out = verdict(GOOD_VERDICT, "--manifeste", "{root}/manifeste.tsv", files=extra)
        self.assertEqual(code, 1)
        self.assertIn("HORS-MANIFESTE\tC01", out)

    def test_an_identifier_the_matrix_does_not_hold_is_unknown(self) -> None:
        """No F-NNNN: ticket #100, A3: le jugement se rapporte à la source, pas à un élément inventé."""
        code, out = verdict(GOOD_VERDICT + element("EXI-99", "absent", "mineur", "-", "-", "x"))
        self.assertEqual(code, 1)
        self.assertIn("UNKNOWN\tEXI-99", out)

    def test_two_states_for_one_identifier_contradict(self) -> None:
        """No F-NNNN: ticket #100, A3: un élément n'a qu'un état ; deux sections qui se contredisent bloquent."""
        both = GOOD_VERDICT + element("EXI-01", "partiel", "mineur", "Écran 2", "e2-clair-bureau.png", "l'index manque à l'écran 2")
        code, out = verdict(both, "--relecture", "{root}/relecture.tsv")
        self.assertEqual(code, 1)
        self.assertIn("CONTRADICTION\tEXI-01", out)


class SecondReading(unittest.TestCase):
    def test_no_publication_before_the_tenu_verdicts_are_reread(self) -> None:
        """No F-NNNN: ticket #100, A6: sans seconde lecture, chaque tenu reste à relire et rien ne se publie."""
        code, out = verdict(GOOD_VERDICT)
        self.assertEqual(code, 1)
        self.assertIn("A-RELIRE\tEXI-01", out)

    def test_a_contested_tenu_blocks(self) -> None:
        """No F-NNNN: ticket #100, A6: un tenu que la seconde lecture conteste n'est pas publié."""
        reading = "LECTURE\tEXI-01\tcontesté\tla capture ne montre pas le numéro du compteur\n"
        code, out = verdict(GOOD_VERDICT, "--relecture", "{root}/relecture.tsv", files={"relecture.tsv": reading})
        self.assertEqual(code, 1)
        self.assertIn("CONTESTE\tEXI-01\tla capture ne montre pas le numéro", out)

    def test_a_tenu_the_second_reader_skipped_blocks(self) -> None:
        """No F-NNNN: ticket #100, A6: chaque tenu est relu, pas un échantillon."""
        code, out = verdict(GOOD_VERDICT, "--relecture", "{root}/relecture.tsv", files={"relecture.tsv": "LECTURE\tC01\tconfirmé\tx\n"})
        self.assertEqual(code, 1)
        self.assertIn("NON-RELU\tEXI-01", out)

    def test_a_tenu_that_describes_a_lack_is_flagged_for_the_reader(self) -> None:
        """No F-NNNN: ticket #100, A6: un tenu dont le constat décrit un manque est signalé au relecteur."""
        text = element("EXI-01", "tenu", "-", "Écran 1", "e1-clair-bureau.png", "le numéro du compteur manque") + LINE_EXI02 + LINE_C01
        code, out = verdict(text)
        self.assertIn("SUSPECT\tEXI-01", out)
        self.assertEqual(code, 1)

    def test_a_clean_tenu_is_not_flagged(self) -> None:
        """No F-NNNN: ticket #100, A6: le signalement ne vise que les constats qui décrivent un manque."""
        code, out = verdict(GOOD_VERDICT, "--relecture", "{root}/relecture.tsv")
        self.assertNotIn("SUSPECT", out)

    def test_a_malformed_reading_is_invalid(self) -> None:
        """No F-NNNN: ticket #100, A6: une lecture sans raison ne confirme rien."""
        code, out = verdict(GOOD_VERDICT, "--relecture", "{root}/relecture.tsv", files={"relecture.tsv": "LECTURE\tEXI-01\tconfirmé\t\n"})
        self.assertEqual(code, 1)
        self.assertIn("INVALID", out)


def apply(text: str, matrice: str = MATRICE, *extra: str) -> tuple[int, str, str]:
    """Run `verdict --appliquer` and give the exit code, the output and the matrix file afterwards."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        files = {"verdict.tsv": text, "matrice.md": matrice, "usine.md": USINE, "source.md": SOURCE, "relecture.tsv": READING}
        for name, content in files.items():
            (root / name).write_text(content, encoding="utf-8")
        (root / "captures").mkdir()
        for name in CAPTURES:
            (root / "captures" / name).write_bytes(b"png")
        argv = ["verdict", str(root / "verdict.tsv"), "--matrice", str(root / "matrice.md"), "--usine", str(root / "usine.md")]
        argv += ["--root", str(root), "--captures", str(root / "captures"), "--relecture", str(root / "relecture.tsv"), *extra]
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = main(argv)
        return code, out.getvalue(), (root / "matrice.md").read_text(encoding="utf-8")


class Outputs(unittest.TestCase):
    def test_the_matrix_takes_the_verdict_and_stays_valid(self) -> None:
        """No F-NNNN: ticket #100, A5: la matrice est mise à jour, état, capture et date du jugement, par la règle unique."""
        code, out, after = apply(GOOD_VERDICT, MATRICE, "--appliquer", "--date", "2026-11-02")
        self.assertEqual(code, 0, out)
        self.assertIn("| EXI-01 | L1 | #5 | tests/a.py::t1 | Écran 1 | e1-clair-bureau.png | tenu | 2026-11-02 |", after)
        self.assertIn("| EXI-02 | L1 | #6 | tests/a.py::t2 | Écran 2 | e2-clair-bureau.png | contraire | 2026-11-02 |", after)
        self.assertIn("| C01 | L2 | #7 | tests/a.py::t3 | Écran 2 | e2-sombre-mobile.png | partiel | 2026-11-02 |", after)
        self.assertIn("APPLIQUE", out)

    def test_a_rejudged_row_takes_the_capture_of_its_new_verdict(self) -> None:
        """No F-NNNN: ticket #101, la boucle rejuge : la ligne ne garde pas la capture d'un jugement d'avant."""
        before = MATRICE.replace("| EXI-01 | L1 | #5 | tests/a.py::t1 | Écran 1 | | absent | |",
                                 "| EXI-01 | L1 | #5 | tests/a.py::t1 | Écran 1 | e1-clair-bureau.png | tenu | 2026-10-01 |")
        absent = element("EXI-01", "absent", "majeur", "-", "-", "l'écran n'a pas été joué")
        code, out, after = apply(absent + LINE_EXI02 + LINE_C01, before, "--appliquer", "--date", "2026-11-02")
        self.assertEqual(code, 0, out)
        self.assertIn("| EXI-01 | L1 | #5 | tests/a.py::t1 | Écran 1 |  | absent | 2026-11-02 |", after)

    def test_a_blocked_verdict_leaves_the_matrix_untouched(self) -> None:
        """No F-NNNN: ticket #100, A5: rien ne s'écrit tant que le verdict a un constat."""
        code, out, after = apply(LINE_EXI01 + LINE_EXI02, MATRICE, "--appliquer", "--date", "2026-11-02")
        self.assertEqual(code, 1)
        self.assertEqual(after, MATRICE)
        self.assertNotIn("APPLIQUE", out)

    def test_applying_asks_for_the_date_of_the_judgment(self) -> None:
        """No F-NNNN: ticket #100, A5: la date du jugement est donnée, jamais devinée."""
        with self.assertRaises(SystemExit) as raised:
            apply(GOOD_VERDICT, MATRICE, "--appliquer")
        self.assertEqual(raised.exception.code, 2)

    def test_an_element_set_aside_by_the_author_is_not_judged_nor_changed(self) -> None:
        """No F-NNNN: ticket #100, A5: la revue ne touche pas une ligne écartée par l'auteur de la source."""
        written = MATRICE.replace("| EXI-02 | L1 | #6 | tests/a.py::t2 | Écran 2 | | absent | |", "| EXI-02 | L1 | #6 | tests/a.py::t2 | Écran 2 | | écarté | 2026-10-01 |")
        code, out, after = apply(LINE_EXI01 + LINE_EXI02 + LINE_C01, written, "--appliquer", "--date", "2026-11-02")
        self.assertEqual(code, 1)
        self.assertIn("REFUSED\tEXI-02", out)
        self.assertEqual(after, written)

    def test_the_gaps_become_one_ticket_per_batch_and_severity_worst_first(self) -> None:
        """No F-NNNN: ticket #100, A5: un ticket par lot cohérent d'écarts, avec gravité, capture et identifiants cités."""
        extra = element("EXI-01", "partiel", "mineur", "Écran 1", "e1-clair-bureau.png", "la date s'affiche en anglais")
        code, out, _ = apply(extra + LINE_EXI02 + LINE_C01, MATRICE, "--tickets")
        self.assertEqual(code, 0, out)
        tickets = [line.split("\t") for line in out.splitlines() if line.startswith("TICKET")]
        self.assertEqual(
            [(t[1], t[2], t[3]) for t in tickets],
            [("bloquant", "L1", "EXI-02"), ("majeur", "L2", "C01"), ("mineur", "L1", "EXI-01")],
        )
        self.assertIn("e2-clair-bureau.png", tickets[0][4])
        self.assertIn("un index inférieur est accepté", tickets[0][5])

    def test_a_batch_with_two_severities_keeps_each_apart(self) -> None:
        """No F-NNNN: ticket #100, A5: la gravité d'un lot ne s'écrase pas sur celle d'un autre écart du même lot."""
        extra = element("EXI-01", "partiel", "mineur", "Écran 1", "e1-clair-bureau.png", "la date s'affiche en anglais")
        _, out, _ = apply(extra + LINE_EXI02 + LINE_C01, MATRICE, "--tickets")
        self.assertEqual(sum(1 for line in out.splitlines() if line.startswith("TICKET\t") and "\tL1\t" in line), 2)

    def test_a_tenu_makes_no_ticket(self) -> None:
        """No F-NNNN: ticket #100, A5: un élément tenu n'ouvre aucun ticket."""
        _, out, _ = apply(GOOD_VERDICT, MATRICE, "--tickets")
        self.assertNotIn("EXI-01", "".join(line for line in out.splitlines() if line.startswith("TICKET")))


def read(*parts: str) -> str:
    return " ".join(support.PLUGIN.joinpath(*parts).read_text(encoding="utf-8").split())


class Contents(unittest.TestCase):
    """The skill and the two agents say what the ticket asks, and the guards name them."""

    def test_the_judge_and_the_second_reader_cannot_write_and_are_guarded(self) -> None:
        """No F-NNNN: ticket #100, A1: un juge distinct de celui qui a codé, en lecture seule."""
        import guard_coder
        import guard_readonly

        for agent in ("review-judge", "review-recheck"):
            with self.subTest(agent=agent):
                tools = read("agents", f"{agent}.md").split("tools:", 1)[1].split("model:", 1)[0]
                for forbidden in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Agent"):
                    self.assertNotIn(forbidden, tools)
                self.assertIn(f"forge:{agent}", guard_readonly.READERS)
        self.assertIn("forge:feature-review", guard_coder.REVIEW_SKILLS)

    def test_the_judge_and_the_second_reader_are_two_agents_and_the_execution_stays_with_the_skill(self) -> None:
        """No F-NNNN: ticket #100, A1: l'exécution est séparée du jugement, comme qc-gate l'est de qc-conf."""
        skill = read("skills", "feature-review", "SKILL.md")
        self.assertIn("forge:review-judge", skill)
        self.assertIn("forge:review-recheck", skill)
        self.assertIn("distinct du juge", skill)
        self.assertIn("L'exécution reste dans ta session", skill)

    def test_the_run_uses_the_keys_of_the_factory_and_never_judges_without_a_capture(self) -> None:
        """No F-NNNN: ticket #100, A2: les clés de capture, « sans objet » quand elles manquent, jamais de jugement sans capture."""
        skill = read("skills", "feature-review", "SKILL.md")
        for key in ("journey-replay", "screenshot-command", "recording-command", "browser-drive", "computer-use-host"):
            self.assertIn(f"`{key}`", skill)
        self.assertIn("sans objet (clé `<nom>` absente)", skill)
        self.assertIn("jamais** un écran d'après le code", skill)
        self.assertIn("en clair et en sombre, sur bureau et sur mobile", skill)
        self.assertIn("jamais en CI", skill)

    def test_the_judge_judges_against_the_source_never_the_diff(self) -> None:
        """No F-NNNN: ticket #100, A3: chaque écran est confronté à la source (exigence, parcours, glossaire)."""
        judge = read("agents", "review-judge.md")
        self.assertIn("contre la source, jamais contre le diff ni contre le ticket", judge)
        for key in ("`product-source`", "`parcours.md`", "`glossary`"):
            self.assertIn(key, judge)
        self.assertIn("règle d'état", judge)

    def test_the_three_severities_have_their_fixed_definitions(self) -> None:
        """No F-NNNN: ticket #100, A4: bloquant, majeur, mineur, aux définitions du ticket, au juge comme au skill."""
        for text in (read("agents", "review-judge.md"), read("skills", "feature-review", "SKILL.md")):
            self.assertIn("`bloquant` : l'expert le voit en quelques minutes, et cela contredit sa demande ou rend l'écran incompréhensible", text)
            self.assertIn("`majeur` : cela gêne le travail ou la confiance", text)
            self.assertIn("`mineur` : le reste", text)

    def test_the_skill_says_who_publishes_the_tickets_and_under_which_label(self) -> None:
        """No F-NNNN: ticket #100, A5: qui publie les tickets et sous quelle étiquette ; le rapport enrichit la page de la feature."""
        skill = read("skills", "feature-review", "SKILL.md")
        self.assertIn("C'est la session qui lance ce skill qui les publie", skill)
        self.assertIn("`ready-for-agent`", skill)
        self.assertIn("critère de sortie", skill)
        self.assertIn("sans en créer une nouvelle", skill)
        self.assertIn("`recette.md`", skill)

    def test_the_second_reading_is_not_the_judge(self) -> None:
        """No F-NNNN: ticket #100, A6: la seconde lecture des tenu est un agent distinct, avant publication."""
        recheck = read("agents", "review-recheck.md")
        self.assertIn("Tu n'es ni le juge", recheck)
        self.assertIn("décrit un manque", recheck)
        self.assertIn("se contredit-il d'une section à l'autre", recheck)
        self.assertNotEqual(read("agents", "review-recheck.md"), read("agents", "review-judge.md"))

    def test_what_ran_on_one_system_only_is_said(self) -> None:
        """No F-NNNN: ticket #100, A7: le skill dit ce qui n'a tourné que sous Linux, sans vrai navigateur."""
        skill = read("skills", "feature-review", "SKILL.md")
        self.assertIn("sous Linux", skill)
        self.assertIn("Aucun vrai navigateur ni aucune application réelle", skill)
        self.assertIn("SYSTEME", skill)

    def test_the_prose_has_no_em_dash_and_names_no_project(self) -> None:
        """No F-NNNN: ticket #100: la prose du plugin est sans tiret cadratin et générique."""
        for parts in (("agents", "review-judge.md"), ("agents", "review-recheck.md"), ("skills", "feature-review", "SKILL.md"),
                      ("scripts", "revue_bout_en_bout.py")):
            with self.subTest(file="/".join(parts)):
                self.assertNotIn(chr(0x2014), read(*parts))


if __name__ == "__main__":
    unittest.main()
