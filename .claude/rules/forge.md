# Règles du dépôt forge

La grille que lisent le coder, le juge et les décideurs sur toute PR de ce dépôt. Elle vaut pour
`plugins/forge/` (ce que les projets chargent), pour `tests/` et pour la documentation de la racine.

## Le contenu du plugin reste générique

- Ce qui est sous `plugins/forge/` cite les clés de `docs/agents/usine.md`, jamais un numéro d'ADR,
  un nom de personne, un nom de projet ou un chemin propre à un projet. Le `README.md`, les pages
  de `docs/` et le `CHANGELOG.md` de la racine peuvent citer la décision ou le projet d'où vient
  un changement.
- Une clé de `usine.md` absente rend l'étape « sans objet (clé `<nom>` absente) », jamais `PASS` ;
  aucune clé ne prend de valeur par défaut. Une nouvelle clé est documentée dans le gabarit
  `plugins/forge/templates/usine.md`.
- Rien de propre à un poste : `${CLAUDE_PLUGIN_ROOT}` plutôt qu'un chemin absolu, aucun terminal
  câblé, aucune variable posée dans un `settings.json`.

## Hooks et scripts

- Python de la bibliothèque standard, lancé par `uv run --no-project --quiet python`, sous Linux et
  sous Windows, à partir de Python 3.10. Une question de processus passe par `handoff_header.py`
  (`/proc` sous Linux, API Win32 sous Windows), jamais par `/proc` seul. Aucun `python3` cité : sous
  Windows, c'est un alias du Microsoft Store.
- Un garde de rôle ou de commande (`guard_git`, `guard_coder`, `guard_readonly`) vaut refus quand il
  échoue : `|| exit 2` dans sa commande de `hooks.json` ; celle de `guard_git` dit en plus que le
  garde a échoué et que la commande est refusée par précaution (sauf pour le code 2, que le garde a
  déjà formulé), et il ajoute `"onFailure": "block"` pour le dépassement du `timeout`, que
  `|| exit 2` ne couvre pas. `guard_pause` n'en est pas un : il échoue ouvert, comme tout hook qui
  avertit ou observe, et ne bloque jamais la session (son échec sort à 0).
- Un garde d'agent filtre sur le nom préfixé (`forge:coder`, `forge:qc-gate`...) : un agent de
  plugin ignore `hooks` dans son front matter. Chaque filtre a son test, car un filtre faux ne
  s'appliquerait à personne, en silence.
- Le `model` d'un agent se fixe dans son front matter. Un appel qui le force l'emporte sur lui.

## Tests

- Chaque comportement ajouté ou changé d'un hook, du parseur ou du contenu a son test dans
  `tests/`. La suite tourne sous Linux et sous Windows :
  `uv run --no-project --quiet python -m unittest discover -s tests`.
- Un test isole `HOME` et `USERPROFILE`, ne passe pas les variables `CLAUDE_` de la session qui le
  lance, et n'écrit jamais dans le vrai `~/.claude`.
- Un test qui ne peut tourner que sous un système le dit par `skipUnless`, avec la raison.

## Version et journal

- La version vit dans `plugins/forge/.claude-plugin/plugin.json`, et nulle part ailleurs
  (`marketplace.json` compris). Un test le garde.
- Chaque version publiée ouvre son entrée en tête de `CHANGELOG.md` : ce qui est entré, par zone
  (Hooks, Agents, Skills, Tests, Gestes humains), et ce qui est resté dehors avec sa raison.
- Un changement qu'un projet consommateur doit voir (variable, geste, comportement d'un hook) est
  décrit dans la page de `docs/` qui en traite, que le `README.md` résume et renvoie ; une variable
  a sa ligne dans le tableau de la passation (`docs/sessions.md`). Le `README.md` reste une page
  d'accueil : ce que fait forge, comment l'installer, où lire la suite.

## Prose

- En français, sans tiret cadratin (le hook `after_write` le refuse).
- Une phrase dit ce qui est, éprouvé ou non : ce qui n'a été essayé que sur un système, ou pas du
  tout sur un vrai poste, le dit.
