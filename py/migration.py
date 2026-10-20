# -*- coding: utf-8 -*-
"""`harnais brain-migre` — DÉPLACER LA MÉMOIRE VERS `brain/`, ET POUVOIR REVENIR.

Port de `harnais/src/migration.rs` (Rust, 0.12.8) ; le Rust gagne.

POURQUOI UNE SOUS-COMMANDE ET PAS UN SCRIPT. La règle qui place ces dossiers
vit dans `memoire`. Un script séparé en serait une seconde copie, et la
maison a déjà payé ce prix : `carnet.amorce()` existe précisément pour que
la compétence qui monte une équipe n'ait pas à recopier `espace()`. Le
précédent exact est `equipe-amorce` — une sous-commande qui écrit, appelée
une fois. Et sur les neuf compétences de l'atelier, **aucune** n'importe le
résolveur : une dixième qui ne l'importerait pas non plus serait le défaut
reconduit. Une sous-commande, elle, EST le résolveur.

CE QU'IL FAIT, ET RIEN D'AUTRE :

    .fact/            -> brain/fact/
    .mind/            -> brain/mind/                (mono)
    memoire/.fact/    -> brain/fact/                (déportée)
    memoire/agents/<nom>/.mind/ -> brain/mind/<nom>/
    memoire/equipe/   -> brain/workspace/

`docs/` et `.logs/` NE BOUGENT PAS : ils sont datés, ils racontent le code,
et les en arracher couperait chaque trace du commit qui l'explique.

**À BLANC PAR DÉFAUT.** Sans `--apply`, il annonce et n'écrit rien — et le
témoin de ce contrat est qu'après un passage à blanc, l'arbre cible n'existe
toujours pas. « Le blanc a écrit » est un contrôle raté, pas un détail.

**`git mv` D'ABORD, ET IL DIT LEQUEL IL A PRIS.** Le précédent de la maison
(`migre-fact-docs.py`) retombait sur un déplacement nu sans jamais dire
lequel des deux chemins il avait emprunté. Un `git mv` qui échoue pour une
bonne raison — fichier non suivi — et un `git mv` qui échoue parce que
l'index est sale se lisent pareil, et le second perd l'historique en
silence. Ici chaque ligne porte son verdict.
"""
import os
import sys

import memoire
import socle
from memoire import Forme

V = "\x1b[32m"
R = "\x1b[31m"
J = "\x1b[33m"
D = "\x1b[2m"
X = "\x1b[0m"

# Les noms que `fact/` a le droit de porter. Le cinquième n'existe qu'en
# équipe. **C'est ici que le plafond mord pour la première fois** : il vivait
# en prose depuis le début et n'était vérifié nulle part — mesuré le
# 10/09/2026, aucun `read_dir` du programme ne portait sur ces dossiers.
# Voir `socle.FAITS_MONO`. La migration n'exige PAS `roles.md` : il n'existe
# qu'à plusieurs agents. Ce découpage est voulu — ce qui ne l'était pas, c'est
# qu'il vive dans une troisième copie de la liste (audit P5).
NOMS_FACT = socle.FAITS_MONO
NOM_FACT_EQUIPE = socle.FAITS_EQUIPE


def _p(s=""):
    sys.stdout.write(s + "\n")


def _oserr(e):
    """Le texte d'une erreur d'E/S comme le Rust l'écrit : `<message> (os error N)`."""
    if getattr(e, "errno", None):
        return "%s (os error %d)" % (os.strerror(e.errno), e.errno)
    return str(e)


# ── chemins : la sémantique de `std::path` ──────────────────────────────────

def _composants(p):
    """(racine, composants) — la racine est "" (relatif), "/" ou, sous Windows,
    le lecteur ("C:/"). Sous Windows `\\` vaut `/` : sans cela un chemin entier
    n'est qu'UN composant, et rien n'est jamais « sous » le projet (mesuré par
    la CI Windows : ménage aveugle, migration refusée)."""
    if os.name == "nt":
        p = p.replace("\\", "/")
        if p.startswith("//?/"):
            p = p[4:]
        if len(p) >= 2 and p[1] == ":" and p[0].isalpha():
            return p[0].upper() + ":/", [c for c in p[2:].split("/") if c not in ("", ".")]
    return ("/" if p.startswith("/") else ""), [c for c in p.split("/") if c not in ("", ".")]


