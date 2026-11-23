---
feature: F-0002
document: design
statut: en-revue
destinataires: l'agent qui implémente (un forge:coder par ticket) ; forge:qc relit ; ikoro-labs (humain de la clé `accepting-human`) accepte par `/forge:feature-accept`
adr: aucun
feature-tickets: 10
base: 30a4634
date: 2026-11-23
---

# F-0002 : design

Le pourquoi est dans `cadrage.md`, le quoi dans `spec.md` (acceptée le 2026-11-23, PR #301). Ici : où
cela se construit, par quelles coutures, et dans quel ordre. Les réponses de `forge:staff-engineer`
(Q1 à Q8) sont dans `seances/2026-11-23-ikoro-labs-design.md` ; les lignes de code qu'il a citées ont été
relues à la base `30a4634` avant d'être écrites ici (section 10 pour ce qui ne l'a pas été).

Taille L, mais sans écran : pas de `parcours.md`. Aucune clé `feature-catalog-command` : pas de catalogue.

## 1. Contextes touchés

Tout vit sous `plugins/forge/`. Aucun contexte nouveau : quatre scripts ou hooks changent, trois scripts
sont ajoutés (`lockfiles.py`, `stack_check.py`, `recurring_findings.py`), deux agents et un skill changent de texte.

| Contexte | Ce qui change | Couture avec les autres |
|---|---|---|
| lecture des verrous (`scripts/lockfiles.py`, nouveau) | reçoit de `lockfile_age.py` `LOCAL_SOURCES`, `parse_uv_lock`, `parse_package_lock`, `read_at` (l.86 à 135), `Package` (l.55), `_quoted` (l.79), `PUBLIC_INDEX` et `PUBLIC_TARBALLS` (l.84-85), puis `direct_dependencies` | `lockfile_age.py` et `stack_check.py` l'importent ; les tests de `lockfile_age` passent sans changement |
| contrôle des dépendances (`scripts/stack_check.py`, nouveau) | compare les paquets directs ajoutés à la liste de la clé `stack` (C01) | importe `lockfiles.py` et `usine.py` (`hooks/`) ; son tableau est lu par `forge:qc-gate` (sonde 16) puis `forge:qc-conf` |
| `never-weaken` (`scripts/never_weaken.py`) | type `raised-entry` dans `check_entry` (l.243), C02 | le message d'un type inconnu (l.264) nomme le nouveau type ; entrée lue par la sonde 10 et `guard_git` déjà en place |
| écriture d'un fichier (`hooks/after_write.py`) | un exécuteur par clé (`format-on-write`, `lint-on-write`), échéance de 120 s partagée, fin de sortie relayée (C05), une ligne au journal par refus | importe `refusal_journal.record` ; `hooks.json` ne change pas (le hook est déjà branché) |
| journal des refus et SLO (`hooks/refusal_journal.py`, `scripts/factory_slo.py`) | `after_write` y écrit ; `guard_refusals` (l.434, filtre l.447) ne compte que `guard_git`, `guard_coder`, `guard_readonly` | le journal garde sa forme à sept champs |
| sondes du juge (`agents/qc-gate.md`, `agents/qc-conf.md`) | sondes 16 (`stack_check`) et 17 (`architecture-check`) ; `BLOCKER` de C01 et C03 | la liste « verbatim » de `## Sortie` et le mode rejeu (l.217) comptent les sondes |
| constat récurrent (`scripts/recurring_findings.py`, nouveau ; `skills/qc/SKILL.md`) | compte les PR distinctes par `F-n` ou `L-n`, réécrit un commentaire du ticket de la clé `slo-issue` (C04) | importe `factory_slo.py` (marqueur, lecture de `gh`) ; lancé par `forge:qc` après un verdict |
| gabarit et documentation (`templates/usine.md`, `docs/`) | une ligne par clé nouvelle, base de règles, page de `docs/` | lus par le projet consommateur |

**Carte des modules** (`forge:codebase-design`). Deux modules profonds, une interface étroite chacun :

- `lockfiles.py` : `read_at(root, ref, path)`, `parse_uv_lock`, `parse_package_lock`, `direct_dependencies(text,
  ecosystem)`. Cache : le format de `uv.lock` et de `package-lock.json`. Appelé par `lockfile_age.py` et
  `stack_check.py` seulement.
