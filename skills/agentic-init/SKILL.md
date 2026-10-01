---
name: agentic-init
description: >
  Monte un ATELIER agentique sur une machine neuve — la couche au-dessus des
  projets : le fichier AGENTS.md de méthode à la racine et sa copie locale dans les instructions du CTO,
  le poste du CTO, harnais posé. À lancer UNE fois par machine, avant tout
  projet. Pour poser le harnais sur un projet, c'est agentic-adopte.
  Trigger: /agentic-init, « installer le CTO », « porter l'atelier sur cette machine ».
---

# Agentic Init

> **Quand l'utiliser** : une machine neuve sur laquelle on veut reposer la même
> architecture agentique. Une fois, avant les projets. Un **projet** à monter →
> `/agentic-adopte`. Ce skill ne touche à aucun projet.

## Ce qu'il monte

```
<racine>/                      ~/Agentic, C:\Users\<toi>\Documents\AGENTIC…
├── AGENTS.md                  ← LA MÉTHODE commune.
├── cto/                       ← le poste du CTO
│   ├── AGENTS.md              son rôle seulement
│   ├── .github/copilot-instructions.md  copie de la méthode, découverte dans le dépôt
│   ├── .github/copilot/settings.json  déclaré ici (voir limite racine git ci-dessous)
│   ├── brain/fact/ brain/mind/  sa mémoire : l'atelier, pas les projets
│   ├── docs/projects.json     projets explicitement déclarés ; vide au départ
│   └── .git/                  sans dépôt, les gardes de commit sont inertes
└── <projet>/                  montés ensuite, un par un
```

## Trois couches, une seule voyage

| Couche | Fichier | Contenu | Portable ? |
|---|---|---|---|
| Poste | `~/.copilot/copilot-instructions.md` | comptes, sessions, réseau, mémoire vive | non — refait par machine |
| **Méthode** | **`<racine>/AGENTS.md`** | mémoire, hooks, compétences, frontières | **oui — c'est l'artefact** |
| Projet | `<projet>/AGENTS.md` | rôle, stack, règles métier | non — propre au projet |

**Copilot cumule les instructions sans priorité garantie entre `AGENTS.md` et
`CLAUDE.md`.** Si ce dernier existe, signaler le doublon et ne pas poser un
`AGENTS.md` contradictoire. Copilot ne remonte pas au-dessus de la racine git :
`adopte` ajoute donc la méthode dans `.github/copilot-instructions.md`
du dépôt, après les instructions existantes. La variable
`COPILOT_CUSTOM_INSTRUCTIONS_DIRS` reste un complément pour les hôtes
qui la prennent en charge. Ne pas placer le rôle du CTO dans la méthode.

## Le geste

```bash
harnais atelier-monte --racine ~/Agentic --utilisateur "<TonPrénom>"        # à blanc
harnais atelier-monte --racine ~/Agentic --utilisateur "<TonPrénom>" --go   # écrit
```

Le programme est celui du paquet, le même sur Mac et sur Windows — le
briefing d'un projet en donne le chemin exact. Il pose la méthode à la racine,
le rôle du CTO, un dépôt git, puis le harnais du CTO par `harnais adopte`.
**Rien n'est remplacé** : les fichiers de mémoire et de rôle sont conservés ;
les réglages sont fusionnés et la méthode est ajoutée une seule fois aux
instructions locales.

## Dernière étape — passer la main, et le DIRE

L'installation dans un dossier `CTO` déjà créé est le parcours normal :
avec l'installateur Windows, fournir `-CtoName CTO`. Prévisualiser depuis ce
dossier, montrer le résultat, puis attendre l'accord avant `-Go`.
Ne pas contourner la politique d'exécution PowerShell.
Après l'application, arrêter cette session et demander un redémarrage.
L'accueil appartient au rôle CTO et au briefing, pas à la méthode commune :
le registre `docs/projects.json` évite de questionner tous les agents projet.
Tant qu'il est vide, le CTO complète sa mémoire, recueille le projet, fait
choisir et personnaliser OPS/PO/QA, puis adopte après accord explicite.
Une déclaration réussie arrête cet accueil ; commiter le registre pour les
prochaines sessions en worktree.

**Avant la nouvelle session, contrôler les instructions locales.**
`install.ps1` ajoute aussi l'atelier à `COPILOT_CUSTOM_INSTRUCTIONS_DIRS`
sans écraser les valeurs existantes ; `atelier-monte` ne pose pas cette variable.
Vérifier la racine git avec `git rev-parse --show-toplevel` : la configuration
Copilot est liée à cette racine, pas au dossier de lancement.

**La session qui monte l'atelier n'est pas celle qui l'exploite.** Quand tout
est en place, ne pas enchaîner : **prévenir l'utilisateur, explicitement, et
s'arrêter là.**

1. **Remplir la mémoire du CTO** (`brain/fact/base.md`, `brain/mind/`). Cette
   session est la seule à savoir ce qui vient d'être monté.
2. **Annoncer que l'atelier est en place**, et nommer le chemin exact où ouvrir
   la session suivante : `<racine>/<cto>`.
3. **Dire pourquoi il faut changer de dossier** : le paquet est activé dans
   les réglages prévus pour le CTO ; son rôle est dans `cto/AGENTS.md`.
   **Attention** : Copilot lit `.github/copilot/settings.json` à la racine
   git, pas dans le `cwd` : si `cto` est un sous-dossier d'un dépôt commun,
   ces réglages et les hooks du plugin n'y sont pas activés par ce fichier.
   Régler ce conflit avant de promettre un briefing.
4. **Ne pas monter de projet depuis ici.** C'est le travail du CTO, depuis son
   dossier, avec `/agentic-adopte`.

Le programme imprime déjà ce bloc après `--go`. **Le relayer quand même** : une
sortie de programme se lit en diagonale, une phrase de l'agent se lit.

## La preuve

Ouvrir une session DANS le dossier du CTO : le briefing d'entrée doit
s'afficher. Un hook qu'on n'a pas vu se déclencher n'est pas un hook vérifié.

## Règles

- **Rien n'est jamais écrasé.**
- **Ne pas mettre le rôle dans le socle**, ni la méthode dans le rôle.
- **Ne pas monter de projet avec ce skill** : il monte l'atelier, une seule fois.
- Rapporter ce qui a été fait, ce qui a été ignoré, et ce qui reste. Ne rien
  voir n'est pas un succès, c'est une absence de mesure.