def strip_prefix(p, base):
    """`Path::strip_prefix` : le reste (en `/`), ou None. Comparaison par COMPOSANTS."""
    rp, cp = _composants(p)
    rb, cb = _composants(base)
    if rp != rb or cp[:len(cb)] != cb:
        return None
    return "/".join(cp[len(cb):])


def starts_with(p, base):
    return strip_prefix(p, base) is not None


def parent(p):
    """`Path::parent` : None pour la racine ou un chemin vide."""
    rp, cp = _composants(p)
    if not cp:
        return None
    if len(cp) == 1:
        return rp
    return rp + "/".join(cp[:-1])


def sans_prefixe(p, base):
    """`p.strip_prefix(base).unwrap_or(p)`, rendu comme `display()`."""
    r = strip_prefix(p, base)
    return p if r is None else r


def egaux(a, b):
    """Égalité de chemins par composants (`PathBuf == PathBuf`)."""
    return _composants(a) == _composants(b)


def lignes(s):
    """`str::lines` de Rust : coupe sur `\\n`, ôte un `\\r` AVANT un `\\n`, rien d'autre
    (`splitlines` de Python couperait aussi sur \\x0b, \\x1c, \\u2028…)."""
    if not s:
        return []
    parts = s.split("\n")
    if parts[-1] == "":
        parts.pop()
        return [x[:-1] if x.endswith("\r") else x for x in parts]
    return [x[:-1] if (x.endswith("\r") and i < len(parts) - 1) else x for i, x in enumerate(parts)]


class Geste(object):
    def __init__(self, de, vers):
        self.de = de
        self.vers = vers
        # Rempli à l'exécution : `git mv` ou `rename`. Jamais supposé.
        self.comment = ""


def raison(stderr):
    """La raison d'un échec de git, lue sur sa sortie d'erreur SANS ses avertissements.
    Git for Windows (autocrlf=true par défaut) écrit « warning: in the working copy of
    '…', LF will be replaced by CRLF… » en tête, une ligne par fichier : tronqué à
    quelques centaines de caractères, un message d'échec ne montrait QUE cela, et la
    vraie raison (`fatal: …`) disparaissait. Si rien d'autre n'est dit, on rend tout."""
    brut = [l.rstrip("\r") for l in (stderr or "").split("\n") if l.strip()]
    utiles = [l for l in brut if not l.lstrip().lower().startswith("warning:")]
    return "\n".join(utiles or brut).strip()


def git(ou, args):
    """`(code, sortie)`. La sortie est la sortie STANDARD : c'est elle seule qui sert de
    verdict (`status --porcelain` vide = propre). La sortie d'erreur n'est lue que
    pour dire POURQUOI git a échoué, et jamais mêlée à un verdict qui a réussi."""
    import subprocess
    try:
        r = subprocess.run(["git"] + list(args), cwd=ou, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, ValueError):
        return -1, ""
    rc = r.returncode if r.returncode >= 0 else -1
    out = r.stdout.decode("utf-8", "replace").strip()
    if rc != 0 and not out:
        # Un échec dit pourquoi : git écrit sa raison sur la sortie d'erreur, et un
        # « PAS enregistré : » sans suite ne se répare pas (CI Windows de Claude, 16/10/2026).
        out = raison(r.stderr.decode("utf-8", "replace"))
    return rc, out


def identite_de_commit(depot):
    """Les options `-c` qui donnent une identité à un commit quand git n'en a AUCUNE
    (un PC neuf, un poste jetable) : sans elle `git commit` s'arrête sur « Author identity
    unknown ». Une identité configurée n'est jamais remplacée. Git for Windows ne devine
    pas l'adresse comme macOS : ce défaut n'apparaissait que là."""
    for qui in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        rc, _ = git(depot, ["var", qui])
        if rc != 0:
            return ["-c", "user.name=harnais", "-c", "user.email=harnais@atelier"]
    return []


