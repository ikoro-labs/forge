# Journal des versions

Une entrée par version publiée du plugin `forge`, la plus récente en haut. Chaque version porte le
tag `forge--v<X.Y.Z>` sur ce dépôt ; sa version est celle de `plugins/forge/.claude-plugin/plugin.json`,
et nulle part ailleurs. Les tags `forge-v<X.Y.Z>` (un seul tiret) appartiennent à l'historique de
Projet A et ne sont pas repris ici.

## [1.4.0] - 2026-10-21

Une seule session par dépôt (ikoro-labs/forge#4, en partie) : une session sait quelles autres
sessions vivent sur son dépôt, le relais de la passation refuse d'en lancer une à côté, et la
session de fond cède à la session interactive de l'humain. Le juge rend un verdict lisible pour une
PR sans ticket ou sans critère livré (#24, #28, #29). Le plugin gagne une icône (#26) et une
licence MIT (#31).

### Hooks

- `handoff_header.py sessions <repo>`, nouveau (#4) : lit le registre que Claude Code tient de ses
  sessions (`~/.claude/sessions/*.json`), garde les processus vivants (sous Linux, `procStart` doit
  être l'heure de départ du processus), les sessions dont le dossier se résout sur la même copie
  principale (`.git` puis `commondir`, worktrees compris), et laisse de côté la session appelante
  (`CLAUDE_PID`, le processus qui lance la commande, et leurs ancêtres). Il imprime
  `pid kind name status cwd` par autre session et sort en 0 si aucune ne vit, en 6 sinon ; une
  entrée illisible compte pour vivante. Sous Windows, `procStart` n'est pas comparé : un pid vivant
  y vaut session vivante. Éprouvé sous Linux sur le registre réel d'un poste (Claude Code 2.1.306,
  registre écrit par 2.1.305) ; sous Windows, seulement par la suite en CI.
- `handoff_relay.py` refuse en code 6 quand une autre session du dépôt vit : il imprime les
  sessions trouvées sur stderr, ne lance aucun successeur, ne touche pas au compteur du jour et ne
  ferme pas la session appelante. Le code 5 passe avant lui, et un registre illisible vaut refus en
  6. Le `README.md` gagne la table des codes du relais (0 à 6).
- Le successeur d'une passation ne compte plus la session qui la lui passe : le relais, comme
  `handoff_header.py set-successor`, écrit `auteur` (`CLAUDE_CODE_SESSION_ID`) à côté de
  `successeur`, et `sessions` laisse de côté l'`auteur` d'une passation du projet qui nomme la
  session appelante successeur, encore vivant pendant `CLAUDE_HANDOFF_CLOSE_DELAY`. `auteur`
  n'entre pas dans les clés requises : une passation écrite avant 1.4.0 reste valide, mais n'exclut
  personne.
- La session de fond cède à la session interactive de l'humain. `handoff_header.py self` imprime
  le type que le registre note pour la session appelante et son identifiant (`?` quand il manque).
  `handoff_trigger.py yield <identifiant>`, lancé par la session de fond, imprime sa conduite : ne
  plus rien lancer, laisser finir ses agents sous `CLAUDE_HANDOFF_DRAIN_MINUTES`, écrire sa
  passation au même format qu'au seuil, la donner à la session interactive par `set-successor`,
  lui envoyer le chemin par `SendMessage`, puis lancer `handoff_relay.py --yield [--force]
  <passation>`. Celui-ci fait les contrôles d'agents du relais (code 5) et sa fermeture
  (`claude stop` puis `claude rm` après `CLAUDE_HANDOFF_CLOSE_DELAY`), sans lancer de session ni
  passer par le code 6 ; il refuse en code 1 une session interactive ou un `CLAUDE_PID` inconnu, en
  code 2 une passation sans `successeur`. Sans argument, `handoff_trigger.py` reste le hook qui ne
  bloque jamais. Seul le type `bg` cède ; un type inconnu fait s'arrêter la nouvelle session.
  `self`, `yield`, l'exclusion de l'`auteur` et `--yield` n'ont tourné que dans la suite, sous
  Linux, `--yield` contre un faux `claude` : qu'un vrai `claude rm` retire l'entrée du registre n'a
  été vérifié sur aucun poste, et le parcours interactif entier n'a été éprouvé sur aucun système.
  Les types du registre ont été lus sous Linux, sur trois entrées réelles toutes `bg`, et dans le
  code de Claude Code 2.1.306, qui écrit `interactive` par défaut.
- Le `README.md` énonce la règle dans une section **Règles communes** (une session par dépôt, le
  premier geste, qui cède à qui), et décrit `--yield` dans **La passation drainée**.

### Agents

- `qc-conf` : une PR qui ne lie aucun ticket (une montée Dependabot, une montée d'épingle) a une
  seule ligne `SPEC: none (<raison>)`, la raison disant contre quoi elle a été jugée, sans
  s'accrocher à une PR ou un ticket qu'elle ne cite pas (#24). Une PR qui cite des tickets sans en
  livrer aucun critère, comme une PR de publication, se juge contre les règles du projet qui
  décrivent ce type de PR (clés `domain-rules`, `git-rules`) et rend
  `SPEC: none (<règles>: <n> critères couverts, <n> partiels, <n> absents)` (#28). Aucun juge n'a
  encore suivi ces consignes sur une vraie PR.

### Skills

- `/forge:qc`, `scripts/parse_output.py verdict` : il admet la ligne unique `SPEC: none (<raison>)`
  et refuse une raison vide ou un `none` mêlé à des lignes `#<ticket>` (#24). Chacun de ses trois
  refus sur `SPEC:` dit ce qui est faux dans la ligne et nomme les deux formes admises, pour que la
  relance du juge suffise (#29). Éprouvé par la suite de tests, sous Linux ; aucun `/forge:qc` n'a
  encore tourné avec ce parseur.
- `/forge:feature-build`, étape 0, point 5 : « Un seul passage par feature » devient « Une seule
  session par projet ». La session lance `handoff_header.py sessions .`, puis `ListAgents`. Une
  session interactive face à des sessions toutes `bg` leur demande de céder (`yield`) et reprend
  depuis leur passation (`successor-ok`, puis le sauvetage) ; dans tout autre cas, elle envoie sa
  demande à la session en place par `SendMessage` et s'arrête ; une session de fond à qui l'on
  demande de céder draine puis s'arrête (#4). Pas encore éprouvé dans un vrai passage.

### Tests

- `tests/test_handoff.py` : `sessions` sur un registre factice, `HOME` et `USERPROFILE` isolés (pid
  vivant, pid mort, worktree, autre dépôt, entrée illisible, session appelante, et `procStart`
  différent, sous Linux seul par `skipUnless`) ; le code 6 du relais ; `auteur`, l'exclusion du
  prédécesseur et `CLAUDE_HANDOFF_DIR` ; `self`, `yield` et `--yield`, dont une troisième session
  qui ne voit plus la session de fond qui a cédé.
- `tests/test_parse_output.py` : les formes de `SPEC: none` et les deux formes nommées par chaque
  refus.
- `tests/test_plugin_content.py` : les consignes de `qc-conf`, le point 5 de `feature-build`, la
  règle du `README.md`, aucun projet ni aucune personne nommés sous `plugins/forge/`, l'icône (un
  PNG carré de 512 à 2048 px, de moins de 2 Mo) et la licence (`LICENSE` MIT à la racine,
  `"license": "MIT"` dans `plugin.json`).
- La suite compte 158 tests sous Linux, dont 3 sautés, propres à Windows. Elle tourne en CI sous
  Linux et sous Windows.

### Gestes humains

- Aucun geste n'est obligatoire à la montée, en dehors des deux commandes de **Monter de version**.
- Monter l'épingle hors d'un `/forge:feature-build` actif, comme le veut déjà **Monter de
  version**, et plus largement hors d'une chaîne de relais en cours : une passation écrite par
  1.3.0 n'a pas d'`auteur`, et son successeur en 1.4.0 s'arrêterait derrière son prédécesseur
  encore vivant.
- L'humain qui ouvre une session interactive sur un dépôt où une session de fond agit la voit
  drainer puis s'arrêter, au plus `CLAUDE_HANDOFF_DRAIN_MINUTES` minutes. Pour la suivre sans
  l'arrêter : `claude attach <id>`, l'identifiant étant celui que donne `claude agents`.

### Restés dehors

- Le hook `SessionStart` qui nomme, au démarrage d'une session, les autres sessions vivantes du
  dépôt (PR #38, critère 5 de #4) : ACCEPT, en attente d'une fusion humaine, car il touche
  `plugins/forge/hooks/hooks.json`, chemin protégé. #4 n'est donc livré qu'en partie : critères 1
  à 4, 6 et 7.
- Ne plus activer le cache de uv dans la CI (PR #34, #32) : ACCEPT, en attente d'une fusion
  humaine, car elle touche `.github/`, chemin protégé. Rien n'en change pour un projet consommateur.

## [1.3.0] - 2026-10-21

Ce que coûte chaque rôle : un niveau de modèle et un effort de réflexion par agent
(ikoro-labs/forge#10, #12), un audit des jetons pour en mesurer l'effet (#14), et la sortie d'une
suite de tests qui passe raccourcie (#19). Avec trois correctifs : la fermeture d'une session
Windows depuis un job (#3), le dossier de la passation depuis un worktree, et la protection d'une
branche lue dans ses rulesets (#17).

### Agents

- Chaque agent fixe dans son front matter un niveau de modèle et un effort de réflexion, le moins
  cher qui fait le travail : `qc-gate` en `haiku`, effort `low` ; `coder` en `sonnet`, effort
  `medium` ; `qc-conf` et `product-owner` en `opus`, effort `medium` ; `staff-engineer` en `opus`,
  effort `high`. En 1.2.0, `qc-gate`, `coder` et `qc-conf` prenaient le modèle de la session,
  `staff-engineer` et `product-owner` le niveau `fable`. Un niveau est un alias : chaque poste le
  fait pointer vers le modèle et le fournisseur de son choix (`ANTHROPIC_DEFAULT_<NIVEAU>_MODEL`,
  `ANTHROPIC_BASE_URL` vers une passerelle), sans toucher au plugin. `CLAUDE_CODE_EFFORT_LEVEL`,
  posé sur un poste, l'emporte sur l'effort. Le gain n'est pas mesuré, et aucune usine servie par
  un autre fournisseur n'a été essayée.
- `qc-gate` démarre sans `CLAUDE.md` (`omitClaudeMd: true`, Claude Code 2.1.271 et plus) et lit ses
  portes dans `docs/agents/usine.md` par Bash. Le champ retire aussi le `~/.claude/CLAUDE.md` du
  poste et le `CLAUDE.local.md`.
- `qc-gate`, sonde « Contextes obligatoires » : elle prend l'union des checks exigés par les
  rulesets actifs de la base (`rules/branches/<base>`) et par l'ancienne protection de branche.
  Elle ne lisait que la seconde, qui rend `contexts: []` pour une branche que seul un ruleset
  protège : chaque revue sur une telle base rendait un `FAIL` à tort. Les deux lectures ont été
  lancées à la main sur ce dépôt ; la sonde modifiée n'a pas encore tourné dans une vraie revue.
- `qc-gate`, sondes des tests sautés : sur une sortie raccourcie par `trim_output.py`, elle relève
  les sauts dans le journal que nomme la première ligne, puisque l'agent ne reçoit plus le milieu
  de la sortie.

### Hooks

- `trim_output.py` (`PostToolUse`, sur `Bash`), nouveau : pour une commande que nomme la clé
  `trimmed-command` de `docs/agents/usine.md`, une sortie réussie de plus de 60 lignes est écrite
  en entier dans `~/.claude/hooks/state/trimmed/` (les 20 journaux les plus récents gardés, jamais
  celui qui vient d'être écrit), et l'agent n'en reçoit que les 20 dernières lignes de chaque flux,
  avec le chemin du journal. Sans la clé, rien ne change. Une commande en échec arrive entière, à
  condition que son code de sortie le dise : derrière un tube ou suivie de `; echo fini`, une suite
  en échec sort à 0 et se raccourcit. Le hook observe : toute erreur sort à 0, la sortie d'origine
  intacte. Éprouvé avec Claude Code 2.1.305 sous Linux, dans une session `claude -p --plugin-dir` ;
  pas encore sous Windows ni dans une session interactive. Une commande lancée par l'outil
  `PowerShell` n'est pas raccourcie.
- `handoff_trigger.py` : la passation se range sous le nom de la copie principale du dépôt, lu dans
  le fichier `.git` du worktree et son `commondir`, sans lancer git. Depuis un worktree, elle se
  rangeait sous le nom du worktree. Un sous-module garde son propre nom. Les passations déjà mal
  rangées restent où elles sont.
- `handoff_relay.py` : sous Windows, une commande que le relais lance et attend reste dans le job de
  la session ; seul le lancement du successeur demande encore à en sortir, avec son repli. Dans un
  job qui interdit d'en sortir (celui d'un runner GitHub, ou celui d'une session dont le lancement
  a dû se replier), `CreateProcess` levait `OSError` : `--exit-console` mourait au `taskkill` d'une
  session sourde à `/exit`, et `--close` sautait chaque commande de son plan sans fermer la
  session. Éprouvé sur les runners Windows de GitHub seulement.

### Skills

- `/forge:audit-jetons` et son script `scripts/token_audit.py`, nouveaux : les jetons dépensés par
  chaque rôle sur un projet, par modèle et par effort, lus dans les journaux que Claude Code écrit
  déjà (`~/.claude/projects/`, ou `CLAUDE_CONFIG_DIR`), worktrees compris. `--depuis` et `--jusqua`
  bornent la période, `--coupure` compare un avant et un après en jetons par lancement d'agent.
  Aucun prix. Claude Code note la plupart des réponses de sous-agents avant leur fin : leur sortie
  est sous-comptée, et le rapport les compte dans une colonne « Sortie partielle ». Le format des
  journaux n'est pas documenté ; il a été lu dans Claude Code 2.1.302 à 2.1.305. Seul le script a
  tourné sur un vrai poste, sous Linux ; le skill n'a été lancé dans aucune session.

### Tests

- `tests/test_plugin_content.py` : le niveau et l'effort de chaque agent, `omitClaudeMd` sur
  `qc-gate` seul, et la sonde de protection qui lit les rulesets.
- `tests/test_trim_output.py` (12 tests, dont la lecture du journal d'une sortie raccourcie par
  `qc-gate`) et `tests/test_token_audit.py` (16 tests), sur des sorties et des journaux factices,
  `HOME` et `USERPROFILE` isolés.
- `tests/test_handoff.py` : la passation d'une session lancée dans un worktree, rangée sous le
  projet ; sous Windows, `CloseInAJob`, un plan de fermeture qui s'exécute dans un job sans
  `JOB_OBJECT_LIMIT_BREAKAWAY_OK`.
- `tests/test_guard_readonly.py` : `guard_readonly` laisse passer la lecture des rulesets.
- La suite tourne en CI sous Linux et sous Windows, avec `claude plugin validate` sur la
  marketplace et le plugin (`.github/workflows/tests.yml`).

### Gestes humains

- Aucun geste n'est obligatoire à la montée, en dehors des deux commandes de **Monter de version**.
- Un projet qui veut raccourcir la sortie de sa suite de tests ajoute la clé `trimmed-command` à
  son `docs/agents/usine.md` (gabarit `templates/usine.md`).
- Un poste servi par une passerelle ou un autre fournisseur fait pointer chaque niveau
  (`ANTHROPIC_DEFAULT_HAIKU_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`)
  vers un modèle qu'il sert.

### Restés dehors

- Le cache d'une heure pour le coder (`experimental.cacheTtl: 1h` dans son front matter) : une
  écriture dans ce cache coûte 2 fois le prix d'entrée, contre 1,25 fois pour celui de 5 minutes,
  et aucun journal de ce poste ne montre un lancement de `forge:coder` qui en prouverait le gain.
  Abandonné.
- Le hook de routage des modèles (PR #6) : fermé, remplacé par le niveau de chaque agent (#11).
- Une seule session par projet (#4) : ouvert, pas commencé.

## [1.2.0] - 2026-10-20

La passation drainée sous Windows (ikoro-labs/forge#3) : elle ne tournait que sous Linux, parce que
le relais était un script bash et que les questions de processus lisaient `/proc`.

### Hooks

- `handoff_relay.py` remplace `handoff_relay.sh` : même usage, mêmes codes de sortie (1 à 5),
  mêmes variables, mêmes messages, en Python de la bibliothèque standard lancé par
  `uv run --no-project --quiet python`. La fermeture différée de la session appelante est une copie
  détachée du relais (`--close`), sortie du job de la session sous Windows quand il le permet. Sous
  Windows, l'exécutable `claude.exe` est préféré au lanceur `.cmd`, pour qu'aucun `cmd.exe` ne
  relise le prompt du successeur ; une session interactive y reçoit `/exit` dans sa console
  (`--exit-console`), et n'est tuée qu'au bout de 15 secondes, le relais coupant alors lui-même le
  suivi de la souris : essayée tuée d'emblée par `taskkill /F`, elle avait laissé chaque mouvement
  de souris s'écrire dans le shell. Une session de fond est arrêtée par `claude stop` puis
  `claude rm`, ses fenêtres `claude attach` fermées d'abord. `CLAUDE_HANDOFF_TERMINAL` accepte
  `wt.exe`. Le nom du compteur du jour remplace aussi `\` et `:` d'un chemin Windows.
- Le relais reconnaît une session interactive au registre de Claude Code
  (`~/.claude/sessions/<pid>.json`, `"kind": "interactive"`) : elle porte elle aussi
  `CLAUDE_CODE_CHILD_SESSION=1` (Claude Code 2.1.304), et la 1.1.0 la traitait en session de fond.
- `feature` ne compte que ses identifiants `F-NNNN` : essayé sous Windows, un « aucune (demande
  ponctuelle) » avait donné au successeur le seuil de 400 k. La consigne du hook le dit.
- `CLAUDE_HANDOFF_CLOSE_DRY_RUN` : `0`, `false`, `no`, `off` ou vide laissent le relais à blanc
  coupé ; toute valeur non vide l'allumait, `0` compris.
- `handoff_header.py` : `process_alive`, `process_start`, `parent_pid` et `ancestors` répondent par
  `/proc` sous Linux et par l'API Win32 (`ctypes`) sous Windows ; ailleurs, un processus compte pour
  vivant. Le verrou d'un worktree d'agent est lu avec ou sans heure de départ : Claude Code n'en
  écrit pas sous Windows (`claude agent <nom> (pid N)`), et l'ancienne expression, qui l'exigeait,
  aurait compté pour vivant tout verrou, même d'un agent mort ou d'une autre session. Sans heure, un
  pid vivant vaut détenteur.
- `handoff_trigger.py` : la consigne lance le relais par `uv run --no-project --quiet python`, et
  la liste des agents en vol passe par `handoff_header.ancestors`. Le prompt du successeur ne cite
  plus `python3`, qui sous Windows est un alias du Microsoft Store.
- `CLAUDE_HANDOFF_DIR` : dossier des passations, `~` et variables développés, par défaut
  `~/.claude/hooks/state/handoffs` comme avant. Essayé sur un poste Windows sous politique gérée :
  le hook s'est déclenché, mais la session n'a pas pu écrire la passation, l'outil Write étant
  refusé sous tout dossier `.claude` ; le relais a répondu `handoff document not found`. Les
  marqueurs et compteurs, écrits par les hooks eux-mêmes, restent dans `~/.claude/hooks/state`.

### Tests

- `tests/test_handoff.py` : le relais tourne sous Windows comme sous Linux (seul git est requis),
  sur un `claude` simulé en Python ; verrou lu avec et sans heure de départ ; processus vivant,
  fini, et ancêtres d'un enfant ; détenteur mort qui libère son worktree ; passation sous
  `CLAUDE_HANDOFF_DIR`, variable développée, marqueur resté dans l'état ; plan de fermeture d'une
  session interactive et d'une session de fond à blanc, registre des sessions ; `feature` en prose
  à 150 k ; `DRY_RUN=0` coupé ; sous Windows, `/exit` tapé dans la console cachée d'une session
  simulée, et session sourde à `/exit` tuée. Les tests isolent `USERPROFILE` comme
  `HOME`, sans quoi sous Windows ils écrivaient dans le vrai `~/.claude/hooks/state`, et ne passent
  plus aux relais les variables `CLAUDE_` de la session qui les lance. `enterContext` (Python 3.11)
  cède la place à `patch.start` : la suite tourne sous le Python 3.10 que `uv` peut choisir.

### Gestes humains

- La règle de permission qui autorisait `bash …/hooks/handoff_relay.sh` vise désormais
  `uv run --no-project --quiet python …/hooks/handoff_relay.py` (README, **Gestes humains**, point 5).

## [1.1.0] - 2026-10-20

La passation drainée d'une session à sa limite de contexte (ikoro-labs/forge#3), décidée dans
Projet B sous l'ADR-0126 (catégorie B, Projet B #973, points A à F) et adoptée par Projet A. Le
plugin devient la source des scripts qui vivaient en copie dans `~/.claude/hooks`.

### Hooks

- `handoff_trigger` (`UserPromptSubmit`, `PostToolUse`) : au seuil de contexte, la session ne
  lance plus rien et attend ses agents (drainage, point A) ; plafond dur au seuil plus 35 k jetons
  ou 45 minutes après le premier avis, avec la liste `sauvetage`. Seuil
  `CLAUDE_SESSION_TOKEN_LIMIT`, 150 k par défaut. Filtre `agent_id` : un sous-agent n'est jamais
  averti. Le hook se tait tant que `~/.claude/settings.json` déclare encore une copie hors
  plugin, pour qu'aucun avis n'arrive deux fois. `hooks_version` de l'en-tête est lu dans
  `plugin.json`. Le skill `handoff` de l'utilisateur n'est cité que s'il existe. La consigne
  rappelle qu'un agent relancé par `SendMessage` ne reverrouille pas son worktree et doit figurer
  sous `en_vol`.
- `handoff_relay.sh` : refuse le relais (code 5) tant qu'un agent de la session est vivant ou que
  `en_vol` est non vide, `--force` seulement avec `sauvetage` non vide (point B) ; plafond du jour
  par projet (code 3), compteur avancé après les contrôles seulement ; écrit `successeur` et
  `seuil` dans l'en-tête, arrête puis supprime la session fermée (`claude stop`, `claude rm`,
  point C). Le successeur démarre à 400 k quand la passation porte une feature, à 150 k sinon
  (point F). Fenêtre de terminal optionnelle par `CLAUDE_HANDOFF_TERMINAL`, aucun terminal câblé ;
  nom de session horodaté.
- `handoff_header.py` : valide le front matter de la passation (point E : onze clés), écrit le
  successeur, dit à une session de relais si elle est le successeur désigné (code 3 sinon), liste
  les worktrees d'agents dont le processus tient encore le verrou.
- État et passations hors du cache du plugin : `~/.claude/hooks/state/`, passations sous
  `handoffs/<projet>/<date>-r<N>.md`.

### Agents

- `forge:coder` : un commit Conventional Commits poussé par critère vert, jamais « wip » (point
  D) : ce qui est poussé se reprend quand la session qui l'a lancé se ferme.

### Tests

- `tests/test_handoff.py` : en-tête invalide (2), agent vivant de la session (5) et agent d'une
  autre session ignoré, `en_vol` (5), `--force` sans `sauvetage` (5), plafond du jour (3) sans
  mouvement du compteur, seuil 400 k avec feature et 150 k sans, même hérité de 400 k, étapes
  drain et hard, copie hors plugin, relais à blanc (`CLAUDE_HANDOFF_CLOSE_DRY_RUN=1`) et relais
  réel sur un `claude` simulé.

## [1.0.0] - 2026-10-19

Première version, selon l'ADR-0129 de Projet B (§1 et §4) : la partie générique de Forge au tag
`forge-v2.2.0` de Projet A, plus les capacités que Projet B avait et que Forge n'avait pas (relevé de
Projet B #897 et de `docs/agents/skills.json` de Projet A). Tout ce qui est propre à un
projet en est sorti : chaque élément qui en dépendait lit désormais la clé correspondante de
`docs/agents/usine.md`, et une clé absente rend l'étape « sans objet », jamais `PASS`.

### Agents

- `forge:coder` : un ticket jusqu'à sa PR, en test-first et dans son worktree, sans la relire ni
  la fusionner ; bloc `RESULT` final, `BLOCKED` sur toute ambiguïté ; mode sync pour une PR en
  retard sur sa base, mode correction pour les `BLOCKER` d'un verdict.
- `forge:qc-gate` : le mesureur de la revue, sondes dans un ordre fixe, rejeu dans une copie de la
  tête, `NOT RUN` jamais `PASS`.
- `forge:qc-conf` : le juge, deux axes (standards, spec du ticket), constats `BLOCKER`,
  `MINOR`, `NOTE`, deux tours au plus.
- `forge:staff-engineer` et `forge:product-owner` : les décideurs délégués de la technique et du
  produit, en lecture seule, qui tranchent selon la matrice de décision du projet ou disent quelle
  case réserve la question à un humain.

### Skills

- `/forge:qc` : revue en deux temps, verdict et rapport postés sur la PR, fusion sur ACCEPT, chemins
  protégés laissés à un humain.
- `/forge:feature-build` : l'aval d'une feature, chaque ticket prêt confié à `forge:coder`, revue
  par `/forge:qc`, questions passées aux décideurs délégués.
- La chaîne des features, de l'idée à la livraison : `/forge:feature-new`,
  `/forge:feature-brainstorm`, `/forge:feature-frame`, `/forge:feature-spec`,
  `/forge:feature-design`, `/forge:feature-accept` (réservé à un humain), `/forge:feature-verify`,
  `/forge:feature-close` et `/forge:feature-status`.
- `forge:codebase-design`, `forge:domain-modeling` et `/forge:improve-codebase-architecture`,
  adaptés de mattpocock/skills (licence dans `plugins/forge/THIRD_PARTY_NOTICES.md`).

### Hooks

- `guard_git` : la partie générique (commit ou push sur `main`, force-push, `branch -D`,
  `reset --hard`, `clean -f`, `--no-verify`, fusion sans checks verts, ticket en `Refs` fermé par
  la fusion).
- `guard_coder` : filtré sur `agent_type == "forge:coder"`, refuse au coder la fusion, la revue,
  l'édition des tickets et le skill `qc` sous ses deux noms, `forge:qc` et `qc`.
- `guard_readonly` (G1) : les juges et les décideurs ne modifient rien ; liste blanche pour
  `forge:qc-conf` et les décideurs, liste noire pour `forge:qc-gate`, étendues par les clés
  `readonly-agent` et `readonly-command`.
- `guard_pause` (G7) : tant que `.claude/PAUSED` existe, aucun agent n'est lancé.
- `after_write` : aucun tiret cadratin au-delà de la tolérance du fichier (clé
  `em-dash-allowances`).

### Scripts, gabarits et tests

- `scripts/parse_output.py` (G19) : lit le `RESULT` du coder et le verdict du juge, et dit
  exactement ce qui ne va pas, pour une seule relance.
- `templates/usine.md` : le gabarit de `docs/agents/usine.md`, avec chaque clé que lisent le plugin
  et ses hooks.
- `templates/adr.md` et `templates/features/` (protocole, idée, séance, cadrage, spec, design,
  recette, livrée).
- `tests/` : les tests des hooks, du parseur et de la configuration, et le test des noms cités
  (G9) : tout `forge:<nom>` cité dans le plugin désigne un agent ou un skill qui existe.

### Restés hors du plugin

- G3, G4, G5, G8 et G15 : lots 3 et 4 de Projet B #898, tenus jusqu'à la clôture de F-0001 ; ils
  arriveront par une montée de version.
- G6 et G18 : demandent une décision qui n'est pas prise.
- G13 : demande un accès réseau que les hooks n'ont pas.
- Le contrôleur `factory/` de Projet A, son contrat de revue d'architecture
  (`docs/architecture/reviews/<FEATURE-ID>.json`) et `python -m factory prepare` : propres à Projet A.
- Les skills de domaine (architect, backend, frontend, postgres, security, observability,
  performance, prompt-engineer, context-engineer, reviewer, langgraph),
  `domain-arbiter`, `run-app` et les skills `projet-a-*` : chacun applique les règles de son
  projet. Un projet les garde dans `.claude/` et les désigne par les clés `domain-skill`,
  `domain-rules`, `review-grid` et `domain-arbiter`.
- Les gardes de CI, `scripts/features.py`, `ci_local`, le modèle de PR et les hooks git : lus par la
  CI, GitHub ou git, qui ne chargent aucun plugin ; ils restent en copie dans chaque dépôt.
- Les gestes de propriétaire de `guard_git` (runners, variables, protection de branche, Dependabot)
  : propres à chaque projet, dans ses hooks de `.claude/settings.json`.
- ruff et Prettier après une écriture : chaque projet formate dans ses propres hooks.
