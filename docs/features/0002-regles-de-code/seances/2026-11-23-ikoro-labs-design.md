---
feature: F-0002
seance: 2026-11-23-ikoro-labs-design
participants: ikoro-labs (humain, a tapé `/forge:feature-design`), l'agent de la session forge, forge:staff-engineer (agent décideur)
sujet: préparer le design de F-0002 (modules touchés, coutures, découpage en tickets)
---

# Séance du 2026-11-23 : design de F-0002

Écrite pendant la séance, tour par tour, jamais réécrite ensuite. Une correction se fait dans une
séance suivante, qui cite celle-ci. Elle suit `2026-11-23-ikoro-labs-spec.md`, dont les décisions sont
reprises telles quelles. `forge:staff-engineer` n'écrit pas : l'agent de la session recopie sa réponse,
résumée, avec sa ligne `MATRIX_CELL`. Seule la synthèse finale de l'agent a été gardée ; le détail de ses
sources (fichier:ligne lus) reste à relire dans le code avant d'écrire `design.md`.

## Sources apportées

| Source | Où | Empreinte | Ce qui en est retenu |
|---|---|---|---|
| Spec acceptée de F-0002 | `spec.md` (acceptée le 2026-11-23, PR #301) | sans objet (versionné) | 35 critères A1 à A35, lots L1 à L3, contrôles C01 à C05 |
| Code lu à la base `30a4634` | `after_write.py`, `lockfile_age.py`, `never_weaken.py`, `factory_slo.py`, `agents/qc-gate.md`, `agents/qc-conf.md` | sans objet (versionné) | voir les réponses du tour 1 |

## Tours

### Tour 1

Questions techniques Q1 à Q8 à `forge:staff-engineer` : lecture du verrou, structure d'`after_write`,
place de `raised-entry`, sondes de `forge:qc-gate`, `recurring_findings.py`, chemins protégés,
frontière de confiance et observabilité, découpage.

**Réponse de `forge:staff-engineer` (synthèse rendue) :**

- Q1 : extraire un module `lockfiles.py` de l'analyse de verrou de `lockfile_age.py` (l.86 à 135), sans
  changer de comportement ; `stack_check.py` le réutilise.
- Q2 : un exécuteur d'`after_write` par clé, une échéance partagée (120 s) entre `format-on-write` et
  `lint-on-write`, `record()` du journal réutilisé ; le calcul de `guard-refusals` (`factory_slo.py:447`)
  reste limité aux trois gardes.
- Q3 : `raised-entry` s'ajoute dans `check_entry` de `never_weaken.py` (l.243).
- Q4 : deux sondes nouvelles en fin de `forge:qc-gate`, numérotées 16 (`stack_check`) et 17
  (`architecture-check`) ; critère F-28 ; les tests de contenu à étendre sont aux lignes 344 et 66 de leurs
  fichiers de test.
- Q5 : `recurring_findings.py` importe `factory_slo.py` (marqueur, lecture de `gh`), sans épinglage de
  version.
- Q6 : aucun lot ne touche un chemin protégé (`hooks.json`, `guard_*`).
- Q8 : dix tickets, aucun ADR déclenché. Ordre, avec les blocages entre parenthèses :
  1. extraction de `lockfiles.py` ;
  2. `stack_check.py` (1) ;
  3. sonde 16 et page de `docs/` (2) ;
  4. `raised-entry` (3) ;
  5. refonte d'`after_write` (aucun comportement changé) ;
  6. `lint-on-write` (5) ;
  7. journal des refus d'`after_write` et filtre de `guard-refusals` (6) ;
  8. sonde 17 (3) ;
  9. `recurring_findings.py` (3) ;
  10. gabarit `usine.md` (3, 4, 6, 8, 9).

Points à reporter dans le design :

- ne pas utiliser `tomllib` : la règle du dépôt fixe Python 3.10 ;
- un fichier `stack` absent à la tête vaut une liste vide ;
- `qc-gate.md:217` est déjà faux : il dit « 1 à 14 » (à corriger au ticket de la sonde 16).

Ligne rendue : `MATRIX_CELL: T2, T4, T6, T7 ; ordre en P2`, `REVERSIBLE: yes`, `VETO: no`,
`REFERENTIAL_UPDATE: timeout par défaut 600 s, code.claude.com/docs/en/hooks, 2026-11-23`.

Non vérifié par l'agent : la forme d'un verrou npm avec espaces de travail, le plafond du stderr d'un
hook, la commande ruff.

## Décidé

| Décision | Par | Va dans |
|---|---|---|
| dix tickets, dans l'ordre ci-dessus, aucun ADR | `forge:staff-engineer` (T2, T4, T6, T7) | design |
| extraction de `lockfiles.py` en prérefactoring, refonte d'`after_write` en prérefactoring | `forge:staff-engineer` | design |
| aucun chemin protégé touché | `forge:staff-engineer` | design |

## Resté ouvert

- Les fichier:ligne cités par l'agent n'ont pas été relus par l'agent de la session : à vérifier avant
  d'écrire `design.md`.
- Les trois points non vérifiés de l'agent (verrou npm avec espaces de travail, plafond du stderr,
  commande ruff) restent ceux de la section 20 de la spec.
