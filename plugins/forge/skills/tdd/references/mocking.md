# Quand simuler

Ne simuler qu'aux **frontières du système** :

- les services externes (paiement, courriel, etc.) ;
- le temps et le hasard ;
- la base de données (parfois : préférer une base de test) ;
- le système de fichiers (parfois).

Ne pas simuler :

- ses propres classes et modules ;
- les collaborateurs internes ;
- tout ce que l'on contrôle.

La règle courte : jamais un collaborateur interne. Si un test a besoin de simuler une partie interne pour passer, c'est la couture qui est mal placée ou le module mal découpé (voir `forge:codebase-design`), pas un cas pour un mock.

## Concevoir pour qu'une frontière se remplace

À une frontière du système, concevoir des interfaces faciles à remplacer.

**1. Injection de dépendance.** Passer les dépendances externes en paramètre au lieu de les créer à l'intérieur :

```python
# Facile à remplacer
def traiter_paiement(commande, client_paiement):
    return client_paiement.debiter(commande.total)

# Difficile à remplacer
def traiter_paiement(commande):
    client = ClientStripe(os.environ["CLE_STRIPE"])
    return client.debiter(commande.total)
```

**2. Des interfaces par opération plutôt qu'un récupérateur générique.** Une fonction par opération externe, au lieu d'une fonction unique pleine de conditions :

```python
# BON : chaque fonction se remplace seule
api = {
    "lire_utilisateur": lambda id: http_get(f"/utilisateurs/{id}"),
    "lire_commandes": lambda id: http_get(f"/utilisateurs/{id}/commandes"),
    "creer_commande": lambda donnees: http_post("/commandes", donnees),
}

# MAUVAIS : le simulacre doit contenir de la logique conditionnelle
api = {"requete": lambda chemin, options: http(chemin, options)}
```

Avec une interface par opération :

- chaque simulacre rend une seule forme ;
- la mise en place du test n'a aucune condition ;
- on voit quelles opérations un test exerce ;
- le typage se fait par opération.
