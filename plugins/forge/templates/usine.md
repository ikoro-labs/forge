# Usine du projet

Gabarit de `docs/agents/usine.md`, le seul fichier où un projet décrit son usine au plugin `forge`.
Copie-le dans le projet, puis, pour chaque clé :

- remplace la valeur d'exemple par la vraie ;
- **ou supprime la ligne** si le projet n'a rien à y mettre.

Une clé absente n'est jamais une erreur : l'étape qui la lit se rend « sans objet (clé `<nom>`
absente) », jamais `PASS`, et aucun agent ne devine de valeur à sa place. Une ligne laissée avec sa
valeur d'exemple, elle, serait lue comme vraie : ne la laisse pas.

## Forme

Une entrée par ligne, qui commence par une puce, puis le nom et la valeur entre accents graves,
séparés par un deux-points : comme chaque ligne d'exemple plus bas. Une clé répétée sur plusieurs lignes donne une liste, dans l'ordre du fichier. Tout le reste (titres,
prose, tableaux, lignes sans cette forme exacte) est ignoré : commente librement. Les chemins sont
relatifs à la racine du dépôt.

## Personnes et décisions

Les humains qui acceptent un document de feature et à qui reviennent les décisions réservées. Une
ligne par humain, sa valeur égale à son `git config user.name`.

- `accepting-human` : `<user.name git du premier humain>`
- `accepting-human` : `<user.name git du second humain>`

La matrice des droits de décision : ce que `forge:staff-engineer` et `forge:product-owner` tranchent
seuls, sous veto, ou jamais. Sans elle, ils ne tranchent rien et rendent tout en `RESERVED`.

- `decision-matrix` : `<docs/agents/decisions.md>`

L'agent du projet qui tranche les questions de doctrine du métier (`DOMAIN`). Sans lui, elles vont à
un humain.

- `domain-arbiter` : `<nom de l'agent, par exemple domain-arbiter>`

Le référent du métier : quand l'arbitre rend `OPEN` (le corpus du projet ne tranche pas),
`forge:feature-build` le mentionne sur le ticket et suit la voie prudente sans arrêter le passage.
La valeur est le login GitHub sans `@` ; le skill ajoute le `@`. Sans la clé, la question va à un
humain par `ready-for-human`.

- `domain-owner` : `<login GitHub du référent, sans @>`

Les sources produit que lit `forge:product-owner`, une par ligne, **dans l'ordre de préséance** :
la plus haute gagne sur les suivantes.

- `product-source` : `<docs/produit/retours-terrain.md>`
- `product-source` : `<docs/produit/parcours.md>`

La règle qui dit si une feature entre au périmètre (`/forge:feature-frame`). Sans elle, l'entrée est
réservée à un humain.

- `entry-gate` : `<docs/produit/perimetre.md>`

## Domaines et règles du dépôt

Les skills de domaine du projet, invoqués quand un chiffre engagé ou une règle du métier est en jeu
(spec, design). Une ligne par skill.

- `domain-skill` : `<nom du skill, par exemple backend>`

Les fichiers de règles de chaque domaine : la grille que lisent le coder, le juge et les décideurs.
Une ligne par fichier.

- `domain-rules` : `<.claude/rules/backend.md>`
- `domain-rules` : `<.claude/rules/frontend.md>`

Le skill qui dit comment le projet écrit ses tests, lu par `forge:coder`.

- `test-skill` : `<nom du skill de tests>`

Les règles git du projet : nommage des branches, format des commits, ligne d'attribution.

- `git-rules` : `<.claude/rules/git.md>`

Le modèle de description de PR que `forge:coder` remplit.

- `pr-template` : `<.github/pull_request_template.md>`

Le glossaire de chaque contexte, une ligne par fichier.

- `glossary` : `<docs/glossaire.md>`

## Features

Le dossier des features : chaque feature y vit dans `NNNN-<slug>/`. Sans lui, aucune commande
`/forge:feature-*` ne peut écrire. Le numéro suivant est le plus haut du dossier, plus un.

- `feature-dir` : `<docs/features>`

La commande qui vérifie qu'un document peut s'ouvrir ou s'accepter : appelée avec `F-NNNN
<document>`, elle sort à 0 si les prérequis sont acceptés, et non nul avec la raison sinon. Sans
elle, la vérification se fait à la main, dans les en-têtes.

- `feature-gate` : `<uv run python -m scripts.features gate>`

## Rejeu et contrôles

Les commandes qui installent une copie du dépôt, **dans l'ordre**, une par ligne. Le coder et le
mesureur les lancent dans leur copie avant tout rejeu.

- `install` : `<uv sync --locked>`
- `install` : `<pnpm install --frozen-lockfile>`

Les commandes qui rejouent la CI en local, une par ligne.

- `ci-replay` : `<uv run pytest>`
- `ci-replay` : `<pnpm -r test>`

Les noms des checks obligatoires de la branche protégée, un par ligne, comparés par
`forge:qc-gate` aux check-runs de la PR et à la protection en place.

- `required-contexts` : `<tests>`
- `required-contexts` : `<lint>`

Les listes de référence (dettes tolérées, exceptions comptées) : une ligne ajoutée ou augmentée doit
se justifier dans la PR. Un chemin par ligne.

- `baselines` : `<scripts/baselines/types.txt>`

La commande qui dit si une PR est trop grosse. Elle lit `BASE_SHA` et `HEAD_SHA` dans
l'environnement ; un code non nul veut dire « à découper ».

- `size-check` : `<uv run python -m scripts.pr_size>`

Le check de CI qui vérifie la traçabilité d'une PR (ticket, feature), et la commande qui le rejoue
en local, appelée avec `--title "<titre>" --body-file body.md`.

- `trace-check` : `<trace>`
- `trace-replay` : `<uv run python -m scripts.trace>`

## Revue

La grille de revue de `forge:qc-conf`, dans son ordre : un skill ou un fichier.

- `review-grid` : `<.claude/skills/reviewer/SKILL.md>`

Les chemins qu'aucun agent ne fusionne, même sur ACCEPT : un humain le fait. Un chemin ou un préfixe
par ligne.

- `protected-path` : `<docs/signatures/>`

## Hooks

Le fichier des tirets cadratins tolérés, une ligne `<nombre> <chemin>` par fichier. Sans lui, aucun
fichier écrit par un agent n'en garde.

- `em-dash-allowances` : `<scripts/baselines/em-dash.txt>`

Les commandes dont la sortie se raccourcit quand elles réussissent (la suite de tests, en général) :
une commande lancée qui contient l'une de ces valeurs, et rend plus de 60 lignes, n'en montre à
l'agent que la fin, la sortie complète gardée dans un journal. Une commande qui échoue reste
entière, à condition que son code de sortie le dise : derrière un tube (`| tee log`) ou suivie
d'une autre commande (`; echo fini`), une suite en échec sort à 0 et se raccourcit. Sans la clé,
aucune sortie n'est raccourcie. Une par ligne.

- `trimmed-command` : `<uv run pytest>`

Les agents du projet tenus en lecture seule comme les décideurs du plugin (l'arbitre du métier, en
général), sous leur nom tel que le voient les hooks. Un par ligne.

- `readonly-agent` : `<domain-arbiter>`

Les commandes que ces agents en lecture seule peuvent lancer en plus des lectures prévues (un
calculateur du projet, par exemple), chacune comme un préfixe. Une par ligne.

- `readonly-command` : `<uv run python -m scripts.calcul>`
