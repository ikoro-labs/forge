---
feature: F-0004
document: cadrage
statut: en-revue
taille: L
destinataires: ikoro-labs (humain de la clé `accepting-human`) ; acceptation par `/forge:feature-accept`, lancée par le modèle sous la clé `agent-autonomy` une fois les points ouverts tranchés ; forge:qc relit
contexte: forge (plugin) ; touchés : manifeste et marketplace, `skills/`, `agents/`, `hooks/hooks.json` et les hooks, les scripts lancés par les skills, gabarit `usine.md`, `docs/installation.md`, `docs/sessions.md`
base: c2ecef9
date: 2026-11-28
---

# F-0004 : cadrage

F-0004 sépare forge en un coeur qui ne dépend d'aucun outil d'agent et en adaptateurs minces, un par
outil : Claude Code reste le premier, sans régression, Codex est le deuxième candidat. Elle prouve
qu'un projet peut mener la chaîne des features, le coder et la revue `forge:qc`, gardes comprises,
depuis un autre outil que Claude Code, sans copie du plugin.

Ce cadrage n'écrit que de la documentation. La construction attend que le lot 1 de F-0003 soit
fusionné (#340), les deux touchant les hooks (section 7). L'audit du plugin est en annexe A, la
correspondance aux standards en annexe B.

## 1. Problème

**Qui souffre, de quoi.** L'humain de la clé `accepting-human`, qui tient forge et un second plugin,
et tout projet qui voudrait l'usine sans Claude Code. Faits relevés le 2026-11-28 sur `c2ecef9`, dans
`plugins/forge/` (commandes en annexe A) :

- 64 fichiers Python sous `hooks/` et `scripts/`, 24 286 lignes ; 22 commandes de hook dans
  `hooks/hooks.json`, sur 6 événements, qui lancent 18 scripts distincts ;
- 35 fichiers hors `evals/` citent une variable `CLAUDE_*` (11 Python, 24 Markdown ou JSON) ;
  `${CLAUDE_PLUGIN_ROOT}` revient 101 fois dans les Markdown des skills, agents et gabarits : 19 des
  21 skills et 2 des 7 agents en dépendent pour trouver un fichier partagé ;
- les 7 agents fixent `model`, `effort` et `tools` aux noms de Claude Code (`sonnet`, `haiku`, `Bash`,
  `Skill`...), un format qu'aucun standard ne couvre ;
- sous `hooks/`, 10 fichiers lisent l'identité de l'agent appelant (`agent_type`, `agent_id`) dans la
  charge de Claude Code et 3 lisent `file_path` ; 4 fichiers Python lisent un transcript, 6 appellent
  la CLI `claude` ;
- l'orchestration (lancer un rôle, l'isoler dans un arbre de travail, attendre son retour) est écrite
  dans les skills avec les outils de Claude Code (`subagent_type`, `SendMessage`, `ScheduleWakeup`) :
  6 fichiers hors `evals/`, dont `skills/feature-build/SKILL.md`.

Un projet sur Codex ne peut donc pas utiliser forge aujourd'hui, et le second plugin, de la même
famille, a le même verrou. Fait plus grave, relevé dans la documentation de Codex : Codex lit par
défaut `hooks/hooks.json` à la racine d'un plugin et pose `CLAUDE_PLUGIN_ROOT` pour compatibilité.
Les gardes de forge pourraient donc tourner sous Codex sur une charge qu'elles ne savent pas lire
(`apply_patch` porte un correctif dans `tool_input.command`, pas de `file_path`), et laisser passer
ce qu'elles devraient refuser. Non éprouvé : aucun essai sous Codex n'a été fait.

**Pourquoi pas plus simple.** Trois voies plus simples ont été regardées.

- Ne rien changer et dire « Claude Code seulement » : c'est l'état actuel, il ne répond pas à la
  demande.
- Copier le plugin par outil : deux copies de 24 286 lignes divergent, et chaque correctif de garde
  se ferait deux fois.
- Se conformer aux standards seuls : Agent Plugins 1.0 ne couvre que les skills et les serveurs MCP ;
  les hooks, les agents et les commandes en sont exclus (annexe B). Or les gardes sont ce qui rend
  l'usine sûre : sans elles, un autre outil aurait les skills et pas les refus.

