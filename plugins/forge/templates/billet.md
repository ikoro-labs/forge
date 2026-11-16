<!-- template: billet | required: from, type, resource, ticket, measure, awaits | rules: socle.md -->
from: <your session name, as the registry of the host lists it>
type: <claim | release | info | question | reply>
resource: <the shared resource the billet is about, or none>
ticket: <#n, or none>
measure: load=<1-minute load, with a dot> memory=<available memory in MB>MB time=<ISO 8601 with its offset>
awaits: <nothing | reply>
---
<The prose: 60 words at most, in English.>

- Le billet est le seul format d'un message vers une autre session : des lignes `key: value`, la ligne `---`, puis la prose. Tout le billet est en anglais, prose comprise.
- `type` : `claim` prend une ressource, `release` la rend, `info` informe, `question` demande, `reply` répond.
- `awaits` : `nothing` ou `reply`.
- `resource` prend ses valeurs dans la clé `shared-resource` de `usine.md` (une ligne par valeur), ou `none`. Sans cette clé, l'étape est sans objet : toute valeur non vide passe.
- `measure` : `load=1.25 memory=5200MB time=2026-11-16T14:13+01:00`. `time` est l'heure ISO 8601 avec son décalage (`Z` compris), jamais l'heure locale nue ni une prose.
- Le hook `guard_output` refuse le message qui s'écarte du gabarit et nomme chaque écart ; un message refusé ne part pas.
