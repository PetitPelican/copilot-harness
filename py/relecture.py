# -*- coding: utf-8 -*-
"""LE RELECTEUR — un juge qui n'a pas écrit ce qu'il relit.

Port de `harnais/src/relecture.rs` (Rust, 0.12.8).

Aucun des quatre systèmes étudiés le 09/09/2026 n'a de juge du fond qui se
déclenche tout seul. ECC énonce le principe mieux que nous — « le relecteur
n'a jamais écrit le code qu'il relit, c'est ce qui élimine le biais
d'auteur » — et ne le câble pas : sa commande de revue relit dans le fil qui
vient d'écrire. mattpocock le dit aussi — « un même contexte qui se relit
lui-même n'est pas une relecture, c'est du biais de confirmation » — et sa
compétence d'implémentation appelle la revue dans sa propre session.

Ils ont la doctrine, nous avons la gâchette : un hook de fin de tour
déterministe. Ce programme est ce qu'il déclenche.

LA BARRIÈRE N'EST PAS UNE PERMISSION, C'EST L'IGNORANCE. Le juge reçoit
l'affirmation, ce qui l'établit et sa vérification. Rien du raisonnement qui
y a mené. Il ne peut pas confirmer ce qu'il n'a pas vu.
"""
import os
import re
import subprocess
import sys
import time

import socle

# Plafond journalier. Le reproche que mattpocock fait à sa propre revue est
# qu'elle s'appelle elle-même : « un rapport a atteint plus de 50 agents ».
# Ici le nombre d'ouvriers lancés dans la journée est borné, point.
PLAFOND_JOUR = 12

# Un seul ouvrier à la fois. Le verrou porte l'heure de pose : un verrou
# oublié par un processus tué ne doit pas bloquer le dispositif pour toujours.
VERROU_PERIME_S = 900

# Le modèle du juge : celui du CLI Copilot par défaut, ou `HARNAIS_MODELE_JUGE`.

# `str::trim` du Rust : les caractères White_Space d'Unicode. `str.strip()`
# retirerait aussi \x1c à \x1f, que le Rust laisse.
_BLANCS = "\t\n\x0b\x0c\r \x85\xa0        " \
          "        　"


def _trim(s):
    return s.strip(_BLANCS)


def _lignes(t):
    """`str::lines` du Rust : coupe sur `\\n`, retire un `\\r` qui précède le
    `\\n`, et ne compte pas de ligne vide après le dernier `\\n`."""
    parts = t.split("\n")
    fin = parts.pop()
    out = [p[:-1] if p.endswith("\r") else p for p in parts]
    if fin != "":
        out.append(fin)
    return out


def _u64(s):
    """`str::parse::<u64>` : chiffres ASCII, un `+` facultatif, pas de débordement."""
    if re.fullmatch(r"\+?[0-9]+", s) is None:
        return None
    v = int(s)
    return v if v < 2 ** 64 else None


def maintenant():
    return int(time.time())


