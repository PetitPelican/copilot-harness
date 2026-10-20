# -*- coding: utf-8 -*-
"""L'AGENT ACTIF — qui parle, quand le dossier ne le dit plus.

Port de `harnais/src/agent.rs` (Rust, 1.3.0). Mêmes noms de fonctions.

Sous le CLI, une session s'ouvrait DANS `agents/<nom>/` : le dossier de lancement
disait qui parlait, et tout le harnais le lisait là. L'app Copilot lance chaque
conversation à la RACINE d'une copie de travail, et l'agent se choisit dans un
menu du champ de saisie (les profils `.github/agents/<nom>.agent.md`). Aucun hook
ne reçoit ce choix, ni dans sa charge ni dans son environnement. Il est écrit
dans le JOURNAL DE SESSION de Copilot — mesuré dans l'app et dans le CLI 1.0.91-1 :

    ~/.copilot/session-state/<session_id>/events.jsonl
    {"type":"subagent.selected","data":{"agentName":"ops",…}}   un agent choisi
    {"type":"subagent.deselected","data":{}}                     « Default agent »

Écrit avant le premier hook, souvent deux fois de suite ; un nouveau à chaque
changement par le menu ; un nouveau en tête de la session qu'ouvre `/clear` ;
intact après `/compact`. Les sous-agents de l'outil task écrivent
`subagent.started|configured|completed`, avec un `agentId` à la racine, et jamais
`selected` : tout événement qui porte un `agentId` est ignoré quand même — un
sous-agent ne doit pas pouvoir changer l'agent de la session.

LA RÈGLE, dans cet ordre :

1. le dernier `selected` du journal désigne un agent du projet → lui (menu) ;
2. sinon le dossier de lancement est sous `agents/<nom>/` → lui (dossier) ;
3. sinon, un projet à plusieurs agents qui en a un nommé QA → QA (défaut) ;
4. sinon aucun agent, et le briefing le dit.

Un agent choisi dans le menu qui n'est pas un agent du projet n'est PAS le
« Default agent » : il ne prend pas QA, et le briefing le signale.

LE HARNAIS SE PLACE ALORS DANS LE DOSSIER DE L'AGENT : `COPILOT_PROJECT_DIR`
devient `<copie>/agents/<nom>`, comme si la session y avait été lancée. Les
modules qui lisent la position de l'agent — état, todo, garde de commit,
périmètre, journal, fin de tour — la lisent donc juste sans changer d'une ligne.
Ce que ce dossier ne dit PAS, le vrai dossier de la session, reste connu ici :
c'est depuis lui que se lisent les chemins relatifs d'un outil, et que
s'affichent les chemins du briefing.
"""
import json
import os
import re
import sys

# L'agent pris quand rien n'est choisi — décision de @user pour les projets à
# plusieurs agents. Il ne s'applique que si le projet a un agent de ce nom.
DEFAUT = "QA"

# Au-delà, le rôle servi par le briefing est coupé, et le briefing le dit.
ROLE_MAX_LIGNES = 250
ROLE_MAX_OCTETS = 16000

# Où un agent compact dépose ce qu'il produit : un dossier par agent, à la racine
# du projet, hors de `brain/` qui ne porte que la mémoire. Le nom de l'atelier
# (décision du 12/10/2026 : « on va l'appeler Assets pas outputs »), le même que
# celui du harnais Claude. C'est le SEUL endroit où ce chemin est écrit ; la garde
# de commit l'ignore comme `docs/` (un livrable en `.sql` n'est pas du code).
BANC = "assets"

# Les anciens emplacements, lus par la garde de commit seulement, pour qu'un
# projet pas encore migré garde ses livrables hors du code : `outputs/` (1.2 à
# 1.3) et `brain/workbench/` (0.19 à 1.1).
BANCS_ANCIENS = ("outputs", "brain/workbench")

# Ce qui fait tenir le harnais : profils, périmètres, réglages. Un agent n'y écrit
# pas : y toucher, c'est changer le rôle ou les limites d'un autre. Le reste de
# `.github/` (CI, MCP, modèles de PR…) appartient au projet.
CONTROLE = [".github/agents", ".github/copilot"]

MARQUE_ROLE = "<!-- harnais:role:start -->"


def banc(nom):
    return "%s/%s" % (BANC, nom)


