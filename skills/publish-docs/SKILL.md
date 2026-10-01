---
name: publish-docs
description: >
  Génère un site de documentation Quarto (HTML + Word/PDF) DEPUIS la mémoire publique du
  projet. Modes : setup (installe Quarto/Graphviz/deps Python), init (scaffold + config),
  refresh (mémoire -> site/_content/), publish (build + rendu + déploiement pluggable).
  Ne lit JAMAIS operations.md (privé). Trigger: /publish-docs [setup|init|refresh|publish]
---

# Publish-docs — doc vivante Quarto depuis la mémoire

Une source unique (`site/_content/`) → **site HTML + un livrable Word/PDF par domaine**.
Le contenu est **généré depuis `brain/fact/`, `brain/mind/` et `docs/`** (fichiers **publics** uniquement),
jamais depuis `operations.md` (privé : hébergement, secrets, dépannage).

## Pièces

- `site/site.config.yml` — titre, tagline, logo, `preset` (data|web|api|generic), domaines, `deploy`.
- `site/_content/**` — **LA** source éditable (produite par `refresh`). `_content/<domaine>/*.qmd` + `_content/status/` + `_content/index.qmd`.
- `site/_content/<domaine>/_diagrams/*.dot` — schémas Graphviz (rendus SVG web + PNG export).
- `site/build_site.py` — assembleur (config → `_quarto.yml` + `theme.scss` + schémas + dossiers). Sidebar/domaines **dérivés** de `_content/`.
- `site/publish.py` — build + rendu Quarto + déploiement (`azure` | `ghpages` | `zip` | `none`).
- Binaires requis : **Quarto** (embarque Typst→PDF et Pandoc→Word) et **Graphviz** (`dot`). Deps pip : `site/requirements.txt`.

Sans argument : demander lequel des 4 modes lancer (setup / init / refresh / publish).

---

## Mode `setup` — outils (semi-auto guidé)

1. **Deps Python** (auto) : `python -m pip install -q -r site/requirements.txt` (matplotlib, jupyter, ipykernel, nbclient, nbformat, graphviz, pyyaml). `-q` limite la sortie (économie de tokens).
2. **Quarto** : `quarto --version`. Si absent, **proposer** (avec confirmation) selon l'OS :
   - Windows : `winget install --id Posit.Quarto -e`
   - macOS : `brew install --cask quarto`
   - Linux : télécharger le `.deb`/`.rpm` depuis `quarto.org/docs/get-started/` (pas de paquet apt officiel)
3. **Graphviz** (`dot`) : `dot -V`. Si absent, proposer :
   - Windows : `winget install --id Graphviz.Graphviz -e`
   - macOS : `brew install graphviz`
   - Linux : `sudo apt-get install -y graphviz`
4. **Valider** : `quarto check` (doit voir Pandoc + Typst) et `dot -V`.

Ne jamais installer en mode silencieux/admin sans confirmation. Typst et Pandoc sont **dans** Quarto : rien à installer en plus.

---

## Mode `init` — scaffold + configuration