La voie retenue garde une seule copie : un coeur en Markdown et en Python de la bibliothèque standard,
des adaptateurs minces qui traduisent la charge d'un outil vers un événement neutre et la décision
neutre vers la sortie de l'outil. Aucun LLM n'est ajouté. Une chance réduit le coût : le format des
hooks de Codex reprend les noms d'événements, `hooks.json`, le code de sortie 2 et
`hookSpecificOutput.permissionDecision` de Claude Code (annexe B), si bien que l'adaptateur porte
surtout sur la charge (noms d'outils, chemins, identité de l'agent), pas sur le transport.

**Le cas d'usage unique.** Un projet consommateur, qui tient déjà `docs/agents/usine.md`, travaille
sous Codex. Il installe forge depuis la marketplace d'ikoro-labs, lance la chaîne d'une feature,
puis le coder sur un ticket prêt. Le coder tente un `git push` sur `main` : le garde le refuse,
comme sous Claude Code. La PR passe par `forge:qc` et ses deux juges. Le même projet, rouvert sous
Claude Code, se comporte exactement comme avant F-0004.

## 2. Périmètre

Deux lots, dans l'ordre, avec un point de décision entre eux (section 8). Le lot A ne change aucun
comportement sous Claude Code ; le lot B n'entre que sur le « oui » du point de décision.

