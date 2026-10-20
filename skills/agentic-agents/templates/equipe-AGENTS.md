# {PROJET}

<!-- Étage 3 sur 4 : ce qui vaut pour tous les agents de {PROJET}, et rien que ce
     que les consignes communes (l'AGENTS.md des dossiers au-dessus) ne disent pas.
     Gabarit du paquet harnais (organisation éprouvée en situation réelle, 14/10/2026, portée
     au harnais Copilot) : à adapter, puis à faire poser par le CTO. -->

[UNE_PHRASE_SUR_LE_PRODUIT]. Agents, chacun dans `agents/<nom>/` : {AGENTS}.
`fact/roles.md` dit qui tient quoi.

## Règles

1. Git : commit libre. Envoi sur `dev` et les branches de travail sans
   demander, si la tâche est dans la liste de travail et que les contrôles
   passent sur l'arbre exactement poussé. `main`, donc la Production :
   uniquement sur demande explicite de @user — le garde de la Production le
   refuse à tous, sauf à {PROD} muni d'un laissez-passer.
2. Jamais de fichier ni de commande git dans le dossier d'un autre agent.
3. Une absence s'affirme avec un témoin : la même recherche, sur un cas connu,
   doit rendre non-zéro.

## Les plans de {GUICHET} s'exécutent sans redemander

Ce que {GUICHET} demande dans un plan publié (`docs/audit/…`) est une commande :
les lots l'exécutent sans demander « je lance le plan ? ». Seuls remontent
l'irréversible et un garde qui refuse. Une demande hors plan : demander à
{GUICHET} de l'écrire.

## Ce qui se fait sans @user

- La base de développement et les projets jetables : libres, supprimés après
  usage. La Production : lecture libre pour les lecteurs désignés, tout geste à
  l'accord de @user au moment du geste, exécuté par {PROD} seul.
- Les compilations d'essai : libres, une à la fois, mémoire de la machine
  vérifiée avant, arrêtées avant de rendre la main. Celles pour les magasins :
  sur ordre de @user.
- **{GUICHET} est le guichet unique des questions.** Les autres agents ne posent
  aucune question à @user : ils l'adressent à {GUICHET} par le carnet d'équipe
  (`↗ {GUICHET} : …`), fermée, avec leur recommandation, et ne portent pas de
  `@user` dans leur todo. Exception : dans un tour ouvert par @user lui-même, la
  question sur le sujet qu'il traite se pose à lui, en fin de tour.
- {GUICHET} tranche des choix, il n'autorise aucun geste réservé à @user :
  Production, `main`, argent réel, magasins, secrets, textes légaux, marque,
  nouveau périmètre produit.

## La liste de travail

[OÙ_VIT_LA_LISTE — tenue par {GUICHET}]. Elle dit QUOI faire ; ce qu'elle
n'autorise pas se demande à @user au moment du geste. Une tâche finie passe à
« fait, à vérifier » avec sa preuve ; jamais « vérifié » par l'agent qui l'a
faite.

## Où regarder

Le dossier du projet est la mémoire de l'équipe, un seul exemplaire : `fact/`,
`shared/` (le carnet), `agents/<nom>/` (état, tâches, et la copie du code dans
`code/`), `docs/`, `assets/`.
