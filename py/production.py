# -*- coding: utf-8 -*-
"""LE GARDE DE LA PRODUCTION — hook PreToolUse (Bash, PowerShell), et `harnais laissez-passer`.

Porté du harnais Claude (0.19, `production.py`). Décision du commanditaire, 14/10/2026 :
« il faut absolument sécuriser la production ». Rien ne refusait une poussée sur
`main` ; la règle n'était qu'écrite.

CE QUI EST REFUSÉ, à tout agent sans laissez-passer :
  · `git push` dont la destination est une branche de production, sous toutes
    ses formes (`origin main`, `HEAD:main`, `refs/heads/main`, `+main`, un motif
    qui la couvre, `--all`, `--mirror`, ou un `git push` nu depuis cette branche) ;
  · `gh pr merge`, et l'API GitHub en écriture sur une de ces branches
    (`gh api`, `curl`, et sous PowerShell `Invoke-RestMethod` / `Invoke-WebRequest`
    avec `-Method Post|Put|Patch|Delete`).

RIEN N'EST FERMÉ SANS RÉGLAGE. Le projet le déclare dans ses règles — l'en-tête
de `brain/fact/rules.md` :

    ---
    production: main, production     les branches qui partent en Production
    production-agent: OPS            le seul qui peut demander un laissez-passer
    production-duree: 15             minutes de validité
    ---

Un fait ne s'écrit qu'à la demande de l'humain (` # fact-ok`) : un agent ne
peut pas desserrer ce réglage en silence.

LE LAISSEZ-PASSER. `harnais laissez-passer "motif"`, que seul l'agent nommé
obtient, après le oui de l'humain au moment du geste. Il vaut `production-duree`
minutes et chaque usage laisse une ligne au journal (agent, heure, commande,
motif). Il vit dans le dossier de données du paquet, hors du projet et hors de
git. Que l'agent nommé puisse se l'accorder est une CONVENTION — le journal la
rend visible, il ne l'empêche pas.

CE QUI CHANGE CHEZ COPILOT.
  · L'agent qui parle se lit comme partout ici (`agent`) : le menu de l'app, le
    dossier de lancement, QA par défaut. Dans un hook, `agent.session()` le sait.
    Le SHELL de l'agent, lui, n'a pas de charge ni de journal sous les yeux :
    `harnais laissez-passer` retrouve l'agent par `COPILOT_PROJECT_DIR`, puis par
    le dossier courant (`agents/<nom>/`, `brain/mind/<nom>/`), et, depuis la
    racine d'une copie où l'app lance la conversation, par `--session <id>` ou
    `--journal <events.jsonl>` (comme `harnais agent`). Sans rien de cela l'appelant
    n'est pas identifié — donc pas l'agent nommé : fermé.
  · Les deux shells : un `toolName` `powershell` est lu avec ses chemins en `\\`
    (shlex n'y mange pas les barres), `Set-Location` / `sl` / `Push-Location`
    comptent comme `cd`, et le backtick de fin de ligne joint les lignes.

NON COUVERT (dit, pas deviné) : une branche passée par variable (`git push origin
$b`), un alias de git (`git config alias.p push`), un script qui pousse à la place
de l'agent, un client Git graphique. Le garde lit la ligne de commande, pas ce
qu'un programme fera.

**fail-open** sur une entrée illisible ; **fail-closed** sur l'identité : un
appelant que le garde n'identifie pas n'est pas l'agent nommé.
"""
import os
import re
import sys
import time

DUREE_DEFAUT = 15
FINS = {"&&", "||", ";", "|", "&", "|&", ";;", "\n"}
PUSH_AVEC_VALEUR = {"-o", "--push-option", "--repo", "--receive-pack", "--exec", "--signed"}
PORTEUSES = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
CHANGE_DOSSIER = {"cd", "pushd", "chdir", "set-location", "sl", "push-location"}
ECRIT_GITHUB = re.compile(
    r"(?:-X\s*|--method[\s=]+|--request\s+)(?:POST|PUT|PATCH|DELETE)\b|\s-f\s|\s-F\s|\s--field\s|"
    r"--raw-field|--input\b|--data|\s-d\s|"
    r"\s-Method[\s:]+['\"]?(?:POST|PUT|PATCH|DELETE)\b|\s-Body\b", re.I)


