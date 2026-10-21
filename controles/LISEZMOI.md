# Les contrôles

Tous tournent sous Windows, dans des dossiers jetables créés à l'intérieur du
dépôt et retirés à la fin. Aucun n'écrit dans l'environnement User, ni dans la
configuration Copilot réelle du poste.

## Sans Copilot

```powershell
python -m unittest discover -s tests
python .\scripts\package_release.py
.\controles\hooks-powershell.ps1
.\controles\install-windows.ps1
.\controles\portable-smoke.ps1
```

- **Les tests** (`tests/`) et ceux du conditionnement passent par
  `package_release.py`, qui les lance sur l'instantané livré avec un `HOME`, un
  `USERPROFILE` et un `COPILOT_HOME` jetables, et sans aucune variable de plugin
  héritée : un test lancé tel quel lit le profil du poste et peut échouer pour
  une raison qui n'est pas dans le code.
- **`hooks-powershell.ps1`** lance le champ `powershell` de chaque hook de
  `hooks/copilot.json`, mot pour mot, dans `powershell.exe` 5.1 puis `pwsh`, sous
  un chemin à espaces et parenthèses : garde de commit (avec son témoin), journal,
  périmètre, garde de la Production, coffre (refus et témoin), sous-agents, consignes, fin de tour, et l'absence de Python (les
  gardes refusent, les autres le disent).
- **`install-windows.ps1`** joue l'installateur de bout en bout avec le vrai CLI
  (configuration isolée) : prévisualisation sans écriture, installation,
  répétition, mise à jour, désinstallation, conflits refusés, installation
  depuis un dossier `CTO` existant, vide et courant, et Copilot Memory coupé
  puis rendu.
- **`portable-smoke.ps1`** joue les charges de hooks contre le lanceur `bin/harnais.cmd` : atelier,
  accueil du CTO puis sa fermeture après déclaration, adoption partielle,
  idempotence, briefing, worktree, tableau de bord, gardes et journal, puis le
  choix d'agent de l'app : profils posés par `equipe`, agent lu dans un
  journal de session, garde de la copie, « Default agent » qui prend QA.
  `-Executable` désigne un autre lanceur que celui de `bin/`.
- **`atelier-deplace.ps1`** joue la mise à jour d'une installation dont
  l'atelier a changé de dossier, en prévisualisation et avec un faux CLI : sans
  `-WorkshopRoot`, refus et rien de recréé à l'ancien chemin ; avec, le
  nouveau dossier est suivi ; un dossier sans le CTO reste refusé.

## Avec un CLI Copilot authentifié

```powershell
.\controles\hook-contract.ps1 -Copilot <executable-Copilot>
.\controles\cto-start.ps1 -Copilot <executable-Copilot>
```

- **`hook-contract.ps1`** charge un plugin de contrôle dans une vraie session :
  `SessionStart` et `userPromptTransformed` doivent partir dans la même
  session. Il relève les noms et types des champs reçus, avec un identifiant
  de session pseudonymisé.
- **`cto-start.ps1`** installe un atelier isolé, lance deux sessions avec des
  prompts synthétiques et observe le briefing par ses deux hooks : instructions
  découvertes, huit skills, accueil unique puis absent après déclaration. Ni la
  fin de tour ni le dialogue humain complet ne sont mesurés par ce banc.

Ces deux bancs demandent un accès Copilot actif dans le terminal qui les lance :
un CLI lancé hors de l'app et jamais connecté (`/login`) s'arrête à
l'authentification, et le banc ne mesure alors rien. Un banc qui ne mesure rien
le dit — il ne passe pas. Ils tournent dans un profil isolé, créé pour
l'occasion : la connexion du profil habituel ne le suit pas, et ils ne peuvent
donc pas tourner hors ligne ni dans un profil isolé jamais connecté.

## Ce qui n'est pas mesuré ici

- Windows PowerShell 5.1 : sa politique d'exécution peut bloquer les scripts,
  et elle n'est pas contournée.
- macOS : la chaîne GitHub rejoue les tests sur un runner `macos-14`
  (Python 3.9 et 3.12) ; aucune session Copilot réelle sur Mac n'est faite ici.

La suite différentielle historique (témoins figés et scripts Python/shell
macOS) a été retirée en 0.14.4 : elle ne tournait plus que contre l'ancien
hôte.
