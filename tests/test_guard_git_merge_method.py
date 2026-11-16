"""La méthode de fusion que dit la clé `merge-method` est la seule qu'un agent lance (ticket #63, suivi #55)."""

import unittest

import support  # noqa: F401  met les hooks sur le chemin d'import
from guard_git import refusal


def always_green(*_target: str | None) -> bool:
    return True


def merge(command: str, key: list[str]) -> str | None:
    """Le verdict de `guard_git` sur `command`, pour un projet dont la clé `merge-method` vaut `key`."""
    return refusal(command, "feat/x", always_green, merge_method=key)


FLAGS = {"squash": ("--squash", "-s"), "merge": ("--merge", "-m"), "rebase": ("--rebase", "-r")}


class MethodAgainstTheKey(unittest.TestCase):
    def test_each_method_is_accepted_when_it_is_the_key(self) -> None:
        # #63 : chaque méthode que dit la clé passe, sous son option longue comme sous la courte.
        for method, flags in FLAGS.items():
            for flag in flags:
                with self.subTest(method=method, flag=flag):
                    self.assertIsNone(merge(f"gh pr merge 5 {flag} --delete-branch", [method]))

    def test_a_method_other_than_the_key_is_refused_and_names_both(self) -> None:
        # #63 : `--squash` sous une clé `merge` fusionne contre la règle du projet.
        for key, other in (("merge", "squash"), ("squash", "merge"), ("merge", "rebase"), ("rebase", "squash")):
            for flag in FLAGS[other]:
                with self.subTest(key=key, flag=flag):
                    verdict = merge(f"gh pr merge 5 {flag}", [key])
                    assert verdict is not None
                    self.assertIn("merge-method", verdict)
                    self.assertIn(f"`{key}`", verdict)
                    self.assertIn(f"`{other}`", verdict)


if __name__ == "__main__":
    unittest.main()
