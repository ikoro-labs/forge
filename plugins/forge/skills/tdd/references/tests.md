# Bons et mauvais tests

## Un bon test

**De style intégration** : il passe par les vraies interfaces, pas par des simulacres des parties internes.

```python
# BON : vérifie un comportement observable
def test_un_client_peut_valider_un_panier_valide():
    panier = creer_panier()
    panier.ajouter(produit)
    resultat = valider(panier, moyen_de_paiement)
    assert resultat.statut == "confirme"
```

Ses traits :

- il vérifie ce qui compte pour l'appelant ;
- il n'utilise que l'interface publique ;
- il survit aux refontes internes ;
- il dit QUOI, pas COMMENT ;
- une seule assertion logique par test.

## Un mauvais test

**Couplé à l'implémentation** : il dépend de la structure interne.

```python
# MAUVAIS : vérifie un détail d'implémentation
def test_valider_appelle_service_paiement_traiter():
    faux = Mock(service_paiement)
    valider(panier, paiement)
    faux.traiter.assert_called_with(panier.total)
```

Les signes :

- simuler un collaborateur interne ;
- tester une méthode privée ;
- asserter sur le nombre ou l'ordre des appels ;
- le test casse sur une refonte sans changement de comportement ;
- le nom du test décrit le COMMENT, pas le QUOI ;
- vérifier par un autre chemin que l'interface.

```python
# MAUVAIS : contourne l'interface pour vérifier
def test_creer_utilisateur_ecrit_en_base():
    creer_utilisateur(nom="Alice")
    ligne = base.requete("SELECT * FROM utilisateurs WHERE nom = ?", ["Alice"])
    assert ligne is not None

# BON : vérifie par l'interface
def test_creer_utilisateur_le_rend_retrouvable():
    utilisateur = creer_utilisateur(nom="Alice")
    assert lire_utilisateur(utilisateur.id).nom == "Alice"
```

## Un test tautologique

L'attendu reformule l'implémentation : le test passe par construction.

```python
# MAUVAIS : l'attendu est recalculé comme le code le calcule
def test_total_somme_les_lignes():
    lignes = [{"prix": 10}, {"prix": 5}]
    attendu = sum(ligne["prix"] for ligne in lignes)
    assert total(lignes) == attendu

# BON : l'attendu est un littéral indépendant et connu
def test_total_somme_les_lignes():
    assert total([{"prix": 10}, {"prix": 5}]) == 15
```
