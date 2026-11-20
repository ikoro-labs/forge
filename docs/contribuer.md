# Contribuer et publier

Pour qui modifie le plugin lui-même. Les règles que suivent les agents de ce dépôt sont dans
[`CLAUDE.md`](../CLAUDE.md) et [`.claude/rules/`](../.claude/rules/).

## Qui écrit, et comment publier

- **Seuls les contributeurs écrivent** : les comptes qui ont le droit d'écriture sur ce dépôt. Un
  projet consommateur n'y écrit pas ; un besoin né dans un projet devient un ticket ou une PR d'un
  contributeur.
- **L'usine développe l'usine** : ce dépôt installe `forge` comme un projet consommateur, épinglé
  dans son `.claude/settings.json`, configuré par son `docs/agents/usine.md`. La session qui tourne
  charge la version épinglée depuis le cache ; ce qu'elle modifie, c'est `plugins/forge/`, qui
  n'agit sur elle qu'une fois publié et l'épingle montée par une PR. Les règles du dépôt sont dans
  `CLAUDE.md` et `.claude/rules/`.
- **La session forge publie** : elle tient ce `CHANGELOG.md` et pose les tags.
- Le contenu reste générique : il cite les clés de `docs/agents/usine.md`, jamais un numéro d'ADR,
  un nom de personne ou un chemin propre à un projet.

Publier une version :

1. Changer `version` dans `plugins/forge/.claude-plugin/plugin.json`, et nulle part ailleurs
   (jamais dans `marketplace.json`).
2. Ouvrir l'entrée correspondante en tête de `CHANGELOG.md`. Si ce dépôt déclare la clé `slo`, y
   ajouter la section « Objectifs de service » que rend
   `uv run --no-project --quiet python plugins/forge/scripts/factory_slo.py changelog . --depuis <date de la version précédente>`
   (voir `docs/indicateurs-de-service.md`). Le rapport est aussi réécrit dans l'issue de suivi par
   `/forge:slo --publier`.
3. Essayer l'usine de bout en bout, avant de vérifier. Depuis la racine du dépôt, la branche de la version
   extraite :

   ```sh
   uv run --no-project --quiet python plugins/forge/scripts/e2e_trial.py
   ```

   Le script lit lui-même ses trois clés, `e2e-repo`, `e2e-command` et `e2e-budget-usd` : la clé
   `e2e-command` est la ligne `claude` que le script lance dans le clone du dépôt d'essai, avec `{plugin}`
   (le plugin de la branche) et `{budget}` (le plafond de la clé `e2e-budget-usd`) ; on ne la lance pas à
   la main. Le script prépare un projet jetable sur le dépôt d'essai, lance cette ligne sous le lanceur
   borné, lit la PR que l'essai a laissée, puis nettoie ce qu'il a créé. La PR de version
   (`chore(release)`) recopie, dans ses **Preuves**, les lignes `RESULTAT`, `TETE` (le commit essayé, avec
   « arbre modifié » quand la branche porte des changements non commités) et, sur un `FAIL`, `ETAPE` et
   `RAISON`. Un `FAIL` bloque la version : la PR de version ne passe pas tant que l'étape qui a manqué
   n'est pas corrigée. Pour une clé absente, le script écrit `SANS-OBJET (clé `<nom>` absente)` : l'étape
   est « sans objet (clé `e2e-command` absente) », ou le nom de la clé qui manque, la PR de version le dit,
   et ne l'écrit jamais comme un `PASS`. La création du dépôt d'essai, de ses étiquettes et de son jeton
   est un geste humain. L'essai coûte de vrais appels de modèle : il ne se lance qu'à un geste de version,
   celui de l'humain ou celui de `/forge:release` (voir plus bas), jamais depuis un test ni depuis un autre
   passage de l'usine.
4. Vérifier :

   ```sh
   uv run --no-project --quiet --with pytest==9.2.0 python -m pytest tests
   claude plugin validate .
   claude plugin validate plugins/forge
   ```

5. Fusionner sur `main`, puis poser et pousser le tag annoté `forge--v<X.Y.Z>`, deux tirets : c'est
   la forme que Claude Code lit. Les anciens tags `forge-v<X.Y.Z>`, antérieurs à ce dépôt, ne changent pas.
