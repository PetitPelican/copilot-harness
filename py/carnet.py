# -*- coding: utf-8 -*-
"""LE CARNET D'ÉQUIPE — l'espace commun d'un projet multi-agents.

Port de `harnais/src/carnet.rs` (0.12.8). Ce n'est pas un hook : c'est le module
que le briefing et la fin de tour importent.

MESURÉ le 08/09/2026 sur une équipe de trois agents :, trois copies physiques du
dépôt, et tout ce qu'un agent écrit ne voyage que dans SA copie. `Projet QA`
avait 187 enregistrements de retard et lisait une liste de tâches de 1 202
lignes là où la vraie en fait 2 810. Rien, nulle part, ne le lui disait.

Le mur n'est pas entre les agents : il est entre leurs copies.

CE QUI EN DÉCIDE LA FORME, ET QU'ON NE CHANGE PAS SANS TOUT CASSER :

1. HORS SUIVI DE VERSION — un dossier suivi par git serait recopié dans les
   trois copies à chaque fusion, et on aurait reconstruit le défaut.
2. UN SEUL ÉCRIVAIN PAR FICHIER — la LECTURE est toujours la fusion des
   trois. C'est ce que nos fichiers séparés donnent gratuitement et que
   sense-lab, avec son espace unique, rachète en rôles et droits.
3. ON AJOUTE, ON NE SUPPRIME JAMAIS.
4. LE CHIFFRE DE CONFIANCE NE VIT PAS DANS LE CARNET. Une entrée est
   immuable et un chiffre bouge : surcouche dans `.etat/confiance.json`,
   indexée par l'empreinte de l'entrée.

**fail-open partout** : toute erreur rend une valeur vide, jamais une exception.

DEUX PIÈGES DU PORTAGE, ET ILS SONT SILENCIEUX. `round()` de Python arrondit
**au pair le plus proche**, pas au supérieur : `format!("{:.1}")` de Rust
fait la même chose, `f64::round` non. Et `json.dumps` garde **l'ordre
d'insertion** des clés : sans le drapeau `preserve_order`, les deux versions
écriraient le même document dans un ordre différent.

Les modules `nature` et `memoire` s'importent DANS les fonctions : `nature`
reprend `sansaccents` d'ici, et un import en tête fermerait la boucle.
"""
import os

# Le départ fixé par le niveau, et les poids du résultat, vivent dans
# `nature` depuis le 11/09/2026 : cette copie et celle de la fin de tour y
# sont réunies. Ne restent ici que les crans propres au carnet.
OUBLI = 0.97
EFFONDRE = 0.5
PLANCHER = 5.0
PLAFOND = 99.0
# Le chiffre n'est AFFICHÉ qu'après avoir bougé deux fois. Avant ça, c'est le
# niveau de départ déguisé en mesure — le défaut qu'on reprochait au chiffre
# saisi à la main. Ne pas retirer cette borne.
MOUVEMENTS_AVANT_AFFICHAGE = 2

# Les blancs de Rust (`char::is_whitespace`, `\s` du crate `regex`) — pas ceux de
# Python, qui y ajoutent \x1c-\x1f.
BLANCS = ("\t\n\x0b\x0c\r \x85\xa0       "
          "         　")
_S = ("[\\t\\n\\x0b\\x0c\\r \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029"
      "\\u202f\\u205f\\u3000]")

_CACHE = {}


def _re(nom, motif, drapeaux=0):
    r = _CACHE.get(nom)
    if r is None:
        import re
        r = _CACHE[nom] = re.compile(motif.replace("\\s", _S), drapeaux)
    return r


def entete_re():
    return _re("entete", r"^##\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s*·\s*(.+?)\s*·\s*(.+?)(?:\s*·\s*(.+?))?\s*\Z")


def pour_re():
    import re
    return _re("pour", r"^\s*↗\s*(.+?)\s*:\s*(.+?)\s*$", re.M)


def rejeu_re():
    """Même syntaxe que les constats de `attente` — on ne crée pas un second
    dialecte de réouverture, il divergerait au premier changement."""
    import re
    return _re("rejeu", r"^\s*↻\s*(machine|service)\s*::\s*(.+?)\s*::\s*(.+?)\s*$", re.I | re.M)


