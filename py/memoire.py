# -*- coding: utf-8 -*-
"""OÙ VIT LA MÉMOIRE D'UN PROJET — une seule autorité, pour tous.

Port de `harnais/src/memoire.rs` (Rust, 0.12.8) ; le Rust gagne, ce module le
suit à l'octet. Ce n'est pas un hook : c'est le module que les autres
importent. Compté le 08/09/2026, **huit programmes** résolvaient chacun de leur
côté l'emplacement de `.mind/` et `.fact/`. Tant qu'ils sont d'accord ça ne se
voit pas ; le jour où l'emplacement change, un oublié ne proteste pas — il lit
l'ancien endroit, le trouve vide, et se tait.

DEUX FORMES COEXISTENT, ET C'EST VOULU.

    en place   <projet>/.fact/ et <projet>/agents/<nom>/.mind/
    déportée   <racine du dépôt>/memoire/ porte les deux

Un projet est déporté si — et seulement si — ce dossier existe.

LE REPÈRE EST `--git-common-dir`, JAMAIS `--show-toplevel`. Le second rend
l'arbre de travail COURANT : appelé depuis les trois copies de Splide il rend
trois chemins, donc trois dossiers `memoire/`, et on aurait reconstruit avec
l'outil censé réparer le défaut qu'il répare.

**fail-open** : toute erreur rend `None`, et l'appelant retombe sur la forme en
place. Rendre `None` n'est PAS une erreur — c'est la réponse « ce projet n'est
pas déporté ».

MAIS CE `None` A COÛTÉ NEUF REPLIS. Mesuré le 10/09/2026 : `pour_agent()`
rendait `None` POUR DIRE « en place », donc chaque appelant devait savoir ce que
« en place » veut dire — donc le recomposer. Neuf recompositions en dur dans le
programme, une vingtaine hors de lui, et **aucune** des neuf compétences
n'appelait ce module. Le symptôme n'était pas la négligence des appelants :
c'était la signature.

D'OÙ `resous()`, qui rend TOUJOURS des chemins et une FORME NOMMÉE. Le `None` ne
survit que pour « hors dépôt », la seule vraie absence de réponse. Et la forme
cesse de se DEVINER : jusqu'ici huit endroits la déduisaient de la présence d'un
dossier, et deux contrats d'état en dépendaient — déplacer ce dossier aurait
fait retomber six projets sur un contrat qu'aucun ne remplit, et refusé tous
leurs enregistrements dès le premier jour.

CE MODULE EST SUR LE CHEMIN CHAUD DE CHAQUE HOOK : il n'importe que `os`, `sys`
en tête ; `subprocess` (cher) et `json` ne se paient qu'à l'usage. Les chemins
sont des `str` (pas de `pathlib`, qui coûte à l'import).
"""
import os
import sys

NOM = "memoire"

# LA FORME CIBLE — décidée par Maxime le 10/09/2026, en même temps que les
# mots. Un CERVEAU, plusieurs ESPRITS.
#
#   mono   <projet>/brain/fact/              les faits du projet
#          <projet>/brain/mind/              state.md · todo.md
#
#   multi  <racine>/brain/fact/              COMMUN aux agents, + roles.md
#          <racine>/brain/mind/<nom>/        un esprit par agent
#          <racine>/brain/workspace/         le carnet commun
#
# CE QUE ÇA SIMPLIFIE, et ce n'était pas prévu : le dossier est TOUJOURS à la
# racine. « Déportée » cesse d'être une FORME — deux arbres à connaître, deux
# branches dans chaque appelant — pour devenir une PROPRIÉTÉ : `brain/` a-t-il
# son propre dépôt git ? Elle ne décide plus que d'une chose, où l'on commite.
BRAIN = "brain"

_VUS = {}


