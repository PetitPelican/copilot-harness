# -*- coding: utf-8 -*-
"""FUSIONNER SANS RIEN PERDRE DE LA MÉMOIRE — PreToolUse Bash, joué avec `production`.

Le besoin (2.2.0). Une mémoire de projet qui vit DANS le dépôt du code se partage
par push et pull. Deux personnes qui pilotent chacune un agent du même projet
écrivent en même temps dans les mêmes fichiers (`state.md`, `todo.md`, les
faits). Le conflit se résout alors à la main — ou par un `--ours` / `--theirs`
pressé — et une moitié du travail de l'autre disparaît sans que rien le dise.

DEUX RÈGLES.

1. RÉCUPÉRER D'ABORD. `git push`, `git merge <branche>` et `git rebase <base>` sont
   refusés quand le dernier `git fetch` date de plus de `FRAICHEUR` minutes (ou n'a
   jamais eu lieu), et quand la branche suivie a des commits que la copie n'a pas
   intégrés : on intègre le travail de l'autre AVANT de pousser ou de fusionner le
   sien. `git pull` récupère de lui-même : il passe. Seulement dans un dépôt qui a
   un distant ET qui porte la mémoire du projet.

2. RIEN PERDU EN RÉSOLVANT. Quand une fusion, un rebase ou un cherry-pick s'est
   arrêté sur un conflit, `git commit`, `git merge --continue`, `git rebase
   --continue` et `git cherry-pick --continue` sont refusés si la résolution indexée
   d'un fichier de mémoire (`brain/fact/`, `brain/mind/`, à toute profondeur)
   PERD une ligne qu'un des deux côtés avait écrite et qu'aucun n'avait retirée —
   ou garde un marqueur de conflit. Les deux côtés se lisent contre leur base
   commune, ligne à ligne : une tâche cochée d'un côté remplace l'ancienne, elle ne
   s'additionne pas. Les lignes d'en-tête qui n'existent qu'une fois (`maj:`,
   `sante:`, `jalon:`) ne comptent pas : l'une des deux doit gagner.

3. DIRE CE QUI EST ARRIVÉ (2.2.1). Après un pull ou une fusion qui apporte des
   commits d'autres auteurs dans la mémoire du projet (`brain/fact/`,
   `brain/mind/`, `.logs/`), le briefing suivant le dit en une ligne — qui,
   combien de commits, quels fichiers — et demande de relire avant d'agir.

` # fusion-ok` en fin de commande lève les deux règles — hors réseau, ou une ligne
volontairement abandonnée — et reste dans l'historique du shell.

NON COUVERT (dit, pas deviné) : un client Git graphique, un alias, un script qui
fusionne à la place de l'agent ; une fusion sans conflit (Git la fait ligne à ligne,
sans perte) ; un `git push --force` après coup — la garde de la Production s'en
charge sur les branches qu'elle protège.

**fail-open** : une entrée illisible, un git absent, un historique inattendu
laissent passer. Une garde muette ne se distingue pas d'une garde qui laisse
passer — c'est pour cela que ses tests la font MORDRE.
"""
import os
import re
import time

FRAICHEUR = 15                  # minutes
MOT = "fusion-ok"
UNIQUES = re.compile(r"^\s*(maj|sante|santé|jalon)\s*:", re.I)
MARQUEURS = re.compile(r"^(<{7}|={7}|>{7}|\|{7})(\s|$)")
MEMOIRE = re.compile(r"(^|/)brain/(fact|mind)/")
SUITES = ("--continue",)
SORTIES = ("--abort", "--quit", "--skip")


def concerne(bas):
    """Le test bon marché, sur la charge brute en minuscules."""
    return "git" in bas and any(m in bas for m in ("push", "merge", "rebase", "commit", "cherry-pick"))


