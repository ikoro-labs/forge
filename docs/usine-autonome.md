# L'usine autonome

Cette page décrit les clés, les gestes de l'humain, la trace et les alertes de la feature F-0003, au fur et
à mesure que ses tickets sont livrés. Le pourquoi est dans `docs/features/0003-usine-autonome/cadrage.md`, le
quoi dans `spec.md`. Pour l'instant, elle traite un seul garde : celui des collections de l'humain.

## Les collections de l'humain : la clé `human-collections`

**Le problème.** Un agent peut écrire dans la base d'une page publiée. Un clic de l'humain dans sa page ne
prouve donc rien tant que rien n'empêche l'agent d'écrire la même ligne : un projet consommateur a refusé
le clic comme autorisation pour cette raison (ticket #340). Le hook `guard_human_data` ferme ces écritures.

**Le geste de l'humain.** Il écrit, dans `docs/agents/usine-gardes.md` (un chemin protégé : la PR qui
change ce fichier se fusionne par lui), une ligne par collection :

```
- `human-collections` : `<page> | <collection>`
```

La page et la collection se comparent telles quelles, sans casse ni espace ajoutés. Une ligne sans ` | ` ou
dont une partie est vide est illisible. La clé se lit comme `origin/main` tient le fichier, jamais dans
l'arbre de travail : une PR qui retire une ligne n'ouvre rien avant sa fusion (A7). Tant que
`usine-gardes.md` est absent de `origin/main`, la clé se lit dans `usine.md`, comme `origin/main` le tient.

**Ce que le garde refuse.** À tout agent, session principale ou sous-agent, sur l'outil `ArtifactData` :

- une écriture simple (`set`, `update`, `str_replace`, `delete`) sur une page et une collection listées ;
- un appel `batch` dont une seule opération vise une collection listée : l'appel entier est refusé,
  aucune opération ne passe ;
- toute écriture, quelle que soit la page, quand une ligne de la clé est illisible : le refus cite la ligne.

Le message commence par `Blocked by the forge plugin (guard_human_data): <page> | <collection>` et dit que
la collection ne s'écrit que depuis la page de l'humain. Il ne contient jamais ce qui était écrit.

**Ce qui passe.** Une lecture (`get`, `list`, `query`, `profiles`), l'écriture d'une autre collection de la
même page, et celle d'une collection du même nom sur une autre page.

**Sans la clé.** L'étape est « sans objet (clé `human-collections` absente) » : aucune écriture n'est refusée. Il n'y a pas
de valeur par défaut.

**Le garde échoue fermé.** Son entrée de `hooks.json` porte `|| exit 2`, `"onFailure": "block"` et un
`timeout` de 60 secondes : une erreur, un script absent ou un dépassement refuse l'écriture. Avec la clé, un
appel que le garde ne sait pas lire (événement illisible, action absente) est refusé, de même qu'une écriture
quand git ne peut pas dire ce que `origin/main` tient de la clé alors que le projet a un fichier de clés.
Un projet sans fichier de clés, ou hors d'un dépôt git, n'a pas la clé : rien n'est refusé.

**La trace.** Chaque refus ajoute une ligne à `~/.claude/hooks/state/refusals/<AAAA-MM-JJ>.jsonl`, avec les
champs des autres gardes : `guard` à `guard_human_data`, `rule` à `human-collection` (ou `unreadable-key-line`,
`unreadable-event`, `unreadable-key`), l'agent, le dépôt, la branche et le verbe `ArtifactData write`. Jamais le
contenu de l'écriture. Le journal vit sur le poste : deux postes, deux journaux.

**Ce qui n'est pas couvert.** Un agent qui écrit la base d'une page par un autre canal que l'outil
`ArtifactData` (un appel réseau lancé depuis `Bash`, par exemple) échappe au garde. Un tel canal, une fois
prouvé, se traite comme un risque de sécurité.

**Ce qui n'a pas été éprouvé.** Les tests rejouent le hook comme un processus sur des événements écrits à la
main, avec les champs `action`, `page`, `collection` et `writes[].collection` que la spec et le design
nomment. Le schéma réel de l'appel `ArtifactData` n'a pas pu être lu pendant la construction, et le hook n'a pas
été joué dans une vraie session de Claude Code : si le nom d'un de ces champs diffère, le garde traite la
partie qu'il ne lit pas comme pouvant viser la collection listée : seule une partie lue et différente laisse
passer l'appel, et sans la clé rien n'est refusé. À vérifier dans la première vraie session qui déclare la clé.
