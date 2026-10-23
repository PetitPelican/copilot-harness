# -*- coding: utf-8 -*-
"""MONTER UN ATELIER sur une machine neuve — pas un projet, la couche au-dessus.

Port de `harnais/src/atelier.rs` (Rust, 1.3.0). Mêmes noms de fonctions.

    <racine>/AGENTS.md      la MÉTHODE, héritée par tout agent d'un sous-dossier
    <racine>/<cto>/         le poste du CTO, harnais posé, dépôt git

Deux fichiers de rôle, puis le harnais sur le poste du CTO — la seconde moitié
est déléguée à `adopte`, au lieu d'en écrire une seconde copie.

POURQUOI LE SOCLE NE « PRÉVAUT » PAS. Un `AGENTS.md` parent n'écrase pas celui
d'un projet : les deux sont lus, le plus précis l'emporte. Le socle porte
l'invariant, le projet ajoute son rôle par-dessus.

**À blanc par défaut.** `--go` pour écrire. Rien n'est jamais écrasé.

Les gabarits se lisent à l'appel dans `skills/agentic-init/templates/` du
paquet, à côté de `py/` (le Rust les compilait dans le programme).
"""
import json
import os
import subprocess
import sys

REGISTRE = "docs/projects.json"

ACCUEIL = (
    "ACCUEIL CTO — aucun projet déclaré dans docs/projects.json.\n"
    "Termine d'abord les sections À REMPLIR de la mémoire du CTO. Puis demande à\n"
    "l'utilisateur s'il a un projet nouveau ou existant ; demande son nom, et où est\n"
    "son code s'il existe, au tour suivant. Ne crée rien avant son accord explicite.\n"
    "Le projet agentique se crée sous la racine de l'atelier (son propre dépôt git) ;\n"
    "un code existant ailleurs y reste, sans rien y écrire : `harnais adopte --code\n"
    "\"<chemin du code>\"` depuis le dossier du projet en garde l'adresse.\n"
    "Présente les profils : OPS = socle (base, routes serveur, CI, déploiement, workspace) ;\n"
    "PO = produit (applications, logique métier, ce que voit l'utilisateur) ;\n"
    "QA = épreuve (mémoire et livrables propres, faits sur accord humain ; jamais de réparation technique).\n"
    "Un profil = mono-agent ; plusieurs = multi-agents après lecture de roles.md.\n"
    "On ne découpe pas parce que le projet est gros. Propose ensuite de personnaliser\n"
    "chaque profil (nom, périmètre, règles, ton), ou de garder ses valeurs par défaut.\n"
    "Prévisualise l'adoption et les agents ; attends l'accord avant l'écriture.\n"
    "Déclare le projet dans docs/projects.json seulement après l'adoption réussie.")


class RegistreInvalide(Exception):
    """Le registre des projets existe mais ne se lit pas comme prévu."""


def accueil(racine):
    """L'accueil du CTO tant qu'aucun projet n'est déclaré, ou None. Lève
    `RegistreInvalide` sur un registre cassé : le dire, jamais deviner."""
    fichier = os.path.join(str(racine), *REGISTRE.split("/"))
    try:
        with open(fichier, encoding="utf-8") as f:
            texte = f.read()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as e:
        raise RegistreInvalide("%s : %s" % (fichier, e))
    try:
        registre = json.loads(texte)
    except ValueError as e:
        raise RegistreInvalide("%s : %s" % (fichier, e))
    s = registre.get("schema") if isinstance(registre, dict) else None
    if isinstance(s, bool) or s != 1:
        raise RegistreInvalide("%s : schema doit valoir 1" % fichier)
    projets = registre.get("projects")
    if not isinstance(projets, list):
        raise RegistreInvalide("%s : projects doit être une liste" % fichier)
    for projet in projets:
        if not isinstance(projet, dict):
            raise RegistreInvalide("%s : projet sans name" % fichier)
        for champ in ("name", "path"):
            v = projet.get(champ)
            if not (isinstance(v, str) and v.strip()):
                raise RegistreInvalide("%s : projet sans %s" % (fichier, champ))
        profils = projet.get("profiles")
        if not isinstance(profils, list):
            raise RegistreInvalide("%s : projet sans liste profiles" % fichier)
        if not profils or any(p not in ("OPS", "PO", "QA") for p in profils):
            raise RegistreInvalide("%s : profiles attend OPS, PO ou QA" % fichier)
    return ACCUEIL if not projets else None


