---
feature: F-NNNN
document: conception
date: AAAA-MM-JJ
expert: <rôle ou compte de l'expert métier, celui de la clé `source-author`>
---

# F-NNNN : conception avec l'expert

Le document vivant d'une conception guidée (`/forge:feature-guide`). Il se remplit question par
question, dans les mots de l'expert, et il se relit et se commente pendant qu'il se remplit. Une fois
que l'expert l'a validé en entier, il devient la source de la feature (clé `product-source`).

Deux états, et seulement deux :

- `proposé` : une rédaction de l'agent, que l'expert n'a pas encore validée. Une correction de
  l'expert réécrit la ligne, qui reste `proposé` jusqu'à son « oui » sur la rédaction corrigée.
- `validé` : l'expert l'a validée, avec son nom et la date. Seul le « oui » de l'expert le pose :
  l'agent n'écrit `validé` qu'en recopiant ce « oui », jamais de son chef.

Chaque identifiant suit le format du comptage (`EXI-01`, `C01`, `G0`) : il est stable, et il reste
celui de la spec, du parcours et de la matrice.

## Ce que le produit doit faire

| Identifiant | Proposition | État | Validé par | Le |
|---|---|---|---|---|
| <EXI-01> | <une exigence, dans les mots de l'expert, avec son critère mesurable> | proposé | | |

## Les contrôles et les règles

| Identifiant | Proposition | État | Validé par | Le |
|---|---|---|---|---|
| <C01> | <le calcul, la tolérance et l'effet, dans l'unité du métier> | proposé | | |

## Les gabarits et les conventions

| Identifiant | Proposition | État | Validé par | Le |
|---|---|---|---|---|
| <G1> | <la structure et les règles du gabarit> | proposé | | |

## Le parcours voulu

Les écrans, dans l'ordre où l'expert les vit, avec les mots exacts de l'écran. Ils deviennent
`parcours.md`.

- <Écran 1 : nom> : <ce que l'expert y voit, ce qu'il y fait> (proposé)

## Les questions ouvertes

<Ce que l'expert n'a pas encore tranché, une ligne chacune. Vide quand tout est tranché.>

## Historique

<Une ligne par rédaction corrigée ou refusée : la date, ce que l'agent avait proposé, ce que
l'expert a dit.>