def git(depart, args):
    """LA MÊME QUESTION N'EST POSÉE QU'UNE FOIS PAR PROCESSUS.

    DÉFAUT MESURÉ le 10/09/2026 (audit P4), avec un faux `git` qui journalise :
    **UN briefing lançait DIX-NEUF fois `git`** — dix `--git-common-dir` et neuf
    `--show-toplevel`, c'est-à-dire DEUX questions posées dix-neuf fois. À 10 ms
    le lancement, ces 19 processus sont la totalité du coût du hook : 0,17 s
    mesurés, 0,19 s pour 19 `git` seuls. Le hook le plus cher de l'atelier ne
    calculait rien, il redemandait.

    La mise en cache est SANS RISQUE DE PÉREMPTION, et c'est ce qui la rend
    acceptable ici : la racine d'un dépôt ne peut pas changer pendant qu'un hook
    s'exécute. Le cache meurt avec le processus — il ne peut donc pas servir une
    réponse d'hier, ce qui est exactement le défaut que ce dispositif existe pour
    éviter. On ne met en cache QUE ces questions de topologie ; rien qui décrive
    un CONTENU.
    """
    cle = (str(depart), tuple(args))
    if cle in _VUS:
        return _VUS[cle]
    r = git_sans_cache(depart, args)
    _VUS[cle] = r
    return r


def git_sans_cache(depart, args):
    import subprocess
    try:
        o = subprocess.run(["git"] + list(args), cwd=str(depart), stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, ValueError):
        return None
    if o.returncode != 0:
        return None
    s = o.stdout.decode("utf-8", "replace").strip()
    return s if s else None


def depart_defaut():
    """Le point de départ : `CLAUDE_PROJECT_DIR`, sinon le dossier courant."""
    d = os.environ.get("CLAUDE_PROJECT_DIR")
    if d:
        return d
    try:
        return os.getcwd()
    except OSError:
        return "."


# ── arithmétique de chemins, à la manière de `Path` en Rust ─────────────────

def _composants(p):
    """Les composants d'un chemin, comme `Path::components()` : les séparateurs
    répétés et les `.` disparaissent."""
    p = str(p)
    if os.sep != "/":
        p = p.replace(os.sep, "/")
    return [c for c in p.split("/") if c and c != "."]


def _strip_prefix(p, base):
    """`Path::strip_prefix` : le reste de `p` sous `base` (composant par
    composant — `/d/Splide` n'est pas un préfixe de `/d/Splide PO/x`), ou None.
    Le reste est une liste de composants, vide si les deux se confondent."""
    if os.path.isabs(str(p)) != os.path.isabs(str(base)):
        return None
    a, b = _composants(p), _composants(base)
    if a[:len(b)] == b:
        return a[len(b):]
    return None


def _canon(p):
    """`Path::canonicalize` : le chemin résolu, ou None s'il n'existe pas."""
    p = str(p)
    if not os.path.exists(p):
        return None
    try:
        return os.path.realpath(p)
    except (OSError, ValueError):
        return None


def racine_depot(depart):
    """La racine du dépôt PRINCIPAL — la même depuis tous ses arbres de travail."""
    g = git(depart, ["rev-parse", "--path-format=absolute", "--git-common-dir"])
    if g is None:
        return None
    if os.path.basename(g) == ".git":
        return os.path.dirname(g)
    return None


def base(depart):
    """`<racine>/memoire`, ou `None` si ce projet n'est pas déporté."""
    r = racine_depot(depart)
    if r is None:
        return None
    b = os.path.join(r, NOM)
    return b if os.path.isdir(b) else None


def base_projet(projet):
    """Même chose quand on tient déjà la racine du projet — sans appeler git."""
    b = os.path.join(str(projet), NOM)
    return b if os.path.isdir(b) else None


def arbre_courant(depart):
    """L'arbre de travail COURANT — celui d'où l'on parle."""
    return git(depart, ["rev-parse", "--show-toplevel"])


def lot(depart):
    """`agents/<nom>` si l'agent en est un, sinon `""`.

    LES DEUX REPÈRES NE SONT PAS INTERCHANGEABLES, et les confondre était le
    défaut trouvé au banc le 08/09/2026 : la POSITION d'un agent se mesure dans
    SON arbre de travail, l'IDENTITÉ du dépôt sur le dépôt principal.
    """
    a = arbre_courant(depart)
    if a is None:
        return ""
    d, a = _canon(depart), _canon(a)
    if d is None or a is None:
        return ""
    p = _strip_prefix(d, a)
    if p is None:
        return ""           # hors de l'arbre : comme relative_to qui lève
    if len(p) >= 2 and p[0] == "agents":
        return "%s/%s" % (p[0], p[1])
    return ""


