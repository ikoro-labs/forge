# Matrice des droits de décision du dépôt forge

Ce que l'humain (`accepting-human` de `docs/agents/usine.md`) délègue à `forge:staff-engineer`
(technique, gouvernance) et à `forge:product-owner` (produit, formulation, priorité dans le
périmètre), et ce qu'il se réserve. La clé `decision-matrix` de `usine.md` désigne ce fichier ; les
deux agents le lisent, et leur ligne `MATRIX_CELL` cite l'identifiant de la case qu'ils appliquent
(`T3`, `P2`, `H1`...).

L'objectif posé le 2026-11-20 est une usine autonome : l'humain ne valide rien dans la discussion et
ne lit que les tickets et les PR qui portent `needs-your-attention`. La matrice délègue donc toute
classe de décision, sauf ce qui est difficile à défaire ou hors de portée des agents (section
« Réservé à l'humain »).

## Règle commune aux classes déléguées

Une décision déléguée se poste en commentaire du ticket ou de la PR concernés, sous la forme
`Décision (<agent>, <case>)`, avec la décision, sa raison et sa source (`chemin:ligne`). L'humain la
relit après coup ; il peut y revenir par un commentaire, et rien n'attend sa lecture. Une case dit
`VETO: yes` seulement quand elle demande en plus `needs-your-attention`. Une question qu'aucune case
ne couvre rend `RESERVED`, avec la recommandation de l'agent.

## Techniques et gouvernance : `forge:staff-engineer`

| Case | Classe de décision | Décideur | Veto | Origine |
| --- | --- | --- | --- | --- |
| `T1` | Correctif d'un défaut relevé par le juge (`BLOCKER`, `MINOR`) : corriger comme le juge le recommande, ou ne pas corriger et dire pourquoi | `forge:staff-engineer` | no | #16, #17 |
| `T2` | Choix d'implémentation dans le périmètre d'un ticket que la spec ne fixe pas, dont la voie sûre quand deux corrections se valent (refuser plutôt que contourner, échouer fermé plutôt qu'ouvert) | `forge:staff-engineer` | no | #17 |
| `T3` | Suite d'un `MINOR` ou d'une `NOTE` du juge : corrigée dans la PR quand elle tient dans ses critères, sinon commentée sur le ticket existant ; un ticket nouveau ne naît pas d'une suite, seulement d'un motif que l'humain a admis | `forge:staff-engineer` | no | #25, #26 |
| `T4` | Nouvelle clé de `usine.md`, ou changement du contrat que lisent les projets consommateurs (forme d'une sortie lue par un script, variable de passation) : documenté dans le gabarit, la clé absente rend « sans objet » | `forge:staff-engineer` | no | #77 |
| `T5` | Changement d'un garde (`guard_git`, `guard_coder`, `guard_readonly`) ou de `hooks.json` : la décision de forme est déléguée, la fusion de la PR reste à l'humain (`H1`) | `forge:staff-engineer` | no | #77 |
| `T6` | Découpage d'un ticket en parties (`Refs #n`), dont le plafond de trois PR par ticket | `forge:staff-engineer` | no | #77 |
| `T7` | Changement d'une règle du dépôt (`CLAUDE.md`, `.claude/rules/`) ou d'un gabarit | `forge:staff-engineer` | no | #77 |
| `T8` | Risque de sécurité prouvé dont le correctif est réversible (une PR le défait) : le correctif se décide et se fusionne par la voie ordinaire ; sans correctif réversible, `H5` | `forge:staff-engineer` | no | #77 |
| `T9` | Deux textes acceptés qui se contredisent : l'option la plus prudente, et la contradiction dite dans le commentaire | `forge:staff-engineer` | yes | #77 |

## Produit, formulation, priorité : `forge:product-owner`

| Case | Classe de décision | Décideur | Veto | Origine |
| --- | --- | --- | --- | --- |
| `P1` | Formulation de la documentation (`README.md`, `docs/`, `CHANGELOG.md`), d'un message affiché à l'utilisateur, d'un libellé, d'une story ou d'un critère d'acceptation | `forge:product-owner` | no | #77 |
| `P2` | Priorité et ordre de travail dans le périmètre : quel ticket prêt passe en premier, quelle partie d'un ticket réparti est livrée d'abord | `forge:product-owner` | no | #77 |
| `P3` | Parcours d'une commande ou d'un skill côté utilisateur (ce qu'il voit, dans quel ordre, ce qui l'arrête) dans une feature ou un ticket acceptés | `forge:product-owner` | no | #77 |

Une question produit qui est en fait technique part vers `forge:staff-engineer` (verdict
`TECHNICAL`), et inversement une question technique qui change ce que voit l'utilisateur part vers
`forge:product-owner`.

## Réservé à l'humain : `accepting-human`

Ce qui est difficile à défaire, ou qu'aucun agent ne peut faire. L'agent rend `RESERVED`, nomme la
case, donne sa recommandation et pose `needs-your-attention`.

| Case | Décision ou geste réservé | Raison |
| --- | --- | --- |
| `H1` | Fusionner une PR qui touche un `protected-path` de `usine.md` | Ces chemins tiennent les gardes des agents et `CODEOWNERS`, qui les garde : un agent ne s'en juge pas lui-même. |
| `H2` | Publier une version (le tag `forge--v<X.Y.Z>`) | Un tag poussé ne se déplace ni ne se supprime. La montée de l'épingle est une PR que l'agent fusionne sur ACCEPT (2026-11-21). |
| `H3` | Protection des branches, réglages du dépôt, changement de compte ou de permission | Hors de la portée des agents, et un mauvais réglage ouvre une voie que la revue ne couvre pas. |
| `H4` | Cette matrice : l'ajout, le retrait ou le changement d'une case | Elle dit ce que l'humain délègue ; lui seul la tranche. |
| `H5` | Un risque de sécurité prouvé sans correctif réversible | Un geste qu'on ne défait pas se décide avec lui. |

## Ce que cette matrice ne couvre pas

- Aucune doctrine de métier : la clé `domain-arbiter` est absente, le plugin n'a pas de métier propre.
- L'entrée d'une feature au périmètre suit la clé `entry-gate`, absente de `usine.md` : tant qu'elle
  l'est, `forge:product-owner` la rend `RESERVED`, la matrice ne peut pas la déléguer.
