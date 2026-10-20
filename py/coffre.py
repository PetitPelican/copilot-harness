# -*- coding: utf-8 -*-
"""LE GARDE DU COFFRE — aucun outil n'affiche une valeur de secret, et celle qui passe se voit.

Porté du harnais Claude (0.19.1, `coffre.py`) : mêmes formes refusées, mêmes jumelles
qui passent. Ce qui change chez Copilot est en bas de ce texte.

Le commanditaire, 16/10/2026 : pourquoi les agents affichent-ils si souvent des clés ? QA a
mesuré la cause : une écriture dans le coffre (Doppler) réimprime les secrets,
valeurs comprises — le 07/10, puis le 16/10 chez OPS, où une clé de Production est
restée dans un terminal. Élargi le soir même à tous les outils qui en affichent.

DEUX NIVEAUX.
  1. `coffre` (PreToolUse Bash, Read, Grep) — la vraie barrière : refuse la forme
     qui affiche, sauf si sa sortie est jetée ou écrite dans un fichier
     (`> /dev/null`, `> .env.local`), capturée (`X=$(gh auth token)`), ou réduite
     aux noms (`--only-names`, `| cut -d= -f1`, `| jq keys`, `| wc -l`, `grep -c`).
  2. `coffre-temoin` (PostToolUse) — cherche dans ce qui vient de passer les formes
     de clé connues et le DIT, à l'agent et à l'humain : la clé est à refaire. Il
     n'empêche rien, la sortie est déjà lue. Le journal garde la sorte de clé, sa
     longueur et une empreinte courte — jamais la valeur.

MESURÉ (17/10/2026) sur Doppler 3.77.0, contre un faux coffre local :
  · `secrets set` réimprime les secrets écrits ; `delete` et `upload`, TOUT le coffre ;
    `--silent` fait taire ces trois-là, même avec `--debug` ;
  · `secrets` et `secrets get` impriment toujours, `--silent` ou non ; `--only-names`
    n'imprime que les noms ; `download --no-file` imprime ; `--json` imprime aussi.
LU DANS L'AIDE, PAS JOUÉ (on ne joue pas une commande qui affiche une vraie clé) :
  `supabase projects api-keys --reveal`, `supabase status` (les clés du projet
  local), `gh auth token`, `gh auth status --show-token`, `security find-*-password
  -w` (sur la sortie) et `-g` (sur la sortie d'erreur), `stripe config --list`,
  `vercel env pull /dev/stdout`.

**fail-open** sur une ligne illisible (guillemet non fermé) : on ne devine pas.

CE QUI CHANGE CHEZ COPILOT.
  · La charge est celle de `hote` : outils `Bash` (bash ET PowerShell), `Read`
    (l'outil `view`), `Grep`. Un refus sort par `hote.refus` — `permissionDecision` à
    la racine, ASCII. Le témoin sort `additionalContext` et `systemMessage` ; que
    Copilot les remette au modèle après un outil n'est PAS MESURÉ — le journal des
    fuites, lui, s'écrit toujours.
  · Les formes PowerShell évidentes, quand `toolName` est `powershell` : lecture
    d'un fichier de secrets (`Get-Content` / `gc` / `type` / `Select-String` / `sls`
    / `more`), `$env:NOM` et `Get-ChildItem Env:` affichés, le dessus du dossier
    `Env:`. Réduit aux noms, aux comptes ou jeté : `Measure-Object`, `Out-Null`,
    `Out-File`, `Set-Content`, `> $null`, `(…).Count`, `Select-String -Quiet`,
    `Select-String -OnlyMatching` du motif des noms, `| Select-Object -ExpandProperty
    Name`. Une instruction qui commence par `$x = ` capture sa sortie : elle passe.
    Les barres inverses d'un chemin Windows ne sont pas mangées.
  · Un nom de variable d'environnement ne se juge que s'il LIT comme un secret
    (KEY, TOKEN, SECRET, PASSWORD, PWD, CREDENTIAL, AUTH, CERT, PRIVATE, DSN).
    Chez Claude `echo $CLE` n'est pas jugé ; ici seul le `$env:CLE` de PowerShell
    l'est, à la demande du port — le `echo $CLE` de bash reste ouvert.

NON COUVERT, pour PowerShell : un chemin construit (`Get-Content (Join-Path $PWD
'.env')`), une valeur relue plus tard depuis une variable (`$x = gc .env; $x`),
`[IO.File]::ReadAllText('.env')`, un `Invoke-Expression` d'une chaîne composée, les
alias définis par l'utilisateur. Le garde lit la ligne, pas l'exécution.
"""
import os
import re
import sys

