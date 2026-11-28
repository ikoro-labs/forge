---
feature: F-0003
document: design
statut: en-revue
destinataires: l'agent qui implémente (un forge:coder par ticket) ; forge:qc relit ; ikoro-labs (humain de la clé `accepting-human`) accepte par `/forge:feature-accept`, que le modèle peut lancer sous la clé `agent-autonomy`
adr: aucun
feature-tickets: 12
base: c2ecef9
date: 2026-11-28
---

# F-0003 : design

Le pourquoi est dans `cadrage.md`, le quoi dans `spec.md` (acceptée le 2026-11-28, PR #394). Ici : où cela se
construit, par quelles coutures, et dans quel ordre. Chaque numéro de ligne a été lu à la base `c2ecef9` pendant
l'écriture de ce design ; ce qui n'a pas pu l'être est à la section 10. Les questions techniques que ni le code
ni la documentation ne tranchent sont posées à `forge:staff-engineer` dans
`seances/2026-11-28-ikoro-labs-design.md` (tour 1, Q1 à Q9). Tant qu'elles n'ont pas de réponse, ce design porte
la recommandation de la séance et le dit à chaque endroit où elle compte (« sous réserve de Qn »).

Taille L, sans écran : il n'y a pas de `parcours.md`. La clé `feature-catalog-command` est absente de
`docs/agents/usine.md` : pas de catalogue.

## 1. Contextes touchés

Fichiers lus à la base `c2ecef9`. « Protégé » veut dire qu'un fichier du changement commence par un chemin de la
clé `protected-path` (`docs/agents/usine-gardes.md:114-117` : `.github/CODEOWNERS`,
`plugins/forge/hooks/hooks.json`, `plugins/forge/hooks/guard_`, `docs/agents/usine-gardes.md`) : la PR se fusionne
par l'humain (case H1 de `docs/agents/decisions.md`, consigne de `skills/qc/SKILL.md:211-217`, filet de
`guard_git.protected_refusal`, `guard_git.py:1416`). La forme du changement d'un garde est déléguée (case T5) ; la
fusion ne l'est pas.

| Contexte | Ce qui change | Couture avec les autres | Protégé |
|---|---|---|---|
| `plugins/forge/hooks/guard_human_data.py` (nouveau) | garde `PreToolUse` de l'outil `ArtifactData` : C01, message G2 | lit `human-collections` par `usine.load` sur `origin/main` ; journal par `refusal_journal.record` (`refusal_journal.py:77`) | oui (préfixe `guard_`) |
| `plugins/forge/hooks/hooks.json` | une entrée `PreToolUse` `ArtifactData` (garde, `\|\| exit 2`, `"onFailure": "block"`, `timeout` 60) ; une entrée `Stop` pour le pont de la question ; la description de la ligne 2 | les entrées `Stop` existantes sont aux lignes 199-217 ; aucun matcher `ArtifactData` n'existe | oui |
| `plugins/forge/hooks/usine.py` | sept clés de G1 entrent dans `SENSITIVE_KEYS` (`usine.py:34-43`) | `load` (l.268) et `read_config` (l.222) inchangés | non (voir Q8) |
| `plugins/forge/hooks/agent_identity.py` (nouveau) | C02 (`ghs_`), lecture du jeton par `agent-token-command`, identité git de l'application | importé par `guard_git` et par `dispatch.py` ; aucune autre dépendance que `usine` | non |
| `plugins/forge/hooks/guard_git.py` | refus d'un geste d'écriture sans jeton `ghs_` quand `agent-token-command` et `agent-login` sont présentes (nouvelle règle dans `RULES`, l.2724) ; acceptation de la fusion d'un chemin protégé quand le statut de `merge-grant` est `success` sur la tête et posé par `agent-login` | `merge_call_refusal` (l.2271-2347) appelle `protected_refusal` à la l.2341 : l'acceptation s'insère juste avant, par un appelable injecté comme les autres de `refusal` (l.2046-2066) ; `_gh_api_reads` (l.888) dit déjà lecture ou écriture | oui |
| `plugins/forge/scripts/merge_grant.py` (nouveau) | C03 : `GRANTED`, `WAITING`, `NOT RUN`, « sans objet » | lit `merge-grant`, `human-collections`, `agent-login` ; poste le statut par `gh api` ; appelé par `forge:qc` et par le tick | non |
| `plugins/forge/hooks/handoff_header.py` | C04 dans `other_sessions` (l.545-567), donc dans `sessions` (l.620-624), le relais et `sessions_notice.py` | lit `ignored-session` par `usine.load` ; sous réserve de Q1, lit aussi les verrous du répartiteur par `agent_lock.held` | non |
| `plugins/forge/hooks/handoff_relay.py` | nouvel essai sur code 6 seulement (C05), trace G4 | le contrôle des autres sessions (l.425-440) précède le compteur (l.441-449) : un essai refusé ne compte pas ; une copie détachée (`detached`, l.107) attend, sous réserve de Q2 | non |
| `plugins/forge/hooks/question_stop.py` (nouveau) | pont du hook `Stop` (story 6) | lit le transcript, appelle `question_delay.py due` ; échoue ouvert, d'où un nom hors du préfixe `guard_` | non (mais `hooks.json` l'est) |
| `plugins/forge/hooks/agent_lock.py` (nouveau) | verrou local d'un agent du répartiteur : poser, lire, libérer, tenu ou mort | `handoff_header.process_alive` (l.215) et `process_start` (l.229) pour Linux et Windows | non |
| `plugins/forge/scripts/dispatch.py` (nouveau) | `tick` : C06 à C08, revendication, lancement, relance, questions dues, trace G3 | `factory_slo.py queue` (`run_queue`, l.1237), `question_delay.py due` et `route --apply`, `agent_lock`, `agent_identity`, `usine.on_main` (l.157) pour `agent-autonomy` | non |
| `plugins/forge/scripts/dispatch_trace.py` (nouveau) | écriture d'une ligne G3, liste blanche de champs par événement (T10) | importé par `dispatch.py`, `merge_grant.py` et `question_delay.py` | non |
| `plugins/forge/scripts/question_delay.py` | `plan_for` (l.262-290) rend `ready-for-agent` à une issue sur `post-default` (A59) ; `apply` (l.293) écrit la ligne G3 `question` (A61) | `kind_of` (l.110) distingue déjà issue et PR | non |
| `plugins/forge/scripts/factory_slo.py` | ligne `agent-identity` (A15) ; relevé de base (A84) ; `prs` (l.209-210) gagne le champ `author` | `report` (l.809), `compute` (l.551), `human_touch` (l.469) pour la forme d'un `Sli` | non |
| `plugins/forge/scripts/ticket_graph.py` | lignes `CHAIN` (C09) et lecture de G9 dans le design | `check` (l.104-122) ; le `Gh` injecté (l.26) reste la seule couture | non |
| `plugins/forge/skills/feature-build/SKILL.md` | argument `--ticket <n>` (story 8), question G5 d'un agent épinglé | l'en-tête `argument-hint` (l.4), l'étape 0.5 (l.40-108, voir Q5), la revendication (l.218), les questions (l.300-335) | non |
| `plugins/forge/skills/qc/SKILL.md` | appel de `merge_grant.py` après ACCEPT sur un chemin protégé ; une relecture à la fois par projet (A65) | contrôle d'état des lignes 11-15 ; fusion l.111-130 ; chemins protégés l.211-222 | non |
| `plugins/forge/skills/feature-design/SKILL.md` | le seuil « 1 000 lignes lisibles » écrit en dur (l.58) devient la clé `ticket-size-max` ; ligne G8 ; étiquettes `zone:` ; appel de `check` et G9 (l.77-89) | `ticket_graph.py` | non |
| `plugins/forge/templates/usine.md` | une ligne par clé de G1 ; le compte « Vingt-quatre clés » (l.22) passe à trente et une | gardé par `tests/test_usine_keys_classified.py`, `tests/test_usine_gardes_docs.py:20`, `tests/test_guard_pr_cap.py:890`, `tests/test_ticket_pr_cap_small.py:148` ; même phrase dans `docs/installation.md:549` | non |
| `docs/usine-autonome.md` (nouveau), `docs/sessions.md`, `README.md`, `CHANGELOG.md` | page de la feature (A88), ligne de `CLAUDE_HANDOFF_RETRY_MINUTES` dans le tableau des variables (`docs/sessions.md:233-241`) | créée par le premier ticket qui ajoute une clé, complétée par chaque ticket pour les siennes | non |

