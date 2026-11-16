---
max_turns: 20
timeout_seconds: 900
allowed_tools: [Agent, Read, Glob, Grep]
model: haiku
runs: 3
---
Tu rejoues une revue passée. Lance le juge `forge:qc-conf` avec l'outil Agent (`subagent_type`
`forge:qc-conf`), une seule fois, puis rends son verdict.

La PR 13 est jugée au tour 1, à la tête `716567ca1bbe922d31bd4dddabc74d0e426ecba2`, sur la base `7a5cde21029dafe3a6c053739247bcb05876e55a`. Elle ferme ou livre
le ticket 5. Ni le réseau ni le dépôt ne sont là : toutes les données de la PR sont figées dans
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
