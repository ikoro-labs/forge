# Un test rouge épuise la mémoire du poste

- Date : 2026-10-24
- Origine : usine
- Classe : mécanique

## Faits

- 2026-10-24 : le ticket #61 constate que l'épuisement de la mémoire d'un poste, causé par un test rouge, a été réparé dans la mémoire du poste et pas dans le plugin. Le dépôt ne porte pas la date de l'incident lui-même : le champ `Date` est le jour de ce constat.
- 2026-11-15 : la PR #214 (ticket #66) livre `bounded_run.py` : une borne de mémoire et de délai pour toute commande, et le budget du poste entier lu avant le lancement.
- 2026-11-15 : `base_replay.py` et `commit_replay.py`, qui rejouent les tests d'une PR pour `forge:qc-gate`, posent leur borne par la même fonction `run_bounded`.
- 2026-11-16 : la version 1.14.0 publie ce lanceur et les clés `run-limits` et `run-budget`.
- 2026-11-17 : le ticket #61 (partie 2) fait refuser par `guard_coder` toute suite que le coder lance sans le lanceur.

## Cause

Un test lancé par un agent n'avait pas de borne de mémoire commune à tous les agents : un test rouge a pu épuiser la mémoire du poste entier, que se partagent les sessions et les sous-agents.

## Ce qui l'a laissé passer

Aucun contrôle ne bornait les suites que lance le coder, ni ne regardait la mémoire disponible du poste avant de lancer. Depuis la PR #214, la borne est mécanique pour les rejeux de `forge:qc-gate` (un script, pas une consigne). Elle restait une consigne du prompt du coder pour les suites qu'il lance lui-même : aucun garde ne refusait une commande de test lancée sans le lanceur. Depuis le ticket #61 (partie 2), `guard_coder` refuse `python -m unittest`, `pytest` et toute ligne de `ci-replay` ou de `red-replay` qui n'est pas passée par `bounded_run.py --`, et donne la forme bornée.

## Correctif

- Correctif : existant : plugins/forge/scripts/bounded_run.py ; tests/test_bounded_run.py
- Correctif : existant : plugins/forge/hooks/guard_coder.py ; tests/test_guard_coder_bound.py