def _gabarit(nom):
    ici = os.path.dirname(os.path.abspath(__file__))
    chemin = os.path.join(os.path.dirname(ici), "skills", "agentic-init", "templates", nom)
    # `newline=""` : aucun saut de ligne n'est traduit, le fichier se pose tel qu'il est.
    with open(chemin, encoding="utf-8", newline="") as f:
        return f.read()


def valeur(args, cle):
    it = iter(args)
    for a in it:
        if a == cle:
            return next(it, None)
        if a.startswith(cle + "="):
            return a[len(cle) + 1:]
    return None


def developpe(p):
    maison = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if p == "~" and maison:
        return maison
    if p.startswith("~/") and maison:
        return os.path.join(maison, p[2:])
    return p


class Echec(Exception):
    pass


def pose(texte, dst, go, faits, ignores):
    """Pose un gabarit, jamais par-dessus un fichier existant. Lève `Echec` si
    l'écriture rate : un atelier monté à moitié se dit."""
    if os.path.exists(dst):
        ignores.append("Existe déjà, non écrasé : %s" % dst)
        return
    faits.append("Créer %s" % dst)
    if go:
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
        except OSError as e:
            raise Echec("%s : %s" % (os.path.dirname(dst), e))
        try:
            # `x` : jamais par-dessus un fichier apparu entre-temps.
            with open(dst, "x", encoding="utf-8", newline="") as f:
                f.write(texte)
        except OSError as e:
            raise Echec("%s : %s" % (dst, e))


def _p(s=""):
    sys.stdout.write(s + "\n")


