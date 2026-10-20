# -*- coding: utf-8 -*-
"""`harnais demenage` — UNE ÉQUIPE `brain/` PASSE À « UN DOSSIER PAR AGENT ».

Port du harnais Claude (`demenage`, 0.19), adapté à Copilot. Python 3.9 minimum,
chemins par `os.path`, aucun lien symbolique : Windows est la cible.

    AVANT                                   APRÈS
    P/            le code (copie princ.)    P/                 la MÉMOIRE (son dépôt)
    P/brain/      la mémoire                  fact/ shared/ docs/ assets/ AGENTS.md
    P/agents/<n>/ rôle, droits, par copie     agents/<n>/       rôle, droits, état
    <copies>/     worktrees du code             agents/<n>/code/  sa copie du code

Ce que cet outil produit, c'est ce que produit la naissance (`adopte --equipe`) :
mêmes dossiers, mêmes profils `.github/agents/<nom>.agent.md`, mêmes périmètres
(`equipe.perimetre_agent(..., equipe_forme=True)`), même déclaration du paquet
(`.github/copilot/settings.json`, UNE à la racine Git), même `.gitignore`.

DEUX SITUATIONS DE DÉPART, parce que Copilot et Claude ne rangent pas la mémoire
au même endroit :

  · A — `brain/` a son PROPRE dépôt git (la forme de Claude). Le dossier, son
    dépôt et son historique deviennent la racine du projet : c'est la séquence
    éprouvée de Claude, rejouée telle quelle.
  · B — `brain/` vit DANS le dépôt du code (la forme ordinaire de Copilot : la
    mémoire se lit dans la copie courante, elle est donc commitée avec le code).
    Rien ne peut « sortir » de ce dépôt sans le réécrire. La mémoire est donc
    COPIÉE vers un dépôt neuf, vérifiée à l'octet ; l'ancien reste intact dans
    la copie du code, avec TOUT son historique (celui de la mémoire compris), et
    n'est nettoyé que sur demande de l'humain.

LA SÉQUENCE DU CODE EST CELLE DE QA, REJOUÉE SUR UN DÉPÔT JETABLE. Le checkout
principal ne se déplace pas par `git worktree move` (« '.' is a main working
tree ») ; et après les `mv`, chaque copie pointe vers `P/.git`, devenu le `.git`
de la MÉMOIRE — un `move` est alors refusé. D'où :

    1. relevé          copies, branches, état git, inventaire (ignorés compris)
    2. mv P -> P.code-demenage ; A : mv P.code-demenage/brain -> P
                                  B : mkdir P, git init P
    3. mv P.code-demenage -> P/agents/<premier>/code
    4. git worktree repair <chemins ACTUELS des copies>, depuis le nouveau principal
    5. git worktree move <copie> P/agents/<n>/code[-<sujet>] ; une copie neuve
       (git worktree add) pour qui n'en avait pas
    6. repair final, puis le TÉMOIN : même nombre de copies, mêmes branches,
       même état git (modifications non enregistrées comprises), inventaire identique
    — sinon RETOUR ARRIÈRE par les mêmes gestes, en sens inverse.

Puis la mémoire : états, carnet, faits, `docs/`, `assets/`, consignes communes
copiés ou déplacés ET COMPARÉS PAR EMPREINTE, droits traduits, profils posés, un
seul enregistrement.

CE QU'IL NE FAIT PAS, ET LE DIT :
  · enregistrer quoi que ce soit dans le dépôt du CODE (retirer `agents/`,
    `brain/`, `docs/`…) — c'est sur demande de l'humain ;
  · trier les copies qu'aucun agent ne lance ; relire la prose ;
  · ÉCARTÉ, avec sa raison : les conversations rangées par dossier de lancement
    et le registre des inscriptions au paquet (Claude). Copilot n'a ni l'un ni
    l'autre : sa mémoire de session vit sous un identifiant de session, et le
    paquet est déclaré dans `.github/copilot/settings.json`, qui voyage avec le
    dépôt. Les crochets `../../.claude/hooks` n'existent pas non plus : les
    crochets viennent du paquet ;
  · la FORME COMPACTE (profils `.github/agents/<nom>.agent.md`, une seule copie
    du code) est un choix de Copilot : elle est NOMMÉE, jamais déplacée. Porter
    ce passage n'est ni simple ni sûr (il faudrait créer une copie du code par
    agent, séparer la mémoire du dépôt du code en réécrivant ou perdant son
    historique, et retrouver les droits dans des périmètres centralisés) ;
    `niveau.COMPACTE` dit quoi faire à la place.

**À BLANC PAR DÉFAUT.** `--apply --agents-arretes` écrit, et seulement si rien
ne bloque : agents arrêtés, mémoire propre, `docs/` identique dans toutes les
copies, aucun secret dans ce qui monte (la mémoire part sur GitHub).
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys

import adopte
import agent
import carnet
import coffre
import copilot
import equipe
import memoire
import niveau
from memoire import Forme

V, R, J, B, D, X = "\x1b[32m", "\x1b[31m", "\x1b[33m", "\x1b[1m", "\x1b[2m", "\x1b[0m"

# Ce qui ne monte JAMAIS dans la mémoire, qui part sur GitHub.
SECRETS_NOMS = re.compile(r"(^|/)(operations\.md|id_rsa.*|.*\.pem|.*\.p12|.*\.key)$")
SECRETS_TEXTE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
# Le code ne garde plus ces dossiers : ils vivent dans la mémoire.
QUITTENT_LE_CODE = ("agents", "brain", "docs", "assets", "AGENTS.md")
INVENTAIRE_SAUF = ("node_modules", ".git")
# Ce que la mémoire d'une équipe porte à sa racine : le reste de `brain/` est NOMMÉ.
BRAIN_CONNU = ("fact", "mind", "workspace", "poids.json")
# Les chemins d'un droit qui appartiennent à la MÉMOIRE (le reste est du code).
MEMOIRE_PREMIER = ("brain", "agents", "docs", "assets", "AGENTS.md", "poids.json", "fact", "shared")


def _p(s=""):
    sys.stdout.write(s + "\n")


def _lis(f):
    with open(f, encoding="utf-8", newline="") as h:
        return h.read()


def _git(ou, args):
    o = subprocess.run(["git"] + list(args), cwd=ou, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return o.returncode, o.stdout.decode("utf-8", "replace"), o.stderr.decode("utf-8", "replace")


def _ok(ou, args):
    c, out, err = _git(ou, args)
    if c != 0:
        raise RuntimeError("git %s (dans %s) : %s" % (" ".join(args), ou, (err or out).strip()[:300]))
    return out


def _norm(p):
    """Un chemin tel que le système l'écrit : résolu, séparateurs natifs (git rend
    `C:/Users/u/…`, Python `C:\\Users\\u\\…`)."""
    return memoire.natif(os.path.realpath(p))


def egal(a, b):
    r = niveau.sous(a, b)
    return r is not None and not r


def _rmtree(d):
    """`rmtree` qui vient à bout des fichiers en lecture seule — ceux d'un `.git`
    sous Windows."""
    def force(fonction, chemin, _exc):
        try:
            os.chmod(chemin, stat.S_IWRITE)
            fonction(chemin)
        except OSError:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(d, onexc=force)         # `onerror` est déprécié depuis 3.12
    else:
        shutil.rmtree(d, onerror=force)


def vivante(c):
    """Une copie qu'on peut réparer et déplacer : son dossier ET son `.git`. Les
    autres (« prunable ») restent telles quelles, nommées."""
    return os.path.isdir(c) and os.path.exists(os.path.join(c, ".git"))


def lis_copies(out, norm=_norm):
    """`[(chemin, branche ou None)]`, le principal en premier — sortie de
    `git worktree list --porcelain`, avec `norm` pour écrire les chemins."""
    v, cur = [], None
    for l in out.split("\n"):
        l = l.rstrip("\r")
        if l.startswith("worktree "):
            cur = [l[len("worktree "):], None]
            v.append(cur)
        elif l.startswith("branch ") and cur is not None:
            cur[1] = l[len("branch refs/heads/"):] if l.startswith("branch refs/heads/") else l[7:]
    return [(norm(p), b) for p, b in v]


def copies(principal):
    return lis_copies(_ok(principal, ["worktree", "list", "--porcelain"]))


def inventaire(racine):
    """`{chemin relatif: (taille, mtime_ns)}` — fichiers ignorés compris, sans
    `node_modules` ni `.git` (comptés à part). Un `mv` garde les deux : c'est le
    témoin qu'aucun fichier n'est resté en route, `.env*` compris."""
    v, lourds = {}, 0
    for d, dirs, fs in os.walk(racine):
        garde = []
        for x in dirs:
            if x in INVENTAIRE_SAUF:
                lourds += 1
            else:
                garde.append(x)
        dirs[:] = garde
        for f in fs:
            # Le `.git` d'une copie est un FICHIER que git réécrit en la réparant :
            # son changement est le geste, pas une perte.
            if f in INVENTAIRE_SAUF:
                continue
            p = os.path.join(d, f)
            try:
                s = os.lstat(p)
            except OSError:
                continue
            v[os.path.relpath(p, racine).replace(os.sep, "/")] = (s.st_size, s.st_mtime_ns)
    return v, lourds


def etat_git(copie, sans_brain=False):
    """L'état git d'une copie : `(HEAD, branche, modifications non enregistrées)`.
    C'est ce qui prouve que le travail en cours a traversé le déménagement."""
    _, head, _ = _git(copie, ["rev-parse", "HEAD"])
    _, br, _ = _git(copie, ["rev-parse", "--abbrev-ref", "HEAD"])
    _, st, _ = _git(copie, ["status", "--porcelain"])
    lignes = sorted(l for l in st.split("\n") if l.strip())
    if sans_brain:
        lignes = [l for l in lignes if not re.match(r'^..\s+"?brain(/|"?$)', l)]
    return head.strip(), br.strip(), lignes


