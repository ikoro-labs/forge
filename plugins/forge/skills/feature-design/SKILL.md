---
name: feature-design
description: "Écrire le design d'une feature dont la spec est acceptée : contextes touchés, ports et adapters, modèle de données, frontière de confiance, observabilité, coutures de test, découpage en tickets, et les ADR déclenchés."
argument-hint: F-NNNN
---

# Concevoir une feature

Avant tout, applique `${CLAUDE_PLUGIN_ROOT}/autonomie.md` : lancé par le modèle plutôt que tapé par
l'humain, ce skill ne s'exécute que si la clé `agent-autonomy` de `docs/agents/usine.md` l'ouvre.

Applique `${CLAUDE_PLUGIN_ROOT}/templates/features/protocole.md`, document `design` : la spec doit
être acceptée.

1. **Faut-il un design ?** En taille S, si rien ne le déclenche (technologie, architecture, service,
   contrat d'API, modèle IA, sécurité, schéma non trivial, ou un déclencheur que le `CLAUDE.md` du
   projet ajoute), dis-le et passe directement au découpage (étape 6). Rien n'est écrit.
2. **Lire le code** des contextes touchés, leur glossaire (clé `glossary`) et le fichier de règles
   de chaque domaine touché (clé `domain-rules`). Invoque le skill de chaque domaine touché (clé
   `domain-skill`) pour ses choix, et `forge:codebase-design` pour le découpage en modules et leurs
   interfaces.
3. **Tours de questions** sur ce que le code ne tranche pas.
4. **Écrire `design.md`** depuis le gabarit : contextes, ports, données (expand puis contract pour
   un changement large), frontière de confiance, les trois réponses d'observabilité avec leur point
   d'émission, les coutures de test (la plus haute qui existe), et le découpage en tranches
   verticales.

   **Le parcours.** Une feature qui a des écrans écrit aussi `parcours.md` dans son dossier, depuis
   `${CLAUDE_PLUGIN_ROOT}/templates/features/parcours.md` : chaque écran, dans l'ordre, ce que
   l'utilisateur y voit (les mots exacts de l'écran, entre « et »), ce qu'il y fait, l'écran suivant
   et les identifiants d'éléments de la source qu'il tient. Il se mène avec l'expert métier quand le
   projet en a un. Lance
   `uv run --no-project --quiet python ${CLAUDE_PLUGIN_ROOT}/scripts/parcours.py <parcours.md>` :
   le script vérifie le format et que chaque écran cite un identifiant que la source (clé
   `product-source`) porte ; sans cette clé, la correspondance est « sans objet » et la spec ne la
   remplace pas ; un `INVALID`, un `UNKNOWN` ou un `BLOCKED` se
   corrige avant la PR. Chaque libellé neuf entre dans le glossaire du contexte (clé `glossary`).
   Sans écran, dis-le et n'écris rien. Le parcours n'a pas de statut propre : il se relit avec le
   design, dans la même PR.
5. **Écrire les ADR déclenchés**, au format `${CLAUDE_PLUGIN_ROOT}/templates/adr.md` (ou le gabarit
   d'ADR du projet s'il en a un), numéro suivant le plus haut de `docs/adr/`, statut proposé, et les
   lister dans `adr:` de l'en-tête. Un terme nouveau entre dans le glossaire du contexte.
