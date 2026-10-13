# -*- coding: utf-8 -*-
"""LA MÉMOIRE PARTAGÉE ENTRE DEUX PERSONNES — récupérer, intégrer, envoyer.

Port de `harnais/src/synchro.rs` (Rust, 0.12.8) — sans précurseur Python.

Demandé par le CTO le 09/10/2026, sur décision de Maxime : Legal, Compta et
Designer servent à Maxime ET à Damien, chacun sur sa machine, chacun avec
son compte. L'agent doit se souvenir de ce qu'il a fait avec l'un comme avec
l'autre, y compris quand les deux travaillent en même temps.

LA FORME : un poste par personne (multi-agents), un esprit chacun, le reste
en commun ; la mémoire dans son propre dépôt (`brain/` autonome, ou
l'ancienne `memoire/`), doté d'un distant. Seul CE dépôt se synchronise,
jamais celui de l'agent.

À LA DEMANDE, PROJET PAR PROJET : `HARNAIS_SYNCHRO=git` dans les réglages
des agents. La présence d'un distant ne suffit pas — un distant de
sauvegarde ne doit pas se mettre à intégrer le travail d'un autre. Sans le
réglage, rien ici ne s'exécute : Splide a une mémoire déportée sans
distant, et son comportement ne doit pas bouger d'un octet.

QUATRE PROMESSES, et chacune a son contrôle :
1. ce qu'écrit l'un est lu par l'autre à son démarrage suivant ;
2. deux séances simultanées sur des fichiers différents fusionnent seules ;
3. le même passage modifié des deux côtés S'ARRÊTE : la fusion est annulée,
   les enregistrements locaux restent, rien n'est envoyé, jamais de force ;
4. hors ligne, rien ne bloque — mais c'est dit, à chaque tour, tant que
   l'envoi est en retard. Un silence ressemblerait à un succès.

FUSION, JAMAIS REBASE : une fusion ratée s'annule sans réécrire un seul
enregistrement, et l'historique garde qui a écrit quoi.

Les chemins sont des `str`. Les imports lourds (`subprocess`, `hashlib`,
`datetime`) se font DANS les fonctions : `active()` est appelé par le briefing à
chaque session, et c'est presque toujours pour répondre « non ».
"""
import json
import os
import time

# Au plus une récupération par minute en fin de tour : le réseau à chaque
# tour aurait rendu à la fin de tour la lenteur qu'elle a perdue en 0.12.7.
# Un envoi en attente, lui, récupère toujours d'abord.
PAS_DE_RECUPERATION = 60.0
DELAI_RECUPERATION = 8.0       # s
DELAI_ENVOI = 15.0
# Au démarrage, le briefing attend, et Claude Code le coupe à 15 s : au
# pire 4 + 4 + 3 = 11 s, fusion locale comprise.
DELAI_DEMARRAGE = 4.0
ENVOI_DEMARRAGE = 4.0
DELAI_DEPOT_AGENT = 3.0

# `std::str::trim` de Rust (White_Space d'Unicode), pas `str.strip()`.
_BLANCS = ("\t\n\x0b\x0c\r \x85\xa0        "
           "        　")


def _trim(s):
    return s.strip(_BLANCS)


def _lignes(t):
    """`str::lines()` de Rust."""
    if not t:
        return []
    parts = t.split("\n")
    dernier = parts.pop()
    out = [p[:-1] if p.endswith("\r") else p for p in parts]
    if dernier != "":
        out.append(dernier)
    return out


def mode():
    """`git` (la mémoire seule, dans son propre dépôt) ou `git-depot` (le dépôt
    ENTIER de l'agent), ou « » quand rien n'est demandé."""
    m = os.environ.get("HARNAIS_SYNCHRO", "").strip(_BLANCS)
    return m if m in ("git", "git-depot") else ""


def active():
    return mode() != ""


def _quoi():
    """Ce qu'on nomme à l'agent : la mémoire seule, ou le dépôt entier."""
    return "dépôt partagé" if mode() == "git-depot" else "mémoire partagée"


