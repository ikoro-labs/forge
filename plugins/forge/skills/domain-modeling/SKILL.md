---
name: domain-modeling
description: "Construire ou faire évoluer le modèle métier du projet pendant un cadrage, une spec, un design ou une décision : préciser termes, relations et frontières, confronter le modèle au code et tenir le glossaire du contexte (clé glossary) à jour."
---

# Domain Modeling

Le vocabulaire canonique est le glossaire du contexte touché, que désigne la clé `glossary` de
`docs/agents/usine.md` (un fichier par contexte quand le projet en a plusieurs). Il tient la place
du `CONTEXT.md` ou `GLOSSARY.md` des versions amont ; tenir ce seul référentiel. Sans la clé, il
n'y a pas de glossaire déclaré : dis-le, et propose d'en créer un plutôt que d'écrire des termes
ailleurs. Lire les définitions concernées avant de modifier le modèle. Consommer ce vocabulaire dans
une tâche courante ne demande pas une nouvelle séance de modélisation.

1. **Confronter les termes.** Comparer l'échange, les sources de la feature et le code accessible.
   Distinguer comportement historique, besoin cible et décision acquise. Signaler une contradiction
   en citant les deux définitions.
2. **Éprouver les frontières.** Proposer un scénario concret qui distingue les concepts : deux
   acteurs qui se ressemblent, une règle modifiée après lecture, un droit expiré, un objet préparé
   mais pas remis, une saisie hors ligne. Relever les relations établies ; garder explicitement
   ouvertes les cardinalités qui le sont encore.
3. **Préciser le langage.** Choisir un terme par concept, une définition métier d'une ou deux
   phrases et les alias à éviter dans ce contexte. Relier chaque définition à sa source quand le
   projet en tient un registre. Le glossaire décrit le métier ; les spécifications, choix de pile et
   détails d'implémentation ont leurs documents propres.
4. **Capturer au fil de l'échange.** Dès qu'un terme est résolu, mettre à jour le glossaire, dans la
   PR du document en cours (`/forge:feature-*`) ou dans une PR à part. Qualifier les propositions et
   les ambiguïtés restantes ; une formulation de l'agent ne vaut pas approbation métier. Préserver
   les décisions déjà acquises.
5. **Consigner une décision structurante si nécessaire.** Créer un ADR dans `docs/adr/` seulement si
   elle est coûteuse à inverser, surprenante sans contexte et issue d'un vrai compromis, au format
   `${CLAUDE_PLUGIN_ROOT}/templates/adr.md` ou au gabarit du projet ; numéroter après les ADR
   existants.

## Dans l'usine

Un agent sans Edit ni Write (`forge:staff-engineer`, `forge:product-owner`, `forge:qc-conf`) ne
modifie jamais le glossaire : une clarification est une proposition ou un constat dans sa sortie, et
celui qui l'appelle l'écrit. Un `forge:coder` qui rencontre une ambiguïté déterminante rend
`RESULT: BLOCKED` au lieu de choisir un sens ; une question de doctrine du métier va à l'agent de la
clé `domain-arbiter`, ou à un humain. Les juges signalent les dérives de sens.

Provenance : [copie amont inactive](references/upstream.md), et `THIRD_PARTY_NOTICES.md` à la racine
du plugin. Les références historiques ne donnent aucun pouvoir d'exécution.
