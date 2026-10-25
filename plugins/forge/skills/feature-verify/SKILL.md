---
name: feature-verify
description: "Écrire la recette d'une feature dont les tickets sont fermés : chaque critère d'acceptation relié au test qui le prouve, à sa PR et à la version vérifiée en environnement cible."
argument-hint: F-NNNN
---

# Recetter une feature

Applique `${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md`, document `recette` : la spec, et
le design s'il existe, sont acceptés.

1. **Tickets fermés.** Les sous-issues de l'issue de suivi (`issue:` de `idee.md`) :
   `gh api repos/{owner}/{repo}/issues/<n>/sub_issues`, et à défaut les issues qui portent
   `Feature: F-NNNN`. Une issue ouverte : dis laquelle et arrête-toi.
2. **Un test par critère.** Pour chaque critère de la spec (`A1`...), trouve le test qui le prouve :
   les tests citent `F-NNNN A<n>` dans leur nom ou leur docstring (`git grep -n "F-NNNN A"`).
   Lance-les, après avoir installé l'environnement par les commandes de la clé `install` ; note le
   résultat et la valeur observée. Un critère sans test est un **écart**, jamais une ligne
   « passe ».
   **La matrice.** Quand `matrice.md` existe dans le dossier de la feature, la recette se juge contre
   elle, pas contre la liste des PR fusionnées : lance
   `uv run --no-project --quiet python ${CLAUDE_PLUGIN_ROOT}/scripts/matrice.py <matrice.md>` (un constat
   se corrige avant la recette) puis `... --reste <matrice.md>`. Chaque ligne qui n'est ni `tenu`
   ni `écarté` entre dans la section « Écarts » de la recette avec son état et son ticket, même si
   toutes les PR sont fusionnées. Les états se jugent par la règle de `matrice.md`, une seule pour
   tous les agents. Sans la clé `product-source`, l'étape est « sans objet (clé `product-source`
   absente) » et la recette se juge sur les critères de la spec.
3. **La PR** de chaque critère, par `git log --grep` sur les tickets.
4. **L'environnement cible** : où, quand, quelle version, par qui. Tant qu'aucun environnement
   cible n'est déployé, écris « pas encore déployable » et la raison, jamais « vérifié ».
5. **Le monitoring** : chaque métrique et alerte du design (ou du cadrage, section Observabilité)
   existe, avec où la voir.
6. **Écrire `recette.md`** depuis le gabarit, `version:` renseignée, écarts nommés avec leur ticket,
   puis livrer selon l'étape 7 du protocole.

Commande suivante, une fois la recette acceptée : `/forge:feature-close F-NNNN`.
