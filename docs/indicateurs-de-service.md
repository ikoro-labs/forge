# Les indicateurs de service de l'usine

Une usine qui fusionne seule doit dire si elle s'améliore. `factory_slo.py` calcule ses indicateurs
de service (SLI) sans modèle, depuis GitHub, git et les journaux de Claude Code. Ses objectifs (SLO)
et leur budget d'erreur se déclarent dans `usine.md` et se calculent par `status` (série
ikoro-labs/forge#55).

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
`sev1`, `sev2` ou `sev3` (voir `docs/gravite-et-sla.md`), pour `restore-time` ; à défaut sur
`gravite:<classe>` (ou `severity:<classe>`), et sans aucune, « sans gravité ».

## Clé `release-tag`

Le motif des tags de version du projet, `{version}` tenant pour la version (`<plugin>--v{version}`).
Une ligne par motif. Sans la clé, `release-lag` est « sans objet (clé `release-tag` absente) » ; aucun
motif n'est supposé. Elle est documentée dans `plugins/forge/templates/usine.md`.

## Les objectifs (SLO) et leur budget d'erreur

Un indicateur sans objectif ne dit pas s'il faut agir. La clé `slo` de `docs/agents/usine.md` déclare
ce que le projet attend de son usine, une ligne par objectif :

```text
- `slo` : `accept-round-1 | >= 80 % | 30`
- `slo` : `lead-time p90 | <= 24 h | 30`
```

`<sli> | <comparateur> <cible> | <fenêtre en jours>`. Une durée (`lead-time`, `release-lag`,
`restore-time`) prend `p90` ou `mediane` après son nom ; les autres SLI n'en prennent pas. L'unité de la
cible est celle du SLI : `%` pour un ratio, `h` pour une durée, un nombre nu pour `tokens-per-merge`.
Un `>=` ne se déclare que sur un ratio : une durée ou un compte n'a pas de borne haute, donc pas de
budget. Un SLI dont la clé de configuration manque (`release-tag`, `required-contexts`) reste « sans
objet », et l'objectif avec lui.

```sh
uv run --no-project --quiet python plugins/forge/scripts/factory_slo.py status <projet> [--json] [--reference <fichier>]
```

