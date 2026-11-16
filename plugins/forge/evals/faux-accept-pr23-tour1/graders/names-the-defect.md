---
type: llm
weight: 0.5
---
Le verdict signale qu'aucun test ne garde le décodage de `rename to` par `_unquote` seul: remettre `_path` sur cette ligne laisse toute la suite verte (un fichier `y/ref.txt` déplacé tel quel vers `b/y/ref.txt` échapperait à une entrée `y/`).
