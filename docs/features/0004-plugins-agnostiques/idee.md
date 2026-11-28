---
feature: F-0004
document: idee
titre: plugins indépendants de l'outil d'agent, un coeur neutre et des adaptateurs minces
porteur: ikoro-labs
etat: active
demande_par: interne, l'humain de la clé accepting-human (demande du 2026-11-28, relayée par sa session de pilotage)
issue: 395
date: 2026-11-28
---

# F-0004 : plugins indépendants de l'outil d'agent, un coeur neutre et des adaptateurs minces

## L'idée, en une phrase

Forge garde tout ce qu'il fait aujourd'hui, mais se sépare en un coeur qui ne dépend d'aucun outil
d'agent et en adaptateurs minces, un par outil : Claude Code reste le premier adaptateur, sans
régression, et Codex est le deuxième candidat.

## D'où elle vient

Une demande de l'humain du 2026-11-28, faite dans sa session de pilotage et relayée à la session
forge par cette session, résumée ici sans la reprendre mot pour mot. Le cadrage peut commencer tout de
suite, car il n'écrit que de la documentation ; la construction attend que le lot 1 de F-0003 soit
fusionné, les deux touchant les hooks.

Chiffres relevés par la session de pilotage le 2026-11-28 sur `origin/main` `6572e1a`, dans
`plugins/forge/`, **non recomptés ici** (le cadrage les recompte avant de s'en servir) : 27 fichiers de
skills, 7 fichiers d'agents, 64 fichiers Python sous `hooks/` et `scripts/` (24 199 lignes) ; 33 fichiers
lisent une variable `CLAUDE_*` ; 6 appellent `claude -p` ou `claude` ; 6 émettent `hookSpecificOutput`
ou `permissionDecision` ; 4 lisent des transcripts ; 6 citent `subagent_type`, `SendMessage` ou
`ScheduleWakeup`. Événements de hook utilisés : `PreToolUse`, `PostToolUse`, `SessionStart`, `Stop`,
`SubagentStop`, `UserPromptSubmit`.

Sources citées par la demande, à confronter aux textes de référence pendant le cadrage :

- la documentation des hooks de Codex, qui décrit les mêmes événements :
  https://developers.openai.com/codex/hooks (non relue ici) ; ceux de Gemini CLI ne sont pas vérifiés ;
- deux sources secondaires sur Agent Plugins 1.0, qui disent que les hooks sont hors du standard et
  que Claude Code garde son propre format :
  https://aaif.io/blog/from-skills-and-tools-to-portable-agent-plugins et
  https://thenewstack.io/agent-plugins-portability-gaps/ (non relues ici).

## Qui l'a demandée

L'humain de la clé `accepting-human`, pour forge et pour un second plugin qu'il tient. La règle
d'entrée est sans objet (clé `entry-gate` absente) : la feature est admise par son issue de suivi.

## Premières questions

- Ce qui est coeur et ce qui est propre à Claude Code dans le plugin, et si la disposition actuelle
  et le modèle de documentation progressive sont efficaces.
- La correspondance de chaque partie (skills, agents, hooks, scripts, gabarits, orchestration) avec
  les standards communs aux outils : `SKILL.md`, `AGENTS.md`, MCP et Agent Plugins 1.0, tous sous
  l'Agentic AI Foundation.
- La stratégie d'adaptateur pour les hooks et l'orchestration, qu'aucun standard ne couvre.
- Le même audit pour le second plugin de l'humain. Son dépôt est privé : cette part de l'audit vit
  hors de ce dépôt (fichier local non suivi, ou dans le dépôt privé), et rien ici ne le nomme ni ne
  décrit son contenu.
