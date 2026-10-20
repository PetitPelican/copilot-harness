# -*- coding: utf-8 -*-
"""`harnais mise-a-niveau` — AMENER UN PROJET À LA FORME ACTUELLE, MONO OU ÉQUIPE.

Port du harnais Claude (`niveau`, 0.19), adapté à Copilot. Python 3.9 minimum,
chemins par `os.path`, aucun lien symbolique : Windows est la cible.

POURQUOI. Un projet monté avant `brain/` n'a jamais migré, et RIEN ne le dit :
le harnais sert l'ancienne forme à l'identique. `brain-migre` ne déplace que le
dossier, et laisse derrière lui la moitié du travail :

- les DROITS : les `deny` d'un agent visent `memoire/agents/OPS`. Après un
  déplacement nu, ils pointent un dossier qui n'existe plus — un périmètre qui
  ne mord plus, et qui ne le dit pas ;
- le `.gitignore` du dépôt de code ignore `memoire/` : le dossier de mémoire
  (un dépôt à part) y apparaîtrait d'un coup comme du code non suivi ;
- les faits manquants, l'esprit d'un agent sans le sien, le carnet absent ;
- l'espace des livrables, resté dans `outputs/` (1.2 à 1.3) ou `brain/workbench/`
  (0.19 à 1.1) alors que le nom d'aujourd'hui est `assets/`.

UN SEUL GESTE, QUELLE QUE SOIT LA FORME DE DÉPART :

    en place     .fact/  .mind/  agents/<nom>/.mind/   -> brain/   (git mv)
    déportée     memoire/  (dépôt à part ou non)        -> brain/   (le dossier
                 entier, son dépôt avec lui), puis DEDANS :
                 .fact -> fact · agents/<nom>/.mind -> mind/<nom> · equipe -> workspace
    brain        rien ne bouge ; on complète seulement
    équipe       « un dossier par agent » : on complète, rien ne bouge

puis, dans toutes les formes : les chemins des droits réécrits (une copie
`.avant-mise-a-niveau-<date>` de chaque fichier touché), les faits manquants
posés « À REMPLIR », l'état de chaque agent lancé, le carnet d'une équipe, le
paquet déclaré à la racine Git, et `outputs/` ou `brain/workbench/` renommé en
`assets/` — seulement s'il n'y a pas déjà un `assets/` : sinon le conflit est
NOMMÉ, et rien n'est fusionné d'office.

COPILOT FAIT AUTREMENT QUE CLAUDE :
  · les droits d'un agent sont `agents/<nom>/.github/copilot/perimetre.json`
    (ou `.github/copilot/perimetres/<nom>.json` en forme compacte), des listes
    `deny` / `allow` de chemins relatifs à la racine du projet — pas des règles
    `Edit(...)` dans un `.claude/settings.json` ;
  · le paquet est déclaré UNE fois, dans `.github/copilot/settings.json` à la
    racine Git, pas dans chaque dossier de lancement ;
  · la FORME COMPACTE (profils `.github/agents/<nom>.agent.md`, sans dossier
    d'agent) est un choix de Copilot : elle est NOMMÉE, jamais déplacée.

**CE QU'IL NE FAIT PAS, ET LE DIT** : trier. Un fichier de trop dans les faits,
un dossier que la méthode ne prévoit pas, une phrase d'un AGENTS.md qui cite
l'ancien chemin — ce sont des jugements de contenu, ils appartiennent au
projet. Le premier BLOQUE (il serait déplacé parmi les faits sans que personne
l'ait vérifié) ; les autres sont NOMMÉS, fichier et ligne.

**À BLANC PAR DÉFAUT.** `--apply` écrit, et seulement si rien ne bloque. Quand
quelque chose bouge, il exige aussi `--agents-arretes` : un agent resté ouvert
réécrirait l'ancien chemin, recréant l'ancienne forme à côté de la neuve.

**UN PROJET À LA FOIS.** `--atelier --racine <dossier>` fait le diagnostic de
tous et n'écrit jamais.
"""
import datetime
import json
import os
import re
import sys

import adopte
import agent
import copilot
import memoire
import migration
import socle
from memoire import Forme

V = "\x1b[32m"
R = "\x1b[31m"
J = "\x1b[33m"
B = "\x1b[1m"
D = "\x1b[2m"
X = "\x1b[0m"

# Ce que `brain/` a le droit de porter à sa racine. Le reste est NOMMÉ, pas
# déplacé : la méthode ne lui donne pas de place, mais seul le projet sait où
# il va (docs/ s'il est daté, assets/ s'il est livré, ailleurs sinon).
# `poids.json` : la confiance des faits (voir `poids`). `.logs/` : légitime
# quand `brain/` est un dépôt à part (le journal s'écrit où l'on commite).
DANS_BRAIN = {"fact", "mind", "workspace", "local", "poids.json", ".git", ".gitignore",
              ".gitattributes", ".logs", ".DS_Store"}

# Les espaces de livrables d'avant, et celui d'aujourd'hui (`agent.BANC`).
LIVRABLES_ANCIENS = ("outputs", "brain/workbench")
LIVRABLES = agent.BANC

COMPACTE = ("équipe COMPACTE (un menu d'agents dans une seule copie du code) : c'est un choix "
            "de Copilot, elle n'est pas touchée. Pour passer à « un dossier par agent » : monter "
            "l'équipe neuve à côté (`harnais adopte --equipe A,B --code <dépôt du code>`, dans un "
            "dossier vide), puis y reporter les faits, les états et les rôles ; `harnais demenage` "
            "ne porte pas ce passage.")
DOSSIER_AVANT = ("équipe « dossier d'avant » (`brain/mind/<nom>` + `agents/<nom>/`) : "
                 "`harnais demenage <projet>` la passe à « un dossier par agent » (à blanc d'abord).")


