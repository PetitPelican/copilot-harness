# -*- coding: utf-8 -*-
"""LE VERROU DES CONSIGNES — hook PreToolUse (Edit, Write, Bash, PowerShell).

Porté du harnais Claude (`consignes.py`). Décision du commanditaire, 14/10/2026 : « je ne veux pas que
les agents touchent à leur claude.md […] interdis à part à CTO et à toi de toucher
aux claude.md ». Le fichier de consignes — celui de l'atelier, de chaque projet, du
rôle de chaque agent — est lu à chaque démarrage : il dit à l'agent qui il est.
Jusqu'ici la règle n'était qu'écrite ; elle est désormais tenue.

CE QUI EST GARDÉ CHEZ COPILOT. Copilot lit trois noms de fichiers (COMMENT-CA-MARCHE.md,
« Qui parle » et section 3) :
  · `AGENTS.md` — la méthode à la racine de l'atelier, le rôle du CTO, le rôle de chaque
    agent (`agents/<nom>/AGENTS.md`) ;
  · `CLAUDE.md` — que Copilot lit aussi, « sans ordre de priorité général » ;
  · `copilot-instructions.md` — la copie de la méthode que `adopte` pose dans
    `.github/`, la seule que Copilot découvre dans le dépôt.
Le verrou porte sur ces NOMS, pas sur un chemin : il tient dans tous les projets,
présents et à venir, sans liste à entretenir. La mémoire de travail (état, tâches,
faits) n'est pas concernée. Les profils `.github/agents/<nom>.agent.md` sont déjà
fermés aux agents par leur périmètre (`agent.CONTROLE`) : ils ne sont pas ajoutés ici.
Non couverts, dit et non deviné : les fichiers d'instructions par chemin
(`.github/instructions/*.instructions.md`), que ce dépôt ne documente pas.

QUI ÉCRIT. Seuls les agents nommés dans `GARDIENS` — le CTO ; il n'y a pas d'agent
Harness dans un atelier Copilot. Le nom se compare sans la casse (`atelier-monte` crée
le dossier `cto`). L'agent est celui que le harnais résout comme partout ici
(`agent.session()` : le menu de l'app, le dossier de lancement, QA par défaut) ; sans
agents dans le projet, c'est le nom du dossier de travail, ou — à la racine d'une copie
de travail — celui du dépôt principal : l'app lance le CTO dans une copie dont le nom
n'est pas `cto`. Un appelant que le garde n'identifie pas n'est pas un gardien.

Les autres LISENT librement — `cat`, `Get-Content`, `grep`, `git diff` passent — mais
toute ÉCRITURE est refusée, avec la raison et à qui s'adresser. Une commande qui NOMME
le fichier n'est pas une commande qui l'ÉCRIT : QA s'est vu refuser l'ajout d'une ligne
à son todo parce que la ligne citait le fichier. On juge donc la CIBLE de chaque
écriture, jamais le texte.

POWERSHELL. `Set-Content` / `Add-Content` / `Out-File` / `Tee-Object` / `New-Item` /
`Remove-Item` / `Rename-Item` / `Move-Item` / `Copy-Item` (et leurs alias `sc`, `ac`,
`ni`, `ri`, `del`, `mi`, `cpi`…), les redirections `>` et `>>`, et `[IO.File]::WriteAllText(…)`
visent une cible : si c'est un de ces noms, c'est refusé. La valeur d'un `-Value`
n'est pas une cible. Non couvert : un chemin construit dans une variable
(`Set-Content $f …`), un script `.ps1` qui écrit à la place de l'agent.

**fail-open** sur une entrée illisible : un garde qui bloque ce qu'il ne
comprend pas se fait désactiver.
"""
import os
import re

GARDIENS = ("CTO",)

NOMS = ("agents.md", "claude.md", "copilot-instructions.md")
NOM = re.compile(r"agents\.md|claude\.md|copilot-instructions\.md", re.I)

