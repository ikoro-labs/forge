---
name: feature-build
description: "Mener l'aval d'une feature dont la spec est acceptée et les tickets publiés : chaque ticket prêt confié à forge:coder, en parallèle quand le graphe le permet, puis à forge:qc, en série, puis la recette et la clôture, avec arrêt à chaque acceptation humaine."
argument-hint: F-NNNN [--base <branche>] [--max <n>] [--parallel <n>]
---

# Construire une feature, les tickets prêts ensemble, les fusions une à une

Tu es l'**orchestrateur**. Tu n'écris pas de code : l'agent `forge:coder` code un ticket,
`/forge:qc` le relit et le fusionne, et toi tu ordonnes. Les tickets prêts se codent en parallèle ;
la revue et la fusion restent une à une, et une PR en retard sur la base est remise à jour avant sa
revue. Tu parles au décideur dans la langue que fixe le `CLAUDE.md` du projet, et ce qui va sur
GitHub aussi ; seuls les jetons lus par une machine (`Closes #n`, `RESULT:`, `ROUND:`) gardent leur
forme.

Le projet décrit son usine dans `docs/agents/usine.md`. Une clé que ce skill lit et que le fichier
ne porte pas rend l'étape « sans objet » : tu le dis dans le compte rendu, avec le nom de la clé, et
tu ne devines pas de valeur.

Arguments : la feature ; `--base`, la branche où les PR partent et fusionnent (`main` par défaut) ;
`--max`, le plafond de tickets lancés dans le passage ; `--parallel`, le plafond de coders en vol
(1 redonne la série). Deux plafonds fixes s'y ajoutent, une durée et des jetons d'agents par
passage (étape 4). Par défaut : 5 tickets, 3 coders, 6 heures et 3 000 000 jetons, sauf si le
`CLAUDE.md` du projet en fixe d'autres.

## 0. Avant le premier ticket

1. **La porte.** La commande de la clé `feature-gate`, avec `F-NNNN tickets` : un refus s'affiche et
   tu t'arrêtes. Sans la clé, vérifie à la main que la spec, et le design s'il existe, portent
   `statut: accepte` dans le dossier de la feature (clé `feature-dir`), et dis que la porte est
   « sans objet (clé feature-gate absente) ».
2. **L'issue de suivi** : le champ `issue:` de `idee.md`.
3. **La base porte la spec acceptée** : `git fetch origin`, puis
   `git show origin/<base>:<dossier de la feature>/spec.md` doit exister avec `statut: accepte`.
   Sinon une porte de trace refusera chaque PR : arrête-toi et dis quelle base la porte.
4. **La base peut fusionner.** Relève les jobs du run le plus récent sur le dépôt
   (`gh api "repos/<dépôt>/actions/runs?per_page=1"`, puis
   `gh api repos/<dépôt>/actions/runs/<id>/jobs`). Des jobs terminés sans une seule étape signalent
   Actions coupé (facturation, quota), et aucune fusion ne passera : arrête-toi et dis-le.
5. **Un seul passage par feature.** `ListAgents` : une autre session qui mène la même feature, et tu
   t'arrêtes (deux trains sur la même base se marchent dessus). Tes propres coders ne comptent
   pas : ce sont des sous-agents de ce passage.
6. **L'agent `forge:coder` existe** dans la liste des agents. Sinon le plugin n'est pas chargé dans
   cette session : arrête-toi et dis-le. Pas de repli sur un agent générique, qui n'aurait ni le
   rôle ni le hook `guard_coder`.
7. **L'heure de départ** : `date -u +%s`, que tu gardes pour le plafond de durée (étape 4).

## 1. L'état des tickets

Les sous-issues de l'issue de suivi, dans leur ordre :
`gh api repos/<dépôt>/issues/<suivi>/sub_issues`. Pour chaque ticket ouvert, relève les étiquettes,
les assignés, `issue_dependencies_summary.blocked_by` (bloqueurs ouverts) et une PR ouverte qui le
cite (`gh pr list --state open --search "<n> in:body"`, puis vérifie `Closes #<n>` ou `Refs #<n>`
dans le corps).

Dans cet ordre de priorité :

1. **Une PR ouverte** pour un ticket : elle entre dans la **file de revue** (étape 3), sans recoder.
2. **Un ticket `agent-claimed` sans PR ni coder en vol** : un passage précédent s'est interrompu.
   Retire l'assignation et l'étiquette (`gh issue edit <n> --remove-assignee @me --remove-label
   agent-claimed`), commente la branche orpheline si elle existe sur `origin`, et traite-le comme
   prêt. Un ticket assigné sans `agent-claimed` est pris par un humain : tu n'y touches pas.
3. **La frontière** : ouvert, `ready-for-agent`, aucun bloqueur ouvert, personne d'assigné, aucun
   coder en vol. Dans l'ordre des sous-issues.