class Forme(object):
    """LA FORME D'UN PROJET — une valeur, plus une déduction.

    Elle était lue huit fois de suite sur la présence d'un dossier. Un dossier
    qui déménage change alors huit comportements à la fois, dont le contrat que
    `mind-guard` exige d'un état d'agent. Ici elle se transporte.
    """
    # Aucun dépôt au-dessus : la plupart des gardes ne s'appliquent pas.
    HorsDepot = "HorsDepot"
    # UN DÉPÔT, ET AUCUNE MÉMOIRE — le cas normal avant adoption. Il portait le
    # nom `HorsDepot` jusqu'au 26/09/2026 : le diagnostic écrivait « forme :
    # hors-depot » et, à la ligne suivante, la racine du dépôt (audit § 6 ③).
    # Même comportement partout : seul le nom change.
    SansMemoire = "SansMemoire"
    # v1 · `<projet>/.fact/` et `<projet>[/agents/<nom>]/.mind/`.
    EnPlace = "EnPlace"
    # v1 · `<racine>/memoire/` porte les deux, pour tous les arbres de travail.
    Deportee = "Deportee"
    # v2 · `<racine>/brain/` porte tout, mono comme multi. Une seule règle.
    Brain = "Brain"
    # LES DEUX À LA FOIS. État qu'une migration interrompue laisse derrière
    # elle. On ne choisit PAS : un choix silencieux lit le mauvais fichier et se
    # tait. L'appelant décide quoi faire d'une ambiguïté nommée.
    Ambigue = "Ambigue"


_MOTS = {
    Forme.HorsDepot: "hors-depot",
    Forme.SansMemoire: "sans-memoire",
    Forme.EnPlace: "en-place",
    Forme.Deportee: "deportee",
    Forme.Brain: "brain",
    Forme.Ambigue: "AMBIGUE",
}


def forme_mot(forme):
    return _MOTS[forme]


def a_des_faits(forme):
    """Vrai quand le projet a migré vers `.fact/` — ce que huit endroits
    déduisaient chacun de leur côté."""
    return forme in (Forme.EnPlace, Forme.Deportee, Forme.Brain, Forme.Ambigue)


# `Forme::mot(&self)` et `Forme::a_des_faits(&self)` du Rust : mêmes noms, sur la classe.
Forme.mot = staticmethod(forme_mot)
Forme.a_des_faits = staticmethod(a_des_faits)


