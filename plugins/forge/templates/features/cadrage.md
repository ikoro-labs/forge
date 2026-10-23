---
feature: F-NNNN
document: cadrage
statut: en-revue
taille: <S | M | L>
destinataires: <qui décide, qui relit>
contexte: <contexte principal ; contextes touchés>
base: <commit sur lequel le document est écrit>
date: AAAA-MM-JJ
---

# F-NNNN : cadrage

<Deux phrases : ce que la feature fait, et ce qu'elle prouve. 45 minutes au plus ; une page en
taille S.>

## 1. Problème

**Qui souffre, de quoi.** <L'utilisateur et sa douleur, chiffrée si possible.>

**Pourquoi pas plus simple.** <Une règle, une requête, une configuration suffiraient-elles ? La
solution la plus simple qui suffit, et pourquoi elle ne suffit pas si on en prend une autre.>

**Le cas d'usage unique.** <Un scénario, de bout en bout.>

## 2. Périmètre

| Exigence | Contenu | Preuve |
|---|---|---|
| <EXI-NN> | <ce qui est dedans> | <texte de référence, principe, retour du terrain, demande> |

**Hors périmètre.** <Ce qui n'y est pas, et où cela ira.>

## 3. Condition d'entrée

<La règle de la clé `entry-gate` et ce qui l'admet ici, source citée ; ou « sans objet (clé
entry-gate absente) ». Si la règle ne l'admet pas, la feature passe au rôle `hors-perimetre` (clé
`feature-state`) dans
`idee.md` et la chaîne s'arrête ici.>

## 4. Observabilité

| Question | Réponse |
|---|---|
| Quelle métrique prouve que ça marche | |
| Quelle alerte si ça casse | |
| Que voit-on dans une trace | |

## 5. Risques

| Risque | Mitigation | Signal |
|---|---|---|

## 6. Faisabilité des données

<Jeu d'acceptation, données de mesure, données exclues et pourquoi.>

## 7. Décisions

| Date | Décision | Par | Séance |
|---|---|---|---|

## 8. Critères d'arrêt

| Vérification | Condition de poursuite | Si non atteinte |
|---|---|---|
| <mesure datée> | | |
