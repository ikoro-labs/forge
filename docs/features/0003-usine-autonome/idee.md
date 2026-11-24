---
feature: F-0003
document: idee
titre: usine autonome, l'humain n'intervient que là où il l'a choisi
porteur: ikoro-labs
etat: active
demande_par: interne, l'humain de la clé accepting-human (échange du 2026-11-24 avec la session forge)
issue: 340
date: 2026-11-24
---

# F-0003 : usine autonome, l'humain n'intervient que là où il l'a choisi

## L'idée, en une phrase

L'usine mène seule un ticket jusqu'à la fusion et la version dans presque tous les cas (cible : une
PR sur cent demande l'humain), et l'humain reprend la main brique par brique, par un interrupteur
qu'il pose là où il le veut, au lieu de règles qui le rappellent par défaut.

## D'où elle vient

Un échange du 2026-11-24 entre l'humain et la session forge, résumé ici sans le reprendre mot pour
mot. L'humain a demandé ce qui manque pour que tout le flux soit autonome, avec le sentiment que
l'usine elle-même bloque l'autonomie. Les faits lus ce jour-là :

- l'objectif `human-touch` (PR ouvertes qui portent `needs-your-attention` ou une ligne `Attention`
  autre que « aucune », hors chemins protégés) valait 28,86 % sur 30 jours (`factory_slo.py report`,
  2026-11-24 vers 16:34 UTC ; dénominateur non relu), pour une cible écrite de 10 % que l'humain veut
  porter à 1 % ;
- sur les 40 dernières PR fusionnées, 26 l'ont été par l'agent et 14 par l'humain ; chaque fusion
  humaine depuis le soir du 2026-11-23 touche un chemin protégé (`gh pr list --state merged`,
  2026-11-24) ;
- l'essai de bout en bout, condition de la publication par l'agent, est en `FAIL` depuis son premier
  lancement du 2026-11-24 (`docs/agents/usine.md`, section « Essai de bout en bout ») ;
- l'approbation du propriétaire du code vient d'un compte dont l'agent détient le jeton : ce n'est
  pas une identité distincte (`docs/agents/usine.md`, clé absente `pr-cap-raiser`) ;
- le filtre de permissions du poste a refusé à l'agent un push `--force-with-lease` que l'humain
  avait autorisé, puis l'arrêt de conteneurs restés en marche alors que la mémoire du poste manquait
  pour rejouer les tests ;
- en ouvrant l'issue de suivi de cette feature, le garde du budget des tickets a réservé la place de
  l'issue alors qu'un autre garde, celui de la forme du corps, refusait ensuite la création : dix
  minutes d'attente avant de pouvoir recommencer, deux fois de suite (`guard_ticket_budget.py`,
  `RESERVATION_SECONDS`).

L'avis du `forge:staff-engineer` (cases réservées H1, H3 et H4 de la matrice) est posté sur le
ticket #280 : relancer l'essai de bout en bout, traiter le refus du push forcé, distinguer
l'identité d'approbation, puis une clé qui dit qui fusionne sur un chemin protégé.

## Qui l'a demandée

L'humain de la clé `accepting-human`, pour l'usine elle-même : interne, la règle d'entrée de ce
dépôt (les besoins viennent de ses tickets) l'admet par l'issue de suivi.

## Premières questions

- Les interrupteurs par brique : quelles briques (fusion, version, chemins protégés, poste), une clé
  par brique ou une seule clé à plusieurs valeurs, et le rendu « sans objet » quand elle manque.
- Les chemins protégés : qui fusionne une PR qui en touche un, et à quelles conditions l'agent le
  peut (par exemple un garde seulement renforcé, avec un test rouge sur la base).
- L'identité d'approbation : un compte ou une application que l'agent ne détient pas, ou l'abandon
  de l'approbation du propriétaire du code au profit d'une autre preuve.
- L'essai de bout en bout : le faire passer, et ce que vaut la publication tant qu'il échoue.
- Les permissions du poste : ce que l'agent peut faire seul pour libérer de la mémoire ou arrêter un
  conteneur, et où l'humain l'écrit (ses réglages, pas le plugin).
- Les cibles des objectifs de service : viser l'optimum, `human-touch` à 1 % compris, et proposer
  avec un relevé des pratiques les deux durées qui n'ont pas de cible donnée.
