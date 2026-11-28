---
feature: F-0003
document: spec
statut: en-revue
destinataires: ikoro-labs (humain de la clé `accepting-human`, relit au titre du métier ; acceptation par `/forge:feature-accept`, tapée par lui ou lancée par le modèle sous la clé `agent-autonomy`), puis l'agent qui implémente ; forge:qc relit
base: b543993
date: 2026-11-28
---

# F-0003 : spécification

Le pourquoi est dans `cadrage.md` (accepté le 2026-11-28, `accepte_via: agent-autonomy`, PR #391). Ici :
**ce qui se construit**, et comment on saura que c'est fait. Les décisions des deux agents décideurs et de
l'humain sont dans `seances/2026-11-28-ikoro-labs-cadrage.md` et dans la section 7 du cadrage ; la spec les
reprend sans les redire. Les choix que ni le cadrage ni la séance ne tranchent sont à la section 18, tranchés
le 2026-11-28 par `forge:staff-engineer` et `forge:product-owner`, sauf le point 5, tranché par l'humain
(sections 17 et 20).

Clés lues dans `docs/agents/usine.md` (base `b543993`) : `product-source`, `source-author`, `glossary` et
`domain-skill` sont absentes (les lignes 126 et 127 disent l'absence des trois premières, `source-author`
n'y figure pas). La source de la spec est donc le cadrage accepté, dont la
section 3 reprend chaque élément.

## 1. Stories

Dix-neuf stories : une par exigence du cadrage, deux pour EXI-18 (l'identité, puis le clic qui autorise une
fusion), une pour la mesure du point de décision ; EXI-10, remplacée, est tenue par les stories 2 et 3 ;
EXI-11, la documentation, est la story 19 et les critères transverses de la section 10. Dans l'ordre des lots
du cadrage (section 11).

1. En tant qu'**humain du projet**, je veux qu'aucun agent ne puisse écrire dans les collections de données de
   ma page que je nomme, pour qu'une ligne écrite sous mon identité prouve mon geste et qu'un clic puisse
   porter une autorisation.
2. En tant qu'**humain du projet**, je veux que les agents agissent sur GitHub sous l'identité d'une
   application à eux, sans mon jeton, pour que leurs gestes ne se confondent plus avec les miens.
3. En tant qu'**humain du projet**, je veux autoriser d'un clic sur ma page la fusion d'une PR qui touche un
   chemin protégé, contrôlé par une vérification obligatoire de GitHub, pour fusionner sans rien taper.
4. En tant que **session au travail**, je veux que les passes courtes sans interface que nomme une clé ne
   comptent pas comme sessions vivantes, pour que mon relais ne soit pas refusé à tort.
5. En tant que **session au travail**, je veux qu'un relais refusé parce qu'une autre session tourne réessaie
   seul, dans une borne, pour qu'un projet ne reste pas sans session faute d'un geste de l'humain.
6. En tant qu'**humain du projet**, je veux qu'une session longue qui attend la réponse à sa propre question
   la fasse trancher au délai `question-default-delay` au lieu de s'arrêter, pour qu'aucune question ne reste
   sans suite tant que des sessions longues tournent.
7. En tant qu'**humain du projet**, je veux un répartiteur sans LLM qui, à chaque tick, lance un agent sans
   interface par ticket prêt et par place libre, pour que les tickets avancent sans session longue ni relais.
8. En tant que **répartiteur**, je veux une entrée de forge épinglée à un seul ticket, pour que l'agent lancé
   ne prenne que lui et s'arrête à la fin de sa PR.
9. En tant que **répartiteur**, je veux revendiquer un ticket par trois verrous et relancer un agent mort sur
   le même ticket, dans un plafond, pour qu'aucun ticket ne soit pris deux fois ni abandonné en silence.
10. En tant qu'**humain du projet**, je veux qu'une question d'un agent court soit tranchée par l'agent
    décideur au délai, puis que le ticket redevienne prêt, pour qu'une question ne bloque pas un ticket.
11. En tant qu'**humain du projet**, je veux plusieurs agents en parallèle, chacun dans son arbre de travail,
    sans deux agents sur la même zone et avec une relecture en série, pour réduire le temps mort entre deux PR.
12. En tant que **session au travail**, je veux que la passation nomme sa suite ou dise qu'il n'y en a pas,
    vérifiée par `handoff_header.py check`, pour qu'un relais ne liste plus un ticket prêt sans le lancer
    (conditionnelle : seulement sur le « non » du point de décision).
13. En tant que **session au travail**, je veux une reprise de relais plus légère, mesurée avant et après,
    pour qu'un relais n'atteigne plus sa limite avant de lancer ses coders (conditionnelle : seulement sur le
    « non » du point de décision).
14. En tant que **product-owner qui découpe**, je veux un seuil de taille déclaré par une clé, pour couper en
    parties du même ticket tout ticket trop gros avant qu'il n'atteigne le plafond de PR.
15. En tant que **répartiteur et juge**, je veux des étiquettes `zone:<zone>` posées au découpage et
    recopiées sur la PR depuis ses fichiers réels, pour séparer les agents par zone sans piloter la CI.
16. En tant que **product-owner qui découpe**, je veux qu'une chaîne de blocage de plus de 3 tickets soit
    relevée et justifiée dans le design, pour réduire l'attente de tickets bloquants.
17. En tant qu'**humain du projet**, je veux, sur le « oui » du point de décision, que les agents tournent sur
    des runners auto-hébergés seulement, après une mesure de ce que cela coûte, pour libérer le poste sans
    payer GitHub Actions.
18. En tant qu'**humain du projet**, je veux un relevé du délai p90, des interventions de l'humain par ticket
    et des jetons par PR, avant le répartiteur puis pendant l'essai, pour trancher le point de décision du
    2026-12-16 sur des chiffres.
19. En tant qu'**humain d'un projet consommateur**, je veux chaque clé nouvelle documentée dans le gabarit
    et dans une page de `docs/`, pour l'écrire sans lire le code.

## 2. Critères d'acceptation

Chaque critère deviendra un test qui cite `F-0003 A<n>`, relié dans la recette. Une clé absente rend « sans
objet (clé `<nom>` absente) », jamais `PASS`, et aucune clé ne prend de valeur par défaut. Les noms de clés,
de scripts et de variables sont ceux de la section 18 (décisions par défaut), sauf mention.

| # | Story | Étant donné | Quand | Alors |
|---|---|---|---|---|
| A1 | 1 | la clé `human-collections` de `usine-gardes.md` sur `origin/main`, une ligne `<page> \| <collection>` | un agent (session principale ou sous-agent) appelle l'outil qui écrit la base d'une page publiée (`ArtifactData`, action `set`, `update`, `delete` ou `batch`) sur cette page et cette collection | l'appel est refusé (code 2) ; le message nomme la page et la collection et dit qu'une ligne de cette collection ne vient que de l'humain |
| A2 | 1 | la même ligne, un appel `batch` dont une seule opération vise la collection nommée | l'agent l'envoie | tout l'appel est refusé, aucune opération ne passe |
| A3 | 1 | la même ligne | un agent lit la collection (`get`, `list`, `query`) ou écrit une autre collection de la page | l'appel passe |
| A4 | 1 | une ligne de la clé sans ` \| ` ou avec une partie vide | un agent écrit dans une page quelconque | l'écriture est refusée et le message cite la ligne fautive (côté prudent) |
| A5 | 1 | un refus du garde | il refuse | une ligne entre au journal des refus : `guard` `guard_human_data`, `rule` `human-collection`, les champs des autres gardes, jamais le contenu de l'écriture |
| A6 | 1 | le garde qui échoue (erreur, script absent) ou qui dépasse son `timeout` | un agent écrit dans la base d'une page | l'écriture est refusée (`\|\| exit 2` et `"onFailure": "block"`) |
| A7 | 1 | une PR qui retire une ligne de `human-collections` dans l'arbre de travail | un agent écrit la collection avant la fusion | le refus tient : la clé se lit sur `origin/main` |
| A8 | 1 | la clé `human-collections` absente | un agent écrit dans la base d'une page | l'appel passe ; la page de `docs/` dit « sans objet (clé `human-collections` absente) » |
| A9 | 2 | les clés `agent-token-command` et `agent-login` de `usine-gardes.md` | le répartiteur lance un agent | l'environnement de l'agent porte un jeton d'installation de l'application (préfixe `ghs_`) tiré de la commande, et aucun autre jeton GitHub |
| A10 | 2 | les mêmes clés | un agent ouvre une PR, la commente ou la fusionne | l'auteur de chaque geste sur GitHub est `agent-login` |
| A11 | 2 | les mêmes clés | un agent fait un geste d'écriture sur GitHub (`git push`, `gh pr`, `gh issue`, `gh api` en écriture, outil MCP GitHub) sans jeton `ghs_` dans son environnement | `guard_git` refuse et dit que le geste se fait sous l'identité des agents |
| A12 | 2 | la commande de `agent-token-command` qui échoue ou n'imprime rien | le répartiteur ou un agent demande un jeton | aucun agent n'est lancé, ou le geste est refusé ; le message nomme la commande ; le jeton de l'humain n'est jamais pris à la place |
| A13 | 2 | un agent lancé depuis plus de 60 minutes (durée de vie d'un jeton d'installation) | il fait un geste d'écriture | le geste passe sous `agent-login`, sans geste de l'humain |
| A14 | 2 | un commit écrit par un agent | il est poussé | son auteur git est l'identité de l'application (`<id>+<login>@users.noreply.github.com`), et le push n'est pas refusé |
| A15 | 2 | la clé `agent-login` et 30 jours de PR | `factory_slo.py report` tourne | il rend une ligne `agent-identity` : le nombre de PR qui portent la section `Rapport d'agent` et dont l'auteur n'est pas `agent-login`, avec son dénominateur ; cible 0 |
| A16 | 2 | les clés `agent-token-command` ou `agent-login` absentes | un agent agit sur GitHub | rien ne change ; `guard_git` ne refuse rien au titre de l'identité ; la ligne `agent-identity` rend « sans objet (clé `agent-login` absente) » |
| A17 | 3 | la clé `merge-grant` (`<contexte> \| <commande>`), une PR qui touche un `protected-path`, ACCEPT de `forge:qc`, et la commande qui sort 0 pour `{pr}` et le SHA de tête `{sha}` | `merge_grant.py` tourne (au tick, ou dans `forge:qc`) | un statut `<contexte>` à `success` est posté sur `{sha}` sous `agent-login`, puis la PR est fusionnée selon `merge-method` |
| A18 | 3 | la même PR, la commande qui sort 1 (aucun clic) | `merge_grant.py` tourne | aucun statut `success`, aucune fusion ; la PR garde `needs-your-attention` |
| A19 | 3 | un clic donné pour un SHA, puis un nouveau push sur la PR | `merge_grant.py` tourne | le clic ne vaut pas pour la nouvelle tête : aucun `success` sur elle, la fusion attend un nouveau clic |
| A20 | 3 | la commande qui échoue autrement (code autre que 0 ou 1, délai) | `merge_grant.py` tourne | aucun `success` ; la sortie dit `NOT RUN` et la raison |
| A21 | 3 | `merge-grant` présente et `human-collections` absente | `merge_grant.py` tourne | il ne poste jamais `success` et dit que le clic ne peut pas être prouvé sans la clé `human-collections` |
| A22 | 3 | le statut `<contexte>` à `success` sur la tête | un agent fusionne la PR qui touche un `protected-path` | `guard_git` laisse passer ; sans ce statut sur la tête, il refuse comme aujourd'hui |
| A89 | 3 | `merge-grant` présente et `agent-token-command` ou `agent-login` absente (les agents agissent sous le jeton de l'humain) | `merge_grant.py` tourne | il ne poste jamais `success` et dit que le clic ne peut pas être prouvé tant que les agents tiennent le jeton de l'humain |
| A23 | 3 | la clé `merge-grant` absente | une PR touche un `protected-path` | sa fusion reste à l'humain, comme aujourd'hui ; `merge_grant.py` rend « sans objet (clé `merge-grant` absente) » |
| A24 | 4 | la clé `ignored-session` de `usine.md` (un nom par ligne, exact, ou préfixe fini par `*`) et une autre session vivante du dépôt dont le `name` du registre correspond | `handoff_header.py sessions` tourne | elle n'est pas listée ; `handoff_relay.py` ne refuse pas en code 6 pour elle, et `sessions_notice.py` ne la signale pas |
| A25 | 4 | une session au `name` qui correspond, mais dont le registre dit `kind` `interactive` | `sessions` tourne | elle est listée : le mode de lancement ne peut qu'ajouter un refus |
| A26 | 4 | une passe `claude -p` dont le `name` ne correspond à aucune ligne | `sessions` tourne | elle est listée : une passe longue est une vraie session |
| A27 | 4 | une entrée du registre illisible | `sessions` tourne | elle compte encore comme session vivante (côté prudent) |
| A28 | 4 | la clé `ignored-session` absente | `sessions` tourne | la sortie est celle d'aujourd'hui |
| A29 | 5 | la variable `CLAUDE_HANDOFF_RETRY_MINUTES` à 30 et un relais refusé en code 6 | l'autre session finit après 4 minutes | le relais réessaie seul (recul de 30 s, doublé, plafonné à 300 s, gigue de plus ou moins 20 %), démarre le successeur au plus 300 s après la fin de l'autre session, et le compteur du jour ne monte qu'une fois |
| A30 | 5 | la même variable, une autre session qui ne finit pas | 30 minutes passent | le relais s'arrête en code 6 ; le message dit le nombre d'essais et le temps attendu |
| A31 | 5 | un refus en code 2, 3, 4 ou 5 | le relais est refusé | il ne réessaie pas |
| A32 | 5 | la variable absente, ou une valeur hors de 1 à 1440 | un relais est refusé en code 6 | il ne réessaie pas, comme aujourd'hui ; une valeur invalide est signalée telle quelle |
| A33 | 5 | des essais de relais | chaque essai part | une ligne de trace par essai : date, projet, numéro d'essai, attente, code rendu |
| A34 | 6 | `question-default-delay` à `10 min`, une session longue qui a posé dans ce passage une étiquette d'attente (`ready-for-human`, `needs-info`) sur un ticket ou une PR encore ouvert | elle finit son tour avant l'échéance | elle ne s'arrête pas ; au plus 1 minute après l'échéance, le hook `Stop` lui fait passer la question à l'agent décideur et appliquer `question_delay.py route --apply` |
| A35 | 6 | un verdict `RESERVED`, `DOMAIN` ou `TECHNICAL`, ou un `DECIDED` non réversible | `route` rend `remind-human` | le rappel est posté, et l'arrêt suivant passe : un geste réservé n'est jamais pris par défaut |
| A36 | 6 | une question qui porte déjà un `Rappel (question-default-delay)` | la session finit son tour | elle est exclue, l'arrêt passe |
| A37 | 6 | 8 blocages successifs de l'arrêt | la session finit son tour une neuvième fois | l'arrêt passe, et la sortie dit que le plafond de 8 est atteint |
| A38 | 6 | une session dont le `name` correspond à `ignored-session` (un agent du répartiteur), ou un sous-agent | elle finit son tour | le hook la laisse s'arrêter : la story 10 la couvre |
| A39 | 6 | la clé `question-default-delay` absente, ou le hook qui échoue | la session finit son tour | l'arrêt passe (le hook échoue ouvert) |
| A40 | 7 | les clés `dispatch-tick`, `dispatch-command` et `agent-slots` à 1, `agent-autonomy` à `on`, deux tickets prêts (ouverts, `ready-for-agent`, sans bloqueur ouvert, sans assigné, sans `agent-claimed`) | `dispatch.py tick <projet>` tourne | il revendique le premier ticket dans l'ordre de `factory_slo.py queue`, lance un agent par `dispatch-command` et rend la main en moins de 30 s, sans attendre l'agent |
| A41 | 7 | aucun ticket prêt, ou aucune place libre | le tick tourne | il ne lance rien ; une ligne de trace dit tickets prêts, places libres, agents lancés |
| A42 | 7 | deux ticks de suite sur le même état GitHub, l'agent du premier vivant | le second tick tourne | il ne lance rien de plus : le tick ne garde aucun état, il relit l'assigné, l'étiquette et le verrou |
| A43 | 7 | la clé `dispatch-tick`, `dispatch-command` ou `agent-slots` absente | le tick tourne | il rend « sans objet (clé `<nom>` absente) », ne lance rien et sort en 0 : le projet garde la session longue |
| A44 | 7 | la clé `agent-autonomy` absente ou autre que `on` sur `origin/main` | le tick tourne | il ne lance aucun agent et dit pourquoi |
| A45 | 7 | `.claude/PAUSED` présent dans le projet | le tick tourne | il ne lance rien et cite la raison du fichier |
| A46 | 7 | un appel `gh` qui échoue pendant le tick | le tick tourne | il sort en code non nul, ne lance rien, et défait une revendication commencée |
| A47 | 8 | `/forge:feature-build F-NNNN --ticket 42` et d'autres tickets prêts | l'agent tourne | il ne mène que le ticket 42 (`forge:coder`, puis `forge:qc`) et s'arrête quand la PR est fusionnée ou son verdict posté ; il ne revendique aucun autre ticket |
| A48 | 8 | le ticket 42 fermé, bloqué, ou ni prêt ni revendiqué pour ce lancement | l'agent démarre | il s'arrête sans rien écrire et dit pourquoi |
| A49 | 8 | le ticket 42 avec une branche ou une PR ouverte d'un agent précédent | l'agent démarre | il reprend depuis cette branche et cette PR, sans en ouvrir de nouvelles |
| A50 | 8 | `/forge:feature-build F-NNNN` sans `--ticket` | il tourne | son comportement est celui d'aujourd'hui |
| A51 | 9 | un ticket prêt et une place libre | le tick le revendique | le ticket porte un assigné (`agent-login`, sinon le compte du jeton), l'étiquette `agent-claimed` et un verrou local (fichier du pid et de l'heure de départ de l'agent) avant le lancement ; si l'un des trois échoue, rien n'est lancé et les deux autres sont défaits |
| A52 | 9 | un ticket revendiqué dont l'agent est mort (verrou d'un pid mort, ou absent alors que l'assigné est `agent-login`), ouvert, sans PR fusionnée | le tick suivant tourne | un agent est relancé sur le même ticket depuis sa branche, sa PR et le commentaire du ticket ; un commentaire du ticket porte le numéro de la relance |
| A53 | 9 | les relances d'un ticket au plafond de `dispatch-relaunch-cap` | l'agent meurt de nouveau | il n'est pas relancé ; le ticket perd `agent-claimed` et l'assigné, gagne `needs-your-attention`, et un commentaire dit le nombre de relances |
| A54 | 9 | un ticket revendiqué dont le verrou tient un pid vivant | le tick tourne | aucun second agent n'est lancé pour lui |
| A55 | 9 | une revendication ou une relance | elle a lieu | une ligne de trace : date, ticket, raison (`claim`, `relaunch`, `cap`), numéro d'essai |
| A56 | 9 | la clé `dispatch-relaunch-cap` absente | un agent meurt | il n'est pas relancé ; le ticket reçoit `needs-your-attention` et la sortie dit « sans objet (clé `dispatch-relaunch-cap` absente) » |
| A57 | 10 | un agent épinglé qui a une question | il la pose | il commente le ticket au format G5 (question, recommandation, décideur), pose `needs-info`, retire `ready-for-agent`, libère son verrou et s'arrête |
| A58 | 10 | cette question due selon `question_delay.py due` | le tick tourne | il lance le décideur que nomme le commentaire, sans interface, puis `question_delay.py route --apply` sur son verdict |
| A59 | 10 | un verdict qui donne `post-default` sur un ticket | `route --apply` agit | le ticket regagne `ready-for-agent` en plus du commentaire de décision ; le tick suivant relance un agent qui reprend depuis la branche et la PR |
| A60 | 10 | un verdict qui donne `remind-human` | `route --apply` agit | le ticket ne redevient pas prêt et garde `needs-your-attention` ; aucun agent n'est relancé |
| A61 | 10 | une question appliquée au délai | elle l'est | une ligne de trace : date, ticket, case de la matrice, recommandation, action (`post-default` ou `remind-human`) |
| A62 | 10 | la clé `question-default-delay` absente | une question est posée | le tick ne décide rien ; le ticket attend l'humain |
| A63 | 11 | `agent-slots` à 3 et cinq tickets prêts de zones distinctes | le tick tourne | trois agents sont lancés, chacun dans son arbre de travail (trois chemins distincts) |
| A64 | 11 | deux tickets prêts qui portent la même étiquette `zone:` | le tick tourne | un seul des deux est lancé ; l'autre attend que la zone se libère |
| A65 | 11 | deux PR prêtes pour la relecture au même moment | les agents arrivent à `forge:qc` | une seule relecture tourne à la fois pour le projet ; l'autre attend son tour sans échec du contrôle d'état de `forge:qc` |
| A66 | 11 | la clé `agent-slots` qui n'est pas un entier supérieur à 0 | le tick tourne | il ne lance rien et cite la ligne fautive |
| A67 | 12 | sur le « non » du point de décision, une passation sans clé d'en-tête `suite` | `handoff_header.py check` tourne | il sort en 2 et nomme la clé |
| A68 | 12 | `suite` qui ne vaut ni `#<n>` ni `aucune` | `check` tourne | il sort en 2 et cite la valeur |
| A69 | 12 | `suite: #42` ou `suite: aucune` | `check` tourne | il sort en 0 et imprime `suite=#42` ou `suite=aucune` en plus de sa ligne d'aujourd'hui |
| A70 | 13 | sur le « non » du point de décision, au moins 5 relais qui lancent un coder | le plancher est mesuré par `token_audit.py` | le plancher (jetons au premier lancement d'un coder) est commenté sur #340 avec ses 5 valeurs, sa date et sa source |
| A71 | 13 | l'invite de reprise réduite à la passation et aux règles | 5 relais tournent | le plancher médian baisse d'au moins 50 % par rapport à A70 ; la mémoire, les anciennes passations et les transcripts ne se lisent qu'à la demande |
| A72 | 14 | la clé `ticket-size-max` à `1000` et un ticket estimé à 1 400 lignes lisibles | le découpage tourne | le ticket est coupé en parties du même ticket (`Refs #n`), chacune estimée à 1 000 lignes au plus ; aucun ticket nouveau n'est ouvert |
| A73 | 14 | un ticket publié | on le lit | il porte la ligne `Taille estimée : <n> lignes lisibles` |
| A74 | 14 | la clé `ticket-size-max` absente | le découpage tourne | la taille est estimée et écrite ; la coupe rend « sans objet (clé `ticket-size-max` absente) » ; aucun seuil n'est écrit en dur dans le skill ; l'entrée de `CHANGELOG.md` de la version qui l'apporte dit que ce projet perd la coupe à 1 000 lignes |
| A75 | 14 | des tickets publiés avant la clé, sans PR ouverte ni fusionnée, et d'autres en vol | le découpage repasse | les premiers sont redécoupés au seuil ; ceux en vol gardent leurs règles |
| A76 | 15 | les clés `zones` (une zone par ligne) et `zone-command` | le découpage publie un ticket | il porte une étiquette `zone:<zone>` par zone qu'il touche, prise dans `zones` ; une zone hors de la liste est refusée, jamais créée |
| A77 | 15 | une PR ouverte | `zone-command` range chacun de ses fichiers changés | la PR porte les étiquettes `zone:` de ses fichiers réels, même quand elles diffèrent de celles du ticket |
| A78 | 15 | les scripts de forge que lancent la CI et `forge:qc-gate` | un test les lit | aucun ne lit une étiquette `zone:` |
| A79 | 15 | la clé `zones` ou `zone-command` absente | un ticket ou une PR est publié | aucune étiquette `zone:` n'est posée ; la sortie dit « sans objet (clé `<nom>` absente) » |
| A80 | 16 | quatre tickets enchaînés par `blocked_by` (une chaîne de plus de 3) | `ticket_graph.py check` tourne | il imprime une ligne `CHAIN` qui liste la chaîne, et sort en 1 tant que le design ne porte pas la ligne `Chaîne justifiée : <tickets> \| <raison>` qui la nomme |
| A81 | 16 | une chaîne de 3 tickets | `check` tourne | aucune ligne `CHAIN` |
| A82 | 17 | le « oui » du point de décision | la spec du lot 3 s'écrit | un commentaire de #340 donne, pour chacun des cinq points (coût en jetons et en runner, hooks de forge dans Actions, charge des runners, secrets, blocage des déclencheurs tiers sur un dépôt public), un chiffre avec sa source ou « non mesuré » avec sa raison |
| A83 | 17 | un workflow que forge fournit pour lancer des agents | un test le lit | chaque job déclare des étiquettes `self-hosted` ; aucune étiquette de runner hébergé par GitHub (`ubuntu-latest`, `windows-latest`, `macos-latest`) |
| A84 | 18 | 30 jours de tickets avant le répartiteur, puis les tickets de l'essai | le relevé tourne | un commentaire de #340 donne le délai p90 (`factory_slo.py`, objectif `lead-time p90`), les interventions de l'humain par ticket fusionné (section 22) et les jetons par PR (`token_audit.py`), chacun avec sa fenêtre et son dénominateur |
| A85 | 18 | le relevé de A84 au 2026-12-16 | la règle du point de décision s'applique | le verdict est « oui » si et seulement si le délai p90 baisse, les interventions par ticket ne montent pas et le journal des questions appliquées (A61) ne porte aucun geste d'une case `H` ; sinon « non » |
| A86 | 18 | le relevé du 2027-01-15 | il tourne | il compte les tickets publiés après la clé `ticket-size-max` qui ont atteint `ticket-pr-cap` ; cible 0 |
| A87 | 19 | le gabarit `plugins/forge/templates/usine.md` | on le lit | chaque clé nouvelle (G1) y a sa ligne, son format, sa place (`usine.md` ou `usine-gardes.md`) et son rendu « sans objet » |
| A88 | 19 | la page `docs/usine-autonome.md` | on la lit | elle dit chaque clé, chaque geste de l'humain (installer l'application, protéger la branche par le contexte de `merge-grant`, installer le minuteur), la trace et les alertes ; `docs/sessions.md` a la ligne de `CLAUDE_HANDOFF_RETRY_MINUTES` |

## 3. Éléments de la source

La clé `product-source` est absente de `usine.md` (ligne 127) : la source de la spec est le cadrage accepté,
et `source_ids.py` rend « sans objet (clé `product-source` absente) ». Ses éléments identifiés sont les
dix-huit exigences de sa section 2 ; le titre `F-0003` du cadrage est l'identifiant de la feature, non une
exigence. Les éléments sans identifiant d'origine reçoivent ici un identifiant stable, avec la ligne de la
source qu'ils désignent ; le cadrage n'est pas modifié.

| Identifiant | Élément (résumé) | Tenu par |
|---|---|---|
| EXI-17 | un hook refuse à tout agent l'écriture dans les collections de l'humain nommées par une clé | story 1, A1 à A8 ; C01 |
| EXI-18 | identité GitHub des agents par une application, sans le jeton de l'humain ; fusion autorisée d'un clic par une vérification obligatoire ; installation par l'humain | story 2, A9 à A16 ; story 3, A17 à A23 et A89 ; C02, C03 |
| EXI-01 | une passe sans interface nommée par une clé ne compte pas comme session vivante ; le mode de lancement en complément | story 4, A24 à A28 ; C04 |
| EXI-02 | nouvel essai d'un relais refusé, recul plafonné et gigue, borne par une variable de passation | story 5, A29 à A33 ; C05 |
| EXI-03 | pont : un hook `Stop` fait trancher la question de la session au délai, gestes réservés exclus | story 6, A34 à A39 |
| EXI-12 | répartiteur : tick sans état, bibliothèque standard, minuteur du poste, un agent par ticket prêt et place libre | story 7, A40 à A46 ; C06, C07 |
| EXI-13 | entrée épinglée à un ticket | story 8, A47 à A50 |
| EXI-14 | revendication à trois verrous, relance depuis la branche et la PR, plafond de relances | story 9, A51 à A56 ; C08 |
| EXI-15 | questions par le répartiteur : `due`, décideur, `route`, ticket remis prêt, gestes réservés exclus | story 10, A57 à A62 |
| EXI-08 | agents en parallèle : places par une clé, un arbre de travail par agent, zones distinctes, relecture en série | story 11, A63 à A66 ; C07 |
| EXI-04 | conditionnelle : la passation nomme sa suite, vérifiée par `check` | story 12, A67 à A69 ; lot conditionnel (section 11) |
| EXI-05 | conditionnelle : reprise légère après mesure du plancher | story 13, A70 et A71 ; lot conditionnel |
| EXI-06 | taille estimée au découpage, seuil par une clé, parties du même ticket, redécoupe des non commencés | story 14, A72 à A75 ; C10 |
| EXI-07 | étiquettes `zone:` : vocabulaire et commande par deux clés, recopiées sur la PR, jamais lues par la CI | story 15, A76 à A79 |
| EXI-09 | chaîne de blocage de plus de 3 tickets justifiée dans le design | story 16, A80 et A81 ; C09 |
| EXI-16 | lot 3 sur le « oui » : runners auto-hébergés seulement, cinq mesures avant sa spec | story 17, A82 et A83 ; lot L3 |
| EXI-10 | remplacée par EXI-18 : l'identité qui prouve l'humain est son compte, une fois que les agents ont la leur | tenue par EXI-18 : stories 2 et 3, A9 à A23 (A21 lie le clic à EXI-17) |
| EXI-11 | documentation : gabarit, page de `docs/`, `docs/sessions.md`, `CHANGELOG.md` | story 19, A87 et A88 ; T1 à T4 (section 10) |
| CAS-1 | cadrage, section 1, « Le cas d'usage unique » : du ticket prêt à la fusion sans saisie, clic pour un chemin protégé | section 7, parcours 2 à 5 ; A17, A40, A47, A58 |
| CLE-1 | cadrage, section 2, « Les clés nouvelles » : noms fixés dans la spec, écrites par l'humain, « sans objet » sans valeur par défaut | G1 ; T5 ; A8, A16, A23, A28, A43, A62, A74, A79 |
| PER-1 | cadrage, section 2, « Ce qui revient à forge, au projet, au poste » | section 8 ; section 14 |
| LIV-1 | cadrage, section 2, « Déjà livré, hors de ce cadrage » | section 9 ; A74 (le seuil écrit en dur par la PR #384 passe à la clé) |
| HOR-1 | cadrage, section 2, « Hors périmètre » | section 14 |
| OBS-1 | cadrage, section 4, ligne « Quelle métrique prouve que ça marche » | story 18, A84 à A86 ; A15 |
| OBS-2 | cadrage, section 4, ligne « Quelle alerte si ça casse » | A15 (identité), A53 (plafond de relances), A52 (revendiqué sans agent vivant) ; T8 |
| OBS-3 | cadrage, section 4, ligne « Que voit-on dans une trace » | A5, A33, A41, A55, A61 ; G3 |
| RSQ-1 | cadrage, section 5 : le hook refuse une écriture légitime | A3 ; section 12 |
| RSQ-2 | un agent garde le jeton de l'humain | A11, A12, A15 ; section 12 |
| RSQ-3 | la vérification du clic est contournable | A19, A21, A22 ; section 12 |
| RSQ-4 | deux agents sur le même ticket | A42, A51, A54 |
| RSQ-5 | un agent mort laisse un ticket revendiqué | A52, A53 |
| RSQ-6 | un agent court coûte plus de jetons qu'une session longue | A84, A85 |
| RSQ-7 | les agents du répartiteur bloquent les relais des sessions longues | A24 ; ordre du lot L1 |
| RSQ-8 | une recommandation appliquée au délai prend un geste réservé | A35, A60, A85 |
| RSQ-9 | deux relectures `forge:qc` en même temps | A65 |
| RSQ-10 | le hook `Stop` boucle ou bloque une session | A36, A37, A39 |
| RSQ-11 | l'étiquette de zone finit par piloter la CI | A78 |
| ARR-1 | cadrage, section 8, vérification du 2026-12-05 | section 11 (L1, identité et relais) |
| ARR-2 | vérification du 2026-12-12 : répartiteur sur un projet consommateur, plancher d'un agent épinglé | section 11 ; A84 |
| ARR-3 | point de décision du 2026-12-16 | A85 ; section 11 (lot conditionnel, L3) |
| ARR-4 | vérification du 2027-01-15 : lot 2 fusionné, aucun ticket nouveau au plafond | A86 ; section 11 (L2) |
| GES-1 | cadrage, section 7, « Gestes réservés à l'humain (H3) » | section 8 (humain) ; section 7, parcours 1 ; A88 |

Aucun élément n'est écarté : la clé `source-author` est absente de `usine.md`, aucun agent n'écarte un élément,
et la spec ne porte aucune ligne d'exclusion.

## 4. Exigences atomiques (`EXI-nn`)

Niveau de preuve : P principe du projet, O piège observé, S souhait d'une source unique (une décision de
l'humain). Les sources de chaque fait sont dans le cadrage (sections 1, 2 et 7).

| Identifiant | Exigence | Critère mesurable | Classement | Niveau de preuve | Lot |
|---|---|---|---|---|---|
| EXI-17 | garde des collections de l'humain | 100 % des écritures d'agent dans une collection nommée refusées, `batch` compris (A1, A2) ; 0 refus en lecture (A3) ; refus si le garde échoue (A6) | obligatoire | O (un projet refuse un clic pour autorisation) | L1, en tête |
| EXI-18 | identité GitHub des agents ; fusion autorisée d'un clic | 0 PR d'agent sous un autre compte que `agent-login` sur 30 jours (A15) ; un clic vaut pour un seul SHA (A19) ; 0 `success` sans `human-collections` (A21) | obligatoire | O (PR #384 non fusionnable sans `--admin`) | L1, après EXI-17 |
| EXI-01 | passes ignorées | une session nommée et non `interactive` n'est pas listée (A24) ; une passe non nommée l'est (A26) | obligatoire | O (projet sans session à partir de 12:05 UTC le 2026-11-28) | L1 |
| EXI-02 | nouvel essai du relais | successeur démarré au plus 300 s après la fin de l'autre session (A29) ; arrêt à la borne (A30) | obligatoire | O (même fait) | L1 |
| EXI-03 | pont : question au délai | décideur saisi au plus 1 min après l'échéance (A34) ; plafond de 8 blocages (A37) | obligatoire | O (`due` lu par `forge:feature-build` seul) | L1, pont |
| EXI-12 | répartiteur | tick rendu en moins de 30 s (A40) ; deuxième tick sans lancement de plus (A42) | obligatoire | S (architecture approuvée le 2026-11-28) | L1 |
| EXI-13 | entrée épinglée | 0 ticket revendiqué en plus du ticket épinglé (A47) | obligatoire | P (`forge:feature-build` ne sait pas épingler) | L1 |
| EXI-14 | revendication et reprise | 3 verrous posés avant lancement, ou aucun (A51) ; relances bornées par la clé (A53) | obligatoire | P | L1 |
| EXI-15 | questions par le répartiteur | ticket de nouveau prêt après `post-default` (A59) ; 0 relance après `remind-human` (A60) | obligatoire | O (`route` ne rend pas l'étiquette du ticket prêt) | L1 |
| EXI-08 | agents en parallèle | `agent-slots` agents dans autant d'arbres distincts (A63) ; 1 agent par zone (A64) ; 1 relecture à la fois (A65) | obligatoire | O (14 % du délai entre deux PR, audit privé) | L1, en dernier |
| EXI-04 | suite nommée dans la passation | `check` sort en 2 sans `suite` (A67) | conditionnelle | O (six relais sans lancement) | conditionnel |
| EXI-05 | reprise légère | plancher médian en baisse d'au moins 50 % sur 5 relais (A71) | conditionnelle | O (environ 56 k jetons au départ d'un relais) | conditionnel |
| EXI-06 | taille au découpage | 0 partie au-dessus de `ticket-size-max` (A72) ; 0 ticket nouveau au plafond de PR au 2027-01-15 (A86) | obligatoire | O (10 tickets sur 19 au plafond) | L2 |
| EXI-07 | étiquettes de zone | étiquettes de la PR égales aux zones de ses fichiers réels (A77) ; 0 lecture par la CI (A78) | obligatoire | S (approuvé par l'humain le 2026-11-28) | L2 |
| EXI-09 | chaînes courtes | toute chaîne de plus de 3 tickets listée `CHAIN` (A80) | souhaitable | O (27 % du délai en attente de bloquants ; seuil non mesuré) | L2 |
| EXI-16 | runners auto-hébergés | 5 mesures sur 5 publiées avant la spec du lot (A82) ; 0 étiquette de runner hébergé (A83) | conditionnelle | S (architecture approuvée) | L3 |
| EXI-10 | remplacée par EXI-18 | les critères d'EXI-18 (A9 à A23) | remplacée | S (décision de l'humain du 2026-11-28) | L1, par EXI-18 |
| EXI-11 | documentation | chaque clé de G1 dans le gabarit (A87) ; une page de `docs/` (A88) ; une entrée de `CHANGELOG.md` par version (T3) | obligatoire | P (`.claude/rules/forge.md`) | tous |

## 5. Contrôles codés (`Cnn`)

| Identifiant | Calcul exact | Tolérance par défaut | Effet |
|---|---|---|---|
| C01 | garde `human-collections` : pour un appel d'écriture de l'outil de base d'une page, la page de l'appel égale à la partie gauche d'une ligne et une collection visée (une opération d'un `batch` suffit) égale à sa partie droite, comparaisons exactes | aucune | refus (code 2), ligne au journal des refus |
| C02 | identité d'un geste d'écriture GitHub d'un agent : un jeton `GH_TOKEN` ou `GITHUB_TOKEN` présent qui commence par `ghs_` | aucune | sans lui, refus de `guard_git` |
| C03 | clic valable : la commande de `merge-grant` sort 0 pour `{pr}` et `{sha}`, `{sha}` étant la tête de la PR au moment du calcul, et la clé `human-collections` est présente | aucune | statut `success` posté sur `{sha}` ; sinon aucun `success` |
| C04 | session ignorée : `name` du registre égal à une ligne de `ignored-session`, ou commençant par la partie avant `*` d'une ligne finie par `*`, et `kind` différent de `interactive` | aucune | la session n'est pas listée par `sessions` |
| C05 | attente avant l'essai `k` (à partir de 0) : `min(30 × 2^k, 300)` secondes, multipliée par un tirage uniforme dans [0,8 ; 1,2] ; arrêt quand le total attendu dépasse `CLAUDE_HANDOFF_RETRY_MINUTES` × 60 | la borne de la variable | code 6 rendu à la borne |
| C06 | ticket prêt : ouvert, `ready-for-agent`, aucun bloqueur ouvert dans le graphe, aucun assigné, sans `agent-claimed` ; ordre de `factory_slo.py queue` | aucune | candidat du tick |
| C07 | places libres : `agent-slots` moins les verrous locaux du projet tenus par un pid vivant ; un candidat dont une étiquette `zone:` est tenue par un agent vivant est sauté | aucune | nombre d'agents lancés au tick |
| C08 | relances d'un ticket : nombre de commentaires du ticket qui portent le marqueur de relance (G6) ; relance permise si ce nombre est inférieur à `dispatch-relaunch-cap` | la valeur de la clé | au plafond : `needs-your-attention`, revendication levée |
| C09 | chaîne : plus long chemin du graphe `blocked_by` entre les tickets de la feature, en tickets ; listée si elle compte plus de 3 tickets | 3, non mesuré (cadrage) | ligne `CHAIN`, sortie 1 sans justification dans le design |
| C10 | taille : estimation en lignes lisibles (code, tests, documents écrits à la main, sans fichier généré ni verrou) comparée à `ticket-size-max` | la valeur de la clé | au-dessus : coupe en parties du même ticket |
| C11 | point de décision : délai p90 de l'essai inférieur à celui de la base, interventions par ticket de l'essai inférieures ou égales à celles de la base, 0 geste d'une case `H` au journal des questions appliquées | aucune | « oui » : lot L3 ouvert, lot conditionnel abandonné ; « non » : l'inverse |

## 6. Gabarits et conventions (`Gn`)

| Identifiant | Structure | Règles |
|---|---|---|
| G1 | clés nouvelles : dans `usine-gardes.md`, `human-collections` (`<page> \| <collection>`), `agent-token-command` (`<commande>`), `agent-login` (`<login>`), `merge-grant` (`<contexte> \| <commande>`), `dispatch-command` (gabarit avec `{feature}`, `{ticket}`, `{name}`), `dispatch-relaunch-cap` (`<entier>`), `agent-slots` (`<entier>`) ; dans `usine.md`, `ignored-session` (`<nom>` ou `<préfixe>*`), `dispatch-tick` (`<délai>`, unités de `question-default-delay`), `ticket-size-max` (`<lignes>`), `zones` (`<zone>`), `zone-command` (gabarit avec `{path}`) | chacune écrite par l'humain du projet, documentée dans le gabarit ; une clé qui borne un garde, ou ce que le répartiteur lance sans l'humain et combien de fois, va dans `usine-gardes.md` ; absente : « sans objet » ; une ligne répétée là où une seule est attendue fait échouer la commande qui la lit |
| G2 | message de refus de `guard_human_data` : `Blocked by the forge plugin (guard_human_data): <page> \| <collection> ...`, puis la raison | dit que la collection ne s'écrit que depuis la page de l'humain ; jamais le contenu de l'écriture |
| G3 | ligne de trace du répartiteur, une ligne JSON par événement dans `~/.claude/hooks/state/dispatch/<AAAA-MM-JJ>.jsonl` : `date`, `project`, `event` (`tick`, `claim`, `relaunch`, `cap`, `question`, `merge-grant`), puis les champs de l'événement | jamais un jeton, une commande complète ni le corps d'un commentaire ; l'écriture du journal ne change aucune décision |
| G4 | ligne de trace d'un essai de relais : `date`, `project`, `attempt`, `wait_s`, `code` | même dossier d'état que les compteurs du relais |
| G5 | commentaire de question d'un agent épinglé : une ligne `Question :`, une ligne `Recommandation :`, une ligne `Décideur : staff-engineer` ou `Décideur : product-owner` | une question par commentaire ; le décideur se choisit selon la matrice (technique ou produit) ; une ligne `Décideur :` absente ou d'une autre valeur vaut `staff-engineer` |
| G6 | marqueur de relance dans le commentaire d'un ticket : `<!-- forge-dispatch relaunch <n> -->` | un commentaire par relance ; le tick compte les marqueurs, il ne garde aucun état |
| G7 | clé d'en-tête de passation `suite` : `#<n>` ou `aucune` (lot conditionnel) | lue par `handoff_header.py check` |
| G8 | ligne de taille d'un ticket : `Taille estimée : <n> lignes lisibles` | écrite au découpage, sur chaque ticket et chaque partie |
| G9 | justification d'une chaîne dans le design : `Chaîne justifiée : #a > #b > #c > #d \| <raison>` | une ligne par chaîne listée `CHAIN` |

## 7. Déroulé pas à pas

**Parcours 1 : première installation sur un projet.**
1. L'humain installe l'application GitHub des agents sur le dépôt, écrit `agent-token-command`, `agent-login`,
   `human-collections` et `merge-grant` dans `usine-gardes.md`, puis exige le contexte de `merge-grant`, posté
   par l'application, dans la protection de `main` (gestes H3).
2. Il écrit `ignored-session` et `dispatch-tick` dans `usine.md`, `dispatch-command`, `dispatch-relaunch-cap` et
   `agent-slots` dans `usine-gardes.md`, et installe
   le minuteur du poste qui lance `dispatch.py tick <projet>` à la période de `dispatch-tick` (geste H3).
3. Au premier tick, la trace dit tickets prêts, places et agents lancés ; sans une clé, le tick dit laquelle.

**Parcours 2 : un ticket, du prêt à la fusion.**
1. Au tick, le répartiteur revendique le ticket prêt (trois verrous) et lance `dispatch-command`, qui ouvre
   `/forge:feature-build F-NNNN --ticket <n>` sans interface, sous `agent-login`.
2. L'agent code (`forge:coder`), ouvre la PR, la fait relire (`forge:qc`, en série) ; sur ACCEPT hors chemin
   protégé, la PR est fusionnée, et l'agent s'arrête.
3. Le tick suivant voit la place libre ; le ticket est fermé par sa PR.

**Parcours 3 : une question.**
1. L'agent commente sa question au format G5, pose `needs-info` et s'arrête.
2. Au délai, le tick lance le décideur, puis `route --apply` : sur `post-default`, le ticket redevient prêt et
   un agent reprend depuis la branche et la PR ; sur `remind-human`, le ticket attend l'humain.

**Parcours 4 : un agent mort.**
1. Le tick voit un ticket revendiqué dont le verrou tient un pid mort.
2. Il relance un agent sur le même ticket, compte la relance (G6) ; au plafond, `needs-your-attention`.

**Parcours 5 : une PR qui touche un chemin protégé.**
1. `forge:qc` rend ACCEPT ; la PR garde `needs-your-attention`.
2. L'humain clique « Fusionner » sur sa page ; la ligne du clic ne peut venir que de lui (story 1).
3. Au tick, `merge_grant.py` lit le clic pour la tête de la PR, poste le statut `success`, et l'application
   fusionne ; un nouveau push avant la fusion demande un nouveau clic.

**Parcours 6 : une session longue, tant qu'il en tourne (pont).**
1. Au relais, une passe du répartiteur nommée par `ignored-session` ne bloque pas le successeur ; une vraie
   session vivante fait réessayer le relais dans la borne de `CLAUDE_HANDOFF_RETRY_MINUTES`.
2. Une session qui finit son tour sur sa propre question est retenue par le hook `Stop` jusqu'au délai, puis
   fait trancher la question par le décideur.

## 8. Rôles

| Rôle | Fait | Ne fait pas |
|---|---|---|
| humain du projet | écrit les clés, installe l'application, le minuteur et la protection de branche (H3), clique « Fusionner » sur sa page, tranche ce qui lui est réservé | ne tape rien dans une session pour un ticket ordinaire |
| répartiteur (`dispatch.py`) | lit l'état GitHub et les verrous, revendique, lance et relance les agents, fait trancher les questions dues, poste le statut du clic | n'appelle aucun LLM lui-même ; ne garde aucun état entre deux ticks ; ne lance rien sans `agent-autonomy` à `on` |
| agent épinglé | mène un seul ticket (`forge:coder` puis `forge:qc`) jusqu'à la PR, pose sa question au format G5, s'arrête | ne prend aucun autre ticket ; n'écrit pas les collections de l'humain ; n'agit pas sous le compte de l'humain |
| agent décideur | tranche une question due selon la matrice | ne prend pas un geste d'une case `H` |
| session longue | travaille comme aujourd'hui tant que le projet n'a pas la clé du répartiteur | ne compte pas les passes nommées comme sessions vivantes |
| projet consommateur | tient la page, ses collections, son bouton « Fusionner » et la commande de `merge-grant` ; mène le premier essai | ne modifie pas le plugin |
| poste | tient le minuteur, la supervision et les règles `autoMode.allow` | ne porte aucune valeur que le plugin devinerait |

## 9. Décisions prises et leur date

| Date | Décision | Par qui |
|---|---|---|
| 2026-11-24 | idée ouverte : l'usine mène seule un ticket, l'humain reprend la main par interrupteur | ikoro-labs (`idee.md`) |
| 2026-11-28 | une feature L, trois lots ordonnés, sans nouvelle issue de suivi ; hors périmètre et leurs destinations | `forge:product-owner`, P2 (séance, tours 2 et 4) |
| 2026-11-28 | passes ignorées par une clé de noms, mode de lancement en complément ; nouvel essai borné du relais | `forge:staff-engineer`, T2, T4 |
| 2026-11-28 | question au délai par un hook `Stop`, plafond de 8 ; touche `hooks.json`, fusion humaine | `forge:staff-engineer`, T5, H1 |
| 2026-11-28 | clés de seuil de taille, de zones et de places ; chaîne de plus de 3 tickets justifiée au design | `forge:staff-engineer`, T4, T6, T2 |
| 2026-11-28 | taille au découpage et étiquettes de zone : principe approuvé (ordre de grandeur 1 000 lignes) | ikoro-labs (#340, commentaire 7237809110) |
| 2026-11-28 | architecture « un agent court par ticket », répartiteur local d'abord, runners auto-hébergés ensuite | ikoro-labs (#340, commentaire 7239304262) |
| 2026-11-28 | la cible est l'option principale ; EXI-04 et EXI-05 conditionnelles ; EXI-03 pont ; mesure principale délai p90 et interventions | `forge:product-owner`, P1, P2, P3 |
| 2026-11-28 | tick sans état sous `plugins/forge/scripts/`, entrée épinglée, revendication à trois verrous, reprise depuis la branche et la PR, relecture en série | `forge:staff-engineer`, T2, T4, T6 |
| 2026-11-28 | deux correctifs d'identité en tête du lot 1 ; EXI-18 tranche EXI-10 | ikoro-labs (#340, commentaire 7239359496) |
| 2026-11-28 | cadrage accepté (PR #391), dates d'arrêt de sa section 8 fixées par l'acceptation | `/forge:feature-accept`, `accepte_via: agent-autonomy` |
| 2026-11-28 | décisions par défaut de la spec : 1 à 4, 6 à 9, 12 à 14, 17 à 19 confirmées ; 10 changée (trois clés du répartiteur dans `usine-gardes.md`) | `forge:staff-engineer`, T2, T4, T5 |
| 2026-11-28 | décisions par défaut de la spec : 11, 15, 18 (nom de la page) confirmées ; 16 changée (interventions comptées par étiquette et par fusion) | `forge:product-owner`, P1, P3 |
| 2026-11-28 | point 5 (fusion d'un chemin protégé sur un clic vérifié) réservé à l'humain | `forge:staff-engineer`, H1, H3, H4 |
| 2026-11-28 | point 5 : oui, actif aux deux conditions de la section 17 | ikoro-labs (réponse relayée par une autre de ses sessions) |

## 10. Critères transverses

- **T1.** Chaque clé nouvelle (G1) a sa ligne dans `plugins/forge/templates/usine.md` (A87).
- **T2.** Une page de `docs/` traite du répartiteur, de l'identité et du clic ; le `README.md` la résume et la
  renvoie ; `docs/sessions.md` a la ligne de `CLAUDE_HANDOFF_RETRY_MINUTES` (A88).
- **T3.** Une entrée de `CHANGELOG.md` ouvre chaque version publiée, par zone (Hooks, Agents, Skills, Tests,
  Gestes humains).
- **T4.** Chaque comportement ajouté a son test dans `tests/`, qui cite `F-0003 A<n>` ; les tests isolent
  `HOME` et `USERPROFILE` et ne passent aucune variable `CLAUDE_` de la session.
- **T5.** Une clé absente rend « sans objet (clé `<nom>` absente) » ; aucune clé n'a de valeur par défaut.
- **T6.** Le contenu de `plugins/forge/` ne cite ni numéro d'ADR, ni nom de personne, ni nom de projet, ni
  chemin propre à un projet ; les noms de page et de collection vivent dans les clés.
- **T7.** Un garde de rôle ou de commande nouveau ou changé (`guard_human_data`, `guard_git`) échoue fermé
  (`|| exit 2`, `"onFailure": "block"`) ; le hook `Stop` de la story 6 et le répartiteur échouent ouverts
  pour la session, fermés pour un lancement (rien n'est lancé sur un doute).
- **T8.** Chaque alerte du cadrage a sa ligne lisible : écriture refusée (A5), PR d'agent sous un autre compte
  (A15), ticket au plafond de relances (A53), ticket revendiqué sans agent vivant (A52).
- **T9.** Un changement de `hooks.json` ou d'un `guard_` est un chemin protégé : sa fusion revient à l'humain
  (H1), ou au clic de la story 3 une fois celle-ci livrée et activée aux conditions de la section 17.
- **T10.** Aucun jeton, aucune clé privée ni aucune commande complète n'entre dans un journal, une trace, un
  commentaire ou une sortie.

## 11. Lots et leur gel

| Lot | Contenu | Gelé le |
|---|---|---|
| L1 | dans l'ordre : EXI-17 (A1 à A8), EXI-18 et EXI-10 (A9 à A23), EXI-01 (A24 à A28), EXI-02 (A29 à A33), EXI-03 (A34 à A39), EXI-12 (A40 à A46), EXI-13 (A47 à A50), EXI-14 (A51 à A56), EXI-15 (A57 à A62), EXI-08 (A63 à A66) ; la mesure de base de la story 18 (A84) avant EXI-12 | à l'acceptation de la spec |
| conditionnel | EXI-04 (A67 à A69), EXI-05 (A70, A71) : construits seulement sur le « non » du point de décision ; sur le « oui », abandonnés, et la recette le dit | à l'acceptation de la spec |
| L2 | EXI-06 (A72 à A75), EXI-07 (A76 à A79), EXI-09 (A80, A81) ; A86 au 2027-01-15 | à l'acceptation de la spec |
| L3 | EXI-16 (A82, A83), sur le « oui » du point de décision (A85) ; sa spec détaillée rouvre ce document après les mesures de A82 | à l'acceptation de cette révision |

EXI-11 se tient dans chaque lot (T1 à T3). Les dates d'arrêt sont celles du cadrage (section 8) : 2026-12-05
(identité, EXI-01 et EXI-02), 2026-12-12 (répartiteur sur un projet consommateur), 2026-12-16 (point de
décision), 2027-01-15 (lot 2).

## 12. Comment elle peut échouer

| Risque | Mécanisme | Parade |
|---|---|---|
| refus d'une écriture légitime | une passe de rafraîchissement de la page écrit une collection nommée | seules les collections de la clé sont fermées, page par page (A3) ; la trace dit laquelle |
| écriture par un autre canal | un agent écrit la base d'une page autrement que par l'outil de base (un appel réseau depuis Bash) | non couvert par ce garde, dit dans la page de `docs/` et en non-goal ; A21 garde au moins que le clic n'est cru qu'avec la clé ; un canal prouvé se traite au motif `securite` |
| jeton de l'humain encore utilisé | `gh` lit le trousseau de l'humain quand `GH_TOKEN` manque | A11 refuse un geste d'écriture sans jeton `ghs_` ; A15 relève toute PR d'agent sous un autre compte |
| clic rejoué ou détourné | un clic donné pour une ancienne tête vaut pour un nouveau push | C03 lie le clic au SHA de tête (A19) ; la protection de branche n'accepte le contexte que de l'application |
| deux agents sur un ticket | deux ticks se chevauchent | trois verrous posés avant lancement, relus à chaque tick (A42, A51, A54) |
| ticket abandonné | l'agent meurt sans PR | relance depuis la branche et la PR, plafond, puis `needs-your-attention` (A52, A53) |
| coût en jetons | un agent court relit plus de contexte qu'une session longue | jetons par PR mesurés avant et pendant l'essai (A84) ; la règle du point de décision (A85) |
| relais bloqués par le répartiteur | ses passes comptent comme sessions vivantes | EXI-01 avant EXI-12 dans L1 (A24) |
| geste réservé pris par défaut | une recommandation touche une case `H` | `route` ne poste `post-default` que sur un `DECIDED` réversible (A35, A60) ; A85 en fait une condition du « oui » |
| boucle du hook `Stop` | la session est retenue sans fin | exclusion des questions rappelées (A36), plafond de 8 (A37), échec ouvert (A39) |
| conflits entre agents parallèles | deux tickets touchent les mêmes fichiers sans étiquette de zone | une zone, un agent (A64) ; sans étiquette, le conflit se rattrape par le mode sync du coder (section 18) |
| zone qui pilote la CI | un job lit l'étiquette | A78 le garde par un test |

## 13. Pièges et parades observés

| Identifiant | Piège | Parade |
|---|---|---|
| PG1 | rien ne distingue un clic de l'humain d'une écriture d'agent : un projet consommateur refuse le clic comme autorisation (#340, commentaire 7239359496) | A1 à A8, puis A21 |
| PG2 | la PR #384, acceptée par `forge:qc`, n'a pas pu être fusionnée sur le « oui » de l'humain sans `--admin` (même commentaire) | A17 à A22 |
| PG3 | une passe sans interface compte comme session vivante : un projet sans session au travail à partir de 12:05 UTC le 2026-11-28 (#340, commentaire 7239037009) | A24 à A28, A29 |
| PG4 | une session qui finit son tour sur une question n'est jamais réveillée : `question-default-delay` n'est lu que par `forge:feature-build` (même commentaire) | A34 à A39, A57 à A62 |
| PG5 | six relais d'une nuit ont listé deux tickets prêts sans en lancer aucun (#340, commentaire 7236859617) | A40 (le répartiteur), A67 à A69 sur le « non » |
| PG6 | un relais démarre à environ 56 k jetons, l'un a atteint sa limite avant ses coders (même commentaire ; non recompté) | A84 ; A70 et A71 sur le « non » |
| PG7 | 10 tickets sur 19 au plafond de PR sur un projet consommateur, faute de taille estimée (#340, commentaire 7237632816) | A72 à A75, A86 |
| PG8 | le seuil de 1 000 lignes est écrit en dur dans le skill de design depuis la PR #384 (`plugins/forge/skills/feature-design/SKILL.md:58`) | A74 |
| PG9 | `question_delay.py route` retire `ready-for-human` et `needs-info` mais ne rend pas `ready-for-agent` (`plugins/forge/scripts/question_delay.py`, docstring de `route`) | A59 |

## 14. Non-goals

- La page de pilotage, ses boutons pour les gestes que l'humain garde, la preuve de bout en bout d'une demande
  de la page et le fil à deux voies par projet : ils restent au projet qui tient la page.
- La supervision qui relance une session par projet, le minuteur lui-même et les règles `autoMode.allow` :
  ils restent au poste ; forge documente leur contrat.
- L'installation de l'application GitHub, la protection de branche, les runners et leurs secrets : gestes de
  l'humain (H3), demandés au moment de la construction.
- Un refus des écritures dans la base d'une page par un autre canal que l'outil de base des pages.
- Un LLM dans le répartiteur, et GitHub Actions sur des runners hébergés par GitHub.
- Une revendication partagée entre deux postes : le verrou est local, un projet a un seul poste répartiteur.
- macOS, et la configuration d'un projet consommateur (ses clés, son épingle), qui reste à sa session.
- Le changement de la matrice des droits de décision qu'entraîne le clic (case `H1`) : un geste de l'humain
  (`H4`), cité en section 21.

## 15. Exigences non fonctionnelles

- Hooks et scripts en Python de la bibliothèque standard, à partir de Python 3.10, sous Linux et sous Windows,
  lancés par `uv run --no-project --quiet python` ; les questions de processus (pid vivant, heure de départ)
  passent par `handoff_header.py`. Le code reste compatible Windows ; la suite y est gelée depuis le
  2026-11-28 (#376), donc un essai Windows n'est pas prouvé par la CI.
- Le tick rend la main en moins de 30 s hors lancement des agents (A40), avec au plus un appel `gh` de liste par
  état lu (tickets prêts, revendiqués, PR) plus un appel par ticket touché.
- Le garde `guard_human_data` ne tourne que sur l'outil de base des pages, avec `timeout` 60 s comme les autres
  gardes ; il ne fait aucun appel réseau.
- Un jeton d'installation vit 60 minutes au plus (limite de GitHub, non relue ce jour) : A13 couvre un agent plus
  long. La clé privée de l'application n'est ni dans le dépôt, ni dans une trace, ni dans une sortie (T10).
- Relais : attente de 30 s à 300 s par essai, gigue de plus ou moins 20 %, total borné par la variable (C05).
- Hook `Stop` : 8 blocages successifs au plus (plafond de la documentation de Claude Code, lue le 2026-11-28
  par `forge:staff-engineer`) ; décideur saisi au plus 1 minute après l'échéance (A34).
- Les tests qui lancent un tick, un relais ou un hook tournent sous `ulimit -v` et `timeout`, et n'appellent
  jamais le vrai `gh` ni le vrai `claude`.
- Aucune donnée d'un client ; l'audit privé de l'humain reste hors dépôt, seuls ses pourcentages agrégés sont
  repris.

## 16. Contrats, en prose

- **`guard_human_data.py`** (hook `PreToolUse`). Entrée : l'appel d'outil, la clé `human-collections` lue sur
  `origin/main`. Sortie : 0 pour laisser passer, 2 et le message G2 pour refuser. Erreurs nommées : ligne de clé
  illisible (refus qui la cite), événement illisible (refus), clé absente (rien n'est refusé).
- **Identité des agents.** Entrée : `agent-token-command`, qui imprime un jeton d'installation sur une ligne et
  sort en 0 ; `agent-login`. Le répartiteur passe le jeton à l'agent qu'il lance, et l'identité git de
  l'application. `guard_git` refuse un geste d'écriture sans jeton `ghs_` quand les clés sont présentes.
  Erreurs nommées : commande en échec, sortie vide, jeton d'un autre préfixe.
- **`merge_grant.py <projet> <pr>`.** Entrée : `merge-grant`, `human-collections`, la tête de la PR, le verdict
  de `forge:qc`. Sortie : `GRANTED` (statut posté, fusion faite), `WAITING` (aucun clic pour cette tête),
  `NOT RUN` (raison), ou « sans objet ». La commande de `merge-grant` reçoit `{pr}` et `{sha}` et sort 0
  (clic présent pour ce SHA) ou 1 (absent) ; tout autre code vaut `NOT RUN`.
- **`handoff_header.py sessions`.** Inchangé, sauf que les sessions que C04 désigne sont omises.
- **`handoff_relay.py`.** Sur un code 6 seulement, et avec la variable, réessaie selon C05 ; ses autres codes
  et son compteur du jour sont inchangés.
- **Hook `Stop` de la question.** Entrée : le transcript de la session, la clé `question-default-delay`, les
  tickets et PR où la session a posé une étiquette d'attente dans ce passage. Sortie : `decision: block` avec
  la consigne (décideur, puis `route --apply`) ou rien. Il échoue ouvert.
- **`dispatch.py tick <projet>`.** Entrée : les clés G1 du répartiteur, `agent-autonomy` sur `origin/main`,
  `.claude/PAUSED`, l'état GitHub, les verrous locaux, `question_delay.py due`. Sortie : les agents lancés
  (détachés), les lignes de trace G3, un code 0 (tick fait ou sans objet), 1 (`gh` en échec), 2 (clé
  illisible).
- **`/forge:feature-build F-NNNN --ticket <n>`.** Entrée : un ticket revendiqué pour ce lancement, ou sa
  branche et sa PR. Sortie : la PR menée jusqu'au verdict, ou une question au format G5, puis l'arrêt.
- **`question_delay.py route`.** Inchangé, sauf qu'un `post-default` sur un ticket (une issue, pas une PR) qui
  attendait une question d'agent lui rend `ready-for-agent`.
- **`ticket_graph.py check`.** Ajoute les lignes `CHAIN <tickets>` pour les chaînes de C09, et sort en 1 tant
  qu'une chaîne listée n'a pas sa ligne G9 dans le design.
- **`zone-command`.** Reçoit `{path}`, imprime une zone de `zones` par ligne ; une zone hors de la liste ou un
  code non nul laisse la PR sans étiquette de ce fichier et le dit.

## 17. Impact sur les règles du métier

Aucune règle du métier touchée : la clé `domain-skill` est absente de `usine.md` (ligne 126, le plugin n'a pas
de métier propre), et la feature n'engage ni un chiffre de métier ni une obligation réglementaire. Elle touche
en revanche la gouvernance de l'usine : le clic de la story 3 change qui fusionne un chemin protégé, ce que la
matrice des droits de décision (case `H1`) devra dire par un geste de l'humain (`H4`).

Décision de l'humain du 2026-11-28 (point 5, réponse relayée par une autre de ses sessions) : un clic vérifié
sur sa page peut laisser les agents fusionner une PR qui touche un chemin protégé. La case `H1` ne devient
active qu'à deux conditions, qui ne sont pas encore remplies :

- **les agents ne tiennent plus le jeton GitHub de l'humain.** Tant qu'ils agissent sous son compte, un clic
  sur la page ne prouve pas que l'humain a décidé : un agent pourrait écrire la même ligne. Le clic ne vaut
  qu'une fois les gestes des agents passés par l'identité de l'application (story 2), dont ils ne tiennent
  pas la clé, et la collection du clic fermée aux agents (story 1) ; A21 et A89 le tiennent ;
- **un clic a été traité de bout en bout.** Aucun ne l'a été à ce jour. L'humain n'exige le contexte de
  `merge-grant` dans la protection de `main` (H3), et ne change la case `H1` (H4), qu'après un essai où un
  clic réel a produit le statut puis la fusion d'une PR d'essai.

## 18. Décisions prises par défaut

Celles de l'agent qui écrit la spec, là où le cadrage et la séance ne tranchent pas. Chacune a été soumise le
2026-11-28 à l'agent décideur de sa nature ; la dernière colonne dit son verdict et la case de la matrice
(`MATRIX_CELL`). Deux sont changées (10, 16), une a été réservée à l'humain, qui l'a tranchée (5).

| # | Décision | Fondement | Si le relecteur lit autrement | Tranché le 2026-11-28 |
|---|---|---|---|---|
| 1 | `human-collections` dans `usine-gardes.md`, ligne `<page> \| <collection>` ; le garde vise l'outil de base des pages (`ArtifactData`, actions d'écriture) ; une ligne illisible ferme toute écriture de base de page (technique) | un garde se lit sur `origin/main` ; la page est nommée pour ne pas fermer les collections homonymes d'une autre page ; échouer fermé (T2 de la matrice) | une clé par nom de collection seul, ou une ligne illisible ignorée ; A1, A4 à relire | confirmé, `forge:staff-engineer`, T5, T2 |
| 2 | identité par une commande `agent-token-command` qui imprime le jeton, plutôt qu'une signature dans forge (technique) | signer un jeton d'application demande RS256, hors de la bibliothèque standard | forge signe lui-même avec un outil du poste ; contrat de la section 16 à revoir | confirmé, `forge:staff-engineer`, T4, T2 |
| 3 | `guard_git` reconnaît l'identité des agents au préfixe `ghs_` du jeton (technique) | préfixe des jetons d'installation de GitHub ; contrôle sans appel réseau | un appel `gh api user` comparé à `agent-login` ; A11 à relire | confirmé, `forge:staff-engineer`, T5, T2 ; seul le préfixe se vérifie, jamais la longueur ni la forme du reste (format allongé par GitHub, rapporté par le décideur, non revérifié ici) |
| 4 | les commits des agents prennent l'identité git de l'application (technique) | sépare aussi l'auteur des commits ; l'adresse `noreply` du compte de l'humain n'est plus nécessaire | garder l'identité git de l'humain, le jeton seul changeant ; A14 à retirer | confirmé, `forge:staff-engineer`, T4, T2 |
| 5 | la vérification du clic est un statut de commit `<contexte>` posté par l'application quand la commande de `merge-grant` confirme le clic pour la tête ; `guard_git` accepte la fusion d'un chemin protégé sur ce statut ; pas de `success` sans `human-collections` (technique) | un statut requis peut être restreint à une application dans la protection de branche ; forge ne lit pas la base d'une page depuis un script, le projet fournit la commande | une vérification dans un workflow du projet ; A17 à A22 à revoir | **réservé à l'humain**, H1, H4, H3 ; tranché par lui : oui, actif aux deux conditions de la section 17 |
| 6 | `ignored-session` : nom exact ou préfixe fini par `*` ; une session `interactive` n'est jamais ignorée (technique) | « le mode de lancement ne sert que de complément » (séance, Q4) : il ne peut qu'ajouter un refus | le mode seul suffit pour certains noms ; A25 à relire | confirmé, `forge:staff-engineer`, T4, T2 |
| 7 | `CLAUDE_HANDOFF_RETRY_MINUTES`, de 1 à 1440 ; absente, aucun nouvel essai ; recul de 30 s doublé, plafond 300 s, gigue 20 % (technique) | sans la variable, le comportement d'aujourd'hui ; chiffres usuels d'un recul exponentiel | une valeur par défaut, comme `CLAUDE_HANDOFF_RELAY_MAX` ; A32 à relire | confirmé, `forge:staff-engineer`, T4, T2 |
| 8 | le hook `Stop` attribue à la session les questions où elle a posé une étiquette d'attente dans ce passage, et passe par le décideur puis `route` au lieu d'appliquer la recommandation brute (technique) | `route` est le seul chemin qui exclut les gestes réservés ; le transcript est la seule trace de ce passage | appliquer la recommandation de la session ; A34, A35 à revoir | confirmé, `forge:staff-engineer`, T5, T2 |
| 9 | l'entrée épinglée est l'option `--ticket <n>` de `/forge:feature-build`, plutôt qu'un skill nouveau (technique) | réutilise la revendication, le coder, `forge:qc` et les questions du skill | un skill dédié ; A47 à A50 renommés | confirmé, `forge:staff-engineer`, T4, T2 |
| 10 | clés du répartiteur `dispatch-tick` dans `usine.md`, `dispatch-command`, `dispatch-relaunch-cap` et `agent-slots` dans `usine-gardes.md` ; le tick exige `agent-autonomy` à `on` (technique) | aucune ne borne un garde ; `e2e-command` vit déjà dans `usine.md` ; l'autonomie dit si un agent peut être lancé | `dispatch-command` et `dispatch-relaunch-cap` dans `usine-gardes.md` ; G1 à revoir | **changé**, `forge:staff-engineer`, T4, T2 : `dispatch-command`, `dispatch-relaunch-cap` et `agent-slots` vont dans `usine-gardes.md` (ce qui se lance sans l'humain, et combien, se lit sur `origin/main`) ; `dispatch-tick` reste dans `usine.md` ; G1 mis à jour |
| 11 | le décideur d'une question d'agent est nommé dans son commentaire (G5) (produit) | l'agent sait si sa question est technique ou produit ; le répartiteur n'a pas de LLM pour en juger | le tick passe toute question à `forge:staff-engineer`, qui renvoie `DOMAIN` au besoin | confirmé, `forge:product-owner`, P3 ; un décideur absent ou inconnu vaut `staff-engineer` (G5) |
| 12 | `route` rend `ready-for-agent` à un ticket après `post-default` (technique) | « remet le ticket prêt » (cadrage, EXI-15) ; `forge:feature-build` en profite aussi | une option de `route`, ou le tick qui pose l'étiquette ; A59 à relire | confirmé, `forge:staff-engineer`, T4, T2 |
| 13 | un ticket sans étiquette `zone:` n'est contraint par aucune zone dans le parallèle ; un conflit se rattrape par le mode sync du coder (technique) | EXI-08 est au lot 1, les étiquettes au lot 2 ; refuser le parallèle sans zone l'annulerait jusqu'au lot 2 | un ticket sans zone tourne seul ; A64 étendu | confirmé, `forge:staff-engineer`, T4, T2 |
| 14 | `ticket-size-max` remplace le seuil de 1 000 écrit en dur ; absente, la coupe est « sans objet » (technique) | `.claude/rules/forge.md` : aucune clé ne prend de valeur par défaut ; cela relâche le comportement de 1.25.0 pour un projet sans la clé | garder 1 000 en dur tant que la clé manque ; A74 à revoir | confirmé, `forge:staff-engineer`, T4 ; le relâchement est dit dans `CHANGELOG.md` (A74) |
| 15 | EXI-05 vise une baisse d'au moins 50 % du plancher médian sur 5 relais (produit) | le cadrage ne chiffre pas la cible ; 56 k jetons contre une limite qui a été atteinte | une autre cible ; A71 à relire | confirmé, `forge:product-owner`, P1 ; aucune cible publiée ne s'applique (DORA ne chiffre pas ce plancher) |
| 16 | « interventions de l'humain par ticket » : par ticket fusionné, étiquettes `needs-your-attention` posées plus fusions par l'humain ; ses commentaires ne comptent que s'ils répondent à une telle étiquette (produit) | ce que l'humain fait de lui-même sur un ticket ; lisible dans GitHub | une autre définition, A84 et A85 à relire | **changé**, `forge:product-owner`, P1 : par ticket fusionné, étiquettes `needs-your-attention` posées plus fusions par l'humain ; un commentaire de l'humain ne compte que s'il répond à une telle étiquette (section 22) |
| 17 | le seuil de chaîne reste 3, écrit dans forge, et la chaîne se détecte dans `ticket_graph.py check` (technique) | décision de la séance (Q11), sans clé ; `check` lit déjà le graphe | une clé de seuil ; C09 à revoir | confirmé, `forge:staff-engineer`, T4, T2 |
| 18 | la page de documentation s'appelle `docs/usine-autonome.md` ; la trace du répartiteur vit dans `~/.claude/hooks/state/dispatch/` (produit pour le nom, technique pour le dossier) | le nom de la feature ; le dossier d'état des hooks existant | d'autres noms, sans effet sur les critères | confirmé : le nom par `forge:product-owner`, P1 ; le dossier par `forge:staff-engineer`, T4, T2 |
| 19 | la ligne `agent-identity` de `factory_slo.py report` reconnaît une PR d'agent à sa section `Rapport d'agent` (technique) | le gabarit de PR du dépôt la porte ; un objectif `slo` nouveau serait une décision de l'humain | un autre marqueur ; A15 à relire | confirmé, `forge:staff-engineer`, T4, T2 |

## 19. Confiance chiffrée

| Partie | Confiance (de 0 à 100 %) | Raison |
|---|---|---|
| modèle | 60 | le répartiteur, la revendication et les questions viennent des décideurs et du code lu (`handoff_header.py`, `handoff_relay.py`, `question_delay.py`, `forge:feature-build`) ; l'identité et le clic reposent sur des faits de GitHub et de Claude Code non vérifiés ici (section 21) |
| périmètre | 85 | les dix-huit exigences et les éléments sans identifiant du cadrage accepté sont repris un par un ; aucun n'est écarté |
| priorités | 80 | l'ordre du lot 1 est celui de l'humain (#340, commentaire 7239359496) ; la place de la mesure de base avant EXI-12 est un choix de la spec |

## 20. Points ouverts

Aucun. Le point 5 (fusion d'un chemin protégé sur un clic vérifié), réservé à l'humain (cases H1, H4 et H3,
`forge:staff-engineer`, 2026-11-28), a été tranché par lui le même jour : oui. Sa réponse a été relayée par
une autre de ses sessions, pas tapée dans celle qui écrit la spec. La story 3 se construit, et ne s'active
qu'aux deux conditions de la section 17.

## 21. Questions pour les entretiens

La feature n'a pas d'expert externe ; l'humain de la clé `accepting-human` décide. Restent à vérifier, avant le
design ou pendant la construction :

- le nom que le registre des sessions donne à une passe `claude -p` lancée avec un nom, et la valeur de `kind`
  qu'il lui écrit (le rapport sur `sdk-cli` n'est pas vérifié, séance Q4) ;
- si `gh auth git-credential` et `git push` prennent bien `GH_TOKEN` quand il est posé ;
- si l'outil de base des pages est le seul canal par lequel un agent peut écrire une collection de la page ;
- le délai d'exécution maximal d'un hook `Stop`, qui borne une attente dans le hook ;
- l'humain accepte-t-il de changer la case `H1` de la matrice pour que le clic vaille fusion (geste `H4`) ?
  Tranché : oui, aux conditions de la section 17.

## 22. Glossaire

La clé `glossary` est absente de `usine.md` (ligne 126) : ces termes restent dans la spec.

| Terme | Définition |
|---|---|
| répartiteur | script sans LLM (`dispatch.py`) qui, à chaque tick, lance un agent par ticket prêt et par place libre |
| tick | un passage du répartiteur, lancé par le minuteur du poste, qui ne garde aucun état |
| agent court, agent épinglé | agent sans interface lancé pour un seul ticket, qui s'arrête à la fin de sa PR |
| place | un agent que le projet admet en même temps (clé `agent-slots`) |
| revendication | assigné, étiquette `agent-claimed` et verrou local posés sur un ticket avant de lancer son agent |
| verrou local | fichier du poste qui tient le pid et l'heure de départ de l'agent d'un ticket |
| relance | nouvel agent lancé sur un ticket dont l'agent est mort, compté par un marqueur de commentaire |
| passe ignorée | session sans interface que nomme `ignored-session`, qui ne compte pas comme session vivante |
| collections de l'humain | collections de la base de sa page que nomme `human-collections`, où seul l'humain écrit |
| identité des agents | le compte de l'application GitHub des agents (`agent-login`), distinct de celui de l'humain |
| clic de fusion | ligne écrite par l'humain depuis sa page pour une PR et un SHA, que confirme la commande de `merge-grant` |
| point de décision | la vérification du 2026-12-16 qui ouvre le lot 3 ou le lot conditionnel (C11) |
| interventions de l'humain par ticket | par ticket fusionné, étiquettes `needs-your-attention` posées plus fusions par l'humain ; un commentaire de l'humain ne compte que s'il répond à une telle étiquette |
| zone | partie du code nommée dans `zones`, portée par une étiquette `zone:<zone>` |
| chaîne de blocage | suite de tickets reliés par `blocked_by`, comptée en tickets |
