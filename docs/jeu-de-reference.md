# Le jeu de référence du juge

`plugins/forge/evals/` mesure le juge `forge:qc-conf` : il rejoue onze revues passées de ce dépôt
devant lui et note le verdict. Il alimente deux objectifs de service (`judge-recall` et
`false-accept`, voir `docs/indicateurs-de-service.md`) que `factory_slo.py` ne sait pas calculer
seul, faute de données : sans ce jeu, ils restent « sans objet ». Une troisième mesure, `false-reject`,
n'a pas d'objectif : elle dit si le juge rejette à tort. Neuf cas piégés s'y ajoutent (voir plus bas) :
ils mesurent le rappel du juge classe de défaut par classe, à part des mesures des cas réels.

Il se lance à la main, sous un plafond de coût. Aucune suite de tests ne le lance, et aucun appel à un
modèle ne se fait ailleurs que par la commande de lancement.

## Les onze cas

Chaque cas est un dossier de `plugins/forge/evals/` : `case.yaml`, `prompt.md`, `graders/`,
`scaffold.sh` et `fixtures/`. Les données de la PR sont figées dans `fixtures/` (le diff de la base à
la tête, le ticket et ses commentaires d'avant la revue, le corps de la PR, la grille de la base et le
tableau de `forge:qc-gate`), parce que le cas doit se rejouer sans réseau et sans le dépôt.

| Famille | Cas | Verdict attendu |
| --- | --- | --- |
| `blocker-` | PR 11, 13, 28, 30 et 51, au tour 1 | `REJECT` : chacune portait un `BLOCKER` avéré |
| `faux-accept-` | PR 13 au tour 2, PR 14 et PR 23 au tour 1 | `REJECT`, ou au moins le défaut que le juge de l'époque a laissé passer ; hors de `false-accept` pour la PR 13 et la PR 23 |
| `accept-` | PR 226, 228 et 238, au tour 1 | `ACCEPT` : chacune a été acceptée au tour 1, fusionnée, et aucun correctif ne l'a suivie |

Les cas `accept-` ont été choisis parmi les PR fusionnées sur un `ACCEPT` du tour 1 et relues dans
`git log` de `main` : aucune PR ultérieure ne les cite comme correctif, et aucun commit ultérieur ne
touche leurs fichiers pour les corriger. Leur verdict de l'époque portait des `MINOR` et des `NOTE` : un
juge qui accepte et les nomme réussit le cas.

Les cas `blocker-` et `faux-accept-` portent deux notations sur le dernier message du juge, des
expressions régulières sur la ligne `VERDICT:` :

- `rejects` réussit si une ligne `VERDICT: REJECT` y figure ;
- `no-false-accept` réussit si aucune ligne `VERDICT: ACCEPT` n'y figure.

Les deux cas `faux-accept-` de la PR 13 au tour 2 et de la PR 23 n'ont pas `no-false-accept` : le défaut
que le juge de l'époque a laissé passer n'y était qu'un `MINOR`, et un juge qui accepte alors peut avoir
raison. Leur `ACCEPT` reste donc hors de `false-accept` (la part ne les compte ni au numérateur ni au
dénominateur). Ils gardent `rejects` et `names-the-defect`, qui se lisent à la main.

Les cas `faux-accept-` ont en plus `names-the-defect`, une notation par un modèle qui dit si le verdict
nomme le défaut manqué. Elle n'entre dans aucune des mesures : elle sert à lire un cas à la main.

Les cas `accept-` attendent le verdict inverse et portent deux autres notations, sur la même ligne :

- `accepts` réussit si une ligne `VERDICT: ACCEPT` y figure ;
- `no-false-reject` réussit si aucune ligne `VERDICT: REJECT` y figure.

Ils ne portent pas `no-false-accept` : un `ACCEPT` y est le bon verdict, et il ne compte pas dans
`false-accept`.

## Les cas piégés

Un cas réel rejoue une PR où le défaut est arrivé tout seul. Un cas piégé part d'un cas `accept-` figé
(PR 226, 228 ou 238, acceptée au tour 1 et jamais corrigée) et y plante **un** défaut connu, d'une
classe donnée, dans `fixtures/pr.diff`. Le juge n'en est pas prévenu : l'invite est celle du cas
`accept-` d'origine, et le défaut est la seule chose qui change dans ce qu'il lit (avec la ligne
`Base et diff` et la ligne `Périmètre` du tableau de `forge:qc-gate`, que le script recalcule sur le
diff piégé). Il doit rendre `REJECT` et nommer le défaut.

Trois classes, trois cas par classe :

| Classe | Ce que le script plante | Cas |
| --- | --- | --- |
| `weakened-test` | une assertion d'un test est retirée ou assouplie | `trap-weakened-test-pr238-label`, `trap-weakened-test-pr228-sha`, `trap-weakened-test-pr228-keywords` |
| `out-of-scope` | un fichier que le ticket ne touche pas est modifié | `trap-out-of-scope-pr226-rule`, `trap-out-of-scope-pr228-threshold`, `trap-out-of-scope-pr238-test-rule` |
| `unmet-criterion` | le code d'un critère est retiré, son test gardé (PR 228) ou supprimé (PR 238) ; la PR 226 n'en a pas | `trap-unmet-criterion-pr226-sev3`, `trap-unmet-criterion-pr228-fail-open`, `trap-unmet-criterion-pr238-attention` |