# ── le journal de session ───────────────────────────────────────────────────

class Choix(object):
    """Ce que le journal dit du choix, ramené au dernier état.

    `genre` : "rien" (aucun `selected` ni `deselected` lisible), "agent" (un
    agent choisi, et la ligne où ce choix a COMMENCÉ — la première d'une suite
    d'événements identiques, pour que le doublon que l'app écrit au démarrage ne
    passe pas pour un changement), "retire" (« Default agent » choisi)."""
    __slots__ = ("genre", "nom", "ligne")

    def __init__(self, genre="rien", nom=None, ligne=0):
        self.genre, self.nom, self.ligne = genre, nom, ligne

    def __eq__(self, o):
        return isinstance(o, Choix) and (self.genre, self.nom, self.ligne) == (o.genre, o.nom, o.ligne)

    def __repr__(self):
        return "Choix(%r, %r, %r)" % (self.genre, self.nom, self.ligne)


class Lecture(object):
    __slots__ = ("chemin", "trouve", "lignes", "compactions", "choix")

    def __init__(self, chemin=None, trouve=False, lignes=0, compactions=0, choix=None):
        self.chemin, self.trouve, self.lignes = chemin, trouve, lignes
        # Les compactions terminées : chacune peut avoir effacé le briefing du
        # contexte, le briefing doit donc repartir après.
        self.compactions = compactions
        self.choix = choix if choix is not None else Choix()

    def etat(self):
        """Ce qu'on a lu, dit en une phrase — c'est aussi la sonde qui répond à
        « l'événement était-il sur le disque quand le hook a lu ? »."""
        if self.chemin is None:
            return "pas d'identifiant de session : journal non lu"
        if not self.trouve:
            return "journal de session introuvable"
        return "journal de session : %d ligne(s) lue(s)" % self.lignes


_ID_SAIN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def chemin_journal(charge, maison_copilot):
    """Le journal de la session : `transcript_path` quand la charge le donne (fin
    de tour), sinon `<COPILOT_HOME>/session-state/<session_id>/events.jsonl`. Un
    identifiant qui n'a pas la forme d'un nom de dossier n'est pas suivi : il ne
    compose jamais un chemin."""
    t = charge.get("transcript_path")
    if isinstance(t, str) and t.strip():
        return t
    i = charge.get("session_id")
    if not isinstance(i, str):
        return None
    i = i.strip()
    if not _ID_SAIN.match(i):
        return None
    return os.path.join(maison_copilot, "session-state", i, "events.jsonl")


def lis_journal(chemin):
    """LE DERNIER CHOIX D'AGENT DU JOURNAL. Lu en entier, une ligne à la fois : le
    choix est en tête du fichier, et un changement peut tomber n'importe où.
    Seules les lignes qui portent `subagent.` ou `compaction_complete` sont
    décodées — ces journaux font des dizaines de Mo."""
    l = Lecture(chemin=chemin)
    try:
        f = open(chemin, "rb")
    except OSError:
        return l
    l.trouve = True
    with f:
        for brut in f:
            l.lignes += 1
            if b"subagent." not in brut and b"compaction_complete" not in brut:
                continue
            try:
                e = json.loads(brut.decode("utf-8", "replace").strip())
            except ValueError:
                continue
            if not isinstance(e, dict):
                continue
            if e.get("agentId") is not None:
                continue
            ty = e.get("type")
            if ty == "session.compaction_complete":
                l.compactions += 1
            elif ty == "subagent.selected":
                d = e.get("data")
                nom = d.get("agentName") if isinstance(d, dict) else None
                nom = nom.strip() if isinstance(nom, str) else ""
                if not nom:
                    continue
                if not (l.choix.genre == "agent" and l.choix.nom == nom):
                    l.choix = Choix("agent", nom, l.lignes)
            elif ty == "subagent.deselected":
                if l.choix.genre != "retire":
                    l.choix = Choix("retire", None, l.lignes)
    return l


# ── les agents du projet ─────────────────────────────────────────────────────

def nom_de_profil(dossier):
    """Le nom de profil d'un agent : celui que `harnais equipe` écrit dans
    `.github/agents/<nom>.agent.md` — le dossier slugifié, en minuscules."""
    import equipe
    return equipe.slug(dossier).lower().strip("-")


