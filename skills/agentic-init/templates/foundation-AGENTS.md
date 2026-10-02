# Atelier agentique — la méthode

Ce fichier porte la **méthode** de tous les projets, sur toute machine.
`harnais adopte` en ajoute une copie dans `.github/copilot-instructions.md`
du projet, sans remplacer les instructions existantes. Ce branchement local
fonctionne aussi dans les worktrees et ne dépend pas de l'environnement
d'une application déjà ouverte. `COPILOT_CUSTOM_INSTRUCTIONS_DIRS=<racine>`
peut ajouter la méthode commune dans les hôtes qui prennent cette variable
en charge ; sa présence seule ne prouve pas que le fichier a été chargé.
Copilot ne remonte pas au-dessus de la racine Git pour chercher la méthode.
La méthode ne prévaut pas sur le rôle : éviter les contradictions, car Copilot
cumule les instructions sans priorité garantie entre `AGENTS.md` et `CLAUDE.md`.

Trois couches, à ne pas mélanger :

| Couche | Fichier | Contenu |
|---|---|---|
| Poste | `~/.copilot/copilot-instructions.md` | comptes, sessions, réseau, RAM — refait par machine |
| **Méthode** | **`<racine>/AGENTS.md`** | mémoire, hooks, skills, frontières — se transporte tel quel |
| Projet | `<projet>/AGENTS.md` | rôle, stack, règles métier — propre au projet |

Un `CLAUDE.md` de projet existant est aussi lu par Copilot : ne pas créer un
`AGENTS.md` contradictoire en parallèle ; signaler le doublon et réconcilier
le contenu avant de migrer.

---

## La mémoire — trois dossiers, trois natures

C'est le cœur. Ce qui les sépare n'est pas le sujet, c'est la **nature du
texte**.

**`brain/fact/`** — les **faits du projet**, en **quatre fichiers**, plus un
cinquième `roles.md` **en multi-agents seulement**. Un
seul écrivain pour tout le projet : un agent n'y écrit qu'à la demande
du commanditaire, et `mind-guard` refuse un commit qui y touche sans ` # fact-ok`. Le
texte périmé s'y **remplace**, il ne s'ajoute pas.

| Fichier | Répond à |
|---|---|
| `base.md` | pourquoi ce projet existe, et où il va (porte le `cap:`) |
| `stack.md` | avec quoi c'est fait |
| `architecture.md` | comment c'est agencé, et ses frontières |
| `rules.md` | ce qu'on ne franchit pas |
| `roles.md` | **multi-agents seulement** — qui tient quoi, et les zones partagées |

**`brain/mind/`** — l'**état d'un agent**, en deux fichiers, un jeu par agent :
directement dans `brain/mind/` en mono-agent, dans `brain/mind/<nom>/` dès qu'il
y en a plusieurs.

| Fichier | Répond à |
|---|---|
| `state.md` | où **cet agent** en est (en-tête `maj / sante / jalon`) |
| `todo.md` | ce qui reste pour lui, et ce qui attend une décision |

**`docs/`** — les **traces datées**, qui s'accumulent sans plafond :
`README.md` (l'index), `decisions.md` (le pourquoi, daté), `operations.md`
(🔒 hébergement, secrets, dépannage), `data-model.md` (si data-lourd).

**`.logs/`** — un fichier `<AAAA-MM-JJ>.md` par jour, **append-only**, écrit par
la machine à chaque commit. Jamais élagué, jamais compressé.

**Le test qui tranche** : une phrase qui commence par « on a décidé de », ou qui
porte une **date au passé**, va dans `docs/`. Ce qui resterait vrai pour un
autre agent du projet va dans `brain/fact/` ; ce que cet agent seul tient, dans
`brain/mind/`.

**Jamais un troisième fichier dans `brain/mind/`, ni un cinquième dans
`brain/fact/` (un sixième à plusieurs), sans une décision explicite de
l'humain.** Le seul fichier à la racine de `brain/` est `poids.json`, écrit par
le harnais (voir `lecture`). S'il n'y rentre pas, il
est à `docs/`. Et `brain/` reste **à la racine du dépôt**, jamais à un niveau
intermédiaire — l'outillage n'en cherche qu'un.

**L'organisation d'avant se lit encore.** Avant `brain/`, les faits vivaient
dans `.fact/` et l'état dans `.mind/`, à la racine du projet (dans
`agents/<nom>/.mind/` à plusieurs), ou déportés ensemble dans `memoire/`. Le
harnais les sert à l'identique ; `harnais brain-migre` les passe en `brain/`
quand on le décide. **Jamais les deux à la fois** : un projet à cheval ne reçoit
aucune mémoire, parce que servir l'une des deux serait choisir en silence
laquelle fait foi.

