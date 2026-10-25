# Installer, configurer, monter de version

Le détail de ce que résume le [`README.md`](../README.md#installer-dans-un-projet) : les prérequis,
l'installation pas à pas, la configuration, les montées de version, les gestes qu'aucun agent ne
fait, et les limites connues.

## Prérequis sur le poste

- Claude Code.
- [uv](https://docs.astral.sh/uv/) : chaque hook se lance par `uv run --no-project --quiet python`.
  Sans uv, `guard_git`, `guard_coder` et `guard_readonly` refusent chaque appel qu'ils filtrent
  (leur échec vaut refus), et les autres gardes ne s'appliquent pas. Le champ `onFailure` de
  `guard_git` (refus aussi au dépassement du délai) demande Claude Code 2.1.295 ou plus ; pas encore
  essayé sur une version plus ancienne.
- [gh](https://cli.github.com/), authentifié : la revue, la chaîne des features et `guard_git`
  lisent et écrivent sur GitHub par lui.

## Installer dans un projet

1. **Épingler** la marketplace et activer le plugin dans le `.claude/settings.json` du projet, par
   une PR :

   ```json
   {
     "enabledPlugins": {
       "forge@ikoro-labs": true
     },
     "extraKnownMarketplaces": {
       "ikoro-labs": {
         "source": {
           "source": "github",
           "repo": "ikoro-labs/forge",
           "ref": "forge--v1.5.0"
         }
       }
     }
   }
   ```

   Le `ref` est un tag de ce dépôt. Changer de version est une PR du projet qui bouge ce `ref`,
   relue comme une montée de dépendance.

2. **Approuver le dossier** à la première session dans le projet : `extraKnownMarketplaces` n'est
   honoré qu'une fois la confiance du dossier accordée. Une session cloud l'ignore.

3. **Installer**, une fois par poste et par projet : `enabledPlugins` active le plugin sans
   l'installer. Depuis la racine du projet, redéclarer d'abord son épingle, puis installer :

   ```sh
   claude plugin marketplace add ikoro-labs/forge@forge--v1.5.0 --scope project
   claude plugin install forge@ikoro-labs --scope project
   ```

   La première ligne remet la marketplace du poste sur le `ref` du projet : un poste ne connaît
   qu'une source par marketplace, celle du dernier projet qui l'a déclarée (voir **Limites
   connues**). Elle réécrit aussi le `.claude/settings.json` du projet dans sa propre forme
   (indentation de deux espaces, `extraKnownMarketplaces` en dernière clé), sans toucher aux autres
   clés : sous la forme de l'étape 1, `git diff` reste vide. S'il montre autre chose que de la mise
   en forme, l'épingle tapée n'est pas celle du projet.

4. **Configurer** : copier `plugins/forge/templates/usine.md` vers `docs/agents/usine.md` dans le
   projet, puis, pour chaque clé, mettre la vraie valeur ou supprimer la ligne (voir **Configurer** plus bas).

5. **Vérifier** : `claude plugin list --json` donne, pour l'entrée de `forge@ikoro-labs` dont le
   `projectPath` est ce projet, la version du `ref` ; `/forge:` dans une session liste les skills.
   Sans `--json`, la liste n'affiche qu'une entrée par plugin, celle du dernier projet installé,
   même quand on la lance depuis un autre.

## Monter de version

1. Une PR du projet bouge le `ref` vers le nouveau tag, après lecture de son entrée au
   `CHANGELOG.md`.
2. Une fois fusionnée, sur chaque poste, depuis la racine du projet :

   ```sh
   claude plugin marketplace add ikoro-labs/forge@<nouveau tag> --scope project
   claude plugin update forge@ikoro-labs --scope project
   ```

   `update` prend la source que le poste connaît, pas le `ref` du projet. Sans la première ligne,
   un projet épinglé sur une version passe à celle qu'un autre projet du poste a déclarée en
   dernier.

**Jamais pendant un `/forge:feature-build` actif.** Une session garde les versions qu'elle a
chargées, mais la suivante charge la nouvelle : un passage repris dans une nouvelle session
changerait d'usine au milieu d'une feature. La mise à jour automatique de la marketplace reste
coupée.

Un poste qui n'a pas lancé `claude plugin update` garde l'ancienne version, et rien ne l'en avertit
en dehors de `/plugin` : après chaque montée, comparer `claude plugin list --json` au `ref` du
projet.

## Configurer : `docs/agents/usine.md`

Le seul fichier où un projet décrit son usine au plugin : qui accepte, la matrice de décision,
l'arbitre du métier, les commandes d'installation et de rejeu de la CI, les checks obligatoires, la
grille de revue, les chemins protégés, les changements que nul agent ne fusionne (`never-weaken` :
une ligne retirée, un nombre relevé, un rang abaissé, mesurés sur le diff par
`plugins/forge/scripts/never_weaken.py`), les tolérances des hooks, les commandes dont la sortie se
raccourcit. Le gabarit, `plugins/forge/templates/usine.md`, documente chaque clé.

Deux clés, `test-path` (un préfixe de chemin des fichiers de test, une ligne par préfixe) et
`red-replay` (la commande qui lance un fichier de test, avec `{file}` ou `{name}`), ouvrent la sonde
de rejeu de `forge:qc-gate` : `plugins/forge/scripts/base_replay.py` pose les tests que la PR ajoute
ou change dans une copie de la base et les y lance, et `forge:qc-conf` lit ceux qui y passent déjà,
parce qu'un test qui ne peut pas échouer sur l'ancien code ne prouve rien du changement. Le script
borne la mémoire (2000 Mo) et le délai (300 s) de chaque commande, puisqu'il exécute du code de test
contre un code qui ne l'attend pas : éprouvé sous Linux seulement : le côté Windows (un objet de
tâche, la commande démarrée suspendue) n'a tourné que dans la CI, où sa première version a échoué (borne
non tenue) ; la version corrigée n'est pas encore vue verte. Il juge au grain du fichier, qu'il rejoue en entier.

Deux clés, `ui-labels` (les fichiers de libellés de l'interface, une ligne par fichier ou dossier) et
`ui-forbidden-word` (un mot ou un motif refusé à l'écran, une ligne par mot), ouvrent la sonde des
libellés de `forge:qc-gate` : `plugins/forge/scripts/ui_labels.py` lit les lignes que la PR ajoute
sous ces fichiers, rend `FORBIDDEN` pour un mot refusé (un `BLOCKER` pour `forge:qc-conf`) et, avec la
clé `glossary`, `UNKNOWN` pour un mot capitalisé absent du glossaire (un `MINOR`). Cette lecture des
mots capitalisés est une approximation du « terme métier » : elle peut relever un mot qui n'en est pas
un. Éprouvé sous Linux seulement, sur des diffs écrits à la main ; pas encore sur un vrai projet.

Deux clés, `product-source` (les sources produit, en Markdown : un PDF, un `.docx` ou une image bloque
l'étape, qui demande un export Markdown) et `source-author` (qui peut écarter un élément d'une
source, un rôle ou un compte GitHub), ouvrent le comptage de `forge:feature-spec` :
`plugins/forge/scripts/source_ids.py` relève les éléments identifiés de la source (une ligne qui
commence par `EX-12`, `RG-3.1`...) et liste ceux que la spec ne reprend pas par leur identifiant ;
la spec ne passe en `ready-for-human` qu'à liste vide. Une exclusion ne vaut que sur un accord écrit
de l'auteur de la source que la spec cite ; sans `source-author`, aucun élément ne s'écarte. Éprouvé
sous Linux seulement, sur des sources écrites à la main ; pas encore sur un vrai projet.

`plugins/forge/scripts/parcours.py` lit le parcours voulu d'une feature (`parcours.md`, écran par
écran) : le format, puis que chaque écran cite un identifiant d'élément de la source, vérifié contre
les fichiers de `product-source` seulement. La spec ne sert jamais de référence de repli (un jeton
comme `F-0000`, `A1` ou `L1` y a la forme d'un identifiant sans être un élément de la source) : sans la
clé, la correspondance est « sans objet (clé `product-source` absente) » et rien n'est dit vérifié. Il ne lit aucune autre clé. Éprouvé
sous Linux seulement, sur des parcours écrits à la main ; pas encore sur un vrai projet.

`plugins/forge/scripts/matrice.py` lit la matrice de traçabilité d'une feature (`matrice.md`, une ligne
par identifiant de la source avec ticket, test, écran, capture, état et date) et applique l'état unique
(`tenu`, `partiel`, `absent`, `contraire`, `écarté`) : un `tenu` sans test ni capture est refusé, un
`écarté` exige l'accord que `source_ids.py` accepte (clé `source-author`). Elle lit `product-source`
comme `parcours.py` : sans la clé, « sans objet (clé `product-source` absente) ». `--reste` dit ce qui
reste par lot et par état, `--sans-ticket` les identifiants que nul ticket ne couvre (ceux de la source sans ligne comptent, aux deux modes, comme `absent`), `--cloture`
refuse sous 100 % (`feature-close` l'appelle). Chaque coder met à jour, avec son ticket, les lignes des identifiants que le
ticket couvre (ligne `Couvre :`), et le juge de la revue le vérifie. Les tickets voisins qui écrivent la
matrice initiale (à la conception) et la relisent de bout en bout (à la revue de la feature) passent par
ce script et ce gabarit ; ils ne sont pas livrés avec lui. Éprouvé sous Linux seulement, sur des matrices écrites à la
main ; pas encore sur un vrai projet.

Le skill de découpage en tickets du projet se déclare avec `ticket-skill` : `/forge:feature-design`
l'utilise à son étape de découpage. Sans la clé, il découpe à la main, dans l'ordre du §7 du
design, et le dit.

Une clé absente ne prend jamais de valeur par défaut : l'étape qui la lit se rend « sans objet (clé
`<nom>` absente) », jamais `PASS`. La revue d'un projet vaut donc ce que sa configuration déclare :
sans ses commandes de porte ni sa grille, `/forge:qc` rend des sondes « sans objet », plus faibles
qu'une revue configurée, et une clé qui pointe un chemin disparu donne un `NOT RUN` à chaque PR
jusqu'à sa correction.

## Les gestes du propriétaire du dépôt

`guard_git` refuse à tout agent les gestes qui reviennent au propriétaire du dépôt, et le refus
dit que l'humain les fait et que l'agent les liste en fin de compte rendu. La liste intégrée :

- les écritures de `gh api` (toute méthode sauf `GET` et `HEAD`, comme `guard_readonly` les lit) sur
  les collaborateurs, les invitations, la protection d'une branche, les rulesets, les runners, les
  secrets et variables d'Actions, ses permissions, les clés de déploiement, les webhooks, les
  environnements, le transfert, et sur le dépôt lui-même (`PATCH`, `DELETE`) ;
- les mutations GraphQL de protection de branche, de ruleset, de collaborateur et de dépôt, mais
  pas les autres : le plugin s'en sert pour les sous-issues. La requête est lue dans les arguments,
  dans le heredoc ou la redirection `<` de cette commande quand elle lit son entrée standard
  (`--input -`, `-F query=@-`), dans un heredoc `query="$(cat <<EOF ...)"`, et dans le fichier que
  nomment `--input` ou `-F query=@fichier`. Seul le descripteur 0 vaut `-`, une fois le
  chemin écrit en entier (`/dev/stdin`, `/dev/./stdin`, `//dev/stdin`, `/dev/fd/0`,
  `/proc/self/fd/0`, `stdin` après `cd /dev`, un lien symbolique vers l'un d'eux). Tout autre
  chemin sous `/dev/` ou `/proc/` (`/dev/fd/3`, `/proc/self/fd/3`, `/dev/tty`, `/dev/zero`) n'est
  pas l'entrée standard : le garde ne l'ouvre jamais et, s'il vise `graphql`, le refuse par
  précaution. Il ne lit qu'un
  fichier ordinaire de 1 Mo au plus. Une forme qui vise `graphql` et ne se lit pas est refusée par
  précaution, même si ce n'était pas une mutation : fichier absent, trop gros, qui n'est pas
  ordinaire (périphérique, FIFO, dossier), entrée standard d'un tube ou d'une chaîne
  (`<<<`), heredoc d'une autre commande, substitution `$(...)` ou variable du shell pour la
  requête. Un mot fait de `<`, `>` ou `&`, ou un nombre, après une option qui prend une valeur
  (`-t '>'`, `-q 1 > out`) peut être cette valeur ou une redirection : le garde juge les deux
  lectures et refuse si l'une refuse (au-delà de cinq mots de ce genre, il refuse sans juger) ;
- `gh secret` et `gh variable` (`set`, `delete`), `gh repo` (`delete`, `rename`, `archive`,
  `edit --visibility`, `deploy-key add` et `delete`, les options de `gh` avant l'action étant
  retirées) ;
- `config.sh`, `config.cmd` et `svc.sh` d'un runner, aussi derrière `sudo` (options collées
  comprises), `env`, `nohup`, `bash`, `sh` ou `cmd /c`, et dans un heredoc envoyé à un shell
  (`svc.sh status` reste une lecture). Un script de ce nom n'est celui d'un runner que dans un
  dossier qui porte `run.sh` ou `run.cmd` et `bin/Runner.Listener` (`bin/Runner.Listener.exe`
  sous Windows), ou appelé avec `--url`, `--token`, `--pat`, `--unattended`, `install`,
  `uninstall`, `start`, `stop` ou `remove` : un `scripts/config.sh` de projet passe. Toute
  affectation `ACTIONS_RUNNER_INPUT_*` est refusée, où qu'elle soit (devant la commande, après
  `env` ou `export`, seule, dans `bash -c` ou un heredoc), car le runner y lit son enregistrement.

