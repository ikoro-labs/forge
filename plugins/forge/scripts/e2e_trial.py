"""Try the factory end to end on a trial repository, before a version is published.

    e2e_trial.py [--projet DIR] [--plugin DIR] [--usine FILE] [--memory-mb N] [--timeout S]
                 [--wait-checks S] [--poll-seconds S] [--id NAME]

The tests of `tests/` prove each hook and each script alone. This script proves the chain: a coder
that opens its pull request, a guard that lets a legitimate gesture through. It builds a throwaway
project, launches `claude -p` on it with the plugin under test, reads what the run left on the trial
repository, and cleans up. It reads three keys of `docs/agents/usine.md` (`--usine` reads another
file), none of which has a default:

    - `e2e-repo` : `<owner>/<name>`, the trial repository on GitHub
    - `e2e-command` : the command line launched in the throwaway project
    - `e2e-budget-usd` : the ceiling of the run, a positive number of dollars

A key that is absent makes the trial "sans objet (clé `<nom>` absente)": the script prints
`SANS-OBJET (clé `<nom>` absente)` and exits 0, and it never prints `PASS`. The launch is bounded by
`bounded_run.py` (ticket #66): the key `run-limits` of the project, or `--memory-mb` and `--timeout`,
which win. Without either, the bound is "sans objet (clé `run-limits` absente)".

`e2e-command` is split into words as a POSIX shell does, then each word has its markers replaced (no
shell runs it): `{plugin}` (the plugin under test, `--plugin`, the plugin that holds this script by
default) and `{budget}` (the key `e2e-budget-usd`) are required, so that a command cannot try the
pinned plugin by mistake, and `{feature}`, `{ticket}` and `{base}` are optional. Any other marker is
refused.

The steps, in this order, each named when it fails: `budget` (the post's budget, `run-budget`, read
before anything is created), `preparation` (a fresh clone of the trial repository in a throwaway
folder, then a base branch `e2e/<name>` pushed with a minimal `usine.md` and a feature whose spec is
accepted), `ticket` (a fictitious ticket `ready-for-agent`, one simple criterion), `lancement` (the
command, under `bounded_run.py`), `pr` (a pull request aimed at the base branch of the trial, open or
merged), `citation` (it cites the ticket), `checks` (all green; the ones still running are awaited up
to `--wait-checks` seconds, none at all is a failure), `nettoyage`.

The cleanup runs whatever happens: it closes the open pull requests aimed at the trial's base branch
and the ticket the trial opened, and deletes those requests' branches and the base branch. It touches
nothing it did not create: each object is found by its number or its name, every `gh` gesture names the
trial repository, and the default branch is never deleted. The trial repository cannot be the
repository of the project that runs the trial.

The result, one fact per line on standard output: `RESULTAT: PASS` or `RESULTAT: FAIL` (with `ETAPE:`
and `RAISON:`), `TETE:` (the commit of the plugin tried, "arbre modifié" when its tree holds changes
the commit does not), `DEPOT:`, `TICKET:`, `PR:`, `CHECKS:`, then one `NETTOYAGE:` line per gesture
(`ECHEC` for one that failed, which turns a `PASS` into a `FAIL` at the step `nettoyage`). The pull
request of a release copies `RESULTAT` and `TETE`.

The trial costs real model calls and needs `gh` signed in on the trial repository: run it only by hand,
for a release. Exit codes: 0 for `PASS` and for `SANS-OBJET`, 1 for `FAIL`, 2 for a wrong call (an
ill-formed key, an unreadable file, the project's own repository named as the trial repository).

The standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import NamedTuple, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import bounded_run  # noqa: E402  the bounded launcher of ticket #66, next to this script
import usine  # noqa: E402  the reader of `usine.md`, found through the `sys.path` set above

REPO_KEY, COMMAND_KEY, BUDGET_KEY, LIMITS_KEY = "e2e-repo", "e2e-command", "e2e-budget-usd", "run-limits"
E2E_KEYS = (REPO_KEY, COMMAND_KEY, BUDGET_KEY)
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
MARKER = re.compile(r"\{(\w+)\}")
REQUIRED_MARKERS = ("plugin", "budget")
MARKERS = (*REQUIRED_MARKERS, "feature", "ticket", "base")
WRONG_CALL = 2

GREEN = ("pass", "skipping")  # the buckets of `gh pr checks` that do not fail the trial
FEATURE = "F-9999"
LABEL = "ready-for-agent"
IDENTITY = ("-c", "user.name=forge-e2e", "-c", "user.email=forge-e2e@users.noreply.github.com", "-c", "commit.gpgsign=false")
ORIGIN = re.compile(r"github\.com[:/]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$")
ISSUE_URL = re.compile(r"/issues/(\d+)\s*$")

# What the throwaway project holds: the smallest `usine.md`, a feature whose spec is accepted (the gate
# `forge:feature-build` reads without the key `feature-gate`), and a ticket with one simple criterion.
USINE_MD = """# Usine du dépôt d'essai

