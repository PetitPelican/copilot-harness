# -*- coding: utf-8 -*-
"""`harnais adopte` — POSER LE HARNAIS SUR UN PROJET, EN UN SEUL GESTE.

Port de `harnais/src/adopte.rs` (Rust, 0.12.8) ; le Rust gagne.

POURQUOI CETTE SOUS-COMMANDE EXISTE. Mesuré le 10/09/2026 par l'audit :
monter un projet demandait **huit gestes, dont deux qu'aucun document ne
mentionne**, et un neuvième invisible — rien n'avertissait qu'à l'étape 6 on
venait de fabriquer un projet dans l'organisation d'AVANT. Les quatre
compétences d'installation ne nommaient pas une seule fois la forme
actuelle. Un atelier qui ne se monte que par quelqu'un qui l'a déjà monté
n'est pas transposable ; c'est un savoir-faire, pas un outil.

CE QU'ELLE FAIT, ET RIEN D'AUTRE :

    brain/fact/base.md        le cap, et ce qu'est ce projet
    brain/fact/workflow.md    comment procéder, à remplir (commun à tous les agents)
    brain/mind/state.md       où on en est aujourd'hui
    brain/mind/todo.md        ce qui attend une décision
    .claude/settings.json     les DEUX clés qui branchent le paquet

En équipe (`--equipe A,B,C`), un jeu d'état PAR AGENT sous
`brain/mind/<nom>/`, un dossier d'agent par nom, et la fiche des rôles.

**PUREMENT ADDITIF.** Rien n'est jamais écrasé : un fichier qui existe est
annoncé comme déjà là et laissé tel quel. Les réglages sont FUSIONNÉS clé à
clé — un projet qui a déjà ses permissions les garde.

**À BLANC PAR DÉFAUT**, `--go` pour écrire. Le témoin de ce contrat est
qu'après un passage à blanc, aucun des fichiers annoncés n'existe.

**CE QU'ELLE NE FAIT PAS, ET LE DIT.** Écrire le cap à la place de
quelqu'un, découper un `CLAUDE.md` existant, trier une mémoire ancienne :
ce sont des jugements, ils demandent d'avoir lu le projet. La commande les
NOMME en fin de rapport au lieu de les deviner — un script qui décide à la
place de l'agent décide sans avoir lu.
"""
import os
import sys

import memoire
from memoire import Forme

V = "\x1b[32m"
J = "\x1b[33m"
B = "\x1b[1m"
D = "\x1b[2m"
X = "\x1b[0m"

# Le dépôt du marché, tel qu'un projet doit le déclarer. Une seule copie :
# c'est l'adresse à laquelle Claude Code va chercher le paquet, et deux
# copies qui divergent enverraient deux projets sur deux versions.
MARCHE = "atelier"
DEPOT = "PetitPelican/claude-harnais"
PAQUET = "harnais@atelier"


def _p(s=""):
    """`println!` : le texte, puis un saut de ligne."""
    sys.stdout.write(s + "\n")


def _panique(msg):
    """Là où le Rust panique (code 101), le Python sort en 101 de même."""
    sys.stderr.write("thread 'main' panicked: %s\n" % msg)
    sys.stdout.flush()
    sys.exit(101)


def _oserr(e):
    """Le texte d'une erreur d'E/S comme le Rust l'écrit : `<message> (os error N)`."""
    if getattr(e, "errno", None):
        return "%s (os error %d)" % (os.strerror(e.errno), e.errno)
    return str(e)


def _composants(p):
    return p.startswith("/"), [c for c in p.split("/") if c not in ("", ".")]


def strip_prefix(p, base):
    """`Path::strip_prefix` : le reste (en `/`), ou None. Comparaison par COMPOSANTS."""
    rp, cp = _composants(p)
    rb, cb = _composants(base)
    if rp != rb or cp[:len(cb)] != cb:
        return None
    return "/".join(cp[len(cb):])


def file_name(p):
    """`Path::file_name` : le dernier composant, ou None."""
    _, c = _composants(p)
    if not c or c[-1] == "..":
        return None
    return c[-1]


def canonicalize(p):
    """`Path::canonicalize` : le chemin réel, ou None s'il n'existe pas."""
    if not os.path.exists(p):
        return None
    try:
        return os.path.realpath(p)
    except OSError:
        return None


