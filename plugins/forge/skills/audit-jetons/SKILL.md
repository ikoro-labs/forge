---
name: audit-jetons
description: "Compter les jetons dépensés par chaque rôle de l'usine sur ce projet, par modèle et par effort, et comparer un avant et un après (une montée de version, un changement de modèle). Lu dans les journaux que Claude Code écrit déjà. Ne modifie rien."
argument-hint: "[--depuis <date>] [--jusqua <date>] [--coupure <date>]"
disable-model-invocation: true
---

# Les jetons de chaque rôle

1. **Le projet** est la copie principale du dépôt, pas un worktree : ses worktrees y sont comptés.
   `git rev-parse --path-format=absolute --git-common-dir` rend `<projet>/.git` ; le projet est
   son dossier parent.
2. **Lance le script** avec les arguments reçus, tels quels :

   ```
   uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/token_audit.py" <projet> $ARGUMENTS
   ```

   Une date est ISO (`2026-10-20` ou `2026-10-20T21:52`), en UTC quand elle n'a pas de zone, comme
   les heures de fusion de GitHub. `--jusqua` est exclue. `--coupure` sépare l'avant de l'après :
   la date de fusion de la PR qui a changé un modèle ou un effort, par exemple.
3. **Rends** les tableaux tels que le script les imprime, puis, en trois lignes au plus, ce qu'ils
   montrent : le rôle qui dépense le plus par lancement, et l'écart de chaque rôle entre l'avant et
   l'après quand il y a une coupure. Un rôle lancé une ou deux fois d'un côté ne prouve rien :
   dis-le au lieu de conclure.

Ne modifie rien. Le total mêle quatre sortes de jetons (entrée, écriture de cache, lecture de
cache, sortie) dont le prix n'est pas le même ; le script n'en donne aucun, faute de tarif publié
par chaque fournisseur. Un code de sortie non nul : rends son message et arrête-toi.