def profil(arbre, nom):
    return os.path.join(str(arbre), ".github", "agents", "%s.agent.md" % nom_de_profil(nom))


def perimetre_compact(arbre, nom):
    return os.path.join(str(arbre), ".github", "copilot", "perimetres", "%s.json" % nom_de_profil(nom))


def agents_du_projet(arbre):
    """LES AGENTS DU PROJET : les dossiers de `agents/` qui ont un ESPRIT — dans le
    cerveau (`brain/mind/<nom>/`), en place (`agents/<nom>/.mind/`) ou déporté. Un
    dossier `agents/` de code n'en a pas : un projet mono qui en porte un reste
    mono, et personne n'est placé dedans."""
    arbre = str(arbre)
    v = []
    try:
        noms = os.listdir(os.path.join(arbre, "agents"))
    except OSError:
        noms = []
    for n in noms:
        if n.startswith(".") or not os.path.isdir(os.path.join(arbre, "agents", n)):
            continue
        if (os.path.isdir(os.path.join(arbre, "brain", "mind", n))
                or os.path.isdir(os.path.join(arbre, "agents", n, ".mind"))
                or os.path.isdir(os.path.join(arbre, "memoire", "agents", n, ".mind"))):
            v.append(n)
    try:
        esprits = os.listdir(os.path.join(arbre, "brain", "mind"))
    except OSError:
        esprits = []
    for n in esprits:
        if os.path.isdir(os.path.join(arbre, "brain", "mind", n)) and os.path.isfile(profil(arbre, n)) \
                and n not in v:
            v.append(n)
    # ÉQUIPE « UN DOSSIER PAR AGENT » : l'arbre EST la mémoire de l'équipe, et chaque
    # dossier de `agents/` qui porte un état (`state.md`) est un agent. C'est ce qui
    # fait apparaître l'agent choisi dans le menu à la racine de l'équipe (le harnais
    # se place alors dans `agents/<nom>/`). Seulement quand `arbre` est cette racine :
    # dans la copie du code d'un agent, le résolveur le place déjà par sa position.
    import memoire
    eq = memoire.porteur_equipe(arbre)
    if eq is not None and eq[1] == "" and _meme(eq[0], arbre):
        try:
            noms_eq = sorted(os.listdir(os.path.join(arbre, "agents")))
        except OSError:
            noms_eq = []
        for n in noms_eq:
            if (not n.startswith(".") and n not in v
                    and os.path.isfile(os.path.join(arbre, "agents", n, "state.md"))):
                v.append(n)
    v.sort()
    return v


