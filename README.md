# forge

La partie générique de l'usine agentique d'ikoro-labs, en plugin Claude Code privé : le coder, la
revue en deux temps, les décideurs délégués, la chaîne des features de l'idée à la livraison, et
les hooks qui gardent git, les rôles et la pause. Les projets (Projet A, Projet B) le consomment à
une version épinglée et gardent dans leur dépôt tout ce qui leur est propre. La décision est
l'ADR-0129 de Projet B.

Ce dépôt est une marketplace (`ikoro-labs`) qui sert un seul plugin (`forge`) : `forge@ikoro-labs`.
Ses noms sont préfixés : `/forge:qc` pour un skill, `forge:coder` pour un agent.

```text
.claude-plugin/marketplace.json   la marketplace ikoro-labs, un plugin à source relative
plugins/forge/                    le plugin
  .claude-plugin/plugin.json      son manifeste, seul endroit qui porte sa version
  agents/                         coder, qc-gate, qc-conf, staff-engineer, product-owner
  skills/                         qc, feature-build, feature-*, codebase-design, domain-modeling,
                                  improve-codebase-architecture
  hooks/                          hooks.json et les gardes, en Python de la bibliothèque standard
  scripts/parse_output.py         lecture du RESULT du coder et du verdict du juge
  templates/                      usine.md, adr.md, features/
tests/                            tests des hooks, du parseur et du contenu
CHANGELOG.md                      une entrée par version publiée
```

Ce qui est entré dans chaque version, et ce qui en est resté dehors avec sa raison : `CHANGELOG.md`.

## Prérequis sur le poste

- Claude Code.
- Un accès git au dépôt privé `ikoro-labs/forge` : une clé SSH, ou `gh auth login` pour HTTPS.
  Claude Code lit une marketplace privée avec les identifiants git du poste.
- [uv](https://docs.astral.sh/uv/) : chaque hook se lance par `uv run --no-project --quiet python`.
  Sans uv, `guard_coder` et `guard_readonly` refusent chaque appel qu'ils filtrent (leur échec
  vaut refus), et les autres gardes ne s'appliquent pas.
- [gh](https://cli.github.com/), authentifié : la revue, la chaîne des features et `guard_git`
  lisent et écrivent sur GitHub par lui.

## Installer dans un projet

1. **Épingler** la marketplace et activer le plugin dans le `.claude/settings.json` du projet, par
   une PR :

   ```json
   {
     "extraKnownMarketplaces": {
       "ikoro-labs": {
         "source": { "source": "github", "repo": "ikoro-labs/forge", "ref": "forge--v1.0.0" }
       }
     },
     "enabledPlugins": {
       "forge@ikoro-labs": true
     }
   }
   ```

   Le `ref` est un tag de ce dépôt. Changer de version est une PR du projet qui bouge ce `ref`,
   relue comme une montée de dépendance.

2. **Approuver le dossier** à la première session dans le projet : `extraKnownMarketplaces` n'est
   honoré qu'une fois la confiance du dossier accordée. Une session cloud l'ignore.

3. **Installer**, une fois par poste et par projet : `enabledPlugins` active le plugin sans
   l'installer.

   ```sh
   claude plugin install forge@ikoro-labs --scope project
   ```

4. **Configurer** : copier `plugins/forge/templates/usine.md` vers `docs/agents/usine.md` dans le
   projet, puis, pour chaque clé, mettre la vraie valeur ou supprimer la ligne (voir plus bas).

5. **Vérifier** : `claude plugin list` montre `forge@ikoro-labs` à la version du `ref`, et `/forge:`
   dans une session liste les skills.

## Monter de version

1. Une PR du projet bouge le `ref` vers le nouveau tag, après lecture de son entrée au
   `CHANGELOG.md`.
2. Une fois fusionnée, sur chaque poste : `claude plugin update forge@ikoro-labs`.

**Jamais pendant un `/forge:feature-build` actif.** Une session garde les versions qu'elle a
chargées, mais la suivante charge la nouvelle : un passage repris dans une nouvelle session
changerait d'usine au milieu d'une feature. La mise à jour automatique de la marketplace reste
coupée.

Un poste qui n'a pas lancé `claude plugin update` garde l'ancienne version, et rien ne l'en avertit
en dehors de `/plugin` : après chaque montée, comparer `claude plugin list` au `ref` du projet.

## Configurer : `docs/agents/usine.md`

Le seul fichier où un projet décrit son usine au plugin : qui accepte, la matrice de décision,
l'arbitre du métier, les commandes d'installation et de rejeu de la CI, les checks obligatoires, la
grille de revue, les chemins protégés, les tolérances des hooks. Le gabarit,
`plugins/forge/templates/usine.md`, documente chaque clé.

Une clé absente ne prend jamais de valeur par défaut : l'étape qui la lit se rend « sans objet (clé
`<nom>` absente) », jamais `PASS`. La revue d'un projet vaut donc ce que sa configuration déclare :
sans ses commandes de porte ni sa grille, `/forge:qc` rend des sondes « sans objet », plus faibles
qu'une revue configurée, et une clé qui pointe un chemin disparu donne un `NOT RUN` à chaque PR
jusqu'à sa correction.

