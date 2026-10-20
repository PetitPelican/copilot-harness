# La machine sur laquelle tu tournes

<!-- Étage 1 sur 4 : ce qui ne vaut que pour CETTE machine. Posé « À REMPLIR » par
     `harnais atelier-monte` s'il manquait ; le CTO le remplit et le tient. -->

- **Système** : À REMPLIR (macOS / Windows, version).
- **Mémoire vive** : À REMPLIR. Avant un build, un serveur ou une base, compter
  les sessions ouvertes ; un seul serveur à la fois, éteint après usage.
- **Compte GitHub Copilot** : un seul, celui de `~/.copilot`. Ne jamais poser
  `COPILOT_HOME` sur un autre dossier sans le dire.
- **Comment [UTILISATEUR] y entre** : À REMPLIR (devant l'écran, ou à distance).
  `localhost` ne sort pas de la machine.
- Pas de tâche longue lancée en arrière-plan à la main : une commande qui dure se
  lance dans un terminal suivi, jamais dans un `&` oublié.
- Un tube efface le code de sortie (`cmd | tail` rend celui de `tail`) :
  rediriger vers un fichier, ou `set -o pipefail`.
