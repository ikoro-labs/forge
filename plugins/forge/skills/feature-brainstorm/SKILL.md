---
name: feature-brainstorm
description: "Tenir une séance de brainstorming sur une feature, à n'importe quelle étape : chaque question, réponse et décision est écrite dans seances/, et les documents apportés entrent dans sources/. À utiliser pour réfléchir, trancher ou importer une note, un PDF ou un échange tenu ailleurs."
argument-hint: F-NNNN <sujet>
disable-model-invocation: true
---

# Séance de brainstorming

C'est ici que l'équipe réfléchit, au lieu d'une conversation ou d'un document partagé ailleurs : ce
qui n'est pas dans le dossier de la feature n'a pas été décidé.

Applique `${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md`. Étape 3 : la feature doit
seulement exister ; une séance est permise à toute étape, y compris sur une feature
`hors-perimetre` qu'on voudrait relancer.

1. **Ouvrir la séance** `seances/AAAA-MM-JJ-<auteur>-<sujet>.md` depuis le gabarit `seance.md`,
   avant la première question. Participants : l'auteur, l'agent, et toute personne que l'auteur
   nomme.
2. **Apporter les sources.** Demande s'il y a un document né ailleurs : note, PDF, export de
   conversation, fichier partagé, compte rendu d'appel. Lis-le **en entier**. Puis :
   - s'il ne contient rien que le protocole exclut, copie-le dans `sources/` sous un nom
     `AAAA-MM-JJ-<nature>-<sujet>.<ext>` ; une conversation collée devient un `.md` ;
   - sinon, ne le copie pas : consigne sa référence, son empreinte `sha256` et ce qui en est retenu.
   Dans les deux cas, une ligne dans le tableau « Sources apportées ».
3. **Questionner par tours** (étape 5 du protocole). Pour une source volumineuse, commence par dire
   ce que tu en retiens et ce qui contredit le dépôt (ADR en vigueur, code, glossaire), puis pose
   les questions que cela ouvre.
4. **Clore la séance** : remplis « Décidé » (chaque décision, par qui, et le document où elle va) et
   « Resté ouvert ». Une séance n'est jamais réécrite ensuite ; une correction est une séance
   suivante.
5. **Reporter.** Propose d'appliquer les décisions au document concerné s'il existe. Un document
   `accepte` que la séance change repasse en `en-revue`, avec la séance citée.
6. **Livrer** (étape 7 du protocole), séance et sources dans la même PR, pour que ceux qui ne l'ont
   pas tenue la relisent.
