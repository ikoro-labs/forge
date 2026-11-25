---
feature: F-0002
document: recette
statut: accepte
accepte_par: ikoro-labs
accepte_le: 2026-11-25
destinataires: ikoro-labs
version: c45a2da (tête de main, non publiée ; la dernière version publiée est forge 1.21.0)
base: c45a2da
date: 2026-11-25
---

# F-0002 : recette

Chaque critère de la spec, relié à ce qui le prouve. Un critère sans test est un critère non tenu.

Les tests de la feature tournent dans neuf fichiers de `tests/`, lancés le 2026-11-25 vers 00:20 UTC
sur `c45a2da`, sous le lanceur borné :
`bounded_run.py -- uv run --no-project --quiet --with pytest==9.2.0 python -m pytest tests/test_stack_check.py tests/test_stack_probe_content.py tests/test_never_weaken.py tests/test_after_write.py tests/test_after_write_journal.py tests/test_architecture_probe_content.py tests/test_recurring_findings.py tests/test_rule_base_content.py tests/test_factory_slo_refus.py --junitxml=<rapport>`.
Résultat : 181 passent, 2 sont ignorés (sous Linux : un shim `.cmd` et l'objet job Win32
n'existent que sous Windows ; aucun des deux n'est cité par un critère), 0 échec. Un test est relié à
un critère par son nom (`test_aN_...`, `test_f0002_aN_...`) ou par sa docstring (`F-0002 A<n>`) ;
chaque critère de A1 à A35 a au moins un test, et tous ses tests passent dans ce rapport.

## 1. Critères

Les fichiers sont sous `tests/`. Quand un critère a plusieurs tests, le premier est nommé et le
nombre total suit entre parenthèses.