### Ce qui ne se compresse jamais

**`brain/mind/todo.md` et les `.logs/` ne passent jamais par un mode de
compression** — `/caveman` compris. Ces fichiers sont relus par un **programme**,
et les règles de compression fusionnent les listes : `!haut` et `@<qui>`
disparaîtraient. On perdrait exactement l'information pour laquelle ces fichiers
existent, et **sans erreur** : le tableau de bord afficherait simplement des
tâches sans priorité et sans destinataire.

La compression utile porte sur le **contexte d'entrée** d'un agent, jamais sur un
fichier que quelque chose d'autre relit.

### Hors du dépôt : sessions, et Copilot Memory coupé

Copilot a sa propre mémoire automatique, **Copilot Memory** : des faits de
dépôt et des préférences qu'il retient de lui-même, stockés chez GitHub, hors
de `brain/`. Rien ne les confronte aux
faits du projet : deux mémoires qui se contrediraient en silence. **Elle est
donc coupée** (`"memory": false` dans `~/.copilot/settings.json`, posé par
l'installateur, ou `/memory off`) ; le briefing signale si elle tourne encore.
Pour un dépôt hébergé sur GitHub, la couper aussi dans ses réglages
(Settings › Copilot › Memory) : l'agent cloud et la revue de code s'en servent.

Les faits durables vont dans `brain/` ou `docs/`, les leçons transversales dans
la méthode après validation humaine. `~/.copilot/session-state/` contient
l'historique des sessions, non une quatrième maison de notes. Le devenir de cet
historique après renommage d'un dossier est **non mesuré** : vérifier les
références au chemin avant de renommer, sans annoncer une perte automatique.

**Règle des quatre semaines** : une affirmation de `brain/fact/` qui n'a pas été
revérifiée depuis un mois est **non confirmée**, et le briefing la signale. On la
mesure avant de s'en servir comme prémisse.

**Une section de fait dit comment elle a été établie**, sur la ligne qui suit
son titre :

```
## Les ports
> **mesuré** · 01/10/2026 — `lsof -i :8080`

## Le déploiement du vendredi
> **observé** · 01/10/2026 · expérience — trois déploiements passés ainsi
```

Le niveau (`mesuré`, `observé`, `supposé`, `dit`) dit d'où part la confiance ;
la nature (`fait`, `croyance`, `expérience`), facultative, posée après la date,
dit à quelle vitesse la section vieillit. Une **supposition est une croyance
d'office** : 2 semaines au lieu de 4, et la déclarer « fait » n'y change rien —
on ne sort de la pente rapide que par une mesure. Une expérience tient 6
semaines. Sans nature déclarée, une section de `brain/fact/` est un fait.

Un instantané ne raconte pas l'histoire, un historique ne dit pas où on en est :
c'est pourquoi il y a `state.md` **et** `.logs/`, et pas l'un des deux.

> Cette mémoire n'est pas écrite pour l'agent. Elle est écrite pour que
> **quelqu'un puisse suivre un projet sans ouvrir le dépôt** — et pour qu'un
> agent qui reprend le projet à froid retrouve l'état sans rien demander.

### Le format est un contrat

`state.md` et `todo.md` sont **relus par un programme**. Leur forme n'est pas
libre.

```
--- brain/mind/state.md : en-tête obligatoire ---
maj:   AAAA-MM-JJ      # la date du jour, en ISO
sante: vert            # vert | orange | rouge
jalon: le prochain caillou, celui qui débloque les autres
```

```
--- brain/fact/base.md : en-tête ---
cap:   ce que le projet doit produire — une phrase : son but, pas son domaine
```

Le `cap:` appartient au **projet**, pas à un agent : il vit dans les faits, et le
tableau de bord le lit là.

```
--- brain/mind/todo.md ---   # les tâches se lisent dans TOUT le fichier
- [ ] !haut @user  ce qui attend une décision
- [>] !moyen         en cours
- [x]                fait
```

États `[ ]` `[>]` `[~]` `[x]` · priorités `!haut` `!moyen` `!bas` ·
destinataires `@<qui>` — n'importe quel nom ; `@dehors` est le seul réservé,
et désigne une attente extérieure que personne dans l'équipe ne peut lever.
`@user` désigne [UTILISATEUR], l'humain qui commande l'atelier ; son nom est
défini à l'initialisation.

**Un `state.md` cassé est pire qu'un périmé.** Périmé, il s'affiche « tiède ».
Cassé, le projet est classé « aucune déclaration » et **disparaît sans un mot**.

---

## Un agent, ou plusieurs

**Architecture compacte (0.17.0, sur choix explicite).** Le profil Copilot et le
rôle sont un seul fichier `.github/agents/<slug>.agent.md` ; le périmètre vit
dans `.github/copilot/perimetres/<slug>.json`. L'état reste
`brain/mind/<nom>/{state,todo}.md`, les productions dans `docs/livrables/<nom>/`.
Le nom de mémoire est conservé, le slug est celui du profil de menu.
Le contexte interne des hooks pointe vers cette mémoire sans déplacer la
session réelle. Le rôle d'un profil choisi est déjà chargé par Copilot et
n'est pas recopié dans le briefing ; un agent par défaut reçoit son rôle.
Un périmètre compact absent ou illisible refuse les écritures de fichiers.
Son `allow` obligatoire est une liste positive : mémoire propre et livrables
propres par défaut. QA reçoit aussi les cinq chemins exacts de faits,
modifiables uniquement sur validation explicite du commanditaire.
`deny` prime. Tout droit de modifier le code
est une extension explicite décidée par l'humain, pas un effet du rangement.
À l'export, le refus historique de `docs/` devient cette liste positive.
Les limites shell/MCP et timeout restent inchangées.

`harnais equipe --compact` prévisualise l'export d'une équipe existante ;
`--apply` écrit seulement les profils fusionnés et périmètres centralisés.
Il ne déplace ni mémoire ni documents et ne supprime aucun ancien dossier.
La migration des livrables et des références communes est une étape distincte
approuvée par l'humain. Les périmètres centralisés font foi ; relire les profils
et valider les sessions avant d'archiver les anciens dossiers.
`harnais adopte --equipe A,B --compact` crée directement cette forme.
`harnais equipe --agents A,B --compact` convertit un mono adopté ; les ajouts
à une équipe compacte conservent cette forme.

**L'organisation décrite ci-dessous est l'architecture historique, encore
prise en charge.** Ses dossiers `agents/<nom>/` ne sont pas requis en compact.

Un projet est tenu par **un** agent par défaut. Quand deux lots ont des rythmes
différents et des contextes disjoints — typiquement infra/fiabilité d'un côté,
produit/apps de l'autre — il peut en porter plusieurs. Ce n'est pas une réponse
à « le projet est gros » : un projet gros mais d'un seul tenant se tient très
bien à un agent.

**On ne découpe pas par couche technique.** Un lot « back » tient aussi la CI,
le workspace et l'outillage — rien de tout ça n'est du back, et c'est pourtant
ce qui casse le travail de l'autre. Le critère est la **dépendance** :
*qu'est-ce que l'autre lot subit sans pouvoir le vérifier lui-même ?* D'où trois
rôles types, et un quatrième hors projet :

| | tient | ne tient pas |
|---|---|---|
| **socle** | base, routes serveur, paquets publiés, CI, workspace | ce que voit l'utilisateur |
| **produit** | applications, logique métier, vitrine, builds | le socle, la mise en production |
| **épreuve** | mémoire et livrables propres ; faits sur accord humain ; plan que les autres exécutent | code, production et réparation technique de son audit |
| *atelier* | *le poste et le harnais, hors projet* | *les projets — lecture seule* |

Le détail — ce que chaque rôle couvre, ce que ce modèle **ne** couvre pas, le
seuil de découpage et son coût — est dans
`skills/agentic-agents/references/roles.md` (dans le paquet). Le lire **avant** de
découper : le nom d'un rôle façonne durablement le comportement de l'agent qui
le porte.

```
MONO                              MULTI
projet/                           projet/
  brain/                            brain/
    fact/   4 fichiers                fact/       4 fichiers + roles.md  ← partagés
    mind/   state · todo              mind/<nom>/ state · todo           ← un jeu par agent
  docs/     les traces                workspace/  le carnet d'équipe
  .logs/    le journal              docs/ · .logs/                       ← partagés
  .github/copilot/settings.json     .github/
  src/ …                              copilot/settings.json              ← le paquet, une fois
                                      agents/<nom>.agent.md              ← le menu d'agent
                                    agents/
                                      ops/ AGENTS.md · .github/copilot/perimetre.json
                                      po/  AGENTS.md · .github/copilot/perimetre.json
                                    src/ …
```

**Quatre éléments par agent** : son profil `.github/agents/<nom>.agent.md` à
la racine git, son `AGENTS.md` de rôle et son `.github/copilot/perimetre.json`
dans `agents/<nom>/`, son état dans `brain/mind/<nom>/`. `brain/fact/`,
`docs/`, `.logs/` et le code n'appartiennent à aucun agent.

`brain/fact/roles.md` rend visibles à tous les périmètres et zones partagées.
Le rôle propre d'un agent reste dans SON `AGENTS.md`.

**Qui parle : l'agent choisi, pas le dossier.** L'app Copilot lance chaque
conversation à la racine d'une copie de travail ; l'agent se choisit dans le
menu d'agent du champ de saisie, qui liste les profils `.github/agents/`.
Aucun hook ne reçoit ce choix : le harnais le lit dans le journal de la
session (`subagent.selected`, `subagent.deselected`) et se place dans
`agents/<nom>/`, comme si la session y avait été lancée. Le briefing dit
l'agent et d'où il vient, et MONTRE son rôle, son état et son périmètre ; la
garde d'écriture, le garde de commit, le journal et la fin de tour suivent le
même agent. La règle, dans cet ordre :

1. l'agent choisi dans le menu (ou `copilot --agent <nom>` dans le CLI) ;
2. sinon le dossier de lancement, quand la session est ouverte dans `agents/<nom>/` ;
3. sinon **QA**, s'il existe : « Default agent » prend QA ;
4. sinon aucun agent — le briefing le dit, et rien n'est gardé.

Un agent choisi qui n'est pas un agent du projet ne prend pas QA. Changer
d'agent dans le menu ou compacter la conversation refait partir le briefing.
**Une conversation, un agent** : le choisir avant le premier message. Le
profil doit être **commité** — une conversation part de l'état commité.

**Attention : réglages non hérités, mais PAS locaux au `cwd`.** Copilot cherche
`.github/copilot/settings.json` à la **racine du dépôt git**. Dans un dépôt
commun, d'anciens fichiers `agents/<nom>/.github/copilot/settings.json`
ne sont pas chargés par Copilot ; leurs
`enabledPlugins` n'activent donc pas chacun le paquet et ses hooks. Le paquet
s'active une fois, à la racine, pour tous les agents : la séparation entre
agents vient du choix d'agent et de la garde du harnais, pas des réglages.
Vérifier dans chaque session la ligne `agent` du briefing, puis un refus de la
garde par un essai négatif ; ne pas qualifier un agent de « gardé » sans cette
preuve.

Copilot ignore les `permissions.deny` ordinaires hors réglages managés : le
périmètre effectif vient de la garde `PreToolUse` du harnais, qui refuse
`Edit|Write` (`edit/create`) hors des chemins autorisés, avec
`permissionDecision: "deny"` et sa raison. Sa source de vérité est le fichier
de périmètre posé par `harnais equipe` dans le dossier d'agent ; le briefing
montre ce qu'applique la garde. Absence de fichier : fail-open. Les chemins du
périmètre sont **relatifs à la racine du projet** et se posent sur la copie de
travail courante ; un chemin absolu vers le dossier principal (périmètres
écrits avant 0.16.0) est transposé sur la copie, et le dossier principal reste
interdit depuis la copie. Un chemin relatif passé à un outil se lit depuis le
dossier de la session. Une commande shell qui écrit des fichiers n'est pas
couverte par le seul matcher `Edit|Write` : cette limite doit être vérifiée
séparément, pas présentée comme un confinement général.

**Aucune phrase du fichier `AGENTS.md` du projet n'est reprise dans celui d'un agent.**
Le test : si elle resterait vraie pour un autre agent, elle est à l'étage
au-dessus. Le fichier du haut est chargé à chaque démarrage de chaque agent —
une phrase répétée est payée deux fois par session.

**Deux agents ne portent jamais des noms qui se slugifient pareil** : leurs
fichiers d'état, leurs dossiers d'agent et leurs profils doivent rester
distincts.

Conversion et ajout d'agent : `/agentic-agents`. Un projet passé en équipe
avant 0.16.0 n'a pas de profils : `harnais equipe --profils --apply`, puis
commiter. Pas de migration de mémoire auto fichier sous Copilot ; pour
l'historique des sessions, effet d'un changement de `cwd` **non mesuré**.

## Les déclencheurs du paquet

Les hooks viennent du paquet `harnais@atelier-copilot`, pas d'une copie
dans le projet. Ils ne s'exécutent que si le plugin est effectivement chargé.
Un hook de commande `preToolUse` refuse une erreur d'exécution ; **un timeout
est fail-open**, même pour une garde. Un fichier de périmètre absent laisse
aussi passer : ces limites imposent un essai négatif avant de promettre une
protection.

- **`briefing`** (`sessionStart` + `userPromptTransformed`) — injecte à l'ouverture
  ce qui ne tient pas dans un pointeur : le `cap:`, la fraîcheur, le nombre de
  décisions en attente, les **titres de section** des faits, et les périmètres
  réellement appliqués. En équipe, il nomme l'agent actif et d'où il le tient
  (menu, dossier, défaut) et, quand Copilot ne l'a pas chargé, montre son rôle. Une empreinte des contenus évite de répéter le même
  briefing dans une session identifiée ; un changement le rafraîchit au prompt
  suivant. Sans identifiant de session, la déduplication n'est pas garantie.
  Chaque worktree Copilot lit son propre `brain/`, jamais celui du checkout
  principal ; le carnet est donc lui aussi local à cette copie. Quand la
  session tourne dans une telle copie (l'app Copilot en ouvre une par session),
  le briefing le dit et nomme le dépôt principal : ses dossiers voisins ne sont
  pas l'atelier, et rien de ce qui y est écrit n'arrive dans le projet avant
  d'être commité puis fusionné. Il donne aussi le chemin complet de `harnais`
  quand le terminal de la session ne trouve pas la commande.
  Il laisse hors du projet une **trace d'entrée** datée, avec la
  version qui l'a écrite : c'est la preuve que l'agent est servi.

  **Pourquoi un pointeur ne suffit pas.** Un rappel du type « les identifiants
  sont dans les faits — les lire avant de conclure qu'un outil manque » ne se
  déclenche que si on doute déjà ; la panne est de croire qu'on sait. Le
  briefing ne demande rien, il montre.

  `userPromptTransformed` peut modifier le contenu transmis au modèle avec
  `modifiedTransformedPrompt` ; un hook commande `userPromptSubmitted` ne
  peut pas injecter un contexte via sa sortie. La preuve de réinjection au
  fil des prompts reste **non mesurée** tant que cette sortie n'a pas été
  vérifiée sur Copilot.

Deux autres regardent les commandes shell.

- **`mind-guard`** (`preToolUse` / `PreToolUse`) — refuse un commit de **code projet** qui
  laisserait `state.md` en arrière, ou qui le rendrait **illisible**, et un
  commit qui touche les faits sans ` # fact-ok`. Il lit le contenu **indexé**,
  pas celui du disque. Échappatoire : ` # mind-ok` en fin de commande. C'est
  l'exception au fail-open : si le programme du paquet ne répond pas, il
  **refuse** la commande plutôt que de la laisser passer sans contrôle.
- **`journal`** (`postToolUse` / `PostToolUse`) — écrit dans `.logs/<jour>.md`. Il regarde
  `HEAD`, pas le retour de la commande : un commit échoué n'écrit rien, un
  double appel ne crée pas deux entrées.

- **`lecture`** (`postToolUse` / `PostToolUse`, sur `Read` et `Bash`) — note
  quelles **sections** de `brain/fact/` l'agent lit (une lecture partielle ne
  crédite que les sections qu'elle couvre). Leur confiance vit dans
  **`brain/poids.json`**, commité : elle part du niveau d'établissement (mesuré
  80, dit 85, observé 60, supposé 40), et les résultats la font bouger — une
  garde qui mord, un constat qui tient, un constat démenti — pour les seules
  sections lues depuis le verdict précédent. Le briefing signale les sections
  peu sûres ou endormies ; `harnais curateur` en donne le détail. Rien n'est
  jamais déplacé ni effacé, et `poids.json` ne s'édite pas à la main.

Le dernier ne dépend d'aucune commande, et c'est ce qui fait sa valeur.

- **`attente`** (`agentStop` / `Stop`) — se déclenche **à chaque fin de tour**, quand l'agent
  rend la main. Il la refuse (sortie JSON `{"decision":"block","reason":"…"}`) si du code a bougé sans que
  `brain/mind/todo.md` suive, parmi quatorze gardes, puis reporte ce qui attend
  l'humain là où il le lira vraiment.

  **Pourquoi `todo.md` a quitté le hook du commit.** Il y était, et ça ne
  pouvait pas marcher : `mind-guard` ne s'arme que sur `git commit`, donc un
  agent qui analyse, qui est bloqué maintenant, ou qui n'a pas encore commité
  n'écrivait **rien**, et les demandes s'empilaient sans qu'aucune remonte. Un
  instantané (`state.md`) se pose à un
  jalon — `commit` va bien. Une alerte (`todo.md`) ne peut pas attendre le
  jalon suivant. **Avant de câbler un hook, demander QUAND il doit voir, pas
  seulement quoi.**

  **Toujours borner un `Stop` qui bloque.** Il se redéclenche après le tour
  qu'il provoque : sans garde propre, il peut bloquer plusieurs tours.
  On mémorise la signature de l'état : à l'identique, laisser passer.
  Copilot termine le tour après **8 blocages consécutifs**, même si le hook
  insiste. Le blocage n'est pas une garantie illimitée.

**Déclarer et résoudre le paquet.** `enabledPlugins` doit contenir
`harnais@atelier-copilot: true` et `extraKnownMarketplaces` doit désigner la
marketplace locale `atelier-copilot`, ou le paquet doit être installé dans
`~/.copilot/installed-plugins/`. `copilot plugin marketplace add <chemin>` puis
`copilot plugin install harnais@atelier-copilot` sont les commandes CLI ;
aucun `--scope project`. Une marketplace locale charge le dossier en direct :
`/restart` ou une nouvelle session applique une correction. Les réglages
sont `.github/copilot/settings.json` à la racine git, et Copilot lit aussi
`.claude/settings.json` : ne jamais écrire dans ce dernier et signaler un
ancien paquet `harnais@atelier` déjà déclaré, risque de double chargement.

---

## Les skills, et lequel quand

| Situation du dépôt | Le skill | Ce qu'il fait au contenu |
|---|---|---|
| on ne sait pas dans quel état il est | `/agentic-team` | **rien — il lit et il dit quoi faire** |
| vide ou tout neuf | `/project-init` | crée et remplit |
| du code, aucun harnais | `/agentic-adopte` | ajoute seulement, n'écrase rien |
| mémoire dans l'organisation d'avant | `harnais brain-migre` | la déplace dans `brain/` |
| harnais présent, en retard | `/restart` (marketplace locale) | recharge le paquet sans écraser le projet |
| un agent ne suffit plus | `/agentic-agents` | déplace l'état dans `brain/mind/<nom>/`, ne touche ni les faits ni le code |
| le disque est plein | `/agentic-clean` | supprime les caches, signale le reste |

**`/agentic-team` passe en premier parce qu'il est le seul à ne rien écrire.** Il lit
la mémoire et les réglages de tout l'atelier et rend deux choses : un
**diagnostic** projet par projet — pour chaque agent, le paquet est-il déclaré,
résolu, **servi**, et en quelle version — qui nomme ce qu'il faut faire, et une
**page HTML autonome — l'`agentic-team`**, qui s'ouvre d'un double-clic sur
n'importe quelle machine, sans serveur ni réseau. Elle ouvre sur **ce qui attend
une décision**, avant l'état des projets.

```bash
harnais equipe-vue --racine <racine>                      # diagnostic
harnais equipe-vue --racine <racine> --projet X           # un seul
harnais equipe-vue --racine <racine> --html agentic-team.html
```

La page est un **relevé daté**, pas un tableau vivant : elle porte l'heure de sa
génération et ne bouge plus. `--watch 60` la réécrit en boucle et y pose un
meta-refresh — le seul rafraîchissement qui fonctionne depuis un `file://`.

`/publish-docs` génère un site Quarto (HTML + Word/PDF) depuis la mémoire
**publique** — il ne lit jamais `operations.md` ni les `.env*`. `/caveman` est un
mode compressé, à la demande — **jamais sur `brain/mind/todo.md` ni sur les `.logs/`**
(voir « Ce qui ne se compresse jamais »), et jamais imposé à un sous-agent qui
**rapporte des constats** : un rapport relu par un autre agent doit être sans
ambiguïté avant d'être court.

Les commandes qui posent ou déplacent (`harnais adopte`, `harnais equipe`)
tournent **à blanc par défaut** et n'écrivent qu'avec `--go` ou `--apply`.
Aucune ne **trie** une mémoire ancienne : trier demande de lire le contenu, et le
contenu appartient au projet. Elles remontent le choix à faire, pas la décision
prise.

---

## Déléguer

**Tout agent délégué prend le modèle intermédiaire par défaut.**

| Comment | La forme |
|---|---|
| Outil `task` | préciser le modèle intermédiaire disponible si l'outil permet de le choisir |
| Processus séparé | `copilot -p "<invite>" --model <id-intermédiaire>` |
| Agent personnalisé | `.github/agents/<nom>.agent.md` avec `model: <id-intermédiaire>` et `include-custom-instructions: true` pour que le sous-agent reçoive aussi les instructions du dépôt |

Un modèle plus gros demande une **consigne explicite de l'humain**, au cas par
cas. Ce n'est pas au parent d'en décider pour son enfant.

**Pourquoi.** Un sous-agent démarre à froid : il redérive un contexte que le
parent possède déjà, et il le paie en entier. Le coût d'un sous-agent est donc
dans le **lancement**, pas dans le prix du jeton — et une grappe de sous-agents
sur le plus gros modèle vide un quota en un après-midi. Pour du travail
**cadré** — une recherche, un balayage, un portage mécanique — le modèle
intermédiaire suffit ; c'est le cadrage qui fait la qualité du retour, pas la
taille du modèle.

Corollaire : **ne pas lancer de sous-agent quand la tâche ne l'exige pas.** Une
tâche « en plusieurs points » ou « à traiter à fond » n'est pas une demande de
délégation. On délègue ce qui a besoin de **fan-out** — beaucoup de fichiers à
balayer, dont on ne veut que la conclusion — ou ce que l'humain demande
nommément.

Les identifiants de modèles vieillissent ; la règle, elle, ne change pas :
**par défaut le modèle intermédiaire, l'escalade sur consigne.**

---

## Les frontières

1. **Un projet appartient à son agent.** Ne pas écrire dans le `brain/` ni le
   `docs/` d'un autre projet. La raison n'est pas hiérarchique, elle est
   mécanique : deux agents qui écrivent dans le même état produisent des
   conflits silencieux.
2. **Ne jamais décider à la place de l'humain.** Un agent ne peut pas en
   débloquer un autre : c'est le seul point de contrôle humain de la chaîne, et
   un agent qui approuverait au nom d'un autre le supprimerait.
3. **`operations.md` est privé** — jamais ouvert, jamais cité, jamais résumé,
   jamais publié. Cela vaut pour son propre projet autant que pour les autres.
4. **Aucun secret en clair dans un fichier commité.** Rapporter l'existence, la
   taille ou la date d'un secret — jamais sa valeur.

---

## Les réflexes

- **Un fait documenté se vérifie par commande avant de servir de prémisse.** Un
  document a toujours un temps de retard sur le disque.
- **Ne rien voir n'est pas un succès, c'est une absence de mesure** — et ça se
  dit. Tout compte rendu distingue trois états : **vérifié bon**, **vérifié
  mauvais**, **pas mesuré**.
- **Ne jamais recopier l'avancement d'un projet ailleurs** : il vit dans son
  `brain/mind/state.md`, et une copie se périmerait en silence. Retenir **où
  regarder**, pas **quoi**.
- **Tenir `brain/mind/` à jour fait partie du travail**, pas de la paperasse d'après.
  Avant de rendre la main, `state.md` et `todo.md` disent l'état réel.
- **Portabilité** : le paquet est un programme natif, livré pour macOS Apple
  Silicon et Windows x86_64. Aucun script propre à un seul système — un outil
  qu'une des machines ne peut pas lancer ne signale jamais qu'il est mort.
