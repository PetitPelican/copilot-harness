---
name: agentic-team
description: >
  Lit la mémoire et les réglages de tous les projets d'un atelier et en rend
  deux vues : un DIAGNOSTIC en terminal (projet par projet et agent par agent :
  la mémoire, le paquet déclaré, inscrit, servi, et quoi faire) et une PAGE HTML autonome, qui s'ouvre d'un double-clic sur n'importe
  quelle machine, sans serveur. Cette page s'appelle **agentic-team**.
  Strictement en lecture.
  Trigger: /agentic-team, « ouvre la page agentic-team », « agentic team »,
  « /equipe » (ancien nom), « la vue
  d'équipe », « le tableau de l'atelier », « où en sont les projets »,
  « diagnostique ce projet », « qu'est-ce qui m'attend ».
---

# Équipe

> **Deux questions, une seule lecture.** « Dans quel état est ce projet, et que
> faut-il y faire ? » et « où en est toute l'équipe ? » se répondent avec les
> mêmes fichiers : la mémoire de chaque projet et les réglages de chaque agent.
> Un seul analyseur, deux sorties — deux analyseurs finiraient par diverger, et
> personne ne le verrait.

**Strictement en lecture.** Ce skill n'écrit que la page HTML qu'on lui demande.
Il ne touche à aucun projet : il dit ce qu'il faut lancer, il ne le lance pas.

## Les trois usages

```bash
# 1. Diagnostic de tout l'atelier, en terminal
harnais equipe-vue --racine ~/Agentic

# 2. Un seul projet, en détail — « va voir ce projet-là »
harnais equipe-vue --racine ~/Agentic --projet <NomDuProjet>

# 3. La page autonome
harnais equipe-vue --racine ~/Agentic --html ~/agentic-team.html
```

Le programme est celui du paquet, le même sur Mac et sur Windows — le
briefing d'un projet en donne le chemin exact.

**Il lit toutes les organisations de mémoire et les réglages du paquet.** Un
diagnostic qui n'en lirait qu'une classerait à tort des projets sains « sans
mémoire », et enverrait vers des commandes qui n'existent plus. Un tableau de
bord qui désigne presque tout l'atelier comme à refaire apprend à ne plus le
lire.

## La page

**Autonome au sens strict** : aucun serveur, aucun CDN, aucune police distante,
aucun fichier joint. Tout est dans le fichier. Elle s'ouvre d'un double-clic,
hors ligne, sur macOS comme sur Windows — et se copie sur une clé si besoin.

Elle ouvre sur **ce qui attend une décision**, avant les cartes de projet : c'est
la seule colonne qui ne se délègue pas. Puis une carte par projet avec le `cap:`,
la fraîcheur, l'état du harnais et l'avancement des tâches. Thème clair et sombre
selon le réglage de la machine.

Régénérer, c'est relancer la commande : la page est un **relevé daté**, pas un
tableau de bord vivant. Elle porte sa date en tête.

## Ce que le diagnostic lit

- **La mémoire, par la même règle que le briefing** : `brain/`, l'organisation
  d'avant (`.fact/` et `.mind/` en place, ou déportés dans `memoire/`), et les
  projets à cheval entre les deux. À plusieurs agents, l'état de chacun est
  cherché là où il vit — `brain/mind/<nom>/`.
- **Le paquet, dans chaque dossier d'où un agent se lance** : la racine en mono,
  chaque `agents/<nom>/` à plusieurs — Copilot charge les réglages à la racine git ; ceux des
  sous-dossiers d'agents sont inertes dans un dépôt commun. Trois choses séparées, parce que chacune peut manquer
  seule et en silence : le paquet **déclaré** (les réglages), le dossier
  **résolu** (marketplace connue ou paquet installé), et la **trace
  d'entrée** qui prouve qu'il a servi, avec la version qui l'a écrite — copies
  de travail comprises, car un agent peut se lancer depuis l'une d'elles.

**Attention :** si `equipe-vue` traite les réglages des sous-dossiers comme
effectifs ou ceux de la racine comme inertes, ses verdicts de plugin ne
prouvent rien sous Copilot. Tester briefing et refus de la garde.

## Les verdicts

Pour chaque projet, dans cet ordre — le premier problème rencontré donne le
verdict, parce que les suivants n'ont pas de sens tant qu'il n'est pas réglé :

