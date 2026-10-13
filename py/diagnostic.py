# -*- coding: utf-8 -*-
"""`harnais diagnostic` — CE QUE JE TROUVE, ET CE QUE JE NE TROUVE PAS.

Port de `harnais/src/diagnostic.rs` (Rust, 0.12.8).

POURQUOI CETTE SOUS-COMMANDE EXISTE. Demandée le 10/09/2026 par l'agent qui
a éprouvé le paquet sur un poste Windows, après avoir conclu FAUX deux fois
— et les deux fois pour la même raison : **le harnais ne fait aucun bruit
quand il autorise**.

  · `memoire` rendait `null` sur un projet parfaitement en forme. C'était le
    comportement juste — ce module ne répond que pour une mémoire déportée —
    mais un `null` qui veut dire « forme en place » et un `null` qui veut
    dire « je n'ai rien trouvé » sont indiscernables dans une sortie muette.
  · une garde a laissé passer trois enregistrements d'affilée. Elle n'était
    pas inerte : sa condition n'était pas réunie. Rien ne le disait.

**Un silence ne prouve rien dans les deux sens.** D'où la règle de cette
sortie : chaque ligne dit ce qui a été CHERCHÉ, ce qui a été TROUVÉ — et
quand rien ne l'a été, POURQUOI. Jamais un blanc.

Elle ne modifie rien, jamais. C'est la seule sous-commande qu'on peut
lancer sur un poste inconnu sans rien risquer.

CE QUI A CHANGÉ AU PORTAGE EN PYTHON (les lignes qui parlaient du programme
natif) : « programme » nomme le point d'entrée Python et on ajoute
« interpréteur » ; « version · source » rend la version du paquet et
l'empreinte de `py/` ; et la section « LE REPLI » n'a plus d'implémentation de
repli à signaler — il n'y a plus qu'une seule implémentation.
"""
import os
import sys

import socle


def dit(quoi, trouve, motif):
    if trouve is not None:
        print("  %-26s %s" % (quoi, trouve))
    else:
        print("  %-26s — %s" % (quoi, motif))


def env_ou(cle):
    v = os.environ.get(cle)
    return v if v else None


def taille(p):
    try:
        n = len(os.listdir(p))
    except OSError:
        return "%s (illisible)" % p
    return "%s (%d entrée(s))" % (p, n)


def _nb_lignes(p):
    """`str::lines().count()` du Rust : un `\\n` final n'ajoute pas de ligne ;
    un fichier illisible ou non UTF-8 en compte 0."""
    try:
        with open(p, "rb") as f:
            t = f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    parts = t.split("\n")
    if parts[-1] == "":
        parts.pop()
    return len(parts)


def _os_rust():
    # `std::env::consts::OS`
    p = sys.platform
    if p == "darwin":
        return "macos"
    if p.startswith("win"):
        return "windows"
    if p.startswith("linux"):
        return "linux"
    return p


def _arch_rust():
    # `std::env::consts::ARCH`
    import platform
    m = platform.machine().lower()
    return {"arm64": "aarch64", "amd64": "x86_64", "x64": "x86_64"}.get(m, m)


def _identite():
    """(version, source) : la version du paquet et l'empreinte de `py/`, comme
    `harnais version` — une seule définition, celle de `main.py`."""
    try:
        import main
        v, _, h = main._identite().partition(" ")
        return v, h
    except Exception:
        return "inconnue", "local"


