---
feature: F-0005
document: cadrage
statut: en-revue
taille: M
destinataires: ikoro-labs (humain de la clé `accepting-human`) ; acceptation par `/forge:feature-accept`, lancée par le modèle sous la clé `agent-autonomy` une fois les points ouverts tranchés ; forge:qc relit
contexte: forge (plugin) ; touchés : un agent nouveau sous `agents/`, un skill nouveau, un script sous `scripts/`, `guard_readonly` (liste `READERS`), un garde et `hooks/hooks.json`, le skill `feature-frame`, `docs/installation.md`
base: fad5921
date: 2026-11-28
---

# F-0005 : cadrage

Quand un projet se branche sur l'usine, un agent d'audit en lecture seule lit le dépôt et écrit un
rapport (l'idée du projet, le code, les tests, la documentation, les risques, des propositions), que
le premier cadrage cite ; aucun cadrage ne s'ouvre tant que ce rapport n'est pas fusionné. Elle
prouve qu'un projet entre dans la chaîne des features avec une image commune et sourcée de son
dépôt, et qu'aucune configuration ne retire cette étape.

Brouillon de la session forge : chaque recommandation encore à trancher renvoie à sa question de la
séance `seances/2026-11-28-ikoro-labs-cadrage.md` (section 9).

## 1. Problème

**Qui souffre, de quoi.** L'humain qui branche un projet, et les agents de son premier cadrage.
Faits relevés le 2026-11-28 sur `fad5921` :

- brancher un projet, c'est copier à la main `plugins/forge/templates/usine.md`, 1 189 lignes et
  113 clés, puis garder ou supprimer chaque ligne (`docs/installation.md:61-62`) ; ce dépôt en
  déclare 35 ; aucun audit ne précède le premier cadrage ;
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
| EXI-01 | Un agent d'audit (nom provisoire `forge:repo-auditor`), en lecture seule : dans `READERS` de `guard_readonly` (`guard_readonly.py:48-51`), outils `Read, Grep, Glob, Bash` sans outil web, modèle fixé dans son front matter. Il rend le texte du rapport, il n'écrit rien (Q5) | `idee.md:16-19` ; `agents/qc-conf.md:4` ; `agents/staff-engineer.md:13-14` |
| EXI-02 | Un skill qui lance le script puis l'agent, écrit le rapport et ouvre la PR ; tapé par l'humain, ou lancé par le modèle sous `agent-autonomy` (`autonomie.md`) | `idee.md:16-19` |
| EXI-03 | Un script d'inventaire de la bibliothèque standard sous `plugins/forge/scripts/`, rejouable, dont l'agent cite la sortie (Q3) | `agents/staff-engineer.md:21-22`, « le déterministe avant le LLM » |
| EXI-04 | Le rapport : Markdown à chemin fixe (provisoire `docs/agents/audit-du-depot.md`) ; en-tête SHA complet, date, version, chemins lus et écartés ; sections idée, code, tests, documentation, risques, propositions avec leur force, non vérifié. Reprend de `improve-codebase-architecture` le vocabulaire de `codebase-design`, les frictions, le test de suppression, les forces et « aucun candidat est un résultat valide » (Q4, Q9) | `SKILL.md:19-21`, `:41-47`, `:53-55`, `:75-78` |
| EXI-05 | Le dépôt neuf : même rapport, court, qui le dit et liste ce qui manque comme risques (Q8) | `idee.md:47` |
| EXI-06 | Lecture sans risque : fichiers suivis seuls ; aucun contenu d'un chemin classé secret possible, nommé comme risque ; aucune valeur de secret ni donnée réelle citée (Q10) | `protocole.md`, « Ce qui n'entre jamais » ; `hooks.json:58` |
| EXI-07 | Obligatoire : un garde refuse la création d'un `cadrage.md` tant que le rapport n'est pas sur `origin/<branche par défaut>`, avec une ligne au journal des refus ; `feature-frame` le dit ; une notice de démarrage, qui échoue ouvert, signale l'audit manquant. Le chemin est fixe, aucune clé ne le désactive (Q6, Q7) | `idee.md:25-26` ; `.claude/rules/forge.md:12-13` ; `guard_ticket_budget.py:1-2` |
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
(`idee.md:7`, `:37-39`) ; l'humain qui acceptera ce cadrage en décide (Q1).

## 4. Observabilité

| Question | Réponse |
|---|---|
| Quelle métrique prouve que ça marche | La part des projets branchés (ceux qui ont `docs/agents/usine.md`) dont le rapport est fusionné ; la part des propositions du rapport citées par le premier cadrage ; les jetons d'un audit et ceux du premier cadrage, avant et après, par `/forge:audit-jetons`, qui compte par rôle (Q14) |
| Quelle alerte si ça casse | Une ligne du journal des refus (`hooks/refusal_journal.py`) à chaque cadrage refusé faute de rapport ; un audit au-delà de son plafond de jetons, fixé dans la spec (Q14) |
| Que voit-on dans une trace | L'en-tête du rapport (SHA, chemins lus et écartés, version du plugin, durée) et la sortie du script d'inventaire, rejouable sur le même SHA |

## 5. Risques

| Risque | Mitigation | Signal |
|---|---|---|
| Un secret ou une donnée réelle entre dans le rapport, sur un dépôt public | EXI-06 ; le script nomme les chemins à risque sans les lire ; relecture par `forge:qc` ; aucun hook de forge ne cherche aujourd'hui un secret dans un écrit (constat du 2026-11-28) | Une valeur de secret dans un diff de rapport |
| `guard_readonly` ne voit pas `Read` (`hooks.json:58`) : la règle de lecture reste une consigne | Fichiers suivis seuls, liste de chemins exclus fournie par le script ; pas d'outil web, rien ne sort du poste | Un chemin exclu dans « chemins lus » de l'en-tête |
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

## 8. Critères d'arrêt

Dates proposées par la session (Q15) ; l'acceptation les fixe.

| Vérification | Condition de poursuite | Si non atteinte |
|---|---|---|
| 2026-12-12 | Spec acceptée | Reporter d'une semaine, la cause commentée sur #413 |
| 2026-12-19 | Agent, skill et script fusionnés ; un rapport fusionné sur ce dépôt et sur le dépôt d'essai | Clore sur ce qui est fusionné, le reste sur #413 |
| 2027-01-08 | Le garde fusionné par l'humain (H1) ; un projet consommateur audité ; métriques de la section 4 relevées | Clore sur l'agent seul, sans garde ; le garde reporté sur #413 |

## 9. Points ouverts

Chaque point renvoie à la séance `seances/2026-11-28-ikoro-labs-cadrage.md`, tour 1.

- Q1 (`forge:product-owner`, attendu `RESERVED`) : condition d'entrée, section 3.
- Q2 (`forge:product-owner`) : qui souffre, cas d'usage unique, section 1.
- Q3 (`forge:staff-engineer`) : script d'inventaire plus agent, EXI-03.
- Q4 (`forge:staff-engineer`) : ce qui est repris de `improve-codebase-architecture`, EXI-04.
- Q5 (`forge:staff-engineer`, T5 puis H1) : rôle en lecture seule, EXI-01.
- Q6 (`forge:staff-engineer`, T5 puis H1) : « obligatoire » par chemin fixe et garde, EXI-07.
- Q7 (`forge:product-owner`) : projets déjà branchés, EXI-07.
- Q8 (`forge:product-owner`) : dépôt neuf, EXI-05.
- Q9 (`forge:staff-engineer`) : chemin et format du rapport, EXI-04.
- Q10 (`forge:staff-engineer`) : lecture sans risque, EXI-06.
- Q11 (`forge:product-owner`) : périmètre et hors périmètre, section 2.
- Q12 (`forge:product-owner`) : taille M, un lot.
- Q13 (`forge:staff-engineer`) : ordre avec F-0003 (#340, ouverte) et F-0004 ; le garde attend le
  lot 1 de F-0003.
- Q14 (`forge:staff-engineer`) : observabilité, section 4.
- Q15 (`forge:product-owner`) : risques et dates, sections 5 et 8.
