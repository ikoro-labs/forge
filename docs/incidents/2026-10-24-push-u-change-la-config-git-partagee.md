# Un `git push -u` change la configuration git que partagent tous les worktrees

- Date : 2026-10-24
- Origine : usine
- Classe : mécanique

## Faits

- 2026-10-24 : le ticket #61 constate qu'un `push -u` a changé la configuration git partagée, et que la parade n'était consignée que dans la mémoire d'un poste. Le dépôt ne porte pas la date de l'incident lui-même : le champ `Date` est le jour de ce constat.
- 2026-10-25 : la PR #86 (ticket #65) fait refuser au coder, par le garde `guard_coder`, `git push` avec `-u`, `--set-upstream`, `-f` ou `--force`, et `git config` en écriture.

## Cause

Les worktrees d'un dépôt partagent un seul fichier de configuration : `git push -u` y écrit la branche amont, et l'écriture d'un coder change l'état que lisent les autres sessions du dépôt.

## Ce qui l'a laissé passer

Aucun garde ne regardait les options de `git push` d'un coder : la parade était consignée dans la mémoire d'un poste, pas dans un contrôle. Depuis la PR #86, le garde refuse la commande elle-même, y compris derrière un `cd` ou un `git -C`.

## Correctif

- Correctif : existant : plugins/forge/hooks/guard_coder.py ; tests/test_guard_coder.py
