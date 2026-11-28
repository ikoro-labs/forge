"""F-0003 A47 to A50, A57, A59 (ikoro-labs/forge#406): a short agent leads one ticket with
`forge:feature-build F-NNNN --ticket <n>`, asks its question in the G5 format, and gets the ticket back
as ready once a default decision answers it.

`gh` is simulated, every test runs under an isolated HOME and USERPROFILE and without the CLAUDE_ variables
of the session running the tests, and nothing is written in the real ~/.claude.
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import support
from agent_lock import main as lock_main
from handoff_header import process_start
from test_question_delay import STAFF, Gh, Project, issue, labeled, waiting

LOCK_SCRIPT = support.PLUGIN / "hooks" / "agent_lock.py"


class ReadyAgain(unittest.TestCase):
    """A59: a `post-default` on a ticket puts `ready-for-agent` back."""

    def test_a_default_decision_on_a_ticket_that_waited_gives_ready_for_agent_back(self) -> None:
        """F-0003 A59: the ticket loses `needs-info` and regains `ready-for-agent`, with the decision comment."""
        project = Project(self)
        gh = waiting(["needs-info"], 30)
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertTrue(gh.bodies()[0].startswith("Décision (staff-engineer, P1) par défaut"))
        self.assertEqual(gh.removed(), ["needs-info"])
        self.assertEqual(gh.added(), ["labels[]=ready-for-agent"])

    def test_a_ticket_that_waited_on_a_human_gesture_label_is_ready_again_too(self) -> None:
        """F-0003 A59: `ready-for-human`, which the skill also sets on a ticket, is answered the same way."""
        project = Project(self)
        gh = waiting(["ready-for-human"], 30)
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.removed(), ["ready-for-human"])
        self.assertEqual(gh.added(), ["labels[]=ready-for-agent"])

    def test_a_pull_request_never_gets_the_ready_label(self) -> None:
        """F-0003 A59: the label is for a ticket (an issue); a pull request that waited keeps only its removal."""
        project = Project(self)
        gh = waiting(["needs-info"], 30, pull_request=True)
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.added(), [])

    def test_a_ticket_already_ready_is_not_labeled_twice(self) -> None:
        """F-0003 A59: a ticket that already carries `ready-for-agent` is left as it is."""
        project = Project(self)
        gh = Gh({12: issue(12, ["needs-info", "ready-for-agent"])}, {12: [labeled("needs-info", 30)]})
        code, out = project.route(gh, STAFF, "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.added(), [])

    def test_a_reminder_gives_no_ready_label(self) -> None:
        """F-0003 A59: a verdict that is not a default decision leaves the ticket with the human."""
        project = Project(self)
        gh = waiting(["needs-info"], 30)
        code, out = project.route(gh, "VERDICT: RESERVED\nDECISION: a human\nMATRIX_CELL: H1\nGROUND: x\n", "--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(gh.added(), ["labels[]=needs-your-attention"])

    def test_the_plan_without_apply_says_the_label_and_writes_nothing(self) -> None:
        """F-0003 A59: the printed plan lists `ready-for-agent` among the labels to add; `gh` gets no write."""
        project = Project(self)
        gh = waiting(["needs-info"], 30)
        code, out = project.route(gh, STAFF, "--json")
        self.assertEqual(code, 0, out)
        self.assertIn('"ready-for-agent"', out)
        self.assertEqual(gh.writes, [])


SKILL = support.PLUGIN / "skills" / "feature-build" / "SKILL.md"
HEADING = "## Mode `--ticket`"


def skill() -> str:
    """The skill with each paragraph on one line, so a sentence wrapped by the editor still matches."""
    return " ".join(SKILL.read_text(encoding="utf-8").split())


def mode() -> str:
    """The section of the pinned agent, up to the end of the file (it is the last one)."""
    text = skill()
    assert HEADING in text, "the skill has no section for the pinned agent"
    return text.split(HEADING, 1)[1]


class OneTicket(unittest.TestCase):
    """A47, A48: the pinned agent leads that ticket only, and stops without a lock."""

    def test_the_option_is_in_the_argument_hint_and_the_arguments(self) -> None:
        """F-0003 A47: `--ticket <n>` is declared in the header and in the paragraph of the arguments."""
        head = SKILL.read_text(encoding="utf-8").split("---", 2)[1]
        self.assertRegex(head, r"argument-hint: .*\[--ticket <n>\]")
        arguments = skill().split("Arguments :", 1)[1].split("## 0.", 1)[0]
        self.assertRegex(arguments, r"`--ticket`, [^;]*mène seul")

    def test_the_lock_check_replaces_the_one_session_per_project_step(self) -> None:
        """F-0003 A48: in this mode step 0.5 gives way to `agent_lock.py check`, held by the session itself."""
        text = mode()
        self.assertRegex(text, r"étape 0\.5[^.]*remplacée par le contrôle du verrou")
        self.assertIn('hooks/agent_lock.py" check', text)
        self.assertRegex(text, r"tenu par ta propre session|qui doit être tenu par la session elle-même")

    def test_without_the_lock_it_stops_and_writes_nothing(self) -> None:
        """F-0003 A48: no lock (code 1 of `check`), the agent stops without a comment, a label or a lock."""
        text = mode()
        self.assertRegex(text, r"sans rien écrire[^.]*(commentaire|étiquette)")
        self.assertRegex(text, r"`check` sort en 1")
        self.assertRegex(text, r"disant dans ta sortie pourquoi")

    def test_a_closed_blocked_or_unready_ticket_stops_it_too(self) -> None:
        """F-0003 A48: closed, an open blocker, or neither `ready-for-agent` nor `agent-claimed`."""
        text = mode()
        self.assertRegex(text, r"fermé")
        self.assertRegex(text, r"bloqueur ouvert|`blocked_by`")
        self.assertRegex(text, r"ni `ready-for-agent` ni `agent-claimed`")

    def test_pause_gate_and_budget_are_still_read(self) -> None:
        """F-0003 A47 (design Q5): `.claude/PAUSED`, the gate and the error budget keep their say."""
        text = mode()
        self.assertIn(".claude/PAUSED", text)
        self.assertRegex(text, r"la porte[^.]*le budget d'erreur|le budget d'erreur[^.]*la porte")

    def test_it_leads_that_ticket_only_and_claims_no_other(self) -> None:
        """F-0003 A47: one ticket, no frontier, no claim of another ticket, no second coder at once."""
        text = mode()
        self.assertRegex(text, r"ne mènes que le ticket")
        self.assertRegex(text, r"ne revendiques? aucun autre ticket")
        self.assertRegex(text, r"[Pp]as de frontière")

    def test_it_does_not_claim_its_own_ticket_again(self) -> None:
        """F-0003 A47: the dispatcher already set the assignee, `agent-claimed` and the lock; step 2.1 is skipped."""
        self.assertRegex(mode(), r"ne revendiques pas[^.]*(déjà|répartiteur)|saute[^.]*revendication")

    def test_it_stops_at_the_merge_or_the_verdict(self) -> None:
        """F-0003 A47: merged, or the verdict posted, then it reports and stops; no end-to-end review, no closing."""
        text = mode()
        self.assertRegex(text, r"fusionnée[^.]*verdict[^.]*(tu t'arrêtes|arrêt)")
        self.assertRegex(text, r"étapes? 3 bis[^.]*5|3 bis et 5")

    def test_the_decider_questions_are_not_its_to_settle(self) -> None:
        """F-0003 A47: the due questions are the dispatcher's (A58); the agent runs no `due` and no `route`."""
        self.assertRegex(mode(), r"questions échues[^.]*répartiteur|répartiteur[^.]*questions échues")


