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

## Clés protégées : `docs/agents/usine-gardes.md`

Vingt-six clés bornent les pouvoirs de l'agent : `agent-autonomy`, `agent-token-command`, `agent-login`, `protected-path`,
`gh-api-allow`, `owner-gesture`, `never-weaken`, `infra-hosts`, `infra-verify`, `pr-cap-raiser`,
`ticket-pr-cap`, `ticket-pr-cap-since`, `ticket-pr-cap-exempt`, `ticket-pr-cap-small`, `ticket-budget`, `run-limits`,
`e2e-run-limits`, `run-budget`,
`budget-action`, `slo`, `accepting-human`, `validation-owner`, `validation-reviewer`, `pin-bump`,
`readonly-agent` et `readonly-command`. Elles gardent ici leur forme et leur section d'exemple, mais
un projet les écrit dans un second fichier, `docs/agents/usine-gardes.md`, protégé comme les gardes
(clé `protected-path`, `CODEOWNERS`) : un agent qui modifie `usine.md` ne change donc aucune de ces
bornes. Les autres clés, dites libres, restent dans `usine.md`.

- Le chemin `docs/agents/usine-gardes.md` est une constante du plugin, jamais une clé.
- Le hook lit ce fichier tel que `origin/main` le tient (`git ls-tree` puis `git cat-file`), jamais dans l'arbre de travail.
  Une clé protégée écrite dans `usine.md` alors que ce fichier existe sur `origin/main` est ignorée, et
  le garde le signale sur sa sortie d'erreur ; une clé libre écrite dans `usine-gardes.md` l'est aussi.
- Tant que ce fichier est absent de `origin/main`, toutes les clés se lisent dans `usine.md`, avec
  un avis : un projet qui n'a pas déplacé ses clés continue de fonctionner.
- Si le fichier est présent et que git ne peut pas le lire, le garde refuse la fusion.
- Les scripts du plugin lisent la configuration par le même chargeur (`usine.read_config`) : les clés libres de
  `usine.md` et les clés protégées de ce fichier sur `origin/main`. Quand git ne sait pas lire le fichier
  (ni dépôt, ni `origin/main`, un objet illisible), un script refuse (code 2, la raison nomme le fichier) au lieu
  de lire `usine.md` seul. Un script lancé avec `--usine <fichier>` lit ce fichier tel quel : `forge:qc-gate` le
  fabrique de la base, les deux fichiers réunis, par `usine_base.py`.

Chaque clé de ce gabarit est rangée d'un côté ou de l'autre : un test échoue sur une clé ajoutée
sans classe.

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

L'autonomie des agents sur ce projet, que l'utilisateur du projet ouvre et que le plugin ne pose
jamais. La seule valeur est `on`. Avec elle, un skill de la chaîne des features (`feature-new`
jusqu'à `feature-design`, `feature-guide`, `feature-brainstorm`, `feature-status`, `feature-accept`) et les
skills `slo`, `audit-jetons`, `improve-codebase-architecture` et `release` peuvent être lancés par le modèle, et leurs
questions vont d'abord à `forge:product-owner` ou à `forge:staff-engineer`, selon la clé
`decision-matrix`. Sans la clé, ou avec une autre valeur, un skill lancé par le modèle écrit
« sans objet (clé `agent-autonomy` absente) » et rend l'étape à l'humain, avec la commande à taper ;
une commande tapée par l'humain s'exécute toujours. La clé est aussi l'interrupteur de la fusion et de la
publication. Avec elle, `forge:qc` fusionne un ACCEPT hors `protected-path` (une entrée `never-weaken` et une
action `human-merge` active l'arrêtent encore), et `release` publie, tag compris, quand l'essai de bout en bout
passe et qu'aucun `sev1` n'est ouvert ; l'état des SLO est cité dans la PR de version, il ne bloque pas. Sans la
clé, `forge:qc` poste son verdict, pose `needs-your-attention` et ne fusionne jamais, et `release` n'ouvre que
la PR de version : l'humain reprend la main sur un projet en retirant la ligne. Le hook `guard_git` tient la
même clé : sans une seule ligne `on`, `guard_git` refuse alors la fusion et le tag, et le refus dit que le geste
reste à l'humain ; il la lit dans `docs/agents/usine-gardes.md` tel que `origin/main` le tient (dans `usine.md` tant que
ce fichier y est absent), jamais dans l'arbre de travail, et un projet qui adopte la clé déclare ce
fichier en `protected-path`. `feature-accept` lancé par le modèle accepte à la place de l'humain, sans
comparer `git config user.name` (la clé `accepting-human` doit exister) : l'en-tête garde `accepte_par` et
gagne `accepte_via: agent-autonomy`, et un document qui garde des points ouverts n'est jamais accepté par le
modèle. `release` lancé par le modèle sans la clé n'écrit rien, pas même la PR de version, et reste commandé
par la clé `release-trigger` pour savoir quand une version est due. La règle est dans
`plugins/forge/autonomie.md`.

- `agent-autonomy` : `on`

L'identité GitHub des agents, que l'humain du projet installe et que le plugin ne pose jamais : une
application GitHub dont les agents tiennent un jeton d'installation (préfixe `ghs_`, une heure de vie), et
non le jeton de l'humain. Deux clés la décrivent, protégées toutes deux (elles bornent ce que l'agent peut
écrire sur GitHub). `agent-token-command` : une commande, sur une ligne, qui imprime un jeton d'installation
sur une ligne et sort en 0 ; le plugin ne signe rien lui-même (RS256 sort de la bibliothèque standard), c'est
la commande du projet qui le fait, et le plugin la nomme par sa clé, jamais par son texte. `agent-login` : le
login que portent les gestes de l'application (par exemple `mon-app[bot]`). Avec les deux clés, `guard_git`
refuse tout geste qui écrit sur GitHub (`git push`, un verbe de `gh pr`, `gh issue`, `gh release`..., un `gh api`
en écriture, une mutation GraphQL) tant que `GH_TOKEN` (sinon `GITHUB_TOKEN`) de la session ne commence pas par
`ghs_`, et le refus le dit ; il refuse aussi, sans condition de jeton, toute écriture par un outil MCP GitHub,
dont le serveur tient son propre jeton : les agents écrivent par `gh`. Le jeton de l'humain ne remplace jamais
celui de l'application. Seul le préfixe se vérifie : le garde ne prouve ni de quelle application vient le jeton
ni qu'une commande ne le change pas pour la sienne. Sans l'une des deux clés, rien ne change : « sans objet
(clé `agent-login` absente) », sans valeur par défaut. Une ligne répétée, ou une valeur vide, ferme toute
écriture et le refus la cite.

- `agent-token-command` : `<commande qui imprime un jeton d'installation sur une ligne>`
- `agent-login` : `<login de l'application, par exemple mon-app[bot]>`

L'agent du projet qui tranche les questions de doctrine du métier (`DOMAIN`). Sans lui, elles vont à
un humain.

- `domain-arbiter` : `<nom de l'agent, par exemple domain-arbiter>`

Le référent du métier : quand l'arbitre rend `OPEN` (le corpus du projet ne tranche pas),
`forge:feature-build` le mentionne sur le ticket et suit la voie prudente sans arrêter le passage.
La valeur est le login GitHub sans `@` ; le skill ajoute le `@`. Sans la clé, la question va à un
humain par `ready-for-human`.

- `domain-owner` : `<login GitHub du référent, sans @>`

Les sources produit que lit `forge:product-owner`, une par ligne, **dans l'ordre de préséance** :
la plus haute gagne sur les suivantes. L'ordre met l'expert métier en tête : ses documents, notes
et entretiens d'abord, avant tout ce que des agents ont écrit.

- `product-source` : `<docs/produit/retours-terrain.md>`
- `product-source` : `<docs/produit/parcours.md>`

Une source produit se lit en **Markdown** : une source déclarée en PDF, en `.docx` ou en image rend
l'étape de spec bloquée, avec la demande d'un export Markdown à son auteur. `forge:feature-spec` en
reprend chaque élément identifié (`EX-12`, `RG-3.1`) par son identifiant, et le comptage
`scripts/source_ids.py` liste ceux que la spec ne reprend pas.

`source-author` : qui peut écarter un élément d'une source, un rôle ou un compte GitHub, **une ligne
par valeur**. Une exclusion de périmètre ne vaut que si cette personne a écarté l'élément par écrit ;
la spec cite l'accord (fichier, date, rôle). Sans la clé, aucun élément ne s'écarte, et l'étape le
dit : « sans objet (clé `source-author` absente) ».

- `source-author` : `<expert métier>`

Le support partagé où l'expert métier relit et commente le document vivant d'une conception guidée
(`/forge:feature-guide`), quand le projet en a un : la valeur nomme le support et l'endroit où le
trouver (un nom de service et un espace, une adresse, un dossier partagé), en une ligne. Forge ne câble
aucun service précis : la clé nomme le support, et le skill dit seulement quoi en faire. Le fichier
du dépôt reste la référence : ce que l'expert écrit ou commente sur le support se recopie dans le
fichier, qui seul devient la source. Sans la clé : « sans objet (clé `shared-doc` absente) » et seul le
fichier du dépôt sert, sans valeur par défaut.

- `shared-doc` : `<le support partagé, par exemple une page d'un wiki ou un dossier partagé>`

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

`forge:tdd`, livré avec le plugin, peut être la valeur ; ce n'est pas une valeur par défaut : une clé absente
rend l'étape « sans objet ».

- `test-skill` : `<nom du skill de tests>`

La bibliothèque de tests par propriétés du projet, lue par `forge:tdd` (section « Les tests par propriétés »)
et par `forge:qc-conf`. Sans la clé, le skill ne demande aucun test par propriétés et le juge n'en attend
pas. Aucune valeur par défaut.

- `property-test-lib` : `<hypothesis>`

Le skill qui découpe le design en tickets, lu par `/forge:feature-design` à l'étape du découpage.
Sans lui, le découpage se fait à la main, dans l'ordre du §7 du design, et le dit.

- `ticket-skill` : `<nom du skill de découpage en tickets>`

Les règles git du projet : nommage des branches, format des commits, ligne d'attribution.

