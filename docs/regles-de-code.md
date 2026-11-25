# Les règles de code que l'usine tient pour un projet

Cette page décrit les clés que le projet écrit dans `docs/agents/usine.md` pour que l'usine tienne ses règles
de code, une par une : le format de chaque ligne, ce que l'usine mesure, le message d'un refus et le geste de
l'humain. Une clé absente rend « sans objet (clé `<nom>` absente) », jamais un `PASS` : un projet qui n'écrit rien
ne change pas, et aucune clé n'a de valeur par défaut. Le gabarit `plugins/forge/templates/usine.md` documente
chacune, avec une base de règles à copier (voir « La base de règles »).

## Les clés, d'un coup d'oeil

- `stack` : `<chemin du fichier>` ; chaque ligne du fichier est `<écosystème> | <paquet> | <source>`. Refuse une
  dépendance directe que personne n'a décidée (sonde 16).
- `lockfile` : `<chemin> | <écosystème>`, une ligne par verrou. Dit quels verrous comparer ; sans elle, `stack` n'a
  rien à lire.
- `never-weaken` : `<chemin> | raised-entry` (ou `<chemin> | removed-line`). Refuse qu'une liste de référence
  grandisse, ou qu'une règle d'une carte disparaisse.
- `lint-on-write` : `<motif> | <commande>`, une ligne par contrôle. Refuse l'écriture d'un fichier que la commande
  rejette, avec la fin de sa sortie.
- `format-on-write` : `<motif> | <commande>`, une ligne par formateur. Même exécuteur : la fin de la sortie d'un
  formateur en échec est relayée aussi.
- `architecture-check` : `<commande>`, sur une seule ligne. Rejoue la carte des modules sur la tête (sonde 17).
- `recurring-finding` : `<seuil> | <jours>`. Liste le constat qui revient de PR en PR, dans un commentaire.
- `slo-issue` : `<numéro du ticket>`. Reçoit ce commentaire ; sans elle, rien n'est écrit.

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

## Les contrôles à l'écriture

La clé `lint-on-write` suit la forme de `format-on-write` : une ligne `<motif> | <commande>` par contrôle, le motif
se comparant au chemin relatif entier. La commande est découpée comme par un shell POSIX, lancée sans shell depuis la
racine du projet, le chemin absolu du fichier écrit en dernier argument. Chaque commande a 30 s et l'écriture 120 s
au total, partagées avec les formateurs : au délai, le groupe de processus est tué.

Un contrôle qui échoue refuse l'écriture, mais ne la défait pas : le hook `after_write` sort en code 2 et écrit sur
stderr, pour que l'agent voie la règle enfreinte et corrige :

```
lint-on-write: <commande> failed on <chemin> (<raison>)
<les 20 dernières lignes de la sortie de l'outil, 2000 octets au plus>
```

La raison est `exit <n>`, `timed out after <n>s`, `command not found`, `could not start: <cause>` ou
`not run: <cause>`. La fin de la sortie est relayée de la même façon pour `format-on-write`, dont elle était
jetée jusqu'ici. Une ligne de la clé qui n'est pas `<motif> | <commande>` est ignorée, et le message le dit. Chaque
refus entre au journal des refus (`guard` `after_write`, `rule` le nom de la clé), jamais avec la commande ni la
sortie ; l'indicateur `guard-refusals` ne compte pas ces lignes. Un fichier écrit par une commande de shell (un
heredoc, `sed`) ne passe pas par ce hook.

## Le contrôle d'architecture

La clé `architecture-check` est une commande, sur une seule ligne, qui sort 0 quand la carte des modules du design
est tenue. `forge:qc-gate` la lit sur la base (une PR ne change pas la règle qui la juge), la rejoue sur une copie
de la tête sous le lanceur borné des clés `run-limits` et `run-budget`, et rend `PASS` (code 0), `FAIL` (un autre
code) ou `NOT RUN` (commande introuvable, poste hors budget, mémoire ou délai atteints : jamais un `PASS`).
`forge:qc-conf` pose un `BLOCKER` de la règle `F-15` sur un `FAIL`, avec la commande et la fin de sa sortie : le
coder sait quel module corriger.

La carte elle-même est un fichier du dépôt : pour qu'une PR n'en retire pas une règle sans l'humain, protège-la
par une entrée `never-weaken` de type `removed-line` :