| # | Critère (spec) | Test qui le prouve | PR | Résultat |
|---|---|---|---|---|
| A1 | une liste `stack` bien formée ne sort aucun `INVALID` | `test_stack_check.py::test_a1_well_formed_lines_give_no_invalid_and_a_lock_without_additions_says_none` | #332 | passe |
| A2 | une ligne d'écosystème inconnu ou de moins de trois champs sort `INVALID` avec son numéro | `test_stack_check.py::test_a2_a_malformed_line_is_invalid_with_its_number_and_never_completed` | #332 | passe |
| A3 | clé `stack` absente : la sonde rend « sans objet », jamais `PASS` | `test_stack_probe_content.py::test_an_absent_key_is_not_applicable_and_never_pass` (4) | #339 | passe |
| A4 | les noms pypi se comparent sans casse ni distinction `-`, `_`, `.` | `test_stack_check.py::test_a4_pypi_names_are_the_same_whatever_the_case_dash_underscore_or_dot` (2) | #332 | passe |
| A5 | un paquet direct absent de la liste sort `UNLISTED` avec la ligne à écrire | `test_stack_check.py::test_a5_a_direct_dependency_missing_from_the_list_is_unlisted_with_the_line_to_write` | #332 | passe |
| A6 | une source vide sort `NO SOURCE` | `test_stack_check.py::test_a6_a_listed_dependency_with_an_empty_source_is_no_source` | #332 | passe |
| A7 | un paquet listé avec sa source sort `OK`, une ligne ajoutée sort `ADDED` | `test_stack_check.py::test_a7_a_listed_dependency_with_a_source_is_ok_and_each_added_list_line_is_added` | #332 | passe |
| A8 | une dépendance indirecte n'est pas comparée | `test_stack_check.py::test_a8_an_indirect_dependency_is_not_compared` | #332 | passe |
| A9 | le chemin de `stack` se lit sur la base, la liste sur la tête | `test_stack_check.py::test_a9_the_path_is_read_on_the_base_and_a_head_without_the_file_is_an_empty_list` | #332 | passe |
| A10 | `UNLISTED` ou `NO SOURCE` : `BLOCKER` du juge qui cite la ligne à écrire | `test_stack_probe_content.py::test_an_unlisted_or_unsourced_package_is_a_blocker_that_cites_the_line_to_write` (3) | #339 | passe |
| A11 | verrou illisible, écosystème hors `lockfile`, `package-lock.json` sans racine : `INVALID` ou `NOT RUN`, jamais `OK` | `test_stack_check.py::test_a11_a_package_lock_without_its_root_entry_is_invalid` (3) | #332 | passe |
| A12 | `raised-entry` : une clé ajoutée est refusée, fichier et clé nommés | `test_never_weaken.py::test_f0002_a12_an_added_key_absent_from_the_removed_lines_is_refused_naming_file_and_key` (4) | #344 | passe |
| A13 | une clé passée de 3 à 4 est refusée, avec les deux nombres | `test_never_weaken.py::test_f0002_a13_a_count_raised_from_3_to_4_is_refused_naming_the_key_and_both_counts` (2) | #344 | passe |
| A14 | une clé retirée ou un nombre qui baisse passe | `test_never_weaken.py::test_f0002_a14_a_removed_key_or_a_lower_count_passes` (3) | #344 | passe |
| A15 | une clé seule compte 1 | `test_never_weaken.py::test_f0002_a15_a_lone_key_counts_1_so_an_added_lone_key_is_a_raise` | #344 | passe |
| A16 | `raised-entry` avec un paramètre sort `INVALID` | `test_never_weaken.py::test_f0002_a16_a_parameter_makes_the_entry_invalid_whatever_the_diff` (2) | #344 | passe |
| A17 | un lint qui échoue : code 2, message `lint-on-write: ... failed on ...` et fin de la sortie | `test_after_write.py::test_a_failing_lint_refuses_the_write_and_relays_the_output` | #330 | passe |
| A18 | au plus 20 lignes et 2000 octets relayés | `test_after_write.py::test_at_most_the_last_20_lines_are_relayed` (4) | #330 | passe |
| A19 | la fin de la sortie d'un `format-on-write` qui échoue est relayée | `test_after_write.py::test_a_failing_formatter_relays_the_end_of_its_output` (2) | #330 | passe |
| A20 | une ligne mal formée est ignorée, et le message le dit | `test_after_write.py::test_a_malformed_line_is_ignored_and_the_message_says_so` | #330 | passe |
| A21 | une commande au-delà du délai est tuée, l'écriture reste | `test_after_write.py::test_a_command_past_its_delay_is_killed_and_the_write_is_kept` (2) | #330 | passe |
| A22 | clé `lint-on-write` absente : rien ne tourne, « sans objet » | `test_after_write.py::test_the_template_says_what_an_absent_key_means` (2) | #330 | passe |
| A23 | un refus d'écriture entre au journal des refus, sans la commande ni la sortie | `test_after_write_journal.py::test_a_refused_lint_adds_one_line_with_the_fields_of_the_three_guards` (8) | #338 | passe |
| A24 | `guard-refusals` ne compte que les trois gardes | `test_factory_slo_refus.py::test_the_refusals_of_after_write_are_not_counted` (3) | #338 | passe |
| A25 | la sonde 17 lance la commande de la base sous le lanceur borné | `test_architecture_probe_content.py::test_probe_17_runs_the_command_of_the_base_under_the_bounded_runner` (3) | #348 | passe |
| A26 | clé `architecture-check` absente : « sans objet » | `test_architecture_probe_content.py::test_an_absent_key_is_not_applicable_and_never_pass` | #348 | passe |
| A27 | une sonde 17 en `FAIL` : `BLOCKER` au titre de F-15 | `test_architecture_probe_content.py::test_a_fail_is_a_blocker_under_f_15_that_cites_the_command_output` (2) | #348 | passe |
| A28 | retirer une règle de la carte des modules est refusé par `never-weaken` | `test_architecture_probe_content.py::test_the_module_map_example_entry_of_never_weaken_refuses_a_removed_rule` | #348 | passe |
| A29 | trois PR distinctes qui citent le même identifiant le font lister | `test_recurring_findings.py::test_three_distinct_prs_in_the_window_list_the_id_with_its_prs` | #349 | passe |
| A30 | deux PR, ou une PR sur plusieurs tours, ne suffisent pas | `test_recurring_findings.py::test_two_prs_or_one_pr_over_several_rounds_are_not_listed` | #349 | passe |
| A31 | un constat sans identifiant est compté à part | `test_recurring_findings.py::test_a_finding_without_an_id_is_counted_apart` | #349 | passe |
| A32 | une relance réécrit le commentaire par son marqueur, sans ouvrir de ticket | `test_recurring_findings.py::test_a_rerun_rewrites_the_comment_found_by_its_marker_and_opens_no_ticket` (2) | #349 | passe |
| A33 | clé `recurring-finding` ou `slo-issue` absente : « sans objet », rien d'écrit | `test_recurring_findings.py::test_an_absent_key_is_not_applicable_and_nothing_is_written` (3) | #349 | passe |
| A34 | le gabarit porte la ligne ruff (10, 5, 5, version épinglée, `--preview`), la carte des modules, un exemple de `stack`, aucun plafond de lignes | `test_rule_base_content.py::test_f0002_a34_the_ruff_line_sets_complexity_10_parameters_5_and_nesting_5` (6) | #350 | passe |
| A35 | la page dit chaque clé, le format de ses lignes, le message de refus et le geste de l'humain | `test_rule_base_content.py::test_f0002_a35_a_table_names_every_key_with_the_format_of_its_line` (9) | #339, #350 | passe |

