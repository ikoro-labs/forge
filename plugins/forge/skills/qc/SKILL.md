---
name: qc
description: "Revue et fusion d'une PR par l'agent, en deux temps (forge:qc-gate mesure, forge:qc-conf juge), verdict et rapport postés sur la PR, fusion si ACCEPT. À lancer après avoir ouvert ou mis à jour une PR, quand on demande de relire une PR, ou depuis forge:feature-build. Jamais par l'agent qui a codé la PR : sans les deux juges, il jugerait et fusionnerait seul son propre travail."
argument-hint: <numéro de PR>
---

# Revue en deux temps, puis fusion

Le mesureur et le juge sont deux agents distincts, aux outils différents à dessein :
`forge:qc-gate` n'a que Bash, `forge:qc-conf` n'a ni Edit ni Write. Le hook `guard_readonly` du
plugin borne leur Bash, et ne rien modifier reste aussi une consigne de leur rôle. Relève
`git rev-parse HEAD`, `git status --short` et `git config --list --local` avant de les lancer,
puis vérifie après leur passage que les trois n'ont pas bougé avant de poster : un commit laisse
le statut vide, et une installation peut écrire dans la configuration git. Un écart : ne poste
rien, pose `needs-your-attention` avec l'écart, arrête-toi.

Toi, tu orchestres, tu postes et tu fusionnes. Personne ne relit après toi : l'humain n'est
qu'alerté.

Le projet décrit son usine dans `docs/agents/usine.md` ; ce skill en lit les clés `protected-path`,
`never-weaken` et `budget-action`.

## Une passe ou deux

