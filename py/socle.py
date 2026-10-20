# -*- coding: utf-8 -*-
"""OÙ LE HARNAIS ÉCRIT, ET OÙ IL LIT — le seul endroit qui connaît les chemins.

Repris du harnais Claude (Python), adapté à `harnais/src/socle.rs` du Copilot
(Rust, 1.3.0). Mêmes noms de fonctions.

Deux variables décident de tout, et Copilot CLI les pose pour chaque hook de
plugin (lu dans le CLI 1.0.90-0, qui les définit par paires) :

- `COPILOT_PLUGIN_DATA` : un dossier qui SURVIT AUX MISES À JOUR. C'est là que
  vivent les témoins, le journal des blocages, les leçons. Le code se remplace,
  pas ce qu'il a appris.
- `COPILOT_PLUGIN_ROOT` : où le code est posé. Chemin ABSOLU, ce qui ferme le
  piège mesuré du chemin relatif : sur un clone Windows, un lien symbolique
  devient un fichier texte et les hooks disparaissent sans bruit.

Sans elles, l'état reste dans `~/.copilot/plugin-data/atelier-copilot/harnais`,
le dossier que Copilot attribue à ce plugin. Résoudre ce chemin ne crée aucun
dossier : seule l'écriture le fait.
"""
import json
import os
import re

# Les noms que le socle prévoit pour les faits d'un projet — UNE SEULE FOIS. Ils
# décidaient de trois choses depuis trois listes séparées (briefing, garde de
# commit, migration) : deux copies ne divergent pas quand on les écrit, elles
# divergent six semaines plus tard, et rien ne le signale.
# `roles.md` est à part : il n'existe qu'à PLUSIEURS agents.
FAITS_MONO = ["base.md", "architecture.md", "stack.md", "rules.md"]
FAITS_EQUIPE = "roles.md"
# COMMUN À TOUS LES AGENTS, développeurs comme experts (décision du 12/10/2026 : « on
# doit intégrer un fichier workflow.md dans le folder fact aussi, pour tous les
# agents ») : comment procéder, les gestes qu'on ne redécouvre pas. Né le même
# jour. Il n'entre PAS dans `FAITS_MONO` : la migration exige ces
# quatre-là, et un projet ancien n'a pas à en avoir un cinquième pour migrer.
FAITS_COMMUNS = ["workflow.md"]

# LE PROFIL EXPERT (décision du 12/10/2026) — un agent qui ne code pas (juridique,
# comptabilité), ou qui code mais tient aussi le dossier de son métier (CTO). Ses faits
# ne sont pas le modèle d'un développeur : un socle — la nature, les SOURCES (ce
# qui fait foi), les règles, la façon de procéder — puis des fiches LIBRES au nom
# du métier (juridique : la société). `stack.md` joue le rôle des sources chez qui
# l'a déjà (le CTO garde ses fiches de développeur).
SOCLE_EXPERT = ["base.md", "sources.md", "rules.md", "workflow.md"]


def faits_tous():
    """Les noms que le garde autorise sans demander : mono, équipe, communs."""
    return FAITS_MONO + [FAITS_EQUIPE] + FAITS_COMMUNS


def profil_expert():
    """`HARNAIS_PROFIL=expert` dans les réglages de l'agent — comme `HARNAIS_CANAL`
    et `HARNAIS_SYNCHRO` : à la demande, agent par agent. Sans lui, rien ne change
    (développeur), et un projet ordinaire reste à l'octet."""
    return os.environ.get("HARNAIS_PROFIL", "").strip() == "expert"


def maison():
    return os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."


def chemin_etat(donnees, maison_copilot):
    return donnees if donnees else os.path.join(maison_copilot, "plugin-data", "atelier-copilot", "harnais")


def socle():
    """Le dossier d'état. `COPILOT_PLUGIN_DATA` d'abord (puis `PLUGIN_DATA`)."""
    import hote
    d = os.environ.get("COPILOT_PLUGIN_DATA") or os.environ.get("PLUGIN_DATA")
    return chemin_etat(d, hote.maison_copilot())


