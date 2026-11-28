---
feature: F-0003
document: cadrage
statut: en-revue
taille: L
destinataires: ikoro-labs (humain de la clé `accepting-human`) ; acceptation par `/forge:feature-accept`, lancée par le modèle sous la clé `agent-autonomy` une fois les points ouverts tranchés ; forge:qc relit
contexte: forge (plugin) ; touchés : passation et relais (`handoff_header.py`, `handoff_relay.py`), hooks, `forge:feature-build`, découpage en tickets, gabarit `usine.md`
base: b47a1f4
date: 2026-11-28
---

# F-0003 : cadrage

F-0003 retire les deux causes qui laissent une usine sans session au travail ou en attente de
l'humain : des relais qui ne se passent pas la main et des questions qui ne reçoivent jamais de
réponse. Elle augmente ensuite le débit, avec des tickets taillés pour le plafond de PR et des coders
en parallèle sur des zones distinctes. Elle prouve qu'un projet avance sans saisie de l'humain dans
la CLI, sauf pour les gestes qu'il s'est réservés.

Le but approuvé par l'humain le 2026-11-28 (#340, commentaire 7238993231) : la page de pilotage est
le poste de commande de l'usine, les sessions exécutent, et une question qui atteint l'humain est
un défaut de règle, pas un message à relayer. Ce cadrage couvre la part de ce but qui vit dans forge.

## 1. Problème

**Qui souffre, de quoi.** L'humain de la clé `accepting-human`, qui veut piloter depuis une page et
ne plus rien taper dans les sessions. Faits relevés le 2026-11-28 :

- un relais refusé parce qu'une passe sans interface compte comme une session vivante : un projet
  consommateur est resté sans session au travail à partir de 12:05 UTC (#340, commentaire
  7239037009) ;