6. Une fois le tag poussé, deux PR : l'une monte l'épingle de ce dépôt (`.claude/settings.json`),
   l'autre le tag cité par l'installation, dans `README.md` et `docs/installation.md`.

## Le poste qui contribue

Ce qui est propre au poste de ce dépôt (l'identité git, le compte `gh`) vit ici, jamais sous
`plugins/forge/` : un test (`tests/test_correspondance_memoire.py`) le garde. Le reste de la mémoire
du poste est rangé ligne à ligne dans [`correspondance-memoire.md`](correspondance-memoire.md).

- **L'identité git.** Les commits de ce poste portent `ikoro-labs` et l'adresse
  `336514991+ikoro-labs@users.noreply.github.com`, donnée à chaque commande :
  `git -c user.name=ikoro-labs -c user.email=336514991+ikoro-labs@users.noreply.github.com commit ...`.
  Elle n'est jamais écrite dans la configuration git, que tous les worktrees partagent (`guard_coder`
  refuse `git config` en écriture). Un commit à une autre adresse a vu son push refusé sur ce poste.
- **La fusion.** Une PR se fusionne par un commit de fusion, jamais par un squash ni un rebase
  (`.claude/rules/git.md`, clé `merge-method`).
- **Le compte `gh`.** `gh` agit sous le compte du jeton du poste : `gh api user --jq .login` le dit
  (`ikoro-labs`, lu le 2026-11-17). `ikoro-labs` est un compte utilisateur, pas une organisation. Avant
  `gh repo create <propriétaire>/<nom>`, relire ce login et nommer le propriétaire voulu en entier : un
  dépôt créé sous un autre propriétaire se corrige avant tout push.

## La publication par l'agent

Quand le projet déclare la clé `release-trigger` (`<N fusions> | <délai max>`), l'agent publie lui-même une
version : `/forge:release`, lancé depuis la session principale, suit les étapes ci-dessus. Une version est
due quand N fusions attendent un tag de la clé `release-tag`, ou quand la plus ancienne attend depuis plus
que le délai ; la première des deux bornes atteinte la déclenche. Sans la clé, la publication reste un geste
de l'humain, et l'agent ne publie rien (`sans objet`).

L'agent publie seul si, et seulement si, ces quatre conditions tiennent, lues par
`plugins/forge/scripts/release.py check` :

- tous les SLO sont `tenu` dans `slo-status.json`, calculé il y a moins d'une heure ;
- aucune action de `budget-action` n'est active (`alert` comprise) ;
- l'essai de bout en bout passe sur la tête de la base : `RESULTAT: PASS` sur exactement ce commit, arbre
  non modifié ;
