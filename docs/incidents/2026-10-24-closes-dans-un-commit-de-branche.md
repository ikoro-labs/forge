# Un `Closes #n` d'un commit de branche ferme un ticket que la PR cite en `Refs`

- Date : 2026-10-24
- Origine : usine
- Classe : mécanique

## Faits

- 2026-10-24 : le ticket #61 constate qu'un `Closes #n` écrit dans un commit de branche a fermé un ticket malgré une PR en `Refs`. Le dépôt ne porte pas la date de l'incident lui-même : le champ `Date` est le jour de ce constat.
- 2026-10-24 : le ticket #64 décrit le défaut : `guard_git` refuse une fusion dont le message ou la description ferme un ticket cité en `Refs`, mais ne lit pas les messages des commits de la branche. Avec un commit de fusion, GitHub les lit pourtant.
- 2026-11-16 : le tri du ticket #64 relit `main` à la version 1.14.0 : `guard_git` ne lit toujours pas les commits de la PR, et seule une consigne du skill `qc` demande de relire leurs messages avant de fusionner.

## Cause

En méthode de fusion `merge`, les commits de la branche arrivent sur la base avec leur message, et GitHub ferme le ticket qui suit un mot-clé de fermeture dans l'un d'eux. Le message d'un commit de branche est écrit pendant le travail, avant que la PR dise si elle livre le ticket en entier.

## Ce qui l'a laissé passer

Le garde `guard_git` lit le message de fusion et la description de la PR, pas les messages des commits. Le seul rempart des commits était une consigne de `forge:qc` (relire les messages avant de fusionner) et une entrée de mémoire d'un poste : une consigne seule, qui ne tient pas quand elle n'est pas lue. Le contrôle déterministe n'existe pas encore ; il est porté par le ticket #64.

## Correctif

- Correctif : #64
