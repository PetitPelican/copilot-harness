---
name: agentic-agents
description: >
  Convertit un projet MONO-agent en MULTI-agents, ou ajoute un agent à un projet
  qui l'est déjà. Marche sur les DEUX organisations de mémoire : `brain/` (l'esprit
  de chaque agent va dans `brain/mind/<nom>/`) et l'ancienne (`agents/<nom>/.mind/`).
  Saute la migration de mémoire auto fichier sous Copilot, déclare le
  PAQUET à la racine git, écrit le profil de chaque agent pour le menu d'agent
  de l'app, amorce le carnet d'équipe et pose les périmètres contrôlés par la
  garde `PreToolUse`. `--profils` met à niveau un projet déjà en équipe. Ne découpe PAS le fichier AGENTS.md : c'est éditorial. Refuse un projet sans
  aucune maison de faits. Dry-run par défaut.
  Trigger: /agentic-agents, « passer ce projet en multi-agents », « ajouter un
  agent », « découper ce projet en lots », « ce projet a besoin de deux agents ».
---

# agentic-agents — un projet, plusieurs agents

**Un seul skill, deux comportements, et c'est la forme du projet qui décide.**
Sur un projet mono il convertit ; sur un projet déjà multi il ajoute. Les deux
sont la même opération à une étape près.

> **Avant de découper, lire [`references/roles.md`](references/roles.md).** Ce
> skill pose la mécanique ; il ne choisit pas les rôles, et c'est ce choix qui
> décide de tout le reste. On y trouve les trois rôles types et leurs
> frontières, pourquoi découper par couche technique (back/front) est presque
> toujours faux, ce que le modèle **ne** couvre pas, le seuil au-delà duquel un
> agent seul ne suffit plus, et ce que le multi-agents coûte réellement.
>
> Deux points qui se paient longtemps s'ils sont ratés ici : **le nom d'un rôle
> façonne le comportement de l'agent qui le porte**, et **chaque agent ajouté
> augmente ce qui remonte vers l'humain** — qui reste le seul à pouvoir
> débloquer un lot au profit d'un autre.

À ne pas confondre avec son voisin :

| | |
|---|---|
| `agentic-team` | la **vue** de l'atelier — lecture seule, ne modifie rien |
| **`agentic-agents`** | la **forme** du projet — combien d'agents y travaillent |

**Architecture compacte (0.17.0, opt-in).** `.github/agents/<slug>.agent.md`
porte le profil ET le rôle ; `.github/copilot/perimetres/<slug>.json` porte
la garde. La mémoire reste `brain/mind/<nom>/`, les livrables vont dans
`docs/livrables/<nom>/`. Aucun dossier `agents/<nom>/` n'est nécessaire.
Le choix dans le menu résout l'identité ; le contexte interne des hooks pointe
vers la mémoire de cet agent, sans changer le cwd réel de Copilot.
Un périmètre compact absent ou illisible refuse les écritures de fichiers.
En compact, `allow` est obligatoire : par défaut mémoire propre et
`docs/livrables/<nom>/`, liste vide pour QA. `deny` prime. Les chemins de code
autorisés se déclarent après arbitrage humain, jamais implicitement.
À l'export, le refus historique de tout `docs/` est remplacé par cette liste
positive : les autres documents restent inaccessibles en écriture.

```powershell
# Export d'une équipe existante, à blanc puis après accord :
harnais equipe --compact --project-root C:\Atelier\Projet
harnais equipe --compact --project-root C:\Atelier\Projet --apply
# Création depuis un mono adopté, ou ajout :
harnais equipe --agents OPS,PO --compact --project-root C:\Atelier\Projet
```

L'export affiche le contenu complet, conserve les personnalisations des profils
et fusionne leur rôle historique dans un bloc délimité. Il ne déplace ni mémoire,
ni documents, ni anciens dossiers. Il remplace les références des rôles exportés
à `agents/<nom>/livrables` par `docs/livrables/<nom>` : la migration des livrables
et des références communes est séparée et nécessite l'accord humain.
Relire le profil fusionné. Valider les nouvelles sessions, puis seulement
archiver/retirer les anciens dossiers sur accord. Les deux formes restent lues.
Sur une équipe compacte, les nouveaux agents gardent la forme compacte.

