# -*- coding: utf-8 -*-
"""LA FIN DE TOUR — hook `Stop`. Ce qui attend le commanditaire.

Port de `harnais/src/attente.rs` (Rust 0.12.8), lui-même port de `hooks/attente.py`,
le plus gros du harnais. `.mind/todo.md` était réclamé par le garde de commit ;
mesuré le 06/09/2026, un agent qui analyse, qui est bloqué maintenant, ou qui n'a
pas encore commité n'écrivait donc RIEN — 124 demandes s'étaient accumulées sur 10
projets sans qu'aucune ne remonte. `Stop` est le seul instant qui coïncide avec
« il va peut-être lire ».

DEUX CHOSES, DANS CET ORDRE : il BLOQUE (code 2) si du code a bougé sans que le
todo suive, et il garde la FORME de ce qui attend le commanditaire dans le todo. Il
n'écrit nulle part ailleurs : plus de Rappels depuis le 08/10/2026 (décision du commanditaire :
« je ne veux plus que la todo qui est tenue »).

FAIL-OPEN PARTOUT, ET SILENCIEUX. Le seul code 2 est celui des gardes, et chacun
est borné par un témoin : on ne bloque QU'UNE FOIS par état. Sans garde, un agent
qui n'obtempère pas — ou qui ne peut pas — tourne à l'infini. Au pire une question
qui attend ; jamais un agent coincé.

VITESSE. `Stop` se déclenche à chaque tour : `re`, `json`, `subprocess`,
`hashlib` ne s'importent que dans les fonctions qui s'en servent, et le hook
sort dès que la date du todo n'a pas bougé (`.pousse`).
"""
import os
import sys
import time

import socle

# Chemins = `str` (pas de pathlib : il coûte à l'import).


def etat_dir():
    return os.path.join(socle.socle(), "attente")


def journal_f():
    return os.path.join(etat_dir(), "blocages.log")


def rechutes_f():
    """LE CARNET QUE LES AGENTS ÉCRIVENT. COPILOT : c'est le même fichier que celui
    qui est servi — `rechutes.md` du dossier d'état, que les messages de la garde
    désignent (« le dossier d'état indiqué par `harnais diagnostic` »). Le défaut
    de Claude 0.18 (le carnet servi n'était pas celui où les agents écrivaient, 144
    lignes lues contre 950 écrites) n'existe donc pas ici : la lecture et
    l'écriture n'ont qu'un chemin, et c'est ce qui doit le rester."""
    return os.path.join(socle.socle(), "rechutes.md")


# Ce qui se SERT doit se lire d'un coup d'œil : la partie lue du carnet a gonflé
# de onze questions à 855 lignes de récidives (Claude, 14/10/2026). On sert les
# titres — une ligne par question — et on nomme le fichier pour le détail.
RECHUTES_LIGNES_MAX = 60


def resserre(texte):
    """Les titres du carnet : les intertitres et le gras de tête de chaque
    `- **question**`. Un carnet sans cette forme est servi tronqué, jamais vide."""
    import re
    out = []
    lignes_ = texte.split("\n")
    for i, l in enumerate(lignes_):
        if l.startswith("#"):
            out.append(l.strip())
            continue
        if not re.match(r"\s*- \*\*", l):
            continue
        # Un titre en gras peut courir sur deux ou trois lignes : on le suit
        # jusqu'au `**` qui le ferme.
        bloc = l.split("**", 1)[1]
        k = i + 1
        while "**" not in bloc and k < len(lignes_) and k <= i + 3 and lignes_[k].strip():
            bloc += " " + lignes_[k].strip()
            k += 1
        titre = bloc.split("**", 1)[0]
        out.append("- " + " ".join(titre.split()))
    if not any(x.startswith("- ") for x in out):
        out = texte.split("\n")
    if len(out) > RECHUTES_LIGNES_MAX:
        out = out[:RECHUTES_LIGNES_MAX] + ["… (%d ligne(s) de plus)" % (len(out) - RECHUTES_LIGNES_MAX)]
    return "\n".join(out).strip()


SEP_RECHUTES = "<!-- ÉCRITURE"

# Au plus, par session : la garde par signature d'état ne suffit pas seule,
# car corriger le todo produit un état neuf, donc un nouveau blocage.
RECHUTES_MAX = 3
# À partir de combien de fois une garde qui reprend le même agent cesse d'être
# un rappel pour devenir une règle à écrire. Trois : deux peuvent être un
# hasard, trois est une habitude.
RECIDIVE = 3
# Combien de mesures identiques avant de dire qu'on s'acharne.
CIBLE_ACHARNEMENT = 3
# Les multiplicateurs du résultat vivent avec tous les autres poids de la
# mémoire, dans `nature`, depuis le 11/09/2026.
# Bornes dures : ce hook a 40 s avant d'être tué, et un tour qui pend est pire
# qu'un constat périmé.
CONSTAT_MAX = 5
CONSTAT_S = 10.0
CONSTAT_BUDGET = 25.0

# L'ÉCHÉANCE COMMUNE DE LA FIN DE TOUR. Le hook est déclaré à 40 s, et un hook
# tué ne dit rien : l'agent rend la main, et ça ressemble à « rien à signaler ».
# Relevé par l'audit (P6) : 25 s de constats + 25 s par appel aux Rappels
# dépassaient déjà la limite ; un verrou de 20 s s'y est ajouté depuis. Plutôt
# que de retoucher chaque chiffre, chaque étape bornée prend AU PLUS ce qui
# reste avant l'échéance ; ce qui n'a plus le temps échoue comme un délai
# dépassé, et les chemins existants le DISENT. 4 s de marge pour parler.
ECHEANCE_S = 36.0
_DEBUT = [None]


def reste_s():
    if _DEBUT[0] is None:
        _DEBUT[0] = time.monotonic()
    return ECHEANCE_S - (time.monotonic() - _DEBUT[0])


CARNET_MAX = 2
# Combien de fois une ligne mal formée est rappelée avant qu'on la laisse.
RAPPELS_FORME = 2
TIENT = "TIENT"
TOMBE = "TOMBÉ"
MUET = "MUET"

_CTX = [("?", "?", ".")]


def ctx():
    return _CTX[0]


def slug(s):
    return "".join(c if ((c.isascii() and c.isalnum()) or c == "_" or c == "-") else "-" for c in s)


def lis(p):
    """`read_to_string` : le fichier tel quel (pas de traduction des fins de
    ligne), et vide s'il manque, est illisible ou n'est pas de l'UTF-8."""
    try:
        with open(p, encoding="utf-8", newline="") as f:
            return f.read()
    except (OSError, ValueError):
        return ""


def ecrit(p, texte):
    """`let _ = std::fs::write(…)` : écrire sans jamais lever."""
    try:
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(texte)
        return True
    except (OSError, ValueError):
        return False


def ajoute(p, texte):
    try:
        with open(p, "a", encoding="utf-8", newline="") as f:
            f.write(texte)
        return True
    except (OSError, ValueError):
        return False


def mkdirs(p):
    try:
        os.makedirs(p, exist_ok=True)
    except OSError:
        pass


def lignes(t):
    """`str::lines()` de Rust : coupe sur `\\n` seulement (jamais sur `\\x0b`,
    `\\x85`, `\\u2028` comme `splitlines`), et n'ôte un `\\r` que devant un `\\n`."""
    if not t:
        return []
    m = t.split("\n")
    if m[-1] == "":
        m.pop()
    fin = len(m) - 1
    avec_saut = t.endswith("\n")
    return [(l[:-1] if (l.endswith("\r") and (k < fin or avec_saut)) else l)
            for k, l in enumerate(m)]


def _re(p, f=""):
    """Un motif compilé ; `f` : « i » (insensible à la casse), « m » (^ et $ par
    ligne), « s » (le point couvre aussi le saut de ligne)."""
    import re
    n = 0
    for c in f:
        n |= {"i": re.I, "m": re.M, "s": re.S}[c]
    return re.compile(p, n)


def _sha(s):
    try:
        import _sha1
        return _sha1.sha1(s.encode("utf-8")).hexdigest()
    except ImportError:
        import hashlib
        return hashlib.sha1(s.encode("utf-8")).hexdigest()


def sha12(s):
    return _sha(s)[:12]


def sha16(s):
    return _sha(s)[:16]


def _i64(s, defaut):
    """`s.parse::<i64>()` : un signe facultatif et des chiffres ASCII, rien d'autre."""
    import re
    if re.match(r"[+-]?[0-9]+\Z", s):
        n = int(s)
        if -(2 ** 63) <= n < 2 ** 63:
            return n
    return defaut


def maintenant(fmt):
    return time.strftime(fmt)


def journal(quoi, detail):
    """Une ligne par blocage. Toute erreur est avalée : tracer ne bloque pas.

    LE HARNAIS N'AVAIT AUCUN INSTRUMENT SUR LUI-MÊME. Neuf sorties bloquantes
    tournaient tous les jours et rien n'écrivait laquelle partait — c'est
    exactement le défaut qu'il traque : un mécanisme sans trace. Le contenu du
    message n'y va PAS : il porte du texte venu des Rappels, donc du dehors."""
    agent, session, _ = ctx()
    mkdirs(etat_dir())
    ajoute(journal_f(), "%s\t%s\t%s\t%s\t%s\n" % (
        maintenant("%Y-%m-%d %H:%M:%S"), agent, quoi, detail[:120], session))


def recidive(quoi, jours):
    """Combien de fois CE blocage a déjà repris CET agent cette semaine. C'est
    lui qui rend la boucle possible : sans trace, « ça revient » était une
    impression, jamais un nombre."""
    agent = ctx()[0]
    limite = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - jours * 86400))
    ls = lignes(lis(journal_f()))
    n = 0
    for l in ls[max(0, len(ls) - 4000):]:
        c = l.split("\t")
        if len(c) >= 3 and c[0] >= limite and c[1] == agent and c[2] == quoi:
            n += 1
    return n


def resultat(mult):
    """UN RÉSULTAT RETOMBE SUR CE QUI A SERVI À L'OBTENIR : les sections de faits
    lues dans cette session depuis le dernier verdict (`brain/poids.json`, voir
    `poids`). LE POIDS CAUSAL EST LE VIDAGE : on n'applique qu'à ce qui a été lu
    DEPUIS LE DERNIER VERDICT, et on efface la liste après."""
    import poids
    _, session, _ = ctx()
    return poids.resultat(socle.socle(), session, mult)


def _json_objet(texte):
    import json
    try:
        v = json.loads(texte, parse_constant=_refuse_constante)
    except Exception:
        return None
    return v if isinstance(v, dict) else None


def _refuse_constante(c):
    raise ValueError(c)


# LES SEULES GARDES QUI RENVOIENT L'AGENT AU TRAVAIL (harnais Copilot 1.3.0).
# Sous Copilot, l'app affiche la raison d'un renvoi comme un message de
# l'UTILISATEUR : les gardes de forme (constats rejouables et tombés, forme des
# questions, liste des rechutes, acharnement sur la cible, relecteur, `!cible`)
# y produisaient de faux messages sans rien apporter au suivi. Leur code reste,
# derrière cette liste ; en ajouter une la réarme. Gardées : le todo à jour après
# du code (B1), le carnet d'équipe (B5), les faits (B6), les questions à poser
# (B13), leur ligne Notion (B14, canal Notion seul) — plus, venues du harnais
# Claude, la synchronisation (B15, si `HARNAIS_SYNCHRO`) et les faits d'un expert
# (B16, si `HARNAIS_PROFIL=expert`).
GARDES_ACTIVES = (
    "B1-code-sans-todo", "B5-carnet", "B6-faits", "B13-poser", "B14-notion",
    "B15-synchro", "B16-faits", "B16-local",
)


def active(quoi):
    return quoi in GARDES_ACTIVES


_LIBELLES = {
    "B1-code-sans-todo": "du code a changé sans que la liste de tâches du projet soit mise à jour",
    "B4-cible": "@user a fait une demande marquée !cible, pas encore close",
    "B5-carnet": "du code a été commité dans une zone partagée sans note au carnet d'équipe",
    "B6-faits": "les fichiers de faits du projet ont été modifiés",
    "B7-constat-sans-rejeu": "des constats de la liste n'ont aucun moyen d'être revérifiés",
    "B8-forme": "des lignes destinées à @user sont écrites comme des constats, pas comme des questions fermées",
    "B9-tombe": "des constats ne sont plus vrais d'après leur propre vérification",
    "B10-rechutes": "des points vont partir chez @user : la liste des erreurs déjà vues doit être rejouée avant",
    "B11-acharnement": "la cible du projet n'avance pas malgré plusieurs mesures",
    "B12-contredit": "un relecteur indépendant contredit des affirmations de l'agent",
    "B13-poser": "des questions nouvelles attendent @user et le message de fin de tour ne les pose pas",
    "B14-notion": "des questions pour @user n'ont pas leur ligne dans la base Notion du projet",
    "B15-synchro": "le dépôt partagé avec l'autre poste ne se synchronise plus",
    "B16-faits": "@user a donné des faits à cet agent expert, et ils ne sont pas notés dans ses fiches",
    "B16-local": "des données qui identifient quelqu'un sont écrites hors du registre local",
}


def libelle(quoi):
    """Ce que dit une garde, en clair : la phrase que lit quelqu'un qui ne connaît
    pas le harnais. Une garde absente de cette liste n'est jamais muette : elle
    retombe sur la formule générale."""
    return _LIBELLES.get(quoi or "", "règle de tenue du projet")


def entete(quoi):
    """LA SIGNATURE. Quand une garde renvoie l'agent au travail, l'app affiche sa
    raison comme un message de l'utilisateur. Sans ce rappel, @user croit avoir
    écrit une consigne qu'il ne reconnaît pas, et personne ne sait d'où elle vient."""
    code = " « %s »" % quoi if quoi else ""
    return ("[Harnais — rappel automatique. Ce message n'a pas été écrit par @user.]\n"
            "Le harnais est le plugin installé dans l'atelier : à chaque fin de tour, une garde "
            "vérifie que le projet est tenu à jour, et renvoie l'agent au travail quand ce n'est "
            "pas le cas.\n"
            "Garde déclenchée%s : %s.\n"
            "@user n'a rien à faire : l'agent corrige seul.\n\n" % (code, libelle(quoi)))


# L'unique canal de sortie — et donc le seul point où tracer un blocage, et le
# seul où l'on peut voir qu'il revient. (Les textes des renvois sont en bas du
# fichier : ils sont longs.)

