# -*- coding: utf-8 -*-
"""DÉCLARATION LOCALE ET PÉRIMÈTRE EFFECTIF DU PAQUET COPILOT.

Port de `harnais/src/copilot.rs` (Rust, 1.3.0). Mêmes noms de fonctions.

Le périmètre est la seule garde FERMÉE en cas de doute : une charge illisible,
un dossier de lancement inconnu, un périmètre compact absent ou mal formé
refusent l'écriture. Partout ailleurs le harnais laisse passer.
"""
import json
import os
import subprocess

MARCHE = "atelier-copilot"
PAQUET = "harnais@atelier-copilot"

WINDOWS = os.name == "nt"


class Refus(Exception):
    """Une erreur qui, dans la garde, vaut refus (le `Err(String)` du Rust)."""


def executable():
    """Le CLI Copilot : `HARNAIS_COPILOT`, puis le PATH, puis (Windows) le SDK
    installé sous `%LOCALAPPDATA%\\github-copilot-sdk\\cli\\<version>\\`."""
    p = os.environ.get("HARNAIS_COPILOT")
    if p:
        return p
    noms = ["copilot.exe", "copilot.cmd", "copilot.bat"] if WINDOWS else ["copilot"]
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d:
            continue
        for n in noms:
            c = os.path.join(d, n)
            if os.path.isfile(c):
                return c
    if WINDOWS and os.environ.get("LOCALAPPDATA"):
        return executable_sdk(os.path.join(os.environ["LOCALAPPDATA"], "github-copilot-sdk", "cli"))
    return None


def executable_sdk(d):
    """La plus haute version numérique `X.Y.Z[-…]` qui porte un `copilot.exe`."""
    try:
        noms = os.listdir(d)
    except OSError:
        return None
    versions = []
    for nom in noms:
        base = nom.split("-")[0]
        try:
            v = [int(x) for x in base.split(".")]
        except ValueError:
            continue
        if len(v) != 3:
            continue
        exe = os.path.join(d, nom, "copilot.exe")
        if os.path.isfile(exe):
            versions.append((v, nom, exe))
    if not versions:
        return None
    versions.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return versions[0][2]


def paquet():
    """La racine du paquet. Lève `Refus` quand rien ne la donne."""
    for k in ("COPILOT_PLUGIN_ROOT", "PLUGIN_ROOT"):
        v = os.environ.get(k)
        if v:
            return v
    # Ce fichier est dans `<paquet>/py/` : la racine est son parent.
    ici = os.path.dirname(os.path.abspath(__file__))
    racine = os.path.dirname(ici)
    if os.path.isfile(os.path.join(racine, ".github", "plugin", "marketplace.json")):
        return racine
    raise Refus("racine du paquet introuvable : poser COPILOT_PLUGIN_ROOT")


def paquet_ou_rien():
    try:
        return paquet()
    except Refus:
        return None


def reglages(d, racine):
    """Déclare le marché local et active le paquet dans un `settings.json` lu."""
    if not isinstance(d, dict):
        raise Refus("settings.json n'est pas un objet")
    mk = d.setdefault("extraKnownMarketplaces", {})
    if not isinstance(mk, dict):
        raise Refus("extraKnownMarketplaces n'est pas un objet")
    source = {"source": {"source": "directory", "path": str(racine)}}
    if MARCHE in mk:
        if mk[MARCHE] != source:
            raise Refus("marketplace %s déjà déclarée avec une autre source" % MARCHE)
    else:
        mk[MARCHE] = source
    ep = d.setdefault("enabledPlugins", {})
    if not isinstance(ep, dict):
        raise Refus("enabledPlugins n'est pas un objet")
    ep[PAQUET] = True


def racine_git(d):
    """La racine de la copie de travail COURANTE, résolue. Lève `Refus`."""
    try:
        o = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(d),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        raise Refus("git depuis %s : %s" % (d, e))
    if o.returncode != 0:
        raise Refus("aucune racine Git depuis %s : %s" % (
            d, o.stderr.decode("utf-8", "replace").strip()))
    chemin = o.stdout.decode("utf-8", "replace").strip()
    if not chemin:
        raise Refus("git n'a pas rendu de racine")
    try:
        return os.path.realpath(chemin)
    except (OSError, ValueError):
        return chemin


