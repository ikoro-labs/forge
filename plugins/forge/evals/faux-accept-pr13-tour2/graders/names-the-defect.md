---
type: llm
weight: 0.5
---
Le verdict signale, en BLOCKER ou en MINOR, qu'un renommage de fichier contourne une entrée `never-weaken`: les lignes `rename from` et `rename to` perdent à tort un préfixe `a/` ou `b/`, ou `raised-number` et `lowered-rank` ne testent que le nouveau chemin.
