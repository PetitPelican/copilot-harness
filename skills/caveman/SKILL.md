---
name: caveman
description: >
  Mode de réponse compressée, activé par /caveman ou sur demande explicite
  de concision. Six intensités : lite, full, ultra, wenyan-lite,
  wenyan-full, wenyan-ultra. Préserve toute information technique.
---

# Caveman — répondre court, pas rendre les fichiers illisibles

Compresser **la réponse**, jamais le code, les citations de messages d'erreur,
les commandes ni les fichiers qu'un programme relit. Ce mode ne réduit pas
les vérifications ni la précision des constats. Ne pas l'imposer aux
sous-agents qui rendent un rapport de faits.

## Ne jamais compresser

`brain/mind/todo.md` (ou `.mind/todo.md` dans l'ancien rangement),
`brain/mind/state.md` et `.logs/*.md` ont un format lu par le harnais.
Fusionner les listes ferait disparaître `!haut` et `@<qui>` ; altérer
l'en-tête `---` rendrait `state.md` illisible. Refuser une demande de
compression de ces fichiers et en expliquer la raison.

## Portée et intensité

Le mode reste actif dans cette session jusqu'à « stop caveman » ou « mode
normal ». Niveau par défaut : `full`. `/caveman lite|full|ultra` change
l'intensité. `wenyan-lite`, `wenyan-full`, `wenyan-ultra` ne s'appliquent
que sur demande explicite du registre classique chinois.

| Niveau | Forme |
|---|---|
| `lite` | phrases complètes, sans remplissage |
| `full` | fragments nets si le sens reste clair |
| `ultra` | abréviations de prose et flèches, jamais des identifiants techniques |
| `wenyan-*` | registre classique chinois, intensité correspondante |

Supprimer les formules de politesse et les répétitions ; garder les réserves
nécessaires (« non mesuré », échec, limite) et la causalité. Pattern :
`constat → raison → suite` quand les trois sont utiles.

**Clarté prioritaire** pour une alerte de sécurité, une action irréversible,
un enchaînement d'étapes où l'ordre compte, une ambiguïté technique ou une
demande de clarification. Revenir à la prose complète pour le passage
concerné ; reprendre le mode ensuite. Écrire code, commits et descriptions
de PR normalement.
