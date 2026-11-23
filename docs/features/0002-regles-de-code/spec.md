---
feature: F-0002
document: spec
statut: en-revue
destinataires: ikoro-labs (humain de la clé `accepting-human`, relit au titre du métier et décide par `/forge:feature-accept`), puis l'agent qui implémente ; forge:qc relit
base: 0c32a60
date: 2026-11-23
---

# F-0002 : spécification

Le pourquoi est dans `cadrage.md` (accepté le 2026-11-23, PR #298). Ici : **ce qui se construit**, et
comment on saura que c'est fait. Les réponses des deux agents décideurs, avec leurs sources, sont dans
`seances/2026-11-23-ikoro-labs-spec.md` ; la spec les reprend sans les redire.

## 1. Stories

Sept stories, une par exigence du cadrage (EXI-08, la documentation, est un critère transverse : section 10).
Dans l'ordre des lots, la coupe du 2026-12-16 gardant `raised-entry` en premier.

1. En tant qu'**humain du projet**, je veux déclarer la liste des paquets permis dans un fichier que la clé
   `stack` désigne, pour que la pile choisie au cadrage soit écrite une fois et lue par l'outil.
2. En tant que **coder**, je veux qu'une dépendance hors liste, ou sans source, soit refusée avec la ligne
   exacte à écrire, pour proposer cette ligne avec sa décision au lieu de deviner.
3. En tant qu'**humain du projet**, je veux qu'une hausse d'une entrée de la liste de référence
   (`baselines`) soit refusée, pour qu'une dette ne monte pas en silence.
4. En tant que **coder**, je veux que la sortie d'un outil de format ou d'analyse qui échoue me soit
   relayée, bornée, pour corriger la règle sans la deviner.
5. En tant que **juge**, je veux qu'une commande d'architecture déclarée par le projet soit lancée par la
   sonde de `forge:qc-gate`, pour relever un manque de module ou une dépendance interdite par une mesure.
6. En tant que **juge**, je veux qu'un constat du juge qui revient sur trois PR distinctes en 30 jours
   devienne un commentaire unique sur le ticket de suivi, pour qu'il soit lu sans ouvrir un ticket.
7. En tant qu'**humain du projet**, je veux une base de règles livrée en gabarit (complexité, paramètres,
   imbrication, carte des modules, pile), pour partir d'un exemple éprouvé sans plafond de lignes.

## 2. Critères d'acceptation

Chaque critère deviendra un test qui cite `F-0002 A<n>`, relié dans la recette. Une clé absente de
`docs/agents/usine.md` rend « sans objet (clé `<nom>` absente) », jamais `PASS`, et aucune clé ne prend de
valeur par défaut.

