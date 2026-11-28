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