def depot(res):
    """Le dépôt à synchroniser.

    · `git` : celui qui porte la mémoire, quand elle en a un À ELLE ; le dépôt de
      l'agent n'est jamais rendu.
    · `git-depot` (Maxime, 13/10/2026, pour Legal partagé avec Damien : « un seul
      dépôt, entièrement synchronisé ») : le dépôt ENTIER de l'agent — consignes,
      réglages, savoir-faire, dossiers et mémoire. Risque accepté par lui en
      connaissance de cause : une consigne ou un droit changé sur un poste arrive
      sur l'autre sans relecture. La mémoire doit alors vivre DANS ce dépôt : une
      mémoire à dépôt propre se synchronise en `git`, pas ici."""
    from memoire import Forme
    m = mode()
    if m == "git-depot":
        if res.forme not in (Forme.Brain, Forme.Deportee) or res.brain_autonome:
            return None
        # La racine du dépôt où l'on travaille (`arbre`) — c'est d'elle que le
        # préfixe des faits (`brain/fact/`) est relatif.
        if not res.arbre:
            return None
        top = court(res.arbre, ["rev-parse", "--show-toplevel"])
        if top is None or not top.strip():
            return None
        return os.path.realpath(top.strip())
    if res.forme in (Forme.Brain, Forme.Deportee) and res.brain_autonome:
        return res.projet
    return None


# CE QUI NE PART JAMAIS, même en synchronisant le dépôt entier : un `.env` (les
# secrets), le registre local d'un expert (ce qui identifie quelqu'un), les
# réglages propres à une machine et la trace d'entrée du briefing (réécrite à
# chaque séance : elle ferait un enregistrement par démarrage). `.gitignore` doit
# déjà les couvrir ; ces exclusions tiennent même s'il ne le fait pas.
JAMAIS = [":(exclude,glob)**/.env", ":(exclude,glob)**/.env.*",
          ":(exclude,glob)**/brain/local/**", ":(exclude,glob)brain/local/**",
          ":(exclude,glob)**/.claude/settings.local.json",
          ":(exclude,glob)**/.claude/.briefing.json",
          # le verrou du briefing existe PENDANT le démarrage, quand la synchro
          # enregistre : il partait, puis son retrait partait — un aller-retour
          # par séance et par poste (mesuré chez Legal par le CTO, 13/10/2026).
          ":(exclude,glob)**/.claude/.briefing.lock"]


def sensibles_suivis(depot):
    """Les fichiers SENSIBLES déjà suivis par git — un `.env` ou le registre local.
    Une exclusion n'y peut plus rien : ils partiraient avec l'historique. Le mode
    `git-depot` refuse alors d'envoyer quoi que ce soit, et le dit."""
    t = court(depot, ["ls-files"]) or ""
    out = []
    for l in _lignes(t):
        nom = l.rsplit("/", 1)[-1]
        if "/brain/local/" in "/" + l or (nom == ".env" or (nom.startswith(".env.")
                                           and nom not in (".env.example", ".env.sample"))):
            out.append(l)
    return out


class Accroc(object):
    """Ce qui a coincé. Cinq genres, comme l'énumération du Rust ; `detail`
    porte le message (ou, pour `Conflit`, la liste des fichiers).

    · HorsLigne(m) — le réseau, le distant ou les identifiants : on réessaiera ;
    · SansSuivi — pas de branche suivie : rien à intégrer, nulle part où envoyer ;
    · Conflit(fichiers) — le même passage modifié des deux côtés ;
    · Bloque(m) — git a refusé d'intégrer sans conflit de contenu (un fichier
      local non enregistré serait écrasé, typiquement un fait en attente) ;
    · Refuse(m) — l'envoi a été refusé : le distant a bougé entre-temps. Le
      prochain passage intègre puis renvoie.
    """
    __slots__ = ("genre", "detail")

    def __init__(self, genre, detail=None):
        self.genre = genre
        self.detail = detail

    @classmethod
    def HorsLigne(cls, m):
        return cls("HorsLigne", m)

    @classmethod
    def Conflit(cls, fichiers):
        return cls("Conflit", list(fichiers))

    @classmethod
    def Bloque(cls, m):
        return cls("Bloque", m)

    @classmethod
    def Refuse(cls, m):
        return cls("Refuse", m)

    def __eq__(self, autre):
        return (isinstance(autre, Accroc) and self.genre == autre.genre
                and self.detail == autre.detail)

    def __ne__(self, autre):
        return not self.__eq__(autre)

    __hash__ = None

    def __repr__(self):
        if self.detail is None:
            return "Accroc.%s" % self.genre
        return "Accroc.%s(%r)" % (self.genre, self.detail)


# L'unique variante sans charge : une valeur, pas une fabrique.
Accroc.SansSuivi = Accroc("SansSuivi")


