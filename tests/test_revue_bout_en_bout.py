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


if __name__ == "__main__":
    unittest.main()
