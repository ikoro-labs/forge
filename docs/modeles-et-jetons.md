# Modèles, effort et jetons

Ce que coûte l'usine, et comment le réduire ou le mesurer : le modèle et l'effort de chaque rôle,
les sorties de tests raccourcies, et l'audit des jetons.

## Les modèles des rôles

Chaque agent fixe dans son front matter un **niveau** de modèle, jamais l'identifiant d'un modèle :
le moins cher qui fait le travail, le plus fort là seulement où une erreur coûte.

| Agent | Niveau | Pourquoi |
| --- | --- | --- |
| `forge:qc-gate` | `haiku` | Il rejoue des commandes et recopie leurs mesures, sans avis. |
| `forge:coder` | `sonnet` | Le plus gros consommateur ; un modèle moyen code un ticket bien découpé. |
| `forge:qc-conf` | `opus` | Le garde-fou de la qualité ; il lit surtout le diff, sa tâche reste courte. Un autre niveau que le coder rend moins probable qu'une même erreur échappe aux deux. |
| `forge:staff-engineer`, `forge:product-owner` | `opus` | Appelés rarement, et leur décision engage la suite. |
| `forge:review-judge`, `forge:review-recheck` | `opus` | Ils jugent des captures contre la source, et un `tenu` publié à tort cache un écart à la clôture ; le juge réfléchit en `high`, la seconde lecture en `medium`. |

La session principale, celle qui lance les skills, n'est pas réglée par le plugin : c'est le
modèle choisi par `/model`, souvent le plus gros poste de consommation.

**L'effort de réflexion.** Avant de répondre, un modèle réfléchit, et cette réflexion se paie
comme du texte produit. Chaque agent fixe donc aussi son `effort` : `low` pour `forge:qc-gate`,
qui n'a rien à peser, `high` pour `forge:staff-engineer`, qui tranche les questions techniques
difficiles, `medium` pour les autres. `CLAUDE_CODE_EFFORT_LEVEL`, posé sur un poste, l'emporte sur
ce réglage. `forge:qc-gate` démarre aussi sans `CLAUDE.md` (`omitClaudeMd`, Claude Code 2.1.271 et
plus) : il lit ses portes dans `docs/agents/usine.md`. Le champ retire ceux du projet, mais aussi le
`~/.claude/CLAUDE.md` du poste et le `CLAUDE.local.md` ; seuls les fichiers de politique gérée
restent. Une consigne du poste dont `forge:qc-gate` aurait besoin (compte `gh`, proxy) ne lui
parvient donc pas. Ces deux champs sont ceux que la documentation de Claude Code donne pour un
agent ; leur gain n'est pas mesuré, et ils n'ont pas encore été essayés sur un vrai poste.

**Brancher un autre fournisseur.** Les quatre niveaux (`fable`, `opus`, `sonnet`, `haiku`) sont
des alias que chaque poste fait pointer où il veut, sans toucher au plugin :

- `ANTHROPIC_DEFAULT_FABLE_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`,
  `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL` : l'identifiant du modèle
  derrière chaque niveau ;
- `ANTHROPIC_BASE_URL` : l'adresse où Claude Code envoie ses requêtes, par exemple une passerelle
  compatible avec l'API Anthropic (LiteLLM, ou une autre) qui les relaie vers GPT, Grok ou un modèle
  local.

Ces variables se posent dans l'environnement du poste ou dans son `~/.claude/settings.json`, jamais
par le plugin. Elles valent pour tout le poste : deux rôles d'un même niveau ont le même modèle.
Sans elles, chaque niveau reste le modèle Claude du même nom.

Un appel qui fixe `model` l'emporte sur le front matter de l'agent.

Ces variables et la forme du champ `model` (un alias ou un identifiant) ont été lues dans Claude
Code 2.1.305. Une usine servie par un autre fournisseur, à travers une passerelle, n'a pas encore
été essayée : l'usage des outils et le cache de prompt peuvent s'y comporter autrement.

## Mesurer les jetons de chaque rôle

`/forge:audit-jetons` compte les jetons que chaque rôle a dépensés sur le projet, par modèle et par
effort, et compare un avant et un après :

```text
/forge:audit-jetons --coupure 2026-10-20T21:52
```

