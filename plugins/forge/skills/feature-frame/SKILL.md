---
name: feature-frame
description: "Écrire le cadrage d'une feature : problème, périmètre, condition d'entrée, observabilité, risques, critères d'arrêt datés, taille S/M/L. Deuxième étape de la chaîne, après /forge:feature-new."
argument-hint: F-NNNN
disable-model-invocation: true
---

# Cadrer une feature

Applique `${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md`, document `cadrage`. 45 minutes au
plus ; une page en taille S. Si le projet a déjà un cadrage accepté, prends-le pour modèle.

Les tours de questions couvrent, dans cet ordre de dépendance :

1. **La condition d'entrée d'abord.** La règle que désigne la clé `entry-gate` : qui l'a demandée,
   ou quelle exception de la règle s'applique, et qui le décide. `forge:product-owner` l'applique à
   la lettre avant que la question parte vers un humain. **Si la règle ne l'admet pas** : écris
   `etat: hors-perimetre` dans `idee.md` avec la raison, livre, et arrête-toi. La chaîne s'arrête
   là. Sans la clé, la condition est « sans objet (clé entry-gate absente) » : écris-le dans la
   section 3 du cadrage, et l'humain qui acceptera le cadrage en décide.
2. **Le problème** : qui souffre, de quoi, chiffré si possible ; le cas d'usage unique.
3. **La solution la plus simple** : pourquoi pas une règle, une requête, une configuration ; et
   pourquoi un LLM s'il en faut un.
4. **Le périmètre** : ce qui est dedans, avec le niveau de preuve de chaque exigence ; ce qui est
   dehors, et où cela ira.
5. **La taille** : S, M ou L. En L, demande si la feature ne doit pas être coupée en deux.
6. **L'observabilité** : la métrique qui prouve, l'alerte qui sonne, ce que montre la trace. Sans
   les trois réponses, la feature n'est pas prête.
7. **Les risques**, la **faisabilité des données** (accords, données exclues) et des **critères
   d'arrêt datés**.

Écris `cadrage.md` depuis le gabarit, `taille:` renseignée, et reporte dans sa section Décisions
celles des séances précédentes. La commande suivante, une fois le cadrage accepté, est
`/forge:feature-spec F-NNNN`.
