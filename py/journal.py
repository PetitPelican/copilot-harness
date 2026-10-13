# -*- coding: utf-8 -*-
"""LE JOURNAL — hook PostToolUse (Bash), sur `git commit`.

Port de `harnais/src/journal.rs` (0.12.8).

Écrit ce qui a été commité dans `.logs/<jour>.md`, et
`.logs/<jour>-<agent>.md` en multi-agents. Il répond à une question que
l'instantané d'état ne sait pas traiter : **qu'est-ce qui a été fait, jour par
jour ?** Un instantané ne dit pas ce qu'on a fait mardi ; un historique ne dit
pas où on en est. D'où les deux.

POURQUOI UN HOOK ET PAS UNE COMPÉTENCE. Ce travail dépendait d'une commande
qu'il fallait penser à lancer. Un journal tenu quand on y pense a des trous
exactement les jours chargés — ceux qu'on aurait le plus besoin de relire.

COMMENT IL SAIT QU'UN COMMIT A EU LIEU. Il ne lit pas le résultat de la
commande : il regarde `HEAD`. Si le commit a échoué, `HEAD` n'a pas bougé,
son empreinte est déjà dans le journal, et rien n'est écrit. Aucune
connaissance de la forme de la réponse n'est nécessaire, et un double appel
ne produit pas deux entrées.

**fail-open et silencieux** : un journal est un confort, il ne doit jamais
empêcher de travailler.

VITESSE. Ce hook tourne après CHAQUE commande Bash ; presque aucune n'est un
commit. Le chemin « rien à faire » ne doit donc importer ni `json` (qui tire
`re`), ni `re`, ni `subprocess` : le texte brut est regardé d'abord. Voir
`main()`.
"""

DOSSIER = ".logs"
# Nombre de fichiers listés dans une entrée avant « … ».
MAX_FICHIERS = 40

# Les blancs de Rust (`char::is_whitespace`, propriété White_Space) — pas ceux de
# `str.strip()` de Python, qui y ajoute \x1c-\x1f.
BLANCS = ("\t\n\x0b\x0c\r \x85\xa0       "
          "         　")