def empreinte(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def arbre_empreintes(racine):
    v = {}
    for d, dirs, fs in os.walk(racine):
        dirs[:] = [x for x in dirs if x != ".git"]
        for f in fs:
            if f == ".DS_Store":
                continue
            p = os.path.join(d, f)
            if os.path.isfile(p) and not os.path.islink(p):
                v[os.path.relpath(p, racine).replace(os.sep, "/")] = empreinte(p)
    return v


def est_secret(rel):
    """Un fichier qui ne doit jamais monter : `.env*`, `.mcp.json`, `operations.md`,
    clés. Le même détecteur que le coffre, plus les noms de clés."""
    return coffre.fichier_secret(rel) or bool(SECRETS_NOMS.search(rel.replace(os.sep, "/")))


def secrets(racine, rel_base="", garde=None):
    """Les fichiers qui ne doivent JAMAIS monter dans la mémoire : par nom, puis par
    contenu (les fichiers de moins de 2 Mo). Jamais la valeur. `garde(rel)` écarte ceux
    qui ne monteront de toute façon pas (rel : relatif à `racine`, en `/`)."""
    out = []
    if not os.path.exists(racine):
        return out
    if os.path.isfile(racine):
        fichiers = [racine]
    else:
        fichiers = []
        for d, dirs, fs in os.walk(racine):
            dirs[:] = [x for x in dirs if x != ".git"]
            fichiers.extend(os.path.join(d, f) for f in fs)
    for p in fichiers:
        if garde is not None and not garde(os.path.relpath(p, racine).replace(os.sep, "/")):
            continue
        rel = os.path.join(rel_base, os.path.relpath(p, os.path.dirname(racine)))
        if est_secret(rel):
            out.append(rel)
            continue
        try:
            if os.path.getsize(p) > 2 * 1024 * 1024:
                continue
            with open(p, "rb") as f:
                t = f.read().decode("utf-8", "ignore")
        except OSError:
            continue
        if SECRETS_TEXTE.search(t) or coffre.cles(t):
            out.append(rel)
    return out


# ── le plan ─────────────────────────────────────────────────────────────────

class Plan(object):
    def __init__(self, projet):
        self.projet = projet
        self.memoire = os.path.join(projet, "brain")
        self.temp = projet.rstrip("/\\") + ".code-demenage"
        self.autonome = False     # A : `brain/` a son propre dépôt ; sinon B
        self.deja = False         # déjà « un dossier par agent »
        self.compacte = False     # forme compacte : nommée, pas touchée
        self.agents = []          # noms, dans l'ordre de `brain/mind/`
        self.premier = None       # l'agent qui reçoit le checkout principal
        self.copies = []          # [(chemin, branche)] — toutes, principal en tête
        self.copie = {}           # nom -> copie existante qui devient la sienne
        self.badge = {}           # nom -> copie d'où se lit son dossier `agents/<nom>/`
        self.nouvelles = []       # [(nom, branche, existe)] — une copie à créer
        self.en_plus = []         # [(nom, sujet, copie)]
        self.livrables = []       # chemins relatifs au code, copiés dans assets/
        self.restent = []         # copies qu'aucun agent ne reprend
        self.bloquants = []
        self.notes = []
        self.corr = None

    def code(self):
        return os.path.join(self.projet, "agents", self.premier, "code")

    def niche(self, copie):
        """Une copie posée DANS le checkout principal part avec lui : où elle se
        trouve après le `mv`."""
        r = niveau.sous(copie, self.projet)
        if r:
            return os.path.join(self.code(), *r)
        return None

    def cible(self, copie):
        """Où une copie arrive."""
        if egal(copie, self.copies[0][0]):
            return self.code()
        for n, c in self.copie.items():
            if egal(c, copie):
                return os.path.join(self.projet, "agents", n, "code")
        for n, s, c in self.en_plus:
            if egal(c, copie):
                return os.path.join(self.projet, "agents", n, "code-" + s)
        return None


def _classe_mixte(pl, dossiers, compacts):
    if compacts and dossiers:
        pl.bloquants.append("équipe MIXTE (compacts : %s ; avec dossier : %s) : ni l'un ni l'autre n'est "
                            "touché. %s" % (", ".join(compacts), ", ".join(dossiers), niveau.COMPACTE))
    elif compacts:
        pl.compacte = True
        pl.notes.append(niveau.COMPACTE)


def planifie(projet, choix=None, en_plus=None, livrables=None, premier=None):
    choix, en_plus, livrables = choix or {}, en_plus or [], livrables or []
    projet = _norm(projet)
    pl = Plan(projet)
    memoire._VUS.clear()
    r = memoire.resous(projet)
    if r.forme == Forme.Equipe:
        pl.deja = True
        pl.notes.append("déjà « un dossier par agent » : rien à déménager. `harnais mise-a-niveau` "
                        "complète ce qui manque.")
        return pl
    if r.forme in (Forme.EnPlace, Forme.Deportee):
        pl.bloquants.append("forme `%s` : la mémoire passe d'abord en `brain/` par `harnais "
                            "mise-a-niveau`, puis l'équipe en « un dossier par agent » par cet outil"
                            % memoire.forme_mot(r.forme))
        return pl
    if r.forme != Forme.Brain:
        pl.bloquants.append("forme `%s` : l'outil part d'une équipe `brain/`" % memoire.forme_mot(r.forme))
        return pl
    rd = memoire.racine_depot(projet)
    if rd is None or not egal(_norm(rd), projet):
        pl.bloquants.append("`%s` n'est pas le checkout principal du code" % projet)
        return pl
    pl.autonome = os.path.exists(os.path.join(pl.memoire, ".git"))
    dossiers, compacts = niveau.classe_agents(projet)
    if compacts:
        _classe_mixte(pl, dossiers, compacts)
        return pl
    mind = os.path.join(pl.memoire, "mind")
    pl.agents = sorted(set(n for n in (os.listdir(mind) if os.path.isdir(mind) else [])
                           if os.path.isdir(os.path.join(mind, n))) | set(dossiers))
    if not pl.agents:
        pl.bloquants.append("aucun agent dans `brain/mind/` : ce n'est pas une équipe")
        return pl
    c = equipe.profils_en_collision(pl.agents)
    if c is not None:
        pl.bloquants.append("%s : le menu d'agent n'en montrerait qu'un" % c)
    for n in pl.agents:
        if n in (".", "..") or any(ch in n for ch in "/\\:") or not agent.nom_de_profil(n):
            pl.bloquants.append("nom d'agent invalide : `%s`" % n)
    try:
        toutes = copies(projet)
    except RuntimeError as e:
        pl.bloquants.append(str(e))
        return pl
    # UNE COPIE DÉJÀ DISPARUE (« prunable ») n'a rien à déménager : elle est
    # nommée, et le témoin ne la compte pas.
    pl.copies = [(c, b) for c, b in toutes if vivante(c)]
    for c, _ in toutes:
        if not os.path.isdir(c):
            pl.notes.append("copie déjà disparue du disque, ignorée : %s (`git worktree prune`)" % c)
        elif not vivante(c):
            pl.notes.append("copie sans `.git`, ignorée et laissée telle quelle : %s" % c)
    chemins = [c for c, _ in pl.copies]

    def parmi(c):
        return next((x for x in chemins if egal(x, c)), None)

    # LE PREMIER REÇOIT LE CHECKOUT PRINCIPAL, qui ne se déplace qu'en bloc. Copilot ne
    # garde aucune trace de « d'où se lançait quel agent » : sans `--premier`, c'est le
    # premier par ordre alphabétique qui n'est pas QA (QA ne répare pas le code).
    if premier is not None and premier not in pl.agents:
        pl.bloquants.append("--premier %s : n'est pas un agent (%s)" % (premier, ", ".join(pl.agents)))
    else:
        pl.premier = premier or next((n for n in pl.agents if not equipe.est_qa(n)), pl.agents[0])
    vus = {}
    for n in pl.agents:
        pl.badge[n] = projet
        if n in choix:
            c = parmi(_norm(choix[n]))
            if c is None or egal(c, projet):
                pl.bloquants.append("--copie %s : `%s` n'est pas une copie de ce dépôt (hors le checkout "
                                    "principal, que reçoit %s)" % (n, choix[n], pl.premier))
                continue
            if n == pl.premier:
                pl.bloquants.append("--copie %s : %s reçoit le checkout principal (`--premier` pour "
                                    "en changer)" % (n, n))
                continue
            pl.copie[n] = c
            pl.badge[n] = c
            if parmi(c) in vus:
                pl.bloquants.append("`%s` et `%s` partagent la même copie" % (vus[parmi(c)], n))
            vus[parmi(c)] = n
    if pl.premier:
        pl.copie[pl.premier] = projet
    for spec in en_plus:
        m = re.match(r"^([^:=]+):([A-Za-z0-9._-]+)=(.+)$", spec)
        if m is None:
            pl.bloquants.append("--en-plus `%s` : la forme est NOM:SUJET=CHEMIN" % spec)
            continue
        n, s, c = m.group(1), m.group(2), parmi(_norm(m.group(3)))
        if n not in pl.agents:
            pl.bloquants.append("--en-plus : `%s` n'est pas un agent" % n)
        if c is None or egal(c, projet) or c in vus:
            pl.bloquants.append("--en-plus : `%s` n'est pas une copie libre de ce dépôt" % m.group(3))
            continue
        pl.en_plus.append((n, s, c))
        vus[c] = n
    # Qui n'a pas de copie en reçoit une NEUVE, comme à la naissance : une branche à son nom.
    pris = dict((b, c) for c, b in pl.copies if b)
    branches = set()
    for n in pl.agents:
        if n in pl.copie:
            continue
        b = equipe._branche(n)
        if b in branches:
            pl.bloquants.append("deux agents donnent la même branche `%s`" % b)
        branches.add(b)
        existe = _git(projet, ["rev-parse", "--verify", "-q", "refs/heads/" + b])[0] == 0
        if existe and b in pris:
            pl.bloquants.append("la branche `%s` de %s est déjà prise par la copie `%s` : `--copie %s=<cette copie>`"
                                % (b, n, pris[b], n))
        pl.nouvelles.append((n, b, existe))
    pl.restent = [c for c in chemins if not egal(c, projet) and c not in vus
                  and not any(egal(c, x) for x in pl.copie.values())]
    pl.livrables = list(livrables)
    _verifie(pl)
    if pl.premier:
        pl.corr = correspondances(pl)
    return pl


def _verifie(pl):
    p = pl.projet
    if os.path.exists(pl.temp):
        pl.bloquants.append("`%s` existe déjà : un déménagement interrompu ? Le regarder d'abord" % pl.temp)
    if pl.autonome:
        c, out, _ = _git(pl.memoire, ["status", "--porcelain"])
        if c != 0:
            pl.bloquants.append("`brain/` ne répond pas à git")
        elif out.strip():
            pl.bloquants.append("la mémoire a des changements non enregistrés (%d) : les enregistrer "
                                "d'abord, et couper toute synchronisation" % len(out.strip().split("\n")))
        for x in ("agents", "shared", "docs", "assets", "AGENTS.md"):
            if os.path.exists(os.path.join(pl.memoire, x)):
                pl.bloquants.append("`brain/%s` existe déjà : il serait écrasé par ce qui monte" % x)
    else:
        c, out, _ = _git(p, ["status", "--porcelain", "--", "brain"])
        if c == 0 and out.strip():
            pl.notes.append("`brain/` porte %d modification(s) non enregistrée(s) : elles sont copiées telles "
                            "qu'elles sont sur le disque, et restent non enregistrées dans le code"
                            % len(out.strip().split("\n")))
        pl.notes.append("`brain/` vit dans le dépôt du code : la mémoire est COPIÉE vers un dépôt neuf "
                        "(son historique passé reste lisible dans le dépôt du code, intact)")
    # L'ESPACE DES LIVRABLES D'AVANT passe d'abord à `assets/` (mise-a-niveau) : traduire
    # des droits vers un dossier qui n'existe pas encore serait un périmètre qui ne mord plus.
    for rel in niveau.LIVRABLES_ANCIENS:
        if os.path.isdir(os.path.join(p, *rel.split("/"))):
            pl.bloquants.append("`%s/` (l'espace des livrables d'avant) : `harnais mise-a-niveau` le passe "
                                "d'abord à `assets/`" % rel)
    # `docs/` : UN exemplaire monte, il faut qu'il n'y en ait qu'une version.
    ref = os.path.join(p, "docs")
    if os.path.isdir(ref):
        e_ref = arbre_empreintes(ref)
        for n, c in sorted(pl.copie.items()):
            if egal(c, p):
                continue
            d = os.path.join(c, "docs")
            e = arbre_empreintes(d) if os.path.isdir(d) else {}
            ecart = sorted(k for k in set(e_ref) | set(e) if e_ref.get(k) != e.get(k))
            if ecart:
                pl.bloquants.append("`docs/` diffère entre la copie principale et celle de %s (%d "
                                    "fichier(s) : %s) — à réunir avant le jour J"
                                    % (n, len(ecart), ", ".join(ecart[:5]) + (", …" if len(ecart) > 5 else "")))
    montent = [(x, os.path.join(p, x)) for x in
               ["docs", "assets", "AGENTS.md", os.path.join(".github", "copilot-instructions.md")] + pl.livrables]
    if not pl.autonome:
        montent.append(("brain", os.path.join(p, "brain")))
    for n in pl.agents:
        montent.append((os.path.join("agents", n), os.path.join(pl.badge[n], "agents", n)))
    for x, chemin in montent:
        # Dans un dossier d'agent, seuls les fichiers COPIÉS montent : un `.env` ou un
        # `.mcp.json` y reste dans le code, nommé plus bas.
        garde = _transmis if x.startswith("agents" + os.sep) else None
        s = secrets(chemin, rel_base=os.path.dirname(x), garde=garde)
        if s:
            pl.bloquants.append("ce qui monte dans la mémoire (publiée sur GitHub) porte des fichiers "
                                "sensibles : %s" % ", ".join(s[:5]))
    for x in pl.livrables:
        if not os.path.exists(os.path.join(p, x)):
            pl.bloquants.append("--livrable `%s` n'existe pas dans le code" % x)
    # Deux sources pour un même fichier d'un agent : jamais l'une par-dessus l'autre.
    for n in pl.agents:
        etat = os.path.join(pl.memoire, "mind", n)
        badge = os.path.join(pl.badge[n], "agents", n)
        a = set(_fichiers(etat))
        b = set(_fichiers(badge))
        for f in sorted(a & b):
            if f in (".github/copilot/perimetre.json", ".github/copilot/settings.json"):
                continue
            pl.bloquants.append("`%s` existe à la fois dans l'état de %s et dans son dossier d'agent : "
                                "en garder un" % (f, n))
    for n in pl.agents:
        restent = [f for f in _fichiers(os.path.join(pl.badge[n], "agents", n))
                   if not _transmis(f) and f not in (".github/copilot/perimetre.json", ".github/copilot/settings.json")
                   and not f.startswith(".claude/")]
        if restent:
            pl.notes.append("%s : reste dans le code, ne monte pas (accès et secrets) : %s"
                            % (n, ", ".join(restent[:5])))
        if not os.path.isfile(os.path.join(pl.badge[n], "agents", n, ".github", "copilot", "perimetre.json")):
            pl.notes.append("%s : aucun périmètre — il recevra celui de la naissance" % n)
        if not os.path.isfile(os.path.join(pl.badge[n], "agents", n, "AGENTS.md")):
            pl.notes.append("%s : aucun rôle (`AGENTS.md`) — un gabarit à remplir sera posé" % n)
        if os.path.isfile(agent.profil(p, n)):
            pl.notes.append("profil `%s` du code : non repris (le profil neuf est posé) — le relire s'il "
                            "a été ajusté" % os.path.relpath(agent.profil(p, n), p))


def _fichiers(d):
    """Les fichiers sous `d` (chemins relatifs en `/`), `.DS_Store` et `.git` exclus."""
    out = []
    for b, dirs, fs in os.walk(d):
        dirs[:] = [x for x in dirs if x != ".git"]
        for f in fs:
            if f != ".DS_Store":
                out.append(os.path.relpath(os.path.join(b, f), d).replace(os.sep, "/"))
    return out


# ── LES DROITS : traduits vers la nouvelle forme ─────────────────────────────

def correspondances(pl):
    """`[(ancien, nouveau)]` absolus : l'ADRESSE de chaque copie du code, calculée
    AVANT le déplacement sur la forme d'avant. Les dossiers de la mémoire se
    traduisent dans `traduit_entree`, qui connaît l'agent dont c'est le droit."""
    v = []
    for c, _ in pl.copies:
        t = pl.cible(c)
        if t is not None and not egal(c, pl.projet) and not pl.niche(c):
            v.append((c, t))
    return sorted(v, key=lambda c: -len(niveau.decoupe(c[0])[1]))


def traduit_entree(e, nom, pl):
    """Un droit (`deny` / `allow`) d'AVANT, traduit pour l'agent `nom` : `(liste, note)`.

    CHAQUE ANCIENNE RÈGLE GARDE SON SENS D'ORIGINE. Relatif, un droit se lisait depuis
    la racine de la copie où l'agent travaillait :
      · ce qui était la mémoire change d'adresse (`brain/mind/QA` -> `agents/QA`,
        `brain/fact` -> `fact`, `brain/workspace` -> `shared`) ;
      · `agents` (le dossier de TOUS les rôles) vise désormais les dossiers des pairs :
        dans la forme neuve il porte aussi l'état et le code de l'agent lui-même ;
      · tout le reste était du CODE : c'est celui de l'agent, `agents/<nom>/code/…`.
    Un absolu reste absolu, un relatif relatif ; chacun garde son séparateur."""
    if not isinstance(e, str) or not e.strip():
        return [e], None
    p = pl.projet
    racine_e, comps_e = niveau.decoupe(e)
    if os.name == "nt" and racine_e == "/":
        return [e], None
    relatif = racine_e == ""
    sep = "\\" if ("\\" in e and "/" not in e) else "/"
    base = pl.badge.get(nom, p)
    proprio = nom
    if relatif:
        if not comps_e or comps_e == [".."] or comps_e[0] == "..":
            return [e], None
        comps = list(comps_e)
    else:
        r = niveau.sous(e, base)
        if r is None:
            # Une autre copie du code qui déménage : elle suit.
            for c, t in correspondances(pl):
                rr = niveau.sous(e, c)
                if rr is not None:
                    return [_ecrit_abs(t, rr, sep)], None
            # Le checkout principal, quand l'agent travaillait ailleurs : son code est celui du premier.
            r = niveau.sous(e, p)
            if r:
                proprio = pl.premier
            else:
                return [e], None
        if not r:
            return [e], None
        comps = list(r)
    autres = [a for a in pl.agents if a != nom]
    note = None
    neuf = []
    # Sous Windows la casse ne distingue pas deux dossiers : on classe sur la minuscule,
    # on écrit avec la casse d'origine.
    cmp = [c.lower() for c in comps] if os.name == "nt" else comps
    t0 = cmp[0]
    if t0 == "brain":
        if len(comps) >= 3 and cmp[1] == "mind":
            neuf = [["agents", comps[2]] + comps[3:]]
        elif len(comps) >= 2 and cmp[1] == "fact":
            neuf = [["fact"] + comps[2:]]
        elif len(comps) >= 2 and cmp[1] == "workspace":
            neuf = [["shared"] + comps[2:]]
        elif len(comps) == 2 and cmp[1] == "poids.json":
            neuf = [["poids.json"]]
        elif len(comps) == 2 and cmp[1] == "mind":
            neuf = [["agents", a] for a in autres]
        elif len(comps) == 1:
            neuf = [["fact"], ["shared"], ["poids.json"]] + [["agents", a] for a in autres]
        elif pl.autonome:
            neuf = [comps[1:]]
        else:
            neuf = [comps]
            note = "droit `%s` : dossier de `brain/` que la méthode ne prévoit pas — non traduit" % e
    elif t0 == "agents":
        if len(comps) == 1:
            neuf = [["agents", a] for a in autres]
        else:
            neuf = [comps]
    elif t0 in MEMOIRE_PREMIER or cmp[:2] in ([".github", "agents"], [".github", "copilot"]) \
            or cmp == [".github"]:
        neuf = [comps]
    else:
        neuf = [["agents", proprio, "code"] + comps]
    sortie = []
    for c in neuf:
        if relatif:
            s = sep.join(c)
        else:
            s = _ecrit_abs(p, c, sep)
        if s not in sortie:
            sortie.append(s)
    return sortie, note


def _ecrit_abs(racine, comps, sep):
    rc, cc = niveau.decoupe(racine)
    return niveau.compose(rc, cc + list(comps), sep)


def traduit_droits(texte, nom, pl):
    """Un `perimetre.json` d'avant, traduit : `(texte, nombre d'entrées changées, notes)`."""
    v = json.loads(texte) if texte.strip() else {}
    if not isinstance(v, dict):
        raise ValueError("pas un objet")
    n, notes = 0, []
    for cle in ("deny", "allow"):
        liste = v.get(cle)
        if not isinstance(liste, list):
            continue
        neuf = []
        for x in liste:
            ys, note = traduit_entree(x, nom, pl)
            n += 1 if ys != [x] else 0
            if note:
                notes.append(note)
            for y in ys:
                if y not in neuf:
                    neuf.append(y)
        v[cle] = neuf
    return json.dumps(v, indent=2, ensure_ascii=False) + "\n", n, notes


# ── LE GESTE ────────────────────────────────────────────────────────────────

class Echec(Exception):
    pass


def _journal(pl, fait, geste):
    fait.append(geste)
    f = pl.projet.rstrip("/\\") + ".demenage.json"
    try:
        with open(f, "w", encoding="utf-8") as h:
            json.dump({"projet": pl.projet, "fait": fait}, h, ensure_ascii=False, indent=1)
    except OSError:
        pass


def _dossier(pl, fait, d):
    """`makedirs` qui inscrit chaque dossier créé au journal : le retour arrière les
    retire, sinon l'essai suivant trouve `agents/` déjà là et refuse."""
    manquants = []
    while d and not os.path.isdir(d):
        manquants.append(d)
        d = os.path.dirname(d)
    for x in reversed(manquants):
        os.mkdir(x)
        _journal(pl, fait, ["mkdir", x])


def deplace_le_code(pl, fait):
    """Étapes 2 à 6. Lève `Echec` après avoir tenté le retour arrière."""
    p, t = pl.projet, pl.temp
    avant = {c: inventaire(c) for c, _ in pl.copies if os.path.isdir(c)}
    etats = {c: etat_git(c, sans_brain=(c == p and pl.autonome)) for c in avant}
    branches = dict(pl.copies)
    fantomes = set()
    try:
        fantomes = {c for c, _ in copies(p) if not vivante(c)}
    except RuntimeError:
        pass
    os.rename(p, t)
    _journal(pl, fait, ["mv", p, t])
    if pl.autonome:
        os.rename(os.path.join(t, "brain"), p)
        _journal(pl, fait, ["mv", os.path.join(t, "brain"), p])
    else:
        # B : la mémoire naît dans un dépôt neuf ; l'ancienne reste dans le code.
        os.mkdir(p)
        _journal(pl, fait, ["mkdir", p])
        _ok(p, ["init", "-q", "-b", "main"])
        _journal(pl, fait, ["init", p])
    nouveau = os.path.join(p, "agents", pl.premier, "code")
    _dossier(pl, fait, os.path.dirname(nouveau))
    os.rename(t, nouveau)
    _journal(pl, fait, ["mv", t, nouveau])
    autres = [pl.niche(c) or c for c, _ in pl.copies[1:]]
    autres = [c for c in autres if os.path.isdir(c) and c not in fantomes]
    if autres:
        _ok(nouveau, ["worktree", "repair"] + autres)
    _journal(pl, fait, ["repair"])
    for c, _ in pl.copies[1:]:
        cible = pl.cible(c)
        if cible is None or pl.niche(c) or not os.path.isdir(c):
            continue
        _dossier(pl, fait, os.path.dirname(cible))
        _ok(nouveau, ["worktree", "move", c, cible])
        _journal(pl, fait, ["move", c, cible])
    _ok(nouveau, ["worktree", "repair"])
    # Une copie NEUVE pour qui n'en avait pas, comme à la naissance.
    for n, b, existe in pl.nouvelles:
        d = os.path.join(p, "agents", n, "code")
        _dossier(pl, fait, os.path.dirname(d))
        if existe:
            _ok(nouveau, ["worktree", "add", "-q", d, b])
        else:
            _ok(nouveau, ["worktree", "add", "-q", "-b", b, d])
        _journal(pl, fait, ["wtadd", d, b, "" if existe else "cree"])
    # LE TÉMOIN.
    mal = []
    memoire._VUS.clear()
    apres = copies(nouveau)
    apres = [(c, b) for c, b in apres if c not in fantomes]
    attendu = len(pl.copies) + len(pl.nouvelles)
    if len(apres) != attendu:
        mal.append("%d copies attendues, %d après" % (attendu, len(apres)))
    chemins_apres = dict(apres)
    for c, b in apres:
        if not os.path.isdir(c):
            mal.append("copie absente : %s" % c)
            continue
        if _git(c, ["rev-parse", "--git-dir"])[0] != 0:
            mal.append("copie sans dépôt : %s" % c)
    for c, ib in avant.items():
        neuf = pl.niche(c) or (pl.cible(c) if not egal(c, p) else nouveau) or c
        if branches.get(c) != chemins_apres.get(_norm(neuf)):
            mal.append("branche changée : %s" % neuf)
        ia = inventaire(neuf)
        if egal(c, p) and pl.autonome:
            # Le checkout principal a perdu `brain/` — c'est voulu.
            ib = ({k: v for k, v in ib[0].items() if not k.startswith("brain/")}, ib[1])
        if ia[0] != ib[0]:
            diff = sorted(set(ia[0]) ^ set(ib[0]))[:3] or sorted(k for k in ia[0] if ia[0][k] != ib[0].get(k))[:3]
            mal.append("inventaire différent dans %s (%s)" % (neuf, ", ".join(diff) or "tailles"))
        ea = etat_git(neuf, sans_brain=(egal(c, p) and pl.autonome))
        if ea != etats[c]:
            mal.append("l'état git a changé dans %s (HEAD, branche ou modifications non enregistrées)" % neuf)
    if mal:
        raise Echec("; ".join(mal))
    return nouveau


def retour_arriere(pl, fait):
    """Les mêmes gestes, en sens inverse. Rend la liste de ce qui n'a pas pu être
    défait — vide si tout est revenu."""
    reste = []
    principal = None
    for g in fait:
        if g[0] == "mv" and g[2].endswith(os.path.join("agents", pl.premier or "", "code")):
            principal = g[2]
    for g in reversed(fait):
        try:
            if g[0] == "move" and principal:
                _ok(principal, ["worktree", "move", g[2], g[1]])
            elif g[0] == "wtadd" and principal:
                _ok(principal, ["worktree", "remove", "--force", g[1]])
                if g[3]:
                    _ok(principal, ["branch", "-D", g[2]])
            elif g[0] == "mkdir":
                if os.path.isdir(g[1]):
                    os.rmdir(g[1])
            elif g[0] == "init":
                _rmtree(os.path.join(g[1], ".git"))
            elif g[0] == "memoire":
                _purge_memoire(g[1])
            elif g[0] == "mv":
                os.rename(g[2], g[1])
                if principal == g[2]:
                    principal = g[1]
        except (OSError, RuntimeError) as e:
            reste.append("%s : %s" % (" ".join(g), e))
    if principal and os.path.isdir(principal):
        autres = [c for c, _ in pl.copies[1:] if os.path.isdir(c)]
        _git(principal, ["worktree", "repair"] + autres)
    return reste


def _purge_memoire(p):
    """B : la mémoire neuve est faite de COPIES ; tout ce que le déménagement y a posé
    est retiré, sauf les copies du code (`agents/*/code*`), qui reviennent à part."""
    for n in os.listdir(p):
        c = os.path.join(p, n)
        if n == ".git":
            _rmtree(c)
        elif n == "agents" and os.path.isdir(c):
            for a in os.listdir(c):
                da = os.path.join(c, a)
                if not os.path.isdir(da):
                    os.remove(da)
                    continue
                for x in os.listdir(da):
                    if x == "code" or x.startswith("code-"):
                        continue
                    f = os.path.join(da, x)
                    _rmtree(f) if os.path.isdir(f) else os.remove(f)
        elif os.path.isdir(c):
            _rmtree(c)
        else:
            os.remove(c)


# ── LA MÉMOIRE ──────────────────────────────────────────────────────────────

# Ce qu'un dossier d'agent d'avant ne transmet PAS : les droits (traduits à part), la
# déclaration du paquet par agent (Copilot ne lit que celle de la racine Git), les accès
# des connexions (jamais sur GitHub), les restes de Claude, l'ancien état.
def _transmis(rel):
    if rel in (".github/copilot/perimetre.json", ".github/copilot/settings.json"):
        return False
    if rel.startswith((".claude/", ".mind/")) or rel.endswith(".DS_Store"):
        return False
    return not est_secret(rel)


def _copie_verifiee(s, d, ops, temoins):
    """Copie un fichier ou un dossier et RELIT l'arrivée : l'empreinte doit être celle
    de la source. Rend la liste des couples (source, arrivée) comparés."""
    if os.path.isdir(s):
        shutil.copytree(s, d, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".git", ".DS_Store"))
        a, b = arbre_empreintes(s), arbre_empreintes(d)
        for k, h in a.items():
            if b.get(k) != h:
                raise Echec("copie de `%s` différente à l'arrivée (%s)" % (s, k))
            temoins.append((os.path.join(s, k), os.path.join(d, k)))
    else:
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)
        if empreinte(s) != empreinte(d):
            raise Echec("copie de `%s` différente à l'arrivée" % s)
        temoins.append((s, d))