- `git-rules` : `<.claude/rules/git.md>`

La méthode de fusion d'une PR par `/forge:qc` : `merge` (commit de fusion, `--merge`), `squash`
(`--squash`) ou `rebase` (`--rebase`), celle que le dépôt GitHub autorise et que ses règles git
demandent. Sans la clé, `/forge:qc` ne fusionne
pas : l'étape est sans objet et la PR reste ouverte sur son ACCEPT. Le hook `guard_git` tient la
même clé pour tout agent : une fusion dont la méthode diffère de la clé ou n'en donne aucune, une
clé absente, sur deux lignes ou d'une valeur autre que `merge`, `squash` ou `rebase` valent refus.

- `merge-method` : `<squash>`

Le modèle de description de PR que `forge:coder` remplit. Le plugin en propose un,
`templates/pr.md` (Change view, Door, Blast radius, Proofs), à copier dans le dépôt : une valeur
possible de la clé, pas une valeur par défaut. Sans la clé, l'étape est sans objet.

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

La colonne propre au projet dans le tableau de complétion (`scripts/completion.py`, que le hook
`guard_completion` exige en réponse à une question sur l'avancement) : `<en-tête> | <commande>`. La
commande se lance depuis la racine du dépôt, `{feature}` remplacé par le `F-NNNN` de la ligne ; sa
sortie, sur une ligne, remplit la cellule, et un code non nul y écrit l'erreur. Sans la clé, le
tableau garde ses huit colonnes.

- `completion-column` : `<Couverture | uv run python -m scripts.features status {feature}>`

## Rejeu et contrôles

Les commandes qui installent une copie du dépôt, **dans l'ordre**, une par ligne. Le coder et le
mesureur les lancent dans leur copie avant tout rejeu.

- `install` : `<uv sync --locked>`
- `install` : `<pnpm install --frozen-lockfile>`

Les commandes qui rejouent la CI en local, une par ligne.

- `ci-replay` : `<uv run pytest>`
- `ci-replay` : `<pnpm -r test>`

Les commandes que la sonde de rejeu de chaque commit lance sur chaque commit de la PR sauf le dernier, une
par ligne : la clé est facultative, et chaque ligne reprend une commande de `ci-replay` (en général les
lints et les types, sans la suite, qui coûte l'essentiel du temps). Le dernier commit, la tête, rejoue
chaque commande de `ci-replay`, et une PR d'un seul commit aussi. Sans la clé, chaque commit rejoue chaque
commande de `ci-replay`, comme avant ; elle n'a pas de valeur par défaut.

- `ci-replay-light` : `<ruff check .>`
- `ci-replay-light` : `<mypy>`

La borne de toute suite et de toute sonde qu'un agent lance, par `scripts/bounded_run.py` : le coder et
le mesureur lancent chaque commande de `ci-replay`, `install` exceptée, par ce lanceur
(`bounded_run.py -- <commande>`). Deux clés, chacune avec son étape « sans objet » et aucune valeur par
défaut.

`run-limits` : la mémoire en Mo et le délai en secondes de chaque commande, une seule ligne. Le lanceur
la tient par `RLIMIT_AS` et le groupe de processus tué au délai sous Linux, par un objet de tâche sous
Windows ; une borne qu'il ne peut pas poser refuse de lancer. Sans la clé, il exige `--memory-mb` et
`--timeout`, et `forge:qc-gate` rend « sans objet (clé `run-limits` absente) » pour ce qu'il aurait
borné.

- `run-limits` : `<mémoire en Mo> | <délai en secondes>`

`run-budget` : le budget du poste entier, que se partagent les sessions, les sous-agents et les workers
(une borne par commande ne l'arrête pas : des processus de 150 Mo chacun, assez nombreux, vident la
mémoire d'un poste). Quatre nombres sur une seule ligne : les Mo disponibles au moins (`MemAvailable`),
la charge à 1 min au plus, le nombre de workers parallèles au plus, et l'attente au plus en secondes.
Avant de lancer une suite, une sonde ou un sous-agent de tests, le lanceur lit le poste ; hors seuil il
attend jusqu'à ce délai, puis sort en 120 avec la raison sur stderr, sans rien lancer. Il ramène le
`-n` de pytest-xdist, `-n auto` compris, au plafond de workers, quand la commande nomme pytest. Sous
Windows, sans moyenne de charge, seule la mémoire juge. Sans la clé, l'étape est « sans objet (clé
`run-budget` absente) » : aucun seuil n'est supposé.

- `run-budget` : `<Mo disponibles au moins> | <charge à 1 min au plus> | <workers au plus> | <attente au plus en secondes>`

Le rejeu de chaque commit d'une PR, par `forge:qc-gate` (`scripts/commit_replay.py`) : chaque commande de
`ci-replay`, précédée de `install`, tourne sur chaque commit propre à la PR, pris seul, dans une copie
extraite par `git archive` et supprimée ensuite, sous la borne de `run-limits` et après le budget de
`run-budget`. Un commit rouge fait tomber un `git bisect` sur la base : c'est un `BLOCKER` pour
`forge:qc-conf`, par la règle `F-24` du socle. Avec la clé facultative `ci-replay-light`, les commits
d'avant la tête ne rejouent que ses commandes, et la tête rejoue tout `ci-replay`. Sans `ci-replay`, « sans objet (clé
`ci-replay` absente) » ; sans `run-limits`, « sans objet (clé `run-limits` absente) » ; sans `run-budget`,
la sonde le dit et ne l'attend pas. Elle dure la suite multipliée par le nombre de commits.

Le rejeu de la sonde d'un `BLOCKER`, par `forge:qc-gate` en mode `MODE: probes` (`scripts/probe_replay.py`) :
un `BLOCKER` du juge qui repose sur une exécution porte le nom d'un fichier de test de la tête et la
sortie attendue. La sonde est fermée : le script lance ce fichier par la commande de la clé `red-replay`,
comme au rejeu des tests sur la base, dans une copie de la tête sans `.git` (faite par `git archive`),
sous la borne de `run-limits` et après le budget de `run-budget`, avant que le `BLOCKER` compte ; rien de
ce que le juge écrit n'est exécuté comme commande. Un nom hors de la tête ou hors de `test-path`, un
chemin absolu, une partie `..` ou un caractère de shell est refusé, jamais lancé, et le verdict revient
au juge. Une sortie dite que le test n'imprime pas (ou qu'un délai interrompt) en fait une `NOTE`
« non reproduit » ; un `BLOCKER` sans sonde compte et se marque « déduit ». Aucune clé de plus : sans
`run-limits`, « sans objet (clé `run-limits` absente) », et de même sans `test-path` ou `red-replay` :
aucune sonde ne tourne et le `BLOCKER` reste en suspens ; sans `run-budget`, la sonde le dit et ne
l'attend pas. Le test tourne avec
les droits de la session, comme tout test de la PR.

Le rejeu des tests d'une PR sur sa base, par `forge:qc-gate` : les fichiers de test que la PR ajoute
ou change sont posés dans une copie de la base, puis rejoués, et chacun doit y échouer. Un test
rouge sur la base prouve le changement ; un qui y passe déjà est rendu à `forge:qc-conf`. Deux clés,
toutes deux nécessaires : sans l'une, la sonde se rend « sans objet (clé `test-path` absente) » ou
« sans objet (clé `red-replay` absente) ».

`test-path` : un préfixe de chemin des fichiers de test, une ligne par préfixe.

- `test-path` : `<tests/>`
- `test-path` : `<apps/web/src/__tests__/>`

`red-replay` : la commande qui lance la suite dans la copie, une seule. `{file}` y est remplacé par le
fichier de test à rejouer (son chemin depuis la racine), `{name}` par son nom de fichier, tous deux
protégés par des guillemets ; l'un des deux au moins est obligatoire. Par défaut, le grain est le
fichier : il est rejoué en entier, et rendu quand la commande sort à 0 sur la base. `{report}`, facultatif
et sans clé de plus, passe au grain du test : il est remplacé par le chemin d'un fichier où la commande
écrit un rapport JUnit XML (`pytest {file} --junitxml={report}`). Le script repère alors les tests que
la PR ajoute ou change dans le fichier, en confrontant les lignes du diff à la place de chaque nom de
test dans le fichier de la tête (une lecture du texte, pas du langage, qui dans le doute compte un test
comme changé : un test qu'il ne sait pas placer, ou un assistant changé sous un test, fait rendre ce
test), et ne rend que ceux de ces tests
qui passent sur la base, chacun sur sa ligne `PASSES` (`<fichier>::<test>`). Une commande qui sort à 0
sans rapport est `NOT RUN`, jamais `PASSES`. Un projet dont le lanceur n'écrit pas de rapport JUnit
reste au grain du fichier. Chaque commande, celles de `install`
comprises, tourne sous une limite de mémoire (2000 Mo) et un délai (300 s) que le script pose lui-même,
parce qu'elle exécute du code de test contre un code qui ne l'attend pas. Ces bornes sont éprouvées sous
Linux seulement ; sous Windows elles reposent sur un objet de tâche (job object), écrit d'après la
documentation Win32, jamais vu hors de la CI, où sa première version a échoué (borne non tenue) ; la
version corrigée n'est pas encore vue verte.

- `red-replay` : `<uv run pytest {file}>`

Au grain du test, cette même ligne porte `{report}` : `<uv run pytest {file} --junitxml={report}>`.

Le motif des tags de version, lu par `scripts/factory_slo.py` pour l'indicateur `release-lag` : `{version}`
tient pour la version (`<plugin>--v{version}`). Une ligne par motif. Sans la clé, `release-lag` est
« sans objet (clé `release-tag` absente) », sans motif supposé.

- `release-tag` : `<monplugin--v{version}>`