def acquit_re():
    """`↩ <empreinte>` : j'ai traité cette entrée. Seul geste « social » du
    dispositif — sans lui, une demande resterait en tête d'un briefing pour
    toujours, et l'agent apprendrait à ne plus la lire."""
    import re
    return _re("acquit", r"^\s*↩\s*([0-9a-f]{6,12})\s*$", re.M)


def sansaccents(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if not unicodedata.category(c).startswith("M"))


def arrondi1(x):
    """`round(x, 1)` de Python — au PAIR le plus proche, pas au supérieur."""
    try:
        return float("%.1f" % x)
    except (ValueError, OverflowError):
        return x


def arrondi0(x):
    """`int(round(x))` de Python — même règle."""
    try:
        return int(float("%.0f" % x))
    except (ValueError, OverflowError):
        return 0


def nb(v):
    """`Value::as_f64().unwrap_or(0.0)`."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return 0.0
    return float(v)


def _entier(v):
    """`Value::as_i64` : un entier JSON qui tient dans 64 bits, sinon None."""
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    if -(2 ** 63) <= v < 2 ** 63:
        return v
    return None


def _plus_un(n):
    """`n + 1` sur un `i64` : le programme livré (mode release) boucle au lieu de
    déborder, et Python n'a pas de borne."""
    n += 1
    if n > 2 ** 63 - 1:
        n -= 2 ** 64
    return n


def borne(x):
    """La valeur telle que Python l'écrirait : un entier quand la borne a mordu
    (`min(99, …)` rend l'entier 99), un flottant sinon."""
    if x > PLAFOND:
        return int(PLAFOND)
    if x < PLANCHER:
        return int(PLANCHER)
    return x


def espace(depart, creer):
    """Le dossier du carnet, ou None."""
    import memoire
    if memoire.racine_depot(depart) is None:
        return None
    # LA FORME DÉCIDE, ET ELLE EST DÉCIDÉE UNE SEULE FOIS — dans le résolveur.
    #
    # Ces deux lignes portaient leur propre règle : `memoire/equipe` si le
    # dossier existait, `equipe` sinon. Elle ignorait le cerveau. Mesuré le
    # 10/09/2026 par l'audit : sur un projet en `brain/`, `equipe-amorce`
    # créait le carnet à la racine pendant que le résolveur le cherchait dans
    # `brain/workspace/`. Le carnet naissait donc INVISIBLE — créé pour de bon,
    # lu par personne, et rien dans la sortie ne le laissait deviner.
    e = memoire.resous(depart).workspace_prevu()
    if e is None:
        return None
    if creer:
        try:
            os.makedirs(os.path.join(e, ".etat"), exist_ok=True)
        except OSError:
            return None
    return e if os.path.isdir(e) else None


def amorce(depart):
    """AMORCER LE CARNET — le geste qui manquait, et rien d'autre ne le faisait.

    Mesuré le 10/09/2026 sur les deux implémentations : `espace()` n'est jamais
    appelé avec `creer` vrai. Le carnet d'équipe est donc LU partout et CRÉÉ
    nulle part — il existe chez le seul projet où il a été monté à la main, et
    un projet neuf qui passe en multi-agents n'en a jamais. Tout ce qui en
    dépend — les entrées, les chiffres de confiance, le résumé servi au
    briefing — reste muet sans que rien ne l'explique.

    La règle qui place le dossier vit dans `espace()`, et elle y reste : la
    recopier ici ferait deux vérités qui se décalent au premier changement.
    """
    return espace(depart, True)


def slug(nom):
    n = nom if nom else "agent"
    return "".join(c if ((c.isascii() and c.isalnum()) or c in "_-") else "-" for c in n)


def fichier(esp, agent, quand):
    """`quand` : une date (ou un instant) — seul `%Y-%m` compte."""
    return os.path.join(esp, "%s-%s.md" % (quand.strftime("%Y-%m"), slug(agent)))


def empreinte(date, heure, auteur, texte):
    """Date + auteur + première ligne. Uniques parce qu'on n'écrase jamais."""
    import hashlib
    t = texte[:120]
    h = hashlib.sha1(("%s %s|%s|%s" % (date, heure, auteur, t)).encode("utf-8"))
    return h.hexdigest()[:12]