def range_la_memoire(pl, ops, fait):
    """Dans le dépôt de la mémoire seulement : états, carnet, faits, badges, droits,
    profils, docs, livrables, consignes. Un seul enregistrement."""
    p = pl.projet
    j = os.path.join
    code = pl.code()
    temoins = []                         # [(source, arrivée)] à comparer à la fin
    if not pl.autonome:
        _journal(pl, fait, ["memoire", p])
    brain_code = j(code, "brain")        # B : où l'ancienne mémoire a atterri
    # 1. l'état de chaque agent, et le carnet
    for n in pl.agents:
        dest = j(p, "agents", n)
        os.makedirs(dest, exist_ok=True)
        if pl.autonome:
            src = j(p, "mind", n)
            for f in sorted(os.listdir(src)) if os.path.isdir(src) else []:
                _ok(p, ["mv", "-k", "/".join(["mind", n, f]), "/".join(["agents", n, f])])
                if os.path.exists(j(src, f)):
                    shutil.move(j(src, f), j(dest, f))
        else:
            src = j(brain_code, "mind", n)
            for f in sorted(os.listdir(src)) if os.path.isdir(src) else []:
                _copie_verifiee(j(src, f), j(dest, f), ops, temoins)
        ops.append("état de %s : mind/%s -> agents/%s" % (n, n, n))
    if pl.autonome:
        if os.path.isdir(j(p, "mind")) and not os.listdir(j(p, "mind")):
            os.rmdir(j(p, "mind"))
        if os.path.isdir(j(p, "workspace")):
            _ok(p, ["mv", "workspace", "shared"])
            ops.append("carnet : workspace -> shared")
        else:
            os.makedirs(j(p, "shared"), exist_ok=True)
    else:
        for de, vers in (("fact", "fact"), ("workspace", "shared"), ("poids.json", "poids.json")):
            if os.path.exists(j(brain_code, de)):
                _copie_verifiee(j(brain_code, de), j(p, vers), ops, temoins)
                ops.append("copié et vérifié : brain/%s -> %s" % (de, vers))
        os.makedirs(j(p, "shared"), exist_ok=True)
        for n in sorted(os.listdir(brain_code)) if os.path.isdir(brain_code) else []:
            if n not in BRAIN_CONNU and n not in (".git", ".DS_Store"):
                ops.append("⚠ brain/%s : hors méthode, laissé dans le code — à ranger" % n)
    # 2. le .gitignore
    gi = j(p, ".gitignore")
    t = _lis(gi) if os.path.isfile(gi) else ""
    if pl.autonome:
        ajouts = [x for x in equipe.GITIGNORE_EQUIPE.split("\n") if x and not x.startswith("#")
                  and x not in t.split("\n")]
        if ajouts:
            with open(gi, "a", encoding="utf-8", newline="") as h:
                h.write(("" if not t or t.endswith("\n") else "\n")
                        + "# un dossier par agent (harnais demenage)\n" + "\n".join(ajouts) + "\n")
    else:
        equipe.ecrit(gi, equipe.GITIGNORE_EQUIPE)
    # 3. le dossier de chaque agent : rôle, droits traduits
    nom_projet = os.path.basename(p.rstrip("/\\"))
    for n in pl.agents:
        de = j(pl.cible(pl.badge[n]) if not egal(pl.badge[n], p) else code, "agents", n)
        vers = j(p, "agents", n)
        for f in _fichiers(de) if os.path.isdir(de) else []:
            if _transmis(f):
                _copie_verifiee(j(de, *f.split("/")), j(vers, *f.split("/")), ops, temoins)
        if not os.path.isfile(j(vers, "AGENTS.md")):
            equipe.ecrit(j(vers, "AGENTS.md"), adopte.agents_md_agent(n, nom_projet))
            ops.append("rôle de %s : gabarit posé (aucun AGENTS.md d'avant)" % n)
        etat = j(vers, "state.md")
        if not os.path.isfile(etat):
            ops.append("⚠ %s n'a pas de state.md : `harnais mise-a-niveau` en pose un" % n)
        src_droits = j(de, ".github", "copilot", "perimetre.json")
        cible_droits = j(vers, ".github", "copilot", "perimetre.json")
        k = 0
        if os.path.isfile(src_droits):
            texte, k, notes = traduit_droits(_lis(src_droits), n, pl)
            os.makedirs(os.path.dirname(cible_droits), exist_ok=True)
            equipe.ecrit(cible_droits, texte)
            for x in notes:
                ops.append("⚠ %s : %s" % (n, x))
        rap = []
        equipe.perimetre_agent(vers, p, [a for a in pl.agents if a != n], True, rap, equipe_forme=True)
        ops.append("droits de %s : %d entrée(s) traduite(s), périmètre de la naissance complété" % (n, k))
    # 4. docs, assets, consignes communes, livrables
    sources = [("docs", "docs"), ("assets", "assets"), ("AGENTS.md", "AGENTS.md"),
               (os.path.join(".github", "copilot-instructions.md"), os.path.join(".github", "copilot-instructions.md"))]
    sources += [(x, os.path.join("assets", os.path.basename(x))) for x in pl.livrables]
    for de, vers in sources:
        s, d = j(code, de), j(p, vers)
        if not os.path.exists(s):
            continue
        _copie_verifiee(s, d, ops, temoins)
        ops.append("copié et vérifié : %s -> %s" % (de.replace(os.sep, "/"), vers.replace(os.sep, "/")))
    if not os.path.exists(j(p, "AGENTS.md")):
        equipe.ecrit(j(p, "AGENTS.md"), equipe.AGENTS_PROJET.replace("{PROJET}", nom_projet))
        ops.append("AGENTS.md du projet : gabarit posé (aucun d'avant)")
    # 5. ce que pose la naissance : déclaration du paquet, profils, méthode, carnet
    rap = []
    try:
        equipe.reglages_racine(p, True, rap)
    except copilot.Refus as e:
        ops.append("⚠ déclaration du paquet : %s — à régler à la main" % e)
    racine_git = copilot.racine_git(p)
    for n in pl.agents:
        equipe.profil(racine_git, p, n, j(p, "agents", n), True, rap)
    inf = j(p, ".github", "copilot-instructions.md")
    try:
        texte = adopte.instructions(inf, p)
    except copilot.Refus as e:
        texte = None
        ops.append("⚠ méthode du projet : %s" % e)
    if texte is not None:
        os.makedirs(os.path.dirname(inf), exist_ok=True)
        equipe.ecrit(inf, texte)
    carnet.amorce(j(p, "agents", pl.premier))
    ops.append("profils du menu d'agent, déclaration du paquet, carnet : posés comme à la naissance")
    # 6. le TÉMOIN d'intégrité : tout ce qui a été copié se retrouve à l'octet
    for s, d in temoins:
        if not os.path.isfile(d) or empreinte(s) != empreinte(d):
            raise Echec("empreinte différente à l'arrivée : %s" % d)
    ops.append("témoin : %d fichier(s) comparés par empreinte, tous identiques" % len(temoins))
    # 7. un seul enregistrement — et rien de sensible dedans
    _ok(p, ["add", "-A"])
    suivis = _ok(p, ["diff", "--cached", "--name-only"]).split("\n")
    trouves = [f for f in suivis if f and est_secret(f)]
    if trouves:
        _git(p, ["reset", "-q"])
        raise Echec("un fichier sensible allait être enregistré : %s" % ", ".join(trouves[:5]))
    c, _, _ = _git(p, ["diff", "--cached", "--quiet"])
    if c != 0:
        _ok(p, ["-c", "user.name=harnais", "-c", "user.email=harnais@atelier", "-c", "commit.gpgsign=false",
                "commit", "-q", "-m", "Un dossier par agent : la mémoire devient le dossier du projet "
                                      "(harnais demenage)"])
        ops.append("mémoire enregistrée")
    memoire._VUS.clear()
    apres = memoire.resous(j(p, "agents", pl.premier))
    if apres.forme != Forme.Equipe:
        raise Echec("le résolveur, relancé à froid, dit `%s` et non `equipe`" % memoire.forme_mot(apres.forme))
    if os.path.exists(j(p, "brain")):
        raise Echec("un `brain/` subsiste dans la mémoire neuve")
    ops.append("le résolveur lit une équipe « un dossier par agent »")


