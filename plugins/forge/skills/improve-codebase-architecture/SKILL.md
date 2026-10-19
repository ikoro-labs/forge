---
name: improve-codebase-architecture
description: "Revue d'architecture d'une zone du code, de préférence avant le design d'une feature : repérer les modules superficiels, présenter les approfondissements dans un rapport HTML, les trancher avec un humain, puis consigner l'issue de chaque candidat."
argument-hint: "[F-NNNN | chemin]"
disable-model-invocation: true
---

# Improve Codebase Architecture

Repérer les frictions d'architecture et proposer des **approfondissements** : des refontes qui
transforment des modules superficiels en modules profonds, pour garder un code testable et lisible
par les agents.

Ce skill se conduit avec un humain, dans une session interactive : c'est lui qui tranche les
candidats. Les agents de l'usine ne l'exécutent pas ; ils en lisent le compte rendu.

Vocabulaire d'architecture : `/forge:codebase-design`, employé exactement (module, interface,
implémentation, profondeur, seam, adaptateur, levier, localité). Vocabulaire métier : le glossaire
du contexte (clé `glossary` de `docs/agents/usine.md`). Les ADR de `docs/adr/` consignent des
décisions acquises.

## 1. Cadrer

Approfondir paie en rendant les prochains changements faciles : commencer par ce que la feature va
toucher.

- Pour une feature, lire son dossier (clé `feature-dir`) : la spec et le design en cours désignent
  la zone prioritaire. Pour un chemin donné, partir de lui.
- Parcourir `git log --oneline` sur une bonne période pour repérer les points chauds ; élargir quand
  les changements sont dispersés.
- Lire les termes concernés du glossaire et les ADR de la zone.

Une direction donnée par l'humain remplace cette inférence.

## 2. Explorer

Confier l'exploration à un sous-agent, sans grille rigide, en relevant les frictions :

- comprendre un concept oblige à passer par beaucoup de petits modules ;
- l'interface d'un module est presque aussi complexe que son implémentation ;
- des fonctions pures extraites pour les tests laissent les vrais bugs dans leur appel ;
- des modules couplés fuient à travers leur seam ;
- du code non testé, ou difficile à tester par son interface actuelle.

Passer chaque suspect au test de suppression. Classer ses dépendances (en processus, substituable localement, distante possédée, externe) : la catégorie fixe la stratégie de test.

## 3. Présenter le rapport

Écrire un rapport HTML autonome dans le répertoire temporaire du système (`%TEMP%` sous Windows, `$TMPDIR` ou `/tmp` ailleurs) : `architecture-review-<F-NNNN ou zone>-<horodatage>.html`. L'ouvrir et donner son chemin absolu. Le dépôt reste inchangé à cette étape. Gabarit, diagrammes et ton : [HTML-REPORT.md](HTML-REPORT.md), en français, termes de codebase-design inchangés.

Une carte par candidat : fichiers, problème, solution, bénéfices en levier et localité avec l'effet sur les tests, schéma avant/après, force (`strong`, `worth-exploring`, `speculative`). Un candidat qui contredit un ADR apparaît seulement si la friction justifie de rouvrir l'ADR, et le dit. Terminer par la recommandation prioritaire. Garder les interfaces pour l'étape suivante et demander : « Lequel voulez-vous explorer ? »

Aucun candidat sérieux est un résultat valide : le rapport le dit.

## 4. Trancher

Pour le candidat choisi, conduire l'interrogatoire par tours de questions, chacune avec ta recommandation : contraintes, dépendances, forme du module approfondi, ce qui passe derrière le seam, tests qui survivent. Pour comparer des interfaces, **concevoir deux fois** : plusieurs sous-agents en parallèle, chacun sous une contrainte radicalement différente (interface minimale, flexibilité, appelant le plus fréquent, ports et adaptateurs). Comparer en profondeur, localité et placement du seam, puis recommander.

Effets au fil des décisions :

- un module nommé d'après un concept absent du glossaire, ou un terme précisé : suivre `/forge:domain-modeling` ;
- un candidat écarté pour une raison durable : proposer un ADR dans `docs/adr/` (format `${CLAUDE_PLUGIN_ROOT}/templates/adr.md` ou gabarit du projet), pour que les revues suivantes ne le reproposent pas ;
- un candidat retenu : soit une refonte livrée dans sa propre PR avant la feature, soit un approfondissement que le design reprend dans sa carte des modules (`/forge:codebase-design`).

## 5. Consigner

Le compte rendu entre dans le dépôt, pour que la revue suivante et les agents le lisent :

- pour une feature, dans son design (section « Ports et adapters », ou une séance
  `/forge:feature-brainstorm` si le design n'est pas encore ouvert) ;
- hors feature, dans le ticket ou la PR de la refonte.

Il porte : le commit relu (SHA complet), les chemins réellement explorés, l'humain qui a tranché, une
conclusion en une à trois phrases, et chaque candidat présenté avec sa force (`strong`,
`worth-exploring`, `speculative`) et son issue : retenu (la feature le reprend), reporté, écarté, ou
écarté et consigné en ADR. Aucun candidat est un résultat valide : la conclusion dit pourquoi.

Une refonte retenue et livrée change le code : une revue courte la confirme avant le design.

Fin : le compte rendu est dans le dépôt, son commit relu est un ancêtre de la base du design, et
chaque candidat présenté y figure avec son issue.

Provenance : [copie amont inactive](references/upstream.md), et `THIRD_PARTY_NOTICES.md` à la racine
du plugin.
