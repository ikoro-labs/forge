---
feature: F-0006
document: idee
titre: une usine modulaire par projet, un coeur non retirable et le reste au choix
porteur: ikoro-labs
etat: active
demande_par: interne, l'humain de la clé accepting-human (demande du 2026-11-28, relayée par sa session de pilotage)
issue: 414
date: 2026-11-28
---

# F-0006 : une usine modulaire par projet, un coeur non retirable et le reste au choix

## L'idée, en une phrase

Chaque projet choisit ses agents et ses portes depuis l'interface de pilotage : la page envoie une
demande, et l'usine la change en une PR qui modifie la configuration forge du projet dans son dépôt.

## D'où elle vient

Une demande de l'humain du 2026-11-28, faite dans sa session de pilotage et relayée à la session
forge, résumée ici sans la reprendre mot pour mot. La recommandation faite à l'humain, à confirmer au
cadrage :

- un coeur non retirable : l'agent d'audit du dépôt (F-0005) et les gardes de sécurité (aucun push
  direct sur la branche par défaut, aucun secret, les chemins protégés) ;
- tout le reste au choix ; retirer une porte affiche, en une phrase, le risque accepté.

Ce qui existe déjà, relevé le 2026-11-28 sur `main` `cc16c53` :

- une porte se coupe déjà par projet : l'étape qui lit une clé absente de `docs/agents/usine.md`
  se rend « sans objet (clé `<nom>` absente) » ; le gabarit `plugins/forge/templates/usine.md`
  documente chaque clé ;
- les clés qui bornent les pouvoirs de l'agent vivent dans `docs/agents/usine-gardes.md`, lues sur
  `origin/main`, et leur fusion revient à l'humain ;
- les agents du plugin ne se retirent pas par projet : le plugin les charge tous.

## Qui l'a demandée

L'humain de la clé `accepting-human`. La règle d'entrée est sans objet (clé `entry-gate` absente) :
la feature est admise par son issue de suivi. Priorité donnée par l'humain : après F-0003 et F-0005.

## Premières questions

- La liste des pièces (agents, portes, gardes) et, pour chacune, coeur ou au choix.
- Comment un agent se retire par projet, alors que le plugin les charge tous.
- Le chemin de la demande : la page, puis qui écrit la PR, et qui la fusionne quand elle touche
  `usine-gardes.md` (chemin protégé).
- La phrase de risque de chaque pièce retirable : où elle vit, et qui la tient à jour.
- Ce qui empêche une demande de retirer une pièce du coeur.