Une PR dont le diff ne touche que des fichiers de verrou et les lignes de version d'une montée
Dependabot mineure ou corrective, ou que du Markdown hors `CLAUDE.md`, `.claude/`, `docs/adr/` et
les chemins de la clé `protected-path` et ceux des entrées de la clé `never-weaken` (le chemin est
la première partie de l'entrée : seul `forge:qc-gate` les mesure), est revue en **une passe** : pas
de `forge:qc-gate`,
`forge:qc-conf` seul, qui relève lui-même les checks de la PR et `git merge-tree` avec la base. Le
verdict, le rapport et la suite sont les mêmes. Tout le reste passe par les deux temps ci-dessous.

## Étapes

1. **Identifier la PR et le tour.**
   `gh pr view <n> --json number,author,headRefName,headRefOid,baseRefName,labels,body,comments`.
   Un commentaire de verdict `ROUND: 1` déjà posté fait de celle-ci le tour 2. Un `ROUND: 2`
   déjà rejeté : il n'y a pas de tour 3, passe à l'étape 6. Chaque verdict porte la ligne
   `HEAD: <sha>` de la tête jugée : un verdict sur la tête actuelle n'est pas à refaire, un
   verdict sur une tête plus ancienne dit quel tour a eu lieu et ce qui a changé depuis.
2. **Mesurer.** Lance l'agent `forge:qc-gate` avec le numéro de PR et le tour. Attends son tableau.
3. **Juger.** Lance l'agent `forge:qc-conf` avec le numéro de PR, le tour, le tableau de
   `forge:qc-gate` recopié tel quel, et au tour 2 les bloqueurs du tour 1. Ne lui impose pas
   d'autre format que le sien.
4. **Lire le verdict.** Écris-le dans un fichier, puis :

   ```
   uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/parse_output.py" verdict <fichier>
   ```

   Code 0 : le verdict est lisible ; vérifie que son `HEAD` est la tête actuelle de la PR. Code 1 :
   relance `forge:qc-conf` une fois, avec la phrase que le script a rendue. Un second échec, ou un
   `HEAD` qui n'est pas la tête : la revue est `FAILED`, ne fusionne pas, pose
   `needs-your-attention` avec la raison, arrête-toi.
5. **Poster.** Le verdict, tel quel, en commentaire de PR : `gh pr comment <n> --body-file
   <fichier>`. La trace sur la PR est le but : une revue qui n'y figure pas n'a pas eu lieu.
6. **Rapporter.** Écris la section `Rapport d'agent` (forme plus bas). Sur une PR que tu as ouverte,
   dans sa description (`gh pr edit <n> --body-file`) ; sur une autre, Dependabot compris, en
   commentaire. Elle est réécrite à chaque tour, jamais laissée périmée.
7. **Suite.**
   - ACCEPT : fusionne (étape 8), sauf ce que les règles **Budget d'erreur** et **Chemins
     protégés** plus bas arrêtent.
   - REJECT au tour 1 : corrige chaque `BLOCKER`, et seulement eux, pousse, puis reprends à
     l'étape 1. Les `MINOR` et `NOTE` restent dans le verdict. Depuis `/forge:feature-build`, la
     correction passe par `forge:coder` en mode correction, pas par toi.
   - Après la fusion ou la fermeture : un `MINOR` qui change un comportement (code, porte, règle
     appliquée) est reporté en commentaire sur un ticket déjà ouvert qui touche le même code,
     sinon sur l'issue de suivi de la feature ; hors feature, il reste dans le verdict. Il n'ouvre
     pas de ticket. Les `NOTE` et les `MINOR` de prose restent dans le verdict.
   - REJECT au tour 2, PR liée à un ticket : ferme la PR avec l'étiquette `agent-rework`, remets
     le ticket en `ready-for-agent` et commente-le avec le retour d'expérience et `REWORK: 1`.
     Si le ticket porte déjà `REWORK: 1`, ne le relance pas : pose `needs-your-attention` sur la
     PR et arrête-toi. Une seule reprise par ticket.
   - REJECT au tour 2, PR sans ticket (Dependabot) : laisse-la ouverte, pose
     `needs-your-attention`, arrête-toi.
8. **Fusionner.** `gh pr merge <n> --squash --delete-branch --body-file <fichier>`, puis
   `gh pr edit <n> --add-label agent-merged` : tu agis sous le compte de l'humain, et sans
   l'étiquette la fusion paraîtrait lue par lui. Toujours avec un corps que tu écris : sans lui,
   GitHub écrit sur la base tous les messages de commit de la branche, périmés compris, et une PR
   reprise au tour 2 porte un message du tour 1 que son correctif a rendu faux. Le corps, en
   français, décrit la tête fusionnée : un paragraphe par ticket cité, chacun avec son
   `Closes #n`, ou son `Refs #n` suivi des points que la PR livre, pour que le commit garde la
   trace de chacun. Un ticket en `Refs #n` n'est suivi d'aucun mot-clé de fermeture nulle part, ni
   dans le message ni dans la description de la PR, `Rapport d'agent` compris : le hook
   `guard_git` du plugin refuse la fusion sinon.

   `--delete-branch` supprime la branche de tête sur `origin` et sa copie locale : après un
   squash, `git branch -d` ne la voit jamais comme fusionnée, et `guard_git` refuse `-D` aux
   agents. Une branche encore extraite dans le worktree d'un coder fait échouer gh après la fusion
   (`failed to delete local branch`), et il s'arrête avant `origin` : la fusion est faite, pose
   l'étiquette, puis `git push origin --delete <branche>` ; la copie locale reste, elle est à ce
   worktree. Une PR empilée sur cette branche n'est pas fermée : GitHub reporte sur la base de
   celle-ci chaque PR ouverte qui la visait, et il reste à y fusionner la base
   (`gh pr update-branch`).

   Si la protection de la base refuse parce que la branche est en retard, `gh pr update-branch <n>`,
   attends les checks, et fusionne. Checks rouges : ce n'est pas un ACCEPT, reprends à l'étape 1.

## Budget d'erreur

Le projet peut rendre les fusions à l'humain quand un objectif de service est épuisé (clé
`budget-action`). Au début de chaque passage, avant l'étape 1, recalcule l'état :

```
uv run --no-project --quiet python "${CLAUDE_PLUGIN_ROOT}/scripts/factory_slo.py" budget <projet>
```

Sans la clé, la commande répond « sans objet (clé `budget-action` absente) » : dis-le dans `REX`,
aucune action. Un code de sortie non nul (ligne mal formée, objectif inconnu, calcul impossible) :
ne fusionne pas, pose `needs-your-attention` avec le message, arrête-toi ; le garde `guard_git`
refuserait la fusion de toute façon.

