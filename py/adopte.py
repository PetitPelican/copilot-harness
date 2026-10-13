# -*- coding: utf-8 -*-
"""`harnais adopte` — POSER LE HARNAIS SUR UN PROJET, EN UN SEUL GESTE.

Port de `harnais/src/adopte.rs` (Rust, Copilot 1.3.0) ; le Rust gagne. Une seule
addition, voulue : le fait commun `workflow.md` (comment procéder), posé après
`base.md`, avec des sections « À REMPLIR ». Seule différence de texte : le dossier
des livrables d'un agent compact se nomme `assets/` (`agent.BANC`).

POURQUOI CETTE SOUS-COMMANDE EXISTE. Monter un projet à la main demande
**une suite de gestes dont certains ne sont documentés nulle part**, et un
dernier invisible — rien n'avertit qu'en cours de route on vient de fabriquer
un projet dans l'organisation d'AVANT. Un atelier qui ne se monte que par
quelqu'un qui l'a déjà monté n'est pas transposable ; c'est un savoir-faire,
pas un outil.

CE QU'ELLE FAIT, ET RIEN D'AUTRE :

    brain/fact/base.md        le cap, et ce qu'est ce projet
    brain/fact/workflow.md    comment procéder, à remplir (commun à tous les agents)
    brain/mind/state.md       où on en est aujourd'hui
    brain/mind/todo.md        ce qui attend une décision
    .github/copilot/settings.json  marketplace locale et paquet activé

En équipe (`--equipe A,B,C`), un jeu d'état PAR AGENT sous
`brain/mind/<nom>/`, un dossier d'agent par nom, et la fiche des rôles.

**PUREMENT ADDITIF.** Rien n'est jamais écrasé : un fichier qui existe est
annoncé comme déjà là et laissé tel quel. Les réglages sont FUSIONNÉS clé à
clé — un projet qui a déjà ses permissions les garde.

**À BLANC PAR DÉFAUT**, `--go` pour écrire. Le témoin de ce contrat est
qu'après un passage à blanc, aucun des fichiers annoncés n'existe.

**CE QU'ELLE NE FAIT PAS, ET LE DIT.** Écrire le cap à la place de
quelqu'un, découper des instructions existantes, trier une mémoire ancienne :
ce sont des jugements, ils demandent d'avoir lu le projet. La commande les
NOMME en fin de rapport au lieu de les deviner — un script qui décide à la
place de l'agent décide sans avoir lu.
"""
import copy
import os
import re
import sys

import memoire
from memoire import Forme

V = "\x1b[32m"
J = "\x1b[33m"
B = "\x1b[1m"
D = "\x1b[2m"
X = "\x1b[0m"

MARQUEUR_METHODE = "<!-- harnais:method:start -->"


def _p(s=""):
    """`println!` : le texte, puis un saut de ligne."""
    sys.stdout.write(s + "\n")


def _e(s=""):
    """`eprintln!`."""
    sys.stderr.write(s + "\n")


def section_code(code):
    """La section qui garde l'adresse d'un code qui vit hors du projet. Son titre
    porte le chemin : le briefing sert les titres des faits à chaque session."""
    import datetime
    jour = datetime.datetime.now().strftime("%d/%m/%Y")
    return ("## Le code : `%(c)s`\n> **dit** · %(j)s — chemin donné à l'adoption\n\n"
            "Le code de ce projet vit hors de ce dépôt, à cet emplacement, et y reste. Ce "
            "dépôt porte les rôles, `brain/` et `docs/` ; on n'écrit dans le dossier du code "
            "que sur demande de @user. En CLI, `copilot --add-dir \"%(c)s\"` donne accès au code "
            "à une session ouverte dans ce projet.\n\n" % {"c": code, "j": jour})


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


