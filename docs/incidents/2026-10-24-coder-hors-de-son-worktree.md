# Un coder écrit hors de son worktree

- Date : 2026-10-24
- Origine : usine
- Classe : mécanique

## Faits

- 2026-10-24 : le ticket #61 constate qu'un coder a codé hors de son worktree, et que la parade n'était consignée que dans la mémoire d'un poste. Le dépôt ne porte pas la date de l'incident lui-même : le champ `Date` est le jour de ce constat.
- 2026-10-25 : la PR #86 (ticket #65) fait refuser au coder toute écriture et toute commande git hors de son worktree lié, et refuse un coder lancé sans worktree dès sa première écriture.

## Cause

Un coder lancé sans isolation a pour dossier de travail la copie principale du dépôt : ses écritures y arrivent, au milieu du travail des autres coders et de l'humain.

## Ce qui l'a laissé passer

Aucun contrôle ne vérifiait, côté coder, que son dossier était un worktree lié : le lancement avec isolation reposait sur l'orchestrateur. Depuis la PR #86, `guard_coder` lit le worktree depuis le dossier de l'événement et refuse l'écriture, par tout outil, sous un chemin qui n'est pas le sien.

## Correctif

- Correctif : existant : plugins/forge/hooks/guard_coder.py ; tests/test_guard_coder.py