class Entree(object):
    """Une entrée du carnet. Mêmes champs que `carnet::Entree` du Rust.

    pour   liste de couples `(qui, quoi)`
    rejeu  `(source, cmd, motif)` ou None
    vus    liste d'empreintes
    rang   None, ou le rang que `resume()` lui donne
    """
    __slots__ = ("date", "heure", "auteur", "issue", "niveau", "texte", "pour",
                 "rejeu", "vus", "id", "quand", "rang")

    def __init__(self, date, heure, auteur, issue, niveau, texte, pour, rejeu,
                 vus, id, quand, rang=None):
        self.date = date
        self.heure = heure
        self.auteur = auteur
        self.issue = issue
        self.niveau = niveau
        self.texte = texte
        self.pour = pour
        self.rejeu = rejeu
        self.vus = vus
        self.id = id
        self.quand = quand
        self.rang = rang


def _lignes(texte):
    """`str::lines()` de Rust : coupe sur `\\n` seulement, retire un `\\r` final
    devant un `\\n`."""
    morceaux = texte.split("\n")
    sortie = []
    dernier = len(morceaux) - 1
    for i, p in enumerate(morceaux):
        if i == dernier:
            if p != "":
                sortie.append(p)
        else:
            sortie.append(p[:-1] if p.endswith("\r") else p)
    return sortie


def entrees(esp, depuis=None):
    """Les carnets de TOUS les agents, fusionnés et triés — du plus récent au plus
    ancien. C'est le point de tout le dispositif : l'écriture est séparée, la
    lecture ne l'est jamais."""
    if not os.path.isdir(esp):
        return []
    rt, rp, rr, ra = entete_re(), pour_re(), rejeu_re(), acquit_re()
    try:
        noms = os.listdir(esp)
    except OSError:
        return []
    # `p.extension() == "md"` : un nom qui ne fait que `.md` n'a pas d'extension.
    fichiers = sorted(n for n in noms
                      if n.endswith(".md") and n != ".md" and not n.endswith("/"))
    out = []
    for nom in fichiers:
        try:
            with open(os.path.join(esp, nom), encoding="utf-8", newline="") as h:
                texte = h.read()
        except (OSError, ValueError):
            continue
        # [date, heure, auteur, issue, niveau, lignes du corps]
        bloc = []
        for l in _lignes(texte):
            m = rt.search(l)
            if m is not None:
                def g(i, m=m):
                    v = m.group(i)
                    return v.strip(BLANCS) if v is not None else ""
                niv = m.group(5)
                niv = niv.strip(BLANCS) if niv is not None else ""
                bloc.append([g(1), g(2), g(3), g(4), niv if niv else "observé", []])
            elif bloc:
                bloc[-1][5].append(l)
        for date, heure, auteur, issue, niveau, corps_l in bloc:
            corps = "\n".join(corps_l).strip(BLANCS)
            # LES TROIS MARQUEURS, PAS DEUX. L'empreinte est calculée sur ce
            # texte ; en oublier un ici et l'entrée relue n'a plus la même
            # empreinte que l'entrée écrite — sa confiance devient
            # introuvable, silencieusement. Mesuré au banc le 08/09/2026.
            garde = []
            for x in _lignes(corps):
                t = x.lstrip(BLANCS)
                if t.startswith("↗") or t.startswith("↻") or t.startswith("↩"):
                    continue
                x = x.strip(BLANCS)
                if x:
                    garde.append(x)
            texte_e = " ".join(garde)
            pour = [(c.group(1).strip(BLANCS), c.group(2).strip(BLANCS))
                    for c in rp.finditer(corps)]
            mr = rr.search(corps)
            rejeu = (mr.group(1).lower(), mr.group(2), mr.group(3)) if mr else None
            vus = [c.group(1) for c in ra.finditer(corps)]
            ident = empreinte(date, heure, auteur, texte_e)
            quand = "%s %s" % (date, heure)
            out.append(Entree(date, heure, auteur, issue, niveau, texte_e, pour,
                              rejeu, vus, ident, quand, None))
    out.sort(key=lambda e: e.quand, reverse=True)   # stable, comme Rust
    if depuis is not None:
        return [e for e in out if e.quand >= depuis]
    return out


_MOIS = ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"]


