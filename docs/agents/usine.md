# Usine du dépôt forge

La configuration de l'usine qui développe le plugin `forge` dans ce dépôt. Le gabarit,
`plugins/forge/templates/usine.md`, documente chaque clé ; une clé absente d'ici rend son étape
« sans objet ». Les clés absentes et leur raison sont en fin de fichier.

Ce fichier ne porte que des clés libres : une PR ordinaire le change (ticket #345). Les clés qui bornent
les pouvoirs de l'agent (`agent-autonomy`, `accepting-human`, `protected-path`, `run-limits`, `slo`...)
sont dans `docs/agents/usine-gardes.md`, un chemin protégé que le plugin lit tel que `origin/main` le tient.

## Personnes et décisions

La personne qui accepte (`accepting-human`) et l'autonomie des agents (`agent-autonomy`) sont dans
`usine-gardes.md`.

La matrice des droits de décision : ce que `forge:staff-engineer` et `forge:product-owner` tranchent
seuls, et ce que l'humain se réserve (fusion d'un chemin protégé, c'est-à-dire d'un garde des
agents, réglages du dépôt, la matrice elle-même, un risque de sécurité sans correctif réversible).

- `decision-matrix` : `docs/agents/decisions.md`

Quand l'agent publie une version, choisi par l'humain le 2026-11-21 (délai resserré le 2026-11-24) : une fusion
en attente d'un tag, ou deux jours d'attente pour la plus ancienne. L'agent ne publie seul que si les
conditions de `.claude/rules/git.md` tiennent ; sinon il ouvre la PR de version et la rend à l'humain.

- `release-trigger` : `1 | 2 j`

## Domaines et règles du dépôt

- `domain-rules` : `.claude/rules/forge.md`
- `git-rules` : `.claude/rules/git.md`
- `merge-method` : `merge`
- `pr-template` : `.github/pull_request_template.md`

## Features

- `feature-dir` : `docs/features`

## Rejeu et contrôles

- `ci-replay` : `uv run --no-project --quiet --with pytest==9.2.0 python -m pytest tests`
- `ci-replay` : `uv run --no-project --quiet --with ruff==0.17.3 ruff check plugins/forge tests`
- `ci-replay` : `uv run --no-project --quiet --with mypy==2.4.1 mypy`
- `ci-replay` : `claude plugin validate .`
- `ci-replay` : `claude plugin validate plugins/forge`