Aucun critère ne se voit à l'écran : forge n'a pas d'interface, et la clé `product-source` est
absente de `docs/agents/usine.md`. La porte de la revue de bout en bout et la matrice sont donc sans
objet (clé `product-source` absente) ; aucune capture n'est reliée.

## 2. Vérification en environnement cible

**Pas encore déployable.** L'environnement cible de forge est une session de projet qui charge une
version publiée du plugin. Les changements de F-0002 sont sur `main` (PR #325 à #350, fusionnées du
2026-11-24 au 2026-11-25), mais aucune version ne les porte encore : la dernière étiquette est
`forge--v1.21.0` (2026-11-23), et son cache ne contient ni `stack_check.py`, ni `recurring_findings.py`,
ni `lint-on-write` dans `after_write.py`, ni `raised-entry` dans `never_weaken.py` (lu le 2026-11-25).

Ce qui reste à faire pour le vérifier : publier la version suivante, monter l'épingle d'un projet
consommateur, y déclarer au moins `lint-on-write` et `stack`, puis voir un refus d'écriture et une
sonde 16 en marche. Rien de cela n'a été essayé : le dépôt forge lui-même ne déclare aucune des clés
`stack`, `lint-on-write`, `architecture-check` ni `recurring-finding`, ses sondes rendent donc
« sans objet ».