Écrite par `e2e_trial.py` pour un essai de bout en bout : deux clés, les autres sont absentes.

- `feature-dir` : `docs/features`
- `merge-method` : `merge`
"""
IDEE_MD = f"""---
feature: {FEATURE}
document: idee
titre: essai de bout en bout
porteur: forge-e2e
etat: active
demande_par: interne, l'essai de bout en bout de l'usine
issue: {{ticket}}
date: {{date}}
---

# {FEATURE} : essai de bout en bout

Un fichier à écrire, pour éprouver l'enchaînement de l'usine.
"""
SPEC_MD = f"""---
feature: {FEATURE}
document: spec
statut: accepte
destinataires: forge:coder
base: {{base}}
date: {{date}}
---

# {FEATURE} : spécification

Le dépôt contient un fichier `essai.txt` à sa racine, dont la seule ligne est `essai de bout en bout`.
"""
TICKET_MD = f"""Motif: to-tickets {FEATURE} essai de bout en bout {{id}}
Feature: {FEATURE}

L'essai de bout en bout de l'usine a besoin d'un ticket qu'un coder prenne seul : un fichier à écrire.

## Criteria

- A1: le fichier `essai.txt` existe à la racine du dépôt et sa seule ligne est `essai de bout en bout`.

## Validation cases

A1.1 | lire `essai.txt` | la ligne `essai de bout en bout`
AGREED: test-author, coder, qc-conf

## Out of scope

- tout autre fichier.

Refs: docs/features/{FEATURE}/spec.md
"""


class Settings(NamedTuple):
    """The keys of the trial, read and checked."""

    repo: str
    command: list[str]
    budget: str


class Failure(Exception):
    """A step of the trial that did not hold: its name, and why."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = " ".join(reason.split())[:400] or "sans détail"