class Resolution(object):
    """Tout ce qu'un appelant doit savoir, résolu UNE fois.

    `fact` et `mind` sont absolus. `prefixe_fact` est le même dossier vu depuis
    le DÉPÔT QUI PORTE SES COMMITS, avec sa barre finale — c'est ce que `git
    diff --cached` rend, et c'est la seule forme contre laquelle une garde de
    commit peut comparer. Ce dépôt n'est PAS toujours la racine : c'est l'arbre
    courant, la mémoire déportée, ou `brain/` quand il a son propre dépôt.
    `base_des_prefixes` le nomme (audit § 6 ③ : ce texte disait « la racine du
    dépôt », et le contrat JSON ne nommait aucune base).

    Champs (chemins en `str`, ou None) :

    forme          une constante de `Forme`.
    racine         le dépôt PRINCIPAL — le même depuis tous ses arbres de
                   travail. C'est lui qui décide où vit une mémoire déportée.
    arbre          l'arbre de travail COURANT — celui d'où l'on parle. C'est LUI
                   qui donne les préfixes, parce que `git diff --cached` rend
                   des chemins relatifs à l'arbre courant. Les confondre ne se
                   voit que dans un worktree, et alors la garde compare des
                   chemins qui ne se rencontrent jamais.
    projet         le dossier qui porte la mémoire (None hors forme).
    lot            `agents/<nom>` — nu, c'est un identifiant.
    prefixe_lot    le même avec sa barre finale, ou vide. C'est un PRÉFIXE de
                   chemin, et les deux ne s'échangent pas : `lot + ".mind"` sans
                   la barre rend `agents/ios.mind`, qui ne désigne rien et ne
                   proteste pas.
    nom_agent      le NOM nu de l'agent (`Splide QA`), sans `agents/`. En v2 c'est
                   lui qui nomme le sous-dossier de `mind/` — `agents/` n'existe
                   plus dans le cerveau, il ne désigne que le dossier de
                   LANCEMENT dans le code.
    fact, mind     les faits (communs) et l'état (de l'agent).
    workspace      le carnet commun. N'existe qu'en équipe — en mono il n'y a
                   personne à qui écrire, et un dossier vide se lirait comme un
                   carnet muet.
    brain_autonome `brain/` a-t-il son PROPRE dépôt git ? Ne décide plus que d'une
                   chose : où l'on commite la mémoire. C'est ce qui reste de
                   « déportée » une fois que ce n'est plus une forme.
    prefixe_mind   L'ESPRIT VU DEPUIS LE DÉPÔT QUI PORTE LES COMMITS — avec barre
                   finale. Il existe parce que `mind_guard` le composait à la
                   main (`lot + ".mind/state.md"`) : sur un arbre migré vers
                   `brain/` ce nom ne désigne plus rien, et le contrôle de
                   lisibilité laissait passer un `state.md` sans en-tête sans un
                   mot. Mesuré le 10/09/2026. Même défaut que `prefixe_fact`
                   réparait, à un dossier près.
    """
    __slots__ = ("forme", "racine", "arbre", "projet", "lot", "prefixe_lot",
                 "nom_agent", "fact", "mind", "workspace", "brain_autonome",
                 "prefixe_projet", "prefixe_fact", "prefixe_mind")

    def __init__(self, forme=Forme.HorsDepot, racine=None, arbre=None, projet=None,
                 lot="", prefixe_lot="", nom_agent="", fact=None, mind=None,
                 workspace=None, brain_autonome=False, prefixe_projet="",
                 prefixe_fact="", prefixe_mind=""):
        self.forme = forme
        self.racine = racine
        self.arbre = arbre
        self.projet = projet
        self.lot = lot
        self.prefixe_lot = prefixe_lot
        self.nom_agent = nom_agent
        self.fact = fact
        self.mind = mind
        self.workspace = workspace
        self.brain_autonome = brain_autonome
        self.prefixe_projet = prefixe_projet
        self.prefixe_fact = prefixe_fact
        self.prefixe_mind = prefixe_mind

    def __repr__(self):
        return "Resolution(%s)" % ", ".join(
            "%s=%r" % (k, getattr(self, k)) for k in self.__slots__)

    def __eq__(self, autre):
        return (isinstance(autre, Resolution)
                and all(getattr(self, k) == getattr(autre, k) for k in self.__slots__))

    __hash__ = None

    def base_des_prefixes(self):
        """Le dossier depuis lequel se lisent `prefixe_fact`, `prefixe_mind` et
        `prefixe_projet` — `None` quand il n'y a rien à préfixer."""
        if self.forme == Forme.Brain and self.brain_autonome:
            return self.projet
        if self.forme in (Forme.Brain, Forme.EnPlace):
            return self.arbre
        if self.forme == Forme.Deportee:
            return os.path.join(self.racine, NOM) if self.racine is not None else None
        return None

    def workspace_prevu(self):
        """OÙ LE CARNET D'ÉQUIPE DOIT VIVRE — qu'il existe déjà ou non.

        `workspace` ci-dessus ne rend le chemin que si le dossier EST là : c'est
        ce qu'il faut pour lire. Pour CRÉER, il faut l'emplacement prévu, et
        c'est ce que cette fonction rend.

        DÉFAUT MESURÉ le 10/09/2026 par l'audit. Cette règle existait en DEUX
        exemplaires : ici, qui connaît les trois formes, et dans `carnet`, qui
        n'en connaissait que deux — `memoire/equipe` et `equipe`. Sur un projet
        en `brain/`, `equipe-amorce` créait donc le carnet à la racine pendant
        que le résolveur le cherchait dans le cerveau : **le carnet naissait
        invisible**, et rien ne le disait. Une seule vérité, ici.
        """
        if self.forme == Forme.Brain:
            # Le cerveau range le commun avec le reste du commun.
            return os.path.join(self.projet, "workspace") if self.projet is not None else None
        if self.forme == Forme.Deportee:
            # Déportée : à côté de la mémoire, pas à côté du code.
            return os.path.join(self.projet, "equipe") if self.projet is not None else None
        if self.forme in (Forme.EnPlace, Forme.HorsDepot, Forme.SansMemoire):
            return os.path.join(self.racine, "equipe") if self.racine is not None else None
        # AMBIGUË : deux arbres cohabitent, on ne choisit pas. Créer un carnet
        # ici, c'est en créer un que l'autre arbre ne verra pas.
        return None


def _prefixe(p, racine):
    r = _strip_prefix(p, racine)
    if not r:
        return ""
    return os.sep.join(r) + "/"


