# -*- coding: utf-8 -*-
"""LA GARDE DES FAITS DES AGENTS EXPERTS (B16) — ce que @user donne se note le jour même.

Demandé par @user le 12/10/2026. Chez Legal, la règle « un fait donné se note
dans les faits » n'était qu'écrite : associés, capital, banque, TVA sont restés
QUATRE JOURS dans la seule conversation. Une règle qu'aucun mécanisme ne porte
se lit comme tenue, parce que rien ne la contredit jamais.

CE QUE LA GARDE FAIT. En fin de tour, pour un agent au profil expert
(`HARNAIS_PROFIL=expert`) : si @user a écrit quelque chose de NEUF depuis le
dernier passage, un juge lit ses messages et les fiches de l'agent, et rend la
liste des faits donnés. La fin de tour est refusée si l'un d'eux n'est noté
nulle part, ou si un fait qui identifie quelqu'un est dans une fiche PARTAGÉE.

POURQUOI UN JUGE ET PAS DES MOTS-CLÉS. Mesuré le 12/10/2026 sur les 86 messages
de @user à Legal : un détecteur à chiffres, dates et noms propres en signale 47
— plus d'un sur deux — et en rate ; aucun indice ne sépare les tours où un fait a
été noté des autres (31 des 71 tours sans écriture portent un nombre de quatre
chiffres). Un garde qui renvoie au travail un tour sur deux sans raison apprend
à l'ignorer. Le juge est celui du relecteur — Sonnet, sans outil, dans un dossier
jetable, `HARNAIS_JUGE` posé pour que ses propres hooks se taisent.

CE QUI IDENTIFIE QUELQU'UN — numéros, adresses, état civil, montants payés — ne
va jamais dans une fiche partagée : le dépôt part sur GitHub et chez l'autre
personne. Il va dans le REGISTRE LOCAL (`local/registre.md` à côté des faits),
que le dépôt doit ignorer. La garde le vérifie : un registre que git suit n'est
pas local.

FAIL-OPEN, MAIS PAS MUET. Un juge qui ne répond pas (réseau, délai, réponse
illisible) ne bloque rien — un garde qui empêche de travailler parce que son
instrument est en panne se fait retirer. Mais la panne s'écrit au journal des
blocages (`B16-muet`) et le briefing la redit : un silence ne doit pas se lire
comme « aucun fait oublié ».

UNE FOIS PAR ÉTAT, comme les autres gardes d'état : le même ensemble de faits
manquants ne renvoie qu'une fois. Au passage suivant, le juge relit — c'est ce qui
prouve que l'agent a VRAIMENT noté, pas seulement promis.
"""
import os

DELAI_JUGE = 25            # s — la fin de tour est coupée à 40 s (hooks/copilot.json)
MAX_MESSAGE = 6000         # caractères par message de @user transmis au juge
MAX_FICHES = 60000         # caractères de fiches transmis au juge
MAX_LOCAL = 20000
REGISTRE = os.path.join("local", "registre.md")

# Ce qui n'est jamais un message de @user, même arrivé par la même porte.
_PREFIXES_HORS = ("<", "Stop hook feedback", "[Request interrupted", "Caveat:",
                  "This session is being continued")
_TRIVIAUX = {"oui", "non", "ok", "go", "merci", "vas-y", "continue", "stop", "d'accord",
             "ok merci", "oui oui", "parfait", "super", "top", "c'est bon ?", "c est bon ?"}


def actif():
    import socle
    return socle.profil_expert()


# ── les messages de @user ──────────────────────────────────────────────────

def _sans_balises(t):
    """Retire les blocs `<system-reminder>…</system-reminder>` qu'injecte l'outil."""
    import re
    return re.sub(r"<system-reminder>.*?</system-reminder>", "", t, flags=re.S).strip()


def messages_maxime(chemin, depuis):
    """Les messages tapés par @user, après l'entrée `depuis`, dans la fin du
    journal de session de Copilot (`events.jsonl` : `user.message`, texte dans
    `data.content`). Sans repère (ou repère hors de la fin lue) : le DERNIER
    seulement — une garde qu'on active ne juge pas tout l'historique d'un coup.

    Rend [(repère, texte)]. Le repère est l'`id` de l'événement quand le journal
    en porte un, sinon une empreinte de la ligne (NON MESURÉ : la forme exacte des
    identifiants d'événement de Copilot). Ce qui n'est pas de lui est écarté :
    renvois de fin de tour (leur pied), messages de pair et notifications
    (balisés), commandes `/…`."""
    import hashlib
    import json
    import attente
    if not isinstance(chemin, str) or not chemin:
        return []
    try:
        with open(chemin, "rb") as f:
            taille = os.fstat(f.fileno()).st_size
            f.seek(max(0, taille - 3000000))
            brut = f.read().decode("utf-8", "replace")
    except (OSError, ValueError):
        return []
    tous = []
    for l in brut.split("\n"):
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if not isinstance(e, dict) or e.get("type") != "user.message":
            continue
        d = e.get("data")
        texte = d.get("content") if isinstance(d, dict) else None
        if not isinstance(texte, str) or attente.MARQUE_RENVOI in texte:
            continue
        texte = _sans_balises(texte)
        if not texte or texte.startswith(_PREFIXES_HORS) or texte.startswith("/"):
            continue
        u = e.get("id") if isinstance(e.get("id"), str) else hashlib.sha1(
            l.strip().encode("utf-8", "replace")).hexdigest()[:16]
        tous.append((u, texte))
    if depuis:
        for i, (u, _) in enumerate(tous):
            if u == depuis:
                return tous[i + 1:]
    return tous[-1:]