| Exigence | Contenu | Preuve |
|---|---|---|
| EXI-01 | Lot A. L'audit de l'annexe A, recompté sur la base de la spec, devient la carte du coeur et des adaptateurs : chaque fichier rangé coeur, adaptateur ou propre à un outil | demande de l'humain du 2026-11-28 ; annexe A |
| EXI-02 | Lot A. Un manifeste Agent Plugins 1.0 (`plugin.json` à la racine du plugin, `$schema` épinglé) à côté de `.claude-plugin/plugin.json` ; la version reste dans `.claude-plugin/plugin.json` seul ou passe au manifeste racine, et un test garde qu'elle ne vit qu'à un endroit | spécification Agent Plugins 1.0, section 4.1 ; `.claude/rules/forge.md`, version et journal |
| EXI-03 | Lot A. Les 21 skills restent conformes à la spécification Agent Skills, et un test le garde : `name` égal au dossier, `description` de 1 024 caractères au plus (vrai aujourd'hui), corps sous 500 lignes (`feature-build` en a 561), références à un niveau de `SKILL.md` | agentskills.io/specification ; annexe A |
| EXI-04 | Lot A. Un fichier partagé (`autonomie.md`, `protocole.md`, gabarits, scripts) se trouve sans dépendre de la substitution de `${CLAUDE_PLUGIN_ROOT}` dans le Markdown, propre à Claude Code ; le mécanisme se fixe dans la spec (point ouvert Q8) | doc Claude Code, variables d'environnement des plugins ; Agent Plugins 1.0, section des variables de chemin |
| EXI-05 | Lot A. Le coeur des hooks lit un événement neutre (événement, nature de l'outil, commande, chemins, rôle de l'agent, session) et rend une décision neutre ; un adaptateur par outil traduit l'entrée et la sortie. Un garde qui reçoit une charge qu'il ne sait pas lire refuse | `.claude/rules/forge.md`, hooks et scripts (un garde vaut refus quand il échoue) ; doc des hooks de Codex |
| EXI-06 | Lot A. Adaptateur Claude Code par extraction pure : `hooks.json`, les sorties et les refus inchangés ; les 127 fichiers de tests (2 778 méthodes `test_`) passent sans changement d'attente sous Linux et Windows, `claude plugin validate` passe sur le dépôt et le plugin | `CLAUDE.md`, vérifier avant toute PR ; demande (« sans régression ») |
| EXI-07 | Lot A. Les rôles en source neutre : le corps de chaque agent ne cite aucun outil propre ; ce qui l'est (modèle, effort, outils permis) vit dans un en-tête par outil, produit depuis une table unique et gardé par un test | doc Claude Code des plugins ; doc des sous-agents de Codex (fichiers TOML) |
| EXI-08 | Lot A. Le contrat d'orchestration en verbes neutres (lancer un rôle dans un contexte neuf et isolé, attendre son retour, reprendre plus tard), avec une table par outil chargée à la demande ; le lanceur sans interface du répartiteur de F-0003 devient une commande de l'adaptateur | `skills/feature-build/SKILL.md` ; F-0003, EXI-12 |
| EXI-09 | Lot B, sur le « oui ». Adaptateur Codex : manifeste Codex (`extensions.com.openai` ou `.codex-plugin/plugin.json`), hooks branchés par l'adaptateur, correspondance des outils (`Bash`, `apply_patch`, `spawn_agent`, MCP), rôles en fichiers d'agent Codex, entrée de marketplace Codex | doc Codex des plugins, des hooks et des sous-agents, lue le 2026-11-28 ; rien d'éprouvé |
| EXI-10 | Lot B. L'essai de bout en bout (`e2e_trial.py`, dépôt d'essai de la clé `e2e-repo`) passe sous Codex, avec un défaut planté que les gardes refusent | `docs/agents/usine.md`, essai de bout en bout |
| EXI-11 | Lots A et B. Les instructions d'un projet : le gabarit `usine.md` et `docs/installation.md` disent comment tenir un `AGENTS.md` lu par tous les outils et un `CLAUDE.md` qui l'importe ; la page dit ce qui marche sous chaque outil, et ce qui reste propre à Claude Code | agents.md ; doc Claude Code de la mémoire (lecture d'`AGENTS.md` dès 2.1.277) |
| EXI-12 | Lots A et B. Documentation : chaque clé nouvelle dans le gabarit `plugins/forge/templates/usine.md`, la page de `docs/` qui en traite, `docs/sessions.md` pour la passation, l'entrée du `CHANGELOG.md` | `.claude/rules/forge.md`, version et journal |

**La stratégie d'adaptateur, pour ce qu'aucun standard ne couvre.** Elle se fixe dans la spec ; le
cadrage en pose la forme.

- *Hooks.* Une table neutre dit quel garde s'applique à quel geste (commande shell, écriture de
  fichier, lancement d'un rôle, message de fin, appel à GitHub). Chaque adaptateur en tire son fichier
  de hooks (filtres aux noms de son outil, commande pour son shell) et un traducteur d'entrée et de
  sortie. Le coeur de chaque garde ne voit que l'événement neutre. Le transport étant commun à Claude
  Code et à Codex, le traducteur porte la charge : `apply_patch` contre `Edit` et `Write`, l'identité
  du rôle appelant, les outils propres (`SubagentHandback`, `SendMessage`, `Skill`). Q5 à Q7.
- *Orchestration.* Les skills décrivent les gestes en verbes neutres ; une table par outil, chargée
  à la demande comme une référence, dit l'outil qui les fait (sous Claude Code l'outil `Agent` avec
  isolation en arbre de travail, sous Codex `spawn_agent` et les fichiers d'agent). Le répartiteur
  de F-0003, script sans LLM qui lance un agent sans interface par ticket, prend la commande de
  lancement de l'adaptateur (`claude -p` sous Claude Code ; `codex exec` sous Codex, d'après sa
  documentation, non éprouvé). C'est la raison de fond de l'ordre : F-0003 sort l'orchestration des
  longues sessions vers un script, ce qui rend l'adaptateur plus mince.

**Le second plugin de l'humain.** Son audit a été fait pendant ce cadrage et vit hors de ce dépôt,
dans un fichier local non suivi. Son adaptation, s'il y en a une, se fait dans son propre dépôt. Rien
ici ne le nomme ni ne décrit son contenu.

**Ce qui reste propre à Claude Code, sauf décision contraire (point ouvert Q3).** La passation drainée
d'une session à sa limite de contexte (registre des sessions, relance d'un terminal, seuil lu dans
le transcript), l'audit des jetons et les objectifs de service tirés des transcripts, dont le format
n'est pas stable sous Codex selon sa documentation.

**Hors périmètre.** Un adaptateur Gemini CLI : ses événements ont d'autres noms (`BeforeTool`,
`AfterTool`...), le modèle neutre doit seulement ne pas l'exclure (annexe B). Cursor, Copilot et les
autres clients d'Agent Plugins 1.0 : ils n'ont que les skills, sans gardes. Un serveur MCP pour les
scripts déterministes, sauf décision contraire (Q11). La traduction du contenu en anglais, chantier à
part (`.claude/rules/forge.md`, prose). La configuration des projets consommateurs, qui reste à leur
session. macOS. Les suites de ces points se commentent sur l'issue de suivi #395.