### Carte des modules

Des modules profonds derrière des interfaces étroites. Chaque interface est ce que les autres modules et les tests
voient ; le reste est caché.

| Module | Interface | Ce qu'il cache |
|---|---|---|
| `guard_human_data` | `refusal(event, lines) -> str \| None` ; `main()` | la forme de l'appel `ArtifactData` (action simple ou `batch`, `writes[].collection`), la lecture des lignes `<page> \| <collection>`, le côté prudent sur une ligne ou un événement illisible |
| `agent_identity` | `is_agent_token(env) -> bool` ; `fresh_token(command) -> str` (lève `IdentityError`) ; `git_identity(login, user_id) -> dict[str, str]` | le préfixe `ghs_`, `GH_TOKEN` avant `GITHUB_TOKEN`, l'appel de la commande et son délai, l'adresse `noreply` |
| `agent_lock` | `claim(project, ticket, pid, name, zones) -> Path` (lève `LockHeld`) ; `held(project) -> list[Lock]` ; `release(project, ticket)` ; `Lock.alive` | l'emplacement, la création atomique (`O_CREAT \| O_EXCL`), la réutilisation d'un pid (par `process_start`), Linux et Windows |
| `dispatch_trace` | `write(event, project, **fields)` | le dossier du jour, la liste blanche des champs, l'échec silencieux (une trace qui échoue ne casse pas un tick, comme `refusal_journal.record`) |
| `dispatch` | `tick(project, run, launch, now) -> int` | C06 à C08, l'ordre des étapes, la revendication à trois verrous et son défaire, la relance, les questions dues |
| `merge_grant` | `grant(project, pr, run) -> Outcome` | C03, la tête de la PR, le statut, l'appel de la commande et son délai |
| `handoff_header.other_sessions` | inchangée, `(repo, caller, session) -> list[str]` | C04 s'ajoute dedans : aucun appelant ne change |

## 2. Ports et adapters

Les fonctions pures prennent des valeurs et rendent des valeurs ; les bords sont des appelables injectés, sur le
modèle déjà en place (`Runner = Callable[[list[str], Path], str]` dans `release.py:68` ; `Runner` de
`factory_slo.py:92` ; `Gh` de `ticket_graph.py:26` ; `main(argv, run, now)` de `question_delay.py`, injecté par
`tests/test_question_delay.py:138`).

