---
feature: F-0003
seance: 2026-11-28-ikoro-labs-design
participants: agent de design (sous-agent de la session forge), forge:product-owner, forge:staff-engineer
sujet: trancher les questions techniques du design de F-0003 que le code et la documentation ne tranchent pas
---

# Séance du 2026-11-28 : design de F-0003

Écrite pendant la séance, tour par tour, jamais réécrite ensuite. Une correction se fait dans une
séance suivante, qui cite celle-ci. Le design est lancé par le modèle sous la clé `agent-autonomy` : chaque
question passe d'abord à l'agent décideur, et seule une case réservée revient à l'humain.

## Sources apportées

| Source | Où | Empreinte | Ce qui en est retenu |
|---|---|---|---|
| Spec de F-0003, acceptée | `spec.md` (PR #394) | sans objet | critères A1 à A89, contrôles C01 à C11, gabarits G1 à G9, contrats (section 16), questions de la section 21 |
| Registre des sessions du poste | hors dépôt : fichiers d'état du poste, relevés le 2026-11-28 sous Claude Code 2.1.332 | non relevée | une passe `claude -p --name ...` porte `kind: interactive` et `entrypoint: sdk-cli` |
| Documentation des hooks de Claude Code | https://code.claude.com/docs/en/hooks, lue le 2026-11-28 | sans objet | délai par défaut 600 s, plafond de 8 continuations du hook `Stop`, `onFailure` sans effet sur `Stop`, héritage de l'environnement |
| Documentation GitHub et gh | docs.github.com et cli.github.com, lues le 2026-11-28 (URL dans `design.md`, section 10) | sans objet | jeton d'installation d'une heure, préfixe `ghs_`, source attendue d'un statut exigé, priorité de `GH_TOKEN` |
| Verdict de `forge:product-owner` sur la coupe | relayé par la session forge le 2026-11-28 | sans objet | voir le tour 0 |

## Tours

### Tour 0

**Coupe en tickets** (posée par la session forge avant ce design). Réponse de `forge:product-owner` (case P2 ;
T6 pour les parties du ticket 8), restituée : la coupe en douze tickets est gardée et le ticket 8 nomme ses trois
parties ; les tickets 11 et 12 sont publiés sans `ready-for-agent`, chacun dit quel verdict de C11 l'ouvre, et
après le 2026-12-16 le gagnant reçoit l'étiquette et le perdant est fermé « not planned » ; le ticket 8 est aussi
bloqué par 6 (mesure de base avant le répartiteur), et la plus longue chaîne reste à 3 tickets (6 > 8 > 9) ;
l'ordre de l'humain reste dans la numérotation, les tickets 1, 2, 4, 5, 6, 7 et 10 sont prêts dès le départ, et
un `Blocked by` 8 sur le ticket 10 reste une option notée, non faite. Écrit dans `design.md`, section 7.

### Tour 1

Questions pour `forge:staff-engineer`. Chacune porte la recommandation de l'agent de design ; aucune n'est
tranchée ici.

**Q1. Session ignorée : C04 contre le registre réel.** C04 et A25 n'ignorent une session nommée que si son `kind`
n'est pas `interactive`. Sur le poste (Claude Code 2.1.332, 2026-11-28), une passe `claude -p --name ...` porte
`kind: interactive` et `entrypoint: sdk-cli` : telle qu'écrite, A24 ne peut pas passer pour les agents du
répartiteur, et deux textes acceptés se contredisent. Recommandation : garder l'esprit de A25 (le mode de
lancement ne fait qu'ajouter un refus) en ignorant une session dont le `name` correspond à `ignored-session` et
dont le pid est tenu par un verrou vivant du répartiteur (`agent_lock`, pid et heure de départ), au lieu du test
sur `kind` ; une session de l'humain n'est jamais derrière un tel verrou. À défaut, tester `entrypoint` autre que
`cli`, moins sûr (valeurs de l'éditeur et de l'application de bureau non relevées). Écrire la décision en
section 9 du design, ou par une révision de la spec si la case le demande.

**Q2. Nouvel essai du relais et délai de l'outil.** `CLAUDE_HANDOFF_RETRY_MINUTES` va jusqu'à 1440, alors qu'une
commande de l'outil `Bash` est bornée à 10 minutes. Recommandation : sur un code 6 avec la variable, le relais
lance une copie détachée de lui-même (`--retry`, sur le modèle de `--close` et de `handoff_relay.detached`), qui
attend selon C05 et écrit la trace G4 ; l'appel rend tout de suite. Le compteur du jour ne monte qu'au lancement
réel, puisque le contrôle des autres sessions précède le compteur (`handoff_relay.py:425-449`).

**Q3. Jeton d'installation au-delà de 60 minutes (A13).** `gh` lit `GH_TOKEN` une fois, au lancement de chaque
commande, et le répartiteur ne peut pas changer l'environnement d'une session lancée. Recommandation : le
répartiteur place en tête du `PATH` de l'agent un dossier d'état qui tient un `gh` et une aide de crédit de git
écrits par forge ; chacun demande un jeton frais à `agent_identity.fresh_token` (cache jusqu'à cinq minutes avant
l'échéance, dans un fichier lisible du seul utilisateur) puis lance le vrai `gh` ou rend le crédit. `GH_TOKEN`
reste posé au lancement pour que `guard_git` voie le préfixe `ghs_`. Variante plus simple à juger : borner la vie
d'un agent épinglé à 55 minutes et relancer (coût en jetons non mesuré).

**Q4. Outils MCP GitHub sous l'identité des agents.** Un serveur MCP GitHub tient son propre jeton : C02, lu
dans l'environnement du hook, ne dit rien de l'auteur d'un geste MCP. Recommandation : quand `agent-token-command`
et `agent-login` sont présentes, `guard_git` refuse tout outil MCP GitHub en écriture, et les agents passent par
`gh` ; la lecture reste permise.

**Q5. Mode `--ticket` et règle d'une seule session par projet.** L'étape 0.5 de `feature-build` (lignes 40 à
108) s'arrête dès qu'une autre session vit sur le dépôt ; avec `agent-slots` au-dessus de 1, deux agents épinglés
se verraient. Recommandation : en mode `--ticket`, l'étape 0.5 est remplacée par le contrôle du verrou du ticket
(il doit être tenu par la session elle-même) ; l'exclusion entre agents est celle du répartiteur (C07, verrous,
zones). `.claude/PAUSED`, la porte et le budget restent lus.

**Q6. Attente dans le hook `Stop`.** Le hook doit faire passer la question au plus 1 minute après l'échéance
(A34). Recommandation : le hook attend dans son processus, en relisant `question_delay.py due` toutes les
30 secondes, jusqu'à l'échéance ou jusqu'à son `timeout` moins une marge, puis rend `decision: block` avec la
consigne (décideur, puis `route --apply`) ; le `timeout` de son entrée de `hooks.json` se règle au plus grand
délai de question admis plus une minute. Bloquer sans attendre ferait tourner le plafond de 8 continuations en
quelques secondes (il se remet à zéro à chaque appel d'outil, documentation des hooks).

**Q7. Lancement du décideur par le tick (A58).** G1 n'a pas de gabarit pour lancer un décideur. Recommandation :
le tick lance `claude -p --agent forge:<décideur>` avec la question, le nom `forge-dispatch-q-<n>` (que couvre
`ignored-session`), l'environnement de l'identité, puis lance `question_delay.py route --apply` sur le verdict ;
pas de clé nouvelle, comme le relais qui lance `claude --bg` en dur. Non vérifié : qu'une passe `-p --agent`
charge l'agent d'un plugin ; le ticket 8 le relève avant d'écrire.

**Q8. `usine.py` hors des chemins protégés.** Les sept clés nouvelles de `usine-gardes.md` ne sont protégées que
par leur présence dans `usine.SENSITIVE_KEYS` ; or `usine.py` n'est pas un chemin protégé, et une PR qui retire
une clé de cette liste la ferait lire dans `usine.md`, que l'agent modifie. Recommandation : demander à l'humain
d'ajouter `plugins/forge/hooks/usine.py` à `protected-path` et à `CODEOWNERS` (geste H, hors de cette feature),
et ne rien changer dans les tickets d'ici là.

**Q9. Qui crée l'arbre de travail d'un agent (A63).** Recommandation : le gabarit de `dispatch-command` porte
`-w {name}` (le drapeau existe dans `claude --help`, 2.1.332), et le tick relève l'arbre créé pour l'écrire dans
le verrou ; le tick supprime l'arbre d'un ticket fermé au tick suivant. À défaut, le tick crée l'arbre lui-même
par `git worktree add` depuis `origin/main`, ce qui lui donne le chemin sans le deviner.

## Décidé

| Décision | Par | Va dans |
|---|---|---|
| coupe en douze tickets, trois parties pour le ticket 8, tickets 11 et 12 sans `ready-for-agent`, ticket 8 bloqué par 6 | `forge:product-owner` (P2, T6) | design, section 7 |

### Réponses du tour 1

Réponses de `forge:staff-engineer`, 2026-11-28 (relu par lui : `docs/agents/decisions.md`, la spec, ce design ;
https://code.claude.com/docs/en/env-vars et https://code.claude.com/docs/en/cli-reference, lues le 2026-11-28).

- **Q1** DECIDED (T9, veto). La spec n'est pas amendée ; l'écart à C04 s'écrit dans le design : une session est
  ignorée quand son `name` correspond à `ignored-session` et que son pid tient un verrou vivant du répartiteur,
  sans test sur `kind`. A25 reste vrai pour une session sans verrou. Le décideur lancé par le tick (Q7) prend
  aussi un verrou, hors des places. Le ticket 4 relève d'abord le `kind` réel d'une passe `-p` vivante.
- **Q2** DECIDED (T2). Une copie `--retry` détachée, un verrou de nouvel essai par projet, la passation relue à
  chaque essai, le message de A30 dans la ligne G4.
- **Q3** DECIDED (T2). Ni `gh` ni aide de crédit qui garde un jeton ; `CLAUDE_ENV_FILE`, exécuté avant chaque
  commande `Bash`, exporte un `GH_TOKEN` frais. Le ticket 2 l'éprouve ; repli : rotation à 55 minutes.
- **Q4** DECIDED (T5, T2). Refus fermé des écritures par un outil MCP GitHub quand les deux clés d'identité sont
  présentes.
- **Q5** DECIDED (T2). En mode `--ticket`, contrôle du verrou du ticket ; sans verrou, l'étape 0.5 actuelle.
- **Q6** DECIDED (T5, T2). Attente dans le hook, `timeout` fixe ; une échéance plus lointaine laisse passer
  l'arrêt. Essai réel dans le ticket 5.
- **Q7** DECIDED (T2). Recommandation suivie, sous `run-limits` ; `claude -p --agent` éprouvé dans le ticket 8.
- **Q8** RESERVED (H1). Ajouter `hooks/usine.py` à `protected-path` touche `usine-gardes.md` et `CODEOWNERS`,
  gestes de l'humain. Recommandation : l'ajouter. Le trou existe déjà pour les clés de garde d'aujourd'hui : ce
  n'est pas un point de ce design, il se commente sur #340.
- **Q9** DECIDED (T2). Le tick crée l'arbre (`git worktree add`), sous un nom hors `agent-*`, et ne le supprime
  que proprement.

## Resté ouvert

- Q8, réservé à l'humain (H1), hors de ce design : à commenter sur #340. Q1 porte un veto : la PR du design
  reçoit `needs-your-attention`.
- Les réponses Q1 à Q9 restent à reporter dans le design (sections 1 à 7, 9 et 10) ; la session qui les a
  reçues a passé la main avant de le faire.
