---
type: llm
weight: 0.5
---
Le verdict signale que `commits_refusal` rend `None` quand la liste des commits est illisible, donc que le critère « fermé par défaut : une liste illisible vaut refus » n'est pas tenu, ou que `test_an_unreadable_list_of_commits_refuses_the_merge` échouerait.