- `after_write.py` : `main()` seul est public. Cache : la grammaire `<motif> | <commande>`, le lanceur borné,
  l'échéance, le relais de sortie. Les deux clés partagent un seul exécuteur, jamais deux copies.

Les dépendances pointent vers `usine.py`, `handoff_header.py` et `refusal_journal.py`, qui ne dépendent d'aucun
de ces modules. `recurring_findings.py` importe `factory_slo.py` : le contraire est interdit.

## 2. Ports et adapters

Aucun port nouveau. Les scripts ont déjà deux bords, et la feature n'en ajoute pas :

- **git** : `read_at` lit un fichier à une révision par `git cat-file` et `git show`. `stack_check.py` lit la
  base, la tête, le verrou et la liste par cette seule fonction. Aucun accès réseau.
- **gh** : `recurring_findings.py` lit les commentaires de verdict et réécrit un commentaire par le lanceur `run`
  (type `Runner`, `factory_slo.py:92`) que `publish` reçoit en argument (`factory_slo.py:951`) : l'appel est
  injecté dans les tests, comme il l'est pour le rapport des SLO.

Le calcul (comparer des noms normalisés, compter des clés, compter des PR distinctes) est en fonctions pures,
sans E/S, que les tests appellent sans git ni `gh`.

## 3. Modèle de données

Pas de base de données, pas de migration. Trois formats de fichier, tous additifs :

- fichier `stack` : une ligne `<écosystème> | <paquet> | <source>` (G1). Nouveau, lu seulement quand la clé existe.
- journal des refus : mêmes sept champs (G4) ; `guard` prend la valeur `after_write`. `guard_refusals` compte aujourd'hui
  toute ligne du dépôt (`factory_slo.py:447`) : sans filtre, elle compterait ces refus, d'où le ticket 7.
- commentaire du constat récurrent : marqueur caché `<!-- forge-recurring-findings -->`, distinct du marqueur
  du rapport des SLO (`factory_slo.py:925`). Retour arrière : supprimer le commentaire.

Chaque clé nouvelle est absente par défaut et rend « sans objet (clé `<nom>` absente) » : un projet qui n'écrit
rien ne change pas. Le retour arrière d'un ticket est son revert.

## 4. Frontière de confiance

| Ce qui entre | Source | Où c'est validé | Qui décide |
|---|---|---|---|
| verrous et fichier `stack` de la tête | la PR, donc l'agent qui code | `stack_check.py` : écosystème fermé, trois champs, nom normalisé ; une ligne mal formée sort `INVALID`, jamais complétée (A2) | le juge lit la source de chaque ligne `ADDED` (F-8, A7) |
| chemin de la clé `stack`, commande de `architecture-check`, lignes de `lint-on-write` | `usine.md` **de la base**, jamais de la tête | la sonde écrit `usine-base.md` avant tout (A9, A25) : une PR ne lève pas la règle qui la juge | l'humain, par une PR sur `usine.md` |
| sortie d'un outil d'écriture | un processus lancé sans shell | bornée à 20 lignes et 2000 octets (C05) ; elle n'entre jamais au journal (A23) | sans objet : l'agent la lit pour corriger |
| commentaires de verdict des PR | `gh` | `recurring_findings.py` n'extrait que `F-n` et `L-n` par motif fermé ; le commentaire écrit ne porte que des identifiants, des numéros de PR et des dates | sans objet |
| commande de `lint-on-write` ou `architecture-check` | `usine.md` | lancée sans shell (`shlex`), avec `run-limits` pour la sonde, 30 s et 120 s pour l'écriture | l'humain qui écrit la clé |

Droits : aucun script n'écrit hors du scratchpad, sauf `recurring_findings.py` (un seul commentaire, sur le
ticket de `slo-issue`) et le journal local. Aucun accès réseau dans `stack_check.py`.

## 5. Observabilité

| Question | Métrique, alerte ou attribut de trace | Où c'est émis |
|---|---|---|
| Ça marche ? | une ligne `OK` ou `ADDED` par paquet ; `PASS` de la sonde 17 ; zéro `INVALID` | tableau de `forge:qc-gate`, rapport de `forge:qc` |
| Ça casse ? | `UNLISTED`, `NO SOURCE`, `FAIL`, `INVALID`, `NOT RUN` avec la raison ; refus d'écriture par règle (`lint-on-write`, `format-on-write`) | tableau du juge ; journal des refus (`guard` `after_write`) |
| Que voit-on dans la trace ? | la règle, le fichier et la fin de la sortie (G3) ; un refus répété se lit au journal par `rule` et `branch` | message de `after_write` ; commentaire du constat récurrent |