def applique(pl):
    fait, ops = [], []
    try:
        deplace_le_code(pl, fait)
    except (Echec, OSError, RuntimeError) as e:
        reste = retour_arriere(pl, fait)
        if not reste:
            try:
                os.remove(pl.projet.rstrip("/\\") + ".demenage.json")
            except OSError:
                pass
        return ["ÉCHEC du déplacement du code : %s" % e] + (
            ["RETOUR ARRIÈRE INCOMPLET : %s" % r for r in reste] if reste else ["retour arrière fait : tout est revenu"])
    ops.append("code déplacé : %d copie(s), témoin vert" % len(pl.copies))
    try:
        range_la_memoire(pl, ops, fait)
    except (Echec, OSError, RuntimeError, ValueError, copilot.Refus) as e:
        if pl.autonome:
            return ops + ["ÉCHEC du rangement de la mémoire : %s — le code est en place ; la mémoire "
                          "est à reprendre (git status dans %s)" % (e, pl.projet)]
        # B : la mémoire neuve n'est que des copies, l'ancienne n'a pas bougé — tout se défait.
        reste = retour_arriere(pl, fait)
        if not reste:
            try:
                os.remove(pl.projet.rstrip("/\\") + ".demenage.json")
            except OSError:
                pass
        return ops + ["ÉCHEC du rangement de la mémoire : %s" % e] + (
            ["RETOUR ARRIÈRE INCOMPLET : %s" % r for r in reste] if reste else ["retour arrière fait : tout est revenu"])
    try:
        os.remove(pl.projet.rstrip("/\\") + ".demenage.json")
    except OSError:
        pass
    return ops


