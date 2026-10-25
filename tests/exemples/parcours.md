---
feature: F-0000
document: parcours
date: 2026-10-25
---

# F-0000 : parcours du relevé des compteurs d'eau

Exemple inventé, neutre, rempli sur le gabarit de parcours ; les tests du plugin le font passer par
`parcours.py`, contre la source d'exemple.

## Écran 1 : Liste des compteurs

- Voit : « Compteurs de la résidence » ; « Saisir un relevé »
- Fait : choisit un compteur dans la liste
- Suivant : Écran 2
- Source : EXI-01, G1

## Écran 2 : Saisie du relevé

- Voit : « Date du relevé » ; « Numéro du compteur » ; « Index (m3) » ; « Enregistrer »
- Fait : saisit la date, le numéro et l'index, puis enregistre
- Suivant : Écran 3
- Source : EXI-01, EXI-02, C01

## Écran 3 : Signature et envoi

- Voit : « Index inférieur au précédent » ; « Signer » ; « Envoyer au syndic »
- Fait : signe puis envoie le relevé
- Suivant : fin
- Source : EXI-03