- aucun ticket `sev1` n'est ouvert, sur un dépôt qui porte l'étiquette (l'agent ne la crée pas).

Une condition qui manque, parce qu'elle n'est pas tenue ou parce que le projet ne permet pas de la lire (une
clé absente, un état périmé, une étiquette qui n'existe pas), vaut condition non remplie, jamais « tenue ».
Sinon, l'agent ouvre quand même la PR de version, pose `needs-your-attention` avec la condition qui manque,
et la revue, la fusion et le tag reviennent à l'humain. Il ne lance l'essai, qui coûte de vrais appels de
modèle, que lorsque les trois autres conditions tiennent.

Quand tout tient, la PR de version passe par `/forge:qc`, puis l'agent pose le tag annoté sur le commit de
fusion, au motif de la clé `release-tag`, et le pousse. Un tag ne se déplace ni ne se supprime. L'agent ne
monte pas l'épingle de ce dépôt, et ne pose aucune règle de tags côté serveur : ce sont des PR et des gestes
de l'humain.

Éprouvé sur des réponses `gh` fictives, des dépôts git jetables et un faux essai, sous Linux. Pas encore
essayé sur un vrai poste : ni le skill dans une vraie session, ni un tag posé par l'agent.

## Le dépôt

Ce dépôt est la marketplace `ikoro-labs`. Il contient le plugin `forge` (`forge@ikoro-labs`) et
référence les autres plugins d'ikoro-labs, publiés depuis leur propre dépôt et épinglés sur leur tag
`<plugin>--v<X.Y.Z>` (`ai-delivery-gates@ikoro-labs`, tag `ai-delivery-gates--v<X.Y.Z>`).
Les noms de forge sont préfixés : `/forge:qc` pour un skill, `forge:coder` pour un agent.

```text
.claude-plugin/marketplace.json   la marketplace ikoro-labs : forge en source relative, les autres
                                  plugins en source github épinglée
plugins/forge/                    le plugin
  .claude-plugin/plugin.json      son manifeste, seul endroit qui porte sa version
  .claude-plugin/icon.png         son icône, l'export de docs/logo.svg
  agents/                         coder, qc-gate, qc-conf, staff-engineer, product-owner,
                                  review-judge, review-recheck
  skills/                         qc, feature-build, feature-*, codebase-design, domain-modeling,
                                  improve-codebase-architecture, tdd, audit-jetons, slo, incident, release
  hooks/                          hooks.json, les gardes, les sorties raccourcies, la passation
                                  drainée et l'avis des autres sessions du dépôt, en Python de la
                                  bibliothèque standard, sous Linux comme sous Windows
  scripts/parse_output.py         lecture du RESULT du coder et du verdict du juge
  scripts/token_audit.py          les jetons de chaque rôle, lus dans les journaux de Claude Code
  scripts/ticket_budget.py        la somme des jetons d'agents par ticket, contre la clé `ticket-budget`
  scripts/factory_slo.py          les indicateurs de service de l'usine, calculés sans modèle
  scripts/incident.py             la lecture d'une revue d'incident et le refus de celle sans correctif
  scripts/completion.py           le tableau de complétion des features, compté comme le budget
  scripts/e2e_trial.py            l'essai de bout en bout de l'usine sur un dépôt d'essai, avant une version
  scripts/release.py              le déclencheur d'une version et les quatre conditions de sa publication par l'agent
  scripts/question_delay.py       les questions restées sans réponse au-delà de la clé `question-default-delay`, et la suite d'un verdict
  socle.md                        le socle commun des critères de revue, règles F-n
  templates/                      usine.md, ticket.md, pr.md, verdict.md, adr.md, features/
tests/                            tests des hooks, du parseur et du contenu
README.md                         la page d'accueil : ce que fait forge, l'installer, où lire la suite
docs/*.md                         le détail : installation, sessions, modèles et jetons, contribuer
CHANGELOG.md                      une entrée par version publiée
CLAUDE.md, .claude/               l'usine de ce dépôt : son épingle, ses règles
docs/agents/usine.md              sa configuration
docs/architecture.excalidraw      le schéma du README, sa source éditable
docs/architecture.svg             son export, que le README affiche
docs/logo.svg                     le logo, sa source
docs/banniere.svg                 la bannière du README et de l'aperçu GitHub, sa source
.github/                          la CI (tests sous Linux et Windows, validation) et le modèle de PR
```

## Le schéma, le logo et la bannière

Le schéma du `README.md` a sa source dans `docs/architecture.excalidraw`, à ouvrir dans Excalidraw ;
`docs/architecture.svg` en est l'export, refait à chaque changement de la source.

Le logo a sa source dans `docs/logo.svg`. Son export en PNG de 1024 px,
`plugins/forge/.claude-plugin/icon.png`, est l'icône du plugin, et se refait à chaque changement
de la source :

```sh
uv run --no-project --quiet --with cairosvg python -c "import cairosvg; cairosvg.svg2png(url='docs/logo.svg', write_to='plugins/forge/.claude-plugin/icon.png', output_width=1024, output_height=1024)"
```

La bannière, `docs/banniere.png` (1280 × 640), s'exporte de même depuis `docs/banniere.svg`, avec
`output_width=1280, output_height=640`. Son texte demande la police JetBrains Mono installée sur le
poste. C'est aussi l'aperçu social du dépôt, à téléverser à la main dans **Settings → General →
Social preview**.

L'export demande la bibliothèque système cairo, que cairosvg charge à l'import : `libcairo2` sous
Linux ; sous Windows, une installation qui la fournit (GTK, MSYS2). Sans elle, `import cairosvg`
lève `OSError: no library called "cairo-2" was found`. La commande n'a été essayée que sous Linux.
