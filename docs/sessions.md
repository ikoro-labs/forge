# Sessions : une par dépôt, et la passation drainée

Ce que suit toute session d'un projet qui utilise forge, et comment une session passe la main à la
suivante quand son contexte est plein. Le résumé est dans le
[`README.md`](../README.md#ce-que-les-hooks-gardent).

## Règles communes

Ce que suit toute session d'un projet qui utilise l'usine, interactive ou de fond
(ikoro-labs/forge#4). Le contenu du plugin la porte (`feature-build`, étape 0, le relais de la
passation et le hook `SessionStart`) ; chaque projet la reçoit à sa montée d'épingle.

- **Une session par dépôt.** Une seule session agit sur un dépôt à la fois, ses worktrees compris.
  « Un seul passage par feature » en est un cas particulier. Des sessions de dépôts différents
  coexistent : la règle porte sur un dépôt, pas sur le poste.
- **Le premier geste** de toute session : lister les autres sessions vivantes du dépôt (voir
  [Le premier geste](#le-premier-geste)).
- **Une autre session agit sur le dépôt** : la nouvelle n'agit pas. Elle envoie sa demande à la
  session en place (`SendMessage`), qui l'ajoute à sa file, puis elle s'arrête et le dit. Une
  tâche annexe entre de même dans la file de la session en place, par message ou par ticket ; elle
  n'ouvre jamais une deuxième session à côté.
- **Une passation ne crée pas de session parallèle** : le relais refuse en code 6 quand une autre
  session du dépôt vit, et ne lance aucun successeur.
- **L'humain ouvre une session interactive** sur un dépôt où une session de fond agit : la session
  de fond draine puis s'arrête, et la session interactive en devient le successeur de fait (voir
  [Qui cède à qui](#qui-cède-à-qui)). Avant d'ouvrir une seconde session sur un dépôt, mieux vaut
  suivre celle qui y agit : `claude attach <id>`, l'identifiant étant celui que donne
  `claude agents`.

### Le premier geste

Depuis le dépôt :

```sh
uv run --no-project --quiet python <hooks>/handoff_header.py sessions .
```

puis `ListAgents`. La commande imprime `pid kind name status cwd` pour chaque autre session et sort
en 0 si aucune ne vit, en code 6 sinon ; une entrée illisible compte pour vivante. Si le registre
manque ou change de forme, `claude agents --json` liste les sessions vivantes avec leur dossier.

Ce qu'elle compte :

- elle lit le registre que Claude Code tient de ses sessions (`~/.claude/sessions/<pid>.json`) et
  garde les processus vivants. Sous Linux, l'heure de départ notée `procStart` doit être celle du
  processus, un pid pouvant être repris ;
- elle garde les sessions dont le dossier se résout sur la même copie principale (`.git` puis
  `commondir`) ;
- elle laisse de côté la session appelante (`CLAUDE_PID`, le processus qui lance la commande, et
  leurs ancêtres) ;
- elle laisse de côté la session qui lui a passé la main : l'`auteur` d'une passation du projet
  dont le `successeur` désigne la session appelante (`CLAUDE_CODE_SESSION_ID`). Un successeur
  n'est pas un descendant de son prédécesseur, qui vit encore pendant son délai de fermeture
  (`CLAUDE_HANDOFF_CLOSE_DELAY`) : sans cette exclusion, le successeur se rangerait derrière une
  session qui va mourir. Seule cette session est laissée de côté ; une passation illisible, ou sans
  `auteur` (écrite avant cette règle), n'en exclut aucune.

### Le hook `SessionStart`

**Le hook** `sessions_notice.py` (`SessionStart`, sur toutes les sources : `startup`, `resume`,
`clear`, `compact`, `fork`) fait ce premier contrôle au démarrage de chaque session. Il appelle la
même détection que `sessions`, avec les mêmes exclusions (l'identifiant de la session est le
`session_id` de l'événement). S'il trouve une autre session vivante du dépôt, il ajoute au
contexte de la session un avis qui la nomme et la renvoie au point 5 de l'étape 0 de
`feature-build`, en commençant par relancer `sessions .`.

Il ne dit rien quand aucune autre session ne vit, ni pour un sous-agent (`agent_id` dans
l'événement), et sort toujours en 0 : il observe et ne bloque jamais la session. `hooks.json` le
lance avec un `timeout` de 10 secondes ; au-delà, Claude Code l'annule et la session démarre sans
l'avis.

### Qui cède à qui

Une session se sait interactive par
`uv run --no-project --quiet python <hooks>/handoff_header.py self`, qui imprime le type que le
registre note pour elle (`CLAUDE_PID`) et son identifiant (`CLAUDE_CODE_SESSION_ID`), `?` quand il
manque. Claude Code 2.1.306 écrit `"kind": "interactive"` par défaut et `"kind": "bg"` pour une
session lancée par `claude --bg` (relais compris) ; `daemon` et `daemon-worker` sont ses propres
processus.

Seule la session interactive qui ne trouve en place que des sessions `bg` demande à céder ; dans
tout autre cas, la nouvelle session s'arrête. L'échange :

1. La session interactive envoie par `SendMessage` son identifiant et la commande que lance la
   session de fond depuis le dépôt :
   `uv run --no-project --quiet python <hooks>/handoff_trigger.py yield <identifiant>`.
2. `yield` imprime la conduite du drainage : ne plus rien lancer, laisser finir les agents, au plus
   `CLAUDE_HANDOFF_DRAIN_MINUTES` minutes, la passation au même chemin et au même format qu'au
   seuil. Céder tout de suite tuerait les sous-agents, et finir le passage ferait attendre
   l'humain.
3. À la place du relais, la session de fond lance
   `handoff_header.py set-successor <passation> <identifiant>` : la passation nomme la session
   interactive successeur et la session de fond auteur, et `sessions` ne compte plus celle-ci pour
   celle-là.
4. La session de fond envoie le chemin de sa passation par `SendMessage`, puis lance
   `handoff_relay.py --yield <passation>` (voir [Céder la main](#céder-la-main-à-la-session-interactive)) :
   elle est arrêtée puis supprimée après `CLAUDE_HANDOFF_CLOSE_DELAY` secondes, sans qu'aucune
   session soit lancée. Laissée vivante, elle resterait dans le registre, et la session suivante du
   dépôt, le relais de la session interactive compris, s'arrêterait derrière elle en code 6.
5. La session interactive reprend depuis la passation (`successor-ok`, puis le sauvetage).

Le contenu chargé par les projets le dit des deux côtés : `feature-build`, étape 0, point 5, et la
sortie de `yield`.

### Ce qui a été éprouvé

- Essayé sous Linux, avec Claude Code 2.1.306 et un registre écrit par 2.1.305 : sur le registre
  réel d'un poste, `sessions` a listé la session de fond d'un autre dépôt, lancée dans un worktree,
  et laissé de côté la session qui la lançait.
- Les types du registre ont été lus sous Linux, sur trois entrées réelles écrites par Claude Code
  2.1.305, toutes `"kind": "bg"` (des relais), et dans le code de 2.1.306, qui écrit
  `interactive` par défaut ; aucune entrée interactive vivante n'a été relue cette fois.
- Le refus du relais en code 6, `self`, `yield` et l'exclusion de l'`auteur` d'une passation n'ont
  tourné que dans la suite de tests, sous Linux et dans la CI Windows. La fermeture par `--yield`
  n'y a tourné que contre un faux `claude`, dont le `rm` retire l'entrée du registre ; qu'un vrai
  `claude rm` la retire n'a été vérifié sur aucun poste.
- La règle entière (premier geste, `SendMessage`, drainage de la session de fond) n'a pas encore
  été éprouvée de bout en bout.
- Sous Windows, rien n'a été essayé hors de la CI ; `procStart` n'y est pas comparé, et un pid
  vivant y vaut session vivante, sans garde contre la reprise d'un pid.
- Le hook `sessions_notice.py` n'a tourné dans aucune session réelle de Claude Code. Il a tourné
  dans la suite de tests sous Linux, que la CI fait aussi tourner sous Windows, et à la main sous
  Linux, son événement passé sur l'entrée standard, sur le registre réel d'un poste : il s'est tu,
  la session qui le lançait exclue par ses ancêtres et les deux autres sessions vivantes du poste
  étant d'autres dépôts. Qu'il nomme une autre session du dépôt n'a été vu que dans la suite de
  tests. Que Claude Code 2.1.306 ne mette `agent_id` que dans l'événement d'un sous-agent a été lu
  dans sa documentation des hooks et dans le schéma d'événement que porte son binaire, pas relevé
  sur une entrée réelle de `SessionStart`.

## La passation drainée

Une session passe la main à une nouvelle session quand son contexte atteint le seuil
(ikoro-labs/forge#3). Fermer une session tue ses sous-agents : la passation est donc un arrêt qui
draine.

### Le déroulé

1. **Au seuil**, le hook `handoff_trigger.py` (`UserPromptSubmit`, `PostToolUse`), qui lit le
   contexte du fil principal dans la transcription, dit à la session de ne plus rien lancer, de
   laisser finir ses agents, puis d'écrire la passation et de lancer le relais. Un sous-agent n'est
   jamais averti.
2. **Au plafond dur** (seuil plus 35 k jetons, ou 45 minutes après le premier avis), il fait
   lister les agents encore vivants sous `sauvetage` et forcer le relais.
3. **La session écrit sa passation**, puis lance le relais depuis le dossier du projet :
   `uv run --no-project --quiet python <hooks>/handoff_relay.py <passation>`.
4. **Le relais** `handoff_relay.py` lance le successeur par `claude --bg`, écrit dans l'en-tête son identifiant
   (`successeur`), son seuil (`seuil`) et la session appelante (`auteur`, que la session ne remplit
   pas en écrivant sa passation), puis arrête et supprime la session appelante.
5. **Le successeur** vérifie d'abord qu'il est bien le successeur désigné
   (`handoff_header.py successor-ok`), et son propre `sessions` laisse de côté l'`auteur` de la
   passation, encore vivant pendant son délai de fermeture.

### Le seuil

`CLAUDE_SESSION_TOKEN_LIMIT`, 150 000 par défaut. Seul le relais le relève, à 400 000 pour un
successeur dont la passation porte une feature, c'est-à-dire un identifiant `F-NNNN` dans
`feature` (du texte comme « aucune » n'en est pas une). Aucun `settings.json` ne doit le fixer.

### La passation

Un fichier `~/.claude/hooks/state/handoffs/<projet>/<date>-r<N>.md` (ou
`<CLAUDE_HANDOFF_DIR>/<projet>/<date>-r<N>.md`), hors du cache du plugin. `<projet>` est le nom de
la copie principale du dépôt, même pour une session lancée dans un worktree.

Il commence par un front matter de onze clés (`projet`, `feature`, `passage_depart`,
`jetons_agents`, `en_vol`, `file_revue`, `sauvetage`, `successeur`, `hooks_version`, `seuil`,
`contexte_passation`), que `handoff_header.py` valide ; son corps est le prompt de reprise. Le
skill `handoff` de l'utilisateur (`~/.claude/skills/handoff/`) est suivi s'il existe.

`jetons_agents` porte les jetons d'agents par ticket (ticket #72, clé `ticket-budget`) : une liste
d'éléments `- #n <rôle> <jetons>`, que `ticket_budget.py passation` imprime et que
`ticket_budget.py reprendre` recharge, pour que le relais reprenne les sommes au lieu de repartir de
zéro. Un nombre seul (`jetons_agents: 0`, les passations d'avant le budget) ne porte rien.

### Les refus du relais

Le relais refuse (code 5) tant qu'un agent de la session est vivant ou que `en_vol` n'est pas vide,
et n'admet `--force` qu'avec `sauvetage` non vide. Il refuse aussi (code 6) quand une autre session
du dépôt vit (voir [Règles communes](#règles-communes)). Chaque refus tombe avant que le compteur
du jour bouge et avant `claude --bg`, sauf le code 4, qui suit le lancement.

| Code | Sortie du relais |
| --- | --- |
| 0 | successeur lancé, fermeture programmée par `--yield`, ou essai à blanc affiché |
| 1 | usage, passation introuvable, ou `--yield` hors d'une session de fond connue (`CLAUDE_PID`) |
| 2 | en-tête de la passation invalide, ou sans `successeur` pour `--yield` |
| 3 | plafond du jour atteint (`CLAUDE_HANDOFF_RELAY_MAX`) |
| 4 | identifiant du successeur illisible dans la sortie de `claude --bg` |
| 5 | agents de la session encore vivants, `en_vol` non vide, ou `--force` sans `sauvetage` |
| 6 | une autre session du dépôt vit : aucun successeur, elle l'est de fait ; les sessions trouvées sont sur stderr |

### Céder la main à la session interactive

La session de fond qui cède (voir [Qui cède à qui](#qui-cède-à-qui)) ne lance pas le relais : sa
passation nomme déjà la session interactive (`handoff_header.py set-successor`). Une fois le chemin
envoyé par `SendMessage`, elle lance
`uv run --no-project --quiet python <hooks>/handoff_relay.py --yield [--force] <passation>`.

Il fait les mêmes contrôles d'agents (code 5, `--force` contre `sauvetage`) et la même fermeture
que le relais (`claude stop` puis `claude rm` après `CLAUDE_HANDOFF_CLOSE_DELAY`), sans lancer de
session, sans toucher au compteur du jour et sans le code 6. Il refuse (code 1) une session
interactive ou un `CLAUDE_PID` inconnu, et (code 2) une passation qui ne nomme aucun successeur.

### Les variables

| Variable | Défaut | Effet |
| --- | --- | --- |
| `CLAUDE_SESSION_TOKEN_LIMIT` | 150000 | seuil de drainage, posé par le relais seulement |
| `CLAUDE_HANDOFF_DRAIN_MINUTES` | 45 | minutes de drainage avant le plafond dur |
| `CLAUDE_HANDOFF_DIR` | `~/.claude/hooks/state/handoffs` | dossier des passations, `~` et variables développés (`%LOCALAPPDATA%\forge\handoffs`) ; les marqueurs et compteurs restent dans `~/.claude/hooks/state` |
| `CLAUDE_HANDOFF_RELAY_MAX` | 5 | relais par projet et par jour (code 3 au-delà) |
| `CLAUDE_HANDOFF_CLOSE_DELAY` | 45 | secondes avant la fermeture de la session appelante, par le relais ou par `--yield`, 0 la garde ouverte |
| `CLAUDE_HANDOFF_TERMINAL` | aucune | commande de terminal (`ghostty -e`, `gnome-terminal --`, `wt.exe` sous Windows) où ouvrir `claude attach <id>` ; sans elle, aucune fenêtre |
| `CLAUDE_HANDOFF_CLOSE_DRY_RUN` | aucune | affiche le lancement et la fermeture sans rien lancer, compteur et passation intacts ; `0`, `false`, `no`, `off` ou vide le laissent coupé |

### Sous Windows

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

### Quand l'écriture sous `.claude` est interdite

La session écrit la passation avec ses propres outils de fichier. Une politique gérée peut les
interdire sous tout dossier `.claude` : le hook se déclenche, mais l'écriture est refusée et le
relais répond `handoff document not found`. Sur un tel poste, `CLAUDE_HANDOFF_DIR` place les
passations ailleurs. Elle se pose dans l'environnement du poste ou dans le bloc `env` du
`~/.claude/settings.json`, pour que le hook, le relais et le successeur la voient :

```json
{ "env": { "CLAUDE_HANDOFF_DIR": "%LOCALAPPDATA%\\forge\\handoffs" } }
```

### Hors des projets où le plugin est activé

La passation ne vaut que dans les projets où le plugin est activé ; une copie de ces scripts dans
`~/.claude/hooks` couvrait tous les projets du poste. Tant que `~/.claude/settings.json` déclare
encore une telle copie, le hook du plugin se tait.
