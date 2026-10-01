# Harnais Copilot : atelier et projets agentiques

## Démarrage en 3 étapes

1. Créer un dossier `Agentic`, puis son sous-dossier `CTO`, hors d'un dépôt
   Git existant. Ouvrir Copilot dans **`Agentic\CTO`**, même si ce dossier est vide.
2. Coller le prompt ci-dessous. Lire la prévisualisation ; l'agent attend
   votre accord explicite avant d'appliquer l'installation.
3. **Redémarrer la session Copilot** dans `Agentic\CTO`. Si l'app ou le terminal
   était déjà ouvert, le fermer puis le rouvrir pour hériter de l'environnement.
   Le CTO termine sa mémoire, puis vous accompagne pour votre premier projet.

### Prompt d'installation à copier

```text
Installe mon atelier agentique avec le harnais Copilot depuis
https://github.com/PetitPelican/copilot-harness.

Je suis dans le dossier Agentic\CTO. Commence par vérifier le dossier courant :
le dossier d'atelier est son parent. Si ce n'est pas le cas, demande-moi le chemin.
Demande-moi mon nom d'utilisateur si tu ne le connais pas, une question à la fois.

Clone le dépôt dans un dossier source séparé de l'atelier. Choisis aussi un
dossier de destination du plugin séparé de la source et de l'atelier.
Montre-moi les trois chemins. Ne réutilise pas un dossier non vide sans vérifier
son origine et obtenir mon accord ; ne supprime ni n'écrase mes fichiers.

Lis le README et install.ps1 du clone. Vérifie Git, PowerShell et Copilot CLI ;
si nécessaire fournis -CopilotPath vers un exécutable vérifié. Ne compile pas
et n'installe pas de dépendances si le binaire Windows livré fonctionne.
Ne désactive ni ne contourne la politique d'exécution PowerShell de mon poste :
si elle bloque le script, explique le blocage et arrête-toi.

Lance install.ps1 avec -Destination le dossier du plugin, -WorkshopRoot le
chemin absolu d'Agentic, -CtoName CTO et -UserName mon nom, SANS -Go.
Affiche la prévisualisation complète et demande explicitement mon accord.
Seulement APRÈS ma réponse affirmative, relance la même commande avec -Go.
Une permission technique d'exécuter une commande n'est pas mon accord
pour appliquer l'installation. En cas de refus, n'applique rien.

Après succès, indique le chemin d'Agentic\CTO et demande-moi de REDÉMARRER
la session dans ce dossier (et l'app/terminal pour les variables utilisateur).
Les instructions, le plugin et l'environnement sont chargés au démarrage :
ne prétends pas qu'ils sont actifs dans cette session d'installation.
Arrête-toi alors ; ne crée pas encore les agents des projets.
```

Après redémarrage, le CTO demande si le projet est **nouveau ou existant**,
puis son emplacement. Il présente OPS (socle), PO (produit) et QA (épreuve),
propose de personnaliser chaque profil et attend un accord avant de créer.
Un profil reste mono-agent ; plusieurs profils forment une équipe, pas
simplement parce que le projet est gros.

