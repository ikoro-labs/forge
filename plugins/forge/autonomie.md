# Qui lance une commande, et l'autonomie du projet

Un skill de la chaîne dont le front matter ne porte pas `disable-model-invocation` peut être lancé
par le modèle (outil Skill) comme par l'humain qui tape la commande. Chacun applique cette règle
avant sa première étape. Le projet décrit son usine dans `docs/agents/usine.md` : la clé que cette
règle lit est `agent-autonomy`, et une clé que le fichier ne porte pas rend l'étape « sans objet »,
sans valeur devinée.

## 1. Qui a lancé la commande

- **L'humain l'a tapée** : le tour porte un bloc `<command-name>`. La commande s'exécute comme
  toujours, sans lire la clé : l'autonomie du projet ne retire rien à l'humain.
- **Le modèle l'a lancée** (outil Skill, aucun bloc `<command-name>` dans le tour) : lis la clé, à
  l'étape 2.

## 2. La clé `agent-autonomy`

Une seule ligne, `agent-autonomy` : `on`, que l'utilisateur du projet écrit pour ouvrir l'autonomie
des agents sur ce projet. Le plugin ne la pose jamais.

- **Clé absente** : sans objet (clé `agent-autonomy` absente). N'écris rien, n'ouvre ni branche ni
  PR, ne lance aucun agent, et rends l'étape à l'humain : dis-lui la commande exacte à taper, avec
  ses arguments. Une valeur autre que `on` et une clé répétée se traitent de même, en citant la
  ligne fautive.
- **Clé à `on`** : la commande s'exécute. Le modèle l'a lancée à la place de l'humain, et rien de ce
  qu'il décide n'attend sa lecture avant d'être écrit : l'humain relit après coup.