## 3. Condition d'entrée

Sans objet (clé `entry-gate` absente) : les besoins de ce dépôt viennent de ses tickets
(`docs/agents/usine.md`, clés absentes). La feature est admise par son issue de suivi #395 (ligne
`Motif : feature-new F-0004`), ouverte le 2026-11-28 à la demande de l'humain de la clé
`accepting-human` (`idee.md`).

## 4. Observabilité

| Question | Réponse |
|---|---|
| Quelle métrique prouve que ça marche | Non-régression : les 2 778 méthodes de test vertes sous Linux et Windows à chaque PR, et l'essai de bout en bout sous Claude Code qui passe avant et après le lot A. Parité : par outil, la part des 18 scripts de hook et des 21 skills qui ont un test d'adaptateur vert (cible lot A : 18 sur 18 pour Claude Code ; lot B : les gardes sur 18 pour Codex). Un test de contrat par garde : le même événement neutre rend la même décision quel que soit l'adaptateur. Lot B : l'essai de bout en bout sous Codex qui passe |
| Quelle alerte si ça casse | Un job de CI rouge (tests, `validate`, `lint`) ; un essai de bout en bout en `FAIL` sous l'un des outils ; un garde qui refuse pour charge illisible plus d'une fois sur un même outil, relevé par le journal des refus |
| Que voit-on dans une trace | À ajouter : la ligne du journal des refus porte l'adaptateur et la nature de l'événement neutre ; une ligne par charge illisible (outil, événement, champs manquants) ; le rapport de l'essai de bout en bout nomme l'outil sous lequel il a tourné |

## 5. Risques

| Risque | Mitigation | Signal |
|---|---|---|
| Les gardes ne se chargent pas sous Codex : la page Codex de construction des plugins dit les hooks de cycle de vie réservés aux plugins installés à la main dans l'application de bureau, hors de l'annuaire public ; la page des hooks dit qu'un plugin activé peut en livrer | Sonde sur une vraie installation de Codex avant la spec du lot B ; si les gardes ne se chargent pas, l'adaptateur Codex se déclare sans gardes et la clé `agent-autonomy` y est refusée | L'essai sous Codex laisse passer le défaut planté |
| Aujourd'hui déjà, les gardes de forge tournent sous Codex sur une charge mal lue et laissent passer | EXI-05 : charge illisible vaut refus ; une fixture de charge Codex par garde | Un test de fixture Codex qui rend « admis » |
| Régression sous Claude Code pendant l'extraction | Lot A par extraction pure, derrière les tests existants, attentes inchangées ; une PR par garde | Une méthode de test rouge, un essai de bout en bout en `FAIL` |
| Collision avec le lot 1 de F-0003, qui touche aussi les hooks et le lancement des agents | Construction après sa fusion (décision de la section 7) ; la spec relit `hooks/` à sa tête | Un conflit de fusion sur `hooks/` |
| Beaucoup de PR de chemins protégés, donc de fusions humaines (H1) | Grouper par garde ; dire dans la spec combien de PR touchent `hooks.json` | Plus de PR en attente de l'humain que de PR fusionnées sur une semaine |
| Les standards bougent : une source secondaire dit Agent Plugins 1.0 en brouillon, la page de la spec le dit publié ; deux pages Codex se contredisent sur les sous-agents | `$schema` épinglé ; textes relus et datés avant la spec | Une page de référence changée depuis la lecture |
| Un `plugin.json` à la racine gêne Claude Code, qui lit `.claude-plugin/plugin.json` | `claude plugin validate` dans la CI dès la première PR du lot A | Un avertissement ou un échec de `validate` |
| Deux adaptateurs à tenir sans utilisateur Codex réel | Point de décision avant le lot B (Q2) | Aucun projet nommé sous Codex à la date du point |

## 6. Faisabilité des données

