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

## La question d'une session longue (ticket 5)

Une session qui pose `ready-for-human` ou `needs-info` sur un ticket ou une PR puis finit son tour s'arrête
et attend : rien ne la réveille, car `question_delay.py` n'est lu que par `forge:feature-build`. Le hook
`Stop` `plugins/forge/hooks/question_stop.py` lui fait suivre sa question. Il ne lit que la clé
`question-default-delay`, déjà documentée ; aucune clé nouvelle.

Ce qu'il fait, dans l'ordre :

1. Il relève dans le transcript les étiquettes que la session a posées depuis le dernier message de
   l'humain (une commande `Bash` : `gh issue edit` ou `gh pr edit` avec `--add-label`, `gh api .../issues/<n>/labels`
   avec un champ `labels[]=`). Une étiquette posée par un autre outil, un outil MCP par exemple, n'est pas vue.
2. Il relit chaque question par les fonctions de `question_delay.py` (`questions`, `Question.due_at`), jamais par
   une copie de leur logique : ouverte, toujours étiquetée, datée.
3. Il garde la session ouverte et relit la question toutes les 30 secondes, jusqu'à l'échéance. Une échéance
   plus lointaine que le `timeout` de son entrée (780 secondes) moins une minute laisse passer l'arrêt : le
   tick du répartiteur la reprend (ticket 8, partie c).
4. À l'échéance, il bloque l'arrêt (`decision: block`) : le décideur (`forge:staff-engineer` pour une question
   technique, `forge:product-owner` pour une question produit), puis `question_delay.py route ... --apply`.
   Une décision réversible est postée par défaut et retire l'étiquette ; un geste réservé reçoit un rappel, et
   l'arrêt suivant passe.

Ce qu'il laisse passer, toujours : une question qui porte déjà un `Rappel (question-default-delay)` (A36, c'est
ce qui rend l'arrêt qui suit un rappel libre, A35), un événement d'un sous-agent (`agent_id`), un agent du
répartiteur (son `name` du registre correspond à `ignored-session` et son pid tient un verrou vivant, comme
`handoff_header.other_sessions` : c'est le tick qui le sert, A38), le neuvième arrêt de suite (A37) avec un
message sur sa sortie qui dit que le plafond de 8 est atteint, et tout échec : clé absente, délai ou transcript
illisible, `gh` en échec, erreur du hook (A39). Le plafond se compte comme Claude Code le compte : les blocages
de `Stop` depuis le dernier appel d'outil, ceux de n'importe quel hook.

`hooks.json` n'a aucun `|| exit 2` pour cette entrée : un hook `Stop` qui sort en 2 retient la session, et
`"onFailure"` est sans effet sur `Stop`. La commande finit par `; exit 0`. `hooks.json` est un chemin protégé :
la PR de ce ticket est fusionnée par l'humain.

Éprouvé : par les tests, hook lancé en processus avec un faux `gh` et une horloge que le test avance ; le
transcript est un fichier que le test écrit, d'après le format relevé dans un transcript réel de la version
2.1.330 (entrée `user` marquée `isMeta` dont le texte commence par `Stop hook feedback:`). Pas éprouvé sur une
vraie session : une attente de plusieurs minutes dans un hook `Stop`, la prise en compte de `timeout` à 780
secondes et le blocage qui relance la session n'ont pas été vus de bout en bout. La question de la décision Q6
du design reste donc à éprouver sur un vrai poste, avant que le tick (ticket 8) n'en dépende. Linux seulement.