La PR 226 ne change que `docs/agents/usine.md` et n'a aucun test : aucun cas `weakened-test` ne s'y
plante. Cette classe s'appuie sur la PR 238 (un cas) et sur la PR 228 (deux cas).

Chaque cas piégé porte les trois notations de la famille `blocker-` : `rejects` et `no-false-accept`
(mêmes expressions régulières sur la ligne `VERDICT:`), et `names-the-defect`, une notation par un
modèle qui dit si le verdict nomme le défaut planté. Cette dernière n'entre dans aucune mesure : elle se
lit à la main.

### Fabriqués par un script, d'après une spécification

Un cas piégé n'est pas écrit à la main : le script `plant_defect.py` (`plugins/forge/scripts/`) le fabrique, et le dossier
du cas est la sortie de sa spécification, versionnée dans `plugins/forge/eval-traps/` (un fichier `<cas>.json` par cas).

```sh
uv run --no-project --quiet python plugins/forge/scripts/plant_defect.py plugins/forge/eval-traps/<cas>.json
```

La spécification donne le `name` (`trap-<classe>-<mot>`), la `class`, la `source` (un cas `accept-`), un
`summary` et le `defect` que le juge doit nommer, puis `edits` (des lignes ajoutées du diff, `old`
remplacé par `new`, trouvé une seule fois) ou `outside` (une ligne d'un fichier que le cas porte dans
`fixtures/`, que le diff ne change pas). Le script refuse une spécification qui n'est pas de sa classe : un
test qui gagne une ligne, un `out-of-scope` qui touche un fichier du diff, un `unmet-criterion` qui
réécrit un test. Les en-têtes `@@` des blocs qui suivent une retouche sont recalculés, et tous les autres
fichiers du cas sont copiés octet pour octet. La même spécification donne le même cas, octet pour octet ;
un test régénère chaque cas depuis sa spécification et le compare au dossier versionné, pour qu'aucun
des deux ne dérive seul. Le script ne lit ni l'horloge, ni l'environnement, et n'appelle aucun modèle.

## Les trois mesures

`eval_reference.py score` lit le `aggregate-result.json` de `claude plugin eval` et écrit le fichier
que `factory_slo.py report --reference` lit :

```sh
uv run --no-project --quiet python plugins/forge/scripts/eval_reference.py score <aggregate-result.json> --output reference.json
```

- `judge-recall` : part des runs des cas `blocker-` dont le verdict est `REJECT`.
- `false-accept` : part des runs des cas qui portent `no-false-accept` (les cas `blocker-` et le cas
  `faux-accept-` de la PR 14) dont le verdict est `ACCEPT`. Ces cas rejouent une PR qui portait un
  défaut de la gravité d'un `BLOCKER`, donc chaque `ACCEPT` y est un faux. Les cas de la PR 13 au tour 2
  et de la PR 23 en sont hors, pour la raison donnée plus haut.
- `false-reject` : part des runs des cas `accept-` dont le verdict est `REJECT`. Sans elle, un juge qui
  rejette tout aurait un `judge-recall` parfait. `factory_slo.py` ne lit que les deux premières clés :
  aucun objectif de service ne porte sur celle-ci.

Ces trois clés du haut ne comptent que les cas réels : un run d'un cas `trap-` n'entre jamais dans les trois
mesures, bien qu'il porte les mêmes notations. Quand des cas piégés ont tourné, le JSON ajoute des clés
imbriquées, que `factory_slo.py` ne lit pas :

```json
{"judge-recall": 0.9, "false-accept": 0.05, "false-reject": 0.1,
 "real": {"judge-recall": 0.9, "false-accept": 0.05, "false-reject": 0.1},
 "trapped": {"judge-recall": 0.8, "false-accept": 0.2},
 "per-class": {"weakened-test": {"judge-recall": 0.7, "false-accept": 0.3},
               "out-of-scope": {"judge-recall": 0.9, "false-accept": 0.1},
               "unmet-criterion": {"judge-recall": 0.8, "false-accept": 0.2}}}
```

- `real` : les trois clés du haut, répétées, pour qu'on lise les cas réels et les cas piégés côte à côte ;
- `trapped` : la part des runs des cas `trap-` en `REJECT` (`judge-recall`), et la part de ces runs en
  `ACCEPT` (`false-accept`) ;
- `per-class` : les deux mêmes parts pour chaque classe qui a tourné ; une classe sans run manque.

Sans aucun run d'un cas piégé, aucune clé imbriquée n'est écrite : le JSON est celui d'avant. La ligne que
`score` imprime sur la sortie d'erreur ajoute une ligne pour les pièges et une par classe.