6. **Découper**, une fois le design accepté (ou la spec seule en taille S) : des tickets en
   tranches verticales, sous-issues de l'issue de suivi, chacun avec ses critères `A<n>`, leurs
   cas `A<n>.<k> | <entrée> | <résultat attendu>` (gabarit `templates/ticket.md`, complétés au
   tour 0 de `forge:feature-build`) et ses
   liens vers la spec et le design figés à un commit, étiquetés `ready-for-agent`, et leurs
   dépendances déclarées. Trois règles :
   - **Un contexte neuf.** Chaque ticket tient dans un seul contexte neuf, celui d'un
     `forge:coder` : s'il n'y tient pas, coupe-le.
   - **Trois PR au plus.** Chaque ticket est taillé pour trois PR au plus, parties en `Refs #n`
     comprises : `feature-tickets` compte des tickets, pas des PR, et un ticket livré en parties
     sans plafond ne borne rien. Un ticket qui en prendrait davantage est coupé avant d'être
     publié, en tickets du budget (`feature-tickets`), jamais en une quatrième partie. Le budget
     en PR de la feature est `feature-tickets` fois 3.
   - **La taille.** Pour chaque ticket, estime la taille du diff qu'il demande, en lignes lisibles (le
     code, les tests et les documents écrits à la main, sans fichier généré ni verrou), et écris
     l'estimation dans le ticket. Un ticket de plus de 1 000 lignes lisibles est coupé en parties, chacune
     livrant des points entiers du ticket en `Refs #n`, dans les PR que la clé `ticket-pr-cap` admet.
     Les tickets pas commencés (sans PR ouverte ni fusionnée) sont redécoupés à cette règle ; ceux en
     cours gardent les règles avec lesquelles ils ont commencé. Sans la clé `ticket-pr-cap`, l'étape est
     « sans objet (clé `ticket-pr-cap` absente) » : aucun plafond n'est deviné pour décider de la coupe.
   - **Le prérefactoring d'abord.** Quand le changement demandé serait difficile dans le code tel
     qu'il est, rends-le facile d'abord (le prérefactoring), puis fais le changement facile. Le
     prérefactoring a son propre ticket, qui bloque ceux qui en dépendent, et ne change aucun
     comportement.
   - **Le refactoring large ne se force pas en tranche verticale.** Un changement mécanique dont le
     rayon couvre tout le code se fait en trois temps : expand (ajouter la nouvelle forme à côté
     de l'ancienne), migration par lots, puis contract (retirer l'ancienne). Chaque étape est un
     ticket bloqué par la précédente.

   **The budget.** The `forge:product-owner` cuts the feature into at most 12 tickets, the
   `feature-tickets` of the design header; `guard_ticket_budget` refuses the ticket beyond it.
   Each published ticket (`gh issue create`) carries the line `Motif : to-tickets F-NNNN`; once the
   list is published, it is closed.

   **Le graphe.** Un `Blocked by #n` écrit seulement dans le texte d'un ticket ne bloque rien pour
   `forge:feature-build` ni pour `report_mail.py`, qui lisent le graphe de GitHub. Une fois les
   tickets publiés (les bloqueurs d'abord, pour que leur numéro soit connu), lance
   `uv run --no-project --quiet python ${CLAUDE_PLUGIN_ROOT}/scripts/ticket_graph.py link <suivi> <tickets>` :
   chaque ticket devient sous-issue de l'issue de suivi, et chaque ligne `Blocked by #n` de son
   corps un lien `blocked_by`. Puis lance
   `uv run --no-project --quiet python ${CLAUDE_PLUGIN_ROOT}/scripts/ticket_graph.py check <suivi> <tickets>` :
   il liste chaque ticket hors de l'issue de suivi, chaque ligne `Blocked by #n` que le graphe n'a pas
   et chaque ticket dont le corps annonce une dépendance (`Blocked by`, `Depends on`, `Dépend de`,
   `Bloqué par`, suivi de `#n`) ailleurs que sur une telle ligne, que le script ne lit pas : une
   dépendance s'écrit donc sur une ligne qui commence par `Blocked by` (le gabarit `ticket.md` la
   porte). La publication n'est pas terminée tant que la liste n'est pas vide, et un code de sortie 2 (graphe
   illisible) ne vaut pas `GRAPH ok`.

   **La matrice.** Chaque ticket cite les identifiants de la source qu'il couvre (une ligne
   `Couvre : <identifiants>` dans son corps). Quand `matrice.md` existe dans le dossier de la
   feature (gabarit `${CLAUDE_PLUGIN_ROOT}/templates/features/matrice.md`), reporte-y le ticket de
   chaque identifiant, puis lance
   `uv run --no-project --quiet python ${CLAUDE_PLUGIN_ROOT}/scripts/matrice.py --sans-ticket <matrice.md>` :
   un identifiant listé n'est couvert par aucun ticket (y compris un identifiant de la source qui n'a
   pas encore de ligne dans la matrice), et le découpage le nomme, dans la PR et dans
   l'issue de suivi, à côté du ticket qui le prendra. Sans la clé `product-source`, l'étape est
   « sans objet (clé `product-source` absente) » : pas de matrice. L'écriture de la matrice initiale
   par la conception n'est pas décrite ici : elle viendra par son propre ticket, sur ce gabarit et
   ce script.

   Découpe avec le skill de la clé `ticket-skill` quand elle est déclarée. Sinon, découpe à la
   main, dans l'ordre du §7 du design, et dis-le (« clé `ticket-skill` absente »).

Commande suivante, une fois les tickets publiés : `/forge:feature-build F-NNNN`.
