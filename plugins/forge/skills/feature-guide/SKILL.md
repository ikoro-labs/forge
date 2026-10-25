---
name: feature-guide
description: "Mener une conception guidée avec un expert métier qui n'est pas développeur : une question à la fois, dans ses mots, une rédaction proposée à valider ou corriger, dans un document vivant qui devient la source une fois validé."
argument-hint: F-NNNN
disable-model-invocation: true
---

# Conduire une conception avec un expert métier

Applique `${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md`. Ce skill est pour l'expert qui sait
ce que le produit doit faire et n'écrit pas de Markdown technique : c'est toi qui tiens la plume, lui
qui tranche. Il se tape en ligne de commande ; le cockpit n'en fait pas encore une interface.

## Les questions

1. **Une seule question à la fois.** Pas de liste numérotée, pas de tour de dix questions : l'expert
   répond, tu écris, puis tu poses la suivante. Le prérequis d'une question est tranché avant elle.
2. **Dans les mots du métier.** Reprends ceux de l'expert et ceux de sa source (clé `product-source`) ;
   jamais un terme de l'implémentation (table, API, ticket, schéma) dans une question.
3. **Propose une rédaction à valider ou à corriger**, jamais une page blanche. Chaque question porte
   ta proposition, tirée de ce que la source et le dépôt disent déjà, et l'expert répond « oui »,
   corrige, ou écarte. Ce que le dépôt ou la source tranchent ne devient pas une question.