def sortie(code, message=None, quoi=None, detail=""):
    """COPILOT : un renvoi (code 2) part sur la sortie standard en
    `{"decision":"block","reason":…}`, et le programme sort en 0 — un code non
    nul n'est qu'une panne de hook (voir `hote`)."""
    if code == 2:
        if quoi is not None:
            vues = recidive(quoi, 7)           # AVANT d'écrire la ligne de ce tour
            journal(quoi, detail)
            # UNE GARDE QUI MORD EST UN RÉSULTAT : ce qu'on avait lu en chemin
            # n'a pas empêché le blocage. Échec MINEUR — un rappel de forme
            # n'est pas un constat démenti.
            import nature
            resultat(nature.GARDE)
            # LA PROMOTION QUI MANQUAIT : une panne qui revient devient une
            # ligne de la liste de contrôle. Pas au premier passage — une garde
            # qui mord une fois a fait son travail.
            if message is not None and vues + 1 >= RECIDIVE:
                message += RECIDIVE_MSG.format(vues + 1)
        # NE RECOPIE PAS. Chaque renvoi faisait réécrire à l'agent tout son
        # message, que @user avait déjà lu.
        if message is not None:
            message = entete(quoi) + message + PIED_RENVOI
        import hote
        hote.renvoie(message or "")
    if message is not None:
        try:
            sys.stderr.write(message)
            sys.stderr.flush()
        except (OSError, ValueError):
            pass
    sys.exit(code)


def enveloppe_note(note):
    """L'ENVELOPPE QUI PARLE À CODE DE SORTIE 0 : une note pour @user, qui ne
    relance pas l'agent. Seul un objet JSON est lu. Que Copilot CLI affiche
    `systemMessage` en fin de tour : NON MESURÉ."""
    import json
    return json.dumps({"systemMessage": note}, separators=(",", ":"))


def dit_sans_bloquer(note):
    """Dire l'échec sans bloquer le tour. Le pendant exact de `sortie(2, …)` :
    celle-là renvoie l'agent au travail, celle-ci ne fait que prévenir."""
    sys.stdout.write(enveloppe_note(note) + "\n")
    sys.stdout.flush()
    sys.exit(0)


def rechutes():
    """La partie SERVIE de la liste — jamais la partie qui dit comment l'écrire.
    Fichier absent, illisible, vide : on rend "" et rien ne bloque."""
    # La copie de l'agent gagne ; celle livrée avec le plugin n'est qu'une
    # amorce, pour qu'une installation neuve ne démarre pas les mains vides.
    cands = [rechutes_f()]
    livre = socle.livre()
    if livre is not None:
        cands.append(os.path.join(livre, "rechutes.md"))
    for f in cands:
        try:
            with open(f, encoding="utf-8", newline="") as h:
                t = h.read()
        except (OSError, ValueError):
            continue
        lu = t.split(SEP_RECHUTES)[0].strip()
        if not lu:
            return ""
        return resserre(lu) + "\n\nLe détail de chaque question, et ses récidives : %s" % f
    return ""


def reouvre_re():
    return _re(r"^\s*↻\s*(machine|service)\s*::\s*(.+?)\s*::\s*(.+?)\s*$", "im")


class Spec(object):
    __slots__ = ("source", "cmd", "motif", "sans")

    def __init__(self, source, cmd, motif, sans):
        self.source, self.cmd, self.motif, self.sans = source, cmd, motif, sans


def est_gabarit(sp):
    """UN GABARIT N'EST PAS UN INSTRUMENT.

    Signalé le 10/09/2026 par un agent d'exploitation, qui recevait à
    chaque cycle « la cible n'est pas tenue et l'écart n'a PAS BOUGÉ depuis 3
    mesures » — alors qu'aucune mesure n'existait. La section `## Consigne` de
    son projet portait la ligne d'EXEMPLE :

        ↻ service :: <commande qui rend le nombre> :: <motif si la cible est tenue>

    Elle a la forme exacte d'une vérification, donc elle était retenue comme
    telle. `<commande…>` échoue, la sortie ne contient pas `<motif…>`, verdict
    TOMBÉ — à chaque tour, sans jamais bouger, ce qui est précisément la
    signature de l'acharnement que le dispositif cherche à attraper.

    **Le garde existait déjà et ne mordait pas** : il testait « la liste est-elle
    vide », et elle ne l'était pas — elle contenait un décor. C'est la troisième
    fois que le même motif se présente : ne rien avoir mesuré et avoir mesuré un
    échec se ressemblent en sortie, et le second est celui qui prescrit."""
    def a_trou(s):
        s = s.strip()
        return (s.startswith("<") and s.endswith(">")) or (s.startswith("[") and s.endswith("]"))
    return a_trou(sp.cmd) or a_trou(sp.motif)


def consigne(d_fact):
    """La cible du projet : une phrase, et de quoi mesurer l'écart.

    ELLE VIT DANS LES FAITS DU PROJET, ET C'EST UNE DÉCISION. Un agent qui écrit
    sa propre cible peut toujours l'atteindre — c'est le commanditaire qui l'écrit, dans
    le seul dossier que le garde protège. Le hook ne fait que la LIRE."""
    if d_fact is None:
        return None, []
    t = lis(os.path.join(d_fact, "base.md"))
    m = _re(r"^#{2,3}\s*consigne\b.*$", "im").search(t)
    if m is None:
        return None, []
    reste = t[m.end():]
    # Bornée au titre suivant : la section porte la phrase, puis ses `↻`.
    f = _re(r"^#{1,3}\s", "m").search(reste)
    corps = reste[:f.start()] if f else reste
    specs = []
    for c in reouvre_re().finditer(corps):
        sp = Spec(c.group(1).lower(), c.group(2), c.group(3), False)
        # Le gabarit reste LISIBLE dans le fichier — il est là pour montrer la
        # forme à qui écrira la vraie ligne. Il ne se joue simplement pas.
        if not est_gabarit(sp):
            specs.append(sp)
    phrase = " ".join(l for l in (x.strip() for x in lignes(corps))
                      if l and not l.startswith("↻"))
    p = lisible(phrase)[:200]
    return (p if p else None), specs


def purge_temoins(jours):
    """Les témoins de SESSION ne servent qu'à leur session. Ceux par AGENT sont
    cumulatifs et durables : on n'y touche JAMAIS — les effacer redonnerait leur
    amnistie de première rencontre et l'arriéré repartirait."""
    limite = time.time() - jours * 86400
    jetables = (".bloc", ".equipe", ".constat", ".tombe", ".faits", ".compteur")
    try:
        noms = os.listdir(etat_dir())
    except OSError:
        return
    for nom in noms:
        if os.path.splitext(nom)[1] in jetables:
            p = os.path.join(etat_dir(), nom)
            try:
                if os.path.getmtime(p) < limite:
                    os.remove(p)
            except OSError:
                pass


def destinataires():
    """À QUI S'ADRESSE UNE DEMANDE. Ne PAS écrire un nom en dur : ce fichier est
    partagé par tous les projets, et un hook qui ne reconnaît pas le
    destinataire ne remonte RIEN — sans le dire, puisqu'il est fail-open."""
    v = [d.strip().lower() for d in os.environ.get("ATTENTE_DESTINATAIRES", "user").split(",")
         if d.strip()]
    return v if v else ["user"]


def lisible(s):
    """Du Markdown vers un libellé lisible d'une ligne."""
    s = s.replace("`", "").replace("**", "").replace("__", "")
    return _re(r"\s{2,}").sub(" ", s).strip(" .,;—-")


def case_re():
    return _re(r"^\s*[-*]\s*\[( |x|X|>|~)\]\s+")


def reponse_re():
    return _re(r"^\s*\S[^→\n]{0,24}?\s*→\s*\S", "m")


# Un tiret de liste devant est admis : `  - fini quand → …` est la même ligne.
# Refusé jusqu'au 27/09/2026, et ça renvoyait des questions bien formées (PO).
def fini_re():
    return _re(r"^\s*(?:[-*•]\s+)?fini quand\s*→\s*\S", "im")


def constat_re():
    return _re(r"(?:^|(?<=\s))\?constat\b", "i")


def arobase_re():
    return _re(r"(?:^|(?<=\s))@[A-Za-zÀ-ÿ][\w-]*\b")


def prio_re():
    return _re(r"!(haut|moyen|bas)\b", "i")


def blocs_bruts(texte):
    """Le texte COMPLET de chaque tâche, recollé pour l'affichage. On ne
    réinterprète RIEN : les marqueurs sont retirés parce que le parseur du
    dialecte les a DÉJÀ lus et en fait foi."""
    cr, rp, cs, ar, pr = case_re(), reponse_re(), constat_re(), arobase_re(), prio_re()
    cont = _re(r"^\s+\S")
    blocs = []
    ouvert = False
    for l in lignes(texte):
        if cr.search(l):
            blocs.append([cr.sub("", l, count=1).strip()])
            ouvert = True
        elif ouvert and l.strip() and cont.search(l):
            # La ligne de réouverture est de la MÉCANIQUE : elle porte une
            # commande shell, exactement ce que la consigne interdit au commanditaire.
            if not l.lstrip().startswith("↻"):
                blocs[-1].append(l.strip())
        elif not l.strip():
            ouvert = False
    out = []
    for b in blocs:
        t = b[0]
        # Un libellé en gras court souvent sur deux lignes et se recolle ; une
        # ligne de RÉPONSE garde la sienne — sur un téléphone, trois réponses
        # aplaties en un paragraphe redeviennent le pavé qu'on veut éviter.
        for l in b[1:]:
            t += ("\n" if rp.search(l) else " ") + l
        t = pr.sub("", t)
        t = ar.sub("", t)
        out.append(cs.sub("", t))
    return out


def blocs_lignes(texte):
    """Les blocs de tâches, lignes BRUTES — marqueurs compris. `blocs_bruts()`
    recolle et nettoie pour l'affichage ; ici la ligne `↻` doit survivre."""
    cr, cont = case_re(), _re(r"^\s+\S")
    blocs = []
    ouvert = False
    for l in lignes(texte):
        if cr.search(l):
            blocs.append([l])
            ouvert = True
        elif ouvert and l.strip() and cont.search(l):
            blocs[-1].append(l)
        elif not l.strip():
            ouvert = False
    return ["\n".join(b) for b in blocs]


def specs_constat(texte):
    """Par tâche, dans l'ordre : `None`, ou ce qu'il faut pour la rouvrir."""
    cs, ro = constat_re(), reouvre_re()
    out = []
    for b in blocs_lignes(texte):
        if not cs.search(b):
            out.append(None)
            continue
        m = ro.search(b)
        if m is not None:
            out.append(Spec(m.group(1).lower(), m.group(2), m.group(3), False))
        else:
            out.append(Spec("", "", "", True))
    return out


# Les inspecteurs du poste : ils ne peuvent PAS répondre à une question distante.
LOCAL = ("grep", "rg", "ls", "cat", "head", "tail", "wc", "awk", "sed",
         "find", "stat", "file", "du", "df", "md5", "shasum", "sort", "uniq", "cut", "tr",
         "echo", "test", "[", "ps", "pgrep", "pkill", "defaults", "diff", "basename",
         "dirname", "readlink", "date", "id", "whoami", "uname")


def sort_de_la_machine(cmd):
    """Vrai si la commande peut atteindre l'extérieur, OU SI ON N'EN SAIT RIEN.

    LA PREMIÈRE VERSION DE CETTE RÈGLE ÉTAIT FAUSSE, et c'est le contrôle qui
    l'a dit : passée sur les 34 `↻` vivants de l'atelier, elle rendait MUET NEUF
    constats justes. D'où la forme d'ici — on ne tranche que ce dont on est SÛR
    qu'il est local. Un doute ne se tranche pas contre le travail de quelqu'un."""
    distant = _re(r"https?://|(?<![\w-])(curl|wget|ssh|scp|rsync|dig|host|nslookup|nc|ncat|ping|telnet|nmap|gh|az|aws|gcloud|tailscale|doppler|supabase|stripe|vercel|fly|netlify|psql|mysql|mongosh|redis-cli|openssl|npm|pnpm|pip|op|vault)\b", "i")
    if distant.search(cmd):
        return True
    c = cmd.strip().lstrip("(").lstrip()
    premier = _re(r"[\s;|&]+").split(c, 1)[0]
    premier = premier.split("/")[-1]
    return premier not in LOCAL          # inconnu ⇒ on ne tranche pas


def _decode(octets):
    """`read_to_string` : un flux qui n'est pas de l'UTF-8 rend VIDE, pas tronqué."""
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def lancer_limite(argv, secs):
    """LANCER, ATTENDRE, ET NE PAS PAYER L'ATTENTE. Les deux flux sont vidés
    pendant l'attente (`communicate`) : lire la sortie APRÈS la fin bloque sur un
    tuyau plein, l'enfant s'arrête en écrivant et on rendrait MUET là où un
    verdict est possible.

    Rend `(code, sortie, erreur)`, ou None si le délai est dépassé ou si rien
    n'a pu être lancé. Séparés : le canal du téléphone ne lisait QUE stdout."""
    import subprocess
    secs = min(secs, reste_s())
    if secs <= 0.0:
        return None
    try:
        e = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, ValueError):
        return None
    try:
        out, err = e.communicate(timeout=max(secs, 0.0))
    except subprocess.TimeoutExpired:
        try:
            e.kill()
        except OSError:
            pass
        try:
            e.wait()
        except OSError:
            pass
        # Un petit-enfant peut garder les tuyaux ouverts : on ne les lit plus.
        for f in (e.stdout, e.stderr):
            try:
                f.close()
            except (OSError, ValueError, AttributeError):
                pass
        return None
    except Exception:
        return None
    code = e.returncode
    return (code if code >= 0 else 1), _decode(out), _decode(err)


def _bash():
    """LE BASH DE GIT, PAS CELUI DE WSL. Sous Windows, `bash` nu se résout d'abord
    dans System32 (`bash.exe`, le lanceur WSL) avant le PATH : la vérification
    tournait hors de la machine de l'agent, ou pas du tout, et un constat vrai
    tombait (CI Windows de Claude, 16/10/2026). COPILOT : pas de variable de
    l'hôte pour désigner Git Bash ; `HARNAIS_BASH` peut le forcer."""
    if os.name != "nt":
        return "bash"
    import shutil
    c = [os.environ.get("HARNAIS_BASH")]
    w = shutil.which("bash")
    if w and "system32" not in w.lower():
        c.append(w)
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.environ.get("LOCALAPPDATA") and os.path.join(os.environ["LOCALAPPDATA"], "Programs")):
        if base:
            c.append(os.path.join(base, "Git", "bin", "bash.exe"))
    for x in c:
        if x and os.path.isfile(x):
            return x
    return "bash"


def bash_limite(cmd, secs):
    """`bash -c`, avec une limite de temps. Rend None si le délai est dépassé."""
    r = lancer_limite([_bash(), "-c", cmd], secs)
    if r is None:
        return None
    # Le motif d'un `↻` est cherché dans stdout PUIS stderr recollés : une
    # commande qui parle sur la sortie d'erreur reste jugeable.
    return r[0], r[1] + r[2]