**Architecture historique, encore prise en charge.**
`agents/<nom>/` porte le RÔLE de l'agent (`AGENTS.md`) et son périmètre ;
`.github/agents/<nom>.agent.md` est son PROFIL, ce qui le fait apparaître dans
le menu d'agent de l'app. Le profil reste court et ne recopie pas le rôle : le
harnais lit le choix dans le journal de session et sert lui-même le rôle,
l'état et le périmètre. Les deux portent le même nom, slugifié en minuscules
(`OPS` → `ops`, `Projet QA` → `projet-qa`).

## Quand un projet mérite plusieurs agents

Les fiches personnalisables sont dans [`references/profiles/`](references/profiles/).
Présenter OPS (socle), PO (produit), QA (épreuve), puis faire choisir
un ou plusieurs profils. **Un seul reste mono-agent**, avec son rôle
dans le `AGENTS.md` racine : ne pas appeler `equipe` pour ce cas.
Avant de créer, proposer nom, périmètre, règles propres et ton ; reprendre
les réponses de l'accueil CTO sans les redemander. QA ne reçoit aucun
droit d'écriture. Les fiches renvoient à `roles.md`, qui reste la référence
pour le découpage et les frontières.

Quand deux lots ont des **rythmes** différents et des **contextes disjoints** —
typiquement fiabilité/infra d'un côté, produit/apps de l'autre. Chacun mérite
alors sa santé, son jalon, sa todo. Un seul agent qui alterne entre les deux
garde une fenêtre à moitié hors sujet.

Ce n'est **pas** une réponse à « le projet est gros ». Un projet gros mais d'un
seul tenant se tient très bien à un agent, et la forme mono coûte moins cher.

## Ce que le script fait

```
brain/mind/{state,todo}.md  ->  brain/mind/<premier>/       l'agent qui était là garde sa mémoire
.github/copilot/settings.json reste à la racine git (activation unique)
.github/agents/<nom>.agent.md  le profil du menu d'agent — jamais écrasé
agents/<nom>/.github/copilot/perimetre.json porte la garde d'écriture, en chemins relatifs
pas de mémoire auto fichier Copilot à migrer
agents/<autres>/            ->  créés, avec rôle et réglages ; leur état neuf dans brain/mind/<nom>/
brain/fact/roles.md         ->  qui tient quoi, et les zones partagées
brain/workspace/            ->  le carnet d'équipe, AMORCÉ
```

Dans l'organisation d'avant, la même opération range l'état dans
`agents/<nom>/.mind/`, `roles.md` dans `.fact/` et le carnet dans `equipe/`.

**Ce que le paquet supprime, et c'était l'étape la plus fragile.** Avant, chaque
agent recevait une copie des déclarations de hooks, dont chaque chemin devait
être repointé vers la source commune deux crans plus haut. **Cette étape
n'existe plus** : les hooks viennent du paquet, par un chemin absolu que l'outil
fournit lui-même. Plus de chemin relatif, plus de lien symbolique, et plus la
panne muette d'un clone Windows qui transforme le lien en fichier texte. Il ne
reste à écrire que deux faits : **quel paquet**, et **ce que cet agent n'a pas
le droit de toucher**.

Les déclarations de hooks présentes sont **retirées** au passage. Deux jeux sur
le même événement, ce sont deux briefings et deux poussées vers le téléphone, et
personne ne verrait lequel a parlé.

**Le carnet d'équipe est amorcé ici, et nulle part ailleurs.** Il est LU
partout — entrées, chiffres de confiance, résumé servi au briefing : sans
création au découpage, un projet neuf passé en multi-agents aurait un dispositif
muet sans que rien ne l'explique. Ce n'est délibérément pas un hook qui le crée :
un projet mono n'a pas d'équipe, et lui fabriquer un carnet vide à chaque tour
donnerait un dispositif qui a l'air monté sans que personne l'ait décidé.

Les faits, `docs/`, `.logs/`, le code : **rien ne bouge** — seul `roles.md`
s'ajoute aux faits. Aucun n'appartient à un agent.