class Page(unittest.TestCase):
    """The page of the feature says what the pinned entry does, and what has not been tried."""

    def page(self) -> str:
        text = (support.REPO_ROOT / "docs" / "usine-autonome.md").read_text(encoding="utf-8")
        return " ".join(text.split("## L'agent épinglé", 1)[1].split("\n## ", 1)[0].split())

    def test_the_page_documents_the_commands_and_the_label(self) -> None:
        """F-0003 A48, A57, A59: the lock check, the release, the G5 lines and the label `route` gives back."""
        page = self.page()
        for text in ("agent_lock.py check . <n>", "agent_lock.py release . <n>", "Décideur : staff-engineer"):
            self.assertIn(text, page)
        self.assertRegex(page, r"rend `ready-for-agent` à un ticket")

    def test_the_page_says_what_was_not_tried(self) -> None:
        """The page says the pinned entry was not run in a real `claude -p` session."""
        self.assertRegex(self.page(), r"Pas éprouvé : une session `claude -p")


class WithoutTheOption(unittest.TestCase):
    """A50: without `--ticket` the skill does what it did before."""

    def before_the_section(self) -> str:
        return skill().split(HEADING, 1)[0]

    def test_the_option_is_named_in_three_places_before_the_section_and_nowhere_else(self) -> None:
        """F-0003 A50: the hint, the paragraph of the arguments and the pointer of step 0.5; no other step changes."""
        # `--ticket '#n'` is the option of the other scripts (ticket_budget, revue_boucle), not this one.
        before = self.before_the_section()
        head, rest = before.split("# Construire une feature", 1)
        arguments, steps = rest.split("## 0. Avant le premier ticket", 1)
        step_five, others = steps.split("6. **L'agent", 1)
        own = re.compile(r"--ticket(?! '#)")
        self.assertEqual(len(own.findall(head)), 1)
        self.assertEqual(len(own.findall(arguments)), 2)
        self.assertEqual(len(own.findall(step_five)), 2)
        self.assertEqual(own.findall(others), [])

    def test_the_section_says_it_does_not_apply_without_the_option(self) -> None:
        """F-0003 A50: both the arguments and the section say the section is for `--ticket` only."""
        self.assertRegex(self.before_the_section(), r"sans lui,\s*cette section ne s'applique pas")
        self.assertRegex(mode(), r"Sans `--ticket`, rien de cette section ne s'applique")

    def test_step_zero_five_still_holds_its_session_check(self) -> None:
        """F-0003 A50: the one-session-per-project step keeps its command and its two branches."""
        step = self.before_the_section().split("5. **Une seule session par projet.**", 1)[1].split("6. **L'agent", 1)[0]
        self.assertIn('hooks/handoff_header.py" sessions .', step)
        self.assertIn("code 6", step)
        self.assertIn("`ListAgents`", step)
        self.assertIn("**Sinon**", step)

    def test_the_steps_keep_their_order(self) -> None:
        """F-0003 A50: steps 0 to 6 are still there, in order, and the section of the pinned agent comes last."""
        text = skill()
        heads = [
            "## 0. Avant le premier ticket", "## 1. L'état des tickets", "## 2. Lancer les coders",
            "## 3. Relire et fusionner", "## 3 bis. La revue de bout en bout", "## 5. Après le dernier ticket",
            "## 6. Rendre compte", HEADING,
        ]  # fmt: skip
        positions = [text.index(head) for head in heads]
        self.assertEqual(positions, sorted(positions))