def _motif_rust(motif):
    """LE `$` DE RUST DANS UN MOTIF PYTHON : sans `(?m)`, il ne couvre que la fin
    du texte (`\\Z`), alors que celui de Python couvre aussi la place juste avant
    un saut de ligne final. Mesuré : `^ATTENDU$` sur « ATTENDU\\n\\n » TOMBE côté
    Rust. Un motif qui ouvre lui-même le mode ligne (`(?m)`) garde le sien : les
    deux langages y disent la même chose."""
    import re
    if re.search(r"\(\?[a-zA-Z-]*m", motif):
        return motif
    out = []
    i, n = 0, len(motif)
    classe = False
    while i < n:
        c = motif[i]
        if c == "\\":
            out.append(motif[i:i + 2])
            i += 2
            continue
        if classe:
            if c == "]":
                classe = False
            out.append(c)
        elif c == "[":
            classe = True
            out.append(c)
            i += 1
            if i < n and motif[i] == "^":
                out.append("^")
                i += 1
            if i < n and motif[i] == "]":       # un `]` placé en tête est littéral
                out.append("]")
                i += 1
            continue
        elif c == "$":
            out.append("\\Z")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def rejouer(spec, budget):
    """TIENT · TOMBÉ · MUET — et jamais autre chose.

    MUET est le cœur du dispositif : **un contrôle qui n'aboutit pas ne doit
    JAMAIS se lire comme un constat confirmé.** Ça a servi dès son premier essai
    — des mesures répétées ont déclenché la limitation de débit du site, et le
    contrôle a rendu MUET au lieu d'annoncer quatre routes cassées."""
    if budget <= 0:
        return MUET, "budget de temps épuisé"
    if spec.source == "service" and not sort_de_la_machine(spec.cmd):
        # PAS un refus : un MUET. La commande peut très bien être juste — mais
        # rien dans elle ne sort d'ici, alors qu'elle prétend interroger un
        # service. Le constat part quand même, en le disant.
        return MUET, MSG_MUET_LOCAL
    r = bash_limite(spec.cmd, min(CONSTAT_S, budget))
    if r is None:
        return MUET, "la vérification n'a pas répondu à temps"
    rc, sortie_ = r
    if rc == 127:
        return MUET, "la commande de vérification n'existe pas"
    # Sous Windows une commande finit ses lignes par « \r\n » : `^a\.b$` tombait
    # sur « a.b\r\n », et un constat vrai quittait la liste (CI Windows, 16/10/2026).
    sortie_ = sortie_.replace("\r\n", "\n")
    # LE `$` DE PYTHON N'EST PAS CELUI DE RUST, et l'écart est silencieux :
    # en Python il matche à la fin de la chaîne OU juste avant un saut de ligne
    # final ; en Rust, à la fin seulement. Or une commande rend presque toujours
    # « ATTENDU\n ». Un motif `^ATTENDU$` TENAIT côté Python et TOMBAIT côté
    # Rust — donc, au second tour, un constat vrai quittait la liste du commanditaire.
    # On rejoue donc sans le saut final quand le premier essai échoue (ce qui,
    # en Python, ne change plus rien — mais ce sont les mêmes deux essais).
    import re
    try:
        r2 = re.compile(_motif_rust(spec.motif), re.I | re.S)
    except (re.error, RecursionError, OverflowError):
        trouve = spec.motif.strip() in sortie_
    else:
        trouve = bool(r2.search(sortie_)) or (
            sortie_.endswith("\n") and bool(r2.search(sortie_[:-1])))
    if trouve:
        return TIENT, ""
    return TOMBE, "la vérification dit le contraire"


def une_ligne(s):
    """UN TITRE TIENT SUR UNE LIGNE. Signalé par OPS le 25/09/2026 : une
    question dont la suite du gras commençait EN DÉBUT de ligne gardait son saut
    de ligne — `lisible` ne fond que les blancs d'au moins deux caractères, et un
    saut seul en est un. Le titre partait tel quel ; relu ligne à ligne, il
    devenait deux lignes, et le morceau sans pastille passait pour une demande du
    commanditaire."""
    return _re(r"\s+").sub(" ", s).strip()


def titre_et_corps(brut):
    """Sépare la demande de son explication. Le gras du libellé porte la demande —
    c'est la convention de tous les `todo.md` de l'atelier."""
    import re
    m = re.match(r"\s*\*\*(.+?)\*\*\s*(.*)", brut, re.S)
    if m:
        return une_ligne(lisible(m.group(1))), lisible(m.group(2))
    t = lisible(brut)
    m = re.match(r"(.{15,110}?[.:])\s+(.+)", t, re.S)
    if m:
        return une_ligne(m.group(1).rstrip(".:")), m.group(2)
    if len(t) <= 110:
        return une_ligne(t), ""
    tete = t[:110]
    reste = t[110:]
    coupe = tete.rsplit(" ", 1)[0] if " " in tete else tete
    return une_ligne(coupe) + "…", reste


# ── LE DIALECTE DE `todo.md` ─────────────────────────────────────────────
# Port de `chantiers()` de l'outil de suivi des projets. CE HOOK NE PARSE PAS LE DIALECTE EN
# IMPORTANT UN AUTRE LECTEUR : c'est LE MÊME code, au même endroit, et le
# contrôle différentiel le compare aux lecteurs existants — deux lecteurs du
# même format divergent au premier changement, et c'est la seule chose qui les
# tienne.

class Tache(object):
    __slots__ = ("etat", "titre", "prio", "qui")

    def __init__(self, etat, titre, prio, qui):
        self.etat, self.titre, self.prio, self.qui = etat, titre, prio, qui


def chantiers(texte):
    # Compatibilité : un `pilotage.md` avec un titre « Chantiers » reste lu tel
    # qu'avant, borné à sa section.
    coupe = _re(r"^#{1,3}\s*chantiers\b.*$", "im")
    morceaux = coupe.split(texte)
    if len(morceaux) >= 2:
        source, borne = morceaux[1], True
    else:
        source, borne = texte, False
    tache = _re(r"^\s*[-*]\s*\[( |x|X|>|~)\]\s+(.+?)\s*\Z")
    titre = _re(r"^#{1,3}\s")
    prio = prio_re()
    qui_re = _re(r"(?:^|(?<=\s))@([A-Za-zÀ-ÿ][\w-]*)\b")
    sep = _re(r"\s{2,}")
    out = []
    for ligne in lignes(source):
        if borne and titre.search(ligne):
            break
        m = tache.match(ligne)
        if m is None:
            continue
        libelle = m.group(2)
        p = "moyen"
        mp = prio.search(libelle)
        if mp:
            p = mp.group(1).lower()
            libelle = libelle.replace(mp.group(0), "")
        qui = None
        mq = qui_re.search(libelle)
        if mq:
            qui = mq.group(1).lower()
            libelle = libelle.replace(mq.group(0), "")
        libelle = libelle.replace("**", "").replace("__", "")
        libelle = sep.sub(" ", libelle).strip(" .—-")
        if libelle:
            c = m.group(1)
            etat = "fait" if c in ("x", "X") else ("encours" if c in (">", "~") else "afaire")
            out.append(Tache(etat, libelle, p, qui))
    return out


# ── LE CARNET D'ÉQUIPE ───────────────────────────────────────────────────
# CE HOOK EST L'ÉCRIVAIN DU CARNET, et il n'écrit que ce que l'agent a
# DÉLIBÉRÉMENT marqué : une case cochée qui porte `↗ <qui> : <quoi>`. Une case
# sans `↗` ne produit rien — décider qu'un travail ne concerne personne reste le
# jugement de l'agent, jamais celui de la machine.
#
# POURQUOI LA CASE COCHÉE ET PAS LE COMMIT. Mesuré le 08/09/2026 : 20 à 50
# commits par jour et par agent, contre ~10 cases cochées. Le commit est la
# mauvaise maille — un carnet à cette fréquence serait illisible, donc non lu.

def audience_re():
    return _re(r"^\s*↗\s*(.+?)\s*:\s*(.+?)\s*$", "m")


def vu_re():
    return _re(r"^\s*↩\s*([0-9a-f]{6,12})\s*$", "m")


def issue_et_niveau(bloc):
    """Cocher une case VAUT « abouti » — c'est ce que cocher veut dire, et ça
    ramène le coût d'écriture à une phrase. Déclarer un échec, lui, demande de
    l'écrire : un échec passé pour une réussite est le seul cas qui coûte cher."""
    m = _re(r"(?:^|\s)(abouti|échoué|echoue|échec|en cours)\b", "i").search(bloc)
    if m is None:
        issue = "abouti"
    else:
        v = m.group(1).lower()
        if v.startswith("échou") or v.startswith("echou") or v.startswith("éche") or v.startswith("eche"):
            issue = "échoué"
        elif v.startswith("en "):
            issue = "en cours"
        else:
            issue = "abouti"
    n = _re(r"(?:^|\s)(mesuré|mesure|observé|observe|supposé|suppose)\b", "i").search(bloc)
    if n is not None:
        v = n.group(1).lower()
        if v.startswith("mesur"):
            niveau = "mesuré"
        elif v.startswith("observ"):
            niveau = "observé"
        else:
            niveau = "supposé"
    else:
        niveau = "mesuré" if reouvre_re().search(bloc) else "observé"
    return issue, niveau


def zones_partagees(esp):
    """Les chemins dont le hook sait, SANS demander à l'agent, qu'ils concernent
    les autres. Déclarés dans le projet, jamais en dur : ce fichier est partagé
    par quinze agents. Absent = aucun blocage, et c'est le bon défaut."""
    out = []
    for l in lignes(lis(os.path.join(esp, "ZONES"))):
        l = l.strip()
        if l and not l.startswith("#"):
            out.append(l)
    return out


def libelle_carnet(bloc):
    """Le libellé d'une tâche cochée, lisible par un AUTRE agent. Un carnet
    illisible ne se lit pas : c'est le seul défaut qui annule tout le
    dispositif, puisque personne ne vient signaler qu'il ne lit plus."""
    ls = lignes(bloc)
    tete = _re(r"^\s*[-*]\s*\[(x|X)\]\s+").sub("", ls[0], count=1).strip()
    morceaux = [tete]
    # Un agent BARRE le libellé quand il coche, et la barre se ferme parfois
    # sur la ligne suivante : on continue jusqu'à sa fermeture, jamais au-delà.
    if tete.startswith("~~") and tete.count("~~") < 2:
        for l in ls[1:]:
            s = l.strip()
            if s.startswith("↗") or s.startswith("↻") or s.startswith("↩"):
                break
            morceaux.append(s)
            if "~~" in s:
                break
    t = " ".join(morceaux).replace("~~", "")
    t = prio_re().sub("", t)
    t = arobase_re().sub("", t)
    t = constat_re().sub("", t)
    t = _re(r"\*\*(.+?)\*\*").sub(r"\1", t)
    t = _re(r"\s+").sub(" ", t).strip(" —-–:·")
    if len(t) > 200:
        return t[:200].rstrip() + "…"
    return t


def carnet_tour(agent, todo, esp):
    """Rend `(écrites, issue de la dernière)` — ce que ce tour a versé au carnet."""
    import carnet
    texte = lis(todo)
    cochee = _re(r"^\s*[-*]\s*\[(x|X)\]")
    au = audience_re()
    cochees = [b for b in blocs_lignes(texte) if cochee.search(b) and au.search(b)]
    vus = os.path.join(etat_dir(), slug(agent) + ".carnet")
    premiere = not os.path.exists(vus)
    deja = lignes(lis(vus))
    empreintes = []
    neuves = []
    for b in cochees:
        h = sha16(b.strip())
        if h not in empreintes:
            empreintes.append(h)
        if h not in deja:
            neuves.append((h, b))
    # PREMIÈRE RENCONTRE : on enregistre sans écrire. Un agent qui porte 144
    # cases déjà cochées noierait le carnet à sa naissance et ferait bouger la
    # confiance de rien. Le passif est amnistié.
    if premiere:
        ecrit(vus, "\n".join(sorted(empreintes)))
        return [], None
    ecrites, derniere = [], None
    for _, b in neuves:
        titre = libelle_carnet(b)
        issue, niveau = issue_et_niveau(b)
        pour = [(c.group(1).strip(), c.group(2).strip()) for c in au.finditer(b)]
        m = reouvre_re().search(b)
        rejeu = "%s :: %s :: %s" % (m.group(1), m.group(2), m.group(3)) if m else None
        vs = [c.group(1) for c in vu_re().finditer(b)]
        ident = carnet.ecrire(esp, agent, titre, issue, niveau, pour, rejeu, vs)
        if ident is not None:
            ecrites.append(ident)
            derniere = issue
    if neuves:
        ecrit(vus, "\n".join(sorted(set(empreintes + deja))))
    return ecrites, derniere


def fnmatch(nom, motif):
    """`fnmatch` de Python : `*` traverse les `/`, `?` un caractère, `[…]` un jeu."""
    import re
    p = "^"
    i, n = 0, len(motif)
    while i < n:
        c = motif[i]
        i += 1
        if c == "*":
            p += ".*"
        elif c == "?":
            p += "."
        elif c == "[":
            jeu = ""
            ferme = False
            while i < n:
                d = motif[i]
                i += 1
                if d == "]" and jeu:
                    ferme = True
                    break
                jeu += d
            if not ferme:
                p += re.escape("[") + re.escape(jeu)
            elif jeu.startswith("!"):
                p += "[^%s]" % jeu[1:]
            else:
                p += "[%s]" % jeu
        else:
            p += re.escape(c)
    p += r"\Z"
    try:
        return re.match(p, nom, re.S) is not None
    except (re.error, RecursionError, OverflowError):
        return False


def git_dans(racine, a):
    """Une commande git dans `racine` : sa sortie, ou None si elle échoue."""
    import subprocess
    try:
        o = subprocess.run(["git"] + list(a), cwd=racine, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, ValueError):
        return None
    if o.returncode != 0:
        return None
    return o.stdout.decode("utf-8", "replace")


def tour_carnet(racine, temoin, zones, a_verse):
    """Les fichiers commités DEPUIS LE TOUR PRÉCÉDENT qui tombent dans une zone
    partagée. Le repère est `HEAD` mémorisé au dernier passage : `git status` ne
    voit que le non-commité, et ce qui vient d'être commité lui est invisible —
    c'est justement ce qu'on cherche.

    LE REPÈRE EST PAR AGENT, PAS PAR SESSION. Mesuré au banc le 08/09/2026 :
    rangé par session, il naissait vide à chaque nouvelle session, et le PREMIER
    commit de chaque session échappait donc à la règle — silencieusement.

    IL AVANCE À CHAQUE TOUR, versé ou non. Signalé par PO le 24/09/2026 : il
    n'avançait qu'aux tours SANS entrée. Un tour qui versait au carnet laissait
    donc le repère en arrière, et le premier tour suivant sans entrée
    ressortait des commits déjà versés (PO en compte 24 depuis le 18/09 ; la
    cause de chacune n'est pas vérifiée)."""
    if a_verse:
        t = git_dans(racine, ["rev-parse", "HEAD"])
        if t is not None:
            ecrit(temoin, t.strip())
        return []
    return zone_touchee(racine, temoin, zones)


