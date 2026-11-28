---
feature: F-0005
document: idee
titre: un audit du dépôt à la connexion d'un projet, que l'usine ne peut pas retirer
porteur: ikoro-labs
etat: active
demande_par: interne, l'humain de la clé accepting-human (demande du 2026-11-28, relayée par sa session de pilotage)
issue: 413
date: 2026-11-28
---

# F-0005 : un audit du dépôt à la connexion d'un projet, que l'usine ne peut pas retirer

## L'idée, en une phrase

Quand un projet se branche sur l'usine, dépôt existant ou neuf, un agent d'audit passe le premier :
il lit le dépôt et sa documentation, dit en quelques lignes l'idée du projet, évalue le code, les
tests, la documentation et les risques, et écrit un rapport d'audit, avec ses propositions, qui
nourrit le cadrage de la première feature.

## D'où elle vient

Une demande de l'humain du 2026-11-28, faite dans sa session de pilotage et relayée à la session
forge, résumée ici sans la reprendre mot pour mot. L'interface de pilotage nommera cet agent à sa
façon ; forge le nomme librement. L'humain demande que l'agent soit obligatoire : aucune usine ne
peut le retirer (F-0006 en fait une pièce du coeur non retirable).

Ce qui existe déjà, relevé le 2026-11-28 sur `main` `cc16c53` :

- le skill `forge:improve-codebase-architecture` revoit l'architecture d'une zone et tranche ses
  candidats avec un humain, en session interactive ; les agents de l'usine ne l'exécutent pas ;
- brancher un projet, c'est aujourd'hui copier à la main le gabarit `plugins/forge/templates/usine.md`
  vers `docs/agents/usine.md` (`docs/installation.md`, étape 4) ; aucun audit ne le précède.

## Qui l'a demandée

L'humain de la clé `accepting-human`. La règle d'entrée est sans objet (clé `entry-gate` absente) :
la feature est admise par son issue de suivi. Priorité donnée par l'humain : après F-0003, avant
F-0006.

## Premières questions

- Ce que l'audit reprend de `forge:improve-codebase-architecture` (vocabulaire, rapport HTML) et ce
  qui change : un agent qui tourne seul, sur tout le dépôt, sans humain pour trancher.
- Ce que « obligatoire » veut dire pour un plugin : une porte qui refuse le premier cadrage sans
  rapport, un garde, ou une étape de l'installation.
- Le dépôt neuf : ce qu'il y a à auditer quand il n'y a presque rien.
- Où vit le rapport (dossier, format), et comment le cadrage le cite.
- Ce que l'agent lit sans risque : secrets, données réelles, dépôts privés.
