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

## Le relevé de base (ticket 6, story 18)

`factory_slo.py baseline` donne les chiffres qui fondent le point de décision du 2026-12-16, avant le
répartiteur puis pendant l'essai. Il ne mesure rien de nouveau pour le délai et les jetons : il reprend
`lead-time` et `tokens-per-merge`. Il ne lit que GitHub, git, les journaux de jetons et la trace du répartiteur.

```sh
uv run --no-project --quiet python plugins/forge/scripts/factory_slo.py baseline .
uv run --no-project --quiet python plugins/forge/scripts/factory_slo.py baseline . --essai 2026-12-05
```

Le premier appel relève la base : les 30 jours avant `--jusqua` (maintenant par défaut), ou depuis `--depuis`.
Le texte rendu est celui du commentaire à poster sur #340 : pour chaque mesure, sa fenêtre et son dénominateur.

| Mesure | Ce qui est compté |
| --- | --- |
| délai p90 | de la pose de `ready-for-agent` à la fusion de la PR qui ferme le ticket ; les tickets sans pose sont comptés à part |
| interventions de l'humain par ticket fusionné | les étiquettes `needs-your-attention` posées sur un ticket fusionné ou sur une PR qui l'a fermé, plus les PR fusionnées par un compte de la clé `accepting-human` (son identifiant court) sans l'étiquette `agent-merged` |
| jetons par PR | les jetons des journaux de ce poste sur la fenêtre, divisés par les PR fusionnées |

L'agent fusionne sous le compte de l'humain et étiquette ce qu'il fusionne `agent-merged` : sans cette étiquette, une
fusion est lue comme celle de l'humain. Sans la clé `accepting-human`, les fusions de l'humain sont « sans objet »
et seules les étiquettes sont comptées. Un commentaire de l'humain n'est jamais compté.

Le second appel, avec `--essai <premier jour de l'essai>` (et `--le <fin>`, maintenant par défaut), relève aussi
l'essai et applique la règle du point de décision : « oui » si et seulement si le délai p90 de l'essai est
strictement plus bas que celui de la base, si les interventions par ticket de l'essai ne dépassent pas celles de la
base, et si la trace du répartiteur de ce poste (`~/.claude/hooks/state/dispatch/<jour>.jsonl`, événement
`question`) ne porte aucun `post-default` d'une case `H<n>` dans l'essai. Sinon « non », avec chaque raison. Une
mesure qu'une fenêtre ne peut pas donner est une raison de « non » : elle ne prouve rien. La trace est lue telle que
la spec la décrit (G3) : `dispatch_trace.py`, qui l'écrit, n'existe pas encore, et le champ `project` est accepté
comme le nom du dépôt ou comme le dossier du projet.

Le relevé compte enfin les tickets publiés après la clé `ticket-size-max` qui ont atteint `ticket-pr-cap`
(cible 0, sur tout l'historique, hors des fenêtres). La date de départ est celle du premier commit de la base qui
porte la ligne de la clé dans `docs/agents/usine.md`. Les PR d'un ticket sont comptées comme `guard_pr_cap.py` les
compte. Sans l'une des deux clés, ou sans commit de la base qui porte `ticket-size-max`, la mesure est « sans objet ».
