---
feature: F-0005
seance: 2026-11-28-ikoro-labs-cadrage
participants: ikoro-labs (humain de la clé `accepting-human`), la session forge (auteur du tour 1), forge:product-owner, forge:staff-engineer
sujet: trancher les questions du cadrage que les faits du dépôt ne règlent pas
---

# Séance du 2026-11-28 : cadrage de F-0005

Écrite pendant la séance, tour par tour, jamais réécrite ensuite. Une correction se fait dans une
séance suivante, qui cite celle-ci.

## Sources apportées

| Source | Où | Empreinte | Ce qui en est retenu |
|---|---|---|---|
| Demande de l'humain du 2026-11-28, relayée par sa session de pilotage | hors dépôt : échange privé, résumé dans `idee.md` sans citation | sans objet | l'agent passe le premier à la connexion d'un projet, son rapport nourrit le premier cadrage, aucune usine ne peut le retirer |
| Faits du dépôt relevés par la session sur `fad5921` | ce dépôt, chemins cités dans chaque question | sans objet | l'état de l'existant, cité en `chemin:ligne` |

## Tours

### Tour 1

Questions de la session forge, dans l'ordre du skill `feature-frame`. P : produit, pour
`forge:product-owner`. T : technique, pour `forge:staff-engineer`. Chaque décideur rend sa décision
avec sa case de la matrice (`docs/agents/decisions.md`), ou `RESERVED`.

**Q1 (P). La condition d'entrée.** La clé `entry-gate` est absente (`docs/agents/usine.md:127`) ;
la matrice dit que l'entrée d'une feature ne se délègue pas tant qu'elle l'est
(`docs/agents/decisions.md:64-65`). Recommandation : écrire « sans objet (clé `entry-gate`
absente) » dans la section 3 du cadrage ; la feature est admise par son issue de suivi #413, ouverte
à la demande de l'humain de la clé `accepting-human` (`idee.md:7`, `idee.md:37-39`), et l'humain
qui acceptera le cadrage en décide. Décideur pressenti : `forge:product-owner`, qui devrait la rendre
`RESERVED` ; la demande de l'humain la tranche déjà.
Réponse : tour 2.

**Q2 (P). Qui souffre, de quoi, et le cas d'usage unique.** Faits : brancher un projet, c'est
copier à la main un gabarit de 1 189 lignes qui documente 113 clés, puis garder ou supprimer chaque
ligne (`docs/installation.md:61-62`, `plugins/forge/templates/usine.md`) ; ce dépôt en déclare 35
(`docs/agents/usine.md` et `usine-gardes.md`, comptage du 2026-11-28). Aucun audit ne précède le
premier cadrage, et chaque commande de la chaîne refait sa propre lecture du code (protocole,
étape 4, « Trouver les faits est ton travail »). Le coût de ces relectures n'est pas mesuré.
Recommandation : celui qui souffre est l'humain qui branche un projet, et les agents du premier
cadrage, qui partent sans image commune du dépôt ; le cas d'usage unique est un dépôt existant qui
se branche : l'audit passe, son rapport est fusionné, le premier cadrage le cite. Le dépôt neuf est
un cas dégradé du même parcours (Q8). Chiffrer par `/forge:audit-jetons` les jetons du premier
cadrage d'un projet, avant et après (section 4 du cadrage).
Réponse : tour 2.

**Q3 (T). La solution la plus simple.** Une étape écrite dans `docs/installation.md` (une liste de
contrôle) ne produit ni jugement ni trace, et rien ne vérifie qu'elle a été suivie. Une
configuration ne peut pas dire l'idée d'un projet ni juger son code. Recommandation : séparer le
déterministe du jugement, selon l'ordre de priorités du décideur (« le déterministe avant le LLM »,
`plugins/forge/agents/staff-engineer.md:21-22`) : un script de la bibliothèque standard sous
`plugins/forge/scripts/` dresse l'inventaire compté (fichiers suivis par langage, tests, workflows
de CI, fichiers de dépendances verrouillées, `README`, licence, chemins qui ressemblent à un
secret, nommés sans leur contenu) ; un agent LLM ne fait que ce qu'un script ne sait pas faire :
dire l'idée du projet en quelques lignes, juger le code, les tests, la documentation et les risques,
et proposer.
Réponse : tour 2.

