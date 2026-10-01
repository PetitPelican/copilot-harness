# Les rôles — [PROJECT_NAME]
_Dernière mise à jour : YYYY-MM-DD_

> **Ce fichier n'existe qu'en multi-agents, et il existe pour une raison
> précise :** le périmètre d'un agent est écrit dans **son** `AGENTS.md`, que
> lui seul charge. Chacun connaît donc sa frontière et **ignore celle des
> autres** — d'où des agents qui déduisent le périmètre d'un tiers pour ne pas
> l'enfreindre, et des dossiers écrits par deux mains sans que personne le
> sache. Ici, chacun lit **tout** le découpage.
>
> Il appartient à `[FAITS]/` parce qu'il répond au test : *cette phrase
> resterait-elle vraie pour un autre agent du projet ?* Oui, pour tous. Il ne
> s'écrit donc qu'à la demande du commanditaire (` # fact-ok` au commit), et le
> texte périmé s'y **remplace**.

## Qui tient quoi

| Agent | Tient | Ne touche pas |
|---|---|---|
| `<agent-1>` | … | … |
| `<agent-2>` | … | … |
| `<agent-3>` | … | … |

Un dossier n'apparaît qu'**une fois** dans la colonne « tient ». S'il en faut
deux, il relève de la section suivante.

## Les zones partagées

**C'est la partie qui justifie ce fichier.** Un périmètre propre se lit dans la garde `PreToolUse` ; une zone partagée ne se lit nulle part, et c'est là que les collisions
arrivent.

| Zone | Qui y écrit | Comment on évite la collision |
|---|---|---|
| `…` | `<agent-1>`, `<agent-2>` | … |

Pour chaque zone : **qui prévient qui**, et à quel moment. Une zone partagée
sans règle de coexistence n'est pas partagée, elle est en conflit.

## Ce qui n'appartient à personne

`[FAITS]/`, `docs/`, `.logs/` et la racine du dépôt. Un agent n'y écrit qu'à la
demande du commanditaire.

## Les frontières qui ne sont pas des dossiers

Ce que la garde de chemins ne peut pas exprimer, et qui doit donc être écrit :

- les **branches** et répertoires de travail de chacun ;
- les **environnements** (qui déploie quoi, qui détient quels accès) ;
- les **surfaces publiées** — un paquet importé par les autres lots : le
  modifier casse leur travail sans qu'ils puissent le prévoir.

## Ce que ce découpage ne couvre pas

Le nommer évite de croire qu'un agent de plus réglerait le problème. La
coordination entre lots n'appartient à aucun agent : **seul l'humain peut
débloquer un lot au profit d'un autre**, et c'est délibéré.

---

_Méthode et rôles types : `skills/agentic-agents/references/roles.md` (dans le paquet)._
