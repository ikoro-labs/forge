# Procédure de relevé des compteurs d'eau d'une résidence

Exemple inventé, neutre, pour les tests du plugin.

## Exigences

- EXI-01 : chaque relevé porte la date, le numéro du compteur et l'index lu.
- EXI-02 : un index inférieur à l'index précédent est refusé.
- EXI-03 : le gardien signe le relevé avant l'envoi au syndic.

## Contrôles

- C01 : consommation = index lu moins index précédent, en mètres cubes ; au-delà de 3 fois la moyenne des six derniers relevés, avertissement.
- C02 : deux relevés d'un même compteur à moins de 20 jours d'écart partent en quarantaine.

## Gabarits

- G1 : fiche de relevé, une ligne par compteur, colonnes date, numéro, index, observation.
- G2 : convention de nommage des fichiers, `releve-AAAA-MM.csv`.

## Pièges

- P1 : un compteur remplacé repart de zéro, ce qui ressemble à un index inférieur.
