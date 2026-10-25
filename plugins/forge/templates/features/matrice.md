---
feature: F-NNNN
document: matrice
date: AAAA-MM-JJ
---

# F-NNNN : matrice de traçabilité

Une ligne par identifiant d'élément de la source (clé `product-source`), de la source à la preuve : le
ticket qui le couvre, le test qui le prouve, l'écran de `parcours.md` qui le montre, la capture qui
le fige, l'état et la date du dernier jugement. `scripts/matrice.py` la lit. La recette (`feature-verify`)
et la clôture (`feature-close`) se jugent contre elle.

Les colonnes, dans cet ordre : `Identifiant`, `Lot` (celui de la spec, vide : « sans lot »), `Ticket`
(`#n`), `Test` (`fichier::nom`), `Écran` (`Écran <n>` du parcours), `Capture` (le fichier), `État`,
`Jugé le` (AAAA-MM-JJ).

## Les états

Une seule règle, que tout agent applique de la même façon :

- `tenu` : le critère l'est en entier. Il exige une preuve (un test ou une capture) et la date du jugement ;
  un `tenu` sans preuve est refusé.
- `partiel` : tenu en partie. La date du jugement est obligatoire.
- `absent` : pas construit. L'état de départ, sans date.
- `contraire` : le produit pose l'inverse, même en partie. La date du jugement est obligatoire.
- `écarté` : mis de côté par l'auteur de la source (clé `source-author`), son accord cité par une ligne
  `Écarté :` sous le tableau. Sans cet accord, la ligne est refusée.

Seuls `tenu` et `écarté` comptent dans la couverture ; la clôture exige 100 %.

## Matrice

| Identifiant | Lot | Ticket | Test | Écran | Capture | État | Jugé le |
|---|---|---|---|---|---|---|---|
| <EXI-01> | <L1> | <#n> | <fichier::nom du test> | <Écran 1> | <fichier de capture> | absent | |

## Éléments écartés

<Une ligne par élément écarté, sur le modèle de la spec ; supprimer cette section s'il n'y en a pas.>

- Écarté : <identifiant> | accord : <fichier> | <AAAA-MM-JJ> | <rôle>
