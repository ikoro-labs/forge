---
name: feature-review
description: "Revue de bout en bout d'une feature livrée : l'application réelle lancée, le parcours voulu joué dans un vrai navigateur sur des captures en clair et en sombre, sur bureau et sur mobile, chaque écran jugé contre la source par un juge en lecture seule, puis la matrice mise à jour, un ticket par lot d'écarts et un rapport dans la page de la feature. À lancer quand les tickets d'une feature sont fusionnés, jamais par l'agent qui a codé."
argument-hint: F-NNNN [--ecrans "Écran n, Écran m"]
---

# Revue de bout en bout d'une feature

`forge:qc` juge une PR contre son ticket et son diff. Cette revue juge **l'écran contre la source** :
une feature dont chaque PR a passé `forge:qc` peut contredire la demande de l'expert. Ici, le juge ne
lit ni le diff ni les tickets, seulement la source (clé `product-source`), le parcours voulu
(`parcours.md`), le glossaire (clé `glossary`) et des captures prises sur l'application qui tourne.

Quatre rôles, tous distincts de celui qui a codé :

| Rôle | Qui | Ce qu'il fait |
|---|---|---|
| Exécution | toi, dans ta session | lance l'application, joue le parcours, prend les captures |
| Jugement | `forge:review-judge`, en lecture seule | un état et une gravité par identifiant de la source |
| Seconde lecture | `forge:review-recheck`, en lecture seule | relit chaque `tenu` avant publication |
| Publication | toi | matrice, tickets, rapport |

L'exécution reste dans ta session : elle lance un navigateur ou commande un poste, et les outils de
pilotage d'une session ne passent pas à un agent à la liste d'outils fixe. Le jugement est à part,
comme `forge:qc-gate` et `forge:qc-conf` le sont pour une PR : un agent qui exécute écrit des
fichiers, un juge n'écrit rien. Le hook `guard_readonly` borne le Bash des deux agents aux lectures,
et le hook `guard_coder` refuse ce skill à `forge:coder`.

Le projet décrit son usine dans `docs/agents/usine.md` ; ce skill en lit les clés `feature-dir`,
`product-source`, `source-author`, `glossary`, `ui-forbidden-word`, `journey-replay`,
`screenshot-command`, `recording-command`, `browser-drive` et `computer-use-host`. Une clé absente
rend son étape « sans objet (clé `<nom>` absente) », jamais `PASS` : forge ne devine aucune valeur.

## Étapes

1. **Préparer.** Le dossier de la feature est `<feature-dir>/NNNN-<slug>/`. Il faut `parcours.md` et
   `matrice.md` : lance `scripts/parcours.py` et `scripts/matrice.py` dessus, un constat s'arrête
   là. Sans la clé `product-source`, il n'y a pas de source à laquelle juger : « sans objet (clé
   `product-source` absente) », arrête-toi et dis-le.
2. **Exécuter.** Joue le parcours voulu de bout en bout dans l'application réelle, avec un compte et
   un jeu de données de démonstration, et prends chaque écran du parcours en **clair et en sombre,
   sur bureau et sur mobile**.
   - La commande de la clé `journey-replay` (sa partie après ` | `) joue le parcours depuis un dépôt
     propre ; sinon `screenshot-command` ou `recording-command`. `{out}` est un dossier que tu crées
     hors de tout dépôt (`mktemp -d`) et où tu laisses les fichiers tels que la commande les écrit.
   - `browser-drive` et `computer-use-host` ne servent que sur le poste que la clé nomme, jamais en
     CI : vérifie le nom du poste (`hostname`) avant, et si ce n'est pas lui, n'y recours pas.
   - Aucune de ces clés : « sans objet » pour chacune, et la revue s'arrête. Elle ne juge **jamais**
     un écran d'après le code ou les tests : sans capture, pas de revue.
   - Les captures sont réelles et non retouchées. Ne les remplace jamais par un écran dessiné ou
     décrit.