class Bilan(object):
    """Ce qu'un passage a fait : reçus, envoyés, en retard, et l'accroc éventuel."""
    __slots__ = ("recus", "envoyes", "en_retard", "accroc")

    def __init__(self, recus=0, envoyes=0, en_retard=0, accroc=None):
        self.recus = recus
        self.envoyes = envoyes
        # Enregistrements locaux qui n'ont pas atteint le distant.
        self.en_retard = en_retard
        self.accroc = accroc

    def __eq__(self, autre):
        return (isinstance(autre, Bilan) and self.recus == autre.recus
                and self.envoyes == autre.envoyes and self.en_retard == autre.en_retard
                and self.accroc == autre.accroc)

    def __ne__(self, autre):
        return not self.__eq__(autre)

    __hash__ = None

    def __repr__(self):
        return "Bilan(recus=%r, envoyes=%r, en_retard=%r, accroc=%r)" % (
            self.recus, self.envoyes, self.en_retard, self.accroc)


class GitErreur(Exception):
    """Le `Err(String)` du Rust : git n'est pas parti, ou n'a pas répondu à temps."""


def git(d, a, delai):
    """Une commande git bornée dans le temps, sans aucune invite : un hook qui
    attend un mot de passe gèle la session sans un mot. Rend `(ok, stdout,
    stderr)` ; lève `GitErreur` (le `Err` du Rust) si le délai est dépassé."""
    import subprocess
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    if "GIT_SSH_COMMAND" not in os.environ:
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o ConnectTimeout=5"
    try:
        p = subprocess.Popen(["git"] + list(a), cwd=d, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, ValueError) as e:
        raise GitErreur("git introuvable : %s" % e)
    try:
        # `communicate` vide les deux tubes en parallèle : un tube plein bloque
        # git, qui ne finit jamais, et le délai serait pris pour une panne réseau.
        o, e = p.communicate(timeout=delai)
    except subprocess.TimeoutExpired:
        try:
            p.kill()
        except OSError:
            pass
        # Un petit-fils (ssh) peut garder les tubes ouverts : on ne les relit pas.
        for t in (p.stdout, p.stderr):
            try:
                t.close()
            except (OSError, ValueError):
                pass
        try:
            p.wait(timeout=5)
        except Exception:
            pass
        raise GitErreur("sans réponse après %d s" % int(delai))
    return (p.returncode == 0, o.decode("utf-8", "replace"), e.decode("utf-8", "replace"))


def court(d, a):
    try:
        r = git(d, a, 5.0)
    except GitErreur:
        return None
    return _trim(r[1]) if r[0] else None


def compte(d, plage):
    s = court(d, ["rev-list", "--count", plage])
    try:
        return int(s) if s is not None and s.isascii() and s.isdigit() else 0
    except ValueError:
        return 0


def premiere(s):
    """La première ligne parlante d'une erreur git, pour un humain."""
    for l in _lignes(s):
        l = _trim(l)
        if l and not l.startswith("hint:"):
            return l[:160]
    return "erreur sans message"


def enregistre(depot, agent, prefixe_fact, exclus=()):
    """ENREGISTRER la mémoire — tout sauf les faits. Rend les faits touchés et non
    enregistrés : c'est au garde des faits de les nommer à l'agent.

    Les faits n'entrent JAMAIS ici : déportée, la mémoire partagée ne passe
    plus par le garde de commit, qui serait devenu inerte en silence.
    """
    # NON ROGNÉ : la première colonne de `--porcelain` est souvent une espace,
    # et rognée elle décale le chemin d'un caractère — le fait passait pour
    # autre chose et partait avec le reste. Trouvé par l'essai des faits.
    try:
        r = git(depot, ["status", "--porcelain"], 5.0)
        st = r[1] if r[0] else ""
    except GitErreur:
        st = ""

    def chemin(l):
        return _trim(l[3:]).strip('"')
    pf = "\x00" if not prefixe_fact else prefixe_fact
    # `exclus` : ce qui ne s'enregistre JAMAIS, quoi qu'il arrive — le registre
    # local d'un expert (12/10/2026). Il doit être ignoré par git ; s'il ne l'est
    # pas, la garde des faits le dit, et ce bloc ne l'emporte pas pour autant.
    lignes = [l for l in _lignes(st)
              if not any(chemin(l) == x.rstrip("/") or chemin(l).startswith(x) for x in exclus)]
    faits = [c for c in (chemin(l) for l in lignes) if c.startswith(pf)]
    if any(not chemin(l).startswith(pf) for l in lignes):
        a = ["add", "-A", "--", "."]
        if prefixe_fact:
            a.append(":(exclude)%s" % prefixe_fact.rstrip("/"))
        for x in exclus:
            a.append(":(exclude)%s" % x.rstrip("/"))
        if mode() == "git-depot":
            a.extend(JAMAIS)
        try:
            git(depot, a, 10.0)
        except GitErreur:
            pass
        try:
            git(depot, ["commit", "-q", "-m", "Mémoire — %s, %s" % (
                agent, time.strftime("%d/%m %H:%M"))], 10.0)
        except GitErreur:
            pass
    return faits