def _p(s=""):
    sys.stdout.write(s + "\n")


def _lis(f):
    try:
        with open(f, encoding="utf-8", newline="") as h:
            return h.read()
    except (OSError, UnicodeDecodeError):
        return None


def _ecris(f, t):
    d = os.path.dirname(f)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(f, "w", encoding="utf-8", newline="") as h:
        h.write(t)


def _dirs(d):
    try:
        return sorted(n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n)))
    except OSError:
        return []


def _court(p, racine):
    return migration.sans_prefixe(p, racine)


# ── les chemins, comme `Path` : composants, jamais sous-chaînes ─────────────
#
# Un droit s'écrit relatif à la racine du projet (`agents/PO`) ou absolu
# (`/Users/u/Proj/agents/PO`, `C:\Users\u\Proj\agents\PO`). Les comparer comme du
# texte fait mordre `memoire` sur `memoire-old` ; les comparer par composants
# non. `os.name` est lu à l'APPEL (et non à l'import) : un essai peut simuler
# Windows. Sous Windows la casse ne distingue pas deux dossiers.

def decoupe(p):
    """`(racine, [composants])` : racine `""` (relatif), `"/"`, ou le lecteur `"C:/"`."""
    return migration._composants(str(p))


def sous(a, b):
    """Le reste de `a` sous `b` (liste de composants, vide si égaux), ou None.
    `a` et `b` sont des chemins du MÊME genre (tous deux absolus)."""
    ra, ca = decoupe(a)
    rb, cb = decoupe(b)
    if os.name == "nt":
        if ra.lower() != rb.lower() or [c.lower() for c in ca[:len(cb)]] != [c.lower() for c in cb]:
            return None
    elif ra != rb or ca[:len(cb)] != cb:
        return None
    return ca[len(cb):]


def compose(racine, comps, sep="/"):
    """Le chemin écrit avec le séparateur `sep` (celui de l'entrée qu'on réécrit)."""
    corps = sep.join(comps)
    if racine == "":
        return corps
    if racine == "/":
        return sep + corps
    return racine[:2] + sep + corps if corps else racine[:2] + sep      # « C:/ »


def reecrit_entree(e, racine, corr, multiples=None):
    """Un droit (`deny` / `allow`) réécrit vers la nouvelle forme : `(liste, changé)`.

    Relatif, il reste relatif à `racine` ; absolu, il reste absolu ; il garde son
    séparateur. `corr` : [(ancien, nouveau)] absolus, du plus long au plus court —
    la première qui couvre l'entrée gagne. `multiples` : un dossier qui se SÉPARE
    en plusieurs ({ancien: [nouveau…]}) ; un droit qui le vise EXACTEMENT vise
    désormais tous les morceaux, sinon un `deny` ne protège que la moitié."""
    multiples = multiples or {}
    if not isinstance(e, str) or not e.strip():
        return [e], False
    racine_e, comps_e = decoupe(e)
    if os.name == "nt" and racine_e == "/":
        return [e], False                # `\x` : ni relatif ni absolu, tel qu'écrit
    relatif = racine_e == ""
    absolu = os.path.join(racine, *comps_e) if relatif else e
    sep = "\\" if ("\\" in e and "/" not in e) else "/"
    cibles = None
    for ancien, cs in multiples.items():
        r = sous(absolu, ancien)
        if r is not None and not r:
            cibles = list(cs)
            break
    if cibles is None:
        for ancien, nouveau in corr:
            r = sous(absolu, ancien)
            if r is not None:
                cibles = [os.path.join(nouveau, *r) if r else nouveau]
                break
    if cibles is None:
        return [e], False
    sortie = []
    for c in cibles:
        if relatif:
            r = sous(c, racine)
            if r is not None:
                sortie.append(compose("", r, sep))
                continue
        rc, cc = decoupe(c)
        sortie.append(compose(rc, cc, sep))
    return sortie, sortie != [e]


def reecrit_droits(texte, racine, corr, multiples=None):
    """Un `perimetre.json`, champ par champ : `deny` et `allow` seulement. Rend
    `(texte, n)` — `n` entrées changées ; le texte est rendu tel quel quand rien
    ne change. Lève `ValueError` si ce n'est pas du JSON."""
    v = json.loads(texte) if texte.strip() else {}
    if not isinstance(v, dict):
        raise ValueError("pas un objet")
    n = 0
    for cle in ("deny", "allow"):
        liste = v.get(cle)
        if not isinstance(liste, list):
            continue
        neuf = []
        for x in liste:
            ys, change = reecrit_entree(x, racine, corr, multiples)
            n += 1 if change else 0
            for y in ys:
                if y not in neuf:
                    neuf.append(y)
        v[cle] = neuf
    if not n:
        return texte, 0
    return json.dumps(v, indent=2, ensure_ascii=False) + "\n", n


# ── la forme d'une équipe ───────────────────────────────────────────────────

def classe_agents(racine):
    """`(dossiers, compacts)` : les agents du projet, selon que leur rôle vit dans un
    dossier `agents/<nom>/` ou dans un profil compact (`agent.compact`)."""
    noms = agent.agents_du_projet(racine)
    compacts = [n for n in noms if agent.compact(racine, n)]
    return [n for n in noms if n not in compacts], compacts


def nom_equipe(dossiers, compacts):
    """`seul`, `dossier`, `compacte` ou `mixte`."""
    if not dossiers and not compacts:
        return "seul"
    if dossiers and compacts:
        return "mixte"
    return "compacte" if compacts else "dossier"


