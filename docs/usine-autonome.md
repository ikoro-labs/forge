# L'usine autonome

La feature F-0003 (`docs/features/0003-usine-autonome/`) retire à l'humain les gestes qui ne demandent pas
son jugement, et lui garde ceux qui le demandent. Cette page grandit avec ses tickets : chacun y décrit ses
clés, ce qu'il refuse et ce qu'il n'a pas pu éprouver.

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
