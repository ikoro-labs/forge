"""`guard_git` relit les messages des commits de la PR avant une fusion (ticket #64, suivi #55)."""

import unittest

import support  # noqa: F401  met les hooks sur le chemin d'import
from guard_git import refusal

Commit = tuple[str, str]
SHA = "8e80a6e46958d38d63deb30b4500f23899bf5c01"


def always_green(*_target: str | None) -> bool:
    return True


def merge(
    command: str,
    commits: list[Commit] | None,
    description: str = "Refs #206\n",
    key: list[str] | None = None,
) -> str | None:
    """Le verdict de `guard_git` sur `command`, pour une PR dont `gh` rend ces commits et cette description."""
    return refusal(
        command,
        "feat/x",
        always_green,
        description=lambda *_target: description,
        commit_messages=lambda *_target: commits,
        merge_method=key,
    )


class ClosingKeywordInACommit(unittest.TestCase):
    def test_a_commit_that_closes_a_ticket_the_description_cites_with_refs_is_refused(self) -> None:
        # #64 : GitHub lit le message de chaque commit de la branche quand la fusion est un commit de fusion.
        verdict = merge("gh pr merge 5 --merge", [(SHA, "feat(x): a\n\nCloses #206\n")])
        assert verdict is not None
        self.assertIn("#206", verdict)

    def test_the_refusal_names_the_commit_and_says_how_to_fix_it(self) -> None:
        # #64 : le sha court, le ticket, puis les deux sorties : réécrire le message ou retirer le `Refs`.
        commits = [("1111111aaaa", "fix: b"), (SHA, "feat(x): a\n\nCloses #206")]
        verdict = merge("gh pr merge 5 --merge", commits)
        assert verdict is not None
        self.assertIn("8e80a6e", verdict)
        self.assertNotIn("1111111", verdict)
        self.assertNotIn(SHA, verdict)
        self.assertIn("rewrite the commit message", verdict)
        self.assertIn("drop #206 from the Refs", verdict)

    def test_a_commit_that_cites_the_ticket_with_refs_passes(self) -> None:
        # #64 : le cas courant, que la règle ne doit pas gêner.
        commits = [(SHA, "feat(x): a\n\nRefs #206\n"), ("2222222", "test(x): b\n\nRefs #206")]
        self.assertIsNone(merge("gh pr merge 5 --merge", commits))

    def test_a_closing_keyword_for_another_ticket_than_the_refs_passes(self) -> None:
        # #64 : seul le ticket que la description cite en `Refs` est gardé ouvert.
        self.assertIsNone(merge("gh pr merge 5 --merge", [(SHA, "fix(x): a\n\nCloses #207\n")]))

    def test_every_closing_keyword_github_reads_is_caught_in_a_commit(self) -> None:
        # #64 : la règle des mots-clés est celle de la description et du message de fusion, une seule fonction.
        for closing in ["Closed #206", "fix #206", "Fixes #206", "resolved: #206", "RESOLVES o/r#206"]:
            with self.subTest(closing=closing):
                self.assertIsNotNone(merge("gh pr merge 5 --merge", [(SHA, f"fix: a\n\n{closing}")]))

    def test_a_commit_that_closes_a_ticket_no_refs_cites_passes(self) -> None:
        # #64 : une PR en `Closes #206` peut porter un commit en `Closes #206`.
        commits = [(SHA, "feat(x): a\n\nCloses #206\n")]
        self.assertIsNone(merge("gh pr merge 5 --merge", commits, description="Closes #206\n"))


if __name__ == "__main__":
    unittest.main()
