---
feature: F-0002
document: livree
statut: accepte
accepte_par: ikoro-labs
accepte_le: 2026-11-28
accepte_via: agent-autonomy
destinataires: ikoro-labs, un nouvel arrivant, un auditeur
version: a1058a5 (tête de main, non publiée ; la dernière version publiée est forge 1.21.0)
base: a1058a5
date: 2026-11-25
---

# F-0002 : règles de code figées au cadrage et tenues par des hooks, telle que livrée

Ce fichier décrit ce qui existe sur `main` au commit `a1058a5`, lu dans le code et dans la recette
acceptée le 2026-11-25, pas ce qui était prévu.

## Ce qu'elle fait

Un projet qui utilise forge peut écrire ses règles de code dans `docs/agents/usine.md`, et l'usine les
tient à sa place, sans qu'un relecteur ait à s'en souvenir :

- une dépendance directe ajoutée sans décision acceptée est refusée à la revue (clé `stack`) ;
- un fichier que le lint du projet rejette est refusé dès son écriture, avec la fin de la sortie de
  l'outil (clé `lint-on-write`), et la sortie d'un formateur en échec est relayée (clé
  `format-on-write`) ;
- une liste de référence qui grandit, par exemple une liste d'exceptions au lint, est refusée
  (`never-weaken` en mode `raised-entry`) ;
- la carte des modules est rejouée sur la tête de chaque PR (clé `architecture-check`) ;
- un constat du juge qui revient de PR en PR est listé dans un commentaire, sans ouvrir de ticket
  (clé `recurring-finding`).

Une clé absente rend « sans objet (clé `<nom>` absente) », jamais `PASS` : un projet qui n'écrit rien
ne voit aucun changement.

## Comment s'en servir

La page `docs/regles-de-code.md` dit chaque clé, le format de sa ligne, le message d'un refus et le
geste de l'humain. Le gabarit `plugins/forge/templates/usine.md` porte une base de règles à copier :
une ligne ruff (complexité 10, 5 paramètres, 5 niveaux d'imbrication, version épinglée, `--preview`),
une carte des modules et un exemple de `stack`.

Ce qu'on voit une fois les clés écrites :

- à la revue, les lignes `OK`, `ADDED`, `UNLISTED`, `NO SOURCE`, `INVALID`, `NOT RUN` de la sonde 16
  et `PASS`, `FAIL`, `NOT RUN` de la sonde 17 dans le tableau de `forge:qc-gate` ; `forge:qc-conf` pose
  un `BLOCKER` `F-8` sur `UNLISTED` ou `NO SOURCE`, et `F-15` sur une sonde 17 en `FAIL` ;
- à l'écriture, le message `lint-on-write: ... failed on ...` d'`after_write` (au plus 20 lignes et
  2000 octets), et une ligne au journal des refus ;
- dans le rapport de `forge:slo`, `guard-refusals` limité aux trois gardes.

## Ses limites

- **Pas encore publiée.** Aucune version ne porte F-0002 : le cache de `forge--v1.21.0` n'a ni
  `stack_check.py` ni `recurring_findings.py`. Rien n'a encore tourné sur un projet consommateur ; la
  vérification en environnement cible de la recette attend la version suivante et la montée de
  l'épingle d'un projet.
- **Forge ne déclare aucune des nouvelles clés** (`stack`, `lint-on-write`, `architecture-check`,
  `recurring-finding`) : ses propres sondes 16 et 17 rendent « sans objet ».
- **La ligne ruff du gabarit n'a été essayée que sur forge**, où elle refuserait 88 fonctions
  existantes (C901 63, PLR0913 25, relevé de la PR #350).
- **Écosystèmes fermés** : `stack` ne lit que `pypi` (`uv.lock`) et `npm` (`package-lock.json`) ; une
  dépendance indirecte n'est pas comparée (son âge reste à la sonde 15).
- **Deux tests ne tournent que sous Windows** (un shim `.cmd`, l'objet job Win32) ; ils ne portent
  aucun critère.

## Où elle vit

| Quoi | Où |
|---|---|
| Code | `plugins/forge/scripts/stack_check.py`, `lockfiles.py`, `never_weaken.py` (`raised-entry`), `recurring_findings.py`, `factory_slo.py` (`guard-refusals`) ; `plugins/forge/hooks/after_write.py` (`lint-on-write`, `format-on-write`, journal des refus) ; sondes 16 et 17 de `plugins/forge/agents/qc-gate.md`, règles `F-8` et `F-15` de `plugins/forge/agents/qc-conf.md` ; gabarit `plugins/forge/templates/usine.md` |
| Décisions | séances de `seances/` (brainstorm et cadrage du 2026-11-22, spec et design du 2026-11-23) ; aucun ADR |
| Tests | `tests/test_stack_check.py`, `test_stack_probe_content.py`, `test_never_weaken.py`, `test_after_write.py`, `test_after_write_journal.py`, `test_architecture_probe_content.py`, `test_recurring_findings.py`, `test_rule_base_content.py`, `test_factory_slo_refus.py` : 181 passent, 2 ignorés sous Linux (recette, `c45a2da`) |
| Métriques et alertes | sondes 16 et 17 de `forge:qc-gate` ; refus de `never-weaken` ; message d'`after_write` ; journal `~/.claude/hooks/state/refusals/<AAAA-MM-JJ>.jsonl` ; `guard-refusals` de `forge:slo` ; commentaire de `recurring_findings.py` sur le ticket de la clé `slo-issue` |

## Historique

| Document | Acceptation |
|---|---|
| `idee.md` | écrite le 2026-11-22 (sans acceptation, comme toute idée) |
| `cadrage.md` | acceptée le 2026-11-23 |
| `spec.md` (critères A1 à A35) | acceptée le 2026-11-23 |
| `design.md` | accepté le 2026-11-23 |
| Tickets #304 à #313, PR #325 à #350 | fusionnées du 2026-11-24 au 2026-11-25 |
| `recette.md` | acceptée le 2026-11-25 (PR #352) |

L'issue de suivi est #291 ; elle se ferme une fois la PR de clôture fusionnée.