def porteur_des_faits(depart, racine):
    """Le premier ancêtre qui porte un `.fact/`, sans jamais sortir du dépôt."""
    p = str(depart)
    while True:
        if os.path.isdir(os.path.join(p, ".fact")):
            return p
        if p == racine:
            return None
        q = os.path.dirname(p)
        if not q or q == p:
            return None
        p = q


def resous(depart):
    """LA RÉSOLUTION. Toujours des chemins, toujours une forme nommée."""
    return resous_depuis(depart, depart)


def resous_depuis(ou_git, depart):
    """La même, quand GIT ne tourne pas là où l'agent se tient.

    Les deux coïncident presque toujours, et c'est ce qui rend la confusion
    invisible. Mais la garde de commit juge l'index du dépôt où `git commit`
    s'exécute — le DOSSIER COURANT — pendant que la position de l'agent se lit
    sur `CLAUDE_PROJECT_DIR`. Les confondre ne se voit que si les deux pointent
    des dépôts différents, et alors on juge le mauvais index en silence.
    """
    ou_git, depart = str(ou_git), str(depart)
    # CANONICALISÉE, comme `arbre` et `deportee` plus bas. C'est la MÊME
    # divergence, sur le champ qui l'avait échappé : `racine_depot()` rend ce que
    # git écrit, et tout le reste de la résolution passe par `canonicalize()`.
    # Deux orthographes du même dossier dans une seule structure, et celle du
    # carnet d'équipe se composait sur la mauvaise. Défaut mesuré le 10/09/2026
    # par la chaîne de construction, sur Windows : le témoin du carnet attendait
    # `\\?\C:\…\equipe` et recevait `C:/…\equipe`. macOS ne pouvait pas le voir —
    # les deux orthographes y coïncident, et c'est ce qui a laissé passer le champ.
    racine = racine_depot(ou_git)
    if racine is None:
        return Resolution()
    racine = _canon(racine) or racine
    # L'arbre courant sert à TOUTE l'arithmétique de chemins ; la racine ne sert
    # qu'à trouver la mémoire déportée. Hors worktree les deux coïncident, et
    # c'est ce qui rend la confusion invisible onze fois sur douze.
    a = arbre_courant(ou_git)
    arbre = (_canon(a) if a is not None else None) or racine
    l = lot(depart)
    lp = l + "/" if l else ""
    # CANONICALISÉ, comme `arbre`. `racine_depot()` rend ce que git écrit — sous
    # Windows `C:/x/y`, avec des barres obliques — tandis que tout le reste d'ici
    # passe par `canonicalize()`, qui rend `\\?\C:\x\y`. Les deux désignent le
    # même dossier et Rust les lit toutes deux, mais elles ne sont PAS ÉGALES : un
    # `strip_prefix` entre les deux ne mord pas, et rien ne le signale. Trouvé
    # par la chaîne de construction, sur Windows seulement — le portage diverge
    # sur les bords, jamais au milieu.
    b0 = base(ou_git)
    deportee = (_canon(b0) or b0) if b0 is not None else None

    depart_c = _canon(depart) or depart
    en_place = porteur_des_faits(depart_c, arbre)
    nom = l.rsplit("/", 1)[-1]

    # ── L'ANCIEN ET LE NEUF EN MÊME TEMPS ? ─────────────────────────────────
    # La question se pose AVANT de choisir lequel lire : c'est ce qu'une
    # migration interrompue laisse derrière elle, et servir l'un des deux
    # servirait l'état d'hier, sans un mot.
    #
    # ELLE NE PORTE QUE SUR v1 CONTRE v2. À l'intérieur de v1, `memoire/` et un
    # `.fact/` résiduel cohabitent LÉGITIMEMENT — le déport ne supprime pas
    # l'ancien dossier, et la règle « le déporté gagne » est établie depuis le
    # 08/09. Le contrôle différentiel l'a dit tout de suite quand je l'ai élargie
    # de trop : deux briefings ont cessé de trouver leurs faits.
    cerveau = os.path.join(racine, BRAIN)
    if os.path.isdir(cerveau) and (deportee is not None or en_place is not None):
        return Resolution(forme=Forme.Ambigue, lot=l, prefixe_lot=lp, nom_agent=nom,
                          racine=racine, arbre=arbre)

    # ── v2 · LE CERVEAU ─────────────────────────────────────────────────────
    # Une seule règle, mono comme multi.
    if os.path.isdir(cerveau):
        c = _canon(cerveau) or cerveau
        esprit = os.path.join(c, "mind", nom) if nom else os.path.join(c, "mind")
        ws = os.path.join(c, "workspace")
        # Les chemins que la garde compare viennent du dépôt qui porte le
        # cerveau : nus s'il est autonome, préfixés sinon.
        autonome = os.path.exists(os.path.join(racine, BRAIN, ".git"))
        pre = "" if autonome else BRAIN + "/"
        return Resolution(
            forme=Forme.Brain,
            brain_autonome=os.path.exists(os.path.join(c, ".git")),
            fact=os.path.join(c, "fact"),
            mind=esprit,
            workspace=ws if os.path.isdir(ws) else None,
            projet=c,
            prefixe_projet="",
            prefixe_fact=pre + "fact/",
            prefixe_mind=pre + "mind/" + (nom + "/" if nom else ""),
            lot=l, prefixe_lot=lp, nom_agent=nom,
            racine=racine, arbre=arbre)

    if deportee is not None:
        # DÉPORTÉE. Les chemins de commit visent le dépôt de MÉMOIRE, pas celui du
        # code : le préfixe y est donc nu, sans le lot.
        b = deportee
        w = os.path.join(b, "equipe")
        return Resolution(
            forme=Forme.Deportee,
            fact=os.path.join(b, ".fact"),
            mind=os.path.join(b, l, ".mind") if l else os.path.join(b, ".mind"),
            projet=b,
            prefixe_projet="",
            prefixe_fact=".fact/",
            prefixe_mind=lp + ".mind/",
            lot=l, prefixe_lot=lp, nom_agent=nom,
            workspace=w if os.path.isdir(w) else None,
            brain_autonome=os.path.exists(os.path.join(b, ".git")),
            racine=racine, arbre=arbre)

    if en_place is not None:
        p = en_place
        return Resolution(
            forme=Forme.EnPlace,
            prefixe_projet=_prefixe(p, arbre),
            prefixe_fact=_prefixe(p, arbre) + ".fact/",
            prefixe_mind=lp + ".mind/",
            fact=os.path.join(p, ".fact"),
            mind=os.path.join(arbre, l, ".mind"),
            projet=p, lot=l, prefixe_lot=lp, nom_agent=nom,
            workspace=None, brain_autonome=False,
            racine=racine, arbre=arbre)
    # Un dépôt sans `.fact/` : forme d'AVANT la migration. Les chemins sont rendus
    # quand même — l'appelant doit pouvoir dire « cherché ici, absent », jamais
    # rester muet.
    return Resolution(
        forme=Forme.SansMemoire,
        mind=os.path.join(arbre, l, ".mind"),
        fact=None,
        projet=None,
        prefixe_projet="",
        prefixe_fact="",
        prefixe_mind=lp + ".mind/",
        lot=l, prefixe_lot=lp, nom_agent=nom,
        workspace=None, brain_autonome=False,
        racine=racine, arbre=arbre)