**Q4 (T). Ce que l'audit reprend de `forge:improve-codebase-architecture`.** Faits : le skill se
conduit avec un humain, qui tranche les candidats ; les agents de l'usine ne l'exécutent pas
(`plugins/forge/skills/improve-codebase-architecture/SKILL.md:16-17`, `:53`, `:57-59`) ; il part
d'une zone, pas du dépôt entier (`:26-35`) ; son rapport HTML est écrit hors du dépôt, dans le
répertoire temporaire (`:51`), et charge Tailwind et Mermaid depuis des CDN
(`HTML-REPORT.md:3`, `:13-15`). Recommandation : reprendre le vocabulaire de `/forge:codebase-design`
employé exactement (`SKILL.md:19-21`), la liste des frictions et le test de suppression (`:41-47`),
les trois forces `strong`, `worth-exploring`, `speculative` (`:53`), « aucun candidat sérieux est un
résultat valide » (`:55`) et les champs consignés : commit relu en SHA complet, chemins réellement
explorés, conclusion en une à trois phrases (`:75-78`). Changer : pas d'humain pour trancher, les
candidats deviennent des propositions avec leur force, tranchées au cadrage ou au design ; le
dépôt entier, borné en lecture ; un rapport Markdown dans le dépôt, que les agents lisent, au lieu
d'un HTML hors du dépôt. Le skill interactif reste inchangé.
Réponse : tour 2.

**Q5 (T). Le rôle qui audite.** Recommandation : un agent nouveau du plugin (nom provisoire
`forge:repo-auditor`, fixé dans la spec), en lecture seule : ajouté à la liste `READERS` de
`guard_readonly` (`plugins/forge/hooks/guard_readonly.py:48-51`), outils `Read, Grep, Glob, Bash`
comme `forge:qc-conf` (`plugins/forge/agents/qc-conf.md:4`), sans `WebSearch` ni `WebFetch`, pour
que rien de ce qu'il lit ne sorte du poste. Il rend le texte du rapport ; le skill qui l'a lancé
l'écrit et ouvre la PR, comme pour les décideurs (`plugins/forge/agents/staff-engineer.md:13-14`).
Modèle fixé dans son front matter (`.claude/rules/forge.md`, hooks et scripts). Toucher `READERS`
change un garde : forme déléguée (T5), fusion humaine (H1).
Réponse : tour 2.

**Q6 (T). Ce que « obligatoire » veut dire pour un plugin.** Faits : une clé absente rend une étape
« sans objet », jamais un défaut, et aucune clé ne prend de valeur par défaut
(`.claude/rules/forge.md:12-13`) : un audit déclenché par une clé se retire en supprimant la ligne,
il n'est donc pas obligatoire. La clé `feature-gate` désigne une commande du projet, que forge ne
fournit pas (`plugins/forge/templates/usine.md:197-201`) et que ce dépôt ne déclare pas
(`docs/agents/usine.md:129`). Le plugin charge tous ses agents, sans liste dans son manifeste
(`plugins/forge/.claude-plugin/plugin.json`). Un garde vaut déjà pour tout projet forge sans clé :
`guard_ticket_budget`, « standard common to every forge project »
(`plugins/forge/hooks/guard_ticket_budget.py:1-2`). Options : A, une étape de l'installation
(rien ne la vérifie) ; B, une étape du protocole de `feature-frame` (texte du plugin, qu'aucune clé
ne retire, mais une consigne) ; C, un garde qui refuse mécaniquement. Recommandation : un chemin fixe
du plugin pour le rapport, pas une clé (comme `docs/agents/usine.md`, chemin fixe), donc rien à
retirer ; C, un garde qui refuse la création d'un `cadrage.md` sous le dossier des features tant que
le rapport n'est pas sur `origin/<branche par défaut>` (lu là, comme `usine-gardes.md`, pour qu'un
fichier vide écrit dans l'arbre de travail ne suffise pas), avec B pour le message et une ligne au
journal des refus ; une notice de démarrage de session qui échoue ouvert, comme `pin_notice`, dit
que l'audit manque. Garde et `hooks.json` : forme déléguée (T5), fusion humaine (H1).
Réponse : tour 2.

