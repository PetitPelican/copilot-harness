# -*- coding: utf-8 -*-
"""LA GARDE DES SOUS-AGENTS — hook PreToolUse (`task`), et `harnais laissez-passer-lot`.

Portée du harnais Claude (0.19.3, `sous_agent.py`). Chez Copilot l'outil des
sous-agents s'appelle `task` (COMMENT-CA-MARCHE.md, « Qui parle » ; `agent.py`) ;
`hote` le ramène à `Task`. Ce que le dépôt NE dit PAS : le nom de ses arguments.
Claude lit `description`, `prompt`, `script`, `args` ; ici, tous les champs texte
des arguments (récursivement), `description` et `prompt` d'abord — PAS MESURÉ
contre un `task` réel.

Le 18/10/2026, un sous-agent a lu 2 273 images dans une
seule conversation : 43 M d'équivalent-entrée, la semaine bloquée deux jours.
Le commanditaire, 20/10 : « l'agent principal me demande l'autorisation d'abord s'il veut
utiliser un sous-agent qui fasse ça ». La règle est écrite dans les consignes
communes ; cette garde la fait tenir au moment du lancement. Chez Copilot,
c'est l'humain (@user) qui répond à la question, comme partout dans ce paquet.

CE QUI EST REFUSÉ, sans laissez-passer : une consigne de sous-agent qui
  · lui fait REGARDER un contenu visuel — un verbe qui voit (regarde, décris,
    lis, ouvre, examine, transcris ; look, describe, read, open…) suivi, à trois
    mots au plus, d'une image, photo, capture d'écran, diapositive, infographie,
    d'un PDF ou d'un fichier de ces formats ;
  · lui fait RÉDIGER des textes alternatifs, ou passe par l'OCR ;
  · lui confie un lot de plus de 30 images, captures, diapositives ou PDF
    (« les 2 273 images », « des centaines de captures »).
Un lot de texte (fichiers, pages, migrations) passe, quelle que soit sa taille :
sur un mois, aucun n'a dépassé 6,7 M, et le coupe-circuit du poste le couvre
(CTO, 20/10).
Un audit qui PARLE d'images (« images sans alt », « images surdimensionnées »)
sans les regarder passe : c'est le témoin muet, mesuré sur les 200 consignes de
sous-agents réelles de l'atelier.

LE LAISSEZ-PASSER, sur le modèle de celui de la Production : après le oui de
l'humain à la question majeure, `harnais laissez-passer-lot "<son oui, cité>"`.
Il vaut 120 minutes, chaque lancement est journalisé. CHEZ COPILOT il vaut pour
la COPIE DE TRAVAIL (la racine git) d'où il est posé, pas pour un agent : l'app
lance toutes les conversations à la racine d'une copie, et le shell d'un agent
n'y sait pas qui parle (voir `production`, qui a besoin de le savoir ; ici
l'identité n'est pas jugée). Pas mesuré : ce que le shell d'un agent de l'app voit
de `COPILOT_PROJECT_DIR` ; la clé est donc le dépôt, que le hook et le shell
retrouvent tous deux.
Il ouvre le visuel, PAS le lot : même muni, une consigne de plus de 30 médias
est refusée — un sous-agent neuf par lot de 30 au plus, jamais un seul qui
grossit. Que l'agent puisse se l'accorder est une CONVENTION que le journal
rend visible ; le coupe-circuit du poste reste derrière.

**fail-open** sur une entrée illisible : un garde qui plante ne doit pas
bloquer tout sous-agent.
"""
import os
import re
import sys
import time

DUREE = 120
LOT_MAX = 30

_VOIT = (r"regarde|regarder|regardez|regardes|d[ée]cri(?:s|re|vez|t|vent)|lis|lire|lisez|lit|"
         r"ouvre|ouvrir|ouvrez|ouvres|examine|examiner|examinez|observe|observer|observez|"
         r"visionne|visionner|transcri(?:s|re|vez|t)|look(?:\s+at)?|views?|describe|read|reads|"
         r"reading|opens?|examine|inspect|inspects|captions?|transcribe")
_VISUEL = (r"images?|photos?|captures?(?:\s+d['’]\s*[ée]cran)?|screenshots?|diapositives?|"
           r"slides?|infographi\w*|visuels?|visuals?|pictures?|scans?|pdfs?|"
           r"[^\s\"'`«»()]*\.(?:png|jpe?g|webp|gif|heic|tiff?|bmp|pdf)")
