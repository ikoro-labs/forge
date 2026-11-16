# Les incidents, chacun devenu un contrôle

Un incident réparé dans la mémoire d'un poste, ou par une consigne, revient sur un autre poste ou
dans un autre projet. `/forge:incident` écrit donc, pour tout incident `sev1` ou `sev2` et pour tout
incident de l'usine elle-même, une revue sans blâme qui finit sur un correctif qu'une machine ou le
jeu de référence tient. Une consigne seule, ou une entrée de mémoire seule, n'est jamais un correctif
suffisant.

## La revue

Le gabarit est `plugins/forge/templates/incident.md`. Une revue est un fichier Markdown du dossier de
la clé `incident-dir`, nommé `AAAA-MM-JJ-<sujet>.md` :

| Partie | Ce qu'elle dit |
| --- | --- |
| `Date`, `Origine`, `Classe` | le jour de l'incident, `sev1`, `sev2` ou `usine`, la classe du correctif |
| `## Faits` | au moins un fait daté (`- AAAA-MM-JJ : ...`), avec sa source |
| `## Cause` | le mécanisme, jamais une personne |
| `## Ce qui l'a laissé passer` | le contrôle qui manquait, ou celui qui ne regardait pas là |
| `## Correctif` | une ligne `- Correctif :` par correctif, de la forme que la classe exige |

## La classe du correctif

- `mécanique` : une règle qu'une machine peut vérifier. Le correctif est `#<n>`, le ticket
  `ready-for-agent` d'un contrôle déterministe et de son test, ou `existant : <contrôle> ; <test>`
  quand le dépôt tient déjà ce contrôle.
- `jugement` : ce que seul un agent voit. Le correctif est `cas : <dossier>`, un cas ajouté au jeu de
  référence (`docs/jeu-de-reference.md`).

Une revue a une classe ; un incident qui demande les deux s'écrit en deux revues. Avant de proposer
un nouveau contrôle, on cherche s'il existe déjà : une garde ou un script du dépôt, et son test.

## Les commandes

```sh
uv run --no-project --quiet python plugins/forge/scripts/incident.py check <revue> --projet .
uv run --no-project --quiet python plugins/forge/scripts/incident.py dir .
uv run --no-project --quiet python plugins/forge/scripts/factory_slo.py incidents . [--json]
```

- `check` lit la revue et sort en 1 en listant ses fautes : un champ ou une section qui manque, une
  `Date` qui n'en est pas une, un `<...>` du gabarit resté en place, aucun fait daté, aucun correctif,
  un correctif qui n'est qu'une consigne, un correctif dont la forme n'est pas celle de la classe. Avec
  `--projet`, les chemins qu'un correctif cite doivent exister sous la racine du projet. Un numéro de
  ticket n'est pas vérifié : le script ne lit pas GitHub. Il ne juge pas le ton : « sans blâme » reste
  l'affaire du lecteur.
- `dir` dit le dossier de la clé `incident-dir`. Sans la clé : « sans objet (clé `incident-dir`
  absente) », aucun dossier par défaut.
- `factory_slo.py incidents` compte les revues du dossier par classe (`mécanique`, `jugement`), une
  classe sans revue valant 0. Une revue que `check` refuse n'est comptée dans aucune classe, est
  listée avec ses fautes, et fait sortir la commande en 1. Le décompte ne figure pas dans le rapport
  des objectifs de service : il n'a pas de cible, et aucun objectif ne s'y appuie.

## Dans ce dépôt

La clé `incident-dir` vaut `docs/incidents`. La première application y est la revue des quatre
incidents que le ticket #61 a constatés : le test rouge qui a épuisé la mémoire du poste, le
`push -u` qui a changé la configuration git partagée, le coder qui a écrit hors de son worktree, et
le `Closes #n` d'un commit de branche qui a fermé un ticket. Chaque revue dit où est son contrôle et
son test, ou le ticket qui le portera. `tests/test_incident_reviews.py` rejoue `check` sur chacune.

Ce qui n'a pas été éprouvé : aucun cas de la classe `jugement` n'existe encore dans ce dépôt, aucun
des quatre incidents n'en relevant, et `/forge:incident` n'a pas tourné dans une vraie session.