# ── le réglage du projet ────────────────────────────────────────────────

def _entete(f):
    try:
        with open(f, encoding="utf-8-sig") as h:     # PowerShell 5.1 écrit un BOM
            t = h.read()
    except (OSError, ValueError):
        return {}
    if not t.startswith("---"):
        return {}
    fin = t.find("\n---", 3)
    if fin < 0:
        return {}
    v = {}
    for l in t[3:fin].splitlines():
        k, s, val = l.partition(":")
        if s:
            v[k.strip().lower()] = val.strip()
    return v


def reglage(depart):
    """`(projet, branches, agent, durée)` ou None si le projet ne ferme rien."""
    import memoire
    r = memoire.resous(depart)
    if r.fact is None:
        return None
    e = _entete(os.path.join(r.fact, "rules.md"))
    branches = {b.strip() for b in e.get("production", "").split(",") if b.strip()}
    if not branches:
        return None
    try:
        duree = int(e.get("production-duree", "") or DUREE_DEFAUT)
    except ValueError:
        duree = DUREE_DEFAUT
    return (r.projet or r.racine, branches, e.get("production-agent", "").strip(), duree)


def _depart():
    """D'où l'on parle : `COPILOT_PROJECT_DIR` (que `hote` a déplacé dans le
    dossier de l'agent quand l'app l'a choisi), sinon le dossier courant."""
    return os.environ.get("COPILOT_PROJECT_DIR") or os.getcwd()


def agent_appelant(depart, lecture=None):
    """Le nom de l'agent. Dans l'ordre : la session résolue par le hook
    (`agent.session()`), le dossier (`memoire.resous` : `agents/<nom>` ou
    `brain/mind/<nom>`), le dossier qui suit `agents/`, puis — pour le shell
    d'un agent lancé à la racine d'une copie — le journal de session donné
    (`lecture`, une `agent.Lecture`). Sinon `""` : l'appelant n'est pas identifié."""
    import agent
    import memoire
    s = agent.session()
    if s is not None and s.actif:
        return s.actif
    r = memoire.resous(depart)
    if r.nom_agent:
        return r.nom_agent
    morceaux = [m for m in re.split(r"[\\/]", os.path.abspath(depart)) if m]
    for i, m in enumerate(morceaux):
        if m == "agents" and i + 1 < len(morceaux):
            return morceaux[i + 1]
    if lecture is not None:
        return agent.resous(depart, lecture).actif or ""
    return ""


# ── le laissez-passer ────────────────────────────────────────────────────

def _dossier():
    import socle
    d = os.path.join(socle.socle(), "production")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def _fichiers(projet):
    import equipe
    s = equipe.slug(projet).strip("-") or "projet"
    d = _dossier()
    return os.path.join(d, s + ".laissez-passer"), os.path.join(d, s + ".log")