def propre(depot):
    rc, out = git(depot, ["status", "--porcelain"])
    return rc == 0 and out == ""


def depot_porteur(p, racine):
    """Le dépôt qui porte réellement ce dossier — le sien s'il en a un, sinon celui
    du dessus. C'est lui qu'il faut interroger pour un `git mv`."""
    q = p
    while True:
        if os.path.exists(os.path.join(q, ".git")):
            return q
        x = parent(q)
        if x is not None and (starts_with(x, racine) or egaux(x, racine)):
            q = x
        else:
            return racine


def _entrees_triees(d):
    try:
        return [os.path.join(d, n) for n in sorted(os.listdir(d))]
    except OSError:
        return []


def _nom(p):
    n = os.path.basename(p.rstrip("/"))
    return n


def gestes(r, racine):
    """Ce qui doit bouger, et vers où. Rien n'est écrit ici. Rend `(liste, None)`
    ou `(None, message)`."""
    j = os.path.join
    brain = j(racine, "brain")
    v = []
    if r.forme == Forme.EnPlace:
        p = r.projet
        if p is None:
            return None, "aucun dossier de projet"
        v.append(Geste(j(p, ".fact"), j(brain, "fact")))
        # Le `.mind/` de CHAQUE agent, pas seulement celui qui parle : la
        # migration est un geste de PROJET. Le lot de l'appelant ne doit
        # pas décider de ce qui bouge.
        ag = j(p, "agents")
        trouve = False
        if os.path.isdir(ag):
            for a in _entrees_triees(ag):
                if os.path.isdir(j(a, ".mind")):
                    v.append(Geste(j(a, ".mind"), j(brain, "mind", _nom(a))))
                    trouve = True
        if not trouve and os.path.isdir(j(p, ".mind")):
            v.append(Geste(j(p, ".mind"), j(brain, "mind")))
    elif r.forme == Forme.Deportee:
        b = memoire.base(racine)
        if b is None:
            return None, "mémoire déportée introuvable"
        v.append(Geste(j(b, ".fact"), j(brain, "fact")))
        ag = j(b, "agents")
        if os.path.isdir(ag):
            for a in _entrees_triees(ag):
                if os.path.isdir(j(a, ".mind")):
                    v.append(Geste(j(a, ".mind"), j(brain, "mind", _nom(a))))
        elif os.path.isdir(j(b, ".mind")):
            v.append(Geste(j(b, ".mind"), j(brain, "mind")))
        if os.path.isdir(j(b, "equipe")):
            v.append(Geste(j(b, "equipe"), j(brain, "workspace")))
    elif r.forme == Forme.Brain:
        return None, "déjà en brain/"
    elif r.forme == Forme.Ambigue:
        return None, ("cet arbre porte l'ANCIEN et le NEUF à la fois — un chantier "
                      "interrompu. Trancher à la main avant de rejouer.")
    else:
        return None, "ce dossier n'a pas de mémoire à déplacer"
    return v, None