def pour_agent(depart):
    """`(mind, fact)` pour l'agent qui parle — ou `(None, None)` si en place."""
    b = base(depart)
    if b is None:
        return (None, None)
    l = lot(depart)
    mind = os.path.join(b, l, ".mind") if l else os.path.join(b, ".mind")
    return (mind, os.path.join(b, ".fact"))


def pour_projet(projet):
    """`(fact, [(nom, mind)])` — la vue de tout le projet, pour les tableaux.

    `nom` vaut None pour l'état du projet lui-même (mono-agent). Rend
    `(None, None)` quand le projet n'est pas déporté."""
    b = base_projet(projet)
    if b is None:
        return (None, None)
    fact = os.path.join(b, ".fact")
    etats = []
    ag = os.path.join(b, "agents")
    if os.path.isdir(ag):
        try:
            noms = sorted(os.listdir(ag))   # `sorted()` : par chaîne, même parent donc par nom
        except OSError:
            noms = []
        for n in noms:
            m = os.path.join(ag, n, ".mind")
            if os.path.isdir(m):
                etats.append((n, m))
    if not etats and os.path.isdir(os.path.join(b, ".mind")):
        etats.append((None, os.path.join(b, ".mind")))
    return (fact if os.path.isdir(fact) else None, etats if etats else None)


