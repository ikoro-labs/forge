---
name: feature-accept
description: "Accepter un document d'une feature (cadrage, spec, design, recette, livree) : seul geste qui écrit statut accepte, réservé à un humain de la clé accepting-human qui tape la commande."
argument-hint: F-NNNN <cadrage | spec | design | recette | livree>
disable-model-invocation: true
---

# Accepter un document

Cette commande est l'acceptation. Elle n'existe que tapée par un humain de la clé
`accepting-human` : si l'humain écrit « j'accepte » en conversation sans la taper, rappelle-lui de
la taper, et n'écris rien.

1. **Qui accepte** : étape 1 de `${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md`. Un nom qui
   n'est pas dans la clé `accepting-human` (la partie gauche de `<user.name git> | <identifiant
   court>`) : refuse. Sans la clé, personne ne peut accepter : dis-le et arrête-toi.
2. **Quoi.** Le document existe et est `en-revue`. Ses prérequis sont acceptés : la commande de la
   clé `feature-gate`, avec `F-NNNN <document>`, doit passer ; sans la clé, vérifie-les à la main
   dans les en-têtes, selon le tableau de la chaîne du protocole, et dis que la porte est « sans
   objet (clé feature-gate absente) ».
3. **Ce qu'il engage.** Affiche en cinq lignes au plus : ce que le document décide, ses décisions
   prises par défaut, et sa section « Points ouverts ». Si des questions restent ouvertes, dis
   lesquelles et demande confirmation avant d'écrire.
4. **Écrire**, dans l'en-tête seulement : `statut: accepte`, `accepte_par: <l'identifiant
   court de la ligne de la clé `accepting-human`, ou son nom si la ligne est sans ` | `>`,
   `accepte_le: AAAA-MM-JJ`. Rien d'autre ne change dans le document.
5. **Livrer.** Sur la branche de la PR du document si elle est ouverte, sinon sur une branche
   `docs/F-NNNN-accept-<document>` : lance d'abord la commande de la clé `feature-catalog-command`
   (étape 7 du protocole : sans argument, depuis la racine, un code non nul arrête avant le commit,
   les fichiers changés entrent dans le commit). Les hooks git du projet tournent, commit
   `docs(features): accept F-NNNN <document>` (au format de la clé `git-rules` si elle en dit
   plus), push. Le commit est la trace de l'acceptation.
6. **Dire la suite**, telle que `/forge:feature-status F-NNNN` la donne. Après une spec :
   `/forge:feature-design F-NNNN`, ou le découpage en tickets s'il n'y a pas de design.
