# Journal des versions

Une entrée par version publiée du plugin `forge`, la plus récente en haut. Chaque version porte le
tag `forge--v<X.Y.Z>` sur ce dépôt ; sa version est celle de `plugins/forge/.claude-plugin/plugin.json`,
et nulle part ailleurs. Les tags `forge-v<X.Y.Z>` (un seul tiret) appartiennent à l'historique
antérieur à ce dépôt et ne sont pas repris ici.

Ce dépôt a été recréé le 2026-10-23 ; l'ancien est `ikoro-labs/forge-archive`. Jusqu'à la 1.5.0, les
numéros de PR et de ticket nus (`#38`) renvoient à l'ancien dépôt ; un renvoi au nouveau dépôt
porte son nom (`ikoro-labs/forge#7`).

## [1.16.0] - 2026-11-17

La passation se fait à 150 000 jetons, avec ou sans feature, et par billet ; une fusion relit les
messages des commits de la PR. Version mineure : deux billets nouveaux, aucune clé nouvelle.

- Hooks : le seuil de passation passe à 150 000 jetons, avec ou sans feature ; le relais lit
  `DEFAULT_LIMIT` de `handoff_trigger.py` et le donne au successeur (ikoro-labs/forge#237, partie 1
  de ikoro-labs/forge#127).
- Hooks : `guard_git` lit les commits d'une PR avant sa fusion et la refuse quand l'un ferme un
  ticket que la description ou le message de fusion ne cite qu'en `Refs` ; une liste illisible vaut
  refus, quelle que soit la méthode (ikoro-labs/forge#228, ikoro-labs/forge#64).
- Hooks : `guard_output` refuse un billet dont l'heure s'écarte de plus de 5 minutes de l'horloge du
  poste (ikoro-labs/forge#236, point A5 de ikoro-labs/forge#227).
- Skills : les billets `handoff-request` et `handoff` remplacent la prose de la passation, dans
  l'étape 0 de `forge:feature-build` et dans ce qu'imprime `handoff_trigger.py yield` ; le hook
  vérifie la session demandeuse dans le registre et le successeur nommé par la passation
  (ikoro-labs/forge#236, point A6 de ikoro-labs/forge#227).
- Gabarits : `billet.md` ajoute les types `handoff-request` et `handoff` ; son plafond passe de 16
  à 24 lignes.
- Tests : le seuil avec et sans feature, les messages des commits pour chaque méthode, l'heure et
  les billets de passation.
- Gestes humains : une session ouverte avec `CLAUDE_SESSION_TOKEN_LIMIT` garde son propre seuil ;
  sans la variable, elle passe la main à 150 000 jetons.
- Resté dehors : le seuil propre à un utilisateur, conservé par le relais, est la suite de
  ikoro-labs/forge#127 ; la dernière partie de ikoro-labs/forge#63 (PR ikoro-labs/forge#238) n'est pas
  encore relue. L'essai de bout en bout est sans objet ici (clé `e2e-repo` absente). Rien d'éprouvé
  sous Windows en local, ni dans une vraie session.

### Objectifs de service

État de chaque objectif au 2026-11-17.

| Objectif | Cible | Fenêtre | Valeur | Budget restant | État |
|---|---|---|---|---|---|
| `accept-round-1` | >= 80 % | 30 j | 62.03 % | 0 % sur 20 % | épuisé |
| `lead-time p90` | <= 24 h | 30 j | 534.3 h | 0 h sur 24 h | épuisé |
| `release-lag p90` | <= 24 h | 30 j | 493.6 h | 0 h sur 24 h | épuisé |
| `escaped-defects` | <= 10 % | 30 j | 0.93 % | 9.07 % sur 10 % | tenu |
| `change-failure` | <= 10 % | 30 j | 0.93 % | 9.07 % sur 10 % | tenu |
| `human-touch` | <= 10 % | 30 j | 15.32 % | 0 % sur 10 % | épuisé |
| `main-green` | >= 100 % | 30 j | 95.24 % | 0 % sur 0 % | épuisé |
| `judge-recall` | >= 95 % | 30 j | sans objet | aucun résultat du jeu de référence (option `--reference` absente) | sans objet |
| `false-accept` | <= 0 % | 30 j | sans objet | aucun résultat du jeu de référence (option `--reference` absente) | sans objet |

Aucun `escaped-defect` ouvert depuis le 2026-11-16.

## [1.15.0] - 2026-11-16

La revue rejoue chaque commit, sonde ses BLOCKER et se mesure sur un jeu de référence ; l'usine
publie seule sous conditions ; les messages entre sessions prennent la forme d'un billet. Version
mineure : sept clés nouvelles, sans valeur par défaut, et un garde de fusion plus strict.

- Hooks : `guard_git` refuse, pour tout agent, une fusion (`gh pr merge`, `gh api`) dont la méthode
  diffère de `merge-method` ou n'en donne aucune ; une clé absente, sur deux lignes ou inconnue
  refuse toute fusion (ikoro-labs/forge#224, ikoro-labs/forge#63).
- Hooks : `guard_output` impose le gabarit `billet` à tout `SendMessage` vers une autre session ;
  le champ `resource` prend ses valeurs dans la clé `shared-resource` (ikoro-labs/forge#233,
  points A1 à A4 de ikoro-labs/forge#227).
- Agents : `forge:qc-gate` rejoue `install` puis `ci-replay` sur chaque commit de la PR
  (`commit_replay.py`) ; un commit rouge est un `BLOCKER` (règle `F-24`) (ikoro-labs/forge#216,
  ikoro-labs/forge#69).
- Agents : `forge:qc-conf` classe la gravité par une grille fixe (`F-25`, `F-26`) ; un `BLOCKER`
  sondé ne compte qu'une fois rejoué par `probe_replay.py`, sinon il est « déduit »
  (ikoro-labs/forge#219, ikoro-labs/forge#68).
- Scripts : `red-replay` peut porter `{report}` ; `junit_report.py` rejoue la base au grain du test
  ajouté ou changé (ikoro-labs/forge#220, ikoro-labs/forge#43).
- Scripts : `eval_reference.py` et huit cas sous `plugins/forge/evals/` mesurent `judge-recall` et
  `false-accept` (ikoro-labs/forge#221, ikoro-labs/forge#67).
- Skills : `forge:incident`, son gabarit et `incident.py check` ; `factory_slo.py incidents`
  compte les incidents par classe (clé `incident-dir`) (ikoro-labs/forge#222, ikoro-labs/forge#61).
- Skills : `forge:release` et `release.py` : l'agent publie seul si tous les SLO sont `tenu`, aucune
  `budget-action` n'est active, l'essai de bout en bout passe et aucun `sev1` n'est ouvert (clé
  `release-trigger`) (ikoro-labs/forge#225, ikoro-labs/forge#71).
- Scripts : `e2e_trial.py` essaie l'usine sur un dépôt jetable (clés `e2e-repo`, `e2e-command`,
  `e2e-budget-usd`) (ikoro-labs/forge#223, ikoro-labs/forge#70).
- Scripts : `factory_slo.py status` signale la date de révision passée (clé `slo-review-date`)
  (ikoro-labs/forge#218).
- Gabarits : `billet.md`, `incident.md` ; `usine.md` documente les sept clés nouvelles.
- Tests : un fichier par script nouveau, plus les cas de `guard_git`, `guard_output` et du contenu.
- Gestes humains : un projet dont un agent fusionne déclare `merge-method`, sans quoi toute fusion
  par un agent est refusée. Les autres clés sont facultatives ; sans elles, l'étape est sans objet.
  Ce dépôt déclare `slo`, `budget-action`, `slo-review-date` et `incident-dir`.
- Resté dehors : le jeu de référence n'a jamais tourné (aucun appel de modèle permis), donc ni
  `judge-recall` ni `false-accept` ne sont mesurés ; l'essai de bout en bout est sans objet ici
  (clé `e2e-repo` absente) ; les points A5 et A6 de ikoro-labs/forge#227 viennent dans une PR à
  part ; le grain du test reste ouvert sur ikoro-labs/forge#43. Rien d'éprouvé sous Windows en
  local.

### Objectifs de service

État de chaque objectif au 2026-11-16.

| Objectif | Cible | Fenêtre | Valeur | Budget restant | État |
|---|---|---|---|---|---|
| `accept-round-1` | >= 80 % | 30 j | 60 % | 0 % sur 20 % | épuisé |
| `lead-time p90` | <= 24 h | 30 j | 534.3 h | 0 h sur 24 h | épuisé |
| `release-lag p90` | <= 24 h | 30 j | 506.4 h | 0 h sur 24 h | épuisé |
| `escaped-defects` | <= 10 % | 30 j | 0.98 % | 9.02 % sur 10 % | tenu |
| `change-failure` | <= 10 % | 30 j | 0.98 % | 9.02 % sur 10 % | tenu |
| `human-touch` | <= 10 % | 30 j | 14.02 % | 0 % sur 10 % | épuisé |
| `main-green` | >= 100 % | 30 j | 94.83 % | 0 % sur 0 % | épuisé |
| `judge-recall` | >= 95 % | 30 j | sans objet | aucun résultat du jeu de référence (option `--reference` absente) | sans objet |
| `false-accept` | <= 0 % | 30 j | sans objet | aucun résultat du jeu de référence (option `--reference` absente) | sans objet |

Aucun `escaped-defect` ouvert depuis le 2026-11-16.

## [1.14.0] - 2026-11-16

Tout test lancé par un agent passe par un lanceur borné, qui tient aussi le budget du poste entier.
Version mineure : un script et deux clés nouvelles, sans valeur par défaut.

- Scripts : `bounded_run.py` lance une commande sous une borne de mémoire et un délai (`RLIMIT_AS`
  et groupe de processus sous Linux, objet de tâche sous Windows) ; une borne qu'il ne peut pas
  poser refuse de lancer. Avant le lancement, il lit la mémoire disponible et la charge à 1 min du
  poste, attend s'ils sont hors budget, puis sort en 120. Il ramène le `-n` de pytest-xdist au
  plafond, `-n auto` compris. Codes distincts : 120 budget, 121 appel faux, 122 borne refusée, 123
  mémoire probablement atteinte, 124 délai. `--check` lit le budget sans rien lancer
  (ikoro-labs/forge#214, ikoro-labs/forge#66).
- Scripts : `base_replay.py` pose sa borne par la fonction partagée `run_bounded`.
- Agents : `forge:coder` et `forge:qc-gate` lancent toute suite et toute sonde par le lanceur ;
  `forge:feature-build` lit le budget avant un sous-agent de tests.
- Gabarits : `usine.md` documente `run-limits` (`<Mo> | <secondes>`) et `run-budget` (`<Mo
  disponibles> | <charge> | <workers> | <attente>`). Ce dépôt déclare `2000 | 300` et
  `4096 | 12 | 2 | 300`.
- Tests : `tests/test_bounded_run.py`.
- Gestes humains : un projet qui veut la borne et le budget déclare les deux clés ; sans elles, le
  lanceur exige ses options et `forge:qc-gate` rend « sans objet ».
- Resté dehors : un `-n` posé par un fichier de configuration, par `PYTEST_ADDOPTS` ou caché dans
  une chaîne shell n'est pas vu ; macOS n'est pas couvert ; le côté Windows n'a tourné qu'en CI.
  Trois MINOR de la revue de #214 sont reportés sur ikoro-labs/forge#55.

## [1.13.0] - 2026-11-15

Trois règles de l'usine passent de la prose aux hooks : le frontmatter et l'index des documents,
les plafonds de la documentation, et le ménage après chaque agent. Version mineure : cinq clés
nouvelles, toutes facultatives ; sans elles, seul le ménage des worktrees et des branches d'agents
agit.

- Hooks : `after_write` tient trois clés. `doc-frontmatter` refuse un `.md` de ses motifs sans
  frontmatter lisible portant un `type` non vide ; `doc-index` régénère l'index de ces documents à
  chaque écriture ; `doc-cap` tient un plafond de mots ou de lignes par motif, avec un cliquet sur la
  version à `HEAD` (un fichier déjà au-dessus ne peut pas grandir). Seul le fichier écrit est jugé ;
  un fichier écrit par une commande shell ne passe pas par là (ikoro-labs/forge#210, points (a) et
  (b) de ikoro-labs/forge#199).
- Hooks : `agent_cleanup.py`, au `SubagentStop` et au `SessionStart`, échoue ouvert. Il retire le
  worktree propre d'un agent fini et signale un worktree sale ; il supprime les branches
  `worktree-agent-*` orphelines dont la tête est dans `main` ou sur une branche distante ; il purge
  les caches d'agents (clé `agent-cache-dir`, au `SubagentStop` seulement) et les bundles de
  sauvetage contenus (clé `rescue-bundle-dir`). Un agent est fini quand le détenteur de son verrou
  est mort ou réattribué, ou, sans verrou, quand sa méta porte `finished` et que sa transcription se
  tait depuis 30 minutes. `guard_git` refuse toujours `git branch -D` aux agents
  (ikoro-labs/forge#211, point (c) de ikoro-labs/forge#199).
- Hooks : `handoff_header.lock_holder_alive`, extrait de `live_agents`, juge le détenteur d'un
  verrou de worktree pour les deux.
- Gabarits : `usine.md` documente `doc-frontmatter`, `doc-index`, `doc-cap`, `agent-cache-dir` et
  `rescue-bundle-dir`.
- Tests : `tests/test_after_write_docs.py`, `tests/test_agent_cleanup.py`, cas nouveaux de
  `tests/test_handoff.py`.
- Gestes humains : aucun. Un projet qui monte à cette version voit disparaître, à sa prochaine
  session, les worktrees propres de ses agents finis et leurs branches déjà poussées. Un coder
  réveillé par `SendMessage` plus de 30 minutes après son rendu ne retrouve plus son worktree ; son
  travail reste sur sa branche.
- Resté dehors, au verdict des PR : la docstring de `doc_rules.py` cite le ticket de ce dépôt ; deux
  lignes `doc-index` ou une valeur vide passent sans mot ; un cache voisin cité par la transcription
  de l'agent qui s'arrête est purgé aussi (reporté sur ikoro-labs/forge#199) ; une branche distante
  périmée compte comme sûre ; deux défauts de prose dans `docs/installation.md`. Rien d'éprouvé en
  vraie session ni sous Windows en local.

## [1.12.0] - 2026-11-15

La réponse de session et la passation portent le tableau des features, et une session sans feature
passe la main plus tard. Version mineure : une nouvelle option, un champ exigé de plus dans la
réponse de session, des valeurs par défaut changées ; aucune clé nouvelle.

- Scripts : `report_mail.py --features` rend, du calcul de la partie Features du mail, un tableau
  (feature, fermés sur total, PR ouvertes, tickets bloqués, tickets prêts) puis la ligne
  `In parallel:`, tickets et features qui tiennent dans les places libres ; une seule ligne sans
  `report-repo`, sans `feature-dir` ou sans feature ouverte. Le module `features_block.py` porte la
  forme du bloc, partagée par le script et la garde (ikoro-labs/forge#204, critère A11 de #181).
- Hooks : `guard_output` (Stop) exige un cinquième champ `Features` dans la réponse de session, le
  bloc du script ou sa ligne, et refuse tout autre contenu ; le bloc sort des plafonds de lignes et
  de mots (ikoro-labs/forge#204, A11 de #181).
- Hooks : la consigne de passation fait lancer `report_mail.py --features` et recopier sa sortie
  sous `Features:` ; aucun hook ne relit ce corps (ikoro-labs/forge#204, A12 de #181).
- Hooks : sans variable, le seuil de passation d'une session sans feature passe de 150k à 300k
  jetons (400k avec une feature, inchangé), et le plafond quotidien de relais par projet
  (`CLAUDE_HANDOFF_RELAY_MAX`) de 5 à 200 (ikoro-labs/forge#206, #205).
- Gabarits : `session-reply.md` gagne le champ `Features`.
- Tests : cas nouveaux de `tests/test_report_mail.py`, `tests/test_output_check.py`,
  `tests/test_guard_output.py` et `tests/test_handoff.py`.
- Gestes humains : aucun. Une session qui monte à cette version voit sa réponse refusée une fois
  sans le champ `Features` ; sans `report-repo`, la ligne `not applicable` suffit.
- Resté dehors : A4 de #181 (retrait des copies hors dépôt, geste de chaque projet) ; #181 reste
  ouvert. Deux MINOR du verdict de #204 : la ligne « `feature-dir` absent » ne s'imprime jamais,
  la clé retombant sur le gabarit, et un tableau tapé à la main de la bonne forme passe la garde.

## [1.11.0] - 2026-11-15

Le mail de relevé dit où en est chaque feature ouverte et propose les tickets prêts qui tiennent
dans les places libres. Version mineure : une nouvelle partie du mail, aucune clé nouvelle.

- Scripts : `report_mail.py` gagne la partie « Features » : chaque feature ouverte avec son
  pourcentage (`completion.percent`), ses PR ouvertes et ses tickets prêts ; une feature que `gh`
  ne lit pas dit « tickets not read » et le reste du mail part. `completion.py` rend aussi
  étiquettes, assignés et bloqueurs ouverts des sous-issues, en un appel `gh` par feature
  (ikoro-labs/forge#200, critère A7 de #181).
- Scripts : avec N places libres (N > 0), la partie « Awaiting you » propose au plus N tickets
  prêts et demande lesquels lancer ; le mail ne lance rien. Avec 0 place ou un nombre inconnu, la
  partie Features dit pourquoi il n'y a pas de proposition (ikoro-labs/forge#200, critère A9 de
  #181).
- Gabarits : `report-mail.md` gagne la section « Features », facultative.
- Tests : cas nouveaux de `tests/test_report_mail.py` et `tests/test_completion.py`.
- Gestes humains : aucun. La partie Features n'est pas un événement : un mail qui ne changerait
  que par elle ne part pas (code 10 inchangé).
- Resté dehors : A4 (retrait des copies hors dépôt, geste de chaque projet), A11 et A12 de #181 ;
  #181 reste ouvert.

## [1.10.0] - 2026-11-15

Le mail de relevé part même quand les runners sont illisibles, et aucun coder ne part sans place
libre sur le poste. Version mineure : une nouvelle clé facultative (`report-host-floor`) et une
nouvelle option (`report_mail.py --slots`).

- Scripts : `report_mail.py` ne sort plus en échec quand `gh api .../actions/runners` refuse le
  jeton (droit d'administration absent) ; le mail et `--line` disent « runners not read »
  (ikoro-labs/forge#195). Refs #181.
- Scripts : `report_mail.py --slots` rend en une ligne les places libres des hôtes de
  `report-host` : les runners libres d'un hôte, aucun sous son plancher `report-host-floor`
  (mémoire et disque libres en Gio, lus par une sonde qui imprime `mem-free` et `disk-free`), et
  `unknown` quand des runners comptés sont illisibles (ikoro-labs/forge#196, critère A8 de #181).
- Skills : `forge:feature-build` lit `--slots` avant chaque coder quand `report-repo` est déclarée ;
  sur `Free slots: 0`, aucun coder ne part (ikoro-labs/forge#196, critère A10 de #181).
- Gabarits : `usine.md` documente `report-host-floor` et le format de sonde qu'il exige.
- Tests : cas nouveaux de `tests/test_report_mail.py` (jeton refusé, places, plancher, sonde).
- Gestes humains : aucun requis, mais un projet qui déclare `report-repo` change de comportement
  sans autre clé : chaque mail porte la ligne « Free slots », et `forge:feature-build` ne lance
  aucun coder quand tous ses runners sont occupés (`Free slots: 0`). Le plancher
  `report-host-floor` et une sonde au format `mem-free` et `disk-free` ajoutent la garde de la
  mémoire et du disque. Un jeton qui ne lit pas les runners donne `unknown`, et seuls `--parallel`
  et `--max` bornent alors le passage.
- Resté dehors : les critères A4 (Shipyard et MeridianRe passent à ce script et retirent leur copie
  hors dépôt, geste de chaque projet après le tag), et A7, A9, A11 et A12 de #181, à livrer ;
  #181 reste ouvert.

## [1.9.0] - 2026-11-14

Le mail de relevé de l'usine vient de forge, le relais de passation ouvre sa fenêtre sans réglage,
et les gardes git ferment les variables de localisation. Version mineure : de nouvelles clés
facultatives (`report-*`, `output-words-report-mail`) et un nouveau hook.

- Scripts : `report_mail.py` construit le mail de relevé depuis les seules clés `report-*` de
  `usine.md`, sort en code 10 sans mail quand rien n'a changé et enregistre l'envoi par `--sent`
  (#188) ; sa partie « CI et runners » groupe les runners par hôte (`report-host`), les runs en
  file et en cours, le dernier run de main, et la mémoire et le disque quand `report-host-probe`
  nomme une sonde (#189). Refs #181.
- Hooks : `guard_report_mail.py` refuse `report_mail.py --sent` quand le mail en attente s'écarte
  du gabarit `templates/report-mail.md` (#190) ; `output_check.py` gagne le genre `report-mail`
  (clé `output-words-report-mail`).
- Hooks : sans `CLAUDE_HANDOFF_TERMINAL`, le relais ouvre `claude attach <id>` dans le terminal par
  défaut du bureau par `xdg-terminal-exec` quand il est installé ; une valeur d'arrêt (`off`, `0`,
  `false`, `no`, vide) n'ouvre aucune fenêtre (#186, closes #185). Essayé seulement sous Linux.
- Hooks : `guard_git` refuse `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_COMMON_DIR`,
  `GIT_OBJECT_DIRECTORY`, `--git-dir` et `--work-tree` ; `guard_coder` refuse `git rebase`,
  `git pull --rebase`, `--force-with-lease`, `git add -A`, `.` ou `:/` et `git commit -a`, y compris
  dans un `bash -c` (#187, refs #105).
- Gabarits : le résumé de session (`session-reply.md`) exige un quatrième champ, « CI et runners »,
  qu'imprime `report_mail.py --line` ; sans `report-repo`, il dit `not applicable` (#191).
- Docs : le schéma d'architecture dit de nouveau l'état du plugin (#184).
- Tests : `test_report_mail.py`, `test_guard_report_mail.py`, et les cas nouveaux de
  `test_guard_git.py`, `test_guard_coder.py`, `test_handoff.py` et `test_output_check.py`.
- Gestes humains : un projet qui monte l'épingle voit son résumé de session renvoyé une fois à la
  réécriture par `guard_output` quand le champ « CI et runners » manque ; pour le mail de relevé, il déclare `report-repo` dans `usine.md` puis retire
  son script hors dépôt (critère A4 de #181, resté dehors : il se fait après le tag).

## [1.8.0] - 2026-11-14

Property-based tests enter the TDD loop and its review, and the format-on-write kill no longer
blocks a session. Minor version: a new optional key, `property-test-lib`.

- Skills: `forge:tdd` gains « Les tests par propriétés » (#167): when to write one and when not,
  the failing property first, the shrunk example kept as an example test, the seed and the minimal
  example copied into the PR's proofs. Without `property-test-lib` it asks for none and the PR says
  « sans objet (clé `property-test-lib` absente) ».
- Agents: `forge:qc-conf` never requires a property test; a reported failure without its seed or
  its minimal example, or without the kept example test, is a `MINOR` finding; without the key it
  writes the skipped step in `GATES` (#167).
- Hooks: `handoff_header` bounds the `wait` after a kill (`KILL_WAIT_SECONDS`), so a process that
  survives the kill no longer blocks the session; on Windows, when `TerminateJobObject` fails it
  falls back to `process.kill()` (#165, closes #26).
- Templates: `usine.md` documents `property-test-lib` (no default) and the three Windows limits of
  the format-on-write kill (#165, #167).
- Tests: `tests/test_property_tests_content.py` (9 tests); `ProcessGroupKill` covers the bounded
  wait on both systems and the Windows fallback.
- Human gestures: none required; a project that writes property tests adds `property-test-lib`.

## [1.7.0] - 2026-11-14

`/forge:qc` merges with the method the project declares, and the three-round rule stops naming a
consuming project. Minor version: a project that upgrades without the new key no longer gets its
PRs merged by the agent.

- Skills: `/forge:qc` step 8 merges with `--squash` or `--merge`, from the new required key
  `merge-method`; without it the PR stays open on its ACCEPT and the report says why. With `merge`,
  the agent reads the branch's commit messages before merging, since they reach the base.
- Agents: `forge:qc-gate` takes rounds 1 to 3, beyond only with `GRANTED:`, as `forge:qc-conf`
  and the skill say. The three-round rule no longer cites a consuming project's ticket in
  `qc-conf.md`, `skills/qc/SKILL.md` and `scripts/parse_output.py`.
- Tests: `MergeMethod` checks the skill's merge line and the template key.
- Human gestures: each project adds `merge-method` to its `docs/agents/usine.md` (`squash` keeps
  the previous behaviour). This repository declares `merge`, as `.claude/rules/git.md` requires.
- Left out: `rebase`, whose merge ignores the body that `guard_git` reads; a `guard_git` check of
  the branch's commit messages under `merge`, left to the skill's reading for now.

## [1.6.0] - 2026-11-14

The factory's rules move from prose into hooks, as a standard shared by every forge project
(decisions of the owner of 2026-11-13 and 2026-11-14, agreed between the two projects that run
forge): agreed and frozen validation cases, the coder's model, a ticket budget per feature with an
admitted reason, a structure for every output, the infrastructure gestures, and the completion
table. Before them: test seams and the `forge:tdd` skill, base replay of added tests, service
objectives, the traceability of a feature to its business source, and the end-to-end review.
Pull request numbers below are those of `ikoro-labs/forge`.

### Hooks

- `guard_cases`, new (#172): with the `validation-cases` key, a PR opens only on a ticket whose
  cases carry an `AGREED:` line for every role, and a verdict blocks only on a case, a rule or a
  regression. Without the key it reads nothing and refuses nothing.
- `guard_coder_model`, new (#172): `forge:coder` runs on `sonnet` with effort `high`; `opus` only
  with a prompt line `ESCALATION: #<n> round 3`, `haiku` only with `MODE: sync`; any other model is
  refused, on an `Agent` call and inside a `Workflow` script. Always on.
- `guard_ticket_budget`, new (#173): a design declares `feature-tickets: N`, and a ticket opens only
  with an admitted `Motif :` line (`to-tickets`, `fusion-bloquee`, `main-rouge`, `securite`,
  `demande-<who>`, `feature-new`) and within its feature's budget. Always on for `gh issue create`.
- `guard_output`, new (#174): subagent returns, GitHub bodies (ticket, PR, comment, verdict) and the
  session's reply follow the templates of `templates/`, with word caps; the `output-*` keys replace a
  template or a cap. An agent is refused once, then passes with a journal line; a gh body is refused
  each time. Always on. `max-lines: 0` in a project's template lifts the line cap, as `0` lifts a
  word cap.
- `guard_infra`, new (#176): Docker, `systemctl`, `lxc`, `service` and `networkctl` gestures that
  stop or delete are refused to a subagent and asked to the human in the main session; on a host of
  `infra-hosts`, everything off a read list is. The merge of a PR touching the guards is the owner's.
- `guard_completion`, new (#175): a question on progress is answered with the table of
  `scripts/completion.py` (completed, open, total, % with its denominator); it fails open.
- `guard_git`: refuses an agent the owner's gestures (#14), fails closed (#22), reads them without
  opening its standard input (#30), counts a line break as a command separator (#160), refuses any
  agent the merge of a PR touching `protected-path` (#90); `never-weaken` decodes `rename to`
  without a prefix (#164).
- `guard_coder`: the coder works in its worktree and pushes without `-u` or `-f` (#86).

### Agents

- `forge:coder`: tests at the declared seams, one vertical slice at a time (#48); the PR body shows
  the change, its gate and its blast radius (#52); a token budget per ticket (#161).
- `forge:qc-gate` replays each added or changed test on the base, where it must fail (#51).
- `forge:qc-conf` reads every added or changed test and flags the tautological, the coupled and the
  off-seam (#47); screen labels are checked against the glossary and refused words (#104, #107).
- `forge:product-owner` reads the business source before the agents' documents (#103).

### Skills

- `forge:tdd`, new (#49). `feature-design` splits into prerefactoring first, then expand and
  contract (#50), and writes a journey file screen by screen (#110). `feature-spec` ingests the
  business source in Markdown and reaches the grain of a target procedure (#108, #109). A
  traceability matrix per feature (#111), a guided design with a non-developer expert (#112), front
  verification capabilities on the command line (#113), the journey replayed in CI (#115), and an
  end-to-end review of a feature, run in a loop on each merge (#116, #117, #120).
- `/forge:qc` hands merges back to the human and freezes features when an error budget is spent
  (#87), and moves stacked PRs before deleting a merged branch (#171).
- Service objectives: indicators computed without a model, objectives and error budgets in
  `usine.md`, their report, severity classes and SLA (#78, #79, #83, #85, #89).

### Tests and CI

- ruff, mypy and SHA-pinned actions in CI, with lint required (#162, #163). The suite counts 1253
  tests on Linux, 5 skipped (Windows only); it runs in CI on Linux and Windows.

### Upgrading

- Bump the `ref` to `forge--v1.6.0`, then `claude plugin marketplace update ikoro-labs` and a new
  session (`docs/installation.md`, « Monter de version »).
- Five hooks act without a key: `guard_coder_model`, `guard_ticket_budget`, `guard_output`,
  `guard_infra` and `guard_completion`. A project whose own rules differ (another coder model, other
  ticket reasons, its own output formats) declares the matching `output-*` keys or changes its rule
  before upgrading. `guard_cases` waits for `validation-cases`.
- Not tried in a real Claude Code session before this release: the six new hooks ran in the test
  suite and in CI only; `completion.py` was run by hand on two real projects.

### Left out

- #165 (bounded kill of a Windows job object) and #167 (when to write a property test): reviewed
  REJECT on 2026-11-14, fixed on their branches after this release.

## [1.5.0] - 2026-10-23

Une session apprend dès son démarrage quelles autres sessions vivent sur son dépôt (PR #38, critère
5 de ikoro-labs/forge-archive#4, qui est ainsi livré en entier). `/forge:qc` retire `needs-your-attention`
quand un agent l'a posée et que sa raison ne tient plus (#45, #46). Hors du plugin, le `README.md`
devient une page d'accueil et la marketplace référence un second plugin ; le plugin prend l'identité
d'ikoro-labs, icône et manifeste alignés sur ceux d'`ai-delivery-gates` (ikoro-labs/forge#7).

### Hooks

- `sessions_notice.py`, nouveau, déclaré sous `SessionStart` dans `hooks.json` (`timeout` 10, sans
  matcher : toutes les sources, `compact` comprise) (#38). Il appelle la détection de
  `handoff_header.py sessions`, sur le même registre et avec les mêmes exclusions, et, s'il trouve
  une autre session vivante du dépôt, ajoute un `additionalContext` qui nomme chacune et renvoie au
  point 5 de l'étape 0 de `feature-build` sans le réécrire. Il ne dit rien sans autre session, ni
  pour un sous-agent (`agent_id` présent), et sort toujours en 0. Il n'a tourné dans aucune session
  réelle de Claude Code : à la main sous Linux (Claude Code 2.1.306), l'événement passé sur l'entrée
  standard, sur le registre réel d'un poste, il est resté silencieux, les autres sessions vivantes
  étant d'autres dépôts. Qu'il nomme une autre session du dépôt n'a été vu que dans la suite de
  tests ; sous Windows, seulement en CI.

### Skills

- `/forge:qc` ne dit plus « Ne la retire jamais » de `needs-your-attention`. L'agent la retire quand
  la raison écrite dans `Attention` ne tient plus (une revue `FAILED` relancée qui aboutit, un écart
  corrigé), et écrit dans `Attention` ce qu'il a retiré et pourquoi ; la ligne gagne la forme
  `retirée : <raison>` (#45). Seulement une étiquette dont un agent a écrit la raison, dans la ligne
  `Attention` d'un `Rapport d'agent` ou dans un commentaire de revue `FAILED` : l'agent agit sous le
  compte de l'humain, et GitHub ne les distingue pas ; une étiquette sans texte d'agent vient d'un
  humain et reste (#46). Sur une PR qui touche un chemin de la clé `protected-path`, elle reste
  jusqu'à la fusion humaine. Aucun retrait n'a encore été fait par un agent qui lit cette règle.

### Tests

- `tests/test_sessions_notice.py`, nouveau (9 tests) : registre factice sous `HOME` et
  `USERPROFILE` isolés, une autre session du dépôt nommée, silence sans elle et pour un sous-agent,
  le prédécesseur d'une passation exclu, une entrée illisible nommée comme vivante, sortie 0 sur
  toute entrée ou tout échec, et la déclaration dans `hooks.json`.
- `tests/test_plugin_content.py` : la règle de retrait de `/forge:qc` et sa borne (#45, #46) ; les
  autres plugins du catalogue épinglés sur un tag (#47) ; le test qui garde le plugin générique ne
  compare plus que l'empreinte SHA-256 des noms qu'il refuse (#48).
- La suite compte 170 tests sous Linux, dont 3 sautés, propres à Windows. Elle tourne en CI sous
  Linux et sous Windows.

### Manifeste et icône

- Le manifeste du plugin gagne `displayName`, `author.url` et `homepage`, dans l'ordre du manifeste
  d'`ai-delivery-gates`, et l'icône (`plugins/forge/.claude-plugin/icon.png`, l'export de
  `docs/logo.svg`) passe aux couleurs d'ikoro-labs (ikoro-labs/forge#7). Aucun test ne garde ces
  trois champs.

### Hors du plugin

- Le `README.md` s'ouvre sur une bannière (`docs/banniere.svg`, exportée en `docs/banniere.png`) et
  gagne une section Limites connues ; le dépôt reçoit un `.gitignore` et un `.gitattributes` communs
  aux plugins d'ikoro-labs, sans renormaliser aucun fichier (ikoro-labs/forge#7).
- Le `README.md` devient une page d'accueil ; le détail passe dans `docs/installation.md`,
  `docs/sessions.md`, `docs/modeles-et-jetons.md` et `docs/contribuer.md`, qui ajoute à la
  publication la PR d'épingle et celle du tag cité par l'installation (#44).
- La documentation ne cite plus de projet utilisateur ni de personne (#48).
- La marketplace `ikoro-labs` n'est plus dite privée et référence `ai-delivery-gates`, publié
  depuis son propre dépôt (#47), puis épinglé sur `ai-delivery-gates--v0.2.4` : les plugins
  d'ikoro-labs se taguent tous `<plugin>--v<X.Y.Z>`, et le test du catalogue exige cette forme
  (ikoro-labs/forge#7).
- La CI n'active plus le cache de uv, qui n'avait rien à garder (#34, #32). Rien n'en change pour un
  projet consommateur.

### Gestes humains

- Aucun geste n'est obligatoire à la montée, en dehors des deux commandes de **Monter de version**.
- Pour qu'un agent retire l'étiquette en mode auto, le poste doit l'autoriser : sur un poste, le
  classifieur du mode auto a refusé `gh pr edit --remove-label` comme écriture externe, et des
  règles `Bash(gh pr edit:*)` et `Bash(gh issue edit:*)` ont levé ce refus.
- Une étiquette `needs-your-attention` posée par `/forge:feature-build` avec un simple commentaire
  de PR passe pour humaine et reste : l'humain la retire.

### Restés dehors

- Dire en toutes lettres qu'une raison déjà marquée `retirée` ne compte plus quand un humain repose
  l'étiquette, et reconnaître les étiquettes que `/forge:feature-build` pose par commentaire : deux
  NOTE du verdict de la #46, sans ticket. L'erreur va dans le sens prudent, l'étiquette reste.
- Une entrée réelle de `SessionStart`, dans une session `claude --plugin-dir` lancée depuis un
  projet jetable : pas encore faite.

## [1.4.0] - 2026-10-21

Une seule session par dépôt (ikoro-labs/forge-archive#4, en partie) : une session sait quelles autres
sessions vivent sur son dépôt, le relais de la passation refuse d'en lancer une à côté, et la
session de fond cède à la session interactive de l'humain. Le juge rend un verdict lisible pour une
PR sans ticket ou sans critère livré (#24, #28, #29). Le plugin gagne une icône (#26) et une
licence MIT (#31).

### Hooks

- `handoff_header.py sessions <repo>`, nouveau (#4) : lit le registre que Claude Code tient de ses
  sessions (`~/.claude/sessions/*.json`), garde les processus vivants (sous Linux, `procStart` doit
  être l'heure de départ du processus), les sessions dont le dossier se résout sur la même copie
  principale (`.git` puis `commondir`, worktrees compris), et laisse de côté la session appelante
  (`CLAUDE_PID`, le processus qui lance la commande, et leurs ancêtres). Il imprime
  `pid kind name status cwd` par autre session et sort en 0 si aucune ne vit, en 6 sinon ; une
  entrée illisible compte pour vivante. Sous Windows, `procStart` n'est pas comparé : un pid vivant
  y vaut session vivante. Éprouvé sous Linux sur le registre réel d'un poste (Claude Code 2.1.306,
  registre écrit par 2.1.305) ; sous Windows, seulement par la suite en CI.
- `handoff_relay.py` refuse en code 6 quand une autre session du dépôt vit : il imprime les
  sessions trouvées sur stderr, ne lance aucun successeur, ne touche pas au compteur du jour et ne
  ferme pas la session appelante. Le code 5 passe avant lui, et un registre illisible vaut refus en
  6. Le `README.md` gagne la table des codes du relais (0 à 6).
- Le successeur d'une passation ne compte plus la session qui la lui passe : le relais, comme
  `handoff_header.py set-successor`, écrit `auteur` (`CLAUDE_CODE_SESSION_ID`) à côté de
  `successeur`, et `sessions` laisse de côté l'`auteur` d'une passation du projet qui nomme la
  session appelante successeur, encore vivant pendant `CLAUDE_HANDOFF_CLOSE_DELAY`. `auteur`
  n'entre pas dans les clés requises : une passation écrite avant 1.4.0 reste valide, mais n'exclut
  personne.
- La session de fond cède à la session interactive de l'humain. `handoff_header.py self` imprime
  le type que le registre note pour la session appelante et son identifiant (`?` quand il manque).
  `handoff_trigger.py yield <identifiant>`, lancé par la session de fond, imprime sa conduite : ne
  plus rien lancer, laisser finir ses agents sous `CLAUDE_HANDOFF_DRAIN_MINUTES`, écrire sa
  passation au même format qu'au seuil, la donner à la session interactive par `set-successor`,
  lui envoyer le chemin par `SendMessage`, puis lancer `handoff_relay.py --yield [--force]
  <passation>`. Celui-ci fait les contrôles d'agents du relais (code 5) et sa fermeture
  (`claude stop` puis `claude rm` après `CLAUDE_HANDOFF_CLOSE_DELAY`), sans lancer de session ni
  passer par le code 6 ; il refuse en code 1 une session interactive ou un `CLAUDE_PID` inconnu, en
  code 2 une passation sans `successeur`. Sans argument, `handoff_trigger.py` reste le hook qui ne
  bloque jamais. Seul le type `bg` cède ; un type inconnu fait s'arrêter la nouvelle session.
  `self`, `yield`, l'exclusion de l'`auteur` et `--yield` n'ont tourné que dans la suite, sous
  Linux et dans la CI Windows, `--yield` contre un faux `claude` : qu'un vrai `claude rm` retire
  l'entrée du registre n'a été vérifié sur aucun poste, et le parcours interactif entier n'a été
  éprouvé sur aucun système.
  Les types du registre ont été lus sous Linux, sur trois entrées réelles toutes `bg`, et dans le
  code de Claude Code 2.1.306, qui écrit `interactive` par défaut.
- Le `README.md` énonce la règle dans une section **Règles communes** (une session par dépôt, le
  premier geste, qui cède à qui), et décrit `--yield` dans **La passation drainée**.

### Agents

- `qc-conf` : une PR qui ne lie aucun ticket (une montée Dependabot, une montée d'épingle) a une
  seule ligne `SPEC: none (<raison>)`, la raison disant contre quoi elle a été jugée, sans
  s'accrocher à une PR ou un ticket qu'elle ne cite pas (#24). Une PR qui cite des tickets sans en
  livrer aucun critère, comme une PR de publication, se juge contre les règles du projet qui
  décrivent ce type de PR (clés `domain-rules`, `git-rules`) et rend
  `SPEC: none (<règles>: <n> critères couverts, <n> partiels, <n> absents)` (#28). Les juges des
  PR #39 à #42 ont rendu ces deux formes, celui de #39 la seconde ; c'était un `qc-conf` antérieur
  à 1.4.0, à qui l'appelant dictait la consigne. Aucun juge ne l'a encore lue dans son propre
  `qc-conf.md`.

### Skills

- `/forge:qc`, `scripts/parse_output.py verdict` : il admet la ligne unique `SPEC: none (<raison>)`
  et refuse une raison vide ou un `none` mêlé à des lignes `#<ticket>` (#24). Chacun de ses trois
  refus sur `SPEC:` dit ce qui est faux dans la ligne et nomme les deux formes admises, pour que la
  relance du juge suffise (#29). Éprouvé par la suite de tests, sous Linux et dans la CI Windows.
  Sous Linux, il a lu les verdicts `SPEC: none` des revues des PR #39 à #41, lancé à la main depuis
  `main` : l'usine de ce dépôt chargeait encore un parseur qui refuse cette forme.
- `/forge:feature-build`, étape 0, point 5 : « Un seul passage par feature » devient « Une seule
  session par projet ». La session lance `handoff_header.py sessions .`, puis `ListAgents`. Une
  session interactive face à des sessions toutes `bg` leur demande de céder (`yield`) et reprend
  depuis leur passation (`successor-ok`, puis le sauvetage) ; dans tout autre cas, elle envoie sa
  demande à la session en place par `SendMessage` et s'arrête ; une session de fond à qui l'on
  demande de céder draine puis s'arrête (#4). Pas encore éprouvé dans un vrai passage.

### Tests

- `tests/test_handoff.py` : `sessions` sur un registre factice, `HOME` et `USERPROFILE` isolés (pid
  vivant, pid mort, worktree, autre dépôt, entrée illisible, session appelante, et `procStart`
  différent, sous Linux seul par `skipUnless`) ; le code 6 du relais ; `auteur`, l'exclusion du
  prédécesseur et `CLAUDE_HANDOFF_DIR` ; `self`, `yield` et `--yield`, dont une troisième session
  qui ne voit plus la session de fond qui a cédé.
- `tests/test_parse_output.py` : les formes de `SPEC: none` et les deux formes nommées par chaque
  refus.
- `tests/test_plugin_content.py` : les consignes de `qc-conf`, le point 5 de `feature-build`, la
  règle du `README.md`, aucun projet ni aucune personne nommés sous `plugins/forge/`, l'icône (un
  PNG carré de 512 à 2048 px, de moins de 2 Mo) et la licence (`LICENSE` MIT à la racine,
  `"license": "MIT"` dans `plugin.json`).
- La suite compte 158 tests sous Linux, dont 3 sautés, propres à Windows. Elle tourne en CI sous
  Linux et sous Windows.

### Gestes humains

- Aucun geste n'est obligatoire à la montée, en dehors des deux commandes de **Monter de version**.
- Monter l'épingle hors d'un `/forge:feature-build` actif, comme le veut déjà **Monter de
  version**, et plus largement hors d'une chaîne de relais en cours : une passation écrite par
  1.3.0 n'a pas d'`auteur`, et son successeur en 1.4.0 s'arrêterait derrière son prédécesseur
  encore vivant.
- L'humain qui ouvre une session interactive sur un dépôt où une session de fond agit la voit
  drainer puis s'arrêter, au plus `CLAUDE_HANDOFF_DRAIN_MINUTES` minutes. Pour la suivre sans
  l'arrêter : `claude attach <id>`, l'identifiant étant celui que donne `claude agents`.

### Restés dehors

- Le hook `SessionStart` qui nomme, au démarrage d'une session, les autres sessions vivantes du
  dépôt (PR #38, critère 5 de #4) : ACCEPT, en attente d'une fusion humaine, car il touche
  `plugins/forge/hooks/hooks.json`, chemin protégé. #4 n'est donc livré qu'en partie : critères 1
  à 4, 6 et 7.
- Ne plus activer le cache de uv dans la CI (PR #34, #32) : ACCEPT, en attente d'une fusion
  humaine, car elle touche `.github/`, chemin protégé. Rien n'en change pour un projet consommateur.

## [1.3.0] - 2026-10-21

Ce que coûte chaque rôle : un niveau de modèle et un effort de réflexion par agent
(ikoro-labs/forge-archive#10, #12), un audit des jetons pour en mesurer l'effet (#14), et la sortie d'une
suite de tests qui passe raccourcie (#19). Avec trois correctifs : la fermeture d'une session
Windows depuis un job (#3), le dossier de la passation depuis un worktree, et la protection d'une
branche lue dans ses rulesets (#17).

### Agents

- Chaque agent fixe dans son front matter un niveau de modèle et un effort de réflexion, le moins
  cher qui fait le travail : `qc-gate` en `haiku`, effort `low` ; `coder` en `sonnet`, effort
  `medium` ; `qc-conf` et `product-owner` en `opus`, effort `medium` ; `staff-engineer` en `opus`,
  effort `high`. En 1.2.0, `qc-gate`, `coder` et `qc-conf` prenaient le modèle de la session,
  `staff-engineer` et `product-owner` le niveau `fable`. Un niveau est un alias : chaque poste le
  fait pointer vers le modèle et le fournisseur de son choix (`ANTHROPIC_DEFAULT_<NIVEAU>_MODEL`,
  `ANTHROPIC_BASE_URL` vers une passerelle), sans toucher au plugin. `CLAUDE_CODE_EFFORT_LEVEL`,
  posé sur un poste, l'emporte sur l'effort. Le gain n'est pas mesuré, et aucune usine servie par
  un autre fournisseur n'a été essayée.
- `qc-gate` démarre sans `CLAUDE.md` (`omitClaudeMd: true`, Claude Code 2.1.271 et plus) et lit ses
  portes dans `docs/agents/usine.md` par Bash. Le champ retire aussi le `~/.claude/CLAUDE.md` du
  poste et le `CLAUDE.local.md`.
- `qc-gate`, sonde « Contextes obligatoires » : elle prend l'union des checks exigés par les
  rulesets actifs de la base (`rules/branches/<base>`) et par l'ancienne protection de branche.
  Elle ne lisait que la seconde, qui rend `contexts: []` pour une branche que seul un ruleset
  protège : chaque revue sur une telle base rendait un `FAIL` à tort. Les deux lectures ont été
  lancées à la main sur ce dépôt ; la sonde modifiée n'a pas encore tourné dans une vraie revue.
- `qc-gate`, sondes des tests sautés : sur une sortie raccourcie par `trim_output.py`, elle relève
  les sauts dans le journal que nomme la première ligne, puisque l'agent ne reçoit plus le milieu
  de la sortie.

### Hooks

- `trim_output.py` (`PostToolUse`, sur `Bash`), nouveau : pour une commande que nomme la clé
  `trimmed-command` de `docs/agents/usine.md`, une sortie réussie de plus de 60 lignes est écrite
  en entier dans `~/.claude/hooks/state/trimmed/` (les 20 journaux les plus récents gardés, jamais
  celui qui vient d'être écrit), et l'agent n'en reçoit que les 20 dernières lignes de chaque flux,
  avec le chemin du journal. Sans la clé, rien ne change. Une commande en échec arrive entière, à
  condition que son code de sortie le dise : derrière un tube ou suivie de `; echo fini`, une suite
  en échec sort à 0 et se raccourcit. Le hook observe : toute erreur sort à 0, la sortie d'origine
  intacte. Éprouvé avec Claude Code 2.1.305 sous Linux, dans une session `claude -p --plugin-dir` ;
  pas encore sous Windows ni dans une session interactive. Une commande lancée par l'outil
  `PowerShell` n'est pas raccourcie.
- `handoff_trigger.py` : la passation se range sous le nom de la copie principale du dépôt, lu dans
  le fichier `.git` du worktree et son `commondir`, sans lancer git. Depuis un worktree, elle se
  rangeait sous le nom du worktree. Un sous-module garde son propre nom. Les passations déjà mal
  rangées restent où elles sont.
- `handoff_relay.py` : sous Windows, une commande que le relais lance et attend reste dans le job de
  la session ; seul le lancement du successeur demande encore à en sortir, avec son repli. Dans un
  job qui interdit d'en sortir (celui d'un runner GitHub, ou celui d'une session dont le lancement
  a dû se replier), `CreateProcess` levait `OSError` : `--exit-console` mourait au `taskkill` d'une
  session sourde à `/exit`, et `--close` sautait chaque commande de son plan sans fermer la
  session. Éprouvé sur les runners Windows de GitHub seulement.

### Skills

- `/forge:audit-jetons` et son script `scripts/token_audit.py`, nouveaux : les jetons dépensés par
  chaque rôle sur un projet, par modèle et par effort, lus dans les journaux que Claude Code écrit
  déjà (`~/.claude/projects/`, ou `CLAUDE_CONFIG_DIR`), worktrees compris. `--depuis` et `--jusqua`
  bornent la période, `--coupure` compare un avant et un après en jetons par lancement d'agent.
  Aucun prix. Claude Code note la plupart des réponses de sous-agents avant leur fin : leur sortie
  est sous-comptée, et le rapport les compte dans une colonne « Sortie partielle ». Le format des
  journaux n'est pas documenté ; il a été lu dans Claude Code 2.1.302 à 2.1.305. Seul le script a
  tourné sur un vrai poste, sous Linux ; le skill n'a été lancé dans aucune session.

### Tests

- `tests/test_plugin_content.py` : le niveau et l'effort de chaque agent, `omitClaudeMd` sur
  `qc-gate` seul, et la sonde de protection qui lit les rulesets.
- `tests/test_trim_output.py` (12 tests, dont la lecture du journal d'une sortie raccourcie par
  `qc-gate`) et `tests/test_token_audit.py` (16 tests), sur des sorties et des journaux factices,
  `HOME` et `USERPROFILE` isolés.
- `tests/test_handoff.py` : la passation d'une session lancée dans un worktree, rangée sous le
  projet ; sous Windows, `CloseInAJob`, un plan de fermeture qui s'exécute dans un job sans
  `JOB_OBJECT_LIMIT_BREAKAWAY_OK`.
- `tests/test_guard_readonly.py` : `guard_readonly` laisse passer la lecture des rulesets.
- La suite tourne en CI sous Linux et sous Windows, avec `claude plugin validate` sur la
  marketplace et le plugin (`.github/workflows/tests.yml`).

### Gestes humains

- Aucun geste n'est obligatoire à la montée, en dehors des deux commandes de **Monter de version**.
- Un projet qui veut raccourcir la sortie de sa suite de tests ajoute la clé `trimmed-command` à
  son `docs/agents/usine.md` (gabarit `templates/usine.md`).
- Un poste servi par une passerelle ou un autre fournisseur fait pointer chaque niveau
  (`ANTHROPIC_DEFAULT_HAIKU_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`)
  vers un modèle qu'il sert.

### Restés dehors

- Le cache d'une heure pour le coder (`experimental.cacheTtl: 1h` dans son front matter) : une
  écriture dans ce cache coûte 2 fois le prix d'entrée, contre 1,25 fois pour celui de 5 minutes,
  et aucun journal de ce poste ne montre un lancement de `forge:coder` qui en prouverait le gain.
  Abandonné.
- Le hook de routage des modèles (PR #6) : fermé, remplacé par le niveau de chaque agent (#11).
- Une seule session par projet (#4) : ouvert, pas commencé.

## [1.2.0] - 2026-10-20

La passation drainée sous Windows (ikoro-labs/forge-archive#3) : elle ne tournait que sous Linux, parce que
le relais était un script bash et que les questions de processus lisaient `/proc`.

### Hooks

- `handoff_relay.py` remplace `handoff_relay.sh` : même usage, mêmes codes de sortie (1 à 5),
  mêmes variables, mêmes messages, en Python de la bibliothèque standard lancé par
  `uv run --no-project --quiet python`. La fermeture différée de la session appelante est une copie
  détachée du relais (`--close`), sortie du job de la session sous Windows quand il le permet. Sous
  Windows, l'exécutable `claude.exe` est préféré au lanceur `.cmd`, pour qu'aucun `cmd.exe` ne
  relise le prompt du successeur ; une session interactive y reçoit `/exit` dans sa console
  (`--exit-console`), et n'est tuée qu'au bout de 15 secondes, le relais coupant alors lui-même le
  suivi de la souris : essayée tuée d'emblée par `taskkill /F`, elle avait laissé chaque mouvement
  de souris s'écrire dans le shell. Une session de fond est arrêtée par `claude stop` puis
  `claude rm`, ses fenêtres `claude attach` fermées d'abord. `CLAUDE_HANDOFF_TERMINAL` accepte
  `wt.exe`. Le nom du compteur du jour remplace aussi `\` et `:` d'un chemin Windows.
- Le relais reconnaît une session interactive au registre de Claude Code
  (`~/.claude/sessions/<pid>.json`, `"kind": "interactive"`) : elle porte elle aussi
  `CLAUDE_CODE_CHILD_SESSION=1` (Claude Code 2.1.304), et la 1.1.0 la traitait en session de fond.
- `feature` ne compte que ses identifiants `F-NNNN` : essayé sous Windows, un « aucune (demande
  ponctuelle) » avait donné au successeur le seuil de 400 k. La consigne du hook le dit.
- `CLAUDE_HANDOFF_CLOSE_DRY_RUN` : `0`, `false`, `no`, `off` ou vide laissent le relais à blanc
  coupé ; toute valeur non vide l'allumait, `0` compris.
- `handoff_header.py` : `process_alive`, `process_start`, `parent_pid` et `ancestors` répondent par
  `/proc` sous Linux et par l'API Win32 (`ctypes`) sous Windows ; ailleurs, un processus compte pour
  vivant. Le verrou d'un worktree d'agent est lu avec ou sans heure de départ : Claude Code n'en
  écrit pas sous Windows (`claude agent <nom> (pid N)`), et l'ancienne expression, qui l'exigeait,
  aurait compté pour vivant tout verrou, même d'un agent mort ou d'une autre session. Sans heure, un
  pid vivant vaut détenteur.
- `handoff_trigger.py` : la consigne lance le relais par `uv run --no-project --quiet python`, et
  la liste des agents en vol passe par `handoff_header.ancestors`. Le prompt du successeur ne cite
  plus `python3`, qui sous Windows est un alias du Microsoft Store.
- `CLAUDE_HANDOFF_DIR` : dossier des passations, `~` et variables développés, par défaut
  `~/.claude/hooks/state/handoffs` comme avant. Essayé sur un poste Windows sous politique gérée :
  le hook s'est déclenché, mais la session n'a pas pu écrire la passation, l'outil Write étant
  refusé sous tout dossier `.claude` ; le relais a répondu `handoff document not found`. Les
  marqueurs et compteurs, écrits par les hooks eux-mêmes, restent dans `~/.claude/hooks/state`.

### Tests

- `tests/test_handoff.py` : le relais tourne sous Windows comme sous Linux (seul git est requis),
  sur un `claude` simulé en Python ; verrou lu avec et sans heure de départ ; processus vivant,
  fini, et ancêtres d'un enfant ; détenteur mort qui libère son worktree ; passation sous
  `CLAUDE_HANDOFF_DIR`, variable développée, marqueur resté dans l'état ; plan de fermeture d'une
  session interactive et d'une session de fond à blanc, registre des sessions ; `feature` en prose
  à 150 k ; `DRY_RUN=0` coupé ; sous Windows, `/exit` tapé dans la console cachée d'une session
  simulée, et session sourde à `/exit` tuée. Les tests isolent `USERPROFILE` comme
  `HOME`, sans quoi sous Windows ils écrivaient dans le vrai `~/.claude/hooks/state`, et ne passent
  plus aux relais les variables `CLAUDE_` de la session qui les lance. `enterContext` (Python 3.11)
  cède la place à `patch.start` : la suite tourne sous le Python 3.10 que `uv` peut choisir.

### Gestes humains

- La règle de permission qui autorisait `bash …/hooks/handoff_relay.sh` vise désormais
  `uv run --no-project --quiet python …/hooks/handoff_relay.py` (README, **Gestes humains**, point 5).

## [1.1.0] - 2026-10-20

La passation drainée d'une session à sa limite de contexte (ikoro-labs/forge-archive#3), décidée dans
un projet qui utilise forge, puis adoptée par les autres. Le plugin devient la source des scripts qui vivaient en copie dans `~/.claude/hooks`.

### Hooks

- `handoff_trigger` (`UserPromptSubmit`, `PostToolUse`) : au seuil de contexte, la session ne
  lance plus rien et attend ses agents (drainage, point A) ; plafond dur au seuil plus 35 k jetons
  ou 45 minutes après le premier avis, avec la liste `sauvetage`. Seuil
  `CLAUDE_SESSION_TOKEN_LIMIT`, 150 k par défaut. Filtre `agent_id` : un sous-agent n'est jamais
  averti. Le hook se tait tant que `~/.claude/settings.json` déclare encore une copie hors
  plugin, pour qu'aucun avis n'arrive deux fois. `hooks_version` de l'en-tête est lu dans
  `plugin.json`. Le skill `handoff` de l'utilisateur n'est cité que s'il existe. La consigne
  rappelle qu'un agent relancé par `SendMessage` ne reverrouille pas son worktree et doit figurer
  sous `en_vol`.
- `handoff_relay.sh` : refuse le relais (code 5) tant qu'un agent de la session est vivant ou que
  `en_vol` est non vide, `--force` seulement avec `sauvetage` non vide (point B) ; plafond du jour
  par projet (code 3), compteur avancé après les contrôles seulement ; écrit `successeur` et
  `seuil` dans l'en-tête, arrête puis supprime la session fermée (`claude stop`, `claude rm`,
  point C). Le successeur démarre à 400 k quand la passation porte une feature, à 150 k sinon
  (point F). Fenêtre de terminal optionnelle par `CLAUDE_HANDOFF_TERMINAL`, aucun terminal câblé ;
  nom de session horodaté.
- `handoff_header.py` : valide le front matter de la passation (point E : onze clés), écrit le
  successeur, dit à une session de relais si elle est le successeur désigné (code 3 sinon), liste
  les worktrees d'agents dont le processus tient encore le verrou.
- État et passations hors du cache du plugin : `~/.claude/hooks/state/`, passations sous
  `handoffs/<projet>/<date>-r<N>.md`.

### Agents

- `forge:coder` : un commit Conventional Commits poussé par critère vert, jamais « wip » (point
  D) : ce qui est poussé se reprend quand la session qui l'a lancé se ferme.

### Tests

- `tests/test_handoff.py` : en-tête invalide (2), agent vivant de la session (5) et agent d'une
  autre session ignoré, `en_vol` (5), `--force` sans `sauvetage` (5), plafond du jour (3) sans
  mouvement du compteur, seuil 400 k avec feature et 150 k sans, même hérité de 400 k, étapes
  drain et hard, copie hors plugin, relais à blanc (`CLAUDE_HANDOFF_CLOSE_DRY_RUN=1`) et relais
  réel sur un `claude` simulé.

## [1.0.0] - 2026-10-19

Première version : la partie générique de l'usine Forge telle qu'elle vivait dans les projets qui
l'utilisaient, plus les capacités que l'un d'eux avait et que Forge n'avait pas. Tout ce qui est propre à un
projet en est sorti : chaque élément qui en dépendait lit désormais la clé correspondante de
`docs/agents/usine.md`, et une clé absente rend l'étape « sans objet », jamais `PASS`.

### Agents

- `forge:coder` : un ticket jusqu'à sa PR, en test-first et dans son worktree, sans la relire ni
  la fusionner ; bloc `RESULT` final, `BLOCKED` sur toute ambiguïté ; mode sync pour une PR en
  retard sur sa base, mode correction pour les `BLOCKER` d'un verdict.
- `forge:qc-gate` : le mesureur de la revue, sondes dans un ordre fixe, rejeu dans une copie de la
  tête, `NOT RUN` jamais `PASS`.
- `forge:qc-conf` : le juge, deux axes (standards, spec du ticket), constats `BLOCKER`,
  `MINOR`, `NOTE`, deux tours au plus.
- `forge:staff-engineer` et `forge:product-owner` : les décideurs délégués de la technique et du
  produit, en lecture seule, qui tranchent selon la matrice de décision du projet ou disent quelle
  case réserve la question à un humain.

### Skills

- `/forge:qc` : revue en deux temps, verdict et rapport postés sur la PR, fusion sur ACCEPT, chemins
  protégés laissés à un humain.
- `/forge:feature-build` : l'aval d'une feature, chaque ticket prêt confié à `forge:coder`, revue
  par `/forge:qc`, questions passées aux décideurs délégués.
- La chaîne des features, de l'idée à la livraison : `/forge:feature-new`,
  `/forge:feature-brainstorm`, `/forge:feature-frame`, `/forge:feature-spec`,
  `/forge:feature-design`, `/forge:feature-accept` (réservé à un humain), `/forge:feature-verify`,
  `/forge:feature-close` et `/forge:feature-status`.
- `forge:codebase-design`, `forge:domain-modeling` et `/forge:improve-codebase-architecture`,
  adaptés de mattpocock/skills (licence dans `plugins/forge/THIRD_PARTY_NOTICES.md`).

### Hooks

- `guard_git` : la partie générique (commit ou push sur `main`, force-push, `branch -D`,
  `reset --hard`, `clean -f`, `--no-verify`, fusion sans checks verts, ticket en `Refs` fermé par
  la fusion).
- `guard_coder` : filtré sur `agent_type == "forge:coder"`, refuse au coder la fusion, la revue,
  l'édition des tickets et le skill `qc` sous ses deux noms, `forge:qc` et `qc`.
- `guard_readonly` (G1) : les juges et les décideurs ne modifient rien ; liste blanche pour
  `forge:qc-conf` et les décideurs, liste noire pour `forge:qc-gate`, étendues par les clés
  `readonly-agent` et `readonly-command`.
- `guard_pause` (G7) : tant que `.claude/PAUSED` existe, aucun agent n'est lancé.
- `after_write` : aucun tiret cadratin au-delà de la tolérance du fichier (clé
  `em-dash-allowances`).

### Scripts, gabarits et tests

- `scripts/parse_output.py` (G19) : lit le `RESULT` du coder et le verdict du juge, et dit
  exactement ce qui ne va pas, pour une seule relance.
- `templates/usine.md` : le gabarit de `docs/agents/usine.md`, avec chaque clé que lisent le plugin
  et ses hooks.
- `templates/adr.md` et `templates/features/` (protocole, idée, séance, cadrage, spec, design,
  recette, livrée).
- `tests/` : les tests des hooks, du parseur et de la configuration, et le test des noms cités
  (G9) : tout `forge:<nom>` cité dans le plugin désigne un agent ou un skill qui existe.

### Restés hors du plugin

- G3, G4, G5, G8 et G15 : encore en cours dans le projet qui les porte ; ils arriveront par une
  montée de version.
- G6 et G18 : demandent une décision qui n'est pas prise.
- G13 : demande un accès réseau que les hooks n'ont pas.
- Le contrôleur `factory/` d'un projet, son contrat de revue d'architecture
  (`docs/architecture/reviews/<FEATURE-ID>.json`) et `python -m factory prepare` : propres à ce projet.
- Les skills de domaine, l'arbitre de domaine, `run-app` et les skills propres à un projet :
  chacun applique les règles de son projet. Un projet les garde dans `.claude/` et les désigne par les clés `domain-skill`,
  `domain-rules`, `review-grid` et `domain-arbiter`.
- Les gardes de CI, `scripts/features.py`, `ci_local`, le modèle de PR et les hooks git : lus par la
  CI, GitHub ou git, qui ne chargent aucun plugin ; ils restent en copie dans chaque dépôt.
- Les gestes de propriétaire de `guard_git` (runners, variables, protection de branche, Dependabot)
  : propres à chaque projet, dans ses hooks de `.claude/settings.json`.
- ruff et Prettier après une écriture : chaque projet formate dans ses propres hooks.
