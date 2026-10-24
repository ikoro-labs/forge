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
2. Ouvrir l'entrée correspondante en tête de `CHANGELOG.md`.
3. Vérifier :

   ```sh
   uv run --no-project --quiet python -m unittest discover -s tests
   claude plugin validate .
   claude plugin validate plugins/forge
   ```

4. Fusionner sur `main`, puis poser et pousser le tag annoté `forge--v<X.Y.Z>`, deux tirets : c'est
   la forme que Claude Code lit. Les anciens tags `forge-v<X.Y.Z>`, antérieurs à ce dépôt, ne changent pas.
5. Une fois le tag poussé, deux PR : l'une monte l'épingle de ce dépôt (`.claude/settings.json`),
   l'autre le tag cité par l'installation, dans `README.md` et `docs/installation.md`.

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
  agents/                         coder, qc-gate, qc-conf, staff-engineer, product-owner
  skills/                         qc, feature-build, feature-*, codebase-design, domain-modeling,
                                  improve-codebase-architecture, tdd, audit-jetons
  hooks/                          hooks.json, les gardes, les sorties raccourcies, la passation
                                  drainée et l'avis des autres sessions du dépôt, en Python de la
                                  bibliothèque standard, sous Linux comme sous Windows
  scripts/parse_output.py         lecture du RESULT du coder et du verdict du juge
  scripts/token_audit.py          les jetons de chaque rôle, lus dans les journaux de Claude Code
  templates/                      usine.md, adr.md, features/
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