def _git(dossier, args, timeout=10):
    import subprocess
    try:
        o = subprocess.run(["git", "-C", dossier] + list(args), stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if o.returncode != 0:
        return None
    return o.stdout.decode("utf-8", "replace")


def commandes_git(cmd, base, powershell=False):
    """`[(dossier, verbe, arguments)]` pour chaque `git` de la ligne — `cd`, `-C`
    compris. Le découpage est celui de la garde de la Production."""
    import production as p
    jetons = p._jetons(cmd, powershell)
    out = []
    cwd, i = base, 0
    while i < len(jetons):
        t = jetons[i]
        if t.lower() in p.CHANGE_DOSSIER and i + 1 < len(jetons) and not jetons[i + 1].startswith("-"):
            cwd = p._resoudre(cwd, jetons[i + 1])
            i += 2
            continue
        fin = i + 1
        while fin < len(jetons) and jetons[fin] not in p.FINS:
            fin += 1
        tete = i
        while tete < fin and re.split(r"[\\/]", jetons[tete])[-1].lower() not in ("git", "git.exe"):
            tete += 1
        if tete < fin:
            dossier, k, verbe = cwd, tete + 1, None
            while k < fin:
                u = jetons[k]
                if u == "-C" and k + 1 < fin:
                    dossier = p._resoudre(dossier, jetons[k + 1])
                    k += 2
                    continue
                if u.startswith("-"):
                    k += 2 if u in p.PORTEUSES else 1
                    continue
                verbe = u
                break
            if verbe is not None:
                out.append((dossier, verbe, jetons[k + 1:fin]))
        i = fin + 1 if fin < len(jetons) else fin
    return out


# ── règle 1 : récupérer d'abord ──────────────────────────────────────────

def _git_dir(dossier):
    g = _git(dossier, ["rev-parse", "--absolute-git-dir"])
    return g.strip() if g else None


def _commun(dossier):
    g = _git(dossier, ["rev-parse", "--path-format=absolute", "--git-common-dir"])
    return g.strip() if g else None


def age_du_fetch(dossier):
    """Minutes depuis le dernier `git fetch` (lu sur `FETCH_HEAD`), ou None jamais."""
    c = _commun(dossier)
    if c is None:
        return None
    try:
        m = os.path.getmtime(os.path.join(c, "FETCH_HEAD"))
    except OSError:
        return None
    return max(0.0, (time.time() - m) / 60.0)


def porte_la_memoire(dossier, depart):
    """La mémoire du projet est-elle versionnée dans CE dépôt ?"""
    import agent
    import memoire
    top = _git(dossier, ["rev-parse", "--show-toplevel"])
    if not top:
        return False
    top = memoire._canon(memoire.natif(top.strip()))
    if top is None:
        return False
    r = memoire.resous_depuis(dossier, depart)
    if r.forme == memoire.Forme.Brain and not r.brain_autonome and r.arbre == top:
        return True
    # Une session ouverte à la racine sans agent choisi : le dépôt porte quand
    # même des mémoires — celle de la racine, ou celles des projets logés.
    return (os.path.isdir(os.path.join(top, "brain", "fact"))
            and not os.path.exists(os.path.join(top, "brain", ".git"))) or bool(agent.loges(top))


def en_retard(dossier):
    """`(suivie, n, fichiers de mémoire)` si la branche suivie a des commits que
    HEAD n'a pas, sinon None. Lu sur les références locales : aucun réseau."""
    u = _git(dossier, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if not u:
        return None
    u = u.strip()
    n = _git(dossier, ["rev-list", "--count", "HEAD..@{u}"])
    try:
        n = int((n or "0").strip())
    except ValueError:
        return None
    if n <= 0:
        return None
    noms = _git(dossier, ["diff", "--name-only", "HEAD...@{u}"]) or ""
    return u, n, [f for f in noms.splitlines() if MEMOIRE.search(f)]


def _echantillon(v, n=4):
    s = ", ".join(v[:n])
    return s + (" … (+%d)" % (len(v) - n) if len(v) > n else "")


def regle_fetch(dossier, verbe, args, depart):
    if verbe == "merge" and any(a in SUITES + SORTIES for a in args):
        return None
    if verbe == "rebase" and any(a in SUITES + SORTIES + ("--edit-todo", "--show-current-patch")
                                 for a in args):
        return None
    if not (_git(dossier, ["remote"]) or "").strip():
        return None
    if not porte_la_memoire(dossier, depart):
        return None
    age = age_du_fetch(dossier)
    if age is None or age > FRAICHEUR:
        if age is None:
            quand = "jamais"
        elif age < 120:
            quand = "il y a %d min" % int(age)
        elif age < 48 * 60:
            quand = "il y a %d h" % int(age / 60)
        else:
            quand = "il y a %d jours" % int(age / 1440)
        return ("fusion : `git %s` sans avoir récupéré le travail des autres (dernier `git fetch` : "
                "%s). La mémoire du projet voyage avec le code : on intègre d'abord. Lance "
                "`git fetch`, intègre ce qui est arrivé (`git pull --rebase`), relis l'état et les "
                "faits de ton projet, puis recommence. Hors réseau : ajoute ` # %s`."
                % (verbe, quand, MOT))
    r = en_retard(dossier)
    if r is not None:
        suivie, n, mem = r
        dont = (", dont la mémoire : %s" % _echantillon(mem)) if mem else ""
        return ("fusion : `%s` a %d commit(s) que ta copie n'a pas intégrés%s. Intègre-les AVANT "
                "de pousser ou de fusionner (`git pull --rebase`), en gardant les lignes des deux "
                "côtés dans l'état, les tâches et les faits ; puis recommence." % (suivie, n, dont))
    return None


# ── règle 2 : rien perdu en résolvant ─────────────────────────────────────

def _lignes(t):
    return [x.rstrip("\r") for x in (t or "").split("\n")]


def _cle(x):
    return x.strip()


def _compte(v):
    return set(_cle(x) for x in v if _cle(x) and not UNIQUES.match(x) and _cle(x) != "---")


def _version(dossier, rev, f):
    t = _git(dossier, ["show", "%s:%s" % (rev, f)])
    return _lignes(t) if t is not None else []


def cotes(dossier):
    """`(nature, ours, theirs, base)` d'une opération arrêtée, ou None."""
    g = _git_dir(dossier)
    if g is None:
        return None
    for nature, tete in (("fusion", "MERGE_HEAD"), ("rebase", "REBASE_HEAD"),
                         ("cherry-pick", "CHERRY_PICK_HEAD")):
        f = os.path.join(g, tete)
        if not os.path.isfile(f):
            continue
        try:
            with open(f, encoding="utf-8", errors="replace") as h:
                theirs = h.read().split()[0]
        except (OSError, IndexError):
            return None
        if nature == "fusion":
            b = _git(dossier, ["merge-base", "HEAD", theirs])
        else:
            b = _git(dossier, ["rev-parse", "--verify", "-q", theirs + "^"])
        if not b:
            return None
        return nature, "HEAD", theirs, b.split()[0]
    return None


def pertes(dossier):
    """`(nature, {fichier: [lignes perdues]}, [fichiers à marqueurs])` — ou None
    hors d'une opération arrêtée."""
    c = cotes(dossier)
    if c is None:
        return None
    nature, ours, theirs, base = c
    noms = set()
    for a in (ours, theirs):
        t = _git(dossier, ["diff", "--name-only", base, a]) or ""
        noms.update(f for f in t.splitlines() if MEMOIRE.search(f))
    if not noms:
        return nature, {}, []
    non_fusionnes = set((_git(dossier, ["diff", "--name-only", "--diff-filter=U"]) or "").splitlines())
    perdues, marques = {}, []
    for f in sorted(noms):
        if f in non_fusionnes:
            continue            # git refusera de lui-même : le conflit n'est pas résolu
        res = _git(dossier, ["show", ":%s" % f])
        resultat = _lignes(res) if res is not None else []
        if any(MARQUEURS.match(x) for x in resultat):
            marques.append(f)
        b, o, t = (_compte(_version(dossier, r, f)) for r in (base, ours, theirs))
        retirees = (b - o) | (b - t)
        exige = (o | t) - retirees
        manque = exige - set(_cle(x) for x in resultat)
        if manque:
            perdues[f] = sorted(manque)
    return nature, perdues, marques


def regle_resolution(dossier):
    p = pertes(dossier)
    if p is None:
        return None
    nature, perdues, marques = p
    if marques:
        return ("fusion : des marqueurs de conflit (`<<<<<<<`, `=======`, `>>>>>>>`) restent dans "
                "la mémoire indexée : %s. Résous-les en gardant les lignes des deux côtés, "
                "réindexe, puis recommence." % _echantillon(marques))
    if not perdues:
        return None
    n = sum(len(v) for v in perdues.values())
    exemples = []
    for f, v in sorted(perdues.items()):
        for x in v[:3]:
            exemples.append("%s : « %s »" % (f, x[:100]))
    return ("fusion : la résolution de ce %s PERD %d ligne(s) de la mémoire — écrites par l'un des "
            "deux côtés, retirées par aucun :\n  %s\nReprends-les : chaque côté garde ses tâches, son "
            "état et ses faits ; une même tâche avancée des deux côtés se tranche en gardant la plus "
            "avancée. Réindexe (`git add`), puis recommence. Si l'abandon est voulu, ajoute ` # %s`."
            % (nature, n, "\n  ".join(exemples[:8]), MOT))


# ── le juge ──────────────────────────────────────────────────────────────

def autorise(cmd):
    return re.search(r"#\s*%s\s*$" % re.escape(MOT), cmd.rstrip()) is not None


def juge(d):
    """Le motif du refus, ou None."""
    import hote
    if not isinstance(d, dict) or not hote.est_shell(d):
        return None
    ti = d.get("tool_input") if isinstance(d.get("tool_input"), dict) else {}
    cmd = ti.get("command")
    if not isinstance(cmd, str) or autorise(cmd):
        return None
    base = d.get("cwd") or os.environ.get("COPILOT_PROJECT_DIR") or os.getcwd()
    depart = os.environ.get("COPILOT_PROJECT_DIR") or base
    for dossier, verbe, args in commandes_git(cmd, base, hote.est_powershell(d)):
        if not os.path.isdir(dossier):
            continue
        if verbe in ("commit",) or (verbe in ("merge", "rebase", "cherry-pick")
                                    and any(a in SUITES for a in args)):
            motif = regle_resolution(dossier)
            if motif is not None:
                return motif
        if verbe in ("push", "merge", "rebase"):
            motif = regle_fetch(dossier, verbe, args, depart)
            if motif is not None:
                return motif
    return None


def ligne_briefing(depart):
    """Une ligne pour le briefing quand la branche suivie a avancé sans nous —
    lue sur les références locales, sans réseau. None sinon.

    AUCUNE DURÉE QUI BOUGE : le briefing est réinjecté quand son texte change, et
    « il y a 12 min » le changerait à chaque message."""
    if not porte_la_memoire(depart, depart):
        return None
    r = en_retard(depart)
    if r is None:
        age = age_du_fetch(depart)
        if age is None:
            return ("partage: aucun `git fetch` dans cette copie — la mémoire du projet voyage avec "
                    "le code : récupère avant de t'y fier.")
        if age > 24 * 60:
            return ("partage: dernier `git fetch` il y a plus d'un jour — la mémoire du projet voyage "
                    "avec le code : récupère avant de t'y fier.")
        return None
    suivie, n, mem = r
    dont = (", dont %d fichier(s) de la mémoire" % len(mem)) if mem else ""
    return ("partage: `%s` a %d commit(s) que tu n'as pas%s — `git pull --rebase` avant de "
            "travailler." % (suivie, n, dont))


# ── ce que les autres ont apporté ────────────────────────────────────────
#
# Le curseur est la dernière tête que le briefing a lue, par agent, dans le
# dossier d'état du paquet. Ce qui est entre lui et HEAD, écrit par un autre
# auteur que celui de cette copie et touchant la mémoire du projet, est
# « arrivé ». Le premier passage pose le curseur sans rien annoncer : tout
# l'historique n'est pas une arrivée.

def _etat_arrivees(depart):
    import briefing
    return os.path.join(os.path.dirname(briefing.etat_du_briefing(depart)), "arrivees.json")


def _lis_etat(f):
    import json
    try:
        with open(f, encoding="utf-8") as h:
            v = json.load(h)
    except (OSError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def _ecris_etat(f, v):
    import json
    try:
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "w", encoding="utf-8", newline="") as h:
            json.dump(v, h)
    except OSError:
        pass


def arrivees(depart):
    """`(jeton, ligne)`. Le jeton entre dans l'empreinte du briefing : il ne
    change QUE quand une arrivée est à annoncer, et reste ensuite celui de la
    dernière annonce — sans quoi la disparition de la ligne referait un briefing.
    La ligne est None quand rien n'est arrivé. Hors d'une mémoire `brain/`
    versionnée avec le code : `(None, None)`."""
    import memoire
    r = memoire.resous(depart)
    if r.forme != memoire.Forme.Brain or r.brain_autonome or not r.fact:
        return None, None
    top = _git(depart, ["rev-parse", "--show-toplevel"])
    head = _git(depart, ["rev-parse", "--verify", "-q", "HEAD"])
    if not top or not head:
        return None, None
    top, head = top.strip(), head.strip()
    f = _etat_arrivees(depart)
    e = _lis_etat(f)
    curseur = e.get("curseur") if isinstance(e.get("curseur"), str) else None
    annonce = e.get("annonce") if isinstance(e.get("annonce"), str) else ""
    if curseur == head:
        return annonce or None, None
    vus = _arrivees_entre(top, r, curseur, head) if curseur else None
    if not vus:
        _ecris_etat(f, {"curseur": head, "annonce": annonce})
        return annonce or None, None
    auteurs, n, fichiers = vus
    return head, ("arrivé : %d commit(s) de %s ont changé la mémoire du projet depuis ta dernière "
                  "lecture — %s. Relis ces fichiers et intègre-les (état, tâches, faits) AVANT d'agir."
                  % (n, ", ".join(auteurs), _echantillon(fichiers, 5)))


def acquitte(depart, jeton):
    """Le briefing qui portait la ligne est servi : le curseur avance."""
    if jeton:
        _ecris_etat(_etat_arrivees(depart), {"curseur": jeton, "annonce": jeton})


def _arrivees_entre(top, r, de, a):
    """`([auteurs], n commits, [fichiers vus depuis le projet])` des commits
    d'autres auteurs qui touchent la mémoire, ou None."""
    brain = os.path.dirname(r.fact)
    projet = os.path.dirname(brain)

    def depuis_top(p):
        try:
            x = os.path.relpath(os.path.realpath(p), os.path.realpath(top)).replace("\\", "/")
        except ValueError:
            return None
        return None if x.startswith("..") else x

    rel = depuis_top(projet)
    if rel is None:
        return None
    pre = "" if rel == "." else rel + "/"
    # Chemins vus du sommet du dépôt : un chemin absolu passé par un lien
    # symbolique serait « hors du dépôt » pour git, et la ligne se tairait.
    chemins = [":(top)" + pre + x for x in ("brain/fact/", "brain/mind/", ".logs/")]
    moi = (_git(top, ["config", "user.email"]) or "").strip().lower()
    t = _git(top, ["log", "--no-merges", "--format=%x00%an%x01%ae", "--name-only",
                   "%s..%s" % (de, a), "--"] + chemins)
    if t is None:
        return None
    auteurs, fichiers, n = [], [], 0
    for bloc in t.split("\x00")[1:]:
        lignes = bloc.split("\n")
        nom, _, mail = lignes[0].partition("\x01")
        if moi and mail.strip().lower() == moi:
            continue
        n += 1
        if nom not in auteurs:
            auteurs.append(nom)
        for x in lignes[1:]:
            x = x.strip()
            if x:
                x = x[len(pre):] if pre and x.startswith(pre) else x
                if x not in fichiers:
                    fichiers.append(x)
    return (auteurs, n, fichiers) if n else None