| Bord | Adapter de production | Couture de test |
|---|---|---|
| `git` (clés sur `origin/main`) | `usine.on_main`, `usine.load` | un vrai dépôt temporaire avec `origin` local, comme `tests/test_guard_git_protected.py` |
| `gh` (issues, PR, statuts, commentaires, étiquettes) | `run(argv, project) -> str`, une fonction par script qui lance `gh` | un `run` injecté qui rend des sorties figées ; pour un test de processus, un faux `gh` en tête de `PATH` |
| lancement de `claude` (agent épinglé, décideur) | `launch(argv, cwd, env) -> int` (le pid), par `subprocess.Popen` et les options de `handoff_relay.detached` | un `launch` injecté qui note l'appel et rend un faux pid ; pour un test de processus, un faux `claude` en tête de `PATH` |
| commande de `agent-token-command`, de `merge-grant`, de `zone-command` | `subprocess.run` avec un délai, dans le module qui la lit | une commande de test (`python -c ...`) écrite dans la clé, qui sort 0, 1, ou autre |
| événement d'outil (`ArtifactData`, `Bash`, outil MCP GitHub) | JSON sur l'entrée standard du hook | `subprocess` du hook avec l'événement sur `stdin`, ou `mock.patch("sys.stdin")` comme `tests/test_guard_pause.py:22-26` |
| questions de processus (pid vivant, heure de départ, parent) | `handoff_header.process_alive`, `process_start`, `parent_pid` (`/proc` sous Linux, Win32 sous Windows) | le pid du test lui-même (vivant) et un pid fini (mort), comme `tests/test_handoff.py` |
| horloge | `now: datetime` passé à `main` | une date figée |
| transcript (hook `Stop`) | fichier JSONL nommé par `transcript_path` de l'événement | un transcript écrit par le test |

Fonctions pures (aucun bord) : C01 (`guard_human_data.refusal`), C02 (`agent_identity.is_agent_token`), le calcul
de C03 une fois la sortie de la commande connue, C04 (le filtre d'une entrée du registre), C05 (l'attente de
l'essai `k`, le tirage étant injecté), C06 à C08 (la sélection d'un tick à partir de listes déjà lues), C09 (le
plus long chemin), la forme d'une ligne G3, G4, G5 et G6.

## 3. Modèle de données

Aucune base de données. L'état vit dans GitHub (étiquettes, assignés, commentaires, statuts, graphe), dans deux
fichiers de clés sur `origin/main`, et dans des fichiers d'état du poste sous `~/.claude/hooks/state`.

**Clés de G1.** Chacune absente rend « sans objet (clé `<nom>` absente) », sans valeur par défaut. Une ligne
répétée là où une seule est attendue fait échouer la commande qui la lit.

| Clé | Fichier | Forme | Lue par |
|---|---|---|---|
| `human-collections` | `docs/agents/usine-gardes.md` | `<page> \| <collection>`, plusieurs lignes | `guard_human_data`, `merge_grant` |
| `agent-token-command` | `docs/agents/usine-gardes.md` | `<commande>`, une ligne | `agent_identity`, `guard_git`, `dispatch`, `merge_grant` |
| `agent-login` | `docs/agents/usine-gardes.md` | `<login>`, une ligne | `guard_git`, `dispatch`, `merge_grant`, `factory_slo` |
| `merge-grant` | `docs/agents/usine-gardes.md` | `<contexte> \| <commande>` avec `{pr}` et `{sha}`, une ligne | `merge_grant`, `guard_git` |
| `dispatch-command` | `docs/agents/usine-gardes.md` | gabarit avec `{feature}`, `{ticket}`, `{name}`, une ligne | `dispatch` |
| `dispatch-relaunch-cap` | `docs/agents/usine-gardes.md` | `<entier>`, une ligne | `dispatch` |
| `agent-slots` | `docs/agents/usine-gardes.md` | `<entier>` supérieur à 0, une ligne | `dispatch` |
| `ignored-session` | `docs/agents/usine.md` | `<nom>` ou `<préfixe>*`, plusieurs lignes | `handoff_header`, `question_stop` |
| `dispatch-tick` | `docs/agents/usine.md` | `<délai>`, unités de `question-default-delay`, une ligne | `dispatch` (présence), la page de `docs/` (minuteur) |
| `ticket-size-max` | `docs/agents/usine.md` | `<lignes>`, une ligne | `feature-design` |
| `zones` | `docs/agents/usine.md` | `<zone>`, plusieurs lignes | `feature-design`, `dispatch`, la PR |
| `zone-command` | `docs/agents/usine.md` | gabarit avec `{path}`, une ligne | la PR (étiquettes de ses fichiers réels) |

Les sept clés de `usine-gardes.md` entrent dans `usine.SENSITIVE_KEYS` ; sans cela, `usine.load` les lirait dans
`usine.md`, que l'agent modifie. Ce dépôt ne déclare aucune de ces clés à la base : tout y reste « sans objet »
jusqu'au geste de l'humain qui les écrit dans `usine-gardes.md` (chemin protégé).

**Verrou local.** Un fichier JSON par ticket, `~/.claude/hooks/state/dispatch/locks/<projet>/<ticket>.json`, le
nom du projet aplati comme `handoff_relay.counter_path` (l.102-104). Champs : `ticket`, `pid`, `start` (valeur de
`process_start`), `name` (le nom passé à `{name}`), `worktree`, `zones`, `since` (date UTC). Créé par
`O_CREAT | O_EXCL` : deux ticks qui se chevauchent ne posent pas deux verrous. Un verrou est mort quand
`process_alive(pid)` est faux ou que `process_start(pid)` diffère de `start` (pid réutilisé). Un verrou illisible
compte pour tenu (côté prudent, comme une entrée illisible du registre, A27).

**Trace G3.** `~/.claude/hooks/state/dispatch/<AAAA-MM-JJ>.jsonl`, une ligne JSON par événement : `date`,
`project`, `event`, puis les champs de l'événement, pris dans une liste blanche par événement :