def _lis(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def compact(arbre, nom):
    t = _lis(profil(arbre, nom))
    return (os.path.exists(perimetre_compact(arbre, nom))
            or (t is not None and MARQUE_ROLE in t)
            or (not os.path.isdir(os.path.join(str(arbre), "agents", nom))
                and os.path.isfile(profil(arbre, nom))))


def contexte(arbre, nom):
    """Le contexte du hook n'est pas le dossier de travail de Copilot."""
    if compact(arbre, nom):
        return os.path.join(str(arbre), "brain", "mind", nom)
    return os.path.join(str(arbre), "agents", nom)


def correspond(nom, agents):
    """Le dossier d'agent que désigne un nom choisi dans le menu — à la casse
    près, ou par son nom de profil."""
    n = nom.strip().lower()
    if not n:
        return None
    for a in agents:
        if a.lower() == n:
            return a
    for a in agents:
        if nom_de_profil(a) == n:
            return a
    return None


# ── la résolution ────────────────────────────────────────────────────────────

class Source(object):
    """D'où vient l'agent actif : "menu", "dossier", "defaut", "inconnu", "aucun".
    `ligne` : la ligne du journal (menu, inconnu ; défaut si « Default agent » a
    été choisi explicitement, sinon None). `nom` : le nom inconnu."""
    __slots__ = ("genre", "ligne", "nom")

    def __init__(self, genre, ligne=None, nom=None):
        self.genre, self.ligne, self.nom = genre, ligne, nom

    def __eq__(self, o):
        return isinstance(o, Source) and (self.genre, self.ligne, self.nom) == (o.genre, o.ligne, o.nom)

    def __repr__(self):
        if self.genre == "menu":
            return "Menu { ligne: %d }" % self.ligne
        if self.genre == "dossier":
            return "Dossier"
        if self.genre == "defaut":
            return "Defaut { ligne: %s }" % ("Some(%d)" % self.ligne if self.ligne is not None else "None")
        if self.genre == "inconnu":
            return "Inconnu { nom: %s, ligne: %d }" % (json.dumps(self.nom, ensure_ascii=False), self.ligne)
        return "Aucun"


class Session(object):
    __slots__ = ("reel", "arbre", "agents", "actif", "source", "lecture", "place")

    def __init__(self, reel, arbre, agents, lecture):
        self.reel = reel            # le dossier de lancement déclaré par l'hôte
        self.arbre = arbre          # la racine de la copie de travail courante
        self.agents = agents        # les agents du projet ; vide : projet mono
        self.actif = None           # le nom du dossier de l'agent actif
        self.source = Source("aucun")
        self.lecture = lecture
        self.place = None           # le dossier où le harnais s'est placé, s'il n'est pas `reel`

    def signature(self):
        """Ce qui doit faire repartir le briefing quand il change : l'agent, d'où
        il vient, la ligne où ce choix a commencé, et les compactions. Le nombre
        de lignes lues n'y est PAS : il change à chaque tour."""
        g = self.source.genre
        ligne = self.source.ligne if self.source.ligne is not None else 0
        if g == "dossier" or g == "aucun":
            ligne = 0
        return "agent=%s|%s|%d|compactions=%d" % (self.actif or "-", g, ligne, self.lecture.compactions)


_SESSION = [None]


def session():
    """La session résolue par `pose()`, ou None hors hook."""
    return _SESSION[0]


def resous(reel, lecture):
    """LA RÉSOLUTION — pure : le dossier de lancement, ce que le journal dit."""
    import memoire
    reel = str(reel)
    a = memoire.arbre_courant(reel)
    arbre = None
    if a is not None:
        try:
            arbre = os.path.realpath(a)
        except (OSError, ValueError):
            arbre = a
    agents = agents_du_projet(arbre) if arbre is not None else []
    s = Session(reel, arbre, list(agents), lecture)
    if arbre is None or not agents:
        return s
    l = memoire.lot(reel)
    dossier = l.rsplit("/", 1)[1] if "/" in l else None
    if dossier is not None and dossier not in agents:
        dossier = None
    c = s.lecture.choix
    if c.genre == "agent":
        a = correspond(c.nom, agents)
        if a is not None:
            s.actif, s.source = a, Source("menu", c.ligne)
        else:
            s.actif, s.source = dossier, Source("inconnu", c.ligne, c.nom)
    else:
        ligne = c.ligne if c.genre == "retire" else None
        if dossier is not None:
            s.actif, s.source = dossier, Source("dossier")
        else:
            q = correspond(DEFAUT, agents)
            if q is not None:
                s.actif, s.source = q, Source("defaut", ligne)
    # Se placer, sauf si la session est DÉJÀ dans ce dossier.
    if s.actif is not None and s.source.genre in ("menu", "defaut") and dossier != s.actif:
        cible = contexte(arbre, s.actif)
        if os.path.isdir(cible):
            s.place = cible
    return s


def pose(charge):
    """APPELÉE PAR `hote.prepare`, une fois par hook : résout l'agent actif et, au
    besoin, place le harnais dans son dossier. Fail-open : sans dépôt, sans
    journal, sans agents, rien ne bouge."""
    if _SESSION[0] is not None:
        return
    import hote
    reel = os.environ.get("COPILOT_PROJECT_DIR") or None
    if reel is None:
        c = charge.get("cwd")
        reel = c if (isinstance(c, str) and c) else None
    if reel is None:
        return
    j = chemin_journal(charge, hote.maison_copilot())
    lecture = lis_journal(j) if j is not None else Lecture()
    s = resous(reel, lecture)
    if s.place is not None:
        os.environ["COPILOT_PROJECT_DIR"] = s.place
    _SESSION[0] = s


def _meme(a, b):
    try:
        if os.path.realpath(a) == os.path.realpath(b):
            return True
    except (OSError, ValueError):
        pass
    return str(a) == str(b)


def ancre_affichage(r):
    """D'où s'affichent les chemins du briefing : le VRAI dossier de la session
    quand le harnais s'est placé ailleurs — un chemin relatif au dossier de
    l'agent ne s'ouvrirait pas depuis la racine où l'agent travaille."""
    s = session()
    if s is not None and s.place is not None and _meme(s.place, r):
        try:
            return os.path.realpath(s.reel)
        except (OSError, ValueError):
            return s.reel
    return r


def role(dossier):
    """Le rôle d'un agent, tel qu'il est écrit — `AGENTS.md`, ou à défaut
    `CLAUDE.md`. None si aucun des deux n'existe."""
    for n in ("AGENTS.md", "CLAUDE.md"):
        p = os.path.join(str(dossier), n)
        if os.path.isfile(p):
            return p, (_lis(p) or "")
    return None


def _lignes(t):
    """`str::lines` de Rust : `\\n` ou `\\r\\n`, sans ligne vide finale."""
    out = t.split("\n")
    if out and out[-1] == "":
        out.pop()
    return [x[:-1] if x.endswith("\r") else x for x in out]


def borne(t):
    """Coupe un rôle trop long, et le dit : (texte, coupé ?)."""
    out = []
    taille = 0
    for i, ligne in enumerate(_lignes(t)):
        n = len(ligne.encode("utf-8"))
        if i >= ROLE_MAX_LIGNES or taille + n + 1 > ROLE_MAX_OCTETS:
            return "".join(out), True
        out.append(ligne + "\n")
        taille += n + 1
    return "".join(out), False


def _sans_entete(t):
    """Le corps d'un profil `.agent.md`, sans son en-tête `---`."""
    for debut, fin in (("---\r\n", "\r\n---\r\n"), ("---\n", "\n---\n")):
        if t.startswith(debut):
            reste = t[len(debut):]
            i = reste.find(fin)
            if i >= 0:
                return reste[i + len(fin):]
    return t


def lignes_briefing(s):
    """LES LIGNES DU BRIEFING SUR L'AGENT — (en tête, en fin).

    En tête, une ligne qui dit QUI parle et D'OÙ on le sait. En fin, le RÔLE,
    relu à l'instant, quand Copilot ne l'a pas chargé de lui-même : une session
    lancée à la racine ne lit pas `agents/<nom>/AGENTS.md`, et un profil qui
    demande au modèle de l'ouvrir laisse la lecture à sa bonne volonté — mesuré.
    Le briefing MONTRE, il ne pointe pas."""
    import socle
    tete, fin = [], []
    if not s.agents:
        return tete, fin
    menu = "le menu d'agent du champ de saisie"
    liste = ", ".join(s.agents)
    g = s.source.genre
    if g == "menu":
        tete.append("agent  : %s — choisi dans %s (journal de session, ligne %d)."
                    % (s.actif or "?", menu, s.source.ligne))
    elif g == "dossier":
        tete.append("agent  : %s — la session est lancée dans son dossier." % (s.actif or "?"))
    elif g == "defaut":
        if s.source.ligne is not None:
            pourquoi = "« Default agent » est choisi dans %s (journal de session, ligne %d)" % (
                menu, s.source.ligne)
        else:
            pourquoi = "aucun agent n'est choisi dans %s (%s)" % (menu, s.lecture.etat())
        tete.append("agent  : %s — l'agent PAR DÉFAUT de ce projet : %s." % (s.actif or "?", pourquoi))
        autres = [a for a in s.agents if a != s.actif]
        tete.append("         Tu tiens ce rôle et ce périmètre. Pour un autre agent (%s), "
                    "@user le choisit dans le menu." % ", ".join(autres))
    elif g == "inconnu":
        tete.append("agent  : « %s », choisi dans %s (journal de session, ligne %d), "
                    "n'est pas un agent de ce projet (%s)." % (s.source.nom, menu, s.source.ligne, liste))
        if s.actif is not None:
            tete.append("         Le dossier de lancement garde l'agent %s." % s.actif)
        else:
            tete.append("         Aucun lot ne s'applique : ni état d'agent, ni périmètre — RIEN n'est gardé.")
    else:
        tete.append("agent  : AUCUN — rien n'est choisi dans %s (%s), et ce projet n'a pas "
                    "d'agent %s par défaut." % (menu, s.lecture.etat(), DEFAUT))
        tete.append("         Aucun lot ne s'applique : ni état d'agent, ni périmètre — RIEN n'est "
                    "gardé. Les agents : %s." % liste)
    # Le rôle n'est servi que si la session n'est PAS dans le dossier de
    # l'agent : là, Copilot le charge déjà, et le servir deux fois le paierait
    # deux fois.
    if s.actif is None or s.arbre is None:
        return tete, fin
    a, arbre = s.actif, s.arbre
    est_compact = compact(arbre, a)
    if s.place is None and not est_compact:
        return tete, fin
    if est_compact and g == "menu":
        p = profil(arbre, a)
        if os.path.isfile(p):
            tete.append("         Rôle : %s — profil choisi dans le menu ; non recopié par le briefing."
                        % socle.chemin_affiche(s.reel, p))
        else:
            tete.append("         Rôle ABSENT : %s ; restaurer le profil avant de travailler." % p)
        return tete, fin
    dossier = contexte(arbre, a)
    try:
        base = os.path.realpath(s.reel)
    except (OSError, ValueError):
        base = s.reel

    def affiche(p):
        return socle.chemin_affiche(base, p)

    role_actif = None
    if est_compact:
        p = profil(arbre, a)
        try:
            with open(p, encoding="utf-8") as f:
                t = f.read()
            role_actif = (p, _sans_entete(t))
        except (OSError, UnicodeDecodeError) as e:
            tete.append("         Profil illisible : %s : %s" % (p, e))
    else:
        role_actif = role(dossier)
    if role_actif is not None:
        p, t = role_actif
        texte, coupe = borne(t)
        fin.append("── Ton rôle · %s — relu à l'instant ──" % affiche(p))
        fin.extend(_lignes(texte))
        if coupe:
            fin.append("[… coupé à %d lignes ou %d octets : la suite est dans %s]"
                       % (ROLE_MAX_LIGNES, ROLE_MAX_OCTETS, affiche(p)))
        fin.append("── fin du rôle ──")
    else:
        tete.append("         Rôle ABSENT : ni AGENTS.md ni CLAUDE.md dans %s — ce rôle "
                    "n'est écrit nulle part." % affiche(dossier))
    return tete, fin


def main(args):
    """`harnais agent` — QUI PARLE, ET D'OÙ JE LE SAIS. Lecture seule.

        harnais agent [--session <id> | --journal <events.jsonl>] [--racine <dossier>]
    """
    import hote
    if "-h" in args or "--help" in args:
        print("harnais agent [--session <id> | --journal <events.jsonl>] [--racine <dossier>]\n\n"
              "L'agent actif tel que les hooks le résolvent : le journal de session lu, le choix trouvé,\n"
              "la règle appliquée (menu, dossier, défaut %s) et le dossier où le harnais se place.\n"
              "Lecture seule." % DEFAUT)
        return 0

    def valeur(cle):
        if cle in args:
            i = args.index(cle)
            if i + 1 < len(args):
                return args[i + 1]
        return None

    racine = valeur("--racine") or os.getcwd()
    charge = {}
    if valeur("--journal") is not None:
        charge["transcript_path"] = valeur("--journal")
    if valeur("--session") is not None:
        charge["session_id"] = valeur("--session")
    j = chemin_journal(charge, hote.maison_copilot())
    lecture = lis_journal(j) if j is not None else Lecture()
    s = resous(racine, lecture)
    print("journal : %s" % (s.lecture.chemin if s.lecture.chemin is not None
                            else "(aucun : ni --session ni --journal)"))
    print("lu      : %s" % s.lecture.etat())
    c = s.lecture.choix
    if c.genre == "rien":
        print("choix   : aucun `subagent.selected` ni `deselected`")
    elif c.genre == "agent":
        print("choix   : « %s », ligne %d" % (c.nom, c.ligne))
    else:
        print("choix   : « Default agent », ligne %d" % c.ligne)
    print("compact.: %d" % s.lecture.compactions)
    print("agents  : %s" % (", ".join(s.agents) if s.agents
                            else "aucun (projet à un agent, ou pas de dépôt)"))
    print("actif   : %s" % (s.actif or "aucun"))
    print("source  : %r" % s.source)
    print("placé   : %s" % (s.place if s.place is not None
                            else "non — le dossier de lancement est gardé"))
    return 0
