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

Réponses : ci-dessous.

#### Réponses du tour 1 (les deux agents ont lu la séance, le cadrage et le code ; recopiées, résumées)

**`forge:staff-engineer`, Q1 à Q8** (sources lues le 2026-11-23 : documentation des hooks de Claude Code,
documentation de ruff ; `PLR1702` y est encore en aperçu). Aucune case ne porte de veto. Q1 et Q2 sont
irréversibles (la forme de `stack` est la seule décision que le cadrage dit irréversible) ; les autres se
reprennent.

- **Q1, corrigée.** On compare les paquets directs de chaque paquet local du verrou, c'est-à-dire ceux dont
  la source est `virtual`, `editable`, `directory` ou `path`, tous groupes confondus (normal, optionnel,
  développement). Pour npm, l'entrée `""` et celles des espaces de travail. Le seul manifeste racine ne
  suffit pas : le verrou de Shipyard (`uv.lock`) a une racine et trois membres locaux, que j'ai relus.
  `MATRIX_CELL: T4`.
- **Q2, corrigée.** Seule la clé `stack` (le chemin du fichier) se lit sur la base ; le contenu de la liste
  se lit sur la tête, puisque la PR propose elle-même la ligne. Chaque ligne que la PR ajoute à la liste
  sort `ADDED` avec sa source, que le juge lit au titre de F-8 ; une source absente sur la tête donne
  `NO SOURCE`. `MATRIX_CELL: T2`.
- **Q3, suivie.** `lint-on-write` partage le code de `format-on-write`. Le message à l'agent garde la forme
  `<clé>: <commande> failed on <chemin> (<raison>)`, avec la fin de la sortie en dessous ; `format-on-write`
  la relaie aussi. « Jamais la commande » ne vaut que pour le journal (Q8). `MATRIX_CELL: T4`.
- **Q4, suivie.** Le fichier de référence est celui que nomme l'entrée `never-weaken` (par exemple
  `scripts/baselines/types.txt | raised-entry`). Dans chaque fichier du diff, chaque clé des lignes ajoutées
  se compare à la même clé dans les lignes retirées du même fichier : une clé sans ligne retirée, ou avec un
  nombre plus grand, est une hausse. Une `<clé>` seule compte 1. `MATRIX_CELL: T4`.
- **Q5, suivie.** Sonde de `forge:qc-gate`, commande lue sur la base. Le fichier qui décrit la carte des
  modules (par exemple `.importlinter`) est lu sur la tête et une PR pourrait l'affaiblir : le gabarit
  conseille une entrée `.importlinter | removed-line`, et la PR qui retire une règle de la carte revient à
  l'humain. `MATRIX_CELL: T4`.
- **Q6, corrigée.** Le commentaire est écrit sur le ticket de la clé `slo-issue`, séparé du rapport des SLO,
  retrouvé par un marqueur caché qui lui est propre (le rapport des SLO a le sien, `factory_slo.py:925`).
  Il est réécrit après chaque verdict que `forge:qc` poste, non après chaque fusion ; le lecteur de verdicts
  de `factory_slo.py` (lignes 275 à 302) est réutilisé. `MATRIX_CELL: T2`.
- **Q7, suivie.** Une section du gabarit `usine.md` et une page de `docs/`, plus un exemple de `stack` ; les
  lignes de ruff écrivent les seuils 10, 5 et 5 en clair, avec `--preview` pour `PLR1702`. `MATRIX_CELL: T7`.
- **Q8, suivie.** Les refus de `after_write` entrent dans le même journal, `guard` à `after_write`, sans la
  commande ni la sortie. L'indicateur `guard-refusals` garde son sens (refus des trois gardes par PR
  fusionnée) en ne comptant que `guard_git`, `guard_coder` et `guard_readonly`. `MATRIX_CELL: T4`.
- Non vérifié par l'agent : l'entrée racine de `package-lock.json`, le plafond du stderr en code 2, le
  lancement d'un script du plugin dans la CI du projet.

**`forge:product-owner`, Q9 et Q10** (aucun veto).

- **Q9, corrigée.** Trois rôles : l'humain du projet, le coder, le juge. Le mainteneur de forge sort de la
  spec : le code de forge lui-même est hors périmètre (`cadrage.md`, section 2). Sept stories, une par
  exigence ; EXI-08 devient un critère transverse. Ordre : EXI-02 et EXI-03 ; puis EXI-06, EXI-04, EXI-05 ;
  puis EXI-07 ; puis EXI-01. Mis en premier, EXI-06 est ce que la coupe du 2026-12-16 garde (`cadrage.md`,
  section 8) ; l'ordre d'origine (EXI-04, EXI-05, EXI-06) la mettait après. `MATRIX_CELL: P1, P2`.
- **Q10, corrigée.** Le premier message de refus d'une dépendance donne la ligne exacte à écrire et le chemin
  de `stack`. Sortie relayée : les 20 dernières lignes et 2000 octets au plus (`trim_output.py`,
  `KEEP_LINES = 20` ; les hooks de Claude Code gardent un aperçu de 2000 caractères d'une sortie
  de plus de 10 000, documentation lue le 2026-11-23). Constat récurrent : 3 PR distinctes en 30 jours, déjà
  décidé. Délai par écriture : 30 s par commande et 120 s au total, les valeurs de `after_write.py:45-46`.
  Ajouter un contrôle : une ligne dans `usine.md`, sans budget de temps. `MATRIX_CELL: P1, P3`.

## Décidé

- Q1 à Q10 : les réponses ci-dessus, telles que les deux agents les ont rendues. Ce que la spec en tire est
  dans `spec.md`, qui reste à l'état `en-revue`.
- Les deux dates d'arrêt du cadrage (2026-12-06, 2026-12-16) et la mesure du 2027-01-15 restent celles de
  l'humain : la spec ne les change pas.

## Resté ouvert

- Rien du tour 1 : les dix questions ont une réponse. Les trois points que le staff-engineer n'a pas vérifiés
  (entrée racine de `package-lock.json`, plafond du stderr en code 2, script du plugin dans la CI) sont
  repris dans la section « Points ouverts » de la spec.
- Le recoupement des deux relevés de la section 1 du cadrage (149 PR fusionnées contre 121 PR jugées) :
  hors de la spec, à éclaircir avant la mesure de la section 4 du cadrage.
