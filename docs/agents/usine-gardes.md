# Clés protégées de l'usine du dépôt forge

Les clés de `docs/agents/usine.md` qui bornent les pouvoirs de l'agent (ticket #345) : l'ensemble est
`SENSITIVE_KEYS`, dans `plugins/forge/hooks/usine.py`, et le gabarit
`plugins/forge/templates/usine.md` en dit la forme. Le plugin lit ce fichier tel que `origin/main` le
tient, jamais dans l'arbre de travail, et `usine.load` le fusionne avec `usine.md`, qui garde les clés
libres. Une clé libre écrite ici est ignorée et signalée ; une clé d'ici écrite dans `usine.md` l'est
aussi.

Ce fichier est un `protected-path` et a sa ligne dans `.github/CODEOWNERS` : aucun agent ne fusionne une
PR qui le change, et une PR est la seule façon d'y changer une ligne. Un changement de `usine.md`, lui,
est une PR ordinaire (décision de l'humain du 2026-11-24, `forge:staff-engineer`, ticket #345). Les clés
absentes et leur raison sont en fin de fichier.

## Personnes et décisions

- `accepting-human` : `kevin_simo | ikoro-labs`

L'autonomie des agents, ouverte par l'utilisateur de ce dépôt le 2026-11-20 : le modèle peut lancer
les skills de la chaîne des features, et leurs questions vont d'abord aux agents de décision.
Depuis le ticket #355, le modèle lance aussi `feature-accept` et `release` sous cette clé, et
`release-trigger` (dans `usine.md`) dit quand une version est due. Depuis le ticket #280, la clé est aussi
l'interrupteur de la fusion par `forge:qc` et de la publication : l'humain reprend la main sur ce dépôt en
retirant la ligne. Elle n'agit qu'une fois l'épingle montée à une version qui la lit (1.18.0 pour les skills,
1.19.0 pour la fusion et la publication, 1.22.0 pour `feature-accept` et `release`).

- `agent-autonomy` : `on`

## Rejeu et contrôles

La borne de toute suite et de toute sonde, lue par `plugins/forge/scripts/bounded_run.py` : la
mémoire (2000 Mo) et le délai (300 s) de chaque commande, puis le budget du poste entier, que
partagent les sessions, les sous-agents et les workers : 4096 Mo disponibles au moins, une charge à
1 min de 12 au plus, 2 workers au plus, et jusqu'à 300 s d'attente avant de renoncer. L'attente est
le choix de ce dépôt, que le ticket ne fixait pas.

- `run-limits` : `2000 | 300`
- `run-budget` : `4096 | 12 | 2 | 300`

## Plafond de PR par ticket