- une session qui termine son tour sur une question n'est jamais réveillée : le délai
  `question-default-delay` (#380, 1.24.0) n'est lu que par `forge:feature-build` (même commentaire) ;
- six relais d'une nuit ont listé deux tickets prêts sans en lancer aucun, parce que rien ne fait
  prendre un ticket prêt à un relais (#340, commentaire 7236859617) ;
- un relais démarre à environ 56 k jetons, et l'un d'eux a atteint sa limite avant de lancer ses
  coders (même commentaire) ;
- un audit privé de l'humain (hors dépôt, deux projets consommateurs, 35 tickets fermés, du 14 au
  28-11) attribue 27 % du délai d'un ticket à l'attente de tickets bloquants et 14 % au temps mort
  entre deux PR d'un même ticket, les agents faisant une PR à la fois ;
- sur les projets consommateurs, le plafond de 3 PR par ticket et celui de 400 lignes par PR se heurtent, faute de taille
  estimée au découpage : 10 tickets sur 19 au plafond sur un projet consommateur (#340, commentaire
  7237632816).

**Pourquoi pas plus simple.** Une consigne dans la passation ne suffit pas : les relais suivent la
suite écrite et sautent le reste, comme la nuit du 2026-11-28 l'a montré. Une configuration locale
corrige un poste, pas les projets qui chargent forge. Le relais, l'attente d'une question et la
passation sont du code de forge : le correctif y vit. Aucun LLM nouveau : des hooks, des clés et des
contrôles de `handoff_header.py`.

**Le cas d'usage unique.** Un projet a un ticket prêt. Sa session atteint son seuil et écrit une
passation qui nomme ce ticket. Le relais est refusé, car une passe sans interface tourne : il
réessaie seul et démarre une minute plus tard, avec la passation et les règles pour tout contexte.
Il lance le coder, pose une question au décideur, et l'humain ne répond pas. Au bout du délai, la
session applique sa recommandation. La PR est fusionnée sans que l'humain ait rien tapé.

## 2. Périmètre

Deux lots, livrés dans l'ordre (section 7).

| Exigence | Contenu | Preuve |
|---|---|---|
| EXI-01 | Lot 1. Une passe courte sans interface ne compte pas comme session vivante : une clé nomme les passes à ignorer, par le `name` du registre ; le mode de lancement ne sert que de complément | #340, commentaire 7239037009 ; séance Q4 (T4) |
| EXI-02 | Lot 1. Un relais refusé parce qu'une autre session tourne réessaie seul, avec un recul plafonné et une gigue, jusqu'à une borne donnée par une variable de passation | même commentaire ; séance Q5 (T2) |
| EXI-03 | Lot 1. Une session qui attend la réponse à sa propre question ne s'arrête pas : un hook `Stop` attend `question-default-delay`, puis lui fait appliquer sa recommandation ; les gestes réservés à l'humain restent exclus | même commentaire ; #380 ; séance Q6 (T5, H1) |
| EXI-04 | Lot 1. Une passation nomme sa suite (un ticket prêt) ou dit qu'il n'y en a pas, dans une clé d'en-tête que `handoff_header.py check` vérifie : refusée quand un ticket prêt et une place libre existent et qu'elle n'en nomme aucun | #340, commentaire 7236859617 ; séance Q7 (T4) |
| EXI-05 | Lot 1. Reprise légère : le plancher de jetons d'un relais qui lance un coder est mesuré, puis l'invite de reprise se limite à la passation et aux règles | même commentaire ; séance Q8 (T2) |
| EXI-06 | Lot 2. Taille estimée au découpage : chaque ticket porte une taille en lignes lisibles ; au-delà du seuil d'une clé (ordre de grandeur 1 000), il est coupé en parties du même ticket (`Refs #n`) ; les tickets non commencés sont redécoupés, ceux en vol finissent | approuvé par l'humain le 2026-11-28 (#340, commentaire 7237809110) ; séance Q9 (T6, T4) |
| EXI-07 | Lot 2. Étiquettes `zone:<zone>` : une clé pour le vocabulaire, une pour la commande qui range un chemin ; posées au découpage, recopiées sur la PR depuis le résultat réel, jamais lues par la CI | même commentaire ; séance Q10 (T4) |
| EXI-08 | Lot 2. Coders en parallèle : une clé fixe les places de coder d'un projet ; deux coders ne prennent pas la même zone | audit privé (14 % du délai entre deux PR) ; séance Q11 (T4, T2) |
| EXI-09 | Lot 2. Chaînes courtes : au découpage, une chaîne de blocage de plus de 3 tickets se justifie dans le design | audit privé (27 % du délai en attente de tickets bloquants) ; séance Q11 ; seuil non mesuré |
| EXI-10 | Lot 2, en dernier. Une approbation humaine qui prouve l'humain : une identité que l'agent ne détient pas | `idee.md` ; séance Q12, réservée à l'humain (H3) |
| EXI-11 | Documentation : chaque clé nouvelle dans le gabarit `plugins/forge/templates/usine.md`, la page de `docs/` qui en traite, la variable de passation dans `docs/sessions.md`, l'entrée du `CHANGELOG.md` | `.claude/rules/forge.md`, version et journal |

**Les clés nouvelles.** EXI-01, EXI-06, EXI-07 et EXI-08 ajoutent chacune une clé de `usine.md`,
EXI-02 une variable de passation, EXI-04 une clé d'en-tête de passation ; leurs noms se fixent dans
la spec. Chaque clé est écrite par l'humain du projet (`usine-gardes.md` quand elle borne un garde),
jamais par le plugin, et rend « sans objet (clé `<nom>` absente) » quand elle manque, sans valeur
par défaut (`.claude/rules/forge.md`).

**Déjà livré, hors de ce cadrage.** La cible `human-touch` à 1 % (#342), l'essai de bout en bout qui
passe (`CHANGELOG.md`, 1.24.0), le délai `question-default-delay` en minutes (#380). Les petites PR
hors plafond sont en cours (#381, PR #384 ouverte, en attente de la fusion humaine).

**Hors périmètre.** Le commentaire 7238993231 de #340 range dans le but de F-0003 des leviers qui ne
vivent pas dans forge ; `forge:product-owner` les a placés ailleurs (séance, Q3). La page de pilotage,
ses boutons pour les gestes que l'humain garde, la preuve de bout en bout d'une demande de la page
et le fil à deux voies par projet restent au projet qui tient la page. Les règles `autoMode.allow`
pour les commandes courantes des agents sont un réglage du poste, que l'humain écrit. La supervision
qui relance une session par projet reste au poste ; forge n'en documente que le contrat de reprise.
macOS reste dehors. La configuration d'un projet consommateur (clés, épingle) reste à sa session.
Les suites de ces points se commentent sur #340.

## 3. Condition d'entrée

Sans objet (clé `entry-gate` absente) : les besoins de ce dépôt viennent de ses tickets
(`docs/agents/usine.md`, clés absentes). La feature est admise par son issue de suivi #340, ouverte
à la demande de l'humain de la clé `accepting-human` (`idee.md`).

## 4. Observabilité

| Question | Réponse |
|---|---|
| Quelle métrique prouve que ça marche | Mesure du but : le taux d'automatisation, part des gestes de l'humain qui ne demandent plus de session CLI ; base d'environ 16 à 17 % sur environ 1 120 gestes du 14 au 28-11 (#340, commentaire 7238993231, tiré de l'audit privé, classement par mots-clés). Lot 1 : temps sans session au travail pendant qu'un ticket prêt existe, par projet ; questions appliquées au délai sur questions posées. Lot 2 : délai d'un ticket (objectif `lead-time p90` de `usine-gardes.md`), temps mort entre deux PR d'un même ticket, tickets qui atteignent le plafond de PR. Base : les chiffres de la section 1 |
| Quelle alerte si ça casse | Les objectifs `lead-time p90` et `human-touch` et leur action `alert` (`budget-action`) ; une passation refusée par `check` s'affiche à la session qui l'écrit |
| Que voit-on dans une trace | À ajouter : une ligne de journal par nouvel essai de relais (raison, essai, borne), une ligne par question appliquée au délai (question, recommandation, heure), la clé de suite dans l'en-tête de chaque passation |

## 5. Risques

| Risque | Mitigation | Signal |
|---|---|---|
| Un relais qui réessaie lance deux sessions sur le même projet | Le nouvel essai relit le registre à chaque tour ; seul le refus « une autre session tourne » réessaie | Deux sessions au travail sur un projet dans le registre |
| Une passe sans interface longue est prise pour une passe à ignorer | La clé nomme les passes, le mode de lancement n'est qu'un complément | Une session ignorée qui écrit sur une branche |
| Le hook `Stop` boucle ou bloque une session | Les questions déjà rappelées sont exclues ; la documentation plafonne les relances successives (8) | Relances répétées sur une même question dans le journal |
| Une recommandation appliquée au délai prend un geste réservé | Les gestes réservés de la matrice sont exclus par le hook | Un geste réservé dans le journal des questions appliquées |
| Deux coders en parallèle se marchent dessus | Zones distinctes ; le contrôle d'état de `forge:qc` reste en place | Conflit de fusion entre deux PR d'un même lot |
| L'étiquette de zone finit par piloter la CI | La clé le dit, la CI ne la lit pas ; la portée reste décidée par le diff | Un job de CI qui lit une étiquette `zone:` |

## 6. Faisabilité des données

Mesures tirées des journaux que forge et Claude Code écrivent déjà : registre des sessions,
passations, transcripts (jetons par appel), PR et tickets GitHub. Aucune donnée d'un client. L'audit
de l'humain reste hors dépôt : seuls ses pourcentages agrégés sont repris ici, sans nom de projet ni
citation.

## 7. Décisions

| Date | Décision | Par | Séance |
|---|---|---|---|
| 2026-11-28 | Une seule feature, taille L, deux lots ordonnés, sans nouvelle issue de suivi | `forge:product-owner`, P2 | cadrage |
| 2026-11-28 | Ordre : défauts de relais, passation et reprise légère, taille et zones, coders en parallèle, identité d'approbation | `forge:product-owner`, P2 | cadrage |
| 2026-11-28 | Hors périmètre et destinations de la section 2 | `forge:product-owner`, P2 | cadrage |
| 2026-11-28 | Passes ignorées par une clé de noms ; nouvel essai borné du relais ; clé de suite vérifiée par `check` ; reprise légère après mesure | `forge:staff-engineer`, T2, T4 | cadrage |
| 2026-11-28 | Question au délai par un hook `Stop` ; touche `hooks.json`, donc fusion humaine | `forge:staff-engineer`, T5, H1 | cadrage |
| 2026-11-28 | Clés de seuil de taille, de zones et de places de coder ; chaîne de plus de 3 tickets justifiée au design | `forge:staff-engineer`, T4, T6, T2 | cadrage |
| 2026-11-28 | Taille au découpage et étiquettes de zone : principe approuvé | ikoro-labs (#340, commentaire 7237809110) | sans objet |

**Point ouvert, réservé à l'humain (H3).** EXI-10, l'identité d'approbation. Recommandation des deux
agents : une application GitHub dont l'agent ne détient pas la clé, essayée d'abord sur un dépôt
d'essai. Elle ne bloque pas le lot 1 ; la demande part vers l'humain dès maintenant.

## 8. Critères d'arrêt

Dates proposées par la session (l'acceptation les fixe).

| Vérification | Condition de poursuite | Si non atteinte |
|---|---|---|
| 2026-12-05 | EXI-01 à EXI-04 fusionnés (EXI-03 par l'humain, H1) ; aucun relais refusé en code 6 sans nouvel essai dans le journal | Garder EXI-01 et EXI-02 seuls, reporter le reste sur #340 |
| 2026-12-12 | EXI-05 : plancher mesuré ; un relais lance un coder avant la moitié de son seuil | Abandonner la reprise légère, garder la mesure |
| 2026-12-23 | EXI-06 à EXI-09 fusionnés ; aucun ticket nouveau au plafond de PR | Couper : garder la taille au découpage, retirer les places parallèles |
| 2027-01-15 | Métriques de la section 4 relevées et comparées aux chiffres de la section 1 | Clore la feature sur ce qui a tenu |
