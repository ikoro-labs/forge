# Le jeu de référence du juge

`plugins/forge/evals/` mesure le juge `forge:qc-conf` : il rejoue huit revues passées de ce dépôt
devant lui et note le verdict. Il alimente deux objectifs de service (`judge-recall` et
`false-accept`, voir `docs/indicateurs-de-service.md`) que `factory_slo.py` ne sait pas calculer
seul, faute de données : sans ce jeu, ils restent « sans objet ».

Il se lance à la main, sous un plafond de coût. Aucune suite de tests ne le lance, et aucun appel à un
modèle ne se fait ailleurs que par la commande de lancement.

## Les huit cas

Chaque cas est un dossier de `plugins/forge/evals/` : `case.yaml`, `prompt.md`, `graders/`,
`scaffold.sh` et `fixtures/`. Les données de la PR sont figées dans `fixtures/` (le diff de la base à
la tête, le ticket et ses commentaires d'avant la revue, le corps de la PR, la grille de la base et le
tableau de `forge:qc-gate`), parce que le cas doit se rejouer sans réseau et sans le dépôt.

| Famille | Cas | Verdict attendu |
| --- | --- | --- |
| `blocker-` | PR 11, 13, 28, 30 et 51, au tour 1 | `REJECT` : chacune portait un `BLOCKER` avéré |
| `faux-accept-` | PR 13 au tour 2, PR 14 et PR 23 au tour 1 | `REJECT`, ou au moins le défaut que le juge de l'époque a laissé passer |

Chaque cas porte deux notations sur le dernier message du juge, des expressions régulières sur la
ligne `VERDICT:` :

- `rejects` réussit si une ligne `VERDICT: REJECT` y figure ;
- `no-false-accept` réussit si aucune ligne `VERDICT: ACCEPT` n'y figure.

Les cas `faux-accept-` ont en plus `names-the-defect`, une notation par un modèle qui dit si le verdict
nomme le défaut manqué. Elle n'entre dans aucune des deux mesures : elle sert à lire un cas à la main.

## Les deux mesures

`eval_reference.py score` lit le `aggregate-result.json` de `claude plugin eval` et écrit le fichier
que `factory_slo.py report --reference` lit :

```sh
uv run --no-project --quiet python plugins/forge/scripts/eval_reference.py score <aggregate-result.json> --output reference.json
```

- `judge-recall` : part des runs des cas `blocker-` dont le verdict est `REJECT`.
- `false-accept` : part des runs de tous les cas dont le verdict est `ACCEPT`. Chaque cas rejoue une PR
  qui n'aurait pas dû être acceptée, donc chaque `ACCEPT` est un faux.

Un run en erreur (appel qui échoue, délai dépassé) reste hors des deux parts et se compte sur la sortie
d'erreur : ce n'est ni un `REJECT` ni un `ACCEPT`. Une mesure sans aucun run derrière elle manque du
fichier, et l'objectif la lit « sans objet », jamais 0 ni 100 %. Un run sans ligne `VERDICT:` compte
comme un défaut du juge dans `judge-recall` (il n'a pas rejeté) et pas comme un faux accept.

## Lancer le jeu

```sh
uv run --no-project --quiet python plugins/forge/scripts/eval_reference.py run --max-cost-usd <plafond> --output-dir <dossier hors du plugin>
```

La commande refuse de partir sans `--max-cost-usd`. Elle lance `claude plugin eval` sur le plugin avec :

- `--max-cost-usd` : le plafond de coût en dollars. Au plafond, `claude plugin eval` s'arrête, rend un
  résultat partiel et sort en code 2 ; `score` le signale et ne compte que les runs menés ;
- `--scaffold` : sans lui le script `scaffold.sh` de chaque cas ne tourne pas, et le juge n'a aucune
  donnée à lire ;
- `--ablation none` : l'autre bras, sans le plugin, doublerait le coût pour un chiffre que personne
  ne lit ici ;
- `--no-publish` : le rapport ne part nulle part ;
- `--output-dir` : un dossier hors du plugin, parce que Claude Code peut charger comme composants les
  fichiers qu'on y laisse. La commande refuse un dossier dans le plugin.

`--runs <n>` et `--case <glob>` passent tels quels. Chaque cas demande trois runs par défaut.

Le plafond n'a pas de valeur par défaut : le coût d'un run n'a jamais été mesuré ici. Au premier
lancement, `--runs 1 --case 'blocker-pr11-*'` avec un plafond bas donne le coût d'un run et dit si le
format des cas tient, avant le jeu entier.

## Ce qui n'a pas été éprouvé

Le format des cas (`case.yaml`, `prompt.md`, `graders/*.md`), la forme de `aggregate-result.json` et
le comportement de `--scaffold` ont été relevés dans le programme `claude` 2.1.325, sans qu'aucun cas
ait tourné : la contrainte de la PR qui a livré le jeu interdisait tout appel à un modèle. Restent à
vérifier au premier lancement :

- que l'agent `forge:qc-conf` se charge et se lance par l'outil `Agent` dans le bac à sable de
  `claude plugin eval` ;
- que le juge lit bien `fixtures/` depuis le dossier de travail que `scaffold.sh` remplit ;
- que `eval_reference.py score` lit un vrai `aggregate-result.json` : il accepte les noms en
  `camelCase` (bras `arms.with`) et en `snake_case` (`runs`).

La CI épingle `claude` à la version 2.1.304 dans son job `validate`. Le jeu ne tourne pas en CI : il se
lance sur un poste dont `claude plugin eval` existe, et la version qui l'a relevé est la 2.1.325.

## Limites des cas

- Les cas `faux-accept-` de la PR 13 (tour 2) et de la PR 23 sont faibles par construction : le défaut
  que le juge de l'époque a laissé passer n'était qu'un `MINOR` dans le verdict rendu ensuite. Le juge
  peut bien juger et ne pas le nommer.
- Les corps de PR figés sont ceux d'aujourd'hui, coupés avant `Rapport d'agent`, pas ceux du moment
  de la revue. Les tableaux de `forge:qc-gate` sont reconstruits (état des checks de la tête, périmètre) :
  les sondes que le jeu ne rejoue pas y sont marquées `NOT RUN`.
- Chaque cas cite un numéro de PR de ce dépôt dans ses données : il les porte avec lui parce qu'un jeu de
  référence est une mémoire de ce dépôt. Aucune invite générique du plugin n'en cite.