Un ticket tient en six PR au plus, ouvertes ou fusionnées (ticket #314, demandé par l'humain ; trois
jusqu'au 2026-11-27, quatre sur décision de l'humain, ticket #367, puis six le 2026-11-28, ticket #381). Le
garde `guard_pr_cap` refuse la septième, que le coder rend en `BLOCKED` ; l'étiquette `pr-cap-raised`, posée par
un compte de la clé `pr-cap-raiser`, relève le plafond à 6, ce qui ne change plus rien ici. Cette clé est absente
ici (voir « Clés absentes ») : on change le plafond par une PR. Le garde agit une fois l'épingle montée à la
version qui le publie.

Le plafond passe à six pendant la transition, parce que les tickets déjà publiés ne sont pas dimensionnés à la
découpe : sur MeridianRe depuis le 2026-11-23, 10 tickets sur 19 ont atteint trois PR et 4 relèvements ont été
demandés et tous accordés (ticket #340), un geste humain qui ne filtre rien. Il redescendra à trois quand les
tickets seront dimensionnés à la découpe, ce que `forge:feature-design` fait désormais pour ceux qu'il publie
(ticket #381). Une PR de moins de 50 lignes (ajouts plus suppressions) ne compte
pas : c'est la clé `ticket-pr-cap-small`.

Le plafond ne compte que les PR créées à partir du 2026-11-23 (demande de l'humain du 2026-11-23) : des
tickets en cours dans des projets de l'humain avaient déjà dépassé trois PR avant le plafond, et les PR
d'avant cette date ne comptent pas.

- `ticket-pr-cap` : `6`
- `ticket-pr-cap-small` : `50`
- `ticket-pr-cap-since` : `2026-11-23`

Les PR d'entretien de l'usine (la montée de l'épingle, la PR de version) n'ont rien à voir avec le ticket
qu'elles citeraient : leur titre `chore(pin):` ou `chore(release):` les sort du compte (décision de l'humain du
2026-11-25, ticket #314), et elles ne citent aucun ticket.

- `ticket-pr-cap-exempt` : `chore(pin)`
- `ticket-pr-cap-exempt` : `chore(release)`

## Objectifs de service

Les objectifs de départ de l'usine (ticket #76), lus par `plugins/forge/scripts/factory_slo.py` sur 30
jours glissants. L'humain a retenu le 2026-11-16 de mesurer pendant 30 jours sans rien bloquer :
chaque action de budget est `alert`, jamais `human-merge` ni `feature-freeze`. Les cibles sont à
réviser à la date de `slo-review-date` (dans `usine.md`), sur le rapport des SLO ; changer une valeur reste
une décision de l'humain. Le 2026-11-24, l'humain a choisi des cibles qui visent l'optimum, même hors
d'atteinte ; les deux durées (1 h) sont la recommandation du `forge:staff-engineer`, appuyée sur le
repère « moins d'un jour » du groupe le plus rapide de DORA. `tokens-per-merge` n'a pas de ligne : sa
cible n'est pas fixée.

- `slo` : `accept-round-1 | >= 99 % | 30`
- `slo` : `lead-time p90 | <= 1 h | 30`
- `slo` : `release-lag p90 | <= 1 h | 30`
- `slo` : `escaped-defects | <= 1 % | 30`
- `slo` : `change-failure | <= 1 % | 30`
- `slo` : `human-touch | <= 1 % | 30`
- `slo` : `main-green | >= 100 % | 30`
- `slo` : `judge-recall | >= 99 % | 30`
- `slo` : `false-accept | <= 0 % | 30`
- `budget-action` : `accept-round-1 | alert`
- `budget-action` : `lead-time p90 | alert`
- `budget-action` : `release-lag p90 | alert`
- `budget-action` : `escaped-defects | alert`
- `budget-action` : `change-failure | alert`
- `budget-action` : `human-touch | alert`
- `budget-action` : `main-green | alert`
- `budget-action` : `judge-recall | alert`
- `budget-action` : `false-accept | alert`

## Revue

Ce qu'aucun agent ne fusionne, même sur ACCEPT : les gardes (`guard_*`, `hooks.json`), `CODEOWNERS` et
ce fichier : `guard_git` lit la clé `agent-autonomy` dans `origin/main`, et une PR est la seule façon
d'y changer une ligne. Ce périmètre ne dit pas que les gardes sont hors d'atteinte d'un agent : l'épingle de ce dépôt
(`.claude/settings.json`), qui choisit la version du plugin et donc les gardes que la session charge,
n'est plus protégée. L'humain l'a déléguée à l'agent le 2026-11-21, avec la CI et le manifeste de la
marketplace : une PR qui change l'épingle est fusionnée sur ACCEPT, et l'agent épingle de même les
projets consommateurs. Le seul recours contre une épingle qui retire un garde est la revue de cette PR.

`docs/agents/usine.md`, qui était dans cette liste, n'y est plus depuis le ticket #345 : il ne porte plus
que des clés libres (`merge-method`, `required-contexts`, `release-trigger`, `output-words-*`...).

- `protected-path` : `.github/CODEOWNERS`
- `protected-path` : `plugins/forge/hooks/hooks.json`
- `protected-path` : `plugins/forge/hooks/guard_`
- `protected-path` : `docs/agents/usine-gardes.md`

## Essai de bout en bout

La clé `e2e-run-limits` donne au lancement de l'essai de bout en bout (`plugins/forge/scripts/e2e_trial.py`,
dépôt d'essai `e2e-repo` dans `usine.md`) son délai de 1800 s, sous le plafond de 3600 s que `release.py`
met à l'essai entier, attente des vérifications comprise. Le 2026-11-25, un essai lancé par `release.py check` a fini
en `FAIL` à l'étape `lancement`, tué par les 300 s de `run-limits` ; lancé à la main avec 1800 s, il a
rendu `PASS` en 6 min 37 s (ticket #359). Elle prend la place de `run-limits` pour ce lancement seul : elle
borne l'agent comme lui, donc elle est ici (ticket #345, reporté des PR #361 et #362). Elle est lue par le
script de la 1.22.0, ou de la tête de `main` passé à `release.py` par `--essai`.

- `e2e-run-limits` : `2000 | 1800`

## Clés absentes

- `gh-api-allow` : ce dépôt n'appelle que ce que le plugin appelle par `gh api` ; sa liste suffit.
- `pr-cap-raiser` : les deux comptes GitHub de l'humain (`ikoro-labs` et `sunderland-labs`) sont aussi ceux dont
  l'agent détient le jeton, et aucun contrôle d'auteur ne les distingue ; sans la clé, personne ne relève le
  plafond par l'étiquette.
- `readonly-agent`, `readonly-command` : aucun agent du dépôt en plus de ceux du plugin.
- `agent-token-command`, `agent-login` : l'application GitHub des agents n'est pas encore installée sur ce
  dépôt (geste de l'humain, ticket #401) ; sans les deux clés, `guard_git` ne refuse aucun geste au titre de
  l'identité, et les agents agissent encore sous le jeton de l'humain.
- `ticket-budget`, `owner-gesture`, `never-weaken`, `infra-hosts`, `infra-verify`, `validation-owner`,
  `validation-reviewer`, `pin-bump` : ce dépôt ne les déclare pas ; l'étape qui lit chacune est « sans
  objet (clé `<nom>` absente) », jamais `PASS`.
