---
name: feature-new
description: "Ouvrir une feature à partir d'une idée brute : crée <feature-dir>/NNNN-slug/idee.md et l'issue de suivi. Première commande de la chaîne des features."
argument-hint: <l'idée en une phrase>
disable-model-invocation: true
---

# Ouvrir une feature

Applique d'abord `${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md` (sauf l'étape 3 : aucune
condition d'entrée).

1. **Numéro.** Sur ta branche partie de la base : le plus grand numéro `NNNN` des dossiers de la clé
   `feature-dir`, plus un, sur quatre chiffres (`0001` pour la première). Choisis un slug court en
   minuscules et tirets.
2. **Un seul tour de questions**, avec ta recommandation pour chacune :
   - le titre court ;
   - le porteur, parmi les humains de la clé `accepting-human` (`porteur` reçoit son identifiant
     court s'il en a un, sinon son `user.name`) ;
   - **qui l'a demandée** : un utilisateur ou un client, nommé ; sinon « interne » et pourquoi. Le
     cadrage dira si la règle d'entrée (clé `entry-gate`) l'admet ;
   - les documents qui l'accompagnent (note, PDF, échange, fichier) ;
   - les premières questions à trancher.
3. **L'idée.** `<feature-dir>/NNNN-slug/idee.md` depuis le gabarit `idee.md`, `etat` à la valeur
   du rôle `active` de la clé `feature-state` (sans la clé, `active`). Un document apporté entre dans `sources/` s'il ne contient rien de ce que le protocole exclut ;
   sinon, seulement sa référence et son empreinte.
4. **L'issue de suivi.** `gh label create feature --color 5319E7 --description "Feature suivie de
   l'idée à la livraison"` si l'étiquette manque, puis
   `gh issue create --label feature --title "F-NNNN : <titre>"`, corps : l'idée, le lien vers le
   dossier, et « Les tickets de cette feature en seront des sous-issues. » Reporte le numéro dans
   `issue:` de `idee.md`.
5. **Livrer** selon l'étape 7 du protocole ; la commande suivante est
   `/forge:feature-brainstorm F-NNNN` s'il reste des questions, sinon `/forge:feature-frame F-NNNN`.

Pas de cadrage ici : une idée tient en une page, et c'est tout ce qu'elle doit être.