Pour chaque objectif, `status` calcule la valeur sur la fenêtre glissante (les `<jours>` derniers jours,
jusqu'à maintenant), puis le budget d'erreur :

- le **budget** est l'écart que la cible permet. Pour `>= 80 %`, 20 points (de 100 % à la cible) ; pour
  `<= 24 h`, 24 h (de zéro à la cible) ;
- la **part consommée** est ce que la valeur en a déjà usé : à 90 % pour `>= 80 %`, 10 points sur 20, soit
  50 % ; à 12 h pour `<= 24 h`, 50 % aussi ;
- l'**état** : `tenu` jusqu'à 75 % consommés compris, `menacé` au-delà, `épuisé` à 100 % et plus. À
  100 % pile la cible est juste tenue, mais il ne reste aucune marge : l'état est `épuisé`. Une cible sans
  marge (`>= 100 %`) est `tenu` à la perfection, `épuisé` sinon.

Une fenêtre sans données (aucune PR, clé absente) rend l'objectif « sans objet » avec sa raison :
jamais `tenu`, jamais `épuisé`. C'est à celui qui lira cet état (les gardes de #59) de décider ce
qu'il en fait.

`status` écrit le résultat dans `<git-common-dir>/forge/slo-status.json`, le dossier commun à tous les
worktrees du dépôt : la date du calcul (`calcule_le`), la branche de base et sa tête (`tete_base`), puis
un élément par objectif (`valeur`, `budget`, `consomme`, `reste`, `etat` ou `raison`). Les gardes le lisent sans
réseau. Une ligne de `slo` mal formée ou qui nomme un SLI inconnu fait échouer la commande (code 1) avec
chaque ligne fautive, et n'écrit rien : jamais un objectif ignoré en silence. Sans la clé `slo`, la
sortie est « sans objet (clé `slo` absente) », sans fichier.

Un ratio ne dépasse pas 100 % : `>= 120 %` (ou `>= 800 %`, faute de frappe pour 80,0) est une ligne
mal formée, qui fait échouer la commande, au lieu d'un objectif hors d'atteinte rendu `tenu`.

## Les actions du budget épuisé

Un budget épuisé doit changer ce que l'usine fait. La clé `budget-action` de `docs/agents/usine.md`
déclare, une ligne par action, `<sli> | <action>`, où `<sli>` nomme un objectif de la clé `slo`
(`lead-time p90` ou `lead-time`) :

```text
- `budget-action` : `accept-round-1 | human-merge`
- `budget-action` : `accept-round-1 | feature-freeze`
- `budget-action` : `lead-time p90 | alert`
```

- `human-merge` : `forge:qc` ne fusionne plus sur ACCEPT. Il pose `needs-your-attention` avec
  l'objectif épuisé dans `Attention`, et l'humain fusionne. Le garde `guard_git` refuse aussi
  `gh pr merge` à tout agent, quel que soit son nom d'agent, tant que l'action est active.
- `feature-freeze` : `forge:feature-build` ne confie plus que les tickets `bug` et `escaped-defect` ;
  les autres attendent, `ready-for-agent`, et le compte rendu du passage le dit.
- `alert` : seulement l'étiquette `needs-your-attention` de l'issue de suivi (`/forge:slo --publier`).

Une action devient **active** quand son objectif est `épuisé` dans `slo-status.json`, et le reste tant
qu'il n'est pas revenu à `tenu` : un passage à `menacé` ne la fait pas cesser (hystérésis). Un objectif
`menacé`, `tenu` ou « sans objet » qui n'a pas été épuisé ne l'active pas. Le fichier d'état garde cette
mémoire d'un calcul à l'autre (clé `epuises`, réécrite aussi par `status`), parce que le garde ne lit que
lui. Une action reste donc active si l'objectif perd ses données (« sans objet ») après un épuisement. `forge:qc` et `forge:feature-build` recalculent l'état
au début de chaque passage :

```sh
uv run --no-project --quiet python plugins/forge/scripts/factory_slo.py budget <projet> [--json] [--reference <fichier>]
```

La commande lance `status` (elle réécrit donc le fichier d'état), puis rend une ligne par action :
`ACTIVE` ou `inactive`, avec la raison. **L'autonomie revient d'elle-même** : quand un objectif repasse à
`tenu`, l'action cesse au calcul suivant, et la ligne ajoute « autonomie rendue » une seule fois : le
fichier d'état précédent la portait active, et plus le nouveau. Tant que l'objectif est `menacé` après un
épuisement, la ligne reste `ACTIVE`, avec la raison « pas encore revenu à `tenu` ».

Le garde est **fermé par défaut**. Quand la clé porte une ligne `human-merge` et que le fichier d'état
manque, est illisible (JSON invalide, date sans fuseau, objectifs absents) ou date de plus de 24 h
(`calcule_le`), `guard_git` refuse `gh pr merge` et donne dans son message la commande à lancer
(`factory_slo.py status <projet>`). Il refuse de même une ligne de la clé mal formée ou une action
inconnue, et un `human-merge` sur un objectif que la clé `slo` ne déclare pas : une fusion ne passe
jamais sur un état qu'on ne sait pas lire. Les lignes `feature-freeze` et `alert` seules ne
refusent aucune fusion, état présent ou non. Sans la clé, tout est « sans objet (clé `budget-action`
absente) », sans action supposée. Le garde ne vaut que pour une commande d'agent : l'humain fusionne
depuis son terminal ou GitHub.

Éprouvé dans les tests, sous Linux, sur un faux `gh` et des dépôts git jetables ; le garde n'a pas
encore refusé une vraie fusion dans une session de Claude Code. Les valeurs et les actions de ce
dépôt viennent dans un ticket suivant (#76).

## Le rapport des SLO

Une mesure que personne ne lit ne change rien. `factory_slo.py report` rend, pour chaque objectif, sa
valeur, son budget restant, son état et sa tendance ; le skill `/forge:slo` le lance et le commente.

```sh
uv run --no-project --quiet python plugins/forge/scripts/factory_slo.py report <projet> [--json] [--reference <fichier>] [--publier]
```

- **La tendance** compare la part du budget consommée à celle de la fenêtre précédente, de même
  durée (les `<jours>` qui précèdent la fenêtre courante) : `amélioration`, `dégradation`, `stable`,
  ou `sans point de comparaison` quand la fenêtre précédente n'a pas de données. Le jeu de référence
  (`judge-recall`, `false-accept`) n'a pas d'historique : sa tendance est toujours sans point de
  comparaison.
- **Sans `--publier`**, `report` ne modifie rien : ni GitHub, ni le fichier d'état de `status`.
- **Avec `--publier`**, le rapport est réécrit dans l'unique commentaire du ticket de suivi que
  désigne la clé `slo-issue` (un numéro). Le script retrouve son commentaire par un marqueur caché
  et le réécrit, il n'en empile pas. Il l'épingle à sa création (mutation GraphQL `pinIssueComment` ;
  si `gh` la refuse, par exemple faute de droit ou parce que le ticket porte déjà trois commentaires
  épinglés, la publication le dit et continue, et l'épingle se pose à la main). Il ne le réépingle pas
  à chaque réécriture. Cette épingle n'a été essayée que contre des faux `gh` : aucune exécution sur un vrai
  dépôt ne la confirme. Sans la clé, la publication est « sans objet (clé `slo-issue` absente) ».
- **L'étiquette `needs-your-attention`** est posée sur ce ticket quand un objectif est `menacé` ou
  `épuisé`, et un commentaire en donne la raison (une fois par changement de l'ensemble des objectifs
  en cause). Elle est retirée, avec un commentaire qui dit pourquoi, seulement quand **chaque** objectif
  est `tenu` et qu'un rapport précédent l'a posée (le marqueur caché `forge-slo-pose` le mémorise) :
  une étiquette qu'un humain avait déjà posée n'est jamais retirée, même si un objectif devient `menacé`
  ensuite. Un objectif « sans objet » n'est ni `tenu` ni épuisé : il ne pose pas l'étiquette, et il la
  retient. Si l'usine s'arrête et qu'un objectif `menacé` devient « sans objet » faute de données,
  l'étiquette reste jusqu'à ce que tous les objectifs soient `tenu`.

### La section du CHANGELOG

```sh
uv run --no-project --quiet python plugins/forge/scripts/factory_slo.py changelog <projet> --depuis <date de la version précédente> [--le <date de cette version>]
```

Elle imprime la section « Objectifs de service » de l'entrée d'une version : l'état de chaque objectif
à la date de la version (`--le`, maintenant par défaut) et les `escaped-defect` ouverts depuis la
précédente. La PR `chore(release)` la colle sous l'entrée qu'elle ouvre (`docs/contribuer.md`).

## Éprouvé, et pas encore

Le script est éprouvé dans les tests, sur des réponses `gh` fictives et des dépôts git jetables, sous
Linux. Il n'a pas encore tourné contre l'API réelle de GitHub : les noms de champs de
`gh pr list --json` (dont `closingIssuesReferences` et `comments`) et la forme des événements
(`gh api .../issues/<n>/events`) sont ceux de la documentation. `gh` plafonne la liste à 1000 PR et
1000 tickets ; une fenêtre qui en demande plus est tronquée sans avertissement. Pour `report
--publier`, les appels d'écriture (`gh api` sur les commentaires, `gh issue edit`, `gh issue comment`)
sont ceux de la documentation de `gh`, essayés seulement contre un faux `gh` : le rapport n'a jamais
été publié sur un vrai ticket.
