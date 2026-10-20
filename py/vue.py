# -*- coding: utf-8 -*-
"""LA VUE D'ÉQUIPE — lit la mémoire de tous les projets d'un atelier et en rend
deux vues : le rapport terminal (le DIAGNOSTIC) et une page autonome (la VUE).

Port de `harnais/src/vue.rs` (Rust, Copilot 1.3.0), à l'octet : le Rust reste
la spécification. Il avait été porté de `agentic-team.py`.

    harnais equipe-vue                     le rapport terminal
    harnais equipe-vue --html team.html    une page autonome
    harnais equipe-vue --projet <nom>      un seul projet

**Une seule lecture, deux sorties** : deux analyseurs se désaccorderaient
sans que personne le voie. **Strictement en lecture** : n'écrit que la page
demandée. La page est **autonome** — ni serveur, ni ressource externe.

LA LECTURE A ÉTÉ REFAITE, et c'est dit : le script lisait l'organisation
d'avant, et des réglages qui ne veulent plus rien dire depuis le paquet. Le
garder à l'octet classerait des projets « aucune mémoire » alors qu'ils sont
servis, et donnerait des conseils qui renvoient à deux compétences
disparues (la mise à niveau et la synchronisation d'avant le paquet). Un
tableau de bord qui désigne presque tout l'atelier comme à refaire est pire
qu'aucun tableau : on apprend à ne plus le lire.

CE QU'IL LIT DÉSORMAIS, et d'où :
· la mémoire, PAR LE RÉSOLVEUR — la même règle que le briefing, toutes les
  formes, jamais un chemin recomposé ;
· le PAQUET, dans le dossier d'où chaque agent se LANCE : la racine en mono,
  `agents/<nom>` à plusieurs — les réglages de la racine y sont inertes ;
· trois choses séparées, parce que chacune peut manquer seule et en silence :
  le paquet DÉCLARÉ, la marketplace INSCRITE (sans quoi Copilot ne le
  charge pas), et la TRACE D'ENTRÉE qui prouve qu'il a servi, avec la
  version qui l'a écrite — toutes copies de travail confondues : un agent
  peut se lancer depuis une copie, et l'arbre principal n'a alors de lui
  qu'une trace ancienne.
"""
import datetime
import json
import os
import re
import sys
import time

import agent
import briefing
import copilot
import hote
import memoire
import socle

CHAMPS = ["maj", "cap", "sante", "jalon", "balle", "depuis", "attente", "suivant"]
MIND_ATTENDU = ["state.md", "todo.md"]
# La taxonomie d'avant, rangée dans `.memory/`.
ANCIENS = ["charter.md", "business.md", "clients.md", "overview.md"]
MONTENT = ["state.md", "rules.md", "architecture.md"]
# `copilot-harness` est la SOURCE du paquet, pas un agent : lui conseiller
# `harnais adopte`, ce serait brancher le paquet sur son propre code.
IGNORE = ["copilot-harness"]
DEHORS = "dehors"
TIEDE_JOURS = 7
PERIME_JOURS = 28

# Les blancs de Rust (`char::is_whitespace`, propriété White_Space) : `\s` de
# Python en ajoute quatre (U+001C..U+001F).
_BLANCS = "\t\n\x0b\x0c\r \x85\xa0                　"
_S = "[" + _BLANCS + "]"

_ENTETE_RE = re.compile(r"\A" + _S + r"*---" + _S + r"*\n(.*?)\n---" + _S + r"*(\n|\Z)", re.S)
_TACHE_RE = re.compile(r"^" + _S + r"*[-*]" + _S + r"*\[( |x|X|>|~)\]" + _S + r"+(.+?)" + _S + r"*\Z")
_PRIO_RE = re.compile(r"!(haut|moyen|bas)\b")
_CHANTIERS_RE = re.compile(r"^#{1,3}" + _S + r"*chantiers\b.*$", re.I | re.M)
_IMPORT_RE = re.compile(r"^@(\S+)", re.M)
# Le `@` doit ouvrir un mot — sinon `root@serveur` serait lu comme un
# destinataire nommé « serveur ».
_QUI_RE = re.compile(r"(?:^|(?<=" + _S + r"))@([A-Za-zÀ-ÿ][\w-]*)\b")


def lis(p):
    try:
        with open(p, "rb") as f:
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def nom(p):
    return os.path.basename(p.rstrip("/")) if p != "/" else ""


def lignes(s):
    """`str::lines` de Rust : coupe sur `\\n`, retire le `\\r` d'un `\\r\\n`."""
    if not s:
        return []
    v = s.split("\n")
    fin = v.pop()
    out = [x[:-1] if x.endswith("\r") else x for x in v]
    if fin != "":
        out.append(fin)
    return out


def est_dir(p):
    return os.path.isdir(p)


def est_fichier(p):
    return os.path.isfile(p)


def canon(p):
    """`Path::canonicalize` : le chemin lui-même quand il n'existe pas."""
    try:
        if os.path.exists(p):
            return os.path.realpath(p)
    except OSError:
        pass
    return p


def _cle(p):
    """Un chemin comparé comme `PathBuf` : sans barres doublées ni barre finale."""
    c = re.sub("/+", "/", p)
    if len(c) > 1:
        c = c.rstrip("/")
    if os.name == "nt":
        # Sous Windows, git rend `C:/x`, le système `C:\x`, et la casse ne
        # distingue rien : un même dossier aurait deux clés, et un agent
        # inscrit passerait pour « non inscrit » (mesuré par la CI Windows).
        if c.startswith("\\\\?\\"):
            c = c[4:]
        c = os.path.normcase(os.path.normpath(c))
    return c


def trie(d):
    try:
        v = [os.path.join(d, n) for n in os.listdir(d)]
    except OSError:
        return []
    v.sort(key=lambda p: os.path.basename(p).encode("utf-8", "surrogateescape"))
    return v


def md_de(d, ext):
    v = []
    for p in trie(d):
        n = os.path.basename(p)
        base, e = os.path.splitext(n)
        if base and e == "." + ext:
            v.append(n)
    v.sort(key=lambda n: n.encode("utf-8", "surrogateescape"))
    return v


def coupe(s, n):
    """Tranche en CARACTÈRES, comme `s[:n]` en Python — jamais au milieu d'un octet."""
    return s[:n]


def gauche(s, n):
    l = len(s)
    return s if l >= n else s + " " * (n - l)