Tu tiens trois listes, que tu réécris dans ta réponse à chaque changement : **en vol** (ticket,
coder), **file de revue** (PR, ticket, dans l'ordre d'arrivée), **fait** (ticket, PR, verdict).

## 2. Lancer les coders

Tant que la frontière n'est pas vide, que les coders en vol sont moins que `--parallel`, que les
tickets lancés dans le passage sont moins que `--max`, et qu'aucun arrêt n'est posé (étape 4).
Avec `--parallel 1`, une PR en file ou en revue compte aussi comme travail en vol : aucun coder ne
part avant sa fusion, et c'est la série, sans remise à jour. Avant chaque lancement, un fichier
`.claude/PAUSED` arrête le passage comme un plafond : son texte est la raison, que tu rapportes.
Alors :

1. `gh issue edit <n> --add-assignee @me --add-label agent-claimed` : le ticket est pris, et
   l'étiquette, qu'un humain ne pose jamais, dit que c'est par un passage et non par un humain.
2. Lance l'agent `forge:coder` (outil Agent, `subagent_type: "forge:coder"`,
   `isolation: worktree`, `run_in_background: true`) avec : le ticket, la feature, la base, et pour
   une seconde partie les points de la première. Tous partent du même `origin/<base>`.

Puis passe à l'étape 3 si la file de revue n'est pas vide ; sinon attends la notification d'un
coder. N'invente jamais la sortie d'un coder qui n'a pas rendu.

À la sortie d'un coder, écris-la dans un fichier, puis :

```
uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/parse_output.py" result <fichier>
```

Code 1 : la sortie n'a pas la forme du contrat. Reprends le coder une fois (`SendMessage`) avec la
phrase que le script a rendue ; un second échec se traite comme `RESULT: FAILED`. Code 0 :

- `RESULT: PR` : la PR entre dans la file de revue.
- `RESULT: BLOCKED` : d'abord l'agent `forge:staff-engineer` (outil Agent, au premier plan), ou
  `forge:product-owner` si la question est produit ou UX, avec la question, la recommandation du
  coder, le ticket et la feature. Un `TECHNICAL` de `forge:product-owner` part, une fois, vers
  `forge:staff-engineer`. Selon le verdict :
  - `DECIDED` : commente le ticket (`Décision (<agent>, <ligne MATRIX_CELL>)`, la décision, sa
    source ; `needs-your-attention` si `VETO: yes`), puis relance un `forge:coder` sur le ticket
    avec ce bloc ; sa PR écrit la décision là où dit `WRITE_TO`. Pas d'arrêt.
  - `DOMAIN` : la question porte sur la doctrine du métier. Passe-la à l'agent que nomme la clé
    `domain-arbiter`, avec la même entrée, et suis le contrat de sortie que cet agent décrit. Sans
    la clé, traite-la comme `RESERVED`.
  - `RESERVED` : une décision réservée à un humain (clé `accepting-human`) ou un geste qu'aucun
    agent ne peut faire (signature, runner, secret, facturation, permission). Commente le ticket
    avec le geste et la recommandation, pose `ready-for-human`, retire `ready-for-agent`,
    `agent-claimed` et l'assignation, et continue les autres tickets ; le compte rendu liste le
    geste.

  Un détail d'implémentation que la spec ne fixe pas relance directement le coder avec « décide-le
  et écris-le dans la PR ». Un ticket n'est jamais relancé deux fois sur la même question : si la
  question revient, commente le ticket, pose `needs-info`, retire `ready-for-agent`,
  `agent-claimed` et l'assignation, et continue. Aucune question n'arrête le passage.
- `RESULT: FAILED` : commente le ticket avec la commande et sa sortie, retire `agent-claimed` et
  l'assignation. **Arrêt sur incident.**

## 3. Relire et fusionner, une PR à la fois

Jamais deux `/forge:qc` en même temps : la fusion est sérielle. Prends la première PR de la file.

1. **À jour ?** `git fetch origin`, puis
   `git merge-base --is-ancestor origin/<base> origin/<branche de la PR>`.
   - Oui : étape 3.2.
   - Non : lance un `forge:coder` en **mode sync** (au premier plan, `isolation: worktree`) avec la
     PR, le ticket et la base. Lis sa sortie comme à l'étape 2. `RESULT: PR` : étape 3.2.
     `RESULT: BLOCKED` ou `FAILED` : commente la PR, pose `needs-your-attention`, **arrêt sur
     incident**.

   Une PR se remet à jour avant sa revue, jamais après son verdict : `forge:qc-gate` doit mesurer
   la tête qui fusionnera.
2. **Intacte ?** `gh pr view <n> --json state,reviews,comments` : la PR est ouverte, sans revue
   GitHub, et sans verdict `ROUND:` si un coder de ce passage l'a ouverte. Sinon elle a été jugée
   ou fusionnée hors de `/forge:qc` : pose `needs-your-attention`, **arrêt sur incident**.
