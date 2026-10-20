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
_REFUSE = ("mind-guard", "perimetre", "production", "coffre", "sous-agent", "consignes")


def _trop_vieux(sous):
    sys.stderr.write(
        "harnais : Python %d.%d trouve, il faut %d.%d au moins — les gardes du paquet "
        "ne partent pas. Mettre Python a jour (macOS : brew install python · Windows : "
        "winget install Python.Python.3.13).\n" % (sys.version_info[0], sys.version_info[1],
                                                    MINIMUM[0], MINIMUM[1]))
    sys.exit(2 if sous in _REFUSE else 1)


# (module, fonction, façon de l'appeler, préparation de la charge)
#   stdin : la charge JSON du hook, lue sur l'entrée standard, passée en texte
#   args  : la liste des arguments, sans le nom de la sous-commande
#   code  : comme `args`, mais la fonction rend le code de sortie
# Préparation (hooks seulement, voir `hote`) : « agent » résout aussi l'agent
# actif dans le journal de session ; « sans-agent » non (une lecture de faits
# part à chaque lecture) ; « commit » ne le résout que pour un `git commit`.
TABLE = {
    "lecture":       ("poids", "main", "stdin", "sans-agent"),
    "journal":       ("journal", "main", "stdin", "commit"),
    "attente":       ("attente", "main", "stdin", "agent"),
    "briefing":      ("briefing", "main", "stdin", "agent"),
    "mind-guard":    ("mind_guard", "main", "stdin", "commit"),
    "perimetre":     ("copilot", "garde", "stdin", "agent"),
    "production":    ("production", "main", "stdin", "agent"),
    "laissez-passer": ("production", "laissez_passer", "code", None),
    "coffre":        ("coffre", "main", "stdin", "sans-agent"),
    "coffre-temoin": ("coffre", "temoin", "stdin", "sans-agent"),
    "consignes":     ("consignes", "main", "stdin", "agent"),
    "sous-agent":    ("sous_agent", "main", "stdin", "sans-agent"),
    "laissez-passer-lot": ("sous_agent", "laissez_passer", "code", None),
    "carnet":        ("carnet", "main", "args", None),
    "carnet-essai":  ("carnet", "essai", "args", None),
    "equipe-amorce": ("carnet", "amorce_cli", "code", None),
    "memoire":       ("memoire", "main", "args", None),
    "resolution":    ("memoire", "resolution_json", "code", None),
    "todo-blocs":    ("attente", "todo_blocs", "code", None),
    "curateur":      ("poids", "curateur", "code", None),
    "relecture":     ("relecture", "main", "args", None),
    "diagnostic":    ("diagnostic", "main", "args", None),
    "agent":         ("agent", "main", "code", None),
    "adopte":        ("adopte", "main", "code", None),
    "menage":        ("menage", "main", "code", None),
    "atelier-monte": ("atelier", "main", "code", None),
    "equipe":        ("equipe", "main", "code", None),
    "equipe-vue":    ("vue", "main", "code", None),
    "brain-migre":   ("migration", "main", "code", None),
    "mise-a-niveau": ("niveau", "main", "code", None),
    "demenage":      ("demenage", "main", "code", None),
}

# Les hooks que `HARNAIS_JUGE` fait taire : le juge lancé par `copilot -p`
# déclencherait sinon les hooks du harnais, en boucle.
_JUGE_MUET = ("briefing", "attente", "mind-guard", "perimetre", "journal", "lecture",
              "apres-bash", "apres-lecture", "production", "coffre", "coffre-temoin", "sous-agent", "consignes")