def a_juger(messages):
    """Les messages qui peuvent porter un fait : pas un « oui », pas un « ok »."""
    garde = []
    for u, t in messages:
        court = t.strip().lower().rstrip(" .!")
        if len(court) < 12 or court in _TRIVIAUX:
            continue
        garde.append((u, t))
    return garde


# ── les fiches ──────────────────────────────────────────────────────────────

def registre_local(d_fact):
    """`local/registre.md`, À CÔTÉ des faits (dans `brain/`), jamais dedans : les
    faits partent avec le dépôt, le registre reste sur la machine."""
    return os.path.join(os.path.dirname(d_fact.rstrip("/\\")), REGISTRE)


def ignore_par_git(chemin):
    """Le dépôt qui contient ce chemin l'ignore-t-il ? `git check-ignore` répond
    même pour un fichier qui n'existe pas encore. Hors dépôt : vrai (rien à suivre)."""
    import subprocess
    d = os.path.dirname(chemin)
    while d and not os.path.isdir(d):
        d = os.path.dirname(d)
    try:
        r = subprocess.run(["git", "check-ignore", "-q", chemin], cwd=d or ".",
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    if r.returncode == 128:          # pas un dépôt
        return True
    return r.returncode == 0


def fiches(d_fact):
    """Toutes les fiches `*.md` des faits, sous-dossiers compris, dans l'ordre."""
    out = []
    for base, dossiers, noms in os.walk(d_fact):
        dossiers.sort()
        for n in sorted(noms):
            if n.endswith(".md"):
                out.append(os.path.join(base, n))
    return out


def _lis(p, plafond):
    try:
        with open(p, "rb") as f:
            return f.read(plafond * 4).decode("utf-8", "replace")[:plafond]
    except OSError:
        return ""


# ── le juge ─────────────────────────────────────────────────────────────────

def invite(messages, d_fact, registre):
    parts = []
    reste = MAX_FICHES
    for p in fiches(d_fact):
        if reste <= 0:
            break
        t = _lis(p, reste)
        reste -= len(t)
        parts.append("=== FICHE PARTAGÉE : %s ===\n%s" % (os.path.relpath(p, d_fact), t))
    local = _lis(registre, MAX_LOCAL) if os.path.isfile(registre) else ""
    msgs = "\n\n".join("--- message ---\n%s" % t[:MAX_MESSAGE] for _, t in messages)
    return (
        "Tu es un greffier. Tu ne parles à personne : tu rends UN objet JSON, rien d'autre.\n\n"
        "@user (le commanditaire) vient d'écrire à son agent expert les messages ci-dessous. "
        "Relève chaque FAIT DURABLE qu'il y DONNE sur le domaine de l'agent : la société, une "
        "personne, un contrat, un chiffre, une date, une décision arrêtée, un document reçu. "
        "N'en sont PAS : une question, une demande de travail, un avis, une hypothèse, ce qui ne "
        "concerne que la conversation ou les outils, ce que @user dit de l'agent lui-même.\n\n"
        "Pour chaque fait donné, dis s'il est déjà noté dans les fiches de l'agent ou dans son "
        "registre local (même reformulé), et s'il IDENTIFIE quelqu'un : un numéro (identité, "
        "banque, sécurité sociale, téléphone, immatriculation personnelle), une adresse "
        "personnelle, l'état civil (naissance, situation familiale), un montant payé à ou par une "
        "personne. Le nom et la fonction d'une personne, le capital, le nom de la banque ou le "
        "régime de TVA de la société n'identifient personne.\n\n"
        "=== MESSAGES DE MAXIME ===\n" + msgs + "\n\n"
        "=== FICHES PARTAGÉES DE L'AGENT ===\n" + ("\n\n".join(parts) or "(aucune)") + "\n\n"
        "=== REGISTRE LOCAL (jamais partagé) ===\n" + (local or "(vide)") + "\n\n"
        "Réponds par ce JSON et rien d'autre :\n"
        '{"faits": [{"fait": "<le fait, en une courte phrase SANS recopier un numéro ni une '
        'adresse>", "note": "partage" | "local" | "nulle-part", "identifiant": true | false}]}\n'
        'Aucun fait donné : {"faits": []}. Dans le doute sur « déjà noté », réponds "nulle-part".'
    )


def lis_verdict(texte):
    """Le JSON du juge, ou None. Un juge bavard, coupé ou hors-sujet n'est PAS un
    « aucun fait » : c'est un juge muet."""
    import json
    if not isinstance(texte, str):
        return None
    a, b = texte.find("{"), texte.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        v = json.loads(texte[a:b + 1])
    except ValueError:
        return None
    faits = v.get("faits") if isinstance(v, dict) else None
    if not isinstance(faits, list):
        return None
    out = []
    for f in faits:
        if not isinstance(f, dict) or not isinstance(f.get("fait"), str):
            return None
        note = f.get("note")
        if note not in ("partage", "local", "nulle-part"):
            return None
        out.append({"fait": " ".join(f["fait"].split())[:160], "note": note,
                    "identifiant": f.get("identifiant") is True})
    return out


def juge(texte_invite):
    """Le verdict du juge, ou None s'il ne répond pas.

    `HARNAIS_FAITS_SIMULE` remplace le juge pour les contrôles : `muet`, ou le
    JSON du verdict, ou le chemin d'un fichier qui le porte. Jamais de modèle
    appelé dans un contrôle."""
    import subprocess
    simule = os.environ.get("HARNAIS_FAITS_SIMULE")
    if simule is not None:
        if simule.strip() == "muet":
            return None
        if os.path.isfile(simule):
            simule = _lis(simule, 200000)
        return lis_verdict(simule)
    import copilot
    exe = copilot.executable()
    if exe is None:
        return None
    import socle
    ici = os.path.join(socle.socle(), "experts-juge")
    try:
        os.makedirs(ici, exist_ok=True)
    except OSError:
        return None
    env = dict(os.environ)
    env["HARNAIS_JUGE"] = "1"                 # ses propres hooks se taisent
    # LE JUGE NE TOUCHE À RIEN : une passe (`-p`), sans outils, sans instructions
    # du projet, sans serveurs MCP — comme le relecteur.
    c = [exe, "-p", texte_invite, "--silent", "--no-custom-instructions",
         "--disable-builtin-mcps", "--available-tools", "--no-ask-user",
         "--no-auto-update", "--no-remote-export"]
    modele = os.environ.get("HARNAIS_MODELE_JUGE", "").strip()
    if modele:
        c += ["--model", modele]
    try:
        r = subprocess.run(c, stdin=subprocess.DEVNULL, cwd=ici, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=DELAI_JUGE)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return lis_verdict(r.stdout.decode("utf-8", "replace"))


# ── la garde ────────────────────────────────────────────────────────────────

def _etat(ed, session):
    return os.path.join(ed, "%s.experts.json" % session)


def _lis_etat(f):
    import json
    try:
        with open(f, encoding="utf-8") as h:
            v = json.load(h)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def _ecris_etat(f, v):
    import json
    try:
        with open(f, "w", encoding="utf-8") as h:
            json.dump(v, h, ensure_ascii=False)
    except OSError:
        pass


def _sig(*parts):
    import hashlib
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def garde(data, d_fact, ed, session, affiche):
    """None quand tout est noté (ou rien à juger) ; sinon (message, code, détail).

    `affiche(chemin)` rend le chemin tel qu'on le nomme à l'agent. `code` vaut
    `B16-faits` ou `B16-local` ; un juge muet rend ("", "B16-muet", n) — le
    journal en garde la trace, la fin de tour passe."""
    if d_fact is None or not os.path.isdir(d_fact):
        return None
    f = _etat(ed, session)
    etat = _lis_etat(f)
    registre = registre_local(d_fact)

    # 1. UN REGISTRE LOCAL QUE GIT SUIT N'EST PAS LOCAL — vérifié sans juge.
    if os.path.isfile(registre) and not ignore_par_git(registre):
        s = _sig("local", registre)
        if etat.get("sig_local") != s:
            etat["sig_local"] = s
            _ecris_etat(f, etat)
            return (MSG_LOCAL.format(registre=affiche(registre),
                                     dossier=os.path.dirname(REGISTRE) + "/"),
                    "B16-local", "1")

    # 2. LES MESSAGES NEUFS DE MAXIME
    msgs = messages_maxime(data.get("transcript_path"), etat.get("vu"))
    if not msgs:
        return None
    dernier = msgs[-1][0]
    juges = a_juger(msgs)
    if not juges:
        etat["vu"] = dernier
        _ecris_etat(f, etat)
        return None

    verdict = juge(invite(juges, d_fact, registre))
    if verdict is None:
        # Deux essais pour les mêmes messages, puis on passe : un juge en panne
        # ne doit pas taxer chaque tour de 25 s.
        cle = _sig("muet", *[u for u, _ in juges])
        etat["muets"] = etat.get("muets", 0) + 1 if etat.get("cle_muet") == cle else 1
        etat["cle_muet"] = cle
        if etat["muets"] >= 2:
            etat["vu"] = dernier
        etat["muet_total"] = etat.get("muet_total", 0) + 1
        _ecris_etat(f, etat)
        return ("", "B16-muet", str(etat["muets"]))

    manquants = [x for x in verdict if x["note"] == "nulle-part"]
    mal_ranges = [x for x in verdict if x["identifiant"] and x["note"] == "partage"]
    etat["muet_total"] = 0
    if not manquants and not mal_ranges:
        etat["vu"] = dernier
        etat.pop("sig", None)
        _ecris_etat(f, etat)
        return None
    s = _sig(*([u for u, _ in juges] + sorted(x["fait"] for x in manquants)
               + ["!"] + sorted(x["fait"] for x in mal_ranges)))
    if etat.get("sig") == s:
        # Déjà renvoyé pour ce même état : une garde qui mord une fois a fait son
        # travail. Si l'agent juge que ce n'est pas un fait, il l'a dit à @user.
        etat["vu"] = dernier
        _ecris_etat(f, etat)
        return None
    etat["sig"] = s
    _ecris_etat(f, etat)
    lignes = []
    for x in manquants[:6]:
        lignes.append("  · %s%s" % (x["fait"], "  — identifiant : registre local"
                                    if x["identifiant"] else ""))
    texte = ""
    if manquants:
        texte = MSG_FAITS.format(liste="\n".join(lignes),
                                 fiches=affiche(d_fact), registre=affiche(registre))
    if mal_ranges:
        texte += (("\n\n" if texte else "attente : ") + MSG_MAL_RANGES.format(
            liste="\n".join("  · %s" % x["fait"] for x in mal_ranges[:6]),
            registre=affiche(registre)))
    return (texte, "B16-faits", str(len(manquants) + len(mal_ranges)))


def rappel(ed, session_quelconque=None):
    """Pour le briefing : le juge est-il muet depuis plusieurs tours ? Lu dans les
    états de session les plus récents, sans réseau."""
    import glob
    pires = 0
    try:
        etats = sorted(glob.glob(os.path.join(ed, "*.experts.json")),
                       key=os.path.getmtime, reverse=True)[:3]
    except OSError:
        return None
    for e in etats:
        pires = max(pires, _lis_etat(e).get("muet_total", 0))
    if pires >= 3:
        return ("garde des faits : le juge n'a pas répondu sur les %d derniers tours où "
                "@user a écrit — ce qu'il a donné n'a PAS été vérifié. Note-le toi-même, "
                "et dis-le-lui." % pires)
    return None


MSG_FAITS = (
    "attente : @user t'a donné des faits que tes fiches ne portent pas encore :\n\n"
    "{liste}\n\n"
    "Un fait donné se note LE TOUR MÊME — une conversation s'oublie, une fiche reste. "
    "Écris-les dans la fiche de ton métier ({fiches}) : une ligne par fait, avec sa date "
    "et sa source — **dit** (@user l'a dit), **lu** (dans un document), **supposé**.\n\n"
    "Ce qui IDENTIFIE quelqu'un — numéros, adresses, état civil, montants payés — ne va "
    "jamais dans une fiche partagée : elle part avec le dépôt. Il va dans le registre "
    "local ({registre}), que le dépôt ignore.\n\n"
    "Si l'un d'eux n'est pas un fait (une hypothèse, une question), dis-le à @user en "
    "une phrase au lieu de l'écrire."
)

MSG_MAL_RANGES = (
    "ces faits IDENTIFIENT quelqu'un et sont dans une fiche partagée :\n\n{liste}\n\n"
    "Déplace-les dans le registre local ({registre}) et retire-les de la fiche — "
    "l'historique du dépôt les garde : si le dépôt a déjà été envoyé, dis-le à @user."
)

MSG_LOCAL = (
    "attente : le registre local ({registre}) est SUIVI par le dépôt. Ce qui identifie "
    "quelqu'un partirait avec lui — sur GitHub, et chez l'autre personne.\n\n"
    "Ajoute `{dossier}` au `.gitignore` du dépôt qui le contient ; s'il a déjà été "
    "enregistré, retire-le de l'index (`git rm --cached`) sans l'effacer, et dis-le à "
    "@user."
)