Quand l'agent publie une version, lu par `scripts/release.py` et le skill `release`. Une seule
ligne, `<N fusions> | <délai max>` : N est un entier au-dessus de 0, le délai un nombre suivi de `h` ou
de `j`, comme dans la clé `sla`. Une version est due quand N fusions attendent un tag de la clé
`release-tag`, ou quand la plus ancienne attend depuis plus que le délai : la première des deux bornes
atteinte la déclenche. Sans la clé, « sans objet (clé `release-trigger` absente) » : l'agent ne publie
rien, et aucune valeur n'est supposée. Une valeur illisible ou une clé répétée fait échouer la commande
(code 2), sans publication. Sans la clé `release-tag`, le compte des fusions en attente est lui aussi
« sans objet (clé `release-tag` absente) ».

- `release-trigger` : `<10 | 7 j>`

La montée de l'épingle de forge dans ce projet, que l'utilisateur du projet ouvre et que le plugin ne pose
jamais. La seule valeur est `auto`. Avec elle, le hook `SessionStart` `pin_notice.py` dit à la session
qu'un tag plus récent que le `ref` de `.claude/settings.json` existe (`forge--v<X.Y.Z>`, le préfixe
étant celui du `ref` épinglé, le plus haut `X.Y.Z` de la marketplace, comparé en nombres) : la clé est
l'accord de l'humain pour que la session ouvre la PR de montée, et aucun billet n'en tient lieu. Le hook
se tait sans la clé (et ne demande alors rien au réseau), pour un sous-agent, quand l'épingle est déjà le
tag le plus récent, et tant qu'une PR ouverte change `.claude/settings.json`. Il est borné dans le temps,
et sort toujours en 0 sans rien dire quand `gh` manque, échoue ou dépasse son délai, quand le réseau est
coupé ou qu'un fichier ne se lit pas. La clé ne décide pas la fusion : `forge:qc` fusionne la PR de
montée sur ACCEPT comme toute PR, et un fichier du diff sous un `protected-path` (déclare
`.claude/settings.json` pour que l'humain garde la montée) ou une action `human-merge` active l'arrête
comme avant ; le geste sur chaque poste (`claude plugin marketplace add`, puis `claude plugin update`)
est celui de la session entre deux tickets, par `scripts/pin_sync.py apply`, jamais entre un coder et le verdict
de la revue. Sans la clé, « sans objet (clé `pin-bump` absente) » : rien ne se dit, aucune valeur
n'est supposée. Le même hook porte un second avis qui ne lit aucune clé : il dit quand la version installée
diffère de l'épingle de `origin/main` (`pin_sync.py check`, `BEHIND`) et donne la commande, sans la lancer.

- `pin-bump` : `auto`

`factory_slo.py` lit aussi `required-contexts` (`main-green`) et `protected-path` (`human-touch`), et
deux conventions du projet : l'étiquette `escaped-defect`, posée sur un ticket de défaut trouvé après la
fusion, avec dans son corps la ligne `Échappé de #<pr>` qui nomme la PR en cause ; et, pour la gravité
de `restore-time`, l'étiquette de gravité ci-dessous. Voir `docs/indicateurs-de-service.md`.

Les classes de gravité d'un ticket de défaut, posées par une étiquette, une seule par ticket (voir
`docs/gravite-et-sla.md`) :

- `sev1` : un garde contourné, un chemin protégé fusionné sans humain, une perte de données ou de
  travail, ou la branche de base rouge ;
- `sev2` : un défaut échappé qui change un comportement (hook, porte, règle appliquée) ;
- `sev3` : la prose, la documentation ou un confort.

`forge:feature-build` prend les tickets prêts par gravité, puis par échéance, et un `sev1` passe devant
tout ticket qui n'est pas encore confié.

Les engagements de délai (SLA), lus par `scripts/factory_slo.py` (`sla`, `queue`, `report`). Une ligne
par gravité : `<gravité> | <prise en charge> | <correctif fusionné> | <correctif publié>`. Chaque délai
est un nombre suivi de `h` ou de `j`, compté depuis l'ouverture du ticket : la prise en charge est
atteinte quand le ticket est assigné ou reçoit `agent-claimed`, le correctif fusionné quand une PR qui
le ferme (`Closes`) est fusionnée, le correctif publié quand son commit de fusion est dans un tag de
la clé `release-tag`. Une gravité inconnue ou répétée, ou un délai illisible, fait échouer la commande.
Sans la clé, les échéances sont « sans objet (clé `sla` absente) », aucune n'est devinée.

- `sla` : `<sev1 | 4 h | 24 h | 3 j>`
- `sla` : `<sev2 | 2 j | 7 j | 14 j>`
- `sla` : `<sev3 | 7 j | 30 j | 60 j>`

L'étiquette d'un ticket dont le but est le délai de l'usine elle-même (le temps de la CI, des gardes,
des relais), lue par `scripts/factory_slo.py queue`. Une seule ligne, le nom de l'étiquette : un ticket
qui la porte passe après `sev1` et avant tout autre ticket (`sev2`, `sev3`, sans classe), et un ticket
qui porte à la fois `sev1` et cette étiquette reste dans `sev1`. L'étiquette doit exister sur le dépôt :
l'agent ne la crée pas. Elle ne change ni un coder déjà en vol, ni un bloqueur ouvert, ni le gel de
feature. Sans la clé, « sans objet (clé `speed-label` absente) » : l'ordre est celui de la clé `sla`
seule, aucune étiquette n'est devinée. Une clé déclarée deux fois fait échouer `queue`. Les skills
`forge:feature-build`, `forge:qc` et `forge:incident` posent l'étiquette sur le ticket qu'ils ouvrent
quand son but est ce délai, et seulement alors.

- `speed-label` : `<factory-speed>`

Les objectifs de service, lus par `scripts/factory_slo.py status`. Une ligne par objectif :
`<sli> | <comparateur> <cible> | <fenêtre en jours>`. Le SLI est l'un de ceux de
`docs/indicateurs-de-service.md` ; une durée prend `p90` ou `mediane` après son nom. Le comparateur est
`>=` ou `<=`, la cible porte son unité (`%` pour un ratio, `h` pour une durée, un nombre nu pour
`tokens-per-merge`). `status` calcule la valeur sur la fenêtre glissante, le budget d'erreur (l'écart que
la cible permet) et son état : `tenu`, `menacé` (plus de 75 % du budget consommé) ou `épuisé`. Il l'écrit
dans `<git-common-dir>/forge/slo-status.json`. Une ligne mal formée ou un SLI inconnu fait échouer la
commande. Sans la clé, les objectifs sont « sans objet (clé `slo` absente) », sans objectif supposé.

- `slo` : `<accept-round-1 | >= 80 % | 30>`
- `slo` : `<lead-time p90 | <= 24 h | 30>`

La date à laquelle les cibles de la clé `slo` sont à réviser, une seule ligne, `AAAA-MM-JJ`. `status` la
rend sous le tableau et, dans `slo-status.json`, sous `revision` (`date`, `passee`) : elle est signalée
« passée » dès le lendemain de cette date (UTC). Elle ne change aucune cible : réviser reste une
décision de l'humain. Sans la clé, « sans objet (clé `slo-review-date` absente) », aucune date n'est
supposée. Une date illisible ou déclarée deux fois fait échouer `status`.

- `slo-review-date` : `<2026-12-16>`

The indicators of the end-to-end review (`matrix-coverage`, `review-regressions`) are computed from the
`matrice.md` and the `revue/boucle.tsv` of the features under the folder of the key `feature-dir`; without
it, they are « sans objet (clé `feature-dir` absente) ». Both ratios are declared like the others. The
proposed objective is on the reintroduced gaps, those that come back after a fix (see
`docs/indicateurs-de-service.md`):

- `slo` : `<review-regressions | <= 10 % | 30>`