def journalise(projet, ligne):
    _, log = _fichiers(projet)
    try:
        with open(log, "a", encoding="utf-8") as h:
            h.write("%s\t%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), ligne.replace("\n", " ")))
    except OSError:
        pass


def valide(projet, duree):
    """Le motif d'un laissez-passer encore valide, ou None."""
    f, _ = _fichiers(projet)
    try:
        if time.time() - os.path.getmtime(f) > duree * 60:
            return None
        with open(f, encoding="utf-8") as h:
            return h.read().strip() or "(sans motif)"
    except (OSError, ValueError):
        return None


# ── la commande qui pousse ───────────────────────────────────────────────

def _jetons(cmd, powershell=False):
    """Les mots de la ligne. Sous PowerShell la barre inverse est un séparateur
    de chemin, pas un échappement : `shlex` la mangerait (`C:\\repo` → `C:repo`),
    et le dossier d'un `git -C` ou d'un `cd` ne se retrouverait plus."""
    import shlex
    if powershell:
        cmd = cmd.replace("`\r\n", " ").replace("`\n", " ")
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        if powershell:
            lex.escape = ""
        return list(lex)
    except ValueError:
        return cmd.split()


def _resoudre(base, cible):
    return os.path.normpath(os.path.join(base, os.path.expanduser(cible)))


def _branche_courante(dossier):
    import subprocess
    try:
        o = subprocess.run(["git", "-C", dossier, "rev-parse", "--abbrev-ref", "HEAD"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return o.stdout.decode("utf-8", "replace").strip() if o.returncode == 0 else ""


def _nom(ref):
    ref = ref.lstrip("+")
    return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref


def _analyse_push(args, dossier, branches):
    options, positionnels, j = set(), [], 0
    while j < len(args):
        a = args[j]
        if a in PUSH_AVEC_VALEUR:
            j += 2
            continue
        if a.startswith("-") and a != "-":
            options.add(a.split("=")[0])
            j += 1
            continue
        positionnels.append(a)
        j += 1
    tout = options & {"--mirror", "--all", "--branches"}
    if tout:
        return "`git push %s` pousse aussi la branche de production" % sorted(tout)[0]
    refspecs = positionnels[1:]
    if not refspecs:
        courante = _branche_courante(dossier)
        if courante in branches:
            return "`git push` depuis une copie qui est SUR `%s`" % courante
        return None
    for spec in refspecs:
        src, _, dst = spec.lstrip("+").partition(":")
        dst = _nom(dst if ":" in spec else src)
        if "*" in dst or ("*" in src and ":" not in spec):
            return "un motif de références (`%s`) qui comprend la branche de production" % spec
        if dst == "HEAD":
            dst = _branche_courante(dossier)
        if dst in branches:
            return "la destination `%s` est une branche de production" % dst
    return None


def pousse_vers_la_production(cmd, base, branches, powershell=False):
    """La raison si la ligne fait avancer une branche de production, sinon None.
    Lit TOUTES les commandes de la ligne : `echo x && git push origin main` ne
    passe pas parce que `echo` vient d'abord."""
    jetons = _jetons(cmd, powershell)
    alt = "|".join(re.escape(b) for b in sorted(branches))
    point = re.compile(r"/merges\b|git/refs/heads/(?:%s)\b|branches/(?:%s)/protection|"
                       r"/(?:%s)/merge-upstream" % (alt, alt, alt))
    cwd, i = base, 0
    while i < len(jetons):
        t = jetons[i]
        if t.lower() in CHANGE_DOSSIER and i + 1 < len(jetons) and not jetons[i + 1].startswith("-"):
            cwd = _resoudre(cwd, jetons[i + 1])
            i += 2
            continue
        fin = i + 1
        while fin < len(jetons) and jetons[fin] not in FINS:
            fin += 1
        # Le programme peut ne pas venir en tête : `env X=1 git push`, `time git push`.
        tete = i
        while tete < fin and re.split(r"[\\/]", jetons[tete])[-1].lower() not in (
                "git", "git.exe", "gh", "gh.exe"):
            tete += 1
        prog = re.split(r"[\\/]", jetons[tete])[-1].lower() if tete < fin else ""
        i = tete
        if prog in ("git", "git.exe"):
            dossier, k, verbe = cwd, i + 1, None
            while k < fin:
                u = jetons[k]
                if u == "-C" and k + 1 < fin:
                    dossier = _resoudre(dossier, jetons[k + 1])
                    k += 2
                    continue
                if u.startswith("-"):
                    k += 2 if u in PORTEUSES else 1
                    continue
                verbe = u
                break
            if verbe == "push":
                raison = _analyse_push(jetons[k + 1:fin], dossier, branches)
                if raison:
                    return raison
        elif prog in ("gh", "gh.exe"):
            mots = jetons[i + 1:fin]
            reste = " ".join(mots)
            if mots[:2] == ["pr", "merge"]:
                return "`gh pr merge` fusionne une branche sans dire laquelle reçoit"
            if mots[:1] == ["api"] and point.search(reste) and ECRIT_GITHUB.search(" " + reste + " "):
                return "`gh api` en écriture sur une branche de production"
        i = fin + 1 if fin < len(jetons) else fin
    if "api.github.com" in cmd and point.search(cmd) and ECRIT_GITHUB.search(" " + cmd + " "):
        return "l'API GitHub en écriture sur une branche de production"
    return None


# ── le hook ──────────────────────────────────────────────────────────────

def juge(d):
    """Le motif du refus (`str`), ou None pour laisser passer."""
    import hote
    if not isinstance(d, dict) or not hote.est_shell(d):
        return None
    ti = d.get("tool_input") if isinstance(d.get("tool_input"), dict) else {}
    cmd = ti.get("command")
    if not isinstance(cmd, str):
        return None
    base = d.get("cwd") or os.environ.get("COPILOT_PROJECT_DIR") or os.getcwd()
    depart = os.environ.get("COPILOT_PROJECT_DIR") or base
    r = reglage(depart)
    if r is None:
        return None
    projet, branches, nomme, duree = r
    raison = pousse_vers_la_production(cmd, base, branches, hote.est_powershell(d))
    if raison is None:
        return None
    qui = agent_appelant(depart)
    if nomme and qui.lower() != nomme.lower():
        return ("production : %s.\n\nLa Production n'est poussée que par %s, sur demande "
                "explicite de l'humain. Pas de laissez-passer pour toi : pousse sur ta branche de "
                "travail, et dis à %s ce qui doit partir." % (raison, nomme, nomme))
    motif = valide(projet, duree)
    if motif is None:
        return ("production : %s.\n\nIl faut le oui de l'humain AU MOMENT du geste, puis un "
                "laissez-passer : `harnais laissez-passer \"<son oui, cité>\"` (valable %d min, "
                "chaque usage journalisé)." % (raison, duree))
    journalise(projet, "%s\tusage\t%s\t%s" % (qui or "?", motif, cmd))
    return None


def main(entree):
    bas = entree.lower()
    if "push" not in bas and "merge" not in bas and "api" not in bas:
        return
    import json
    import hote
    try:
        d = json.loads(entree)
    except (ValueError, RecursionError):
        return
    motif = juge(d)
    if motif is not None:
        sys.stdout.write(hote.refus(motif) + "\n")


def _option(args, nom):
    """`(valeur, reste)` : l'option `nom <valeur>` ou `nom=<valeur>`, sortie des arguments."""
    reste, valeur, i = [], None, 0
    while i < len(args):
        a = args[i]
        if a == nom and i + 1 < len(args):
            valeur = args[i + 1]
            i += 2
            continue
        if a.startswith(nom + "="):
            valeur = a[len(nom) + 1:]
            i += 1
            continue
        reste.append(a)
        i += 1
    return valeur, reste


def laissez_passer(args):
    """`harnais laissez-passer [--session ID | --journal events.jsonl] "motif"` :
    seul l'agent nommé l'obtient. Les deux options servent au shell d'un agent
    lancé à la racine d'une copie, où ni le dossier ni l'environnement ne disent
    qui parle."""
    import agent
    import hote
    session, args = _option(list(args), "--session")
    journal, args = _option(args, "--journal")
    depart = _depart()
    r = reglage(depart)
    if r is None:
        sys.stderr.write("laissez-passer : ce projet ne ferme aucune branche (pas de `production:` "
                         "dans l'en-tête de ses règles) — rien à ouvrir.\n")
        return 1
    projet, branches, nomme, duree = r
    lecture = None
    if session is not None or journal is not None:
        charge = {}
        if journal is not None:
            charge["transcript_path"] = journal
        if session is not None:
            charge["session_id"] = session
        j = agent.chemin_journal(charge, hote.maison_copilot())
        lecture = agent.lis_journal(j) if j is not None else None
    qui = agent_appelant(depart, lecture)
    if nomme and qui.lower() != nomme.lower():
        sys.stderr.write("laissez-passer : réservé à %s ; tu es « %s ».%s\n" % (
            nomme, qui or "?",
            "" if qui else " Lance-le depuis le dossier de ton agent, ou ajoute `--session <id>` "
                           "(le journal de session dit qui a été choisi dans le menu)."))
        journalise(projet, "%s\tREFUSÉ\t%s" % (qui or "?", " ".join(args)))
        return 1
    motif = " ".join(a for a in args if a).strip()
    if not motif:
        sys.stderr.write("laissez-passer : cite le oui de l'humain, entre guillemets.\n")
        return 2
    f, log = _fichiers(projet)
    with open(f, "w", encoding="utf-8") as h:
        h.write(motif + "\n")
    journalise(projet, "%s\tdéposé\t%s" % (qui or "?", motif))
    sys.stdout.write("Laissez-passer posé pour %s : %d min, branches %s. Journal : %s\n"
                     % (qui or "ce projet", duree, ", ".join(sorted(branches)), log))
    return 0