class Plan(object):
    def __init__(self, racine):
        self.racine = racine
        self.forme = None
        self.equipe = False
        self.agents = []          # tous les agents, par nom
        self.ag_dossier = []      # ceux qui ont un dossier `agents/<nom>/`
        self.ag_compact = []      # ceux qui n'ont qu'un profil compact
        self.deplacements = []    # [(de, vers, comment, mode)] — la MÉMOIRE ; mode : "dossier" | "geste"
        self.renommages = []      # [(de, vers, comment)] — les livrables vers assets/
        self.correspondances = [] # [(ancien, nouveau)] chemins absolus, du plus précis au plus large
        # Un ancien dossier qui se SÉPARE en deux : `memoire/agents/<nom>/` donne
        # son état à `brain/mind/<nom>/` et garde le reste (preuves, notes) sous
        # `brain/agents/<nom>/`. Un droit qui le visait doit viser LES DEUX.
        self.multiples = {}       # {ancien: [nouveau, nouveau…]}
        self.reglages = []        # [(fichier, ancien, nouveau, n)]
        self.ignore = None        # (fichier, ancien, nouveau)
        self.poses = []           # [(chemin, quoi, contenu)]
        self.dossiers = []        # [(chemin, quoi)]
        self.bloquants = []
        self.a_relire = []
        self.suites = []          # ce qu'un autre outil ferait ensuite, nommé
        self.v3 = False           # forme « un dossier par agent » : on complète, rien ne bouge

    @property
    def bouge(self):
        return bool(self.deplacements or self.renommages)

    def travail(self):
        return bool(self.deplacements or self.renommages or self.reglages or self.poses
                    or self.dossiers or self.ignore)


# ── ce qui bouge ────────────────────────────────────────────────────────────

def _plan_deplacements(pl, r):
    j = os.path.join
    racine = pl.racine
    brain = j(racine, "brain")
    if r.forme == Forme.EnPlace:
        v, m = migration.gestes(r, racine)
        if v is None:
            pl.bloquants.append(m)
            return
        for g in v:
            pl.deplacements.append((g.de, g.vers, "", "geste"))
            pl.correspondances.append((g.de, g.vers))
        return
    if r.forme != Forme.Deportee:
        return
    b = memoire.base(racine)
    if b is None:
        pl.bloquants.append("mémoire déportée introuvable")
        return
    # LE DOSSIER ENTIER D'ABORD. Ne déplacer que `.fact/` et les `.mind/`
    # laisserait `memoire/` debout avec le reste : le résolveur verrait
    # l'ancien ET le neuf, et le projet ne recevrait plus aucune mémoire.
    pl.deplacements.append((b, brain, "", "dossier"))
    dedans = []
    if os.path.isdir(j(b, ".fact")):
        dedans.append((".fact", "fact"))
    ag = j(b, "agents")
    for n in _dirs(ag):
        if os.path.isdir(j(ag, n, ".mind")):
            dedans.append((j("agents", n, ".mind"), j("mind", n)))
    if not any(d.startswith("agents") for d, _ in dedans) and os.path.isdir(j(b, ".mind")):
        dedans.append((".mind", "mind"))
    if os.path.isdir(j(b, "equipe")):
        dedans.append(("equipe", "workspace"))
    for de, vers in dedans:
        pl.deplacements.append((j(brain, de), j(brain, vers), "", "geste"))
        pl.correspondances.append((j(b, de), j(brain, vers)))
    for n in _dirs(ag):
        if not os.path.isdir(j(ag, n, ".mind")):
            continue
        reste = [x for x in os.listdir(j(ag, n)) if x not in (".mind", ".DS_Store")]
        pl.multiples[j(ag, n)] = [j(brain, "mind", n)] + ([j(brain, "agents", n)] if reste else [])
    pl.correspondances.append((b, brain))     # le reste du dossier, tel quel


def _plan_livrables(pl, r):
    """`outputs/` et `brain/workbench/` passent à `assets/` — SEULEMENT s'il n'y a pas
    déjà un `assets/`. Un conflit est nommé, rien n'est fusionné d'office : seul le
    projet sait si deux espaces de livrables doivent n'en faire qu'un."""
    j = os.path.join
    base = pl.racine
    assets = j(base, LIVRABLES)
    anciens = []
    for rel in LIVRABLES_ANCIENS:
        p = j(base, *rel.split("/"))
        if os.path.isdir(p):
            anciens.append((rel, p))
    if not anciens:
        return
    noms = " et ".join("`%s/`" % rel for rel, _ in anciens)
    if os.path.exists(assets):
        pl.a_relire.append("CONFLIT — %s et `%s/` coexistent : rien n'est renommé ni fusionné d'office. "
                           "Choisir à la main lequel garde les livrables." % (noms, LIVRABLES))
        return
    if len(anciens) > 1:
        pl.a_relire.append("CONFLIT — %s veulent tous deux devenir `%s/` : rien n'est renommé. "
                           "Les réunir à la main d'abord." % (noms, LIVRABLES))
        return
    rel, p = anciens[0]
    # Un renommage ne traverse pas deux dépôts : `git mv` y perdrait l'historique d'un
    # côté et laisserait du travail non enregistré de l'autre.
    if not migration.egaux(migration.depot_porteur(p, base), migration.depot_porteur(j(base), base)):
        pl.a_relire.append("`%s/` vit dans un autre dépôt que `%s/` : à déplacer à la main."
                           % (rel, LIVRABLES))
        return
    pl.renommages.append((p, assets, ""))
    pl.correspondances.append((p, assets))