Le ticket de suivi de l'usine du projet (un par projet), où `scripts/factory_slo.py report --publier`
(le skill `forge:slo`) réécrit le rapport des objectifs dans un commentaire unique, retrouvé par un
marqueur caché, et pose `needs-your-attention` quand des objectifs sont `menacé` ou `épuisé`, puis la
retire quand chaque objectif est `tenu` (un objectif « sans objet » la retient, et une étiquette qu'un
humain avait posée n'est pas retirée). Un numéro, avec ou sans `#`. Le script épingle le commentaire à
sa création et le garde unique : il le réécrit. Sans la clé, la publication est
« sans objet (clé `slo-issue` absente) » et aucune issue n'est devinée.

- `slo-issue` : `<55>`

Le constat qui revient de PR en PR. Quand le juge relève le même `F-n` ou `L-n` sur plusieurs PR, c'est la règle
qui manque ou qui est mal tenue, et personne ne le voit PR par PR. Une clé, sans valeur par défaut.

`recurring-finding` : le seuil et la fenêtre, `<seuil> | <jours>`, sur une seule ligne : deux nombres entiers
positifs. `forge:qc` lance `scripts/recurring_findings.py` après chaque verdict posé. Le script lit les
commentaires de verdict des PR jugées dans les derniers `<jours>` jours, extrait la règle de chaque constat
(le deuxième champ de la ligne `- [BLOCKER] <lieu> | <règle> | ...`) par le motif fermé `F-<n>` ou `L-<n>`, et
compte les PR distinctes par identifiant : une PR qui le cite à plusieurs tours compte une fois. Un identifiant cité
par au moins `<seuil>` PR distinctes est listé, avec ses PR, dans un commentaire unique du ticket de la clé
`slo-issue`, retrouvé par son marqueur caché `<!-- forge-recurring-findings -->` (distinct de celui du rapport des
SLO) et réécrit à chaque passage. Un constat sans `F-n` ni `L-n` est compté à part, jamais mêlé aux identifiants.
Le commentaire ne porte que des identifiants, des numéros de PR et des dates ; le constat devient un commentaire,
jamais un ticket. Sans la clé `recurring-finding`, « sans objet (clé `recurring-finding` absente) » ; sans la clé
`slo-issue`, « sans objet (clé `slo-issue` absente) » : aucune valeur par défaut, aucune devinée, rien n'est écrit.

- `recurring-finding` : `<3 | 30>`

Ce que l'usine fait quand le budget d'erreur d'un objectif est épuisé. Une ligne par action :
`<sli> | <action>`, où `<sli>` nomme un objectif de la clé `slo` (`lead-time p90`, ou `lead-time`
seul) et où l'action est l'une de ces trois :

- `human-merge` : `forge:qc` ne fusionne plus sur ACCEPT. Il pose `needs-your-attention` avec
  l'objectif épuisé dans `Attention`, et l'humain fusionne. Le garde `guard_git` refuse en plus
  `gh pr merge` à tout agent tant que l'action est active.
- `feature-freeze` : `forge:feature-build` ne confie plus que les tickets `bug` et `escaped-defect` ;
  les autres attendent, et le compte rendu du passage le dit.
- `alert` : seulement l'étiquette sur l'issue de suivi (clé `slo-issue`, `forge:slo --publier`).

L'état est celui de `slo-status.json`, que `forge:qc` et `forge:feature-build` recalculent au début de
chaque passage par `scripts/factory_slo.py budget <projet>`. Une action devient active quand son objectif
est `épuisé`, reste active tant qu'il est `menacé` ensuite, et cesse au calcul suivant qui le trouve
revenu à `tenu` : le rapport dit alors « autonomie rendue », et pas avant. Le fichier d'état garde cette
mémoire d'un calcul à l'autre ; un fichier précédent qui existe sans se lire retient tout objectif qui
n'est pas `tenu`, pour qu'une action ne cesse pas faute de mémoire. Un objectif « sans objet » qui n'a jamais été épuisé n'est pas épuisé. Quand la clé est déclarée avec
`human-merge` et que le fichier d'état manque, est illisible ou date de plus de 24 h, `guard_git` refuse
la fusion par précaution et donne la commande à lancer (`factory_slo.py status <projet>`). Une ligne
mal formée, une action inconnue ou un objectif absent de la clé `slo` font échouer `budget` et refuser
la fusion. Sans la clé, les actions sont « sans objet (clé `budget-action` absente) » : aucune action,
aucune valeur par défaut.

- `budget-action` : `<accept-round-1 | human-merge>`
- `budget-action` : `<accept-round-1 | feature-freeze>`
- `budget-action` : `<lead-time p90 | alert>`

Le dossier des revues sans blâme que le skill `incident` écrit, relatif à la racine du dépôt, un seul
dossier sur une seule ligne. Chaque incident `sev1` ou `sev2`, et chaque incident de l'usine
elle-même, y laisse une revue (`templates/incident.md`) : les faits datés, la cause, ce qui l'a
laissé passer, et la classe du correctif, `mécanique` (le ticket d'un contrôle déterministe et de son
test, ou un contrôle que le dépôt tient déjà) ou `jugement` (un cas ajouté au jeu de référence). Une
revue sans correctif est refusée par `scripts/incident.py check`. `scripts/factory_slo.py incidents
<projet>` compte les revues du dossier par classe. Sans la clé, l'étape est
« sans objet (clé `incident-dir` absente) » : aucune revue n'est écrite ni comptée, et aucun dossier
n'est deviné. Une valeur qui sort du dépôt, ou une clé répétée, fait échouer la lecture.

- `incident-dir` : `<docs/incidents>`

Le plafond de jetons d'agents par ticket, un nombre entier sur une seule ligne. `forge:feature-build`
tient, pour chaque ticket, la somme des jetons de chaque agent lancé pour lui (coder, remise à jour,
corrections, `forge:qc-gate`, `forge:qc-conf`, décideurs) plus la part de la session principale, et
ne lance plus rien pour un ticket dont la somme dépasse ce nombre : il pose `needs-your-attention`
sur le ticket et sa PR. Une somme égale au plafond lance encore. Sans la clé, « sans objet (clé
`ticket-budget` absente) » : aucun plafond, aucune valeur par défaut. Une valeur qui n'est pas un
nombre entier fait échouer le contrôle.

- `ticket-budget` : `<300000>`

Le plafond de PR par ticket, un nombre entier au-dessus de 0 sur une seule ligne : `6` tant que les tickets
ne sont pas dimensionnés à la découpe (ceux publiés avant que `forge:feature-design` en estime la taille),
`3` une fois qu'ils le sont. Une PR dont le corps cite
`Closes #n` ou `Refs #n` est refusée par `guard_pr_cap` quand le ticket `#n` a déjà ce nombre de PR,
ouvertes ou fusionnées (une PR fermée sans fusion ne compte pas) : c'est le `BLOCKED` de la PR de trop,
le ticket est commenté et reçoit `needs-your-attention`, et aucun ticket ne naît du plafond. Le coder
(`forge:coder`) et l'orchestrateur (`forge:feature-build`) le lisent avant de couper un ticket : ils en
prévoient au plus ce nombre. Seule l'étiquette `pr-cap-raised`, posée par un compte de la clé
`pr-cap-raiser` (plus bas ; le dernier événement de l'étiquette doit être sa pose), relève le plafond à 6.
Sans la clé
`ticket-pr-cap`, « sans objet (clé `ticket-pr-cap` absente) » : le garde ne lit rien, aucune valeur par
défaut n'est devinée. Une valeur qui n'est pas un nombre entier au-dessus de 0, ou une clé répétée, fait
refuser toute PR qui cite un ticket, tant qu'elle n'est pas corrigée.

- `ticket-pr-cap` : `<3>`

Le jour à partir duquel les PR d'un ticket comptent dans ce plafond, une seule ligne au format `AAAA-MM-JJ`
(jour UTC). `guard_pr_cap` lit la date de création de chaque PR (`createdAt` de `gh pr list`) : une PR créée
avant cette date n'est pas comptée, une PR créée ce jour-là ou après l'est. Sert à introduire le plafond
dans un projet dont des tickets en ont déjà dépassé le nombre : un ticket qui a au moins une PR créée avant
cette date (ouverte ou fusionnée) est un ticket déjà commencé ; il termine la PR en vol, puis admet une seule
dernière PR, en dernier recours, au lieu du plafond (la limite de 1 est une constante du garde, pas une clé ;
l'étiquette `pr-cap-raised` relève toujours la limite à 6). Sans la clé `ticket-pr-cap-since`, « sans
objet (clé `ticket-pr-cap-since` absente) » : aucune date par défaut n'est devinée, le plafond compte toutes
les PR du ticket, quelle que soit leur date. Sans la clé `ticket-pr-cap`, la date n'est pas lue non plus. Une
valeur qui n'est pas un jour valide (`2026-13-45`, `demain`), une clé répétée, ou une PR dont `createdAt` est
illisible fait refuser toute PR qui cite un ticket, tant que ce n'est pas corrigé.

- `ticket-pr-cap-since` : `<AAAA-MM-JJ>`

Le seuil sous lequel une PR ne compte pas dans ce plafond, un nombre de lignes entier au-dessus de 0 sur une
seule ligne. `guard_pr_cap` lit `additions` et `deletions` de chaque PR dans le même appel `gh pr list --json`
que le compte, et laisse hors du compte, ouverte ou fusionnée, une PR dont la somme est strictement
inférieure à ce nombre : elle compte moins de lignes que lui, une PR d'exactement ce nombre compte. Une PR
sortie du compte ne démarre pas non plus un ticket (la date de `ticket-pr-cap-since` ne lui est pas
appliquée). Une PR en création n'a pas de diff lisible avant que gh ne s'exécute : elle compte jusqu'à ce
qu'elle soit listée. La clé relâche le plafond, donc elle est protégée. Sans la clé `ticket-pr-cap-small`,
« sans objet (clé `ticket-pr-cap-small` absente) » : toutes les PR comptent, quelle que soit leur taille,
aucune valeur par défaut n'est devinée et les deux champs ne sont pas demandés. Une valeur qui n'est pas un
nombre entier au-dessus de 0, une clé répétée, ou une PR du compte dont `additions` ou `deletions` est
illisible fait refuser toute PR qui cite un ticket, tant que ce n'est pas corrigé. Sans la clé
`ticket-pr-cap`, la taille n'est pas lue non plus.

- `ticket-pr-cap-small` : `<50>`

Les PR d'entretien de l'usine, que `guard_pr_cap` laisse hors du compte du plafond : une ligne par
`type(scope)` (`chore(factory)`, `chore(pin)`), et une PR dont le titre commence exactement par
`type(scope):` ne compte pour aucun ticket, ouvertes ou fusionnées. Une PR d'entretien (une épingle de
forge, une date de plafond) n'a rien à voir avec le ticket qu'elle cite : elle ne cite aucun ticket, et celle
qui en cite un sort du compte quand même. Le titre est lu dans l'appel `gh pr list --json` que le garde fait
déjà ; une PR en création n'est exemptée que par son argument `--title` ou `-t`, et sans titre elle compte.
Le garde ne vérifie pas le diff : la clé est protégée, et le juge (`forge:qc-conf`) refuse un titre de cette
liste sur un diff qui n'est pas de l'entretien de l'usine. Sans la clé `ticket-pr-cap-exempt`, « sans objet
(clé `ticket-pr-cap-exempt` absente) » : toutes les PR comptent, aucune valeur par défaut n'est devinée.
Une ligne qui n'est pas un `type(scope)`, ou une PR du compte dont le titre est illisible, fait refuser
toute PR qui cite un ticket, tant que ce n'est pas corrigé.

- `ticket-pr-cap-exempt` : `<chore(factory)>`

Les comptes GitHub qui peuvent relever le plafond de PR par ticket à 6, en posant l'étiquette `pr-cap-raised`.
Une ligne par compte, le login GitHub (ou `<nom> | <login>` : le login après ` | `) ; la casse est libre.
Mets ici des comptes dont l'agent n'a aucun jeton : si l'agent peut agir sous un de ces comptes, il pose
l'étiquette lui-même et relève son propre plafond, ce que la clé existe pour empêcher. Elle est distincte de
`accepting-human`, dont un compte peut être celui de l'agent, et `guard_pr_cap` ne lit pas
`accepting-human` pour ce contrôle. Sans la clé `pr-cap-raiser`, « sans objet (clé `pr-cap-raiser`
absente) » pour la relève : personne ne relève le plafond, et la valeur de `ticket-pr-cap` tient ; aucune
valeur par défaut n'est devinée. La clé n'a d'effet que si l'humain a un compte GitHub dont l'agent n'a
aucun jeton ; sinon, ne la déclare pas : on relève le plafond en changeant `ticket-pr-cap` par une PR.

- `pr-cap-raiser` : `<login GitHub d'un humain>`

Le délai après lequel une question restée sans réponse d'un humain reçoit une décision par défaut, une
seule ligne : un nombre au-dessus de 0 suivi de `min` (minutes), `h` (heures) ou `j` (jours), comme
`10 min`, `24 h` ou `2 j`. `h` et `j` se lisent comme dans la clé `sla` ; `min` n'existe que pour cette clé,
`sla` et `release-trigger` gardent les heures et les jours. Une question est
un ticket ou une PR ouverts qui portent `ready-for-human`, `needs-info` ou `needs-your-attention` ;
elle attend depuis la dernière pose d'une de ces étiquettes, et `scripts/question_delay.py due` liste
celles qui dépassent le délai. `forge:feature-build` la lance au début du passage, avant chaque lancement
d'un coder et après chaque fusion, pour qu'un délai court (`10 min`) soit tenu entre deux tickets, et passe
chaque question échue à `forge:staff-engineer` ou à `forge:product-owner`, puis `scripts/question_delay.py route` agit sur leur verdict : une décision
`DECIDED` que la matrice donne, avec sa source et `REVERSIBLE: yes`, est postée comme décision par
défaut (`Décision (<agent>, <case>)`), que l'humain peut défaire d'un commentaire ; tout autre verdict
(`RESERVED`, `DOMAIN`, `TECHNICAL`, une décision sans source ou irréversible) laisse la question à
l'humain, qui reçoit un rappel et `needs-your-attention`. Chaque décision par défaut et chaque rappel
relance le délai. Sans la clé, « sans objet (clé `question-default-delay` absente) » : aucune question
n'est listée ni tranchée, et aucun délai n'est deviné. Une valeur illisible, ou une clé répétée, fait
échouer la commande (code 2).

- `question-default-delay` : `<24 h>`

Les sessions voisines à consulter avant de proposer un levier (une amélioration, une optimisation, une
suite), une par ligne. `guard_ticket_budget` refuse un ticket dont le corps porte une ligne `Lever:` sans
ligne `Peers:` qui nomme chacune de ces sessions (un nom entier, pas un morceau de mot), ou sans ligne
`Searched:` qui dit ce qui a été cherché. Le garde lit la présence, jamais la vérité : il ne vérifie ni
qu'un pair a répondu ni que la recherche a eu lieu. Sans la clé, « sans objet (clé `lever-peers` absente) » :
une ligne `Lever:` ne demande ni `Peers:` ni `Searched:`, et aucune session n'est devinée.

- `lever-peers` : `<nom de la session voisine>`

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

L'âge des dépendances qu'une PR ajoute à un lockfile, ou dont elle change la version. Un paquet qu'un agent
cite peut ne pas exister, ou venir d'être publié par un tiers sous ce nom, et aucune autre couche ne le regarde.
Deux clés, chacune avec son étape « sans objet » et aucune valeur par défaut.

`lockfile` : un lockfile par ligne, `<chemin> | <écosystème>`. Les écosystèmes sont fermés : `pypi` lit un
`uv.lock` (index `https://pypi.org/simple`), `npm` lit un `package-lock.json` (lockfileVersion 2 ou 3, registre
`https://registry.npmjs.org/`). Une entrée à qui il manque une partie, ou dont l'écosystème est inconnu, est
rendue `INVALID`, jamais complétée. Sans la clé, « sans objet (clé `lockfile` absente) ».

`dependency-min-age` : le nombre entier de jours qu'une version doit avoir sur le registre, sur une seule
ligne. La popularité (les téléchargements) n'entre pas dans la règle. Sans la clé, « sans objet (clé
`dependency-min-age` absente) » : la sonde ne demande rien au registre.

`forge:qc-gate` lance `scripts/lockfile_age.py` avec les clés lues sur la base : une PR ne baisse pas le seuil
qui la juge. Le script lit chaque lockfile à la base et à la tête par `git show` et rend une ligne par paquet
ajouté ou dont la version change, avec la date de première publication du paquet et celle de la version, lues
sur le registre public par le réseau, sans identifiant (c'est la seule sonde qui l'appelle). Chaque ligne est
`OLD` (la version a au moins le seuil), `YOUNG` (moins), `NOT FOUND` (le registre ne connaît pas le paquet ou
la version), `NOT CHECKED` (le paquet ne vient pas du registre public : git, URL, autre index), `NOT RUN` ou
`INVALID`. Un registre qui ne répond pas est `NOT RUN` avec la requête qui a échoué, jamais `PASS`. Le script
ne lance aucune commande du projet. `forge:qc-conf` fait de `YOUNG` et de `NOT FOUND` un `BLOCKER`.

- `lockfile` : `<uv.lock | pypi>`
- `lockfile` : `<package-lock.json | npm>`
- `dependency-min-age` : `<7>`

Les dépendances directes qu'une PR ajoute, comparées à la liste de ce que le projet a décidé de permettre. Un
paquet qu'un agent ajoute sans décision acceptée est refusé, et le refus dit la ligne à écrire. Une clé, sans
valeur par défaut.

`stack` : le fichier de la liste, un chemin relatif à la racine du projet, sur une seule ligne. Chaque ligne du
fichier est `<écosystème> | <paquet> | <source>` : l'écosystème est fermé (`pypi` ou `npm`), et la source est la
décision acceptée qui permet le paquet (un ADR, une séance). Pour `pypi`, les noms se comparent normalisés
(casse, `-`, `_`, `.`) ; pour `npm`, tels qu'écrits. Une ligne mal formée est `INVALID` avec son numéro, jamais
complétée. Sans la clé, « sans objet (clé `stack` absente) » : aucune valeur par défaut, et la sonde ne compare rien.

`forge:qc-gate` lance `scripts/stack_check.py` avec les clés lues sur la base : le chemin du fichier vient de la
base, pour qu'une PR ne relève pas la liste qui la juge, et son contenu se lit sur la tête. Le script compare, pour
chaque entrée de la clé `lockfile`, les paquets directs que le lockfile d'un membre local déclare à la tête et
non à la base ; une dépendance indirecte n'est pas comparée. Il rend une ligne par paquet : `OK` (dans la liste,
avec sa source), `UNLISTED` (absent de la liste : la ligne dit la ligne à écrire et le chemin du fichier),
`NO SOURCE` (dans la liste, sans source), `ADDED` (une ligne que la PR ajoute à la liste, avec sa source), `NONE`,
`NOT RUN` (un écosystème de la liste qu'aucune entrée de `lockfile` ne lit) ou `INVALID`. Il n'ouvre aucun accès
réseau et ne lance aucune commande du projet. Il lit la clé `lockfile` en même temps : sans elle, « sans objet
(clé `lockfile` absente) ». `forge:qc-conf` fait de `UNLISTED` et de `NO SOURCE` un `BLOCKER`, et lit la source
de chaque ligne `ADDED`.

- `stack` : `<docs/agents/stack.md>`

Le fichier que la clé désigne, à titre d'exemple : une ligne `<écosystème> | <paquet> | <source>` par paquet permis.

```
pypi | httpx | docs/decisions/client-http.md
npm | zod | docs/seances/validation-des-formulaires.md
```

La mesure de la carte des modules, ce que le design accepté d'une feature déclare : un module ne s'utilise que par
son interface, et les dépendances pointent vers l'intérieur. Une clé, sans valeur par défaut.

`architecture-check` : la commande qui la mesure, une seule commande sur une seule ligne, découpée comme par un
shell POSIX et lancée sans shell depuis la racine du projet. Elle sort 0 quand la carte est tenue, et un autre code
sinon ; elle n'a pas besoin de réseau. `forge:qc-gate` la lit sur la base (une PR ne change pas la règle qui la
juge) et la rejoue sur une copie de la tête, sous le lanceur borné qui lit `run-limits` : `PASS` (code 0), `FAIL`
(un autre code) ou `NOT RUN` (commande introuvable, poste hors budget, mémoire ou délai atteints). Sans la clé,
« sans objet (clé `architecture-check` absente) » : aucune valeur par défaut, aucune commande devinée.
`forge:qc-conf` fait de `FAIL` un `BLOCKER` de la règle `F-15`, qui cite la commande et la fin de sa sortie. La
carte elle-même est un fichier du dépôt : pour qu'une PR ne puisse pas en retirer une règle sans l'humain, protège
ce fichier par une entrée `never-weaken` de type `removed-line`.