def zone_touchee(racine, temoin, zones):
    """SEULS COMPTENT LES COMMITS FAITS DANS CET ARBRE. Signalé par PO le
    24/09/2026 : la différence brute entre deux têtes ramassait aussi ce qu'une
    remise à niveau apportait d'un PAIR — son travail, que le pair avait versé
    lui-même. L'auteur ne tranche pas (tous les agents commitent sous la même
    identité) ; le journal de HEAD de l'arbre, si : il dit `commit:` pour ce qui
    a été fait ici, `merge`, `pull` ou `rebase` pour ce qui est arrivé.

    Sans journal lisible, on garde toute la plage : une fausse alerte vaut mieux
    qu'une garde qui se tait."""
    t = git_dans(racine, ["rev-parse", "HEAD"])
    if t is None:
        return []
    tete = t.strip()
    ancien = lis(temoin).strip()
    ecrit(temoin, tete)
    if ancien == "" or ancien == tete:
        return []
    r = git_dans(racine, ["rev-list", "%s..%s" % (ancien, tete)])
    if r is None:
        return []
    plage = [l.strip() for l in lignes(r) if l.strip()]
    journal_ = git_dans(racine, ["reflog", "show", "-n", "2000", "--format=%H %gs", "HEAD"]) or ""
    faits_ici = set()
    for l in lignes(journal_):
        if " " not in l:
            continue
        h, quoi = l.split(" ", 1)
        if quoi.startswith("commit:") or quoi.startswith("commit (amend):") \
                or quoi.startswith("commit (initial):"):
            faits_ici.add(h)
    retenus = plage if not journal_.strip() else [c for c in plage if c in faits_ici]
    touches = []
    for c in retenus:
        d = git_dans(racine, ["diff-tree", "--no-commit-id", "--name-only", "-r", c]) or ""
        for f in (x.strip() for x in lignes(d)):
            if f and any(fnmatch(f, z) for z in zones) and f not in touches:
                touches.append(f)
    return touches


def _composants(p):
    return [c for c in str(p).replace("\\", "/").split("/") if c and c != "."]


def racine_de(ici):
    """`(racine, résolution)` — la racine que la garde regarde. EN ÉQUIPE (Claude
    0.18), l'agent se tient dans `agents/<nom>/` — la MÉMOIRE, qui ignore `code/` —
    et le travail sort dans SA copie du code : c'est elle qu'on regarde, sinon du
    code écrit sans todo passerait sans un mot. Partagée avec le briefing, qui doit
    nommer l'agent exactement comme la garde (registre des questions posées)."""
    import memoire
    racine = memoire.arbre_courant(ici)         # `git rev-parse --show-toplevel`
    if racine is None:
        return None, None
    r0 = memoire.resous(ici)
    if r0.forme == memoire.Forme.Equipe and r0.nom_agent:
        code = os.path.join(r0.mind, "code")
        if os.path.isdir(code):
            racine = memoire._canon(code) or code
    return racine, r0


def registre_posees(agent):
    return os.path.join(etat_dir(), slug(agent) + ".posees")


def questions_ouvertes(texte):
    """Les demandes ouvertes au commanditaire, titrées comme la garde les titre."""
    taches = chantiers(texte)
    bruts = blocs_bruts(texte)
    dests = destinataires()
    # Les deux listes décrivent les mêmes tâches dans le même ordre. Si elles
    # divergent (todo réécrit entre les deux lectures), on se rabat sur le
    # libellé du dialecte : tronqué, mais jamais faux.
    out = []
    for i, t in enumerate(taches):
        if t.qui is None or t.qui not in dests or t.etat != "afaire":
            continue
        if i < len(bruts) and len(bruts) == len(taches):
            titre, corps = titre_et_corps(bruts[i])
        else:
            titre, corps = lisible(t.titre), ""
        out.append(Att(titre, corps, i, False))
    return out


def deja_posees(texte, agent):
    """LES QUESTIONS QUE LE COMMANDITAIRE A DÉJÀ VUES — `[(titre, posée)]`.

    Décision du 14/10/2026 (chez Claude) : « pourquoi tu me poses 4 fois la même
    question ?? » — et « cela arrive à tous les agents, c'est structurel ». La
    garde de fin de tour retenait déjà ce qui avait été posé et ne le redemandait
    jamais ; c'est le BRIEFING, servi avant CHAQUE message (ceux d'un pair
    compris), qui disait « ça passe avant tout le reste dans un point
    d'avancement » : chaque tour déclenché par un pair finissait donc sur la même
    question. Le briefing lit désormais le même registre que la garde."""
    deja = set(lignes(lis(registre_posees(agent))))
    return [(q.titre, sha16(q.titre) in deja) for q in questions_ouvertes(texte)]


def nom_agent(racine):
    """Le nom LISIBLE de l'agent — c'est un titre de liste, pas un slug. Le
    suffixe du journal résout le même cas mais rend `-projet-OPS` : il nomme un
    fichier. Ici on veut « projet OPS », tel que le commanditaire l'a écrit."""
    import memoire
    depart = memoire.depart_defaut()
    # EN ÉQUIPE, l'agent est nommé par sa position (`agents/<nom>/`), d'où qu'il
    # démarre dessous : depuis le fond de sa copie du code, le dernier composant du
    # chemin serait « apps », pas lui. Le briefing et la garde passent ici tous
    # les deux — c'est ce qui fait coïncider leur registre des questions posées.
    r = memoire.resous(depart)
    if r.forme == memoire.Forme.Equipe and r.nom_agent:
        return r.nom_agent
    p = os.path.realpath(depart) if os.path.exists(depart) else depart
    if os.path.exists(racine):
        a, b = _composants(p), _composants(os.path.realpath(racine))
        if os.path.isabs(p) and a[:len(b)] == b:
            rel = a[len(b):]
            if len(rel) == 2 and rel[0] == "agents":
                return rel[1]
            # COPILOT, forme compacte : le harnais se place dans `brain/mind/<nom>`.
            if len(rel) == 3 and rel[0] == "brain" and rel[1] == "mind":
                return rel[2]
    comp = _composants(p)
    return comp[-1] if comp and comp[-1] != ".." else ""


# ── LES DEMANDES DU FIL — `!cible` (11/09/2026) ───────────────────────────
# Ce que le commanditaire tape dans la conversation n'était stocké nulle part : aucune
# garde ne voyait une demande à moitié traitée, et elle disparaissait avec le
# fil. Les Rappels avaient leur canal descendant (B4) ; le fil n'en avait pas,
# et sur le PC il n'y a pas de Rappels du tout. Proposé par un audit, décidé par
# le commanditaire avec ce mot-là.
#
# LE MARQUEUR EST EXPLICITE, et c'est sa contrainte : sans lui, un message reste
# ce qu'il était. L'ENTRÉE (le briefing) écrit la ligne au todo et un témoin par
# AGENT — une cible dure des jours, un témoin de session se remplirait une fois
# pour toutes. LA FIN DE TOUR la rappelle UNE fois si elle n'est pas close, puis
# la laisse vivre dans le todo : une cible que l'agent ne peut pas satisfaire ne
# doit pas le faire tourner à l'infini.
MARQUE_CIBLE = "!cible"
TITRE_CIBLES = "## Demandes du fil"


def texte_cible(prompt):
    """Le texte d'une demande marquée, ou None. Le marqueur OUVRE le message et
    finit un mot : `!ciblex` n'en est pas un, une mention au milieu non plus —
    et un message de pair, qui s'ouvre sur son enveloppe, jamais."""
    s = prompt.lstrip()
    if not s.startswith(MARQUE_CIBLE):
        return None
    reste = s[len(MARQUE_CIBLE):]
    if not (reste == "" or reste[0].isspace() or reste[0] == ":"):
        return None
    s = reste.lstrip(":").strip()
    return s if s else None


def repere_cible(h):
    """Le repère qu'on retrouve dans le todo : court, et stable pour un texte."""
    return "cible %s" % h[:6]


def ligne_cible(texte, h, jour):
    """La ligne du todo : la première ligne en titre, le reste en corps.

    `@` devient `＠` : une demande qui citerait `@user` ne doit pas devenir, par
    accident, une question que le commanditaire se poserait à lui-même."""
    net = texte.replace("@", "＠").replace("**", "")
    l = [x for x in (y.strip() for y in lignes(net)) if x]
    titre = l[0][:160] if l else ""
    out = "- [ ] **%s** — demandé par l'humain dans le fil, le %s · %s" % (titre, jour, repere_cible(h))
    for c in l[1:]:
        out += "\n      %s" % c
    return out


def insere_cible(t, ligne):
    """Pose la ligne sous « Demandes du fil », la plus récente en tête. Sans cette
    section, elle est créée AVANT la première section : c'est le haut du todo
    que l'agent relit."""
    l = lignes(t)
    i = next((k for k, x in enumerate(l) if x.rstrip() == TITRE_CIBLES), None)
    if i is not None:
        j = i + 1
        while j < len(l) and not l[j].strip():
            j += 1
        out = l[:i + 1] + ["", ligne, ""] + l[j:]
    else:
        i = next((k for k, x in enumerate(l) if x.startswith("## ")), None)
        if i is not None:
            out = l[:i] + [TITRE_CIBLES, "", ligne, ""] + l[i:]
        else:
            out = list(l)
            if out and out[-1].strip():
                out.append("")
            out += [TITRE_CIBLES, "", ligne]
    s = "\n".join(out)
    while s.endswith("\n\n"):
        s = s[:-1]
    if not s.endswith("\n"):
        s += "\n"
    return s


def racine_git(ici):
    r = git_dans(ici, ["rev-parse", "--show-toplevel"])
    if r is None:
        return None
    import memoire
    return memoire.natif(r.strip())


def inscrire_cible(prompt):
    """L'ENTRÉE : appelée par le briefing sur chaque message du commanditaire. Rend ce
    qu'il faut dire à l'agent, ou None si le message n'est pas marqué ou si le
    projet n'a pas de todo."""
    import memoire
    texte = texte_cible(prompt)
    if texte is None:
        return None
    ici = memoire.depart_defaut()
    racine = racine_git(ici)
    if racine is None:
        return None
    mind = memoire.resous(ici).mind
    if mind is None:
        return None
    todo = os.path.join(mind, "todo.md")
    if not os.path.exists(todo):
        return None
    agent = nom_agent(racine)
    h = sha16(texte)
    f = os.path.join(etat_dir(), slug(agent) + ".cibles")
    if not any(l.startswith(h) for l in lignes(lis(f))):
        jour = maintenant("%d/%m/%Y")
        neuf = insere_cible(lis(todo), ligne_cible(texte, h, jour))
        tmp = todo[:-3] + ".md.cible" if todo.endswith(".md") else todo + ".cible"
        try:
            with open(tmp, "w", encoding="utf-8", newline="") as o:
                o.write(neuf)
            os.replace(tmp, todo)
        except OSError:
            return None
        court = (lignes(texte)[0] if lignes(texte) else "").replace("\t", " ")[:80]
        mkdirs(etat_dir())
        t = lis(f)
        t += "%s\t%s\touverte\t%s\n" % (h, maintenant("%Y-%m-%d"), court)
        ecrit(f, t)
    return MSG_CIBLE.format(ou_ecrire(racine, todo), repere_cible(h))


def cibles_a_rappeler(f, todo_txt):
    """LA FIN DE TOUR : les cibles ouvertes qui n'ont pas encore été rappelées.
    Rend `(repère, état, texte court)` et note qu'elles l'ont été — une seule
    fois par cible. Une ligne cochée ferme la cible sans bruit."""
    t = lis(f)
    a_rappeler = []
    out = []
    todo_l = lignes(todo_txt)
    for l in lignes(t):
        c = l.split("\t", 3)
        if len(c) < 4 or c[2] != "ouverte":
            out.append(l)
            continue
        rep = repere_cible(c[0])
        ligne = next((x for x in todo_l if rep in x), None)
        if ligne is not None and (ligne.lstrip().startswith("- [x]") or ligne.lstrip().startswith("- [X]")):
            etat = "faite"
        elif ligne is not None:
            a_rappeler.append((rep, "ouverte", c[3]))
            etat = "rappelee"
        else:
            a_rappeler.append((rep, "disparue", c[3]))
            etat = "rappelee"
        out.append("%s\t%s\t%s\t%s" % (c[0], c[1], etat, c[3]))
    if "\n".join(out).strip() != t.strip():
        ecrit(f, "\n".join(out) + "\n")
    return a_rappeler


class Att(object):
    __slots__ = ("titre", "corps", "i", "tombe")

    def __init__(self, titre, corps, i, tombe):
        self.titre, self.corps, self.i, self.tombe = titre, corps, i, tombe


NOTION_MAX = 3


def lien_notion(texte):
    """Une ligne de la base Notion : l'adresse et l'identifiant de 32 caractères
    de la page. « notion.so » seul, ou « voir Notion », ne suffisent pas."""
    return _re(r"notion\.(?:so|site|com)/\S*?[0-9a-f]{32}", "i").search(texte) is not None


MARQUE_RENVOI = "@user a DÉJÀ lu ton message"


def lecture_du_tour(data):
    """LE JOURNAL DE SESSION DE COPILOT CLI (`events.jsonl`) : un événement par
    ligne, le texte dans `data.content`. On n'en lit que la fin — ces journaux
    font des dizaines de Mo. Rend le texte écrit par l'agent depuis le dernier
    message de l'utilisateur, et si ce message était un renvoi du harnais.

    UN RENVOI N'OUVRE PAS UN NOUVEAU TOUR : remettre à zéro dessus faisait
    oublier ce que l'agent venait de poser — et le forçait à tout recopier."""
    import json
    chemin = data.get("transcript_path")
    if not isinstance(chemin, str) or not chemin:
        return "", False
    try:
        with open(chemin, "rb") as f:
            taille = os.fstat(f.fileno()).st_size
            f.seek(max(0, taille - 3000000))
            brut = f.read()
    except (OSError, ValueError):
        return "", False
    morceaux = []
    renvoi = False
    for l in lignes(brut.decode("utf-8", "replace")):
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        d = e.get("data")
        contenu = d.get("content") if isinstance(d, dict) else None
        contenu = contenu if isinstance(contenu, str) else ""
        ty = e.get("type")
        if ty == "assistant.message":
            if contenu.strip():
                morceaux.append(contenu)
        elif ty == "user.message":
            renvoi = MARQUE_RENVOI in contenu
            if not renvoi:
                morceaux = []
    return "\n".join(morceaux), renvoi


def dernier_message(data):
    """Le texte que l'agent a écrit depuis le dernier message de l'utilisateur —
    ce qu'il s'apprête à rendre. Illisible → vide, et la garde demande."""
    return lecture_du_tour(data)[0]


