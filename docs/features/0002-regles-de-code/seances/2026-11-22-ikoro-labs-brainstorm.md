---
feature: F-0002
seance: 2026-11-22-ikoro-labs-brainstorm
participants: ikoro-labs (humain), l'agent de la session forge, forge:staff-engineer (agent décideur)
sujet: trancher les premières questions de l'idée F-0002 avant le cadrage
---

# Séance du 2026-11-22 : les premières questions de F-0002

Écrite pendant la séance, tour par tour, jamais réécrite ensuite. Une correction se fait dans une
séance suivante, qui cite celle-ci.

Les décisions sont celles de `forge:staff-engineer`, rendues en réponse aux quatre premières
questions de `idee.md` (Q1 à Q4) et à une question de périmètre que la séance ajoute (Q5) ; la
cinquième question de `idee.md`, le recoupement avec un projet consommateur, reste ouverte. Il n'a
rien écrit lui-même, l'agent de la session les recopie ici. Les questions techniques sont passées à
l'agent décideur avant tout humain (`autonomie.md`, étape 3).

## Sources apportées

| Source | Où | Empreinte | Ce qui en est retenu |
|---|---|---|---|
| NIST SP 500-235, « Structured Testing », §2.5 | hors dépôt : publication publique, citée par sa référence | sans objet | la complexité cyclomatique de 10 comme seuil de référence |
| Commentaire de l'issue #291 sur la clôture de #157 | issue #291 | sans objet | les trois questions de #157 sont absorbées par F-0002 et restent à poser |

## Tours

### Tour 1

**Q1. Le jeu de règles livré en gabarit, et un plafond de lignes malgré l'absence de source ?**
Recommandation : la base de l'idée (complexité, imbrication, paramètres, carte des modules, pile),
sans plafond de lignes.
Réponse de `forge:staff-engineer` : DECIDED. Base retenue, sans plafond de lignes (aucune source ne
relie une longueur aux défauts). Complexité cyclomatique 10 (NIST SP 500-235 §2.5), paramètres 5,
imbrication 5 (le défaut de ruff : le 4 n'a pas de source). `MATRIX_CELL` : T7, T4, T3.

**Q2. Où vit la liste des dépendances permises, et comment une décision l'ajoute-t-elle sans refus
silencieux ?**
Recommandation : un fichier du projet nommé par une clé.
Réponse de `forge:staff-engineer` : DECIDED. La clé `stack` est un fichier de lignes
`<écosystème> | <paquet> | <ADR accepté ou séance>`. Le script refuse un paquet hors liste ou une
source absente, et nomme la ligne à écrire (jamais de refus muet). Les manifestes sont lus par la
clé `lockfile` de #155. Ligne `MATRIX_CELL` : non reportée dans la passation qui a transmis la
décision.

**Q3. La forme des clés `lint-on-write` et `architecture-check`, et leur rendu quand elles manquent ?**
Recommandation : une commande par clé, « sans objet (clé absente) » sans valeur par défaut.
Réponse de `forge:staff-engineer` : DECIDED. `lint-on-write` est une ligne `<motif> | <commande>`
lue dans `after_write` (la commande qui échoue sort en code 2). `architecture-check` est une
commande, lancée par la sonde de `forge:qc-gate` et par la CI. Une clé absente rend « sans objet
(clé `<nom>` absente) ». Pas de nouveau garde (H1 : un garde nouveau toucherait un
`protected-path`, donc une fusion humaine). Ligne `MATRIX_CELL` : non reportée dans la
passation qui a transmis la décision.

**Q4. Le cliquet : où vit la liste de référence, quelle commande refuse une hausse, et le chemin
d'un constat récurrent du juge ?**
Recommandation : la liste dans `baselines`, contrôlée par `never-weaken`.
Réponse de `forge:staff-engineer` : DECIDED. La liste de référence vit dans `baselines`. Un nouveau
type `never-weaken`, `raised-entry`, refuse la hausse : `raised-number` laisse passer une dette
ajoutée seule (`never_weaken.py:165-169`). Un constat `MINOR` qui revient devient un commentaire,
jamais un ticket. `MATRIX_CELL` : T3.

**Q5. Le périmètre de la feature et son découpage.**
Recommandation : neuf lots, de `never-weaken` jusqu'à la documentation.
Réponse de `forge:staff-engineer` : RESERVED. Aucune case de la matrice ne tranche le périmètre
(P2, citée par l'agent, ne couvre que l'ordre dans un périmètre déjà accepté) : il s'accepte par
l'humain, avec `feature-accept`. Hors périmètre
proposé : #155 (suivi à part), le garde de commande Bash, le code de forge lui-même. Tout est
réversible, sauf la forme de la clé `stack` (Q2).

## Décidé

| Décision | Par | Va dans |
|---|---|---|
| Base sans plafond de lignes ; complexité 10, paramètres 5, imbrication 5 | `forge:staff-engineer`, T7, T4, T3 | cadrage |
| Clé `stack` : fichier de lignes `<écosystème> \| <paquet> \| <source>`, refus qui nomme la ligne à écrire | `forge:staff-engineer` | cadrage, puis spec |
| `lint-on-write` (`<motif> \| <commande>`, `after_write`) et `architecture-check` (commande, sonde et CI) ; clé absente, « sans objet » ; pas de nouveau garde | `forge:staff-engineer`, H1 | cadrage, puis spec |
| Liste de référence dans `baselines` ; type `never-weaken` `raised-entry` ; un `MINOR` récurrent devient un commentaire | `forge:staff-engineer`, T3 | cadrage, puis spec |

## Resté ouvert

- Le périmètre en neuf lots, et ce qu'il laisse dehors (#155, garde Bash, code de forge) : réservé à
  l'humain de la clé `accepting-human`, par `/forge:feature-accept` sur le cadrage.
- Les trois questions de #157, à poser à `forge:staff-engineer` : la liste fermée des catégories de
  BLOCKER, le seuil N et la fenêtre, et si la proposition ouvre un ticket seule ou passe à l'humain.
- Le recoupement avec les travaux d'un projet consommateur sur un catalogue de règles partagé : non
  traité dans cette séance.
