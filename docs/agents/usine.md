# Usine du dépôt forge

La configuration de l'usine qui développe le plugin `forge` dans ce dépôt. Le gabarit,
`plugins/forge/templates/usine.md`, documente chaque clé ; une clé absente d'ici rend son étape
« sans objet ». Les clés absentes et leur raison sont en fin de fichier.

## Personnes et décisions

- `accepting-human` : `ikoro-labs`

## Domaines et règles du dépôt

- `domain-rules` : `.claude/rules/forge.md`
- `git-rules` : `.claude/rules/git.md`
- `pr-template` : `.github/pull_request_template.md`

## Features

- `feature-dir` : `docs/features`

## Rejeu et contrôles

- `ci-replay` : `uv run --no-project --quiet python -m unittest discover -s tests`
- `ci-replay` : `uv run --no-project --quiet --with ruff==0.17.3 ruff check plugins/forge tests`
- `ci-replay` : `uv run --no-project --quiet --with mypy==2.4.1 mypy`
- `ci-replay` : `claude plugin validate .`
- `ci-replay` : `claude plugin validate plugins/forge`

Les tests que la PR ajoute, rejoués par `forge:qc-gate` sur une copie de la base, où chacun doit
échouer. Le motif `-p {name}` choisit le fichier dans `tests/`.

- `test-path` : `tests/`
- `red-replay` : `uv run --no-project --quiet python -m unittest discover -s tests -p {name}`

Les jobs de `.github/workflows/tests.yml`.

- `required-contexts` : `tests (ubuntu-latest)`
- `required-contexts` : `tests (windows-latest)`
- `required-contexts` : `validate`
- `required-contexts` : `lint`

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

- `decision-matrix` : aucune matrice encore ; `forge:staff-engineer` et `forge:product-owner`
  rendent tout en `RESERVED`, et chaque décision revient à l'humain qui accepte.
- `domain-arbiter`, `domain-skill`, `glossary` : le plugin n'a pas de métier propre.
- `product-source`, `entry-gate` : les besoins viennent des tickets de ce dépôt.
- `test-skill` : la façon d'écrire les tests est dans `.claude/rules/forge.md`.
- `feature-gate` : la porte se vérifie à la main, dans les en-têtes des documents.
- `install` : la suite n'a que la bibliothèque standard ; `uv` choisit le Python.
- `baselines`, `size-check`, `trace-check`, `trace-replay`, `review-grid` : aucun outil encore.
- `em-dash-allowances` : aucun fichier n'en tolère.
- `readonly-agent`, `readonly-command` : aucun agent du dépôt en plus de ceux du plugin.
