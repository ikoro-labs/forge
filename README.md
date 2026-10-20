# forge

La partie générique de l'usine agentique d'ikoro-labs, en plugin Claude Code privé : le coder, la
revue en deux temps, les décideurs délégués, la chaîne des features de l'idée à la livraison, et
les hooks qui gardent git, les rôles et la pause, et la passation drainée d'une session à sa
limite de contexte. Les projets (Projet A, Projet B) le consomment à
une version épinglée et gardent dans leur dépôt tout ce qui leur est propre. La décision est
l'ADR-0129 de Projet B.

Ce dépôt est une marketplace (`ikoro-labs`) qui sert un seul plugin (`forge`) : `forge@ikoro-labs`.
Ses noms sont préfixés : `/forge:qc` pour un skill, `forge:coder` pour un agent.

```text
.claude-plugin/marketplace.json   la marketplace ikoro-labs, un plugin à source relative
plugins/forge/                    le plugin
  .claude-plugin/plugin.json      son manifeste, seul endroit qui porte sa version
  agents/                         coder, qc-gate, qc-conf, staff-engineer, product-owner
  skills/                         qc, feature-build, feature-*, codebase-design, domain-modeling,
                                  improve-codebase-architecture, audit-jetons
  hooks/                          hooks.json, les gardes et la passation drainée, en Python de la
                                  bibliothèque standard, sous Linux comme sous Windows
  scripts/parse_output.py         lecture du RESULT du coder et du verdict du juge
  scripts/token_audit.py          les jetons de chaque rôle, lus dans les journaux de Claude Code
  templates/                      usine.md, adr.md, features/
tests/                            tests des hooks, du parseur et du contenu
CHANGELOG.md                      une entrée par version publiée
CLAUDE.md, .claude/               l'usine de ce dépôt : son épingle, ses règles
docs/agents/usine.md              sa configuration
.github/                          la CI (tests sous Linux et Windows, validation) et le modèle de PR
```

Ce qui est entré dans chaque version, et ce qui en est resté dehors avec sa raison : `CHANGELOG.md`.

## Prérequis sur le poste

- Claude Code.
- Un accès git au dépôt privé `ikoro-labs/forge` : une clé SSH, ou `gh auth login` pour HTTPS.
  Claude Code lit une marketplace privée avec les identifiants git du poste.
