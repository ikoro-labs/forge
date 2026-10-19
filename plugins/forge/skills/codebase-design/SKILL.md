---
name: codebase-design
description: "Vocabulaire et principes des modules profonds : déclarer la carte des modules d'une feature dans son design, implémenter derrière l'interface déclarée, relire la profondeur d'un module dans une PR. Pour /forge:feature-design, forge:coder et forge:qc-conf."
---

# Codebase Design

Concevoir des **modules profonds** : beaucoup de comportement derrière une petite interface, placée à un seam net, testée à travers cette interface. Le but : du levier pour les appelants, de la localité pour la maintenance, des tests qui survivent aux refontes internes. Un code facile à changer est ce qui permet à chaque ticket d'améliorer l'ensemble au lieu de le dégrader.

## Vocabulaire

Employer exactement ces termes dans les specs, designs, tickets, PR et verdicts. Ils complètent le glossaire du contexte touché (clé `glossary` de `docs/agents/usine.md`), qui nomme le métier : un module porte le nom d'un concept du glossaire (« Registre des reçus »), pas celui d'un détail technique (« ReceiptHandler »).

- **Module** : ce qui a une interface et une implémentation, à toute échelle (fonction, classe, paquet, tranche verticale). Éviter : composant, service, unité.
- **Interface** : tout ce qu'un appelant doit savoir pour l'utiliser correctement : signature, invariants, ordre des appels, modes d'erreur, configuration requise, performance. Éviter : API, signature.
- **Implémentation** : le corps du module.
- **Profondeur** : le levier à l'interface, c'est-à-dire le comportement qu'un appelant ou un test exerce par unité d'interface apprise. **Profond** : beaucoup de comportement derrière une petite interface. **Superficiel** : une interface presque aussi complexe que l'implémentation.
- **Seam** (Michael Feathers) : l'endroit où l'on modifie un comportement sans éditer à cet endroit ; là où vit l'interface d'un module. Éviter : frontière, couche.
- **Adaptateur** : ce qui satisfait une interface à un seam (stockage réel, faux en mémoire).
- **Levier** : ce que la profondeur donne aux appelants : plus de capacité par unité d'interface apprise.
- **Localité** : ce qu'elle donne à la maintenance : changement, bugs et vérification concentrés en un seul endroit.

## Principes

- **Test de suppression.** Imaginer le module supprimé. Si la complexité disparaît, c'était un simple relais : le fusionner. Si elle réapparaît chez plusieurs appelants, il mérite sa place.
- **L'interface est la surface de test.** Appelants et tests franchissent le même seam. Un test qui doit aller au-delà de l'interface signale un module mal découpé.
- **Un adaptateur : seam hypothétique. Deux : seam réel.** Introduire un seam seulement quand quelque chose varie réellement à travers lui, typiquement la production et le test.
- **La profondeur est une propriété de l'interface.** Un module profond peut être composé de petites pièces et de seams internes pour ses propres tests ; ils restent hors de l'interface.
- **Testable par construction** : recevoir ses dépendances plutôt que les créer, rendre des résultats plutôt que produire des effets cachés, garder une petite surface.

## Approfondir selon les dépendances

Classer les dépendances d'un module ; la catégorie fixe la façon de tester à travers le seam.

1. **En processus** (calcul pur, état en mémoire) : fusionner et tester directement par la nouvelle interface, sans adaptateur.
2. **Substituable localement** (base embarquée, système de fichiers en mémoire) : tester avec le substitut dans la suite ; le seam reste interne.
3. **Distante mais possédée** : un port au seam, un adaptateur réseau en production, un adaptateur mémoire en test.
4. **Externe** (service tiers) : la dépendance entre par un port, un adaptateur simulé la remplace en test.

**Remplacer, ne pas empiler.** Quand des tests existent à l'interface du module approfondi, supprimer les anciens tests des modules superficiels qu'il absorbe. Les tests vérifient des résultats observables par l'interface ; un test qui change quand l'implémentation change teste au-delà de l'interface.

## Par rôle

**Design** (`/forge:feature-design`). Partir des candidats retenus par une revue
`/forge:improve-codebase-architecture` sur la zone, s'il y en a une : ce sont des engagements de la
feature ; les candidats écartés ne sont pas reproposés. Déclarer dans la section « Ports et
adapters » du design chaque module que la feature crée ou modifie :

- son nom : le concept du glossaire ;
- son interface : ce que l'appelant doit savoir, invariants et erreurs compris ;
- son seam : où vit l'interface et quels adaptateurs le justifient ;
- sa surface de test : ce que les tests exercent par l'interface (section « Coutures de test ») ;
- le candidat retenu qu'il reprend, s'il en reprend un.

Chaque ticket du découpage nomme les modules qu'il change ; chaque module est changé par au moins un
ticket. Approfondir un module existant passe avant la création d'un nouveau module superficiel. Fin :
chaque module déclaré passe le test de suppression et chaque critère se vérifie par une interface
déclarée.

**Coder** (`forge:coder`). L'interface est conçue par le design ; l'implémentation est déléguée.
Implémenter derrière l'interface déclarée. Écrire les tests rouges sur la surface de test déclarée,
par l'interface seulement. Exposer uniquement les entrées de l'interface déclarée ; les aides
restent privées au module. Une interface déclarée insuffisante pour un critère se signale :
`RESULT: BLOCKED`, le design reste la seule source de l'interface.

**Juge** (`forge:qc-conf`). Relire la PR contre la carte des modules du design et du ticket.

- `BLOCKER` : code d'un module absent de la carte du ticket ; test qui atteint l'état interne ou une
  aide privée au lieu de l'interface ; entrée publique ajoutée hors de l'interface déclarée.
- `MINOR`, sans rejet à lui seul : module qui échoue au test de suppression, seam à un seul
  adaptateur, logique d'un même concept dispersée entre modules, anciens tests superficiels
  conservés à côté des tests d'interface.

Sans design (feature de taille S, ou ticket hors feature), la carte est celle que le ticket déclare ;
s'il n'en déclare aucune, ces règles valent pour les modules que le diff touche.

Provenance : [copie amont inactive](references/upstream.md), et `THIRD_PARTY_NOTICES.md` à la racine
du plugin. Les fichiers amont `DEEPENING.md` et `DESIGN-IT-TWICE.md` sont résumés ici ou dans
`/forge:improve-codebase-architecture`.
