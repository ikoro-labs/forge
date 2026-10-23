---
name: feature-close
description: "Clore une feature dont la recette est acceptée : écrit son README.md tel que livré, met à jour le document de conception du système s'il existe, ferme l'issue de suivi une fois la PR fusionnée."
argument-hint: F-NNNN
---

# Clore une feature

Applique `${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md`, document `livree` : la recette est
acceptée.

1. **Le `README.md` de la feature**, depuis le gabarit `livree.md` : ce qui **existe**, lu dans le
   code et la recette, pas ce qui était prévu. Destinataires : toi dans six mois, un nouvel
   arrivant, un auditeur.
2. **Le document de conception du système**, si le `CLAUDE.md` du projet en nomme un : la section
   que la feature change. Sinon, rien : dis-le.
3. **Livrer** selon l'étape 7 du protocole, avec `statut: en-revue`. La commande de la clé
   `feature-catalog-command` se lance avant le commit, donc avant le push, pour que le catalogue
   régénéré entre dans la PR de clôture.
4. **L'issue de suivi** : `gh issue close <n> --comment` avec le lien vers le README, une fois la PR
   de clôture fusionnée. Pas avant.

Une fois le README accepté par `/forge:feature-accept F-NNNN livree`, la feature est livrée.
