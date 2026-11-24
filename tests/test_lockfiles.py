"""F-0002 T4: `lockfiles.py` reads lockfiles alone, `lockfile_age.py` only judges their age."""

import ast
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import support

UV_LOCK = """version = 1
revision = 3
requires-python = ">=3.10"

[[package]]
name = "My_Project"
version = "0.1.0"
source = { editable = "." }

[[package]]
name = "Requests"
version = "2.32.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "internal-lib"
version = "1.0.0"
source = { registry = "https://pypi.example.com/simple" }
"""

PACKAGE_LOCK = json.dumps(
    {
        "name": "app",
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "app", "version": "1.0.0"},
            "node_modules/left-pad": {
                "version": "1.3.0",
                "resolved": "https://registry.npmjs.org/left-pad/-/left-pad-1.3.0.tgz",
            },
            "node_modules/@scope/mirrored": {
                "version": "2.0.0",
                "resolved": "https://mirror.example.com/mirrored-2.0.0.tgz",
            },
            "node_modules/linked": {"resolved": "../linked", "link": True},
        },
    }
)

MOVED = ("Package", "_quoted", "PUBLIC_INDEX", "PUBLIC_TARBALLS", "LOCAL_SOURCES", "parse_uv_lock", "parse_package_lock", "read_at")


class LockfilesAloneTest(unittest.TestCase):
    def test_t4_3_a_uv_lock_is_parsed_without_the_age_check(self) -> None:
        """F-0002 T4.3: `lockfiles` imported alone parses a small `uv.lock` into the packages it gave before the move."""
        import lockfiles

        self.assertEqual(
            lockfiles.parse_uv_lock(UV_LOCK),
            [
                lockfiles.Package("requests", "2.32.0"),
                lockfiles.Package("internal-lib", "1.0.0", '{ registry = "https://pypi.example.com/simple" }'),
            ],
        )

    def test_t4_3_a_package_lock_is_parsed_without_the_age_check(self) -> None:
        """F-0002 T4.3: `lockfiles` imported alone parses a small `package-lock.json` into the packages it gave before the move."""
        import lockfiles

        self.assertEqual(
            lockfiles.parse_package_lock(PACKAGE_LOCK),
            [
                lockfiles.Package("left-pad", "1.3.0"),
                lockfiles.Package("@scope/mirrored", "2.0.0", "https://mirror.example.com/mirrored-2.0.0.tgz"),
            ],
        )

    def test_t4_3_a_file_is_read_at_a_ref_and_a_missing_one_is_none(self) -> None:
        """F-0002 T4.3: `read_at` gives the text of a file at a ref, None where it does not exist."""
        import lockfiles

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            git = ["git", "-C", folder, "-c", "user.name=t", "-c", "user.email=t@example.com"]
            subprocess.run([*git, "init", "--quiet"], check=True)
            (root / "uv.lock").write_text(UV_LOCK, encoding="utf-8")
            subprocess.run([*git, "add", "uv.lock"], check=True)
            subprocess.run([*git, "commit", "--quiet", "-m", "lock"], check=True)
            self.assertEqual(lockfiles.read_at(root, "HEAD", "uv.lock"), UV_LOCK)
            self.assertIsNone(lockfiles.read_at(root, "HEAD", "package-lock.json"))

    def test_t4_1_the_age_check_imports_what_moved_and_defines_none_of_it(self) -> None:
        """F-0002 T4.1: `lockfile_age.py` holds no definition of what moved to `lockfiles.py`, and imports what it uses."""
        import lockfile_age
        import lockfiles

        tree = ast.parse((support.PLUGIN / "scripts" / "lockfile_age.py").read_text(encoding="utf-8"))
        defined = {
            node.name for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))
        } | {
            target.id
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        self.assertEqual(defined & set(MOVED), set())
        for name in ("Package", "parse_uv_lock", "parse_package_lock", "read_at"):  # what the age check uses
            self.assertIs(getattr(lockfile_age, name), getattr(lockfiles, name), name)


if __name__ == "__main__":
    unittest.main()
