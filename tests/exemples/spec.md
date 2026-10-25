---
feature: F-0000
document: spec
statut: en-revue
destinataires: le gardien, puis l'agent qui implémente
base: 0000000
date: 2026-10-25
---

# F-0000 : relevé des compteurs d'eau

Exemple inventé, neutre, rempli sur le gabarit de spec ; les tests du plugin le font passer par le
comptage de `source_ids.py`.

## 1. Stories

1. En tant que gardien, je veux saisir le relevé d'un compteur, pour garder une trace datée.
2. En tant que gardien, je veux que les index incohérents soient refusés, pour ne rien envoyer de faux.
3. En tant que syndic, je veux recevoir un relevé signé, pour le facturer sans le ressaisir.
4. En tant que gardien, je veux être averti d'une consommation anormale, pour vérifier le compteur.
5. En tant que gardien, je veux que deux relevés rapprochés soient mis de côté, pour ne pas facturer deux fois.

## 2. Critères d'acceptation

| # | Story | Étant donné | Quand | Alors |
|---|---|---|---|---|
| A1 | 1 | un compteur n° 12 | le gardien saisit la date, le numéro et l'index 1 250 | le relevé est enregistré avec ces trois valeurs |
| A2 | 2 | un index précédent de 1 250 m3 | le gardien saisit 1 200 | le relevé est refusé avec le message « index inférieur » |
| A3 | 3 | un relevé non signé | le gardien l'envoie | l'envoi est refusé |
| A4 | 4 | une moyenne de 10 m3 sur six relevés | le gardien saisit une consommation de 31 m3 | un avertissement s'affiche |
| A5 | 5 | deux relevés du compteur n° 12 à 15 jours d'écart | le second est saisi | il part en quarantaine |

## 3. Éléments de la source

| Identifiant | Élément (résumé) | Tenu par |
|---|---|---|
| EXI-01 | date, numéro, index | story 1, A1 |
| EXI-02 | index inférieur refusé | story 2, A2 |
| EXI-03 | signature avant envoi | story 3, A3 |
| C01 | consommation et avertissement | story 4, A4 |
| C02 | quarantaine des relevés rapprochés | story 5, A5 |
| G1 | fiche de relevé | section 6 |
| G2 | nommage des fichiers | section 6 |
| P1 | compteur remplacé | section 13 |

## 4. Exigences atomiques

| Identifiant | Exigence | Critère mesurable | Classement | Niveau de preuve | Lot |
|---|---|---|---|---|---|
| EXI-01 | un relevé porte date, numéro, index | 3 champs non vides sur 100 % des relevés | obligatoire | P | L1 |
| EXI-02 | index décroissant refusé | refus si index < précédent, 0 faux négatif sur le jeu d'essai | obligatoire | O | L1 |
| EXI-03 | signature avant envoi | 0 envoi sans signature | obligatoire | P | L2 |

## 5. Contrôles codés

| Identifiant | Calcul exact | Tolérance par défaut | Effet |
|---|---|---|---|
| C01 | index lu moins index précédent, en m3 | 3 fois la moyenne des 6 derniers relevés | avertissement |
| C02 | jours entre deux relevés d'un même compteur | moins de 20 jours | quarantaine |

## 6. Gabarits et conventions

| Identifiant | Structure | Règles |
|---|---|---|
| G1 | une ligne par compteur : date, numéro, index, observation | l'observation est facultative |
| G2 | `releve-AAAA-MM.csv` | un fichier par mois |

## 7. Déroulé pas à pas

Première installation : 1. le gardien charge la liste des compteurs. 2. Il saisit les index de départ.
Livraison : 1. il saisit les relevés du mois. 2. Il signe. 3. Il envoie au syndic.
Relivraison : 1. il corrige un relevé refusé. 2. Il signe de nouveau. 3. Il renvoie.

## 8. Rôles

| Rôle | Fait | Ne fait pas |
|---|---|---|
| gardien | saisit, signe, envoie | facture |
| syndic | reçoit, facture | saisit |

## 9. Décisions prises et leur date

| Date | Décision | Par qui |
|---|---|---|
| 2026-10-20 | le relevé est mensuel | le syndic |

## 10. Critères transverses

- Tout refus dit sa raison en une phrase.

## 11. Lots et leur gel

| Lot | Contenu | Gelé le |
|---|---|---|
| L1 | saisie et contrôles | 2026-11-15 |
| L2 | signature et envoi | 2026-12-01 |

## 12. Comment elle peut échouer

| Risque | Mécanisme | Parade |
|---|---|---|
| envoi d'un faux relevé | index saisi à l'envers | refus de l'index inférieur (A2) |

## 13. Pièges et parades observés

| Identifiant | Piège | Parade |
|---|---|---|
| P1 | un compteur remplacé repart de zéro | une observation « compteur remplacé » lève le refus |

## 14. Non-goals

- Le paiement des factures.

## 15. Exigences non fonctionnelles

Saisie d'un relevé en moins de 2 secondes pour 200 compteurs.

## 16. Contrats, en prose

Entrée : une fiche de relevé. Sortie : un fichier mensuel. Erreur nommée : « index inférieur ».

## 17. Impact sur les règles du métier

Aucune règle du métier touchée : la procédure ne porte aucun chiffre réglementaire.

## 18. Décisions prises par défaut

| # | Décision | Fondement | Si le relecteur lit autrement |
|---|---|---|---|
| D1 | séparateur de colonnes : point-virgule | usage local | à changer dans G2 |

## 19. Confiance chiffrée

| Partie | Confiance | Raison |
|---|---|---|
| modèle | 80 % | procédure courte |
| périmètre | 70 % | lots non encore gelés |
| priorités | 60 % | classement à confirmer |

## 20. Points ouverts

Aucun.

## 21. Questions pour les entretiens

- Que fait-on d'un compteur illisible ?

## 22. Glossaire

| Terme | Définition |
|---|---|
| quarantaine | un relevé mis de côté, hors de l'envoi, en attente de vérification |
