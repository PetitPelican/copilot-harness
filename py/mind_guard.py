# -*- coding: utf-8 -*-
"""LE GARDE DE COMMIT — hook PreToolUse (Bash), sur `git commit`.

Port de `harnais/src/mind_guard.rs` (0.12.8). Il garde deux choses, et pas la
même façon :

    .fact/          mémoire PARTAGÉE du projet — ne s'écrit qu'à la demande
    .mind/state.md  déclaration de l'agent — doit rester LISIBLE et FRAÎCHE

UN EN-TÊTE CASSÉ EST PIRE QU'UN EN-TÊTE VIEUX. `claude-projets` range le
projet en « aucune déclaration » et il disparaît du tableau de bord sans que
personne s'en aperçoive : un fichier illisible est un silence, et un silence
se lit comme une absence de problème.

LES DEUX ÉCHAPPATOIRES SE LISENT EN FIN DE COMMANDE, PAS N'IMPORTE OÙ.
C'était un test de sous-chaîne brut : une branche `essai-fact-ok` désarmait
le garde, sans intention et sans trace. Et `mind-ok` ne lève QUE les règles
sur la déclaration de l'agent — jamais celle sur `.fact/`, qui protège la
mémoire des autres agents. Une clé, une serrure.

**fail-open** : toute erreur, ambiguïté ou dépôt non git laisse passer.

VITESSE. Ce garde tourne avant CHAQUE commande Bash. Presque aucune n'est un
commit : le chemin « rien à faire » ne regarde que le texte brut et n'importe
RIEN (ni `json`, ni `re`, ni `subprocess`, ni `memoire`). Tout le reste vit
dans des fonctions qui importent à la demande.
"""

# --- à ajuster selon le projet ---------------------------------------------
# `.github/copilot/` : les réglages, profils et périmètres du harnais Copilot.
# `.claude/` reste ignoré : Copilot lit aussi ce dossier, ce n'est pas du code.
PREFIXES_IGNORES = [".github/copilot/", ".claude/", ".mind/", ".fact/", "docs/", ".memory/", ".logs/"]
# L'ESPACE DES LIVRABLES (Maxime, 12/10/2026 : « un espace dédié aux livrables, et
# on va l'appeler Assets ») : ce qu'un agent PRODUIT — plans, analyses, requêtes,
# scripts livrés — vit dans `assets/` (mono-agent) ou `assets/<nom>/` (un dossier
# par agent), séparé de `docs/`, qui reste l'archive du projet, et du code, qui
# est ce qu'on livre. Un script SQL rangé ici n'oblige donc pas à mettre l'état
# à jour. Né dans le harnais Copilot sous le nom `outputs/`. Seul le dossier de
# la RACINE du projet (ou du lot) compte : `src/assets/` d'un site reste du code.
ESPACE_LIVRABLES = "assets/"
# LES ANCIENS NOMS, toujours lus : un projet Copilot pas encore migré garde ses
# livrables hors du code — `outputs/` (1.2 à 1.3) et `brain/workbench/` (0.19 à
# 1.1). Le même nom que `agent.BANC` et `agent.BANCS_ANCIENS`, écrit ici sans
# import : ce module ne charge rien avant d'en avoir besoin.
ESPACES_LIVRABLES_ANCIENS = ["outputs/", "brain/workbench/"]
EXT_CODE = [
    ".py", ".sql", ".qmd", ".ipynb", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".rb", ".php", ".c", ".h", ".hpp", ".cpp", ".cc",
    ".cs", ".swift", ".scala", ".sh", ".ps1", ".r", ".jl", ".vue", ".svelte",
    ".dart", ".ex", ".exs",
]
DOSSIERS_SRC = ["src/", "app/", "lib/", "python/", "sql/",
                "packages/", "services/", "api/"]
# ---------------------------------------------------------------------------

# Deux contrats, selon la forme. Avant migration le `cap` est dans
# `state.md` ; après, il appartient au projet et vit dans `.fact/base.md` —
# le réclamer ici ferait échouer tout commit d'un projet correctement migré.
# LES NOMS QUE LE SOCLE PRÉVOIT. La liste vit dans le socle : voir
# `socle.FAITS_MONO`. Elle était ici, dans `briefing.rs` et dans `migration.rs` —
# trois copies d'accord entre elles, ce qui est la forme la plus tranquille d'un
# futur désaccord (audit P5).


def noms_fact():
    import socle
    return socle.faits_tous()


NOMS_MIND = ["state.md", "todo.md"]

