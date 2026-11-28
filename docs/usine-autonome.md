# L'usine autonome (F-0003)

Cette page suit la feature F-0003 (`docs/features/0003-usine-autonome/`) : ce que chaque ticket livre, les
clés de `usine.md` qu'il ajoute, ce que l'humain doit faire. Elle se complète à chaque ticket ; elle ne
décrit que ce qui est entré.

## Les clés

Une clé absente rend son étape « sans objet (clé `<nom>` absente) » : aucune n'a de valeur par défaut. Le
gabarit `plugins/forge/templates/usine.md` donne la forme de chacune.

| Clé | Fichier | Rôle |
| --- | --- | --- |
| `agent-token-command` | `docs/agents/usine-gardes.md` | une commande qui imprime un jeton d'installation de l'application GitHub des agents |
| `agent-login` | `docs/agents/usine-gardes.md` | le login que portent les gestes de l'application |
| `ignored-session` | `docs/agents/usine.md` | les noms de session (exact, ou préfixe fini par `*`) des agents d'un répartiteur, que `handoff_header.py sessions` ne compte pas comme sessions au travail |

## L'identité GitHub des agents

Sans elle, les agents agissent sur GitHub avec le jeton de l'humain : rien ne distingue un geste d'agent
d'un geste de l'humain, et une ligne écrite sous son compte ne prouve pas qu'il l'a voulue. Avec elle, les
agents ont leur propre compte, une application GitHub, et `guard_git` refuse tout geste d'écriture qui ne
passe pas par elle.

### Les deux clés

Écrites par l'humain du projet dans `docs/agents/usine-gardes.md`, lues telles que `origin/main` le tient
(ce sont deux clés protégées de `usine.SENSITIVE_KEYS`) :

- `agent-token-command` : une commande qui imprime un jeton d'installation de l'application sur une ligne
  et sort en 0. Forge ne signe rien : signer un jeton d'application demande RS256, hors de la bibliothèque
  standard, donc la commande est celle du projet.
- `agent-login` : le login que portent les gestes de l'application.

### Ce que `guard_git` refuse

Avec les deux clés, un geste qui écrit sur GitHub est refusé tant que `GH_TOKEN` (sinon `GITHUB_TOKEN`) de
la session ne commence pas par `ghs_`, le préfixe d'un jeton d'installation. `GH_TOKEN` passe avant
`GITHUB_TOKEN` parce que `gh` le lit le premier : un `GH_TOKEN` de l'humain à côté d'un `GITHUB_TOKEN`
d'application est le jeton que `gh` enverrait, donc refusé.

Un geste d'écriture est :

- `git push`, hors `--dry-run` et `-n` ;
- un verbe de `gh pr`, `gh issue` ou `gh project` qui n'est pas une lecture, et les verbes qui écrivent de
  `gh release`, `gh label`, `gh run`, `gh workflow`, `gh repo`, `gh gist` et `gh cache` ;
- un verbe d'un autre groupe de `gh` que ces listes ne nomment pas, sauf une lecture (`gh secret list`,
  `gh variable get`, `gh ssh-key list`, `gh codespace view`, `gh discussion view`...) : `gh secret set`,
  `gh ssh-key add` ou `gh codespace create` écrivent sous le jeton de l'humain comme un `gh pr create`. Un groupe
  que le garde ne connaît pas (la commande d'une extension, un groupe que `gh` ajoute) est fermé de la même
  façon. Ne sont jamais des écritures sur GitHub, chacun pour sa raison écrite dans `GH_NEVER_WRITE` : `help`,
  `version`, `completion`, `config`, `alias`, `auth`, `browse`, `extension`, `preview`, `search`, `status`,
  `licenses`, `attestation`, `org` et `ruleset` ;
- un appel `gh api` d'une autre méthode que GET ou HEAD ;
- un appel GraphQL dont la requête porte `mutation`, ou que le garde ne peut pas lire (une variable, un tube) ;
- n'importe quelle écriture par un outil MCP d'un serveur GitHub, avec ou sans jeton : ce serveur tient son
  propre jeton, qu'aucune variable d'environnement ne remplace, donc les agents écrivent par `gh`. Une
  lecture (`get_`, `list_`, `search_`, un nom qui finit par `_read`) passe.

Le refus nomme le geste, dit que l'écriture se fait sous l'identité des agents, cite `agent-login` et la clé
de la commande, et ne propose jamais le jeton de l'humain à la place. Il entre au journal des refus sous la
règle `agent-identity`.

Une ligne répétée ou une valeur vide dans l'une des deux clés ferme toute écriture, et le refus cite la
ligne : le garde échoue fermé, comme les autres clés protégées.

### Le jeton, tiré de la commande

`agent_identity.fresh_token` lance la commande de `agent-token-command` et rend la ligne qu'elle imprime. Une
commande qui échoue, qui n'imprime rien, qui imprime deux lignes ou un jeton d'un autre préfixe que `ghs_`,
qui dépasse son délai (30 secondes) ou qui ne peut pas démarrer lève une erreur qui nomme la clé, jamais la
commande, sa sortie ni un jeton. Rien ne prend alors le jeton de l'humain à la place : le répartiteur d'un
ticket suivant ne lance aucun agent sur cette erreur. Aucun jeton n'est écrit dans un fichier ni dans un
journal.

### Sans les clés

Avec l'une des deux clés absente, rien ne change : `guard_git` ne refuse aucun geste au titre de l'identité,
et l'étape est « sans objet (clé `agent-login` absente) », sans valeur par défaut. Ce dépôt ne les déclare
pas encore.

### Ce qui n'est pas couvert

- Le garde ne lit que le préfixe : il ne prouve pas de quelle application vient le jeton, ni qu'aucun autre
  chemin n'emploie le jeton de l'humain. Un `export GH_TOKEN=...` ou une affectation en tête de commande
  change l'environnement de la commande, pas celui du hook, qui hérite de celui du processus `claude`.
- Le jeton d'installation vit une heure : la tenue du jeton au-delà de 60 minutes, l'identité git des
  commits et la ligne `agent-identity` de `factory_slo.py report` sont la partie suivante du même ticket.
- Installer l'application, écrire les deux clés et fusionner leur PR est un geste de l'humain.

### Ce qui a été éprouvé

Par les tests de `tests/test_guard_git_identity.py` (la détection d'un geste), de `tests/test_agent_identity.py`
(le jeton et les messages), de `tests/test_agent_identity_token.py` (la commande, lancée pour de vrai) et de
`tests/test_guard_git_identity_keys.py` (le hook joué comme un processus, dépôts jetables, `HOME` jeté), sous
Linux seulement. Pas encore avec une vraie application GitHub ni dans une
vraie session de Claude Code : les noms des outils MCP des serveurs GitHub sont supposés d'après ceux qu'on
voit dans les tests de fusion, et le comportement d'un vrai serveur n'a pas été joué.

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
