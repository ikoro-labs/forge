# Les indicateurs de service de l'usine

Une usine qui fusionne seule doit dire si elle s'améliore. `factory_slo.py` calcule ses indicateurs
de service (SLI) sans modèle, depuis GitHub, git et les journaux de Claude Code. Ses objectifs (SLO)
et leur budget d'erreur viennent après (série ikoro-labs/forge#55).

```sh
uv run --no-project --quiet python plugins/forge/scripts/factory_slo.py sli <projet> --depuis 2026-10-01 [--jusqua 2026-11-01] [--json]
```

La fenêtre est `[depuis, jusqua[`, `jusqua` valant maintenant par défaut. Sans option, le script rend
un tableau Markdown ; `--json` rend un document `{projet, depuis, jusqua, sli: [...]}`. Il lance
`gh` depuis le dossier du projet (le dépôt se déduit de son `origin`) et `git` dans ce même dossier ;
il ne lit que `docs/agents/usine.md` en configuration.

## Les indicateurs

| SLI | Définition |
| --- | --- |
| `accept-round-1` | part des PR dont le premier verdict (`ROUND: 1`, posté dans la fenêtre) est `ACCEPT` |
| `rework-rate` | part des tickets cités par les PR ouvertes dans la fenêtre qui finissent en `agent-rework` |
| `escaped-defects` | tickets `escaped-defect` ouverts dans la fenêtre, rapportés aux PR fusionnées |
| `lead-time` | médiane et p90 du délai entre la première pose de `ready-for-agent` sur le ticket et la fusion de la PR qui le ferme (`Closes`, pas `Refs`) |
| `release-lag` | médiane et p90 du délai entre une fusion et le premier tag de version qui contient son commit |
| `change-failure` | part des fusions de la fenêtre suivies, dans la fenêtre, d'un revert (`This reverts commit`) ou d'un `escaped-defect` qui les cite |
| `restore-time` | médiane et p90 du délai entre l'ouverture d'un `escaped-defect` et la fusion de la PR qui le ferme (`Closes`, pas `Refs`), par gravité |
| `tokens-per-merge` | jetons de tous les rôles, session principale comprise (`token_audit.py`), divisés par les PR fusionnées |
| `human-touch` | part des PR qui ont reçu `needs-your-attention`, ou dont la ligne `Attention` du `Rapport d'agent` n'est pas `aucune`, pour une autre raison qu'un chemin de la clé `protected-path` |
| `main-green` | part des commits de la branche de base dont les checks de la clé `required-contexts` sont verts |
| `judge-recall`, `false-accept` | lus dans le dernier résultat du jeu de référence (`--reference <fichier JSON>`), sinon « sans objet » |

Les durées sont en heures, la médiane est la vraie médiane, le p90 est au rang le plus proche.

## Ce que le script lit, et ce qu'il ignore

- **Un SLI que ses données ne permettent pas de calculer** (aucune PR dans la fenêtre, clé absente)
  est rendu « sans objet » avec sa raison, jamais 0 ni 100 %. Les clés lues sont `release-tag`,
  `required-contexts` et `protected-path`.
- **Un commentaire de verdict illisible** (`VERDICT:` présent, mais sans `ACCEPT` ou `REJECT`, ou
  sans `ROUND: 1` ou `2`) est ignoré et compté (`illisibles`).
- **`main-green`** : un commit sans résultat pour l'un des checks exigés n'est ni vert ni rouge, il
  est compté à part (`inconnus`). Un check `failure`, `cancelled` ou `timed_out` rend le commit rouge.
- **`lead-time`** : un ticket sans événement `ready-for-agent` avant la fusion est compté à part
  (`sans_evenement`). **`release-lag`** : une fusion qui n'est dans aucun tag de version est comptée
  à part (`non_publiees`) ; un commit absent du clone local l'est aussi.

## L'étiquette `escaped-defect` et la ligne `Échappé de #<pr>`

Un défaut trouvé après la fusion d'une PR devient un ticket portant l'étiquette `escaped-defect`.
Le juge qui reporte un `MINOR` devenu ticket de défaut, ou l'orchestrateur qui trouve le défaut,
pose l'étiquette et écrit dans le corps du ticket une ligne `Échappé de #<pr>` qui nomme la PR
fusionnée en cause. `change-failure` s'appuie sur cette ligne. La gravité se lit sur une étiquette
`gravite:<classe>` (ou `severity:<classe>`), pour `restore-time` ; sans elle, « sans gravité ».

## Clé `release-tag`

Le motif des tags de version du projet, `{version}` tenant pour la version (`<plugin>--v{version}`).
Une ligne par motif. Sans la clé, `release-lag` est « sans objet (clé `release-tag` absente) » ; aucun
motif n'est supposé. Elle est documentée dans `plugins/forge/templates/usine.md`.

## Éprouvé, et pas encore

Le script est éprouvé dans les tests, sur des réponses `gh` fictives et des dépôts git jetables, sous
Linux. Il n'a pas encore tourné contre l'API réelle de GitHub : les noms de champs de
`gh pr list --json` (dont `closingIssuesReferences` et `comments`) et la forme des événements
(`gh api .../issues/<n>/events`) sont ceux de la documentation. `gh` plafonne la liste à 1000 PR et
1000 tickets ; une fenêtre qui en demande plus est tronquée sans avertissement.