| `event` | Champs |
|---|---|
| `tick` | `ready`, `free`, `launched`, `reason` (`paused`, `autonomy`, `sans objet`, `gh`) |
| `claim` | `ticket`, `attempt` |
| `relaunch` | `ticket`, `attempt` |
| `cap` | `ticket`, `attempt` |
| `question` | `item`, `case`, `recommendation` (la première ligne, tronquée à 200 caractères), `action` (`post-default`, `remind-human`) |
| `merge-grant` | `pr`, `sha`, `outcome` (`GRANTED`, `WAITING`, `NOT RUN`) |

**Trace G4.** `~/.claude/hooks/state/relay-retry-<projet>-<AAAA-MM-JJ>.jsonl`, à côté des compteurs du relais :
`date`, `project`, `attempt`, `wait_s`, `code`.

**Marqueur G6.** `<!-- forge-dispatch relaunch <n> -->` dans un commentaire du ticket, un par relance. C08 compte
ces marqueurs dans les commentaires du ticket ; le tick ne garde rien d'autre.

**Étiquettes.**

| Étiquette | Qui la pose | Qui la retire |
|---|---|---|
| `agent-claimed` | le tick (revendication), ou `feature-build` sans `--ticket` comme aujourd'hui (`SKILL.md:218`) | le tick (défaire, plafond), l'agent épinglé (question G5) |
| `ready-for-agent` | `question_delay.py route --apply` sur `post-default` d'une issue (A59) ; le découpage | l'agent épinglé (question G5) |
| `needs-info`, `ready-for-human` | l'agent épinglé (question G5), `feature-build` | `route --apply` (`plan_for`, l.279) |
| `needs-your-attention` | le tick (plafond de relance, clé de relance absente), `forge:qc` | l'agent qui la lève en le disant (règle du dépôt) |
| `zone:<zone>` | le découpage (ticket), la PR par `zone-command` | jamais par un script ; une zone hors de `zones` n'est jamais créée |

Toutes sont créées par `gh label create` au premier besoin, par le script qui les pose, sauf `zone:<zone>`, créée
seulement pour une valeur de `zones`.

**Statut de `merge-grant`.** Un statut de commit (`POST repos/{owner}/{repo}/statuses/{sha}`), `context` égal à
la partie gauche de la clé, `state` `success`, posté sous le jeton de l'application, donc par `agent-login`.
`guard_git` ne l'accepte que s'il est sur la tête de la PR et que son `creator.login` est `agent-login`. La
protection de `main` qui l'exige, avec l'application comme source attendue, est un geste de l'humain (H3).

## 4. Frontière de confiance

**Ce qui vient du dehors, et où c'est validé.**

| Entrée | Validée par | Côté prudent |
|---|---|---|
| événement d'outil `ArtifactData` (page, collection, `writes`) | `guard_human_data.refusal`, avant l'appel | événement illisible, ligne de clé illisible : refus (A4, A6) |
| événement d'outil `Bash` ou MCP GitHub | `guard_git`, comme aujourd'hui | échec du garde : refus (`\|\| exit 2`, `"onFailure": "block"`) |
| sortie de `gh` (étiquettes, assignés, statuts, commentaires) | le script qui la lit, en JSON, champs typés | `gh` en échec : le tick sort en 1 et défait la revendication commencée (A46) |
| sortie de la commande de `merge-grant` | `merge_grant` : seul le code compte, 0 ou 1 ; la sortie n'est ni lue comme une instruction ni recopiée | autre code ou délai : `NOT RUN` (A20) |
| sortie de `agent-token-command` | `agent_identity.fresh_token` : une ligne non vide qui commence par `ghs_` | vide, autre préfixe, échec : aucun agent lancé, geste refusé (A12) |
| le clic écrit par l'humain dans sa page | la commande de `merge-grant`, que le projet écrit ; forge ne lit jamais la page lui-même | le clic n'est cru qu'avec `human-collections` (A21) et l'identité des agents (A89) |
| le registre des sessions, les verrous | `handoff_header`, `agent_lock` | entrée illisible : vivante, verrou illisible : tenu |
| le texte d'un commentaire ou d'un ticket (question G5, marqueur G6) | lu comme donnée : le tick ne compte que les marqueurs ; le décideur lit la question | une ligne `Décideur :` absente : la question va à l'humain |

**Qui fait quoi.**

| Acteur | Peut | Ne peut pas |
|---|---|---|
| agent (session, épinglé, sous-agent) | lire toute collection ; écrire les autres collections ; agir sur GitHub sous `agent-login` ; poster le statut de `merge-grant` par `merge_grant.py` | écrire une collection de `human-collections` ; agir en écriture sur GitHub sans jeton `ghs_` quand les clés sont présentes ; fusionner un chemin protégé sans le statut `success` sur la tête |
| humain | écrire ses collections depuis sa page ; écrire `usine-gardes.md` ; fusionner ; installer l'application, le minuteur, la protection de branche | rien n'est retiré à l'humain |
| répartiteur (script sans LLM) | lire les clés, l'état GitHub et les verrous ; revendiquer ; lancer et relancer ; lancer un décideur sur une question due | décider une question ; fusionner ; écrire une clé |

**Pourquoi les clés se lisent sur `origin/main`.** Une PR qui retire une ligne de `human-collections`, ou qui
change `agent-slots`, n'agit pas avant sa fusion (A7) : un agent ne relâche pas une borne en la modifiant dans son
arbre de travail. C'est déjà la règle des clés protégées (`templates/usine.md:33-44`, `usine.load`).