def base_md(nom):
    return ("---\ncap: À REMPLIR — une phrase : où va ce projet, et pour qui\n---\n\n"
            "# %s\n\n## Nature\n\nCe que ce projet EST, en trois lignes. Pas son historique.\n\n"
            "## Où on va\n\nLe prochain jalon, et à quoi on saura qu'il est atteint.\n\n"
            "## Ce que ce projet n'est pas\n\nLes confusions qui coûtent cher. Une par ligne.\n" % nom)


def workflow_md(nom):
    """COMMUN À TOUS LES AGENTS (Maxime, 12/10/2026) : comment procéder. Posé avec
    la marque « À REMPLIR » : tant qu'elle y est, le briefing dit « À RENSEIGNER »."""
    return ("# Comment procéder — %s\n\n"
            "## Les gestes qu'on ne redécouvre pas\n\n"
            "À REMPLIR — les commandes, leur ordre, les pièges de ce projet : une ligne\n"
            "chacun. Ce qu'on a appris à ses dépens et qui ne se lit nulle part dans le code.\n\n"
            "## Ce qu'on vérifie avant de dire que c'est fini\n\n"
            "À REMPLIR — la preuve qu'on attend d'un travail terminé, et comment la produire.\n"
            % nom)


def state_md(jour):
    return ("---\nmaj: %s\nsante: verte\njalon: À REMPLIR — ce vers quoi on va\n---\n\n"
            "# État\n\n## Phase\n\nOù en est ce projet AUJOURD'HUI. Ce fichier n'énumère que\n"
            "des faits actuels : si on le lit, c'est que le projet est comme ça.\n" % jour)


TODO_MD = ("# À faire\n\n"
           "Une ligne par tâche. `@user` marque ce qui attend une décision humaine, et\n"
           "ces lignes-là partent en premier dans tout point d'avancement.\n\n"
           "- [ ] première tâche\n")


def roles_md(agents):
    s = ("# Rôles\n\n"
         "Qui tient quoi — et SURTOUT les zones partagées. Un périmètre propre se lit\n"
         "dans les droits de chacun ; une zone partagée ne se lit nulle part, et c'est\n"
         "là que les collisions arrivent.\n\n")
    for a in agents:
        s += "## %s\n\nCe que cet agent tient, et ce qu'il ne touche pas.\n\n" % a
    s += "## Zones partagées\n\nCe que plusieurs agents touchent, et qui prévient qui.\n"
    return s


def claude_md_agent(nom, projet):
    return ("# %(n)s — %(p)s\n\n"
            "Tu es **%(n)s** sur ce projet. Ce fichier ne porte QUE ton rôle : ce qui vaut\n"
            "pour tout le monde vit dans le `CLAUDE.md` de la racine, qui est hérité.\n\n"
            "Contrôle de sortie : aucune phrase d'ici ne resterait vraie pour un autre agent.\n\n"
            "## Ce que tu tiens\n\nÀ REMPLIR.\n\n## Ce que tu ne touches pas\n\nÀ REMPLIR.\n"
            % {"n": nom, "p": projet})


# ── le rapport ───────────────────────────────────────────────────────────

class Rapport(object):
    def __init__(self):
        self.a_faire = []   # [(chemin, quoi)]
        self.deja = []      # [chemin]
        self.main = []      # [texte]

    def pose(self, ou, quoi, _contenu):
        """AJOUTE UN FICHIER — ou constate qu'il est déjà là. C'est le seul endroit
        qui décide d'écrire, et il ne peut pas écraser : le test d'existence et
        la décision sont la même ligne."""
        if os.path.exists(ou):
            self.deja.append(ou)
        else:
            self.a_faire.append((ou, quoi))


def court(p, racine):
    r = strip_prefix(p, racine)
    return p if r is None else r


# ── les réglages : fusionner, jamais remplacer ───────────────────────────

def _refuse_constante(c):
    raise ValueError(c)


def _lit_json(f):
    """Le JSON d'un fichier, ou None s'il manque ou n'est pas du JSON valide."""
    import json
    try:
        with open(f, encoding="utf-8", newline="") as h:
            return json.loads(h.read(), parse_constant=_refuse_constante), True
    except (OSError, ValueError, RecursionError):
        return None, False


