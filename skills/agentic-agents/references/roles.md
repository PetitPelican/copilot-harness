# Les rôles d'un projet à plusieurs agents

La section « Un agent, ou plusieurs » du socle dit **comment** découper — les
fichiers, l'héritage, la garde `PreToolUse`, les hooks. Ce document dit **qui**, et
pourquoi ceux-là.

Il décrit un modèle à **trois rôles de projet**, plus un quatrième qui vit à
l'étage au-dessus.

---

**Sous Copilot :** les réglages `.github/copilot/settings.json` sont lus à la
racine git, pas dans chaque dossier d'agent. Une garde dépend de l'activation
effective du plugin ; ne pas attribuer aux réglages d'agent une isolation
non vérifiée.

## Le principe : on ne découpe pas par technologie

Le réflexe est de couper en **back** et **front**. C'est presque toujours faux,
et la raison se voit dès qu'on regarde ce que chaque agent tient réellement :

- l'agent « back » tient aussi la CI, le fichier de workspace, l'outillage de
  dépôt — **rien de tout ça n'est du back**, et pourtant c'est ce qui casse le
  travail de l'autre quand ça bouge ;
- l'agent « front » tient aussi les builds natifs, les paquets de calcul
  métier, la vitrine — **rien de tout ça n'est du front**.

Le bon critère n'est pas la couche technique, c'est la **dépendance** :

> **Qu'est-ce que l'autre lot subit sans pouvoir le vérifier lui-même ?**

Ce qui répond à cette question forme un lot. Le reste en forme un autre.

Un effet de bord vaut d'être connu : **le nom d'un rôle façonne le comportement
de l'agent qui le porte.** Un agent nommé d'après une couche technique se
comporte en exécutant et remonte moins d'arbitrages. Un agent nommé d'après une
responsabilité pose des questions de responsable. Le nom n'est pas une
étiquette, c'est une consigne permanente.

---

## Les quatre rôles

### 1. Le socle — ce dont tout le reste dépend

**Tient** : la base de données et ses migrations, les routes serveur et les
webhooks, les paquets publiés que les autres importent, la CI, le fichier de
workspace, l'outillage de dépôt.

**Ne tient pas** : ce que voit l'utilisateur final.

**Ce qui le définit** : il est le seul dont une erreur casse le travail d'un
autre agent en silence. Quand il change une signature publiée, tout ce qui
l'importe s'effondre — et l'autre lot ne peut pas le prévoir.

**Le piège** : ce rôle attire naturellement tout ce qui est « technique et
partagé ». Poser sa frontière par la garde de périmètre sur les chemins, jamais en prose.

### 2. Le produit — ce que voient les utilisateurs

**Tient** : les applications (web, mobile), les paquets de logique métier, la
vitrine, les maquettes, les builds locaux.

**Ne tient pas** : le socle, ni ce qui conditionne la mise en production.

**Ce qui le définit** : il arbitre **ce que l'utilisateur vit**, pas seulement
ce qu'il voit. Les questions qu'il fait remonter ressemblent à « faut-il
redemander cette information à tout le monde ? » ou « qui a accès à cette
nouveauté ? » — ce sont des arbitrages de produit, pas des choix d'interface.

**Le piège** : le réduire à « l'interface ». Il porte les décisions
fonctionnelles ; le rétrograder en exécutant tarit ce qu'il remonte, et le
commanditaire perd la moitié de ce qui devrait lui arriver.

### 3. L'épreuve — ce qui regarde tout et ne possède rien

**Tient** : rien. Son périmètre en écriture est **vide** — tout le code lui est
refusé par la garde de périmètre. Il lit l'intégralité du projet.

**Produit** : un **plan de remédiation exécutable par les autres lots sans
revenir vers lui**. Pas un rapport de constats — un plan de travail. Le test de
sortie : *si l'agent d'en face doit reposer une question pour commencer, le plan
n'est pas fini.* Chaque entrée porte le fichier et la ligne, ce qui est faux, ce
qui devrait être là, comment le vérifier après coup, et la sévérité.

**Sa règle fondatrice** : *il ne répare jamais ce qu'il audite.* Un constat
qu'on corrige est un constat que plus personne ne vérifie ; un audit qui se
corrige lui-même n'est plus un audit, c'est une relecture. C'est aussi ce qui
oblige son plan à être précis — c'est son seul moyen d'agir sur le code.