# Une commande qui NOMME un fichier de consignes n'est pas une commande qui l'ÉCRIT :
# on juge la CIBLE de chaque écriture, jamais le texte.
INTERPRETES = re.compile(r"\b(python3?|node|perl|ruby|sh|bash|zsh|pwsh|powershell)\b")
# `open(f, 'w')` : le MODE, après une virgule. Chez Claude le motif était `open\([^)]*['"][wax+]`,
# qui prend pour un mode la première lettre d'un chemin en minuscule (`open('agents.md')`) :
# les noms de consignes d'ici s'écrivent aussi en minuscules.
ECRIT_SCRIPT = re.compile(r"\.write|write_text|\bopen\([^)]*,\s*(?:mode\s*=\s*)?['\"][rbt]*[wax+]|"
                          r"\bunlink\b|\bshutil\.|\bos\.(remove|rename|replace)\b|writeFile|"
                          r"appendFile|\brm\b|\bmv\b|>|"
                          r"(?i:Set-Content|Add-Content|Out-File|Remove-Item|WriteAll|AppendAll)")
TOUT_ARG = {"rm", "unlink", "truncate", "touch", "mv", "shred", "chmod",
            # PowerShell, alias compris
            "remove-item", "ri", "del", "erase", "clear-content", "clc", "set-content", "sc",
            "add-content", "ac", "out-file", "new-item", "ni", "rename-item", "rni", "ren",
            "rename", "move-item", "mi", "move", "set-itemproperty", "sp", "tee-object"}
DERNIER_ARG = {"cp", "ln", "install", "rsync", "ditto", "copy-item", "cpi", "copy"}
GIT_ECRIT = {"rm", "mv", "checkout", "restore", "apply", "am", "stash", "reset"}
# Les paramètres PowerShell dont la valeur est un contenu, pas une cible.
CONTENU_PS = {"-value", "-inputobject", "-encoding"}
DESTINATION_PS = {"-destination", "-dest", "-newname", "-filepath", "-literalpath", "-path"}
ECRIT_DOTNET = re.compile(r"\[(?:System\.)?IO\.File\]::(Write\w*|Append\w*|Delete|Move|Copy|"
                          r"Replace|Create\w*)\s*\(((?:[^()]|\([^()]*\))*)\)?", re.I)
CHAINE_PS = re.compile(r"""['"]([^'"\r\n]+)['"]""")
HERE_STRING = re.compile(r"@(['\"])[ \t]*\r?\n.*?\r?\n\1@", re.S)


def _nomme(tok):
    tok = tok.strip("'\"")
    return re.split(r"[\\/]", tok.rstrip("/\\"))[-1].lower() in NOMS