def main(args):
    depart = args[0] if args else os.getcwd()

    print("\n  QUI TOURNE")
    version, source = _identite()
    print("  %-26s %s %s" % ("version · source", version, source))
    print("  %-26s %s / %s" % ("plateforme", _os_rust(), _arch_rust()))
    ici = os.path.dirname(os.path.abspath(__file__))
    dit("programme", os.path.join(ici, "main.py"),
        "chemin du programme introuvable — cas très rare, à signaler")
    dit("interpréteur", "%s (Python %d.%d.%d)" % (
        sys.executable or "?", sys.version_info[0], sys.version_info[1], sys.version_info[2]),
        "interpréteur introuvable — cas très rare, à signaler")

    # ── LE SHELL, et c'est le point qui décide sur Windows ───────────────────
    # Le lanceur des hooks est du shell POSIX. Confié à `cmd`, il meurt sur une
    # erreur de syntaxe : aucune sortie, aucun hook, aucun mot. C'est la panne
    # la plus vicieuse du dispositif — tout est installé, et rien ne part.
    # Le programme ne peut pas voir qui l'a lancé, mais l'environnement le
    # trahit : un shell POSIX sous Windows pose `MSYSTEM`.
    print("\n  PAR QUEL SHELL")
    msys = env_ou("MSYSTEM")
    gitbash = env_ou("CLAUDE_CODE_GIT_BASH_PATH")
    if sys.platform.startswith("win"):
        dit("shell POSIX (MSYSTEM)", msys,
            "AUCUN SIGNE. Si les hooks ne partent pas, c'est ici qu'il faut regarder : "
            "le lanceur est du shell POSIX et `cmd` ne sait pas le lire.")
        dit("chemin déclaré vers bash", gitbash,
            "non posée. Sur un poste où `Git\\bin` n'est pas dans le PATH, "
            "c'est elle qui dit à l'outil quel shell employer.")
    else:
        dit("shell POSIX", env_ou("SHELL") or "présent", "")
        dit("MSYSTEM", msys, "normal hors Windows")

    # ── LE PAQUET ────────────────────────────────────────────────────────────
    print("\n  LE PAQUET")
    racine_paquet = env_ou("CLAUDE_PLUGIN_ROOT")
    dit("dossier du paquet", racine_paquet,
        "non posé. Le programme tourne donc HORS paquet — appelé à la main, "
        "ou déclaré par des chemins écrits en dur.")
    dit("dossier de données", env_ou("CLAUDE_PLUGIN_DATA"),
        "non posé : l'état retombe sur le dossier personnel, ce qui est le "
        "comportement de repli prévu")
    s = socle.socle()
    dit("où l'état s'écrit", taille(s), "")
    if not os.path.exists(s):
        print("  %-26s — il n'existe pas encore ; il sera créé au premier écrit" % "")
    dit("ce qui est LIVRÉ", socle.livre(),
        "introuvable : les critères de relecture et la liste des rechutes "
        "d'origine ne seront pas lus depuis le paquet")

    # ── CE QUI EST LIVRÉ AVEC LE PAQUET ──────────────────────────────────────
    print("\n  LES FICHIERS QUE LE HARNAIS CHERCHE")
    for nom, rel in (("liste des rechutes", "rechutes.md"),
                     ("critères de relecture", "criteres-relecture.md")):
        ou = [os.path.join(s, rel)]
        l = socle.livre()
        if l is not None:
            ou.append(os.path.join(l, rel))
        trouve = None
        for p in ou:
            if os.path.isfile(p):
                trouve = p
                break
        dit(nom, trouve,
            "cherché à %s — sans lui, la garde qui s'en sert ne mord pas" % " puis ".join(ou))

    # ── LE PROJET ────────────────────────────────────────────────────────────
    print("\n  LE PROJET, VU DEPUIS %s" % depart)

    # ON DEMANDE AU RÉSOLVEUR. Ce module recomposait ses chemins depuis la
    # racine du dépôt sans jamais l'appeler — il annonçait donc « absent » sur
    # un projet à mémoire déportée parfaitement sain. Deux agents l'ont
    # remonté le 10/09/2026, et l'un d'eux a ANNULÉ une bascule juste à cause
    # de cette sortie : le harnais servait son état complet au même instant.
    # Un instrument qui répond à une question plus petite que celle qu'on lui
    # pose coûte plus cher qu'un instrument absent — on lui obéit.
    import memoire
    r = memoire.resous(depart)
    print("  %-26s %s" % ("forme du projet", memoire.forme_mot(r.forme)))
    if r.forme == memoire.Forme.Ambigue:
        print("  %-26s — CE PROJET PORTE LES DEUX ARBRES À LA FOIS. C'est" % "")
        print("  %-26s   l'état qu'une migration interrompue laisse ; rien" % "")
        print("  %-26s   ne sera lu au hasard, mais il faut trancher." % "")
    racine = r.racine
    dit("racine du dépôt", racine,
        "aucun dépôt au-dessus de ce dossier : la plupart des gardes ne "
        "s'appliquent pas, et c'est voulu")
    dit("arbre de travail", r.arbre, "aucun — hors dépôt")
    if r.lot:
        print("  %-26s %s" % ("lot de cet agent", r.lot))
    if racine is not None:
        dit("faits du projet", taille(r.fact) if (r.fact and os.path.isdir(r.fact)) else None,
            "cherché à %s — le projet n'a pas (encore) cette maison"
            % (r.fact if r.fact is not None else "(nulle part : forme d'avant migration)"))
        dit("état de l'agent", taille(r.mind) if (r.mind and os.path.isdir(r.mind)) else None,
            "cherché à %s" % (r.mind if r.mind is not None else "(nulle part)"))
        d = os.path.join(racine, "docs")
        dit("traces datées", taille(d) if os.path.isdir(d) else None,
            "absent — le projet n'a pas (encore) cette maison")
        for nom, f in (("ce qui attend", "todo.md"), ("où on en est", "state.md")):
            p = os.path.join(r.mind, f) if r.mind is not None else None
            dit(nom, ("%d lignes" % _nb_lignes(p)) if (p is not None and os.path.isfile(p)) else None,
                "cherché à %s — la garde de fin de tour le réclamera "
                "dès que du code bougera" % (p if p is not None else "(nulle part)"))
        # LE PIÈGE NOMMÉ : ce module ne répond que pour une mémoire DÉPORTÉE.
        # Un `null` ici ne veut PAS dire « cassé ».
        dit("mémoire déportée", memoire.base(depart),
            "ce projet garde sa mémoire dans son dépôt — c'est la forme la plus "
            "courante, et ce n'est PAS une panne")
        import carnet
        e = carnet.espace(depart, False)
        dit("carnet d'équipe", taille(e) if e is not None else None,
            "aucun : projet à un seul agent, ou équipe jamais amorcée "
            "(`equipe-amorce` le crée)")

    # ── LE REPLI ─────────────────────────────────────────────────────────────
    print("\n  LE REPLI")
    print("  %-26s %s" % ("vous lisez ceci, donc",
                          "le programme répond : il n'y a plus qu'une implémentation, "
                          "sans repli — l'interpréteur Python est la seule condition"))
    print("\n  Rien n'a été modifié.\n")