def avant(r, racine, v):
    """LES ASSERTIONS D'AVANT. Elles refusent, et ne touchent à rien."""
    e = []
    j = os.path.join
    brain = j(racine, "brain")

    # ① L'arbre cible ne doit pas exister — c'est l'état « à moitié migré ».
    if os.path.exists(brain):
        e.append("`%s` existe déjà : soit la migration est faite, soit "
                 "elle a été interrompue. Rien ne sera écrit par-dessus." % brain)

    # ② LE PLAFOND, ET C'EST ICI QU'IL MORD POUR LA PREMIÈRE FOIS.
    f = r.fact
    if f is not None and os.path.isdir(f):
        equipe = r.workspace is not None or (r.projet is not None and os.path.isdir(j(r.projet, "agents")))
        attendus = list(NOMS_FACT)
        if equipe:
            attendus.append(NOM_FACT_EQUIPE)
        try:
            vus = [n for n in os.listdir(f) if n.endswith(".md")]
        except OSError:
            vus = []
        # `workflow.md` est AUTORISÉ, pas exigé (Claude 0.17.0) : commun à tous
        # depuis le 12/10/2026, il faisait refuser un projet comme « un fichier de trop ».
        autorises = attendus + list(socle.FAITS_COMMUNS)
        for n in vus:
            if n not in autorises:
                e.append("`%s` porte `%s`, qui n'est pas un des %d noms "
                         "attendus. Un fichier de trop dans les faits "
                         "n'a jamais été vérifié nulle part : c'est ici "
                         "qu'on s'en aperçoit, AVANT de le déplacer." % (f, n, len(attendus)))
        for n in attendus:
            if n not in vus:
                e.append("`%s` manque dans `%s`" % (n, f))

    # ③ RIEN EN ATTENTE **SUR CE QUI BOUGE**. Migrer par-dessus du travail non
    # enregistré rend le retour impossible — mais la question ne porte que sur
    # les dossiers déplacés.
    #
    # LA PREMIÈRE VERSION EXIGEAIT UN ARBRE ENTIÈREMENT PROPRE, et elle a
    # refusé le premier projet réel qu'on lui a présenté : le hook de journal
    # réécrit `.logs/<jour>.md` à chaque tour, donc un projet vivant n'est
    # JAMAIS propre. Exiger la propreté de tout l'arbre revenait à exiger que
    # le harnais soit à l'arrêt — une condition qu'aucun projet en service ne
    # peut tenir, et que le bac à sable ne pouvait pas révéler.
    depots = [racine]
    if r.projet is not None:
        d = depot_porteur(r.projet, racine)
        if not egaux(d, racine):
            depots.append(d)
    for g in v:
        d = depot_porteur(g.de, racine)
        rel = sans_prefixe(g.de, d)
        rc, out = git(d, ["status", "--porcelain", "--", rel])
        if rc == 0 and out != "":
            e.append("`%s` a du travail non enregistré :\n        %s\n                                  Enregistre-le d'abord — sans ça, revenir en arrière "
                     "ne rendrait pas l'état de départ." % (rel, "\n        ".join(lignes(out)[:4])))
    # Le reste de l'arbre est SIGNALÉ, jamais refusé : il ne bouge pas, et le
    # taire ferait croire qu'on a tout vérifié.
    for d in depots:
        if not propre(d):
            _, o = git(d, ["status", "--porcelain"])
            n = len(lignes(o))
            _p("  %snote%s %d modification(s) en attente dans `%s` — hors "
               "du périmètre, rien n'y touchera" % (J, X, n, d))

    # ④ LE DÉPÔT DE MÉMOIRE A-T-IL UN DISTANT ? S'il n'en a pas, la migration
    # réécrit 100 % de ses chemins sans qu'aucune copie existe ailleurs.
    for d in depots:
        if egaux(d, racine):
            continue
        _, o = git(d, ["remote"])
        if o == "":
            e.append("`%s` n'a AUCUN dépôt distant. Il n'y a pas de "
                     "retour arrière possible hors de cette machine." % d)

    # ⑤ Chaque source doit exister, et chaque cible être libre.
    for g in v:
        if not os.path.exists(g.de):
            e.append("source absente : %s" % g.de)
        if os.path.exists(g.vers):
            e.append("cible déjà occupée : %s" % g.vers)
    return e


def deplace(g, racine):
    """Rend None, ou le texte de l'erreur."""
    p = parent(g.vers)
    if p:
        try:
            os.makedirs(p, exist_ok=True)
        except OSError as x:
            return _oserr(x)
    d = depot_porteur(g.de, racine)
    de_r = sans_prefixe(g.de, d)
    vers_r = sans_prefixe(g.vers, d)
    rc, _ = git(d, ["mv", de_r, vers_r])
    if rc == 0:
        g.comment = "git mv"
        return None
    # LE REPLI DIT QU'IL EST UN REPLI. Un `git mv` qui échoue parce que le
    # fichier n'est pas suivi et un qui échoue parce que l'index est sale se
    # lisent pareil, et le second perd l'historique sans un mot.
    try:
        os.rename(g.de, g.vers)
    except OSError as x:
        return _oserr(x)
    g.comment = "rename (git mv a refusé — historique NON suivi)"
    return None