def _decoupe(cmd):
    """(texte sans les corps de heredoc, [(ligne qui ouvre, corps)])."""
    lignes = cmd.split("\n")
    out, corps, i = [], [], 0
    while i < len(lignes):
        l = lignes[i]
        out.append(l)
        fins = re.findall(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", l)
        i += 1
        for fin in fins:
            b = []
            while i < len(lignes) and lignes[i].strip() != fin:
                b.append(lignes[i])
                i += 1
            i += 1
            corps.append((l, "\n".join(b)))
    return "\n".join(out), corps


def _jetons(segment, powershell=False):
    import shlex
    if powershell:
        # Ni `\` échappement, ni parenthèses collées aux mots : `(Join-Path $d 'AGENTS.md')`.
        segment = re.sub(r"[()]", " ", segment)
    try:
        lex = shlex.shlex(segment, posix=True)
        lex.whitespace_split = True
        lex.commenters = ""
        if powershell:
            lex.escape = ""
        return list(lex)
    except ValueError:
        return segment.split()


def _sans_valeurs(args):
    """Les arguments d'une cmdlet, sans la valeur d'un `-Value` / `-InputObject` (un contenu)."""
    out, saute = [], False
    for a in args:
        if saute:
            saute = False
            continue
        if a.lower() in CONTENU_PS:
            saute = True
            continue
        out.append(a)
    return out


def _valeur_ps(args, noms):
    for i, a in enumerate(args):
        if a.lower() in noms and i + 1 < len(args):
            return args[i + 1]
        if ":" in a and a.lower().split(":", 1)[0] in noms:
            return a.split(":", 1)[1]
    return None


def ecrit_un_fichier_de_consignes(cmd, powershell=False):
    """La ligne ÉCRIT-elle (crée, modifie, déplace, supprime) un fichier de consignes ?"""
    if not NOM.search(cmd):
        return False
    if powershell:
        cmd = cmd.replace("`\r\n", " ").replace("`\n", " ")
        cmd = HERE_STRING.sub(" ", cmd)
        # Une méthode .NET qui écrit, avec un nom de consignes parmi ses chaînes.
        for m in ECRIT_DOTNET.finditer(cmd):
            # La CIBLE, pas le contenu : le chemin est le premier argument ; pour Move, Copy
            # et Replace, le second l'est aussi.
            cibles = CHAINE_PS.findall(m.group(2))[:2 if m.group(1).lower() in ("move", "copy", "replace") else 1]
            if any(_nomme(c) for c in cibles):
                return True
    texte, corps = _decoupe(cmd)
    # 1. Les redirections : seule leur CIBLE compte.
    for m in re.finditer(r"(?<![0-9<])>>?\|?\s*(\"[^\"]*\"|'[^']*'|[^\s;&|<>]+)", texte):
        if _nomme(m.group(1)):
            return True
    # 2. Les commandes, segment par segment.
    for seg in re.split(r"&&|\|\||[;|\n]", texte):
        tok = _jetons(seg, powershell)
        if not tok:
            continue
        k = 0
        while k < len(tok) and ("=" in tok[k] and not tok[k].startswith("-")):
            k += 1                                     # VAR=x devant la commande
        if k < len(tok) and tok[k] == "&":
            k += 1                                     # l'opérateur d'appel de PowerShell
        if k >= len(tok):
            continue
        prog = re.split(r"[\\/]", tok[k])[-1]
        prog = prog[:-4] if prog.lower().endswith(".exe") else prog
        prog_min = prog.lower()
        args = [a for a in tok[k + 1:] if not a.startswith(">")]
        if powershell:
            args = _sans_valeurs(args)
        noms = [a for a in args if not a.startswith("-")]
        if prog_min in TOUT_ARG and any(_nomme(a) for a in noms):
            return True
        if prog_min in DERNIER_ARG and noms and _nomme(noms[-1]):
            return True
        if powershell and prog_min in DERNIER_ARG:
            dest = _valeur_ps(args, DESTINATION_PS)
            if dest is not None and _nomme(dest):
                return True
        if powershell and prog_min in TOUT_ARG:
            cible = _valeur_ps(args, DESTINATION_PS)
            if cible is not None and _nomme(cible):
                return True
        if prog_min == "tee" and any(_nomme(a) for a in noms):
            return True
        if prog_min in ("sed", "perl") and any(a.startswith("-i") or (a.startswith("-") and "i" in a[1:] and prog_min == "perl")
                                               for a in args) and any(_nomme(a) for a in noms):
            return True
        if prog_min == "git":
            verbes = [a for a in noms if a in GIT_ECRIT]
            if verbes and any(_nomme(a) for a in noms):
                return True
        if INTERPRETES.fullmatch(prog_min or "") and ("-c" in args or "-e" in args
                                                       or "-command" in [a.lower() for a in args]):
            s = " ".join(args)
            if NOM.search(s) and ECRIT_SCRIPT.search(s):
                return True
    # 3. Un script passé en heredoc à un interprète : son texte EST le geste.
    for ouvre, b in corps:
        if INTERPRETES.search(ouvre.split("<<")[0]) and NOM.search(b) and ECRIT_SCRIPT.search(b):
            return True
    return False


# ── qui parle ────────────────────────────────────────────────────────────

def qui(dossier=None):
    """Les noms sous lesquels l'appelant peut se reconnaître gardien. Vide si le garde ne
    sait pas qui parle : un inconnu n'est pas un gardien."""
    import agent
    import memoire
    s = agent.session()
    if s is not None and s.agents:
        return [s.actif] if s.actif else []
    d = dossier or os.environ.get("COPILOT_PROJECT_DIR") or os.getcwd()
    try:
        d = os.path.realpath(d)
    except (OSError, ValueError):
        pass
    noms = [os.path.basename(d.rstrip("\\/"))]
    # À la racine d'une copie de travail : le nom du dépôt principal. Pas dans un
    # sous-dossier (`agents/PO` d'un projet qui s'appellerait `cto` n'est pas le CTO), et pas
    # dans un projet à plusieurs agents (c'est alors l'agent choisi qui parle).
    arbre = memoire.arbre_courant(d)
    try:
        a_la_racine = arbre is not None and os.path.realpath(arbre) == d
    except (OSError, ValueError):
        a_la_racine = False
    if a_la_racine and not agent.agents_du_projet(d):
        principal = memoire.racine_depot(d)
        if principal:
            noms.append(os.path.basename(os.path.realpath(principal).rstrip("\\/")))
    return noms


def est_gardien(dossier=None):
    gardiens = [g.lower() for g in GARDIENS]
    return any(n.lower() in gardiens for n in qui(dossier) if n)


def vise(chemin):
    return isinstance(chemin, str) and _nomme(chemin)


def _cibles(outil, ti):
    """Les chemins qu'une écriture d'`Edit` / `Write` vise : champs de chemin, et les
    en-têtes d'un patch `*** Begin Patch` (`apply_patch`)."""
    import copilot
    chemins = []
    patch = None
    if isinstance(ti, dict):
        chemins = [ti[k] for k in ("file_path", "path", "filePath", "notebook_path")
                   if isinstance(ti.get(k), str)]
        patch = ti.get("patch") if isinstance(ti.get("patch"), str) else None
    elif isinstance(ti, str) and ti.lstrip().startswith("*** Begin Patch"):
        patch = ti
    if patch:
        for ligne in patch.splitlines():
            for prefixe in copilot._ENTETES_PATCH:
                if ligne.startswith(prefixe):
                    chemins.append(ligne[len(prefixe):].strip())
                    break
    return chemins


def juge(d):
    """Rend le motif (`str`) pour refuser, `None` pour laisser passer."""
    import hote
    if not isinstance(d, dict):
        return None
    outil = d.get("tool_name")
    ti = d.get("tool_input")
    if hote.est_shell(d):
        cmd = ti.get("command") if isinstance(ti, dict) else None
        if not isinstance(cmd, str) or not ecrit_un_fichier_de_consignes(cmd, hote.est_powershell(d)):
            return None
        cible = "un fichier de consignes"
    elif outil in ("Edit", "Write"):
        visees = [c for c in _cibles(outil, ti) if vise(c)]
        if not visees:
            return None
        cible = visees[0]
    else:
        return None
    if est_gardien():
        return None
    return (
        "consignes : les fichiers de consignes (%s) ne se modifient que par %s (décision du "
        "14/10/2026 : « interdis à part à CTO et à toi de toucher aux claude.md »).\n\n"
        "  visé : %s\n\n"
        "Ce fichier dit à chaque agent qui il est ; il ne bouge que sur l'ordre de l'humain. "
        "Si une consigne te semble fausse ou manquante, écris-le dans ton todo, adressé à "
        "@user, avec la phrase que tu proposes — le CTO la posera s'il dit oui. Ta "
        "mémoire de travail (état, tâches, faits) n'est pas concernée."
        % ("AGENTS.md, CLAUDE.md, copilot-instructions.md", " et ".join(GARDIENS), cible))


def main(entree):
    bas = entree.lower()
    if "agents.md" not in bas and "claude.md" not in bas and "copilot-instructions.md" not in bas:
        return
    import json
    import sys
    import hote
    try:
        d = json.loads(entree)
    except (ValueError, RecursionError):
        return
    motif = juge(d)
    if motif is not None:
        sys.stdout.write(hote.refus(motif) + "\n")