def ecrire(esp, agent, texte, issue, niveau=None, pour=(), rejeu=None, vus=()):
    """Une entrée, EN AJOUT SEUL. Rend son empreinte, ou None.

    C'est le seul écrivain du carnet, et il n'écrit que ce que l'agent a
    DÉLIBÉRÉMENT marqué : une case cochée qui porte `↗`. Une case sans `↗` ne
    produit rien — décider qu'un travail ne concerne personne reste le jugement
    de l'agent, jamais celui de la machine.
    """
    if not texte.strip(BLANCS):
        return None
    import datetime
    quand = datetime.datetime.now()
    if niveau is None:
        niveau = "mesuré" if rejeu is not None else "observé"
    f = fichier(esp, agent, quand)
    bloc = []
    if not os.path.exists(f):
        # Le mois en toutes lettres, en anglais comme `chrono` (`%B`) — jamais selon
        # la langue de la machine.
        bloc.append("# Carnet d'équipe — %s · %s %d" % (agent, _MOIS[quand.month - 1], quand.year))
        bloc.append("")
        bloc.append("Écrit par le hook `attente` quand une tâche cochée porte `↗`.")
        bloc.append("**En ajout seul** : on n'y réécrit rien, on n'y supprime rien.")
        bloc.append("")
    bloc.append("## %s %s · %s · %s · %s" % (quand.strftime("%Y-%m-%d"),
                                              quand.strftime("%H:%M"), agent, issue, niveau))
    bloc.append(texte.strip(BLANCS))
    for qui, quoi in pour:
        bloc.append("↗ %s : %s" % (qui, quoi))
    if rejeu is not None:
        bloc.append("↻ %s" % rejeu.lstrip("↻ ").strip(BLANCS))
    # L'ACQUITTEMENT est le seul geste « social » du dispositif.
    for v in vus:
        bloc.append("↩ %s" % v)
    bloc.append("")
    try:
        with open(f, "a", encoding="utf-8", newline="") as fh:
            fh.write("\n".join(bloc) + "\n")
    except OSError:
        return None
    ident = empreinte(quand.strftime("%Y-%m-%d"), quand.strftime("%H:%M"),
                      agent, texte.strip(BLANCS))
    naissance(esp, ident, niveau)
    return ident


# ── la confiance : une surcouche, jamais le carnet ───────────────────────

def etat(esp):
    return os.path.join(esp, ".etat", "confiance.json")


def _refuse(c):
    # serde_json refuse NaN et Infinity ; `json.loads` de Python les accepte.
    raise ValueError(c)


def confiances(esp):
    import json
    try:
        with open(etat(esp), encoding="utf-8") as h:
            v = json.loads(h.read(), parse_constant=_refuse)
    except (OSError, ValueError, RecursionError):
        return {}
    return v if isinstance(v, dict) else {}