**Le contrôle `ghs_` et ses limites.** C02 dit seulement qu'un jeton d'installation d'application est présent dans
l'environnement de la session. Il ne prouve pas de quelle application il vient (une autre application installée
sur le dépôt passerait), ni qu'un jeton de l'humain n'est pas employé par un autre chemin : un `export GH_TOKEN=...`
ou une affectation en tête de commande dans `Bash` change l'environnement de la commande, pas celui du hook, qui
hérite de celui du processus `claude` (documentation des hooks, section 10). Il ne couvre pas un outil MCP GitHub,
dont le serveur tient son propre jeton (Q4). La preuve d'auteur, a posteriori, est la ligne `agent-identity`
(A15) ; la preuve qui compte pour un chemin protégé est le `creator.login` du statut, que `guard_git` relit.

**T10.** Aucun jeton, aucune clé privée ni commande complète n'entre dans un journal, une trace, un commentaire ou
une sortie. `dispatch_trace.write` n'écrit que les champs de sa liste blanche ; un message d'erreur de
`agent_identity` nomme la commande par sa clé (`agent-token-command`), jamais par son texte ; `merge_grant` ne
recopie pas la sortie de sa commande. Un test par module passe un jeton `ghs_` factice et vérifie qu'il ne figure
dans aucune sortie ni aucun fichier écrit.

**Non-goal.** Un agent qui écrit la base d'une page par un autre canal que l'outil `ArtifactData` (un appel réseau
depuis `Bash`) n'est pas couvert (spec, section 12). La page de `docs/` le dit ; un canal prouvé se traite au
motif `securite`.

## 5. Observabilité

| Question | Métrique, alerte ou attribut de trace | Où c'est émis |
|---|---|---|
| Ça marche ? | le tick lance (A41 : `tick` avec `ready`, `free`, `launched`) | `dispatch.py`, fonction `tick`, par `dispatch_trace.write("tick", ...)` à la fin de chaque tick, lancé ou non |
| Ça marche ? | revendications et relances (A55 : `claim`, `relaunch`, `cap`, `attempt`) | `dispatch.py`, fonctions `claim` et `relaunch`, une ligne après la pose des trois verrous ou le constat du plafond |
| Ça marche ? | essais du relais (A33 : `attempt`, `wait_s`, `code`) | `handoff_relay.py`, nouvelle fonction `retry_trace`, appelée par la boucle d'essai de `relay` (l.393) à chaque essai |
| Ça casse ? | refus du garde des collections (A5 : `guard` `guard_human_data`, `rule` `human-collection`) | `guard_human_data.py`, fonction `main`, par `refusal_journal.record("guard_human_data", reason, RULES, event, verb)` |
| Ça casse ? | PR d'agent sous un autre compte (A15 : ligne `agent-identity`, numérateur et dénominateur, cible 0) | `factory_slo.py`, nouvelle fonction `agent_identity(f: Factory) -> Sli`, appelée par `compute` (l.551), rendue par `report` (l.809) |
| Ça casse ? | geste réservé pris par défaut (A61 : `question` avec `case` et `action`) | `question_delay.py`, fonction `apply` (l.293), par `dispatch_trace.write("question", ...)` : un seul point d'émission, que la question vienne du tick ou du hook `Stop` |
| Que voit-on dans la trace ? | délai p90, interventions de l'humain par ticket fusionné, jetons par PR, chacun avec sa fenêtre et son dénominateur (A84) | `factory_slo.py`, nouvelle sous-commande `baseline` (fonction `run_baseline`, appelée par `main`, l.1319), et `token_audit.py` inchangé ; le commentaire de #340 est posté par l'agent qui lance le relevé |

## 6. Coutures de test

La couture la plus haute : le hook ou le script lancé en processus, un événement JSON sur l'entrée standard, sous
un `HOME` et un `USERPROFILE` temporaires, sans aucune variable `CLAUDE_` ni `GIT_` de la session, avec
`GIT_CONFIG_GLOBAL` et `GIT_CONFIG_SYSTEM` à `os.devnull` (`tests/test_guard_refusals.py:38-39`,
`tests/test_handoff.py:40-44`). Un faux `gh` et un faux `claude` en tête de `PATH` notent leurs appels dans un
fichier et rendent des sorties figées. Ensuite, deux coutures plus basses : `main(argv, run, now)` avec un `run`
et un `launch` injectés, et les fonctions pures de la section 2.

- Chaque test cite son critère dans son nom ou sa docstring : `F-0003 A<n>`.
- Les tests restent des classes `unittest` ; les dossiers temporaires viennent de `tempfile.TemporaryDirectory()`,
  jamais du vrai `HOME`. Aucun test n'écrit dans le vrai `~/.claude` (`tests/support.py:13-25` détourne déjà le
  journal des refus).
- Un test de processus sous un système seulement le dit par `skipUnless`, avec la raison.
- Chaque lancement de la suite, en local comme dans un brief de coder, est borné :
  `ulimit -v 4000000; timeout 600 uv run --no-project --quiet --with pytest==9.2.0 python -m pytest tests`.
- Un garde a un test de son filtre (`ArtifactData` dans `hooks.json`), de son échec fermé (script absent, délai)
  et de sa ligne au journal ; le hook `Stop` a un test de son échec ouvert.
- Le tick a un test par contrôle (C06 à C08), un test de deux ticks de suite sur le même état (A42), et un test
  du défaire quand le deuxième des trois verrous échoue (A51).
- T10 a un test par module qui écrit une trace ou une sortie (section 4).
- Un bon test ici prouve un comportement par l'interface du module (le code de sortie, la ligne écrite, l'appel
  noté par le faux `gh`), jamais par sa structure interne.

## 7. Découpage en tickets