def entete(texte):
    """L'en-tête : un dict (l'ordre d'insertion est celui du Rust)."""
    m = _ENTETE_RE.match(texte)
    d = {}
    if m is None:
        return d
    for ligne in lignes(m.group(1)):
        if ":" in ligne:
            k, v = ligne.split(":", 1)
            k = k.strip(_BLANCS).lower()
            if k in CHAMPS:
                d[k] = v.strip(_BLANCS)
    return d


class Tache(object):
    __slots__ = ("etat", "titre", "prio", "qui")

    def __init__(self, etat, titre, prio, qui):
        self.etat, self.titre, self.prio, self.qui = etat, titre, prio, qui


def taches(texte):
    """Le fichier ENTIER, toutes sections confondues : une version antérieure ne
    lisait que la section « Chantiers » et rendait zéro tâche sur des fichiers
    pleins. Le titre reste reconnu, pour les anciens fichiers qui la bornaient."""
    if not texte:
        return []
    ms = list(_CHANTIERS_RE.finditer(texte))
    if ms:
        fin = ms[1].start() if len(ms) > 1 else len(texte)
        corps = texte[ms[0].end():fin]
    else:
        corps = texte
    out = []
    for ligne in lignes(corps):
        t = _TACHE_RE.match(ligne)
        if t is None:
            continue
        titre = t.group(2)
        p = _PRIO_RE.search(titre)
        prio = p.group(1) if p else ""
        q = _QUI_RE.search(titre)
        qui_ = q.group(1) if q else ""
        sans_qui = _QUI_RE.sub("", titre)
        net = _PRIO_RE.sub("", sans_qui)
        net = net.strip(" -—·")
        c = t.group(1)
        etat = "fait" if c in ("x", "X") else ("encours" if c in (">", "~") else "afaire")
        out.append(Tache(etat, net, prio, qui_))
    return out


def _date(maj):
    """`%Y-%m-%d`, sinon `%Y%m%d`, comme chrono : chiffres ASCII, avide, sans retour en arrière."""
    def nombre(s, i, largeur):
        j = i
        while j < len(s) and j - i < largeur and "0" <= s[j] <= "9":
            j += 1
        return (int(s[i:j]), j) if j > i else (None, i)
    for forme in ("-", ""):
        i = 0
        a, i = nombre(maj, i, 4)
        if a is None:
            continue
        if forme:
            if maj[i:i + 1] != forme:
                continue
            i += 1
        m, i = nombre(maj, i, 2)
        if m is None:
            continue
        if forme:
            if maj[i:i + 1] != forme:
                continue
            i += 1
        j, i = nombre(maj, i, 2)
        if j is None or i != len(maj):
            continue
        try:
            return datetime.date(a, m, j)
        except ValueError:
            continue
    return None


def fraicheur(maj, aujourdhui):
    d = _date(maj)
    if d is None:
        return ("illisible", None)
    j = (aujourdhui - d).days
    if j > PERIME_JOURS:
        return ("perime", j)
    if j > TIEDE_JOURS:
        return ("tiede", j)
    return ("frais", j)


class Lancement(object):
    """Un dossier d'où un agent se LANCE — la racine en mono, `agents/<nom>` à
    plusieurs. Ses réglages et sa trace d'entrée vivent là."""
    __slots__ = ("nom", "declare", "inscrit", "inscrite", "trace", "deny")

    def __init__(self, nom, declare, inscrit, inscrite, trace, deny):
        self.nom = nom
        # `paquet` · `non`
        self.declare = declare
        # None : les inscriptions n'ont pas pu être lues — on ne conclut rien.
        self.inscrit = inscrit
        # La version que cette inscription chargera au prochain démarrage.
        self.inscrite = inscrite
        # La plus récente, toutes copies de travail confondues : (version, instant).
        # Une trace sans version a été écrite avant la 0.10.0.
        self.trace = trace
        self.deny = deny


class Harnais(object):
    __slots__ = ("git", "depot", "forme", "fact_dir", "fact", "minds", "mind", "manque",
                 "surplus", "anciens", "lancements", "oriente", "logs", "dispersion")


class Illisibles(object):
    pass


class Toutes(object):
    def __init__(self, version):
        self.version = version


class Chemins(object):
    def __init__(self, entrees):
        self.entrees = entrees  # [(chemin, version)]


def inscriptions():
    """Les inscriptions au paquet, lues UNE fois par relevé, dans les réglages de
    l'utilisateur (`<COPILOT_HOME>/settings.json`)."""
    f = os.path.join(hote.maison_copilot(), "settings.json")
    if not os.path.exists(f):
        return Chemins([])
    try:
        v = json.loads(lis(f))
    except ValueError:
        return Illisibles()
    actif = _obj(_obj(v, "enabledPlugins"), copilot.PAQUET) is True
    return Toutes(None) if (actif and resolu(v)) else Chemins([])


def resolu(v):
    """La marketplace locale est-elle résolue : un dossier déclaré qui porte le
    manifeste du paquet, ou le paquet installé par Copilot ?"""
    src = _obj(_obj(_obj(v, "extraKnownMarketplaces"), copilot.MARCHE), "source")
    local = False
    if isinstance(src, dict) and src.get("source") == "directory":
        chemin = src.get("path")
        local = isinstance(chemin, str) and est_fichier(os.path.join(chemin, ".github/plugin/plugin.json"))
    return local or est_dir(os.path.join(hote.maison_copilot(), "installed-plugins/atelier-copilot/harnais"))


def copies(p):
    """Les copies de travail du dépôt qui porte `p`, `p` compris.

    Un agent peut se lancer depuis une copie de travail (par exemple
    `.worktrees/<nom>`) ; l'arbre principal n'a alors de lui qu'une trace
    ancienne. Ne lire que l'arbre principal, ce serait crier « jamais servi »
    sur un agent qui tourne."""
    v = [p]
    import subprocess
    try:
        o = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=p,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return v
    if o.returncode != 0:
        return v
    for l in lignes(o.stdout.decode("utf-8", "replace")):
        if l.startswith("worktree "):
            w = canon(l[len("worktree "):])
            if not any(_cle(w) == _cle(x) for x in v):
                v.append(w)
    return v


def maintenant_s():
    return time.time()


