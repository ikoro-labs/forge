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

Autant de stories qu'il en faut pour reprendre la source entière, chacune INVEST (indépendante,
négociable, utile, estimable, petite, testable).

1. En tant que <rôle>, je veux <capacité>, pour <bénéfice>.

## 2. Critères d'acceptation

Chaque critère deviendra un test qui cite `F-NNNN A<n>`, relié dans la recette.

| # | Story | Étant donné | Quand | Alors |
|---|---|---|---|---|
| A1 | 1 | <état de départ, données> | <action> | <résultat observable, chiffré> |

## 3. Éléments de la source

Chaque élément identifié de la source (clé `product-source`), un par un, avec son identifiant
d'origine (`EX-12`, `RG-3.1`, `C01`) et l'endroit où la spec le tient. Un élément sans identifiant en
reçoit un ici, stable, avec la ligne de la source qu'il désigne. Aucun agent n'écarte un élément ; si
l'auteur de la source (clé `source-author`) l'a écarté par écrit, une ligne le dit. Les Non-goals
n'écartent rien.

| Identifiant | Élément (résumé) | Tenu par |
|---|---|---|
| <EX-1> | <ce que dit la source> | <story 1, A1> |

- Écarté : <identifiant> | accord : <fichier> | <AAAA-MM-JJ> | <rôle>

Chacune des sections 4 à 13 et 19 à 22 se remplit, ou dit en une phrase pourquoi elle est sans objet.

## 4. Exigences atomiques (`EXI-nn`)

Une exigence, un critère d'acceptation mesurable, chiffré dès que possible : jamais seulement
« doit gérer X ». Niveau de preuve : T texte réglementaire, P principe du projet, O piège observé,
M parité marché, S souhait d'une source unique.

| Identifiant | Exigence | Critère mesurable | Classement | Niveau de preuve | Lot |
|---|---|---|---|---|---|
| <EXI-01> | <une chose à tenir> | <valeur, seuil, durée> | <obligatoire, souhaitable> | <T, P, O, M ou S> | <L1> |

## 5. Contrôles codés (`Cnn`)

Le calcul exact, la tolérance par défaut et l'effet (quarantaine, avertissement, condition de
signature), dans l'unité du métier.

| Identifiant | Calcul exact | Tolérance par défaut | Effet |
|---|---|---|---|
| <C01> | <formule, unité du métier> | <valeur> | <quarantaine, avertissement ou condition de signature> |

## 6. Gabarits et conventions (`Gn`)

| Identifiant | Structure | Règles |
|---|---|---|
| <G1> | <champs, ordre, colonnes> | <convention de nommage, obligatoire ou facultatif> |

## 7. Déroulé pas à pas

Un déroulé par parcours : première installation, livraison, relivraison...

<Parcours : 1. qui fait quoi, 2. ce qui se passe ensuite, 3. ce qu'on voit à la fin.>

## 8. Rôles

| Rôle | Fait | Ne fait pas |
|---|---|---|
| <rôle> | <actions> | <limites> |

## 9. Décisions prises et leur date

| Date | Décision | Par qui |
|---|---|---|
| <AAAA-MM-JJ> | <ce qui a été tranché> | <rôle> |

## 10. Critères transverses

<Ce qui vaut pour tout parcours : une règle par ligne, chiffrée si possible.>

## 11. Lots et leur gel

| Lot | Contenu | Gelé le |
|---|---|---|
| <L1> | <exigences et contrôles du lot> | <AAAA-MM-JJ> |

## 12. Comment elle peut échouer

| Risque | Mécanisme | Parade |
|---|---|---|
| <ce qui peut mal tourner> | <comment> | <ce qui l'empêche ou le rattrape> |

## 13. Pièges et parades observés

| Identifiant | Piège | Parade |
|---|---|---|
| <P1> | <ce qui a été vu sur le terrain> | <ce qui y répond> |

## 14. Non-goals

- <Ce que la feature ne fait pas, même si on pourrait le croire.>

## 15. Exigences non fonctionnelles

<Performance mesurée, volumétrie, sécurité, disponibilité. Un chiffre, ou « sans objet » et pourquoi.>

## 16. Contrats, en prose

<Ce qui entre, ce qui sort, les erreurs nommées. Pas de code : le design et les tickets le feront.>

## 17. Impact sur les règles du métier

<Obligatoire dès qu'un chiffre engagé, une obligation réglementaire ou une règle du métier est en
jeu : ce que dit le skill du domaine (clé `domain-skill`), et comment la feature le tient. Sinon :
« aucune règle du métier touchée », et pourquoi.>

## 18. Décisions prises par défaut

Celles de l'agent qui écrit la spec, là où la source ne tranche pas ; les décisions de l'humain sont
à la section 9.

| # | Décision | Fondement | Si le relecteur lit autrement |
|---|---|---|---|

## 19. Confiance chiffrée

| Partie | Confiance (de 0 à 100 %) | Raison |
|---|---|---|
| modèle | <%> | <pourquoi> |
| périmètre | <%> | <pourquoi> |
| priorités | <%> | <pourquoi> |

## 20. Points ouverts

<Aucun, idéalement : un point qui bloque un ticket se tranche avant le découpage en tickets.>

## 21. Questions pour les entretiens

- <Ce qu'il reste à demander à l'expert, une question par ligne.>

## 22. Glossaire

Les mots de l'écran et du métier, un par ligne. Il alimente le glossaire du contexte (clé `glossary`) :
chaque terme nouveau y entre.

| Terme | Définition |
|---|---|
| <terme> | <ce qu'il désigne, en une phrase> |