class Resume(unittest.TestCase):
    """A49: a ticket with a branch or an open PR of a previous agent is resumed, not started again."""

    def resume(self) -> str:
        return mode().split("**La reprise.**", 1)[1].split("**L'arrêt.**", 1)[0]

    def test_the_section_exists(self) -> None:
        """F-0003 A49: the pinned mode has a paragraph for the resumption."""
        self.assertIn("**La reprise.**", mode())

    def test_an_open_pr_goes_to_the_review_without_a_new_coder_or_pr(self) -> None:
        """F-0003 A49: the open PR that cites the ticket enters step 3; nobody recodes, no PR is opened."""
        text = self.resume()
        self.assertRegex(text, r"gh pr list --state open --search \"<n> in:body\"")
        self.assertRegex(text, r"étape 3[^.]*sans recoder")
        self.assertRegex(text, r"n'ouvres? (aucune|pas de) (nouvelle )?PR")

    def test_a_branch_without_a_pr_is_resumed_by_the_coder_from_that_branch(self) -> None:
        """F-0003 A49: the coder is told to start from the existing branch, to push on it and to open its PR."""
        text = self.resume()
        self.assertIn("git ls-remote --heads origin", text)
        self.assertIn("git switch --detach origin/<b>", text)
        self.assertIn("git push origin HEAD:<b>", text)
        self.assertRegex(text, r"sans en créer une autre")

    def test_without_branch_or_pr_the_coder_starts_from_the_base(self) -> None:
        """F-0003 A49: nothing left by a previous agent, the coder starts as step 2 says."""
        self.assertRegex(self.resume(), r"[Ss]ans (branche ni PR|l'une ni l'autre)[^.]*(base|étape 2)")