3. Lance le skill `forge:qc` sur la PR. Il mesure, juge, fusionne sur ACCEPT, et renvoie le ticket
   en reprise sur un second REJECT (une seule par ticket). Sur un REJECT au tour 1, la correction
   revient à un `forge:coder` en **mode correction** (au premier plan, `isolation: worktree`), avec
   la PR, le ticket, la base et le verdict ; le coder qui a ouvert la PR, repris par
   `SendMessage`, s'il est encore joignable. Lis sa sortie comme à l'étape 2 ; `BLOCKED` ou
   `FAILED` : **arrêt sur incident**. Tu ne corriges rien toi-même. Puis `/forge:qc` reprend au
   tour 2.

Après `/forge:qc` :

- **Fusionnée sur la branche par défaut** : `Closes #n` ferme le ticket.
- **Fusionnée sur une autre base** : GitHub ne ferme un ticket que sur la branche par défaut.
  Ferme-le toi-même, pour débloquer la suite :
  `gh issue close <n> --comment "Fusionné dans <base> par #<pr> ; atteindra la branche par défaut avec <base>."`
- **Renvoyé en reprise** (`agent-rework`) : `/forge:qc` l'a remis en `ready-for-agent` mais
  assigné. Retire l'assignation et `agent-claimed` : la frontière exige un ticket sans assigné. Il
  y revient, et un coder neuf le reprend à l'étape 2 dans ce passage, sous les mêmes plafonds.
- **`needs-your-attention` sans fusion**, ou fusion refusée : **arrêt sur incident**.

Une fusion déplace la base : les autres PR de la file passeront par 3.1. Elle peut aussi débloquer
des tickets : relis l'étape 1, puis retourne à l'étape 2.

## 4. Arrêts

Un arrêt ferme le robinet, il ne coupe pas le travail en cours : plus aucun coder ne part, et ceux
en vol vont jusqu'à leur sortie, que tu traites comme à l'étape 2.

- **Plafond atteint** : `--max` tickets lancés, la durée depuis l'heure de départ, ou les jetons
  d'agents. Ces jetons sont la somme des `subagent_tokens` que rend le bloc `<usage>` de chaque
  agent du passage, coders et agents de `/forge:qc` compris ; les tiens ne se lisent pas. Vérifie
  les trois, et `.claude/PAUSED`, avant chaque lancement de l'étape 2. La file de revue se vide
  normalement (étape 3, remises à jour comprises), puis tu rends compte.
- **Arrêt sur incident** (échec, remise à jour impossible, fusion refusée ; une question n'arrête
  jamais le passage, étape 2) : plus aucun `/forge:qc` ne part non plus. Les PR de la file restent
  ouvertes ; le passage suivant les reprend en tête (étape 1, priorité 1). Tu rends compte dès que
  plus aucun coder n'est en vol.
- **Frontière vide, rien en vol, file vide** : toutes les sous-issues fermées, étape 5 ; des
  tickets encore ouverts (humains ou bloqués), étape 6.

## 5. Après le dernier ticket

Quand toutes les sous-issues sont fermées, lis l'état de la feature (`/forge:feature-status
F-NNNN`, ou les en-têtes des documents de son dossier) :

- pas de recette : lance le skill `forge:feature-verify F-NNNN`, sur la base du passage. Sa PR est
  de la doc, relue par `/forge:qc` en une passe. Puis arrête-toi :
  **`/forge:feature-accept F-NNNN recette`** est à l'humain de la clé `accepting-human` ;
- recette acceptée, pas de doc livrée : lance le skill `forge:feature-close F-NNNN`, puis
  arrête-toi : **`/forge:feature-accept F-NNNN livree`** est à cet humain ;
- un document `en-revue` : arrête-toi, il attend son acceptation.

Tu ne lances jamais `/forge:feature-accept`, et tu ne fermes jamais l'issue de suivi :
`forge:feature-close` le fait, après acceptation.

## 6. Rendre compte

Au décideur :

```text
| Ticket | PR | Remise à jour | Verdict | État |
|---|---|---|---|---|
| #244 | #280 | 1 | ACCEPT au tour 1 | fusionné sur <base>, fermé |
| #245 | #281 | 0 | - | ouverte, en file |
```

Puis la durée du passage et ses jetons d'agents, qui calibrent les plafonds ; la **raison de
l'arrêt**, en une ligne (plafond atteint et lequel, pause, reprise épuisée, remise à jour
impossible, acceptation attendue, tickets humains restants) ; les questions passées à l'arbitre de
domaine et les tickets `ready-for-human` ou `needs-info` ; chaque clé de `docs/agents/usine.md`
trouvée absente ; et **ce que le décideur doit faire**, jamais répondre à une question : faire un
geste qu'aucun agent ne peut faire sur un ticket `ready-for-human` en le nommant, taper
`/forge:feature-accept`, ou relancer `/forge:feature-build F-NNNN` pour la suite. Une moyenne de
plus d'une remise à jour par PR dit que le parallélisme coûte plus qu'il ne rapporte : signale-le.