Douze tickets, `feature-tickets: 12`, dans l'ordre que fixe le lot L1 de la spec (section 11), puis L2, le lot
conditionnel et L3. Verdict de `forge:product-owner` (case P2 ; T6 pour les parties du ticket 8) : la coupe en
douze est gardée, le ticket 8 nomme ses trois parties, l'ordre de l'humain reste dans la numérotation. Aucun
prérefactoring : les modules nouveaux s'ajoutent à côté des anciens, et les fonctions touchées (`other_sessions`,
`merge_call_refusal`, `plan_for`) gardent leur interface.

La documentation (EXI-11, A87, A88, T1 à T3) n'a pas de ticket à elle : chaque ticket documente ses propres clés
dans `templates/usine.md`, dans `docs/usine-autonome.md` et, pour une variable, dans `docs/sessions.md`. La page
`docs/usine-autonome.md` est créée par le premier ticket qui ajoute une clé. Chaque ticket qui ajoute une clé de
`usine-gardes.md` change aussi le compte « Vingt-quatre clés » du gabarit et de `docs/installation.md:549`, et les
trois tests qui le lisent (section 1) : les tickets 1, 2, 3 et 8 se croisent sur cette phrase, qu'une remise à
jour en mode sync règle.

| # | Ticket | Couvre | Fichiers | Taille estimée | PR | Blocked by | Protégé |
|---|---|---|---|---|---|---|---|
| 1 | garde des collections de l'humain | EXI-17 : A1 à A8 | `hooks/guard_human_data.py`, `hooks/hooks.json`, `hooks/usine.py`, `templates/usine.md`, `docs/usine-autonome.md`, `docs/installation.md`, `tests/test_guard_human_data.py` | 550 | 1 | aucun | oui |
| 2 | identité des agents (partie 1) | EXI-18 : A9 à A16 | `hooks/agent_identity.py`, `hooks/guard_git.py`, `hooks/usine.py`, `scripts/factory_slo.py`, gabarit, page, tests | 900 | 2 | aucun | oui |
| 3 | `merge_grant.py` et acceptation par `guard_git` | EXI-18 : A17 à A23, A89 | `scripts/merge_grant.py`, `scripts/dispatch_trace.py`, `hooks/guard_git.py`, `skills/qc/SKILL.md`, gabarit, page, tests | 750 | 1 | 1, 2 | oui |
| 4 | passes ignorées et nouvel essai du relais | EXI-01 : A24 à A28 ; EXI-02 : A29 à A33 | `hooks/handoff_header.py`, `hooks/handoff_relay.py`, `hooks/agent_lock.py` (lecture, sous réserve de Q1), `docs/sessions.md`, gabarit, page, tests | 750 | 2 | aucun | non |
| 5 | pont du hook `Stop` | EXI-03 : A34 à A39 | `hooks/question_stop.py`, `hooks/hooks.json`, page, tests | 550 | 1 | aucun | oui |
| 6 | relevé de base avant le répartiteur | story 18 : A84 à A86 | `scripts/factory_slo.py` (`baseline`, champ `author`), page, tests ; le commentaire de #340 | 450 | 1 | aucun | non |
| 7 | entrée épinglée, question G5, `route` rend le ticket prêt | EXI-13 : A47 à A50 ; EXI-15 : A57, A59 | `skills/feature-build/SKILL.md`, `scripts/question_delay.py`, page, tests | 400 | 1 | aucun | non |
| 8 | `dispatch.py` : tick, revendication, relance, questions dues | EXI-12 : A40 à A46 ; EXI-14 : A51 à A56 ; EXI-15 : A58, A60 à A62 | `scripts/dispatch.py`, `hooks/agent_lock.py`, `scripts/dispatch_trace.py`, `scripts/question_delay.py` (trace de `apply`), `hooks/usine.py`, gabarit, page, tests | 2 200 | 3 | 2, 4, 6, 7 | non |
| 9 | agents en parallèle | EXI-08 : A63 à A66 | `scripts/dispatch.py`, `skills/qc/SKILL.md`, page, tests | 700 | 1 | 8 | non |
| 10 | lot 2 : taille, zones, chaînes | EXI-06 : A72 à A75 ; EXI-07 : A76 à A79 ; EXI-09 : A80, A81 | `skills/feature-design/SKILL.md`, `scripts/ticket_graph.py`, gabarit, page, `CHANGELOG.md`, tests | 1 500 | 3 | aucun | non |
| 11 | conditionnel : clé `suite`, reprise légère | EXI-04 : A67 à A69 ; EXI-05 : A70, A71 | `hooks/handoff_header.py` (`check`), `hooks/handoff_relay.py` (invite de reprise), `docs/sessions.md`, tests | 600 | 2 | 6 | non |
| 12 | lot 3 : runners auto-hébergés seulement | EXI-16 : A82, A83 | le workflow fourni, `tests/`, le commentaire de #340 | 250 | 1 | 6 | non |

La taille est une estimation en lignes lisibles (code, tests, documents écrits à la main, sans fichier généré ni
verrou), faite sur les fichiers voisins lus à la base (par exemple `guard_pause.py`, 51 lignes,
`refusal_journal.py`, 140 lignes, `ticket_graph.py`, 147 lignes) ; aucune n'est mesurée. Chaque corps de ticket
porte la ligne `Taille estimée : <n> lignes lisibles` (G8), chaque PR au plus 1 000 lignes lisibles, au plus trois
PR par ticket, sous le plafond `ticket-pr-cap` (6, `docs/agents/usine-gardes.md:60`).

Précisions par ticket :

- **Ticket 1.** Fichier nouveau sous le préfixe `guard_` et `hooks.json` : la PR va à l'humain (H1). Le garde
  refuse sur `set`, `update`, `str_replace`, `delete` et `batch` (une opération de `writes` suffit) ; `get`,
  `list`, `query` et `profiles` passent. L'action `str_replace` n'est pas nommée par A1 : c'est une écriture, et le
  garde la refuse (côté prudent).