| # | Story | Étant donné | Quand | Alors |
|---|---|---|---|---|
| A1 | 1 | une clé `stack` qui désigne un fichier dont chaque ligne est `<écosystème> \| <paquet> \| <source>`, l'écosystème étant `pypi` ou `npm` | `stack_check.py` lit le fichier | aucune ligne ne sort `INVALID` |
| A2 | 1 | une ligne de `stack` d'un écosystème autre que `pypi` ou `npm`, ou de moins de trois champs | `stack_check.py` lit le fichier | la ligne sort `INVALID` avec son numéro, et n'est jamais complétée |
| A3 | 1 | la clé `stack` absente | la sonde de `forge:qc-gate` passe | elle rend « sans objet (clé `stack` absente) », jamais `PASS` |
| A4 | 1 | le paquet pypi `Foo_Bar` du verrou et la ligne `pypi \| foo-bar \| ...` de la liste | le contrôle compare | les deux noms sont le même paquet (casse, `-`, `_` et `.` équivalents) |
| A5 | 2 | une PR qui ajoute au verrou un paquet direct d'un membre local, absent de la liste | `stack_check.py` compare le diff | le paquet sort `UNLISTED`, et le premier message de refus donne la ligne `<écosystème> \| <paquet> \| <ADR ou séance>` à écrire et le chemin du fichier `stack` |
| A6 | 2 | un paquet direct ajouté, présent dans la liste de la tête avec une source vide | `stack_check.py` compare | le paquet sort `NO SOURCE` |
| A7 | 2 | un paquet ajouté, présent dans la liste de la tête avec sa source | `stack_check.py` compare | le paquet sort `OK` ; chaque ligne que la PR ajoute à la liste sort `ADDED` avec sa source, que le juge lit au titre de F-8 |
| A8 | 2 | un paquet ajouté que nul membre local ne déclare (dépendance indirecte) | `stack_check.py` compare | il n'est pas comparé ; son âge reste à `lockfile_age.py` |
| A9 | 2 | une PR qui change dans `usine.md` le chemin de la clé `stack` | `forge:qc-gate` lance le contrôle | le chemin se lit sur la base : la PR ne relève pas la liste qui la juge, mais le contenu de la liste se lit sur la tête |
| A10 | 2 | un `UNLISTED` ou un `NO SOURCE` dans le tableau de `forge:qc-gate` | `forge:qc-conf` juge | il pose un `BLOCKER` qui cite la ligne à écrire ; `NOT RUN` et `INVALID` sont rendus tels quels, jamais `OK` |
| A11 | 2 | un verrou illisible, un écosystème hors `lockfile`, ou un `package-lock.json` sans entrée racine | `stack_check.py` tourne | la sortie est `INVALID` ou `NOT RUN` avec la raison, jamais un `OK` |
| A12 | 3 | une entrée `<chemin> \| raised-entry` de `never-weaken`, et une PR qui ajoute au fichier de référence une clé absente des lignes retirées | `never_weaken.py` juge le diff | le refus nomme le fichier et la clé |
| A13 | 3 | la même entrée, une clé dont le nombre passe de 3 à 4 | `never_weaken.py` juge le diff | le refus nomme la clé, l'ancien et le nouveau nombre |
| A14 | 3 | la même entrée, une clé retirée ou dont le nombre baisse | `never_weaken.py` juge le diff | la PR passe |
| A15 | 3 | une ligne `<clé>` seule | le script la lit | elle compte 1 ; une clé seule ajoutée est donc une hausse |
| A16 | 3 | l'entrée `<chemin> \| raised-entry \| <paramètre>` | le script lit l'entrée | elle sort `INVALID` : le type ne prend pas de paramètre |
| A17 | 4 | une ligne `<motif> \| <commande>` de `lint-on-write`, et une écriture d'un fichier qui correspond au motif | la commande sort en erreur | `after_write` sort en code 2 et écrit `lint-on-write: <commande> failed on <chemin> (<raison>)`, suivi de la fin de la sortie de l'outil |
| A18 | 4 | une sortie de plus de 20 lignes ou de plus de 2000 octets | `after_write` la relaie | l'agent reçoit les 20 dernières lignes au plus, et 2000 octets au plus |
| A19 | 4 | une ligne de `format-on-write` dont la commande échoue | `after_write` la relaie | la fin de sa sortie est relayée de la même façon (jusqu'ici jetée) |
| A20 | 4 | une ligne de `lint-on-write` qui n'est pas `<motif> \| <commande>` | `after_write` la lit | elle est ignorée et le message le dit |
| A21 | 4 | une commande qui dépasse 30 s, ou un total de 120 s sur l'écriture | `after_write` attend | la commande est tuée, le message dit le délai, l'écriture n'est pas défaite |
| A22 | 4 | la clé `lint-on-write` absente | un fichier s'écrit | `after_write` ne lance rien, et la sonde ou le texte rend « sans objet (clé `lint-on-write` absente) » |
| A23 | 4 | un refus de `lint-on-write` ou de `format-on-write` | `after_write` refuse | une ligne entre au journal des refus : `guard` `after_write`, `rule` `lint-on-write` ou `format-on-write`, les champs des trois gardes, jamais la commande ni la sortie |
| A24 | 4 | des refus de `after_write` dans le journal | `factory_slo.py` calcule `guard-refusals` | l'indicateur ne compte que `guard_git`, `guard_coder` et `guard_readonly` |
| A25 | 5 | une clé `architecture-check` qui nomme une commande | `forge:qc-gate` lance sa sonde | la commande, lue sur la base, tourne sous le lanceur borné avec les limites de `run-limits`, et sort `PASS`, `FAIL` ou `NOT RUN` |
| A26 | 5 | la clé `architecture-check` absente | la sonde passe | elle rend « sans objet (clé `architecture-check` absente) » |
| A27 | 5 | une sonde en `FAIL` | `forge:qc-conf` juge | il pose un `BLOCKER` au titre de F-15 |
| A28 | 5 | le fichier de la carte des modules protégé par une entrée `<chemin> \| removed-line` | une PR retire une règle de la carte | le refus de `never-weaken` renvoie la PR à l'humain |
| A29 | 6 | la clé `recurring-finding : 3 \| 30` et trois PR distinctes jugées dans les 30 jours dont le verdict cite le même `F-n` ou `L-n` | `recurring_findings.py` compte | le commentaire du ticket de la clé `slo-issue` liste cet identifiant avec ses trois PR |
| A30 | 6 | deux PR distinctes seulement, ou une PR qui cite l'identifiant à deux tours | le script compte | l'identifiant n'est pas listé : on compte les PR distinctes, jamais les tours |
| A31 | 6 | un constat sans `F-n` ni `L-n` | le script compte | il est compté à part, jamais mêlé aux identifiants |
| A32 | 6 | un commentaire déjà posé par le script | le script tourne de nouveau | le commentaire est réécrit, retrouvé par son marqueur caché, sans doublon et sans toucher au rapport des SLO ; aucun ticket n'est ouvert |
| A33 | 6 | la clé `recurring-finding` ou la clé `slo-issue` absente | `forge:qc` poste un verdict | le script rend « sans objet (clé `<nom>` absente) » et n'écrit rien |
| A34 | 7 | le gabarit `usine.md` | on le lit | il porte des lignes d'exemple de `lint-on-write` pour ruff (complexité 10, paramètres 5, imbrication 5 par `PLR1702`, version de ruff épinglée, `--preview`), la forme de la carte des modules en exemple de `architecture-check`, un exemple de `stack`, et aucun plafond de lignes |
| A35 | 7 | la page de `docs/` de la feature | on la lit | elle dit chaque clé, le format de chaque ligne, le message de refus et le geste de l'humain qui accepte une dépendance |

## 3. Éléments de la source

La clé `product-source` est absente de `usine.md` : la source de la spec est le cadrage accepté, dont
`source_ids.py` n'est donc pas lancé (sans objet, clé `product-source` absente). Les éléments sont les huit
exigences de sa section 2.

| Identifiant | Élément (résumé) | Tenu par |
|---|---|---|
| EXI-01 | base de règles livrée en gabarit (10, 5, 5, carte des modules, pile ; sans plafond de lignes) | story 7, A34 et A35 |
| EXI-02 | clé `stack` : fichier de lignes, refus nommant la ligne à écrire | story 1, A1 à A4 ; story 2, A5 |
| EXI-03 | contrôle des dépendances : liste comparée au diff, manifestes lus par la clé `lockfile` | story 2, A5 à A11 |
| EXI-04 | clé `lint-on-write`, code 2, sortie relayée | story 4, A17 à A24 |
| EXI-05 | clé `architecture-check`, sonde de `forge:qc-gate` et CI | story 5, A25 à A28 |
| EXI-06 | type `raised-entry` de `never-weaken` | story 3, A12 à A16 |
| EXI-07 | un constat récurrent devient un commentaire, jamais un ticket | story 6, A29 à A33 |
| EXI-08 | documentation : gabarit, page de `docs/`, `CHANGELOG.md` | critères transverses T1 à T3 (section 10), A34 et A35 |

Aucun élément n'est écarté : aucune ligne `Écarté :`.

## 4. Exigences atomiques (`EXI-nn`)

Niveau de preuve : P principe du projet, O piège observé, M parité marché. Les sources de chaque
chiffre sont dans le cadrage (sections 2 et 7) et dans la séance du 2026-11-23.

| Identifiant | Exigence | Critère mesurable | Classement | Niveau de preuve | Lot |
|---|---|---|---|---|---|
| EXI-01 | base de règles en gabarit | trois seuils écrits en clair (10, 5, 5), zéro plafond de lignes, un exemple de `stack`, un de carte des modules (A34) | obligatoire | M (NIST SP 500-235 pour le 10, défaut de ruff pour le 5) | L3 |
| EXI-02 | clé `stack` | 100 % des lignes mal formées sortent `INVALID` avec leur numéro (A2) | obligatoire | P | L1 |
| EXI-03 | contrôle des dépendances | un paquet direct hors liste sort `UNLISTED` et le premier message donne la ligne à écrire (A5) ; test vert, rouge sur la base | obligatoire | O (12 des 17 findings de Shipyard portent sur les dépendances) | L1 |
| EXI-04 | `lint-on-write` | sortie relayée : 20 lignes et 2000 octets au plus (A18) ; 30 s par commande, 120 s au total (A21) ; une ligne de journal par refus (A23) | obligatoire | O (`after_write` jette la sortie) | L2 |
| EXI-05 | `architecture-check` | `PASS`, `FAIL` ou `NOT RUN`, lancé sous `run-limits` (A25) | souhaitable | P | L2 |
| EXI-06 | `raised-entry` | une clé nouvelle ou un nombre plus grand est refusé, une baisse passe (A12 à A14) | obligatoire | O (`raised-number` laisse passer une dette ajoutée seule) | L2 |
| EXI-07 | constat récurrent | 3 PR distinctes en 30 jours listent l'identifiant ; 2 ne le listent pas (A29, A30) ; zéro ticket | souhaitable | O (`_derouler` relevé cinq fois sur Shipyard #86 à #94) | L3 |
| EXI-08 | documentation | chaque clé nouvelle a sa ligne dans le gabarit ; une page de `docs/` ; une entrée de `CHANGELOG.md` (T1 à T3) | obligatoire | P | tous |

## 5. Contrôles codés (`Cnn`)

| Identifiant | Calcul exact | Tolérance par défaut | Effet |
|---|---|---|---|
| C01 | `stack_check.py` : pour chaque paquet direct ajouté entre la base et la tête au verrou d'une ligne de la clé `lockfile`, comparer son nom normalisé à la liste de la tête ; sortie `OK`, `UNLISTED`, `NO SOURCE`, `NOT RUN`, `INVALID`, plus `ADDED` par ligne de liste ajoutée | aucune : un paquet hors liste est refusé | `UNLISTED` et `NO SOURCE` : `BLOCKER` de `forge:qc-conf` |
| C02 | `raised-entry` : par fichier du diff, pour chaque clé des lignes ajoutées, comparer son nombre (1 pour une clé seule) à celui de la même clé dans les lignes retirées du même fichier ; une clé sans ligne retirée, ou un nombre plus grand, est une hausse | aucune | refus de `never_weaken.py`, la PR revient à l'humain |
| C03 | sonde `architecture-check` : lancer la commande de la base sous le lanceur borné | limites de `run-limits` | `FAIL` : `BLOCKER` au titre de F-15 ; `NOT RUN` : rendu tel quel |
| C04 | `recurring_findings.py` : compter, par `F-n` ou `L-n`, les PR distinctes jugées dans les 30 jours glissants dont un commentaire de verdict cite l'identifiant ; seuil : 3 | `3 \| 30`, clé `recurring-finding` | un commentaire réécrit sur le ticket de la clé `slo-issue` ; jamais un ticket |
| C05 | relais de la sortie d'un outil d'écriture : les 20 dernières lignes, puis 2000 octets au plus | 20 lignes, 2000 octets | l'agent voit la règle, le fichier et la fin de la sortie |

## 6. Gabarits et conventions (`Gn`)

| Identifiant | Structure | Règles |
|---|---|---|
| G1 | fichier `stack` : une ligne `<écosystème> \| <paquet> \| <ADR accepté ou séance>` | écosystèmes fermés (`pypi`, `npm`) ; le nom se normalise (pypi : casse, `-`, `_`, `.`) ; jamais complété |
| G2 | message de refus d'une dépendance : la ligne `<écosystème> \| <paquet> \| <ADR ou séance>` à écrire, puis le chemin du fichier `stack` | la ligne figure dans le premier message ; jamais un refus muet |
| G3 | message d'écriture : `<clé>: <commande> failed on <chemin> (<raison>)`, puis la fin de la sortie | la commande figure dans le message, jamais dans le journal |
| G4 | ligne du journal des refus : `date`, `guard`, `rule`, `agent`, `repo`, `branch`, `verb` | `guard` vaut `after_write`, `rule` vaut `lint-on-write` ou `format-on-write` ; ni la commande ni la sortie |
| G5 | commentaire du constat récurrent : un marqueur caché propre (`<!-- forge-recurring-findings -->`), la fenêtre en dates, un tableau `Identifiant \| PR distinctes \| PR`, une ligne des constats sans identifiant | un seul commentaire, réécrit ; distinct du rapport des SLO |
| G6 | clés nouvelles de `usine.md` : `stack`, `lint-on-write`, `architecture-check`, `recurring-finding` ; type `raised-entry` de `never-weaken` | chacune documentée dans le gabarit ; `lint-on-write` prend la grammaire de `format-on-write` ; `recurring-finding` s'écrit `<seuil> \| <jours>` |

## 7. Déroulé pas à pas

**Un coder ajoute une dépendance.**
1. Le coder ajoute un paquet au manifeste d'un membre local, et le verrou change.
2. `forge:qc-gate` lance `stack_check.py` ; le paquet n'est pas dans la liste : `UNLISTED`.
3. `forge:qc-conf` pose un `BLOCKER` avec la ligne à écrire ; le coder ajoute la ligne et sa source à `stack`
   dans la même PR, le contrôle sort `OK` et `ADDED`, et le juge lit la source au titre de F-8.

**Un coder écrit un fichier.**
1. Le coder écrit un fichier qui correspond au motif d'une ligne de `lint-on-write`.
2. L'outil échoue : `after_write` sort en code 2 et relaie la règle, le fichier et la fin de la sortie ;
   une ligne entre au journal des refus.
3. Le coder corrige et réécrit : le fichier passe, rien n'est relayé.

**Une PR hausse une entrée de `baselines`.**
1. La PR ajoute une clé ou un nombre plus grand dans le fichier de référence.
2. `never_weaken.py` refuse et nomme le fichier et la clé ; l'humain décide.

**Un constat revient.**
1. `forge:qc` poste un verdict ; `recurring_findings.py` compte les PR distinctes par identifiant.
2. À trois PR en 30 jours, le commentaire du ticket de suivi est réécrit avec l'identifiant et ses PR.

## 8. Rôles

| Rôle | Fait | Ne fait pas |
|---|---|---|
| humain du projet | écrit la clé `stack`, ses sources et ses seuils, accepte la spec, décide d'une hausse d'entrée | n'ouvre pas un ticket par constat récurrent |
| coder | propose la ligne de `stack` avec sa décision, corrige ce que `lint-on-write` lui relaie | n'élargit pas lui-même la liste sans source ; ne relève pas la clé qui le juge |
| juge | lit la source d'une ligne ajoutée (F-8), pose les `BLOCKER` de C01 et C03, tient le commentaire récurrent | ne juge pas le code de forge lui-même (hors périmètre) |

## 9. Décisions prises et leur date

| Date | Décision | Par qui |
|---|---|---|
| 2026-11-22 | base sans plafond de lignes ; 10, 5, 5 ; `stack` en fichier de lignes ; `lint-on-write` et `architecture-check` ; `raised-entry` ; un constat récurrent devient un commentaire | `forge:staff-engineer` (brainstorm) |
| 2026-11-23 | seuil de 3 PR distinctes sur 30 jours ; commentaire unique sur la clé `slo-issue` | `forge:staff-engineer` (cadrage) |
| 2026-11-23 | cadrage accepté (PR #298) | ikoro-labs |
| 2026-11-23 | Q1 à Q8 : paquets directs de chaque membre local ; chemin de `stack` lu sur la base, liste lue sur la tête ; relais partagé avec `format-on-write` ; `raised-entry` par fichier ; carte des modules protégée par `removed-line` ; commentaire réécrit après chaque verdict ; journal des refus étendu à `after_write` | `forge:staff-engineer` (séance de spec) |
| 2026-11-23 | Q9 et Q10 : trois rôles, sept stories, EXI-08 transverse ; 20 lignes et 2000 octets ; 30 s et 120 s | `forge:product-owner` (séance de spec) |

## 10. Critères transverses

- **T1.** Chaque clé nouvelle (G6) a sa ligne dans `plugins/forge/templates/usine.md`.
- **T2.** Une page de `docs/` traite des clés et du geste de l'humain ; le `README.md` la résume et la
  renvoie.
- **T3.** Une entrée de `CHANGELOG.md` ouvre chaque version publiée, par zone.
- **T4.** Chaque comportement ajouté a son test dans `tests/`, qui cite `F-0002 A<n>`, sous Linux et sous
  Windows.
- **T5.** Une clé absente rend « sans objet (clé `<nom>` absente) » ; aucune clé n'a de valeur par défaut.
- **T6.** Le contenu de `plugins/forge/` ne cite ni numéro d'ADR, ni nom de personne, ni nom de projet.
- **T7.** Les sorties relayées et les messages ne portent aucun tiret cadratin.
- **T8.** Un contrôle qui ne peut pas tourner rend `NOT RUN` ou `INVALID` avec sa raison, jamais `PASS`.
- **T9.** Ajouter un contrôle à un projet ne demande qu'une ligne de `usine.md` ; aucun budget de temps.

## 11. Lots et leur gel

| Lot | Contenu | Gelé le |
|---|---|---|
| L1 | EXI-02, EXI-03 : `stack`, C01, A1 à A11 | à l'acceptation de la spec (`/forge:feature-accept`) |
| L2 | EXI-06, EXI-04, EXI-05 : `raised-entry` d'abord (C02, A12 à A16), puis `lint-on-write` et le journal (C05, A17 à A24), puis `architecture-check` (C03, A25 à A28) | à l'acceptation de la spec |
| L3 | EXI-07, EXI-01 : constat récurrent (C04, A29 à A33), puis la base de règles (A34, A35) | à l'acceptation de la spec |

EXI-08 se tient dans chaque lot (T1 à T3). Les dates d'arrêt du cadrage (2026-12-06 pour L1, 2026-12-16 pour
L2) et la mesure du 2027-01-15 restent celles de l'humain : la spec ne les fixe pas.

## 12. Comment elle peut échouer

| Risque | Mécanisme | Parade |
|---|---|---|
| faux blocage | une dépendance légitime refusée, ou un paquet indirect pris pour un direct | seuls les paquets directs des membres locaux se comparent (A8) ; le refus nomme la ligne à écrire (A5) ; les refus répétés se lisent au journal |
| une PR s'autorise elle-même | elle ajoute à `stack` la ligne du paquet qu'elle ajoute | `ADDED` est rendu avec sa source et le juge la lit au titre de F-8 (A7) ; le chemin de la clé vient de la base (A9) |
| contournement par une autre commande | un hook se contourne | la CI rejoue les mêmes commandes et tranche en dernier ; aucun hook sur Bash (hors périmètre) |
| règle d'imbrication retirée ou changée | `PLR1702` est en aperçu dans ruff | version de ruff épinglée et règle nommée dans le gabarit (A34) |
| carte des modules affaiblie | le fichier se lit sur la tête | entrée `removed-line` conseillée (A28) |
| clé renommée dans la liste de référence | un renommage est une clé nouvelle | `raised-entry` le refuse (A12) : l'humain tranche |
| sortie relayée trop longue ou sensible | un outil imprime beaucoup, ou un extrait de code | 20 lignes et 2000 octets (A18) ; la commande ne va pas au journal (A23) |
| bruit du commentaire récurrent | un identifiant très général | seuil de 3 PR distinctes (A30) ; un seul commentaire réécrit (A32) |

## 13. Pièges et parades observés

| Identifiant | Piège | Parade |
|---|---|---|
| P1 | `after_write` jette la sortie de l'outil (`after_write.py:102-111,146`) : l'agent voit un échec sans la règle | A17, A19 |
| P2 | `raised-number` laisse passer une dette ajoutée seule (`never_weaken.py:167-169`) | A12 à A15 |
| P3 | un verrou liste les paquets indirects : une comparaison de tous les paquets refuserait à tort ; le verrou de Shipyard a une racine et trois membres locaux | A5, A8 |
| P4 | `_derouler` relevé cinq fois par le juge sur Shipyard #86 à #94 | A29 |

## 14. Non-goals

- Un garde de commande Bash : un hook se contourne, la CI tranche en dernier.
- Le code de forge lui-même.
- Un plafond de lignes : aucune source ne relie une longueur aux défauts.
- Un catalogue de règles partagé avec un projet consommateur : `socle.md` en tient lieu.
- La licence des dépendances.
- Un ticket par constat récurrent : un commentaire, jamais un ticket.
- La comparaison des dépendances indirectes : elles restent à `lockfile_age.py`.
- Le recoupement des deux relevés du cadrage (149 PR fusionnées, 121 PR jugées).

## 15. Exigences non fonctionnelles

- Les hooks et les scripts sont en Python de la bibliothèque standard, sous Linux et sous Windows, à partir
  de Python 3.10, lancés par `uv run --no-project --quiet python`.
- Délai d'une écriture : 30 s par commande et 120 s au total, les valeurs actuelles de `after_write.py`
  (A21).
- Sortie relayée : 20 lignes et 2000 octets au plus (A18). Les hooks de Claude Code gardent un aperçu de
  2000 caractères au-delà de 10 000 (documentation lue le 2026-11-23).
- La sonde de `architecture-check` tourne sous les limites de `run-limits` (A25).
- `stack_check.py` lit le verrou par `git show` et n'ouvre aucun accès réseau. Aucun délai mesuré : aucun
  chiffre n'est engagé ici, il se relèvera à l'essai.

## 16. Contrats, en prose

- **`stack_check.py`.** Entrée : les clés `stack` et `lockfile` lues sur la base, la liste lue sur la tête, les
  verrous de la base et de la tête. Sortie : une ligne par paquet direct ajouté (`OK`, `UNLISTED`,
  `NO SOURCE`, `NOT RUN`, `INVALID`) et une ligne `ADDED` par ligne de liste ajoutée. Erreurs nommées :
  verrou illisible, écosystème hors `lockfile`, ligne de liste mal formée : toutes `INVALID` ou `NOT RUN`, avec
  la raison. Il ne complète jamais une ligne.
- **`raised-entry`.** Entrée : le fichier du diff que l'entrée `never-weaken` nomme. Sortie : un refus par
  clé en hausse, ou rien. Une entrée avec un paramètre est `INVALID`.
- **`after_write`.** Entrée : l'écriture d'un fichier. Sortie : code 2 et un message de la forme G3 quand une
  commande de `lint-on-write` ou de `format-on-write` échoue, sinon 0 ; une ligne au journal par refus
  (G4). Une commande introuvable, un délai ou une ligne mal formée ont chacun leur message.
- **Sonde `architecture-check`.** Entrée : la commande de la clé, lue sur la base. Sortie : `PASS`, `FAIL`
  ou `NOT RUN`, avec la raison du `NOT RUN`.
- **`recurring_findings.py`.** Entrée : les commentaires de verdict des PR jugées dans la fenêtre, la clé
  `recurring-finding`, la clé `slo-issue`. Sortie : un commentaire G5 réécrit sur le ticket. Erreurs :
  clé absente, « sans objet » ; ticket introuvable, rien n'est écrit et la raison est dite.

## 17. Impact sur les règles du métier

Aucune règle du métier touchée : la clé `domain-skill` est absente de `usine.md`, et la feature ne touche ni
un chiffre engagé ni une obligation réglementaire. Les seuils 10, 5 et 5 sont des conseils de gabarit, pas des
règles que forge impose.

## 18. Décisions prises par défaut

| # | Décision | Fondement | Si le relecteur lit autrement |
|---|---|---|---|
| 1 | scripts nommés `stack_check.py` et `recurring_findings.py` | recommandation de la séance, non contestée par `forge:staff-engineer` | renommer avant le design |
| 2 | marqueur du commentaire récurrent `<!-- forge-recurring-findings -->` | le rapport des SLO a le sien (`factory_slo.py:925`) | un autre nom, sans effet sur les critères |
| 3 | `verb` du journal d'une écriture : le nom de l'outil d'écriture | les trois gardes écrivent déjà `verb` | un autre libellé, A23 à relire |
| 4 | `OK` pour un paquet listé avec source, `ADDED` pour une ligne de liste ajoutée | Q2 de la séance : la ligne ajoutée est rendue avec sa source | fusionner les deux sorties |
| 5 | lots gelés à l'acceptation de la spec, dates d'arrêt non reprises | elles sont à l'humain (cadrage, section 8) | écrire les dates ici après son accord |
| 6 | le journal des refus de `after_write` entre avec EXI-04 (L2) | la condition du 2026-12-16 demande le journal alimenté | le sortir en lot à part |

## 19. Confiance chiffrée

| Partie | Confiance (de 0 à 100 %) | Raison |
|---|---|---|
| modèle | 70 | les formes de C01, C02 et C04 viennent des deux agents et du code lu ; trois points ne sont pas vérifiés (section 20) |
| périmètre | 80 | les huit exigences viennent du cadrage accepté ; EXI-08 devient transverse sur l'avis du product-owner |
| priorités | 75 | l'ordre garde `raised-entry` à la coupe du 2026-12-16 ; l'ordre d'origine (EXI-04, EXI-05, EXI-06) était contraire |

## 20. Points ouverts

- L'entrée racine d'un `package-lock.json` (npm) et les espaces de travail : non vérifiée par l'agent ; A11 la
  traite par `INVALID` ou `NOT RUN` en attendant.
- Le plafond de sortie d'un hook qui sort en code 2 (stderr) : non vérifié ; A18 borne la sortie en deçà.
- Le lancement d'un script du plugin dans la CI du projet (la CI rejoue la commande de la sonde) : non vérifié
  sur un projet réel ; à éprouver à l'essai de L1.
- Le recoupement des deux relevés du cadrage (149 PR fusionnées contre 121 PR jugées) : hors spec, à
  éclaircir avant la mesure du 2027-01-15.

## 21. Questions pour les entretiens

- Sans objet : la feature n'a pas d'expert externe ; l'humain de la clé `accepting-human` décide.

## 22. Glossaire

La clé `glossary` est absente de `usine.md` : ces termes restent dans la spec.

| Terme | Définition |
|---|---|
| `stack` | clé de `usine.md` qui désigne le fichier des paquets permis, une ligne par paquet |
| paquet direct | paquet que déclare un membre local du verrou (source `virtual`, `editable`, `directory` ou `path`) |
| membre local | paquet du verrou qui est du projet lui-même, non de l'index |
| `raised-entry` | type de `never-weaken` qui refuse une clé nouvelle ou un nombre plus grand dans un fichier de référence |
| `lint-on-write` | clé de `usine.md` : lignes `<motif> \| <commande>` lancées à chaque écriture, sortie relayée |
| `architecture-check` | clé de `usine.md` : une commande que lance la sonde de `forge:qc-gate` et la CI |
| constat récurrent | `F-n` ou `L-n` cité par le verdict de trois PR distinctes en 30 jours |
| `NOT RUN` | le contrôle n'a pas pu tourner : jamais un `PASS` |