def jour():
    # Pas de dépendance pour une date : le compteur journalier n'a besoin que
    # d'une clé qui change chaque jour, pas d'un calendrier.
    return "%d" % (maintenant() // 86400)


def decoupe(t):
    """Lecture d'un fichier « clé: valeur » suivi de sections `--- nom ---`.
    Format volontairement lisible à l'œil : une demande de relecture doit
    pouvoir être ouverte et comprise sans outil."""
    tetes, sections = {}, {}
    courante, tampon = "", ""
    for l in _lignes(t):
        n = _trim(l)
        if n.startswith("--- ") and n.endswith(" ---"):
            if courante != "":
                sections[courante] = _trim(tampon)
            courante = _trim(n[4:len(n) - 4])
            tampon = ""
        elif courante == "":
            if ":" in n:
                k, v = n.split(":", 1)
                tetes[_trim(k)] = _trim(v)
        else:
            tampon += l + "\n"
    if courante != "":
        sections[courante] = _trim(tampon)
    return tetes, sections


def _majuscule_ascii(s):
    # `char::to_ascii_uppercase` : « é » reste « é » (`str.upper()` en ferait « É »).
    return "".join(chr(ord(c) - 32) if "a" <= c <= "z" else c for c in s)


def _apres_octets(s, n):
    # `s[n.min(s.len())..]` du Rust : l'index est en OCTETS UTF-8.
    return _trim(s.encode("utf-8")[n:].decode("utf-8", "replace"))


def normalise(sortie):
    """Le jeu fermé. Toute réponse qui n'y entre pas devient INSUFFISANT — jamais
    CONFIRME. Un juge qu'on ne comprend pas ne vaut pas un accord."""
    brut = _trim(sortie)
    premiere = ""
    for l in _lignes(brut):
        if _trim(l) != "":
            premiere = _trim(l)
            break
    haut = _majuscule_ascii(premiere)
    # On retire les accents des trois mots attendus plutôt que d'espérer que le
    # modèle les pose : « CONFIRMÉ » et « CONFIRME » doivent valoir pareil.
    sans = haut.replace("É", "E").replace("È", "E")
    # STRICT (repris du harnais Copilot) : UNE ligne, et le mot exact. « CONFIRME
    # pas vraiment », « CONFIRMERA » ou un CONFIRME suivi d'une autre ligne ne
    # confirment rien — l'ancien `startswith` les comptait comme des accords.
    une = len(_lignes(brut)) == 1
    if une and sans == "CONFIRME":
        return "CONFIRME"
    elif une and sans.startswith("CONTREDIT "):
        return "CONTREDIT " + _apres_octets(premiere, 9)
    elif une and sans.startswith("INSUFFISANT "):
        return "INSUFFISANT " + _apres_octets(premiere, 11)
    else:
        # LE POINT LE PLUS IMPORTANT DU PROGRAMME. Un juge muet, coupé,
        # hors-sujet ou bavard n'est PAS un accord. C'est la même règle que
        # MUET pour les vérifications : un contrôle qui n'aboutit pas ne se lit
        # jamais comme un constat confirmé.
        return ("INSUFFISANT le relecteur n'a pas rendu un verdict lisible (%s)"
                % premiere[:80])


def invite(criteres, demande):
    return (
        "Tu es un relecteur. Tu n'as PAS écrit ce qui suit et tu n'as accès à "
        "rien d'autre que ce message : ni la conversation, ni le dépôt, ni le "
        "raisonnement qui a mené à cette affirmation.\n\n"
        "Tes critères, que tu ne peux pas modifier :\n\n" + criteres + "\n\n"
        "=== CE QUE TU DOIS JUGER ===\n\n" + demande + "\n\n=== FIN ===\n\n"
        "Réponds par UNE SEULE LIGNE, commençant par exactement l'un de ces trois "
        "mots : CONFIRME, ou CONTREDIT suivi du motif en une phrase, ou INSUFFISANT "
        "suivi de ce qui manque. Aucun préambule, aucune explication au-delà de cette "
        "ligne. Dans le doute, INSUFFISANT."
    )


def _erreur_io(e):
    # Le texte de `io::Error` du Rust : « No such file or directory (os error 2) ».
    return "%s (os error %s)" % (e.strerror or "erreur", e.errno)


def juge(invite_):
    """Lance le juge — le CLI Copilot en une passe (`copilot -p`), sans outils,
    sans instructions du projet, sans serveurs MCP. Rend le verdict normalisé —
    et jamais une erreur silencieuse : un échec d'exécution est un INSUFFISANT
    explicite."""
    import copilot
    exe = copilot.executable()
    if exe is None:
        return ("INSUFFISANT CLI Copilot introuvable : poser HARNAIS_COPILOT, installer copilot "
                "dans PATH ou le SDK")
    c = [exe, "-p", invite_, "--silent", "--no-custom-instructions", "--disable-builtin-mcps",
         "--available-tools", "--no-ask-user", "--no-auto-update", "--no-remote-export"]
    modele = os.environ.get("HARNAIS_MODELE_JUGE", "").strip()
    if modele:
        c += ["--model", modele]
    env = dict(os.environ)
    # Le juge tourne dans le dossier de l'agent : sans ça, ses propres hooks
    # (briefing, fin de tour) partiraient pendant qu'il juge.
    env["HARNAIS_JUGE"] = "1"
    try:
        r = subprocess.run(c, env=env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        return "INSUFFISANT le relecteur n'a pas pu être lancé (%s)" % _erreur_io(e)
    if r.returncode == 0:
        return normalise(r.stdout.decode("utf-8", "replace"))
    return "INSUFFISANT le relecteur n'a pas abouti (code %d)" % (
        r.returncode if r.returncode >= 0 else -1)


def _lire(p):
    try:
        with open(p, "rb") as f:
            return f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def criteres():
    """LES CRITÈRES SONT LIVRÉS, JAMAIS ÉCRITS PAR L'AGENT — et il faut donc les
    trouver là où ils sont livrés, pas là où l'agent écrit. Deux endroits, dans
    cet ordre : le dossier du plugin quand on tourne en plugin, et **à côté du
    programme** sinon — c'est le cas du CTO, qui appelle le programme par son
    chemin sans passer par le plugin. Sans cette seconde adresse, le relecteur
    se serait tu pour toujours chez lui, en annonçant « critères introuvables ».

    « À côté du programme » : le lanceur (`bin/`) et la racine du dépôt, comme
    le binaire Rust cherchait à côté de lui et dans son parent.

    Ce qu'on NE cherche PAS : le dossier d'état de l'agent. Y mettre les
    critères reviendrait à laisser celui qu'on juge écrire les conditions de son
    acceptation. La barrière n'est pas un droit de fichier — le dépôt
    m'appartient — c'est que les changer laisse une trace dans l'historique."""
    cands = []
    r = socle.livre()
    if r is not None:
        cands.append(os.path.join(r, "criteres-relecture.md"))
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cands.append(os.path.join(racine, "bin", "criteres-relecture.md"))
    cands.append(os.path.join(racine, "criteres-relecture.md"))
    for c in cands:
        t = _lire(c)
        if t is not None and _trim(t) != "":
            return t
    return ""


def compteur_jour(dossier):
    f = os.path.join(dossier, ".compteur")
    j = jour()
    vu, n = "", 0
    t = _lire(f)
    if t is not None:
        t = _trim(t)
        if " " in t:
            a, b = t.split(" ", 1)
            vu = a
            v = _u64(b)
            n = v if v is not None else 0
    if vu != j:
        n = 0
    return j, n


def _ecrire(p, texte):
    try:
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(texte)
        return True
    except OSError:
        return False


def _supprimer(p):
    try:
        os.remove(p)
    except OSError:
        pass


def main(args):
    dossier = os.path.join(socle.socle(), "relecture")
    try:
        os.makedirs(dossier, exist_ok=True)
    except OSError:
        return  # fail-open : un relecteur qui empêche de travailler est pire que pas de relecteur
    sec = "--sec" in args

    # ── un seul ouvrier à la fois ─────────────────────────────────────────
    verrou = os.path.join(dossier, ".verrou")
    t = _lire(verrou)
    if t is not None:
        pose = _u64(_trim(t))
        pose = pose if pose is not None else 0
        if max(maintenant() - pose, 0) < VERROU_PERIME_S:
            print("un relecteur tourne déjà")
            return

    try:
        attente = sorted(
            os.path.join(dossier, nom) for nom in os.listdir(dossier)
            if os.path.splitext(nom)[1] == ".demande")
    except OSError:
        attente = []
    if not attente:
        print("rien à relire")
        return

    j, n = compteur_jour(dossier)
    if n >= PLAFOND_JOUR:
        print("plafond journalier atteint (%d relectures)" % n)
        return

    crit = criteres()
    if _trim(crit) == "":
        # SANS CRITÈRES, PAS DE JUGEMENT. On ne se rabat pas sur « le bon sens
        # du modèle » : c'est précisément ce que les critères remplacent.
        print("critères introuvables — aucune relecture (et c'est voulu)")
        return

    _ecrire(verrou, str(maintenant()))
    faits = 0
    for d in attente[:PLAFOND_JOUR - n]:
        brut = _lire(d)
        if brut is None:
            continue
        tetes, _ = decoupe(brut)
        # ON NE RELIT JAMAIS UNE RELECTURE. Une demande qui porterait un verdict
        # serait une revue de revue — le chemin par lequel mattpocock est monté
        # à cinquante agents.
        if "verdict_relecteur" in tetes:
            _supprimer(d)
            continue
        if sec:
            verdict = "CONFIRME (simulation, aucun juge lancé)"
        else:
            verdict = juge(invite(crit, brut))
        cible = os.path.splitext(d)[0] + ".verdict"
        _ecrire(cible, "verdict_relecteur: %s\nrendu_le: %d\nsur: %s\n"
                % (verdict, maintenant(), tetes.get("id", "?")))
        _supprimer(d)
        faits += 1
        print("%s → %s" % (os.path.basename(d), verdict))
        sys.stdout.flush()
    _ecrire(os.path.join(dossier, ".compteur"), "%s %d" % (j, n + faits))
    _supprimer(verrou)