1. Si `site/` est absent (projet existant), le copier depuis un modèle de site (`cp -r <modèle>/site ./site`).
2. Poser / déduire :
   - **titre** (défaut : nom du projet dans AGENTS.md), **tagline**, **logo_letter** (1 lettre, défaut = initiale du titre),
   - **preset** (défaut = type de projet vu par `project-init` : data-pipeline→`data`, web-app→`web`, API→`api`, sinon `generic`),
   - **domaines** (mono-domaine = un seul ; multi-domaine = un par sous-projet),
   - **deploy.target** (`zip` par défaut ; `azure`/`ghpages` si l'hébergement est connu — cf. `operations.md`).
3. Écrire `site/site.config.yml`.
4. Lancer `setup` si les outils manquent.
5. Retirer le domaine d'exemple (`_content/example/`) avant le premier `refresh` réel.

---

## Mode `refresh` — mémoire → `_content/` (le cœur)

Lire les fichiers mémoire **publics** et le code, puis **écrire une prose publiable, orientée
lecteur** dans `site/_content/<domaine>/<section>.qmd` selon la carte du preset. **Ne pas** recopier
la mémoire telle quelle : reformuler pour un lecteur externe, factualiser, structurer.

### Carte mémoire → sections (spine commun)

| Section | Source mémoire | Contenu |
|---|---|---|
| `objectifs-perimetre.qmd` | champ `cap:` de `brain/fact/base.md` (et sa prose « Où on va ») + frontières de `brain/fact/architecture.md` | Résumé, objectif, périmètre (dans/hors), contexte. Mettre `@@EXPORT:<domaine>@@` en tête. |
| `architecture.qmd` | `brain/fact/architecture.md` (+ `docs/data-model.md`) | Vue d'ensemble, composants, flux (schéma `dot`), modèle de données. |
| `regles-gestion.qmd` *(preset data/generic)* | `brain/fact/rules.md` | Règles métier & d'accès, contraintes. |
| `points-ouverts.qmd` | `docs/decisions.md` + `brain/mind/todo.md` (`[ ]`, `[>]`, `@<qui>`) | Décisions présentables + points à trancher. |
| `status/{journal,en-cours,backlog}.qmd` | `.logs/<jour>.md` (journal daté) + `brain/mind/todo.md` (en cours, backlog) | Transverse, pas par domaine. |
| `index.qmd` | `cap:` de `brain/fact/base.md` (tagline) + `AGENTS.md` (titre) | Accueil : hero `@@TITLE@@`/`@@TAGLINE@@` + `@@CARDS@@`. |

Presets — sections spécifiques en plus du spine :
- **web** : `stack-conventions.qmd` (← `brain/fact/stack.md` + `brain/fact/rules.md` : stack, conventions de code), `fonctionnalites.qmd` (← `brain/fact/architecture.md` + `brain/fact/rules.md` : features).
- **api** : `endpoints.qmd` (← architecture : routes), `auth-securite.qmd` (← rules : auth, RBAC — **sans secrets**).
- **data** : `recette.qmd` (← state/decisions : validation, chiffres — graphes matplotlib possibles).

### Schémas & graphes
- **Flux/architecture** → créer/mettre à jour `_content/<domaine>/_diagrams/<nom>.dot` (boîtes `style="filled,rounded"`, `rankdir=LR`) et l'embarquer :
  `::: {.column-page-right}` + `![Légende.](img/<nom>.svg){#fig-<id> fig-align="center"}` + `:::`
- **Graphes de données** → cellule ```{python}``` matplotlib (le build gère SVG web / PNG export). Ne jamais inventer de chiffres : les tirer d'une source réelle (requête, fichier) ou les omettre.
- **Code/SQL réel** → jetons `@@SQL:chemin.sql@@` / `@@CODE:chemin.py:python@@` (DRY, jamais de copie).

### Règles secrets (DURES)
- **Ne jamais lire** `operations.md` ni un fichier `.env*`.
- **Ne jamais écrire** de token, clé, secret, mot de passe, IP interne, URL/chemin sensible dans `_content/`.
- Après écriture : contrôle `grep -rIE '(\.env|BEGIN PRIVATE|SAS|token|secret|[0-9]{1,3}(\.[0-9]{1,3}){3})' site/_content/` → doit être **vide**.
- **Faire relire le diff `_content/` par l'humain avant `publish`.**

---

## Mode `publish`

1. `python site/publish.py --no-deploy` d'abord (vérifier HTML + dossiers Word/PDF).
2. Puis `python site/publish.py` (déploie selon `deploy.target`) ou `--target <cible>` pour forcer.
3. Rappeler la cible et l'URL (azure) / la branche (ghpages) / le zip produit.

Pré-condition : l'humain a relu `_content/`. Ne pas déployer une doc non relue.

---

## Règles

- Le contenu publiable ne vient QUE des fichiers mémoire **publics** ; `operations.md` est un pare-feu.
- Éditer la doc = éditer `docs/` puis `/publish-docs refresh` (ou éditer `_content/` directement pour un ajustement ponctuel) — **jamais** `site/<domaine>/*.qmd` (générés) ni `_site/`.
- Après une mise à jour de `brain/mind/`, proposer `/publish-docs refresh` pour resynchroniser.
- Ne pas committer/pousser sans accord explicite (le déploiement `ghpages` pousse une branche : confirmer).