Le CI de la tête de `main` (`c45a2da`, run 45516059599) : `validate`, `lint` et
`tests (ubuntu-latest)` verts, `tests (windows-latest)` encore en cours à 00:25 UTC. Le run de
`b6e2727` (PR #349) est vert sur les quatre.

## 3. Monitoring en place

Les signaux du design (section 5) et du cadrage (section 4). Chacun existe dans le source et est gardé
par un test ; aucun n'a encore été vu en marche sur un projet (section 2).

| Métrique ou alerte | Où la voir | Vérifiée le |
|---|---|---|
| Lignes `OK`, `ADDED`, `UNLISTED`, `NO SOURCE`, `INVALID`, `NOT RUN` de la sonde 16 | tableau de `forge:qc-gate` (`plugins/forge/agents/qc-gate.md`, sonde 16), rapport de `forge:qc` sur la PR | 2026-11-25, dans le source et par `test_stack_probe_content.py` ; jamais en marche |
| `PASS`, `FAIL`, `NOT RUN` de la sonde 17 | tableau de `forge:qc-gate` (sonde 17) ; `BLOCKER` F-15 du juge | 2026-11-25, dans le source et par `test_architecture_probe_content.py` ; jamais en marche |
| Refus de `raised-entry` | sortie de `never_weaken.py`, sonde de `never-weaken` de `forge:qc-gate` | 2026-11-25, par `test_never_weaken.py` ; jamais en marche |
| Refus d'écriture, règle `lint-on-write` ou `format-on-write`, et fin de la sortie de l'outil | message de `after_write` dans la session de l'agent | 2026-11-25, par `test_after_write.py` ; jamais en marche |
| Une ligne par refus d'écriture, `guard` `after_write` | journal des refus, `~/.claude/hooks/state/refusals/<AAAA-MM-JJ>.jsonl` | 2026-11-25, par `test_after_write_journal.py` ; jamais en marche |
| `guard-refusals` limité aux trois gardes | rapport de `forge:slo` | 2026-11-25, par `test_factory_slo_refus.py` |
| Constat récurrent (un identifiant cité par trois PR distinctes) | commentaire de `recurring_findings.py` sur le ticket de la clé `slo-issue` | 2026-11-25, par `test_recurring_findings.py` ; sans objet sur forge (clé `recurring-finding` absente) |
| Constats du juge qui citent F-8, F-13, F-15, F-17 ou L-n, par PR jugée | verdicts de `forge:qc-conf` sur les PR | base du cadrage (2026-11-22) : 3 constats F-13 sur 303 `BLOCKER` et `MINOR`, 121 PR jugées ; pas remesurée, rien à mesurer avant la publication |

## 4. Écarts

Aucun critère sans test, aucun test rouge. Ce qui n'est pas tenu par cette recette, et où il se suit
(l'issue de suivi #291, qui reste ouverte jusqu'à la clôture) :

- **Pas encore déployé** (section 2) : la vérification en environnement cible attend la publication
  de la version qui porte F-0002 et la montée de l'épingle d'un projet consommateur.
- **La ligne ruff du gabarit n'a été essayée que sur forge** : elle y refuserait 88 fonctions
  existantes (C901 63, PLR0913 25), relevé de la PR #350 ; jamais sur un projet consommateur.
  `docs/regles-de-code.md` le dit.
- **Les deux tests ignorés sous Linux** ne portent aucun critère ; ils tournent sur
  `tests (windows-latest)` du CI.

## 5. Tickets

Les dix sous-issues de #291, toutes fermées, avec leur PR fusionnée :

| Ticket | Objet | PR | Fusionnée |
|---|---|---|---|
| #304 | `lockfiles.py` extrait de `lockfile_age.py` | #325 | 2026-11-24 01:24 UTC |
| #305 | un lanceur par clé dans `after_write` | #326 | 2026-11-24 01:52 UTC |
| #306 | `stack_check.py` (A1, A2, A4 à A9, A11) | #332 | 2026-11-24 11:55 UTC |
| #307 | `lint-on-write` (A17 à A22) | #330 | 2026-11-24 09:49 UTC |
| #308 | sonde 16 et `BLOCKER` du juge (A3, A10, A35 pour `stack`) | #339 | 2026-11-24 17:51 UTC |
| #309 | `raised-entry` (A12 à A16) | #344 | 2026-11-24 19:53 UTC |
| #310 | refus d'écriture au journal (A23, A24) | #338 | 2026-11-24 15:54 UTC |
| #311 | sonde 17 et `BLOCKER` F-15 (A25 à A28) | #348 | 2026-11-24 22:59 UTC |
| #312 | `recurring_findings.py` (A29 à A33) | #349 | 2026-11-24 23:36 UTC |
| #313 | base de règles du gabarit et page complète (A34, A35) | #350 | 2026-11-25 00:10 UTC |