# Trois mots au plus entre le verbe et l'objet, sans franchir une ponctuation qui
# clôt : « Lis d'abord docs/regles.md.\n5. Images : alt manquant » n'est pas une lecture d'images.
_ENTRE = r"(?:[ \t\u00a0]+[^\s.;:!?]+){0,3}?[ \t\u00a0]+[(«\"“]?(?:l['’]|d['’])?"
VOIT = re.compile(r"\b(?:%s)\b(?:\s*-\s*(?:la|le|les|l['’]))?%s(?:%s)\b"
                  % (_VOIT, _ENTRE, _VISUEL), re.I)
ALT = re.compile(r"\b(?:r[ée]dig\w*|[ée]cri\w*|g[ée]n[ée]r\w*|produi\w*|propos\w*|write\w*|"
                 r"generat\w*|draft\w*|creat\w*)\b%s(?:textes?\s+alternatifs?|"
                 r"alt[- ]?texts?|attributs?\s+alt|descriptions?\s+d['’]\s*images?)" % _ENTRE, re.I)
OCR = re.compile(r"\bOCR\b")
NOMBRE = r"\d{1,3}(?:[ \u00a0\u202f,]\d{3})+|\d+"
MEDIAS = (r"images?|photos?|captures?|screenshots?|diapositives?|slides?|infographies?|"
          r"pdfs?|visuels?|visuals?|pictures?|scans?")
LOT = re.compile(r"(?<![\w.,/\-])(%s)\s+(?:[^\W\d_]+\s+)?(%s)\b" % (NOMBRE, MEDIAS), re.I)
MASSE = re.compile(r"\b(?:des\s+centaines|des\s+milliers|hundreds|thousands)\s+(?:de|d['’]|of)\s*"
                   r"(?:\S+\s+)?(?:%s)\b" % MEDIAS, re.I)
NEGATION = re.compile(r"\bn['’]|\bne\s|\baucun|\bjamais\b|\bnever\b|\bdon['’]t\b|\bdo\s+not\b|"
                      r"\bnot\b|\bno\s", re.I)
BORNE = re.compile(r"[;!?\n,:]|\.\s")


def _niee(texte, debut):
    """La proposition qui porte la prise est-elle niée avant elle ?"""
    avant = texte[:debut]
    coupe = 0
    for m in BORNE.finditer(avant):
        coupe = m.end()
    return bool(NEGATION.search(avant[coupe:]))


def _extrait(texte, m):
    return " ".join(texte[m.start():m.end()].split())[:80]


def visuel(texte):
    """La prise (un extrait de la consigne) qui fait regarder du visuel, ou None."""
    for motif in (ALT, VOIT):
        for m in motif.finditer(texte):
            if not _niee(texte, m.start()):
                return _extrait(texte, m)
    m = OCR.search(texte)
    if m and not _niee(texte, m.start()):
        return "OCR"
    return None


def lot(texte):
    """`(nombre, extrait)` du plus gros lot de plus de LOT_MAX médias nommé, ou None."""
    pire = None
    for m in LOT.finditer(texte):
        n = int(re.sub(r"\D", "", m.group(1)))
        if n <= LOT_MAX or _niee(texte, m.start()):
            continue
        if pire is None or n > pire[0]:
            pire = (n, _extrait(texte, m))
    if pire:
        return pire
    m = MASSE.search(texte)
    if m and not _niee(texte, m.start()):
        return (None, _extrait(texte, m))
    return None


# ── le laissez-passer ────────────────────────────────────────────────────

def _agent(depart=None):
    """La clé du laissez-passer : la racine git de la copie de travail (le dossier
    lui-même hors dépôt). Le hook (`COPILOT_PROJECT_DIR`, déplacé dans `agents/<nom>`
    par l'app) et le shell de l'agent (dossier courant) y arrivent tous deux."""
    d = os.path.abspath(depart or os.environ.get("COPILOT_PROJECT_DIR") or os.getcwd())
    try:
        import memoire
        r = memoire.arbre_courant(d)
    except Exception:       # noqa — la clé retombe sur le dossier
        r = None
    try:
        return os.path.realpath(r or d)
    except (OSError, ValueError):
        return r or d


def _fichiers(agent):
    import socle
    d = os.path.join(socle.socle(), "sous-agents")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    s = socle.cle_memoire(agent).strip("-") or "agent"
    return os.path.join(d, s + ".laissez-passer"), os.path.join(d, s + ".log")