**Qui parle.** L'app Copilot lance chaque conversation à la racine d'une
copie de travail : le dossier ne dit plus qui parle. L'agent se choisit dans
le menu d'agent du champ de saisie ; le harnais lit ce choix dans le journal
de session et se place dans `agents/<nom>/`. Règle : le menu, sinon le dossier
de lancement (CLI), sinon QA s'il existe (« Default agent » prend QA), sinon
aucun agent — le briefing le dit. Une conversation, un agent : le choisir
avant le premier message.

**Limite de la forme multi-agents :** Copilot ne lit `.github/copilot/settings.json`
qu'à la racine du dépôt git. Le paquet s'y active une fois pour tous les
agents ; la séparation entre agents vient du choix d'agent et de la garde, pas
des réglages. Vérifier dans chaque session la ligne `agent` du briefing et un
refus de la garde, ne pas annoncer l'isolation comme acquise.

**Un agent du projet appelé comme sous-agent** (outil task, ou délégation
décidée par le modèle) n'est pas suivi : ses écritures sont jugées sous le
périmètre de l'agent de la conversation. Le profil n'interdit pas cette
délégation ; `disable-model-invocation: true` le ferait d'après la
documentation de Copilot, **non mesuré** sur le menu de l'app.

## Le piège qu'il existe pour éviter

Copilot n'a pas de mémoire auto fichier indexée par chemin. Sa migration
est sautée en le disant. L'effet du changement de `cwd` sur la reprise des
sessions `~/.copilot/session-state/` est **non mesuré**.

Il refuse aussi deux noms qui se **slugifient pareil** (`<projet> OPS` et
`<projet>-OPS`) : leurs dossiers ou leurs états risqueraient de se confondre.

Et il refuse si le projet porte encore des hooks locaux d'avant le paquet :
leur `briefing`, à une seule remontée, ne verrait jamais les faits depuis un
dossier d'agent. Les retirer et déclarer le paquet d'abord (`harnais adopte
--go`). Sous le paquet la question ne se pose plus — c'est le paquet qui porte
la version — mais un projet peut encore arriver avec ses anciens hooks à la
main, et ce sont eux qui sont testés.

## Marche à suivre

```bash
# 1. le projet doit déjà avoir ses faits (brain/fact/ ou .fact/) — sinon :
harnais adopte --go

# 2. à blanc, toujours — le premier nommé hérite de l'état existant
harnais equipe --project-root . --agents "OPS,PO"

# 3. appliquer
harnais equipe --project-root . --agents "OPS,PO" --apply

# un projet passé en équipe avant 0.16.0 : profils manquants, périmètres relatifs
harnais equipe --project-root . --profils --apply
```

Puis **commiter** : une nouvelle conversation de l'app part de l'état commité,
un profil non commité n'apparaît pas dans le menu.

Le programme est celui du paquet, le même sur Mac et sur Windows — le
briefing d'un projet en donne le chemin exact. C'est un programme natif : il ne
dépend d'aucun interpréteur installé sur la machine.

## Ce qui reste à la main

1. **Découper le `AGENTS.md`** : le commun reste à la racine git, le rôle
   descend dans `agents/<nom>/AGENTS.md`. Si `CLAUDE.md` existe, le signaler
   plutôt que laisser deux instructions contradictoires : Copilot lit les deux.
2. **Déclarer les périmètres dans la source de vérité du harnais** posée
   par `equipe`, non dans `permissions.deny` (ignoré hors réglages managés).
   La garde `PreToolUse` refuse `Edit|Write` (`edit/create`) dans les
   dossiers interdits à l'agent actif (`permissionDecision: deny` et raison),
   en chemins relatifs à la racine du projet, posés sur la copie de travail
   courante. Sans fichier, fail-open. Les écritures par shell ne sont pas
   couvertes par ce matcher.
3. **Résoudre le paquet** : `copilot plugin marketplace add <chemin-local>`
   puis `copilot plugin install harnais@atelier-copilot`. Les fichiers
   des dossiers d'agent ne suffisent pas ; tester briefing et garde de chacun.
4. **Commiter, puis choisir l'agent dans le menu d'agent de l'app** (`ops`,
   `po`, `qa`…) — dans le CLI, `copilot --agent <nom>` ou une session lancée
   dans `agents/<nom>/`. Vérifier la ligne `agent` du premier briefing.