**Q7 (P). Les projets déjà branchés.** Ce dépôt et les projets consommateurs ont déjà des features ;
F-0004 a un cadrage en revue. Recommandation : le garde ne refuse que la création d'un `cadrage.md`
absent ; modifier un cadrage existant passe. Chaque projet déjà branché passe donc l'audit une fois,
avant son prochain cadrage, après la montée d'épingle qui apporte la version ; la note de version
le dit. Rien n'est rétroactif sur les documents déjà écrits.
Réponse : tour 2.

**Q8 (P). Le dépôt neuf.** Recommandation : le même rapport, court : il dit « dépôt neuf » et sur
quel critère (seuil de fichiers suivis fixé dans la spec), reprend l'idée du projet depuis le
`README` ou l'`idee.md` de la première feature s'il existe, liste ce qui manque (tests, CI, licence,
règles du dépôt) comme risques, et propose les premiers pas. Il satisfait le garde comme un rapport
complet. Le dépôt d'essai public de l'essai de bout en bout (clé `e2e-repo`,
`docs/agents/usine.md:114`) sert de cas d'acceptation.
Réponse : tour 2.

**Q9 (T). Où vit le rapport, son format, et comment le cadrage le cite.** Recommandation : un
fichier Markdown à chemin fixe, `docs/agents/audit-du-depot.md` (nom fixé dans la spec), à côté de
`usine.md`. En-tête : commit relu (SHA complet), date, version du plugin, agent, chemins lus,
chemins écartés et pourquoi. Sections : l'idée du projet en quelques lignes ; code ; tests ;
documentation ; risques ; propositions, chacune avec sa force ; ce qui n'a pas pu être vérifié. Une
nouvelle passe réécrit le fichier, git garde l'historique. Le premier cadrage le cite par
`chemin:ligne` et par le SHA du rapport, dans sa section 1.
Réponse : tour 2.

**Q10 (T). Ce que l'agent lit sans risque.** Faits : `guard_readonly` ne voit ni `Read` ni `Grep`
ni `Glob` (`plugins/forge/hooks/hooks.json:58`) : un agent en lecture seule peut lire tout fichier
de l'arbre de travail, `.env` compris ; aucun hook de forge ne cherche un secret dans ce qu'un agent
écrit (recherche de `secret`, `.env`, `credential` sous `plugins/forge/hooks/`, 2026-11-28). Le
protocole exclut du dépôt tout secret et toute donnée réelle (`protocole.md`, « Ce qui n'entre
jamais »). Recommandation : l'agent ne lit que les fichiers suivis (`git ls-files`) ; il ne lit
jamais le contenu d'un chemin que le script d'inventaire classe comme secret possible (`.env*`,
clés, certificats, fichiers d'identifiants : liste fixée dans la spec), il le nomme comme risque ;
il ne cite jamais une valeur qui ressemble à un secret, ni une donnée réelle d'un jeu de test,
désignée par son chemin seul ; sans outil web, rien ne sort du poste ; le rapport d'un dépôt privé
reste dans ce dépôt. Le rapport passe par une PR et `forge:qc` comme tout document.
Réponse : tour 2.

**Q11 (P). Le périmètre, et ce qui reste dehors.** Recommandation : dedans, l'agent, le skill qui le
lance, le script d'inventaire, le format du rapport, le garde et sa notice, la documentation.
Dehors : proposer ou écrire les clés de `usine.md` d'un projet (F-0006, qui change la configuration
d'un projet par une PR) ; un audit périodique ou une date d'expiration du rapport (commentaire sur
#413 si le besoin se montre) ; le nom que l'interface de pilotage donne à l'agent (projet de la
page) ; corriger ce que l'audit relève (cela passe par la chaîne, à partir du cadrage) ; le skill
interactif `improve-codebase-architecture`, inchangé.
Réponse : tour 2.

**Q12 (P). La taille.** Recommandation : M, un seul lot : un agent, un skill, un script, un garde,
de la documentation, aucune clé nouvelle. Pas L : un seul outil, aucune infrastructure, rien à
couper.
Réponse : tour 2.

**Q13 (T). L'ordre avec F-0003 et F-0004.** Faits : la priorité donnée par l'humain est après F-0003,
avant F-0006 (`idee.md:38-39`) ; l'issue de suivi de F-0003, #340, est ouverte (2026-11-28) ; F-0004
attend le lot 1 de F-0003 parce que les deux touchent les hooks
(`docs/features/0004-plugins-agnostiques/cadrage.md:20-21`). Recommandation : le garde et
`hooks.json` attendent le lot 1 de F-0003 ; l'agent, le skill, le script et le format du rapport ne
touchent pas les hooks, sauf la liste `READERS` de `guard_readonly`, qui suit le garde.
Réponse : tour 2.

**Q14 (T). L'observabilité.** Recommandation : métrique, la part des projets branchés (ceux qui ont
`docs/agents/usine.md`) dont le rapport est fusionné, la part des propositions du rapport citées par
le premier cadrage, et les jetons d'un audit par `/forge:audit-jetons`, qui compte par rôle ;
alerte, une ligne du journal des refus (`refusal_journal.py`) à chaque cadrage refusé faute de
rapport, et un audit qui dépasse son plafond de jetons, fixé dans la spec ; trace, l'en-tête du
rapport (SHA, chemins lus et écartés, version, durée) et la sortie du script d'inventaire, rejouable.
Réponse : tour 2.