def _affiche(pl):
    _p("\n  %sDÉMÉNAGEMENT — un dossier par agent%s   %s%s%s" % (B, X, D, pl.projet, X))
    for n in pl.notes:
        _p("  %s· %s%s" % (D, n, X))
    if pl.deja or pl.compacte:
        return
    _p("  %-22s %s" % ("mémoire", "brain/ a son propre dépôt (elle devient le projet, historique compris)"
                       if pl.autonome else "brain/ est dans le dépôt du code (copiée vers un dépôt neuf)"))
    if pl.premier:
        _p("  %-22s %s" % ("checkout principal", "-> agents/%s/code (un seul mv)" % pl.premier))
    for n in pl.agents:
        c = pl.copie.get(n)
        if c is not None and n != pl.premier:
            _p("  %-22s %s -> %s" % (n, c, pl.cible(c)))
    for n, b, existe in pl.nouvelles:
        _p("  %-22s copie neuve agents/%s/code, branche `%s`%s" % (n, n, b, " (existe déjà)" if existe else ""))
    for n, s, c in pl.en_plus:
        _p("  %-22s %s -> %s" % ("%s, en plus" % n, c, pl.cible(c)))
    for c in pl.restent:
        if pl.premier and pl.niche(c):
            _p("  %-22s %s — part avec le checkout principal" % ("copie imbriquée", c))
        else:
            _p("  %s%-22s %s — reste en place, signalée par la page d'équipe%s" % (J, "copie sans agent", c, X))
    for x in pl.livrables:
        _p("  %-22s %s -> assets/%s" % ("livrable", x, os.path.basename(x)))
    _p("  %s· écarté, sans objet chez Copilot : les conversations rangées par dossier de lancement et "
       "le registre des inscriptions au paquet (la déclaration vit dans `.github/copilot/settings.json`, "
       "qui voyage avec le dépôt)%s" % (D, X))
    _p("\n  %sÀ ENREGISTRER DANS LE CODE, sur demande de l'humain%s : retirer %s ; ajouter au "
       "`.gitignore` : %s" % (B, X, ", ".join("`%s`" % x for x in QUITTENT_LE_CODE + tuple(pl.livrables)),
                              " ".join("/%s/" % x for x in ("agents", "brain", "docs", "assets"))))
    if pl.bloquants:
        _p("\n  %sBLOQUÉ%s" % (R, X))
        for b in pl.bloquants:
            _p("    %s✗%s %s" % (R, X, b))


