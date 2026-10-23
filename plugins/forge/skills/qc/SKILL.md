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

Le projet décrit son usine dans `docs/agents/usine.md` ; ce skill en lit la clé `protected-path`.

## Une passe ou deux

Une PR dont le diff ne touche que des fichiers de verrou et les lignes de version d'une montée
Dependabot mineure ou corrective, ou que du Markdown hors `CLAUDE.md`, `.claude/`, `docs/adr/` et
les chemins de la clé `protected-path`, est revue en **une passe** : pas de `forge:qc-gate`,
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
   - ACCEPT : fusionne (étape 8), sauf ce que la règle **Chemins protégés** plus bas arrête.
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

## Chemins protégés

Une PR dont le diff touche un chemin de la clé `protected-path` (un registre, une chaîne de
certification, une référence de contre-validation, un fichier de signatures...) ne se fusionne pas
sur ACCEPT : pose `needs-your-attention`, écris le chemin touché dans `Attention`, arrête-toi. Un
humain fusionne. Sans la clé, la règle est sans objet : dis-le dans `REX`.

`needs-your-attention` alerte ; hors des chemins protégés, elle ne bloque pas la fusion. Pose-la
toi-même quand un point mérite le regard humain, et écris-en la raison dans `Attention`.
Retire-la quand la raison écrite dans `Attention` ne tient plus (une revue `FAILED` relancée qui
aboutit, un écart corrigé), et écris dans `Attention` ce que tu as retiré et pourquoi. Sur une PR
qui touche un chemin protégé, elle reste jusqu'à la fusion humaine.

Retire seulement une étiquette dont un agent a écrit la raison, dans la ligne `Attention` d'un
`Rapport d'agent` ou dans un commentaire de revue `FAILED`. Tu agis sous le compte de l'humain :
l'auteur de l'étiquette sur GitHub ne vous distingue pas. Une étiquette dont aucun texte d'agent ne
donne la raison vient d'un humain : elle reste, même si un commentaire l'explique.

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
