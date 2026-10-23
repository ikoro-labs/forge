---
name: feature-status
description: "Dire où en est chaque feature et la commande suivante à lancer, lu dans les en-têtes des documents du dossier des features (clé feature-dir). Ne modifie rien."
argument-hint: "[F-NNNN]"
disable-model-invocation: true
---

# Où en sont les features

Le projet décrit son usine dans `docs/agents/usine.md` ; ce skill en lit la clé `feature-dir`. Sans
elle, il n'y a pas de dossier des features : dis-le et arrête-toi.

1. `git fetch origin`, puis lis, sur `origin/<branche par défaut>`, l'en-tête de chaque document de
   chaque dossier `NNNN-<slug>/` (ou du seul F-NNNN demandé) : `etat` de `idee.md`, `statut` de
   `cadrage.md`, `spec.md`, `design.md`, `recette.md` et `README.md`. Lis-les avec
   `git show origin/<base>:<chemin>`, pas dans ta copie de travail, qui peut être en avance ou en
   retard.
2. **L'étape** se déduit du tableau de la chaîne de
   `${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md` : la dernière étape dont le document
   existe, et s'il est `en-revue` ou `accepte`. Entre la spec acceptée (et le design s'il existe) et
   la recette, l'état des sous-issues de l'issue de suivi (`issue:` de `idee.md`) dit si l'on en est
   aux tickets ou à la construction :
   `gh api repos/{owner}/{repo}/issues/<n>/sub_issues --jq '.[] | [.number, .state] | @tsv'`.
3. `gh pr list --state open --search "Feature: F-"` : les documents en cours de relecture.
4. Rends un tableau court : feature, étape, ce qui attend qui (une relecture, une acceptation par un
   humain de la clé `accepting-human`, une commande), et la commande suivante. Signale une feature
   du rôle `hors-perimetre` ou `abandonnee` (clé `feature-state` : ses valeurs, sinon ces mots)
   sans la compter comme en retard. Lis `etat` par cette clé ; une valeur qu'aucun rôle ne porte
   est signalée telle quelle.

Ne modifie rien. Si un en-tête est illisible, ou contredit un autre (une spec acceptée sous un
cadrage en revue), dis-le tel quel au lieu de deviner l'étape.