def repart_sur_un_renvoi(data):
    """L'agent repart-il sur un renvoi de fin de tour ? Copilot ne le dit pas dans
    la charge : le renvoi revient au journal comme un message de l'utilisateur,
    reconnaissable à son pied, que chaque renvoi porte."""
    return lecture_du_tour(data)[1]


def mots_porteurs(s):
    """Les mots qui portent une question : quatre lettres et plus, en minuscules."""
    mots, cur = [], []
    for c in s.lower():
        if c.isalnum():
            cur.append(c)
        else:
            if len(cur) >= 4:
                mots.append("".join(cur))
            cur = []
    if len(cur) >= 4:
        mots.append("".join(cur))
    return mots


# LE COMMANDITAIRE N'A PAS DE TERMINAL (12/10/2026, dit par lui : il travaille à 95 % depuis
# l'app Claude, à distance). Une ligne qui commence par « ! » — le préfixe qui lance
# une commande dans la session — lui est donc inutile : il ne peut que répondre,
# approuver une demande de permission ou changer de mode. La ligne du socle ne
# suffisait pas (« une ligne dans le CLAUDE.md n'est suivie qu'une partie du
# temps ») : la règle se tient ICI, au moment où le message part.
COMMANDE_A_TAPER = _re(r"(?m)^[ \t>]*!\s+\S|`!\s+\S")


def commandes_a_taper(message):
    """Les lignes du message qui demandent au commanditaire de taper une commande avec `!` :
    une ligne ou un bloc de code qui COMMENCE par « ! », ou un code en ligne
    (« `! python3 … ` »). « `!` compris » ou « Super ! » n'en sont pas."""
    out = []
    for l in lignes(message or ""):
        if COMMANDE_A_TAPER.search(l):
            out.append(l.strip()[:90])
    return out


def posee(message, titre):
    """LA QUESTION EST-ELLE POSÉE dans ce message ? L'agent la reformule souvent
    pour le commanditaire, donc pas d'égalité de texte : au moins 60 % des mots porteurs
    du titre doivent s'y trouver. Un titre sans mot porteur ne se juge pas —
    on le tient pour posé plutôt que de relancer sur du vide."""
    mots = mots_porteurs(titre)
    if not mots:
        return True
    dans = set(mots_porteurs(message))
    trouves = sum(1 for w in mots if w in dans)
    return trouves * 10 >= len(mots) * 6


def lignes_temoin(p):
    return lis(p).split()


def ou_ecrire(racine, todo):
    """OÙ L'AGENT DOIT ÉCRIRE, tel qu'on le lui DIT — le chemin résolu, jamais un
    littéral. Relatif au dépôt quand le fichier y vit ; ABSOLU sinon, ce qui est
    le cas d'une mémoire déportée. Séparateurs en `/` : c'est la convention de
    l'atelier.

    Cette fonction existe pour être ÉPROUVÉE. Les messages la contournaient en
    écrivant `.mind/todo.md` en dur ; le défaut n'était visible d'aucun contrôle
    parce que les cas construits n'étaient jamais dans la forme `brain/`."""
    return socle.chemin_affiche(racine, todo)


def mtime(p):
    try:
        return os.path.getmtime(p)
    except OSError:
        return 0.0


def lance_relecture():
    """(c) LE DÉCLENCHEUR. Détaché, sans entrée ni sortie : son seul produit est
    un fichier, lu au tour suivant. Ce n'est pas une tâche longue qu'on perdrait
    de vue — le juge porte son propre verrou et son plafond journalier, et un
    ouvrier tué laisse sa demande en place, donc rejouée. Aucun tour n'attend
    après lui.

    L'INTERRUPTEUR DES CONTRÔLES, ET IL EST NOMMÉ POUR CE QU'IL EST. Sans lui,
    chaque passage de la suite différentielle lancerait une douzaine de vrais
    juges — du temps, de l'argent, et le plafond journalier consommé par des bacs
    à sable. En simulation le verdict rendu porte le mot « simulation » et part
    au journal : un interrupteur laissé par mégarde se voit.
    « aucun » : on dépose et on ne lance rien — le seul moyen d'inspecter ce qui
    est déposé, puisque le juge le consomme aussitôt."""
    simulee = os.environ.get("HARNAIS_RELECTURE_SIMULEE")
    if simulee == "aucun":
        return
    import subprocess
    argv = [sys.executable, "-S", "-E"]
    if getattr(sys, "pycache_prefix", None):
        argv += ["-X", "pycache_prefix=%s" % sys.pycache_prefix]
    argv += [os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"), "relecture"]
    if simulee is not None:
        argv.append("--sec")
    opts = {}
    if os.name == "nt":
        # Pas de `start_new_session` sous Windows : DETACHED_PROCESS (0x8) +
        # CREATE_NEW_PROCESS_GROUP (0x200), pour que le juge survive au hook.
        opts["creationflags"] = 0x00000008 | 0x00000200
    else:
        opts["start_new_session"] = True
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True, **opts)
    except (OSError, ValueError):
        pass


def socle_profil_expert():
    import socle
    return socle.profil_expert()


