# forge

La partie générique de l'usine agentique d'ikoro-labs, en plugin Claude Code privé : le coder, la
revue en deux temps, les décideurs délégués, la chaîne des features de l'idée à la livraison, et
les hooks qui gardent git, les rôles et la pause, et la passation drainée d'une session à sa
limite de contexte. Les projets (Projet A, Projet B) le consomment à
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
  hooks/                          hooks.json, les gardes et la passation drainée, en Python de la
                                  bibliothèque standard (et handoff_relay.sh en bash)
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
     "enabledPlugins": {
       "forge@ikoro-labs": true
     },
     "extraKnownMarketplaces": {
       "ikoro-labs": {
         "source": {
           "source": "github",
           "repo": "ikoro-labs/forge",
           "ref": "forge--v1.1.0"
         }
       }
     }
   }
   ```

   Le `ref` est un tag de ce dépôt. Changer de version est une PR du projet qui bouge ce `ref`,
   relue comme une montée de dépendance.

2. **Approuver le dossier** à la première session dans le projet : `extraKnownMarketplaces` n'est
   honoré qu'une fois la confiance du dossier accordée. Une session cloud l'ignore.

3. **Installer**, une fois par poste et par projet : `enabledPlugins` active le plugin sans
   l'installer. Depuis la racine du projet, redéclarer d'abord son épingle, puis installer :

   ```sh
   claude plugin marketplace add ikoro-labs/forge@forge--v1.1.0 --scope project
   claude plugin install forge@ikoro-labs --scope project
   ```

   La première ligne remet la marketplace du poste sur le `ref` du projet : un poste ne connaît
   qu'une source par marketplace, celle du dernier projet qui l'a déclarée (voir **Limites
   connues**). Elle réécrit aussi le `.claude/settings.json` du projet dans sa propre forme
   (indentation de deux espaces, `extraKnownMarketplaces` en dernière clé), sans toucher aux autres
   clés : sous la forme de l'étape 1, `git diff` reste vide. S'il montre autre chose que de la mise
   en forme, l'épingle tapée n'est pas celle du projet.

4. **Configurer** : copier `plugins/forge/templates/usine.md` vers `docs/agents/usine.md` dans le
   projet, puis, pour chaque clé, mettre la vraie valeur ou supprimer la ligne (voir plus bas).

5. **Vérifier** : `claude plugin list --json` donne, pour l'entrée de `forge@ikoro-labs` dont le
   `projectPath` est ce projet, la version du `ref` ; `/forge:` dans une session liste les skills.
   Sans `--json`, la liste n'affiche qu'une entrée par plugin, celle du dernier projet installé,
   même quand on la lance depuis un autre.

## Monter de version

1. Une PR du projet bouge le `ref` vers le nouveau tag, après lecture de son entrée au
   `CHANGELOG.md`.
2. Une fois fusionnée, sur chaque poste, depuis la racine du projet :

   ```sh
   claude plugin marketplace add ikoro-labs/forge@<nouveau tag> --scope project
   claude plugin update forge@ikoro-labs --scope project
   ```

   `update` prend la source que le poste connaît, pas le `ref` du projet. Sans la première ligne,
   un projet épinglé sur une version passe à celle qu'un autre projet du poste a déclarée en
   dernier.

**Jamais pendant un `/forge:feature-build` actif.** Une session garde les versions qu'elle a
chargées, mais la suivante charge la nouvelle : un passage repris dans une nouvelle session
changerait d'usine au milieu d'une feature. La mise à jour automatique de la marketplace reste
coupée.

Un poste qui n'a pas lancé `claude plugin update` garde l'ancienne version, et rien ne l'en avertit
en dehors de `/plugin` : après chaque montée, comparer `claude plugin list --json` au `ref` du
projet.

## La passation drainée

Une session passe la main à une nouvelle session quand son contexte atteint le seuil
(ikoro-labs/forge#3). Fermer une session tue ses sous-agents : la passation est donc un arrêt qui
draine.

- **Le hook** `handoff_trigger.py` (`UserPromptSubmit`, `PostToolUse`) lit le contexte du fil
  principal dans la transcription. Au seuil, il dit à la session de ne plus rien lancer, de laisser
  finir ses agents puis d'écrire la passation et de lancer le relais. Au plafond dur (seuil plus
  35 k jetons, ou 45 minutes après le premier avis), il fait lister les agents encore vivants sous
  `sauvetage` et forcer le relais. Un sous-agent n'est jamais averti.
- **La passation** est un fichier `~/.claude/hooks/state/handoffs/<projet>/<date>-r<N>.md`, hors du
  cache du plugin, qui commence par un front matter de onze clés (`projet`, `feature`,
  `passage_depart`, `jetons_agents`, `en_vol`, `file_revue`, `sauvetage`, `successeur`,
  `hooks_version`, `seuil`, `contexte_passation`). `handoff_header.py` le valide ; son corps est le
  prompt de reprise. Le skill `handoff` de l'utilisateur (`~/.claude/skills/handoff/`) est suivi
  s'il existe.
- **Le relais** `handoff_relay.sh`, lancé par la session depuis le dossier du projet, refuse
  (code 5) tant qu'un agent de la session est vivant ou que `en_vol` n'est pas vide, et n'admet
  `--force` qu'avec `sauvetage` non vide. Il lance le successeur par `claude --bg`, écrit son
  identifiant et son seuil dans l'en-tête, puis arrête et supprime la session appelante. Le
  successeur vérifie d'abord qu'il est bien le successeur désigné
  (`handoff_header.py successor-ok`).
- **Le seuil** est `CLAUDE_SESSION_TOKEN_LIMIT`, 150 000 par défaut. Seul le relais le relève, à
  400 000 pour un successeur dont la passation porte une feature. Aucun `settings.json` ne doit le
  fixer.

| Variable | Défaut | Effet |
| --- | --- | --- |
| `CLAUDE_SESSION_TOKEN_LIMIT` | 150000 | seuil de drainage, posé par le relais seulement |
| `CLAUDE_HANDOFF_DRAIN_MINUTES` | 45 | minutes de drainage avant le plafond dur |
| `CLAUDE_HANDOFF_RELAY_MAX` | 5 | relais par projet et par jour (code 3 au-delà) |
| `CLAUDE_HANDOFF_CLOSE_DELAY` | 45 | secondes avant la fermeture de la session appelante, 0 la garde ouverte |
| `CLAUDE_HANDOFF_TERMINAL` | aucune | commande de terminal (`ghostty -e`, `gnome-terminal --`) où ouvrir `claude attach <id>` ; sans elle, aucune fenêtre |
| `CLAUDE_HANDOFF_CLOSE_DRY_RUN` | aucune | affiche le lancement et la fermeture sans rien lancer, compteur et passation intacts |

Le relais lit `/proc` et tourne sous bash : Linux seulement. La passation ne vaut que dans les
projets où le plugin est activé ; une copie de ces scripts dans `~/.claude/hooks` couvrait tous les
projets du poste. Tant que `~/.claude/settings.json` déclare encore une telle copie, le hook du
plugin se tait.

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
   SSH, ou `gh auth login`) ; puis, dans chaque projet, approuver le dossier et lancer les deux
   commandes de l'étape 3 d'**Installer dans un projet**.
3. À chaque montée d'épingle, sur chaque poste et dans chaque projet : les deux commandes de
   **Monter de version**.
4. Une fois `forge` 1.1.0 installé dans chaque projet du poste qui fait des passations : retirer de
   `~/.claude/settings.json` les entrées `UserPromptSubmit` et `PostToolUse` qui lancent la copie
   `~/.claude/hooks/handoff_trigger.py`, puis cette copie et ses deux voisins
   (`handoff_header.py`, `handoff_relay.sh`) ; garder `~/.claude/hooks/state/`, qui porte les
   passations et les compteurs. Remplacer la règle de permission qui autorise
   `bash ~/.claude/hooks/handoff_relay.sh` par la même règle sur le relais du plugin
   (`~/.claude/plugins/cache/ikoro-labs/forge/<version>/hooks/handoff_relay.sh`). Jusque-là, le
   hook du plugin se tait et la copie reste celle qui tourne.

## Limites connues

- **Une source par marketplace et par poste** : la marketplace `ikoro-labs` n'est connue qu'une
  fois par poste, à la source du dernier projet qui l'a déclarée (`claude plugin marketplace add`).
  L'ouverture d'une session ne la remet pas sur le `ref` du projet. Deux projets d'un même poste
  peuvent tourner sur deux versions, car chaque installation garde son propre dossier de cache ;
  mais `install` et `update` prennent la source du poste. D'où la redéclaration de l'épingle avant
  chacun d'eux.
- **Dépendance à GitHub** : un poste neuf ou une nouvelle version ne s'installent pas si GitHub ou
  les identifiants git du poste font défaut.
- **Noms préfixés** : `forge:coder`, `/forge:qc`. Les commandes tapées, les tests et les mesures
  d'un projet qui lisent un nom d'agent doivent suivre à la migration.
- **Frontmatter des agents** : un agent de plugin ignore `hooks`, `permissionMode`, `mcpServers` et
  `initialPrompt`. Les gardes des agents sont donc des hooks globaux du plugin, filtrés sur
  `agent_type` (`forge:coder`, `forge:qc-gate`...) ; un filtre faux ne s'appliquerait à personne,
  en silence, d'où les tests de `tests/`.
- **Aucun `CLAUDE.md`** n'est chargé depuis un plugin : la constitution reste celle du projet.

### Éprouvé sur un poste (Claude Code 2.1.303, 2026-10-19)

Les quatre points que l'ADR-0129 laissait à confirmer, essayés dans des projets jetables :

- **Deux projets, deux `ref`** : possible, avec la limite ci-dessus. Un projet épinglé sur 1.0.0,
  un autre sur 1.0.1 : chacun a gardé sa version, jusqu'à un `update` lancé dans le premier, qui
  l'a fait passer en 1.0.1 ; redéclarer son épingle puis relancer `update` l'a ramené en 1.0.0.
- **`qc` du projet et `forge:qc`** : `/qc` lance le skill du projet ; `forge:qc` reste joignable
  sous son nom préfixé, et les deux figurent dans la liste des skills. Pendant la transition, les
  commandes qui doivent viser le plugin écrivent `/forge:qc`.
- **`guard_coder` dans un worktree** : un `forge:coder` lancé avec `isolation: worktree` porte bien
  `agent_type: "forge:coder"` dans l'événement du hook. Rejoué sur `guard_coder`, cet événement
  est refusé pour `gh pr merge` comme pour le skill `forge:qc`, et le même événement avec un autre
  `agent_type` passe.
- **Marketplace injoignable au démarrage** : avec git coupé vers GitHub, la session charge la
  version en cache, skills et agents compris.

## Licence

Privé. Trois skills adaptent mattpocock/skills sous licence MIT :
`plugins/forge/THIRD_PARTY_NOTICES.md`.