def _racine_git_ou_rien(d):
    try:
        return racine_git(d)
    except Refus:
        return None


def settings(d):
    return os.path.join(str(d), ".github", "copilot", "settings.json")


def avertit_settings_agent(d):
    f = settings(d)
    if os.path.exists(f):
        import sys
        sys.stderr.write("ATTENTION : %s est ignoré par Copilot (hors racine Git) ; reporter ses "
                         "réglages à la racine du dépôt, sans écraser ce fichier.\n" % f)


def ancien_paquet(d):
    try:
        with open(os.path.join(str(d), ".claude", "settings.json"), encoding="utf-8") as f:
            v = json.load(f)
    except (OSError, ValueError):
        return False
    ep = v.get("enabledPlugins") if isinstance(v, dict) else None
    return isinstance(ep, dict) and ep.get("harnais@atelier") is True


def avertit_ancien(d):
    if ancien_paquet(d):
        import sys
        sys.stderr.write("ATTENTION : %s déclare encore harnais@atelier ; Copilot lit aussi ce "
                         "fichier et peut charger cet ancien paquet en doublon.\n"
                         % os.path.join(str(d), ".claude", "settings.json"))


# ── chemins : à la manière de `Path` en Rust, Windows compris ───────────────

def _sans_racine(p):
    """Relatif au sens du projet : ni lecteur ni racine (`\\x` a une racine)."""
    lecteur, reste = os.path.splitdrive(str(p))
    if lecteur:
        return False
    return not (reste.startswith("/") or (WINDOWS and reste.startswith("\\")))


def _absolu(p):
    """`Path::is_absolute` : sous Windows il faut un lecteur ET une racine (`\\x`
    n'est pas absolu ; `os.path.isabs` le disait avant Python 3.13)."""
    p = str(p)
    if not WINDOWS:
        return p.startswith("/")
    lecteur, reste = os.path.splitdrive(p)
    if lecteur.startswith("\\\\") or lecteur.startswith("//"):
        return True
    return bool(lecteur) and reste[:1] in ("\\", "/")


def _composants(p):
    p = str(p)
    if WINDOWS:
        p = p.replace("\\", "/")
    return [c for c in p.split("/") if c and c != "."]


def sous(p, base):
    """Le reste de `p` sous `base` (liste de composants, vide si égaux), ou None.
    Sans égard à la casse sous Windows."""
    a, b = _composants(p), _composants(base)
    if WINDOWS:
        a2, b2 = [x.lower() for x in a], [x.lower() for x in b]
    else:
        a2, b2 = a, b
    if len(a2) >= len(b2) and a2[:len(b2)] == b2:
        return a[len(b):]
    return None


def _pose(copie, reste):
    out = str(copie)
    for c in reste:
        out = os.path.join(out, c)
    return out


def canonique(p):
    """`canonicalize`, même pour un chemin qui n'existe pas encore : l'ancêtre
    existant est résolu, le reste lui est rattaché."""
    p = str(p)
    if os.path.exists(p):
        try:
            return os.path.realpath(p)
        except (OSError, ValueError):
            return p
    reste = []
    courant = p
    while not os.path.exists(courant):
        parent, nom = os.path.split(courant.rstrip("/\\") or courant)
        if nom:
            reste.append(nom)
        if not parent or parent == courant:
            return p
        courant = parent
    try:
        canon = os.path.realpath(courant)
    except (OSError, ValueError):
        canon = courant
    for n in reversed(reste):
        canon = os.path.join(canon, n)
    return canon


def ancre(p, copie, principal):
    """Un dossier interdit, posé sur la copie courante. Composé COMPOSANT PAR
    COMPOSANT : sous Windows une barre oblique ne sépare plus rien dans `\\\\?\\`."""
    if copie is None:
        return str(p)
    if _sans_racine(p):
        return _pose(copie, _composants(p))
    if principal is not None:
        r = sous(canonique(p), canonique(principal))
        if r is not None:
            return _pose(copie, r)
    return str(p)


