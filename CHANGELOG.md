# Journal des versions

Une entrée par version publiée du plugin `forge`, la plus récente en haut. Chaque version porte le
tag `forge--v<X.Y.Z>` sur ce dépôt ; sa version est celle de `plugins/forge/.claude-plugin/plugin.json`,
et nulle part ailleurs. Les tags `forge-v<X.Y.Z>` (un seul tiret) appartiennent à l'historique de
Projet A et ne sont pas repris ici.

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