3. **Écrire le manifeste** `manifeste.tsv` : une ligne `CAPTURE` par fichier pris (fichier, écran,
   thème, taille), une ligne `NON-JOUE` par écran que tu n'as pas pu jouer avec sa raison, et des
   lignes `ENVIRONNEMENT` : le `système` (obligatoire : ce qui n'a tourné que sur un système le dit),
   le navigateur, la version de l'application, le compte et le jeu de données de démonstration.
   Puis :

   ```
   uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/revue_bout_en_bout.py" manifeste --captures <dossier> parcours.md manifeste.tsv
   ```

   Un `MANQUE` se rejoue une fois ; au second échec, il reste dans le rapport comme variante non
   vue, jamais comblée. Un `INVALID` ou un `SANS-ENVIRONNEMENT` se corrige.
4. **Juger.** Lance `forge:review-judge` avec : les fichiers de la clé `product-source`,
   `parcours.md`, `matrice.md`, les fichiers de la clé `glossary` et les mots de la clé
   `ui-forbidden-word`, le manifeste et le dossier des captures. Pas le diff, pas les tickets. Écris
   son verdict dans `verdict.tsv`, puis :

   ```
   uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/revue_bout_en_bout.py" verdict verdict.tsv --matrice matrice.md --manifeste manifeste.tsv --captures <dossier>
   ```

   Sur écrans touchés, ajoute `--ecrans "<liste>"` à cette commande et aux suivantes.
   Il ne doit rester que des lignes `A-RELIRE` (et des `SUSPECT`, qui sont à la seconde lecture). Tout
   autre constat (`NON-JUGE`, `CONTRADICTION`, `INVALID`, `SANS-FICHIER`, `HORS-MANIFESTE`) revient
   au juge, avec la ligne du script, une fois ; au second échec, arrête-toi et pose
   `needs-your-attention`.
5. **Seconde lecture.** Lance `forge:review-recheck` avec le verdict, la sortie du script, la source,
   `parcours.md` et les captures. C'est un agent distinct du juge, parce qu'un juge qui se relit
   confirme ce qu'il a déjà écrit. Écris ses lignes dans `relecture.tsv` et relance la commande de
   l'étape 4 avec `--relecture relecture.tsv`. Un `CONTESTE` ou un `NON-RELU` revient au juge pour cet
   identifiant seulement, puis à la seconde lecture ; deux tours au plus.
6. **Publier**, une fois la commande propre :

   ```
   uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/revue_bout_en_bout.py" verdict verdict.tsv --matrice matrice.md --manifeste manifeste.tsv --captures <dossier> --relecture relecture.tsv --appliquer --date <AAAA-MM-JJ> --tickets
   ```

   - **La matrice** est mise à jour par ce script, qui ne change que l'état, la capture et la date du
     jugement d'une ligne et ne l'écrit que si `matrice.py` accepte le résultat. Un élément `écarté`
     n'est jamais jugé, et la revue n'en écrit aucun.
   - **Les tickets.** Sa sortie `TICKET` donne un lot par gravité et par lot de la spec, du plus grave
     au moins grave. Rédige un ticket par lot : titre, gravité, capture, identifiants de la source cités,
     constat, et un **critère de sortie** (« chaque identifiant repasse `tenu` à la revue suivante,
     capture à l'appui »), la ligne `Couvre : <identifiants>` que `forge:qc-conf` lit et la ligne
     `Feature: F-NNNN`. Ils sont étiquetés `ready-for-agent` et `gravite:<gravité>` (`bloquant`,
     `majeur` ou `mineur`, celle de leur ligne `TICKET`) : les indicateurs de la revue de
     `factory_slo.py` les comptent par cette étiquette. Ils sont rattachés à l'issue de suivi de la
     feature (`issue:` de `idee.md`). Avant de publier le premier, vérifie par `gh label list` que
     `ready-for-agent` et les étiquettes de gravité des lots (`bloquant`, `majeur`, `mineur`) existent
     (`docs/installation.md`) : le skill ne les crée pas, et s'il en manque une il ne publie rien et le
     dit en nommant l'étiquette. Lancé par `forge:feature-build` (étape 3 bis), le passage les
     publie lui-même, sans accord de l'humain : c'est la boucle, et un geste humain l'arrêterait.
     Lancé à la main, hors de la boucle, la session qui l'a lancé montre les brouillons et ne les
     publie qu'après l'accord de l'humain de la clé `accepting-human`. Le skill ne câble aucun
     projet : le dépôt et les étiquettes sont ceux du projet.
   - **Le rapport** enrichit la page de la feature, sans en créer une nouvelle : une section
     « Revue de bout en bout » ajoutée à `recette.md` (ou, si la feature est déjà close, à la section
     « Ses limites » de son `README.md`). Elle dit la date, le système et ce qui n'a pas été vu, la
     couverture (`scripts/matrice.py --reste`), les écarts par gravité avec leur ticket, les `NON-JOUE`,
     et reprend les captures citées, copiées dans le dossier de la feature sous `revue/`.
7. **Livrer** le tout dans une PR vers la base : matrice, rapport, captures citées, et le compte
   rendu ci-dessous écrit dans le dossier de la feature sous `revue/compte-rendu.txt` (c'est là que
   `forge:feature-verify` et `forge:feature-build` le lisent pour la porte de la recette). La revue ne
   corrige jamais le code d'une feature : ce sont les tickets qui repartent en construction.

## Gravité

Trois niveaux, aux définitions fixes, que le juge applique tels quels :

- `bloquant` : l'expert le voit en quelques minutes, et cela contredit sa demande ou rend l'écran
  incompréhensible ;
- `majeur` : cela gêne le travail ou la confiance ;
- `mineur` : le reste.

La gravité dit ce que l'expert vivrait. Elle ne dépend ni du coût de la correction ni de la PR
d'où vient l'écart.

## Ce qui n'est pas ici

La boucle (déclencher la revue à la fusion, porte de recette, arrêt sur un écart revenu) est celle de
`forge:feature-build`, étape 3 bis, avec `scripts/revue_boucle.py` ; les indicateurs de la revue sont
à part. Deux portées :

- **En entier** (par défaut) : tous les écrans du parcours, tous les éléments de la matrice.
- **Sur écrans touchés** (`--ecrans "Écran 2, Écran 3"`, donnés par la ligne `ECRAN` de
  `revue_boucle.py declencher`) : les écrans hors de la liste sont écrits `NON-JOUE` au manifeste
  (« hors de la revue sur écrans touchés »), et la commande de l'étape 4 reçoit
  `--ecrans "Écran 2, Écran 3"` : seuls les éléments de ces écrans sont jugés. Une ligne du verdict pour un
  élément d'un autre écran (le juge dit `absent` un écran non joué) est écartée, ligne `HORS-PORTEE` :
  `--appliquer` ne l'écrit pas, `--tickets` n'en fait pas un ticket, et la ligne de la matrice garde
  son état et sa capture. Une revue sur écrans touchés n'ouvre jamais la recette.

Ce skill se termine par un compte rendu que ces étapes lisent :

```text
RESULT: REVUE
FEATURE: F-NNNN
COUVERTURE: <tenus et écartés>/<total>, <pourcentage> %
ECARTS: bloquant <n>, majeur <n>, mineur <n>
TICKETS: brouillons | publiés (#n, #m)
PORTEE: entière | écrans touchés (<Écran n>, ...)
RAPPORT: <fichier de la page de la feature>
SYSTEME: <ce sur quoi la revue a tourné, et ce qu'elle n'a pas vu>
```

## Ce qui est éprouvé

Le script et les agents n'ont tourné que sur des fichiers écrits à la main, sous Linux, avec les
tests du dépôt de forge. Aucun vrai navigateur ni aucune application réelle n'ont encore servi à
cette revue, aucun expert métier n'a relu un rapport, et le jugement d'une capture par le juge n'a
été essayé sur aucune image réelle. Corrige le skill de ce que le premier vrai passage en dira.