def main(entree):
    _DEBUT[0] = time.monotonic()
    import json
    try:
        data = json.loads(entree, parse_constant=_refuse_constante)
    except Exception:
        sortie(0)
    if not isinstance(data, dict):
        data = {}               # `Value::get` d'un non-objet : toujours rien
    # Un sous-agent a son propre événement et n'a pas à déclarer l'attente de
    # son parent.
    if "agent_type" in data or "agent_id" in data:
        sortie(0)
    # UNE SESSION DU JUGE N'EST PAS L'AGENT. Lancée dans son dossier, elle en a
    # tous les droits, et ce hook la traitait comme lui : il renvoyait une sonde
    # au travail, qui réécrivait le todo. Le relecteur pose HARNAIS_JUGE.
    if "HARNAIS_JUGE" in os.environ:
        sortie(0)
    import memoire
    ici = memoire.depart_defaut()
    racine, _r0 = racine_de(ici)
    if racine is None:
        sortie(0)                               # pas un dépôt : rien à dire

    # `(lot, projet)` ne servent qu'à lire `git status` et à composer le chemin
    # de repli : on ne paie la question (et l'import) que si l'on en a besoin.
    _c = []

    def contexte():
        if not _c:
            import mind_guard
            _c.append(mind_guard.contexte_defaut(ici))
        return _c[0]

    # LA MÉMOIRE PEUT ÊTRE DÉPORTÉE (08/09/2026) : hors du dépôt de code, pour
    # n'exister qu'une fois quand plusieurs agents travaillent sur plusieurs
    # copies. Chercher sous `racine/lot/` ne trouverait alors rien — et ce hook
    # étant fail-open, il se tairait.
    # La résolution, une fois, nommée. Le résolveur rend TOUJOURS ce chemin quand
    # il y a un dépôt ; le repli ne sert que hors dépôt.
    res = memoire.resous(ici)
    d_mind, d_fact = res.mind, res.fact
    if d_mind is not None:
        todo = os.path.join(d_mind, "todo.md")
    else:
        todo = os.path.join(racine, contexte()[0], ".mind", "todo.md")
    if not os.path.exists(todo):
        sortie(0)                               # projet hors harnais

    # LE CHEMIN QU'ON NOMME EST CELUI QU'ON A RÉSOLU. Huit messages de ce module
    # écrivaient le chemin en dur, quelle que soit la forme du projet — alors que
    # le chemin était résolu plus haut et servait déjà à lire le fichier.
    #
    # DÉFAUT MESURÉ le 10/09/2026 par l'audit, et observé en session réelle :
    # sur un projet en `brain/`, un agent renvoyé au travail par ce garde a
    # suivi le chemin annoncé, s'est heurté à un refus d'écriture, et a rendu
    # la main sans rien noter. Le tour perdu — et ce qui devait remonter au
    # commanditaire perdu avec lui, en silence. Un garde qui mord avec la
    # mauvaise phrase apprend le mauvais geste.
    # En équipe, nommé depuis le dossier de l'agent (où il se tient), pas depuis
    # sa copie du code.
    ou_todo = ou_ecrire(_r0.mind if (_r0.forme == memoire.Forme.Equipe and _r0.nom_agent) else racine, todo)
    ed = etat_dir()

    # --- 1. bloquer si du travail est sorti sans être noté ------------------
    st = git_dans(racine, ["status", "--porcelain"]) or ""
    code = []
    for l in lignes(st):
        f = l[3:].strip().strip('"')
        if f:
            import mind_guard
            lot, projet = contexte()[0], contexte()[1]
            if mind_guard.est_du_code(f, lot, projet):
                p = os.path.join(racine, f)
                if os.path.exists(p):
                    code.append(p)
    mkdirs(ed)
    # UN SEUL RENVOI DE FORME PAR FIN DE TOUR. Quand l'agent repart déjà sur un
    # renvoi de fin de tour — Copilot ne le dit pas dans la charge : on le lit au
    # journal de session, au pied que porte chaque renvoi — les gardes de FORME
    # (B8, B10, B13) ne renvoient plus : enchaînées, elles faisaient réécrire
    # plusieurs fois la même conclusion. Les gardes d'ÉTAT (todo, carnet, faits)
    # renvoient toujours : elles se satisfont en travaillant, pas en réécrivant.
    # Copilot arrête l'agent après HUIT blocages consécutifs : chaque garde est
    # aussi bornée par un témoin de l'état qui l'a déclenchée.
    deja_renvoye = repart_sur_un_renvoi(data)
    # L'ACCUEIL DU CTO N'EST PAS UN PROJET EN COURS. Tant que son registre est
    # vide, ses questions sont du cadrage (« nouveau ou existant ? ») : exiger
    # conséquences, critère « fini quand » et relecture des rechutes n'y produit
    # que des messages bureaucratiques. Les gardes de FORME s'y taisent, comme
    # après un renvoi ; les gardes d'ÉTAT restent armées.
    import atelier
    try:
        accueil = atelier.accueil(racine) is not None
    except atelier.RegistreInvalide:
        accueil = False
    forme_muette = deja_renvoye or accueil
    # LE CANAL NOTION (30/09/2026, décision du commanditaire : plus de notes
    # d'équipe dans ses rappels, tout passe désormais par Notion). Posé par projet, dans les
    # réglages des agents : `HARNAIS_CANAL=notion`. Alors plus rien ne part vers
    # les Rappels ni n'en est lu, et chaque question pour le commanditaire doit
    # porter le lien de sa ligne dans la base Décisions (garde B14).
    notion = os.environ.get("HARNAIS_CANAL", "").strip() == "notion"
    sid = data.get("session_id")
    session = "".join(c for c in (sid if isinstance(sid, str) else "x")
                      if (c.isascii() and c.isalnum()) or c == "_" or c == "-")[:64]
    # LE NOM DE L'AGENT EST RÉSOLU ICI, avant le premier blocage : il l'était
    # plus bas, ce qui rendait le premier blocage anonyme dans le journal.
    agent = nom_agent(racine)
    _CTX[0] = (agent, session, racine)
    purge_temoins(7)

    if code:
        recent = max(mtime(p) for p in code)
        if mtime(todo) < recent:
            # Signature de l'ÉTAT, pas du tour : c'est elle qui borne la boucle.
            sig = sha16("%.0f|%d" % (recent, len(code)))
            temoin = os.path.join(ed, session + ".bloc")
            if lis(temoin).strip() != sig:
                ecrit(temoin, sig)
                noms = [os.path.basename(p.rstrip("/\\")) for p in code[:4]]
                ech = ", ".join(noms) + (", …" if len(code) > 4 else "")
                sortie(2, MSG_B1.format(ech, ou_todo=ou_todo), "B1-code-sans-todo", str(len(code)))

    # --- 1 ter ter. CE QU'IL T'A DEMANDÉ DANS LE FIL — `!cible` -------------
    # La même garde que la précédente, seconde source : la conversation. Elle ne
    # dépend pas des Rappels, donc elle tient aussi là où ils n'existent pas.
    f = os.path.join(ed, slug(agent) + ".cibles")
    r = cibles_a_rappeler(f, lis(todo)) if active("B4-cible") else []
    if r:
        liste = "\n".join(
            ("  ✗ « %s » (%s) — retirée du todo SANS être cochée" % (court, rep)) if etat == "disparue"
            else ("  → « %s » (%s) — encore ouverte" % (court, rep))
            for rep, etat, court in r)
        sortie(2, MSG_B4.format(len(r), liste, ou_todo=ou_todo), "B4-cible", str(len(r)))

    # --- 1 quater. LE CARNET D'ÉQUIPE --------------------------------------
    import carnet
    esp = carnet.espace(racine, False)
    # INITIALISÉES AVANT LA BRANCHE, et c'est le point : un seul projet de
    # l'atelier a un espace d'équipe, et pour les autres tout ce qui lirait
    # `ecrites` plus bas tomberait — en SILENCE, puisque le hook est fail-open.
    ecrites = []
    if esp is not None:
        ecrites, issue = carnet_tour(agent, todo, esp)
        # LE MÉCANISME DE SENSE-LAB, à l'identique : ce que l'agent avait LU
        # voit sa confiance bouger quand il déclare son issue — sans qu'il
        # désigne quoi que ce soit. Un échec grave coûte cinq réussites.
        if issue is not None:
            import nature
            lus = carnet.lu(esp, agent, session)
            carnet.bouge(esp, lus, nature.ECHEC_DECLARE if issue == "échoué" else nature.REUSSITE, True)
        # LE BLOCAGE. On ne demande pas à l'agent de juger si son travail
        # concerne les autres — on le lit du chemin qu'il a touché.
        zones = zones_partagees(esp)
        if zones:
            repere = os.path.join(ed, slug(agent) + ".tete")
            touches = tour_carnet(racine, repere, zones, bool(ecrites))
            if touches:
                sig = sha16("carnet|" + "|".join(sorted(touches)))
                temoin = os.path.join(ed, session + ".equipe")
                if lis(temoin).strip() != sig:
                    ecrit(temoin, sig)
                    touches = touches[:4]
                    sortie(2, MSG_B5.format(", ".join(touches), ou_todo=ou_todo),
                           "B5-carnet", str(len(touches)))

    # --- 1 quinquies. LA MÉMOIRE DÉPORTÉE S'ENREGISTRE TOUTE SEULE ---------
    # Sans ce bloc elle n'aurait AUCUN historique — on aurait échangé la
    # duplication contre l'amnésie, ce qui est pire.
    #
    # `.fact/` EN EST EXCLU, ET C'EST LE POINT DÉLICAT : déportée, la mémoire
    # partagée ne passe plus par le garde de commit, qui serait devenu inerte en
    # silence. Le garde vient donc ici.
    #
    # DEPUIS LE 09/10/2026 : aussi un `brain/` doté de son propre dépôt — rien
    # ne l'enregistrait, alors que c'est la forme cible. Et, là où le projet l'a
    # demandé (`HARNAIS_SYNCHRO=git`), la mémoire s'intègre et s'envoie ensuite :
    # deux personnes, deux machines, un seul souvenir.
    #
    # UN EXPERT ÉCRIT SES FAITS LUI-MÊME (12/10/2026) : c'est ce que le commanditaire lui
    # demande, et ce que la garde B16 exige. Ils s'enregistrent donc avec le
    # reste, et B6 se tait — elle s'opposerait à B16 sur la même écriture. Le
    # registre local, lui, ne s'enregistre jamais.
    expert = socle_profil_expert()
    if d_mind is not None:
        import synchro
        b = synchro.depot(res)
        if b is not None:
            if expert:
                # Le registre local est à côté des faits : `local/` dans un dépôt de
                # mémoire, `brain/local/` dans le dépôt entier (`git-depot`).
                pf = res.prefixe_fact or ""
                base_brain = pf[:-len("fact/")] if pf.endswith("fact/") else ""
                faits_touches = synchro.enregistre(b, agent, "", exclus=(base_brain + "local/",))
            else:
                faits_touches = synchro.enregistre(b, agent, res.prefixe_fact)
            if synchro.active():
                bil = synchro.fin_de_tour(b)
                rv = synchro.renvoi(b, bil)
                if rv is not None:
                    cle, msg = rv
                    sig = sha16("synchro|" + cle)
                    temoin = os.path.join(ed, session + ".synchro")
                    if lis(temoin).strip() != sig:
                        ecrit(temoin, sig)
                        sortie(2, msg, "B15-synchro", str(bil.en_retard))
            if faits_touches:
                sig = sha16("fact|" + "|".join(sorted(faits_touches)))
                temoin = os.path.join(ed, session + ".faits")
                if lis(temoin).strip() != sig:
                    ecrit(temoin, sig)
                    ech = faits_touches[:4]
                    sortie(2, MSG_B6.format(", ".join(ech)), "B6-faits", str(len(faits_touches)))

    # --- 1 sexies. B16 — LES FAITS QUE LE COMMANDITAIRE DONNE À UN EXPERT -------------
    # Garde d'ÉTAT : elle renvoie même après un premier renvoi de ce tour (le
    # juge relit, c'est ce qui prouve que l'agent a vraiment noté), une fois par
    # état. Voir `experts.py`.
    if expert and d_fact is not None:
        import experts
        v = experts.garde(data, d_fact, ed, session,
                          lambda p: ou_ecrire(racine, p))
        if v is not None:
            texte, quoi, detail = v
            if quoi == "B16-muet":
                journal(quoi, detail)
            else:
                sortie(2, texte, quoi, detail)

    # --- 2. composer ce qui attend @user ----------------------------------
    # Mesuré : trop pour être payé à chaque tour, d'où la garde sur la date du
    # todo.
    empreinte = "%.0f" % mtime(todo)
    dernier = os.path.join(ed, slug(agent) + ".pousse")
    if lis(dernier).strip() == empreinte:
        sortie(0)

    texte = lis(todo)
    taches = chantiers(texte)
    attente = questions_ouvertes(texte)

    # --- 2 bis. LES CONSTATS : rouvrir avant de servir ----------------------
    # Ici et nulle part ailleurs. Le bon instant est celui où le constat ATTEINT
    # le commanditaire — c'est rare, et c'est exactement le moment qui a échoué.
    specs = specs_constat(texte)

    def spec_de(i):
        return specs[i] if i < len(specs) else None

    manquants = [t for t in attente if spec_de(t.i) is not None and spec_de(t.i).sans]
    if active("B7-constat-sans-rejeu") and manquants:
        sig = sha16("constat|%s|%d" % (empreinte, len(manquants)))
        temoin = os.path.join(ed, session + ".constat")
        if lis(temoin).strip() != sig:
            ecrit(temoin, sig)
            ech = ", ".join(t.titre[:40] for t in manquants[:3])
            sortie(2, MSG_B7.format(len(manquants), ech), "B7-constat-sans-rejeu", str(len(manquants)))

    # UN SEUL CONTRÔLE EN ÉCHEC NE SUFFIT PLUS À SORTIR UNE LIGNE DE SA VUE.
    # Une vérification se trompe : réseau lent, jeton expiré, débit limité. Le
    # premier échec annote et garde ; le second, CONSÉCUTIF, retire. Un TIENT ou
    # un MUET remet le compteur à zéro — « consécutif » veut dire consécutif.
    ftombes = os.path.join(ed, slug(agent) + ".tombes")
    tombes_vus = lignes_temoin(ftombes)
    tombes_apres = list(tombes_vus)
    tombes = []
    restant = min(CONSTAT_BUDGET, reste_s() - 10.0)
    jour = maintenant("%d/%m")
    # B9 DÉSARMÉE (Copilot) : les constats ne sont même pas rejoués.
    indices = [n for n, x in enumerate(attente)
               if spec_de(x.i) is not None and not spec_de(x.i).sans
               and active("B9-tombe")][:CONSTAT_MAX]
    for n in indices:
        import nature
        t0 = time.monotonic()
        verdict, raison = rejouer(spec_de(attente[n].i), restant)
        restant -= time.monotonic() - t0
        h = sha12(attente[n].titre)
        if verdict == TIENT:
            attente[n].corps += " · reconfirmé le %s" % jour
            tombes_apres = [x for x in tombes_apres if x != h]
            # UN CONSTAT QUI TIENT EST UN RÉSULTAT, et le meilleur qu'on ait :
            # une commande vient de confirmer une affirmation.
            resultat(nature.REUSSITE)
        elif verdict == MUET:
            # JAMAIS lu comme une confirmation : le constat part quand même.
            attente[n].corps += " · le %s, %s" % (jour, raison)
            tombes_apres = [x for x in tombes_apres if x != h]
        elif h in tombes_vus:
            attente[n].tombe = True                 # deuxième échec de suite
            tombes.append(attente[n].titre)
            tombes_apres = [x for x in tombes_apres if x != h]
            # DEUX ÉCHECS CONSÉCUTIFS : c'est le vrai démenti, pas le premier.
            resultat(nature.DEMENTI)
        else:
            attente[n].corps += " · le %s, sa vérification a échoué une première fois" % jour
            if h not in tombes_apres:
                tombes_apres.append(h)

    # ── LE CARNET AUSSI A DES `↻`, ET PERSONNE NE LES REJOUAIT ─────────────
    # `replancher` porte l'effondrement et la restauration au plancher de
    # niveau. Le code existait depuis le début SANS AUCUN APPELANT : la
    # confiance ne pouvait que s'éroder, jamais se refaire par une mesure —
    # exactement l'inverse de ce que sa description promet.
    if esp is not None:
        if restant > 0.0:
            conf = carnet.confiances(esp)
            auj = maintenant("%Y-%m-%d")

            def _vu(i):
                v = conf.get(i)
                return v.get("vu") if isinstance(v, dict) else None

            candidats = [x for x in carnet.entrees(esp, None)
                         if x.rejeu is not None and x.id in conf and _vu(x.id) != auj][:CARNET_MAX]
            for c in candidats:
                if restant <= 0.0:
                    break
                s, cmd, motif = c.rejeu
                t0 = time.monotonic()
                v, _ = rejouer(Spec(s, cmd, motif, False), restant)
                restant -= time.monotonic() - t0
                carnet.replancher(esp, c.id, v)

    # ── LA CIBLE DU PROJET, REJOUÉE ICI ET SERVIE PAR LE BRIEFING ──────────
    # Le capteur et les actionneurs existaient ; la CONSIGNE manquait. Rejouée
    # ici parce que le budget de temps est déjà là et que le briefing tient en
    # 15 s : y lancer une commande réseau ferait tomber le démarrage.
    # Pas de faits = pas de consigne, et c'est une RÉPONSE. Le chemin composé
    # ici ne sert qu'à ce que la lecture échoue proprement au lieu de sauter
    # le bloc : un projet sans cible et un projet dont la cible n'a pas été
    # lue doivent se distinguer dans la sortie.
    d_f = d_fact if d_fact is not None else os.path.join(racine, contexte()[0], ".fact")
    phrase, specs_cible = consigne(d_f) if active("B11-acharnement") else (None, [])
    if phrase is not None:
        f_cible = os.path.join(ed, slug(agent) + ".cible")
        # UNE CIBLE SANS MESURE N'EST PAS UNE CIBLE NON MESURÉE. Les deux
        # rendraient MUET et se liraient pareil, alors qu'ils appellent des
        # gestes opposés : l'un dit « répare ta vérification », l'autre
        # « personne n'en a encore écrit », qui est le premier travail à faire.
        verdict = "SANS" if not specs_cible else MUET
        for sp in specs_cible[:2]:
            if restant <= 0.0:
                break
            t0 = time.monotonic()
            v, _ = rejouer(sp, restant)
            restant -= time.monotonic() - t0
            # LE PIRE VERDICT GAGNE. Deux mesures dont une tombe, ce n'est pas
            # « à moitié tenu » : c'est tombé.
            if verdict == TOMBE or v == TOMBE:
                verdict = TOMBE
            elif verdict == MUET:
                verdict = v
        # LA NON-PROGRESSION SE COMPTE SUR LA MESURE, PAS SUR LES TOURS : ce
        # bloc ne tourne que quand le travail a bougé. Il repart à zéro dès que
        # le verdict change — ou que la cible elle-même change, sinon une cible
        # neuve hériterait de l'acharnement de l'ancienne.
        anc = lis(f_cible)
        ch = anc.split("\t")
        avant_v = ch[0]
        if len(ch) > 3 and ch[2] != "" and all(c in "0123456789" for c in ch[2]):
            avant_n = _i64(ch[2], 1)
        elif anc == "":
            avant_n = 0
        else:
            avant_n = 1
        avant_p = "" if anc == "" else ch[-1]
        suite = avant_n + 1 if (verdict == avant_v and phrase == avant_p) else 1
        ecrit(f_cible, "%s\t%s\t%d\t%s" % (verdict, jour, suite, phrase))

        # ON NE BLOQUE QUE SUR TOMBÉ, et jamais sur MUET ni sur SANS : une
        # vérification qui n'aboutit pas ne prouve pas qu'on s'acharne, elle
        # prouve qu'on ne sait pas.
        if verdict == TOMBE and suite >= CIBLE_ACHARNEMENT and suite % CIBLE_ACHARNEMENT == 0:
            sortie(2, MSG_B11.format(suite, phrase[:150], CIBLE_ACHARNEMENT, ou_todo=ou_todo),
                   "B11-acharnement", str(suite))

    # LE CONSTAT TOMBÉ N'EST PLUS PRÉSENTÉ — ET RESTE DANS LE TODO DE L'AGENT.
    # AUCUN verdict de machine ne détruit quoi que ce soit : une vérification
    # qui se trompe effacerait un vrai blocage en silence, et un contrôle dont
    # l'échec ressemble au succès est précisément la panne qu'on traque.
    attente = [t for t in attente if not t.tombe]
    ecrit(ftombes, "\n".join(sorted(set(tombes_apres))))

    # --- 2 ter. LA FORME : une question, jamais un constat ------------------
    # Le hook connaît la forme mieux qu'un texte de socle : il lit ces lignes à
    # chaque fin de tour, il sait donc les refuser AU MOMENT où elles sont
    # écrites, à UN agent. Une règle écrite est un conseil ; une règle ici est
    # appliquée. IL NE JUGE QUE LA FORME, jamais la qualité.
    empreintes = [sha12(t.titre) for t in attente]
    vus_f = os.path.join(ed, slug(agent) + ".forme")
    if not os.path.exists(vus_f):
        # PREMIÈRE RENCONTRE : on enregistre l'arriéré SANS bloquer. Reprendre
        # 73 lignes anciennes n'est pas le travail du tour en cours, et un
        # garde-fou qui bloque tout le monde le premier jour est un garde-fou
        # qu'on finit par désarmer.
        ecrit(vus_f, "\n".join(sorted(set(empreintes))))
    else:
        # ANCIEN FORMAT : une empreinte nue vaut « déjà avertie », donc épuisée
        # — l'arriéré garde le comportement d'hier.
        deja = {}
        for l in lis(vus_f).split("\n"):
            m = l.split()
            if m:
                n = _i64(m[1], RAPPELS_FORME) if len(m) > 1 else RAPPELS_FORME
                deja.pop(m[0], None)
                deja[m[0]] = n
        fr, rp = fini_re(), reponse_re()

        def bien(t):
            sans_fini = fr.sub("", t.corps)       # la fin ne se compte pas
            return ("?" in t.titre and len(rp.findall(sans_fini)) >= 2
                    and fr.search(t.corps) is not None)

        mauvais = [t for t in attente
                   if not bien(t) and deja.get(sha12(t.titre), 0) < RAPPELS_FORME]
        # Une ligne CORRIGÉE est classée : on ne la recomptera jamais. Une ligne
        # encore mauvaise voit son compteur monter — et rien d'autre ne bouge.
        h_mauvais = [sha12(t.titre) for t in mauvais]
        n_mauvais = len(mauvais)
        ech = ", ".join("« %s »" % t.titre[:50] for t in mauvais[:3]) + (", …" if n_mauvais > 3 else "")
        for t in attente:
            h = sha12(t.titre)
            if bien(t):
                v = RAPPELS_FORME
            elif h in h_mauvais:
                v = deja.get(h, 0) + 1
            else:
                v = None
            if v is not None:
                deja[h] = v
        ecrit(vus_f, "\n".join("%s %d" % (h, n) for h, n in sorted(deja.items(), key=lambda a: a[0])))
        if active("B8-forme") and n_mauvais > 0 and not forme_muette:
            sortie(2, MSG_B8.format(n_mauvais, ech), "B8-forme", str(n_mauvais))

    # --- 2 quater. LA LISTE DE CONTRÔLE, JOUÉE AVANT D'AFFIRMER -------------
    # ICI ET PAS AILLEURS : c'est le dernier point où le tour est encore
    # rattrapable — les constats viennent d'être rejoués, la forme d'être
    # jugée, et rien n'est encore parti vers le téléphone.
    #
    # ELLE NE MORD QUE SUR CE QUI COÛTE UNE DÉCISION. Le travail ordinaire —
    # du code, des essais, une lecture — n'est JAMAIS interrompu : c'est la
    # condition pour qu'elle survive.
    liste = rechutes()
    if active("B10-rechutes") and liste and attente:
        # DEUX TÉMOINS, DEUX DURÉES DE VIE, et les confondre était l'erreur. Ce
        # qui a DÉJÀ été contrôlé appartient à l'agent et survit aux sessions ;
        # le PLAFOND appartient à la session, sinon il se remplit une fois pour
        # toutes et la liste ne se rejoue plus jamais.
        f_rech = os.path.join(ed, slug(agent) + ".rechutes")
        # Suffixe différent du témoin d'agent, exprès : la purge des témoins de
        # session ramasse celui-ci et ne doit SURTOUT PAS ramasser l'autre.
        f_cpt = os.path.join(ed, session + ".compteur")
        h_neufs = sorted(set(sha12(t.titre) for t in attente))
        if not os.path.exists(f_rech):
            ecrit(f_rech, "\n".join(h_neufs))
        else:
            deja_l = lignes_temoin(f_rech)
            faits = _i64(lis(f_cpt).strip(), 0)
            neufs = sum(1 for t in attente if sha12(t.titre) not in deja_l)
            # Une entrée de carnet versée ce tour compte aussi : elle porte un
            # niveau de confiance, donc elle affirme.
            declenche = neufs > 0 or len(ecrites) > 0
            ecrit(f_rech, "\n".join(sorted(set(deja_l + h_neufs))))
            if declenche and faits < RECHUTES_MAX and not forme_muette:
                ecrit(f_cpt, str(faits + 1))
                n = neufs if neufs > 0 else len(ecrites)
                sortie(2, MSG_B10.format(n, liste), "B10-rechutes", str(neufs))

    # --- 2 quinquies. LE RELECTEUR ------------------------------------------
    # LA BARRIÈRE N'EST PAS UNE PERMISSION, C'EST L'IGNORANCE. En triptyque, le
    # capteur est un AUTRE agent, sans droit d'écriture. Seul, le rôle se sépare
    # par le CONTEXTE : le juge reçoit l'affirmation, ce qui l'accompagne et sa
    # vérification — jamais le raisonnement qui y a mené, jamais la
    # conversation. Il ne peut pas confirmer ce qu'il n'a pas vu.
    #
    # IL EST ASYNCHRONE, ET C'EST UN CHOIX. Le faire attendre bloquerait la fin
    # de tour trente à soixante secondes, à chaque tour. La ligne part donc chez
    # le commanditaire, et le verdict revient au tour d'après — s'il contredit, l'agent
    # est renvoyé au travail avec le motif.
    dep = os.path.join(socle.socle(), "relecture")

    def liste_ext(ext):
        try:
            return sorted(os.path.join(dep, n) for n in os.listdir(dep)
                          if os.path.splitext(n)[1] == ext)
        except OSError:
            return []

    # (a) LE VERDICT D'AVANT, S'IL CONTREDIT UNE LIGNE ENCORE OUVERTE.
    contredits = []
    for p in (liste_ext(".verdict") if active("B12-contredit") else []):
        t = lis(p)
        verdict, sur = "", ""
        for l in lignes(t):
            if l.startswith("verdict_relecteur:"):
                verdict = l[len("verdict_relecteur:"):].strip()
            if l.startswith("sur:"):
                sur = l[len("sur:"):].strip()
        # UN MÉCANISME SANS TRACE NE PEUT PAS ÊTRE JUGÉ — y compris celui-ci.
        ajoute(os.path.join(ed, "relectures.log"), "%s\t%s\t%s\t%s\n" % (
            maintenant("%Y-%m-%d %H:%M:%S"), agent, sur, verdict[:120]))
        if verdict.startswith("CONTREDIT"):
            x = next((x for x in attente if sha12(x.titre) == sur), None)
            if x is not None:
                contredits.append((x.titre, verdict[9:].strip()))
        # TRAITÉ UNE FOIS, JAMAIS DEUX : un verdict qui se represente
        # indéfiniment est un agent coincé, et aucun garde ne doit pouvoir ça.
        # S'il n'est pas corrigé, la ligne sera redéposée et rejugée.
        try:
            os.rename(p, os.path.splitext(p)[0] + ".traite")
        except OSError:
            pass
    if contredits:
        liste = "\n".join("  ✗ %s\n    → %s" % (t[:90], m[:200]) for t, m in contredits)
        sortie(2, MSG_B12.format(len(contredits), liste, ou_todo=ou_todo),
               "B12-contredit", str(len(contredits)))

    # (b) DÉPOSER — L'ARTEFACT SEUL. Une ligne n'est déposée qu'une fois : le
    # témoin est par AGENT et cumulatif, comme celui de la forme.
    vus_r = os.path.join(ed, slug(agent) + ".relu")
    deja_r = lignes_temoin(vus_r)
    en_attente = len(liste_ext(".demande"))
    deposes = []
    if active("B12-contredit") and en_attente < 20 and not accueil:   # le juge est borné
        mkdirs(dep)
        for t in attente:
            # ON NE DÉPOSE QUE CE QUI AFFIRME QUELQUE CHOSE. Mesuré au premier
            # essai réel : une question ordinaire — « j'autorise ceci ? » — ne
            # contient aucune affirmation, le juge a répondu INSUFFISANT, et
            # l'appel était perdu. Le marqueur `?constat` est précisément la
            # déclaration, par l'agent, que la ligne porte un fait qui peut
            # cesser d'être vrai tout seul ; et le garde B7 a déjà exigé qu'il
            # porte de quoi le rejouer. Il n'y a donc rien à juger ailleurs.
            s = spec_de(t.i)
            if s is None or s.sans:
                continue
            verif = "%s :: %s :: %s" % (s.source, s.cmd, s.motif)
            ident = sha12(t.titre)
            if ident in deja_r or ident in deposes:
                continue
            d = ("id: %s\nagent: %s\ndepose_le: %s\n\n--- affirmation ---\n%s\n\n"
                 "--- ce qui l'accompagne ---\n%s\n\n--- vérification ---\n%s\n") % (
                ident, agent, maintenant("%Y-%m-%d %H:%M"),
                t.titre, t.corps.strip() if t.corps.strip() else "(rien)", verif)
            if ecrit(os.path.join(dep, ident + ".demande"), d):
                deposes.append(ident)
    if deposes:
        ecrit(vus_r, "\n".join(sorted(set(deja_r + deposes))))
        lance_relecture()

    # --- 3 bis. LE CANAL NOTION : chaque question porte sa ligne ------------
    # Le hook ne lit pas Notion (il faudrait une clé sur la machine ; choix du
    # commanditaire le 30/09 : « contrôle : 1 »). Il exige le LIEN de la ligne
    # Décisions — une adresse Notion avec l'identifiant de la page. Garde
    # d'ÉTAT : elle renvoie même après un premier renvoi, mais pas plus de
    # NOTION_MAX fois de suite dans une session — au-delà, elle laisse finir
    # et le dit au commanditaire, plutôt que de tourner en rond.
    if notion:
        sans = [t for t in attente if not lien_notion("%s\n%s" % (t.titre, t.corps))]
        f_n = os.path.join(ed, session + ".notion")
        n = _i64(lis(f_n).strip(), 0)
        if sans:
            ech = "\n".join("  · %s" % t.titre for t in sans[:4])
            if n < NOTION_MAX:
                ecrit(f_n, str(n + 1))
                sortie(2, MSG_B14.format(len(sans), ech, ou_todo, NOTION_MAX),
                       "B14-notion", str(len(sans)))
            try:
                os.remove(f_n)
            except OSError:
                pass
            dit_sans_bloquer(MSG_NOTION_FIN.format(agent, len(sans)))
        try:
            os.remove(f_n)
        except OSError:
            pass
    ecrit(dernier, empreinte)

    # --- 5. DIRE À L'AGENT CE QUI EST TOMBÉ --------------------------------
    # Sans ça, un constat cesserait d'être présenté sans que personne le sache, et
    # on aurait fabriqué la panne même qu'on traque : un effet sans trace.
    if tombes:
        sig = sha16("tombe|%s|%s" % (empreinte, "|".join(tombes)))
        temoin = os.path.join(ed, session + ".tombe")
        if lis(temoin).strip() != sig:
            ecrit(temoin, sig)
            liste = "\n".join("  ✗ %s" % t for t in tombes)
            sortie(2, MSG_B9.format(len(tombes), liste, ou_todo=ou_todo),
                   "B9-tombe", str(len(tombes)))
    # --- 3. POSER, PAS DÉPOSER ---------------------------------------------
    # DERNIER BLOC, ET C'EST VOULU : `sortie` quitte le programme, donc tout ce
    # qui précède a la priorité. Celui-ci ne parle que d'un tour par ailleurs
    # irréprochable — la liste est à jour, les questions sont bien formées — et
    # c'est EXACTEMENT le tour où rien ne disait plus rien.
    #
    # POURQUOI IL EXISTE. Le 23/09/2026, le commanditaire : « avec la logique des rappels
    # ils ne me posent plus les questions ». La cause était dans ce fichier :
    # un bloc enseignait que la liste est « le SEUL endroit où le commanditaire
    # voit ce qui lui revient — il le lit depuis son téléphone, pas dans cette
    # conversation ». Chaque agent en concluait que poser la question en fin de
    # tour ne servait à rien. La phrase est corrigée ; sans ce bloc, le
    # correctif ne toucherait que les tours DÉJÀ en faute.
    #
    # Il INSTRUIT, il ne vérifie pas : un garde de fin de tour ne lit pas le
    # message que l'agent s'apprête à écrire. Le dire est donc tout ce qu'il
    # peut faire — et ne pas prétendre l'avoir vérifié.
    # LA GARDE RÉPÉTAIT (le commanditaire, 26/09/2026, capture à l'appui). Deux défauts :
    # elle ne lisait pas le message que l'agent venait d'écrire — et le relançait
    # donc sur des questions qu'il venait de poser ; et son témoin portait sur
    # TOUTE la liste, si bien qu'une seule question nouvelle réarmait la demande
    # de reposer les trente (PO en avait 30 ouvertes). Désormais : seules
    # comptent les questions JAMAIS demandées, mémorisées par agent ; et celles
    # que le message de fin de tour pose déjà ne déclenchent rien.
    if attente:
        vivantes = [t for t in attente if not t.tombe]
        registre = registre_posees(agent)
        premiere = not os.path.exists(registre)
        deja_p = lignes(lis(registre))
        neuves = [t for t in vivantes if sha16(t.titre) not in deja_p]
        if neuves:
            # Toute question vue est inscrite : on ne la redemande jamais deux fois.
            ecrit(registre, "\n".join(sorted(set(deja_p + [sha16(t.titre) for t in neuves]))))
            # PREMIÈRE RENCONTRE : le passif est amnistié, comme au carnet — sans
            # quoi la mise à jour exigerait de reposer d'un coup tout l'arriéré.
            message = dernier_message(data)
            a_poser = [] if premiere else [t for t in neuves if not posee(message, t.titre)]
            if a_poser and not forme_muette:
                liste = "\n".join("  · %s" % t.titre for t in a_poser[:4])
                reste = "\n  … et %d autre(s)." % (len(a_poser) - 4) if len(a_poser) > 4 else ""
                sortie(2, MSG_B13.format(len(a_poser), liste, reste), "B13-poser", str(len(a_poser)))

    sortie(0)


