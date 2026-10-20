# Règles git du dépôt forge

## Branches et PR

- Une branche par changement, depuis `main` : `feat/<slug>`, `fix/<slug>`, `docs/<slug>`,
  `test/<slug>` ou `chore/<slug>`, le slug en français, en minuscules et avec des tirets.
- Jamais de commit ni de push sur `main` : tout passe par une PR, fusionnée par un commit de fusion.
- Le titre d'une PR suit le format des commits. Son corps suit `.github/pull_request_template.md`
  et cite son ticket (`Closes #n`, ou `Refs #n` quand la PR n'en livre qu'une partie).

## Commits

- Conventional Commits, en français : `<type>(<zone>): <ce qui change>`, la zone étant celle du
  plugin touchée (`hooks`, `coder`, `qc`, `feature-build`, `release`...). Exemple :
  `fix(hooks): fermer proprement une session Windows`.
- Le corps dit pourquoi, et ce qui a été essayé ; il finit par `Refs #n` ou `Closes #n`, puis par la
  ligne `Co-Authored-By` de l'agent qui a écrit le commit.
- Un commit par critère vert, jamais « wip ».

## Publier une version

C'est la session forge qui publie, en suivant **Contribuer et publier** du `README.md` :

1. Une PR `chore(release): forge <X.Y.Z>, <ce qu'elle apporte>` change `version` dans
   `plugins/forge/.claude-plugin/plugin.json` et ouvre l'entrée du `CHANGELOG.md`.
2. Une fois fusionnée, le tag annoté `forge--v<X.Y.Z>` (deux tirets) est posé sur le commit de
   fusion de `main`, puis poussé. Un tag ne se déplace ni ne se supprime une fois poussé.
