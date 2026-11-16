# <Titre : ce qui s'est passé, en une ligne, sans nom de personne>

- Date : <AAAA-MM-JJ, le jour de l'incident>
- Origine : <sev1, sev2 ou usine>
- Classe : <mécanique ou jugement>

## Faits

- <AAAA-MM-JJ> : <un fait daté, avec sa source : commit, PR, run, ticket ou journal>

## Cause

<Le mécanisme qui a produit l'incident, en une ou deux phrases. Une cause est un mécanisme, jamais une personne.>

## Ce qui l'a laissé passer

<Le contrôle qui manquait, ou celui qui ne regardait pas là. Un contrôle qui existait et n'a rien vu se nomme.>

## Correctif

Une ligne `- Correctif :` par correctif, de la forme que la classe exige. Une consigne seule ou une
entrée de mémoire seule n'est jamais un correctif suffisant.

- `mécanique` (une règle qu'une machine peut vérifier) : `#<n>`, le ticket `ready-for-agent` d'un
  contrôle déterministe et de son test, ou `existant : <chemin du contrôle> ; <chemin de son test>`
  quand le contrôle est déjà dans le dépôt.
- `jugement` (ce que seul un agent voit) : `cas : <chemin du dossier du cas>`, un cas ajouté au jeu
  de référence.

- Correctif : <#n, ou existant : <contrôle> ; <test>, ou cas : <dossier>>