class Question(unittest.TestCase):
    """A57: a pinned agent that has a question posts it in the G5 format, hands the ticket back and stops."""

    def question(self) -> str:
        return mode().split("**Une question.**", 1)[1].split("**L'arrêt.**", 1)[0]

    def test_the_comment_has_the_three_lines_of_the_g5_format(self) -> None:
        """F-0003 A57: `Question :`, `Recommandation :` and `Décideur :`, one question per comment."""
        text = self.question()
        for line in ("Question : <", "Recommandation : <", "Décideur : staff-engineer"):
            self.assertIn(line, text)
        self.assertIn("Décideur : product-owner", text)
        self.assertRegex(text, r"un commentaire par question|une question par commentaire")

    def test_a_missing_decider_line_means_the_staff_engineer(self) -> None:
        """F-0003 A57 (G5): the decider is chosen by the matrix, and a missing line reads `staff-engineer`."""
        self.assertRegex(self.question(), r"ligne absente[^.]*`staff-engineer`|`staff-engineer`[^.]*ligne absente")

    def test_the_ticket_waits_for_an_answer_and_is_no_longer_claimed(self) -> None:
        """F-0003 A57: `needs-info` is set; `ready-for-agent`, `agent-claimed` and the assignee are removed."""
        text = self.question()
        self.assertIn("--add-label needs-info", text)
        self.assertIn("--remove-label ready-for-agent", text)
        self.assertIn("--remove-label agent-claimed", text)
        self.assertIn("--remove-assignee", text)

    def test_the_lock_is_freed_and_the_agent_stops(self) -> None:
        """F-0003 A57: `agent_lock.py release`, then the stop; no decider is launched from here."""
        text = self.question()
        self.assertIn('hooks/agent_lock.py" release . <n>', text)
        self.assertRegex(text, r"[Aa]rrête-toi")
        self.assertRegex(text, r"ni décideur ni `route`|aucun décideur")

    def test_the_comment_comes_first_and_the_lock_last(self) -> None:
        """F-0003 A57: a ticket never waits on a question that was not posted, and the lock goes last."""
        text = self.question()
        comment, labels, release = (text.index(m) for m in ("Commente le ticket", "--add-label needs-info", "release ."))
        self.assertLess(comment, labels)
        self.assertLess(labels, release)

    def test_an_implementation_detail_is_not_a_question(self) -> None:
        """F-0003 A57: what the spec does not fix is decided and written in the PR, as step 2 says."""
        self.assertRegex(self.question(), r"détail d'implémentation[^.]*décide-le")

    def test_the_default_decision_gives_the_ticket_back(self) -> None:
        """F-0003 A59: the section says what follows an answer: `ready-for-agent` and a resumption."""
        self.assertRegex(self.question(), r"`ready-for-agent`[^.]*reprend")


