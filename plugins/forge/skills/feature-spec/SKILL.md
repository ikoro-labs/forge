---
name: feature-spec
description: "Écrire la spec d'une feature dont le cadrage est accepté : huit stories INVEST au plus, critères « Étant donné, quand, alors », non-goals, exigences non fonctionnelles, contrats en prose, impact sur les règles du métier."
argument-hint: F-NNNN
disable-model-invocation: true
---

# Spécifier une feature

Applique `${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md`, document `spec` : le cadrage doit
être accepté. La spec est un fichier du dépôt, pas une issue : c'est elle que les tickets et les PR
citeront.

1. **Auditer avant de demander.** Code concerné, contrats existants, données disponibles : ce que le
   dépôt ou la donnée tranche ne devient pas une question.
2. **Tours de questions** : le rôle et le bénéfice de chaque story, les cas limites, les chiffres
   attendus des critères, ce qui est explicitement hors du but.
3. **Écrire `spec.md`** depuis le gabarit :
   - **huit stories au plus**, chacune INVEST ; au-delà, propose de couper la feature ;
   - chaque critère au format **Étant donné, quand, alors**, avec un résultat observable et chiffré
     quand c'est possible : il deviendra un test qui cite `F-NNNN A<n>`, relié dans la recette ;
   - les non-goals, les exigences non fonctionnelles chiffrées, les contrats décrits en prose ;
   - **l'impact sur les règles du métier**, obligatoire dès qu'un chiffre engagé ou une obligation
     réglementaire est en jeu : invoque alors le skill du domaine (clé `domain-skill`) et reporte
     ses conclusions ;
   - les décisions prises par défaut, et une section « Questions ouvertes » vide si possible.
4. **Ne pas découper en tickets ici** : cela vient après l'acceptation, avec le design.

Commande suivante, une fois la spec acceptée : `/forge:feature-design F-NNNN`, ou directement le
découpage en tickets en taille S quand rien ne déclenche un design (voir ce skill, étape 1).