- `architecture-check` : `<uv run python scripts/check_modules.py>`
- `never-weaken` : `<docs/agents/modules.md | removed-line>`

La forme que prend la carte des modules, à titre d'exemple : un fichier de lignes `<module> | <interface publique>
| <dépend de>`, que la commande du projet lit et que forge ne lit pas. Elle dit, pour chaque module, ce qu'on en
utilise (l'interface) et de quels modules il dépend (`aucun` pour une feuille) ; une dépendance qui n'est pas dans
cette colonne, ou qui contourne l'interface, est ce que la commande refuse. Une carte qui ne suit pas cette forme
convient aussi, pourvu que la commande sorte 0 quand elle est tenue.

```
lockfiles | read_at, parse_uv_lock, direct_dependencies | aucun
stack_check | main | lockfiles, usine
```

## Essai de bout en bout

L'essai de l'usine avant une version, par `scripts/e2e_trial.py`. Les tests de `tests/` éprouvent chaque
hook et chaque script seul ; l'essai éprouve l'enchaînement (un coder qui n'ouvre pas sa PR, un garde qui
refuse un geste légitime) sur un dépôt d'essai que le projet désigne. Trois clés, chacune sur une seule
ligne et sans valeur par défaut : une clé absente rend « sans objet (clé `<nom>` absente) » et le script
n'écrit jamais `PASS`. Une quatrième, `e2e-run-limits`, est facultative. La création du dépôt d'essai et
de son jeton est un geste humain : le script ne la fait pas.

`e2e-repo` : le dépôt d'essai sur GitHub, `<propriétaire>/<nom>`. Le script y crée un ticket fictif et y
nettoie ensuite ce qu'il a créé, retrouvé par son numéro, rien d'autre. Sans la clé, l'étape est
« sans objet (clé `e2e-repo` absente) ».

- `e2e-repo` : `<propriétaire/depot-d-essai>`

`e2e-command` : la commande lancée dans le projet jetable, un clone neuf du dépôt d'essai, découpée en mots
comme le fait un shell puis lancée sans shell, sous le lanceur borné (`e2e-run-limits` ou `run-limits`, `run-budget`). Elle cite
`{plugin}` (le plugin à essayer) et `{budget}` (la clé `e2e-budget-usd`), sans quoi l'essai ne tiendrait pas
le plugin à essayer sous le plafond ; `{feature}`, `{ticket}` et `{base}` (la branche de base de l'essai)
sont facultatives. Toute autre marque est refusée. Sans la clé, l'étape est
« sans objet (clé `e2e-command` absente) ».

- `e2e-command` : `<claude -p --plugin-dir {plugin} --max-budget-usd {budget} "/forge:feature-build {feature} --base {base}">`

`e2e-budget-usd` : le plafond de l'essai en dollars, un nombre positif, que la commande passe à
`--max-budget-usd` par `{budget}`. Sans la clé, l'étape est « sans objet (clé `e2e-budget-usd` absente) ».

- `e2e-budget-usd` : `<2.50>`

`e2e-run-limits` : clé facultative, protégée (elle lève la borne de `run-limits` pour le lancement : elle se lit dans
`usine-gardes.md`), la mémoire en Mo et le délai en secondes du seul lancement de la
commande, sous la forme de `run-limits` (une seule ligne, deux nombres positifs). Une feature entière
(`forge:feature-build`) tourne plus longtemps qu'une suite de tests : `run-limits` est dimensionnée pour
la suite, et cette clé donne à l'essai sa propre borne. Elle l'emporte sur `run-limits`, les options
`--memory-mb` et `--timeout` du script l'emportent sur les deux, chaque part (mémoire, délai) séparément.
Elle ne borne que le lancement : le budget du poste (`run-budget`) se lit comme avant. Comme `run-limits`,
qu'elle remplace pour le lancement, elle borne l'agent : un projet l'écrit dans `docs/agents/usine-gardes.md`,
avec les autres clés protégées. Sans la clé, la
borne est celle de `run-limits`, comme avant ; une valeur mal formée refuse l'appel (code 2). Le
délai de la clé, plus l'attente des vérifications (`--wait-checks`, 600 s par défaut), doit rester sous
le plafond de 3600 s que `scripts/release.py` met à l'essai entier : au-delà, le script est tué sans
avoir nettoyé.

- `e2e-run-limits` : `<mémoire en Mo> | <délai en secondes>`

## Libellés de l'écran

Les libellés qu'une PR ajoute ou change, confrontés par `forge:qc-gate` (`scripts/ui_labels.py`) aux
mots refusés et au glossaire. Deux clés, qui ne se remplacent pas : une clé absente rend sa partie
« sans objet », jamais `PASS`, sans valeur supposée.

`ui-labels` : les fichiers de libellés du projet, un par ligne ; un chemin qui finit par `/` est un
dossier. Un libellé est la valeur d'une ligne ajoutée (`clé: "Valeur"`, `clé=Valeur`, ou la ligne
seule) ; la clé qui le porte, une ligne vide et un commentaire (`#`, `//`) n'en sont pas. Sans cette clé,
toute la sonde est « sans objet (clé `ui-labels` absente) ».