def agents_md_agent(nom, projet):
    import equipe
    if equipe.est_qa(nom):
        return equipe.role_qa()
    return ("# %(n)s — %(p)s\n\n"
            "Tu es **%(n)s** sur ce projet. Ce fichier ne porte QUE ton rôle : ce qui vaut\n"
            "pour tout le monde vit dans `AGENTS.md` à la racine, qui est hérité.\n\n"
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
    import equipe
    r = equipe.strip_prefix(p, racine)
    if r is None:
        return p
    return os.sep.join(r) if r else ""


# ── les réglages : fusionner, jamais remplacer ───────────────────────────

def reglages(f):
    """LES DEUX CLÉS QUI BRANCHENT LE PAQUET, posées dans un fichier qui existe
    peut-être déjà et qui porte peut-être déjà des permissions.

    Rend `(json à écrire, ce qui manquait)`. Si rien ne manque, la seconde
    valeur est vide et on n'écrit pas : réécrire un fichier pour n'y rien
    changer, c'est brouiller un `git status` pour rien. Lève `copilot.Refus`."""
    import copilot
    import equipe
    if os.path.exists(f):
        try:
            t = equipe.lis(f)
        except (OSError, UnicodeDecodeError) as e:
            raise copilot.Refus(equipe.err_es(e))
        try:
            v = equipe.lis_json(t)
        except (ValueError, RecursionError) as e:
            raise copilot.Refus("%s : %s" % (f, e))
    else:
        v = {}
    avant = copy.deepcopy(v)
    copilot.reglages(v, copilot.paquet())
    manque = [] if v == avant else ["marketplace locale et paquet activé"]
    return equipe.json_indent2(v) + "\n", manque


def _methode_brute():
    """La méthode, telle que le paquet la livre (`include_str!` dans le Rust)."""
    ici = os.path.dirname(os.path.abspath(__file__))
    chemin = os.path.join(os.path.dirname(ici), "skills", "agentic-init", "templates", "foundation-AGENTS.md")
    with open(chemin, encoding="utf-8", newline="") as f:
        return f.read()


_NOM_USER = re.compile(r"`@user` désigne (.+?), l'humain qui commande l'atelier")


def nom_de_user(projet):
    """Le nom de `@user`, tel que l'initialisation l'a écrit dans la méthode de
    l'atelier : le premier `AGENTS.md` des dossiers parents qui le porte."""
    d = str(projet)
    while True:
        parent = os.path.dirname(d)
        if not parent or parent == d:
            return None
        d = parent
        try:
            with open(os.path.join(d, "AGENTS.md"), encoding="utf-8", newline="") as f:
                t = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        m = _NOM_USER.search(t)
        if m:
            n = m.group(1).strip()
            if n and n != "[UTILISATEUR]":
                return n


def methode(projet):
    """La méthode à copier dans le projet, `@user` nommé quand l'atelier le connaît."""
    brute = _methode_brute()
    n = nom_de_user(projet)
    if n is not None:
        return brute.replace("[UTILISATEUR]", n)
    return brute.replace("[UTILISATEUR], ", "")


def instructions(f, projet):
    """Le texte final des instructions, ou None si la méthode y est déjà. Lève
    `copilot.Refus` si le fichier est illisible."""
    import copilot
    import equipe
    try:
        avant = equipe.lis(f)
    except FileNotFoundError:
        avant = ""
    except (OSError, UnicodeDecodeError) as e:
        raise copilot.Refus("%s : %s" % (f, equipe.err_es(e)))
    if MARQUEUR_METHODE in avant:
        return None
    separation = "" if not avant else "\n\n"
    return "%s%s%s\n%s\n<!-- harnais:method:end -->\n" % (avant, separation, MARQUEUR_METHODE, methode(projet))


# ── la commande ──────────────────────────────────────────────────────────

def _absolu(s):
    """`std::path::absolute` : sans résoudre les liens, `.` et séparateurs
    redondants disparus, `..` conservés (POSIX) ou résolus (Windows)."""
    if os.name == "nt":
        return os.path.abspath(s)
    import equipe
    if s.startswith("/"):
        base = ""
    else:
        try:
            base = os.getcwd()
        except OSError:
            return s
    comps = equipe.composants(base) if base else []
    if comps and comps[0] == os.sep:
        comps = comps[1:]
    comps = [c for c in comps if c != "."]
    for c in equipe.composants(s):
        if c == os.sep or c == ".":
            continue
        comps.append(c)
    return "/" + "/".join(comps)


def main(args):
    import agent
    import copilot
    import equipe
    go = any(a == "--go" or a == "--apply" for a in args)
    demande_compact = "--compact" in args
    equipe_noms = []
    if "--equipe" in args:
        i = args.index("--equipe")
        if i + 1 < len(args):
            equipe_noms = [x.strip() for x in args[i + 1].split(",") if x.strip()]
    # LE CODE PEUT VIVRE AILLEURS. Un projet agentique se tient dans l'atelier ;
    # son code existant reste dans son dépôt — souvent un sous-dossier d'un dépôt
    # plus large — et n'y reçoit aucun fichier. `--code` en garde l'adresse.
    code = None
    if "--code" in args:
        i = args.index("--code")
        if i + 1 < len(args):
            code = _absolu(args[i + 1])
    if code is not None and not os.path.isdir(code):
        _e("adopte : --code %s : ce dossier n'existe pas." % code)
        return 1
    ou = None
    for i, a in enumerate(args):
        if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--equipe", "--code")):
            ou = a
            break
    if ou is None:
        try:
            ou = os.getcwd()
        except OSError:
            ou = ""

    r = memoire.resous(ou)
    racine = r.racine or equipe.canonicalize(ou) or ou
    nom = equipe.file_name(racine) or "ce projet"

    _p("%sharnais adopte%s — poser le harnais sur ce projet\n" % (B, X))
    _p("  projet : %s" % racine)
    # DEUX SITUATIONS SANS RAPPORT : pas de dépôt du tout (`HorsDepot`), et
    # dépôt sans mémoire (`SansMemoire`). Le résolveur les distingue lui-même.
    # C'est la PREMIÈRE ligne que lit qui découvre l'outil.
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
    if r.forme in (Forme.EnPlace, Forme.Deportee):
        _e("adopte : mémoire ancienne préservée ; lancer brain-migre avant de compléter brain/.")
        return 2
    if any(a == "." or a == ".." or any(c in a for c in "/\\:") for a in equipe_noms):
        _e("adopte : chaque nom d'agent doit être un nom de dossier simple.")
        return 1

    import datetime
    jour = datetime.datetime.now().strftime("%Y-%m-%d")
    rap = Rapport()
    ecrits = []   # [(chemin, contenu)]

    j = os.path.join
    fact = j(racine, "brain/fact")
    mind = j(racine, "brain/mind")
    compact = demande_compact or any(agent.compact(racine, n) for n in equipe_noms)

    c = base_md(nom)
    rap.pose(j(fact, "base.md"), "le cap du projet, et ce qu'il est", c)
    ecrits.append((j(fact, "base.md"), c))
    # La seule addition au Rust : le fait commun « comment procéder ».
    c = workflow_md(nom)
    rap.pose(j(fact, "workflow.md"), "comment procéder, à remplir", c)
    ecrits.append((j(fact, "workflow.md"), c))
    for f, titre, description in (
            ("architecture.md", "Architecture", "composants, flux et frontières du projet"),
            ("stack.md", "Stack", "outils, versions et commandes de ce projet"),
            ("rules.md", "Règles", "invariants et limites propres au projet")):
        c = "# %s\n\n" % titre
        if f == "architecture.md" and code is not None:
            c += section_code(code)
        c += "## À REMPLIR\n\nDécrire les %s, après lecture du projet.\n" % description
        rap.pose(j(fact, f), description, c)
        ecrits.append((j(fact, f), c))
    if code is not None and os.path.exists(j(fact, "architecture.md")):
        rap.main.append("brain/fact/architecture.md existe : y ajouter à la main la section "
                        "« Le code : `%s` »" % code)

    if not equipe_noms:
        c = state_md(jour)
        rap.pose(j(mind, "state.md"), "où on en est aujourd'hui", c)
        ecrits.append((j(mind, "state.md"), c))
        rap.pose(j(mind, "todo.md"), "ce qui attend une décision", TODO_MD)
        ecrits.append((j(mind, "todo.md"), TODO_MD))
    else:
        c = roles_md(equipe_noms)
        rap.pose(j(fact, "roles.md"), "qui tient quoi, et les zones partagées", c)
        ecrits.append((j(fact, "roles.md"), c))
        for a in equipe_noms:
            c = state_md(jour)
            rap.pose(j(mind, a, "state.md"), "l'état de %s" % a, c)
            ecrits.append((j(mind, a, "state.md"), c))
            rap.pose(j(mind, a, "todo.md"), "ce qui attend %s" % a, TODO_MD)
            ecrits.append((j(mind, a, "todo.md"), TODO_MD))
            if compact:
                profil = agent.profil(racine, a)
                s = agent.nom_de_profil(a)
                if not s or sum(1 for n in equipe_noms if agent.nom_de_profil(n) == s) != 1:
                    _e("adopte : nom de profil vide ou en collision : %s" % a)
                    return 1
                c = ("---\nname: %s\ndescription: Agent %s — rôle propre au projet\n---\n"
                     "Lis brain/mind/%s/state.md et brain/mind/%s/todo.md à la reprise.\n\n"
                     "<!-- harnais:role:start -->\n%s<!-- harnais:role:end -->\n"
                     % (s, a, a, a, agents_md_agent(a, nom)))
                rap.pose(profil, "profil et rôle uniques de %s" % a, c)
                ecrits.append((profil, c))
                garde = agent.perimetre_compact(racine, a)
                denies = list(agent.CONTROLE)
                denies.append("brain/poids.json")
                if not equipe.est_qa(a):
                    denies.append("brain/fact")
                for n in [n for n in equipe_noms if n != a]:
                    denies.append("brain/mind/%s" % n)
                    denies.append(agent.banc(n))
                v = {"deny": denies}
                allow = equipe.allow_par_defaut(a, "brain/fact", "brain/mind/%s" % a, agent.banc(a))
                if allow is not None:
                    v["allow"] = allow
                c = equipe.json_compact(v) + "\n"
                rap.pose(garde, "périmètre centralisé de %s" % a, c)
                ecrits.append((garde, c))
                continue
            d = j(racine, "agents", a)
            c = agents_md_agent(a, nom)
            if os.path.exists(j(d, "CLAUDE.md")):
                rap.main.append("%s : CLAUDE.md existe ; ne pas créer AGENTS.md en doublon" % a)
            else:
                rap.pose(j(d, "AGENTS.md"), "le rôle de %s, et lui seul" % a, c)
                ecrits.append((j(d, "AGENTS.md"), c))
            garde = j(d, ".github/copilot/perimetre.json")
            if os.path.exists(garde):
                try:
                    copilot.perimetre(d)
                except copilot.Refus as e:
                    _e("adopte : %s" % e)
                    return 1
                rap.deja.append(garde)
            else:
                denies = [j(racine, "agents", n) for n in equipe_noms if n != a]
                rap.a_faire.append((garde, "protéger le périmètre de %s" % a))
                v = {"deny": denies}
                if equipe.est_qa(a):
                    allow = equipe.allow_par_defaut(a, "brain/fact", "brain/mind/%s" % a,
                                                    "agents/%s/livrables" % a)
                    v["allow"] = allow if allow is not None else []
                ecrits.append((garde, equipe.json_compact(v) + "\n"))
            copilot.avertit_ancien(d)
            copilot.avertit_settings_agent(d)

    copilot.avertit_ancien(racine)
    inf = j(racine, ".github/copilot-instructions.md")
    try:
        texte = instructions(inf, racine)
    except copilot.Refus as e:
        _e("adopte : %s" % e)
        return 1
    if texte is not None:
        rap.a_faire.append((inf, "ajouter la méthode locale, en conservant les instructions existantes"))
        ecrits.append((inf, texte))
    else:
        rap.deja.append(inf)
    sf = copilot.settings(racine)
    try:
        json_texte, manque = reglages(sf)
    except copilot.Refus as e:
        _e("adopte : %s" % e)
        return 1
    if manque:
        rap.a_faire.append((sf, "brancher le paquet — %s" % ", ".join(manque)))
        ecrits.append((sf, json_texte))
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
    if equipe_noms:
        rap.main.append("découper AGENTS.md : le commun reste à la racine, le rôle "
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
        est_instructions = os.path.basename(p) == "copilot-instructions.md"
        est_settings = os.path.basename(p) == "settings.json"
        if os.path.exists(p) and not est_settings and not est_instructions:
            continue
        d = os.path.dirname(p)
        if d:
            try:
                os.makedirs(d, exist_ok=True)
            except OSError as e:
                _e("adopte : %s : %s" % (d, equipe.err_es(e)))
                return 1
        try:
            if est_instructions and os.path.exists(p):
                avant = equipe.lis(p)
                if not contenu.startswith(avant):
                    raise OSError("instructions modifiées depuis la prévisualisation")
                ajout = contenu[len(avant):]
                with open(p, "a", encoding="utf-8", newline="") as h:
                    h.write(ajout)
            elif est_settings:
                equipe.ecrit(p, contenu)
            else:
                # `create_new` : jamais d'écrasement, même si le fichier est apparu depuis.
                with open(p, "x", encoding="utf-8", newline="") as h:
                    h.write(contenu)
            poses += 1
        except (OSError, UnicodeDecodeError) as e:
            _p("  %séchec%s %s : %s" % (J, X, court(p, racine), equipe.err_es(e)))
            return 1
    _p("\n  %s%d fichier(s) posé(s).%s" % (V, poses, X))
    _p("  Ouvre une session dans ce dossier : le briefing d'entrée doit s'afficher.")
    return 0