Aucune donnée d'un client. Le lot A se mesure sur la suite de tests et l'essai de bout en bout
existants. Le lot B demande un poste avec Codex installé et un compte, que ce cadrage n'a pas
vérifiés (Q14), et des fixtures de charge de hook Codex, tirées de sa documentation puis d'une vraie
session ; le chemin du transcript existe sous Codex, mais son format n'y est pas stable. L'audit du
second plugin reste hors dépôt. Les chiffres relevés par la session de pilotage le 2026-11-28 sur
`6572e1a` ont été recomptés sur `c2ecef9` (annexe A) ; les écarts y sont dits.

## 7. Décisions

| Date | Décision | Par | Séance |
|---|---|---|---|
| 2026-11-28 | Forge garde tout ce qu'il fait et se sépare en un coeur neutre et des adaptateurs minces ; Claude Code reste le premier adaptateur, sans régression ; Codex est le deuxième candidat | ikoro-labs, demande relayée par sa session de pilotage (`idee.md`) | sans objet |
| 2026-11-28 | Le cadrage s'écrit tout de suite ; la construction attend la fusion du lot 1 de F-0003 (#340), les deux touchant les hooks | ikoro-labs, même demande | sans objet |
| 2026-11-28 | L'audit du second plugin de l'humain vit hors de ce dépôt ; rien ici ne le nomme ni ne décrit son contenu | ikoro-labs, même demande | sans objet |

**Points ouverts.** Les questions Q1 à Q14 de la séance
`seances/2026-11-28-ikoro-labs-cadrage.md`, tour 1, attendent `forge:product-owner` (P) et
`forge:staff-engineer` (T) : Q1 lots ou deux features (P), Q2 utilisateur Codex réel (P), Q3 parité
attendue (P), Q4 portée de la contrainte d'ordre (T), Q5 fichier de hooks par adaptateur (T), Q6 choix
de l'adaptateur dans la commande du hook (T), Q7 charge illisible (T), Q8 fichiers partagés (T), Q9
rôles générés (T), Q10 modèle par rôle et par outil (T), Q11 serveur MCP (T), Q12 disposition du
dossier (T), Q13 `AGENTS.md` des projets (P), Q14 accès à Codex (T, sans doute H3). Tant qu'un point
reste ouvert, l'acceptation par le modèle n'est pas permise.

## 8. Critères d'arrêt

