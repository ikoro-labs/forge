---
feature: F-0002
document: idee
titre: règles de code figées au cadrage et tenues par des hooks
porteur: ikoro-labs
etat: active
demande_par: interne, l'humain de la clé accepting-human (brainstorm du 2026-11-20)
issue: 291
date: 2026-11-22
---

# F-0002 : règles de code figées au cadrage et tenues par des hooks

## L'idée, en une phrase

Un projet qui adopte forge fige au cadrage sa pile et ses règles de code (complexité, imbrication,
nombre de paramètres, carte des modules, dépendances permises), et des hooks les font tenir
pendant que l'agent écrit, au lieu que le juge les relève à la lecture, une PR après l'autre.

## D'où elle vient

Un brainstorm du 2026-11-20, mené par la session forge à la demande de l'humain, a comparé ce que
font aujourd'hui forge, AI Delivery Gates et Shipyard. Ses constats, résumés ici sans le reprendre
mot pour mot (le document de séance est privé et n'entre pas dans le dépôt) :

- rien, dans forge, ne fige la pile ni des règles de code chiffrées : une technologie se décide
  feature par feature, et le juge la relit à chaque PR ;
- les règles qui valent d'être imposées sont celles qu'un outil sait mesurer : format, complexité
  cyclomatique, imbrication, nombre de paramètres, carte des modules (qui importe qui), liste
  permise des dépendances ; aucune source trouvée ne relie une longueur de fichier ou de fonction
  aux défauts, et ces plafonds poussent vers des modules superficiels, à l'opposé de
  `forge:codebase-design` ;
- aucun outil ne refuse une dépendance nouvelle : il faut un contrôle propre, la liste permise
  comparée au diff ;
- une règle figée ne reste pas immobile : une règle à cliquet gèle l'existant par une liste de
  référence qui ne peut que rétrécir, et un constat de revue qui revient devient une règle
  (aujourd'hui un constat mineur du juge part en commentaire et rien n'en fait une règle) ;
- un hook se contourne (une commande Bash, un autre outil) : la CI tranche en dernier, avec les
  mêmes commandes.

## Qui l'a demandée

L'humain de la clé `accepting-human`, pour lui-même : interne, la règle d'entrée de ce dépôt (les
besoins viennent de ses tickets) l'admet par l'issue de suivi.

## Premières questions

- Le jeu de règles livré en gabarit : complexité, imbrication, paramètres, carte des modules, pile,
  sans plafond de lignes. L'humain en veut-il un malgré l'absence de source, et lequel ?
- Où vit la liste des dépendances permises (un fichier du projet nommé par une clé), et comment une
  décision d'ajouter une dépendance la met à jour sans que le hook ne la refuse en silence.
- Les clés nouvelles de `usine.md`, noms provisoires `stack`, `lint-on-write` et
  `architecture-check` : leur forme, et le rendu « sans objet (clé absente) » quand elles manquent
  (aucune valeur par défaut).
- Le cliquet : où vit la liste de référence, quelle commande refuse une hausse, et le chemin d'un
  constat récurrent du juge jusqu'à une proposition de règle.
- Le recoupement avec les travaux d'un projet consommateur sur un catalogue de règles partagé entre
  le coder et le relecteur.