def main(args):
    """`harnais memoire [depart]` — rend la résolution en JSON, pour la comparer
    à celle de Python. C'est un instrument, pas un hook."""
    import json
    depart = args[0] if args else depart_defaut()
    mind, fact = pour_agent(depart)
    pf, pe = pour_projet(depart)
    etats = None if pe is None else [[n, m] for (n, m) in pe]
    sys.stdout.write(json.dumps({
        "racine_depot": racine_depot(depart),
        "base":         base(depart),
        "base_projet":  base_projet(depart),
        "arbre":        arbre_courant(depart),
        "lot":          lot(depart),
        "mind":         mind,
        "fact":         fact,
        "projet_fact":  pf,
        "projet_etats": etats,
    }, ensure_ascii=False, separators=(",", ":")) + "\n")


def _debug_str(s):
    """`format!("{:?}", &str)` de Rust : entre guillemets, `"` `\\` `\\n` `\\r`
    `\\t` `\\0` échappés ; tout ce qui n'est pas imprimable, et les marques
    d'extension de graphème, en `\\u{xxxx}`. L'apostrophe n'est pas échappée."""
    sortie = ['"']
    unicodedata = None
    for c in s:
        o = ord(c)
        if c == '"':
            sortie.append('\\"')
        elif c == "\\":
            sortie.append("\\\\")
        elif c == "\n":
            sortie.append("\\n")
        elif c == "\r":
            sortie.append("\\r")
        elif c == "\t":
            sortie.append("\\t")
        elif c == "\0":
            sortie.append("\\0")
        elif 0x20 <= o < 0x7f:
            sortie.append(c)
        elif o < 0x80:
            sortie.append("\\u{%x}" % o)
        else:
            if unicodedata is None:
                import unicodedata
            cat = unicodedata.category(c)
            # Non imprimables (Rust `is_printable`) et Grapheme_Extend (Mn, Me, et
            # les quelques Mc qui en font partie) : `\u{…}`. APPROCHÉ pour les
            # points de code rares ; exact sur les chemins d'un poste.
            if cat in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp", "Zs", "Mn", "Me"):
                sortie.append("\\u{%x}" % o)
            else:
                sortie.append(c)
    sortie.append('"')
    return "".join(sortie)


def resolution_json(args):
    """LA RÉSOLUTION ENTIÈRE, EN JSON — pour les outils du poste.

    `memoire` existe déjà et rend un contrat d'AVANT `brain/`, que le contrôle
    différentiel compare octet pour octet à la version Python. Y ajouter des
    champs le ferait échouer pour une bonne raison ; on ajoute donc une porte, on
    ne déforme pas l'ancienne.

    Elle existe pour que les outils du poste — `claude-projets`, les pages du
    tailnet — cessent de recomposer `<projet>/.fact` à la main. Ils rendaient
    « mémoire absente » sur un projet migré, ce qui est la forme la plus
    dangereuse de faux : un tableau de bord vide se lit comme un projet vide.

    Le gabarit est celui du Rust, à l'octet : les chaînes y sont écrites avec
    `{:?}` (le `Debug` de Rust), pas avec un sérialiseur JSON.
    """
    if args:
        d = args[0]
    else:
        try:
            d = os.getcwd()
        except OSError:
            d = ""
    r = resous(d)

    def s(o):
        return "null" if o is None else _debug_str(o)

    def b(x):
        return "true" if x else "false"

    sys.stdout.write(
        '{"forme":%s,"racine":%s,"arbre":%s,"projet":%s,"fact":%s,"mind":%s,'
        '"workspace":%s,"lot":%s,"nom_agent":%s,"brain_autonome":%s,'
        '"prefixe_fact":%s,"prefixe_mind":%s,"prefixe_projet":%s,"prefixes_depuis":%s,'
        '"a_des_faits":%s}\n' % (
            _debug_str(forme_mot(r.forme)), s(r.racine), s(r.arbre), s(r.projet),
            s(r.fact), s(r.mind), s(r.workspace), _debug_str(r.lot),
            _debug_str(r.nom_agent), b(r.brain_autonome), _debug_str(r.prefixe_fact),
            _debug_str(r.prefixe_mind), _debug_str(r.prefixe_projet),
            s(r.base_des_prefixes()), b(a_des_faits(r.forme))))
    return 0