AIDE = """harnais — le socle agentique

POSER LE HARNAIS SUR UN PROJET — le seul geste à connaître pour démarrer :
  adopte       pose la mémoire du projet et branche le paquet.
               `--go` pour écrire · `--equipe A,B,C [--modeles ops,po,qa] [--code D]` :
               une équipe neuve, un dossier par agent
  brain-migre  déplace une mémoire de l'ancienne organisation vers `brain/`
  mise-a-niveau  amène un projet à la forme actuelle, mono ou équipe : mémoire en `brain/`,
               droits réécrits, faits manquants, `outputs/` -> `assets/` ; sans rien perdre
               à blanc par défaut · `--apply [--agents-arretes]` · `--atelier --racine R`
               dit, pour chaque projet de l'atelier, ce qu'il faudrait faire
  demenage     passe une équipe « dossier d'avant » (`brain/` + `agents/<nom>/`) à « un dossier
               par agent » : code, copies, mémoire, droits ; la forme compacte est nommée, pas touchée
               à blanc par défaut · `--apply --agents-arretes` · `--copie NOM=CHEMIN`
  equipe-vue   l'état de tous les projets d'un atelier — terminal ou `--html`
  equipe       passe un projet en équipe, ou lui ajoute un agent
               `--agents A,B` · `--retire A` · à blanc par défaut · `--apply`
  atelier-monte  la méthode à la racine, puis le poste du CTO et son harnais
               à blanc par défaut · `--go` · `--racine R --utilisateur P`
  menage       caches à supprimer, résidus et mémoires trop grosses à signaler
               à blanc par défaut · `--apply` · `--racine R` pour un atelier

À LA MAIN, pour comprendre ce que je vois :
  curateur     la confiance des sections de faits (brain/poids.json), lecture seule
  resolution   où vit la mémoire de ce dossier (JSON complet)
  memoire      la même, restreinte — sert à comparer deux versions
  version      la version du paquet, et l'état du code qui l'a produite
  laissez-passer-lot  « <le oui de l'humain> » — laisse partir, 120 min, les sous-agents
               qui lisent du visuel depuis cette copie, par lots de 30 au plus ; journalisé
  laissez-passer  « <le oui de l'humain> » — ouvre la Production à l'agent nommé dans
               les règles, pour la durée réglée ; journalisé. `--session <id>` si le
               shell est lancé à la racine d'une copie (le journal dit qui parle)

APPELÉES PAR LE HARNAIS (chacune lit sa charge JSON sur l'entrée standard) :
  journal      PostToolUse/Bash — écrit ce qui a été commité
  lecture      PostToolUse/Read|Bash — note les sections de faits lues
  apres-bash   PostToolUse/Bash — `journal`, `lecture` puis `coffre-temoin`, en UN processus
  attente   Stop — ce qui attend @user, et les gardes
  briefing  SessionStart/userPromptTransformed — le briefing d'entrée
  carnet    lecture du carnet d'équipe (JSON, pour comparer)
  equipe-amorce  crée le carnet d'équipe — appelé UNE fois, à la conversion
  mind-guard PreToolUse/Bash — garde les faits et la déclaration d'état
  perimetre   PreToolUse/Edit|Write — refuse les écritures hors lot
  production  PreToolUse/Bash — rien ne part en Production sans laissez-passer
  coffre      PreToolUse/Bash, Read, Grep — aucun outil n'affiche une valeur de secret
  coffre-temoin  PostToolUse — une clé de forme connue passée en clair se signale
  consignes   PreToolUse/Edit|Write|Bash — seuls les gardiens (le CTO) écrivent AGENTS.md,
              CLAUDE.md et copilot-instructions.md
  sous-agent  PreToolUse/Task — pas de sous-agent qui lit des images ou un lot de plus de
              30 médias sans l'accord de l'humain
  apres-lecture  PostToolUse/Read|Grep — `lecture` puis `coffre-temoin`, en UN processus
  relecture    lance le juge sur les demandes en attente
  diagnostic   ce que je trouve, ce que je ne trouve pas, et par quel shell
  agent        l'agent actif d'une session : journal lu, règle appliquée (lecture seule)
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
        with open(os.path.join(racine, ".github", "plugin", "plugin.json"), encoding="utf-8") as f:
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


def _enchaine(nom, gestes):
    """Plusieurs gestes d'après-outil sur la MÊME charge, en un seul processus.

    Après chaque commande shell, trois hooks partaient : trois démarrages de
    Python, et sous Windows chacun se paie (antivirus, disque). Les gestes
    restent indépendants : la panne de l'un n'empêche pas les autres, et
    chacune se dit sur la sortie d'erreur, comme seule.

    `gestes` : [(module, fonction, préparation de la charge)].
    """
    try:
        texte = sys.stdin.read()
    except (OSError, UnicodeDecodeError):
        texte = ""
    import hote
    code = 0
    for nom_module, nom_fonction, prep in gestes:
        try:
            getattr(__import__(nom_module), nom_fonction)(getattr(hote, prep)(texte))
        except SystemExit:
            raise
        except Exception as e:      # noqa — les autres gestes partent quand même
            sys.stderr.write("harnais : erreur interne dans « %s » (%s) — %s: %s\n"
                             % (nom, nom_module, type(e).__name__, e))
            code = 1
    return code


def _apres_bash():
    """`journal`, `lecture`, puis le témoin du coffre, sur la même charge."""
    return _enchaine("apres-bash", [("journal", "main", "prepare_si_commit"),
                                    ("poids", "main", "prepare_sans_agent"),
                                    ("coffre", "temoin", "prepare_sans_agent")])


def _apres_lecture():
    """`lecture`, puis le témoin du coffre, après un `Read` ou un `Grep`."""
    return _enchaine("apres-lecture", [("poids", "main", "prepare_sans_agent"),
                                       ("coffre", "temoin", "prepare_sans_agent")])


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
    if sous in ("apres-bash", "apres-lecture"):
        import os
        if os.environ.get("HARNAIS_JUGE"):
            return 0
        return _apres_bash() if sous == "apres-bash" else _apres_lecture()
    cible = TABLE.get(sous)
    if cible is None:
        # On le DIT, et le code est 1 : sous Copilot un hook mal câblé se voit
        # comme une panne de hook, il n'arrête pas l'agent.
        sys.stderr.write("harnais : sous-commande inconnue « %s »\n" % sous)
        return 1
    import os
    if os.environ.get("HARNAIS_JUGE") and sous in _JUGE_MUET:
        return 0
    nom_module, nom_fonction, facon, prep = cible
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
            import hote
            if prep == "agent":
                texte = hote.prepare(texte)
            elif prep == "sans-agent":
                texte = hote.prepare_sans_agent(texte)
            elif prep == "commit":
                texte = hote.prepare_si_commit(texte)
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
        if sous == "perimetre":
            # LA SEULE GARDE FERMÉE DANS LE DOUTE : une panne refuse l'écriture,
            # et le dit — comme une charge illisible.
            import hote
            sys.stdout.write(hote.refus("garde de périmètre en panne (%s: %s) : écriture refusée"
                                        % (type(e).__name__, e)) + "\n")
            return 0
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