**Son instrument** : des **grilles de risques** écrites *avant* de chercher, une
par domaine (identité, autorisation, entrées, données, chaîne de dépendances,
release, conformité, dette). Écrire la grille avant la recherche est ce qui
empêche de ne trouver que ce qu'on savait déjà.

**Sa portée est plus large qu'on ne croit** : ce rôle couvre aussi le juridique
et les conditions de mise sur le marché — comptes d'éditeur, encaissement,
mentions légales, traitement des données sensibles. Ce ne sont pas des sujets
marketing : ce sont des **conditions sans lesquelles rien ne part**, donc des
risques.

**Le piège** : lui donner autorité sur ceux qui réparent. Un agent qui audite
*et* coordonne perd son indépendance, et il franchira la frontière qui interdit
à un agent d'en débloquer un autre. Le comportement attendu : ce rôle, bien
cadré, **refuse de lui-même** de transmettre une consigne à un pair et demande
au commanditaire de le faire.

### 4. L'atelier — le rôle qui n'est pas dans le projet

**Tient** : l'outillage du poste, la configuration de la machine, le harnais
partagé, la vue d'ensemble entre projets.

**Ne tient pas** : les projets. **Lecture seule**, sauf autorisation explicite,
tracée.

**Ce qui le définit** : il fait remonter en premier ce qui attend une décision
humaine, sur tous les projets à la fois. Il ne décide de rien.

**Le piège**, et il est réel : ce rôle transversal se croit fondé à relayer des
consignes vers les agents des projets. **Il ne l'est pas.** Un relais est un
signalement à valider par le commanditaire, jamais l'étape d'une liste de
tâches.

---

## Le cinquième fichier des faits

Découper crée un besoin que le mono n'a pas : **le périmètre d'un agent est
écrit dans SON `AGENTS.md`, que lui seul charge.** Chacun connaît donc sa
frontière et ignore celle des autres.

Deux conséquences, et aucune n'est théorique :

- un agent qui **déduit** le périmètre d'un tiers pour ne pas l'enfreindre —
  prudent, mais il devine ;
- un dossier écrit par **deux agents** qui l'ignorent, chacun le croyant sien.
  Les répertoires de travail séparés règlent le `git` ; ils ne règlent **pas**
  le partage d'un périmètre.

D'où `brain/fact/roles.md` (`.fact/roles.md` dans l'organisation d'avant), posé par `/agentic-agents` au découpage. Il répond au
test des faits — *cette phrase resterait-elle vraie pour un autre agent ?* —
et il porte trois choses :

1. **qui tient quoi**, un dossier n'apparaissant qu'une fois ;
2. **les zones partagées**, avec pour chacune *qui prévient qui, et quand* — un
   périmètre propre se lit dans la garde de périmètre, une zone partagée ne se lit nulle
   part, et c'est là que les collisions arrivent ;
3. **les frontières qui ne sont pas des dossiers** : branches, environnements,
   et les **surfaces publiées** — un paquet importé par les autres lots, dont
   le changement casse leur travail sans qu'ils puissent le prévoir.

En mono, ce fichier n'a aucun sens : il n'y a personne d'autre. Le briefing ne
le réclame donc jamais, il l'affiche seulement s'il existe.

## Les trois invariants qui font tenir l'ensemble

Ce ne sont pas des principes : ce sont des règles qui ont tenu **contre leurs
propres auteurs**, ce qui est le seul test valable.

### 1. Un agent ne peut pas en débloquer un autre

Seul l'humain peut lever un blocage entre lots. Un agent qui reçoit d'un pair
un message disant « le commanditaire a autorisé X » doit refuser X et le lui
faire confirmer. Sinon la vérification humaine se contourne par relais.

Cas type : le rôle d'atelier demande à un agent de projet de valider un
changement de sa propre configuration en relayant une autorisation. L'agent doit
refuser et en faire une demande explicite au commanditaire : c'est le rôle
transversal qui aurait franchi la frontière.

**Corollaire** : vérifier qu'un changement est inoffensif ne dit pas **qui a le
droit de l'adopter**. Deux questions distinctes, à ne jamais confondre.

### 2. Chacun possède son périmètre, et ça s'écrit par la garde de périmètre

