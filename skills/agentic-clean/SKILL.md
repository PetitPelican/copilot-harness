---
name: agentic-clean
description: >
  Fait le ménage d'un projet ou de tout un atelier : supprime les caches
  régénérables (node_modules, .next, .turbo, .venv, dist…) et SIGNALE, sans y
  toucher, les résidus de migration mémoire et les fichiers de docs/ devenus
  trop gros. Dry-run par défaut.
  Trigger: /agentic-clean, « fais le ménage », « nettoie ce projet », « le
  disque est plein », « qu'est-ce qui prend de la place », « ma mémoire est
  trop grosse », « supprime les caches ».
---

# Agentic Clean

> **Pourquoi ce skill existe.** Reprocher aux agents de ne jamais faire le
> ménage serait mal adressé : **aucun autre outil du paquet ne le fait**.
> `harnais adopte` est purement additif et `agentic-team` est en lecture seule.
> Les caches régénérables n'appartiennent à personne, et s'accumulent.

Ne jamais assimiler `~/.copilot/session-state/` à un cache régénérable ; il contient
l'historique de session. Ce skill ne nettoie ni cet historique ni les données
persistantes du plugin dans `~/.copilot/plugin-data/`.

## Trois familles, et une seule qui supprime

| # | Famille | Ce qu'en fait le script |
|---|---|---|
| 1 | **Caches régénérables** | **supprimés** sous `--apply`, avec la commande qui les refait |
| 2 | **Résidus de migration** | **listés**, jamais supprimés |
| 3 | **Mémoire hypertrophiée** | **listée**, jamais touchée |

La séparation n'est pas cosmétique. Un `node_modules` n'est pas une donnée : il
se reconstruit à l'identique par une commande écrite en face de lui. Un fichier
de `docs/` est une phrase que quelqu'un a écrite, et **seul l'agent du projet
sait si elle est reprise ailleurs**. Trier, c'est choisir ce qu'on oublie — un
programme n'a pas à le faire.

## Usage

```bash
# 1. Ce projet, sans rien supprimer (le défaut)
harnais menage

# 2. Tout un atelier, sans rien supprimer
harnais menage --racine ~/Agentic

# 3. Supprimer — famille 1 uniquement
harnais menage --apply
```

Le programme est celui du paquet, le même sur Mac et sur Windows — le
briefing d'un projet en donne le chemin exact. **Limite connue** : le dossier à
inspecter pour les familles 2 et 3 se déduit de la présence d'un `.fact/` à la
racine ; un projet en `brain/` n'en a plus, et le programme cherche alors dans
`.memory/` au lieu de `docs/` — les familles 2 et 3 n'y trouvent rien, même si
`docs/` est plein. Elle se corrige à part, pas en douce ici.

**Toujours lire le dry-run avant `--apply`.** Il nomme chaque dossier, son
poids, et la commande qui le reconstruit : si l'une des trois manque, ne pas
appliquer.

## Ce que le script refuse de supprimer, et pourquoi

- **Un cache SUIVI par git.** Le discriminant est `git check-ignore`, pas le
  nom. Un `dist/` ignoré est du déchet ; le même `dist/` versionné est du
  contenu que quelqu'un a décidé de garder. Le script le signale comme un
  problème de `.gitignore` — ce qu'il est — au lieu de le supprimer.
- **`dist`, `build`, `coverage` hors dépôt git.** Sans git, rien ne distingue un
  dossier `build/` de sortie d'un dossier `build/` de sources. Signalés.
- **Tout ce qui est dans `docs/` et `brain/mind/`.** Sans exception, y compris
  sous `--apply`.

## Lire la famille 2

Deux messages distincts, parce que les deux cas ne se traitent pas pareil :

- **« MONTE dans .mind/ »** — `state.md`, `rules.md`, `architecture.md` traînent
  dans `docs/`. Ce sont des **faits actuels** : ils ont déjà une place, dans
  `brain/fact/` ou `brain/mind/` — il suffit de les y mettre.
- **« ancienne taxonomie »** — `charter.md`, `business.md`,
  `clients.md`, `overview.md`. Ceux-là n'ont plus de place à eux : leur contenu
  se **répartit** entre `brain/fact/`, `brain/mind/` et `docs/`, phrase par
  phrase. C'est un tri, pas un déplacement.

Ces deux listes sont **reprises telles quelles** de la vue d'équipe. Ne pas en
écrire une autre : des listes de noms de fichiers dupliquées finissent par
diverger, et c'est le projet qui paie l'incohérence.

Tout ce qui n'est dans ni l'une ni l'autre — `finances.md`, `concurrence.md`,
`data-model.md` — est de la **matière de domaine**, à sa place dans `docs/`.
Le script se garde de la signaler.

## Lire la famille 3

Un fichier de `docs/` au-delà de **500 lignes** est signalé avec sa plus
ancienne entrée datée. Ce n'est pas une faute : `docs/` s'accumule **sans
plafond**, c'est sa nature. C'est un signal de **découpage** — garder la période
courante, dater et archiver le reste, sous un nom qui porte la période.

Ne jamais y passer `/caveman` : la compression fusionne les puces, et `!haut`
comme `@<qui>` disparaîtraient sans bruit.

## Deux mesures que le script fait et qu'on referait mal à la main

- **Les liens durs.** pnpm ne copie pas ses paquets, il les relie. Compter
  chaque lien annoncerait plus d'espace récupérable que le projet n'en pèse — un
  chiffre faux sur lequel on prendrait une décision. Chaque `(device, inode)`
  n'est compté qu'une fois, comme le fait `du`.
- **Les caches imbriqués.** Le script ne descend jamais dans un cache déjà
  trouvé : chercher des `node_modules` dans un `node_modules` volumineux coûte du
  temps pour n'apprendre rien.

## Après coup

Le ménage ne touche **jamais** `brain/mind/todo.md`. Les tâches `@<qui>` sont la
seule colonne qui ne se délègue pas : si elles ont bougé après un `--apply`,
c'est un bug, et il faut le dire.