def todo_blocs(args):
    """LE DIALECTE DU TODO, RENDU EN DONNÉES — pour que personne n'en écrive un
    sixième lecteur.

    `harnais todo-blocs <fichier>` rend chaque tâche avec son état, sa
    priorité, son destinataire, et le découpage titre/corps EXACTEMENT tel que
    la fin de tour le lit.

    Pourquoi une sous-commande plutôt qu'une bibliothèque : `tableau`
    vit dans l'autre caisse, celle des outils du poste. Sans ce point d'entrée
    il aurait fallu y recopier le dialecte — ce qui fait exactement ce que le
    commentaire d'en-tête interdit.

    UN LIBELLÉ COURT SOUVENT SUR DEUX LIGNES, et c'est toute la raison d'être
    de ce point d'entrée : `chantiers()` ne rend que la ligne qui porte la
    case — c'est son contrat, et il est bon — mais s'en tenir à elle coupe les
    titres au milieu d'un mot."""
    if not args:
        sys.stderr.write("todo-blocs : il manque le chemin du fichier todo\n")
        return 2
    chemin = args[0]
    try:
        with open(chemin, encoding="utf-8", newline="") as f:
            texte = f.read()
    except (OSError, ValueError) as e:
        # ON DIT LE MANQUE. Rendre une liste vide se lirait comme « aucune
        # décision n'attend », c'est-à-dire l'inverse de la vérité quand le
        # fichier est simplement introuvable.
        if isinstance(e, OSError) and e.errno is not None:
            raison = "%s (os error %d)" % (e.strerror, e.errno)
        else:
            raison = "stream did not contain valid UTF-8"
        sys.stderr.write("todo-blocs : %s illisible — %s\n" % (chemin, raison))
        return 1
    import json
    taches = chantiers(texte)
    bruts = blocs_bruts(texte)
    dests = destinataires()
    out = []
    for i, t in enumerate(taches):
        # Les blocs et les tâches se correspondent un à un TANT QUE les deux
        # lecteurs voient la même chose. Quand ce n'est pas le cas, on ne
        # devine pas : on retombe sur le libellé de la ligne, et on le DIT
        # dans la sortie, pour qu'un décalage se voie au lieu de produire des
        # titres attribués de travers.
        apparie = len(bruts) == len(taches)
        if apparie:
            titre, corps = titre_et_corps(bruts[i])
        else:
            titre, corps = lisible(t.titre), ""
        out.append({
            "etat": t.etat,
            "prio": t.prio,
            "qui": t.qui,
            "pour_le_commanditaire": t.qui is not None and any(d == t.qui for d in dests),
            "titre": titre,
            "corps": corps,
            "apparie": apparie,
        })
    sys.stdout.write(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0




# ── LES TEXTES DES RENVOIS ────────────────────────────────────────────────
# Recopiés du Rust et comparés à l'octet par le contrôle différentiel : une
# garde qui mord avec la mauvaise phrase apprend le mauvais geste. `{}` et
# `{ou_todo}` sont remplis par `str.format` ; `{{ }}` est une accolade littérale.

PIED_RENVOI = (
    "\n"
    "\n"
    "— — —\n"
    "@user a DÉJÀ lu ton message : ne le recopie pas, ni tes conclusions, ni les questions que tu as déjà posées dans ce tour. Fais ce qui est demandé, puis termine par une ou deux lignes qui disent ce que tu as changé."
)

RECIDIVE_MSG = (
    "\n"
    "\n"
    "— — —\n"
    "Cette garde t'a repris {} fois cette semaine. Un rappel qui revient n'est plus un rappel, c'est une règle manquante.\n"
    "\n"
    "Avant de repartir, ouvre `rechutes.md` dans le dossier d'état indiqué par `harnais diagnostic` : qu'aurait-il fallu vérifier avant ? Seuls les TITRES en gras (`- **question ?**`) au-dessus de la ligne « ÉCRITURE » sont relus aux agents — une ligne ajoutée en fin de fichier ne revient jamais à personne. Si une question dit déjà à peu près ça, AFFÛTE son titre ; sinon ajoute une question dans la bonne section. La même leçon apprise deux fois est une seule règle. N'y mets jamais une panne d'environnement, ni une affirmation négative sur un outil.\n"
)

MSG_B1 = (
    "attente : tu as modifié du code ({}) sans mettre `{ou_todo}` à jour. Ce fichier est ce que @user retrouve quand il n'est pas là — il le lit souvent depuis son téléphone. Ce n'est PAS un moyen de ne pas lui demander : il est souvent disponible, et une question rangée sans être posée dort des jours.\n"
    "\n"
    "Avant de rendre la main : coche ce que tu as fini, et écris ce qui l'attend, une entrée par blocage, dans cette forme exacte (l'exemple est INVENTÉ et sans rapport avec ce projet : seule la forme compte) :\n"
    "\n"
    "- [ ] !haut @user **J'archive les anciens rapports ? oui / non**\n"
    "      oui → ils partent en archive demain ; tu pourras les rouvrir pendant 30 jours.\n"
    "      non → ils restent où ils sont et le dossier continue de grossir.\n"
    "      fini quand → tu ouvres le dossier et il ne reste que le mois en cours.\n"
    "      Ça attend depuis 4 jours ; j'ai continué sur le reste.\n"
    "\n"
    "UNE QUESTION FERMÉE, JAMAIS UN CONSTAT. Un constat lui laisse tout le travail : comprendre ce qu'on lui demande, deviner comment répondre, et mesurer seul ce qu'il risque à ne pas répondre. Il doit trancher d'un mot, depuis son téléphone, sans rien ouvrir.\n"
    "\n"
    "Sous la ligne, une ligne par réponse possible — ce qu'elle DÉCLENCHE, pas ce qu'elle signifie. Trois voies : numérote-les, il répond « 2 ». Et si tu ne sais pas quoi faire de l'une des réponses, la question n'est pas prête : elle n'a rien à faire dans sa liste.\n"
    "\n"
    "@user n'est pas forcément technique — PAS de nom de fichier, de fonction ni de variable d'environnement.\n"
    "\n"
    "SI TON PROJET A UN GUICHET DES QUESTIONS (un pair qui les reçoit, comme QA), c'est à lui que tu l'adresses (`@QA`) et que tu la lui transmets par le carnet d'équipe, pas à `@user`.\n"
    "\n"
    "ET POSE-LA : tout `@user` que tu écris ce tour-ci se pose AUSSI, en clair et sous sa forme fermée, dans ton message de fin de tour. Le todo est le filet pour quand il n'est pas là ; il ne remplace pas la question.\n"
    "\n"
    "Tu ne t'arrêtes pas pour autant : si tu peux avancer par un chemin réversible, prends-le, note l'hypothèse, et continue."
)

MSG_B4 = (
    "attente : @user t'a fait {} demande(s) marquée(s) !cible dans le fil, pas encore close(s).\n"
    "\n"
    "{}\n"
    "\n"
    "Traite-la ; si elle ne peut pas l'être maintenant, écris sous sa ligne dans `{ou_todo}` ce qui manque pour la finir. Coche-la quand c'est fait. Une ligne retirée sans être cochée : remets-la, ou dis à @user pourquoi tu la laisses. Je ne te la rappelle qu'une fois — ensuite elle vit dans ton todo, comme tes autres tâches."
)

MSG_B5 = (
    "attente : tu viens de commiter dans une zone que d'autres agents lisent ou importent ({}), sans rien verser au carnet d'équipe.\n"
    "\n"
    "Tes coéquipiers travaillent sur d'autres copies du dépôt : ils ne verront ton travail qu'à leur prochaine fusion, parfois deux jours plus tard, et RIEN ne le leur dira. Le carnet est le seul endroit qui n'existe qu'une fois.\n"
    "\n"
    "Ajoute `↗` sous la tâche que tu viens de finir dans `{ou_todo}`, et coche-la :\n"
    "\n"
    "- [x] Réparer l'inscription des utilisateurs\n"
    "      ↗ PO : l'écran d'inscription n'a plus besoin de son contournement.\n"
    "      ↻ service :: curl -s -o /dev/null -w '%{{http_code}}' https://…/signup :: ^200$\n"
    "\n"
    "UNE LIGNE `↗` PAR AGENT CONCERNÉ, et ce qu'elle dit est ce que ça change POUR LUI — pas le résumé de ton travail. Sans `↗`, rien n'est versé : c'est à toi de juger qui est concerné.\n"
    "\n"
    "La ligne `↻` est facultative et vaut « mesuré » : l'entrée porte alors de quoi être revérifiée, et sa confiance se restaure quand elle tient. Sans elle, l'entrée vaut « observé ».\n"
    "\n"
    "Si ton travail a ÉCHOUÉ, écris-le : `échoué` dans le bloc. Un échec sert d'examen, jamais d'exemple — le taire est la façon la plus sûre de le refaire."
)

MSG_B6 = (
    "attente : tu as modifié les FAITS du projet ({}). Ce sont les seuls fichiers partagés par tous les agents, et ils ne s'écrivent qu'à la demande de @user — un agent qui les réécrit depuis son lot efface le travail d'un autre en silence.\n"
    "\n"
    "Ta mémoire est déportée : elle s'enregistre toute seule en fin de tour, MAIS jamais ces fichiers-là. Ils resteront donc en attente indéfiniment.\n"
    "\n"
    "Si @user ne l'a pas demandé, annule-les. S'il l'a demandé, enregistre-les toi-même avec ` # fact-ok` dans le message — l'autorisation restera dans l'historique."
)

MSG_B7 = (
    "attente : {} constat(s) sans moyen d'être rouvert(s) : {}.\n"
    "\n"
    "Un constat n'est pas une tâche. « Construire X » reste vrai jusqu'à ce que tu le fasses ; « X manque » peut cesser d'être vrai TOUT SEUL, sans que personne y touche — et un constat bien mesuré n'est pas plus durable qu'un constat bâclé, seulement plus crédible, donc plus dangereux quand il périme.\n"
    "\n"
    "Ajoute sous chaque ligne `?constat` de quoi la rejouer :\n"
    "\n"
    "      ↻ service :: curl -s -o /dev/null -w '%{{http_code}}' https://exemple.fr/contact :: ^200$\n"
    "\n"
    "Trois champs. D'ABORD LA SOURCE — `machine` si la réponse est sur ce poste, `service` si elle est chez le fournisseur. Une mesure locale ne répond jamais à une question distante : c'est ainsi qu'un contrôle a décodé un cache vieux de quatre jours et rendu un chiffre net, cohérent, et hors sujet. Puis la commande, puis ce qu'elle doit répondre si le constat tient encore.\n"
    "\n"
    "Si une ligne est une tâche et non un constat, retire `?constat`."
)

MSG_B11 = (
    "attente : la cible du projet n'est pas tenue, et l'écart n'a PAS BOUGÉ depuis {} mesures.\n"
    "\n"
    "  🎯 {}\n"
    "\n"
    "Ce que tu essaies ne marche pas. Continuer à prescrire la même chose ne la fera pas marcher — et personne ne s'en apercevra, parce qu'une boucle qui tourne ressemble à une boucle qui avance.\n"
    "\n"
    "ARRÊTE de represcrire. Deux gestes, dans cet ordre :\n"
    "\n"
    "1. Demande-toi si c'est la MESURE qui est fausse avant de conclure que le produit l'est. Une vérification qui rend toujours le même verdict est suspecte : de quelle source lit-elle sa réponse ?\n"
    "2. Si la mesure tient, pose la question à @user dans `{ou_todo}` — une question fermée, ce que chaque réponse déclenche, et la ligne `fini quand →`. C'est lui qui tranche entre changer d'approche, changer la cible, ou accepter l'écart.\n"
    "\n"
    "Si tu ne conduis pas la campagne, tu n'as rien à prescrire : note-le et continue ton travail.\n"
    "\n"
    "Je te le redirai dans {} cycles si rien ne bouge."
)

MSG_B8 = (
    "attente : {} ligne(s) qui attend(ent) @user sont écrites comme des CONSTATS, pas comme des questions : {}.\n"
    "\n"
    "Un constat lui laisse tout le travail — comprendre ce qu'on lui demande, deviner comment répondre, mesurer seul ce qu'il risque à ne pas répondre. Il doit trancher d'un mot, depuis son téléphone, sans rien ouvrir.\n"
    "\n"
    "Réécris chacune dans cette forme (l'exemple est INVENTÉ et sans rapport avec ce projet : seule la forme compte) :\n"
    "\n"
    "- [ ] !haut @user **J'archive les anciens rapports ? oui / non**\n"
    "      oui → ils partent en archive demain ; tu pourras les rouvrir pendant 30 jours.\n"
    "      non → ils restent où ils sont et le dossier continue de grossir.\n"
    "      fini quand → tu ouvres le dossier et il ne reste que le mois en cours.\n"
    "      Ça attend depuis 4 jours ; j'ai continué sur le reste.\n"
    "\n"
    "Le libellé porte la question ET les réponses possibles. Dessous, une ligne par réponse : ce qu'elle DÉCLENCHE, pas ce qu'elle signifie. Trois voies : numérote-les, il répond « 2 ».\n"
    "\n"
    "La dernière ligne est obligatoire : `fini quand → …`, ce que @user doit voir pour considérer la chose réglée. Pas une commande, pas un `↻` : ce qu'il constate, lui, de son côté. Sans elle, il n'a que ta parole.\n"
    "\n"
    "Et si tu ne sais pas quoi faire de l'une des réponses, la question n'est pas prête — elle n'a rien à faire dans sa liste.\n"
    "\n"
    "Une question que tu as déjà posée dans ce tour l'est : ne la recopie pas. Une question que tu n'as pas encore posée, pose-la.\n"
    "\n"
    "Je te le redemanderai au plus une fois encore par ligne : c'est un avertissement, pas un blocage permanent."
)

MSG_B10 = (
    "attente : {} point(s) vont partir chez @user. Avant qu'ils partent, rejoue ceci — c'est la liste de nos erreurs qui reviennent, et elle t'a déjà repris :\n"
    "\n"
    "{}\n"
    "\n"
    "Reprends chacune de tes affirmations en face de ces questions. Si l'une d'elles mord, corrige la mesure AVANT de corriger la conclusion — c'est presque toujours l'instrument qui a tort, pas le monde.\n"
    "\n"
    "Si rien ne mord, dis-le en une ligne et continue : je ne te le redemanderai pas pour ces points-là."
)

MSG_B12 = (
    "attente : un relecteur qui n'a PAS écrit ces lignes en contredit {}.\n"
    "\n"
    "{}\n"
    "\n"
    "Il n'a reçu que l'affirmation, ce qui l'accompagne et sa vérification — ni ton raisonnement, ni cette conversation. Il ne peut donc pas confirmer par complaisance ce qu'il n'a pas vu, et c'est précisément ce qui rend son avis utile : c'est le seul regard de la chaîne qui ne soit pas le tien.\n"
    "\n"
    "Il n'a pas raison d'office. Trois issues, et une seule est interdite :\n"
    "\n"
    "1. Il a raison → corrige la ligne dans `{ou_todo}` avant qu'elle coûte une décision à @user.\n"
    "2. Il a tort parce que ta vérification mesure mal → corrige la VÉRIFICATION, c'est presque toujours l'instrument qui a tort.\n"
    "3. Il a tort et tu peux le montrer → écris pourquoi sous la ligne, en une phrase, et continue.\n"
    "\n"
    "Ce qui est interdit : passer outre sans rien écrire. Je ne te le redirai pas pour ces lignes-là — elles seront rejugées si elles repartent inchangées."
)

MSG_B14 = (
    "attente : {} question(s) pour @user n'ont pas leur ligne dans la base Décisions de Notion :\n"
    "\n"
    "{}\n"
    "\n"
    "Sur ce projet, il lit ses questions dans la base Décisions de Notion. Pour chacune, crée la ligne (statut, demandé par, options numérotées, ce qui est bloqué), puis ajoute son lien sous la question dans `{}` :\n"
    "\n"
    "      ↳ https://www.notion.so/…\n"
    "\n"
    "Si Notion ne répond pas, dis-le dans ton message : au bout de {} renvois, je laisse finir et je le signale à @user."
)

MSG_NOTION_FIN = (
    "{} termine avec {} question(s) sans ligne dans Décisions (Notion) — la liste de ses questions est dans son todo."
)

MSG_B9 = (
    "attente : {} constat(s) ne tiennent plus — leur propre vérification dit le contraire, DEUX FOIS DE SUITE :\n"
    "\n"
    "{}\n"
    "\n"
    "Un premier échec les avait seulement annotés : une vérification rate aussi pour de mauvaises raisons — réseau, jeton, débit limité. Deux d'affilée, c'est autre chose.\n"
    "\n"
    "Ils ne lui sont plus présentés comme des questions, pour qu'il n'ait pas à contrôler des lignes fausses. Ils sont TOUJOURS dans `{ou_todo}` : rien n'a été détruit, parce qu'une vérification peut se tromper et qu'un contrôle dont l'échec ressemble au succès est exactement ce qu'on cherche à éviter.\n"
    "\n"
    "À toi de trancher : si le constat est bien caduc, coche-le ou retire la ligne. S'il tient encore, c'est ta VÉRIFICATION qui est fausse — corrige-la plutôt que le constat, et demande-toi d'abord de quelle source elle a lu sa réponse.\n"
    "\n"
    "ET DANS LES DEUX CAS, TU AS AFFIRMÉ QUELQUE CHOSE DE FAUX : ou bien le constat, ou bien le contrôle. C'est le seul endroit de la chaîne où on le sait avec certitude. Dans `rechutes.md` (dossier d'état indiqué par `harnais diagnostic`), au-dessus de la ligne « ÉCRITURE » (le reste n'est jamais relu) : qu'aurait-il fallu vérifier avant ? Affûte le titre en gras d'une question existante si elle dit déjà à peu près ça, sinon ajoute une question — la même leçon apprise deux fois est une seule règle."
)

MSG_B13 = (
    "attente : {} question(s) NOUVELLE(S) attendent @user, et ton message ne les pose pas :\n"
    "\n"
    "{}{}\n"
    "\n"
    "Pose CELLES-LÀ, en clair et sous leur forme fermée, voies numérotées comprises — pas les autres, qu'il a déjà vues. Le todo est le filet pour quand il n'est pas là ; une question rangée sans être posée dort des jours.\n"
    "\n"
    "Tu ne t'arrêtes pas pour autant : ce qui peut avancer par un chemin réversible avance."
)

MSG_MUET_LOCAL = (
    "elle annonce une source distante et ne sort pas de cette machine — une mesure locale ne répond pas à une question distante"
)

MSG_CIBLE = (
    "demande !cible de @user notée dans `{}` (repère « {} »). Elle est suivie : traite-la, et coche sa ligne quand c'est fait. Si elle ne peut pas l'être dans ce tour, écris sous elle ce qui manque — la fin de tour te la rappellera une fois."
)