def jours_depuis(t):
    return int(max((maintenant_s() - t) // 86400.0, 0.0))


def _relatif(p, l):
    """`l.strip_prefix(p)`, par composants ; vide si `l` n'est pas sous `p`."""
    pc, lc = _cle(p), _cle(l)
    if lc == pc:
        return ""
    sep = "\\" if os.name == "nt" else "/"
    pre = pc if pc.endswith(sep) else pc + sep
    if not lc.startswith(pre):
        return ""
    # La fin du chemin D'ORIGINE, pas de la clé : sous Windows la clé est en
    # minuscules, et un dossier doit garder le nom qu'on lui a donné.
    brut = l
    if os.name == "nt":
        if brut.startswith("\\\\?\\"):
            brut = brut[4:]
        brut = os.path.normpath(brut)
    else:
        brut = re.sub("/+", "/", brut)
        if len(brut) > 1:
            brut = brut.rstrip("/")
    return brut[len(brut) - (len(lc) - len(pre)):]


def _obj(v, k):
    return v.get(k) if isinstance(v, dict) else None


def lancement(p, l, nom_, cps, ins):
    rel = _relatif(p, l)
    jumeaux = [c for c in (os.path.join(c, rel) if rel else c for c in cps) if est_dir(c)]
    declare = "non"
    try:
        local = json.loads(lis(copilot.settings(p)))
    except ValueError:
        local = None
    if _obj(_obj(local, "enabledPlugins"), copilot.PAQUET) is True:
        declare = "paquet"
    try:
        copilot.lis_allow(l)
        deny = len(copilot.perimetre(l))
    except (copilot.Refus, OSError):
        deny = None
    if isinstance(ins, Illisibles):
        inscrit, inscrite = None, None
    elif isinstance(ins, Toutes):
        inscrit, inscrite = True, ins.version
    else:
        j = [_cle(canon(x)) for x in jumeaux]
        inscrit, inscrite = False, None
        for (c, v) in ins.entrees:
            if _cle(canon(c)) in j:
                inscrit, inscrite = True, v
                break
    if declare == "paquet" and inscrit is not True:
        try:
            globales = json.loads(lis(os.path.join(hote.maison_copilot(), "settings.json")))
        except ValueError:
            globales = None
        if (local is not None and resolu(local)) or (globales is not None and resolu(globales)):
            inscrit, inscrite = True, None
    trace = None
    for j in jumeaux:
        try:
            v = json.loads(lis(briefing.etat_du_briefing(j)))
        except ValueError:
            continue
        d = _obj(v, "derniere")
        if isinstance(d, bool) or not isinstance(d, (int, float)):
            continue
        ver = _obj(v, "version")
        cand = (ver if isinstance(ver, str) else None, float(d))
        # `max_by` rend le DERNIER des égaux.
        if trace is None or cand[1] >= trace[1]:
            trace = cand
    return Lancement(nom_, declare, inscrit, inscrite, trace, deny)


def harnais(p, ins):
    p = canon(p)
    agents = [agent.contexte(p, n) for n in agent.agents_du_projet(p)]
    if not agents:
        dossiers = [(None, p)]
    else:
        dossiers = [(nom(d), d) for d in agents]
    r = memoire.resous(dossiers[0][1])
    anciens = [n for n in ANCIENS + MONTENT if est_fichier(os.path.join(p, ".memory", n))]
    F = memoire.Forme
    if r.forme == F.Equipe:
        forme = "equipe"
    elif r.forme == F.Brain:
        forme = "brain"
    elif r.forme == F.EnPlace:
        forme = "en-place"
    elif r.forme == F.Deportee:
        forme = "deportee"
    elif r.forme == F.Ambigue:
        forme = "ambigue"
    else:
        if anciens:
            forme = "ancienne"
        elif est_dir(os.path.join(p, ".mind")):
            forme = "mind-seul"
        else:
            forme = "aucune"
    manque, surplus = [], []

    def aff(d):
        return socle.chemin_affiche(p, d) + "/"
    fact = []
    # Les cinq noms, mono et équipe confondus (le `socle::faits_tous` du Rust).
    faits_tous = socle.FAITS_MONO + [socle.FAITS_EQUIPE]
    if r.fact is not None:
        d = r.fact
        ici = md_de(d, "md") if est_dir(d) else []
        for a in socle.FAITS_MONO:
            if a not in ici:
                manque.append(aff(d) + a)
        for x in ici:
            if x not in faits_tous:
                surplus.append(aff(d) + x)
        fact = ici
    minds, mind = [], []
    for (_, l) in dossiers:
        m = memoire.resous(l).mind
        if m is None:
            continue
        ici = md_de(m, "md") if est_dir(m) else []
        for a in MIND_ATTENDU:
            if a not in ici:
                manque.append(aff(m) + a)
        for x in ici:
            # En équipe, le dossier de l'agent porte aussi son RÔLE (COPILOT :
            # `AGENTS.md`, ou le `CLAUDE.md` d'une équipe mixte).
            if x not in MIND_ATTENDU and not (forme == "equipe" and x in ("AGENTS.md", "CLAUDE.md")):
                surplus.append(aff(m) + x)
        mind.extend(aff(m) + x for x in ici)
        if est_dir(m):
            minds.append(m)
    # Une mémoire que le résolveur ne sert pas garde un état LISIBLE : le
    # tableau le montre, pour que « à trier » dise aussi depuis quand.
    if not minds:
        for c in (".mind", ".memory"):
            m = os.path.join(p, c)
            if est_fichier(os.path.join(m, "state.md")):
                minds.append(m)
                break
    # Les instructions du projet (`AGENTS.md`, ou un `CLAUDE.md` que Copilot lit
    # aussi) nomment-elles la mémoire ? Les `@imports` comptent. Depuis le
    # briefing c'est une information, plus un verdict : le harnais sert
    # l'index de la mémoire à l'entrée, qu'il la nomme ou non.
    #
    # LES ÉTAGES DU DESSUS COMPTENT (Claude 0.17.0). Les consignes vont en quatre
    # étages et rien n'est répété : le renvoi vers `brain/` vit dans le fichier
    # COMMUN, au-dessus des projets, et celui du projet ne le redit plus. Ne lire
    # que celui du projet affichait « NON » partout où la règle est suivie.
    oriente = False
    etages = []
    q = os.path.dirname(os.path.abspath(p))
    while q and len(etages) < 12:
        for n_ in ("AGENTS.md", "CLAUDE.md"):
            f = os.path.join(q, n_)
            if est_fichier(f):
                etages.append(f)
        n = os.path.dirname(q)
        if n == q:
            break
        q = n
    propres = [os.path.join(p, n_) for n_ in ("AGENTS.md", "CLAUDE.md") if est_fichier(os.path.join(p, n_))]
    if propres or etages:
        # Le fichier du projet se lit d'abord (`AGENTS.md` avant `CLAUDE.md`), puis
        # les étages du plus proche au plus haut.
        vu, restants = [], list(reversed(etages)) + list(reversed(propres))
        while len(vu) < 8 + len(etages) and restants:
            f = restants.pop()
            if f in vu or not est_fichier(f):
                continue
            vu.append(f)
            t = lis(f)
            if ".mind" in t or "brain/" in t or "memoire/" in t:
                oriente = True
                break
            for c in _IMPORT_RE.finditer(t):
                j = os.path.join(os.path.dirname(f), c.group(1))
                restants.append(canon(j))
    if forme == "equipe":
        # La mémoire EST le dossier du projet : il n'y a rien à nommer.
        oriente = True
    cps = copies(p)
    h = Harnais()
    h.git = os.path.exists(os.path.join(p, ".git"))
    h.depot = r.racine is not None
    h.forme = forme
    h.fact_dir = r.fact if (r.fact is not None and est_dir(r.fact)) else None
    h.fact = fact
    h.minds, h.mind, h.manque, h.surplus, h.anciens = minds, mind, manque, surplus, anciens
    h.lancements = [lancement(p, l, n, cps, ins) for (n, l) in dossiers]
    h.oriente = oriente
    logs = os.path.join(p, ".logs")
    h.logs = len(md_de(logs, "md")) if est_dir(logs) else 0
    h.dispersion = []
    if forme == "equipe":
        # Le journal vit dans la copie du code de chaque agent.
        h.logs = sum(len(md_de(os.path.join(l, "code", ".logs"), "md"))
                     for (_, l) in dossiers if est_dir(os.path.join(l, "code", ".logs")))
        h.dispersion = dispersion(p, [l for (_, l) in dossiers])
    return h


def dispersion(p, lancements):
    """CE QUI S'ÉPARPILLE À NOUVEAU (Claude, 14/10/2026, question de @user : « on est
    sûr qu'on ne va plus retrouver des dossiers éparpillés ? »).

    Deux signaux, lus à chaque relevé : une copie du code hors des dossiers
    d'agents (source : `git worktree list`, qui voit aussi les copies posées à
    la main ou dans un dossier temporaire), et un ancien dossier — `brain/`,
    `agents/`, `docs/` — qui réapparaît dans une copie du code."""
    out = []
    racine_agents = canon(os.path.join(p, "agents"))
    vues = set()
    for l in lancements:
        code = os.path.join(l, "code")
        if not est_dir(code):
            continue
        for c in copies(code):
            k = _cle(c)
            if k in vues:
                continue
            vues.add(k)
            rel = _relatif(racine_agents, c) if racine_agents else None
            if rel is None or rel == "" or rel.startswith(".."):
                out.append("copie hors des agents : «%s»" % c)
        for n in ("brain", "agents", "docs"):
            if est_dir(os.path.join(code, n)):
                out.append("`%s/` réapparu dans %s" % (n, socle.chemin_affiche(p, code)))
    return out


def forme_mot(h):
    return {"equipe": "équipe (un dossier par agent)", "brain": "brain/", "en-place": "en place (.fact/ .mind/)", "deportee": "déportée (memoire/)",
            "ambigue": "À CHEVAL", "ancienne": "taxonomie d'avant",
            "mind-seul": "tout dans .mind/"}.get(h.forme, "aucune")


def jauge(h):
    n = len(h.lancements)
    equipe = any(l.nom is not None for l in h.lancements)
    agents = " · %d agent(s)" % n if equipe else ""
    # À plusieurs, les faits en tiennent un de plus : qui tient quoi.
    attendus = len(socle.FAITS_MONO) + (1 if equipe else 0)
    return "faits %d/%d · état %d/%d%s" % (len(h.fact), attendus, len(h.mind), len(MIND_ATTENDU) * n, agents)


def numeros(v):
    """`0.10.4-local` → (0, 10, 4). Ce qui ne se lit pas ne se compare pas."""
    morceaux = re.findall(r"[0-9]+", v)
    if len(morceaux) < 3:
        return None
    out = []
    for x in morceaux[:3]:
        n = int(x)
        if n > 0xFFFFFFFF:
            return None
        out.append(n)
    return tuple(out)


_VERSION = None


def version_annoncee():
    """La version que ce programme annonce : le premier mot de `harnais version`
    (la logique de `main._identite()`, sans l'empreinte)."""
    global _VERSION
    if _VERSION is None:
        racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        version = "inconnue"
        try:
            with open(os.path.join(racine, ".github", "plugin", "plugin.json"), encoding="utf-8") as f:
                version = json.load(f).get("version", version)
        except (OSError, ValueError, AttributeError):
            pass
        _VERSION = str(version).split(" ")[0]
    return _VERSION


def ligne_paquet(l):
    if l.trace is None:
        servi = "NON"
    else:
        servi = "%s il y a %d j" % (l.trace[0] if l.trace[0] is not None else "avant 0.10.0",
                                    jours_depuis(l.trace[1]))
    return "%sdéclaré %s · inscrit %s · servi %s" % (
        "%s — " % l.nom if l.nom is not None else "",
        {"paquet": "oui"}.get(l.declare, "NON"),
        {True: "oui", False: "NON"}.get(l.inscrit, "?"), servi)


def qui(ls):
    """`A, B : ` à plusieurs — rien en mono : l'agent EST le projet."""
    n = [l.nom for l in ls if l.nom is not None]
    return "%s : " % ", ".join(n) if n else ""


def verdict(h):
    """Quoi faire. Le programme ne le fait pas — c'est une décision, pas un geste.
    CHAQUE COMMANDE CITÉE ICI EXISTE : un conseil qui envoie vers une commande
    morte apprend à ne plus lire les conseils (voir les essais)."""
    brain = h.forme in ("brain", "equipe")
    if not h.depot:
        return ("sans-git", "Pas de dépôt git : le harnais ne cherche la mémoire que dans un dépôt, et ses gardes "
                "se déclenchent au commit. `git init`, puis relire.")
    if h.forme == "aucune":
        return ("neuf", "Aucune mémoire : `harnais adopte` la pose et branche le paquet — à blanc "
                "d'abord, `--go` pour écrire.")
    if h.forme == "ancienne":
        return ("ancien", "Ancienne taxonomie dans `.memory/` (%s) : aucun "
                "outil ne la migre — le tri se fait à la main, puis `harnais adopte`." % ", ".join(h.anciens))
    if h.forme == "mind-seul":
        return ("ancien", "Tout dans `.mind/`, sans faits du projet : l'organisation d'avant les "
                "faits. Répartir faits et état à la main, puis `harnais brain-migre`.")
    if h.forme == "ambigue":
        return ("ambigu", "À cheval entre `brain/` et l'organisation d'avant : le harnais refuse de "
                "choisir et ne sert AUCUNE mémoire. `harnais brain-migre` termine la migration.")
    # CE QUI S'ÉPARPILLE PASSE AVANT LE RESTE : c'est la panne que la forme
    # « un dossier par agent » existe pour éviter (Claude, 14/10/2026). Aucune
    # commande n'est citée : celle qui range existe côté Claude (`demenage`), pas encore ici.
    if getattr(h, "dispersion", None):
        return ("disperse", "Ça s'éparpille à nouveau (%s) : une copie du code de plus vit dans "
                "`agents/<nom>/code-<sujet>/`, et la mémoire hors du code." % " · ".join(h.dispersion[:3]))
    pose = ("`harnais adopte --go` le pose sans rien écraser." if brain
            else "à créer à la main — ou passer en `brain/` avec `harnais brain-migre`.")
    if not h.mind and h.fact:
        return ("sans-agent", "Des faits, aucun état d'agent — il manque %s : %s" % (", ".join(h.manque), pose))
    if h.manque:
        return ("incomplet", "Il manque %s : %s" % (", ".join(h.manque), pose))
    non = [l for l in h.lancements if l.declare == "non"]
    if non:
        return ("non-branche", "%sRien ne déclare le paquet : %s" % (
            qui(non), "`harnais adopte --go` le branche." if brain
            else "`harnais brain-migre`, puis `harnais adopte --go`."))
    ni = [l for l in h.lancements if l.declare == "paquet" and l.inscrit is False]
    if ni:
        return ("non-inscrit", "%sPaquet déclaré mais marketplace locale non résolue : vérifier le chemin "
                "dans .github/copilot/settings.json." % qui(ni))
    nm = [l for l in h.lancements if l.declare == "paquet" and l.inscrit is None]
    if nm:
        return ("non-mesure", "%sLes inscriptions au paquet n'ont pas pu être lues : qu'il se charge au "
                "prochain démarrage n'est PAS vérifié." % qui(nm))
    js = [l for l in h.lancements if l.trace is None]
    if js:
        return ("jamais-servi", "%sAucune trace d'entrée : l'agent n'a pas démarré depuis qu'il est "
                "branché — ou le paquet ne se charge pas. Le démarrer, puis relire." % qui(js))
    if not h.git:
        return ("sans-git", "Pas de dépôt git : les gardes se déclenchent au commit, elles sont donc inertes.")
    if h.surplus:
        return ("surplus", "La mémoire porte %d fichier(s) que le harnais ne prévoit pas (%s) : les faits "
                "en tiennent quatre, cinq à plusieurs ; l'état d'un agent, deux." % (len(h.surplus), ", ".join(h.surplus)))
    sd = [l for l in h.lancements if (l.deny or 0) == 0]
    if sd:
        return ("sans-deny", "%sAucune règle `deny` : ce qui doit être interdit ici ne l'est que par la "
                "prose, donc se redemande à chaque session." % qui(sd))
    # LA RÉFÉRENCE EST CE QUI EST INSCRIT, pas la version de ce programme-ci :
    # c'est l'inscription que l'agent chargera à son prochain démarrage. Ce
    # programme ne sert qu'à voir si l'inscription elle-même a pris du retard.
    ici = version_annoncee()

    def vieille(l):
        a = numeros(l.inscrite) if l.inscrite is not None else None
        b = numeros(ici)
        return a is not None and b is not None and a < b
    vieilles = [l for l in h.lancements if vieille(l)]
    if vieilles:
        v = vieilles[0].inscrite or ""
        return ("inscription-vieille", "%sInscrit en %s alors que le paquet en est à %s : dans le dossier, "
                "corriger la marketplace locale, puis redémarrer Copilot." % (qui(vieilles), v, ici))

    def vieux_(l):
        if l.trace is None:
            return False
        v = l.trace[0]
        reference = l.inscrite if l.inscrite is not None else ici
        a = numeros(v) if v is not None else None
        if a is None:
            return True
        b = numeros(reference)
        return b is not None and a < b
    vieux = [l for l in h.lancements if vieux_(l)]
    if vieux:
        d = []
        for l in vieux:
            v, t = l.trace
            d.append("%s%s (entrée il y a %d j), %s inscrite" % (
                "%s — " % l.nom if l.nom is not None else "",
                v if v is not None else "une version d'avant la 0.10.0", jours_depuis(t),
                l.inscrite if l.inscrite is not None else ici))
        return ("en-retard", "La session tourne encore sur %s : la nouvelle arrivera à son prochain "
                "démarrage." % " · ".join(d))
    if h.forme in ("en-place", "deportee"):
        return ("v1", "Servi, en organisation d'avant (`.fact/`, `.mind/`) : `harnais brain-migre` la passe en "
                "`brain/` quand tu le décides.")
    v = [l.trace[0] for l in h.lancements if l.trace is not None and l.trace[0] is not None]
    return ("ok", "Servi en %s, mémoire complète." % (v[0] if v else ""))


class Projet(object):
    __slots__ = ("nom", "harnais", "champs", "taches", "fraicheur", "jours", "verdict", "conseil",
                 "attente", "encours", "afaire")


def scanne(racine, un_seul):
    aujourdhui = datetime.date.today()
    ins = inscriptions()
    dossiers = trie(racine)
    dossiers.sort(key=lambda d: nom(d).lower())
    out = []
    for d in dossiers:
        n = nom(d)
        if not est_dir(d) or n.startswith("."):
            continue
        if not un_seul and n in IGNORE:
            continue
        if un_seul and n.lower() != un_seul.lower():
            continue
        h = harnais(d, ins)
        # Une seule voix : l'état le plus en difficulté, et les tâches réunies.
        e, t = {}, []
        for m in h.minds:
            x = entete(lis(os.path.join(m, "state.md")))
            if x and (not e or x.get("sante") == "rouge"):
                e = x
            t.extend(taches(lis(os.path.join(m, "todo.md"))))
        # Le `cap` appartient au PROJET : il vit dans les faits, là où le
        # résolveur les trouve — avant eux, dans l'état.
        if h.fact_dir is not None:
            b = entete(lis(os.path.join(h.fact_dir, "base.md")))
            e.pop("cap", None)
            if b.get("cap"):
                e["cap"] = b["cap"]
        etat, jours = fraicheur(e.get("maj", ""), aujourdhui)
        code, conseil = verdict(h)
        p = Projet()
        p.nom, p.fraicheur, p.jours, p.verdict, p.conseil = n, etat, jours, code, conseil
        p.attente = [x for x in t if x.qui and x.qui != DEHORS and x.etat != "fait"]
        p.encours = len([x for x in t if x.etat == "encours"])
        p.afaire = len([x for x in t if x.etat == "afaire"])
        p.harnais, p.champs, p.taches = h, e, t
        out.append(p)
    return out


def symbole(v):
    return {"ok": "OK  ", "v1": "V1  ", "en-retard": "RETD", "neuf": "NEUF", "ancien": "TRI ",
            "ambigu": "AMBI", "incomplet": "MANQ", "sans-agent": "AGT?", "non-branche": "BRCH",
            "non-inscrit": "INSC", "jamais-servi": "SERV",
            "inscription-vieille": "MAJ ", "non-mesure": "????",
            "sans-git": "GIT ", "surplus": "TROP", "sans-deny": "DENY",
            "disperse": "DISP"}.get(v, "?   ")


def frais_mot(f):
    return {"frais": "à jour", "tiede": "tiède", "perime": "PÉRIMÉ"}.get(f, "ILLISIBLE")


def rang(p):
    return {"haut": 0, "moyen": 1, "": 2}.get(p, 3)


def oui(b):
    return "oui" if b else "NON"


def deny_txt(h):
    """Le plus faible des dossiers de lancement : c'est lui qui laisse passer."""
    d = [l.deny for l in h.lancements if l.deny is not None]
    return str(min(d)) if d else "—"


def terminal(projets, racine):
    out = ["Atelier : %s — %d projet(s)\n" % (racine, len(projets))]
    att = []
    for p in projets:
        h, e = p.harnais, p.champs
        out.append("── %s [%s] %s" % (gauche(p.nom, 22), symbole(p.verdict), p.conseil))
        if e.get("cap"):
            out.append("     cap    : %s" % coupe(e["cap"], 90))
        maj = e.get("maj", "—")
        j = " (%d j)" % p.jours if p.jours is not None else ""
        jalon = e.get("jalon") or "—"
        out.append("     maj    : %s — %s%s   santé : %s   jalon : %s" % (
            maj, frais_mot(p.fraicheur), j, e.get("sante", "—"), coupe(jalon, 44)))
        out.append("     mémoire: %s · %s · .logs %d · git %s" % (forme_mot(h), jauge(h), h.logs, oui(h.git)))
        for l in h.lancements:
            out.append("     paquet : %s" % ligne_paquet(l))
        for l in h.lancements:
            base = os.path.join(racine, p.nom)
            d = agent.contexte(base, l.nom) if l.nom is not None else base
            if copilot.ancien_paquet(d):
                out.append("     ATTENTION : %s déclare encore harnais@atelier (risque de double chargement)"
                           % os.path.join(d, ".claude/settings.json"))
            if d != base and est_fichier(copilot.settings(d)):
                out.append("     ATTENTION : %s est inerte hors de la racine Git" % copilot.settings(d))
        out.append("     contexte: AGENTS.md→mémoire %s · deny %s" % (oui(h.oriente), deny_txt(h)))
        if p.taches:
            out.append("     tâches : %d en cours · %d à faire · %d attendent une décision" % (
                p.encours, p.afaire, len(p.attente)))
        for a in p.attente:
            att.append((p.nom, a))
        out.append("")
    out.append("═" * 64)
    if att:
        out.append("CE QUI ATTEND UNE DÉCISION — %d point(s), la seule colonne qui ne se délègue pas\n" % len(att))
        att.sort(key=lambda x: rang(x[1].prio))
        for (n, a) in att:
            out.append("  [%s] %s @%s %s" % (gauche(a.prio if a.prio else "—", 5), gauche(n, 18),
                                             gauche(a.qui, 9), coupe(a.titre, 60)))
    else:
        out.append("Aucune tâche `@<qui>` ouverte — ce qui peut vouloir dire deux choses :")
        out.append("rien n'attend, ou personne n'en a déclaré. Le second cas est le plus fréquent.")
    sys.stdout.write("\n".join(out) + "\n")


def e(s):
    """`html.escape(s, quote=True)` — les cinq, dans cet ordre."""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#x27;"))


CSS = """
:root{--fond:#f3f4f6;--carte:#fff;--creux:#e9ebef;--encre:#15181e;--doux:#4a5160;
--pale:#767e8e;--trait:#d6d9e0;--accent:#3b4e8f;--vert:#2f7d4f;--orange:#9a6b12;
--rouge:#a5432f;--vert-f:#e4f0e9;--orange-f:#f7eeda;--rouge-f:#f6e7e3;--acc-f:#e6e9f4}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--fond:#14161b;
--carte:#1b1e25;--creux:#23272f;--encre:#e7e9ed;--doux:#a8afbd;--pale:#7c8494;
--trait:#2e333d;--accent:#9bb0e8;--vert:#7bc49a;--orange:#d8b45c;--rouge:#e2907e;
--vert-f:#1c2a22;--orange-f:#2c2618;--rouge-f:#33221e;--acc-f:#232b42}}
*{box-sizing:border-box}
body{margin:0;background:var(--fond);color:var(--encre);font:15px/1.6 -apple-system,
BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
.p{max-width:78rem;margin:0 auto;padding:2.5rem 1.25rem 4rem}
h1{font-size:1.9rem;margin:0 0 .3rem;letter-spacing:-.01em}
.sous{color:var(--pale);font-size:.9rem;margin:0 0 2rem}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,"Cascadia Mono",monospace}
.att{background:var(--carte);border:1px solid var(--trait);border-left:3px solid var(--rouge);
border-radius:5px;padding:1.1rem 1.25rem;margin-bottom:2rem}
.att h2{font-size:1rem;margin:0 0 .8rem;color:var(--rouge);letter-spacing:.02em}
.att ul{margin:0;padding-left:1.1rem}.att li{margin-bottom:.4rem}
.att .p-{display:inline-block;font-size:.68rem;padding:.08rem .4rem;border-radius:3px;
margin-right:.5rem;font-family:ui-monospace,monospace;background:var(--creux);color:var(--doux)}
.att .p-haut{background:var(--rouge-f);color:var(--rouge)}
.att .proj{color:var(--pale);font-size:.85rem}
.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(21rem,1fr));gap:.9rem}
.c{background:var(--carte);border:1px solid var(--trait);border-radius:6px;padding:1rem 1.1rem}
.c h3{margin:0;font-size:1.05rem;display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}
.b{font-size:.66rem;padding:.12rem .45rem;border-radius:3px;font-family:ui-monospace,monospace;
letter-spacing:.03em;text-transform:uppercase}
.b-ok{background:var(--vert-f);color:var(--vert)}
.b-warn{background:var(--orange-f);color:var(--orange)}
.b-bad{background:var(--rouge-f);color:var(--rouge)}
.cap{color:var(--doux);font-size:.88rem;margin:.55rem 0 .8rem}
.meta{font-size:.79rem;color:var(--pale);font-family:ui-monospace,monospace;
border-top:1px solid var(--trait);padding-top:.6rem;margin-top:.2rem;
display:flex;flex-wrap:wrap;gap:.15rem .9rem}
.meta b{font-weight:500;color:var(--doux)}
.no{color:var(--rouge)}
.conseil{margin-top:.7rem;font-size:.83rem;background:var(--acc-f);color:var(--accent);
padding:.45rem .6rem;border-radius:4px}
.barre{display:flex;height:5px;border-radius:3px;overflow:hidden;background:var(--creux);margin:.7rem 0 .35rem}
.barre i{display:block}.b1{background:var(--vert)}.b2{background:var(--accent)}.b3{background:var(--trait)}
.tt{font-size:.78rem;color:var(--pale)}
footer{margin-top:2.5rem;padding-top:1rem;border-top:1px solid var(--trait);
color:var(--pale);font-size:.8rem}
"""


def badge(v):
    t = {
        "ok": ("b-ok", "servi"), "v1": ("b-warn", "organisation d'avant"),
        "en-retard": ("b-warn", "version en retard"), "neuf": ("b-bad", "sans mémoire"),
        "ancien": ("b-bad", "taxonomie ancienne"), "ambigu": ("b-bad", "à cheval"),
        "sans-agent": ("b-bad", "aucun agent"), "incomplet": ("b-warn", "mémoire incomplète"),
        "non-branche": ("b-bad", "paquet non déclaré"), "non-inscrit": ("b-bad", "non inscrit"),
        "jamais-servi": ("b-bad", "jamais servi"),
        "inscription-vieille": ("b-warn", "inscription à mettre à jour"),
        "non-mesure": ("b-warn", "non mesuré"), "sans-git": ("b-warn", "sans git"),
        "surplus": ("b-warn", "fichier en trop"), "sans-deny": ("b-warn", "aucun deny"),
        "disperse": ("b-bad", "ça s'éparpille"),
    }.get(v)
    return t if t is not None else ("b-warn", v)


def badge_frais(f):
    return {"frais": ("b-ok", "à jour"), "tiede": ("b-warn", "tiède"),
            "perime": ("b-bad", "périmé")}.get(f, ("b-bad", "en-tête illisible"))


def page(projets, racine, watch):
    att = [(p.nom, a) for p in projets for a in p.attente]
    att.sort(key=lambda x: rang(x[1].prio))
    bloc = ['<div class="att"><h2>Ce qui attend une décision — %d point(s)</h2>' % len(att)]
    if att:
        bloc.append("<ul>")
        for (n, a) in att:
            bloc.append('<li><span class="p- p-%s">%s</span>%s <span class="proj">— %s · @%s</span></li>' % (
                e(a.prio), e(a.prio if a.prio else "—"), e(a.titre), e(n), e(a.qui)))
        bloc.append("</ul>")
    else:
        bloc.append('<p style="margin:0;font-size:.9rem">Aucune tâche <span class="mono">@&lt;qui&gt;</span> '
                    "ouverte. Deux lectures possibles : rien n'attend, ou personne n'en a déclaré.</p>")
    bloc.append("</div>")

    cartes = []
    for p in projets:
        h, ch = p.harnais, p.champs
        bv, bt = badge(p.verdict)
        fv, ft = badge_frais(p.fraicheur)
        fait = len([x for x in p.taches if x.etat == "fait"])
        enc, af = p.encours, p.afaire
        tot = float(max(fait + enc + af, 1))
        c = ['<div class="c"><h3>%s <span class="b %s">%s</span> <span class="b %s">%s</span></h3>' % (
            e(p.nom), bv, e(bt), fv, e(ft))]
        c.append('<p class="cap">%s</p>' % e(ch.get("cap") or "— pas de <span>cap:</span> déclaré —"))
        if p.taches:
            c.append('<div class="barre"><i class="b1" style="width:%.1f%%"></i><i class="b2" style="width:%.1f%%"></i>'
                     '<i class="b3" style="width:%.1f%%"></i></div>' % (100.0 * fait / tot, 100.0 * enc / tot, 100.0 * af / tot))
            c.append('<div class="tt">%d fait · %d en cours · %d à faire</div>' % (fait, enc, af))

        def non(ok, t):
            return t if ok else '<span class="no">%s</span>' % t
        c.append('<div class="meta"><span><b>maj</b> %s</span><span><b>santé</b> %s</span><span>%s</span>'
                 '<span><b>mémoire</b> %s · %s</span><span><b>.logs</b> %d</span></div>' % (
                     e(ch.get("maj") or "—"), e(ch.get("sante") or "—"),
                     non(h.git, "git"), e(forme_mot(h)), e(jauge(h)), h.logs))
        for l in h.lancements:
            base = os.path.join(racine, p.nom)
            d = agent.contexte(base, l.nom) if l.nom is not None else base
            if copilot.ancien_paquet(d):
                c.append('<div class="conseil">ATTENTION : %s déclare encore harnais@atelier (double chargement '
                         'possible)</div>' % e(os.path.join(d, ".claude/settings.json")))
            if d != base and est_fichier(copilot.settings(d)):
                c.append('<div class="conseil">ATTENTION : %s est inerte hors de la racine Git</div>'
                         % e(copilot.settings(d)))
            servi = l.trace is not None
            if l.declare != "non" and l.inscrit is not False and servi:
                corps = e(ligne_paquet(l))
            else:
                corps = '<span class="no">%s</span>' % e(ligne_paquet(l))
            c.append('<div class="meta"><span>%s</span></div>' % corps)
        c.append('<div class="meta"><span>%s</span><span><b>deny</b> %s</span></div>' % (
            non(h.oriente, "AGENTS.md → mémoire"), deny_txt(h)))
        if p.verdict != "ok":
            c.append('<div class="conseil">%s</div>' % e(p.conseil))
        c.append("</div>")
        cartes.append("".join(c))
    # `meta refresh` est le SEUL rafraîchissement qui marche depuis `file://`.
    refresh = "<meta http-equiv=refresh content=%d>" % watch if watch > 0 else ""
    if watch > 0:
        pied = "Régénérée toutes les %d s tant que <span class=mono>--watch</span> tourne." % watch
    else:
        pied = ("Relevé daté, pas un tableau vivant. Régénérer avec "
                "<span class=mono>harnais equipe-vue --html</span>.")
    now = datetime.datetime.now()
    date = now.strftime("%d/%m/%Y") + " à " + now.strftime("%H:%M")
    return ("<!doctype html><html lang=fr><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>" + refresh +
            "<title>Agentic Team</title><style>" + CSS + "</style></head><body><div class=p>"
            "<h1>Agentic Team</h1>"
            "<p class=sous><span class=mono>" + e(racine) + "</span> · " + str(len(projets)) +
            " projets · relevé du " + date + "</p>" +
            "".join(bloc) + "<div class=g>" + "".join(cartes) + "</div>"
            "<footer>Page autonome : aucun serveur, aucune ressource externe. " + pied + "</footer>"
            "</div></body></html>")


class _Signaux(object):
    """SIGINT ET SIGTERM : un `kill` simple laissait, en Python, la balise
    `refresh` en place, et la page se rechargeait sur un relevé mort."""
    arret = False

    @classmethod
    def arme(cls):
        import signal

        def attrape(_s, _f):
            cls.arret = True
        for s in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(s, attrape)
            except (ValueError, OSError):
                pass


def valeur(args, cle):
    it = iter(args)
    for a in it:
        if a == cle:
            return next(it, None)
        if a.startswith(cle + "="):
            return a[len(cle) + 1:]
    return None


def developpe(p):
    h = os.environ.get("HOME")
    if h is None:
        h = os.environ.get("USERPROFILE")
    if p == "~" and h is not None:
        return h
    if p.startswith("~/") and h is not None:
        return os.path.join(h, p[2:])
    return p


def resous(p):
    # Comme `Path.resolve()` : le parent résolu même quand le fichier n'existe pas encore.
    if os.path.exists(p):
        return os.path.realpath(p)
    q = p.rstrip("/") if p.strip("/") else p
    d, n = os.path.dirname(q), os.path.basename(q)
    if d and n and n != "..":
        if os.path.exists(d):
            return os.path.join(os.path.realpath(d), n)
        return p
    return os.path.join(os.getcwd(), p)


def arret(msg):
    sys.stderr.write(msg + "\n")
    return 1


def main(args):
    if "-h" in args or "--help" in args:
        sys.stdout.write(
            "harnais equipe-vue [--racine R] [--projet NOM] [--html PAGE [--watch N]]\n\n"
            "Lit la mémoire de tous les projets d'un atelier : le diagnostic au terminal, ou\n"
            "une page autonome. Strictement en lecture — n'écrit que la page demandée.\n")
        return 0
    racine = valeur(args, "--racine")
    racine = resous(developpe("~/Agentic" if racine is None else racine))
    un_seul = valeur(args, "--projet") or ""
    html = valeur(args, "--html") or ""
    w = valeur(args, "--watch")
    if w is None:
        watch = 0
    else:
        if re.match(r"\+?[0-9]+\Z", w) and int(w) <= 0xFFFFFFFFFFFFFFFF:
            watch = int(w)
        else:
            sys.stderr.write("harnais equipe-vue : --watch attend un nombre de secondes\n")
            return 2
    if not est_dir(racine):
        return arret("Racine introuvable : %s" % racine)
    if watch > 0 and not html:
        return arret("--watch n'a de sens qu'avec --html : sans page à réécrire, il n'y a rien à rafraîchir.")
    if 0 < watch < 5:
        return arret("--watch en dessous de 5 s relit tous les .mind/ en boucle pour rien. 60 s convient.")

    def releve():
        p = scanne(racine, un_seul)
        if not p:
            raise _Echec("Aucun projet trouvé dans %s%s" % (
                racine, "" if not un_seul else " pour « %s »" % un_seul))
        return p
    if not html:
        try:
            p = releve()
        except _Echec as ex:
            return arret(str(ex))
        terminal(p, racine)
        return 0
    cible = resous(developpe(html))
    d = os.path.dirname(cible)
    if d:
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass

    def ecris(w):
        p = releve()
        try:
            with open(cible, "wb") as f:
                f.write(page(p, racine, w).encode("utf-8", "replace"))
        except OSError as ex:
            raise _Echec("%s (os error %s)" % (ex.strerror, ex.errno))
        return len(p)
    try:
        n = ecris(watch)
    except _Echec as ex:
        return arret(str(ex))
    try:
        ko = os.path.getsize(cible) / 1024.0
    except OSError:
        ko = 0.0
    sys.stdout.write("Page écrite : %s  (%d projets, %.0f Ko)\n" % (cible, n, ko))
    if watch == 0:
        sys.stdout.write("Elle s'ouvre d'un double-clic — aucun serveur nécessaire.\n")
        return 0
    sys.stdout.write("Suivi toutes les %d s. La page se recharge seule ; Ctrl-C pour arrêter.\n" % watch)
    sys.stdout.flush()
    _Signaux.arme()
    while not _Signaux.arret:
        for _ in range(watch * 4):
            if _Signaux.arret:
                break
            time.sleep(0.25)
        else:
            try:
                ecris(watch)
            except _Echec:
                pass
    # Réécrire une dernière fois sans refresh : la page reste lisible et cesse
    # de se prétendre vivante.
    try:
        ecris(0)
        sys.stdout.write("\nSuivi arrêté — la page reste en place, en relevé daté.\n")
    except _Echec as ex:
        sys.stdout.write("\nSuivi arrêté, mais la page garde son meta-refresh (%s). Elle se rechargera sur "
                         "un relevé figé : sa date en tête ne bougera plus.\n" % ex)
    return 0


class _Echec(Exception):
    pass