def git(args):
    """`git <args>` depuis le dossier courant : la sortie rognée, ou None si git
    échoue ou n'existe pas."""
    import subprocess
    try:
        o = subprocess.run(["git"] + list(args), stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except (OSError, ValueError):
        return None
    if o.returncode == 0:
        return o.stdout.decode("utf-8", "replace").strip(BLANCS)
    return None


def est_un_commit(cmd):
    """Est-ce une commande de commit ? Même motif que la version Python :
    `git` puis `commit`, aux frontières de mot."""
    # Deux sous-chaînes nécessaires au motif : sans elles, on ne paie pas `re`.
    if "git" not in cmd or "commit" not in cmd:
        return False
    import re
    return re.search(r"\bgit\b.+\bcommit\b", cmd) is not None


def suffixe_agent(racine, projet):
    """En MULTI-agents, le nom de l'agent ; sinon la chaîne vide.

    MESURÉ le 05/09/2026. Depuis qu'un agent a son propre répertoire de travail,
    la racine rendue par git est celle DU WORKTREE : deux agents écriraient deux
    journaux de même chemin relatif, suivis tous les deux, invisibles l'un à
    l'autre, et que la première fusion met en collision. Un journal qui bloque
    une fusion a cessé d'être un confort.

    `racine` et `projet` sont des `str` ; `projet` peut être None.
    """
    if not projet:
        return ""
    import memoire
    a = memoire._canon(projet)
    b = memoire._canon(racine)
    # Comme `match (p.canonicalize(), racine.canonicalize())` : un seul des deux
    # introuvable et on compare les chemins tels quels.
    if a is None or b is None:
        a, b = projet, racine
    rel = memoire._strip_prefix(a, b)
    if rel is None:
        return ""
    if len(rel) != 2 or rel[0] != "agents":
        return ""
    out = []
    tiret = False
    for c in rel[1]:
        if (c.isascii() and c.isalnum()) or c in "._-":
            out.append(c)
            tiret = False
        elif not tiret:
            out.append("-")
            tiret = True
    return "-" + "".join(out).strip("-")


def _mot(c):
    # `char::is_alphanumeric` en Rust, plus `_`.
    return c.isalnum() or c == "_"


def deja_journalise(deja, court):
    """L'empreinte est-elle déjà dans le journal ? Frontières de mot des deux
    côtés, comme `\\b` en Python : c'est le garde-fou contre les doublons."""
    if not court:
        return False
    n = len(court)
    i = deja.find(court)
    while i != -1:
        avant_ok = (i == 0) or not _mot(deja[i - 1])
        apres_ok = (i + n == len(deja)) or not _mot(deja[i + n])
        if avant_ok and apres_ok:
            return True
        i = deja.find(court, i + 1)
    return False


def bloc(heure, court, branche, amend, sujet, touches, auteur):
    """Le bloc écrit dans le journal. Séparé pour être éprouvé sans dépôt git."""
    l = [
        "",
        "## %s · `%s` · %s%s" % (heure, court, branche,
                                 " · réécriture (`--amend`)" if amend else ""),
        "",
        "**%s**" % sujet,
        "",
    ]
    for f in touches[:MAX_FICHIERS]:
        l.append("- `%s`" % f)
    if len(touches) > MAX_FICHIERS:
        l.append("- … et %d autres fichiers" % (len(touches) - MAX_FICHIERS))
    l.append("")
    l.append("<!-- %s -->" % auteur)
    return "\n".join(l)


def main(entree):
    # LE CHEMIN « RIEN À FAIRE », SANS IMPORT. La commande doit contenir
    # `commit` pour être un commit ; le texte JSON ne la déguise qu'avec une
    # échappation `\uXXXX`, que l'on envoie alors au chemin complet. Ce test de
    # sous-chaîne ne laisse donc jamais passer un commit que le Rust verrait.
    if "commit" not in entree and "\\u" not in entree:
        return
    import json
    try:
        d = json.loads(entree, parse_constant=_refuse)
    except (ValueError, RecursionError):
        return
    if not isinstance(d, dict):
        return
    ti = d.get("tool_input")
    cmd = ti.get("command") if isinstance(ti, dict) else None
    if not isinstance(cmd, str):
        cmd = ""
    if not est_un_commit(cmd):
        return
    import os
    racine = git(["rev-parse", "--show-toplevel"])
    if not racine:
        return
    # `%x09` = tabulation : un séparateur qu'un sujet de commit ne contient pas.
    tete = git(["log", "-1", "--date=short",
                "--format=%h%x09%ad%x09%cI%x09%s%x09%an"])
    if tete is None:
        return
    ch = tete.split("\t")
    if len(ch) != 5:
        return
    court, jour, iso, sujet, auteur = ch

    fichier = os.path.join(racine, DOSSIER, "%s%s.md" % (
        jour, suffixe_agent(racine, os.environ.get("CLAUDE_PROJECT_DIR"))))
    try:
        with open(fichier, encoding="utf-8", newline="") as h:
            deja = h.read()
    except (OSError, ValueError):
        deja = ""
    if deja_journalise(deja, court):
        return

    brut = git(["show", "--name-only", "--format=", "HEAD"]) or ""
    # Le journal ne se journalise pas : l'entrée de la veille est commitée
    # avec le travail du jour, et se retrouverait dans la liste.
    touches = [f for f in _lignes(brut)
               if f.strip(BLANCS) and not f.startswith(DOSSIER + "/")]

    heure = iso[11:16] if len(iso) >= 16 else "??:??"
    branche = git(["rev-parse", "--abbrev-ref", "HEAD"])
    if branche is None:
        branche = "?"
    corps = bloc(heure, court, branche, "--amend" in cmd, sujet, touches, auteur)

    try:
        os.makedirs(os.path.dirname(fichier) or racine, exist_ok=True)
    except OSError:
        pass
    if not deja:
        entete = ("# Journal — %s\n\nÉcrit par le hook `journal` à chaque commit. "
                  "**Append-only** : on n'y réécrit rien, on n'y compresse rien.\n" % jour)
        try:
            with open(fichier, "w", encoding="utf-8", newline="") as h:
                h.write("%s%s\n" % (entete, corps))
        except OSError:
            pass
    else:
        try:
            with open(fichier, "a", encoding="utf-8", newline="") as h:
                h.write(corps + "\n")
        except OSError:
            pass


def _refuse(c):
    # serde_json refuse NaN et Infinity ; `json.loads` de Python les accepte.
    raise ValueError(c)


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