def ecrire_etat(esp, d):
    """La forme de `serde_json` en mode joli avec UN espace d'indentation, clés
    dans l'ORDRE D'INSERTION, accents écrits tels quels, sans retour final."""
    import json
    try:
        os.makedirs(os.path.join(esp, ".etat"), exist_ok=True)
    except OSError:
        return
    try:
        texte = json.dumps(d, ensure_ascii=False, indent=1)
    except (TypeError, ValueError):
        return
    cible = etat(esp)
    tmp = os.path.join(esp, ".etat", "confiance.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as h:
            h.write(texte)
        os.replace(tmp, cible)
    except OSError:
        pass


def auj():
    import time
    return time.strftime("%Y-%m-%d")


def naissance(esp, ident, niveau):
    import nature
    d = confiances(esp)
    if ident in d:
        return
    e = {}
    e["n"] = nature.depart(niveau, nature.Maison.Carnet)
    e["m"] = 0
    e["niveau"] = niveau
    e["vu"] = auj()
    d[ident] = e
    ecrire_etat(esp, d)


def bouge(esp, idents, facteur, marque):
    """Le mécanisme de sense-lab : ce que l'agent avait LU bouge quand il déclare
    son issue. Faisable ici parce que c'est le briefing qui sert les entrées —
    il sait donc exactement ce qui a été lu, sans que l'agent désigne rien."""
    if not idents:
        return
    d = confiances(esp)
    a = auj()
    for i in idents:
        c = d.get(i)
        if not isinstance(c, dict):
            continue
        n = arrondi1(nb(c.get("n", 0)) * facteur)
        c["n"] = borne(n)
        if marque:
            m = _entier(c.get("m")) or 0
            c["m"] = _plus_un(m)
        c["vu"] = a
    ecrire_etat(esp, d)


def replancher(esp, ident, verdict):
    """Un `↻` rejoué. TIENT rend son plancher de niveau — c'est ce qui fait que les
    deux étages se tiennent : une mesure refaite RESTAURE la confiance, là où
    l'accumulation seule ne fait que l'éroder. MUET ne conclut RIEN, jamais."""
    import nature
    d = confiances(esp)
    c = d.get(ident)
    if not isinstance(c, dict):
        return
    if verdict == "TIENT":
        niv = c.get("niveau")
        niv = niv if isinstance(niv, str) else ""
        c["n"] = nature.depart(niv, nature.Maison.Carnet)
    elif verdict == "TOMBÉ":
        n = arrondi1(nb(c.get("n", 0)) * EFFONDRE)
        c["n"] = int(PLANCHER) if n < PLANCHER else n
    else:
        return
    m = _entier(c.get("m")) or 0
    c["m"] = _plus_un(m)
    c["vu"] = auj()
    ecrire_etat(esp, d)


def oubli(esp, jours):
    """Ce qui n'est jamais relu descend d'un cran, sans être détruit.

    LE DÉLAI SUIT LA NATURE depuis le 11/09/2026. `jours` est celui d'un fait.
    Une entrée de carnet est une EXPÉRIENCE — ce qu'un agent a fait, et dit
    l'avoir fait — et attend une fois et demie plus longtemps avant de
    descendre ; une entrée « supposé » est une CROYANCE et attend deux fois
    moins. Le cran, lui, ne change pas : la nature étire le temps, elle ne
    frappe pas plus fort.
    """
    import datetime
    import nature
    d = confiances(esp)
    if not d:
        return
    aujd = datetime.date.today()
    change = False
    a = auj()
    for _, c in d.items():
        if not isinstance(c, dict):
            continue
        niv = c.get("niveau")
        niv = niv if isinstance(niv, str) else None
        nat, _o = nature.de(nature.Maison.Carnet, niv, None)
        # `f64::round` : au plus loin de zéro à mi-chemin.
        brut = nature.duree(nat, float(jours))
        delai = int(brut + 0.5) if brut >= 0 else -int(-brut + 0.5)
        limite = (aujd - datetime.timedelta(days=delai)).strftime("%Y-%m-%d")
        vu = c.get("vu")
        vu = vu if isinstance(vu, str) else "9999"
        if vu < limite:
            n = arrondi1(nb(c.get("n", 0)) * OUBLI)
            c["n"] = int(PLANCHER) if n < PLANCHER else n
            c["vu"] = a
            change = True
    if change:
        ecrire_etat(esp, d)


def chiffre(conf, ident):
    """Le chiffre, ou None tant qu'il n'a pas bougé deux fois."""
    c = conf.get(ident)
    if not isinstance(c, dict):
        return None
    if (_entier(c.get("m")) or 0) < MOUVEMENTS_AVANT_AFFICHAGE:
        return None
    return arrondi0(nb(c.get("n", 0)))


# ── ce que le briefing a servi ───────────────────────────────────────────

def lu_fichier(esp, agent, session):
    return os.path.join(esp, ".etat", "%s-%s.lu" % (slug(agent), slug(session)))


def sert(esp, agent, session, idents):
    if not idents:
        return
    try:
        os.makedirs(os.path.join(esp, ".etat"), exist_ok=True)
    except OSError:
        return
    f = lu_fichier(esp, agent, session)
    try:
        with open(f, encoding="utf-8", newline="") as h:
            deja = h.read()
    except (OSError, ValueError):
        deja = ""
    tout = deja.split()
    tout.extend(idents)
    tout = sorted(set(tout))
    try:
        with open(f, "w", encoding="utf-8", newline="") as h:
            h.write("\n".join(tout))
    except OSError:
        pass


def lu(esp, agent, session):
    try:
        with open(lu_fichier(esp, agent, session), encoding="utf-8", newline="") as h:
            return h.read().split()
    except (OSError, ValueError):
        return []


# ── le résumé servi au démarrage ─────────────────────────────────────────

def vise(cible, agent):
    """`↗ PO :` doit atteindre « Projet PO ». On compare sans accents, dans les
    deux sens : un agent écrit tantôt le nom court, tantôt le nom complet."""
    c, a = sansaccents(cible).strip(BLANCS), sansaccents(agent).strip(BLANCS)
    if not c or not a:
        return False
    if c in ("tous", "all", "equipe", "*"):
        return True
    return (c == a or c in a.split() or a.endswith(" " + c) or c.endswith(" " + a))


def acquits(esp, agent):
    """Les empreintes que CET agent a déclaré avoir traitées."""
    out = []
    if not os.path.isdir(esp):
        return out
    fin = "-%s.md" % slug(agent)
    ra = acquit_re()
    try:
        noms = os.listdir(esp)
    except OSError:
        return out
    for nom in noms:
        if not nom.endswith(fin):
            continue
        try:
            with open(os.path.join(esp, nom), encoding="utf-8", newline="") as h:
                t = h.read()
        except (OSError, ValueError):
            continue
        out.extend(c.group(1) for c in ra.finditer(t))
    return sorted(set(out))


def resume(esp, agent, heures, maxi):
    """Rend `(lignes, empreintes servies)`.

    L'ORDRE EST LA MOITIÉ DU DISPOSITIF, et il n'est pas chronologique :
      1. ce qui M'EST ADRESSÉ et que je n'ai pas acquitté — sans limite d'âge,
         parce qu'une demande ne cesse pas d'exister en vieillissant ;
      2. les ÉCHECS des autres, jamais masqués. Repris tel quel à sense-lab :
         un échec sert d'examen, jamais d'exemple ;
      3. le reste, par date.
    """
    import datetime
    oubli(esp, 30)
    limite = (datetime.datetime.now()
              - datetime.timedelta(hours=heures)).strftime("%Y-%m-%d %H:%M")
    conf = confiances(esp)
    vus = acquits(esp, agent)
    pour_moi, echecs, reste = [], [], []
    for e in entrees(esp, None):
        if e.auteur == agent:
            continue                    # je ne me relis pas moi-même
        if any(vise(q, agent) for q, _ in e.pour) and e.id not in vus:
            e.rang = "→ POUR TOI"
            pour_moi.append(e)
        elif sansaccents(e.issue).startswith("echou"):
            if e.quand >= limite:
                e.rang = "ÉCHEC"
                echecs.append(e)
        elif e.quand >= limite:
            e.rang = e.issue
            reste.append(e)
    total = len(pour_moi) + len(echecs) + len(reste)
    choix = (pour_moi + echecs + reste)[:maxi]
    if not choix:
        return ([], [])
    lignes = []
    for e in choix:
        n = chiffre(conf, e.id)
        marque = e.rang if e.rang is not None else e.issue
        quoi = e.texte
        for q, p in e.pour:
            if vise(q, agent):
                quoi = p                # ce qui me concerne
                break
        quoi = quoi[:110]
        jour = e.date[5:]
        # L'EMPREINTE EST DANS LA LIGNE QUI DEMANDE DE L'ACQUITTER. Sans elle,
        # le briefing disait « acquitte par `↩ <empreinte>` » sans jamais
        # donner l'empreinte : le seul geste social du carnet était inerte.
        # Mesuré le 12/09/2026 chez un agent d'épreuve — trois
        # entrées qui le visaient depuis le 08/09, dont une re-versée à
        # l'identique, et aucun moyen de les sortir de sa tête de briefing.
        # Il a tenté de deviner le calcul : la troncature du texte à 120
        # caractères le lui cachait. Un identifiant qu'on demande se montre.
        acquit = " ↩ %s" % e.id if e.rang == "→ POUR TOI" else ""
        lignes.append("  %s · %s · %s%s%s — %s" % (
            jour, e.auteur, marque, acquit,
            " (%d)" % n if n is not None else "", quoi))
    if total > len(choix):
        lignes.append("  … et %d autre(s) dans `equipe/`" % (total - len(choix)))
    return (lignes, [e.id for e in choix])


def main(args):
    """`harnais carnet <espace> <agent>` — rend la lecture du carnet en JSON, pour
    la comparer à celle de Python. C'est un instrument, pas un hook."""
    import sys
    sortie, code = lecture(args[0] if len(args) > 0 else "",
                           args[1] if len(args) > 1 else "")
    sys.stdout.write(_compact(sortie) + "\n")
    if code != 0:
        sys.exit(code)


def _compact(v):
    """`Value::to_string()` de `serde_json` : compact, accents tels quels."""
    import json
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def lecture(esp, agent):
    """Rend `(json, code de sortie)`.

    « CE DOSSIER N'EXISTE PAS » ET « CE CARNET EST VIDE » APPELLENT DEUX GESTES
    OPPOSÉS, et rendaient la même chose : `{"entrees":[]}`, code 0. Mesuré le
    12/09/2026 : un agent a appelé l'instrument avec sa charge sur l'entrée
    standard au lieu de deux arguments ; il a lu un dossier vide, et conclu que
    le carnet d'équipe était vide. Un instrument qui ne trouve pas son objet le
    DIT — c'est la même règle que le reste du harnais.
    """
    if not os.path.isdir(esp):
        return ({"raison": "ce dossier n'existe pas : %s" % esp,
                 "entrees": [], "resume": [], "servis": [], "confiances": {}}, 2)
    es = []
    for e in entrees(esp, None):
        es.append({
            "date": e.date, "heure": e.heure, "auteur": e.auteur, "issue": e.issue,
            "niveau": e.niveau, "texte": e.texte, "id": e.id, "quand": e.quand,
            "pour": [[a, b] for a, b in e.pour],
            "rejeu": (None if e.rejeu is None
                      else {"source": e.rejeu[0], "cmd": e.rejeu[1], "motif": e.rejeu[2]}),
            "vus": e.vus,
        })
    vide = not es
    lignes, servis = resume(esp, agent, 48, 8)
    o = {"entrees": es, "resume": lignes, "servis": servis,
         "confiances": confiances(esp)}
    # Le dossier est là, il ne porte aucune entrée : on le dit, sans faire de
    # ce cas normal une erreur.
    if vide:
        o["vide"] = True
    return (o, 0)


def essai(args):
    """`harnais carnet-essai <espace> <json des empreintes>` — rejoue EXACTEMENT
    la même suite d'écritures que le contrôle différentiel côté Python. Il
    n'existe que pour ça : sans lui, on ne comparerait que la lecture, et les
    écritures — arrondis, bornes, ordre des clés — sont justement là où deux
    implémentations divergent en silence."""
    import json
    import nature
    import sys
    esp = args[0] if len(args) > 0 else ""
    try:
        ids = json.loads(args[1] if len(args) > 1 else "[]")
        if not (isinstance(ids, list) and all(isinstance(x, str) for x in ids)):
            ids = []
    except ValueError:
        ids = []
    for i, niveau in enumerate(["mesuré", "observé", "supposé"]):
        if i < len(ids):
            naissance(esp, ids[i], niveau)
    bouge(esp, ids, nature.REUSSITE, True)
    bouge(esp, ids[:min(1, len(ids))], nature.ECHEC_DECLARE, True)
    if len(ids) >= 3:
        replancher(esp, ids[0], "TIENT")
        replancher(esp, ids[1], "TOMBÉ")
        replancher(esp, ids[2], "MUET")
    sert(esp, "CTO", "sess-1", ids)
    sys.stdout.write(_compact({"lu": lu(esp, "CTO", "sess-1")}) + "\n")


def amorce_cli(args):
    """`harnais equipe-amorce [dossier]` — le seul appel qui CRÉE le carnet. Il n'est
    pas dans un hook exprès : un projet mono-agent n'a pas d'équipe, et lui
    fabriquer un carnet vide à chaque tour donnerait un dispositif qui a l'air
    monté sans que personne l'ait décidé. La conversion en multi-agents
    (`equipe`) appelle `amorce` directement ; cette porte-ci n'a plus d'appelant
    (passe mécanique du 26/09/2026) et reste pour la main.

    Rend le code de sortie."""
    import sys
    ou = args[0] if args else os.getcwd()
    e = amorce(ou)
    if e is not None:
        sys.stdout.write(e + "\n")
        return 0
    sys.stderr.write("carnet non amorcé : aucun dépôt trouvé depuis %s\n" % ou)
    return 1