Une ligne `ACTIVE : human-merge sur <objectif>` arrête la fusion de la même façon qu'un chemin
protégé, même sur ACCEPT : le verdict reste celui de la revue, mais pose `needs-your-attention`,
écris l'objectif épuisé dans `Attention`, `fusionnée par l'agent : non` dans `Verdict`, arrête-toi.
L'humain fusionne. Les actions `feature-freeze` (celle de `forge:feature-build`) et `alert` (l'étiquette
de l'issue de suivi, posée par `forge:slo --publier`) ne changent rien ici.

Une action reste active tant que l'objectif n'est pas revenu à `tenu`, même s'il n'est plus que
`menacé` : la ligne reste `ACTIVE`. L'autonomie revient d'elle-même : quand la commande dit
« autonomie rendue » (l'objectif est revenu à `tenu`), fusionne comme d'habitude et écris-le dans `REX`. Retire alors `needs-your-attention` d'une PR
que tu avais arrêtée pour ce seul objectif, en écrivant dans `Attention` ce que tu retires et pourquoi.

## Chemins protégés

Une PR dont le diff touche un chemin de la clé `protected-path` (un registre, une chaîne de
certification, une référence de contre-validation, un fichier de signatures...) ne se fusionne pas
sur ACCEPT : pose `needs-your-attention`, écris le chemin touché dans `Attention`, arrête-toi. Un
humain fusionne. Sans la clé, la règle est sans objet : dis-le dans `REX`. Cette consigne reste : le
garde `guard_git` est le filet (il refuse `gh pr merge` à tout agent quand un fichier du diff commence
par un de ces chemins, et la clé déclarée, quand la liste des fichiers est illisible), la consigne
évite le refus.

La clé `never-weaken` arrête la fusion de la même façon, pour un changement qui retire un droit (une
ligne retirée, un nombre relevé, un rang abaissé). `forge:qc-gate` mesure chaque entrée sur le
diff, `forge:qc-conf` dit dans la ligne `GATES` (`never-weaken : <entrée>, ...`) celles qui
s'appliquent. Dès qu'une entrée s'applique, même sur ACCEPT : pose `needs-your-attention`, écris
l'entrée et ce que le script a mesuré dans `Attention`, `fusionnée par l'agent : non` dans
`Verdict`, arrête-toi. Un humain fusionne. Le verdict reste ACCEPT : la PR peut être bonne, c'est
la décision qui lui revient. Une sonde en `FAIL` (entrée invalide) ou `NOT RUN` ne vaut pas
« aucune entrée » : arrête la fusion de même, avec la raison dans `Attention`. Sans la clé, la
règle est sans objet : dis-le dans `REX`.

`needs-your-attention` alerte ; hors des chemins protégés et des entrées `never-weaken`, elle ne
bloque pas la fusion. Pose-la
toi-même quand un point mérite le regard humain, et écris-en la raison dans `Attention`.
Retire-la quand la raison écrite dans `Attention` ne tient plus (une revue `FAILED` relancée qui
aboutit, un écart corrigé), et écris dans `Attention` ce que tu as retiré et pourquoi. Sur une PR
qui touche un chemin protégé, elle reste jusqu'à la fusion humaine. Sur une PR dont une entrée
`never-weaken` s'applique, de même.

Retire seulement une étiquette dont un agent a écrit la raison, dans la ligne `Attention` d'un
`Rapport d'agent` ou dans un commentaire de revue `FAILED`. Tu agis sous le compte de l'humain :
l'auteur de l'étiquette sur GitHub ne vous distingue pas. Une étiquette dont aucun texte d'agent ne
donne la raison vient d'un humain : elle reste, même si un commentaire l'explique.

## Porte à sens unique

Une PR dont la porte est `sens unique` (geste destructif, publication, migration de données,
décision difficile à défaire) alerte l'humain. Lis la ligne `GATES` du verdict, entrée
`one-way-door` : `déclarée` (la PR le dit) ou `relevée` (`forge:qc-conf` l'a trouvée dans le diff,
la PR ne la déclarait pas). Dans les deux cas, pose `needs-your-attention` et écris la raison dans
`Attention` : la porte et le geste qui ne se défait pas. `one-way-door : aucune`, ou la mention
absente, ne pose rien.

Cette étiquette alerte et ne bloque pas la fusion : hors des chemins protégés et des entrées
`never-weaken`, un ACCEPT se fusionne. L'humain peut durcir ce choix en ajoutant le chemin concerné
à la clé `protected-path`. Sur ACCEPT fusionné, l'étiquette reste jusqu'à ce qu'un humain la retire.

## Rapport d'agent

En français, six lignes, aucune vide :

```markdown
## Rapport d'agent

- **Fait :** ce qui a changé, en trois lignes au plus
- **Pourquoi :** le ticket, et la raison qui le porte
- **REX :** ce qui a résisté, ce qui a surpris, ce que le prochain agent doit savoir
- **Reprise :** aucune | reportée sur #<issue> | à refaire (agent-rework)
- **Attention :** aucune | une raison par needs-your-attention | retirée : <raison>
- **Verdict :** ACCEPT | REJECT au tour <n> ; fusionnée par l'agent : oui | non
```

`REX` n'est jamais « rien à signaler » : dis au moins ce que tu as vérifié et comment.
`Reprise : reportée sur #n` nomme le ticket ouvert où les `MINOR` qui changent un comportement
sont reportés ; sinon `Reprise : aucune`.

L'étape est finie quand verdict et rapport sont postés, et que la suite qu'ils commandent est faite.