def dedans(path, interdit):
    return sous(canonique(path), canonique(interdit)) is not None


def fichier_perimetre(d):
    """Où est le périmètre de l'agent : compact (`.github/copilot/perimetres/
    <profil>.json` à la racine) ou dossier (`agents/<nom>/.github/copilot/
    perimetre.json`)."""
    arbre = _racine_git_ou_rien(d)
    if arbre is not None:
        import memoire
        l = memoire.lot(d)
        if "/" in l:
            nom = l.rsplit("/", 1)[1]
            import agent
            if agent.compact(arbre, nom):
                return agent.perimetre_compact(arbre, nom)
    return os.path.join(str(d), ".github", "copilot", "perimetre.json")


def _est_compact(p):
    parent = os.path.dirname(p)
    return _composants(parent)[-3:] == [".github", "copilot", "perimetres"]


def lis_deny(d):
    """Les entrées de `deny` TELLES QU'ÉCRITES — pour les réécrire, pas pour garder."""
    p = fichier_perimetre(d)
    if not os.path.isfile(p) and _est_compact(p):
        raise Refus("%s : périmètre compact absent ; écriture refusée" % p)
    if not os.path.isfile(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            t = f.read()
    except OSError as e:
        raise Refus(str(e))
    try:
        v = json.loads(t)
    except ValueError as e:
        raise Refus("%s : %s" % (p, e))
    deny = v.get("deny") if isinstance(v, dict) else None
    if not isinstance(deny, list):
        raise Refus("%s : deny doit être une liste" % p)
    out = []
    for x in deny:
        if not isinstance(x, str):
            raise Refus("%s : deny doit contenir des chemins" % p)
        out.append(x)
    return out


def lis_allow(d):
    p = fichier_perimetre(d)
    compact = _est_compact(p)
    if not compact and not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            t = f.read()
    except OSError as e:
        raise Refus("%s : %s" % (p, e))
    try:
        v = json.loads(t)
    except ValueError as e:
        raise Refus("%s : %s" % (p, e))
    # Sans liste `allow`, le périmètre ne fait que séparer l'agent de ses pairs
    # (`deny`) : tout le reste lui est permis. Une liste présente mais mal formée
    # refuse : on ne devine pas ce que son auteur voulait permettre.
    if not isinstance(v, dict) or "allow" not in v:
        return None
    liste = v["allow"]
    if not isinstance(liste, list):
        raise Refus("%s : allow doit être une liste" % p)
    out = []
    for x in liste:
        if not isinstance(x, str) or not x.strip():
            raise Refus("%s : allow doit contenir des chemins non vides" % p)
        out.append(x)
    return out


def perimetre(d):
    """LE PÉRIMÈTRE D'UN AGENT, rattaché à la copie de travail COURANTE.

    `deny` liste des dossiers. Écrits RELATIFS (`agents/PO`), ils se lisent depuis
    la racine de la copie où l'on travaille — c'est ce qu'écrit `harnais equipe`.
    Écrits ABSOLUS, comme jusqu'en 0.15.0, ils visent le dossier PRINCIPAL : dans
    une copie de l'app, aucune écriture n'y tombe, et la garde laissait tout
    passer sans le dire. Un absolu sous le principal est donc transposé sur la
    copie ; un absolu hors du dépôt reste tel quel."""
    import memoire
    copie = _racine_git_ou_rien(d)
    principal = memoire.racine_depot(d)
    return [ancre(x, copie, principal) for x in lis_deny(d)]


def perimetre_garde(d):
    """CE QUE LA GARDE REFUSE : le périmètre posé sur la copie courante, ET le
    même dans le dossier principal quand on travaille dans une copie."""
    import memoire
    v = perimetre(d)
    principal = memoire.racine_depot(d)
    for x in lis_deny(d):
        p = ancre(x, principal, principal)
        if p not in v:
            v.append(p)
    return v


OUTILS_ECRITURE = ("Edit", "Write", "edit", "create", "apply_patch", "str_replace_editor")
_ENTETES_PATCH = ("*** Add File: ", "*** Update File: ", "*** Delete File: ", "*** Move to: ")


def decision(charge, lancement):
    """None : l'écriture passe. Un texte : le motif du refus. Lève `Refus` quand
    on ne peut pas juger — la garde refuse alors aussi."""
    import memoire
    nom = charge.get("tool_name") or charge.get("toolName") or ""
    if not isinstance(nom, str) or nom not in OUTILS_ECRITURE:
        return None
    denies = perimetre_garde(lancement)
    copie = _racine_git_ou_rien(lancement)
    principal = memoire.racine_depot(lancement)
    allow = lis_allow(lancement)
    if allow is not None:
        allow = [ancre(x, copie, principal) for x in allow]
    if not denies and allow is None:
        return None
    args = charge["tool_input"] if "tool_input" in charge else charge.get("toolArgs")
    if isinstance(args, str) and args.lstrip().startswith("*** Begin Patch"):
        args_texte = {"patch": args}
    elif isinstance(args, str):
        try:
            args_texte = json.loads(args)
        except ValueError as e:
            raise Refus("arguments de l'outil illisibles : %s" % e)
    elif args is None:
        raise Refus("arguments de l'outil absents")
    else:
        args_texte = args
    if not isinstance(args_texte, dict):
        args_texte = {}
    # Le réglage du plugin vit à la racine Git ; le périmètre reste au lancement de l'agent.
    depot = racine_git(lancement)
    agent_d = canonique(lancement) if os.path.exists(str(lancement)) else str(lancement)
    if sous(agent_d, depot) is None:
        raise Refus("dossier de lancement hors du dépôt Git")
    # UN CHEMIN RELATIF SE LIT DEPUIS LE DOSSIER DE LA SESSION, pas depuis le
    # dossier de l'agent : dans l'app, la session tourne à la racine de la copie,
    # et le harnais s'est placé dans `agents/<nom>/` (voir `agent`).
    cwd = charge.get("cwd")
    base = cwd if (isinstance(cwd, str) and _absolu(cwd)) else str(lancement)
    chemins = [args_texte[k] for k in ("file_path", "path", "filePath")
               if isinstance(args_texte.get(k), str)]
    patch = args_texte.get("patch")
    if isinstance(patch, str):
        for ligne in patch.splitlines():
            for prefixe in _ENTETES_PATCH:
                if ligne.startswith(prefixe):
                    chemins.append(ligne[len(prefixe):].strip())
                    break
    if not chemins:
        raise Refus("outil d'écriture sans chemin vérifiable")
    for c in chemins:
        chemin = os.path.join(base, c)
        if allow is not None:
            ok = False
            for a in allow:
                # Les fichiers de faits sont des autorisations exactes, pas des dossiers.
                if a.lower().endswith(".md") if WINDOWS else a.endswith(".md"):
                    r = sous(canonique(chemin), canonique(a))
                    if r is not None and not r:
                        ok = True
                        break
                elif dedans(chemin, a):
                    ok = True
                    break
            if not ok:
                return "Écriture refusée hors périmètre autorisé : %s" % chemin
        for interdit in denies:
            if dedans(chemin, interdit):
                return "Écriture refusée hors périmètre : %s (dossier interdit : %s)" % (chemin, interdit)
    return None


def garde(entree):
    """`perimetre` — PreToolUse/Edit|Write. FERMÉE dans le doute."""
    import sys
    import hote
    if os.environ.get("HARNAIS_JUGE"):
        return
    try:
        charge = json.loads(entree)
        if not isinstance(charge, dict):
            raise ValueError("pas un objet")
    except ValueError as e:
        sys.stdout.write(hote.refus("charge de garde illisible : %s" % e) + "\n")
        return
    lancement = os.environ.get("COPILOT_PROJECT_DIR") or (
        charge.get("cwd") if isinstance(charge.get("cwd"), str) else None)
    if not lancement:
        sys.stdout.write(hote.refus("dossier de lancement inconnu") + "\n")
        return
    try:
        motif = decision(charge, lancement)
    except Refus as e:
        motif = str(e)
    if motif is not None:
        sys.stdout.write(hote.refus(motif) + "\n")


def main(entree):
    import hote
    garde(hote.prepare(entree))
