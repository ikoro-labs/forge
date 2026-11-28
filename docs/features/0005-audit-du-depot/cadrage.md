---
feature: F-0005
document: cadrage
statut: en-revue
taille: M
destinataires: ikoro-labs (humain de la clé `accepting-human`) ; acceptation par `/forge:feature-accept`, lancée par le modèle sous la clé `agent-autonomy` une fois les points ouverts tranchés ; forge:qc relit
contexte: forge (plugin) ; touchés : un agent nouveau sous `agents/`, un skill nouveau, un script sous `scripts/`, `guard_readonly` (liste `READERS`), un garde et `hooks/hooks.json`, le skill `feature-frame`, `docs/installation.md`
base: 3886526
date: 2026-11-28
---

# F-0005 : cadrage

Quand un projet se branche sur l'usine, un agent d'audit en lecture seule lit le dépôt et écrit un
rapport (l'idée du projet, le code, les tests, la documentation, les risques, des propositions), que
le premier cadrage cite ; aucun cadrage ne s'ouvre tant que ce rapport n'est pas fusionné. Elle
prouve qu'un projet entre dans la chaîne des features avec une image commune et sourcée de son
dépôt, et qu'aucune configuration ne retire cette étape.

Brouillon de la session forge, réponses des décideurs reportées : chaque décision renvoie à sa question de la
séance `seances/2026-11-28-ikoro-labs-cadrage.md` (section 9).

## 1. Problème

**Qui souffre, de quoi.** L'humain qui branche un projet, et les agents de son premier cadrage.
Faits relevés le 2026-11-28 sur `fad5921` :

- brancher un projet, c'est copier à la main le gabarit `plugins/forge/templates/usine.md`
  (`docs/installation.md:61-62`) ; aucun audit ne précède le premier cadrage, et aucun agent ne part
  d'une image commune du dépôt (Q2 : le compte des clés du gabarit n'est pas une preuve ici, l'audit
  n'écrit aucune clé, c'est F-0006) ;
- chaque commande de la chaîne refait sa propre lecture du code (protocole des features, étape 4) ;
  le coût de ces relectures n'est pas mesuré ;
- l'outil le plus proche, `forge:improve-codebase-architecture`, se conduit avec un humain qui
  tranche, sur une zone et non sur le dépôt, et écrit son rapport HTML hors du dépôt
  (`plugins/forge/skills/improve-codebase-architecture/SKILL.md:16-17`, `:26-35`, `:51`) : les agents
  de l'usine ne l'exécutent pas et ne lisent pas ce rapport.

**Pourquoi pas plus simple.** Une liste de contrôle dans `docs/installation.md` ne produit ni
jugement ni trace, et rien ne vérifie qu'elle a été suivie ; une configuration ne dit pas l'idée d'un
projet. Un script de la bibliothèque standard dresse l'inventaire compté (langages, tests, CI,
dépendances verrouillées, chemins qui ressemblent à un secret, nommés sans contenu) ; un LLM ne fait
que ce qu'un script ne sait pas : résumer l'idée, juger, proposer (Q3).

**Le cas d'usage unique.** Un dépôt existant se branche. Le skill d'audit lance le script puis
l'agent ; l'agent rend le rapport, le skill l'écrit au chemin fixe et ouvre une PR, que `forge:qc`
relit et fusionne. `/forge:feature-frame` sur la première feature cite le rapport par `chemin:ligne`
et son SHA. Un dépôt neuf suit le même parcours, avec un rapport court (Q8).

## 2. Périmètre

