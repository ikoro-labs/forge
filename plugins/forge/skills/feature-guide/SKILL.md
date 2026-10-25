---
name: feature-guide
description: "Mener une conception guidée avec un expert métier qui n'est pas développeur : une question à la fois, dans ses mots, une rédaction proposée à valider ou corriger, dans un document vivant qui devient la source une fois validé."
argument-hint: F-NNNN
disable-model-invocation: true
---

# Conduire une conception avec un expert métier

Applique `${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md`. Ce skill est pour l'expert qui sait
ce que le produit doit faire et n'écrit pas de Markdown technique : c'est toi qui tiens la plume, lui
qui tranche. Il se tape d'abord en ligne de commande ; le cockpit
suivra. Aucun expert métier réel n'a encore mené une conception avec ce skill : ses questions, son
rythme et la forme du document n'ont été éprouvés que sur des textes écrits à la main. Dis-le à
l'expert en ouvrant la séance, et corrige le skill de ce qu'il en dit.

## Les questions

1. **Une seule question à la fois.** Pas de liste numérotée, pas de tour de dix questions : l'expert
   répond, tu écris, puis tu poses la suivante. Le prérequis d'une question est tranché avant elle.
2. **Dans les mots du métier.** Reprends ceux de l'expert et ceux de sa source (clé `product-source`) ;
   jamais un terme de l'implémentation (table, API, ticket, schéma) dans une question.
3. **Propose une rédaction à valider ou à corriger**, jamais une page blanche. Chaque question porte
   ta proposition, tirée de ce que la source et le dépôt disent déjà, et l'expert répond « oui »,
   corrige, ou écarte. Ce que le dépôt ou la source tranchent ne devient pas une question.

## Le document vivant

La conception s'écrit dans `conception.md`, un fichier Markdown du dossier de la feature (clé `feature-dir`), dans
`NNNN-<slug>/`, depuis le gabarit
`${CLAUDE_PLUGIN_ROOT}/templates/features/conception.md`. Il se remplit au fil des réponses, ligne par
ligne : l'expert peut l'ouvrir et le commenter à tout moment, et la prochaine question part de ce
qu'il y a lu.

Quand l'expert a validé le document en entier, il **devient la source** de la feature : demande à
l'humain de la clé `accepting-human` d'ajouter son fichier à la clé `product-source` de
`docs/agents/usine.md`, en tête (la source de l'expert prime sur ce que des agents ont écrit), et pas avant :
tant qu'une ligne reste `proposé`, le comptage de `forge:feature-spec` prendrait une
rédaction d'agent pour un élément de la source.

### Le support partagé

La clé `shared-doc` nomme, quand le projet en a un, le support partagé où l'expert relit et commente le
document. Forge ne câble aucun service : tu ne devines pas lequel c'est, tu utilises celui que la clé
nomme, avec les outils que la session a pour lui.

- **Avec la clé** : propose à l'expert d'y publier le document, puis, à chaque question, lis ses
  commentaires et recopie dans le fichier du dépôt ce qu'il a écrit ou corrigé sur le support. Le
  fichier du dépôt reste la référence : en cas d'écart, il fait foi, et seul lui devient la source.
  Si la session n'a aucun outil pour ce support, dis-le et continue avec le fichier seul.
- **Sans la clé** : « sans objet (clé `shared-doc` absente) ». Seul le fichier du dépôt sert : l'expert
  le lit et le commente tel quel, sans valeur par défaut ni support deviné.

## La validation

Chaque rédaction que tu écris porte l'état `proposé`, et le garde jusqu'au « oui » de l'expert. Une
correction de l'expert réécrit la ligne, qui reste `proposé` : il valide la rédaction corrigée, pas
la première.

- **Une exigence n'entre jamais `validé` sans l'expert.** Sa ligne ne passe à `validé` qu'avec son
  nom (clé `source-author`) et la date de son accord, que tu recopies de sa réponse dans les colonnes
  « Validé par » et « Le ». Un silence n'est pas un accord, une réponse à une autre question non plus : ni l'humain de
  la clé `accepting-human` ni un agent ne le remplacent. Un refus s'efface de la table et s'écrit à
  l'historique.
- Clé `source-author` absente : « sans objet (clé `source-author` absente) ». Personne n'est désigné
  pour valider, donc aucune ligne ne passe à `validé` et le document ne devient pas une source.
- Le document n'est validé en entier que quand il ne reste aucune ligne `proposé` ni question
  ouverte.

## Les trois sorties

Une fois le document validé en entier et déclaré dans la clé `product-source`, tu en tires trois
documents dans le dossier de la feature. Chacun s'écrit en `en-revue` ou sans statut : seul
`/forge:feature-accept`, tapée par un humain, accepte (protocole, étape 6).

1. **La spec, au grain de la procédure cible.** Depuis `${CLAUDE_PLUGIN_ROOT}/templates/features/spec.md`
   et en suivant `/forge:feature-spec` : la section « Éléments de la source » reprend chaque
   identifiant du document validé, un par un. Lance
   `uv run --no-project --quiet python ${CLAUDE_PLUGIN_ROOT}/scripts/source_ids.py <spec.md>` : à
   liste `MISSING` vide seulement, elle peut être relue.
2. **Le parcours voulu.** Les écrans du document, depuis
   `${CLAUDE_PLUGIN_ROOT}/templates/features/parcours.md`, avec les mots exacts de l'expert, puis
   `uv run --no-project --quiet python ${CLAUDE_PLUGIN_ROOT}/scripts/parcours.py <parcours.md>`.
   Sans écran, dis-le et n'écris rien.
3. **La matrice initiale.** Depuis `${CLAUDE_PLUGIN_ROOT}/templates/features/matrice.md` : une ligne
   `absent` par identifiant du document, sans ticket, sans date, avec le lot de la spec et l'écran du
   parcours qui le montre. Elle ne juge rien. Lance
   `uv run --no-project --quiet python ${CLAUDE_PLUGIN_ROOT}/scripts/matrice.py <matrice.md>` : un
   `INVALID`, un `UNKNOWN`, un `DUPLICATE` ou un `MISSING` se corrige avant la PR. Le découpage en
   tickets reporte ensuite les tickets (`/forge:feature-design`, étape 6), puis chaque coder tient les
   lignes de son ticket.

Chaque libellé neuf entre dans le glossaire du contexte (clé `glossary`).
