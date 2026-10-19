# Format du rapport HTML

La revue d'architecture est rendue sous la forme d'un unique fichier HTML autonome, placé dans le répertoire temporaire du système. Tailwind et Mermaid proviennent tous deux de CDN. Mermaid gère de façon fiable les schémas en forme de graphe ; des divs construits à la main et du SVG inline prennent en charge les visuels plus éditoriaux (schémas de masse, vues en coupe). Combiner les deux : ne pas tout confier à Mermaid, sinon le rendu devient vite générique.

## Squelette

```html
<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <title>Revue d'architecture {{F-NNNN ou zone}}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({ startOnLoad: true, theme: "neutral", securityLevel: "loose" });
    </script>
    <style>
      /* petite couche sur mesure pour ce que Tailwind ne couvre pas proprement :
         lignes de seam en pointillés, pointes de flèche à l'allure dessinée main, etc. */
      .seam { stroke-dasharray: 4 4; }
      .leak { stroke: #dc2626; }
      .deep { background: linear-gradient(135deg, #0f172a, #1e293b); }
    </style>
  </head>
  <body class="bg-stone-50 text-slate-900 font-sans">
    <main class="max-w-5xl mx-auto px-6 py-12 space-y-12">
      <header>...</header>
      <section id="candidates" class="space-y-10">...</section>
      <section id="top-recommendation">...</section>
    </main>
  </body>
</html>
```

## En-tête

Nom du dépôt, date et une légende compacte : boîte pleine = module, ligne pointillée = seam, flèche rouge = fuite, boîte sombre épaisse = module profond. Pas de paragraphe d'introduction. Directement les candidats.

## Carte de candidat

Les schémas portent l'essentiel. La prose est rare, simple, et emploie les termes du glossaire (issus du skill `/codebase-design`) sans cérémonie.

Chaque candidat est un `<article>` :

- **Titre** : court, nomme l'approfondissement (par exemple « Fusionner le pipeline de réception des commandes »).
- **Rangée de badges** : force de la recommandation (`Fort` = emerald, `À explorer` = amber, `Spéculatif` = slate), plus une étiquette pour la catégorie de dépendance (`en processus`, `substituable localement`, `ports et adaptateurs`, `mock`).
- **Fichiers** : liste en chasse fixe, `font-mono text-sm`.
- **Schéma avant / après** : la pièce maîtresse. Deux colonnes, côte à côte. Voir les modèles ci-dessous.
- **Problème** : une phrase. Ce qui fait mal.
- **Solution** : une phrase. Ce qui change.
- **Gains** : puces, 6 mots au plus chacune. Par exemple « Les tests passent par une interface », « La logique de prix ne fuit plus », « Supprimer 4 wrappers superficiels ».
- **Encadré ADR** (le cas échéant) : une ligne dans une boîte teintée d'amber.

Pas de paragraphes d'explication. Si le schéma a besoin d'un paragraphe pour être compris, redessiner le schéma.

## Modèles de schémas

Choisir le modèle qui convient au candidat. Les combiner. Ne pas donner à tous les schémas le même aspect. La variété fait partie de l'intérêt.

### Graphe Mermaid (l'outil de base pour les dépendances et le flux d'appels)

Utiliser un `flowchart` ou un `graph` Mermaid quand le propos est « X appelle Y qui appelle Z, et voyez le désordre ». L'envelopper dans une carte stylée avec Tailwind pour qu'il ne semble pas parachuté. Styliser avec classDef pour colorer en rouge les arêtes de fuite et en sombre le module profond. Les diagrammes de séquence fonctionnent bien pour « avant : 6 allers-retours ; après : 1 ».

```html
<div class="rounded-lg border border-slate-200 bg-white p-4">
  <pre class="mermaid">
    flowchart LR
      A[OrderHandler] --> B[OrderValidator]
      B --> C[OrderRepo]
      C -.fuite.-> D[PricingClient]
      classDef leak stroke:#dc2626,stroke-width:2px;
      class C,D leak
  </pre>
</div>
```

