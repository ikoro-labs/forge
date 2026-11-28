---
name: incident
description: "Écrire la revue sans blâme d'un incident : les faits datés, la cause, ce qui l'a laissé passer, et la classe du correctif (mécanique, un ticket de contrôle et son test ; jugement, un cas du jeu de référence). À lancer pour tout incident sev1 ou sev2 et pour tout incident de l'usine elle-même. Refuse une revue sans correctif."
argument-hint: "<l'incident en une phrase, ou le numéro du ticket sev1 ou sev2>"
---

# La revue sans blâme d'un incident

Un incident n'est réparé que lorsqu'un contrôle l'empêche de revenir. Une consigne seule ou une
entrée de mémoire seule n'est jamais un correctif suffisant : un autre poste, ou un autre projet,
rejouera l'incident sans l'avoir lue.

1. **Le projet** est la copie principale du dépôt, pas un worktree : `git rev-parse --path-format=absolute
   --git-common-dir` rend `<projet>/.git`, et le projet est son dossier parent.
2. **Le dossier des revues** vient de la clé `incident-dir` :

   ```
   uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/incident.py" dir <projet>
   ```

   Sans la clé, le script répond « sans objet (clé `incident-dir` absente) » : rends cette phrase,
   n'écris aucune revue et ne devine aucun dossier. Une clé que le script refuse (dossier hors du
   dépôt, clé répétée) : rends son message et arrête-toi.
3. **Les faits** se prennent à la source, pas de mémoire : l'historique git, les PR, les runs de CI,
   les tickets, le journal de l'outil. Chaque fait porte sa date et sa source. Une note qu'un poste
   a gardée de l'incident (une mémoire privée) ne se cite jamais : elle dit où chercher, et seul
   ce que la source confirme entre dans la revue.
4. **La revue** suit `${CLAUDE_PLUGIN_ROOT}/templates/incident.md` et se pose dans le dossier de
   l'étape 2, sous `AAAA-MM-JJ-<sujet-en-minuscules>.md`. Elle est sans blâme : la cause est un
   mécanisme, jamais une personne. N'écris aucun nom de personne, aucun chemin de poste, aucun nom
   d'un autre projet, et ne cite rien mot pour mot d'une mémoire privée : le dépôt peut être public.
   Les sections sont les faits datés, la cause, ce qui l'a laissé passer, puis le correctif.
5. **Ce qui l'a laissé passer** se cherche avant le correctif : quel contrôle manquait, ou lequel
   existait et ne regardait pas là. Avant de proposer un nouveau contrôle, cherche s'il existe déjà
   (les gardes, les scripts, les tests du dépôt). Un contrôle qui existe et tient l'incident se cite
   comme `existant : <contrôle> ; <test>` ; un contrôle qui existe et n'a rien vu se nomme à la
   section « ce qui l'a laissé passer », et son défaut est le correctif.
6. **La classe du correctif** se choisit avec une question : une machine peut-elle vérifier la règle ?
   - `mécanique` : oui. Le correctif est le ticket `ready-for-agent` d'un contrôle déterministe et de
     son test, ou ce contrôle et son test quand le dépôt les tient déjà. Le ticket de correctif cite la
     revue (son chemin), pour qu'on remonte du contrôle à l'incident. Il naît sous les règles du
     projet : sa ligne `Motif :` est un cas que le projet admet, et un ticket que le projet n'admet pas
     n'est pas ouvert. Dans ce cas, cherche un ticket existant qui porte déjà ce contrôle et cite-le ;
     sans lui, arrête-toi et dis à l'humain le correctif qui manque, sans écrire la revue comme close.
     Quand le but de ce ticket est le délai de l'usine elle-même (le temps de la CI, des gardes, des
     relais), il porte aussi l'étiquette de la clé `speed-label` (`--label`) et passe devant la file,
     après `sev1` ; un autre but ne la reçoit jamais. Clé absente : « sans objet (clé `speed-label`
     absente) », aucune étiquette n'est devinée ; l'étiquette doit exister sur le dépôt, tu ne la crées pas.
   - `jugement` : non, seul un agent le voit. Le correctif est un cas ajouté au jeu de référence du
     projet, que le juge rejoue ; la revue cite le dossier du cas (`cas : <dossier>`).
   Une revue a une classe. Un incident qui demande les deux s'écrit en deux revues.
7. **Valide la revue** avant de la rendre :

   ```
   uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/incident.py" check <revue> --projet <projet>
   ```

   Une sortie non nulle liste les fautes : corrige la revue, jamais le script. Une revue sans
   correctif est refusée, et une consigne n'est pas un correctif : n'en écris pas pour passer le
   contrôle. Les chemins que le correctif cite doivent exister dans le dépôt.
8. **Le décompte** par classe se lit, sans rien modifier :

   ```
   uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/factory_slo.py" incidents <projet>
   ```

Rends le chemin de la revue, sa classe, son correctif (ticket, contrôle existant ou cas) et le
décompte. Dis ce que tu n'as pas pu vérifier à la source. Tu n'ouvres, ne fermes ni ne modifies aucun
ticket sauf celui de correctif, et seulement sous les règles du projet.
