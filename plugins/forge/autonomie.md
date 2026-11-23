# Qui lance une commande, et l'autonomie du projet

Un skill de la chaîne dont le front matter ne porte pas `disable-model-invocation` peut être lancé
par le modèle (outil Skill) comme par l'humain qui tape la commande. Chacun applique cette règle
avant sa première étape. Le projet décrit son usine dans `docs/agents/usine.md` : la clé que cette
règle lit est `agent-autonomy`, et une clé que le fichier ne porte pas rend l'étape « sans objet »,
sans valeur devinée.

## 1. Qui a lancé la commande

Le bloc `<command-name>` d'un tour dit quelle commande l'humain a tapée. Il ne vaut que pour le skill
qu'il nomme : compare sa valeur au nom du skill que tu exécutes (celui de ce `SKILL.md`, avec ou sans
le préfixe `forge:`), jamais à « une commande du tour ».

- **L'humain l'a tapée** : le tour porte un bloc `<command-name>` qui porte le nom du skill que tu
  exécutes. La commande s'exécute comme toujours, sans lire la clé : l'autonomie du projet ne retire
  rien à l'humain.
- **Le modèle l'a lancée** (outil Skill) : aucun bloc `<command-name>` du tour ne porte ton nom. Un
  bloc pour une autre commande ne compte pas : l'humain a tapé `/forge:feature-new`, puis le modèle a
  lancé `feature-frame` ? Pour `feature-frame`, le modèle l'a lancée. Lis la clé, à l'étape 2.

## 2. La clé `agent-autonomy`

Une seule ligne, `agent-autonomy` : `on`, que l'utilisateur du projet écrit pour ouvrir l'autonomie
des agents sur ce projet. Le plugin ne la pose jamais.

- **Clé absente** : sans objet (clé `agent-autonomy` absente). N'écris rien, n'ouvre ni branche ni
  PR, ne lance aucun agent, et rends l'étape à l'humain : dis-lui la commande exacte à taper, avec
  ses arguments. Une valeur autre que `on` et une clé répétée se traitent de même, en citant la
  ligne fautive.
- **Clé à `on`** : la commande s'exécute. Le modèle l'a lancée à la place de l'humain, et rien de ce
  qu'il décide n'attend sa lecture avant d'être écrit : l'humain relit après coup.

La même clé est l'interrupteur de la fusion et de la publication. Elle se ferme comme elle s'ouvre : l'humain
reprend la main sur un projet en retirant la ligne.

- **Clé à `on`** : `forge:qc` fusionne un ACCEPT hors `protected-path` (ses autres arrêts restent : une entrée
  `never-weaken`, une action `human-merge` active), et `release` publie, tag compris, quand l'essai de bout en
  bout passe et qu'aucun ticket `sev1` n'est ouvert ; l'état des SLO est cité dans la PR de version, il ne
  bloque pas.
- **Clé absente** : `forge:qc` poste son verdict, pose `needs-your-attention` et ne fusionne jamais ; `release`
  n'ouvre que la PR de version. L'humain fusionne et publie.

Le skill n'est pas seul à tenir cet interrupteur : le hook `guard_git` tient la même clé, pour tout
agent. Sans une seule ligne `agent-autonomy` : `on`, il refuse la fusion et le tag (`gh pr merge`, la
fusion par `gh api`, l'outil MCP de fusion d'un serveur GitHub, `git tag` qui écrit, le push d'un tag),
et le refus dit que le geste reste à l'humain. Il lit la clé dans `origin/main`, jamais dans l'arbre de
travail, que l'agent peut modifier. L'essai de bout en bout et l'absence de `sev1` restent au skill :
un hook ne peut pas les vérifier.

## 3. Les questions, avec la clé

Aucune question ne part vers un humain avant d'être passée à un agent décideur : une question
produit (parcours, périmètre, formulation, priorité) à `forge:product-owner`, une question technique
(architecture, contrat, CI, règle du dépôt) à `forge:staff-engineer`, selon la matrice que désigne
la clé `decision-matrix`, avant tout humain. Un verdict `TECHNICAL` ou `DOMAIN` passe une fois à
l'agent ou à l'humain que le verdict désigne.

- **`DECIDED`** : la décision est prise. Écris-la dans la section Décisions du document que la
  commande produit, avec sa raison, sa source et la ligne `MATRIX_CELL` de l'agent, et dans la séance
  quand il y en a une. Une case sous veto (`VETO: yes`) demande en plus l'étiquette que le projet
  réserve à l'humain (clé `report-attention-label`), sur la PR que la commande ouvre.
- **`RESERVED`** : la décision appartient à l'humain. N'en prends aucune à sa place : nomme la case
  ou le geste que l'agent cite, donne sa recommandation, écris la question ouverte dans le document
  et dans le corps de la PR, et laisse-la attendre l'humain.
- **Sans la clé `decision-matrix`**, les deux agents rendent tout en `RESERVED` : la commande suit
  la ligne ci-dessus pour chaque question.

## 4. Ce que la clé n'ouvre pas

- **`feature-accept`** garde `disable-model-invocation: true` : seul un humain de la clé
  `accepting-human` l'écrit, en la tapant. Un document que le modèle produit reste `en-revue`, et
  la commande suivante qu'il dit est celle de l'acceptation, à l'humain.
- **`release`** garde `disable-model-invocation: true` et reste commandée par la clé
  `release-trigger`, qui dit quand une version est due. `agent-autonomy` dit si l'agent publie : absente, `release`
  ouvre la PR de version et s'arrête, sans tag.
- **Ce que la matrice réserve à l'humain** (clé `decision-matrix`, sa section réservée) reste à lui,
  clé ouverte ou non : l'étape 3 le dit pour chaque question.
