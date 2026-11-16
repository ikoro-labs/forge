---
max_turns: 20
timeout_seconds: 900
allowed_tools: [Agent, Read, Glob, Grep]
model: haiku
runs: 3
---
Tu rejoues une revue passée. Lance le juge `forge:qc-conf` avec l'outil Agent (`subagent_type`
`forge:qc-conf`), une seule fois, puis rends son verdict.

La PR 11 est jugée au tour 1, à la tête `9a796c5782790e38d08378124e4e5c829b2d6ca8`, sur la base `9c0847e7f3c2c86424c77f8d0689212a93618e9f`. Elle ferme ou livre
le ticket 2. Ni le réseau ni le dépôt ne sont là : toutes les données de la PR sont figées dans
le dossier `fixtures/` du dossier de travail. Dis au juge de les lire avec ses outils de lecture, à
la place de `gh` et de `git`, et d'y trouver :

- `fixtures/ticket.txt` : le ticket et ses commentaires d'avant la revue ;
- `fixtures/pr-body.txt` : le corps de la PR ;
- `fixtures/pr.diff` : le diff de la base à la tête ;
- `fixtures/gate.txt` : le tableau de `forge:qc-gate`, figé ;
- `fixtures/claude.txt`, `fixtures/rules-forge.txt`, `fixtures/rules-git.txt` et `fixtures/usine.txt` :
  le `CLAUDE.md`, les deux fichiers de règles et la configuration de l'usine de la base, qui font la grille ;

Dis-lui de juger au tour 1, sans lancer aucune commande, et de rendre son verdict dans la forme
habituelle. Quand il a répondu, recopie son verdict tel quel, de la ligne `VERDICT:` à la dernière
ligne, sans le commenter ni le corriger.
