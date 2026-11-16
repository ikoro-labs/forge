---
name: release
description: "Publier une version quand le déclencheur de la clé release-trigger est atteint : l'agent publie seul si et seulement si tous les SLO sont tenus (état calculé dans l'heure), aucune action de budget-action n'est active, l'essai de bout en bout passe sur la tête de la base et aucun ticket sev1 n'est ouvert. Sinon il ouvre la PR de version, pose needs-your-attention avec la condition manquante, et la publication revient à l'humain. Clé release-trigger absente : sans objet, l'agent ne publie rien."
disable-model-invocation: true
---

# La publication continue

Une version attend des fusions : l'usine qui relit le projet reste épinglée sur l'ancienne tant qu'aucun tag
ne sort. Ce skill dit quand une version est due, et si l'agent la publie seul ou la rend à l'humain. Il lit
les clés `release-trigger`, `release-tag`, `slo`, `budget-action`, `e2e-repo`, `e2e-command`,
`e2e-budget-usd`, `git-rules` et `protected-path` de `docs/agents/usine.md`. Une clé absente rend son étape
« sans objet (clé `<nom>` absente) », jamais « tenue » : aucune valeur n'est devinée.

Il se lance depuis la session principale, jamais depuis un coder, un juge ou un passage de `forge:qc` :
il pose un tag, geste qui ne se défait pas.

## 1. Se mettre sur la tête de la base

1. **Le projet** est la copie principale du dépôt, pas un worktree : `git rev-parse --path-format=absolute
   --git-common-dir` rend `<projet>/.git`, et le projet est son dossier parent.
2. `git fetch origin --tags`, puis un worktree détaché hors du projet sur la tête de la base :
   `git worktree add --detach <dossier jetable> origin/<base>`. L'essai de bout en bout porte sur le plugin
   de ce dossier, et sa tête doit être celle de la base : l'essai d'une autre copie ne prouve rien.
3. Recalcule l'état des objectifs, que la condition lit dans l'heure :

   ```
   uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/factory_slo.py" status <projet>
   ```

## 2. Lire la décision

```
uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/release.py" check <projet> --plugin <le plugin du worktree>
```

Le script ne publie, ne tague et n'ouvre rien : il rend une ligne `DECISION:`, le `DECLENCHEUR:`, une ligne
`CONDITION:` par condition (`tenue`, `non tenue` ou `non vérifiable`) et, quand il en manque, `MANQUE:`. Un code
de sortie non nul (clé `release-trigger` illisible) : rends son message et arrête-toi, sans publier.

- `sans objet` (clé `release-trigger` ou `release-tag` absente) : dis-le et arrête-toi. L'agent ne publie rien.
- `rien` : aucune version n'est due, dis combien de fusions attendent et depuis quand, arrête-toi.
- `humain` : le déclencheur est atteint et une condition manque. Ouvre quand même la PR de version (étape 3),
  pose `needs-your-attention` sur elle avec, dans `Attention`, chaque condition de `MANQUE:` et la phrase du
  script qui la dit, puis arrête-toi : la revue, la fusion et le tag reviennent à l'humain. Ne lance pas
  l'essai à sa place : le script ne le lance que lorsque les trois autres conditions tiennent, parce qu'il
  coûte de vrais appels de modèle.
- `publier` : les quatre conditions tiennent, suis les étapes 3 à 5.

Les quatre conditions, chacune lue par le script :

- les SLO : tous `tenu` dans `slo-status.json`, calculé il y a moins d'une heure ; un objectif `menacé`,
  `épuisé` ou « sans objet » ne suffit pas ;
- le budget d'erreur : aucune action de la clé `budget-action` n'est active, `alert` comprise, ni retenue
  pendant la reconstitution du budget ; un état précédent illisible garde l'action fermée ;
- l'essai de bout en bout : `RESULTAT: PASS` sur exactement la tête de la base, arbre non modifié ;
- aucun ticket `sev1` ouvert, sur un dépôt qui porte l'étiquette (l'agent ne la crée pas).

## 3. La PR de version

Elle suit les règles git du projet (clé `git-rules`) : la branche, le titre `chore(release)`, la version
changée à l'endroit que ces règles disent, l'entrée du journal des changements, et, quand la clé `slo` est
déclarée, la section « Objectifs de service » que rend
`factory_slo.py changelog <projet> --depuis <date de la version précédente>`. Le numéro de version se choisit
comme ces règles le disent. Quand elles ne disent pas comment (majeur, mineur ou correctif), c'est une
question de décision : pose `needs-your-attention`, écris la question dans `Attention`, arrête-toi.

La section **Preuves** de la PR recopie les lignes `RESULTAT` et `TETE` de l'essai, et sur un `FAIL` ses lignes
`ETAPE` et `RAISON`. Quand l'essai n'a pas été lancé, elle le dit et dit pourquoi. Elle liste aussi les quatre
conditions telles que le script les a rendues.

## 4. La revue et la fusion

Lance `/forge:qc` sur la PR de version : c'est lui qui juge et fusionne, jamais toi. Un chemin de la clé
`protected-path` touché, ou une action `human-merge` active, arrête la fusion : l'humain fusionne, et ce skill
s'arrête sans tag.

## 5. Le tag

Une fois la PR fusionnée :

1. `git fetch origin --tags`, puis relis les trois conditions peu coûteuses sur l'état recalculé :
   `factory_slo.py status <projet>` puis `release.py condition slo|budget|sev1 <projet>`. Une condition qui
   ne tient plus : pas de tag, `needs-your-attention` avec la condition, l'humain décide.
2. Pose le tag **annoté** sur le commit de fusion de la PR de version, nommé par le motif de la clé
   `release-tag` avec la version de la PR, puis pousse-le par son nom : `git tag -a <tag> -m <message> <commit>`,
   `git push origin <tag>`. Vérifie que `git rev-parse <tag>^{commit}` est le commit de fusion.
3. **Un tag ne se déplace ni ne se supprime**, même poussé par erreur : ni `git tag -f`, ni
   `git push --force`, ni `git push --delete`. Une erreur de tag se dit à l'humain.
4. Retire le worktree détaché du premier pas, et dis le tag posé, le commit et l'état des quatre conditions.

Ce skill ne monte pas l'épingle de l'usine du projet et ne change aucune règle de tags côté serveur : ce
sont des PR et des gestes à part.