`guard-refusals` (SLO) reste l'indicateur des trois gardes : un refus d'écriture n'entre pas dans son
numérateur (A24). Les refus de `after_write` se lisent au journal, pas dans un SLO nouveau.

## 6. Coutures de test

La couture la plus haute est celle que les tests existants des mêmes modules utilisent déjà. Un bon test ici
nomme `F-0002 A<n>`, construit un vrai dépôt git jetable avec un vrai verrou, et ne simule que `gh` et le
registre.

1. **Le script lancé en sous-processus** (comme `tests/test_lockfile_age.py`) : `stack_check.py` sur un dépôt
   `tempfile.TemporaryDirectory()` à deux commits, avec un `uv.lock` produit par `uv lock` et non écrit à la
   main (voir la section 10). Il prouve A1, A2, A4 à A9 et A11 (A3 et A10 sont des tests de contenu, couture 4).
2. **Le hook par son entrée** (comme `tests/test_after_write.py`) : un événement JSON sur stdin, `HOME` et
   `USERPROFILE` isolés, la commande de la clé étant un petit script Python qui échoue avec une sortie connue.
   Il prouve A17 à A24.
3. **La fonction pure** : `never_weaken.check(entries, diff_text)` pour `raised-entry` (A12 à A16), le calcul
   de `recurring_findings` avec une liste de commentaires donnée (A29 à A33).
4. **Le contenu** : `qc-gate.md`, `qc-conf.md` et le gabarit lus comme texte (A3, A10, A26, A27, A34, A35), les
   tests de contenu existants étant étendus (`tests/test_lockfile_age_content.py:62` pour la liste verbatim,
   `tests/test_plugin_content.py:344` pour la même phrase).

Chaque test tourne sous Linux et sous Windows ; un test d'un seul système le dit par `skipUnless`.

## 7. Découpage en tickets

Dix tickets, `feature-tickets: 10`. Deux prérefactorings ouvrent leurs chaînes (1 et 5) et ne changent aucun
comportement. Aucun refactoring ne couvre tout le code : pas de ticket expand puis contract.