def _verifie_avant(pl, r):
    j = os.path.join
    racine = pl.racine
    brain = j(racine, "brain")
    if pl.deplacements and os.path.exists(brain):
        pl.bloquants.append("`brain/` existe déjà à côté de l'ancienne mémoire : une migration "
                            "interrompue. Trancher à la main avant de rejouer.")
    # Rien d'enregistré en attente SUR CE QUI BOUGE — sans ça, revenir en arrière
    # ne rend pas l'état de départ.
    sources = [d for (d, _v, _c, _m) in pl.deplacements] + [d for (d, _v, _c) in pl.renommages]
    vus = set()
    for src in sources:
        if not os.path.exists(src):
            continue      # un geste INTÉRIEUR : sa source n'existe qu'après le premier
        porteur = migration.depot_porteur(src, racine)
        rel = migration.sans_prefixe(src, porteur)
        rel = "." if (rel == src or rel == "") else rel
        rc, out = migration.git(porteur, ["status", "--porcelain", "--", rel])
        # `.DS_Store` : le Finder en sème partout, il voyage avec le dossier.
        sales = [l for l in migration.lignes(out) if not l.rstrip('"').endswith(".DS_Store")]
        if rc == 0 and sales:
            pl.bloquants.append("%d modification(s) non enregistrée(s) dans `%s`. Les enregistrer "
                                "d'abord : sans ça, revenir en arrière ne rend pas l'état de "
                                "départ." % (len(sales), _court(src, racine)))
        # UN DÉPÔT DE MÉMOIRE À PART DOIT AVOIR UNE COPIE AILLEURS.
        if pl.deplacements and not migration.egaux(porteur, racine) and porteur not in vus:
            vus.add(porteur)
            _, o = migration.git(porteur, ["remote"])
            if not o:
                pl.bloquants.append("le dépôt de la mémoire (`%s`) n'a AUCUN dépôt distant : pas de "
                                    "retour arrière possible hors de cette machine. Lui en donner "
                                    "un et y pousser d'abord." % (_court(porteur, racine) or porteur))


def _expert():
    return socle.profil_expert()


def _verifie_faits(pl, fact_actuel):
    """UN FICHIER DE TROP DANS LES FAITS BLOQUE. Il serait déplacé parmi les faits sans que personne
    l'ait vérifié — et les faits ne s'écrivent qu'à la demande."""
    if fact_actuel is None or not os.path.isdir(fact_actuel) or _expert():
        return
    autorises = socle.faits_tous()
    try:
        vus = sorted(n for n in os.listdir(fact_actuel) if n.endswith(".md"))
    except OSError:
        vus = []
    for n in vus:
        if n not in autorises:
            pl.bloquants.append("`%s` n'est pas un fait de la méthode (%s). Le ranger d'abord : "
                                "dans `docs/` s'il est daté, sinon dans le fait qui lui répond."
                                % (_court(os.path.join(fact_actuel, n), pl.racine), ", ".join(autorises)))


# ── ce qui se réécrit : les droits ──────────────────────────────────────────

def fichiers_droits(racine, ag_dossier):
    """Les fichiers de droits d'un projet : un par dossier d'agent, plus les périmètres
    centralisés de la forme compacte."""
    j = os.path.join
    out = []
    for a in ag_dossier:
        f = j(racine, "agents", a, ".github", "copilot", "perimetre.json")
        if os.path.isfile(f):
            out.append(f)
    d = j(racine, ".github", "copilot", "perimetres")
    try:
        noms = sorted(n for n in os.listdir(d) if n.endswith(".json"))
    except OSError:
        noms = []
    return out + [j(d, n) for n in noms]


def _plan_reglages(pl):
    if not pl.correspondances:
        return
    for f in fichiers_droits(pl.racine, pl.ag_dossier):
        t = _lis(f)
        if t is None:
            continue
        try:
            neuf, n = reecrit_droits(t, pl.racine, pl.correspondances, pl.multiples)
        except ValueError:
            pl.bloquants.append("`%s` n'est pas du JSON valide : le réparer d'abord" % _court(f, pl.racine))
            continue
        if n:
            pl.reglages.append((f, t, neuf, n))


def _plan_ignore(pl):
    """Le dossier de mémoire déporté, dépôt à part, était ignoré par le dépôt du
    code. `brain/` doit l'être de la même façon, sinon il y apparaît en entier."""
    if not pl.deplacements or pl.deplacements[0][3] != "dossier":
        return
    if not os.path.exists(os.path.join(pl.deplacements[0][0], ".git")):
        return
    f = os.path.join(pl.racine, ".gitignore")
    t = _lis(f) or ""
    neuf, n = re.subn(r"(?m)^(/?)memoire(/?)[ \t]*$", r"\1brain\2", t)
    if not n:
        neuf = t + ("" if t.endswith("\n") or not t else "\n") + "# la mémoire, dépôt à part\nbrain/\n"
    pl.ignore = (f, t, neuf)


# ── ce qui se pose ──────────────────────────────────────────────────────────

def _plan_poses(pl):
    j = os.path.join
    brain = j(pl.racine, "brain")
    fact, mind = j(brain, "fact"), j(brain, "mind")
    if pl.v3:
        # UN DOSSIER PAR AGENT : la mémoire est le projet, l'état est dans le
        # dossier de l'agent. Poser ici un `brain/` recréerait la dispersion.
        brain, fact, mind = pl.racine, j(pl.racine, "fact"), j(pl.racine, "agents")
    nom = os.path.basename(pl.racine.rstrip("/\\")) or "ce projet"
    jour = datetime.date.today().strftime("%Y-%m-%d")

    def pose(p, quoi, c):
        if not os.path.exists(p) and not _arrive(pl, p):
            pl.poses.append((p, quoi, c))

    if not _expert():
        pose(j(fact, "stack.md"), "avec quoi c'est fait, à remplir", adopte.stack_md(nom))
        pose(j(fact, "architecture.md"), "comment c'est agencé, à remplir", adopte.architecture_md(nom))
        pose(j(fact, "rules.md"), "ce qu'on ne franchit pas, à remplir", adopte.rules_md(nom))
    pose(j(fact, "base.md"), "le cap, à remplir", adopte.base_md(nom))
    pose(j(fact, "workflow.md"), "comment procéder, à remplir", adopte.workflow_md(nom))
    if pl.equipe:
        pose(j(fact, "roles.md"), "qui tient quoi, et les zones partagées", adopte.roles_md(pl.agents))
        for a in pl.agents:
            pose(j(mind, a, "state.md"), "l'état de %s" % a, adopte.state_md(jour))
            pose(j(mind, a, "todo.md"), "ce qui attend %s" % a, adopte.TODO_MD)
        ws = j(brain, "shared" if pl.v3 else "workspace")
        if not os.path.isdir(ws) and not _arrive(pl, ws):
            pl.dossiers.append((j(ws, ".etat"), "le carnet d'équipe"))
    else:
        pose(j(mind, "state.md"), "où on en est aujourd'hui", adopte.state_md(jour))
        pose(j(mind, "todo.md"), "ce qui attend une décision", adopte.TODO_MD)

    # LE PAQUET DÉCLARÉ — UNE FOIS, à la racine Git (Copilot ne lit que celle-là).
    f = copilot.settings(pl.racine)
    try:
        texte, manque = adopte.reglages(f)
    except copilot.Refus as e:
        pl.a_relire.append("déclaration du paquet (%s) : %s — à régler à la main"
                           % (_court(f, pl.racine), e))
        return
    if manque:
        pl.reglages = [x for x in pl.reglages if x[0] != f]
        pl.reglages.append((f, _lis(f) or "", texte, len(manque)))


