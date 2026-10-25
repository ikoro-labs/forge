---
feature: F-NNNN
document: spec
statut: en-revue
destinataires: <qui relit au titre du métier, puis l'agent qui implémente>
base: <commit>
date: AAAA-MM-JJ
---

# F-NNNN : spécification

Le pourquoi est dans le cadrage. Ici : **ce qui se construit**, et comment on saura que c'est fait.

## 1. Stories

Huit au plus, chacune INVEST (indépendante, négociable, utile, estimable, petite, testable). Au-delà,
la feature est trop grosse : on la découpe en deux features.

1. En tant que <rôle>, je veux <capacité>, pour <bénéfice>.

## 2. Critères d'acceptation

Chaque critère deviendra un test qui cite `F-NNNN A<n>`, relié dans la recette.

| # | Story | Étant donné | Quand | Alors |
|---|---|---|---|---|
| A1 | 1 | <état de départ, données> | <action> | <résultat observable, chiffré> |

## 2 bis. Éléments de la source

Chaque élément identifié de la source (clé `product-source`), un par un, avec son identifiant
d'origine (`EX-12`, `RG-3.1`) et l'endroit où la spec le tient. Un élément sans identifiant en reçoit
un ici, stable, avec la ligne de la source qu'il désigne. Aucun agent n'écarte un élément ; si
l'auteur de la source (clé `source-author`) l'a écarté par écrit, une ligne le dit.

| Identifiant | Élément (résumé) | Tenu par |
|---|---|---|
| <EX-1> | <ce que dit la source> | <story 1, A1> |

- Écarté : <identifiant> | accord : <fichier> | <AAAA-MM-JJ> | <rôle>

## 3. Non-goals

- <Ce que la feature ne fait pas, même si on pourrait le croire.>

## 4. Exigences non fonctionnelles

<Performance mesurée, volumétrie, sécurité, disponibilité. Un chiffre, ou « sans objet » et pourquoi.>

## 5. Contrats, en prose

<Ce qui entre, ce qui sort, les erreurs nommées. Pas de code : le design et les tickets le feront.>

## 6. Impact sur les règles du métier

<Obligatoire dès qu'un chiffre engagé, une obligation réglementaire ou une règle du métier est en
jeu : ce que dit le skill du domaine (clé `domain-skill`), et comment la feature le tient. Sinon :
« aucune règle du métier touchée », et pourquoi.>

## 7. Décisions prises par défaut

| # | Décision | Fondement | Si le relecteur lit autrement |
|---|---|---|---|

## 8. Questions ouvertes

<Aucune, idéalement : une question qui bloque un ticket se tranche avant le découpage en tickets.>