# ── ce qui affiche ───────────────────────────────────────────────────────

A_VALEUR = {"--api-host", "--attempts", "--config-dir", "--dashboard-host",
            "--dns-resolver-address", "--dns-resolver-proto", "--dns-resolver-timeout",
            "--scope", "--timeout", "-t", "--token", "-p", "--project", "-c", "--config",
            "--type", "--visibility", "--format", "--name-transformer", "--passphrase",
            "--fallback", "--fallback-passphrase", "--use-env", "--output",
            "--mount", "--mount-format", "--mount-template", "--mount-max-reads",
            "--command", "--project-ref", "--workdir", "--profile", "-o", "--output-format",
            "--hostname", "--environment", "--git-branch", "--cwd", "--override-name"}
PREFIXES = {"env", "command", "time", "sudo", "nice", "nohup", "exec", "builtin",
            "npx", "bunx", "xargs"}
GESTIONNAIRES = {"pnpm", "yarn", "bun"}
COQUILLES = {"sh", "bash", "zsh", "dash"}
ECRAN = {"/dev/stdout", "/dev/stderr", "/dev/tty", "/dev/fd/1", "/dev/fd/2", "-"}
VIDAGES = {"env", "printenv"}
LANCEURS = {"doppler": "run", "op": "run", "infisical": "run", "vercel": "env"}
LECTEURS = {"cat", "bat", "batcat", "head", "tail", "less", "more", "nl", "tac", "grep",
            "egrep", "fgrep", "rg", "ag", "sed", "awk", "gawk", "jq", "xxd", "hexdump", "od",
            "strings", "diff", "sort", "uniq", "column", "tee", "paste", "fold", "base64", "cut",
            "tr", "rev", "pr", "expand",
            # PowerShell (alias compris) : `type` est `Get-Content` sous cmd et PowerShell.
            "get-content", "gc", "type", "more", "select-string", "sls"}
CHERCHEURS_PS = {"select-string", "sls"}       # leurs paramètres sont nommés : pas de « motif d'abord »
PUITS_PS = {"measure-object", "measure", "out-null", "out-file", "set-content", "add-content",
            "sc", "ac"}
NOMS_SEULS = "^[A-Z_][A-Z0-9_]*="
# Un nom d'environnement qui se lit comme un secret.
NOM_SECRET = re.compile(r"key|token|secret|passw|pwd|credential|auth|cert|private|dsn", re.I)
AFFICHEURS_PS = {"write-host", "write-output", "write-information", "write-warning", "write-error",
                 "write-verbose", "write-debug", "echo", "out-host", "out-string", "format-list",
                 "fl", "format-table", "ft", "tee-object", "tee"}
PARCOURS_PS = {"get-childitem", "gci", "ls", "dir", "get-item", "gi", "get-content", "gc", "type",
               "cat"}
VAR_ENV = re.compile(r"\$\{?env:([A-Za-z_*][\w.*-]*)\}?", re.I)
# `(…).Count`, `(…).Name`, `(…).mcpServers.PSObject.Properties.Name` : un compte ou des noms.
REDUIT_PS = re.compile(r"\((?:[^()]|\([^()]*\))*\)(?:\s*\.\w+)*\s*\.(?:Count|Length|Name|Keys)\b", re.I)
ASSIGNE_PS = re.compile(r"^\s*\$\{?[\w:.]+\}?\s*[-+*/]?=(?!=)")
SEPARATEURS = {"&&", "||", ";", "&", ";;", "(", ")", "{", "}"}
TUBES = {"|", "|&"}
SANS_VALEURS = (".example", ".sample", ".template", ".dist", ".defaults", ".schema")


def _nom(t):
    return re.split(r"[\\/]", t)[-1].lower()