class Locked(unittest.TestCase):
    """A48, A57: the pinned agent runs only on a ticket whose lock it holds itself, and frees it to ask."""

    def setUp(self) -> None:
        self.home = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.repo = self.home / "demo"
        (self.repo / ".git").mkdir(parents=True)
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in [key for key in os.environ if key.startswith(("CLAUDE_", "GIT_"))]:
            del os.environ[name]
        os.environ.update(HOME=str(self.home), USERPROFILE=str(self.home))

    def sleeper(self) -> int:
        """A running process that is neither this one nor one of its ancestors."""
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return process.pid

    def dead_pid(self) -> int:
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait()
        return process.pid

    def lock(self, pid: int, ticket: str = "406", text: str | None = None) -> Path:
        """The lock of a ticket as the design's data model writes it."""
        project = re.sub(r"[\\/:]", "-", str(self.repo))
        folder = self.home / ".claude" / "hooks" / "state" / "dispatch" / "locks" / project
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{ticket}.json"
        fields = {
            "ticket": ticket, "pid": pid, "start": process_start(pid), "name": "forge-dispatch-406",
            "worktree": str(self.repo), "zones": [], "since": "2026-11-28T12:00:00Z",
        }
        path.write_text(json.dumps(fields) if text is None else text, encoding="utf-8")
        return path

    def call(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = lock_main(list(args))
        return code, out.getvalue()

    def test_a_lock_held_by_the_session_itself_passes(self) -> None:
        """F-0003 A48: the lock names this process (or an ancestor): the agent may go on."""
        self.lock(os.getpid())
        code, out = self.call("check", str(self.repo), "406")
        self.assertEqual(code, 0, out)
        self.assertIn("tenu par cette session", out)

    def test_without_a_lock_the_agent_stops(self) -> None:
        """F-0003 A48: no lock file for the ticket, code 1 and the reason."""
        code, out = self.call("check", str(self.repo), "406")
        self.assertEqual(code, 1, out)
        self.assertIn("aucun verrou", out)

    def test_a_lock_of_another_live_process_stops_the_agent(self) -> None:
        """F-0003 A48: a lock a live process of another agent holds is not this session's."""
        self.lock(self.sleeper())
        code, out = self.call("check", str(self.repo), "406")
        self.assertEqual(code, 1, out)
        self.assertIn("autre processus", out)

    def test_a_lock_of_a_dead_process_stops_the_agent(self) -> None:
        """F-0003 A48: a lock whose pid is gone says nothing for this session."""
        self.lock(self.dead_pid())
        code, out = self.call("check", str(self.repo), "406")
        self.assertEqual(code, 1, out)
        self.assertIn("pid mort", out)

    def test_an_unreadable_lock_stops_the_agent(self) -> None:
        """F-0003 A48: a lock file that cannot be read is no lock."""
        self.lock(os.getpid(), text="not json")
        code, out = self.call("check", str(self.repo), "406")
        self.assertEqual(code, 1, out)
        self.assertIn("illisible", out)

    def test_the_lock_of_another_ticket_does_not_count(self) -> None:
        """F-0003 A47, A48: the agent holds the lock of its own ticket, not the one of #407."""
        self.lock(os.getpid(), ticket="407")
        code, out = self.call("check", str(self.repo), "406")
        self.assertEqual(code, 1, out)

    def test_a_worktree_path_reads_the_locks_of_its_main_checkout(self) -> None:
        """F-0003 A48: the dispatcher keys its locks by the main checkout; the agent runs in a worktree of it."""
        self.lock(os.getpid())
        worktree = self.home / "wt"
        gitdir = self.repo / ".git" / "worktrees" / "wt"
        gitdir.mkdir(parents=True)
        (gitdir / "commondir").write_text("../..\n", encoding="utf-8")
        worktree.mkdir()
        (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
        code, out = self.call("check", str(worktree), "406")
        self.assertEqual(code, 0, out)

    def test_a_ticket_that_is_not_a_number_is_a_wrong_call(self) -> None:
        """F-0003 A48: the ticket names a file, so `../x` is refused with code 2 and nothing is read."""
        code, out = self.call("check", str(self.repo), "../406")
        self.assertEqual(code, 2, out)

    def test_releasing_removes_the_lock_this_session_holds(self) -> None:
        """F-0003 A57: the agent that asks its question frees its lock; the ticket is then without one."""
        path = self.lock(os.getpid())
        code, out = self.call("release", str(self.repo), "406")
        self.assertEqual(code, 0, out)
        self.assertFalse(path.exists())

    def test_releasing_never_removes_the_lock_of_another_process(self) -> None:
        """F-0003 A57: a lock another agent holds stays, and the command says it did nothing."""
        path = self.lock(self.sleeper())
        code, out = self.call("release", str(self.repo), "406")
        self.assertEqual(code, 1, out)
        self.assertTrue(path.exists())

    def test_the_script_runs_as_a_process(self) -> None:
        """F-0003 A48: the form the skill calls, `agent_lock.py check <project> <ticket>`, under an isolated HOME."""
        env = {k: v for k, v in os.environ.items()}
        done = subprocess.run(
            [sys.executable, str(LOCK_SCRIPT), "check", str(self.repo), "406"],
            capture_output=True, text=True, env=env, timeout=30,
        )  # fmt: skip
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("aucun verrou", done.stdout)


if __name__ == "__main__":
    unittest.main()