def _arrive(pl, p):
    """Ce chemin existera-t-il APRÈS les déplacements ? (une pose qui l'ignorerait
    poserait un gabarit à l'endroit où arrive le vrai fichier)."""
    for ancien, nouveau in pl.correspondances:
        r = sous(p, nouveau)
        if r is not None:
            src = os.path.join(ancien, *r) if r else ancien
            if os.path.exists(src):
                return True
    return False


# ── ce qui se nomme ─────────────────────────────────────────────────────────

_ANCIENS = re.compile(r"memoire/|\.fact/|\.mind/")
_ANCIENS_LIVRABLES = re.compile(r"(?<![\w.-])outputs[/\\]|brain[/\\]workbench[/\\]")


def _plan_relire(pl, r):
    j = os.path.join
    racine = pl.racine
    textes = [j(racine, "AGENTS.md"), j(racine, "CLAUDE.md"), j(racine, ".github", "copilot-instructions.md")]
    textes += [j(racine, "agents", a, "AGENTS.md") for a in pl.ag_dossier]
    textes += [agent.profil(racine, a) for a in pl.agents]
    if pl.deplacements:
        for f in textes:
            t = _lis(f)
            if not t:
                continue
            for i, l in enumerate(t.split("\n"), 1):
                if _ANCIENS.search(l):
                    pl.a_relire.append("%s:%d cite l'ancien chemin — %s"
                                       % (_court(f, racine), i, l.strip()[:90]))
    if pl.renommages:
        for f in textes:
            t = _lis(f)
            if not t:
                continue
            for i, l in enumerate(t.split("\n"), 1):
                if _ANCIENS_LIVRABLES.search(l):
                    pl.a_relire.append("%s:%d cite l'ancien espace des livrables — %s"
                                       % (_court(f, racine), i, l.strip()[:90]))
    if pl.bouge:
        # Ce qui reste écrit à l'ancienne dans les droits sans être ancré : on ne le
        # devine pas (« memoire/** » relatif peut viser autre chose).
        for f in fichiers_droits(racine, pl.ag_dossier):
            t = _lis(f) or ""
            for (ff, _a, neuf, _n) in pl.reglages:
                if ff == f:
                    t = neuf
            for i, l in enumerate(t.split("\n"), 1):
                if re.search(r"(?<![\w/])memoire[/\\*]|(?<![\w])\.fact[/\\*]|(?<![\w])\.mind[/\\*]", l):
                    pl.a_relire.append("%s:%d mention à l'ancienne, non réécrite (note, ou chemin relatif) — %s"
                                       % (_court(f, racine), i, l.strip()[:90]))
    # LES CROCHETS GIT DU DÉPÔT DE MÉMOIRE voyagent avec lui, et peuvent viser
    # l'ancien chemin. Ils ne cassent rien — ils cessent de servir, sans un mot.
    if pl.deplacements and pl.deplacements[0][3] == "dossier":
        crochets = j(pl.deplacements[0][0], ".git", "hooks")
        for n in sorted(os.listdir(crochets)) if os.path.isdir(crochets) else []:
            if n.endswith(".sample"):
                continue
            t = _lis(j(crochets, n)) or ""
            if _ANCIENS.search(t):
                pl.a_relire.append("crochet git `%s` du dépôt de mémoire vise l'ancien chemin : "
                                   "il cessera de servir" % n)
    # LE CONTENU QUE LA MÉTHODE NE PRÉVOIT PAS DANS `brain/`.
    src = None
    if pl.deplacements and pl.deplacements[0][3] == "dossier":
        src = pl.deplacements[0][0]
    elif r.forme == Forme.Brain:
        src = j(racine, "brain")
    if src:
        try:
            noms = sorted(os.listdir(src))
        except OSError:
            noms = []
        avant = {".fact": "fact", ".mind": "mind", "equipe": "workspace"} if src != j(racine, "brain") else {}
        for n in noms:
            if avant.get(n, n) in DANS_BRAIN:
                continue
            if n == "workbench" and any(d == j(racine, "brain", "workbench") for (d, _v, _c) in pl.renommages):
                continue      # il part dans assets/ : ce n'est plus du contenu à ranger
            if n == "agents" and avant:
                for a in _dirs(j(src, "agents")):
                    reste = [x for x in os.listdir(j(src, "agents", a)) if x not in (".mind", ".DS_Store")]
                    if reste:
                        pl.a_relire.append("brain/agents/%s/ garde %s : hors méthode, à ranger"
                                           % (a, ", ".join(sorted(reste))))
                continue
            pl.a_relire.append("brain/%s : hors méthode, à ranger (docs/ si c'est daté, assets/ "
                               "si c'est livré)" % n)
    # UN ESPRIT SANS DOSSIER DE LANCEMENT NI PROFIL — un agent retiré, ou lancé d'ailleurs.
    if pl.equipe and not pl.v3:
        esprits = set()
        if r.forme == Forme.Brain:
            esprits = set(_dirs(j(racine, "brain", "mind")))
        else:
            for (de, vers, _c, _m) in pl.deplacements:
                rr = sous(vers, j(racine, "brain", "mind"))
                if rr:
                    esprits.add(rr[0])
        for n in sorted(esprits - set(pl.agents)):
            pl.a_relire.append("brain/mind/%s/ n'a ni dossier dans agents/ ni profil compact : "
                               "agent retiré, ou lancé d'ailleurs ? À décider." % n)
    if pl.v3:
        manque = [a for a in pl.agents if not os.path.isfile(agent.profil(racine, a))]
        if manque:
            pl.a_relire.append("profil du menu d'agent absent pour %s : `harnais equipe --profils "
                               "--apply`, puis commiter" % ", ".join(manque))