- `ui-labels` : `<app/i18n/>`

`ui-forbidden-word` : un mot ou un motif refusé à l'écran, **une ligne par mot**. C'est une expression
régulière, cherchée sans égard à la casse et comme mot entier (un mot simple ne correspond pas au mot
plus long qui le contient). Un libellé qui en contient un est rendu `FORBIDDEN`, et `forge:qc-conf` en
fait un `BLOCKER`. Sans cette clé, cette partie est « sans objet (clé `ui-forbidden-word` absente) ».

- `ui-forbidden-word` : `<commit>`
- `ui-forbidden-word` : `<F-\d{4}>`

Avec la clé `glossary`, la sonde rend aussi `UNKNOWN` chaque mot capitalisé d'un libellé (le premier
mot du libellé mis à part) qui n'est dans aucun fichier du glossaire ; `forge:qc-conf` en fait un
`MINOR`. Sans la clé `glossary`, cette partie est « sans objet (clé `glossary` absente) ».

## Preuves d'écran

Quatre capacités de vérification du front, puis le rejeu du parcours en CI, que le projet active **une par une**, chacune par sa propre
clé. Une clé absente rend sa capacité « sans objet (clé `<nom>` absente) », jamais `PASS`, et aucun
agent n'en suppose une : le projet qui n'a pas d'interface n'en déclare aucune. `scripts/preuves_ecran.py`
les lit et dit, sans avis, ce que chacune déclare et si les captures que la matrice attend sont jointes à
la PR. `forge:coder` s'en sert pour la section **Preuves**, `forge:qc-gate` mesure, `forge:qc-conf` juge
et `forge:feature-verify` relie le critère à sa capture ; `forge:feature-review` s'en sert pour jouer le parcours sur l'application réelle. Éprouvé sous Linux seulement, sur des
fichiers écrits à la main, et sur aucun vrai poste.

`screenshot-command` : la commande qui prend des captures du navigateur sans écran (en CI comme en
local), lancée depuis la racine du dépôt. `{out}` y est obligatoire : le dossier où elle écrit ses
fichiers, que l'appelant choisit et protège par des guillemets. Une valeur sans `{out}` fait échouer le
script. La commande d'exemple n'a pas de `--` avant le fichier de spec (avec lui, `pnpm` le transmet tel
quel et Playwright ignore le filtre : toute la suite se lance).

- `screenshot-command` : `<pnpm --filter <app> e2e e2e/<spec> --output {out}>`

`recording-command` : la même chose pour une vidéo ou un GIF d'un parcours, `{out}` obligatoire.

- `recording-command` : `<pnpm --filter <app> e2e e2e/<parcours> --output {out}>`

`browser-drive` : un navigateur piloté par un agent, `<outil> | <poste>`. Il ne tourne que sur un poste
avec une session ouverte, **jamais en CI** : la clé nomme le poste où le faire, et un agent ne le lance
pas ailleurs. Sans la clé, aucun navigateur n'est piloté. Elle sert la recette sur ce poste : une PR faite ailleurs
n'en attend aucune capture.

- `browser-drive` : `<nom de l'outil de pilotage | nom du poste de recette>`

`computer-use-host` : le poste **dédié** où l'ordinateur se commande (clics, saisie, captures de
l'écran entier), par son nom, jamais le poste personnel d'un membre : la clé ne se remplit pas par
défaut avec le poste de celui qui lance la session, et sans elle la commande de l'ordinateur est
« sans objet (clé `computer-use-host` absente) ». Comme `browser-drive`, elle sert la recette sur son
poste et n'ouvre aucune attente de capture sur une PR : seules `screenshot-command` et `recording-command`
l'ouvrent.

- `computer-use-host` : `<nom du poste dédié à la recette>`

`journey-replay` : `<contexte de CI> | <commande>`, la commande qui joue le parcours voulu
(`parcours.md` de la feature) de bout en bout, depuis un dépôt propre jusqu'au poste de travail de
l'utilisateur, et le nom du job de CI qui la lance. Le contexte doit figurer parmi les `required-contexts` :
un parcours cassé bloque alors la PR ; sans cela `scripts/preuves_ecran.py` rend `CONTEXTE-NON-REQUIS`, et
sans la clé `required-contexts` la mesure est « sans objet (clé `required-contexts` absente) ». `{out}` est
obligatoire dans la commande : le dossier où elle écrit les captures, que le job envoie comme artefact.
Les captures sont réelles et non retouchées. Une capture pleine page de Playwright ne déclenche pas
`loading="lazy"` : pour les captures de contrôle, la page retire l'attribut. Sans la clé, la capacité est
« sans objet (clé `journey-replay` absente) ».

- `journey-replay` : `<parcours (ubuntu-latest) | pnpm --filter <app> e2e e2e/<spec> --output {out}>`

