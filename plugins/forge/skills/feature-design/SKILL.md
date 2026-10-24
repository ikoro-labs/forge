---
name: feature-design
description: "Écrire le design d'une feature dont la spec est acceptée : contextes touchés, ports et adapters, modèle de données, frontière de confiance, observabilité, coutures de test, découpage en tickets, et les ADR déclenchés."
argument-hint: F-NNNN
disable-model-invocation: true
---

# Concevoir une feature

Applique `${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md`, document `design` : la spec doit
être acceptée.

1. **Faut-il un design ?** En taille S, si rien ne le déclenche (technologie, architecture, service,
   contrat d'API, modèle IA, sécurité, schéma non trivial, ou un déclencheur que le `CLAUDE.md` du
   projet ajoute), dis-le et passe directement au découpage (étape 6). Rien n'est écrit.
2. **Lire le code** des contextes touchés, leur glossaire (clé `glossary`) et le fichier de règles
   de chaque domaine touché (clé `domain-rules`). Invoque le skill de chaque domaine touché (clé
   `domain-skill`) pour ses choix, et `forge:codebase-design` pour le découpage en modules et leurs
   interfaces.
3. **Tours de questions** sur ce que le code ne tranche pas.
4. **Écrire `design.md`** depuis le gabarit : contextes, ports, données (expand puis contract pour
   un changement large), frontière de confiance, les trois réponses d'observabilité avec leur point
   d'émission, les coutures de test (la plus haute qui existe), et le découpage en tranches
   verticales.
5. **Écrire les ADR déclenchés**, au format `${CLAUDE_PLUGIN_ROOT}/templates/adr.md` (ou le gabarit
   d'ADR du projet s'il en a un), numéro suivant le plus haut de `docs/adr/`, statut proposé, et les
   lister dans `adr:` de l'en-tête. Un terme nouveau entre dans le glossaire du contexte.
6. **Découper**, une fois le design accepté (ou la spec seule en taille S) : des tickets en
   tranches verticales, sous-issues de l'issue de suivi, chacun avec ses critères `A<n>` et ses
   liens vers la spec et le design figés à un commit, étiquetés `ready-for-agent`, et leurs
   dépendances déclarées. Trois règles :
   - **Un contexte neuf.** Chaque ticket tient dans un seul contexte neuf, celui d'un
     `forge:coder` : s'il n'y tient pas, coupe-le.
   - **Le prérefactoring d'abord.** Quand le changement demandé serait difficile dans le code tel
     qu'il est, rends-le facile d'abord (le prérefactoring), puis fais le changement facile. Le
     prérefactoring a son propre ticket, qui bloque ceux qui en dépendent, et ne change aucun
     comportement.
   - **Le refactoring large ne se force pas en tranche verticale.** Un changement mécanique dont le
     rayon couvre tout le code se fait en trois temps : expand (ajouter la nouvelle forme à côté
     de l'ancienne), migration par lots, puis contract (retirer l'ancienne). Chaque étape est un
     ticket bloqué par la précédente.

Commande suivante, une fois les tickets publiés : `/forge:feature-build F-NNNN`.
