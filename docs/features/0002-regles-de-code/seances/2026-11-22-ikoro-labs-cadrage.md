---
feature: F-0002
seance: 2026-11-22-ikoro-labs-cadrage
participants: ikoro-labs (humain, a tapé `/forge:feature-frame`), l'agent de la session forge, forge:product-owner et forge:staff-engineer (agents décideurs)
sujet: cadrer F-0002 (problème, périmètre, taille, observabilité, risques, critères d'arrêt)
---

# Séance du 2026-11-22 : cadrage de F-0002

Écrite pendant la séance, tour par tour, jamais réécrite ensuite. Une correction se fait dans une
séance suivante, qui cite celle-ci. Elle suit `2026-11-22-ikoro-labs-brainstorm.md`, dont les
décisions Q1 à Q4 sont reprises telles quelles dans le cadrage. Les deux agents décideurs n'écrivent
pas : l'agent de la session recopie leurs réponses, résumées, avec leurs lignes `MATRIX_CELL`.

## Sources apportées

| Source | Où | Empreinte | Ce qui en est retenu |
|---|---|---|---|
| `idee.md` de F-0002 | `docs/features/0002-regles-de-code/idee.md` | sans objet (versionné) | l'idée, ses cinq questions |
| Séance du brainstorm | `seances/2026-11-22-ikoro-labs-brainstorm.md` | sans objet (versionnée) | décisions Q1 à Q4, périmètre réservé |
| `docs/agents/decisions.md` | dépôt | sans objet (versionné) | cases T3, T4, T7, P2, H1 ; `entry-gate` absente |

## Tours

### Tour 1

La condition d'entrée n'est pas une question : la clé `entry-gate` est absente de `usine.md`, la
section 3 du cadrage dit « sans objet (clé `entry-gate` absente) » et l'humain qui acceptera le
cadrage en décide.

**Q1. Qui souffre, de quoi, et quel chiffre ?** Recommandation : celui qui relit une PR et le juge
qui relève à la lecture une règle de code qu'un outil aurait mesurée ; chiffre à relever sur les
verdicts des PR de ce dépôt (source, date, dénominateur).
Réponse de `forge:product-owner` : DECIDED, `MATRIX_CELL` P1. Sur les verdicts de forge, 0 finding
sur 288 (69 `BLOCKER`, 219 `MINOR`) porte sur les six classes (format, complexité, imbrication,
paramètres, modules, dépendances), 149 PR fusionnées, du 2026-10-23 au 2026-11-22. Sur Shipyard, 17
sur 721, dont 12 sur les dépendances. Trop peu pour conclure : recentrer le problème sur les
dépendances et sur le constat récurrent (`_derouler` relevé cinq fois, Shipyard #86 à #94). Les
verdicts encore en revue ne sont pas comptés, et les findings hors du filtre ne sont pas lus un par un.

**Q2. Pourquoi pas plus simple ?** Recommandation : ruff et une étape de CI suffiraient pour un
projet Python seul, pas pour figer la pile, refuser une dépendance et faire monter une règle depuis
la revue.
Réponse de `forge:staff-engineer` : DECIDED, `MATRIX_CELL` T4, T7. Non, ils ne suffisent pas.
`after_write` jette la sortie de l'outil (règle et ligne : `after_write.py:102-111,146`), aucune
sonde de `forge:qc-gate` ne contrôle l'architecture ni les dépendances, `raised-number` laisse passer
une dette ajoutée seule (`never_weaken.py:167-169`), les constats F-8 et F-15 du juge restent en
lecture seule, et la configuration de ruff ne vaut que pour Python. Réversible, sauf la forme de `stack`.

**Q3. Le périmètre en exigences, avec la preuve de chacune.** Recommandation : une exigence par
décision de la séance du brainstorm, plus la documentation.
Réponse de `forge:product-owner` : RESERVED (aucune case : `feature-accept`). Proposition : EXI-01
base de règles ; EXI-02 `stack` ; EXI-03 contrôle des dépendances (dépend de #155) ; EXI-04
`lint-on-write` ; EXI-05 `architecture-check` ; EXI-06 `raised-entry` ; EXI-07 constat récurrent en
commentaire (attend les trois questions de #157) ; EXI-08 documentation. Hors périmètre, à reporter
en commentaire de #291 : garde Bash, code de forge, plafond de lignes, licence, catalogue partagé ;
#155 reste suivi à part.

**Q4. La taille.** Recommandation : L, avec la question de la couper en deux.
Réponse de `forge:product-owner` : RESERVED (aucune case pour la coupe ; P2 pour l'ordre). Taille L,
ne pas couper : une seule acceptation par l'humain ; l'ordre des lots se règle ensuite par P2.

**Q5. L'observabilité : métrique, alerte, trace.** Recommandation : part des écarts relevés hors
juge, alerte sur `raised-entry`, trace de la règle refusée.
Réponse de `forge:staff-engineer` : DECIDED, `MATRIX_CELL` T4. Métrique : constats du juge qui citent
F-8, F-13, F-15, F-17 ou L-n, par PR jugée, sans cible (`qc-conf.md:330`). Alerte : `raised-entry`
qui s'applique, ou sonde en `FAIL`. À ajouter : la sortie de l'outil relayée à l'agent, une ligne de
journal jsonl par refus (`refusal_journal.py`), et les sondes (`usine.md:80-81`). Réversible, une PR.

**Q6. Risques, faisabilité des données, critères d'arrêt datés.** Recommandation : risque principal,
une règle qui bloque l'agent à tort ; mesure sur les verdicts de ce dépôt ; arrêt à date fixe.
Réponse de `forge:staff-engineer` : risques DECIDED (T2) : faux blocage, contournement par Bash,
règle `PLR1702` de ruff encore en preview (https://docs.astral.sh/ruff/rules/too-many-nested-blocks/,
lue le 2026-11-22). Base de mesure du 2026-11-22 : 3 constats F-13 sur 303 `BLOCKER` et `MINOR`, 121
PR jugées. Critères d'arrêt RESERVED (aucune case : `feature-accept`), dates proposées : 2026-12-06,
2026-12-16 et 2027-01-15.

## Décidé

| Décision | Par | Va dans |
|---|---|---|
| Problème recentré sur les dépendances et le constat récurrent (0 sur 288 sur les six classes dans forge) | `forge:product-owner`, P1 | cadrage, section 1 |
| Config et CI seules ne suffisent pas (`after_write`, `qc-gate`, `raised-number`) | `forge:staff-engineer`, T4, T7 | cadrage, section 1 |
| Métrique, alerte et trace de l'observabilité | `forge:staff-engineer`, T4 | cadrage, section 4 |
| Risques : faux blocage, contournement par Bash, `PLR1702` en preview | `forge:staff-engineer`, T2 | cadrage, section 5 |

## Resté ouvert

- Les huit exigences, le hors périmètre et la taille L sans coupe : réservés à l'humain, par
  `/forge:feature-accept` sur le cadrage.
- Les trois dates d'arrêt (2026-12-06, 2026-12-16, 2027-01-15) et leurs conditions : réservées à
  l'humain, de même.
- Les trois questions de #157 (catégories de `BLOCKER`, seuil N et fenêtre, ticket seul ou proposé),
  dont dépend EXI-07.
- Le recoupement avec un projet consommateur (cinquième question de `idee.md`).