def fichier_secret(chemin):
    """Un fichier qui porte des valeurs de secrets : `.env`, `.env.*` (sauf les
    gabarits), `.envrc`, `.mcp.json`, et tout ce qui vit sous un dossier caché `.…secrets`."""
    if not chemin:
        return False
    p = os.path.expanduser(chemin.strip("'\""))
    morceaux = [m for m in re.split(r"[\\/]", p) if m]
    if not morceaux:
        return False
    base = morceaux[-1]
    if base == ".env" or base.startswith(".env.") or base.startswith(".env*"):
        if not base.lower().endswith(SANS_VALEURS):
            return True
    if base in (".mcp.json", ".envrc"):
        return True
    return any(re.match(r"^\.[\w.-]*secrets?$", m, re.I) for m in morceaux[:-1])


def _option(args, *noms):
    for a in args:
        for n in noms:
            if a == n or a == n + "=true" or (n.startswith("--") and a.startswith(n + "=")
                                               and not a.endswith("=false")):
                return True
    return False


def _mots(args):
    mots, i = [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            mots.append(a)
            mots.extend(args[i + 1:])
            break
        if a.startswith("-"):
            i += 2 if a in A_VALEUR else 1
            continue
        mots.append(a)
        i += 1
    return mots


def _valeur(args, *noms):
    for i, a in enumerate(args):
        for n in noms:
            if a == n and i + 1 < len(args):
                return args[i + 1]
            if a.startswith(n + "="):
                return a[len(n) + 1:]
    return None


def _reducteur(prog, args):
    """Ce segment ne laisse passer que des noms, des comptes ou rien."""
    texte = " ".join(args)
    if prog == "wc" or prog in PUITS_PS:
        return True
    if prog in CHERCHEURS_PS:
        minuscules = [a.lower() for a in args]
        if any(a.startswith("-q") for a in minuscules):          # -Quiet : un booléen
            return True
        return ("-onlymatching" in minuscules
                and any(a.strip("'\"").startswith(NOMS_SEULS) for a in args))
    if prog in ("select-object", "select", "foreach-object", "foreach", "%"):
        m = [a.lower() for a in args]
        return m in (["name"], ["-expandproperty", "name"], ["-expand", "name"], ["{$_.name}"])
    if prog in ("grep", "egrep", "fgrep", "rg"):
        if any(re.match(r"^-[A-Za-z]*[clLq]", a) or a in ("--count", "--files-with-matches",
                                                              "--quiet", "--files-without-match")
               for a in args):
            return True
        # Les noms seuls : `grep -oE '^[A-Z_][A-Z0-9_]*='`. Pas `cut -d= -f1` ni
        # `sed 's/=.*//'` : une valeur sur plusieurs lignes (une clé PEM) les
        # traverse presque entière — mesuré au faux coffre le 17/10/2026.
        return (any(re.match(r"^-[A-Za-z]*o", a) for a in args)
                and any(a.startswith(NOMS_SEULS) for a in args))
    if prog == "jq":
        return "keys" in texte
    return False


def _commande(prog, args, powershell=False):
    """`(raison, taisable)` si la commande affiche des valeurs, sinon None.
    `taisable` : `--silent` la fait taire (les écritures Doppler)."""
    mots = _mots(args)
    # `doppler run -- env`, `op run -- printenv X`… : tout le coffre d'un coup.
    if prog in LANCEURS and mots[:1] == [LANCEURS[prog]]:
        apres = mots[mots.index("--") + 1:] if "--" in mots else []
        cmd = _valeur(args, "--command")
        tete = _nom(apres[0]) if apres else (_nom(cmd.split()[0]) if cmd and cmd.split() else "")
        if tete in VIDAGES:
            return ("`%s %s -- %s` affiche les secrets injectés, valeurs comprises"
                    % (prog, LANCEURS[prog], tete), False)
    if prog == "doppler":
        if mots[:1] != ["secrets"]:
            return None
        sous = mots[1] if len(mots) > 1 else ""
        if sous == "":
            if _option(args, "--only-names"):
                return None
            return ("`doppler secrets` imprime tout le coffre, valeurs comprises — pour les "
                    "noms seuls : `doppler secrets --only-names`", False)
        if sous == "get":
            return ("`doppler secrets get` imprime la valeur, `--silent` ou non — elle ne se "
                    "lit que capturée (`X=$(doppler secrets get NOM --plain)`) ; pour savoir "
                    "qu'elle existe : `doppler secrets --only-names`", False)
        if sous in ("set", "delete", "upload"):
            if _option(args, "--silent"):
                return None
            quoi = "les secrets écrits" if sous == "set" else "TOUT le coffre"
            return ("`doppler secrets %s` réimprime %s, valeurs comprises — ajoute `--silent`"
                    % (sous, quoi), True)
        if sous == "download" and _option(args, "--no-file"):
            return ("`doppler secrets download --no-file` imprime le coffre — écris-le dans un "
                    "`.env*.local` (`> .env.local`) ou retire `--no-file`", False)
        if sous == "substitute" and _valeur(args, "--output") is None:
            return ("`doppler secrets substitute` imprime le gabarit rempli — `--output "
                    "FICHIER`", False)
        return None
    if prog == "supabase":
        if mots[:1] == ["status"]:
            return ("`supabase status` imprime les clés du projet (service_role, secret, S3) "
                    "— pour l'état seul, réduis la sortie : `supabase status -o json | jq "
                    "keys`", False)
        if mots[:2] == ["projects", "api-keys"]:
            return ("`supabase projects api-keys` imprime les clés du projet — pour savoir "
                    "qu'elles existent : `supabase projects api-keys | wc -l`", False)
        return None
    if prog == "gh":
        if mots[:2] == ["auth", "token"]:
            return ("`gh auth token` imprime le jeton — il ne se lit que capturé "
                    "(`GH_TOKEN=$(gh auth token)`)", False)
        if mots[:2] == ["auth", "status"] and _option(args, "-t", "--show-token"):
            return "`gh auth status --show-token` imprime le jeton — retire `--show-token`", False
        return None
    if prog == "security":
        if mots[:1] and mots[0] in ("find-generic-password", "find-internet-password"):
            if _option(args, "-w"):
                return ("`security %s -w` imprime le mot de passe — il ne se lit que capturé"
                        % mots[0], False)
            if _option(args, "-g"):
                return ("`security %s -g` imprime le mot de passe sur la sortie d'erreur — "
                        "retire `-g`" % mots[0], "erreur")
            return None
        if mots[:1] == ["dump-keychain"] and _option(args, "-d"):
            return "`security dump-keychain -d` imprime le trousseau en clair", False
        return None
    if prog == "stripe":
        if mots[:1] == ["config"] and _option(args, "--list"):
            return ("`stripe config --list` imprime les clés d'API — `stripe config --list | "
                    "grep -c _key` pour savoir qu'elles existent", False)
        return None
    if prog == "vercel":
        if mots[:2] == ["env", "pull"] and len(mots) > 2 and mots[2] in ECRAN:
            return ("`vercel env pull %s` imprime les variables — laisse-la écrire "
                    "`.env.local`" % mots[2], False)
        return None
    if prog in PARCOURS_PS and powershell:
        # `Get-ChildItem Env:` / `ls env:` / `Get-Item Env:CLE` : l'environnement est un lecteur.
        for a in args:
            if a.lower().startswith("env:"):
                r = _env_nomme(a[4:])
                if r:
                    return r, False
    if prog in LECTEURS:
        if _reducteur(prog, args):
            return None
        fichiers = [a for a in args if not a.startswith("-")]
        if (prog in ("grep", "egrep", "fgrep", "rg", "sed", "awk", "gawk", "jq") and fichiers
                and not any(a in ("-e", "-f", "--regexp", "--file") for a in args)):
            fichiers = fichiers[1:]         # le premier mot est le motif ou le programme
        for f in fichiers:
            if fichier_secret(f):
                return ("`%s %s` affiche un fichier de secrets — pour ses noms seuls : %s"
                        % (prog, f, _noms_seuls(f, powershell)), False)
    return None


def _noms_seuls(fichier, powershell):
    """Comment ne lire que les NOMS d'un fichier de secrets — dans le shell qui parle."""
    if powershell:
        return ("`(Get-Content %s).Count` pour les compter, `Select-String -Quiet -Pattern NOM "
                "-Path %s` pour savoir si l'un existe, ou, sous PowerShell 7, `Select-String "
                "-OnlyMatching -Pattern '^[A-Z_][A-Z0-9_]*=' -Path %s` pour les noms (et "
                "`(Get-Content %s | ConvertFrom-Json).mcpServers.PSObject.Properties.Name` pour "
                "un JSON)" % (fichier, fichier, fichier, fichier))
    return ("`grep -oE '^[A-Z_][A-Z0-9_]*=' %s` (ou `jq keys` pour un JSON)" % fichier)


def _env_nomme(nom):
    """La raison si lire l'environnement sous ce nom (ou ce motif) affiche un secret."""
    nom = nom.strip("\\/ '\"")
    if not nom or not nom.strip("*?") or NOM_SECRET.search(nom):
        return ("lire l'environnement (`%s`) affiche des valeurs de secrets — pour savoir qu'elles "
                "existent : `Get-ChildItem Env: | Select-Object -ExpandProperty Name`, ou "
                "`Test-Path Env:NOM`" % ("Env:" + nom if nom else "Env:"))
    return None


# ── la ligne de commande ─────────────────────────────────────────────────

def _jetons(ligne, powershell=False):
    """Les mots de la ligne. Sous PowerShell la barre inverse sépare un chemin, elle
    n'échappe rien : `shlex` la mangerait (`C:\\x\\.env` → `C:x.env`)."""
    import shlex
    lex = shlex.shlex(ligne, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    if powershell:
        lex.escape = ""
    return list(lex)


def _lignes(cmd):
    """Les lignes de commande, suites `\\` jointes et corps de heredoc sautés."""
    lignes, fin_heredoc, courante = [], None, ""
    for l in cmd.replace("\r\n", "\n").split("\n"):
        if fin_heredoc is not None:
            if l.strip() == fin_heredoc:
                fin_heredoc = None
            continue
        if l.endswith("\\"):
            courante += l[:-1] + " "
            continue
        courante += l
        m = re.search(r"<<-?\s*['\"]?([A-Za-z_][\w-]*)['\"]?", courante)
        lignes.append(courante)
        courante = ""
        if m:
            fin_heredoc = m.group(1)
    if courante:
        lignes.append(courante)
    return lignes


def _substitutions(ligne, powershell=False):
    """`(reste, [contenus capturés])` : `$(…)` et `…` sortis de la ligne. Sous PowerShell
    le backtick échappe, il ne capture rien."""
    captures, sortie, i = [], [], 0
    while i < len(ligne):
        if ligne.startswith("$(", i) and not ligne.startswith("$((", i):
            prof, j = 1, i + 2
            while j < len(ligne) and prof:
                prof += {"(": 1, ")": -1}.get(ligne[j], 0)
                j += 1
            captures.append(ligne[i + 2:j - 1])
            sortie.append(" CAPTURE ")
            i = j
            continue
        if ligne[i] == "`" and not powershell:
            j = ligne.find("`", i + 1)
            if j < 0:
                break
            captures.append(ligne[i + 1:j])
            sortie.append(" CAPTURE ")
            i = j + 1
            continue
        sortie.append(ligne[i])
        i += 1
    return "".join(sortie), captures


def _redirige(seg, flux):
    """Le flux (1 : sortie, 2 : erreur) du segment part ailleurs qu'à l'écran."""
    for k, t in enumerate(seg):
        if t not in (">", ">>", ">|", "&>", "&>>"):
            continue
        avant = seg[k - 1] if k else ""
        if t in ("&>", "&>>"):
            vise = (1, 2)
        elif avant.isdigit():
            vise = (int(avant),)
        else:
            vise = (1,)
        cible = seg[k + 1] if k + 1 < len(seg) else ""
        if flux in vise and cible and cible not in ECRAN:
            return True
    return False


def _programme(seg):
    """`(nom, arguments)` du programme lancé, après `env X=1`, `time`, `npx`…"""
    i = 0
    while i < len(seg):
        t = seg[i]
        n = _nom(t)
        if re.match(r"^[A-Za-z_]\w*=", t):
            i += 1
        elif n in PREFIXES:
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                i += 2 if seg[i] in ("-u", "-C", "-S", "-n") else 1
        elif n in GESTIONNAIRES:
            i += 1
            if i < len(seg) and seg[i] in ("dlx", "exec", "x"):
                i += 1
        else:
            prog = n[:-4] if n.endswith(".exe") else n
            return prog, seg[i + 1:]
    return "", []


VERBES_DOPPLER = {"secrets", "run"}


def _lance_doppler(seg, args, cwd):
    """Le programme du segment est-il un script qui relaie ses arguments à Doppler ?
    Lu seulement si un verbe de Doppler suit : la plupart des commandes n'y viennent pas."""
    if not any(a in VERBES_DOPPLER for a in args):
        return False
    tete = seg[len(seg) - len(args) - 1]    # le jeton du programme, tel qu'écrit
    import shutil
    chemin = os.path.expanduser(tete)
    if not re.search(r"[\\/]", tete):
        chemin = shutil.which(tete) or ""
    elif not os.path.isabs(chemin):
        chemin = os.path.join(cwd or os.getcwd(), chemin)
    try:
        with open(chemin, "rb") as h:
            debut = h.read(8192)
    except (OSError, ValueError):
        return False
    if b"\0" in debut:
        return False            # un programme compilé : on ne lit pas dedans
    texte = debut.decode("utf-8", "replace")
    return bool(re.search(r"\bdoppler\b", texte) and re.search(r'"\$[@*]"|\$\{@|\$@|"\$\{@', texte))


def _chaines(jetons):
    """`a | b && c` → [[a, b], [c]]."""
    chaines, chaine, seg = [], [], []
    for t in jetons + [";"]:
        if t in SEPARATEURS:
            if seg:
                chaine.append(seg)
            if chaine:
                chaines.append(chaine)
            chaine, seg = [], []
        elif t in TUBES:
            chaine.append(seg)
            seg = []
        else:
            seg.append(t)
    return chaines


def _juge_jetons(jetons, profondeur, capture, cwd=None, powershell=False):
    for chaine in _chaines(jetons):
        for k, seg in enumerate(chaine):
            prog, args = _programme(seg)
            if prog in COQUILLES and "-c" in args:
                i = args.index("-c")
                if i + 1 < len(args):
                    r = _juge_texte(args[i + 1], profondeur + 1,
                                    capture or _redirige(chaine[-1], 1), cwd, powershell)
                    if r:
                        return r
                continue
            if prog == "eval":
                r = _juge_texte(" ".join(args), profondeur + 1, capture or _redirige(chaine[-1], 1),
                                cwd, powershell)
                if r:
                    return r
                continue
            d = _commande(prog, args, powershell)
            if d is None and prog not in ("doppler",) and _lance_doppler(seg, args, cwd):
                # `~/.secrets/coffre prd secrets` : un lanceur qui finit par
                # `exec doppler "$@"`. Ses premiers mots sont à lui ; Doppler commence
                # au premier verbe qu'il connaît (QA, 17/10/2026).
                k0 = next((i for i, a in enumerate(args) if a in VERBES_DOPPLER), None)
                if k0 is not None:
                    d = _commande("doppler", args[k0:])
            if d is None:
                continue
            raison, taisable = d
            if taisable == "erreur":
                # La valeur sort sur l'erreur : ni un tube ni une capture ne la retiennent.
                if _redirige(seg, 2):
                    continue
                return raison
            if capture or _redirige(seg, 1):
                continue
            # Sa sortie part dans un tube : un réducteur plus loin, ou une fin hors écran.
            suite = chaine[k + 1:]
            if suite and (any(_reducteur(*_programme(s)) for s in suite)
                          or _redirige(chaine[-1], 1)):
                continue
            return raison
    return None


def _juge_texte(cmd, profondeur=0, capture=False, cwd=None, powershell=False):
    if profondeur > 4:
        return None
    for l in _lignes(cmd):
        reste, captures = _substitutions(l, powershell)
        for c in captures:
            r = _juge_texte(c, profondeur + 1, True, cwd, powershell)
            if r:
                return r
        r = _juge_jetons(_jetons(reste, powershell), profondeur, capture, cwd, powershell)
        if r:
            return r
    return None


# ── PowerShell ───────────────────────────────────────────────────────────

def _instructions_ps(cmd):
    """Les instructions d'une ligne PowerShell : coupées sur `;` et sur les sauts de
    ligne, hors guillemets. Le backtick de fin de ligne joint la ligne suivante."""
    cmd = cmd.replace("`\r\n", " ").replace("`\n", " ").replace("\r\n", "\n")
    sorties, courante, guillemet = [], [], None
    for c in cmd:
        if guillemet:
            courante.append(c)
            if c == guillemet:
                guillemet = None
        elif c in "'\"":
            guillemet = c
            courante.append(c)
        elif c in ";\n":
            sorties.append("".join(courante))
            courante = []
        else:
            courante.append(c)
    sorties.append("".join(courante))
    return [x.strip() for x in sorties if x.strip()]


def _env_ps(instruction):
    """La raison si l'instruction PowerShell AFFICHE une variable d'environnement qui se
    lit comme un secret : `Write-Host $env:CLE`, ou l'expression seule (`$env:CLE`,
    `"$env:CLE"`, `[Environment]::GetEnvironmentVariable('CLE')`)."""
    montre = re.search(r"\[Environment\]::GetEnvironmentVariables\s*\(", instruction, re.I)
    noms = [m.group(1) for m in VAR_ENV.finditer(instruction)]
    noms += [m.group(1) for m in re.finditer(
        r"GetEnvironmentVariable\s*\(\s*['\"]([^'\"]+)['\"]", instruction, re.I)]
    if not noms and not montre:
        return None
    # Ce qui s'affiche : une expression qui est l'instruction entière, ou un afficheur.
    mots = instruction.split()
    if mots and mots[0] == "&":
        mots = mots[1:]
    cmdlet = mots[0].lower().strip("'\"") if mots else ""
    expression = instruction[0] in "$\"'[(@"
    if not (expression or cmdlet in AFFICHEURS_PS):
        return None
    secrets = [n for n in noms if NOM_SECRET.search(n) or not n.strip("*?")]
    if montre or secrets:
        quoi = "toutes les variables d'environnement" if montre else "`$env:%s`" % secrets[0]
        return ("afficher %s montre des valeurs de secrets — pour savoir qu'elles existent : "
                "`Test-Path Env:NOM`, ou `Get-ChildItem Env: | Select-Object -ExpandProperty "
                "Name`" % quoi)
    return None


def _juge_ps(cmd, cwd=None):
    cmd = REDUIT_PS.sub(" CAPTURE ", cmd.replace("`\r\n", " ").replace("`\n", " "))
    for instruction in _instructions_ps(cmd):
        if ASSIGNE_PS.match(instruction):
            continue                    # `$x = …` capture la sortie, comme `X=$(…)`
        r = _juge_texte(instruction, cwd=cwd, powershell=True)
        if r:
            return r
        # La sortie de l'instruction est jetée, écrite ou comptée : l'environnement non plus.
        jetons = _jetons(instruction, True)
        chaines = _chaines(jetons)
        if chaines and (_redirige(chaines[-1][-1], 1)
                        or any(_reducteur(*_programme(s)) for s in chaines[-1][1:])):
            continue
        r = _env_ps(instruction)
        if r:
            return r
    return None


def affiche_un_secret(cmd, cwd=None, powershell=False):
    """La raison si la ligne de commande affiche une valeur de secret, sinon None.
    `powershell` : la ligne est lue comme PowerShell (chemins en `\\`, `$env:`, cmdlets)."""
    try:
        if powershell:
            return _juge_ps(cmd, cwd)
        return _juge_texte(cmd, cwd=cwd)
    except ValueError:      # guillemet non fermé : on ne devine pas
        return None


# ── le hook d'avant ──────────────────────────────────────────────────────

FIN = ("\n\nUne valeur affichée reste dans la conversation : elle est à tenir pour fuitée, "
       "et la clé à refaire. Sortie jetée ou écrite dans un fichier, capturée dans une "
       "variable, ou réduite aux noms : la commande passe.")


def juge(d):
    """Le motif du refus (`str`), ou None."""
    import hote
    if not isinstance(d, dict):
        return None
    outil = d.get("tool_name")
    ti = d.get("tool_input") if isinstance(d.get("tool_input"), dict) else {}
    if hote.est_shell(d):
        cmd = ti.get("command")
        raison = (affiche_un_secret(cmd, d.get("cwd"), hote.est_powershell(d))
                  if isinstance(cmd, str) else None)
    elif outil == "Read":
        f = ti.get("file_path")
        raison = None
        if isinstance(f, str) and fichier_secret(f):
            raison = ("ouvrir `%s` affiche ses valeurs — pour ses noms seuls : %s ; sous PowerShell : %s"
                      % (re.split(r"[\\/]", f)[-1], _noms_seuls("FICHIER", False),
                         _noms_seuls("FICHIER", True)))
    elif outil == "Grep":
        raison = None
        if ti.get("output_mode") == "content":
            import fnmatch
            chemin, motif = ti.get("path"), ti.get("glob")
            if ((isinstance(chemin, str) and fichier_secret(chemin))
                    or (isinstance(motif, str) and any(
                        fnmatch.fnmatch(n, re.split(r"[\\/]", motif)[-1])
                        for n in (".env", ".env.local", ".mcp.json")))):
                raison = ("chercher en mode contenu dans un fichier de secrets affiche ses "
                          "valeurs — `output_mode: count` ou `files_with_matches`")
    else:
        return None
    return None if raison is None else "coffre : %s.%s" % (raison, FIN)


def main(entree):
    bas = entree.lower()
    if not any(m in bas for m in ("doppler", "supabase", "gh", "security", "stripe", "vercel",
                                  "env", "mcp.json", "secret", "printenv")):
        return
    import json
    import hote
    try:
        d = json.loads(entree)
    except (ValueError, RecursionError):
        return
    motif = juge(d)
    if motif is not None:
        sys.stdout.write(hote.refus(motif) + "\n")


# ── le témoin d'après ────────────────────────────────────────────────────

FORMES = [
    ("Supabase, jeton personnel", r"sbp_[A-Za-z0-9]{20,}"),
    ("Supabase, clé secrète", r"sb_secret_[A-Za-z0-9_-]{16,}"),
    ("Stripe, clé de Production", r"[sr]k_live_[A-Za-z0-9]{16,}"),
    ("Stripe, clé de test", r"[sr]k_test_[A-Za-z0-9]{16,}"),
    ("GitHub, jeton", r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    ("Doppler, jeton", r"dp\.(?:st|pt|ct|sa|scim|audit)\.[A-Za-z0-9._-]{20,}"),
    ("Anthropic, clé", r"sk-ant-[A-Za-z0-9_-]{30,}"),
    ("jeton JWT", r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{16,}"),
]


def _role_jwt(j):
    import base64
    import json
    try:
        p = j.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4))).get("role")
    except (ValueError, IndexError, AttributeError):
        return None


def cles(texte):
    """`[(sorte, longueur, empreinte)]` des clés trouvées — jamais la valeur.
    Une clé `anon` de Supabase est publique (elle part dans l'app) : pas une fuite."""
    import hashlib
    vues, trouvees = set(), []
    for sorte, motif in FORMES:
        for m in re.finditer(motif, texte):
            v = m.group(0)
            if v in vues:
                continue
            vues.add(v)
            if sorte == "jeton JWT" and _role_jwt(v) == "anon":
                continue
            trouvees.append((sorte, len(v), hashlib.sha256(v.encode()).hexdigest()[:10]))
    return trouvees


def _journal(lignes):
    import time
    try:
        import socle
        d = os.path.join(socle.socle(), "coffre")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "fuites.log"), "a", encoding="utf-8") as h:
            for l in lignes:
                h.write("%s\t%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), l))
        return os.path.join(d, "fuites.log")
    except OSError:
        return None


def temoin(entree):
    """PostToolUse : la clé vue dans la commande ou sa sortie se signale."""
    if not any(m in entree for m in ("sbp_", "sb_secret_", "k_live_", "k_test_", "gh", "dp.",
                                      "sk-ant-", "eyJ")):
        return
    import json
    try:
        d = json.loads(entree)
    except (ValueError, RecursionError):
        return
    if not isinstance(d, dict):
        return
    texte = json.dumps([d.get("tool_input"), d.get("tool_response"), d.get("tool_result")],
                       ensure_ascii=False)
    trouvees = cles(texte)
    if not trouvees:
        return
    outil = d.get("tool_name") or "?"
    projet = os.environ.get("COPILOT_PROJECT_DIR") or d.get("cwd") or "?"
    log = _journal(["%s\t%s\t%s\t%d car.\tempreinte %s" % (projet, outil, s, n, e)
                    for s, n, e in trouvees])
    liste = ", ".join("%s (empreinte %s)" % (s, e) for s, _, e in trouvees)
    note = ("coffre : une clé est passée en clair dans ce que %s vient de lire ou d'écrire — "
            "%s. Elle est dans la conversation : à tenir pour fuitée et à refaire. Ne la "
            "recopie nulle part ; dis à l'humain laquelle refaire (la sorte et l'empreinte, "
            "jamais la valeur).%s" % (outil, liste,
                                      " Journal : %s" % log if log else ""))
    import hote
    sys.stdout.write(hote.json_ascii({
        "systemMessage": "coffre : clé vue en clair (%s) — à refaire." % liste,
        "additionalContext": note,
    }) + "\n")