- [uv](https://docs.astral.sh/uv/) : chaque hook se lance par `uv run --no-project --quiet python`.
  Sans uv, `guard_coder` et `guard_readonly` refusent chaque appel qu'ils filtrent (leur échec
  vaut refus), et les autres gardes ne s'appliquent pas.
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
           "ref": "forge--v1.2.0"
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
   claude plugin marketplace add ikoro-labs/forge@forge--v1.2.0 --scope project
   claude plugin install forge@ikoro-labs --scope project
   ```

   La première ligne remet la marketplace du poste sur le `ref` du projet : un poste ne connaît
   qu'une source par marketplace, celle du dernier projet qui l'a déclarée (voir **Limites
   connues**). Elle réécrit aussi le `.claude/settings.json` du projet dans sa propre forme
   (indentation de deux espaces, `extraKnownMarketplaces` en dernière clé), sans toucher aux autres
   clés : sous la forme de l'étape 1, `git diff` reste vide. S'il montre autre chose que de la mise
   en forme, l'épingle tapée n'est pas celle du projet.

4. **Configurer** : copier `plugins/forge/templates/usine.md` vers `docs/agents/usine.md` dans le
   projet, puis, pour chaque clé, mettre la vraie valeur ou supprimer la ligne (voir plus bas).

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

## La passation drainée

Une session passe la main à une nouvelle session quand son contexte atteint le seuil
(ikoro-labs/forge#3). Fermer une session tue ses sous-agents : la passation est donc un arrêt qui
draine.

- **Le hook** `handoff_trigger.py` (`UserPromptSubmit`, `PostToolUse`) lit le contexte du fil
  principal dans la transcription. Au seuil, il dit à la session de ne plus rien lancer, de laisser
  finir ses agents puis d'écrire la passation et de lancer le relais. Au plafond dur (seuil plus
  35 k jetons, ou 45 minutes après le premier avis), il fait lister les agents encore vivants sous
  `sauvetage` et forcer le relais. Un sous-agent n'est jamais averti.
- **La passation** est un fichier `~/.claude/hooks/state/handoffs/<projet>/<date>-r<N>.md` (ou
  `<CLAUDE_HANDOFF_DIR>/<projet>/<date>-r<N>.md`), `<projet>` étant le nom de la copie principale
  du dépôt, même pour une session lancée dans un worktree, hors du cache du plugin, qui commence par un front matter de onze clés (`projet`, `feature`,
  `passage_depart`, `jetons_agents`, `en_vol`, `file_revue`, `sauvetage`, `successeur`,
  `hooks_version`, `seuil`, `contexte_passation`). `handoff_header.py` le valide ; son corps est le
  prompt de reprise. Le skill `handoff` de l'utilisateur (`~/.claude/skills/handoff/`) est suivi
  s'il existe.
- **Le relais** `handoff_relay.py`, lancé par la session depuis le dossier du projet
  (`uv run --no-project --quiet python <hooks>/handoff_relay.py <passation>`), refuse
  (code 5) tant qu'un agent de la session est vivant ou que `en_vol` n'est pas vide, et n'admet
  `--force` qu'avec `sauvetage` non vide. Il lance le successeur par `claude --bg`, écrit son
  identifiant et son seuil dans l'en-tête, puis arrête et supprime la session appelante. Le
  successeur vérifie d'abord qu'il est bien le successeur désigné
  (`handoff_header.py successor-ok`).
- **Le seuil** est `CLAUDE_SESSION_TOKEN_LIMIT`, 150 000 par défaut. Seul le relais le relève, à
  400 000 pour un successeur dont la passation porte une feature, c'est-à-dire un identifiant
  `F-NNNN` dans `feature` (du texte comme « aucune » n'en est pas une). Aucun `settings.json` ne
  doit le fixer.

| Variable | Défaut | Effet |
| --- | --- | --- |
| `CLAUDE_SESSION_TOKEN_LIMIT` | 150000 | seuil de drainage, posé par le relais seulement |
| `CLAUDE_HANDOFF_DRAIN_MINUTES` | 45 | minutes de drainage avant le plafond dur |
| `CLAUDE_HANDOFF_DIR` | `~/.claude/hooks/state/handoffs` | dossier des passations, `~` et variables développés (`%LOCALAPPDATA%\forge\handoffs`) ; les marqueurs et compteurs restent dans `~/.claude/hooks/state` |
| `CLAUDE_HANDOFF_RELAY_MAX` | 5 | relais par projet et par jour (code 3 au-delà) |
| `CLAUDE_HANDOFF_CLOSE_DELAY` | 45 | secondes avant la fermeture de la session appelante, 0 la garde ouverte |
| `CLAUDE_HANDOFF_TERMINAL` | aucune | commande de terminal (`ghostty -e`, `gnome-terminal --`, `wt.exe` sous Windows) où ouvrir `claude attach <id>` ; sans elle, aucune fenêtre |
| `CLAUDE_HANDOFF_CLOSE_DRY_RUN` | aucune | affiche le lancement et la fermeture sans rien lancer, compteur et passation intacts ; `0`, `false`, `no`, `off` ou vide le laissent coupé |

Le relais tourne sous Linux et sous Windows. Les questions de processus (un pid vit-il, quand
est-il né, qui est son parent) passent par `/proc` sous Linux et par l'API Win32 (`ctypes`) sous
Windows ; ailleurs, un processus compte pour vivant, le côté prudent. Différences sous Windows :

- Claude Code y verrouille le worktree d'un agent sans heure de départ (`claude agent <nom>
  (pid N)`) : un pid vivant y vaut détenteur du verrou, sans garde contre la réutilisation d'un pid.
- La session interactive fermée par le relais reçoit `/exit` dans sa console, comme si on le
  tapait : Claude Code se ferme normalement et rend le terminal propre ; sa fenêtre reste ouverte
  sur l'invite du shell qui l'a lancée. Si elle vit encore 15 secondes plus tard, elle est tuée
  (`taskkill /F`) et le relais coupe lui-même le suivi de la souris dans la console : tuée sans
  cela, elle laissait chaque mouvement de souris s'écrire dans le shell. Une session de fond est
  arrêtée puis supprimée (`claude stop`, `claude rm`) comme sous Linux, ses fenêtres
  `claude attach` fermées d'abord.
- Une session interactive porte elle aussi `CLAUDE_CODE_CHILD_SESSION=1` : le relais la reconnaît au
  registre de Claude Code (`~/.claude/sessions/<pid>.json`, `"kind": "interactive"`), sous Linux
  comme sous Windows.

La session écrit la passation avec ses propres outils de fichier. Une politique gérée peut les
interdire sous tout dossier `.claude` : le hook se déclenche, mais l'écriture est refusée et le
relais répond `handoff document not found`. Sur un tel poste, `CLAUDE_HANDOFF_DIR` place les
passations ailleurs. Elle se pose dans l'environnement du poste ou dans le bloc `env` du
`~/.claude/settings.json`, pour que le hook, le relais et le successeur la voient :

```json
{ "env": { "CLAUDE_HANDOFF_DIR": "%LOCALAPPDATA%\\forge\\handoffs" } }
```

La passation ne vaut que dans les projets où le plugin est activé ; une copie de ces scripts dans
`~/.claude/hooks` couvrait tous les projets du poste. Tant que `~/.claude/settings.json` déclare
encore une telle copie, le hook du plugin se tait.

## Configurer : `docs/agents/usine.md`

Le seul fichier où un projet décrit son usine au plugin : qui accepte, la matrice de décision,
l'arbitre du métier, les commandes d'installation et de rejeu de la CI, les checks obligatoires, la
grille de revue, les chemins protégés, les tolérances des hooks. Le gabarit,
`plugins/forge/templates/usine.md`, documente chaque clé.

Une clé absente ne prend jamais de valeur par défaut : l'étape qui la lit se rend « sans objet (clé
`<nom>` absente) », jamais `PASS`. La revue d'un projet vaut donc ce que sa configuration déclare :
sans ses commandes de porte ni sa grille, `/forge:qc` rend des sondes « sans objet », plus faibles
qu'une revue configurée, et une clé qui pointe un chemin disparu donne un `NOT RUN` à chaque PR
jusqu'à sa correction.

## Les modèles des rôles

Chaque agent fixe dans son front matter un **niveau** de modèle, jamais l'identifiant d'un modèle :
le moins cher qui fait le travail, le plus fort là seulement où une erreur coûte.

| Agent | Niveau | Pourquoi |
| --- | --- | --- |
| `forge:qc-gate` | `haiku` | Il rejoue des commandes et recopie leurs mesures, sans avis. |
| `forge:coder` | `sonnet` | Le plus gros consommateur ; un modèle moyen code un ticket bien découpé. |
| `forge:qc-conf` | `opus` | Le garde-fou de la qualité ; il lit surtout le diff, sa tâche reste courte. Un autre niveau que le coder rend moins probable qu'une même erreur échappe aux deux. |
| `forge:staff-engineer`, `forge:product-owner` | `opus` | Appelés rarement, et leur décision engage la suite. |

La session principale, celle qui lance les skills, n'est pas réglée par le plugin : c'est le
modèle choisi par `/model`, souvent le plus gros poste de consommation.

**L'effort de réflexion.** Avant de répondre, un modèle réfléchit, et cette réflexion se paie
comme du texte produit. Chaque agent fixe donc aussi son `effort` : `low` pour `forge:qc-gate`,
qui n'a rien à peser, `high` pour `forge:staff-engineer`, qui tranche les questions techniques
difficiles, `medium` pour les autres. `CLAUDE_CODE_EFFORT_LEVEL`, posé sur un poste, l'emporte sur
ce réglage. `forge:qc-gate` démarre aussi sans les `CLAUDE.md` du projet (`omitClaudeMd`) : il lit
ses portes dans `docs/agents/usine.md`. Ces deux champs sont ceux que la documentation de Claude
Code donne pour un agent ; leur gain n'est pas mesuré, et ils n'ont pas encore été essayés sur un
vrai poste.

**Brancher un autre fournisseur.** Les quatre niveaux (`fable`, `opus`, `sonnet`, `haiku`) sont
des alias que chaque poste fait pointer où il veut, sans toucher au plugin :

- `ANTHROPIC_DEFAULT_FABLE_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`,
  `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL` : l'identifiant du modèle
  derrière chaque niveau ;
- `ANTHROPIC_BASE_URL` : l'adresse où Claude Code envoie ses requêtes, par exemple une passerelle
  compatible avec l'API Anthropic (LiteLLM, ou une autre) qui les relaie vers GPT, Grok ou un modèle
  local.

Ces variables se posent dans l'environnement du poste ou dans son `~/.claude/settings.json`, jamais
par le plugin. Elles valent pour tout le poste : deux rôles d'un même niveau ont le même modèle.
Sans elles, chaque niveau reste le modèle Claude du même nom.

Un appel qui fixe `model` l'emporte sur le front matter de l'agent.

Ces variables et la forme du champ `model` (un alias ou un identifiant) ont été lues dans Claude
Code 2.1.305. Une usine servie par un autre fournisseur, à travers une passerelle, n'a pas encore
été essayée : l'usage des outils et le cache de prompt peuvent s'y comporter autrement.

## Mesurer les jetons de chaque rôle

`/forge:audit-jetons` compte les jetons que chaque rôle a dépensés sur le projet, par modèle et par
effort, et compare un avant et un après :

```text
/forge:audit-jetons --coupure 2026-10-20T21:52
```

Il lit les journaux que Claude Code écrit déjà sur le poste (`~/.claude/projects/`, ou le dossier
de `CLAUDE_CONFIG_DIR`), ne garde que les réponses dont le dossier de travail est le projet ou l'un
de ses worktrees, et compte une seule fois une réponse écrite sur plusieurs lignes. `--depuis` et
`--jusqua` bornent la période ; `--coupure` la coupe en deux, par exemple à l'heure de fusion de la
PR qui a changé un modèle ou un effort. Une date sans zone est en UTC, comme les heures de GitHub.
La comparaison se fait en jetons par lancement d'agent, puisque le volume de travail change d'une
période à l'autre. Le script ne donne aucun prix : les quatre sortes de jetons (entrée, écriture
de cache, lecture de cache, sortie) n'ont pas le même, et chaque fournisseur a le sien.

Une limite des journaux eux-mêmes : Claude Code note la plupart des réponses des sous-agents avant
leur fin, avec la sortie connue à ce moment, bien en dessous de la vraie. Le rapport compte ces
réponses dans sa colonne « Sortie partielle » ; leur sortie est sous-comptée, l'entrée et le cache
ne le sont pas. Le format des journaux a été lu dans Claude Code 2.1.302 à 2.1.305 sous Linux ; il
n'est pas documenté et peut changer. Le skill n'a pas été essayé sous Windows.

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

## Contribuer et publier

- **Seuls les contributeurs écrivent** : les comptes qui ont le droit d'écriture sur ce dépôt. Un
  projet consommateur n'y écrit pas ; un besoin né dans un projet devient un ticket ou une PR d'un
  contributeur.
- **L'usine développe l'usine** : ce dépôt installe `forge` comme un projet consommateur, épinglé
  dans son `.claude/settings.json`, configuré par son `docs/agents/usine.md`. La session qui tourne
  charge la version épinglée depuis le cache ; ce qu'elle modifie, c'est `plugins/forge/`, qui
  n'agit sur elle qu'une fois publié et l'épingle montée par une PR. Les règles du dépôt sont dans
  `CLAUDE.md` et `.claude/rules/`.
- **La session forge publie** : elle tient ce `CHANGELOG.md` et pose les tags.
- Le contenu reste générique : il cite les clés de `docs/agents/usine.md`, jamais un numéro d'ADR,
  un nom de personne ou un chemin propre à un projet.

Publier une version :

1. Changer `version` dans `plugins/forge/.claude-plugin/plugin.json`, et nulle part ailleurs
   (jamais dans `marketplace.json`).
2. Ouvrir l'entrée correspondante en tête de `CHANGELOG.md`.
3. Vérifier :

   ```sh
   uv run --no-project --quiet python -m unittest discover -s tests
   claude plugin validate .
   claude plugin validate plugins/forge
   ```

4. Fusionner sur `main`, puis poser et pousser le tag annoté `forge--v<X.Y.Z>`, deux tirets : c'est
   la forme que Claude Code lit. Les anciens tags `forge-v<X.Y.Z>` de Projet A ne changent pas.

## Gestes humains

Ce qu'aucun agent ne fait à la place d'un humain :

1. Créer le dépôt privé `ikoro-labs/forge` (fait), et choisir ses contributeurs, seuls comptes à
   y avoir le droit d'écriture.
2. Sur chaque poste (bureau, PC personnel) : un accès git au dépôt privé (clé SSH, ou
   `gh auth login`) ; puis, dans chaque projet, approuver le dossier et lancer les deux commandes
   de l'étape 3 d'**Installer dans un projet**. Un contributeur installe le plugin : un accès en lecture
   lui suffit, pour installer comme pour monter de version.
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
   Puis, si l'offre GitHub du dépôt le permet, protéger `main` avec les checks de la clé
   `required-contexts` de `docs/agents/usine.md`. Sans protection, seul `guard_git` retient une
   fusion dont un check n'est pas vert.

## Limites connues

- **Une source par marketplace et par poste** : la marketplace `ikoro-labs` n'est connue qu'une
  fois par poste, à la source du dernier projet qui l'a déclarée (`claude plugin marketplace add`).
  L'ouverture d'une session ne la remet pas sur le `ref` du projet. Deux projets d'un même poste
  peuvent tourner sur deux versions, car chaque installation garde son propre dossier de cache ;
  mais `install` et `update` prennent la source du poste. D'où la redéclaration de l'épingle avant
  chacun d'eux.
- **Dépendance à GitHub** : un poste neuf ou une nouvelle version ne s'installent pas si GitHub ou
  les identifiants git du poste font défaut.
- **Noms préfixés** : `forge:coder`, `/forge:qc`. Les commandes tapées, les tests et les mesures
  d'un projet qui lisent un nom d'agent doivent suivre à la migration.
- **Frontmatter des agents** : un agent de plugin ignore `hooks`, `permissionMode`, `mcpServers` et
  `initialPrompt`. Les gardes des agents sont donc des hooks globaux du plugin, filtrés sur
  `agent_type` (`forge:coder`, `forge:qc-gate`...) ; un filtre faux ne s'appliquerait à personne,
  en silence, d'où les tests de `tests/`.
- **Aucun `CLAUDE.md`** n'est chargé depuis un plugin : la constitution reste celle du projet.

### Éprouvé sur un poste (Claude Code 2.1.303, 2026-10-19)

Les quatre points que l'ADR-0129 laissait à confirmer, essayés dans des projets jetables :

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
- **Marketplace injoignable au démarrage** : avec git coupé vers GitHub, la session charge la
  version en cache, skills et agents compris.

## Licence

Privé. Trois skills adaptent mattpocock/skills sous licence MIT :
`plugins/forge/THIRD_PARTY_NOTICES.md`.