`journey-paths` : les préfixes de chemin du front et des API qu'il consomme, un par ligne. Toute PR qui
change un fichier sous l'un d'eux joint les captures du parcours (`forge:qc-gate` rend `PARCOURS-TOUCHE`,
`forge:qc-conf` fait de l'absence de capture un `BLOCKER`). Sans la clé, la sonde le dit
(« sans objet (clé `journey-paths` absente) ») et ne devine aucun chemin.

- `journey-paths` : `<apps/web/>`
- `journey-paths` : `<apps/api/routes/>`

Les artefacts du job envoyés par `actions/upload-artifact` se conservent 90 jours par défaut.
Conserver les captures du parcours plus longtemps demande de relever la rétention du dépôt
(`actions/permissions/artifact-and-log-retention`, au plus 400 jours pour un dépôt privé) : `retention-days`
est borné par ce réglage, et le changer est un geste du propriétaire, à faire avant le premier run.
Épingler alors `retention-days` sur les autres artefacts, pour qu'ils ne passent pas à la nouvelle durée
sans qu'on l'ait voulu.

## Revue

La grille de revue de `forge:qc-conf`, dans son ordre : un skill ou un fichier.

- `review-grid` : `<.claude/skills/reviewer/SKILL.md>`

Les cas de validation des tickets (`socle.md`, Validation cases). La date d'adoption : un ticket
créé avant elle n'a pas besoin de cas, et son critère `A<n>` vaut le cas `A<n>.1`. Sans la clé,
`guard_cases` ne lit rien et ne refuse rien. Chaque relecteur déclaré lit les cas au tour 0 quand le
ticket nomme un chemin de son périmètre, et doit figurer dans `AGREED:` quand le diff de la PR en
touche un. Le propriétaire est le login GitHub dont une modification du corps après l'ouverture de
la PR reste admise. Les règles de sécurité locales s'ajoutent à la liste fermée du socle.

- `validation-cases` : `<2026-11-14>`
- `validation-reviewer` : `<securite | runner/, .github/>`
- `validation-owner` : `<login GitHub du propriétaire>`
- `security-rules` : `<L-3, L-4>`

Les chemins qu'aucun agent ne fusionne, même sur ACCEPT : un humain le fait. Un chemin ou un préfixe
par ligne, comparé mot à mot au chemin POSIX relatif de chaque fichier du diff. `forge:qc` s'arrête
avant la fusion ; `guard_git` refuse en plus `gh pr merge` à tout agent quand un fichier du diff
commence par une ligne de la clé (lue par `gh pr view --json files`), et, la clé déclarée, quand la
liste est illisible ou que `gh` échoue ou dépasse son délai. Sans la clé, il ne refuse rien à ce titre.

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
- `raised-entry` : un fichier de référence gagne une clé ou en relève le nombre. Sans paramètre : une
  entrée qui en porte un est `INVALID`. Le fichier est de lignes `<nombre> <clé>`, ou `<clé>` seule, qui
  compte 1. Pour chaque fichier du diff sous le chemin, chaque clé des lignes ajoutées se compare à la même
  clé des lignes retirées du même fichier : une clé sans ligne retirée, ou un nombre plus grand, s'applique
  et nomme le fichier et la clé (avec les deux nombres pour un relèvement) ; une clé retirée ou un nombre
  plus bas passe.

`forge:qc-gate` lance `scripts/never_weaken.py` sur le diff de la PR, avec les entrées lues sur la
base : une PR ne peut pas lever la règle qui la juge, et retirer ou modifier une entrée dans
`docs/agents/usine.md` s'applique elle-même. Le script lit le diff et ne lance aucune commande du
projet. Une entrée à qui il manque une partie, ou dont le type est inconnu, est signalée, jamais
complétée. Sans la clé, la règle est sans objet.

- `never-weaken` : `<.github/workflows/ | removed-line>`
- `never-weaken` : `<config/tolerances.toml | raised-number | ^rel_tol = (\S+)>`
- `never-weaken` : `<docs/fonctions/ | lowered-rank | statut | certifie > valide > brouillon>`
- `never-weaken` : `<scripts/baselines/types.txt | raised-entry>`

## Rapport

Le mail de relevé de l'usine, construit par `scripts/report_mail.py` à partir de ces seules clés. Le
script sort en code 10 quand rien n'a changé depuis le dernier envoi (aucun mail), et `--sent`
enregistre l'envoi. Sans `report-repo`, il s'arrête et nomme la clé ; sans une autre, sa partie du
mail dit « clé `<nom>` absente » et rien n'est deviné.

Les dépôts relevés (PR fusionnées, verdicts, CI de `main`, runners), une ligne par dépôt `<propriétaire>/<nom>`.
Le premier sert aussi aux tickets et aux PR de la partie « Features », que `report_mail.py --features`
rend en tableau pour la réponse de session et la passation.

- `report-repo` : `<propriétaire/dépôt>`

L'étiquette dont l'ensemble des tickets et des PR ouverts est relevé et compté parmi les événements.

- `report-attention-label` : `<needs-your-attention>`

Le fichier de workflow dont le dernier run terminé sur `main` est relevé. Sans la clé, le dernier run
terminé de `main`, tout workflow confondu.

- `report-main-workflow` : `<ci.yml>`

Le groupement des runners (`gh api repos/<dépôt>/actions/runners`) par hôte : `<hôte> | <étiquette de
runner>`, une ligne par hôte. Un runner qu'aucune ligne ne réclame est listé sous « no host ». Sans la
clé, les runners sont comptés par dépôt.

- `report-host` : `<poste | shipyard-ci>`
- `report-host` : `<vps | vps-ci>`

La sonde mémoire et disque d'un hôte : `<hôte> | <commande>`, lancée par le shell du poste, qui
imprime sa mesure en une ligne (reprise telle quelle, 200 caractères au plus). Sans ligne pour un
hôte, le mail dit qu'aucune sonde n'est nommée ; une sonde en échec se lit « probe failed », et le
script n'échoue pas.

- `report-host-probe` : `<poste | free -h | awk 'NR==2{print "mem " $3 "/" $2}'; df -h / | awk 'NR==2{print "disk " $3 "/" $2}'>`

Le plancher d'un hôte, en Gio libres : `<hôte> | <mémoire> | <disque>`. Les places libres d'un hôte
sont ses runners libres (en ligne, pas occupés) ; sous son plancher, il n'en a aucune. Sa sonde doit
alors imprimer `mem-free <Gio>` et `disk-free <Gio>` : une sonde en échec ou sans ces deux mesures
donne aucune place. `report_mail.py --slots` rend le total en une ligne, `unknown` quand les runners
d'un hôte compté sont illisibles (jeton sans droit d'administration) ; `feature-build` le lit avant
chaque coder. Sans la clé, un hôte compte ses runners libres sans plancher.

- `report-host-floor` : `<poste | 2 | 10>`

L'heure UTC après laquelle un bilan du jour part même sans événement. Sans la clé, aucun bilan : un
jour sans événement n'envoie rien.

- `report-digest-hour` : `<7>`

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

Le ménage après un agent fini (`agent_cleanup.py`, au `SubagentStop` et au `SessionStart`) retire sans
clé le worktree propre d'un agent fini (`.claude/worktrees/agent-*` ; fini : verrou d'un détenteur mort,
ou, sans verrou, agent noté rendu par Claude Code et sa transcription silencieuse depuis 30 minutes)
et supprime la branche
`worktree-agent-*` orpheline dont la tête est dans `main` ou une branche distante : ces deux étapes
suivent la convention de Claude Code, pas une valeur du projet. Deux clés ajoutent le reste, chacune
indépendante, et une clé absente rend son étape « sans objet (clé `<nom>` absente) » : rien n'est
supprimé, aucune valeur par défaut. Chacune est un dossier, `~` développé, un par ligne.

Le dossier où les agents posent leurs caches. Au `SubagentStop` seulement, le hook supprime les
sous-dossiers directs que nomme la transcription de l'agent qui s'arrête ; jamais au `SessionStart`,
car une autre session du poste peut avoir des agents vivants dans ce dossier. Un dossier qui contient
le home ou le dépôt est ignoré.

- `agent-cache-dir` : `<~/.cache/agents>`

Le dossier des bundles de sauvetage (`*.bundle`, `git bundle create`). Le hook supprime chaque bundle
dont toutes les têtes existent dans le dépôt et sont contenues dans `main` ou une branche distante ;
un bundle illisible, ou dont une tête manque au dépôt, reste et est signalé. `guard_git` lit aussi ce
dossier : il laisse passer `git branch -D` sur une branche locale quand un bundle que `git bundle verify`
accepte tient chaque commit qu'aucune branche distante ne tient. Sans la clé, ou sans bundle, le refus reste
et le geste revient à l'humain.

- `rescue-bundle-dir` : `<~/.cache/rescue-bundles>`

Les agents du projet tenus en lecture seule comme les décideurs du plugin (l'arbitre du métier, en
général), sous leur nom tel que le voient les hooks. Un par ligne.

- `readonly-agent` : `<domain-arbiter>`

Les commandes que ces agents en lecture seule peuvent lancer en plus des lectures prévues (un
calculateur du projet, par exemple), chacune comme un préfixe. Une par ligne.

- `readonly-command` : `<uv run python -m scripts.calcul>`

The hosts of the project's infrastructure (a CI server, an LXD instance), by address, DNS name, ssh
alias or `lxc` instance name, one per line: `guard_infra` admits only its read list on them, by
`ssh`, `scp`, `rsync` or `lxc exec <host> --`. Without the key, no remote host is guarded; the local
deny list (`docker rm`, `systemctl restart`...) still holds.

- `infra-hosts` : `<203.0.113.7>`
- `infra-hosts` : `<ci-runner>`

The project's own check commands, admitted on those hosts besides the read list, one per line and
word for word: `bash <command>` and `sh <command>` count as `<command>`, any other argument or form
is held. Without the key, no such command is admitted.

- `infra-verify` : `<infra/runner/check.sh verify>`
- `infra-verify` : `</opt/ci/host-check.sh status>`

Les gestes du propriétaire du dépôt propres au projet, que `guard_git` refuse à tout agent en plus
de sa liste intégrée (écritures de `gh api` sur les collaborateurs, protections de branche,
rulesets, runners, secrets, variables, clés, webhooks et dépôt ; `gh secret`, `gh variable`,
`gh repo` ; les scripts d'un runner ; les mutations GraphQL de protection, de ruleset, de
collaborateur et de dépôt). Une ligne `<préfixe de commande> | <raison>` par geste. Le préfixe se
compare mot à mot au début de la commande, après les affectations d'environnement et les options
globales de gh (`gh -R o/r label delete` correspond à `gh label delete`) ; la raison est reprise
dans le refus. Une ligne sans raison refuse quand même, et le dit. Une lecture (`GET`, `HEAD`) n'est
pas un geste du propriétaire ; elle passe si `gh-api-allow` et la liste du plugin l'admettent. Sans la
clé, seule la liste intégrée s'applique. Une par ligne.

- `owner-gesture` : `<gh label delete | les étiquettes sont posées par le propriétaire>`

Les appels `gh api` propres au projet, que `guard_git` laisse passer en plus de la liste du plugin (les
lectures d'une PR, de ses fichiers, de ses commentaires et de ses checks, de la CI et des sous-tickets,
l'écriture d'un commentaire, d'un sous-ticket et d'une étiquette, GraphQL et la fusion). Un `gh api`
qui n'est ni sur la liste du plugin ni sur une de ces lignes est refusé, l'appel et la raison nommés.
Une ligne `<méthode> | <motif de chemin> | <raison>` par appel : la méthode est `GET`, `HEAD`, `POST`,
`PUT`, `PATCH` ou `DELETE`, lue comme `gh` la lit (le dernier `-X`, sinon `POST` dès qu'un champ ou
`--input` est donné, sinon `GET`) ; le motif se compare au chemin sans `?` ni `/` de tête, avec `*`
(une partie d'un segment) et `**/` (des dossiers) ; la raison dit pourquoi le projet fait cet appel. Une
ligne à qui il manque une partie, ou dont la méthode n'en est pas une, n'autorise rien et est citée dans
le refus. La clé n'ouvre pas un geste du propriétaire (`owner-gesture` et la liste intégrée restent
refusés). Sans la clé, seule la liste du plugin s'applique. Une par ligne.