def livre():
    """Le dossier du paquet, ou None hors plugin. Sert à retrouver ce qui est
    LIVRÉ (critères de relecture, liste des rechutes d'origine) par opposition à
    ce que l'agent a écrit depuis."""
    import copilot
    return copilot.paquet_ou_rien()


def cle_memoire(brut):
    """LA CLÉ SOUS LAQUELLE CLAUDE CODE RANGE LA MÉMOIRE D'UN PROJET.

    Un tiret par caractère non alphanumérique, SANS jamais les fondre : c'est la
    règle que Claude Code applique en écrivant ces dossiers, donc c'est elle qui
    décide où ils sont. `…/Agentic/.worktrees/x` reçoit `--worktrees` (mesuré :
    27 dossiers réels sur 51 portent un double tiret).

    Le préfixe canonique de Windows (`\\\\?\\`) n'entre pas dans la clé : slugifiés,
    `\\\\?\\C:\\x` et `C:\\x` seraient deux mémoires.

    ASCII seulement : `str.isalnum()` accepterait « é », ce que Claude Code ne fait pas.
    """
    if brut.startswith("\\\\?\\"):
        brut = brut[4:]
    return "".join(c if (c.isascii() and c.isalnum()) else "-" for c in brut)


def dossier_de_la_memoire(d):
    """LE DOSSIER DONT CLAUDE CODE TIRE CETTE CLÉ : la racine de l'arbre PRINCIPAL
    du dépôt, pas le dossier de lancement ; hors dépôt, le dossier lui-même."""
    try:
        brut = os.path.realpath(d)
    except OSError:
        brut = str(d)
    import memoire
    r = memoire.racine_depot(brut)
    if r is not None:
        try:
            return os.path.realpath(r)
        except OSError:
            return str(r)
    return brut


def memoire_auto(racine):
    """La mémoire auto d'un projet (`~/.claude/projects/<clé>/memory`), ou None."""
    slug = cle_memoire(dossier_de_la_memoire(racine))
    m = os.path.join(maison(), ".claude", "projects", slug, "memory")
    return m if os.path.isdir(m) else None


def chemin_affiche(depuis, cible):
    """COMMENT ON NOMME UN FICHIER À UN AGENT — une seule règle, partout.

    Relatif au dossier d'où il travaille quand le fichier y est accessible ;
    ABSOLU sinon. Séparateurs en `/` : convention de l'atelier. Un chemin
    recomposé à la main au lieu d'être dérivé est le défaut mesuré trois fois
    par l'audit du 10/09/2026.

    Comme `Path::strip_prefix` en Rust : le préfixe se compare par COMPOSANTS
    (`/d/Projet` n'est pas un préfixe de `/d/Projet PO/x`).
    """
    depuis = str(depuis).replace("\\", "/").rstrip("/")
    cible_s = str(cible).replace("\\", "/")
    if depuis and (cible_s == depuis):
        return ""
    if depuis and cible_s.startswith(depuis + "/"):
        return cible_s[len(depuis) + 1:]
    return cible_s


# ── JSON : la forme exacte des fichiers d'état ──────────────────────────────

def json_python(v):
    """`json.dumps(x)` de Python, à l'octet : séparateurs `, ` et `: `, tout ce
    qui n'est pas ASCII échappé en `\\uXXXX`."""
    return json.dumps(v)


def json_trie(v):
    """`sort_keys=True`, à TOUS les niveaux (ne trier que le premier fait que les
    deux versions n'écrivent plus le même octet)."""
    if isinstance(v, dict):
        return {k: json_trie(v[k]) for k in sorted(v)}
    if isinstance(v, list):
        return [json_trie(x) for x in v]
    return v


def ecrire_json(f, v):
    """`json.dumps(x, ensure_ascii=False, indent=1, sort_keys=True)` puis
    remplacement atomique — la forme exacte des fichiers d'état du harnais."""
    try:
        texte = json.dumps(json_trie(v), ensure_ascii=False, indent=1)
    except (TypeError, ValueError):
        return
    f = str(f)
    tmp = re.sub(r"\.[^./\\]*$", "", f) + ".json.tmp" if "." in os.path.basename(f) else f + ".json.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as h:
            h.write(texte)
        os.replace(tmp, f)
    except OSError:
        pass