Dates proposées par la session (l'acceptation les fixe).

| Vérification | Condition de poursuite | Si non atteinte |
|---|---|---|
| 2026-12-05 | Points ouverts tranchés, cadrage accepté | Reporter les dates d'autant, sur l'issue de suivi |
| Fusion du lot 1 de F-0003, au plus tôt 2026-12-12 | La spec s'écrit sur la tête de `main` qui le porte | Attendre ; rien ne se construit avant |
| 2026-12-19, sonde Codex | Sur une vraie installation de Codex : les hooks d'un plugin se chargent, des charges réelles sont capturées pour chaque garde | Lot B réduit à un adaptateur sans gardes documenté, ou abandonné (Q2) |
| 2027-01-15 | Lot A fusionné ; aucune attente de test changée ; essai de bout en bout sous Claude Code qui passe | Garder ce qui est fusionné ; le reste se commente sur l'issue de suivi |
| 2027-01-22, point de décision | « Oui » au lot B si un projet nommé travaille sous Codex et si la sonde a passé | « Non » : clore la feature sur le coeur neutre et l'adaptateur Claude Code |
| 2027-02-26 | Lot B fusionné ; essai de bout en bout sous Codex qui passe, défaut planté refusé | Clore sur ce qui a tenu ; l'adaptateur Codex reste marqué non éprouvé |

## Annexe A : audit du plugin

Relevé le 2026-11-28 sur `c2ecef9`, dans `plugins/forge/`. Commandes, lancées depuis ce dossier :
`find skills -type f | wc -l` (27 fichiers, dont 21 `SKILL.md`) ; `find agents -type f | wc -l` (7) ;
`find hooks scripts -name '*.py' | wc -l` (64) et leur `cat ... | wc -l` (24 286 lignes) ;
`grep -rlE 'CLAUDE_' --exclude-dir=evals .` (35) ; `grep -rlE "claude -p|\"claude\"|'claude'"` sur les
Python (6) ; `grep -rlE 'hookSpecificOutput|permissionDecision' hooks scripts` (6) ;
`grep -rlE 'transcript_path'` sur les Python (4) ; `grep -rlE 'subagent_type|SendMessage|ScheduleWakeup'`
(26, dont 20 sous `evals/`, donc 6 hors `evals/`).

**Écarts avec les chiffres relayés** (session de pilotage, `6572e1a`) : 24 286 lignes contre 24 199,
la base a avancé ; 35 fichiers `CLAUDE_*` contre 33, la commande d'origine n'est pas connue, l'écart
n'est pas expliqué. Les autres chiffres sont égaux : 27, 7, 64, 6, 6, 4, 6. Événements de hook :
`PreToolUse`, `PostToolUse`, `SessionStart`, `Stop`, `SubagentStop`, `UserPromptSubmit`, confirmés.

| Partie | Coeur | Propre à Claude Code | Standard | Adaptateur |
|---|---|---|---|---|
| Manifeste `.claude-plugin/plugin.json` | nom, version, description | l'emplacement, `displayName` | Agent Plugins 1.0 (`plugin.json` racine) | manifeste par outil, version en un seul lieu |
| Marketplace `.claude-plugin/marketplace.json` | la liste des plugins | l'emplacement, le format | aucun ; Codex lit `.agents/plugins/marketplace.json` | une entrée par outil |
| 21 skills (`SKILL.md`) | le corps, les étapes | `argument-hint` (17), `${CLAUDE_PLUGIN_ROOT}` (19 skills), noms d'outils dans le texte | Agent Skills : conformes sur `name` et `description` ; `feature-build` dépasse 500 lignes | chemin des fichiers partagés (Q8) |
| 6 fichiers de référence de skills | entier | aucun | Agent Skills, `references/` | aucun |
| `autonomie.md` (14 skills), `protocole.md` (10), `socle.md` | entier | le chemin par `${CLAUDE_PLUGIN_ROOT}` | hors standard : hors d'un dossier de skill | Q8 |
| 7 agents | le corps du rôle | `model`, `effort`, `tools`, `omitClaudeMd` ; nom préfixé `forge:` | aucun (exclus d'Agent Plugins 1.0) | en-tête par outil (EXI-07) |
| `hooks/hooks.json` | la table : quel garde sur quel geste | noms d'outils des filtres (`PowerShell`, `MultiEdit`, `NotebookEdit`, `Skill`, `Task`, `Workflow`, `SubagentHandback`, `SendMessage`), commande en shell POSIX | aucun ; Codex a le même format, Gemini CLI un autre | fichier par outil (Q5) |
| 18 scripts de hook | la règle de chaque garde | lecture de `tool_input`, `agent_type`, `file_path` ; sortie `hookSpecificOutput` (6) | aucun | traduction entrée et sortie (EXI-05) |
| Passation et sessions (`handoff_*.py`, `sessions_notice.py`) | le contrat de passation | registre sous `~/.claude`, `CLAUDE_PID`, relance de la CLI, seuil lu dans le transcript | aucun | propre à Claude Code (Q3) |
| 35 scripts (`scripts/`) | presque tout : `factory_slo`, `matrice`, `ticket_graph`, `question_delay`... | `e2e_trial`, `pin_sync`, `eval_reference`, `token_audit` (CLI ou transcripts de Claude Code) | MCP possible, non retenu (Q11) | commande de lancement par outil |
| Gabarits (`templates/`) | entiers | aucun | aucun ; Markdown | aucun |
| Orchestration dans les skills | les étapes, l'ordre, les arrêts | `subagent_type`, isolation en arbre de travail, `SendMessage`, `ScheduleWakeup` | aucun | table des gestes par outil (EXI-08) |
| `evals/` et `eval-traps/` | les cas | `claude plugin eval` | aucun | propre à Claude Code |

**La documentation progressive.** Le modèle tient : chaque skill charge à la demande le protocole,
l'autonomie et les gabarits, et un seul exemplaire de chacun sert 10 à 14 skills. Trois limites. Ces
fichiers partagés vivent hors des dossiers de skill, donc hors de ce qu'Agent Plugins 1.0 sait
adresser. `feature-build` (561 lignes) dépasse la borne de 500 lignes conseillée par Agent Skills, et
trois agents sont longs (`qc-conf` 420, `coder` 310, `qc-gate` 306), chargés en entier à chaque
lancement. Côté projet, `CLAUDE.md` et `.claude/rules/` ne sont lus que par Claude Code, alors
qu'`AGENTS.md` est lu par Codex, Gemini CLI et Claude Code (en repli). Les chemins des règles passent
déjà par des clés (`domain-rules`, `git-rules`), donc neutres.

## Annexe B : correspondance aux standards

Textes lus le 2026-11-28.

| Standard | Statut et gardien | Ce qu'il couvre | Forge aujourd'hui |
|---|---|---|---|
| Agent Skills, https://agentskills.io/specification | Format ouvert, créé par Anthropic ; aucun texte lu ne le dit sous l'AAIF | `SKILL.md`, `name` et `description` requis, `scripts/`, `references/`, `assets/`, chargement progressif, corps sous 500 lignes, références à un niveau | conforme sur l'en-tête ; une skill trop longue ; fichiers partagés hors des dossiers |
| AGENTS.md, https://agents.md | Gardé par l'Agentic AI Foundation, sous la Linux Foundation (page lue) | Markdown libre ; le fichier le plus proche l'emporte | absent ; projets sur `CLAUDE.md` |
| MCP, https://modelcontextprotocol.io/specification/latest (version 2026-07-28) | Projet fondateur de l'AAIF, annoncé le 2025-12-09 (communiqué de la Linux Foundation, vu en résultat de recherche, non relu) | outils, ressources, invites ; extensions dont une pour servir des skills | aucun serveur MCP ; seuls des filtres de hook visent les outils MCP de GitHub |
| Agent Plugins 1.0, https://agent-plugins.org/specification | Publié (page de la spec, sans date) ; billet invité sur aaif.io du 2026-08-06 qui dit le format **hors de l'AAIF**, porté par son propre comité | `plugin.json` racine, `skills/`, `mcp.json`, dossiers d'extension par espace de noms ; commandes, hooks, agents et règles exclus ; `${PLUGIN_ROOT}` développé dans les champs MCP seulement | absent ; clients cités : VS Code, Cursor, Copilot, Codex, Kiro ; Claude Code n'y est pas, et sa doc dit ignorer `$schema` |
| Hooks de Codex, https://developers.openai.com/codex/hooks (redirigé vers learn.chatgpt.com/docs/hooks) | Doc de l'éditeur, sans mention d'essai | mêmes noms d'événements que Claude Code et d'autres ; `hooks.json` ; code 2 ; `permissionDecision` ; `Bash`, `apply_patch` (filtrable en `Edit` ou `Write`), `spawn_agent` (filtrable en `Agent`) ; pose `CLAUDE_PLUGIN_ROOT` ; hooks à approuver par l'utilisateur | même format de transport ; charge différente |
| Plugins de Codex, https://developers.openai.com/codex/plugins/build.md | Doc de l'éditeur | `plugin.json` racine Agent Plugins ou `.codex-plugin/plugin.json` ; `extensions.com.openai.hooks` ; marketplace `.agents/plugins/marketplace.json` | la contradiction sur les hooks de plugin est le premier risque |
| Skills et sous-agents de Codex | Doc de l'éditeur (pages build-skills et subagents, vue en résultat de recherche) | skills sous `.agents/skills` ; agents en TOML sous `.codex/agents/` ; livraison d'agents par un plugin non vérifiée | rôles à traduire |
| Hooks de Gemini CLI, https://geminicli.com/docs/hooks/reference/ | Doc de l'éditeur | `BeforeTool`, `AfterTool`, `BeforeAgent`, `AfterAgent`, `SessionStart`... ; code 2 ; `decision: deny` ; livraison par une extension non vérifiée | hors périmètre |

Non vérifié : l'article de The New Stack sur les écarts de portabilité (accès refusé, HTTP 403) ; la
gouvernance d'Agent Skills ; la livraison d'agents par un plugin Codex ; la substitution de chemins
dans le Markdown d'une skill sous Codex ; les extensions de Gemini CLI. La demande plaçait les quatre
standards sous l'AAIF : seuls AGENTS.md et MCP le sont dans les textes lus.