def reste_en_v1(atelier):
    """Combien de projets de l'atelier sont encore sur l'ancien arbre.

    C'EST LE TÉMOIN QUI COMPTE. Un script qui n'a rien trouvé et un script qui a
    tout fait rendent tous les deux zéro ; ce nombre, lui, doit descendre de un."""
    n = 0
    for d in _entrees_triees(atelier):
        if not os.path.isdir(d) or not os.path.exists(os.path.join(d, ".git")):
            continue
        if memoire.resous(d).forme in (Forme.EnPlace, Forme.Deportee):
            n += 1
    return n


def main(args):
    appliquer = any(a == "--apply" for a in args)
    depart = None
    for a in args:
        if not a.startswith("--"):
            depart = a
            break
    if depart is None:
        try:
            depart = os.getcwd()
        except OSError:
            depart = ""

    r = memoire.resous(depart)
    racine = r.racine
    if racine is None:
        _p("  %saucun dépôt au-dessus de %s%s" % (R, depart, X))
        return 2
    _p("\n  %sMIGRATION VERS `brain/`%s   %s%s%s" % ("\x1b[1m", X, D, racine, X))
    _p("  %-22s %s" % ("forme actuelle", memoire.forme_mot(r.forme)))

    v, m = gestes(r, racine)
    if v is None:
        _p("  %srien à faire : %s%s" % (J, m, X))
        return 1

    ecarts = avant(r, racine, v)
    if ecarts:
        _p("\n  %sREFUSÉ — %d raison(s), et RIEN n'a été touché :%s" % (R, len(ecarts), X))
        for e in ecarts:
            _p("    · %s" % e)
        return 2

    for g in v:
        if appliquer:
            m = deplace(g, racine)
            if m is not None:
                _p("  %sÉCHEC%s %s : %s" % (R, X, g.de, m))
                return 2
            _p("  %s→%s %-44s %s%s%s" % (V, X, sans_prefixe(g.de, racine), D, g.comment, X))
        else:
            _p("  %s?%s %-44s -> %s" % (J, X, sans_prefixe(g.de, racine), sans_prefixe(g.vers, racine)))

    if not appliquer:
        # LE TÉMOIN DU BLANC : après cette ligne, l'arbre cible ne doit pas
        # exister. Si le blanc a écrit, le contrôle est raté, pas le détail.
        _p("\n  %d déplacement(s) À FAIRE  %s(--apply pour agir)%s" % (len(v), D, X))
        _p("  %sbrain/ existe déjà ? %s%s" % (D, "OUI — ANOMALIE" if os.path.exists(os.path.join(racine, "brain")) else "non", X))
        return 0

    # ── LES ASSERTIONS D'APRÈS, dans la même exécution ──────────────────
    mal = []
    apres = memoire.resous(depart)
    if apres.forme != Forme.Brain:
        mal.append("le résolveur, relancé à froid, dit `%s` et non `brain`" % memoire.forme_mot(apres.forme))
    for g in v:
        # « EXISTE ET EST VIDE » N'EST PAS « N'EXISTE PLUS ». Un dossier vide
        # se lit comme un dossier, et la détection de forme le compterait.
        if os.path.exists(g.de):
            mal.append("l'ancien dossier existe encore : %s" % g.de)
        if not os.path.exists(g.vers):
            mal.append("le nouveau dossier manque : %s" % g.vers)
    if apres.fact is not None:
        if not os.path.isfile(os.path.join(apres.fact, "base.md")):
            mal.append("`brain/fact/base.md` est introuvable après le déplacement")

    _p()
    if not mal:
        _p("  %s✓%s %d déplacement(s), %d assertion(s) d'après tenues" % (V, X, len(v), 3 + len(v) * 2))
    else:
        _p("  %s⚠ %d assertion(s) d'après ONT ÉCHOUÉ :%s" % (R, len(mal), X))
        for x in mal:
            _p("    · %s" % x)
    pa = parent(racine)
    n = reste_en_v1(pa if pa is not None else racine)
    _p("  %sreste sur l'ancien arbre dans l'atelier : %d%s" % (D, n, X))
    return 0 if not mal else 2
