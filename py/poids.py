# -*- coding: utf-8 -*-
"""LA CONFIANCE DES FAITS — `brain/poids.json`.

Port de `harnais/src/poids.rs` (Rust, 1.3.0). Mêmes noms de fonctions.

L'unité est la SECTION d'un fichier de faits (un titre `##` et ce qui le suit).
Chaque section porte une confiance qui part de son niveau d'établissement
(mesuré 80, dit 85, observé 60, supposé 40, inconnu 50), puis bouge avec les
résultats : une garde qui mord, un constat qui tient, un constat démenti. La
confiance doit être facile à perdre et lente à reconstruire.

DEUX ÉTATS, ET ILS N'ONT PAS LA MÊME DURÉE DE VIE.
· `brain/poids.json` est COMMITÉ : il suit le projet d'une session à l'autre,
  d'un worktree à l'autre, d'un agent à l'autre. Pour ne pas le réécrire à
  chaque lecture, la date de dernière lecture d'une section n'y bouge qu'une
  fois par jour. SAUF DANS UN PROJET LOGÉ (2.2.1) : le dépôt est celui du code,
  partagé par plusieurs personnes ; réécrit chaque jour sur chaque poste, le
  fichier ferait un conflit à chaque pull. `adopte --projet` l'ignore : chaque
  poste y tient ses propres compteurs.
· le registre de session est LOCAL (dossier d'état du paquet) : il retient
  quelles sections ont été lues depuis le dernier verdict, et rien d'autre. Le
  vider quand un résultat tombe est ce qui rend le lien causal : une section
  lue il y a trois jours n'est pas punie pour un échec d'aujourd'hui.

Mesuré sur Copilot CLI 1.0.90-0 : une lecture par l'outil `view` arrive au hook
après outil sous `tool_name: "Read"`, avec `tool_input.path` en absolu et, pour
une lecture partielle, `view_range: [début, fin]` ; une lecture par le shell
arrive sous `tool_name: "Bash"`, la commande en clair.

RIEN N'EST JAMAIS DÉPLACÉ NI EFFACÉ. Le rapport signale ; trier les faits reste
une décision de @user.
"""
import datetime
import json
import math
import os
import re

import nature

# Sous ce seuil, une section est signalée comme peu sûre.
SEUIL_PEU_SUR = 50.0
# Sans lecture depuis cette durée (graduée par la nature), une section dort.
DORMANT_J = 30.0
# Au-delà de ce nombre de fichiers nommés par une seule commande, c'est un
# inventaire, pas une lecture : on ne compte rien.
FICHIERS_MAX = 2


def aujourdhui():
    return datetime.date.today().strftime("%Y-%m-%d")


def fichier(r):
    """Le fichier des poids d'un projet en forme `brain/` ; aucun pour les autres."""
    import memoire
    if r.forme != memoire.Forme.Brain or not r.fact:
        return None
    return os.path.join(os.path.dirname(r.fact), "poids.json")


def _lignes(t):
    out = t.split("\n")
    if out and out[-1] == "":
        out.pop()
    return [x[:-1] if x.endswith("\r") else x for x in out]


_TITRE = re.compile(r"^##\s+(.+?)\s*\Z")


def sections(texte):
    """Les sections d'un fichier de faits : (titre, première ligne, dernière
    ligne), numérotées à partir de 1, bornes comprises."""
    lignes = _lignes(texte)
    out = []
    for i, l in enumerate(lignes):
        n = i + 1
        if l.startswith("# "):
            if out and out[-1][2] == 0:
                out[-1][2] = n - 1
        else:
            c = _TITRE.match(l)
            if c is not None:
                if out and out[-1][2] == 0:
                    out[-1][2] = n - 1
                out.append([c.group(1), n, 0])
    if out and out[-1][2] == 0:
        out[-1][2] = len(lignes)
    return [tuple(x) for x in out]


def cle(fichier_, titre):
    """La clé d'une section dans `poids.json`."""
    return "%s › %s" % (fichier_, titre)