def main(args):
    if any(a == "-h" or a == "--help" for a in args):
        _p("harnais atelier-monte [--racine R] [--cto NOM] [--utilisateur PRÉNOM] [--go]\n\n"
           "Monte un atelier : la méthode à la racine, le poste du CTO avec son rôle et le\n"
           "harnais. À blanc par défaut ; `--go` écrit. Rien n'est jamais écrasé.")
        return 0
    import adopte
    import copilot
    go = any(a == "--go" or a == "--apply" for a in args)
    racine = developpe(valeur(args, "--racine") or "~/Agentic")
    nom_cto = valeur(args, "--cto")
    if nom_cto is None:
        # « CTO », pas « cto » (Claude 0.19) : c'est l'adresse que lit le verrou des
        # consignes et celle des outils du poste. Un poste monté en minuscules
        # donnait un CTO qui n'avait le droit d'écrire aucune consigne commune.
        nom_cto = "CTO"
    if nom_cto in ("", ".", "..") or any(c in nom_cto for c in "/\\:"):
        sys.stderr.write("atelier-monte : --cto doit être un nom de dossier simple.\n")
        return 1
    qui = (valeur(args, "--utilisateur") or "").strip() or "l'utilisateur"
    cto = os.path.join(racine, nom_cto)

    _p("Atelier — montage")
    _p("Racine      : %s" % racine)
    _p("CTO         : %s" % cto)
    _p("Mode        : %s" % ("ÉCRITURE" if go else "À BLANC"))
    _p()

    faits, ignores = [], []
    try:
        if not os.path.exists(racine):
            faits.append("Créer la racine %s" % racine)
            if go:
                try:
                    os.makedirs(racine, exist_ok=True)
                except OSError as e:
                    raise Echec("%s : %s" % (racine, e))
        # 0. L'ÉTAGE 1, la machine : posé « À REMPLIR » s'il manque, jamais écrasé.
        #    COPILOT : les instructions personnelles de Copilot CLI sont dans
        #    `<COPILOT_HOME>/copilot-instructions.md` (supposé : non mesuré sur un hôte réel).
        import hote
        pose(_gabarit("poste-AGENTS.md").replace("[UTILISATEUR]", qui),
             os.path.join(hote.maison_copilot(), "copilot-instructions.md"), go, faits, ignores)
        # 1. La racine ne porte qu'un renvoi : la méthode vit dans chaque dépôt
        #    (2.2.2). Deux copies par session — l'une ici par
        #    COPILOT_CUSTOM_INSTRUCTIONS_DIRS, l'autre dans le dépôt — doublaient
        #    les instructions. `nom_de_user` y lit encore le nom de @user.
        pose(_gabarit("atelier-AGENTS.md").replace("[UTILISATEUR]", qui),
             os.path.join(racine, "AGENTS.md"), go, faits, ignores)
        # 2. Le poste du CTO. Son rôle seulement — la méthode, il l'hérite.
        if os.path.exists(os.path.join(cto, "CLAUDE.md")):
            ignores.append("%s existe : ne pas créer AGENTS.md en doublon" % os.path.join(cto, "CLAUDE.md"))
        else:
            racine_abs = os.path.abspath(racine)
            paquet = copilot.paquet_ou_rien() or "introuvable — `harnais diagnostic` le cherche"
            role = (_gabarit("cto-AGENTS.md").replace("[UTILISATEUR]", qui)
                    .replace("[RACINE]", racine_abs).replace("[PAQUET]", paquet))
            pose(role, os.path.join(cto, "AGENTS.md"), go, faits, ignores)
        # 3. Un dépôt git, AVANT le harnais : `adopte` n'en crée pas, et sans lui
        #    les gardes de commit sont inertes — un garde inerte ne dit pas qu'il
        #    l'est.
        if os.path.exists(os.path.join(cto, ".git")):
            ignores.append("Dépôt git déjà présent dans %s" % cto)
        else:
            faits.append("git init dans %s (sans lui, les gardes de commit sont inertes)" % cto)
            if go:
                try:
                    os.makedirs(cto, exist_ok=True)
                except OSError as e:
                    raise Echec("%s : %s" % (cto, e))
                try:
                    o = subprocess.run(["git", "init", "-q", "-b", "main"], cwd=cto,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                except OSError as e:
                    raise Echec("git init : %s" % e)
                if o.returncode != 0:
                    raise Echec("git init : %s" % o.stderr.decode("utf-8", "replace"))
    except Echec as e:
        sys.stderr.write("atelier-monte : %s\n" % e)
        return 1

    _p("Fait :")
    _p("- Rien" if not faits else "\n".join("- %s" % m for m in faits))
    _p()
    _p("Ignorés (non écrasés) :")
    _p("- Aucun" if not ignores else "\n".join("- %s" % m for m in ignores))
    _p()

    # 4. Le harnais sur le poste du CTO : un projet comme un autre, dont le
    #    produit se trouve être l'atelier. `adopte` pose sa mémoire et branche
    #    le paquet — à blanc s'il est à blanc.
    _p("── harnais du CTO (harnais adopte) %s" % ("─" * 30))
    if not os.path.isdir(cto) and not go:
        _p("(le dossier n'existe pas encore : `adopte` le posera à l'écriture)")
    a = [cto]
    if go:
        a.append("--go")
    rc = adopte.main(a) if (os.path.isdir(cto) or go) else 0
    _p("─" * 65)
    _p()

    _p("À faire ensuite :")
    _p("- REMPLIR la mémoire du CTO : le cap dans `brain/fact/base.md`, l'état et ce qui "
       "attend dans `brain/mind/`. Tant qu'ils portent « À REMPLIR », le briefing le dit.")
    _p("- LA RACINE ne porte qu'un renvoi. Le poste (comptes, sessions, réseau, mémoire "
       "vive) va dans ~/.copilot/copilot-instructions.md ; le rôle de chaque agent, dans son "
       "profil ; les règles métier, dans les faits du projet.")
    _p("- La méthode est dans .github/copilot-instructions.md du CTO, comme dans chaque dépôt\n  "
       "adopté : une seule copie par session. Ne pas ajouter %s à\n  "
       "COPILOT_CUSTOM_INSTRUCTIONS_DIRS. Ouvrir une nouvelle session et contrôler /instructions." % racine)
    _p("- LA PREUVE : dans une session ouverte DANS le dossier du CTO, un briefing doit "
       "s'afficher au démarrage. Un hook qu'on n'a pas vu se déclencher n'est pas un hook vérifié.")
    _p("- LA SUITE : pour chaque projet, `harnais adopte` dans son dossier.")
    if rc == 0:
        reg = os.path.join(cto, *REGISTRE.split("/"))
        _p("- Registre CTO : %s (créé seulement s'il est absent)." % reg)
        try:
            pose('{"schema":1,"projects":[]}\n', reg, go, faits, ignores)
            if go:
                accueil(cto)
        except (Echec, RegistreInvalide) as e:
            sys.stderr.write("atelier-monte : %s\n" % e)
            return 1

    if not go:
        _p("\nÀ blanc seulement. Relancer avec --go pour écrire.")
        return rc
    if rc == 0:
        _p("\nL'atelier est en place. Ouvrir une nouvelle session Copilot dans %s : ses réglages\n"
           "déclarent le paquet ; il faut aussi l'installer via la marketplace. AGENTS.md porte le "
           "rôle du CTO." % cto)
    else:
        sys.stderr.write("atelier-monte : montage incomplet ; corriger l'erreur puis relancer --go.\n")
    return rc
