---
feature: F-0003
seance: 2026-11-28-ikoro-labs-cadrage
participants: session forge (relais 9 du 2026-11-28, agent), forge:product-owner, forge:staff-engineer
sujet: trancher le périmètre, la taille, l'ordre et les mécanismes du cadrage de F-0003
---

# Séance du 2026-11-28 : cadrage de F-0003

Écrite pendant la séance, tour par tour, jamais réécrite ensuite. Une correction se fait dans une
séance suivante, qui cite celle-ci. Le cadrage est lancé par le modèle sous la clé `agent-autonomy` :
chaque question passe d'abord à l'agent décideur, et seule une case réservée revient à l'humain.

## Sources apportées

| Source | Où | Empreinte | Ce qui en est retenu |
|---|---|---|---|
| Idée de F-0003 | `idee.md` | sans objet | les six premières questions (interrupteurs, chemins protégés, identité d'approbation, essai de bout en bout, permissions du poste, cibles des objectifs) |
| Audit « piloter sans taper dans la CLI », 2026-11-28 | hors dépôt : note privée de l'humain, chiffres de projets privés | non relevée | où passe le temps d'un ticket (46 % usine à l'arrêt, 27 % attente de tickets bloquants, 14 % entre deux PR) ; les interventions de l'humain par type ; la pratique d'Anthropic (classes de risque, petites PR, sélection des tests) |
| Constats du 2026-11-28 sur les relais | #340, commentaire 7236859617 | sans objet | aucun relais ne prend un ticket prêt ; un relais démarre à environ 56 k jetons |
| Plafond de PR et taille des tickets | #340, commentaires 7237632816 et 7237809110 | sans objet | taille estimée au découpage, étiquettes `zone:<service>` ; approuvés par l'humain le 2026-11-28 |
| Deux défauts de relais | #340, commentaire 7239037009 | sans objet | une passe sans interface compte comme session vivante ; une session qui attend une réponse n'est jamais réveillée |

## Tours

### Tour 1

**Q1. Taille et coupe.** Le périmètre couvre les relais et les questions (l'humain hors de la boucle)
et le débit (coders en parallèle, taille des tickets, zones, chaînes de blocage). Taille L : faut-il
couper la feature en deux ? Recommandation : une seule feature, taille L, livrée en deux lots dans
l'ordre ; pas de nouvelle issue de suivi.

**Q2. Ordre.** Recommandation : d'abord les deux défauts de relais (un projet est resté sans session
au travail le 2026-11-28), puis la règle de passation et la reprise légère, puis la taille et les
zones, puis les coders en parallèle et les chaînes courtes, l'identité d'approbation en dernier.

**Q3. Hors périmètre.** Recommandation : la page de pilotage (boîte de réception, boutons) reste au
projet qui la tient ; la supervision qui relance une session par projet reste au poste, forge
n'en documente que le contrat ; macOS reste dehors ; la configuration d'un projet consommateur
reste à sa session.

**Q4. Passe sans interface.** Comment le relais distingue-t-il une passe courte sans interface
(`claude -p`) d'une session vivante ? Recommandation : détection par le mode de lancement quand elle
est fiable, sinon une clé qui nomme les passes à ignorer.

**Q5. Relais refusé.** Recommandation : un relais refusé parce qu'une autre session tourne réessaie
seul, à intervalle borné, au lieu de renvoyer l'ouverture de la session suivante à l'humain.

**Q6. Question en attente.** Comment une session qui attend la réponse à sa propre question
applique-t-elle sa recommandation au bout de `question-default-delay` ? Recommandation : un hook
de fin de tour qui empêche la session de s'arrêter tant qu'une question à elle est en attente, et
la fait appliquer sa recommandation au délai ; les gestes réservés restent exclus.

**Q7. Règle de passation.** Recommandation : une passation est refusée quand un ticket prêt et une
place libre existent et que sa suite n'en nomme aucun.

**Q8. Reprise légère.** Recommandation : un relais ne charge que la passation et les règles ; la
mémoire, les anciennes passations et les transcripts ne se lisent qu'à la demande.

**Q9. Taille au découpage.** Recommandation : chaque ticket porte une taille estimée en lignes
lisibles ; au-delà d'un seuil déclaré par une clé, il est coupé en parties du même ticket
(`Refs #n`) dès le design ; les tickets non commencés sont redécoupés, ceux en vol finissent.

**Q10. Étiquettes de zone.** Recommandation : une clé déclare le vocabulaire des zones et la commande
qui range un chemin dans une zone ; l'étiquette est posée au découpage, recopiée sur la PR depuis
le résultat réel, et ne pilote jamais la CI.

**Q11. Coders en parallèle et chaînes courtes.** Recommandation : une clé fixe le nombre de places
de coder par projet ; deux coders ne prennent pas la même zone ; au découpage, une chaîne de blocage
plus longue qu'un seuil se justifie dans le design.

**Q12. Identité d'approbation.** Recommandation : une identité que l'agent ne détient pas (une
application GitHub dont la clé n'est pas sur le poste) ; réservée à l'humain (comptes et
permissions).

### Tour 2 : réponses des agents décideurs

**Q1, Q2, Q3.** Réponse de `forge:product-owner` (DECIDED, `MATRIX_CELL: P2`, sans veto) : une seule
feature, taille L, deux lots ordonnés, sans nouvelle issue de suivi. Lot 1 : relais et questions
(Q4 à Q8). Lot 2 : débit (Q9 à Q11), puis Q12. Ordre : défauts de relais, passation et reprise
légère, taille et zones, coders en parallèle. Hors périmètre : la page de pilotage chez le projet qui
la tient, la supervision au poste, macOS, la configuration d'un projet à sa session ; leurs suites
se commentent sur #340. Source citée : DORA, petits lots,
https://dora.dev/capabilities/working-in-small-batches/ (lue le 2026-11-28, chiffres non relus).

**Q4.** Réponse de `forge:staff-engineer` (DECIDED, T4) : une clé nomme les passes à ignorer, par le
`name` du registre des sessions. Le mode de lancement (`entrypoint`) ne sert que de complément : une
passe `-p` longue est une vraie session. Le rapport sur la valeur `sdk-cli` n'est pas vérifié.

**Q5.** Réponse de `forge:staff-engineer` (DECIDED, T2) : nouvel essai borné dans
`handoff_relay.py`, sur le seul refus « une autre session tourne », avec un recul plafonné et une
gigue ; la borne est une variable de passation.

**Q6.** Réponse de `forge:staff-engineer` (DECIDED, T5, `VETO: yes`, H1) : un hook `Stop` attend
l'échéance de la question, puis bloque l'arrêt pour faire appliquer la recommandation ; il exclut
les questions déjà rappelées. Le changement touche `hooks.json` : la fusion revient à l'humain.
Limite relevée : la documentation des hooks `Stop` plafonne les relances successives (8),
code.claude.com, lue le 2026-11-28.

**Q7.** Réponse de `forge:staff-engineer` (DECIDED, T4) : la passation porte une clé d'en-tête qui
nomme la suite (un ticket) ou dit qu'il n'y en a pas, vérifiée par `handoff_header.py check`.

**Q8.** Réponse de `forge:staff-engineer` (DECIDED, T2) : mesurer d'abord le plancher de jetons d'un
relais qui lance un coder, puis limiter l'invite de reprise à la passation et aux règles.

**Q9.** Réponse de `forge:staff-engineer` (DECIDED, T6, T4) : une clé déclare le seuil ; le principe
et l'ordre de grandeur (environ 1 000 lignes lisibles) sont déjà approuvés par l'humain (#340,
commentaire 7237809110).

**Q10.** Réponse de `forge:staff-engineer` (DECIDED, T4) : une clé pour le vocabulaire des zones, une
pour la commande qui range un chemin ; l'étiquette ne pilote jamais la CI.

**Q11.** Réponse de `forge:staff-engineer` (DECIDED, T4, T2) : une clé fixe les places de coder
(l'option `--parallel` de `forge:feature-build`) ; deux coders ne prennent pas la même zone ; une
chaîne de blocage de plus de 3 tickets se justifie au design (seuil non mesuré).

**Q12.** Réponses des deux agents (RESERVED, H3, `VETO: yes`) : recommandation, une application
GitHub dont l'agent ne détient pas la clé, essayée d'abord sur un dépôt d'essai. La demande part
vers l'humain dès le lot 1, la livraison reste en fin de lot 2.

**Déjà livré, à ne pas redemander** (`forge:staff-engineer`) : la cible `human-touch` à 1 % (#342) ;
l'essai de bout en bout passe (`CHANGELOG.md:36`). Pas encore livré : les petites PR hors plafond
(#381, PR #384 ouverte, en attente de la fusion humaine).

## Décidé

| Décision | Par | Va dans |
|---|---|---|
| Une feature L, deux lots ordonnés, sans nouvelle issue | `forge:product-owner`, P2 | cadrage |
| Hors périmètre et leurs destinations | `forge:product-owner`, P2 | cadrage |
| Mécanismes de Q4 à Q11 | `forge:staff-engineer`, T2, T4, T5, T6 | cadrage, puis spec |
| Q6 touche `hooks.json` : fusion humaine | `forge:staff-engineer`, H1 | cadrage, construction |

## Resté ouvert

- Q12, identité d'approbation : réservée à l'humain (H3), recommandation ci-dessus.
- Les dates d'arrêt de la section 8 du cadrage : proposées, l'acceptation les fixe.

### Tour 3 : après la revue de la PR #387

Le juge (`forge:qc-conf`, tour 1, ACCEPT avec deux `MINOR`) relève que le but approuvé par l'humain
(#340, commentaire 7238993231 : la page de pilotage comme poste de commande, une question qui atteint
l'humain comme défaut de règle, la mesure du taux d'automatisation) n'est pas repris, et que le
cadrage ne dit pas ce que rend une clé nouvelle absente. La session les ajoute au cadrage. Les
leviers de ce commentaire qui ne vivent pas dans forge (page, boutons, preuve d'une demande de la
page, fil à deux voies, règles `autoMode.allow` du poste) restent hors périmètre, comme
`forge:product-owner` l'a décidé au tour 2 (P2) ; aucune décision nouvelle.

### Tour 4 : l'architecture cible « un agent court par ticket » (relais 10)

L'humain approuve une architecture cible (#340, commentaire 7239304262) : un agent par ticket, qui
démarre, mène la PR et s'arrête ; un répartiteur local d'abord, sur un projet consommateur ; des
runners auto-hébergés seulement ensuite, sans GitHub Actions payant. Il demande qu'elle devienne
l'option principale du cadrage, après discussion avec les agents. La session pose les questions
suivantes aux deux décideurs.

**P1 à P5** (`forge:product-owner`, DECIDED sauf mention) : la cible est l'option principale (P1) ;
ordre : défauts de relais, répartiteur, taille et zones, runners sur le « oui » d'un point de
décision ; EXI-04 et EXI-05 deviennent conditionnelles, abandonnées si le répartiteur tient ; EXI-03
reste comme pont pour les sessions longues ; le cas d'usage est réécrit. Une seule feature, une seule
issue de suivi (P2) ; une feature nouvelle serait réservée à l'humain, la clé `entry-gate` étant
absente. Forge tient la boucle, le contrat de l'agent, `question_delay route`, les clés ; le projet et
le poste gardent la page, la supervision, `autoMode` et le premier essai ; les runners sont un lot
sous condition, pas un hors périmètre (P3, T4, verdict TECHNICAL sur la frontière). Mesure
principale : délai p90 et interventions de l'humain, taux d'automatisation secondaire (P1). EXI-10
reste réservée à l'humain (H3).

**T1 à T7** (`forge:staff-engineer`, DECIDED sauf mention) : un tick sans état sous
`plugins/forge/scripts/`, lancé par un minuteur du poste dont l'installation revient à l'humain (H3) ;
une entrée épinglée à un ticket manque, `forge:feature-build` ne sait pas épingler (T4, T2). Garder
EXI-01, prérequis puisque les agents du répartiteur sont des passes sans interface, et EXI-02 ;
remplacer EXI-03 par la boucle du répartiteur, `question_delay.py route` ne rendant pas l'étiquette
du ticket prêt (T2). Point de reprise : la branche, la PR et le commentaire du ticket ; revendication
par assigné, étiquette `agent-claimed` et verrou local par processus ; relances plafonnées (T2).
Places par une clé, un arbre de travail par agent, relecture `forge:qc` en série ; la note d'un
`push -u` qui changerait la configuration partagée ne vaut plus pour le coder (`guard_coder.py`) (T4,
T6). Runners et secrets : gestes réservés (H3). Coupe : verdict DOMAIN, rendu à `forge:product-owner`.
Dates proposées : 12-05, 12-12, 12-16 (point de décision). Non vérifiés par l'agent : les 375 relais,
les 56 k jetons.

**Écart entre les deux décideurs, tranché par la case.** Sur EXI-03, le maintien comme pont relève de
la priorité dans le périmètre (P1, `forge:product-owner`) : il reste au lot 1, et la boucle du
répartiteur (EXI-15) le remplace pour les agents courts, comme le propose `forge:staff-engineer`.

### Tour 5 : deux correctifs d'identité en tête du lot 1

L'humain place deux correctifs en tête du lot 1 (#340, commentaire 7239359496, relayé par une autre
session) : un hook de forge qui refuse aux agents l'écriture dans les collections de données de sa
page ; une application GitHub qui donne aux agents leur propre identité, son jeton n'étant plus donné
aux agents, puis un bouton « Fusionner » dont le clic autorise la fusion par une vérification
obligatoire. Ordre du lot 1 : ces deux correctifs, les défauts de relais, puis le répartiteur.
Installer l'application est un geste unique de l'humain.

La session en tire : EXI-17 et EXI-18 en tête du lot 1 ; le répartiteur rejoint le lot 1 ; les lots
deviennent trois (identité, relais et répartiteur ; taille et zones ; runners sur le « oui »). EXI-18
tranche EXI-10 : l'identité qui prouve l'humain est son compte, une fois que les agents ont la leur.
Aucun point de décision ne reste ouvert ; les installations restent des gestes de l'humain (H3).