def synchronise(depot, recuperer, delai, envoi):
    """INTÉGRER ce que l'autre a envoyé, puis ENVOYER. Ne force jamais, n'écrase
    jamais : une fusion qui coince est annulée et nommée."""
    b = Bilan()
    if mode() == "git-depot":
        sens = sensibles_suivis(depot)
        if sens:
            b.en_retard = compte(depot, "@{u}..HEAD")
            b.accroc = Accroc("Sensible", sens)
            return b
    suivi = court(depot, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if suivi is None:
        b.accroc = Accroc.SansSuivi
        return b
    en_avance = compte(depot, "@{u}..HEAD")
    if recuperer or en_avance > 0:
        try:
            ok, _, e = git(depot, ["fetch", "-q"], delai)
        except GitErreur as err:
            b.en_retard = en_avance
            b.accroc = Accroc.HorsLigne(str(err))
            return b
        if not ok:
            b.en_retard = en_avance
            b.accroc = Accroc.HorsLigne(premiere(e))
            return b
    derriere = compte(depot, "HEAD..@{u}")
    if derriere > 0:
        try:
            ok, o, e = git(depot, ["merge", "--no-edit", "-q", "@{u}"], 20.0)
            err = "%s\n%s" % (e, o)
        except GitErreur as ge:
            ok, err = False, str(ge)
        if ok:
            b.recus = derriere
        else:
            en_conflit = [x for x in _lignes(
                court(depot, ["diff", "--name-only", "--diff-filter=U"]) or "")]
            # Annuler SEULEMENT une fusion commencée : sans elle, `--abort`
            # n'a rien à défaire, et l'arbre est déjà intact.
            gd = court(depot, ["rev-parse", "--git-dir"])
            if gd is not None:
                if not os.path.isabs(gd):
                    gd = os.path.join(depot, gd)
                if os.path.exists(os.path.join(gd, "MERGE_HEAD")):
                    try:
                        git(depot, ["merge", "--abort"], 10.0)
                    except GitErreur:
                        pass
            b.en_retard = compte(depot, "@{u}..HEAD")
            b.accroc = Accroc.Bloque(premiere(err)) if not en_conflit else Accroc.Conflit(en_conflit)
            return b
    a_envoyer = compte(depot, "@{u}..HEAD")
    if a_envoyer > 0:
        try:
            ok, _, e = git(depot, ["push", "-q"], envoi)
        except GitErreur as err:
            b.en_retard = a_envoyer
            b.accroc = Accroc.HorsLigne(str(err))
            return b
        if ok:
            b.envoyes = a_envoyer
        else:
            b.en_retard = a_envoyer
            m = premiere(e)
            if "rejected" in e or "fetch first" in e or "non-fast-forward" in e:
                b.accroc = Accroc.Refuse(m)
            else:
                b.accroc = Accroc.HorsLigne(m)
    return b


# ── L'état du dernier passage — lu par le briefing ───────────────────────────

def fichier_etat(depot):
    import hashlib
    import socle
    nom = hashlib.sha1(str(depot).encode("utf-8")).hexdigest()[:16]
    return os.path.join(socle.socle(), "attente", "synchro-%s.json" % nom)


def lis_etat(depot):
    try:
        with open(fichier_etat(depot), "rb") as f:
            v = json.loads(f.read().decode("utf-8"))
    except (OSError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def maintenant():
    return time.time()


def _nombre(v):
    """`as_f64` : un nombre JSON, pas un booléen ; sinon None."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


def note(depot, b, recupere):
    avant = lis_etat(depot)
    horsligne = b.accroc is not None and b.accroc.genre in ("HorsLigne", "SansSuivi")
    if recupere and not horsligne:
        recup = maintenant()
    else:
        x = _nombre(avant.get("recuperation"))
        recup = x if x is not None else 0.0
    v = {
        "quand": maintenant(),
        "recuperation": recup,
        "recus": b.recus, "envoyes": b.envoyes, "en_retard": b.en_retard,
        "accroc": None,
        # Depuis quand l'envoi est en retard : c'est ce qu'un humain demande.
        "retard_depuis": None,
    }
    if b.accroc is not None:
        v["accroc"] = phrase(b.accroc)
    if b.en_retard > 0:
        anc = avant.get("retard_depuis")
        v["retard_depuis"] = anc if anc is not None else maintenant()
    f = fichier_etat(depot)
    try:
        os.makedirs(os.path.dirname(f), exist_ok=True)
    except OSError:
        pass
    try:
        with open(f, "w", encoding="utf-8", newline="") as h:
            h.write(json.dumps(v, ensure_ascii=False, separators=(",", ":")))
    except OSError:
        pass


def phrase(a):
    g = a.genre
    if g == "HorsLigne":
        return "distant injoignable (%s)" % a.detail
    if g == "SansSuivi":
        return "le dépôt de mémoire n'a pas de branche suivie sur un distant"
    if g == "Conflit":
        return "le même passage a été modifié des deux côtés dans : %s" % ", ".join(a.detail)
    if g == "Bloque":
        return "intégration refusée par git (%s)" % a.detail
    if g == "Sensible":
        return ("un secret ou une donnée qui identifie quelqu'un est suivi par git (%s) : RIEN n'est "
                "envoyé tant qu'il l'est" % ", ".join(a.detail[:4]))
    return "envoi refusé, le distant a bougé (%s) — réessayé au prochain tour" % a.detail


def fin_de_tour(depot):
    """FIN DE TOUR : enregistrer (fait par l'appelant), puis intégrer et envoyer."""
    x = _nombre(lis_etat(depot).get("recuperation"))
    derniere = x if x is not None else 0.0
    recuperer = maintenant() - derniere >= PAS_DE_RECUPERATION
    b = synchronise(depot, recuperer, DELAI_RECUPERATION, DELAI_ENVOI)
    note(depot, b, recuperer)
    return b


def presentation():
    """Ce que l'agent doit savoir de son dépôt, dit à chaque ouverture."""
    if mode() == "git-depot":
        return ("dépôt partagé : ce dépôt est synchronisé avec l'autre poste à chaque fin de "
                "tour. Tout ce que tu y changes — consignes, réglages, savoir-faire, faits, "
                "mémoire — arrive chez l'autre sans relecture. Ne partent jamais : les secrets "
                "(.env), le registre local, les réglages propres à ce poste.")
    return ("mémoire partagée : ta mémoire est synchronisée avec l'autre poste à chaque fin "
            "de tour ; le reste du dépôt ne l'est pas.")


def demarrage(res, agent):
    """DÉMARRAGE : récupérer toujours, avant que le briefing ne lise la mémoire.
    Rend la ligne à mettre en tête du briefing, s'il y a quelque chose à dire."""
    if not active():
        return None
    lignes = []
    d = depot(res)
    if d is None:
        if mode() == "git-depot":
            lignes.append("dépôt partagé : HARNAIS_SYNCHRO=git-depot est posé, mais ce dossier n'est pas "
                          "un dépôt dont la mémoire fait partie — rien n'est synchronisé. Dis-le à ton humain.")
        else:
            lignes.append("mémoire partagée : HARNAIS_SYNCHRO=git est posé, mais cette mémoire n'a pas "
                          "de dépôt à elle — rien n'est synchronisé. Dis-le à ton humain.")
    else:
        # L'AGENT LE SAIT EN CLAIR, à chaque ouverture : sans cette ligne il ne
        # l'apprenait que par la consigne de son poste (constaté chez Legal, 13/10/2026).
        lignes.append(presentation())
        enregistre(d, agent, res.prefixe_fact)
        b = synchronise(d, True, DELAI_DEMARRAGE, ENVOI_DEMARRAGE)
        note(d, b, True)
        l = ligne(d, b)
        if l is not None:
            lignes.append(l)
        elif b.recus > 0:
            lignes.append(_quoi() + " : %d enregistrement(s) de l'autre poste intégré(s) — "
                          "ce que tu lis plus bas les contient." % b.recus)
    # LE DÉPÔT DE L'AGENT N'EST JAMAIS TIRÉ — seulement regardé. Ses savoir-
    # faire et ses consignes peuvent avoir avancé chez l'autre : invisible sans
    # cette ligne, et c'était le but de Maxime. Hors ligne : la ligne de la
    # mémoire le dit déjà, celle-ci se tait.
    a = res.arbre if mode() == "git" else None   # en `git-depot`, il vient d'être tiré
    if a:
        if court(a, ["rev-parse", "--abbrev-ref", "@{u}"]) is not None:
            try:
                ok = git(a, ["fetch", "-q"], DELAI_DEPOT_AGENT)[0]
            except GitErreur:
                ok = False
            if ok:
                n = compte(a, "HEAD..@{u}")
                if n > 0:
                    lignes.append("dépôt de l'agent : %d enregistrement(s) sur le distant que cette "
                                  "copie n'a pas (savoir-faire, consignes). Rien n'est tiré "
                                  "automatiquement : dis-le à ton humain, c'est lui qui décide "
                                  "de les prendre." % n)
    return "\n".join(lignes) if lignes else None


def ligne(depot, b):
    """Ce qui ne va pas, en une ligne — `None` quand tout est à jour."""
    a = b.accroc
    if a is None:
        return None
    retard = (" %d enregistrement(s) local(aux) pas encore envoyé(s)." % b.en_retard
              if b.en_retard > 0 else "")
    if a.genre in ("Conflit", "Bloque", "Sensible"):
        return (_quoi() + (" BLOQUÉ" if mode() == "git-depot" else " BLOQUÉE") + " : %s. Rien n'est écrasé ni envoyé.%s "
                "Pose-le à ton humain (voir %s)." % (phrase(a), retard, depot))
    return (_quoi() + " : %s.%s Ce que tu lis peut ne pas contenir le dernier "
            "travail de l'autre poste." % (phrase(a), retard))


def rappel(res):
    """À CHAQUE MESSAGE : tant que le dernier passage a un accroc, le dire. Lu
    depuis l'état, sans réseau."""
    if not active():
        return None
    d = depot(res)
    if d is None:
        return None
    v = lis_etat(d)
    accroc = v.get("accroc")
    if not isinstance(accroc, str):
        return None
    r = v.get("en_retard")
    retard = r if (isinstance(r, int) and not isinstance(r, bool) and r > 0) else 0
    depuis = ""
    t = _nombre(v.get("retard_depuis"))
    if t is not None:
        import datetime
        try:
            depuis = datetime.datetime.fromtimestamp(int(t)).strftime(" depuis %d/%m %H:%M")
        except (OverflowError, OSError, ValueError):
            depuis = ""
    return _quoi() + ", dernier passage : %s.%s" % (
        accroc,
        (" %d enregistrement(s) pas encore envoyé(s)%s." % (retard, depuis)) if retard > 0 else "")


def renvoi(depot, b):
    """Le texte qui renvoie l'agent vers son humain, en fin de tour. `None` quand
    rien ne demande un humain (hors ligne : on le dit, on ne bloque pas)."""
    a = b.accroc
    if a is None:
        return None
    if a.genre == "Conflit":
        cle, quoi = "conflit|" + "|".join(a.detail), phrase(a)
    elif a.genre == "Bloque":
        cle, quoi = "bloque|%s" % a.detail, phrase(a)
    elif a.genre == "Sensible":
        return ("sensible|" + "|".join(a.detail),
                "attente : la synchronisation du dépôt est ARRÊTÉE — %s.\n\n"
                "Rien n'est envoyé. Retire ce fichier du suivi de git sans l'effacer, ajoute-le aux fichiers "
                "ignorés, enregistre ; l'envoi repart au tour suivant. Si l'historique déjà envoyé le contient, "
                "dis-le à ton humain : c'est lui qui décide de la suite." % phrase(a))
    else:
        return None
    return (cle,
            "attente : la mémoire partagée n'a pas pu intégrer le travail de l'autre poste — %s.\n\n"
            "RIEN N'EST PERDU : tes enregistrements restent chez toi, les siens sur le distant, et RIEN n'est envoyé "
            "tant que ce n'est pas réglé. Rien n'a été écrasé ni forcé.\n\n"
            "Pose-le à ton humain, en une question fermée : pour chaque passage en double, garder (1) sa version, "
            "(2) celle de l'autre poste, ou (3) les deux réunies. Une fois répondu, dans `%s` : `git merge @{u}`, "
            "résous selon sa réponse, enregistre — l'envoi repart tout seul au tour suivant." % (quoi, depot))
