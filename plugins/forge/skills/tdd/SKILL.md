---
name: tdd
description: "Développement piloté par les tests : ce qu'est un bon test, où les écrire (les coutures), les trois anti-patterns, les règles de la boucle rouge puis verte et l'usage des mocks. Pour forge:coder, quand la clé test-skill de docs/agents/usine.md le désigne, et pour forge:qc-conf."
---

# Développement piloté par les tests

La boucle rouge puis verte fait écrire un test avant le code. Ce skill dit ce qui fait qu'un test vaut d'être gardé : ce qu'est un bon test, où le mettre, les anti-patterns, les règles de la boucle. Chaque section vaut à chaque cycle : la consulter avant et pendant la boucle, pas après.

En explorant le code, lire le glossaire du contexte touché (clé `glossary` de `docs/agents/usine.md`) pour que les noms de tests et le vocabulaire d'interface suivent le langage du métier, et respecter les décisions (ADR) de la zone.

## Ce qu'est un bon test

Un test vérifie un **comportement** à travers l'interface publique, jamais un détail d'implémentation. Le code peut changer entièrement, le test non. Un bon test se lit comme une spécification (« un client peut valider un panier valide ») : il dit quelle capacité existe et survit à une refonte, parce qu'il ignore la structure interne.

Exemples bons et mauvais : [references/tests.md](references/tests.md). Règles sur les mocks : [references/mocking.md](references/mocking.md).

## Les coutures : où vont les tests

Une **couture** (seam) est la frontière publique où l'on teste : l'interface par laquelle on observe un comportement sans regarder dedans. Les tests vivent aux coutures, jamais contre les internes.

**On ne teste qu'aux coutures déclarées.** Avant d'écrire un test, repérer les coutures sous test :

- dans une feature, celles du §6 du design (section « Coutures de test ») ;
- sans design (feature de taille S, ticket hors feature), celles que le ticket nomme ou, à défaut, celles que la PR écrit.

Aucun test ne s'écrit à une couture qui n'est pas déclarée. On ne peut pas tout tester : déclarer les coutures d'avance fait porter l'effort sur les chemins critiques et la logique complexe, pas sur chaque cas limite. Chaque couture se déclare avec une ligne : **ce qu'elle attrape** et **ce qu'elle manque**. Une interface déclarée insuffisante pour un critère se signale (`BLOCKED` pour le coder), elle ne se contourne pas par un test sur les internes.

Quand la forme de l'interface est elle-même en question (profondeur du module, place de la couture, ce que l'interface expose), consulter `forge:codebase-design` pour le vocabulaire (module, interface, seam, adaptateur, levier, localité). C'est une référence, pas une session à mener.

## Anti-patterns

- **Couplé à l'implémentation** : le test simule un collaborateur interne, appelle une méthode privée, ou vérifie par un canal latéral (interroger la base au lieu de passer par l'interface). Le signe : il casse sur une refonte qui ne change aucun comportement.
- **Tautologique** : l'attendu se calcule comme le code le calcule (`attendu = a + b` pour tester `ajouter(a, b)`, un instantané dérivé de la même façon, une constante comparée à elle-même). Le test passe par construction et ne peut jamais contredire le code. La valeur attendue vient d'une source indépendante : un littéral connu, un exemple travaillé, la spec.
- **Tranches horizontales** : écrire tous les tests d'abord, tout le code ensuite. Des tests en bloc vérifient un comportement imaginé : ils testent la forme des choses, deviennent insensibles aux vrais changements et figent une structure avant d'avoir compris l'implémentation. Travailler en **tranches verticales** : un test, une implémentation, puis on recommence ; chaque test est un tir traceur qui répond à ce que le cycle précédent a appris.

## Les mocks

Ne simuler qu'aux **frontières du système** : service externe, temps, hasard, parfois fichiers ou base. Jamais un collaborateur interne. Pour qu'une frontière se remplace, la dépendance entre par injection et l'interface est découpée par opération. Détail : [references/mocking.md](references/mocking.md).

## Règles de la boucle

- **Rouge avant vert.** Écrire d'abord le test qui échoue, le lancer, et voir qu'il échoue pour la bonne raison (le comportement manque, pas une faute de frappe ni un import cassé). Puis seulement le code qui le fait passer. Ne pas anticiper les tests suivants ni ajouter de fonctionnalité spéculative.
- **Une tranche à la fois.** Une couture, un test, une implémentation minimale par cycle.
- **Le refactoring est hors de la boucle.** Le faire pendant la boucle mélange deux changements dont un seul est vérifié par le test rouge. Il a sa place au découpage (`/forge:feature-design`, étape 6) : un prérefactoring dans son propre ticket, avant le changement qu'il facilite, et un refactoring large en expand, migrations par lots puis contract. La revue ne refactore pas. Un refactoring que le ticket ne porte pas se signale dans la PR, il ne se glisse pas dans la boucle.

## Par rôle

**Coder** (`forge:coder`). Suivre la boucle critère par critère, aux coutures déclarées, avec la citation du critère dans chaque test qui le prouve.

**Juge** (`forge:qc-conf`). Relire les tests contre ces trois anti-patterns et contre la règle des mocks : un test qui reproduit son attendu par le calcul du code, qui simule un collaborateur interne ou qui s'écrit à une couture non déclarée est un défaut à relever.
