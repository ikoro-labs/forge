---
feature: F-NNNN
document: parcours
date: AAAA-MM-JJ
---

# F-NNNN : parcours

Le parcours voulu de la feature, écran par écran, dans l'ordre où l'utilisateur le vit. Il sert
d'entrée au rejeu en CI et à la revue de bout en bout, et ses libellés alimentent le glossaire
(section « Glossaire » de la spec, clé `glossary`). Il garde ce format simple : `scripts/parcours.py`
le lit.

Un écran par titre `## Écran <n> : <nom>`, numérotés de 1 sans trou, et quatre lignes :

- `Voit` : les libellés exacts de l'écran, chacun entre « et », séparés par `;` ; les mots du métier,
  jamais ceux de l'implémentation.
- `Fait` : ce que l'utilisateur y fait.
- `Suivant` : `Écran <n>` (un écran de ce parcours) ou `fin` ; le dernier écran finit par `fin`.
- `Source` : au moins un identifiant d'élément de la source (`EXI-01`, `RG-3.1`, `C01`, `G0`), séparés
  par des virgules, que l'écran tient. Un identifiant sans tiret s'écrit tel qu'à la source.

## Écran 1 : <nom de l'écran>

- Voit : « <libellé exact> » ; « <autre libellé exact> »
- Fait : <ce que l'utilisateur y fait>
- Suivant : Écran 2
- Source : <EXI-01>, <C01>

## Écran 2 : <nom de l'écran>

- Voit : « <libellé exact> »
- Fait : <ce que l'utilisateur y fait>
- Suivant : fin
- Source : <EXI-02>
