# Règles git du dépôt forge

## Branches et PR

- Une branche par changement, depuis `main` : `feat/<slug>`, `fix/<slug>`, `docs/<slug>`,
  `test/<slug>` ou `chore/<slug>`, le slug en anglais, en minuscules et avec des tirets.
- Jamais de commit ni de push sur `main` : tout passe par une PR, fusionnée par un commit de fusion.
- Le titre d'une PR suit le format des commits. Son corps suit `.github/pull_request_template.md`
  et cite son ticket (`Closes #n`, ou `Refs #n` quand la PR n'en livre qu'une partie).
- Les tickets, les titres et les corps de PR s'écrivent en anglais. Restent en français la section
  `Rapport d'agent` d'une PR et les réponses à l'humain.

## Commits

- Conventional Commits, en anglais, sujet et corps : `<type>(<zone>): <ce qui change>`, la zone
  étant celle du plugin touchée (`hooks`, `coder`, `qc`, `feature-build`, `release`...). Exemple :
  `fix(hooks): close a Windows session cleanly`.
- Le corps dit pourquoi, et ce qui a été essayé ; il finit par `Refs #n` ou `Closes #n`, puis par la
  ligne `Co-Authored-By` de l'agent qui a écrit le commit.
- Un commit par critère vert, jamais « wip ».

## Publier une version

C'est la session forge qui publie, en suivant `docs/contribuer.md` :

1. Une PR `chore(release): forge <X.Y.Z>, <ce qu'elle apporte>` change `version` dans
   `plugins/forge/.claude-plugin/plugin.json` et ouvre l'entrée du `CHANGELOG.md`.
2. Une fois fusionnée, le tag annoté `forge--v<X.Y.Z>` (deux tirets) est posé sur le commit de
   fusion de `main`, puis poussé. Un tag ne se déplace ni ne se supprime une fois poussé.

Quand ce dépôt déclare la clé `release-trigger`, l'agent publie lui-même, par `/forge:release` (voir
`docs/contribuer.md`). L'agent publie seul si, et seulement si, tous les SLO sont `tenu` (état calculé dans
l'heure), aucune action de `budget-action` n'est active, l'essai de bout en bout passe sur la tête de `main`
et aucun `sev1` n'est ouvert. Une condition qui manque, ou qu'on ne peut pas lire, vaut condition non
remplie : l'agent ouvre alors la PR de version, pose `needs-your-attention` avec la condition manquante, et
la publication revient à l'humain. Sans la clé, il ne publie rien. Les règles de tags côté serveur restent
un geste de l'humain ; la montée de l'épingle est une PR, que l'agent fusionne sur ACCEPT.
