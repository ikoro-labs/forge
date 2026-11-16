# Usine du dépôt forge

La configuration de l'usine qui développe le plugin `forge` dans ce dépôt. Le gabarit,
`plugins/forge/templates/usine.md`, documente chaque clé ; une clé absente d'ici rend son étape
« sans objet ». Les clés absentes et leur raison sont en fin de fichier.

## Personnes et décisions

- `accepting-human` : `ikoro-labs`

## Domaines et règles du dépôt

- `domain-rules` : `.claude/rules/forge.md`
- `git-rules` : `.claude/rules/git.md`
- `merge-method` : `merge`
- `pr-template` : `.github/pull_request_template.md`

## Features

- `feature-dir` : `docs/features`

## Rejeu et contrôles

- `ci-replay` : `uv run --no-project --quiet python -m unittest discover -s tests`
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
échouer. Le motif `-p {name}` choisit le fichier dans `tests/`.

- `test-path` : `tests/`
- `red-replay` : `uv run --no-project --quiet python -m unittest discover -s tests -p {name}`

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

## Incidents

Les revues sans blâme que `/forge:incident` écrit (ticket #61), une par incident `sev1`, `sev2` ou
de l'usine, avec la classe de leur correctif. `factory_slo.py incidents` les compte par classe.

- `incident-dir` : `docs/incidents`

## Revue

Ce qu'aucun agent ne fusionne, même sur ACCEPT : la CI, l'épingle de l'usine de ce dépôt, le
manifeste de la marketplace, et les gardes qui tiennent les agents eux-mêmes.

- `protected-path` : `.github/`
- `protected-path` : `.claude/settings.json`
- `protected-path` : `.claude-plugin/marketplace.json`
- `protected-path` : `plugins/forge/hooks/hooks.json`
- `protected-path` : `plugins/forge/hooks/guard_`

## Hooks

La suite de tests de ce dépôt, dont la sortie se raccourcit quand elle passe.

- `trimmed-command` : `python -m unittest discover -s tests`

## Clés absentes

- `sla` : `sev2` n'a pas de délai de prise en charge, et l'étape où court le délai de 30 jours de
  `sev3` n'est pas dite ; aucun délai n'est deviné, la clé reste absente jusqu'à la décision de
  l'humain (ticket #76).
- `decision-matrix` : aucune matrice encore ; `forge:staff-engineer` et `forge:product-owner`
  rendent tout en `RESERVED`, et chaque décision revient à l'humain qui accepte.
- `domain-arbiter`, `domain-skill`, `glossary` : le plugin n'a pas de métier propre.
- `product-source`, `entry-gate` : les besoins viennent des tickets de ce dépôt.
- `test-skill` : la façon d'écrire les tests est dans `.claude/rules/forge.md`.
- `feature-gate` : la porte se vérifie à la main, dans les en-têtes des documents.
- `install` : la suite n'a que la bibliothèque standard ; `uv` choisit le Python.
- `baselines`, `size-check`, `trace-check`, `trace-replay`, `review-grid` : aucun outil encore.
- `em-dash-allowances` : aucun fichier n'en tolère.
- `doc-frontmatter`, `doc-index`, `doc-cap` : ce dépôt n'a décidé ni de `type` de frontmatter, ni
  d'index, ni de plafond pour sa documentation (`README.md`, `docs/`, `CHANGELOG.md`).
- `readonly-agent`, `readonly-command` : aucun agent du dépôt en plus de ceux du plugin.
- `agent-cache-dir`, `rescue-bundle-dir` : ce dépôt n'a pas de dossier de caches d'agents ni de bundles
  de sauvetage à tenir ; le ménage d'`agent_cleanup.py` y retire seulement les worktrees et les
  branches `worktree-agent-*`, qui ne lisent aucune clé.
