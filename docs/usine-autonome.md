# L'usine autonome (F-0003)

Cette page suit la feature F-0003 (`docs/features/0003-usine-autonome/`) : ce que chaque ticket livre, les
clés de `usine.md` qu'il ajoute, ce que l'humain doit faire. Elle se complète à chaque ticket ; elle ne
décrit que ce qui est entré.

## Les clés

Une clé absente rend son étape « sans objet (clé `<nom>` absente) » : aucune n'a de valeur par défaut. Le
gabarit `plugins/forge/templates/usine.md` donne la forme de chacune.

| Clé | Fichier | Rôle |
| --- | --- | --- |
| `ignored-session` | `docs/agents/usine.md` | les noms de session (exact, ou préfixe fini par `*`) des agents d'un répartiteur, que `handoff_header.py sessions` ne compte pas comme sessions au travail |

## Les passes ignorées (ticket 4, partie a)

`ignored-session` ne cache une session que si deux faits tiennent : son `name` du registre correspond à une
ligne de la clé, et son pid tient un verrou vivant du répartiteur
(`~/.claude/hooks/state/dispatch/locks/<projet>/<ticket>.json`). Le relais ne la compte plus en code 6, et
`sessions_notice.py` ne la signale plus. Voir [`docs/sessions.md`](sessions.md) pour la détection.

Ce que la partie a ne fait pas : écrire le verrou. Le répartiteur le pose avec le ticket 8 ; tant que
personne ne l'écrit, aucune session n'est ignorée, ce qui est le côté prudent. Le nouvel essai d'un relais
refusé (`CLAUDE_HANDOFF_RETRY_MINUTES`) est la partie b du même ticket.

Le nom d'une session ne prouve rien, une session de l'humain peut porter n'importe quel nom : c'est le
verrou, qu'une session de l'humain ne tient jamais, qui la distingue. La spec disait « une session
`interactive` n'est jamais ignorée », mais une passe `claude -p` s'inscrit `interactive` (relevé du
2026-11-28, Claude Code 2.1.332) : le design (décision Q1, veto de l'humain) a remplacé ce test par le verrou.