La sonde de rejeu de chaque commit (`commit_replay.py`) ne lance que ces deux commandes, ruff et mypy, sur
chaque commit avant la tête : la suite y passait 21 min pour 6 commits et 46 min pour 13 (ticket #331, demande
de l'humain du 2026-11-24). La tête rejoue chaque ligne de `ci-replay`.

- `ci-replay-light` : `uv run --no-project --quiet --with ruff==0.17.3 ruff check plugins/forge tests`
- `ci-replay-light` : `uv run --no-project --quiet --with mypy==2.4.1 mypy`

Les tests que la PR ajoute, rejoués par `forge:qc-gate` sur une copie de la base, où chacun doit
échouer. `{file}` choisit le fichier dans `tests/`, et `{report}` donne au rejeu le grain du test : la
commande y écrit un rapport JUnit XML, et chaque test ajouté ou changé qui passe sur la base est rendu.
Le `pytest` est celui de `ci-replay`, même version épinglée.

- `test-path` : `tests/`
- `red-replay` : `uv run --no-project --quiet --with pytest==9.2.0 python -m pytest {file} --junitxml={report}`

Les jobs de `.github/workflows/tests.yml`.

- `required-contexts` : `tests (ubuntu-latest)`
- `required-contexts` : `tests (windows-latest)`
- `required-contexts` : `validate`
- `required-contexts` : `lint`

## Objectifs de service

Les objectifs (`slo`) et leurs actions de budget (`budget-action`) sont dans `usine-gardes.md` : changer
une cible reste une décision de l'humain (ticket #76). Ici restent le gabarit du tag d'une version, la date
où revoir les cibles, sur le rapport des SLO, et l'issue de suivi où il se publie.

- `release-tag` : `forge--v{version}`
- `slo-review-date` : `2026-12-16`
- `slo-issue` : `55`

Les engagements de délai par gravité (ticket #76), lus par `factory_slo.py sla` et `queue`, que l'humain a
retenus le 2026-11-16. Ils sont tirés du ticket ; la prise en charge de `sev2` et de `sev3`, que le ticket
ne fixait pas, est une proposition de l'agent que l'humain a acceptée. Ils mesurent et ordonnent la file, sans rien bloquer.

- `sla` : `sev1 | 1 h | 24 h | 24 h`
- `sla` : `sev2 | 1 j | 3 j | 7 j`
- `sla` : `sev3 | 7 j | 30 j | 30 j`

L'étiquette d'un ticket dont le but est le délai de l'usine elle-même (décision de l'humain du 2026-11-28,
ticket #377) : `factory_slo.py queue` la range après `sev1` et avant tout autre ticket, sans geste de
l'humain. Elle doit exister sur le dépôt, l'agent ne la crée pas.

- `speed-label` : `factory-speed`

## Incidents

Les revues sans blâme que `/forge:incident` écrit (ticket #61), une par incident `sev1`, `sev2` ou
de l'usine, avec la classe de leur correctif. `factory_slo.py incidents` les compte par classe.

- `incident-dir` : `docs/incidents`

## Essai de bout en bout

L'essai de l'usine avant une version, par `plugins/forge/scripts/e2e_trial.py`, sur un dépôt d'essai public
que l'humain a créé le 2026-11-16 et qui n'est pas ce dépôt. Le plafond de 2.50 dollars est la valeur du
gabarit, reprise le 2026-11-24 sur l'accord de l'humain. La ligne de commande est celle du gabarit : un premier
essai l'a lancée le 2026-11-24 et a fini en `FAIL` à l'étape `checks`, le dépôt d'essai n'ayant alors aucun
workflow ; un workflow y a été fusionné depuis. La borne du lancement, `e2e-run-limits`, est dans
`usine-gardes.md` : elle remplace `run-limits` pour ce lancement, donc elle borne l'agent comme lui.

- `e2e-repo` : `ikoro-labs/forge-essai`
- `e2e-command` : `claude -p --plugin-dir {plugin} --max-budget-usd {budget} "/forge:feature-build {feature} --base {base}"`
- `e2e-budget-usd` : `2.50`

## Hooks

La suite de tests de ce dépôt, dont la sortie se raccourcit quand elle passe.

- `trimmed-command` : `python -m pytest tests`

## Clés absentes

- `domain-arbiter`, `domain-skill`, `glossary` : le plugin n'a pas de métier propre.
- `product-source`, `entry-gate` : les besoins viennent des tickets de ce dépôt.
- `test-skill` : la façon d'écrire les tests est dans `.claude/rules/forge.md`.
- `feature-gate` : la porte se vérifie à la main, dans les en-têtes des documents.
- `install` : la suite n'a que la bibliothèque standard, et `pytest` (épinglé) arrive par `uv run --with` à chaque lancement ; `uv` choisit le Python.
- `baselines`, `size-check`, `trace-check`, `trace-replay`, `review-grid` : aucun outil encore.
- `em-dash-allowances` : aucun fichier n'en tolère.
- `doc-frontmatter`, `doc-index`, `doc-cap` : ce dépôt n'a décidé ni de `type` de frontmatter, ni
  d'index, ni de plafond pour sa documentation (`README.md`, `docs/`, `CHANGELOG.md`).
- Les clés protégées absentes (`gh-api-allow`, `pr-cap-raiser`, `readonly-agent`...) sont en fin de `usine-gardes.md`.
- `agent-cache-dir`, `rescue-bundle-dir` : ce dépôt n'a pas de dossier de caches d'agents ni de bundles
  de sauvetage à tenir ; le ménage d'`agent_cleanup.py` y retire seulement les worktrees et les
  branches `worktree-agent-*`, qui ne lisent aucune clé.
