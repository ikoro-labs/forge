---
feature: F-NNNN
document: conception
date: AAAA-MM-JJ
expert: <rôle ou compte de l'expert métier, celui de la clé `source-author`>
---

# Conception avec l'expert (F-NNNN)

<!-- Le titre ne commence pas par l'identifiant de la feature : une ligne qui commence par un
identifiant est un élément de la source pour le comptage. -->

Le document vivant d'une conception guidée (`/forge:feature-guide`). Il se remplit question par
question, dans les mots de l'expert, et il se relit et se commente pendant qu'il se remplit. Une fois
que l'expert l'a validé en entier, il devient une source du projet (clé `product-source`) : cette clé
vaut pour toutes les features, et le comptage de chaque spec lit tous ses fichiers.

Deux états, et seulement deux :

- `proposé` : une rédaction de l'agent, que l'expert n'a pas encore validée. Une correction de
  l'expert réécrit la ligne, qui reste `proposé` jusqu'à son « oui » sur la rédaction corrigée.
- `validé` : l'expert l'a validée, avec son nom et la date. Seul le « oui » de l'expert le pose :
  l'agent n'écrit `validé` qu'en recopiant ce « oui », jamais de son chef.

Chaque identifiant suit le format du comptage, et il est stable : il reste celui de la spec, du
parcours et de la matrice. Il ne peut heurter ni celui d'une autre conception ni celui d'une source
déjà déclarée, car le comptage fond deux identifiants égaux en un seul élément :

- **Un élément neuf** porte le numéro de la feature dans son identifiant : la lettre du type, le
  numéro à quatre chiffres de `F-NNNN`, un tiret, puis le rang (`EXI0042-01`, `C0042-01`, `G0042-1`
  pour `F-0042`). Les `NNNN` des exemples ci-dessous sont à remplacer par ce numéro.
- **Un élément que la source déjà déclarée porte** garde son identifiant d'origine, sans préfixe :
  c'est le même élément, il se compte une fois, et la spec le reprend une fois.

## Ce que le produit doit faire

| Identifiant | Proposition | État | Validé par | Le |
|---|---|---|---|---|
| <EXINNNN-01> | <une exigence, dans les mots de l'expert, avec son critère mesurable> | proposé | | |

## Les contrôles et les règles

| Identifiant | Proposition | État | Validé par | Le |
|---|---|---|---|---|
| <CNNNN-01> | <le calcul, la tolérance et l'effet, dans l'unité du métier> | proposé | | |

## Les gabarits et les conventions

| Identifiant | Proposition | État | Validé par | Le |
|---|---|---|---|---|
| <GNNNN-1> | <la structure et les règles du gabarit> | proposé | | |

## Le parcours voulu

Les écrans, dans l'ordre où l'expert les vit, avec les mots exacts de l'écran. Ils deviennent
`parcours.md`.

- <Écran 1 : nom> : <ce que l'expert y voit, ce qu'il y fait> (proposé)

## Les questions ouvertes

<Ce que l'expert n'a pas encore tranché, une ligne chacune. Vide quand tout est tranché.>

## Historique

<Une ligne par rédaction corrigée ou refusée : la date, ce que l'agent avait proposé, ce que
l'expert a dit.>