# ── le plan, puis l'exécution ───────────────────────────────────────────────

def planifie(depart):
    r = memoire.resous(depart)
    if r.racine is None:
        return None, "aucun dépôt git au-dessus de %s" % depart
    racine = r.racine
    pl = Plan(racine)
    pl.forme = r.forme
    if r.forme in (Forme.SansMemoire, Forme.HorsDepot):
        return pl, "aucune mémoire : c'est `harnais adopte` qui pose le harnais"
    if r.forme == Forme.Equipe:
        # Déjà dans la forme la plus récente : on COMPLÈTE, rien ne bouge, aucun
        # chemin n'est réécrit — sauf l'espace des livrables, qui a un nom d'aujourd'hui.
        pl = Plan(r.projet)
        pl.forme, pl.v3 = r.forme, True
        pl.agents = [n for n in os.listdir(os.path.join(r.projet, "agents"))
                     if os.path.isdir(os.path.join(r.projet, "agents", n)) and not n.startswith(".")] \
            if os.path.isdir(os.path.join(r.projet, "agents")) else []
        pl.agents.sort()
        pl.ag_dossier = list(pl.agents)
        pl.equipe = True
        _verifie_faits(pl, r.fact)
        _plan_livrables(pl, r)
        _verifie_avant(pl, r)
        _plan_reglages(pl)
        _plan_poses(pl)
        _plan_relire(pl, r)
        pl.correspondances.sort(key=lambda c: -len(decoupe(c[0])[1]))
        return pl, None
    pl.ag_dossier, pl.ag_compact = classe_agents(racine)
    pl.agents = sorted(pl.ag_dossier + pl.ag_compact)
    pl.equipe = bool(pl.agents)
    if r.forme == Forme.Ambigue:
        pl.bloquants.append("ce projet porte l'ANCIENNE mémoire et `brain/` à la fois : une "
                            "migration interrompue, ou un agent resté ouvert pendant la "
                            "migration. Trancher à la main.")
        return pl, None
    _plan_deplacements(pl, r)
    if r.forme == Forme.Deportee:
        b = memoire.base(racine)
        _verifie_faits(pl, os.path.join(b, ".fact") if b else None)
    else:
        _verifie_faits(pl, r.fact)
    _plan_livrables(pl, r)
    pl.correspondances.sort(key=lambda c: -len(decoupe(c[0])[1]))
    _verifie_avant(pl, r)
    _plan_reglages(pl)
    _plan_ignore(pl)
    _plan_poses(pl)
    _plan_relire(pl, r)
    genre = nom_equipe(pl.ag_dossier, pl.ag_compact)
    if genre == "compacte":
        pl.suites.append(COMPACTE)
    elif genre == "mixte":
        pl.suites.append("équipe MIXTE (des agents compacts, d'autres avec un dossier) : ni l'un ni "
                         "l'autre n'est touché. " + COMPACTE)
    elif genre == "dossier":
        pl.suites.append(DOSSIER_AVANT)
    return pl, None


def _sauve(f, jour):
    s = "%s.avant-mise-a-niveau-%s" % (f, jour)
    if os.path.exists(f) and not os.path.exists(s):
        with open(f, "rb") as a, open(s, "wb") as b:
            b.write(a.read())


def _commit(pl, gestes, message):
    """Enregistre les déplacements faits par `git mv`, dépôt par dépôt, et RIEN d'autre
    avec eux : laissé en attente, le déplacement partirait dans le prochain commit de
    code de quelqu'un — ou ferait refuser le suivant. Seuls les chemins déplacés sont
    nommés. Rend un message d'échec, ou None."""
    par_depot = {}
    for (de, vers, c) in gestes:
        if not c.startswith("git mv"):
            continue
        d = migration.depot_porteur(vers, pl.racine)
        par_depot.setdefault(d, []).extend([migration.sans_prefixe(de, d), migration.sans_prefixe(vers, d)])
    for d, chemins in par_depot.items():
        rc, out = migration.git(d, ["commit", "-q", "-m", message, "--"] + chemins)
        if rc != 0:
            return ("le déplacement est fait mais PAS enregistré dans `%s` : %s"
                    % (_court(d, pl.racine) or d, out[:200]))
    return None