CHAMPS_REQUIS = ["maj", "cap", "jalon"]
CHAMPS_REQUIS_FACT = ["maj", "sante", "jalon"]

# Les blancs de Rust (`\s` du crate `regex`, `str::trim`) — pas ceux de Python,
# qui y ajoutent \x1c-\x1f.
BLANCS = ("\t\n\x0b\x0c\r \x85\xa0       "
          "         　")
S = ("[\\t\\n\\x0b\\x0c\\r \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029"
     "\\u202f\\u205f\\u3000]")


class Git(object):
    """`git` lancé DEPUIS un dossier donné."""

    def __init__(self, dossier):
        self.dossier = dossier

    def run(self, args):
        """`(code, sortie)`. Git absent ou dossier introuvable : `(1, "")`."""
        import subprocess
        try:
            o = subprocess.run(["git"] + list(args), cwd=self.dossier,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
        except (OSError, ValueError):
            return (1, "")
        return (o.returncode, o.stdout.decode("utf-8", "replace"))


def autorise(cmd, mot):
    """Ce que la forme exige : un `#` de commentaire shell, le mot, puis la fin."""
    import re
    return re.search("#" + S + "*" + re.escape(mot) + S + "*\\Z", cmd) is not None


def refus(motif):
    """COPILOT : `permissionDecision` à la RACINE de l'objet (voir `hote`)."""
    return {"permissionDecision": "deny", "permissionDecisionReason": motif}


def entete(texte):
    """L'en-tête `---` en tête de fichier, en YAML plat. Liste vide si absent.

    Liste de couples `(clé, valeur)` dans l'ordre du fichier : une clé répétée
    y figure deux fois, et `champ()` rend la DERNIÈRE."""
    import re
    m = re.match("(?s)" + S + "*---" + S + "*\\n(.*?)\\n---" + S + "*(\\n|\\Z)", texte)
    if m is None:
        return []
    cmt = re.compile(S + "+#.*\\Z")
    out = []
    g = m.group(1)
    for l in g.split("\n"):
        if ":" in l and not l.lstrip(BLANCS).startswith("#"):
            c, v = l.split(":", 1)
            out.append((c.strip(BLANCS).lower(), cmt.sub("", v, count=1).strip(BLANCS)))
    return out


def champ(e, cle):
    # Python : le DERNIER gagne, un dict écrase la clé répétée.
    for k, v in reversed(e):
        if k == cle:
            return v
    return None


def aujourd_hui():
    import time
    return time.strftime("%Y-%m-%d")


def verifie_state(texte, champs):
    """Les reproches, ÉTIQUETÉS PAR NATURE. La distinction n'est pas cosmétique :
    un fichier illisible fait disparaître le projet du tableau de bord sans
    bruit, un fichier périmé l'y montre avec une date fausse.

    Rend une liste de couples `("structure" | "fraicheur", message)`."""
    d = entete(texte)
    if not d:
        return [("structure",
                 "il n'a plus d'en-tête `---` en première ligne — le collecteur le "
                 "range en « aucune déclaration » et le projet disparaît du tableau de bord")]
    maux = []
    manquants = ["`%s:`" % c for c in champs if not champ(d, c)]
    if manquants:
        maux.append(("structure", "il lui manque %s" % ", ".join(manquants)))
    maj = champ(d, "maj") or ""
    if maj:
        import re
        if re.match("\\d{4}-\\d{2}-\\d{2}\\Z", maj) is None:
            maux.append(("structure",
                         "`maj:` doit être une date ISO `AAAA-MM-JJ`, pas « %s »" % maj[:20]))
        elif maj != aujourd_hui():
            maux.append(("fraicheur",
                         "`maj:` porte %s alors que le commit est d'aujourd'hui (%s) — le "
                         "tableau de bord datera ce projet du mauvais jour"
                         % (maj, aujourd_hui())))
    return maux


def est_du_code(f, lot, projet):
    """Deux jeux de préfixes à ignorer, pas un : le harnais de l'AGENT et celui du
    PROJET. N'ignorer que le second faisait compter `agents/ios/.claude/hooks/`
    pour du code projet."""
    for p in PREFIXES_IGNORES + [ESPACE_LIVRABLES] + ESPACES_LIVRABLES_ANCIENS:
        if f.startswith(lot + p) or f.startswith(projet + p):
            return False
    if f.startswith(projet + "site/") and not f.startswith(projet + "site/_content/"):
        return False   # moteur / rendu généré du site de doc
    for e in EXT_CODE:
        if f.endswith(e):
            return True
    for d in DOSSIERS_SRC:
        if f.startswith(lot + d) or f.startswith(projet + d):
            return True
    return False


def _prefixe(rel):
    """`rel` : liste de composants. Vide → pas de préfixe."""
    if not rel:
        return ""
    return "/".join(rel) + "/"


def _cwd(repli):
    import os
    try:
        return os.getcwd()
    except OSError:
        return repli


def contexte_defaut(depart):
    """`contexte()` tel que la version Python l'appelle : git depuis le dossier
    COURANT, `depart` seulement pour l'arithmétique de chemins.

    Rend `(lot, projet, faits)`."""
    return contexte(Git(_cwd(depart)), depart)


def contexte(g, depart):
    """`(lot, projet, faits)` — où l'agent travaille, et sous quelle forme.

    MESURÉ le 04/09/2026 : `git diff --cached --name-only` rend des chemins
    relatifs à la RACINE DU DÉPÔT, jamais au dossier courant. Un agent de
    `agents/ios/` voit donc `agents/ios/.mind/state.md`, et la constante
    `.mind/state.md` ne correspondait plus à rien : le garde laissait passer
    TOUT, sans le dire.
    """
    import memoire
    import os
    rc, out = g.run(["rev-parse", "--show-toplevel"])
    if rc != 0:
        return ("", "", None)
    racine = memoire._canon(out.strip(BLANCS))
    if racine is None:
        return ("", "", None)
    agent = memoire._canon(depart)
    if agent is None:
        return ("", "", None)
    rel = memoire._strip_prefix(agent, racine)
    if rel is None:
        return ("", "", None)
    lot = _prefixe(rel)
    # Le projet : le premier ancêtre qui porte un `.fact/`, sans jamais sortir
    # du dépôt. Absent = forme d'avant migration, tout se lit dans `.mind/`.
    p = agent
    while True:
        if os.path.isdir(os.path.join(p, ".fact")):
            r = memoire._strip_prefix(p, racine)
            pre = _prefixe(r) if r is not None else ""
            return (lot, pre, pre + ".fact/")
        parent = os.path.dirname(p)
        if p == racine or not parent or parent == p:
            return (lot, lot, None)
        p = parent


def indexe(g, chemin):
    """Le contenu tel qu'il sera COMMITÉ, pas celui du disque : lire le disque
    laisserait passer une correction non indexée."""
    rc, out = g.run(["show", ":" + chemin])
    return out if rc == 0 else None


def lis_disque(p):
    """Le fichier tel qu'il est SUR LE DISQUE. Déportée, la mémoire n'est pas dans
    l'index du dépôt de code ; le disque est alors la seule vérité."""
    try:
        with open(p, encoding="utf-8", newline="") as h:
            return h.read()
    except (OSError, ValueError):
        return ""


def echantillon(v, n):
    s = ", ".join(v[:n])
    if len(v) > n:
        s += ", …"
    return s


def juge(entree, depart):
    """Rend le motif (`str`) pour refuser, `None` pour laisser passer."""
    import json
    try:
        d = json.loads(entree, parse_constant=_refuse)
    except (ValueError, RecursionError):
        return None
    if not isinstance(d, dict):
        return None
    ti = d.get("tool_input")
    cmd = ti.get("command") if isinstance(ti, dict) else None
    if not isinstance(cmd, str):
        cmd = ""
    import re
    if re.search(r"\bgit\b.+\bcommit\b", cmd) is None:
        return None
    import memoire
    import os
    from memoire import Forme
    # GIT TOURNE DEPUIS LE DOSSIER COURANT, PAS DEPUIS `depart`. La version
    # Python appelle `_git` sans `cwd`, donc depuis le processus ; `depart`
    # (`COPILOT_PROJECT_DIR`) ne sert qu'à l'arithmétique de chemins. Les
    # confondre ne se voit que si les deux pointent des dépôts DIFFÉRENTS —
    # et alors le garde jugerait l'index du mauvais dépôt.
    courant = _cwd(depart)
    g = Git(courant)

    # `mind-ok` N'EST PAS TESTÉ ICI : chaque échappatoire est testée devant la
    # règle qu'elle lève, et pas avant.
    # LA FORME EST DEMANDÉE, PLUS DEVINÉE. Elle se lisait ici sur la présence
    # d'un `.fact/`, et DEUX CONTRATS D'EN-TÊTE en dépendent — déplacer ce
    # dossier aurait fait retomber six projets sur `CHAMPS_REQUIS`, qui exige
    # un `cap:` qu'aucun de leurs `state.md` ne porte. Tous leurs commits
    # auraient été refusés dès le premier jour, celui de la migration compris.
    # GIT DEPUIS LE DOSSIER COURANT, POSITION DEPUIS `depart` — les deux
    # repères de ce fichier, déjà nommés plus haut, et déjà confondus une fois.
    r = memoire.resous_depuis(courant, depart)
    # `prefixe_lot`, PAS `lot` : ce qui suit compose des chemins.
    lot, projet = r.prefixe_lot, r.prefixe_projet
    # En forme DÉPORTÉE, `.fact/` n'est pas dans CE dépôt : aucun chemin rendu
    # par `git diff --cached` ne peut le viser. La serrure y est donc inerte
    # par construction, et le relais vit dans le hook de fin de tour, qui juge
    # le dépôt de mémoire. Le mot impossible le dit au lieu de le taire.
    forme = r.forme
    if forme in (Forme.EnPlace, Forme.Ambigue):
        faits = r.prefixe_fact
    elif forme == Forme.Brain and r.brain_autonome:
        # v2 · le cerveau. Ce qui décide n'est plus la forme mais son
        # autonomie : un cerveau qui a son propre dépôt ne montre aucun de ses
        # chemins ici, exactement comme la mémoire déportée d'avant.
        faits = "«cerveau à part»"
    elif forme == Forme.Brain:
        faits = r.prefixe_fact
    elif forme == Forme.Deportee:
        faits = "«déporté»"
    else:                       # HorsDepot, SansMemoire
        faits = None
    # `prefixe_mind`, DEMANDÉ AU RÉSOLVEUR. Cette ligne composait
    # `lot + ".mind/state.md"` — un nom juste avant la migration et
    # faux après : sur un arbre `brain/`, aucun fichier indexé ne s'appelle
    # `.mind/state.md`, donc le contrôle de lisibilité ci-dessous ne trouvait
    # JAMAIS son fichier et laissait passer un en-tête cassé. Mesuré le
    # 10/09/2026 sur une copie migrée, en indexant un `state.md` sans en-tête :
    # `allow`. Le garde n'avait pas faibli, il regardait ailleurs.
    state = r.prefixe_mind + "state.md"
    # `resous()` rend TOUJOURS des chemins — c'est tout l'intérêt. Mais quatre
    # tests d'ici lisaient `Some(chemin)` comme « la mémoire est déportée »,
    # parce que l'ancienne signature ne rendait un chemin que dans ce cas. Le
    # sens était porté par la présence, pas par le nom. Ici on demande la
    # FORME, et les chemins ne servent plus qu'à lire des fichiers.
    # « La mémoire vit dans un AUTRE dépôt » — le seul sens qui reste. En v1
    # c'était la forme déportée ; en v2 c'est un cerveau qui a son propre `.git`.
    deportee = forme == Forme.Deportee or (forme == Forme.Brain and r.brain_autonome)
    if deportee:
        d_mind, d_fact = r.mind, r.fact
    else:
        d_mind, d_fact = None, None
    champs = CHAMPS_REQUIS_FACT if memoire.a_des_faits(forme) else CHAMPS_REQUIS

    rc, out = g.run(["diff", "--cached", "--name-only"])
    if rc != 0:
        return None   # pas un dépôt git, ou git indisponible
    fichiers = [f.strip(BLANCS) for f in _lignes(out)]
    fichiers = [f for f in fichiers if f]
    if not fichiers:
        return None   # `git commit --amend`, commit vide… : rien à juger

    # UN EXPERT ÉCRIT SES FAITS : c'est son métier (Maxime, 12/10/2026). Le fait
    # que Maxime donne EST l'accord, et la garde de fin de tour B16 exige qu'il
    # soit noté le jour même — lui demander ` # fact-ok` en plus, ou plafonner les
    # noms de ses fiches libres, opposerait deux gardes sur la même écriture.
    import socle
    expert = socle.profil_expert()

    # 0. `.fact/` NE S'ÉCRIT QU'À LA DEMANDE DE MAXIME. C'est la seule mémoire
    # partagée par tous les agents d'un projet : un agent qui la réécrit depuis
    # son lot efface ce qu'un autre y avait mis, et personne ne le voit.
    if faits is not None and not expert:
        # `fact-neuf` VAUT `fact-ok`, et ce n'est pas une clé partagée : c'est
        # une hiérarchie, déclarée ici plutôt que subie. `autorise()` ancre le
        # mot en FIN de commande — deux mots ne peuvent donc pas cohabiter. Or
        # créer un cinquième fichier de faits, c'est nécessairement toucher aux
        # faits : les deux serrures se ferment sur le même commit. Sans cette
        # ligne, `fact-neuf` serait une serrure qu'aucune commande ne peut
        # ouvrir — mesuré, 8 cas sur 9, le 10/09/2026.
        if not autorise(cmd, "fact-ok") and not autorise(cmd, "fact-neuf"):
            touches = [x for x in fichiers if x.startswith(faits)]
            if touches:
                return (
                    "mind-guard : ce commit modifie `.fact/` (%s). Ces fichiers sont partagés par "
                    "TOUS les agents du projet et ne s'écrivent qu'à la demande de @user — un "
                    "agent qui les réécrit depuis son lot efface le travail d'un autre en silence. Si "
                    "@user l'a demandé, ajoute ` # fact-ok` à la fin de la commande : "
                    "l'autorisation restera dans l'historique." % echantillon(touches, 4))

    # 0 bis. LE PLAFOND, ET IL PORTE SUR LES NOMS.
    #
    # « Jamais un 5ᵉ fichier dans les faits, jamais un 3ᵉ dans l'esprit, sans le
    # demander au commanditaire » est une règle du socle depuis toujours, et
    # elle n'était **vérifiée nulle part** : mesuré le 10/09/2026 en indexant
    # un `fact/extra.md` — passé sans un mot. Une règle qu'aucun mécanisme ne
    # porte se lit comme tenue, parce que rien ne la contredit jamais.
    #
    # UNE CLÉ, UNE SERRURE : ` # fact-ok` autorise à ÉCRIRE les faits, pas à en
    # créer un cinquième. Le mot est donc distinct — et c'est voulu : la
    # première autorisation est courante, la seconde change la forme du projet.
    # Un mot qui ouvrirait les deux ferait passer la seconde à chaque fois
    # qu'on demande la première.
    #
    # Le plafond ne compte QUE les fichiers à la racine du dossier : un
    # sous-dossier et son contenu n'ont pas de plafond. Aucun n'est prévu —
    # `belief/` et `experience/` étaient nommés ici sans que rien ne les crée
    # ni ne les lise (audit du 11/09/2026) ; les noms sont retirés, pas la règle.
    if faits is not None and not expert:
        if not autorise(cmd, "fact-neuf"):
            noms = noms_fact()
            intrus = []
            for x in fichiers:
                if x.startswith(faits):
                    reste = x[len(faits):]
                    if "/" not in reste and reste not in noms:
                        intrus.append(reste)
            if intrus:
                return (
                    "mind-guard : ce commit ajoute un fichier de faits que le socle ne prévoit pas (%s). Les faits d'un projet tiennent en quatre noms — `base`, `architecture`, `stack`, `rules` — plus `roles` à plusieurs agents et `workflow` pour tous, et ce plafond existe pour qu'on sache toujours où chercher. Un cinquième nom se demande à @user. S'il l'a accordé, ajoute ` # fact-neuf` à la fin de la commande."
                    % echantillon(intrus, 4))
    if r.prefixe_mind and not autorise(cmd, "mind-neuf"):
        intrus = []
        for x in fichiers:
            if x.startswith(r.prefixe_mind):
                reste = x[len(r.prefixe_mind):]
                if "/" not in reste and reste not in NOMS_MIND:
                    intrus.append(reste)
        if intrus:
            return (
                "mind-guard : ce commit ajoute un fichier d'état que le socle ne prévoit pas (%s). L'esprit d'un agent tient en deux fichiers — `state` et `todo` — et le reste se range dans `docs/`, dans les faits, ou dans la mémoire auto selon ce que c'est. Un troisième nom se demande à @user. S'il l'a accordé, ajoute ` # mind-neuf` à la fin de la commande."
                % echantillon(intrus, 4))

    if autorise(cmd, "mind-ok"):
        return None

    # 1. LISIBILITÉ — vaut même sans code, un fichier cassé est le pire cas.
    if state in fichiers or d_mind is not None:
        if d_mind is not None:
            texte = lis_disque(os.path.join(d_mind, "state.md"))
        else:
            texte = indexe(g, state)
        # `None` = suppression ou renommage : ce n'est pas notre sujet.
        if texte is not None:
            maux = verifie_state(texte, champs)
            if maux:
                if any(k == "structure" for k, _ in maux):
                    tete = "ne serait plus lisible par le tableau de bord"
                else:
                    tete = "n'est pas à jour"
                liste = " ; ".join(m for _, m in maux)
                return ("mind-guard : `%s` %s — %s. Corrige, réindexe (`git add %s`), "
                        "puis recommite." % (state, tete, liste, state))

    # 2. FRAÎCHEUR — du code sort, la déclaration doit suivre.
    code = [f for f in fichiers if est_du_code(f, lot, projet)]
    if not code:
        return None

    # Le projet doit savoir dire où il va. `.fact/base.md` porte le `cap:` —
    # il a quitté `state.md` le 04/09/2026, parce qu'un projet n'a qu'une
    # destination même à plusieurs agents.
    if faits is not None:
        if d_fact is not None:
            contenu = lis_disque(os.path.join(d_fact, "base.md"))
        else:
            rc, tete = g.run(["show", "HEAD:%sbase.md" % faits])
            s = indexe(g, "%sbase.md" % faits)
            if s is not None and s != "":
                contenu = s
            else:
                contenu = tete if rc == 0 else ""
        if not champ(entete(contenu), "cap"):
            return (
                "mind-guard : `%sbase.md` ne porte pas de `cap:` — le tableau de bord n'a alors "
                "AUCUNE réponse au niveau du projet, quel que soit le nombre d'agents qui s'y "
                "déclarent. Écris-y l'en-tête `---` avec `cap:`, puis recommite (` # fact-ok`, "
                "c'est `.fact/`)." % faits)

    # DÉPORTÉ, `state.md` n'est JAMAIS dans l'index du dépôt de code : exiger
    # qu'il y soit bloquerait tous les commits, pour toujours. La règle devient
    # « il doit être plus récent que le code », lue sur le disque.
    if d_mind is not None:
        # LES CHEMINS DE `git diff --cached` SONT RELATIFS À LA RACINE DU DÉPÔT,
        # jamais au dossier courant — les stat-er tels quels ne trouverait rien,
        # et le garde laisserait tout passer sans le dire.
        rc, out = g.run(["rev-parse", "--show-toplevel"])
        if rc != 0:
            return None
        rr = out.strip(BLANCS)
        try:
            s = os.stat(os.path.join(d_mind, "state.md")).st_mtime_ns
        except OSError:
            return None
        recent = None
        for f in code:
            try:
                t = os.stat(os.path.join(rr, f)).st_mtime_ns
            except OSError:
                continue
            if recent is None or t > recent:
                recent = t
        if recent is None:
            return None
        if s >= recent:
            return None
        return (
            "mind-guard : du code projet est indexé (%s) alors que ta déclaration d'état n'a "
            "pas bougé depuis. C'est ce que le tableau de bord lit pour savoir où en est ce "
            "projet. Mets `.mind/state.md` à jour (dont le champ `maj:`), puis recommite. Si "
            "elle n'a vraiment pas à bouger, ajoute ` # mind-ok` à la fin de la commande.\n\n"
            "Ta mémoire est DÉPORTÉE dans `memoire/` : il n'y a rien à `git add`, elle est "
            "versionnée à part et commitée toute seule en fin de tour." % echantillon(code, 5))

    if state not in fichiers:
        return (
            "mind-guard : du code projet est indexé (%s) sans mise à jour de `%s`. C'est ce "
            "que le tableau de bord lit pour savoir où en est ce projet — pas poussé, mais lu "
            "sur le disque : un commit qui le laisse en arrière rend le projet muet. Mets-le à "
            "jour (dont le champ `maj:`), indexe-le (`git add %s`), puis recommite. Si la "
            "déclaration n'a vraiment pas à bouger, ajoute ` # mind-ok` à la fin de la "
            "commande.\n\n`.mind/todo.md` n'est plus exigé ICI — c'est le hook `Stop` qui le "
            "réclame, à chaque fin de tour." % (echantillon(code, 5), state, state))
    return None


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


def main(entree):
    # LE CHEMIN « RIEN À FAIRE » — presque toutes les commandes Bash : pas un mot
    # `commit` dans le texte, donc pas de `git commit`. Seule une échappation
    # `\uXXXX` pourrait le déguiser, et elle part au chemin complet. Rien n'est
    # importé avant ce test.
    if "commit" not in entree and "\\u" not in entree:
        return
    import memoire
    depart = memoire.depart_defaut()
    motif = juge(entree, depart)
    if motif is not None:
        import json
        import sys
        sys.stdout.write(json.dumps(refus(motif)) + "\n")
    # Pas de sortie = décision par défaut (allow).