La lecture passe toujours : un `GET` ou `HEAD` explicite (le dernier `-X`/`--method` compte, comme
pour gh, et la valeur d'une option comme `--jq` ou `-q` n'est pas une méthode), avec `-f`/`-F` ou
non, ou l'absence de méthode, de champ et de `--input` (avec un champ ou `--input`, gh envoie un
`POST`). Un projet ajoute ses gestes avec la clé `owner-gesture` de `docs/agents/usine.md`, une
ligne `<préfixe de commande> | <raison>` chacune ; sans la clé, la liste intégrée s'applique
seule. Ce comportement resserre celui des projets qui gardaient ces gestes dans leurs propres
hooks : ceux-ci peuvent rester, ils tournent à côté.

Cette garde protège d'un accident, pas d'une intention. Les formes qu'elle ne lit pas :

- un wrapper devant `gh` (`env gh`, `command gh`, `/usr/bin/gh`), et pour les scripts de runner un
  wrapper autre que `sudo`, `env`, `nohup`, `bash`, `sh`, `zsh`, `dash`, `cmd /c` et PowerShell
  (`exec ./svc.sh`, `xargs`, `ssh runner ./svc.sh start`) ;
- une mutation GraphQL hors de `gh api graphql` (`curl` vers l'API, un script), et celle d'un
  fichier que le garde ne peut pas lire depuis la machine où il tourne ;
- un script de runner appelé sans argument de runner depuis un dossier qui n'en porte pas les
  fichiers, ou dont le dossier n'est pas connu du garde (`cd "$DIR"`, `cd -`) ;
- une commande placée sur une autre ligne que la première : les sauts de ligne ne séparent pas les
  commandes pour le garde, hors des heredocs qu'il lit (constaté, hors du périmètre de ce
  changement) ;