```
- `never-weaken` : `docs/agents/modules.md | removed-line`
```

## Le constat récurrent

Quand le juge relève le même `F-n` ou `L-n` sur plusieurs PR, c'est la règle qui manque ou qui est mal tenue. La
clé `recurring-finding` s'écrit `<seuil> | <jours>` (deux entiers positifs, par exemple `3 | 30`). Après chaque
verdict, `forge:qc` lance `plugins/forge/scripts/recurring_findings.py` : le script compte les PR distinctes jugées
dans la fenêtre qui citent un même identifiant, une PR qui le cite à plusieurs tours comptant une fois. Un
identifiant cité par au moins `<seuil>` PR distinctes est listé, avec ses PR, dans un commentaire unique du ticket
de la clé `slo-issue`, retrouvé par son marqueur caché et réécrit à chaque passage. Un constat sans `F-n` ni `L-n`
est compté à part. Le commentaire ne porte que des identifiants, des numéros de PR et des dates : le constat devient
un commentaire, jamais un ticket. Sans l'une des deux clés, le script rend « sans objet (clé `<nom>` absente) » et
n'écrit rien.

## La base de règles

Le gabarit propose, en une ligne de `lint-on-write`, trois règles de ruff avec leur seuil écrit en clair :

```
- `lint-on-write` : `**/*.py | uv run --no-project --quiet --with ruff==0.17.3 ruff check --preview --select C901,PLR0913,PLR1702 --config lint.mccabe.max-complexity=10 --config lint.pylint.max-args=5 --config lint.pylint.max-nested-blocks=5`
```

| Règle | Seuil | Ce qu'elle refuse |
|---|---|---|
| `C901` | 10 | une fonction de complexité cyclomatique supérieure à 10 |
| `PLR0913` | 5 | une fonction de plus de 5 paramètres |
| `PLR1702` | 5 | une fonction qui imbrique plus de 5 blocs |

`PLR1702` est en aperçu dans ruff : `--preview` est nécessaire et la version est épinglée, car une règle d'aperçu
peut changer de sens ou disparaître. `--select` limite la ligne à ces trois règles, pour que l'aperçu ne s'applique
qu'à elles. Il n'y a aucun plafond de lignes : aucune règle de la base ne borne la longueur d'une fonction ni d'un
fichier. Le gabarit donne aussi la forme d'une carte des modules (`<module> | <interface publique> | <dépend de>`)
à côté de `architecture-check`, et deux lignes d'un fichier `stack`.

Ces réglages ont été essayés sur ce dépôt avant d'être écrits, par la commande de la ligne ci-dessus sur
`plugins/forge` et `tests`, avec `--statistics` : 88 constats, dont `C901` 63 et `PLR0913` 25, et `PLR1702` 0
(81 constats dans `plugins/forge`, 7 dans `tests`). `PLR1702` n'est pas muette pour autant : sur une fonction de
six `for` imbriqués, elle sort « Too many nested blocks (6 > 5) ». Un projet qui copie la ligne verra donc ses
fonctions existantes refusées à la prochaine écriture ; il règle un seuil sur sa ligne, ou écrit la dette dans une
liste de référence (`raised-entry`).

## Ce qui est éprouvé

Éprouvé par les tests, sous Linux : `stack` par `tests/test_stack_check.py`, sur un dépôt jetable avec un `uv.lock`
produit par `uv lock` et un `package-lock.json` produit par `npm install --package-lock-only` (le cas npm est sauté
quand `npm` manque) ; `raised-entry` par `tests/test_never_weaken.py`, sur des diffs écrits à la main ;
`lint-on-write` et la fin de sortie relayée par `tests/test_after_write.py` et `tests/test_after_write_journal.py` ;
`recurring-finding` par `tests/test_recurring_findings.py`, où `gh` est simulé ; le contenu du gabarit, de cette
page et du `README.md` par `tests/test_rule_base_content.py`. La commande de ruff a été lancée sur ce dépôt, pas
sur un projet consommateur.

Pas encore éprouvé : une vraie passe de `forge:qc-gate` pour les sondes 16 et 17, la sonde 17 sur un projet réel,
`recurring_findings.py` contre un vrai ticket.
