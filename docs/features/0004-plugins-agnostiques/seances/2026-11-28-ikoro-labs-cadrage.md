---
feature: F-0004
seance: 2026-11-28-ikoro-labs-cadrage
participants: ikoro-labs (humain de la clé `accepting-human`, par sa session de pilotage), la session forge, forge:product-owner, forge:staff-engineer
sujet: trancher les questions du cadrage que les faits ne règlent pas
---

# Séance du 2026-11-28 : cadrage de F-0004

Écrite pendant la séance, tour par tour, jamais réécrite ensuite. Une correction se fait dans une
séance suivante, qui cite celle-ci.

## Sources apportées

| Source | Où | Empreinte | Ce qui en est retenu |
|---|---|---|---|
| Demande de l'humain du 2026-11-28, relayée par sa session de pilotage | hors dépôt : échange privé, résumé dans `idee.md` sans citation | sans objet | le périmètre, Claude Code d'abord sans régression, Codex ensuite, construction après le lot 1 de F-0003 |
| Audit d'un second plugin de l'humain | hors dépôt : dépôt privé, fichier local non suivi | sans objet | rien n'en est repris ici |
| Textes de référence lus le 2026-11-28 | URL dans l'annexe B du cadrage | sans objet | correspondance aux standards, risques de la section 5 |

## Tours

### Tour 1

Questions de la session forge. P : produit, pour `forge:product-owner`. T : technique, pour
`forge:staff-engineer`. Chaque décideur rend sa décision avec sa case de la matrice, ou `RESERVED`.