| # | Ticket | Couvre | Bloqué par | Lot |
|---|---|---|---|---|
| 1 | extraire `lockfiles.py` de `lockfile_age.py`, sans changer de comportement (prérefactoring) | T4 (les tests de `lockfile_age` passent à l'identique) | aucun | L1 |
| 2 | `stack_check.py` et `direct_dependencies` : C01 | A1, A2, A4 à A9, A11 | 1 | L1 |
| 3 | sonde 16 dans `qc-gate.md`, règle de `BLOCKER` dans `qc-conf.md`, ligne `stack` du gabarit, début de la page de `docs/` | A3, A10, A35 (début), T1 pour `stack` | 2 | L1 |
| 4 | `raised-entry` dans `never_weaken.py`, sa ligne du gabarit et de la page | A12 à A16, T1 pour `raised-entry` | 3 | L2 |
| 5 | refondre `after_write.py` : un exécuteur par clé, échéance partagée, sans changer de comportement (prérefactoring) | T4 (les tests de `after_write` passent à l'identique) | aucun | L2 |
| 6 | `lint-on-write` et relais de la fin de sortie, aussi pour `format-on-write`, ligne du gabarit | A17 à A22, T1 pour `lint-on-write` | 5 | L2 |
| 7 | journal des refus d'`after_write` et filtre de `guard-refusals` | A23, A24 | 6 | L2 |
| 8 | sonde 17 (`architecture-check`), règle de `BLOCKER` au titre de F-15, ligne du gabarit | A25 à A28, T1 pour `architecture-check` | 3 | L2 |
| 9 | `recurring_findings.py`, son appel dans `skills/qc/SKILL.md`, ligne du gabarit | A29 à A33, T1 pour `recurring-finding` | 3 | L3 |
| 10 | base de règles du gabarit (ruff 10, 5, 5, carte des modules, `stack`) et page de `docs/` complète | A34, A35 | 3, 4, 6, 8, 9 | L3 |

Précisions et choix de l'agent de session, que le relecteur peut contester :

- **Le gabarit s'écrit par ticket, pas seulement au dixième.** `.claude/rules/forge.md` demande qu'une clé
  nouvelle soit documentée dans le gabarit dans la PR qui l'introduit ; la séance du tour 1 plaçait le gabarit
  au dixième ticket, bloqué par les cinq autres. Le dixième garde alors la base de règles (A34) et la lecture
  finale de la page (A35), et chaque ticket de clé écrit sa propre ligne. Les blocages restent ceux de la séance.
- **Le ticket 2 ne se limite pas à un appel.** `parse_uv_lock` écarte les membres locaux (`LOCAL_SOURCES`,
  l.86 et 107) : `stack_check.py` a besoin de leurs listes `dependencies`, que `lockfiles.py` ne lit pas
  encore. `direct_dependencies` est donc du code nouveau, ajouté au ticket 2, après l'extraction pure du
  ticket 1. Pour npm, l'entrée racine `packages[""]` est écartée par `parse_package_lock` (l.120) : c'est
  elle que `direct_dependencies` lit, et son absence est `INVALID` (A11).
- **Le ticket 3 corrige un texte déjà faux.** `agents/qc-gate.md:217` dit « les sondes 1 à 14 » alors que la
  sonde 15 existe. Le ticket 3 écrit « 1 à 16 », le ticket 8 « 1 à 17 », et chacun ajoute son numéro à la liste
  « sondes 2, 5, 6, 7, 10, 11, 12, 13, 14 et 15 » de `## Sortie`, avec son test de contenu.
- **Ordre contre la coupe du 2026-12-16.** `raised-entry` (4) précède `lint-on-write` (6) et la sonde 17 (8) dans
  l'ordre voulu, comme la spec le demande ; les blocages ne l'imposent pas, et l'ordre dans lequel
  `forge:feature-build` prend les tickets prêts n'a pas été vérifié ici : à dire à l'humain à la publication.
- **Parallélisme.** Après le ticket 3, les tickets 4, 8 et 9 se codent en parallèle, comme 1 et 5 au départ ; 4,
  8 et 9 touchent chacun la page de `docs/` et le gabarit : un coder qui voit un conflit de fusion rebase, sans
  ouvrir de ticket.
- **À reporter dans les tickets.** Pas de `tomllib` (Python 3.10). Un fichier `stack` absent à la tête vaut une
  liste vide, donc tout paquet ajouté est `UNLISTED`. `stack_check.py` normalise les noms pypi (casse, `-`,
  `_`, `.`), pas les noms npm. Aucun ticket ne touche `hooks.json` ni un `guard_*` : aucun chemin protégé.

## 8. ADR déclenchés

Aucun. Aucune décision structurante ne sort de la feature : pas de technologie nouvelle, pas de contrat
d'API, pas de modèle IA, pas de schéma non trivial. `forge:staff-engineer` l'a décidé le 2026-11-23
(case T2, T4, T6, T7 de la matrice).

| ADR | Décision | Statut |
|---|---|---|
| aucun | sans objet | sans objet |

## 9. Décisions prises pendant la construction

| Ticket | Décision | Par | Source |
|---|---|---|---|

## 10. Ce qui n'est pas vérifié

- **La forme réelle des verrous.** Les listes `dependencies` d'un membre local d'un `uv.lock` et l'entrée
  racine d'un `package-lock.json` avec espaces de travail n'ont pas été lues sur un verrou réel pour ce design.
  Le ticket 2 les produit avec `uv lock` et `npm install --package-lock-only` dans un dépôt jetable, ou rend
  `NOT RUN` pour npm si l'outil manque, jamais un `OK` (A11, spec section 20).
- **La commande de ruff.** Les réglages `PLR1702` (aperçu), la complexité 10, les paramètres 5 et
  l'imbrication 5 du gabarit (A34) n'ont pas été lancés ici : le ticket 10 les essaie sur le dépôt de forge.
- **Le plafond du stderr d'un hook.** Non vérifié ; la sortie relayée est bornée en deçà (A18).
- **Le lancement dans la CI d'un projet.** La sonde de `architecture-check` rejoue la commande de la clé ; son
  lancement sur un projet réel n'est pas éprouvé (spec section 20).
- **Ce qui a été relu.** `after_write.py` (en entier), `lockfile_age.py:86-156`, `never_weaken.py:140-289`,
  `factory_slo.py:434-460` et 925, `refusal_journal.py`, `qc-gate.md:190-263`, `qc-conf.md:86-102`, le gabarit
  `usine.md:830-860` : les lignes citées plus haut sont celles de la base `30a4634`.