**Q15 (P). Les risques et les critères d'arrêt datés.** Recommandation : risques et mitigations de
la section 5 du cadrage ; dates proposées : 2026-12-12, spec acceptée ; 2026-12-19, l'agent et le
script fusionnés, un rapport fusionné sur ce dépôt et sur le dépôt d'essai ; 2027-01-08, le garde
fusionné par l'humain (H1), un projet consommateur audité, les métriques relevées. Si le
2027-01-08 n'est pas tenu, clore sur l'agent seul et reporter le garde sur #413.
Réponse : tour 2.

## Décidé

| Décision | Par | Va dans |
|---|---|---|
| L'agent est obligatoire : aucune usine ne peut le retirer | ikoro-labs (demande du 2026-11-28, `idee.md:25-26`) | cadrage, section 7 |
| Priorité : après F-0003, avant F-0006 | ikoro-labs (`idee.md:38-39`) | cadrage, section 7 |
| Q2, Q7, Q8, Q11, Q12, Q15 tranchées | `forge:product-owner`, tour 2 | cadrage, sections 1, 2, 5, 8 |
| Q3, Q4, Q5, Q6, Q9, Q10, Q14 tranchées ; Q13 pour sa part technique | `forge:staff-engineer`, tour 2 | cadrage, sections 2, 4, 5 |

## Resté ouvert

- Q1 : réservée à l'humain (aucune case, `decisions.md:64-65`, veto) ; son acceptation du cadrage vaut
  entrée.
- Q13, l'exception à l'ordre qu'il a posé : réservée à l'humain (aucune case). Recommandation du
  staff-engineer : laisser partir l'agent, le skill et le script avant la fin du lot 1 de F-0003, ce qui
  ne touche pas les hooks. Commentée sur #413 avec `needs-your-attention`.

### Tour 2 (2026-11-28, session forge)

Réponses des décideurs, lus en entier, reportées dans le cadrage. Chiffres et lignes revérifiés par le
staff-engineer sur `origin/main` `3886526`.

- Q1, `forge:product-owner` : `RESERVED` (aucune case, `decisions.md:64-65`), veto. « Sans objet » en
  section 3 ; l'acceptation du cadrage par l'humain vaut entrée.
- Q2, `forge:product-owner` (P1, P3) : souffrant et cas unique retenus. Le compte du gabarit
  (1 189 lignes, clés) sort des preuves : l'audit n'écrit aucune clé, c'est F-0006. 1 189 vérifié ; le
  compte des clés non reproduit (113 écrit, 121 distinctes comptées par le staff-engineer).
- Q3, `forge:staff-engineer` (T2) : retenue. Le script lit l'arbre du SHA par git (`ls-tree`,
  `cat-file`), pas l'arbre de travail, borne le volume lu et a son test.
