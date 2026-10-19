---
feature: F-NNNN
document: design
statut: en-revue
destinataires: <l'agent qui implémente ; qui relit>
adr: <ADR-NNNN, ADR-NNNN, ou « aucun »>
base: <commit>
date: AAAA-MM-JJ
---

# F-NNNN : design

En taille S, ce document se saute si rien ne le déclenche : ni technologie, ni architecture, ni
service, ni contrat d'API, ni modèle IA, ni sécurité, ni schéma non trivial.

## 1. Contextes touchés

| Contexte | Ce qui change | Couture avec les autres |
|---|---|---|

## 2. Ports et adapters

<Les ports nouveaux ou modifiés, qui les implémente, qui les appelle. Le domaine ne dépend de rien.>

## 3. Modèle de données

<Tables, contraintes, migration (expand puis contract si le changement est large).>

## 4. Frontière de confiance

<Ce qui entre de l'extérieur, où c'est validé, qui a le droit de faire quoi.>

## 5. Observabilité

| Question | Métrique, alerte ou attribut de trace | Où c'est émis |
|---|---|---|
| Ça marche ? | | |
| Ça casse ? | | |
| Que voit-on dans la trace ? | | |

## 6. Coutures de test

<La couture la plus haute qui existe, et les deux ou trois autres au plus. Ce qu'est un bon test ici.>

## 7. Découpage en tickets

<Tranches verticales, dans l'ordre, avec ce qui bloque quoi.>

## 8. ADR déclenchés

| ADR | Décision | Statut |
|---|---|---|

## 9. Décisions prises pendant la construction

| Ticket | Décision | Par | Source |
|---|---|---|---|
