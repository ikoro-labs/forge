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

0. **Lire la source produit en Markdown.** Chaque fichier de la clé `product-source` se lit en
   Markdown. Une source déclarée en PDF, en `.docx` ou en image rend l'étape bloquée : demande à son
   auteur un export Markdown, et ne la convertis pas toi-même. Clé absente : la reprise des éléments
   de la source est « sans objet (clé `product-source` absente) ».
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
4. **Reprendre chaque élément de la source, par son identifiant.** Un **identifiant** est celui
   d'origine de la source, avec ou sans tiret : capitales et chiffres, un tiret, un nombre (`EXI-01`,
   `RG-3.1`), ou une à cinq capitales collées à un nombre (`C01`, `G0`), le nombre pouvant porter des
   sous-numéros par points. Un mot ordinaire n'en est pas un (`Note`, `Phase 2`), mais une capitale et
   un chiffre en tête de ligne (`Q3 : bilan`) en est un : le comptage le liste, à toi de corriger la
   source ou d'en parler à son auteur. Un **élément identifié** de la source (exigence, contrôle, gabarit, règle, piège) est une
   ligne qui commence par son identifiant, après au plus une puce, un titre, une barre de tableau, un
   gras ou un crochet ; un identifiant cité au milieu d'une phrase n'en est pas un.
   - La section « Éléments de la source » de la spec reprend chaque élément, un par un, avec son
     identifiant d'origine, et dit où la spec le tient (story, critère).
   - Un élément de la source qui n'a aucun identifiant reçoit de toi un identifiant stable, que la
     spec dit avec la ligne de la source qu'il désigne ; la source n'est pas modifiée, et cet
     identifiant ne remplace jamais un identifiant d'origine, avec ou sans tiret.
   - Le comptage : `uv run --no-project --quiet python ${CLAUDE_PLUGIN_ROOT}/scripts/source_ids.py <spec.md>`
     relit la source et la spec et liste les identifiants de la source absents de la spec
     (`MISSING`). La spec ne passe en `ready-for-human` qu'à liste vide ; il ne compte pas les
     éléments sans identifiant, que tu relis toi-même.
   - **Un agent n'écarte jamais un élément.** Une exclusion de périmètre ne peut écarter un élément
     de la source que si son auteur l'a écarté par écrit, un auteur que désigne la clé
     `source-author` (un rôle ou un compte GitHub). La spec cite cet accord, une ligne par élément :
     `Écarté : <identifiant> | accord : <fichier> | <AAAA-MM-JJ> | <rôle>`, le fichier citant
     l'identifiant. Sans accord, l'élément reste dans la liste. Clé `source-author` absente : aucun
     élément ne s'écarte, et l'étape le dit.
5. **Ne pas découper en tickets ici** : cela vient après l'acceptation, avec le design.

Commande suivante, une fois la spec acceptée : `/forge:feature-design F-NNNN`, ou directement le
découpage en tickets en taille S quand rien ne déclenche un design (voir ce skill, étape 1).