def reglages(f):
    """LES DEUX CLÉS QUI BRANCHENT LE PAQUET, posées dans un fichier qui existe
    peut-être déjà et qui porte peut-être déjà des permissions.

    Rend `(json à écrire, ce qui manquait)`. Si rien ne manque, la seconde
    valeur est vide et on n'écrit pas : réécrire un fichier pour n'y rien
    changer, c'est brouiller un `git status` pour rien.
    """
    import json
    v, ok = _lit_json(f)
    if not ok or v is None:
        v = {}
    if not isinstance(v, dict):
        # Le Rust panique ici (indexer une valeur qui n'est pas un objet).
        _panique("réglages : le fichier n'est pas un objet JSON")
    manque = []

    m = v.get("extraKnownMarketplaces")
    marche_ok = isinstance(m, dict) and MARCHE in m
    if not marche_ok:
        manque.append("le marché où trouver le paquet")
        if m is None:
            m = v["extraKnownMarketplaces"] = {}
        if not isinstance(m, dict):
            _panique("réglages : extraKnownMarketplaces n'est pas un objet")
        m[MARCHE] = {"source": {"source": "github", "repo": DEPOT}}
    pl = v.get("enabledPlugins")
    paquet_ok = isinstance(pl, dict) and pl.get(PAQUET) is True
    if not paquet_ok:
        manque.append("le paquet lui-même, activé")
        if pl is None:
            pl = v["enabledPlugins"] = {}
        if not isinstance(pl, dict):
            _panique("réglages : enabledPlugins n'est pas un objet")
        pl[PAQUET] = True
    return json.dumps(v, indent=2, ensure_ascii=False) + "\n", manque


# ── la commande ──────────────────────────────────────────────────────────

