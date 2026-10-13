# -*- coding: utf-8 -*-
"""LE POINT D'ENTRÉE — `harnais <sous-commande>`, le même contrat que le programme d'avant.

Ce fichier doit rester LISIBLE par un Python ancien (pas de `match`, pas de
`X | Y` dans les annotations) : sa première tâche est de dire « trop vieux »
plutôt que de mourir sur une erreur de syntaxe que rien n'explique.

Les modules se chargent À LA DEMANDE. Un hook qui sort tôt (la plupart des
commandes Bash n'ont rien à garder) ne doit jamais payer l'import d'un module
qu'il n'utilisera pas : Python démarre en 14 ms, chaque import en ajoute.
"""
import sys

MINIMUM = (3, 9)
# Les hooks qui REFUSENT quand ils sont absents rendent 2 ; tous les autres 1.
_REFUSE = ("mind-guard",)


def _trop_vieux(sous):
    sys.stderr.write(
        "harnais : Python %d.%d trouve, il faut %d.%d au moins — les gardes du paquet "
        "ne partent pas. Mettre Python a jour (macOS : brew install python · Windows : "
        "winget install Python.Python.3.13).\n" % (sys.version_info[0], sys.version_info[1],
                                                    MINIMUM[0], MINIMUM[1]))
    sys.exit(2 if sous in _REFUSE else 1)


# (module, fonction, façon de l'appeler)
#   stdin : la charge JSON du hook, lue sur l'entrée standard, passée en texte
#   args  : la liste des arguments, sans le nom de la sous-commande
#   code  : comme `args`, mais la fonction rend le code de sortie
TABLE = {
    "usage":         ("usage", "main", "stdin"),
    "refus-auto":    ("refus_auto", "main", "stdin"),
    "journal":       ("journal", "main", "stdin"),
    "attente":       ("attente", "main", "stdin"),
    "briefing":      ("briefing", "main", "stdin"),
    "mind-guard":    ("mind_guard", "main", "stdin"),
    "carnet":        ("carnet", "main", "args"),
    "carnet-essai":  ("carnet", "essai", "args"),
    "equipe-amorce": ("carnet", "amorce_cli", "code"),
    "memoire":       ("memoire", "main", "args"),
    "resolution":    ("memoire", "resolution_json", "code"),
    "todo-blocs":    ("attente", "todo_blocs", "code"),
    "curateur":      ("curateur", "main", "code"),
    "relecture":     ("relecture", "main", "args"),
    "diagnostic":    ("diagnostic", "main", "args"),
    "adopte":        ("adopte", "main", "code"),
    "menage":        ("menage", "main", "code"),
    "atelier-monte": ("atelier", "main", "code"),
    "equipe":        ("equipe", "main", "code"),
    "equipe-vue":    ("vue", "main", "code"),
    "brain-migre":   ("migration", "main", "code"),
    "bascule":       ("bascule", "main", "code"),
}

AIDE = """harnais — le socle agentique

POSER LE HARNAIS SUR UN PROJET — le seul geste à connaître pour démarrer :
  adopte       pose la mémoire du projet et branche le paquet.
               `--go` pour écrire · `--equipe A,B,C` à plusieurs
  brain-migre  déplace une mémoire de l'ancienne organisation vers `brain/`
  equipe-vue   l'état de tous les projets d'un atelier — terminal ou `--html`
  equipe       passe un projet en équipe, ou lui ajoute un agent
               `--agents A,B` · à blanc par défaut · `--apply`
  atelier-monte  la méthode à la racine, puis le poste du CTO et son harnais
               à blanc par défaut · `--go` · `--racine R --utilisateur P`
  menage       caches à supprimer, résidus et mémoires trop grosses à signaler
               à blanc par défaut · `--apply` · `--racine R` pour un atelier

À LA MAIN, pour comprendre ce que je vois :
  curateur     la mémoire auto de ce projet : ce qui sert, ce qui dort,
               ce qu'un résultat a démenti · `--appliquer` pour ranger
  resolution   où vit la mémoire de ce dossier (JSON complet)
  memoire      la même, restreinte — sert à comparer deux versions
  bascule      bascule un projet d'un canal de hooks à l'autre
  version      la version du paquet, et l'état du code qui l'a produite

APPELÉES PAR LE HARNAIS (chacune lit sa charge JSON sur l'entrée standard) :
  usage        PostToolUse/Read — note qu'une note de mémoire a servi
  refus-auto   PermissionDenied — note qu'un geste a été refusé par le mode auto
  journal      PostToolUse/Bash — écrit ce qui a été commité
  attente   Stop — ce qui attend le commanditaire, et les gardes
  briefing  SessionStart/UserPromptSubmit — le briefing d'entrée
  carnet    lecture du carnet d'équipe (JSON, pour comparer)
  equipe-amorce  crée le carnet d'équipe — appelé UNE fois, à la conversion
  mind-guard PreToolUse/Bash — garde les faits du projet et la déclaration d'état
  relecture    lance le juge sur les demandes en attente
  diagnostic   ce que je trouve, ce que je ne trouve pas, et par quel shell
  carnet-essai un banc du carnet, pour les contrôles
  todo-blocs   les blocs du todo tels que la fin de tour les lit (JSON)
"""


