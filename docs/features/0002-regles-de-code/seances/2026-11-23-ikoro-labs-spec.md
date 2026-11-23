---
feature: F-0002
seance: 2026-11-23-ikoro-labs-spec
participants: ikoro-labs (humain, a tapé `/forge:feature-spec`), l'agent de la session forge, forge:staff-engineer et forge:product-owner (agents décideurs)
sujet: écrire la spec de F-0002 (stories, critères, exigences, contrôles, gabarits, contrats)
---

# Séance du 2026-11-23 : spec de F-0002

Écrite pendant la séance, tour par tour, jamais réécrite ensuite. Une correction se fait dans une
séance suivante, qui cite celle-ci. Elle suit `2026-11-22-ikoro-labs-brainstorm.md` et
`2026-11-22-ikoro-labs-cadrage.md`, dont les décisions sont reprises telles quelles. Les deux agents
décideurs n'écrivent pas : l'agent de la session recopie leurs réponses, résumées, avec leurs lignes
`MATRIX_CELL`. Les questions techniques passent d'abord à `forge:staff-engineer`, les questions
produit à `forge:product-owner`, chacune avec la recherche de la pratique établie.

## Sources apportées

| Source | Où | Empreinte | Ce qui en est retenu |
|---|---|---|---|
| Cadrage accepté de F-0002 | `cadrage.md` (accepté le 2026-11-23, PR #298) | sans objet (versionné) | les huit exigences EXI-01 à EXI-08, le hors périmètre, les dates d'arrêt |
| Code lu à la base `2651b33` | `plugins/forge/hooks/after_write.py`, `plugins/forge/scripts/never_weaken.py`, `plugins/forge/scripts/lockfile_age.py`, `plugins/forge/hooks/refusal_journal.py`, `plugins/forge/templates/usine.md` | sans objet (versionné) | `format-on-write` existe déjà (même grammaire que `lint-on-write`, sortie jetée) ; `baselines` existe déjà (un chemin par ligne, « aucun outil encore ») ; `never_weaken.py` connaît trois types ; `lockfile` lit `uv.lock` (pypi) et `package-lock.json` (npm) ; `refusal_journal.py` n'est appelé que par trois gardes |
| `source_ids.py` | clé `product-source` absente de `usine.md` | sans objet | la source produit de la spec est le cadrage : les éléments identifiés sont EXI-01 à EXI-08 |

## Tours

### Tour 1

Questions techniques, à `forge:staff-engineer`.

**Q1. Que contient `stack` et que compare le contrôle : les paquets directs, ou tous ceux du verrou ?**
Un verrou liste aussi les dépendances indirectes ; les ajouter toutes à la liste ferait refuser à tort
(faux blocage, risque de la section 5 du cadrage). Recommandation : écosystèmes fermés, ceux de la clé
`lockfile` (`pypi`, `npm`) ; nom normalisé (pypi : casse, `-`, `_` et `.` équivalents) ; seuls les
paquets directs se comparent (ceux que le manifeste racine déclare, lus dans le verrou), les indirects
restant à la sonde d'âge de `lockfile_age.py`.

**Q2. Où le contrôle des dépendances refuse-t-il, et que rend-il ?** Recommandation : un script
`stack_check.py`, lancé par `forge:qc-gate` avec les clés lues sur la base (une PR ne relève pas la liste
qui la juge), une ligne par paquet ajouté (`OK`, `UNLISTED`, `NO SOURCE`, `NOT RUN`, `INVALID`) ;
`forge:qc-conf` fait de `UNLISTED` et de `NO SOURCE` un `BLOCKER` ; la CI du projet rejoue la même
commande ; aucun hook sur Bash.

**Q3. `lint-on-write` : une clé de plus à côté de `format-on-write`, ou une extension ?**
`format-on-write` a déjà la grammaire `<motif> | <commande>`, l'exécuteur, les délais et le code 2 ;
seule la sortie est jetée (`after_write.py:102-111,146`). Recommandation : `lint-on-write` partage le
code de `format-on-write`, relaie la fin de la sortie à l'agent (bornée en lignes et en octets, jamais
la commande), et `format-on-write` la relaie aussi, car la sortie jetée est le défaut constaté.