Plugin pour **GitHub Copilot CLI** : méthode `AGENTS.md`, mémoire versionnée,
briefing, gardes, journal et huit skills. Le dépôt de distribution est
[PetitPelican/copilot-harness](https://github.com/PetitPelican/copilot-harness).

## Prérequis

- Windows 10/11 x86_64, Git et PowerShell 5.1 ou supérieur.
- Copilot CLI installé et accès Copilot actif pour les sessions.
  L'installateur cherche `copilot` dans le PATH puis le CLI du SDK de l'app ;
  `-CopilotPath` permet de fournir son exécutable explicitement.
- Aucun Rust, Python ou compilateur requis pour utiliser le paquet Windows.
  Ils sont nécessaires uniquement pour reconstruire le programme.
- Le binaire précompilé du dépôt est Windows x86_64. Pour macOS Apple Silicon,
  construire une archive native avec la procédure de livraison ; un ancien
  binaire Mac n'est pas conservé comme s'il correspondait à cette version.

L'app Copilot, le CLI et les extensions Copilot des IDE ne sont pas
interchangeables : ce guide vise le CLI et les sessions de l'app qui
l'utilisent. Une installation du plugin ne prouve pas son chargement
dans tous les hôtes.

## Alternative : installer manuellement sous Windows

Cloner le dépôt publié, ou extraire une archive Windows construite par
la procédure de [livraison](scripts/RELEASE.md). Depuis ce dossier :

```powershell
git clone https://github.com/PetitPelican/copilot-harness.git
Set-Location .\copilot-harness

# Prévisualiser : aucun fichier ni réglage n'est modifié.
.\install.ps1 -Destination C:\Tools\harnais-copilot `
  -WorkshopRoot C:\Atelier -UserName Alice

# Appliquer après lecture de la prévisualisation.
.\install.ps1 -Destination C:\Tools\harnais-copilot `
  -WorkshopRoot C:\Atelier -UserName Alice -Go
```

Pour une archive extraite, commencer directement par les commandes
`install.ps1`, sans cloner. Adapter les chemins et le nom à son poste.
Source, destination du plugin et atelier doivent être des dossiers distincts.
Si la politique PowerShell bloque le script, suivre la politique de son
organisation ; ne pas désactiver globalement les protections du poste.

L'installateur copie les fichiers du plugin, enregistre la marketplace
locale `atelier-copilot`, installe `harnais@atelier-copilot`, initialise
`C:\Atelier\cto` et ajoute l'atelier à
`COPILOT_CUSTOM_INSTRUCTIONS_DIRS` sans remplacer les valeurs existantes.
Il préserve la méthode, les instructions et la mémoire déjà présentes.
Les faits nouvellement créés portent des sections **À REMPLIR** :
l'agent doit les renseigner après lecture du projet.

Il **coupe aussi Copilot Memory** (`"memory": false` dans
`~\.copilot\settings.json`, ce qu'écrit `/memory off`) : Copilot retiendrait
sinon ses propres « faits du dépôt » hors de `brain/`, sans que rien ne les
confronte à ceux du projet. La prévisualisation affiche la valeur actuelle ;
la désinstallation la rend si personne n'y a touché entre-temps.
`-KeepCopilotMemory` laisse le réglage tel quel. Le réglage vaut pour toutes
les sessions Copilot CLI de l'utilisateur, pas seulement l'atelier. Pour un
dépôt hébergé sur GitHub, la couper aussi dans ses réglages
(Settings › Copilot › Memory) : l'agent cloud et la revue de code s'en servent.

Fermer puis rouvrir le terminal et l'app Copilot pour hériter de
l'environnement utilisateur. Ouvrir une nouvelle session sur
`C:\Atelier\cto`, renseigner sa mémoire et commiter le dépôt pour
que les nouvelles sessions en worktree héritent de ses fichiers.
L'installateur ajoute `…\bin` du plugin au PATH de l'utilisateur, pour que la
commande `harnais` citée par les skills et les messages existe dans les
sessions des agents (`-EnvironmentScope None` l'en empêche ; la désinstallation
retire cette seule entrée). Les commandes ci-dessous donnent quand même le
chemin complet du lanceur, valable avant le redémarrage du terminal.

**Dans l'app Copilot, chaque session tourne dans une copie de travail**
(un worktree rangé sous `~\.copilot\repos\copilot-worktrees\`), pas dans le
dossier du projet. Le briefing le signale. Ce que l'agent y écrit n'arrive dans
le projet qu'une fois commité puis fusionné, et les dossiers voisins de cette
copie ne sont pas l'atelier : c'est pourquoi le rôle du CTO porte le chemin
absolu de l'atelier.

## Adopter un projet existant

Le projet agentique se tient dans l'atelier : un dossier sous sa racine, avec
son propre dépôt Git, qui porte les rôles, `brain/` et `docs/`. Depuis ce
dossier :

```powershell
C:\Tools\harnais-copilot\bin\harnais.cmd adopte
C:\Tools\harnais-copilot\bin\harnais.cmd adopte --go
```

Quand le code existe déjà ailleurs, il reste à sa place et ne reçoit aucun
fichier ; `--code` en garde l'adresse dans `brain/fact/architecture.md`, et le
briefing la remontre à chaque session :

```powershell
git init
C:\Tools\harnais-copilot\bin\harnais.cmd adopte --code "D:\depots\mon-code" --go
```

En CLI, `copilot --add-dir "D:\depots\mon-code"` donne à une session ouverte
dans le projet l'accès au code. Adopter directement le dépôt du code reste
possible, si c'est ce qu'on veut : lancer `adopte` depuis sa racine Git.

Les quatre fichiers de faits, l'état et les tâches sont complétés sans
écraser l'existant. Les réglages du plugin sont fusionnés dans
`.github\copilot\settings.json` à la racine Git. La méthode est ajoutée
une seule fois dans `.github\copilot-instructions.md`, après le contenu
existant et sans le remplacer. `adopte` ne décide pas
du rôle ni des règles métier : créer ou réconcilier le `AGENTS.md`
du projet et renseigner les sections **À REMPLIR**.
Un `CLAUDE.md` existant est aussi lu par Copilot : ne pas ajouter
un `AGENTS.md` contradictoire. Une mémoire ancienne `.fact`/`.mind`
doit être migrée avec `brain-migre` avant de compléter `brain`.

## Vérifier, avant de considérer l'installation terminée

Dans le CLI interactif, `/instructions` doit montrer les instructions
du projet, dont `.github\copilot-instructions.md` contenant la méthode.
La méthode au-dessus de la racine Git n'est pas découverte automatiquement.
La variable d'environnement est conservée pour les hôtes qui la prennent
en charge, mais le CLI SDK 1.0.90-0 testé ne chargeait pas ce dossier
supplémentaire : la copie locale évite d'en dépendre.
Le bloc `harnais:method:start` est préservé au prochain passage ;
une évolution de la méthode dans les projets déjà adoptés doit être
réconciliée explicitement avec leurs instructions.

Le briefing doit être reçu et les huit skills disponibles :
`agentic-adopte`, `agentic-agents`, `agentic-clean`, `agentic-init`,
`agentic-team`, `project-init`, `publish-docs`, `caveman`.

```powershell
C:\Tools\harnais-copilot\bin\harnais.cmd version
C:\Tools\harnais-copilot\bin\harnais.cmd equipe-vue --racine C:\Atelier
```

La mémoire Copilot est lue dans le **checkout courant**, y compris
en worktree ; elle ne se replie pas sur celle du checkout principal.
Les fichiers doivent donc être commités avant de créer une autre session.
Dans un dépôt multi-agents, les réglages du plugin restent à la racine Git,
pas dans chaque dossier d'agent.

## Mise à jour et désinstallation

Depuis une nouvelle archive extraite ou le clone mis à jour :

```powershell
.\install.ps1 -Action Update -Destination C:\Tools\harnais-copilot
.\install.ps1 -Action Update -Destination C:\Tools\harnais-copilot -Go

.\install.ps1 -Action Uninstall -Destination C:\Tools\harnais-copilot
.\install.ps1 -Action Uninstall -Destination C:\Tools\harnais-copilot -Go
```

Le journal d'installation permet de remplacer seulement les fichiers
possédés et inchangés. Une modification locale bloque la mise à jour
au lieu d'être écrasée. La désinstallation conserve l'atelier, les
projets, Git, les mémoires et les fichiers modifiés ou étrangers.
Elle ne retire que les réglages et les valeurs d'environnement ajoutés
par cette installation. Redémarrer les sessions après une mise à jour.

Une mise à jour depuis une version antérieure à 0.14.3 coupe Copilot Memory
comme une installation neuve ; elle laisse en place une mémoire que
l'utilisateur a rallumée après coup. Le texte de méthode déjà copié dans les
projets adoptés n'est pas réécrit : le réconcilier à la main pour y reprendre
la section « Hors du dépôt ».

## Installation du plugin seul

Pour un utilisateur du CLI qui ne souhaite pas l'installateur Windows :

```powershell
copilot plugin marketplace add PetitPelican/copilot-harness
copilot plugin install harnais@atelier-copilot
```

Ce parcours n'initialise pas l'atelier, ne configure pas la variable
d'instructions commune et ne coupe pas Copilot Memory : lancer `/memory off`
dans une session (le briefing le rappelle tant qu'elle tourne).
Pour le développement local :

```powershell
copilot plugin marketplace add C:\Sources\copilot-harness
copilot plugin install harnais@atelier-copilot
copilot --plugin-dir C:\Sources\copilot-harness
```

`--plugin-dir` est une alternative pour une session, pas une étape
nécessaire après une installation persistante. Les éditions d'une
marketplace locale sont chargées à la prochaine session.
Ne pas mélanger plusieurs installations de la même marketplace :
l'installateur refuse de remplacer une inscription qu'il ne possède pas.

## Limites et contrôles

- La garde Edit/Write, y compris les patches FREEFORM, **ne couvre pas
  les écritures par shell**. Ce n'est pas une sandbox.
- Un hook simulé ne prouve pas son déclenchement dans une vraie session.
  Le CLI 1.0.90-0 a été utilisé pour mesurer les identifiants des événements
  de briefing ; les autres hôtes doivent être vérifiés séparément.
- Le relecteur utilise le modèle par défaut du CLI, ou
  `HARNAIS_MODELE_JUGE` si fourni ; un échec est explicitement insuffisant.
- Windows est la plateforme de validation. La chaîne prévoit
  macOS Apple Silicon ; sa réussite doit être vérifiée sur un Mac.
- Selon sa politique d'exécution, Windows PowerShell 5.1 peut refuser les
  fichiers scripts. Ce blocage n'est pas contourné : le parcours est mesuré
  avec PowerShell 7.
- La chaîne conserve des archives comme artifacts ; elle ne publie pas
  automatiquement une release GitHub.

Architecture, mémoire et hooks : [COMMENT-CA-MARCHE.md](COMMENT-CA-MARCHE.md).
Construction et empreintes du paquet : [scripts/RELEASE.md](scripts/RELEASE.md).