class Trial:
    """What a trial created on the trial repository, found again by its number: nothing else is touched."""

    def __init__(self, repo: str, name: str, scratch: Path) -> None:
        self.repo = repo
        self.name = name
        self.base = f"e2e/{name}"
        self.scratch = scratch
        self.clone = scratch / "projet"
        self.ticket: int | None = None
        self.base_pushed = False
        self.default_branch = ""
        self.failed = False  # a gesture of the cleanup did not hold
        self.prs: list[int] = []  # every pull request aimed at the base branch of the trial
        self.pr: int | None = None  # the one that is judged

    def tool(self, stage: str, argv: list[str], *, cwd: Path | None = None) -> str:
        """Run `git` or `gh` and give its standard output; a failure is a `Failure` of `stage`."""
        try:
            done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        except OSError as error:
            raise Failure(stage, f"{argv[0]} ne se lance pas ({error})") from None
        if done.returncode != 0:
            raise Failure(stage, f"`{' '.join(argv[:3])}` a rendu {done.returncode} : {done.stderr.strip() or done.stdout.strip()}")
        return done.stdout

    def gh(self, stage: str, *args: str) -> str:
        """A `gh` gesture, always aimed at the trial repository."""
        return self.tool(stage, ["gh", *args, "--repo", self.repo])

    def git(self, stage: str, *args: str) -> str:
        return self.tool(stage, ["git", "-C", str(self.clone), *args])

    def prepare(self, today: str) -> None:
        """A fresh clone, the fictitious ticket, then the base branch of the trial with the project's files."""
        self.tool("preparation", ["gh", "repo", "clone", self.repo, str(self.clone)])
        self.gh("ticket", "label", "create", LABEL, "--force", "--description", "Prêt pour un agent")
        body = self.scratch / "ticket.md"
        body.write_text(TICKET_MD.format(id=self.name), encoding="utf-8")
        title = f"Essai de bout en bout {self.name}"
        created = self.gh("ticket", "issue", "create", "--title", title, "--body-file", str(body), "--label", LABEL)
        if not (match := ISSUE_URL.search(created)):
            raise Failure("ticket", f"`gh issue create` n'a pas rendu l'adresse du ticket : {created.strip()[:120]}")
        self.ticket = int(match.group(1))
        self.default_branch = self.git("preparation", "rev-parse", "--abbrev-ref", "HEAD").strip()
        self.git("preparation", "switch", "-c", self.base)
        files = {
            Path("docs") / "agents" / "usine.md": USINE_MD,
            Path("docs") / "features" / FEATURE / "idee.md": IDEE_MD.format(ticket=self.ticket, date=today),
            Path("docs") / "features" / FEATURE / "spec.md": SPEC_MD.format(base=self.base, date=today),
        }
        for relative, text in files.items():
            (self.clone / relative).parent.mkdir(parents=True, exist_ok=True)
            (self.clone / relative).write_text(text, encoding="utf-8")
        self.git("preparation", "add", "-A")
        self.git("preparation", *IDENTITY, "commit", "-m", f"chore(e2e): le projet de l'essai {self.name}")
        self.git("preparation", "push", "origin", f"HEAD:{self.base}")
        self.base_pushed = True

    def delete_branch(self, branch: str) -> None:
        """Delete a branch of the trial repository; one that is already gone is not a failure."""
        endpoint = f"repos/{self.repo}/git/refs/heads/{branch}"
        try:
            self.tool("nettoyage", ["gh", "api", "--method", "DELETE", endpoint])
        except Failure as failure:
            if not re.search(r"does not exist|Not Found|HTTP (404|422)", failure.reason):
                raise

    def clean_up(self) -> list[str]:
        """Close what the trial created and delete its branches, found again by number; one line per gesture.

        Only the ticket the trial opened, the pull requests aimed at its own base branch, those requests'
        branches (never the base of the clone, `main` or `master`) and the base branch itself are touched.
        A gesture that fails is told (`ECHEC`) and the others go on; `failed` then says the cleanup did not hold.
        """
        lines: list[str] = []

        def step(label: str, gesture: Callable[[], object]) -> None:
            try:
                gesture()
                lines.append(f"NETTOYAGE: {label}")
            except Failure as failure:
                self.failed = True
                lines.append(f"NETTOYAGE: ECHEC {label} : {failure.reason}")

        found: list[dict] = []
        if self.base_pushed:
            try:
                found = self.list_prs("nettoyage")
            except Failure as failure:
                self.failed = True
                lines.append(f"NETTOYAGE: ECHEC lecture des PR vers {self.base} : {failure.reason}")
        for item in found:
            if item["state"] == "OPEN":
                step(f"PR #{item['number']} fermée", partial(self.gh, "nettoyage", "pr", "close", str(item["number"])))
        protected = {self.base, self.default_branch, "main", "master", ""}
        for branch in sorted({item["headRefName"] for item in found} - protected):
            step(f"branche {branch} supprimée", partial(self.delete_branch, branch))
        if self.ticket is not None:
            step(
                f"ticket #{self.ticket} fermé",
                lambda: self.gh("nettoyage", "issue", "close", str(self.ticket), "--reason", "not planned"),
            )
        if self.base_pushed:
            step(f"branche {self.base} supprimée", lambda: self.delete_branch(self.base))
        return lines

    def list_prs(self, stage: str) -> list[dict]:
        """Every pull request aimed at the base branch of the trial, in any state."""
        listing = self.gh(
            stage, "pr", "list", "--state", "all", "--base", self.base, "--limit", "100",
            "--json", "number,title,body,state,headRefName",
        )
        try:
            return json.loads(listing)
        except ValueError:
            raise Failure(stage, f"`gh pr list` n'a pas rendu du JSON : {listing.strip()[:120]}") from None

    def find_pr(self) -> int:
        """The pull request the run left: the latest one aimed at the base of the trial that cites the ticket.

        Pull requests are found by that base branch, a name only this trial uses, merged ones included
        (`forge:qc` merges on ACCEPT). None is a `pr` failure, none that cites the ticket a `citation`
        failure, a closed one a `pr` failure.
        """
        found = self.list_prs("pr")
        self.prs = sorted(item["number"] for item in found)
        if not found:
            raise Failure("pr", f"aucune PR n'a été ouverte vers la base {self.base}")
        cite = re.compile(rf"(?<![\w/])#{self.ticket}(?!\d)")
        citing = [item for item in found if cite.search(f"{item['title']}\n{item['body']}")]
        if not citing:
            listed = ", ".join(f"#{number}" for number in self.prs)
            raise Failure("citation", f"aucune PR vers la base ne cite #{self.ticket} (PR : {listed})")
        latest = max(citing, key=lambda item: item["number"])
        if latest["state"] not in ("OPEN", "MERGED"):
            raise Failure("pr", f"la PR #{latest['number']} est fermée sans fusion")
        self.pr = latest["number"]
        return latest["number"]

    def read_checks(self) -> list[dict]:
        """The checks of the judged pull request, `name` and `bucket` each, as `gh` rates them."""
        done = subprocess.run(
            ["gh", "pr", "checks", str(self.pr), "--json", "name,bucket", "--repo", self.repo],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        try:
            return json.loads(done.stdout)
        except ValueError:
            if "no checks reported" in done.stderr:
                return []  # gh exits non-zero while a pull request has no check; the JSON alone judges
            raise Failure("checks", f"`gh pr checks` n'a pas rendu du JSON : {done.stderr.strip()[:200]}") from None

    def wait_green(self, wait: int, poll: float) -> int:
        """The number of checks once all are green; the checks still running are awaited, up to `wait` seconds."""
        start = time.monotonic()
        while True:
            found = self.read_checks()
            if not found:
                raise Failure("checks", f"aucun check n'est rapporté sur la PR #{self.pr} : rien ne dit qu'elle est verte")
            red = [item["name"] for item in found if item["bucket"] not in (*GREEN, "pending")]
            if red:
                raise Failure("checks", f"checks rouges sur la PR #{self.pr} : {', '.join(red)}")
            running = [item["name"] for item in found if item["bucket"] == "pending"]
            if not running:
                return len(found)
            if time.monotonic() - start >= wait:
                raise Failure("checks", f"checks encore en cours sur la PR #{self.pr} après {wait} s : {', '.join(running)}")
            time.sleep(poll)


LAUNCHER = Path(__file__).resolve().with_name("bounded_run.py")
# What `bounded_run.py` says with its own exit codes, in the words of a step that failed.
LAUNCHER_CODES = {
    bounded_run.BUDGET: "le budget du poste n'est pas tenu",
    bounded_run.WRONG_CALL: "appel du lanceur borné refusé",
    bounded_run.REFUSED: "la borne n'a pas pu être posée",
    bounded_run.MEMORY: "la borne de mémoire est probablement atteinte",
    bounded_run.DELAY: "le délai est dépassé et la commande tuée",
    bounded_run.NOT_FOUND: "commande introuvable",
}


def launcher(usine_file: Path, args: argparse.Namespace, *rest: str) -> list[str]:
    """The call of the bounded launcher: the project's keys, then the options that win over them."""
    call = [sys.executable, str(LAUNCHER), "--usine", str(usine_file)]
    if args.memory_mb:
        call += ["--memory-mb", str(args.memory_mb)]
    if args.timeout:
        call += ["--timeout", str(args.timeout)]
    return [*call, *rest]


def check_budget(usine_file: Path, args: argparse.Namespace) -> None:
    """Before anything is created: the post's budget (key `run-budget`), read by the launcher."""
    done = subprocess.run(
        launcher(usine_file, args, "--check"), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if done.returncode != 0:
        raise Failure("budget", f"{LAUNCHER_CODES.get(done.returncode, 'lanceur borné')} : {done.stderr.strip()}")


def launch(trial: Trial, settings: Settings, plugin: Path, usine_file: Path, args: argparse.Namespace) -> None:
    """Run the command of the key in the throwaway project, under the bounded launcher (ticket #66)."""
    marks = {
        "plugin": str(plugin), "budget": settings.budget, "ticket": str(trial.ticket),
        "feature": FEATURE, "base": trial.base,
    }
    words = [MARKER.sub(lambda found: marks[found.group(1)], word) for word in settings.command]
    done = subprocess.run(
        launcher(usine_file, args, "--", *words),
        cwd=trial.clone, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0:
        why = LAUNCHER_CODES.get(done.returncode)
        tail = done.stderr.strip()[-300:] or done.stdout.strip()[-300:]
        raise Failure("lancement", f"{why or f'`{words[0]}` a rendu le code {done.returncode}'} : {tail}")


def head_tried(plugin: Path) -> str:
    """The commit of the plugin under trial, and whether its tree has changes the commit does not hold."""
    def git(*words: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(plugin), *words], capture_output=True, text=True, encoding="utf-8", errors="replace"
        )

    try:
        head = git("rev-parse", "HEAD")
        sha = head.stdout.strip() if head.returncode == 0 else ""
        if not sha:
            return "inconnue (le plugin n'est pas dans un dépôt git)"
        return f"{sha} (arbre modifié)" if git("status", "--porcelain", "--", ".").stdout.strip() else sha
    except OSError:
        return "inconnue (git ne se lance pas)"


def report(
    trial: Trial, head: str, failure: Failure | None = None, checks: int = 0, cleanup: list[str] | None = None
) -> None:
    """The result, one fact per line: what the pull request of the release copies, then the cleanup."""
    lines = ["RESULTAT: FAIL" if failure else "RESULTAT: PASS"]
    if failure:
        lines += [f"ETAPE: {failure.stage}", f"RAISON: {failure.reason}"]
    lines += [f"TETE: {head}", f"DEPOT: {trial.repo}"]
    if trial.ticket is not None:
        lines.append(f"TICKET: #{trial.ticket}")
    if trial.pr is not None:
        lines.append(f"PR: #{trial.pr}")
    if not failure:
        lines.append(f"CHECKS: {checks} verts")
    print("\n".join([*lines, *(cleanup or [])]))


def origin_repo(project: Path) -> str | None:
    """The `owner/name` of the project's `origin` on GitHub, None when it has none or it is elsewhere."""
    try:
        done = subprocess.run(
            ["git", "-C", str(project), "remote", "get-url", "origin"], capture_output=True, text=True, encoding="utf-8"
        )
    except OSError:
        return None
    match = ORIGIN.search(done.stdout.strip()) if done.returncode == 0 else None
    return match.group(1) if match else None


def scratch_root() -> str | None:
    """Where the throwaway folder goes: the session's `TMPDIR` or `TEMP`, read when the trial runs."""
    return os.environ.get("TMPDIR") or os.environ.get("TEMP") or None


class Call(argparse.ArgumentParser):
    """Its usage errors exit with the call's own code, 2."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"e2e_trial: {message}", file=sys.stderr)
        raise SystemExit(WRONG_CALL)


def absent_message(key: str) -> str:
    return f"SANS-OBJET (clé `{key}` absente)"


def single(config: dict[str, list[str]], key: str) -> str | None:
    """The one value of `key`, None when it is absent; a repeated key has no single value."""
    values = config.get(key)
    if not values:
        return None
    if len(values) > 1:
        raise ValueError(f"la clé `{key}` est répétée : elle vaut une seule ligne")
    return values[0]


def read_settings(config: dict[str, list[str]], *, bounded: bool) -> Settings | list[str]:
    """The settings of the trial, or the `SANS-OBJET` lines of the keys that are absent.

    `bounded` says the bound of the launch is given by the options: `run-limits` is then not needed.
    A key present and ill-formed raises `ValueError`: nothing is completed with a guess.
    """
    values = {key: single(config, key) for key in E2E_KEYS}
    absent = [absent_message(key) for key, value in values.items() if value is None]
    if not bounded and single(config, LIMITS_KEY) is None:
        absent.append(absent_message(LIMITS_KEY))
    if absent:
        return absent
    repo, command, budget = values[REPO_KEY], values[COMMAND_KEY], values[BUDGET_KEY]
    assert repo is not None and command is not None and budget is not None
    if not REPO.fullmatch(repo):
        raise ValueError(f"la clé `{REPO_KEY}` vaut `<propriétaire>/<nom>`, pas `{repo}`")
    try:
        if not float(budget) > 0:
            raise ValueError
    except ValueError:
        raise ValueError(f"la clé `{BUDGET_KEY}` vaut un nombre de dollars positif, pas `{budget}`") from None
    try:
        words = shlex.split(command)
    except ValueError as error:
        raise ValueError(f"la clé `{COMMAND_KEY}` est illisible ({error})") from None
    used = set(MARKER.findall(command))
    if unknown := sorted(used - set(MARKERS)):
        raise ValueError(
            f"la clé `{COMMAND_KEY}` cite des marques inconnues : {', '.join('{' + name + '}' for name in unknown)} "
            f"(admises : {', '.join('{' + name + '}' for name in MARKERS)})"
        )
    if lacking := [name for name in REQUIRED_MARKERS if name not in used]:
        raise ValueError(
            f"la clé `{COMMAND_KEY}` doit citer {', '.join('{' + name + '}' for name in lacking)} : "
            "sans elles l'essai ne porterait pas sur le plugin à essayer, sous le plafond"
        )
    return Settings(repo, words, budget)


def main(argv: list[str] | None = None) -> int:
    parser = Call(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--projet", default=".", help="the project that runs the trial (default: .)")
    parser.add_argument("--plugin", help="the plugin to try (default: the one that holds this script)")
    parser.add_argument("--usine", help="the usine.md to read (default: <projet>/docs/agents/usine.md)")
    parser.add_argument("--memory-mb", dest="memory_mb", type=bounded_run.positive, help="memory limit, in MB")
    parser.add_argument("--timeout", type=bounded_run.positive, help="delay of the launch, in seconds")
    parser.add_argument("--wait-checks", dest="wait_checks", type=bounded_run.non_negative, default=600,
                        help="seconds to wait for the checks of the pull request (default: 600)")
    parser.add_argument("--poll-seconds", dest="poll_seconds", type=bounded_run.positive_float, default=15,
                        help="seconds between two reads of the checks (default: 15)")
    parser.add_argument("--id", help="the name of the trial (default: the time and a random part)")
    args = parser.parse_args(argv)
    project = Path(args.projet)
    usine_file = Path(args.usine) if args.usine else project / usine.CONFIG_PATH
    try:
        config = bounded_run.read_config(str(usine_file))
        settings = read_settings(config, bounded=bool(args.memory_mb and args.timeout))
    except ValueError as error:
        print(f"e2e_trial: {error}", file=sys.stderr)
        return WRONG_CALL
    if isinstance(settings, list):
        print("\n".join(settings))
        return 0
    if origin_repo(project) == settings.repo:
        print(
            f"e2e_trial: le dépôt d'essai `{settings.repo}` est le dépôt de ce projet : "
            "l'essai crée et ferme des tickets, il ne tourne jamais sur le dépôt qu'il protège",
            file=sys.stderr,
        )
        return WRONG_CALL
    name = args.id or f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    plugin = Path(args.plugin) if args.plugin else Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="forge-e2e-", dir=scratch_root()) as folder:
        trial = Trial(settings.repo, name, Path(folder))
        head = head_tried(plugin)
        failure: Failure | None = None
        checks = 0
        try:
            try:
                check_budget(usine_file, args)
                trial.prepare(f"{datetime.now(timezone.utc):%Y-%m-%d}")
                launch(trial, settings, plugin, usine_file, args)
                trial.find_pr()
                checks = trial.wait_green(args.wait_checks, args.poll_seconds)
            except Failure as error:
                failure = error
        finally:
            cleanup = trial.clean_up()  # whatever happened, including an interruption
        if failure is None and trial.failed:
            failure = Failure("nettoyage", "le nettoyage de l'essai n'a pas tenu : voir les lignes NETTOYAGE")
        report(trial, head, failure, checks, cleanup)
    return 1 if failure else 0


if __name__ == "__main__":
    sys.exit(main())
