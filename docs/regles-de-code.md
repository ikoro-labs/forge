# Les règles de code que l'usine tient pour un projet

Cette page décrit les clés que le projet écrit dans `docs/agents/usine.md` pour que l'usine tienne ses règles
de code, une par une. Elle commence par la clé `stack` : une PR qui ajoute une dépendance que personne n'a
décidée n'est plus relue, elle est refusée. Elle dit ensuite le type `raised-entry` de la clé `never-weaken`,
qui refuse qu'une liste de référence grandisse. Les autres clés de la feature s'ajoutent ici quand leur ticket
est fusionné ; le gabarit `plugins/forge/templates/usine.md` documente chacune.

## La clé `stack`

La clé désigne un fichier, sur une seule ligne de `usine.md` :

```
- `stack` : `<chemin du fichier>`
```

Chaque ligne de ce fichier dit un paquet que le projet a décidé de permettre :

```
<écosystème> | <paquet> | <source>
```

- L'écosystème est fermé : `pypi` (lu dans un `uv.lock`) ou `npm` (lu dans un `package-lock.json`).
  Un autre écosystème est une ligne `INVALID`.
- Le paquet est comparé normalisé pour `pypi` (casse, `-`, `_` et `.` valent le même caractère) et tel qu'écrit
  pour `npm`.
- La source est la décision acceptée qui permet le paquet : un ADR, ou une séance. Une ligne sans source
  existe, mais ne permet rien (`NO SOURCE`).
- Une ligne de moins de trois champs, ou d'un écosystème inconnu, est `INVALID` avec son numéro de ligne :
  elle n'est jamais complétée.

Sans la clé, la sonde rend « sans objet (clé `stack` absente) » et n'est jamais un `PASS` : un projet qui
n'écrit rien ne change pas. La clé `lockfile` (un lockfile par ligne, `<chemin> | <écosystème>`) doit aussi
être écrite, car c'est elle qui dit quels verrous comparer ; sans elle, la sonde est « sans objet (clé
`lockfile` absente) ».

## Ce que `forge:qc-gate` mesure

La sonde 16 lance `plugins/forge/scripts/stack_check.py` avec les clés lues sur la base. Pour chaque lockfile
de la clé `lockfile`, le script lit le fichier à la base et à la tête par `git show`, et compare les paquets
directs que la tête déclare dans un membre local et que la base ne déclarait pas. Une dépendance indirecte
(un paquet dont un autre a besoin) n'est pas comparée : son âge reste à la sonde 15. Le script n'ouvre aucun
accès réseau et ne lance aucune commande du projet.

Une ligne par résultat :

| Statut | Sens |
|---|---|
| `OK` | le paquet est dans la liste, avec une source |
| `UNLISTED` | le paquet n'est pas dans la liste |
| `NO SOURCE` | le paquet est dans la liste, sans source |
| `ADDED` | la PR ajoute cette ligne à la liste, avec sa source |
| `NONE` | le lockfile n'ajoute aucun paquet direct |
| `NOT RUN` | un écosystème de la liste qu'aucune entrée de `lockfile` ne lit : rien n'y est comparé |
| `INVALID` | une ligne de la liste, une entrée de clé ou un lockfile mal formés |

## Le message de refus

`forge:qc-conf` pose un `BLOCKER` (règle `F-8` du socle) sur chaque ligne `UNLISTED` ou `NO SOURCE`, et son
premier message dit quoi écrire, jamais un refus muet :

```
UNLISTED    <lockfile>    pypi <paquet>    ligne à écrire : `pypi | <paquet> | <ADR ou séance>` dans <chemin de la liste>
NO SOURCE   <lockfile>    pypi <paquet>    ligne <n> de <chemin de la liste> sans source : écrire l'ADR ou la séance qui l'autorise
```

`NOT RUN` et `INVALID` ne sont pas un constat sur un paquet : le juge les rend tels quels, jamais comme un
`OK` ni comme « aucune dépendance ajoutée ».

## Accepter une dépendance

Le geste est celui de l'humain du projet, ou de la personne à qui il a délégué la décision : la décision vient
d'abord, la ligne ensuite.

1. Décider le paquet par écrit : un ADR quand il est structurant, sinon une séance qui le dit.
2. Écrire sa ligne dans le fichier de la clé `stack`, avec cette décision pour source :
   `pypi | <paquet> | <ADR ou séance>`. Le coder peut proposer la ligne dans sa PR ; la décision reste celle
   de l'humain.
3. Laisser la PR passer la revue. La ligne que la PR ajoute sort `ADDED` avec sa source, et le juge lit cette
   source au titre de `F-8` : une source qui n'existe pas, ou qui n'autorise pas ce paquet, rejette la PR. Le
   paquet et sa ligne se fusionnent ensemble.

Une PR ne s'autorise pas elle-même par un changement du chemin : le chemin de la clé `stack` se lit sur la
base, pas sur la tête. Le contenu de la liste, lui, se lit sur la tête : un fichier absent à la tête est une
liste vide, donc tout paquet ajouté est `UNLISTED`.

## La liste de référence, `raised-entry`

Une liste de référence est un fichier de dettes tolérées (la clé `baselines` dit à quels fichiers le juge
applique `F-13`). Le type `raised-entry` de la clé `never-weaken` la garde contre une hausse : `raised-number`
laisse passer une dette ajoutée seule, `raised-entry` non. L'entrée s'écrit sans paramètre :

```
- `never-weaken` : `<chemin> | raised-entry`
```

Le chemin est un fichier, ou un dossier quand il finit par `/`. Chaque ligne du fichier est `<nombre> <clé>`, ou
`<clé>` seule, qui compte 1. `forge:qc-gate` lance `plugins/forge/scripts/never_weaken.py` sur le diff de la PR,
avec les entrées lues sur la base, et compare, fichier du diff par fichier du diff, chaque clé des lignes
ajoutées à la même clé des lignes retirées du même fichier :

| Le diff | Le script |
|---|---|
| une clé nouvelle, absente des lignes retirées | `APPLIES`, avec le fichier et la clé |
| un nombre plus grand (de 3 à 4) | `APPLIES`, avec la clé et les deux nombres |
| une clé retirée, ou une baisse du nombre | rien : la PR passe |
| une ligne `<clé>` seule ajoutée | `APPLIES` : elle compte 1, donc c'est une clé nouvelle |

Un renommage de clé est une clé nouvelle : l'humain tranche. Une entrée `<chemin> | raised-entry | <paramètre>`
est `INVALID` : le type ne prend pas de paramètre, et le script ne la complète pas. Une PR qui retire ou modifie
l'entrée dans `usine.md` s'applique elle-même, comme pour les autres types.

## Ce qui est éprouvé

Éprouvé par les tests de `tests/test_stack_check.py` seulement, sur un dépôt jetable avec un `uv.lock` produit
par `uv lock` et un `package-lock.json` produit par `npm install --package-lock-only` (le cas npm est sauté
quand `npm` manque), sous Linux. `raised-entry` l'est par `tests/test_never_weaken.py`, sur des diffs écrits
à la main, sous Linux. Pas encore dans une vraie passe de `forge:qc-gate`, ni sur un projet
consommateur. Le détail des autres clés de la feature, et la lecture finale de cette page, viennent avec leurs
tickets.
