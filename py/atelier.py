# -*- coding: utf-8 -*-
"""MONTER UN ATELIER sur une machine neuve — pas un projet, la couche au-dessus.

Port de `harnais/src/atelier.rs` (Rust, 0.12.8) ; le Rust gagne.

    <racine>/CLAUDE.md      la MÉTHODE, héritée par tout agent d'un sous-dossier
    <racine>/<cto>/         le poste du CTO, harnais posé, dépôt git

REMPLACE `agentic-init.py` LE 11/09/2026, ET CE N'EST PAS UN PORTAGE. Le
script ne tournait plus nulle part : il exigeait d'être lancé depuis un
clone du starter et déléguait à `agentic-upgrade.py`, retiré depuis que
`harnais adopte` pose un projet en un geste. Livré par le paquet, il
s'arrêtait à la première ligne (« Ce script doit vivre dans un clone du
starter »). On garde donc ce qu'il FAISAIT — deux fichiers de rôle, puis
le harnais sur le poste du CTO — et on délègue la seconde moitié à
`adopte`, au lieu d'en écrire une seconde copie.

POURQUOI LE SOCLE NE « PRÉVAUT » PAS. Un `CLAUDE.md` parent n'écrase pas
celui d'un projet : les deux sont lus, le plus précis l'emporte. Le socle
porte l'invariant, le projet ajoute son rôle par-dessus.

**À blanc par défaut.** `--go` pour écrire. Rien n'est jamais écrasé.

DIVERGENCE CONNUE avec le Rust : les gabarits ne sont plus COMPILÉS dans le
programme (`include_str!`), ils se lisent à l'appel dans `skills/agentic-init/
templates/` du paquet, à côté de `py/`.
"""
import os
import sys

import adopte


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
    maison = os.environ.get("HOME")
    if maison is None:
        maison = os.environ.get("USERPROFILE")
    if p == "~" and maison is not None:
        return maison
    if p.startswith("~/") and maison is not None:
        return os.path.join(maison, p[2:])
    return p


def pose(texte, dst, go, faits, ignores):
    """Pose un gabarit, jamais par-dessus un fichier existant. Rend ce qui a été
    fait ou ignoré, pour le rapport."""
    if os.path.exists(dst):
        ignores.append("Existe déjà, non écrasé : %s" % dst)
        return
    faits.append("Créer %s" % dst)
    if go:
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
        except OSError:
            pass
        try:
            with open(dst, "w", encoding="utf-8", newline="") as f:
                f.write(texte)
        except OSError:
            pass


def _p(s=""):
    sys.stdout.write(s + "\n")


def main(args):
    if any(a == "-h" or a == "--help" for a in args):
        _p("harnais atelier-monte [--racine R] [--cto NOM] [--utilisateur PRÉNOM] [--go]\n\n"
           "Monte un atelier : la méthode à la racine, le poste du CTO avec son rôle et le\n"
           "harnais. À blanc par défaut ; `--go` écrit. Rien n'est jamais écrasé.")
        return 0
    go = any(a == "--go" or a == "--apply" for a in args)
    racine = valeur(args, "--racine")
    if racine is None:
        racine = "~/Agentic"
    racine = developpe(racine)
    nom_cto = valeur(args, "--cto")
    if nom_cto is None:
        nom_cto = "cto"
    qui = valeur(args, "--utilisateur")
    qui = qui.strip() if qui is not None else ""
    if not qui:
        qui = "l'utilisateur"
    cto = os.path.join(racine, nom_cto)

    _p("Atelier — montage")
    _p("Racine      : %s" % racine)
    _p("CTO         : %s" % cto)
    _p("Mode        : %s" % ("ÉCRITURE" if go else "À BLANC"))
    _p()

    faits, ignores = [], []
    if not os.path.exists(racine):
        faits.append("Créer la racine %s" % racine)
        if go:
            try:
                os.makedirs(racine, exist_ok=True)
            except OSError:
                pass
    # 1. La MÉTHODE, à la racine. C'est l'artefact portable.
    pose(_gabarit("foundation-CLAUDE.md"), os.path.join(racine, "CLAUDE.md"), go, faits, ignores)
    # 2. Le poste du CTO. Son rôle seulement — la méthode, il l'hérite.
    pose(_gabarit("cto-CLAUDE.md").replace("[UTILISATEUR]", qui),
         os.path.join(cto, "CLAUDE.md"), go, faits, ignores)
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
            except OSError:
                pass
            import subprocess
            try:
                subprocess.run(["git", "init", "-q", "-b", "main"], cwd=cto,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except OSError:
                pass

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
    if os.path.isdir(cto) or go:
        if go:
            try:
                os.makedirs(cto, exist_ok=True)
            except OSError:
                pass
        rc = adopte.main(a)
    else:
        rc = 0
    _p("─" * 65)
    _p()

    _p("À faire ensuite :")
    _p("- REMPLIR la mémoire du CTO : le cap dans `brain/fact/base.md`, l'état et ce qui "
       "attend dans `brain/mind/`. Tant qu'ils portent « À REMPLIR », le briefing le dit.")
    _p("- LE SOCLE de la racine ne porte QUE la méthode. Le poste (comptes, sessions, "
       "réseau, mémoire vive) va dans ~/.claude/CLAUDE.md ; le rôle et les règles métier, dans le "
       "CLAUDE.md de chaque projet.")
    _p("- LA PREUVE : dans une session ouverte DANS le dossier du CTO, un briefing doit "
       "s'afficher au démarrage. Un hook qu'on n'a pas vu se déclencher n'est pas un hook vérifié.")
    _p("- LA SUITE : pour chaque projet, `harnais adopte` dans son dossier.")

    if not go:
        _p("\nÀ blanc seulement. Relancer avec --go pour écrire.")
        return rc
    # La passe-main. Elle vient EN DERNIER et se voit : la mémoire auto d'un
    # agent est indexée sur le CHEMIN de travail, donc tout ce qui
    # s'apprendrait depuis la racine serait rangé sous une clé que le CTO
    # n'ouvrira jamais.
    barre = "─" * 72
    # Les lignes se suivent SANS indentation : en Rust, `\` en fin de ligne d'un
    # littéral avale aussi les espaces de la ligne suivante (mesuré contre le binaire).
    _p("\n%s\n  L'ATELIER EST EN PLACE. CETTE SESSION N'A PLUS D'OBJET.\n\n"
       "Avant de la fermer, remplir la mémoire de `%s` : cette session est la seule\n"
       "à savoir ce qui vient d'être monté.\n\n"
       "Puis OUVRIR UNE NOUVELLE SESSION DANS :\n      %s\n\n"
       "Pourquoi changer de dossier, et pas continuer ici :\n"
       "· le paquet est activé dans SES réglages — ici ses hooks sont inertes ;\n"
       "· son CLAUDE.md porte le rôle du CTO — ici on ne lit que la méthode ;\n"
       "· la mémoire auto est indexée sur le CHEMIN, et ne se déplace pas.\n\n"
       "C'est de là que se montent les projets, un par un.\n%s" % (barre, nom_cto, cto, barre))
    return rc