- **Ticket 2, deux PR.** (a) `agent_identity.py`, refus de `guard_git` sans jeton `ghs_` (A11, A12, A16), les deux
  clés dans `SENSITIVE_KEYS`, gabarit et page. (b) l'identité git de l'application (A14), la ligne
  `agent-identity` de `factory_slo.py` (A15), la tenue du jeton au-delà de 60 minutes (A13, sous réserve de Q3).
  A9 et A10 se prouvent dans la partie (b) par la fonction qui construit l'environnement de l'agent, que le
  ticket 8 appelle. `guard_git.py` : la PR va à l'humain.
- **Ticket 3.** A89 appartient à EXI-18 et ce ticket la couvre : les plages de la spec aux lignes 256 et 386
  (« A9 à A23 ») l'omettent, la spec n'est pas modifiée ici. `merge_grant.py` crée `dispatch_trace.py` (événement
  `merge-grant`) ; le ticket 8 l'étend. `guard_git.py` : la PR va à l'humain. La story 3 ne s'active qu'aux deux
  conditions de la spec (section 17) : le code se livre, la clé `merge-grant` reste absente de ce dépôt jusqu'au
  geste de l'humain.
- **Ticket 4, deux PR.** (a) EXI-01 dans `other_sessions` (A24 à A28). (b) EXI-02 dans le relais (A29 à A33),
  la variable `CLAUDE_HANDOFF_RETRY_MINUTES` dans `docs/sessions.md`. La forme de C04 attend la réponse à Q1 :
  telle que la spec l'écrit, A24 ne peut pas passer pour une passe `claude -p` (section 10).
- **Ticket 5.** `hooks.json` : la PR va à l'humain. Le hook échoue ouvert (aucun `\|\| exit 2` ; la
  documentation dit que `"onFailure"` est sans effet sur `Stop`). Son attente est bornée par le `timeout` de son
  entrée (Q6).
- **Ticket 6.** Le relevé compte les interventions de l'humain par ticket fusionné (spec, section 22) : il lit les
  événements d'étiquette (`needs-your-attention` posée) et l'auteur de la fusion, que `factory_slo` ne lit pas
  aujourd'hui. A85 et A86 se rendent aux dates de la spec (2026-12-16, 2027-01-15) par la même sous-commande.
- **Ticket 7.** `--ticket` ne change rien sans l'argument (A50). Le traitement de l'étape 0.5 en mode épinglé
  attend Q5.
- **Ticket 8, trois PR**, chacune verte seule :
  - (8a) le tick en lecture seule : clés, `agent-autonomy` sur `origin/main`, `.claude/PAUSED`, tickets prêts
    dans l'ordre de `factory_slo.py queue`, places libres, ligne `tick`, codes de sortie. Couvre A41, A43, A44,
    A45, et la sélection de A40 sans lancement. Crée `agent_lock.py` en entier (ou le complète si le ticket 4 en a
    posé la lecture). Environ 800 lignes.
  - (8b) revendication à trois verrous, lancement par `dispatch-command` avec l'environnement de l'identité
    (ticket 2), défaire, relance depuis la branche et la PR, marqueur G6, plafond. Couvre A40 (lancement), A42,
    A46, A51 à A56. Environ 850 lignes.
  - (8c) questions dues : `question_delay.py due`, lancement du décideur sans interface (Q7), `route --apply`,
    ligne `question` émise par `question_delay.apply`. Couvre A58, A60 à A62. Environ 550 lignes.
- **Ticket 9.** Un arbre de travail par agent (Q9), une zone par agent (C07), une relecture à la fois par projet
  par un verrou de `forge:qc` du même module `agent_lock` (A65), `agent-slots` mal formée (A66).
- **Ticket 10, trois PR.** (a) `ticket-size-max` et G8 dans `feature-design` (A72 à A75) ; l'entrée du
  `CHANGELOG.md` dit que ce projet perd la coupe à 1 000 lignes (A74). (b) `zones`, `zone-command`, étiquettes du
  ticket et de la PR, test qu'aucun script de la CI ne lit `zone:` (A76 à A79). (c) `CHAIN` dans
  `ticket_graph.py check` et lecture de G9 (A80, A81). Le ticket est prêt dès le départ ; s'il était servi trop
  tôt par la file, ajouter `Blocked by` 8 reste une option, notée et non faite.
- **Tickets 11 et 12.** Publiés sans `ready-for-agent`. Le corps de chacun dit quel verdict de C11 l'ouvre :
  « non » pour le 11, « oui » pour le 12. Après le point de décision du 2026-12-16, le gagnant reçoit
  `ready-for-agent` et le perdant est fermé « not planned ». Tous deux sont bloqués par 6, dont le relevé fonde
  le verdict.

Prêts dès le départ : 1, 2, 4, 5, 6, 7 et 10. Le ticket 3 attend 1 et 2 ; le ticket 8 attend 2, 4, 6 et 7 (la
spec, ligne 386, place la mesure de base A84 avant EXI-12) ; le ticket 9 attend 8.

**Plus longue chaîne : 3 tickets** (6 > 8 > 9, et de même 2 > 8 > 9, 4 > 8 > 9, 7 > 8 > 9 ; 1 > 3 et 2 > 3 en
comptent 2 ; 6 > 11 et 6 > 12 en comptent 2). Elle ne dépasse pas le seuil de C09 : aucune ligne
`Chaîne justifiée`.

## 8. ADR déclenchés

Aucun. Le dépôt n'a pas de dossier `docs/adr/` ; les décisions de cette feature vivent dans la spec (section 18,
décisions prises par défaut) et dans le cadrage (section 7), et celles du design dans la séance de design.