Le JSON et la ligne que `score` imprime sur la sortie d'erreur ne disent pas la même chose : chaque clé du
JSON porte une part (un nombre entre 0 et 1), et la ligne porte un compte (runs en défaut sur runs notés).
Avec trois cas `accept-` d'un run chacun dont un est jugé `REJECT`, la clé `false-reject` vaut `0.333` et
la ligne imprimée porte le compte `1/3`. `factory_slo.py` lit la part, jamais la ligne.

Un run en erreur (appel qui échoue, délai dépassé) reste hors des trois parts et se compte sur la sortie
d'erreur : ce n'est ni un `REJECT` ni un `ACCEPT`. Une mesure sans aucun run derrière elle manque du
fichier, et l'objectif la lit « sans objet », jamais 0 ni 100 % ; `false-reject` est « sans objet » tant
qu'aucun cas `accept-` n'a tourné. Un run sans ligne `VERDICT:` compte
comme un défaut du juge dans `judge-recall` (il n'a pas rejeté), et pas comme un faux accept ni un faux
reject.

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

`--runs <n>` et `--case <glob>` passent tels quels. Chaque cas demande trois runs par défaut : avec les
neuf cas piégés, le jeu compte vingt cas et soixante runs. `--case 'trap-*'` ne lance que les cas piégés,
`--case 'trap-weakened-test-*'` une seule classe. Le lancement reste à la main, sous son plafond.

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

La CI épingle `claude` à la version 2.1.304 dans son job `validate` (`.github/workflows/tests.yml`, chemin
protégé : il n'est pas changé ici). `claude plugin eval` existe dans la version 2.1.304. Relevé le
2026-11-17 : le paquet `@anthropic-ai/claude-code@2.1.304` installé dans un dossier jetable, son binaire
lancé avec un `HOME` jetable, `claude --version` répond `2.1.304 (Claude Code)`, et `claude plugin --help` liste la
sous-commande `eval`. `claude plugin eval --help` y montre les options que `eval_reference.py run` passe
(`--scaffold`, `--ablation`, `--no-publish`, `--max-cost-usd`, `--output-dir`, `--runs`, `--case`). Aucun
cas n'y a tourné, et aucun appel à un modèle n'a été fait : seule l'aide a été lue. Le jeu ne tourne pas en
CI : il se lance sur un poste dont `claude plugin eval` existe, et la version qui a relevé le format des
cas est la 2.1.325.

## Limites des cas piégés

- Le défaut est planté dans le diff, pas dans le dépôt : la tête que dit l'invite (le `sha` d'origine) n'est
  pas celle que le diff décrit, et le juge, qui ne lance aucune commande, ne peut pas le vérifier.
- Le corps de la PR, le ticket et le tableau de `forge:qc-gate` sont ceux du cas d'origine, sauf les
  deux lignes que le script recalcule. Un cas qui garde le test d'un critère retiré (`trap-unmet-criterion-pr228-fail-open`)
  montre donc un tableau où la CI est verte : le juge doit relire le test contre le code, ce qu'un juge qui
  se fie à la CI ne fait pas. C'est voulu, et c'est un défaut du cas aussi : une vraie PR rouge aurait un
  tableau rouge.
- Neuf cas à trois runs (vingt-sept runs de cas piégés, neuf par classe) disent où le juge se trompe, pas de
  combien. La taille et la discrétion des défauts plantés sont un choix de celui qui a écrit les
  spécifications : un juge qui les trouve tous n'est pas pour autant sûr devant un défaut plus discret. Une
  classe de plus, ou un cas de plus par classe, est une partie suivante du ticket #154.
- Aucun cas piégé n'a tourné devant un modèle : comme le reste du jeu, ils n'ont été éprouvés que sur la
  forme (fichiers, notations, comptes), jamais sur un verdict réel.

## Limites des cas

- Les cas `faux-accept-` de la PR 13 (tour 2) et de la PR 23 sont faibles par construction : le défaut
  que le juge de l'époque a laissé passer n'était qu'un `MINOR` dans le verdict rendu ensuite. Le juge
  peut bien juger et ne pas le nommer. Ils sont hors de `false-accept` (choix de l'orchestrateur du
  ticket) pour qu'un `ACCEPT` juste ne fasse pas échouer l'objectif `false-accept <= 0 %`.
- Les corps de PR et de ticket figés sont ceux d'aujourd'hui (les commentaires du ticket sont ceux
  d'avant le verdict), les corps de PR coupés avant `Rapport d'agent`, pas ceux du moment de la revue. Les tableaux de `forge:qc-gate` sont reconstruits (état des checks de la tête, périmètre) :
  les sondes que le jeu ne rejoue pas y sont marquées `NOT RUN`.
- Trois cas `accept-` font neuf runs par défaut (trois par cas) : `false-reject` est une alarme contre un
  juge qui rejette tout, pas une mesure fine. Un cas de plus à chaque faux `REJECT` constaté.
- Le diff du cas de la PR 238 part de l'ancêtre commun de la PR (`8a6a4ce`), les quatre fichiers que
  GitHub montre, et non de la pointe de `main` à la revue.
- Chaque cas cite un numéro de PR de ce dépôt dans ses données : il les porte avec lui parce qu'un jeu de
  référence est une mémoire de ce dépôt. Aucune invite générique du plugin n'en cite.