- le contenu d'un heredoc envoyé à autre chose qu'un shell ou qu'un `gh api graphql`.

Éprouvé sous Linux seulement. Sous Windows, les chemins `C:\...`, `config.cmd` et le dossier d'un
runner Windows sont lus par des tests qui ne dépendent pas du système. La commande de `guard_git`
dans `hooks.json` est écrite pour un shell POSIX (`$(...)`, `case`, `printf`) : c'est celui de
Linux et de macOS, et ce doit être Git Bash sous Windows, ce qui n'a pas été essayé. Elle ne
s'analyse pas sous PowerShell sans Git Bash, et ce que Claude Code y fait d'une commande qui ne
s'analyse pas n'a pas été essayé non plus. `guard_coder` et `guard_readonly`, qui s'écrivent
`... || exit 2`, n'ont pas ce prérequis.

## Les PR qui touchent un chemin protégé

`guard_git` refuse à tout agent `gh pr merge <n>` quand un fichier du diff de la PR commence par une
ligne de la clé `protected-path` de `usine.md`. Le diff se lit par `gh pr view <n> --json files`, sous
le délai des autres appels du garde. Le refus nomme le fichier et le préfixe, et dit que la fusion
revient à l'humain, à lister en fin de compte rendu. La clé déclarée, une liste illisible, ou un `gh`
qui échoue ou dépasse son délai, vaut refus. Sans la clé, le garde ne refuse rien à ce titre. La
consigne de `forge:qc` reste (s'arrêter avant la fusion) : le garde est le filet, la consigne évite
le refus. Essayé sur Linux seulement, par les tests ; pas encore sur un vrai poste Windows.

## Compléter ou remplacer, sans éditer le plugin

- **Un complément** est un fichier du projet : ses skills de domaine, son arbitre du métier, ses
  propres hooks restent dans son `.claude/` et coexistent avec le plugin, dont les noms préfixés ne
  les heurtent pas. Ses hooks de `.claude/settings.json` tournent à côté de ceux du plugin.
- **Un remplacement** est un skill ou un agent du projet sous un autre nom, que la configuration
  désigne.
- **Le cache du plugin ne s'édite jamais** : il est réécrit à chaque version. Un écart qui vaut
  pour tous les projets se propose en PR à ce dépôt.

Ce qui reste forcément dans chaque projet, parce que ce n'est pas Claude Code qui le lit : les
gardes de CI, le modèle de PR, les hooks git. La CI ne charge aucun plugin.

## Gestes humains

Ce qu'aucun agent ne fait à la place d'un humain :

1. Créer le dépôt `ikoro-labs/forge` (fait), et choisir ses contributeurs, seuls comptes à
   y avoir le droit d'écriture.
2. Sur chaque poste (bureau, PC personnel), dans chaque projet : approuver le dossier et lancer
   les deux commandes de l'étape 3 d'**Installer dans un projet**. Un utilisateur sans droit
   d'écriture installe le plugin et monte de version de la même façon.
3. À chaque montée d'épingle, sur chaque poste et dans chaque projet : les deux commandes de
   **Monter de version**.
4. Une fois `forge` 1.1.0 installé dans chaque projet du poste qui fait des passations : retirer de
   `~/.claude/settings.json` les entrées `UserPromptSubmit` et `PostToolUse` qui lancent la copie
   `~/.claude/hooks/handoff_trigger.py`, puis cette copie et ses deux voisins
   (`handoff_header.py`, `handoff_relay.sh`) ; garder `~/.claude/hooks/state/`, qui porte les
   passations et les compteurs. Remplacer la règle de permission qui autorise
   `bash ~/.claude/hooks/handoff_relay.sh` par la même règle sur le relais du plugin
   (`~/.claude/plugins/cache/ikoro-labs/forge/<version>/hooks/handoff_relay.sh`). Jusque-là, le
   hook du plugin se tait et la copie reste celle qui tourne.
5. À la montée vers `forge` 1.2.0 : remplacer la règle de permission qui autorise
   `bash ~/.claude/plugins/cache/ikoro-labs/forge/<version>/hooks/handoff_relay.sh` par
   `uv run --no-project --quiet python ~/.claude/plugins/cache/ikoro-labs/forge/<version>/hooks/handoff_relay.py`.
   Le relais bash n'existe plus.
6. Dans ce dépôt, une fois par poste qui y développe : les deux commandes de l'étape 3
   d'**Installer dans un projet**, depuis sa racine.
   `main` est protégée par un ruleset qui exige les checks de la clé `required-contexts` de
   `docs/agents/usine.md` (Settings, Rules, Rulesets, ciblant la branche par défaut). Sans
   protection, seul `guard_git` retient une fusion dont un check n'est pas vert. `forge:qc-gate`
   lit la protection dans les rulesets comme dans l'ancienne protection de branche.

## Limites connues

- **Une source par marketplace et par poste** : la marketplace `ikoro-labs` n'est connue qu'une
  fois par poste, à la source du dernier projet qui l'a déclarée (`claude plugin marketplace add`).
  L'ouverture d'une session ne la remet pas sur le `ref` du projet. Deux projets d'un même poste
  peuvent tourner sur deux versions, car chaque installation garde son propre dossier de cache ;
  mais `install` et `update` prennent la source du poste. D'où la redéclaration de l'épingle avant
  chacun d'eux.
- **Dépendance à GitHub** : un poste neuf ou une nouvelle version ne s'installent pas si GitHub
  est injoignable.
- **Noms préfixés** : `forge:coder`, `/forge:qc`. Les commandes tapées, les tests et les mesures
  d'un projet qui lisent un nom d'agent doivent suivre à la migration.
- **Frontmatter des agents** : un agent de plugin ignore `hooks`, `permissionMode`, `mcpServers` et
  `initialPrompt`. Les gardes des agents sont donc des hooks globaux du plugin, filtrés sur
  `agent_type` (`forge:coder`, `forge:qc-gate`...) ; un filtre faux ne s'appliquerait à personne,
  en silence, d'où les tests de `tests/`.
- **Aucun `CLAUDE.md`** n'est chargé depuis un plugin : la constitution reste celle du projet.

### Éprouvé sur un poste (Claude Code 2.1.303, 2026-10-19)

Les quatre points restés à confirmer, essayés dans des projets jetables :

- **Deux projets, deux `ref`** : possible, avec la limite ci-dessus. Un projet épinglé sur 1.0.0,
  un autre sur 1.0.1 : chacun a gardé sa version, jusqu'à un `update` lancé dans le premier, qui
  l'a fait passer en 1.0.1 ; redéclarer son épingle puis relancer `update` l'a ramené en 1.0.0.
- **`qc` du projet et `forge:qc`** : `/qc` lance le skill du projet ; `forge:qc` reste joignable
  sous son nom préfixé, et les deux figurent dans la liste des skills. Pendant la transition, les
  commandes qui doivent viser le plugin écrivent `/forge:qc`.
- **`guard_coder` dans un worktree** : un `forge:coder` lancé avec `isolation: worktree` porte bien
  `agent_type: "forge:coder"` dans l'événement du hook. Rejoué sur `guard_coder`, cet événement
  est refusé pour `gh pr merge` comme pour le skill `forge:qc`, et le même événement avec un autre
  `agent_type` passe.

  Avec le ticket #65, `guard_coder` lit aussi le champ `cwd` de l'événement : il refuse au
  coder une écriture (`Edit`, `Write`, `MultiEdit`, `NotebookEdit`) ou une commande git hors de son
  worktree, tout `cwd` qui n'est pas un worktree lié (coder lancé sans isolation), `git push` avec
  `-u`, `--set-upstream`, `-f` ou `--force`, et `git config` en écriture. Ce comportement n'a été
  essayé que par les tests, sur un dépôt temporaire et un worktree lié réels, pas encore dans une
  vraie session ; le champ `cwd` d'un coder isolé reste à confirmer sur un poste.
- **Marketplace injoignable au démarrage** : avec git coupé vers GitHub, la session charge la
  version en cache, skills et agents compris.