def applique(pl):
    """Rend la liste des écarts d'après (vide = tenu)."""
    jour = datetime.date.today().strftime("%Y%m%d")
    for i, (de, vers, _c, mode) in enumerate(pl.deplacements):
        if mode == "dossier" and os.path.exists(os.path.join(de, ".git")):
            os.rename(de, vers)
            pl.deplacements[i] = (de, vers, "dossier déplacé avec son dépôt", mode)
            continue
        g = migration.Geste(de, vers)
        m = migration.deplace(g, pl.racine)
        if m is not None:
            return ["ÉCHEC du déplacement %s : %s" % (_court(de, pl.racine), m)]
        pl.deplacements[i] = (de, vers, g.comment, mode)
        # Un `agents/<nom>/` vidé de son `.mind/` ne doit pas rester comme coquille.
        par = os.path.dirname(de)
        if os.path.basename(par) and os.path.isdir(par):
            try:
                restes = [x for x in os.listdir(par) if x != ".DS_Store"]
                if not restes:
                    for x in os.listdir(par):
                        os.remove(os.path.join(par, x))
                    os.rmdir(par)
                    gp = os.path.dirname(par)
                    if os.path.basename(gp) == "agents" and not os.listdir(gp):
                        os.rmdir(gp)
            except OSError:
                pass
    echec = _commit(pl, [(de, vers, c) for (de, vers, c, _m) in pl.deplacements],
                    "Mise à niveau : la mémoire passe dans la forme brain/ "
                    "(harnais mise-a-niveau) # fact-ok # mind-ok")
    if echec:
        return [echec]
    for i, (de, vers, _c) in enumerate(pl.renommages):
        g = migration.Geste(de, vers)
        m = migration.deplace(g, pl.racine)
        if m is not None:
            return ["ÉCHEC du renommage %s : %s" % (_court(de, pl.racine), m)]
        pl.renommages[i] = (de, vers, g.comment)
    echec = _commit(pl, pl.renommages,
                    "Mise à niveau : les livrables passent dans assets/ "
                    "(harnais mise-a-niveau) # fact-ok # mind-ok")
    if echec:
        return [echec]
    for (f, _a, neuf, _n) in pl.reglages:
        _sauve(f, jour)
        _ecris(f, neuf)
    if pl.ignore:
        _ecris(pl.ignore[0], pl.ignore[2])
    for (p, _q, c) in pl.poses:
        if not os.path.exists(p):
            _ecris(p, c)
    for (d, _q) in pl.dossiers:
        os.makedirs(d, exist_ok=True)

    # ── LES ASSERTIONS D'APRÈS, dans la même exécution ──
    memoire._VUS.clear()
    mal = []
    apres = memoire.resous(pl.racine)
    attendue = Forme.Equipe if pl.v3 else Forme.Brain
    if apres.forme != attendue:
        mal.append("le résolveur, relancé à froid, dit `%s` et non `%s`"
                   % (memoire.forme_mot(apres.forme), memoire.forme_mot(attendue)))
    if pl.v3 and os.path.exists(os.path.join(pl.racine, "brain")):
        mal.append("un `brain/` est apparu dans une équipe « un dossier par agent »")
    for (de, vers) in [(d, v) for (d, v, _c, _m) in pl.deplacements] + [(d, v) for (d, v, _c) in pl.renommages]:
        if os.path.exists(de):
            mal.append("l'ancien dossier existe encore : %s" % _court(de, pl.racine))
        if not os.path.exists(vers):
            mal.append("le nouveau dossier manque : %s" % _court(vers, pl.racine))
    for (f, _a, _n2, _n) in pl.reglages:
        t = _lis(f) or ""
        try:
            json.loads(t)
        except ValueError:
            mal.append("%s n'est plus du JSON valide" % _court(f, pl.racine))
    for f in fichiers_droits(pl.racine, pl.ag_dossier):
        try:
            v = json.loads(_lis(f) or "{}")
        except ValueError:
            continue
        for cle in ("deny", "allow"):
            for x in (v.get(cle) if isinstance(v, dict) and isinstance(v.get(cle), list) else []):
                ys, change = reecrit_entree(x, pl.racine, pl.correspondances)
                if change:
                    mal.append("%s cite encore l'ancien chemin %s" % (_court(f, pl.racine), x))
    if apres.fact is not None and not os.path.isfile(os.path.join(apres.fact, "base.md")):
        mal.append("brain/fact/base.md introuvable après coup")
    return mal


def _affiche(pl):
    rc = lambda p: _court(p, pl.racine)
    genre = nom_equipe(pl.ag_dossier, pl.ag_compact)
    _p("  %-16s %s%s" % ("forme", memoire.forme_mot(pl.forme),
                         "  ·  équipe %s : %s" % (genre if not pl.v3 else "« un dossier par agent »",
                                                  ", ".join(pl.agents)) if pl.equipe else "  ·  un agent"))
    if pl.deplacements:
        _p("\n  %sLA MÉMOIRE BOUGE (%d)%s" % (B, len(pl.deplacements), X))
        for (de, vers, c, _m) in pl.deplacements:
            _p("    %-40s -> %s %s%s%s" % (rc(de), rc(vers), D, c, X))
    if pl.renommages:
        _p("\n  %sLES LIVRABLES PASSENT À assets/ (%d)%s" % (B, len(pl.renommages), X))
        for (de, vers, c) in pl.renommages:
            _p("    %-40s -> %s %s%s%s" % (rc(de), rc(vers), D, c, X))
    if pl.reglages:
        _p("\n  %sDROITS ET RÉGLAGES RÉÉCRITS (%d)%s %s— copie gardée à côté%s" % (B, len(pl.reglages), X, D, X))
        for (f, _a, _n2, n) in pl.reglages:
            _p("    %-40s %d chemin(s) ou clé(s)" % (rc(f), n))
    if pl.ignore:
        _p("\n  %s.gitignore%s      memoire/ -> brain/ (le dépôt de mémoire reste à part)" % (B, X))
    if pl.poses or pl.dossiers:
        _p("\n  %sÀ POSER (%d)%s %s— jamais par-dessus un fichier%s" % (B, len(pl.poses) + len(pl.dossiers), X, D, X))
        for (p, q, _c) in pl.poses:
            _p("    %-40s %s%s%s" % (rc(p), D, q, X))
        for (d, q) in pl.dossiers:
            _p("    %-40s %s%s%s" % (rc(d), D, q, X))
    if pl.a_relire:
        _p("\n  %sÀ RELIRE (%d)%s %s— rien n'y est touché : c'est du contenu%s" % (B, len(pl.a_relire), X, D, X))
        for x in pl.a_relire:
            _p("    · %s" % x)
    if pl.suites:
        _p("\n  %sNOMMÉ, PAS TOUCHÉ%s" % (B, X))
        for x in pl.suites:
            _p("    · %s" % x)
    if pl.bloquants:
        _p("\n  %sBLOQUÉ — %d raison(s), rien ne sera écrit tant qu'elles tiennent :%s" % (R, len(pl.bloquants), X))
        for x in pl.bloquants:
            _p("    · %s" % x)