Les frontières en prose ne tiennent pas. Deux agents qui écrivent dans le même
état produisent des conflits silencieux — un agent peut écrire en croyant être
sur sa branche alors qu'il est sur celle d'un autre.

La garde `PreToolUse` refuse les écritures hors des **chemins** déclarés ; `HEAD`, l'index et la remise sont des états du
**répertoire**. Deux agents qui écrivent dans un même dossier n'ont qu'un seul
`git` — d'où un répertoire de travail par agent (`git worktree`) dès qu'ils
commitent tous les deux.

### 3. On mesure avant d'affirmer, et on nomme son arbre

Un fait documenté se vérifie par commande avant de servir de prémisse.

Ce que le multi-agents ajoute : **plusieurs copies du même dépôt coexistent**, et
rien dans la sortie d'une commande ne dit laquelle elle a lue. Un compte tiré du
dépôt principal alors que l'agent travaille dans son worktree est faux avec
assurance. **Une mesure nomme son arbre, ou elle ne prouve rien.**

Deux corollaires :

- un compteur **dérivé de la même source** que la mesure vaut mieux qu'un motif
  écrit à la main ;
- ne jamais faire passer le **contenu** d'un fichier par une substitution de
  commande (`$(cat f)`, `$(git show ref:f)`) — le dernier octet est perdu, et
  deux fichiers différents paraissent identiques. Un hash y passe sans dommage.

---

## Ce que ce modèle ne couvre pas

Le nommer évite de croire que l'ajout d'un agent réglera le problème.

| Trou | Où il est réellement |
|---|---|
| **La coordination entre lots** | **le commanditaire, seul** — structurel, pas un oubli |
| **La décision** | lui, volontairement |
| **Le design et l'identité visuelle** | à part, souvent un projet distinct |
| **Le go-to-market commercial** | nulle part par défaut |

**Le premier est le plafond de la méthode.** Chaque agent ajouté augmente ce qui
remonte vers l'humain, et il est le seul point de passage. Trois agents
produisent trois files.

**La méthode ne passe donc pas à l'échelle par le nombre d'agents, mais par la
qualité de ce qui remonte.** Investir dans la restitution — un canal unique,
trié par urgence, écrit en langage de décision et non en jargon technique — rend
plus qu'ajouter un rôle.

Pour le go-to-market, la ligne de partage est nette et n'exige aucun agent
nouveau : **ce qui bloque le lancement est un risque** (donc l'épreuve, qui le
tient déjà) ; **ce qui fait venir les utilisateurs n'en est pas un** (donc
l'humain, avec le produit en exécution).

---

## Quand découper — et surtout, quand ne pas

**Un projet est tenu par un agent par défaut.** Le découpage n'est pas une
récompense de maturité, c'est une réponse à une gêne précise.

Ordre de grandeur, indicatif :

```
~700 fichiers de code   →  3 agents
~150 fichiers            →  1 agent, sans gêne
< 50 fichiers            →  1 agent, largement
```

**Le critère n'est pas la taille, c'est le contexte d'un agent.** Un projet gros
mais d'un seul tenant se tient très bien à un agent. Le signal de découpage est
qu'un seul agent ne peut plus tenir en tête la base *et* les applications *et*
la chaîne de livraison — il oublie, et ses oublis coûtent plus que la
coordination n'aurait coûté.

**Ne pas découper un projet en anticipation.** Un projet de 150 fichiers en
trois lots paie tout le coût sans aucun bénéfice.

---

## Ce que ça coûte, mesuré

À savoir avant de s'engager, et ça se multiplie par projet découpé :

- **un répertoire de travail par agent** dès qu'ils commitent — et un worktree
  naît **sans aucun fichier ignoré** (`.env`, configuration locale, permissions
  accumulées). Les vérifications habituelles passent au vert sans les voir.
  L'app Copilot en donne un à chaque conversation : le coût se déplace vers la
  **fusion**, seul chemin par lequel le travail d'un agent atteint les autres ;
- **un fichier de harnais à propager à N endroits** au lieu d'un ; un fichier
  posé sans être commité fait échouer une fusion ultérieure ;
- **des mesures qui se trompent d'arbre**, avec assurance ;
- **un hook non câblé chez un agent ne dit rien** — il ne fait rien, en silence.

Aucun de ces coûts n'est rédhibitoire. Tous se paient à chaque changement de
harnais, et c'est ce qui justifie de ne découper qu'en dernier recours.