## Compléter ou remplacer, sans éditer le plugin

- **Un complément** est un fichier du projet : ses skills de domaine, son arbitre du métier, ses
  propres hooks restent dans son `.claude/` et coexistent avec le plugin, dont les noms préfixés ne
  les heurtent pas. Ses hooks de `.claude/settings.json` tournent à côté de ceux du plugin.
- **Un remplacement** est un skill ou un agent du projet sous un autre nom, que la configuration
  désigne.
- **Le cache du plugin ne s'édite jamais** : il est réécrit à chaque version. Un écart qui vaut
  pour tous les projets se propose en PR à ce dépôt.

Ce qui reste forcément dans chaque projet, parce que ce n'est pas Claude Code qui le lit : les
gardes de CI, le modèle de PR, les hooks git. La CI ne charge aucun plugin.

## Contribuer et publier

- **Projet A publie** : la session Projet A tient ce `CHANGELOG.md` et pose les tags.
- **Projet B propose** ses changements par PR à ce dépôt ; elle ne pose pas de tag.
- Le contenu reste générique : il cite les clés de `docs/agents/usine.md`, jamais un numéro d'ADR,
  un nom de personne ou un chemin propre à un projet.

Publier une version :

1. Changer `version` dans `plugins/forge/.claude-plugin/plugin.json`, et nulle part ailleurs
   (jamais dans `marketplace.json`).
2. Ouvrir l'entrée correspondante en tête de `CHANGELOG.md`.
3. Vérifier :

   ```sh
   python3 -m unittest discover -s tests
   claude plugin validate .
   claude plugin validate plugins/forge
   ```

4. Fusionner sur `main`, puis poser et pousser le tag annoté `forge--v<X.Y.Z>`, deux tirets : c'est
   la forme que Claude Code lit. Les anciens tags `forge-v<X.Y.Z>` de Projet A ne changent pas.

## Gestes humains

Ce qu'aucun agent ne fait à la place d'un humain :

1. Créer le dépôt privé `ikoro-labs/forge` (fait) et donner à la session Projet A le droit d'y pousser
   et d'y poser les tags.
2. Sur chaque poste (bureau, PC personnel), et pour chaque contributeur : un accès git au dépôt privé (clé
   SSH, ou `gh auth login`) ; puis, dans chaque projet, approuver le dossier et lancer
   `claude plugin install forge@ikoro-labs --scope project`.
3. À chaque montée d'épingle : `claude plugin update forge@ikoro-labs` sur chaque poste.

## Limites connues

- **Dépendance à GitHub** : un poste neuf ou une nouvelle version ne s'installent pas si GitHub ou
  les identifiants git du poste font défaut.
- **Noms préfixés** : `forge:coder`, `/forge:qc`. Les commandes tapées, les tests et les mesures
  d'un projet qui lisent un nom d'agent doivent suivre à la migration.
- **Frontmatter des agents** : un agent de plugin ignore `hooks`, `permissionMode`, `mcpServers` et
  `initialPrompt`. Les gardes des agents sont donc des hooks globaux du plugin, filtrés sur
  `agent_type` (`forge:coder`, `forge:qc-gate`...) ; un filtre faux ne s'appliquerait à personne,
  en silence, d'où les tests de `tests/`.
- **Aucun `CLAUDE.md`** n'est chargé depuis un plugin : la constitution reste celle du projet.

### Points à confirmer sur un poste

Lus dans la documentation de Claude Code, pas encore éprouvés :

- deux projets d'un même poste qui épinglent la marketplace sur deux `ref` différents ;
- la priorité entre un skill de projet et le skill du plugin de même nom court (`qc` et
  `forge:qc`), pendant la transition où les deux existent ;
- le comportement de `guard_coder`, filtré sur `agent_type`, dans le worktree d'un agent ;
- le chargement d'une version déjà en cache quand la marketplace est injoignable au démarrage.

## Licence

Privé. Trois skills adaptent mattpocock/skills sous licence MIT :
`plugins/forge/THIRD_PARTY_NOTICES.md`.
