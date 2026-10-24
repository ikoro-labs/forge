---
name: slo
description: "Rendre le rapport des objectifs de service de l'usine (SLO) : chaque objectif, sa valeur, son budget d'erreur restant, son état et sa tendance par rapport à la fenêtre précédente. À la demande, sans rien modifier. Avec l'argument --publier, réécrit le rapport dans l'issue de suivi (clé slo-issue)."
argument-hint: "[--publier] [--json] [--reference <fichier>]"
disable-model-invocation: true
---

# Le rapport des objectifs de service

1. **Le projet** est la copie principale du dépôt, pas un worktree : `git rev-parse --path-format=absolute
   --git-common-dir` rend `<projet>/.git`, et le projet est son dossier parent.
2. **Lance le script** avec les arguments reçus, tels quels :

   ```
   uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/factory_slo.py" report <projet> $ARGUMENTS
   ```

   Sans la clé `slo` de `docs/agents/usine.md`, le script répond « sans objet (clé `slo` absente) » :
   rends cette phrase, sans rien supposer. Un code de sortie non nul (une ligne de `slo` mal formée,
   une clé `slo-issue` qui n'est pas un numéro, `gh` qui échoue) : rends son message et arrête-toi.
3. **Rends** le tableau tel que le script l'imprime, puis, en trois lignes au plus : les objectifs
   `menacé` ou `épuisé` avec la part de budget consommée, ceux dont la tendance se dégrade, et ceux
   « sans objet » avec leur raison. Un objectif « sans objet » n'est ni tenu ni épuisé : ne conclus
   rien à son sujet.

Sans `--publier`, le script ne modifie rien : ni GitHub, ni fichier. Avec `--publier`, il réécrit le
rapport dans l'unique commentaire que la clé `slo-issue` désigne (retrouvé par un marqueur caché),
pose `needs-your-attention` sur cette issue, avec la raison, quand un objectif passe à `menacé` ou
`épuisé`, et la retire, en disant pourquoi, quand plus aucun ne l'est. Il ne retire jamais une
étiquette qu'un de ses rapports n'a pas posée. N'ajoute `--publier` que si l'humain l'a demandé,
ou si la procédure de publication d'une version le prévoit. Sans la clé `slo-issue`, la publication
est « sans objet (clé `slo-issue` absente) ».