- `gh-api-allow` : `<DELETE | repos/*/*/git/refs/heads/* | le nettoyage des branches de PR>`

Les formateurs lancés après chaque écriture d'un agent (Edit, Write, MultiEdit) : une ligne
`<motif> | <commande>` par formateur. Le motif se compare au chemin relatif entier, en POSIX, casse
comprise : `**/` (des dossiers, ou aucun), `*` et `?` (jamais un `/`), `{a,b}` (non imbriqué), tout
le reste est littéral. La commande est découpée comme par un shell POSIX, lancée sans shell depuis la
racine du dépôt, le chemin absolu du fichier ajouté en dernier argument ; elle peut contenir `|`
(la coupe se fait au premier ` | `). Plusieurs motifs qui correspondent : toutes les commandes,
dans l'ordre du fichier, avant le contrôle du tiret cadratin. Chacune a 30 s, 120 s au total.
Chaque formateur est lancé dans son propre groupe de processus (une session neuve sous Linux, un
job Win32 sous Windows) : au délai, tout le groupe est tué, pas seulement la commande, avec trois
limites sous Windows : un petit-enfant lancé avant `AssignProcessToJobObject` échappe au job ; si
le job ne peut être créé ou assigné, seul l'enfant direct est tué ; et si `TerminateJobObject`
échoue (retour 0), le hook retombe sur `process.kill()` et seul l'enfant direct est tué aussi. Le
`wait` qui suit le `kill` est borné : un processus qui ne meurt pas en temps ne bloque pas la
session. Sous Windows, un formateur résolu en `.cmd` ou `.bat` passe par `cmd.exe` : le hook refuse
de lui donner un chemin qui contient `&|<>^%!"` ou une parenthèse, plutôt que de le citer. Le refus
ne couvre pas une commande que le projet fait passer par `cmd /c` : `cmd` se résout en `cmd.exe`, qui
n'est ni `.cmd` ni `.bat`, et le chemin du fichier arrive en argument après `/c`. Un échec ou un
délai dépassé ne défait pas l'écriture : une ligne sur stderr que l'agent voit, `format-on-write:
<commande> failed on <chemin> (<raison>)`, la raison étant `exit <n>`, `timed out after <n>s`
(arrondi au supérieur), `command not found`, `could not start: <cause>` ou `not run: <cause>`,
suivie de la fin de ce que la commande a imprimé : les 20 dernières lignes et 2000 octets au plus.
Sans la clé, rien n'est formaté.

- `format-on-write` : `<**/*.py | uv run ruff format>`
- `format-on-write` : `<apps/web/**/*.{ts,tsx} | pnpm --dir apps/web exec prettier --write>`

Les contrôles lancés après chaque écriture d'un agent, une fois les formateurs passés : une ligne
`<motif> | <commande>` par contrôle, du même motif et de la même forme que `format-on-write`
(commande découpée comme par un shell POSIX, lancée sans shell depuis la racine, chemin absolu du
fichier en dernier argument, groupe de processus tué au délai, 30 s par commande et 120 s au total,
partagés avec les formateurs). Un contrôle qui échoue refuse l'écriture : code 2, et une ligne sur
stderr, `lint-on-write: <commande> failed on <chemin> (<raison>)`, de mêmes raisons que
`format-on-write`, suivie de la fin de la sortie de l'outil (les 20 dernières lignes et 2000 octets
au plus), pour que l'agent voie la règle enfreinte. Le fichier reste écrit, la commande trop lente
est tuée. Une ligne qui n'est pas `<motif> | <commande>` est ignorée, et le message le dit. Sans la
clé, rien ne tourne et l'étape est « sans objet (clé `lint-on-write` absente) » : aucun outil
n'est deviné. Le nombre de lignes n'est pas plafonné.

- `lint-on-write` : `<**/*.py | uv run ruff check>`

La base de règles de code que ce gabarit propose à un projet Python, en une ligne de `lint-on-write` : trois
règles de ruff, chacune avec son seuil écrit en clair. `C901` refuse une fonction de complexité cyclomatique
supérieure à 10 (le seuil de McCabe, repris par la norme NIST SP 500-235), `PLR0913` une fonction de plus de 5
paramètres (le défaut de ruff) et `PLR1702` une fonction qui imbrique plus de 5 blocs (le défaut de ruff
aussi). `PLR1702` est en aperçu dans ruff : `--preview` est nécessaire, et la version de ruff s'épingle
(`--with ruff==<version>`), car une règle d'aperçu peut changer de sens ou disparaître d'une version à l'autre ;
monter l'épingle est un geste du projet, qui relance la commande sur son code avant de la changer. `--select`
limite le contrôle à ces trois règles : l'aperçu ne s'applique alors qu'à elles, et la ligne `uv run ruff check`
du projet garde ses propres règles. Un seuil se règle sur la ligne, jamais dans un défaut du plugin. Il n'y a aucun
plafond de lignes : aucune règle de la base ne borne la longueur d'une fonction ni d'un fichier, aucune source ne
relie la longueur aux défauts.

- `lint-on-write` : `<**/*.py | uv run --no-project --quiet --with ruff==0.17.3 ruff check --preview --select C901,PLR0913,PLR1702 --config lint.mccabe.max-complexity=10 --config lint.pylint.max-args=5 --config lint.pylint.max-nested-blocks=5>`

Les documents que le projet tient par hook plutôt que par une consigne dans un skill. Le hook
`after_write` les contrôle sur le fichier que l'agent vient d'écrire, avec la même sortie que le
tiret cadratin : une ligne sur stderr, code 2, l'écriture reste et l'agent corrige. Seul le fichier
écrit est jugé : un document existant que personne ne touche ne bloque rien. Un fichier écrit par
une commande de shell (un heredoc, `sed`) ne passe pas par ce hook. Sans une clé, son contrôle est
sans objet, et aucune ne prend de valeur par défaut. Le motif est celui de `format-on-write`.

`doc-frontmatter` : un motif par ligne. Un `.md` écrit dont le chemin relatif en suit un doit
s'ouvrir sur un frontmatter (`---`, des lignes plates `clé: valeur`, `---`) qui porte un `type` non
vide ; sinon le hook dit quoi ajouter en tête de fichier.

- `doc-frontmatter` : `<docs/**/*.md>`

`doc-index` : le chemin de l'index généré des documents que couvre `doc-frontmatter`. À chaque
écriture d'un tel fichier, le hook reconstruit l'index depuis `git ls-files` (les fichiers suivis et
les non suivis que git n'ignore pas, plus le fichier écrit) : un frontmatter `type: index`, une
ligne qui dit qu'il est généré et ne s'édite pas à la main, puis un tableau Document, Type, Titre
trié par chemin, pour chaque `.md` couvert qui porte un `type` (le titre est `title` du frontmatter,
sinon le premier titre `# `). L'index ne s'y liste pas, le contrôle de `doc-frontmatter` ne le juge
pas, et le fichier n'est réécrit que si son contenu change. Une seule valeur ; sans
`doc-frontmatter`, pas d'index.

- `doc-index` : `<docs/index.md>`

`doc-cap` : `<motif> | <n> mots` ou `<motif> | <n> lignes`, une ligne par plafond (plusieurs
plafonds peuvent viser un même fichier). Le compte porte sur le corps du fichier écrit, frontmatter
exclu : les mots se coupent sur les blancs, toutes les lignes comptent, les vides aussi. Le
cliquet est la version du fichier à `HEAD` (`git show`) : absent de `HEAD` ou sous le plafond à
`HEAD`, le fichier doit tenir sous le plafond ; déjà au-dessus à `HEAD`, il ne peut pas grandir.
Un dépassement sort le compte, le plafond, la ligne de la clé, et la consigne de raccourcir ou
d'écrire un nouveau document qui remplace l'ancien. Une valeur illisible (pas d'unité, `0`, un
nombre qui n'en est pas un) est signalée et ignorée, jamais devinée.

- `doc-cap` : `<docs/adr/*.md | 800 mots>`
- `doc-cap` : `<docs/guides/*.md | 300 lignes>`

### Output structure

The hook `guard_output` checks every output against its template under `templates/`: a subagent's
final text, the body of a gh ticket, pull request or comment, and the session's reply to the human.
These keys are the exception to the rule above: an absent key keeps the cap written here, so the
check holds in every project. Code blocks and table cells count, HTML comments do not; `0` lifts a cap.

- `output-words-ticket` : `150`
- `output-words-comment` : `150`
- `output-words-pr` : `200`
- `output-words-session-reply` : `150`
- `output-words-report-mail` : `500`
- `output-words-subagent-return` : `200`
- `output-words-paragraph` : `60`

A project template replaces the plugin's for the required fields of one kind (`ticket`, `pr`,
`comment`, `verdict`, `session-reply`, `subagent-return`): the `required:` part of its first line
names them, or none.

- `output-template` : `<pr | .github/pull_request_template.md>`

A project agent checked against a declared format rather than the generic rule: `coder`, `verdict`,
`decider` (keys `VERDICT:` and `DECISION:`), `gate` (a table), `subagent-return`, or `exempt`.

- `output-agent-format` : `<security-reviewer | exempt>`

`shared-resource` : une ligne par ressource que deux sessions du poste peuvent se disputer (un pool de
worktrees, un runner, une base de test). Le hook `guard_output` impose le billet (`templates/billet.md`)
à tout message envoyé à une autre session, et le champ `resource` du billet prend ses valeurs dans cette
clé, plus `none`. Sans la clé, le contrôle de `resource` est sans objet (clé `shared-resource` absente) :
toute valeur non vide passe, le champ restant exigé. Aucune valeur n'est devinée.

- `shared-resource` : `<worktree-pool>`

The keys a project adds to a structured format (`verdict`, `coder`, `decider`): any other key is
refused.

- `output-extra-keys` : `<verdict | REGIME, VERIFIED, REMARKS, OUT OF SCOPE>`