- Q4, `forge:staff-engineer` (T2) : retenue. L'agent lit le vocabulaire par
  `${CLAUDE_PLUGIN_ROOT}/skills/codebase-design/SKILL.md`, faute de pouvoir appeler un skill ; le commit
  relu est un ancêtre de la base (`SKILL.md:82-83`) ; le texte repris entre dans
  `THIRD_PARTY_NOTICES.md`. Source : https://code.claude.com/docs/en/plugins-reference, lue le 2026-11-28.
- Q5, `forge:staff-engineer` (T5, puis H1 pour la fusion) : retenue. Un nom absent de `READERS` n'est
  pas gardé (`guard_readonly.py:277`) : test du filtre obligatoire. Une entrée dans `FORGE_AGENTS`
  (`output_check.py:106-115`) pour le retour du rapport. Modèle proposé : `sonnet`, effort `medium`,
  confirmé par la mesure de Q14.
- Q6, `forge:staff-engineer` (T5, puis H1) : option C. Chemin en constante (`usine.py:28-30`) ; lecture
  sur `refs/remotes/origin/main` par `usine.on_ref` (`usine.py:32`, `:157-159`), refus si illisible, le
  message dit `git fetch origin` ; repli du dossier des features sur le gabarit
  (`guard_ticket_budget.py:23-24`) ; un script commun au garde et au skill vérifie l'en-tête ; notice hors
  du préfixe `guard_`, qui échoue ouvert. « Aucune usine ne peut le retirer » vaut contre les clés, pas
  contre l'épingle ni la désactivation du plugin : la documentation le dit.
- Q7, `forge:product-owner` (P3) : retenue ; le refus et la notice donnent la commande exacte.
- Q8, `forge:product-owner` (P3) : retenue ; dépôt d'essai de la clé `e2e-repo` en acceptation ; l'effet
  du garde sur l'essai de bout en bout est à vérifier en spec.
- Q9, `forge:staff-engineer` (T4 pour la forme lue par script, T2) : retenue. Un gabarit
  `plugins/forge/templates/audit-du-depot.md` avec en-tête de contrôle et front matter lisible ; des
  identifiants stables pour les propositions ; deux SHA, le commit relu et le commit du rapport ; aucune
  clé nouvelle.
- Q10, `forge:staff-engineer` (T2) : retenue, le levier passe au script : liste de lecture et liste des
  exclus avec leur raison ; scan du contenu hors du contexte du modèle, chemin rendu sans le texte ; même
  scan sur le rapport avant la PR. Pas de garde sur `Read` dans ce lot : un chemin exclu reste lisible par
  `cat`, résidu écrit. Ce que l'agent lit part vers l'API du modèle : « rien ne sort du poste » est faux.
  Source : https://code.claude.com/docs/en/permissions, lue le 2026-11-28.
- Q11, `forge:product-owner` (P1, formulation) : listes retenues ; l'acceptation ratifie le périmètre.
- Q12, `forge:product-owner` (P2) : M, sans « un seul lot », à cause de la dépendance à F-0003.
- Q13, `forge:staff-engineer` : technique (T2), le garde, `hooks.json` et `READERS` attendent #400 et
  #404, qui écrivent `hooks.json`, pas tout le lot 1 ; l'exception à l'ordre de l'humain est réservée.
  F-0004 contre F-0005 relève de P2 ; avis technique : le garde avant l'extraction des hooks de F-0004.
- Q14, `forge:staff-engineer` (T2, T4) : retenue avec corrections. Ajouter le garde à `GUARDS` de
  `factory_slo.py` (`:460`) ; le journal des refus est local, une trace lue par un indicateur, pas une
  alerte ; mesure par projet (rapport sur `origin/main`, SHA, âge), pas une part des projets ; le coût d'un
  audit est la mesure, la comparaison ne vaut que sur plusieurs projets ; le plafond est le volume du
  script.
- Q15, `forge:product-owner` (P2) : dates gardées ; risque ajouté (lot 1 de F-0003 et fusion H1) ; au
  2027-01-08 non tenu, commenter #413 avec `needs-your-attention` plutôt que clore sans garde. Le
  staff-engineer juge ces dates fragiles (11 sous-tickets ouverts sur 12 dans #340).
- Non vérifié par les décideurs : qui porte la PR du rapport hors feature (la règle des tickets s'y
  applique) ; à traiter en spec.
