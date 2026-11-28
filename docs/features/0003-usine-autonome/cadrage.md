---
feature: F-0003
document: cadrage
statut: accepte
accepte_par: ikoro-labs
accepte_le: 2026-11-28
accepte_via: agent-autonomy
taille: L
destinataires: ikoro-labs (humain de la clé `accepting-human`) ; acceptation par `/forge:feature-accept`, lancée par le modèle sous la clé `agent-autonomy` une fois les points ouverts tranchés ; forge:qc relit
contexte: forge (plugin) ; touchés : un hook qui garde les données de l'humain, l'identité GitHub des agents, passation et relais (`handoff_header.py`, `handoff_relay.py`), un répartiteur nouveau sous `plugins/forge/scripts/`, `question_delay.py`, `forge:coder`, `forge:qc`, découpage en tickets, gabarit `usine.md`
base: 80ce163
date: 2026-11-28
---

# F-0003 : cadrage

Réécrit le 2026-11-28 : l'humain a approuvé une architecture cible, « un agent court par ticket »
(#340, commentaire 7239304262), qui devient l'option principale de ce cadrage, puis a placé deux
correctifs d'identité en tête du premier lot (#340, commentaire 7239359496). La version fusionnée par
la PR #387 corrigeait les relais d'une session longue ; celle-ci sépare d'abord le geste de l'humain
de celui d'un agent, garde ces correctifs de relais, puis remplace la session longue par un
répartiteur.

F-0003 sépare d'abord l'identité de l'humain de celle des agents : un clic de l'humain sur sa page
peut alors porter une autorisation. Elle retire ensuite les deux causes qui laissent une usine sans agent au travail ou en attente de
l'humain : des relais qui ne se passent pas la main et des questions qui ne reçoivent jamais de
réponse. Elle remplace ensuite la session longue par un agent court par ticket : il démarre, mène
son ticket jusqu'à la PR, puis s'arrête. Elle prouve qu'un projet avance sans saisie de l'humain dans
la CLI, sauf pour les gestes qu'il s'est réservés.

Le but approuvé par l'humain le 2026-11-28 (#340, commentaire 7238993231) : la page de pilotage est
le poste de commande de l'usine, les agents exécutent, et une question qui atteint l'humain est un
défaut de règle, pas un message à relayer. Ce cadrage couvre la part de ce but qui vit dans forge.

## 1. Problème

**Qui souffre, de quoi.** L'humain de la clé `accepting-human`, qui veut piloter depuis une page et
ne plus rien taper dans les sessions. Faits relevés le 2026-11-28 :

- rien ne distingue un clic de l'humain sur sa page d'une écriture d'agent : les agents tournent sous
  le même compte et peuvent écrire les données de la page, si bien qu'un projet consommateur refuse de
  tenir un clic pour une autorisation (#340, commentaire 7239359496) ;
- les agents poussent, ouvrent et fusionnent les PR avec le jeton GitHub de l'humain ; seule la revue
  obligatoire du propriétaire du code les distingue : la PR #384, acceptée par `forge:qc`, n'a pas pu
  être fusionnée sur le « oui » de l'humain sans `--admin`, qui n'a pas servi (même commentaire) ;
- un relais refusé parce qu'une passe sans interface compte comme une session vivante : un projet
  consommateur est resté sans session au travail à partir de 12:05 UTC (#340, commentaire
  7239037009) ;
- une session qui termine son tour sur une question n'est jamais réveillée : le délai
  `question-default-delay` (#380, 1.24.0) n'est lu que par `forge:feature-build` (même commentaire) ;
- six relais d'une nuit ont listé deux tickets prêts sans en lancer aucun (#340, commentaire
  7236859617) ;
- un relais démarre à environ 56 k jetons, et l'un d'eux a atteint sa limite avant de lancer ses
  coders (même commentaire) ; le commentaire de l'architecture cible compte 375 relais en 14 jours
  (#340, commentaire 7239304262 ; chiffre non recompté par cette session) ;
- un audit privé de l'humain (hors dépôt, deux projets consommateurs, 35 tickets fermés, du 14 au
  28-11) attribue 27 % du délai d'un ticket à l'attente de tickets bloquants et 14 % au temps mort
  entre deux PR d'un même ticket, les agents faisant une PR à la fois ;
- sur un projet consommateur, 10 tickets sur 19 au plafond de PR, faute de taille estimée au
  découpage (#340, commentaire 7237632816).

**Pourquoi pas plus simple.** Une consigne qui demande aux agents de ne pas écrire les données de
l'humain ne prouve rien : seul un refus mécanique, un hook, fait d'une ligne écrite sous l'identité de
l'humain une preuve de son geste. De même, tant que les agents tiennent son jeton GitHub, aucune
vérification ne sépare son approbation de la leur : il leur faut une identité à eux. Corriger les
relais ne suffit pas : la session longue reste l'unité de
travail, et chaque relais coûte une reprise et un risque de blocage. Une consigne dans la passation
ne suffit pas non plus : les relais suivent la suite écrite et sautent le reste, comme la nuit du
2026-11-28 l'a montré. Un agent court par ticket supprime le relais : le ticket, la branche et la PR
portent tout le contexte. Le répartiteur est un script de la bibliothèque standard, sans LLM : il lit
les tickets prêts et lance un agent par ticket. GitHub Actions n'est pas la première marche : l'humain
ne paie pas Actions, et un répartiteur local prouve le modèle avant de déplacer les agents.

**Le cas d'usage unique.** Un projet a un ticket prêt et une place libre. Au tick suivant, le
répartiteur revendique le ticket et lance un agent sans interface sur ce seul ticket. L'agent code,
ouvre la PR, la fait relire et s'arrête. S'il a une question, il la commente sur le ticket et
s'arrête ; au bout du délai, le répartiteur fait trancher la question par l'agent décideur, remet le
ticket prêt et relance un agent, qui reprend depuis la branche et la PR. La PR est fusionnée sans
que l'humain ait rien tapé ; quand elle touche un chemin protégé, il clique « Fusionner » sur sa page,
et ce clic, qu'aucun agent ne peut écrire, autorise la fusion.

## 2. Périmètre

Trois lots, livrés dans l'ordre (section 7). Le premier suit l'ordre fixé par l'humain (#340,
commentaire 7239359496) : les deux correctifs d'identité, puis les défauts de relais, puis le
répartiteur. Le lot 3 n'entre que sur le « oui » du point de décision de la section 8.

| Exigence | Contenu | Preuve |
|---|---|---|
| EXI-17 | Lot 1, en tête. Un hook de forge refuse à tout agent l'écriture dans les collections de données de l'humain que nomme une clé (ses acceptations, ses réponses, ses demandes sur sa page). Une ligne écrite sous l'identité de l'humain ne peut alors venir que de lui, et un clic sur sa page peut porter une autorisation | #340, commentaire 7239359496 ; décidé par l'humain |
| EXI-18 | Lot 1, ensuite. Les agents agissent sur GitHub sous l'identité d'une application GitHub à eux ; le jeton de l'humain ne leur est plus donné. Une fusion qu'il autorise d'un clic passe par une vérification obligatoire de GitHub qui contrôle ce clic. Installer l'application est un geste unique de l'humain | même commentaire ; décidé par l'humain ; remplace EXI-10 |
| EXI-01 | Lot 1. Une passe courte sans interface ne compte pas comme session vivante : une clé nomme les passes à ignorer, par le `name` du registre ; le mode de lancement ne sert que de complément. Prérequis du répartiteur : ses agents sont des passes sans interface | #340, commentaire 7239037009 ; séance Q4, T1 (T4) |
| EXI-02 | Lot 1. Un relais refusé parce qu'une autre session tourne réessaie seul, avec un recul plafonné et une gigue, jusqu'à une borne donnée par une variable de passation | même commentaire ; séance Q5, T2 (T2) |
| EXI-03 | Lot 1, pont. Une session longue qui attend la réponse à sa propre question ne s'arrête pas : un hook `Stop` attend `question-default-delay`, puis lui fait appliquer sa recommandation ; les gestes réservés à l'humain restent exclus. Il sert tant que des sessions longues tournent ; EXI-15 le remplace pour les agents du répartiteur | même commentaire ; #380 ; séance Q6, P1 (P2) |
| EXI-12 | Lot 1. Le répartiteur : un tick sans état, en Python de la bibliothèque standard sous `plugins/forge/scripts/`, lancé par un minuteur du poste. À chaque tick, pour chaque ticket prêt et chaque place libre, il revendique le ticket et lance un agent sans interface sur ce seul ticket (`forge:coder`, puis `forge:qc`), qui s'arrête à la fin de la PR | #340, commentaire 7239304262 ; séance T1 (T4, T2) |
| EXI-13 | Lot 1. Une entrée épinglée à un ticket : un agent lancé pour un ticket ne prend que lui ; `forge:feature-build` ne sait pas aujourd'hui épingler un ticket | séance T1 |
| EXI-14 | Lot 1. Revendication et reprise : le ticket revendiqué porte un assigné, une étiquette `agent-claimed` et un verrou local par processus ; un agent mort est relancé sur le même ticket depuis sa branche, sa PR et le commentaire du ticket, avec un nombre de relances plafonné | séance T3 (T2) |
| EXI-15 | Lot 1. Les questions par le répartiteur : l'agent commente sa question et s'arrête ; le répartiteur lit `question_delay.py due`, fait trancher par l'agent décideur, applique `route`, remet le ticket prêt et relance ; `route` ne rend pas aujourd'hui l'étiquette du ticket prêt. Les gestes réservés restent exclus | #340, commentaire 7239304262 ; `plugins/forge/scripts/question_delay.py` ; séance T2 |
| EXI-08 | Lot 1, en dernier. Agents en parallèle : une clé fixe les places d'un projet ; un arbre de travail par agent ; deux agents ne prennent pas la même zone ; la relecture `forge:qc` reste en série | audit privé (14 % du délai entre deux PR) ; séance Q11, T4 (T4, T6) |
| EXI-04 | Conditionnelle. Une passation nomme sa suite (un ticket prêt) ou dit qu'il n'y en a pas, dans une clé d'en-tête que `handoff_header.py check` vérifie. Abandonnée si le point de décision de la section 8 dit « oui » | #340, commentaire 7236859617 ; séance Q7, P1 |
| EXI-05 | Conditionnelle. Reprise légère d'un relais, après mesure de son plancher de jetons. Abandonnée si le point de décision dit « oui » | même commentaire ; séance Q8, P1 |
| EXI-06 | Lot 2. Taille estimée au découpage : chaque ticket porte une taille en lignes lisibles ; au-delà du seuil d'une clé (ordre de grandeur 1 000), il est coupé en parties du même ticket (`Refs #n`) ; les tickets non commencés sont redécoupés, ceux en vol finissent | approuvé par l'humain le 2026-11-28 (#340, commentaire 7237809110) ; séance Q9 (T6, T4) |
| EXI-07 | Lot 2. Étiquettes `zone:<zone>` : une clé pour le vocabulaire, une pour la commande qui range un chemin ; posées au découpage, recopiées sur la PR depuis le résultat réel, jamais lues par la CI | même commentaire ; séance Q10 (T4) |
| EXI-09 | Lot 2. Chaînes courtes : au découpage, une chaîne de blocage de plus de 3 tickets se justifie dans le design | audit privé (27 % du délai en attente de tickets bloquants) ; séance Q11 ; seuil non mesuré |
| EXI-16 | Lot 3, sur le « oui » du point de décision. Les agents tournent sur des runners auto-hébergés seulement, jamais sur des runners hébergés par GitHub. À mesurer avant la spec de ce lot : le coût en jetons et en runner, les hooks de forge dans Actions, la charge des runners, les secrets, le blocage des déclencheurs tiers sur un dépôt public | #340, commentaire 7239304262 ; séance P3, T5 (H3) |
| EXI-10 | Remplacée par EXI-18 : l'identité qui prouve l'humain est son compte, une fois que les agents ont la leur | `idee.md` ; séance Q12, P5 ; #340, commentaire 7239359496 |
| EXI-11 | Documentation : chaque clé nouvelle dans le gabarit `plugins/forge/templates/usine.md`, la page de `docs/` qui en traite, la variable de passation dans `docs/sessions.md`, l'entrée du `CHANGELOG.md` | `.claude/rules/forge.md`, version et journal |

**Les clés nouvelles.** EXI-17 ajoute une clé qui nomme les collections de l'humain, EXI-18 sans
doute une clé pour l'identité des agents ; EXI-01, EXI-06, EXI-07 et EXI-08 ajoutent chacune une clé
de `usine.md`, EXI-02 une variable de passation, EXI-04 une clé d'en-tête de passation, EXI-12 et
EXI-14 sans doute une clé chacun (le minuteur, le plafond de relances) ; leurs noms se fixent dans la
spec. Chaque clé est écrite par l'humain du projet (`usine-gardes.md` quand elle borne un garde),
jamais par le plugin, et rend « sans objet (clé `<nom>` absente) » quand elle manque, sans valeur par
défaut (`.claude/rules/forge.md`). Sans la clé du répartiteur, un projet garde la session longue.

**Ce qui revient à forge, au projet, au poste.** Forge tient le hook qui protège les données de
l'humain, le contrat de l'identité des agents, la boucle du répartiteur, le contrat de l'agent
épinglé, la revendication, `question_delay.py`, les clés et leur documentation. Le projet qui
l'essaie le premier tient sa page de pilotage, son bouton « Fusionner » et le premier essai ; la part
générique de la vérification qui contrôle le clic se décide dans la spec. Le poste tient la
supervision, le minuteur et les règles `autoMode.allow`. Installer l'application GitHub et le minuteur
sont des gestes de l'humain (H3).

**Déjà livré, hors de ce cadrage.** La cible `human-touch` à 1 % (#342), l'essai de bout en bout qui
passe (`CHANGELOG.md`, 1.24.0), le délai `question-default-delay` en minutes (#380), les petites PR
hors plafond et le plafond de PR relevé à 6 pendant la transition (#381, PR #384 fusionnée le
2026-11-28 en `80ce163`, après 1.24.0 : la version suivante les apporte aux projets).

**Hors périmètre.** La page de pilotage, ses boutons pour les gestes que l'humain garde, la preuve de
bout en bout d'une demande de la page et le fil à deux voies par projet restent au projet qui tient
la page (`forge:product-owner`, séance Q3). Les gestes du lot 3 sur les runners et les secrets restent
à l'humain (H3). macOS reste dehors. La configuration d'un projet consommateur (clés, épingle) reste à
sa session. Les suites de ces points se commentent sur #340.

## 3. Condition d'entrée

Sans objet (clé `entry-gate` absente) : les besoins de ce dépôt viennent de ses tickets
(`docs/agents/usine.md`, clés absentes). La feature est admise par son issue de suivi #340, ouverte
à la demande de l'humain de la clé `accepting-human` (`idee.md`).

## 4. Observabilité

| Question | Réponse |
|---|---|
| Quelle métrique prouve que ça marche | Mesure principale : le délai d'un ticket au 90e centile (objectif `lead-time p90` de `usine-gardes.md`) et le nombre d'interventions de l'humain par ticket, relevés avant le répartiteur puis pendant l'essai. Mesure du but, secondaire : le taux d'automatisation, part des gestes de l'humain qui ne demandent plus de session CLI ; base d'environ 16 à 17 % sur environ 1 120 gestes du 14 au 28-11 (#340, commentaire 7238993231, tiré de l'audit privé). Identité : écritures d'agent refusées dans les collections de l'humain ; actions GitHub d'un agent sous le compte de l'humain (cible : zéro). Relais : temps sans session au travail pendant qu'un ticket prêt existe ; questions appliquées au délai sur questions posées. Répartiteur : jetons par PR d'un agent court, comparés à ceux d'une session longue ; plancher de jetons d'un agent épinglé |
| Quelle alerte si ça casse | Les objectifs `lead-time p90` et `human-touch` et leur action `alert` (`budget-action`) ; un push, une PR ou une fusion d'agent sous le compte de l'humain ; un ticket revendiqué sans agent vivant ni PR au-delà d'un délai ; un ticket qui atteint le plafond de relances |
| Que voit-on dans une trace | À ajouter : une ligne par écriture refusée par le hook (agent, collection), une ligne par tick du répartiteur (tickets prêts, places, agents lancés), une ligne par revendication et par relance (ticket, raison, essai), une ligne par question appliquée au délai (question, recommandation, heure), une ligne par nouvel essai de relais |

## 5. Risques

| Risque | Mitigation | Signal |
|---|---|---|
| Le hook refuse une écriture légitime d'un agent dans les données de la page | Il ne vise que les collections que la clé nomme ; les autres restent ouvertes | Une passe de rafraîchissement de la page en échec sur un refus |
| Un agent garde le jeton de l'humain quelque part | Le jeton n'est plus donné aux agents ; l'alerte de la section 4 relève toute action d'agent sous son compte | Une action GitHub d'agent sous le compte de l'humain |
| La vérification du clic est contournable | Elle est obligatoire sur la branche protégée, et la ligne du clic ne peut venir que de l'humain (EXI-17 avant EXI-18) | Une fusion sans clic enregistré |
| Deux agents sur le même ticket | Revendication à trois verrous (assigné, étiquette, verrou local) ; le tick relit l'état avant de lancer | Deux PR ou deux agents vivants pour un ticket |
| Un agent mort laisse un ticket revendiqué | Relance depuis la branche et la PR ; relances plafonnées, puis `needs-your-attention` | Un ticket au plafond de relances |
| Un agent court coûte plus de jetons qu'une session longue | Plancher mesuré avant le point de décision, qui compare les jetons par PR | Jetons par PR au-dessus de la base |
| Les agents du répartiteur bloquent les relais des sessions longues | EXI-01 livré avant le répartiteur | Un relais refusé en code 6 pendant un tick |
| Une recommandation appliquée au délai prend un geste réservé | Les gestes réservés de la matrice sont exclus, par le hook comme par le répartiteur | Un geste réservé dans le journal des questions appliquées |
| Deux relectures `forge:qc` en même temps cassent son contrôle d'état | La relecture reste en série ; un arbre de travail par agent | Un contrôle d'état de `forge:qc` en échec |
| Le hook `Stop` boucle ou bloque une session | Les questions déjà rappelées sont exclues ; relances successives plafonnées (8) | Relances répétées sur une même question |
| L'étiquette de zone finit par piloter la CI | La clé le dit, la CI ne la lit pas | Un job de CI qui lit une étiquette `zone:` |

## 6. Faisabilité des données

Mesures tirées des journaux que forge et Claude Code écrivent déjà : registre des sessions,
passations, transcripts (jetons par appel), PR et tickets GitHub. Aucune donnée d'un client. L'audit
de l'humain reste hors dépôt : seuls ses pourcentages agrégés sont repris ici, sans nom de projet ni
citation. Le chiffre de 375 relais et le plancher de 56 k jetons sont repris de #340, sans recompte.

## 7. Décisions

| Date | Décision | Par | Séance |
|---|---|---|---|
| 2026-11-28 | Une seule feature, taille L, sans nouvelle issue de suivi | `forge:product-owner`, P2 | cadrage, tours 2 et 4 |
| 2026-11-28 | Hors périmètre et destinations de la section 2 | `forge:product-owner`, P2 | cadrage |
| 2026-11-28 | Passes ignorées par une clé de noms ; nouvel essai borné du relais | `forge:staff-engineer`, T2, T4 | cadrage |
| 2026-11-28 | Question au délai par un hook `Stop` ; touche `hooks.json`, donc fusion humaine | `forge:staff-engineer`, T5, H1 | cadrage |
| 2026-11-28 | Clés de seuil de taille, de zones et de places ; chaîne de plus de 3 tickets justifiée au design | `forge:staff-engineer`, T4, T6, T2 | cadrage |
| 2026-11-28 | Taille au découpage et étiquettes de zone : principe approuvé | ikoro-labs (#340, commentaire 7237809110) | sans objet |
| 2026-11-28 | Architecture cible « un agent court par ticket », répartiteur local d'abord, runners auto-hébergés ensuite : approuvée | ikoro-labs (#340, commentaire 7239304262) | sans objet |
| 2026-11-28 | La cible est l'option principale ; EXI-04 et EXI-05 conditionnelles ; EXI-03 garde un rôle de pont ; runners sur le « oui » seulement | `forge:product-owner`, P1, P2 | cadrage, tour 4 |
| 2026-11-28 | Forge tient la boucle, le contrat de l'agent, les clés ; le projet et le poste gardent la page, la supervision, le minuteur et le premier essai | `forge:product-owner`, P3 ; `forge:staff-engineer`, T4 | cadrage, tour 4 |
| 2026-11-28 | Répartiteur en tick sans état sous `plugins/forge/scripts/` ; entrée épinglée à un ticket ; revendication à trois verrous ; reprise depuis la branche et la PR ; relecture en série | `forge:staff-engineer`, T2, T4, T6 | cadrage, tour 4 |
| 2026-11-28 | Mesure principale : délai p90 et interventions de l'humain ; taux d'automatisation secondaire | `forge:product-owner`, P1 | cadrage, tour 4 |
| 2026-11-28 | Deux correctifs d'identité en tête du lot 1 : le hook qui protège les données de l'humain, puis une application GitHub pour les agents ; ordre du lot 1 : identité, relais, répartiteur. Tranche EXI-10 (H3) | ikoro-labs (#340, commentaire 7239359496) | cadrage, tour 5 |

**Gestes réservés à l'humain (H3), demandés au moment de la construction.** Installer l'application
GitHub des agents (EXI-18), le minuteur du poste (EXI-12) et, sur le « oui », les runners et leurs
secrets (EXI-16). Aucun point de décision ne reste ouvert dans ce cadrage.

## 8. Critères d'arrêt

Dates proposées par la session (l'acceptation les fixe).

| Vérification | Condition de poursuite | Si non atteinte |
|---|---|---|
| 2026-12-05 | EXI-17 et EXI-18 fusionnés, l'application installée ; EXI-01 et EXI-02 fusionnés, EXI-03 proposé (fusion humaine, H1) | Garder ce qui est fusionné, reporter le reste sur #340 |
| 2026-12-12 | Le répartiteur tourne sur un projet consommateur ; plancher de jetons d'un agent épinglé mesuré | Garder l'identité et les relais, reprendre EXI-04 et EXI-05 |
| 2026-12-16, point de décision | « Oui » si le délai p90 baisse, si les interventions de l'humain ne montent pas et si aucun geste réservé n'est pris par défaut | « Non » : garder l'identité et les relais, reprendre EXI-04 et EXI-05, le lot 3 n'entre pas |
| 2027-01-15 | Lot 2 fusionné ; aucun ticket nouveau au plafond de PR ; métriques de la section 4 comparées à la base | Clore la feature sur ce qui a tenu ; le lot 3 se redimensionne après le « oui » |