def journalise(agent, ligne):
    _, log = _fichiers(agent)
    try:
        with open(log, "a", encoding="utf-8") as h:
            h.write("%s\t%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), ligne.replace("\n", " ")))
    except OSError:
        pass


def valide(agent):
    """Le motif d'un laissez-passer encore valide, ou None."""
    f, _ = _fichiers(agent)
    try:
        if time.time() - os.path.getmtime(f) > DUREE * 60:
            return None
        with open(f, encoding="utf-8") as h:
            return h.read().strip() or "(sans motif)"
    except (OSError, ValueError):
        return None


# ── le hook ──────────────────────────────────────────────────────────────

def _textes(v, profondeur=0):
    """Tous les textes d'une valeur d'arguments : chaînes, et ce que portent listes et objets."""
    if profondeur > 6:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [t for x in v.values() for t in _textes(x, profondeur + 1)]
    if isinstance(v, (list, tuple)):
        return [t for x in v for t in _textes(x, profondeur + 1)]
    return []


def consigne(d):
    """Le texte que le sous-agent recevra, ou None si ce n'est pas un lancement."""
    import hote
    if not isinstance(d, dict) or not hote.est_sous_agent(d):
        return None
    ti = d.get("tool_input")
    if isinstance(ti, dict):
        # `description` et `prompt` d'abord (les noms de Claude), puis tout autre champ texte.
        premiers = [ti.get(k) for k in ("description", "prompt")]
        reste = [v for k, v in ti.items() if k not in ("description", "prompt")]
        morceaux = _textes(premiers) + _textes(reste)
    else:
        morceaux = _textes(ti)
    return "\n".join(m for m in morceaux if m)


QUESTION = (
    "Pose d'abord à l'humain (@user) la question majeure, fermée, dans ton message de fin de tour : "
    "ce que le sous-agent lira (images, captures, PDF…), combien d'éléments en tout, et le "
    "découpage — un sous-agent neuf par lot de %d au plus, donc combien de lots. Sur son oui, "
    "et seulement lui : `harnais laissez-passer-lot \"<son oui, cité>\"` (valable %d min, chaque "
    "lancement journalisé), puis relance, une consigne par lot." % (LOT_MAX, DUREE))


def juge(d):
    """Le motif du refus (`str`), ou None pour laisser passer."""
    texte = consigne(d)
    if not texte:
        return None
    agent = _agent(os.environ.get("COPILOT_PROJECT_DIR") or d.get("cwd"))
    l = lot(texte)
    if l is not None:
        n, extrait = l
        combien = ("%d médias" % n) if n else "une masse de médias"
        return ("sous-agent : la consigne lui confie %s (« %s »), au-delà du lot de %d.\n\n"
                "Un sous-agent neuf par lot de %d au plus, jamais un seul qui grossit (18/10 : "
                "2 273 images lues par un seul, la semaine bloquée deux jours). Même avec un "
                "laissez-passer, découpe : donne à chacun sa part, pas le total. %s"
                % (combien, extrait, LOT_MAX, LOT_MAX, QUESTION))
    prise = visuel(texte)
    if prise is None:
        return None
    motif = valide(agent)
    if motif is None:
        return ("sous-agent : la consigne lui fait lire du visuel (« %s »).\n\nUn sous-agent "
                "qui lit des images, des captures ou des PDF ne part pas sans l'accord de l'humain "
                "(18/10 : 2 273 images lues, 43 M de jetons, la semaine bloquée). %s"
                % (prise, QUESTION))
    journalise(agent, "usage\t%s\t%s" % (motif, " ".join(texte.split())[:160]))
    return None


def main(entree):
    import json
    import hote
    try:
        d = json.loads(entree)
    except (ValueError, RecursionError):
        return
    motif = juge(d)
    if motif is not None:
        sys.stdout.write(hote.refus(motif) + "\n")


def laissez_passer(args):
    """`harnais laissez-passer-lot "motif"` : le oui de l'humain, cité, pour cette copie de travail."""
    agent = _agent()
    motif = " ".join(a for a in args if a).strip()
    if not motif:
        sys.stderr.write("laissez-passer-lot : cite le oui de l'humain, entre guillemets.\n")
        return 2
    f, log = _fichiers(agent)
    with open(f, "w", encoding="utf-8") as h:
        h.write(motif + "\n")
    journalise(agent, "déposé\t%s" % motif)
    sys.stdout.write("Laissez-passer posé : %d min, pour les sous-agents lancés depuis la copie %s, "
                     "par lots de %d au plus. Journal : %s\n" % (DUREE, agent, LOT_MAX, log))
    return 0