| Exigence | Contenu | Preuve |
|---|---|---|
| EXI-01 | Un agent d'audit (nom provisoire `repo-auditor`, préfixé `forge`), en lecture seule : dans `READERS` de `guard_readonly` (`guard_readonly.py:48-51`), avec le test de son filtre, car un nom absent n'est pas gardé (`:277`) ; outils `Read, Grep, Glob, Bash` sans outil web ; modèle fixé dans son front matter (proposé : `sonnet`, effort `medium`, confirmé par la mesure de la section 4) ; une entrée dans `FORGE_AGENTS` (`output_check.py:106-115`) pour son retour. Il rend le texte du rapport, il n'écrit rien (Q5) | `idee.md:16-19` ; `agents/qc-conf.md:4` ; `agents/staff-engineer.md:13-14` |
| EXI-02 | Un skill qui lance le script puis l'agent, écrit le rapport et ouvre la PR ; tapé par l'humain, ou lancé par le modèle sous `agent-autonomy` (`autonomie.md`) | `idee.md:16-19` |
| EXI-03 | Un script d'inventaire de la bibliothèque standard sous `plugins/forge/scripts/`, qui lit l'arbre du SHA par git (`ls-tree`, `cat-file`) et non l'arbre de travail, borne le volume lu et rend la liste de lecture de l'agent ; rejouable, testé, l'agent cite sa sortie (Q3, Q10) | `agents/staff-engineer.md:21-22`, « le déterministe avant le LLM » |
| EXI-04 | Le rapport : Markdown à chemin fixe (provisoire `docs/agents/audit-du-depot.md`) ; en-tête SHA complet, date, version, chemins lus et écartés ; sections idée, code, tests, documentation, risques, propositions avec leur force et un identifiant stable, non vérifié. Un gabarit `plugins/forge/templates/audit-du-depot.md` avec son en-tête de contrôle et un front matter lisible par script ; deux SHA nommés, le commit relu (ancêtre de la base) et le commit du rapport, que le cadrage cite. Reprend de `improve-codebase-architecture` le vocabulaire de `codebase-design`, lu par `${CLAUDE_PLUGIN_ROOT}`, les frictions, le test de suppression, les forces et « aucun candidat est un résultat valide » ; le texte repris entre dans `THIRD_PARTY_NOTICES.md` (Q4, Q9) | `SKILL.md:19-21`, `:41-47`, `:53-55`, `:75-78`, `:82-83` |
| EXI-05 | Le dépôt neuf : même rapport, court, qui le dit et liste ce qui manque comme risques (Q8) | `idee.md:47` |
| EXI-06 | Lecture sans risque : fichiers suivis seuls, dans la liste de lecture du script ; le script scanne le contenu hors du contexte du modèle et écarte un fichier qui ressemble à un secret, nommé par son chemin seul ; le même scan passe sur le rapport avant la PR ; aucune donnée réelle citée (consigne : elle ne se détecte pas par motif). Pas de garde sur `Read` dans ce lot : un chemin exclu reste lisible par `cat`, résidu écrit (Q10) | `protocole.md`, « Ce qui n'entre jamais » ; `hooks.json:58` |
| EXI-07 | Obligatoire : un garde refuse la création d'un `cadrage.md` absent tant que le rapport n'est pas sur `refs/remotes/origin/main` (lu par `usine.on_ref`, refus si illisible, le message dit `git fetch origin` et la commande d'audit) ; un script commun au garde et au skill vérifie l'en-tête ; une ligne au journal des refus, et le garde dans `GUARDS` de `factory_slo.py` ; `feature-frame` le dit ; une notice de démarrage hors du préfixe `guard_`, qui échoue ouvert. Le chemin est une constante, aucune clé ne le désactive ; l'épingle et la désactivation du plugin restent possibles, la documentation le dit (Q6, Q7, Q14) | `idee.md:25-26` ; `.claude/rules/forge.md:12-13` ; `guard_ticket_budget.py:1-2` |
| EXI-08 | Documentation : une étape de `docs/installation.md` après la copie de `usine.md`, le résumé du `README.md`, l'entrée du `CHANGELOG.md` | `.claude/rules/forge.md`, version et journal |

**Aucune clé nouvelle.** Une clé absente rend son étape « sans objet » et ne prend aucune valeur par
défaut (`.claude/rules/forge.md:12-13`) : un audit déclenché par une clé se retirerait en supprimant
la ligne. Le chemin fixe du rapport, comme celui de `docs/agents/usine.md`, n'a rien à retirer. Un
garde qui vaut pour tout projet forge sans clé existe déjà (`guard_ticket_budget.py:1-2`).

**Hors périmètre.** Proposer ou écrire les clés de `usine.md` d'un projet : F-0006, qui change la
configuration d'un projet par une PR. Un audit périodique ou l'expiration du rapport : un commentaire
sur #413 si le besoin se montre. Le nom que l'interface de pilotage donne à l'agent : projet de la
page. Corriger ce que l'audit relève : la chaîne des features, à partir du cadrage. Le skill
interactif `improve-codebase-architecture` reste inchangé. Faire de l'audit une pièce du coeur dans
une usine modulaire : F-0006 (Q11).

## 3. Condition d'entrée

Sans objet (clé `entry-gate` absente, `docs/agents/usine.md:127`) : la matrice ne délègue pas
l'entrée d'une feature tant que la clé l'est (`docs/agents/decisions.md:64-65`). La feature est
admise par son issue de suivi #413, ouverte à la demande de l'humain de la clé `accepting-human`
(`idee.md:7`, `:37-39`). Q1 est réservée à l'humain (`forge:product-owner`, aucune case, veto) : son
acceptation de ce cadrage vaut entrée.

## 4. Observabilité

| Question | Réponse |
|---|---|
| Quelle métrique prouve que ça marche | Par projet (le plugin ne voit qu'un dépôt) : le rapport sur `origin/main`, son SHA et son âge ; la part des propositions du rapport citées par le premier cadrage, par leurs identifiants ; le coût d'un audit par `/forge:audit-jetons`, qui compte par rôle, une comparaison avant et après ne valant que sur plusieurs projets (Q14) |
| Quelle alerte si ça casse | Le journal des refus (`hooks/refusal_journal.py`) est local au poste : une trace que lit un indicateur de `factory_slo.py`, pas une alerte qui sonne. Le plafond d'un audit est le volume que lit le script ; un dépassement se commente sur #413 (Q14) |
| Que voit-on dans une trace | L'en-tête du rapport (SHA, chemins lus et écartés, version du plugin, durée) et la sortie du script d'inventaire, rejouable sur le même SHA |

## 5. Risques

| Risque | Mitigation | Signal |
|---|---|---|
| Un secret ou une donnée réelle entre dans le rapport, sur un dépôt public | EXI-06 ; le script scanne les fichiers et le rapport, et nomme les chemins à risque sans les citer ; relecture par `forge:qc` ; aucun hook de forge ne cherche aujourd'hui un secret dans un écrit (constat du 2026-11-28) | Une valeur de secret dans un diff de rapport |
| `guard_readonly` ne voit pas `Read` (`hooks.json:58`), et ce que lit l'agent part vers l'API du modèle | Liste de lecture et chemins exclus fournis par le script ; pas d'outil web ; le résidu (`cat` d'un chemin exclu) est écrit, un garde de lecture reste une option T5 puis H1 | Un chemin exclu dans « chemins lus » de l'en-tête |
| Le lot 1 de F-0003 ou la fusion humaine (H1) du garde tarde, et les dates glissent | Le garde n'attend que #400 et #404 (Q13) ; au 2027-01-08 non tenu, `needs-your-attention` sur #413 plutôt qu'une clôture sans garde (Q15) | 11 sous-tickets ouverts sur 12 dans #340 au 2026-11-28 |
| Le garde ne lit que `origin/main` | Une autre branche par défaut n'est pas servie : la documentation le dit (Q6) | Un refus sur un dépôt dont la branche par défaut n'est pas `main` |
| Le garde bloque un projet déjà branché au milieu d'une feature | Il ne refuse que la création d'un `cadrage.md` absent ; un cadrage existant se modifie (Q7) | Un refus sur un cadrage déjà présent |
| Un rapport vide ou de complaisance satisfait le garde | Le garde lit le rapport sur la branche par défaut, donc après relecture ; l'en-tête est vérifié (SHA, sections présentes) | Un rapport sans SHA ou sans section accepté |
| L'audit d'un gros dépôt coûte trop de jetons | Lecture bornée, inventaire par script, plafond fixé dans la spec | Jetons d'un audit au-delà du plafond |
| Les propositions dérivent en revue d'architecture interactive | Propositions avec force, sans interrogatoire ; le cadrage ou le design les tranchent | Un rapport qui pose des questions à un humain |

## 6. Faisabilité des données

L'agent lit le dépôt du projet qui se branche, et rien d'autre. Jeu d'acceptation : ce dépôt, dépôt
existant, et le dépôt d'essai public de l'essai de bout en bout (clé `e2e-repo`,
`docs/agents/usine.md:114`), cas du dépôt neuf ; puis un projet consommateur, avec l'accord de
l'humain, son rapport restant dans son dépôt. Exclus : les secrets, les données réelles d'un jeu de
test, tout ce que le protocole exclut (« Ce qui n'entre jamais ») : nommés par leur chemin, jamais
cités. Aucun dépôt privé n'est lu depuis un autre dépôt.

## 7. Décisions

| Date | Décision | Par | Séance |
|---|---|---|---|
| 2026-11-28 | L'agent est obligatoire : aucune usine ne peut le retirer | ikoro-labs (`idee.md:25-26`) | cadrage, sources |
| 2026-11-28 | Priorité : après F-0003, avant F-0006 | ikoro-labs (`idee.md:38-39`) | cadrage, sources |
| 2026-11-28 | Q2, Q7, Q8, Q11, Q12 (taille M, sans lot unique), Q15 | `forge:product-owner` (P1 à P3) | tour 2 |
| 2026-11-28 | Q3, Q4, Q9, Q10, Q14 ; Q5 et Q6 sur la forme, fusion par l'humain (H1) ; Q13 pour la part technique : le garde attend #400 et #404 | `forge:staff-engineer` (T2, T4, T5) | tour 2 |

## 8. Critères d'arrêt

Dates gardées par `forge:product-owner` (Q15) ; le staff-engineer les juge fragiles (Q13) ; l'acceptation
les fixe.

| Vérification | Condition de poursuite | Si non atteinte |
|---|---|---|
| 2026-12-12 | Spec acceptée | Reporter d'une semaine, la cause commentée sur #413 |
| 2026-12-19 | Agent, skill et script fusionnés ; un rapport fusionné sur ce dépôt et sur le dépôt d'essai | Clore sur ce qui est fusionné, le reste sur #413 |
| 2027-01-08 | Le garde fusionné par l'humain (H1) ; un projet consommateur audité ; métriques de la section 4 relevées | Commenter #413 avec `needs-your-attention` : l'humain décide, l'agent seul ne tient pas l'obligation (`idee.md:25-26`) |

## 9. Points ouverts

Chaque point renvoie à la séance `seances/2026-11-28-ikoro-labs-cadrage.md`, tours 1 et 2. Q2 à Q12,
Q14 et Q15 sont tranchées par les décideurs et reportées ci-dessus ; restent à l'humain de la clé
`accepting-human` :

- Q1 (réservée, aucune case, veto) : la condition d'entrée, section 3 ; son acceptation vaut entrée.
- Q13 (réservée, aucune case) : laisser partir l'agent, le skill et le script avant la fin du lot 1 de
  F-0003, ce qui ne touche pas les hooks ; recommandation du staff-engineer : oui. Commentée sur #413.

Pour la spec : qui porte la PR du rapport hors feature (la règle des tickets s'y applique) ; l'effet du
garde sur l'essai de bout en bout (Q8) ; le seuil du dépôt neuf, la liste des chemins secrets, le nom de
l'agent et du rapport.
