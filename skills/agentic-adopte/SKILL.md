---
name: agentic-adopte
description: >
  Pose le harnais sur N'IMPORTE QUEL projet, en un seul geste : la mémoire du
  projet (`brain/fact/` et `brain/mind/`) et les deux clés qui branchent le
  paquet. Mono par défaut, `--equipe A,B,C` pour plusieurs agents. Purement
  additif : n'écrase jamais un fichier, fusionne les réglages existants. À blanc
  par défaut, `--go` pour écrire. C'est la porte d'entrée : un projet adopté
  sert son briefing à la session suivante.
  Trigger: /agentic-adopte, « mettre ce projet au harnais », « adopter ce
  projet », « installer le harnais ici », « démarrer un projet agentique ».
---

# agentic-adopte — la porte d'entrée

**Un geste, pas huit.** Un atelier qui ne se monte que par quelqu'un qui l'a
déjà monté n'est pas un outil, c'est un savoir-faire.

## Le geste

```bash
harnais adopte                     # dit ce qu'il poserait, n'écrit rien
harnais adopte --go                # écrit
harnais adopte --equipe PO,QA,OPS --go
harnais adopte --code "<chemin du code>" --go   # code existant ailleurs
```

**Le projet agentique se tient dans l'atelier.** Quand le code existe déjà
ailleurs — un autre dépôt, ou un sous-dossier d'un dépôt plus large —, on
n'adopte pas ce dépôt : on crée le dossier du projet sous la racine de
l'atelier, on y fait `git init`, et on l'adopte avec `--code`. Le chemin du code
entre dans `brain/fact/architecture.md` (section « Le code »), que le briefing
remontre à chaque session ; rien n'est écrit dans le dossier du code. Adopter
le dépôt du code lui-même ne se fait que si @user le demande expressément.

Le programme est celui du paquet — le briefing d'un projet sans mémoire en donne
le chemin exact, parce qu'il change à chaque version et qu'un mode d'emploi faux
est pire qu'absent.

## Ce qu'il pose

| | |
|---|---|
| `brain/fact/base.md` | le cap du projet, et ce qu'il est |
| `brain/fact/architecture.md`, `stack.md`, `rules.md` | gabarits à remplir après lecture, complétés même sur mémoire partielle |
| `brain/mind/state.md` | où on en est aujourd'hui |
| `brain/mind/todo.md` | ce qui attend une décision |
| `.github/copilot/settings.json` | le marché, et le paquet activé |
| `.github/copilot-instructions.md` | méthode ajoutée une seule fois après le contenu existant |

Copilot lit ces réglages à la racine du dépôt git, pas dans un sous-dossier
`agents/<nom>/`. Une déclaration par agent dans un dépôt commun ne suffit donc
pas à activer le paquet et ses hooks ; vérifier le briefing et la garde avant
de conclure que l'installation sert vraiment.

En équipe : un jeu d'état **par agent** sous `brain/mind/<nom>/`, un dossier
d'agent par nom avec son `AGENTS.md` et `.github/copilot/perimetre.json`,
et `brain/fact/roles.md`. L'activation du plugin reste unique à la racine git.

## Ce qu'il ne fait pas, et le dit

Écrire le cap, découper un `AGENTS.md` existant, répartir les périmètres : ce
sont des jugements, ils demandent d'avoir lu le projet. La commande les NOMME en
fin de rapport. **Un script qui décide à la place de l'agent décide sans avoir
lu.**

## Trois garanties, chacune tenue par un essai

- **Purement additif** — les fichiers de mémoire existants restent tels quels ;
  les réglages sont fusionnés clé à clé et un bloc de méthode est ajouté aux
  instructions sans remplacer leur contenu. Réconcilier toute règle métier
  contradictoire ; les copies de méthode déjà présentes ne sont pas actualisées
  automatiquement. Ne jamais modifier
  `.claude/settings.json` ; s'il active `harnais@atelier`, signaler le risque
  de double chargement.
- **Le blanc n'écrit rien** — après un passage sans `--go`, aucun des fichiers
  annoncés n'existe. Son témoin négatif est l'essai qui exige que `--go` écrive
  vraiment : sans lui, une commande qui n'écrit jamais passerait le premier.
- **Relancer ne change rien** — un outil d'installation qu'on n'ose pas relancer
  n'est pas un outil, c'est un pari.

## Ce qu'il refuse

Un projet **à cheval sur deux organisations de mémoire** : poser des fichiers
dessus, c'est choisir en silence lequel des deux arbres fait foi. Il renvoie
vers `harnais brain-migre`, qui termine la migration.
Une mémoire ancienne intacte reste elle aussi préservée : migrer explicitement
avant l'adoption, plutôt que créer deux arbres concurrents.

## Après

Ouvre une session dans le dossier et vérifie que le briefing d'entrée s'affiche.
Une absence de briefing n'est pas un succès. Pour passer
un projet mono à plusieurs agents **plus tard**, c'est `agentic-agents` — il
déplace l'état existant au lieu d'en créer un neuf.