### Boîtes et flèches faites main (quand la mise en page de Mermaid résiste)

Les modules sont des `<div>` avec bordures et libellés. Les flèches sont des éléments SVG inline `<line>` ou `<path>` positionnés en absolu au-dessus d'un conteneur en position relative. Y recourir quand le schéma « après » doit apparaître comme un seul module profond à bordure épaisse, aux éléments internes grisés, car Mermaid ne le rendra pas avec le bon poids.

### Vue en coupe (adaptée à la superficialité empilée)

Empiler des bandes horizontales (`h-12 border-l-4`) pour montrer les niveaux que traverse un appel. Avant : 6 niveaux fins qui ne font rien. Après : 1 bande épaisse portant la responsabilité consolidée.

### Schéma de masse (adapté à « une interface aussi large que l'implémentation »)

Deux rectangles par module : un pour la surface de l'interface, un pour l'implémentation. Avant : le rectangle de l'interface est presque aussi haut que celui de l'implémentation (superficiel). Après : le rectangle de l'interface est court, celui de l'implémentation est haut (profond).

### Effondrement du graphe d'appels

Avant : un arbre d'appels de fonctions rendu en boîtes imbriquées. Après : le même arbre replié en une seule boîte, les appels devenus internes affichés en transparence à l'intérieur.

## Conseils de style

- Viser l'éditorial, pas le tableau de bord d'entreprise. Des espaces généreux. Serif facultatif pour les titres (`font-serif` s'accorde bien avec stone/slate).
- Couleur avec parcimonie : un accent (emerald ou indigo), plus le rouge pour les fuites et l'amber pour les avertissements.
- Garder les schémas autour de 320px de haut pour que l'avant et l'après tiennent confortablement côte à côte sans défilement.
- Utiliser `text-xs uppercase tracking-wider` pour les libellés de modules dans les schémas, afin qu'ils se lisent comme un schéma technique et non comme une interface utilisateur.
- Les seuls scripts sont le CDN Tailwind et l'import ESM de Mermaid. Le rapport est par ailleurs statique : pas de code applicatif, aucune interactivité au-delà du rendu de Mermaid.

## Section de la recommandation prioritaire

Une seule carte, plus grande. Nom du candidat, une phrase sur la raison, lien d'ancre vers sa carte. C'est tout.

## Ton

Un français simple et concis, mais les noms et verbes d'architecture viennent directement du skill `/codebase-design`. La concision n'excuse pas la dérive.

**Employer exactement :** module, interface, implémentation, profondeur, profond, superficiel, seam, adaptateur, levier, localité.

**Ne jamais substituer :** composant, service, unité (pour module) · API, signature (pour interface) · frontière (pour seam) · couche, wrapper (pour module, quand on veut dire module).

**Formulations dans le style attendu :**

- « Le module de réception des commandes est superficiel : l'interface reproduit presque l'implémentation. »
- « La tarification fuit à travers le seam. »
- « Approfondir : une interface, un seul endroit à tester. »
- « Deux adaptateurs justifient le seam : HTTP en production, en mémoire dans les tests. »

**Les puces de gains** nomment le bénéfice dans les termes du glossaire : *« localité : les bugs se concentrent dans un module »*, *« levier : une interface, N sites d'appel »*, *« l'interface rétrécit ; l'implémentation absorbe les wrappers »*. Ne pas écrire *« plus facile à maintenir »* ou *« code plus propre »* : ces termes ne figurent pas dans le glossaire et ne méritent pas leur place.

Pas de précautions oratoires, pas de raclements de gorge, pas de « il convient de noter que… ». Si une phrase peut devenir une puce, en faire une puce. Si une puce peut être coupée, la couper. Si un terme ne figure pas dans le glossaire de `/codebase-design`, en chercher un qui y figure avant d'en inventer un nouveau.
