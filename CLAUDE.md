# forge

Ce dépôt est le plugin Claude Code `forge` et la marketplace `ikoro-labs` qui le sert. Il se
développe avec sa propre usine : le plugin y est installé à la version épinglée dans
`.claude/settings.json`, et sa configuration est `docs/agents/usine.md`.

- **L'usine qui tourne n'est pas celle qu'on modifie.** La session charge la version épinglée
  depuis le cache (`~/.claude/plugins/cache/ikoro-labs/forge/<version>/`) ; un changement s'écrit
  dans `plugins/forge/` et n'agit sur l'usine de ce dépôt qu'une fois publié, quand une PR monte
  l'épingle. Le cache ne s'édite jamais.
- **Essayer un changement dans une vraie session** : `claude --plugin-dir <ce dépôt>/plugins/forge`,
  lancé depuis un projet jetable, jamais pendant un passage de l'usine dans ce dépôt.
- **Les règles** : `.claude/rules/forge.md` pour le contenu et les tests, `.claude/rules/git.md`
  pour les branches, les commits et la publication.
- **Vérifier avant toute PR** :

  ```sh
  uv run --no-project --quiet python -m unittest discover -s tests
  uv run --no-project --quiet --with ruff==0.17.3 ruff check plugins/forge tests
  uv run --no-project --quiet --with mypy==2.4.1 mypy
  claude plugin validate .
  claude plugin validate plugins/forge
  ```
