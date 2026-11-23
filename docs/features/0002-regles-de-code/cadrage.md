---
feature: F-0002
document: cadrage
statut: en-revue
taille: L
destinataires: ikoro-labs (humain de la clé `accepting-human`, décide par `/forge:feature-accept`) ; forge:qc relit
contexte: forge (plugin) ; touchés : hooks, forge:qc-gate, never-weaken, template `usine.md`
base: 28ab594
date: 2026-11-22
---

# F-0002 : cadrage

Un projet qui adopte forge fige au cadrage sa pile et ses règles de code, et l'outil les fait tenir
pendant que l'agent écrit : une dépendance hors liste est refusée avec la ligne à écrire, une dette
ne peut pas monter en silence, un constat récurrent du juge devient un commentaire. La feature
mesure si l'on relève ainsi hors du juge ce qu'il relevait à la lecture, sans bloquer l'agent à tort ;
la base est faible (3 constats sur 303, section 4), et la feature ne promet pas un gain avant sa mesure.

## 1. Problème

**Qui souffre, de quoi.** Celui qui relit une PR, et le juge qui relève à la lecture une règle
qu'un outil aurait mesurée. Le chiffre est faible, et le cadrage le dit : sur les verdicts de ce
dépôt, 0 finding sur 288 (69 `BLOCKER`, 219 `MINOR`) porte sur les six classes (format, complexité,
imbrication, paramètres, modules, dépendances), 149 PR fusionnées, du 2026-10-23 au 2026-11-22
(`forge:product-owner`, séance de cadrage, Q1). Sur Shipyard, 17 sur 721, dont 12 sur les
dépendances. Trop peu pour conclure sur les six classes : le problème est recentré sur les
dépendances et sur le constat récurrent (`_derouler` relevé cinq fois, Shipyard #86 à #94). Les
verdicts encore en revue ne sont pas comptés, et les findings hors du filtre ne sont pas lus un par un.
Deux relevés distincts, non rapprochés : 288 findings sur 149 PR fusionnées (ici), et 303 `BLOCKER` et
`MINOR` sur 121 PR jugées (sections 4 et 6) ; la différence de périmètre n'est pas éclaircie.

**Pourquoi pas plus simple.** Ruff et une étape de CI suffiraient pour un projet Python seul, mais
pas ici (`forge:staff-engineer`, T4, T7) : `after_write` jette la sortie de l'outil
(`after_write.py:102-111,146`), aucune sonde de `forge:qc-gate` ne contrôle l'architecture ni les
dépendances, `raised-number` laisse passer une dette ajoutée seule (`never_weaken.py:167-169`), les
constats F-8 et F-15 du juge restent en lecture seule, et la configuration de ruff ne vaut que pour
Python.

**Le cas d'usage unique.** Un projet déclare `stack` (liste des paquets permis) et `lint-on-write`.
Le coder ajoute une dépendance absente de la liste : le contrôle des dépendances échoue et nomme la
ligne `<écosystème> | <paquet> | <ADR ou séance>` à écrire. Le coder la propose avec sa décision, la
PR passe `forge:qc-gate`, et la liste a la source de la décision. Plus tard, une PR hausse une
entrée de `baselines` : `raised-entry` la refuse.

## 2. Périmètre

Les exigences sont une proposition de `forge:product-owner` (RESERVED, aucune case : `feature-accept`).

| Exigence | Contenu | Preuve |
|---|---|---|
| EXI-01 | Base de règles livrée en gabarit : complexité cyclomatique 10, paramètres 5, imbrication 5, carte des modules, pile ; sans plafond de lignes | NIST SP 500-235 §2.5 pour le 10 ; 5 est le défaut de ruff ; aucune source ne relie une longueur aux défauts (brainstorm Q1, T7, T4, T3) |
| EXI-02 | Clé `stack` : fichier de lignes `<écosystème> \| <paquet> \| <ADR accepté ou séance>` ; refus d'un paquet hors liste ou d'une source absente, qui nomme la ligne à écrire | brainstorm Q2 (case non reportée) ; la forme de `stack` est la seule décision irréversible |
| EXI-03 | Contrôle des dépendances : la liste permise comparée au diff, manifestes lus par la clé `lockfile` | brainstorm Q2 ; s'appuie sur #155 (fermé le 2026-11-22, PR #294 fusionnée) |
| EXI-04 | Clé `lint-on-write` : lignes `<motif> \| <commande>` lues dans `after_write` ; la commande qui échoue sort en code 2 ; sortie relayée à l'agent | brainstorm Q3 (H1 : pas de nouveau garde) |
| EXI-05 | Clé `architecture-check` : une commande, lancée par une sonde de `forge:qc-gate` et par la CI | brainstorm Q3 |
| EXI-06 | Type `never-weaken` `raised-entry` : la liste de référence vit dans `baselines`, une hausse est refusée | brainstorm Q4 (T3) ; `raised-number` ne suffit pas |
| EXI-07 | Un constat `MINOR` récurrent du juge devient un commentaire, jamais un ticket | brainstorm Q4 ; seuil et fenêtre tranchés (section 7) ; reprend les trois questions de #157 |
| EXI-08 | Documentation : gabarit `usine.md` pour chaque clé nouvelle, page de `docs/`, `CHANGELOG.md` | `.claude/rules/forge.md` (version et journal) |

Une clé absente rend « sans objet (clé `<nom>` absente) », sans valeur par défaut. Noms de clés
provisoires jusqu'à la spec.

**Hors périmètre.** Le garde de commande Bash (un hook se contourne, la CI tranche en dernier) ; le
code de forge lui-même ; un plafond de lignes ; la licence ; un catalogue de règles partagé avec un
projet consommateur (cinquième question de `idee.md` : `socle.md` est déjà ce catalogue, selon
`forge:staff-engineer` et `forge:product-owner`, 2026-11-23). À reporter en commentaire de
#291. #155 reste suivi à part.

## 3. Condition d'entrée

Sans objet (clé `entry-gate` absente). L'humain de la clé `accepting-human` en décide en acceptant ce cadrage.

## 4. Observabilité

| Question | Réponse |
|---|---|
| Quelle métrique prouve que ça marche | Constats du juge qui citent F-8, F-13, F-15, F-17 ou L-n, par PR jugée, sans cible (`qc-conf.md:330`). Base du 2026-11-22 : 3 constats F-13 sur 303 `BLOCKER` et `MINOR`, 121 PR jugées |
| Quelle alerte si ça casse | `raised-entry` qui s'applique, ou une sonde de `forge:qc-gate` en `FAIL` |
| Que voit-on dans une trace | À ajouter : la sortie de l'outil relayée à l'agent (règle et ligne), une ligne de journal jsonl par refus (`refusal_journal.py`), et les sondes de `forge:qc-gate` |

## 5. Risques

| Risque | Mitigation | Signal |
|---|---|---|
| Une règle bloque l'agent à tort (faux blocage) | Refus qui nomme la règle, la ligne et le remède ; jamais de refus muet | Refus répétés sur un même motif dans le journal jsonl |
| Contournement par une commande Bash ou un autre outil | La CI rejoue les mêmes commandes et tranche en dernier | Écart entre les refus de `lint-on-write` et les `FAIL` de la CI |
| La règle `PLR1702` (imbrication) de ruff est encore en preview | Lue le 2026-11-22 sur https://docs.astral.sh/ruff/rules/too-many-nested-blocks/ ; épingler la version de ruff et nommer la règle dans le gabarit | Une mise à jour de ruff change la règle ou la retire |

## 6. Faisabilité des données

Jeu de mesure : les verdicts des PR jugées de ce dépôt (121 PR jugées, 303 `BLOCKER` et `MINOR` au
2026-11-22). Les verdicts de Shipyard servent de témoin (721 findings), hors du jeu d'acceptation.
Exclus : les verdicts encore en revue, et les findings hors du filtre, que personne n'a lus un par
un. Aucune donnée ne prouve aujourd'hui un gain sur les six classes (0 sur 288) : la mesure suit
les constats récurrents et les dépendances, pas ces six classes.

## 7. Décisions

| Date | Décision | Par | Séance |
|---|---|---|---|
| 2026-11-22 | Base sans plafond de lignes ; complexité 10, paramètres 5, imbrication 5 | `forge:staff-engineer`, T7, T4, T3 | brainstorm |
| 2026-11-22 | Clé `stack` en fichier de lignes ; refus qui nomme la ligne à écrire | `forge:staff-engineer` | brainstorm |
| 2026-11-22 | `lint-on-write` et `architecture-check` ; clé absente, « sans objet » ; pas de nouveau garde | `forge:staff-engineer`, H1 | brainstorm |
| 2026-11-22 | Liste de référence dans `baselines` ; `raised-entry` ; un `MINOR` récurrent devient un commentaire | `forge:staff-engineer`, T3 | brainstorm |
| 2026-11-22 | Problème recentré sur les dépendances et le constat récurrent | `forge:product-owner`, P1 | cadrage |
| 2026-11-22 | Config et CI seules ne suffisent pas | `forge:staff-engineer`, T4, T7 | cadrage |
| 2026-11-22 | Métrique, alerte et trace de la section 4 ; risques de la section 5 | `forge:staff-engineer`, T4, T2 | cadrage |
| 2026-11-23 | #157, catégories : aucune liste nouvelle, la `Nature` et les `F-n`/`L-n` de `socle.md`, tenus par `guard_cases` ; un constat sans identifiant se compte à part | `forge:staff-engineer`, T3, T4, T2 | cadrage |
| 2026-11-23 | #157, seuil et fenêtre : 3 PR distinctes sur le même `F-n`/`L-n`, 30 jours glissants ; clé `recurring-finding : 3 \| 30`, absente : « sans objet » | `forge:staff-engineer`, T3, T4, T2 | cadrage |
| 2026-11-23 | #157, suite : aucun ticket ; un commentaire unique, réécrit, sur le ticket de suivi (clé `slo-issue`) ; sans doublon ; vaut aussi pour les `BLOCKER` | `forge:staff-engineer` ; `forge:product-owner` (P3, après acceptation) | cadrage |
| 2026-11-23 | Cadrage corrigé : phrase d'ouverture, deux relevés non rapprochés, #155 fermé | `forge:product-owner`, P1 | cadrage |
| à venir | Huit exigences, hors périmètre (catalogue partagé compris : `socle.md` en tient lieu), taille L sans coupe, dates d'arrêt | ikoro-labs, `/forge:feature-accept` | cadrage |

Restent ouvertes : le recoupement des deux relevés de la section 1 (149 PR fusionnées contre 121 PR
jugées), à éclaircir avant la mesure de la section 4 ; la forme exacte du commentaire est celle de la
spec. Les seuils chiffrés ci-dessus viennent de la lecture de sources publiques par
`forge:staff-engineer` (lues le 2026-11-23), dont le dénominateur de l'une n'a pas été retrouvé.

## 8. Critères d'arrêt

Dates proposées par `forge:staff-engineer` (RESERVED : l'humain les fixe à l'acceptation). Les
conditions ci-dessous sont celles que l'agent de la session propose avec elles.

| Vérification | Condition de poursuite | Si non atteinte |
|---|---|---|
| 2026-12-06 | EXI-02 et EXI-03 fusionnés, le refus de dépendance nomme la ligne à écrire (test vert, rouge sur la base) | Arrêter la feature, garder #155 seul |
| 2026-12-16 | EXI-04 à EXI-06 fusionnés, journal jsonl alimenté, aucun refus muet relevé | Couper : ne garder que `raised-entry` |
| 2027-01-15 | Mesure de la section 4 relevée sur les PR jugées depuis la fusion, comparée à la base du 2026-11-22 | Retirer les règles qui n'ont refusé aucun écart, ou clore la feature |
