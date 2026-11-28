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
| `human-collections` | `docs/agents/usine-gardes.md` | les collections de pages (`<adresse de l'artefact> \| <collection>`) que le garde `guard_human_data` ferme aux écritures d'un agent |

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

## Les collections de l'humain : la clé `human-collections`

**Le problème.** Un agent peut écrire dans la base d'une page publiée. Un clic de l'humain dans sa page ne
prouve donc rien tant que rien n'empêche l'agent d'écrire la même ligne : un projet consommateur a refusé
le clic comme autorisation pour cette raison (ticket #340). Le hook `guard_human_data` ferme ces écritures.

**Le geste de l'humain.** Il écrit, dans `docs/agents/usine-gardes.md` (un chemin protégé : la PR qui
change ce fichier se fusionne par lui), une ligne par collection :

```
- `human-collections` : `<adresse de l'artefact> | <collection>`
```

- La page est l'adresse de l'artefact telle que l'outil `ArtifactData` la nomme dans son champ `url`
  (`claude.ai/artifact/<id>`, ou `claude.ai/code/artifact/<uuid>`) : l'outil n'a pas de titre de page. Deux
  adresses valent la même page quand elles portent le même identifiant, sans égard au schéma, à la casse,
  à la barre finale ni à la requête ; les deux formes de l'adresse, `artifact/` et `code/artifact/`, valent
  la même page quand l'identifiant est le même (le côté prudent : on ne sait pas si un même identifiant peut
  désigner deux artefacts selon la forme).
- La collection est un chemin à barres, dont les segments alternent collection et document
  (`boards/b1/columns`). Une collection listée ferme aussi tout ce qui est dessous (`decisions/d1/notes` pour
  `decisions`), segment entier par segment entier : `decisions2` n'est pas sous `decisions`.
- Une ligne sans ` | `, dont une partie est vide, dont la page n'est pas une adresse d'artefact (un titre
  comme `Tableau`) ou dont la collection n'a aucun segment est illisible.
- La clé se lit comme `origin/main` tient le fichier, jamais dans l'arbre de travail : une PR qui retire une
  ligne n'ouvre rien avant sa fusion. Tant que `usine-gardes.md` est absent de `origin/main`, la clé se lit
  dans `usine.md`, comme `origin/main` le tient.

**Ce que le garde refuse.** À tout agent, session principale ou sous-agent, sur l'outil `ArtifactData` :

- une écriture simple (`set`, `update`, `str_replace`, `delete`) sur l'artefact et la collection listés, ou
  sous elle ;
- un appel `batch` dont une seule entrée de `writes` (chacune porte son `op`, sa `collection` et son
  `doc_id`) vise une collection listée : l'appel entier est refusé, aucune entrée ne passe. Une entrée que le
  garde ne sait pas lire compte comme visant la collection ;
- toute écriture, quel que soit l'artefact, quand une ligne de la clé est illisible : le refus cite la ligne.

Le message commence par `Blocked by the forge plugin (guard_human_data): <page> | <collection>` et dit que
la collection ne s'écrit que depuis la page de l'humain. Il ne contient jamais ce qui était écrit.

**Ce qui passe.** Une lecture (`get`, `list`, `query`, `profiles`), l'écriture d'une autre collection du
même artefact, celle d'une collection au nom qui commence pareil, et celle d'une collection du même nom sur
un autre artefact.

**Sans la clé.** L'étape est « sans objet (clé `human-collections` absente) » : aucune écriture n'est refusée. Il n'y a pas
de valeur par défaut.

**Le garde échoue fermé.** Son entrée de `hooks.json` porte `|| exit 2`, `"onFailure": "block"` et un
`timeout` de 60 secondes : une erreur, un script absent ou un dépassement refuse l'écriture. Avec la clé, un
appel que le garde ne sait pas lire (événement illisible, action absente) est refusé, de même qu'une écriture
quand git ne peut pas dire ce que `origin/main` tient de la clé alors que le projet a un fichier de clés.
Un projet sans fichier de clés, ou hors d'un dépôt git, n'a pas la clé : rien n'est refusé.

**La trace.** Chaque refus ajoute une ligne à `~/.claude/hooks/state/refusals/<AAAA-MM-JJ>.jsonl`, avec les
champs des autres gardes : `guard` à `guard_human_data`, `rule` à `human-collection` (ou `unreadable-key-line`,
`unreadable-event`, `unreadable-key`), l'agent, le dépôt, la branche et le verbe `ArtifactData write`. Jamais le
contenu de l'écriture. Le journal vit sur le poste : deux postes, deux journaux.

**Ce qui n'est pas couvert.** Un agent qui écrit la base d'une page par un autre canal que l'outil
`ArtifactData` (un appel réseau lancé depuis `Bash`, par exemple) échappe au garde. Un tel canal, une fois
prouvé, se traite comme un risque de sécurité.

**Ce qui n'a pas été éprouvé.** Les champs (`url`, `collection`, `doc_id`, `writes[].op`,
`writes[].collection`) et les actions sont ceux que le schéma de l'outil donne, rapportés à l'agent qui a
écrit le garde ; les tests rejouent le hook comme un processus sur des événements écrits à la main à cette
forme. Le hook n'a pas été joué dans une vraie session de Claude Code : le nom exact de l'outil dans
l'événement (`ArtifactData`, filtre de `hooks.json`) et la forme réelle de `tool_input` restent à vérifier
dans la première vraie session qui déclare la clé. Un chemin de collection avec des segments `.` ou `..`,
ou un `doc_id` qui porte des barres, n'est pas traité à part : on ne sait pas si l'outil les résout.

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

## L'agent épinglé : `forge:feature-build F-NNNN --ticket <n>` (ticket 7)

Un agent court mène un seul ticket, au lieu de la feature entière : le répartiteur (ticket 8) le lance sans
interface une fois le ticket revendiqué. Ce ticket livre l'entrée, pas le répartiteur : tant que personne ne
pose le verrou (ticket 8, partie b), l'agent épinglé s'arrête toujours à son premier contrôle, ce qui est le
côté prudent. Aucune clé nouvelle.

**Sans `--ticket`, rien ne change.** Le skill `feature-build` ne nomme l'option qu'à trois endroits avant sa
section dédiée (l'en-tête, le paragraphe des arguments, un renvoi à l'étape 0.5), et un test les compte.

**Le contrôle, à la place de l'étape 0.5.** L'étape 0.5 (une seule session par projet) vaut pour une session
qui mène un dépôt ; un agent épinglé est l'une des sessions du répartiteur, pas la session du projet. Il lit le
ticket, puis le verrou :

```sh
uv run --no-project --quiet python plugins/forge/hooks/agent_lock.py check . <n>
```

Le verrou est le fichier du ticket sous `~/.claude/hooks/state/dispatch/locks/<projet>/<n>.json`. La commande
sort en 0 quand ce fichier nomme un pid vivant qui est le processus de la session, l'un de ses ancêtres ou
`CLAUDE_PID`, en 1 sinon (aucun fichier, fichier illisible, pid mort, pid d'un autre agent), en 2 pour un appel
faux (un ticket qui n'est pas un nombre). Lancée depuis un arbre de travail, elle lit les verrous de son dépôt
principal, où le répartiteur les range.

L'agent s'arrête sans rien écrire (ni commentaire, ni étiquette, ni verrou, ni branche), et dit pourquoi, quand le
ticket est fermé, a un bloqueur ouvert, ne porte ni `ready-for-agent` ni `agent-claimed`, n'a pas son verrou, ou
quand `.claude/PAUSED`, la porte ou le budget d'erreur l'arrêtent comme ils arrêtent une session de feature.
Les questions échues (étape 0.9) ne sont pas les siennes : le répartiteur les fait trancher.

**Ce qu'il mène.** Le ticket seul : `forge:coder` (tour 0 compris), puis `forge:qc` sur sa PR, sans frontière, sans
revendication (elle est faite) et sans autre ticket. Il s'arrête quand la PR est fusionnée, ou quand son verdict
est posté (un `ACCEPT` qui attend l'humain sur un chemin protégé, l'arrêt du tour 3), ou sur un incident. La revue
de bout en bout et la clôture (étapes 3 bis et 5) restent à la session qui mène la feature sans `--ticket`.

**La reprise.** Une PR ouverte qui cite le ticket entre directement dans la relecture : aucun coder, aucune
nouvelle PR. Une branche sans PR, que le ticket nomme dans un commentaire et que `git ls-remote` trouve, est
confiée au coder par son brief, qui lui dit de partir d'elle et d'y pousser. La définition du coder n'est pas
changée : la reprise d'une branche sans PR tient au brief, et n'a pas été jouée avec un vrai coder.

**Une question.** L'agent commente le ticket en trois lignes (G5), un commentaire par question :

```text
Question : <la question>
Recommandation : <la recommandation>
Décideur : staff-engineer
```

`Décideur : product-owner` pour une question produit ou UX ; une ligne absente vaut `staff-engineer`. Puis il pose
`needs-info`, retire `ready-for-agent`, `agent-claimed` et l'assignation, libère son verrou
(`agent_lock.py release . <n>`, qui ne retire que le verrou de sa propre session) et s'arrête. Il ne lance aucun
décideur : le lancer au délai est la partie c du ticket 8.

**Le ticket redevient prêt.** `question_delay.py route --apply` rend `ready-for-agent` à un ticket (une issue,
jamais une PR) qui portait `needs-info` ou `ready-for-human` quand le verdict est `post-default`, sauf s'il
l'a déjà. Un rappel (`remind-human`) ne le rend pas. C'est un changement pour tout appelant de `route`, la
session de feature comprise : le skill y relançait déjà un coder. Une cellule qui laisse un veto à l'humain
pose en plus `needs-your-attention`, et le ticket redevient prêt quand même : la décision par défaut est
réversible d'un commentaire.

**Éprouvé et pas éprouvé.** Éprouvé par des tests : `route` sur des `gh` simulés, `agent_lock.py` en
processus sous un `HOME` isolé (verrou propre, absent, mort, d'un autre pid, illisible, chemin d'un arbre de
travail), et le contenu du skill (ses phrases, leur ordre, ses mentions de l'option). Pas éprouvé : une
session `claude -p ... --ticket` réelle. Le contrôle suppose que `CLAUDE_PID` ou les ancêtres du processus
atteignent le pid que le répartiteur écrira dans le verrou ; la forme de ce pid est le choix du ticket 8,
partie b.

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