| Verdict | Ce qui a été constaté | Ce qu'il faut faire |
|---|---|---|
| `GIT` | pas de dépôt git | `git init` — sans dépôt, aucune mémoire n'est cherchée |
| `NEUF` | aucune mémoire | `harnais adopte`, à blanc puis `--go` |
| `TRI` | ancienne taxonomie, ou tout dans `.mind/` | le tri à la main, puis `harnais adopte` ou `harnais brain-migre` |
| `AMBI` | `brain/` et l'organisation d'avant à la fois | `harnais brain-migre` termine la migration |
| `AGT?` | des faits, aucun état d'agent | `harnais adopte --go` en `brain/` |
| `MANQ` | un fichier de la mémoire manque | `harnais adopte --go` en `brain/` ; à la main sinon |
| `BRCH` | rien ne déclare le paquet | `harnais adopte --go` |
| `HOOK` | câblé par des hooks locaux d'avant le paquet | déclarer le paquet, puis retirer les hooks locaux |
| `INSC` | déclaré, mais paquet non résolu : il ne se charge pas | `copilot plugin marketplace add <chemin-local>` puis `copilot plugin install harnais@atelier-copilot` ; vérifier la racine git |
| `????` | la résolution du paquet n'a pas pu être vérifiée | rien n'est conclu — ce n'est pas un « inscrit » |
| `SERV` | aucune trace d'entrée | démarrer l'agent, puis relire |
| `TROP` | un fichier que la mémoire ne prévoit pas | le déplacer vers `docs/` |
| `DENY` | garde de périmètre absente | poser et tester `PreToolUse` du harnais |
| `MAJ` | session antérieure à une correction du paquet local | `/restart` ou nouvelle session (marketplace locale chargée en direct) |
| `RETD` | la session tourne sur une version plus vieille que l'inscrite | rien : elle la prendra à son prochain démarrage |
| `V1` | servi, dans l'organisation d'avant | `harnais brain-migre`, quand on le décide |
| `OK` | servi, mémoire complète | rien |

**Ces conseils sont à vérifier contre la version du programme en service.**
Un verdict d'une version antérieure ne prouve pas l'activation actuelle. C'est le
défaut à éviter : un conseil qui envoie vers une commande morte apprend à ne
plus lire les conseils.

Le `AGENTS.md` qui nomme (ou non) la mémoire, références `@` comprises, reste affiché
comme une information : depuis le briefing, le harnais sert l'index de la
mémoire à l'entrée, qu'il la nomme ou non.

Il lit aussi l'en-tête de `state.md` (`maj`, `sante`, `jalon`), le `cap:` dans
les faits du projet, et rend trois états de fraîcheur, jamais deux : **à
jour**, **tiède** (plus de 7 jours), **périmé** (plus de 4 semaines) — et
**illisible**, qui est le cas grave : un en-tête cassé fait disparaître le
projet des tableaux de bord sans un mot.

## Formater un projet existant — la marche à suivre

Le diagnostic dit **quoi** faire. Le faire demande deux précautions.

**1. Travailler depuis le dossier du projet.** Le *jugement* — écrire le cap,
trier une mémoire, réconcilier `AGENTS.md` — demande d'être dans le projet :
Copilot charge les instructions de la racine git aux dossiers intermédiaires
jusqu'au `cwd`, mais les réglages uniquement à la racine git. Une session
ouverte ailleurs peut donc recevoir d'autres instructions et réglages.

**2. Le tri de mémoire n'est jamais automatique.** Le diagnostic signale une
taxonomie ancienne, il ne la migre pas : trier demande de lire le contenu, et le
contenu appartient au projet.

Puis vérifier, dans cet ordre : le dépôt est un dépôt git · le paquet est
déclaré **et inscrit** à la racine git · en équipe, chaque agent a son profil
`.github/agents/<nom>.agent.md` commité · **il sert vraiment**, ce qui se voit
au briefing d'entrée (ligne `agent` en équipe). Relancer `harnais equipe-vue --projet
<nom>` doit alors rendre `OK`.

## Le contrat de lecture

L'analyseur suit **le même contrat que le tableau de bord**, et
c'est une contrainte, pas un détail : deux analyseurs qui divergent, c'est deux
vérités et aucun signal.

- en-tête `---` … `---` en tête de `state.md`, champs `maj cap sante jalon`
- tâches `- [ ]` `- [>]` `- [~]` `- [x]`, **dans tout le fichier**, toutes
  sections confondues
- marqueurs `!haut` `!moyen` `!bas` et `@<qui>`, dont `@dehors` réservé

> Ne pas se borner à une section « Chantiers ». Les fichiers réels s'organisent
> librement — « Attend une décision », « Outillage », « Technique ». Un analyseur
> qui ne lirait que ce qui suit un titre « Chantiers » rendrait **zéro tâche sur
> des projets pleins**, sans rien signaler. Le titre reste reconnu pour les
> anciens `pilotage.md` qui bornaient réellement leur section.

## Règles

- **Lecture seule.** Ne jamais modifier un projet depuis ce skill.
- **Ne rien voir n'est pas un succès.** Zéro tâche `@<qui>` sur tout un atelier
  se vérifie avant d'être annoncé — c'est plus souvent un analyseur cassé qu'un
  atelier serein.
- Ne pas recopier l'état d'un projet ailleurs : la page est un relevé daté, la
  vérité reste dans la mémoire de chaque projet.