Il lit les journaux que Claude Code écrit déjà sur le poste (`~/.claude/projects/`, ou le dossier
de `CLAUDE_CONFIG_DIR`), ne garde que les réponses dont le dossier de travail est le projet ou l'un
de ses worktrees, et compte une seule fois une réponse écrite sur plusieurs lignes. `--depuis` et
`--jusqua` bornent la période ; `--coupure` la coupe en deux, par exemple à l'heure de fusion de la
PR qui a changé un modèle ou un effort. Une date sans zone est en UTC, comme les heures de GitHub.
La comparaison se fait en jetons par lancement d'agent, puisque le volume de travail change d'une
période à l'autre. Le script ne donne aucun prix : les quatre sortes de jetons (entrée, écriture
de cache, lecture de cache, sortie) n'ont pas le même, et chaque fournisseur a le sien.

Une limite des journaux eux-mêmes : Claude Code note la plupart des réponses des sous-agents avant
leur fin, avec la sortie connue à ce moment, bien en dessous de la vraie. Le rapport compte ces
réponses dans sa colonne « Sortie partielle » ; leur sortie est sous-comptée, l'entrée et le cache
ne le sont pas. Le format des journaux a été lu dans Claude Code 2.1.302 à 2.1.305 sous Linux ; il
n'est pas documenté et peut changer. Seul le script a tourné sur un vrai poste, sous Linux : le
skill lui-même n'a été lancé dans aucune session, et rien n'a été essayé sous Windows hors CI.

## Un budget de jetons par ticket

La clé `ticket-budget` de `docs/agents/usine.md` (un nombre entier de jetons, sans valeur par défaut)
plafonne ce qu'un ticket peut coûter. `forge:feature-build` additionne, par ticket, le
`subagent_tokens` de la notification de fin de chaque agent lancé pour lui, plus la part de la
session principale depuis la prise du ticket, lue comme `token_audit.py` la lit
(`scripts/ticket_budget.py`). Avant chaque lancement pour ce ticket, une somme strictement au-dessus
du budget ne lance rien : le ticket et sa PR reçoivent `needs-your-attention`, avec la somme, le détail par rôle et le dernier
verdict, et le passage continue avec le ticket suivant. La somme est écrite sous `jetons_agents` dans
la passation, qu'un relais reprend. Sans la clé, aucun plafond. Le coût par fusion en indicateur
(`tokens-per-merge`) reste à part (#56). Éprouvé par les tests sur des notifications fictives ; le
format de la notification d'un vrai agent n'est lu que dans le champ `subagent_tokens`, déjà utilisé par le
plafond de passage, et le contrôle n'a tourné dans aucun vrai passage.

## Les sorties de tests raccourcies

Une suite de tests qui passe rend des centaines de lignes que l'agent relit et paie en jetons, alors
que seul le résumé lui sert. Le hook `trim_output.py` (`PostToolUse`, sur `Bash`) raccourcit la
sortie d'une commande que nomme la clé `trimmed-command` de `docs/agents/usine.md` : la commande
lancée contient l'une de ses valeurs. Sans la clé, il ne fait rien.

- Une commande nommée qui réussit et rend plus de 60 lignes (les deux flux ensemble) : sa sortie
  complète est écrite dans un journal, `~/.claude/hooks/state/trimmed/<session>-<instant>.log`, et
  l'agent ne reçoit que les 20 dernières lignes de chaque flux plus long que cela, précédées du
  chemin du journal. Le dossier est commun à toutes les sessions et à tous les projets du poste ;
  les 20 journaux les plus récents y sont gardés, rangés par l'instant inscrit dans leur nom, et
  celui qu'une session vient d'écrire n'est jamais du nombre des supprimés.
- Une commande qui échoue n'est jamais raccourcie : Claude Code envoie alors `PostToolUseFailure`
  à la place de `PostToolUse`, et l'agent voit la sortie entière. Seul compte le code de sortie de
  la commande entière : une suite qui échoue derrière un tube (`| tee log`, `| tail`) ou suivie
  d'une autre commande (`; echo fini`) sort à 0, et sa sortie est raccourcie comme celle d'une
  suite qui passe. Le début de ses échecs n'est alors que dans le journal.
- `forge:qc-gate` reconnaît une sortie raccourcie à sa première ligne et relève les tests sautés
  dans le journal qu'elle nomme : ils sont au milieu de la sortie, que l'agent ne reçoit plus.
- Le hook observe : une entrée illisible ou un journal impossible à écrire le fait sortir à 0, la
  sortie d'origine intacte.

Éprouvé avec Claude Code 2.1.305 sous Linux, dans une session `claude -p --plugin-dir` lancée
depuis un projet jetable : 200 lignes d'une commande nommée qui réussit arrivent à l'agent en 21
lignes, et les mêmes 200 lignes d'une commande qui échoue arrivent entières. Pas encore essayé sous
Windows, ni dans une session interactive. Une commande lancée par l'outil `PowerShell` n'est pas
raccourcie.
