## Résumé

<!-- Ce que la PR change, et pourquoi. Une sous-section par changement quand il y en a plusieurs. -->

Closes #

### Vue du changement

<!-- La plus petite vue qui suffise, à côté du texte qu'elle porte : pseudo-code, arbre d'appels ou
de fichiers, croquis de diff. Inutile quand le diff tient en quelques lignes. -->

## Porte

<!-- `double sens` : un retour en arrière coûte peu.
`sens unique` : geste destructif, publication, migration de données, décision difficile à défaire.
Pour un sens unique, dis lequel est le geste qui ne se défait pas, et pourquoi. -->

## Rayon d'impact

<!-- Un mot (aucun, local, consommateurs...) puis une phrase : ce qu'un projet consommateur peut voir
changer à la fusion (une variable, un geste, le comportement d'un hook). -->

## Ce qui ne change pas

<!-- Ce qu'un lecteur pourrait croire touché et qui ne l'est pas : version, autres hooks, projets. -->

## Preuves

- Avant (rouge) : le test de chaque critère vu échouer, sortie recopiée, avec la raison de l'échec :
- Après (vert) : le même test, sortie recopiée :
- `uv run --no-project --quiet python -m unittest discover -s tests` :
- `claude plugin validate .` et `claude plugin validate plugins/forge` :
- Essayé sur un vrai poste (système, version de Claude Code), ou « pas encore » :

## Définition du Done

<!-- Chaque case cochée honnêtement : une case non tenue dit pourquoi. -->

## Rapport d'agent

<!-- Laissé vide : `/forge:qc` l'écrit. -->

## Suite

<!-- Ce qui reste à faire après cette PR, avec son ticket. -->