def valeurs(args, cle):
    v, i = [], 0
    while i < len(args):
        if args[i] == cle and i + 1 < len(args):
            v.append(args[i + 1])
            i += 2
        else:
            i += 1
    return v


def main(args):
    if not args or args[0].startswith("-"):
        _p("usage : harnais demenage <projet> [--premier NOM] [--copie NOM=CHEMIN]… "
           "[--en-plus NOM:SUJET=CHEMIN]… [--livrable CHEMIN]… [--apply --agents-arretes]")
        return 2
    choix = {}
    for s in valeurs(args, "--copie"):
        if "=" in s:
            k, c = s.split("=", 1)
            choix[k] = c
    premier = (valeurs(args, "--premier") or [None])[0]
    pl = planifie(args[0], choix, valeurs(args, "--en-plus"), valeurs(args, "--livrable"), premier)
    _affiche(pl)
    appliquer = "--apply" in args or "--go" in args
    if pl.deja or pl.compacte:
        return 0
    if not appliquer:
        _p("\n  %sÀ blanc%s : rien n'est écrit. `--apply --agents-arretes` pour déménager." % (D, X))
        return 1 if pl.bloquants else 0
    if pl.bloquants:
        _p("\n  Rien n'est écrit tant qu'un point bloque.")
        return 1
    if "--agents-arretes" not in args:
        _p("\n  %s--agents-arretes%s manque : un agent ouvert écrirait l'ancien chemin pendant "
           "le déplacement. Les arrêter, puis relancer." % (B, X))
        return 1
    ops = applique(pl)
    for o in ops:
        _p("  %s %s" % ("✗" if o.startswith(("ÉCHEC", "RETOUR")) else "✓", o))
    if not any(o.startswith(("ÉCHEC", "RETOUR")) for o in ops):
        _p("\n  Ensuite : `harnais mise-a-niveau %s` complète ce qui manque (faits, états), puis "
           "relancer les agents un par un." % pl.projet)
    return 1 if any(o.startswith(("ÉCHEC", "RETOUR")) for o in ops) else 0