**Q1 (P). Une feature en deux lots, ou deux features ?** Le cadrage est en taille L. Lot A : coeur
neutre et adaptateur Claude Code, sans changement de comportement ; lot B : adaptateur Codex.
Recommandation : une seule feature, deux lots, un point de décision entre eux, comme F-0003 ; une
seule issue de suivi.
Réponse de forge:product-owner (P2) : DECIDED. Une feature, deux lots, un point de décision entre eux, une issue (#395) ; lot A d'abord.

**Q2 (P). Le lot B attend-il un utilisateur Codex réel ?** Aucun projet consommateur n'est sous Codex
à la date du cadrage, à la connaissance de la session (non vérifié auprès des autres sessions).
Recommandation : le lot B n'entre que si un projet nommé travaille sous Codex à la date du point de
décision et si la sonde Codex a passé ; sinon la feature se clôt sur le lot A, ce qui garde la
séparation, utile à elle seule pour le second plugin.
Réponse de forge:product-owner : RESERVED, veto. L'entrée du lot B est une entrée de feature, la clé `entry-gate` est absente et aucune case ne la délègue. Recommandation : garder la condition proposée (projet nommé sous Codex, sonde passée), sinon clore sur le lot A. La PR du cadrage reçoit `needs-your-attention`.

**Q3 (P). Quelle parité sous Codex ?** « Tout ce que forge fait » comprend la passation drainée, le
registre des sessions, l'audit des jetons et des objectifs tirés des transcripts, tous liés à Claude
Code. Recommandation : parité pour la chaîne des features, le coder, `forge:qc`, les décideurs et
tous les gardes ; la passation, l'audit des jetons et les évaluations restent propres à Claude Code,
listés comme tels dans `docs/installation.md`. Avec le répartiteur de F-0003, un agent court par
ticket, la passation perd de son poids.
Réponse de forge:product-owner (P3, P1 pour le libellé) : DECIDED, recommandation retenue ; sans gardes chargés, l'adaptateur le dit.

**Q4 (T). La contrainte d'ordre couvre-t-elle aussi ce qui ne touche pas les hooks ?** Le manifeste
racine, la conformité des skills et le gabarit `AGENTS.md` ne touchent pas les hooks.
Recommandation : garder la contrainte telle que l'humain l'a posée, toute la construction après la
fusion du lot 1 de F-0003 ; une exception changerait sa décision, ce qui lui revient.
Réponse de forge:staff-engineer : à venir.

**Q5 (T). Un fichier de hooks partagé, ou un par adaptateur ?** Codex lit par défaut
`hooks/hooks.json` et pose `CLAUDE_PLUGIN_ROOT` : il chargerait les filtres et la commande POSIX
écrits pour Claude Code. Recommandation : plus de `hooks/hooks.json` par défaut ; un fichier par
adaptateur, produit depuis une table neutre (quel garde sur quel geste), désigné par la clé `hooks`
de `.claude-plugin/plugin.json` pour Claude Code et par `extensions.com.openai.hooks` pour Codex ; un
test garde que les fichiers produits suivent la table. Touche `hooks.json` : fusion humaine (T5, H1).
Réponse de forge:staff-engineer : à venir.

**Q6 (T). Comment un script de hook sait-il sous quel outil il tourne ?** Les variables ne
discriminent pas : Codex pose aussi `CLAUDE_PLUGIN_ROOT`. Recommandation : l'adaptateur passe l'outil
en argument dans la commande du hook (par exemple `--outil codex`) ; sans argument, le comportement
de Claude Code, pour ne rien changer au lot A.
Réponse de forge:staff-engineer : à venir.

**Q7 (T). Que fait un hook devant une charge qu'il ne sait pas lire ?** Recommandation : un garde
de rôle ou de commande refuse et écrit une ligne au journal des refus (outil, événement, champs
manquants) ; un hook qui avertit ou observe laisse passer, comme `guard_pause` aujourd'hui. C'est la
règle actuelle d'un garde qui échoue, étendue à la charge illisible.
Réponse de forge:staff-engineer : à venir.

**Q8 (T). Comment une skill trouve-t-elle un fichier partagé hors de son dossier ?** 19 skills et 2
agents s'appuient sur la substitution de `${CLAUDE_PLUGIN_ROOT}` dans le Markdown, propre à Claude
Code ; Agent Plugins 1.0 ne développe `${PLUGIN_ROOT}` que dans les champs MCP ; la substitution
sous Codex n'est pas vérifiée. Options : garder la substitution par outil, copier les fichiers dans
chaque skill à la construction, chemins relatifs, serveur MCP, commandes sur le `PATH`.
Recommandation : vérifier d'abord, par la sonde Codex, si Codex substitue la variable ; à défaut, une
copie produite par adaptateur et gardée par un test, une seule source dans le dépôt.
Réponse de forge:staff-engineer : à venir.

**Q9 (T). Les en-têtes des rôles : produits ou écrits à la main ?** Recommandation : une table
unique (rôle, outils permis, modèle, effort) et un script de la bibliothèque standard qui produit
les en-têtes de chaque outil ; les fichiers produits sont versionnés et un test garde qu'ils suivent
la table, pour que `claude plugin validate` et Codex lisent des fichiers réels.
Réponse de forge:staff-engineer : à venir.

**Q10 (T). Le modèle d'un rôle sous un autre outil ?** `sonnet`, `haiku` et `effort` n'ont pas de
correspondance sous Codex. Recommandation : une clé de `usine.md` par outil qui donne le modèle de
chaque rôle ; absente, l'en-tête du rôle ne fixe pas de modèle, ce que la documentation dit
« sans objet (clé absente) » ; le choix pour Claude Code reste dans le front matter, inchangé.
Réponse de forge:staff-engineer : à venir.

**Q11 (T). Un serveur MCP pour les scripts déterministes ?** MCP est le seul standard qui rendrait
`factory_slo.py`, `question_delay.py` ou `matrice.py` appelables par tout client. Recommandation :
hors périmètre ; les deux outils lancent des commandes, aucun besoin d'un troisième client n'est
prouvé ; la suite se commente sur l'issue de suivi.
Réponse de forge:staff-engineer : à venir.

**Q12 (T). Quelle disposition du dossier ?** Recommandation : le coeur reste en place sous
`plugins/forge/` ; `skills/` reste à la racine du plugin, lu tel quel par Agent Plugins, Claude Code
et Codex ; les adaptateurs vont sous `plugins/forge/adapters/<outil>/` (fichier de hooks, en-têtes
des rôles, table des gestes d'orchestration) ; le manifeste Agent Plugins à la racine du plugin.
Réponse de forge:staff-engineer : à venir.

**Q13 (P). Que recommande-t-on aux projets pour leurs instructions ?** Claude Code lit `AGENTS.md`
en repli quand il n'a pas de `CLAUDE.md` (depuis 2.1.277), Codex et Gemini CLI le lisent d'abord.
Recommandation : le gabarit et `docs/installation.md` recommandent un `AGENTS.md` commun et un
`CLAUDE.md` qui l'importe, plus les règles propres à Claude Code ; ce dépôt garde son `CLAUDE.md`
dans cette feature.
Réponse de forge:product-owner (P1) : DECIDED. Un `AGENTS.md` commun et un `CLAUDE.md` qui importe `@AGENTS.md` puis ajoute les règles propres à Claude Code, sans lien symbolique (https://code.claude.com/docs/en/memory, lue le 2026-11-28) ; ce dépôt garde son `CLAUDE.md`.

**Q14 (T). Qui fournit Codex pour la sonde et l'essai ?** La sonde et l'essai de bout en bout
demandent Codex installé et un compte sur le poste, non vérifiés. Recommandation : demander à
l'humain, au début de la sonde, le compte et un plafond de dépense ; c'est un geste de compte,
sans doute `H3`.
Réponse de forge:staff-engineer : à venir (probablement `RESERVED`, H3).

## Décidé

| Décision | Par | Va dans |
|---|---|---|
| Coeur neutre et adaptateurs minces ; Claude Code d'abord, sans régression ; Codex ensuite | ikoro-labs, demande du 2026-11-28 | cadrage, section 7 |
| Construction après la fusion du lot 1 de F-0003 | ikoro-labs, même demande | cadrage, section 7 |
| Audit du second plugin hors dépôt, sans nom ni contenu ici | ikoro-labs, même demande | cadrage, section 2 |

## Resté ouvert

- Q2 : réservé à l'humain (veto), recommandation écrite au tour 1. Q1, Q3, Q13 tranchés, à reporter dans le cadrage (section 7).
- Réponses de forge:staff-engineer, 2026-11-28, à reporter dans les créneaux du tour 1 et dans le cadrage :
  Q4 DECIDED, ordre de l'humain gardé (T2). Q5 DECIDED, un fichier de hooks par adaptateur ; au lot A,
  `hooks/hooks.json` de Claude Code inchangé, pas de manifeste racine sans valeur Codex explicite (T5, fusion
  H1). Q6 DECIDED, argument `--outil` (T2). Q7 DECIDED, refus sur charge illisible ; `guard_ticket_budget.py`
  admet un `tool_input` qui n'est pas un dictionnaire, à aligner (T2). Q8 DECIDED, substitution de Claude Code
  gardée, Codex à sonder, repli par copie produite (T2). Q9 DECIDED, en-têtes produits, Claude Code identique
  octet pour octet (T2). Q10 DECIDED, une clé de modèle par outil (T4). Q11 DECIDED, MCP hors périmètre (T2).
  Q12 DECIDED, disposition acceptée, manifeste racine sans `version` (T2). Q14 RESERVED (H3) : compte,
  installation et plafond Codex reviennent à l'humain. Charge Codex lue par les gardes : non prouvée, risque
  non prouvé ; sans `agent_type` dans la charge Codex, deux filtres de garde seraient inertes ; aucun essai ;
  une ligne « non pris en charge sous Codex » ira dans `docs/installation.md`. Sources lues le 2026-11-28 :
  https://learn.chatgpt.com/docs/hooks, https://developers.openai.com/codex/plugins/build.md,
  https://code.claude.com/docs/en/plugins-reference.
- Restent à l'humain : Q2 (veto, entrée du lot B) et Q14 (H3, accès à Codex).