def main(args):
    go = any(a == "--go" or a == "--apply" for a in args)
    equipe = []
    if "--equipe" in args:
        i = args.index("--equipe")
        if i + 1 < len(args):
            equipe = [x.strip() for x in args[i + 1].split(",") if x.strip()]
    ou = None
    for a in args:
        if not a.startswith("--") and not any(e in a for e in equipe):
            ou = a
            break
    if ou is None:
        try:
            ou = os.getcwd()
        except OSError:
            ou = ""

    r = memoire.resous(ou)
    racine = r.racine or canonicalize(ou) or ou
    nom = file_name(racine) or "ce projet"

    _p("%sharnais adopte%s — poser le harnais sur ce projet\n" % (B, X))
    _p("  projet : %s" % racine)
    # DEUX SITUATIONS SANS RAPPORT, que l'audit a nommées (§ 6 ③) : pas de
    # dépôt du tout, et dépôt sans mémoire. Elles partageaient un seul nom,
    # `HorsDepot` ; depuis le 26/09/2026 le résolveur les distingue lui-même
    # (`SansMemoire`). C'est la PREMIÈRE ligne que lit qui découvre l'outil.
    etat = {
        Forme.SansMemoire: "un dépôt git, et aucune mémoire — c'est le cas normal avant adoption",
        Forme.HorsDepot: "aucun dépôt git au-dessus — les gardes de commit ne s'appliqueront pas",
        Forme.EnPlace: "déjà une mémoire, dans la forme d'avant (`.fact/` et `.mind/`)",
        Forme.Deportee: "déjà une mémoire déportée (`memoire/`)",
        Forme.Brain: "déjà une mémoire dans la forme actuelle (`brain/`)",
        Forme.Ambigue: "À CHEVAL sur deux formes — une migration s'est arrêtée en route",
    }[r.forme]
    _p("  état   : %s%s%s\n" % (D, etat, X))

    # UNE MIGRATION INTERROMPUE NE SE COMPLÈTE PAS À L'AVEUGLE. Poser des
    # fichiers sur un arbre à cheval, c'est choisir en silence lequel des deux
    # fera foi — exactement ce que le résolveur refuse de faire.
    if r.forme == Forme.Ambigue:
        _p("  %sJe m'arrête ici.%s Ce projet porte les DEUX arbres de mémoire." % (J, X))
        _p("  Terminer la migration d'abord : %sharnais brain-migre%s" % (B, X))
        return 2

    import datetime
    jour = datetime.date.today().strftime("%Y-%m-%d")
    rap = Rapport()
    ecrits = []   # [(chemin, contenu)]

    j = os.path.join
    fact = j(racine, "brain/fact")
    mind = j(racine, "brain/mind")

    c = base_md(nom)
    rap.pose(j(fact, "base.md"), "le cap du projet, et ce qu'il est", c)
    ecrits.append((j(fact, "base.md"), c))
    c = workflow_md(nom)
    rap.pose(j(fact, "workflow.md"), "comment procéder, à remplir", c)
    ecrits.append((j(fact, "workflow.md"), c))

    if not equipe:
        c = state_md(jour)
        rap.pose(j(mind, "state.md"), "où on en est aujourd'hui", c)
        ecrits.append((j(mind, "state.md"), c))
        rap.pose(j(mind, "todo.md"), "ce qui attend une décision", TODO_MD)
        ecrits.append((j(mind, "todo.md"), TODO_MD))
    else:
        c = roles_md(equipe)
        rap.pose(j(fact, "roles.md"), "qui tient quoi, et les zones partagées", c)
        ecrits.append((j(fact, "roles.md"), c))
        for a in equipe:
            c = state_md(jour)
            rap.pose(j(mind, a, "state.md"), "l'état de %s" % a, c)
            ecrits.append((j(mind, a, "state.md"), c))
            rap.pose(j(mind, a, "todo.md"), "ce qui attend %s" % a, TODO_MD)
            ecrits.append((j(mind, a, "todo.md"), TODO_MD))
            d = j(racine, "agents", a)
            c = claude_md_agent(a, nom)
            rap.pose(j(d, "CLAUDE.md"), "le rôle de %s, et lui seul" % a, c)
            ecrits.append((j(d, "CLAUDE.md"), c))
            json_a, manque = reglages(j(d, ".claude/settings.json"))
            if manque:
                rap.a_faire.append((j(d, ".claude/settings.json"),
                                    "brancher le paquet pour %s" % a))
                ecrits.append((j(d, ".claude/settings.json"), json_a))
            else:
                rap.deja.append(j(d, ".claude/settings.json"))

    sf = j(racine, ".claude/settings.json")
    texte, manque = reglages(sf)
    if manque:
        rap.a_faire.append((sf, "brancher le paquet — %s" % ", ".join(manque)))
        ecrits.append((sf, texte))
    else:
        rap.deja.append(sf)

    # ── le rapport ───────────────────────────────────────────────────────
    if not rap.a_faire:
        _p("  %sCe projet est déjà au harnais.%s Rien à poser." % (V, X))
    else:
        _p("  %sÀ POSER (%d)%s" % (B, len(rap.a_faire), X))
        for p, quoi in rap.a_faire:
            _p("    %-34s %s%s%s" % (court(p, racine), D, quoi, X))
    if rap.deja:
        _p("\n  %sDÉJÀ LÀ (%d)%s %s— jamais écrasé%s" % (B, len(rap.deja), X, D, X))
        for p in rap.deja:
            _p("    %s" % court(p, racine))

    rap.main.append("remplir `cap:` — une phrase : où va ce projet, et pour qui")
    if equipe:
        rap.main.append("découper le CLAUDE.md : le commun reste à la racine, le rôle "
                        "descend chez chaque agent")
        rap.main.append("dire qui touche quoi dans les droits de chacun — les périmètres "
                        "ne se devinent pas")
    _p("\n  %sENSUITE, À TA MAIN%s" % (B, X))
    for m in rap.main:
        _p("    · %s" % m)

    if not go:
        _p("\n  %sRien n'a été écrit.%s Relance avec %s--go%s pour appliquer." % (J, X, B, X))
        return 0

    poses = 0
    for p, contenu in ecrits:
        # `Path::ends_with` : par composant — seul `settings.json` se réécrit (fusionné).
        if os.path.exists(p) and os.path.basename(p) != "settings.json":
            continue
        try:
            d = os.path.dirname(p)
            if d:
                os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        try:
            with open(p, "w", encoding="utf-8", newline="") as h:
                h.write(contenu)
            poses += 1
        except OSError as e:
            _p("  %séchec%s %s : %s" % (J, X, court(p, racine), _oserr(e)))
            return 1
    _p("\n  %s%d fichier(s) posé(s).%s" % (V, poses, X))
    _p("  Ouvre une session dans ce dossier : le briefing d'entrée doit s'afficher.")
    return 0
