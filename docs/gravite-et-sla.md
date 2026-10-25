# Les classes de gravité et les engagements de délai

Tous les défauts ne se valent pas : un garde contourné n'attend pas dans la même file qu'une phrase
de documentation. Le projet pose une classe de gravité sur chaque ticket de défaut, et déclare en
combien de temps l'usine s'engage à le prendre en charge, à le corriger et à publier le correctif.

## Les trois classes

Elles se posent par une étiquette de ticket, une seule par ticket.

| Étiquette | Gravité | Ce qu'elle recouvre |
|---|---|---|
| `sev1` | la plus haute | un garde contourné, un chemin protégé fusionné sans humain, une perte de données ou de travail, ou la branche de base rouge |
| `sev2` | moyenne | un défaut échappé qui change un comportement (hook, porte, règle appliquée) |
| `sev3` | basse | la prose, la documentation ou un confort |

Le doute se tranche vers la classe la plus haute, et se rabaisse dans un commentaire qui dit pourquoi.
Les étiquettes `sev1`, `sev2` et `sev3` doivent exister sur le dépôt ; l'agent ne les crée pas.

## Les engagements de délai (SLA)

La clé `sla` de `docs/agents/usine.md` donne une ligne par classe :

```
- `sla` : `<gravité> | <prise en charge> | <correctif fusionné> | <correctif publié>`
- `sla` : `sev1 | 4 h | 24 h | 72 h`
```

Chaque délai est un nombre suivi de `h` (heures) ou de `j` (jours), et se compte **depuis l'ouverture du
ticket** : ce sont trois échéances, pas trois durées bout à bout.

| Étape | Atteinte quand |
|---|---|
| prise en charge | le ticket est assigné, ou reçoit l'étiquette `agent-claimed` |
| correctif fusionné | une PR qui le ferme (`Closes`, pas `Refs`) est fusionnée |
| correctif publié | le commit de fusion de cette PR est dans un tag de version (clé `release-tag`) |

La clé n'a pas de valeur par défaut. Sans elle, les échéances sont « sans objet (clé `sla` absente) » :
aucune échéance n'est devinée, et rien n'est mesuré. Une ligne mal formée, une classe inconnue ou
répétée fait échouer la commande. Sans la clé `release-tag`, l'étape « correctif publié » est
« sans objet (clé `release-tag` absente) ».

## La file de `forge:feature-build`

`forge:feature-build` prend les tickets prêts par gravité (`sev1`, puis `sev2`, puis `sev3`, puis ceux
sans classe), et à gravité égale par échéance de prise en charge (la plus proche d'abord). Sans la clé
`sla`, la gravité trie encore (elle vient de l'étiquette) et l'échéance est « sans objet » : l'ordre
des sous-issues départage. Un ticket `sev1` passe devant tout ticket qui n'est pas encore confié ; il
ne passe ni devant un coder déjà en vol, ni devant un bloqueur ouvert, et il reste soumis à un gel de
feature (clé `budget-action`) s'il ne porte ni `bug` ni `escaped-defect`.

```sh
uv run --no-project --quiet python plugins/forge/scripts/factory_slo.py queue <projet> <ticket> [<ticket> ...]
```

## La mesure

```sh
uv run --no-project --quiet python plugins/forge/scripts/factory_slo.py sla <projet> [--json]
```

`sla` relit chaque ticket étiqueté `sev1`, `sev2` ou `sev3` qui est ouvert, ou qui a été ouvert depuis
`--depuis` (30 jours avant maintenant par défaut), et dit pour chaque étape son échéance, la date où
elle a été atteinte, et son état :

- `tenue` : atteinte à l'échéance ou avant ;
- `dépassée` : atteinte après l'échéance, ou échéance passée sans qu'elle soit atteinte ;
- `en cours` : pas atteinte, échéance devant nous ;
- `sans objet`, avec sa raison : la gravité n'a pas de ligne dans la clé `sla`, la clé `release-tag` est
  absente (étape « correctif publié »), ou le ticket est fermé sans que l'étape ait été atteinte.

`restore-time` (voir `docs/indicateurs-de-service.md`) se ventile par ces classes, avec les étiquettes
`sev1`, `sev2` et `sev3` ; l'ancienne étiquette `gravite:<classe>` reste lue quand un ticket n'a pas de
classe. `factory_slo.py report` ajoute au rapport la section « Engagements de délai » et y liste chaque
dépassement ; sans la clé `sla`, la section dit « sans objet (clé `sla` absente) ».

## Éprouvé, et pas encore

Les calculs sont éprouvés sur des réponses `gh` fictives et des dépôts git jetables, sous Linux. Les
événements `assigned` et `labeled` de `gh api .../issues/<n>/events` sont ceux de la documentation de
GitHub ; la commande n'a pas encore tourné contre l'API réelle.
