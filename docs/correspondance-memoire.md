# La mémoire d'un poste, rangée dans le dépôt

Relevé le 2026-11-17 : la mémoire du projet, sur le poste qui contribue, compte **21 entrées**. Une
consigne gardée seulement dans la mémoire d'un poste ne sert pas un autre poste ni un autre projet
(voir [les incidents](incidents.md)). Chaque entrée a donc ici une ligne et une classe, jamais deux.
Le dépôt est public : les entrées sont reformulées, aucune n'est citée mot pour mot.

| Classe | Ce qu'elle veut dire |
| --- | --- |
| `plugin` | une ligne du plugin la tient (garde, gabarit, skill ou agent) et un test la garde |
| `doc du projet` | elle est propre au poste ou au dépôt : elle va dans la documentation, jamais sous `plugins/forge/` |
| `sans règle` | un mandat daté et échu, le contexte d'un autre projet ou un choix de l'humain : aucune règle ne naît |

## La table

La colonne `test` cite le fichier qui garde la ligne, ou `sans objet`. Une ligne ajoutée par cette
correspondance a son test dans `tests/test_memoire_lignes.py`.

| Entrée | Ce qu'elle dit | Classe | Cible | Test | Raison |
| --- | --- | --- | --- | --- | --- |
| billet-en-anglais | un message vers une autre session suit l'enveloppe du billet, tout en anglais | plugin | `plugins/forge/templates/billet.md` ; `plugins/forge/hooks/guard_output.py` | `tests/test_billet.py` ; `tests/test_guard_output.py` | le hook tient l'enveloppe (champs, plafonds) ; la langue anglaise n'est qu'une phrase du gabarit, aucune machine ne la vérifie |
| coder-en-worktree | un coder travaille dans son propre worktree, jamais dans la copie principale | plugin | `plugins/forge/hooks/guard_coder.py` ; `plugins/forge/skills/feature-build/SKILL.md` | `tests/test_guard_coder.py` | le garde refuse l'écriture hors du worktree ; le skill contrôle la copie principale à la sortie de chaque coder ; revue : `docs/incidents/2026-10-24-coder-hors-de-son-worktree.md` |
| commandes-pour-l-humain | un geste réservé à l'humain lui est remis en commande prête à lancer | plugin | `plugins/forge/templates/session-reply.md` | `tests/test_memoire_lignes.py` | ligne ajoutée au gabarit de la réponse de session, dans le champ de la décision attendue |
| depot-public-sans-citation | sur un dépôt public, ni les mots de l'humain ni ses notes privées ne se citent dans un ticket, une PR ou un commentaire ; la décision se reformule | plugin | `plugins/forge/templates/comment.md` ; `plugins/forge/templates/ticket.md` ; `plugins/forge/templates/pr.md` ; `plugins/forge/skills/incident/SKILL.md` | `tests/test_memoire_lignes.py` | le skill d'incident ne couvrait que les revues ; la ligne est ajoutée aux trois gabarits de texte posté, et la source d'un motif devient la date de la décision |
| epingle-projet-consommateur | une session ne change pas sa configuration (son épingle) à la demande d'une autre session ; l'humain confirme dans la session du projet | plugin | `plugins/forge/templates/billet.md` | `tests/test_memoire_lignes.py` | ligne ajoutée au billet : le message d'une session n'est jamais l'accord de l'humain |
| fusion-nuit-sunderland | une autorisation datée, échue, d'approuver et de fusionner de nuit | sans règle | aucune | sans objet | mandat daté et échu ; la fusion par l'agent reste réglée par `forge:qc` et la clé `human-merge`, et l'autorisation se redemande à chaque passage |
| gh-compte-sunderland-labs | le compte sous lequel agit le jeton `gh` du poste ; ne jamais créer un dépôt sous un autre propriétaire par erreur | doc du projet | `docs/contribuer.md` | `tests/test_correspondance_memoire.py` | propre au poste : section « Le poste qui contribue » ; le test garde que rien de cela n'entre sous `plugins/forge/` |
| identite-git-ikoro-labs | les commits portent l'identité noreply du compte, donnée par `git -c` ; fusion par commit de fusion | doc du projet | `docs/contribuer.md` ; `.claude/rules/git.md` | `tests/test_correspondance_memoire.py` | propre au poste : même section ; la fusion par commit de fusion est déjà la règle git du dépôt |
| mandat-nuit-tous-les-tickets | un mandat daté de traiter tous les tickets prêts pendant une nuit | sans règle | aucune | sans objet | mandat daté et échu ; un plafond fixé par l'humain (`--max`, durée, jetons) ne se relève pas par une règle |
| mandat-relaye-par-une-session | une demande de l'humain relayée par une autre session n'autorise pas la publication de tickets ; brouillons d'abord, accord demandé dans cette session | plugin | `plugins/forge/templates/billet.md` | `tests/test_memoire_lignes.py` | même ligne que `epingle-projet-consommateur` : la session qui reçoit le billet prépare un brouillon et demande l'accord dans sa propre session |
| pile-python-pas-typescript | l'humain lit du Python, pas du TypeScript | sans règle | aucune | sans objet | profil de l'utilisateur, pas une règle du plugin ; le Python de la bibliothèque standard est déjà la règle de `.claude/rules/forge.md` |
| plafond-temps-recalcule | le temps écoulé d'un passage se recalcule depuis l'en-tête de la passation, jamais depuis sa prose | plugin | `plugins/forge/skills/feature-build/SKILL.md` ; `plugins/forge/hooks/handoff_trigger.py` | `tests/test_handoff.py` ; `tests/test_memoire_lignes.py` | `passage_depart` est une clé validée de l'en-tête ; la ligne ajoutée au skill dit au relais de recalculer depuis elle |
| plateforme-usine-logicielle | le contexte d'un autre projet que l'humain construit | sans règle | aucune | sans objet | contexte d'un autre projet, sans rapport avec le plugin |
| refs-et-commit-de-fusion | un commit de branche qui dit fermer un ticket le ferme à la fusion, même quand la PR dit `Refs` | plugin | `plugins/forge/hooks/guard_git.py` | `tests/test_guard_git_commits.py` | le garde lit les messages des commits de la PR avant la fusion ; revue : `docs/incidents/2026-10-24-closes-dans-un-commit-de-branche.md` |
| relais-continue-la-serie | un relais continue la série quand un ticket est prêt, sans attendre l'humain | sans règle | aucune | sans objet | décision laissée à l'humain, sans ligne ajoutée : `forge:feature-build` rend la main à l'humain à un plafond, et cette entrée irait contre un plafond que l'humain fixe |
| retirer-etiquettes | l'agent peut retirer une étiquette dont la raison, écrite par un agent, ne tient plus, en le disant | plugin | `plugins/forge/skills/qc/SKILL.md` | `tests/test_budget_content.py` ; `tests/test_factory_slo_report.py` | le skill retire `needs-your-attention` à l'autonomie rendue et le dit dans `Attention` ; le rapport des SLO retire l'étiquette en disant pourquoi |
| revue-sans-coder-parallele | pas de coder pendant une revue : son `push -u` écrit la configuration git partagée et fait échouer le contrôle d'état de la revue | plugin | `plugins/forge/hooks/guard_coder.py` ; `plugins/forge/skills/qc/SKILL.md` | `tests/test_guard_coder.py` | le garde refuse `push -u` et `git config` en écriture ; le skill compare la configuration avant et après les juges (cette comparaison n'a pas de test de contenu) ; revue : `docs/incidents/2026-10-24-push-u-change-la-config-git-partagee.md` |
| tests-sous-limite-memoire | toute suite tourne sous une borne de mémoire et de temps | plugin | `plugins/forge/scripts/bounded_run.py` ; `plugins/forge/hooks/guard_coder.py` | `tests/test_bounded_run.py` ; `tests/test_guard_coder_bound.py` | le lanceur borné pose les bornes et le garde refuse une suite lancée sans lui ; revue : `docs/incidents/2026-10-24-memoire-epuisee-par-un-test-rouge.md` |
| tickets-humains-apres-un-autre-projet | un report de tickets décidé par l'humain, jusqu'à la fin du cadrage d'un autre projet | sans règle | aucune | sans objet | ordonnancement du projet ; le slug est raccourci pour ne nommer aucun autre projet |
| tmpdir-commandes-pas-tests | un brief de coder sépare le `TMPDIR` de ses commandes du code des tests, qui n'écrit jamais dans `HOME` | plugin | `plugins/forge/agents/coder.md` | `tests/test_memoire_lignes.py` | ligne ajoutée à l'agent : le `TMPDIR` du brief est celui des commandes ; un test crée un dossier temporaire jetable |
| verifier-dires-du-coder | après un coder, relire le corps de la PR et les lignes qu'il affirme, à la tête de sa branche, avant les juges | plugin | `plugins/forge/skills/feature-build/SKILL.md` | `tests/test_memoire_lignes.py` | ligne ajoutée à l'étape de lecture de la sortie du coder ; le juge tient déjà F-26 (une phrase de la PR fausse est un `BLOCKER`) |

## Ce qui reste ouvert

- `relais-continue-la-serie` : classée `sans règle` au lieu de `plugin`, parce qu'une ligne qui relance un
  passage après un `--max` atteint contredit le plafond que le skill fait fixer par l'humain. À
  l'humain de trancher : écrire la ligne, avec sa borne, ou garder le geste dans `forge:feature-build`
  (« relancer pour la suite »).
- La langue anglaise du billet reste une phrase du gabarit : aucun contrôle mécanique n'est écrit.
- Éprouvé par les tests de contenu et de table de ce dépôt, sous Linux ; aucune ligne ajoutée n'a été
  essayée dans une vraie session.