def _flux_utf8():
    # Windows écrit en cp1252 par défaut : un « é » du briefing deviendrait autre
    # chose, ou lèverait une erreur dans un hook. Les trois flux, en UTF-8.
    for f in (sys.stdin, sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _identite():
    """`version` : <version du paquet> <empreinte du code qui tourne>.

    L'empreinte est celle des fichiers de `py/`, calculée ICI, à l'appel : un
    paquet périmé par rapport à son source ne peut plus se faire passer pour lui.
    """
    import hashlib
    import json
    import os
    ici = os.path.dirname(os.path.abspath(__file__))
    racine = os.path.dirname(ici)
    version = "inconnue"
    try:
        with open(os.path.join(racine, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            version = json.load(f).get("version", version)
    except (OSError, ValueError):
        pass
    h = hashlib.sha1()
    for nom in sorted(os.listdir(ici)):
        if nom.endswith(".py"):
            h.update(nom.encode("utf-8") + b"\0")
            with open(os.path.join(ici, nom), "rb") as f:
                h.update(f.read())
    return "%s %s" % (version, h.hexdigest()[:12])


def main(argv):
    sous = argv[0] if argv else ""
    if sys.version_info < MINIMUM:
        _trop_vieux(sous)
    _flux_utf8()
    if sous in ("version", "--version", "-V"):
        print(_identite())
        return 0
    if sous in ("", "-h", "--help", "aide"):
        sys.stdout.write(AIDE)
        return 0
    cible = TABLE.get(sous)
    if cible is None:
        # On le DIT, mais on ne bloque pas : un hook mal câblé ne doit pas
        # arrêter l'agent, il doit se voir dans le journal de débogage.
        sys.stderr.write("harnais : sous-commande inconnue « %s »\n" % sous)
        return 0
    nom_module, nom_fonction, facon = cible
    # Le dossier de ce fichier est déjà en tête de sys.path (c'est le script) :
    # `import usage` trouve py/usage.py, sans paquet ni installation.
    try:
        module = __import__(nom_module)
        fonction = getattr(module, nom_fonction)
        if facon == "stdin":
            try:
                texte = sys.stdin.read()
            except (OSError, UnicodeDecodeError):
                texte = ""
            rendu = fonction(texte)
        else:
            rendu = fonction(argv[1:])
    except SystemExit:
        raise
    except Exception as e:      # noqa — un hook ne doit jamais mourir en silence
        # Ni muet (un garde qui plante ressemble à un garde qui laisse passer),
        # ni bloquant (code 1 : l'erreur se voit, la commande de l'agent passe).
        import traceback
        ou = traceback.extract_tb(e.__traceback__)[-1]
        sys.stderr.write("harnais : erreur interne dans « %s » — %s: %s (%s:%s). "
                         "Le garde n'a pas jugé.\n" % (sous, type(e).__name__, e,
                                                      ou.filename.rsplit("/", 1)[-1], ou.lineno))
        return 1
    return rendu if (facon == "code" and isinstance(rendu, int)) else 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BrokenPipeError:
        # `harnais ... | head` : le lecteur est parti, ce n'est pas une panne.
        sys.exit(0)