def a_faire(pl, m):
    """Ce qu'il faudrait faire à ce projet, en une phrase — pour le diagnostic d'atelier."""
    if pl is None or m:
        return "adopte" if (m or "").startswith("aucune mémoire") else (m or "—")
    if pl.bloquants:
        return "BLOQUÉ (%d) : voir `mise-a-niveau <projet>`" % len(pl.bloquants)
    gestes = []
    if pl.bouge:
        gestes.append("mise-a-niveau --apply --agents-arretes")
    elif pl.travail():
        gestes.append("mise-a-niveau --apply")
    genre = nom_equipe(pl.ag_dossier, pl.ag_compact) if not pl.v3 else "equipe"
    if genre == "dossier":
        gestes.append("puis demenage (équipe d'avant)")
    elif genre in ("compacte", "mixte"):
        gestes.append("équipe %s : nommée, pas touchée" % genre)
    if pl.a_relire:
        gestes.append("%d à relire" % len(pl.a_relire))
    return " ; ".join(gestes) if gestes else "rien — à niveau"


def _atelier(dossier):
    _p("\n  %sMISE À NIVEAU — DIAGNOSTIC DE L'ATELIER%s   %s%s%s" % (B, X, D, dossier, X))
    _p("  %s(rien n'est écrit ; chaque projet se met à niveau seul, agents arrêtés)%s\n" % (D, X))
    _p("  %-22s %-12s %-10s %s" % ("projet", "forme", "équipe", "à faire"))
    n_faire = 0
    try:
        noms = sorted(os.listdir(dossier))
    except OSError:
        noms = []
    for n in noms:
        d = os.path.join(dossier, n)
        if not os.path.isdir(os.path.join(d, ".git")):
            continue
        pl, m = planifie(d)
        if pl is None or m:
            _p("  %-22s %s%s%s" % (n[:22], D, a_faire(pl, m), X))
            continue
        genre = "dossier" if pl.v3 else nom_equipe(pl.ag_dossier, pl.ag_compact)
        verdict = a_faire(pl, m)
        if not verdict.startswith("rien"):
            n_faire += 1
        _p("  %-22s %-12s %-10s %s%s%s" % (n[:22], memoire.forme_mot(pl.forme),
                                          "v3" if pl.v3 else genre,
                                          R if pl.bloquants else "", verdict, X if pl.bloquants else ""))
    _p("\n  %d projet(s) demandent un geste. Le détail : `harnais mise-a-niveau <projet>`." % n_faire)
    return 0


def _valeur(args, cle):
    for i, a in enumerate(args):
        if a == cle and i + 1 < len(args):
            return args[i + 1]
        if a.startswith(cle + "="):
            return a[len(cle) + 1:]
    return None


def main(args):
    if "--atelier" in args:
        i = args.index("--atelier")
        d = _valeur(args, "--racine")
        if d is None and i + 1 < len(args) and not args[i + 1].startswith("--"):
            d = args[i + 1]
        if d is None:
            d = os.getcwd()
        return _atelier(os.path.abspath(os.path.expanduser(d)))
    appliquer = "--apply" in args or "--go" in args
    arretes = "--agents-arretes" in args
    valeurs = [_valeur(args, "--racine")]
    depart = next((a for a in args if not a.startswith("--") and a not in valeurs), None) or os.getcwd()
    pl, m = planifie(depart)
    if pl is None:
        _p("  %s%s%s" % (R, m, X))
        return 2
    _p("\n  %sMISE À NIVEAU%s   %s%s%s" % (B, X, D, pl.racine, X))
    if m:
        _p("  %s%s%s" % (J, m, X))
        return 1
    _affiche(pl)
    if not pl.travail() and not pl.bloquants:
        _p("\n  %sDéjà à niveau.%s %s" % (V, X, "Reste à relire ce qui est nommé ci-dessus." if pl.a_relire else ""))
        return 0
    if pl.bloquants:
        _p("\n  %sRien n'a été écrit.%s" % (J, X))
        return 2
    if not appliquer:
        _p("\n  %sRien n'a été écrit.%s Relance avec %s--apply%s%s pour agir." % (
            J, X, B, X, " --agents-arretes" if pl.bouge else ""))
        if pl.bouge:
            _p("  %sQuelque chose bouge : arrêter d'abord TOUTES les sessions de ce projet.%s" % (D, X))
        return 0
    if pl.bouge and not arretes:
        _p("\n  %sREFUSÉ%s — quelque chose bouge : arrêter toutes les sessions de ce projet, puis "
           "relancer avec %s--agents-arretes%s." % (R, X, B, X))
        return 2
    mal = applique(pl)
    _p()
    if mal:
        _p("  %s⚠ %d assertion(s) d'après ONT ÉCHOUÉ :%s" % (R, len(mal), X))
        for x in mal:
            _p("    · %s" % x)
        return 2
    _p("  %s✓ Fait.%s Relancer les agents un par un, puis "
       "`harnais equipe-vue --racine <atelier>`." % (V, X))
    return 0
