# Protocole commun des commandes `/forge:feature-*`

Toute commande `/forge:feature-*` l'applique avant ses étapes propres. Le projet décrit son usine
dans `docs/agents/usine.md` : une clé que ce protocole lit et que le fichier ne porte pas rend
l'étape « sans objet », et tu le dis avec le nom de la clé, sans deviner de valeur.

Le dossier des features est celui de la clé `feature-dir` ; une feature y vit dans
`NNNN-<slug>/`. Les gabarits sont dans `${CLAUDE_PLUGIN_ROOT}/templates/features/`. Sans la clé
`feature-dir`, aucune commande `/forge:feature-*` ne peut écrire : dis-le et arrête-toi.

## La chaîne

| Étape | Document | Entre quand | Commande |
|---|---|---|---|
| idée | `idee.md` | toujours | `/forge:feature-new` |
| cadrage | `cadrage.md` | l'idée est `etat: active` | `/forge:feature-frame` |
| spec | `spec.md` | le cadrage est `statut: accepte` | `/forge:feature-spec` |
| design (facultatif) | `design.md` | la spec est `statut: accepte` | `/forge:feature-design` |
| tickets | sous-issues de l'issue de suivi | la spec, et le design s'il existe, sont `accepte` | le skill de découpage du projet |
| construction | PR | les tickets sont publiés | `/forge:feature-build` |
| recette | `recette.md` | les sous-issues sont fermées | `/forge:feature-verify` |
| livraison | `README.md` (`document: livree`) | la recette est `statut: accepte` | `/forge:feature-close` |

Une séance (`/forge:feature-brainstorm`) est permise à toute étape. Chaque document, sauf l'idée,
s'accepte par `/forge:feature-accept`, tapée par un humain.

## 1. Savoir qui parle

`git config user.name`, comparé aux valeurs de la clé `accepting-human`. Une valeur égale : c'est
cet humain. Sinon, demande-lui son nom. L'auteur signe les séances ; seul un humain de la clé
`accepting-human` peut accepter. Sans la clé, personne ne peut accepter : dis-le.

## 2. Partir de la base, sur une branche à soi

`git fetch origin`, puis une branche `docs/F-NNNN-<document>` depuis `origin/<branche par défaut>`,
nommée selon les règles git du projet (clé `git-rules`) si elles en disent plus. Si une branche de
la même feature a une PR ouverte, demande s'il faut continuer dessus.

## 3. Vérifier l'entrée

La commande de la clé `feature-gate`, avec `F-NNNN <document>`. Un refus s'affiche tel quel et la
commande s'arrête : elle ne contourne jamais un document non accepté. Sans la clé, vérifie à la
main, dans les en-têtes, la condition d'entrée du tableau plus haut, et dis que la porte est
« sans objet (clé feature-gate absente) ».

## 4. Lire avant de demander

Le dossier de la feature en entier (idée, séances, sources, documents), les ADR du domaine, le
glossaire des contextes touchés (clé `glossary`), le skill du domaine touché (clé `domain-skill`)
si un chiffre engagé ou une règle du métier est en jeu, et le code concerné. **Trouver les faits
est ton travail** : audite la donnée et le code avant de poser une question dont la réponse s'y
trouve.

## 5. Questionner par tours, et tout écrire

Ouvre d'abord la séance `seances/AAAA-MM-JJ-<auteur>-<document>.md` depuis le gabarit
`seance.md`. Puis, tour par tour :

- pose d'un coup toutes les questions dont les prérequis sont tranchés, numérotées, chacune avec ta
  recommandation ;
- écris le tour dans la séance **avant** d'attendre les réponses, puis les réponses citées au plus
  près, avec leur auteur ;
- recommence jusqu'à ce qu'il ne reste rien de supposé en silence.

Une question technique passe d'abord par l'agent `forge:staff-engineer`, une question produit par
`forge:product-owner` : ce qu'ils tranchent s'écrit dans la séance avec leur ligne `MATRIX_CELL`, et
seul ce qu'ils rendent `RESERVED` ou `DOMAIN` reste une question pour l'humain.

Si l'humain répond « décide par défaut », tranche sur la pratique établie du métier du projet et
des équipes logicielles, et écris la décision dans la section « Décisions prises par défaut » du
document, avec son fondement et ce qui change si le relecteur lit autrement.

## 6. Écrire le document

Depuis son gabarit, avec `statut: en-revue`. **Jamais `accepte`** : seul `/forge:feature-accept`,
tapée par un humain, l'écrit. Modifier un document déjà accepté le repasse en `en-revue`, avec une
ligne qui dit pourquoi. Exception : la section 9 du design (« Décisions prises pendant la
construction ») s'écrit pendant la construction, sans rouvrir le document ni le repasser en revue.
Chaque terme nouveau entre dans le glossaire de son contexte (clé
`glossary`).

## 7. Livrer dans une PR

1. Un commit au format des règles git du projet (clé `git-rules`), par exemple
   `docs(features): F-NNNN <ce qui a été fait>`, avec la ligne d'attribution du dépôt. Les hooks git
   du projet tournent : ne les contourne pas.
2. `git push`, puis une PR dont le corps commence par `Feature: F-NNNN` et cite l'issue de suivi en
   `Refs #n` (jamais un mot-clé de fermeture : l'issue de suivi vit jusqu'à la clôture).
3. Termine en disant la commande suivante, telle que `/forge:feature-status F-NNNN` la donne.

## Ce qui n'entre jamais

Aucune donnée réelle d'un client ou d'un partenaire, aucun nom de client ou de personne tierce,
aucun identifiant d'un espace de stockage privé, aucun secret, ni rien que les règles de sécurité
du projet (`CLAUDE.md`, clé `domain-rules`) excluent du dépôt. Un document qui en contient reste
hors du dépôt : la séance en garde la référence, son empreinte et ce qui en a été retenu.