**Q4. `raised-entry` : quelle hausse refuse-t-il, et que devient la clé `baselines` ?**
Recommandation : type `<chemin> | raised-entry`, sans paramètre ; la liste de référence est un fichier de
lignes `<nombre> <clé>` ou `<clé>` seule ; une hausse est une clé nouvelle, ou un nombre plus grand que
celui de la base ; une baisse ou un retrait passe ; le chemin vient de l'entrée `never-weaken`, comme
pour les trois autres types ; `baselines` reste la liste des chemins que `F-13` fait lire au juge, sans
être lue par le script.

**Q5. `architecture-check` : comment la sonde le lance-t-elle ?** Recommandation : une sonde de
`forge:qc-gate`, commande lue sur la base, lancée sous le lanceur borné avec les limites de `run-limits`,
rendue `PASS`, `FAIL` ou `NOT RUN` ; clé absente : « sans objet (clé `architecture-check` absente) » ;
un `FAIL` est un `BLOCKER` au titre de `F-15` ; la CI du projet lance la même commande.

**Q6. Constat récurrent : qui compte, où et quand ?** Recommandation : un script
`recurring_findings.py` lit les commentaires de verdict des PR jugées dans la fenêtre (clé
`recurring-finding : 3 | 30`), compte les PR distinctes par `F-n` ou `L-n`, et réécrit un commentaire
unique sur le ticket de la clé `slo-issue`, retrouvé par un marqueur caché, distinct du rapport des SLO ;
lancé par `forge:qc` après chaque fusion ; un constat sans identifiant se compte à part.

**Q7. EXI-01 : sous quelle forme la base de règles est-elle livrée ?** Recommandation : une section du
gabarit `usine.md` et une page de `docs/`, sans fichier de plus : lignes d'exemple de `lint-on-write`
pour ruff (complexité 10, paramètres 5, imbrication 5 avec la règle `PLR1702` et la version de ruff
épinglée), et la forme de la carte des modules en exemple de `architecture-check`.

**Q8. Le journal des refus couvre-t-il `lint-on-write` ?** Recommandation : oui, une ligne par refus de
`after_write` (garde `after_write`, règle nommée par la clé : `lint-on-write` ou `format-on-write`),
mêmes champs que les trois gardes, jamais la commande ni la sortie.

Questions produit, à `forge:product-owner`.

**Q9. Les rôles des stories et leur ordre.** Recommandation : quatre rôles (l'humain du projet, le coder,
le juge, le mainteneur de forge), huit stories, une par exigence, dans l'ordre des lots : dépendances
d'abord (EXI-02, EXI-03), puis écriture (EXI-04, EXI-05), cliquet (EXI-06, EXI-07), base et
documentation (EXI-01, EXI-08), selon la règle P2 sur l'ordre.

**Q10. Les chiffres des critères que le cadrage laisse ouverts.** Recommandation : refus d'une
dépendance : la ligne à écrire figure dans le premier message de refus ; relais de la sortie : 20 lignes
et 2000 octets au plus ; constat récurrent : 3 PR distinctes en 30 jours, comme décidé ; temps d'ajout
d'un contrôle : aucun budget, une exécution de la commande suffit.

Réponses : en attente.

## Décidé

(Rien encore : le tour 1 est posé, les réponses des agents ne sont pas arrivées.)

## Resté ouvert

- Q1 à Q10 de ce tour, avec leurs réponses.
- Le recoupement des deux relevés de la section 1 du cadrage (149 PR fusionnées contre 121 PR jugées) :
  hors de la spec, à éclaircir avant la mesure de la section 4 du cadrage.