def lues(nom, texte, plage):
    """Les sections touchées par une lecture : celles qui chevauchent la plage
    (`fin` = -1 : jusqu'à la fin), toutes sans plage."""
    out = []
    for t, debut, fin in sections(texte):
        if plage is not None:
            a, b = plage
            if b < 0:
                b = float("inf")
            if not (debut <= b and fin >= a):
                continue
        out.append(cle(nom, t))
    return out


def lis_json(f):
    try:
        with open(f, encoding="utf-8") as h:
            v = json.load(h)
    except (OSError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def _trie(v):
    if isinstance(v, dict):
        return {k: _trie(v[k]) for k in sorted(v)}
    if isinstance(v, list):
        return [_trie(x) for x in v]
    return v


def ecris_json(f, v):
    """Écriture atomique : un fichier tronqué se lirait comme une mémoire neuve.
    Clés triées à tous les niveaux : un diff de `poids.json` ne montre que ce
    qui a bougé."""
    try:
        t = json.dumps(_trie(v), indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return
    tmp = os.path.splitext(f)[0] + ".json.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as h:
            h.write(t + "\n")
        os.replace(tmp, f)
    except OSError:
        pass


def etablissement(texte, titre):
    """Le niveau et la nature déclarés d'une section, lus sur sa ligne
    d'établissement : (niveau, nature) ou (None, None)."""
    import briefing
    for e in briefing.etablissements(texte):
        if e[0] == titre:
            return e[1], (e[3] if len(e) > 3 else None)
    return None, None


def _lis(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def inscris(poids, fact, cles):
    """Inscrit des lectures dans `poids.json` — une entrée neuve part de son
    niveau ; `jours_lus` et `vu` ne bougent qu'une fois par jour et par section."""
    p = lis_json(poids)
    jour = aujourdhui()
    p.setdefault("schema", 1)
    p.setdefault("depuis", jour)
    change = not os.path.exists(poids)
    s = p.get("sections")
    s = dict(s) if isinstance(s, dict) else {}
    for k in cles:
        if " › " in k:
            fich, titre = k.split(" › ", 1)
        else:
            fich, titre = k, ""
        if k not in s:
            change = True
            niv, _ = etablissement(_lis(os.path.join(fact, fich)), titre)
            s[k] = {"conf": nature.depart(niv or "", nature.Maison.Faits),
                    "jours_lus": 0, "verdicts": 0, "vu": None}
        o = s[k]
        if isinstance(o, dict) and o.get("vu") != jour:
            n = o.get("jours_lus")
            n = (n if isinstance(n, int) and not isinstance(n, bool) else 0) + 1
            o["jours_lus"] = n
            o["vu"] = jour
            change = True
    p["sections"] = s
    if change:
        ecris_json(poids, p)
    return change


# ── le registre de session ──────────────────────────────────────────────────

def registre(etat, session):
    s = "".join(c if ((c.isascii() and c.isalnum()) or c == "-") else "_" for c in session)
    return os.path.join(etat, "lectures", "%s.json" % s)


def retiens(etat, session, poids, cles):
    """Ajoute au registre de la session les sections lues : (fichier des poids, clé)."""
    if not session or not cles:
        return
    f = registre(etat, session)
    r = lis_json(f)
    p = str(poids)
    liste = r.get(p)
    liste = list(liste) if isinstance(liste, list) else []
    for k in cles:
        if k not in liste:
            liste.append(k)
    r[p] = liste
    try:
        os.makedirs(os.path.dirname(f), exist_ok=True)
    except OSError:
        pass
    ecris_json(f, r)


def _arrondi(x):
    """`f64::round` de Rust : la moitié s'éloigne de zéro."""
    return math.floor(x + 0.5) if x >= 0 else -math.floor(-x + 0.5)


def resultat(etat, session, mult):
    """UN RÉSULTAT RETOMBE SUR CE QUI A SERVI À L'OBTENIR : les sections lues dans
    cette session depuis le dernier verdict voient leur confiance multipliée,
    puis le registre est vidé. Rend le nombre de sections touchées."""
    f = registre(etat, session)
    r = lis_json(f)
    n = 0
    for poids, cles in r.items():
        p = lis_json(poids)
        s = p.get("sections")
        if not isinstance(s, dict):
            continue
        for k in (cles if isinstance(cles, list) else []):
            o = s.get(k) if isinstance(k, str) else None
            if not isinstance(o, dict):
                continue
            c = o.get("conf")
            c = float(c) if isinstance(c, (int, float)) and not isinstance(c, bool) else 50.0
            c = _arrondi(c * mult * 10.0) / 10.0
            o["conf"] = min(max(c, 1.0), 100.0)
            v = o.get("verdicts")
            o["verdicts"] = (v if isinstance(v, int) and not isinstance(v, bool) else 0) + 1
            n += 1
        ecris_json(poids, p)
    try:
        os.remove(f)
    except OSError:
        pass
    return n


# ── le hook après lecture ───────────────────────────────────────────────────

_ECRIT = re.compile(r"(?i)\b(set-content|add-content|out-file|tee-object|sed\s+-i)\b")
_FAIT = re.compile(r"(?i)[^\s'\"`;|<>]*brain[/\\]fact[/\\]"
                   r"(?:base|architecture|stack|rules|roles|workflow)\.md")


def fichiers_dans_commande(cmd):
    """Les fichiers de faits nommés dans une commande shell, hors de ce qu'elle
    ÉCRIT (`> fichier`, `Set-Content`, `Out-File`…)."""
    if _ECRIT.search(cmd):
        return []
    out = []
    for m in _FAIT.finditer(cmd):
        if cmd[:m.start()].rstrip().endswith(">"):
            continue
        s = m.group(0)
        if s not in out:
            out.append(s)
    return out


def _meme(a, b):
    try:
        return (os.path.exists(a) and os.path.exists(b)
                and os.path.realpath(a) == os.path.realpath(b))
    except (OSError, ValueError):
        return False


def fait_lu(chemin):
    """Une lecture d'un fichier de faits : (fichier des poids, dossier des faits,
    nom du fichier). Le projet est celui du FICHIER lu, pas celui de la session."""
    import memoire
    import socle
    nom = os.path.basename(str(chemin))
    if nom not in socle.faits_tous():
        return None
    dossier = os.path.dirname(str(chemin))
    if not dossier:
        return None
    r = memoire.resous(dossier)
    if not r.fact or not _meme(r.fact, dossier):
        return None
    f = fichier(r)
    if f is None:
        return None
    return f, r.fact, nom


def _entier(x):
    return x if (isinstance(x, int) and not isinstance(x, bool)) else None


def main(entree):
    """`harnais lecture` — PostToolUse/Read|Bash. Ne bloque jamais, ne dit rien."""
    import memoire
    import socle
    try:
        d = json.loads(entree)
    except ValueError:
        return
    if not isinstance(d, dict):
        return
    session = d.get("session_id") if isinstance(d.get("session_id"), str) else ""
    cwd = d.get("cwd") if isinstance(d.get("cwd"), str) else memoire.depart_defaut()
    ti = d.get("tool_input") if isinstance(d.get("tool_input"), dict) else {}
    nom_outil = d.get("tool_name")
    if nom_outil == "Read":
        p = ti.get("file_path") if "file_path" in ti else ti.get("path")
        if not isinstance(p, str):
            return
        plage = None
        vr = ti.get("view_range")
        if isinstance(vr, list) and len(vr) >= 2 and _entier(vr[0]) is not None and _entier(vr[1]) is not None:
            plage = (vr[0], vr[1])
        lectures = [(p, plage)]
    elif nom_outil == "Bash":
        cmd = ti.get("command") if isinstance(ti.get("command"), str) else ""
        f = fichiers_dans_commande(cmd)
        if len(f) > FICHIERS_MAX:
            return
        lectures = [(os.path.join(cwd, s), None) for s in f]
    else:
        return
    etat = socle.socle()
    for chemin, plage in lectures:
        r = fait_lu(chemin)
        if r is None:
            continue
        poids, fact, nom = r
        texte = _lis(os.path.join(fact, nom))
        cles = lues(nom, texte, plage)
        if not cles:
            continue
        inscris(poids, fact, cles)
        retiens(etat, session, poids, cles)


# ── le rapport ──────────────────────────────────────────────────────────────

class Etat(object):
    __slots__ = ("cle", "conf", "jours_lus", "vu", "dort", "peu_sur", "orpheline")

    def __init__(self, **k):
        for a in self.__slots__:
            setattr(self, a, k[a])


def _jours(iso):
    try:
        d = datetime.datetime.strptime(iso, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return float((datetime.date.today() - d).days)


def etats(poids, fact):
    """L'état de chaque section inscrite. Une section jamais lue depuis la
    création de `poids.json` ne dort qu'une fois la mesure assez ancienne : un
    compteur à zéro est une absence de preuve, pas une péremption."""
    p = lis_json(poids)
    depuis = p.get("depuis") if isinstance(p.get("depuis"), str) else ""
    out = []
    s = p.get("sections")
    if not isinstance(s, dict):
        return out
    for k, v in s.items():
        if " › " in k:
            fich, titre = k.split(" › ", 1)
        else:
            fich, titre = k, ""
        texte = _lis(os.path.join(fact, fich))
        orpheline = not any(t == titre for t, _, _ in sections(texte))
        niv, nat = etablissement(texte, titre)
        n, _ = nature.de(nature.Maison.Faits, niv, nat)
        v = v if isinstance(v, dict) else {}
        conf = v.get("conf")
        conf = float(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else 50.0
        vu = v.get("vu") if isinstance(v.get("vu"), str) else None
        age = _jours(vu) if vu is not None else None
        if age is None:
            age = _jours(depuis)
        dort = age is not None and age > nature.duree(n, DORMANT_J)
        jl = _entier(v.get("jours_lus"))
        out.append(Etat(cle=k, conf=conf, jours_lus=jl if jl is not None else 0, vu=vu, dort=dort,
                        peu_sur=conf < SEUIL_PEU_SUR, orpheline=orpheline))
    return out


def _court(v):
    t = list(v[:3])
    if len(v) > 3:
        t.append("… et %d autre(s)" % (len(v) - 3))
    return " · ".join(t)


def ligne_briefing(poids, fact):
    """Une ou deux lignes pour le briefing, ou None."""
    if not os.path.exists(poids):
        return None
    e = etats(poids, fact)
    peu = ["%s (%.0f)" % (x.cle, x.conf) for x in e if x.peu_sur and not x.orpheline]
    dort = [x.cle for x in e if x.dort and not x.orpheline]
    if not peu and not dort:
        return None
    l = []
    if peu:
        l.append("poids  : %d section(s) peu sûre(s) — des résultats les ont démenties : %s. "
                 "Revérifie avant de t'en servir." % (len(peu), _court(peu)))
    if dort:
        l.append("%s%d section(s) endormie(s), plus lue(s) depuis longtemps : %s. "
                 "`harnais curateur` pour le détail." % ("poids  : " if not l else "         ",
                                                         len(dort), _court(dort)))
    return "\n".join(l)


def curateur(args):
    """`harnais curateur [dossier]` — le détail, en lecture seule."""
    import memoire
    ici = args[0] if args else memoire.depart_defaut()
    r = memoire.resous(ici)
    poids = fichier(r)
    if poids is None or not r.fact:
        print("curateur : pas de mémoire `brain/` ici (%s)." % ici)
        return 1
    if not os.path.exists(poids):
        print("curateur : aucune lecture inscrite encore (%s n'existe pas)." % poids)
        return 0
    e = sorted(etats(poids, r.fact), key=lambda x: x.conf)
    p = poids[4:] if poids.startswith("\\\\?\\") else poids
    print("%s\n" % p)
    print("  %5s  %4s  %-10s  %-9s  section" % ("conf", "jours", "vu", "état"))
    for x in e:
        etat = ("disparue" if x.orpheline else "peu sûre" if x.peu_sur
                else "endormie" if x.dort else "active")
        print("  %5.1f  %4d  %-10s  %-9s  %s" % (x.conf, x.jours_lus, x.vu or "jamais", etat, x.cle))
    print("\n  Rien n'est déplacé ni effacé : trier les faits reste une décision de @user.")
    return 0
