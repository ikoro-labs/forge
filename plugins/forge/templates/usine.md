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
ligne par humain, sa valeur égale à son `git config user.name`. Un identifiant court peut suivre,
après ` | ` : c'est lui qu'écrivent `accepte_par` et `porteur`, à la place du `user.name`, que la
comparaison garde pour reconnaître l'humain. Sans ` | `, le `user.name` est écrit tel quel. Une
version du plugin antérieure à cette forme lirait la ligne entière comme un nom et refuserait
l'acceptation (échec sûr, rien n'est écrit).

- `accepting-human` : `<user.name git du premier humain> | <identifiant court>`
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

Les états qu'une feature peut porter dans l'`etat` de son `idee.md`, dans le vocabulaire du
projet : une ligne `<rôle> | <valeur du projet>`, les rôles étant `active`, `hors-perimetre` et
`abandonnee`. Les commandes disent le rôle et écrivent la valeur. Une clé présente doit déclarer les
trois rôles : un rôle manquant arrête la commande, qui ne revient pas aux mots intégrés. Sans la
clé, les trois mots s'écrivent tels quels. Le `statut` des documents (`en-revue`, `accepte`) reste
fixe.

- `feature-state` : `<active | actif>`
- `feature-state` : `<hors-perimetre | hors_perimetre>`
- `feature-state` : `<abandonnee | abandonne>`

La commande qui régénère le catalogue des features, lancée sans argument depuis la racine du dépôt
après chaque commande `/forge:feature-*` qui écrit un en-tête (acceptation comprise) et à l'étape 3
de la clôture, avant le commit et le push. Un code non nul arrête la commande avant le commit ; les
fichiers qu'elle change entrent dans le commit en cours. Sans la clé, rien ne se lance.

- `feature-catalog-command` : `<uv run python -m scripts.features catalog>`

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

Les changements qui retirent un droit, et qu'aucun agent ne fusionne non plus même sur ACCEPT : un
humain le fait. Une ligne `<chemin> | <type> [| <paramètre>]` par règle, le chemin étant un fichier,
ou un dossier quand il finit par `/`. Les types sont fermés, et se décident sur le diff seul :

- `removed-line` : une ligne est retirée sous le chemin, un fichier y est supprimé ou en sort. Sans
  paramètre.
- `raised-number` : un nombre monte. Le paramètre est une expression régulière à un seul groupe, qui
  isole le nombre sur sa ligne ; les lignes retirées et ajoutées d'un fichier s'apparient dans
  l'ordre. Une valeur qui n'est pas un nombre et qui change s'applique aussi.
- `lowered-rank` : un rang baisse. Le paramètre est `<champ> | <rang> > <rang> [> ...]`, le meilleur
  rang d'abord ; une valeur hors de l'échelle qui change s'applique aussi.

`forge:qc-gate` lance `scripts/never_weaken.py` sur le diff de la PR, avec les entrées lues sur la
base : une PR ne peut pas lever la règle qui la juge, et retirer ou modifier une entrée dans
`docs/agents/usine.md` s'applique elle-même. Le script lit le diff et ne lance aucune commande du
projet. Une entrée à qui il manque une partie, ou dont le type est inconnu, est signalée, jamais
complétée. Sans la clé, la règle est sans objet.

- `never-weaken` : `<.github/workflows/ | removed-line>`
- `never-weaken` : `<config/tolerances.toml | raised-number | ^rel_tol = (\S+)>`
- `never-weaken` : `<docs/fonctions/ | lowered-rank | statut | certifie > valide > brouillon>`

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

Les gestes du propriétaire du dépôt propres au projet, que `guard_git` refuse à tout agent en plus
de sa liste intégrée (écritures de `gh api` sur les collaborateurs, protections de branche,
rulesets, runners, secrets, variables, clés, webhooks et dépôt ; `gh secret`, `gh variable`,
`gh repo` ; les scripts d'un runner ; les mutations GraphQL de protection, de ruleset, de
collaborateur et de dépôt). Une ligne `<préfixe de commande> | <raison>` par geste. Le préfixe se
compare mot à mot au début de la commande, après les affectations d'environnement et les options
globales de gh (`gh -R o/r label delete` correspond à `gh label delete`) ; la raison est reprise
dans le refus. Une ligne sans raison refuse quand même, et le dit. La lecture (`GET`, `HEAD`)
passe toujours. Sans la clé, seule la liste intégrée s'applique. Une par ligne.

- `owner-gesture` : `<gh label delete | les étiquettes sont posées par le propriétaire>`

Les formateurs lancés après chaque écriture d'un agent (Edit, Write, MultiEdit) : une ligne
`<motif> | <commande>` par formateur. Le motif se compare au chemin relatif entier, en POSIX, casse
comprise : `**/` (des dossiers, ou aucun), `*` et `?` (jamais un `/`), `{a,b}` (non imbriqué), tout
le reste est littéral. La commande est découpée comme par un shell POSIX, lancée sans shell depuis la
racine du dépôt, le chemin absolu du fichier ajouté en dernier argument ; elle peut contenir `|`
(la coupe se fait au premier ` | `). Plusieurs motifs qui correspondent : toutes les commandes,
dans l'ordre du fichier, avant le contrôle du tiret cadratin. Chacune a 30 s, 120 s au total.
Un échec ou un délai dépassé ne défait pas l'écriture : une ligne sur stderr, `format-on-write:
<commande> failed on <chemin> (exit <n>)`, que l'agent voit. Sans la clé, rien n'est formaté.

- `format-on-write` : `<**/*.py | uv run ruff format>`
- `format-on-write` : `<apps/web/**/*.{ts,tsx} | pnpm --dir apps/web exec prettier --write>`
