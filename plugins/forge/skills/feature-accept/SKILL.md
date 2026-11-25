---
name: feature-accept
description: "Accepter un document d'une feature (cadrage, spec, design, recette, livree) : seul geste qui écrit statut accepte, tapé par un humain de la clé accepting-human, ou lancé par le modèle quand la clé agent-autonomy est on (alors accepte_via: agent-autonomy, et jamais avec des points ouverts)."
argument-hint: F-NNNN <cadrage | spec | design | recette | livree>
---

# Accepter un document

Avant tout, applique `${CLAUDE_PLUGIN_ROOT}/autonomie.md` : lancé par le modèle plutôt que tapé par
l'humain, ce skill ne s'exécute que si la clé `agent-autonomy` de `docs/agents/usine.md` l'ouvre. Clé
absente : n'écris rien, n'ouvre ni branche ni PR, et rends à l'humain la commande exacte, avec ses
arguments : `/forge:feature-accept F-NNNN <document>`.

Cette commande est l'acceptation. Elle se lance de deux façons, et le document dit laquelle :

- **tapée** par un humain de la clé `accepting-human` : elle s'exécute comme toujours. Si l'humain
  écrit « j'accepte » en conversation sans la taper, rappelle-lui de la taper, et n'écris rien ;
- **lancée par le modèle**, la clé `agent-autonomy` étant `on` : le modèle accepte à la place de
  l'humain, qui relit après coup. Il n'accepte jamais un document qui garde des points ouverts (étape 3).

1. **Qui accepte** : étape 1 de `${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md`. Tapée : un
   nom qui n'est pas dans la clé `accepting-human` (la partie gauche de `<user.name git> |
   <identifiant court>`) : refuse. Lancée par le modèle : exige que la clé `accepting-human`
   existe, et ne compare pas `git config user.name`, qui est le nom de l'humain de la session, pas
   celui de l'agent ; l'identifiant écrit à l'étape 4 est celui de la première ligne de la clé.
   Sans la clé, personne ne peut accepter, ni tapée ni lancée par le modèle : dis-le et arrête-toi.
2. **Quoi.** Le document existe et est `en-revue`. Ses prérequis sont acceptés : la commande de la
   clé `feature-gate`, avec `F-NNNN <document>`, doit passer ; sans la clé, vérifie-les à la main
   dans les en-têtes, selon le tableau de la chaîne du protocole, et dis que la porte est « sans
   objet (clé feature-gate absente) ».
3. **Ce qu'il engage.** Affiche en cinq lignes au plus : ce que le document décide, ses décisions
   prises par défaut, et sa section « Points ouverts ». Tapée, si des questions restent ouvertes,
   dis lesquelles et demande confirmation avant d'écrire. Lancée par le modèle, avec des points
   ouverts, n'écris pas `accepte` : passe chaque point à `forge:product-owner` (question produit)
   ou à `forge:staff-engineer` (question technique), selon la clé `decision-matrix`, comme
   l'étape 3 de `autonomie.md` le dit.
   - Un point rendu `RESERVED` : le document reste `en-revue`, la PR reçoit `needs-your-attention`
     avec le point, la case citée et ta recommandation, et tu arrêtes là : l'humain décide.
   - Tous les points rendus `DECIDED` : le skill du document écrit chaque décision, avec sa raison
     et sa ligne `MATRIX_CELL`, et retire le point de la section (`feature-frame` pour un cadrage,
     `feature-spec` pour une spec, `feature-design` pour un design, `feature-verify` pour une
     recette, `feature-close` pour la livraison). Puis relance `feature-accept` : sans point
     ouvert, elle poursuit à l'étape 4.
4. **Écrire**, dans l'en-tête seulement : `statut: accepte`, `accepte_par: <l'identifiant
   court de la ligne de la clé `accepting-human`, ou son nom si la ligne est sans ` | `>`,
   `accepte_le: AAAA-MM-JJ`. Lancée par le modèle, ajoute `accepte_via: agent-autonomy` : il dit
   que l'acceptation n'est pas une frappe de l'humain. Tapée, n'écris pas `accepte_via`. Rien
   d'autre ne change dans le document.
5. **Livrer.** Sur la branche de la PR du document si elle est ouverte, sinon sur une branche
   `docs/F-NNNN-accept-<document>` : lance d'abord la commande de la clé `feature-catalog-command`
   (étape 7 du protocole : sans argument, depuis la racine, un code non nul arrête avant le commit,
   les fichiers changés entrent dans le commit). Les hooks git du projet tournent, commit
   `docs(features): accept F-NNNN <document>` (au format de la clé `git-rules` si elle en dit
   plus), push. Le commit est la trace de l'acceptation. Lancée par le modèle, le corps du commit
   porte la ligne `accepte_via: agent-autonomy`, et le corps de la PR (celle du document, ou
   une PR nouvelle selon l'étape 7 du protocole) répète `accepte_via: agent-autonomy`.
6. **Dire la suite**, telle que `/forge:feature-status F-NNNN` la donne. Après une spec :
   `/forge:feature-design F-NNNN`, ou le découpage en tickets s'il n'y a pas de design.
