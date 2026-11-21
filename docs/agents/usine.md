# Usine du dépôt forge

La configuration de l'usine qui développe le plugin `forge` dans ce dépôt. Le gabarit,
`plugins/forge/templates/usine.md`, documente chaque clé ; une clé absente d'ici rend son étape
« sans objet ». Les clés absentes et leur raison sont en fin de fichier.

## Personnes et décisions

- `accepting-human` : `ikoro-labs`

La matrice des droits de décision : ce que `forge:staff-engineer` et `forge:product-owner` tranchent
seuls, et ce que l'humain se réserve (fusion d'un chemin protégé, c'est-à-dire d'un garde des
agents, réglages du dépôt, la matrice elle-même, un risque de sécurité sans correctif réversible).

- `decision-matrix` : `docs/agents/decisions.md`

L'autonomie des agents, ouverte par l'utilisateur de ce dépôt le 2026-11-20 : le modèle peut lancer
les skills de la chaîne des features, et leurs questions vont d'abord aux agents de décision.
`feature-accept` reste tapé par l'humain, et la publication reste réglée par `release-trigger`. Elle
n'agit qu'une fois l'épingle montée à une version qui la lit (1.18.0).

- `agent-autonomy` : `on`

Quand l'agent publie une version, choisi par l'humain le 2026-11-21 : cinq fusions en attente d'un tag,
ou deux jours d'attente pour la plus ancienne. L'agent ne publie seul que si les conditions de
`.claude/rules/git.md` tiennent ; sinon il ouvre la PR de version et la rend à l'humain.

- `release-trigger` : `5 | 2 j`

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

La borne de toute suite et de toute sonde, lue par `plugins/forge/scripts/bounded_run.py` : la
mémoire (2000 Mo) et le délai (300 s) de chaque commande, puis le budget du poste entier, que
partagent les sessions, les sous-agents et les workers : 4096 Mo disponibles au moins, une charge à
1 min de 12 au plus, 2 workers au plus, et jusqu'à 300 s d'attente avant de renoncer. L'attente est
le choix de ce dépôt, que le ticket ne fixait pas.

- `run-limits` : `2000 | 300`
- `run-budget` : `4096 | 12 | 2 | 300`

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

Les objectifs de départ de l'usine (ticket #76), lus par `plugins/forge/scripts/factory_slo.py` sur 30
jours glissants. L'humain a retenu le 2026-11-16 de mesurer pendant 30 jours sans rien bloquer :
chaque action de budget est `alert`, jamais `human-merge` ni `feature-freeze`. Les cibles sont à
réviser à la date de `slo-review-date`, sur le rapport des SLO ; changer une valeur reste une
décision de l'humain. `tokens-per-merge` n'a pas de ligne : sa cible n'est pas fixée.

- `release-tag` : `forge--v{version}`
- `slo` : `accept-round-1 | >= 80 % | 30`
- `slo` : `lead-time p90 | <= 24 h | 30`
- `slo` : `release-lag p90 | <= 24 h | 30`
- `slo` : `escaped-defects | <= 10 % | 30`
- `slo` : `change-failure | <= 10 % | 30`
- `slo` : `human-touch | <= 10 % | 30`
- `slo` : `main-green | >= 100 % | 30`
- `slo` : `judge-recall | >= 95 % | 30`
- `slo` : `false-accept | <= 0 % | 30`
- `slo-review-date` : `2026-12-16`
- `slo-issue` : `55`
- `budget-action` : `accept-round-1 | alert`
- `budget-action` : `lead-time p90 | alert`
- `budget-action` : `release-lag p90 | alert`
- `budget-action` : `escaped-defects | alert`
- `budget-action` : `change-failure | alert`
- `budget-action` : `human-touch | alert`
- `budget-action` : `main-green | alert`
- `budget-action` : `judge-recall | alert`
- `budget-action` : `false-accept | alert`

Les engagements de délai par gravité (ticket #76), lus par `factory_slo.py sla` et `queue`, que l'humain a
retenus le 2026-11-16. Ils sont tirés du ticket ; la prise en charge de `sev2` et de `sev3`, que le ticket
ne fixait pas, est une proposition de l'agent que l'humain a acceptée. Ils mesurent et ordonnent la file, sans rien bloquer.

- `sla` : `sev1 | 1 h | 24 h | 24 h`
- `sla` : `sev2 | 1 j | 3 j | 7 j`
- `sla` : `sev3 | 7 j | 30 j | 30 j`

## Incidents

Les revues sans blâme que `/forge:incident` écrit (ticket #61), une par incident `sev1`, `sev2` ou
de l'usine, avec la classe de leur correctif. `factory_slo.py incidents` les compte par classe.

- `incident-dir` : `docs/incidents`

## Revue

Ce qu'aucun agent ne fusionne, même sur ACCEPT : les gardes qui tiennent les agents eux-mêmes, et
`CODEOWNERS`, qui les garde. Choisi par l'humain le 2026-11-21 (« tout sauf les gardes ») : la CI,
l'épingle de ce dépôt et le manifeste de la marketplace passent à l'agent, sur ACCEPT.

- `protected-path` : `.github/CODEOWNERS`
- `protected-path` : `plugins/forge/hooks/hooks.json`
- `protected-path` : `plugins/forge/hooks/guard_`

## Hooks

La suite de tests de ce dépôt, dont la sortie se raccourcit quand elle passe.

- `trimmed-command` : `python -m pytest tests`

## Clés absentes

- `domain-arbiter`, `domain-skill`, `glossary` : le plugin n'a pas de métier propre.
- `product-source`, `entry-gate` : les besoins viennent des tickets de ce dépôt.
- `test-skill` : la façon d'écrire les tests est dans `.claude/rules/forge.md`.
- `feature-gate` : la porte se vérifie à la main, dans les en-têtes des documents.
- `install` : la suite n'a que la bibliothèque standard, et `pytest` (épinglé) arrive par `uv run --with` à chaque lancement ; `uv` choisit le Python.
- `gh-api-allow` : ce dépôt n'appelle que ce que le plugin appelle par `gh api` ; sa liste suffit.
- `baselines`, `size-check`, `trace-check`, `trace-replay`, `review-grid` : aucun outil encore.
- `em-dash-allowances` : aucun fichier n'en tolère.
- `doc-frontmatter`, `doc-index`, `doc-cap` : ce dépôt n'a décidé ni de `type` de frontmatter, ni
  d'index, ni de plafond pour sa documentation (`README.md`, `docs/`, `CHANGELOG.md`).
- `readonly-agent`, `readonly-command` : aucun agent du dépôt en plus de ceux du plugin.
- `agent-cache-dir`, `rescue-bundle-dir` : ce dépôt n'a pas de dossier de caches d'agents ni de bundles
  de sauvetage à tenir ; le ménage d'`agent_cleanup.py` y retire seulement les worktrees et les
  branches `worktree-agent-*`, qui ne lisent aucune clé.
