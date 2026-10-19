# Journal des versions

Une entrée par version publiée du plugin `forge`, la plus récente en haut. Chaque version porte le
tag `forge--v<X.Y.Z>` sur ce dépôt ; sa version est celle de `plugins/forge/.claude-plugin/plugin.json`,
et nulle part ailleurs. Les tags `forge-v<X.Y.Z>` (un seul tiret) appartiennent à l'historique de
Projet A et ne sont pas repris ici.

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
