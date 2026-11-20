---
feature: F-0001
document: idee
titre: forge alimente le poste de pilotage
porteur: ikoro-labs
etat: active
demande_par: interne, l'humain de la clé accepting-human (2026-11-20) et la session du poste de pilotage
issue: 263
date: 2026-11-20
---

# F-0001 : forge alimente le poste de pilotage

## L'idée, en une phrase

Un poste de pilotage extérieur au dépôt (une page que l'humain ouvre seule) lit l'état de l'usine
de chaque projet depuis des flux que forge produit, en lecture seule, au lieu que l'humain le
demande dans le chat ou dans un terminal.

## D'où elle vient

L'humain a demandé le 2026-11-20 de piloter l'usine depuis une seule page et de ne plus lire que
l'étiquette `needs-your-attention`. La session du projet qui tient cette page a dit, par billet
entre sessions, les cinq flux qu'il lui faut, et qu'elle ne relaie ni acceptation ni fusion :

1. les cases `RESERVED` ouvertes (ce que la matrice de décision réserve à l'humain et qui attend) ;
2. les verdicts des décideurs et des juges, avec `MATRIX_CELL` et `VETO` ;
3. les refus des hooks (le journal des refus) ;
4. l'état des passations de chaque session (en vol, file de revue, successeur) ;
5. la version de forge installée contre la version épinglée, par projet.

S'y ajoute la propagation d'une version publiée : un billet `info` aux sessions des projets
consommateurs, qui montent leur épingle.

## Qui l'a demandée

L'humain de la clé `accepting-human`, pour lui-même : interne, la règle d'entrée de ce dépôt (les
besoins viennent de ses tickets) l'admet par l'issue de suivi.

## Premières questions

- La forme des flux : un JSON par commande (`scripts/`), stable et versionné, ou un fichier écrit à
  chaque passage. Recommandation : une commande par flux, sortie JSON, un schéma documenté.
- Où les flux trouvent leurs sources : `refusal_journal.py`, `handoff_header.py`, les commentaires
  de verdict sur GitHub, l'épingle de `.claude/settings.json` du projet.
- La matrice de décision acceptée (`docs/agents/decisions.md`) réserve la publication et l'épingle
  à l'humain : la propagation se limite au billet, la montée reste au geste que la matrice dit,
  tant que l'humain ne change pas la matrice.
- Ce qui ne sort jamais d'un flux : aucun secret, aucun texte de l'humain mot pour mot (dépôt public).
