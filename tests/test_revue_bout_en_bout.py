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


if __name__ == "__main__":
    unittest.main()