| ADR | Décision | Statut |
|---|---|---|

## 9. Décisions prises pendant la construction

| Ticket | Décision | Par | Source |
|---|---|---|---|

## 10. Ce qui n'est pas vérifié

Questions de la section 21 de la spec, relevées le 2026-11-28 :

- **Nom et `kind` d'une passe `claude -p` nommée.** Observé sur le poste (Claude Code 2.1.332, `claude --version`,
  2026-11-28) dans `~/.claude/sessions/<pid>.json` d'une passe lancée par `claude -p --name ...` : `name` est la
  valeur de `--name` (`nameSource: user`), `kind` vaut `interactive`, `entrypoint` vaut `sdk-cli`. Une session
  `--bg` porte `kind: bg` et `entrypoint: cli` ; la session interactive de l'humain `kind: interactive` et
  `entrypoint: cli`. C04 et A25 excluent toute session `interactive` : telle que la spec l'écrit, A24 ne peut pas
  passer pour une passe `claude -p`. Deux textes acceptés se contredisent : la question va à
  `forge:staff-engineer` (Q1). Non vérifié : les valeurs sous Windows, et celles de l'extension d'éditeur ou de
  l'application de bureau.
- **`gh auth git-credential` et `git push` avec `GH_TOKEN`.** Vérifié sur le poste (gh 2.102.0, 2026-11-28) :
  `gh auth git-credential get`, appelé avec `GH_TOKEN=ghs_...` factice, rend `username=x-access-token` et ce
  jeton comme mot de passe ; l'aide de crédit de git du poste est `gh auth git-credential`. Un `git push` prend
  donc `GH_TOKEN` là où cette aide est configurée (`gh auth setup-git`), et seulement là : non vérifié sous Windows
  ni avec un autre gestionnaire de crédit. La documentation de gh (https://cli.github.com/manual/gh_help_environment,
  lue le 2026-11-28) dit que `GH_TOKEN` passe avant `GITHUB_TOKEN` et avant les crédits stockés ; elle ne parle
  pas de l'aide de crédit.
- **L'outil `ArtifactData` comme seul canal d'écriture de la base d'une page.** Non vérifiable. Le schéma de
  l'outil, lu dans cette session le 2026-11-28, nomme les actions (`get`, `list`, `query`, `profiles`, `set`,
  `update`, `str_replace`, `delete`, `batch`) et les champs (`url`, `collection`, `doc_id`, `writes[].collection`).
  Non vérifié : la valeur exacte de `tool_name` et la forme de `tool_input` dans un vrai événement `PreToolUse`
  de cet outil ; le ticket 1 la relève sur un événement réel avant d'écrire le filtre.
- **Délai maximal d'un hook `Stop`.** Documentation des hooks (https://code.claude.com/docs/en/hooks, lue le
  2026-11-28) : délai par défaut de 600 secondes pour un hook `command`, réglable par `timeout`, sans maximum
  écrit ; `"onFailure"` est sans effet sur `Stop` ; plafond de 8 continuations successives, remis à zéro à chaque
  appel d'outil, réglable par `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` ; champ `stop_hook_active` dans l'entrée. Non
  vérifié sur une vraie session : une attente longue dans le hook (Q6).
- **Case H1 et clic de fusion.** Tranché par l'humain le 2026-11-28 (spec, section 20, points ouverts), aux conditions de la
  section 17.

Autres faits :

- **Héritage de l'environnement par un hook.** Documentation des hooks (même page, même date) : un hook hérite de
  l'environnement du processus parent, sauf les variables `OTEL_*` et ce que retire
  `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` ; la page ne dit pas si `GH_TOKEN` en fait partie. Non vérifié : que l'outil
  `Bash` passe `GH_TOKEN` à ses commandes.
- **Jeton d'installation.** Documentation GitHub
  (https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app,
  lue le 2026-11-28) : il expire après une heure ; un nouveau format `ghs_APPID_JWT` est en déploiement, le préfixe
  `ghs_` reste.
- **Source attendue d'un statut exigé.** Documentation GitHub
  (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets,
  lue le 2026-11-28) : une règle « Require status checks to pass » peut exiger une application comme source, et
  un statut posé par une autre personne ou intégration bloque la fusion.
- **Drapeaux de `claude`.** `claude --help` (2.1.332, 2026-11-28) liste `--agent`, `-n/--name`, `-w/--worktree`,
  `--bg`, `--permission-mode`, `-p/--print`. Non vérifié : qu'une passe `-p --agent forge:staff-engineer` charge
  l'agent d'un plugin, et l'emplacement de l'arbre créé par `-w`.
- **Non vérifiés.** La forme du champ `author` de `gh pr list --json` pour une PR ouverte par une application
  (`app/<slug>` ou `<slug>[bot]`) ; l'identifiant numérique de l'adresse `noreply` du compte de l'application ;
  l'existence d'un champ `creator.login` dans la sortie de `commits/{sha}/status` pour un statut d'application ;
  tout comportement sous Windows et sous macOS ; la tenue d'un agent détaché quand le tick qui l'a lancé sort
  (le modèle de `handoff_relay.detached` est éprouvé pour le relais, pas pour une passe `-p`).
- **Lu avant une compaction du contexte.** Les numéros de ligne de `guard_git.py` (sauf ceux relus par `grep` :
  888, 1416, 2271, 2516, 2724, 2797, 2814, 2859), de `usine.py` (sauf 34-43), de `release.py`, de
  `refusal_journal.py`, de `handoff_relay.py` (sauf 95-125, 393, 487) et de `skills/qc/SKILL.md` ont été lus à la
  base `c2ecef9` dans cette même session, avant une compaction ; ils n'ont pas été relus après.
