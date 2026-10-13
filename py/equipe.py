# -*- coding: utf-8 -*-
"""PASSER UN PROJET EN ÉQUIPE — ou lui ajouter un agent.

Port de `harnais/src/equipe.rs` (Rust, Copilot 1.3.0) ; le Rust gagne. Même
sortie, mêmes fichiers. Seule différence de texte voulue : le dossier des
livrables d'un agent compact se nomme `assets/` ici (`agent.BANC`), `outputs/`
dans le Rust.

UNE SEULE COMMANDE, DEUX COMPORTEMENTS, ET C'EST LA FORME DU PROJET QUI
DÉCIDE. Sur un projet mono elle convertit et crée les premiers agents ; sur
un projet déjà multi elle en ajoute un.

    en `brain/`      brain/mind/{state,todo}.md -> brain/mind/<premier>/
                     brain/fact/roles.md, carnet dans brain/workspace/
    à l'ancienne     .mind/                     -> agents/<premier>/.mind/
                     .fact/roles.md, carnet dans equipe/
    dans les deux    .github/copilot/settings.json à la racine Git
                     .github/agents/<nom>.agent.md, le profil du menu d'agent
                     .github/copilot/perimetre.json pour la garde d'écriture
                     agents/<autres>/AGENTS.md pour le rôle

`--profils` MET À NIVEAU un projet déjà en équipe sans lui ajouter d'agent :
profils manquants, périmètres réécrits en chemins relatifs.

CE QU'ELLE NE FAIT PAS : découper le `AGENTS.md` du projet (éditorial),
toucher aux faits, aux traces ni au code.

**À blanc par défaut.** `--apply` (ou `--go`) pour écrire.

DIVERGENCE CONNUE avec le Rust : le gabarit des rôles ne voyage plus DANS le
programme (`include_str!`) ; il se lit à l'appel dans
`skills/agentic-agents/templates/roles.md` du paquet, à côté de `py/`. Les
messages d'erreur d'un JSON illisible sont ceux de Python, pas ceux de serde.
"""
import copy
import json
import os
import re
import shutil
import sys

ROLE = """# {} — rôle

> Le `AGENTS.md` du projet est **hérité** : il est chargé en même temps que
> celui-ci, à chaque démarrage. N'y recopier AUCUNE de ses phrases. Le test :
> si une phrase resterait vraie pour un autre agent du projet, elle est à
> l'étage au-dessus.

## Ce que cet agent tient

[LE_PÉRIMÈTRE — en dossiers, pas en intentions. « orienté produit » n'empêche
personne de toucher au backend ; la frontière qui tient est celle écrite en
le périmètre affiché par le briefing et appliqué par la garde.]

## Ce qu'il ne touche pas

[LES_AUTRES_LOTS — et qui les tient.]
"""


def _gabarit_roles():
    ici = os.path.dirname(os.path.abspath(__file__))
    chemin = os.path.join(os.path.dirname(ici), "skills", "agentic-agents", "templates", "roles.md")
    with open(chemin, encoding="utf-8", newline="") as f:
        return f.read()


def role_qa():
    return ("# QA — épreuve indépendante et documentation\n\n"
            "Auditer sans réparer le code ni la production et sans diriger les autres lots.\n"
            "Écrire ses plans et grilles dans ses livrables, tenir son état et sa todo.\n"
            "Les cinq fichiers de faits (base, stack, architecture, rules, roles) ne sont\n"
            "modifiables qu'après validation explicite de l'humain ; conserver cap,\n"
            "provenance, dates et distinction entre mesure et information rapportée.\n"
            "Un commit documentaire est permis dans ce périmètre : mettre son état à jour,\n"
            "utiliser ` # fact-ok` uniquement pour les faits autorisés, jamais ` # mind-ok`.\n"
            "Ne pas modifier les sources d'audit, les instructions, gardes, mémoires des\n"
            "pairs ou le carnet automatique. Ne pas lire ni écrire operations.md, .env\n"
            "ou secrets ; ne pas exécuter de pipeline ni changer une base ou un cloud.\n"
            "Tous les outils lui sont ouverts, MCP compris, mais en lecture seule : jamais\n"
            "d'écriture sur un système. Il fait les plans que les autres agents exécutent.\n"
            "La garde de fichiers ne confine pas le shell/MCP ; elle ne prouve pas\n"
            "la disponibilité d'accès en lecture. Nommer l'arbre, la preuve et les limites.\n")


def role(nom):
    if est_qa(nom):
        return role_qa()
    return ROLE.replace("{}", nom, 1)


def est_qa(nom):
    """`eq_ignore_ascii_case("QA")`."""
    return len(nom) == 2 and nom.isascii() and nom.lower() == "qa"


def allow_par_defaut(nom, fact, mind, livrables):
    """Seul QA reçoit une liste autorisée par défaut (sa mémoire, son établi et les
    faits). OPS et PO n'ont qu'une liste de refus — le territoire de leurs pairs — et
    tout le reste leur est permis : un périmètre sépare les agents, il ne borne pas
    ce qu'un agent sait faire."""
    if not est_qa(nom):
        return None
    import socle
    allow = [mind, livrables]
    allow.extend("%s/%s" % (fact, f) for f in socle.faits_tous())
    return allow


def _p(s=""):
    sys.stdout.write(s + "\n")


def _e(s=""):
    sys.stderr.write(s + "\n")


# ── chemins : la sémantique de `std::path` ──────────────────────────────────

def err_es(e):
    """Une erreur d'E/S comme le Rust l'écrit : `<message> (os error N)`."""
    if isinstance(e, UnicodeDecodeError):
        return "stream did not contain valid UTF-8"
    if getattr(e, "errno", None):
        return "%s (os error %d)" % (os.strerror(e.errno), e.errno)
    return str(e)


def composants(p):
    """`Path::components()` : le lecteur, la racine, puis les composants nommés.
    Les séparateurs répétés et les `.` disparaissent, sauf un `.` en tête."""
    p = str(p)
    nt = os.name == "nt"
    out = []
    lecteur, reste = os.path.splitdrive(p) if nt else ("", p)
    if lecteur:
        out.append(lecteur)
    racine = bool(reste) and reste[0] in ("/\\" if nt else "/")
    if racine:
        out.append(os.sep)
    parts = re.split(r"[/\\]+" if nt else "/+", reste)
    normaux = [x for x in parts if x not in ("", ".")]
    if not out and parts and parts[0] == ".":
        out.append(".")
    return out + normaux


def strip_prefix(p, base):
    """`Path::strip_prefix` : la liste des composants restants, ou None."""
    cp, cb = composants(p), composants(base)
    if cp[:len(cb)] == cb:
        return cp[len(cb):]
    return None


def meme_chemin(a, b):
    return composants(a) == composants(b)


def file_name(p):
    """`Path::file_name` : le dernier composant nommé, ou None."""
    c = composants(p)
    if not c:
        return None
    d = c[-1]
    if d in (".", "..") or d == os.sep or (os.name == "nt" and d.endswith(":")):
        return None
    return d


def nom(p):
    n = file_name(p)
    return n if n is not None else ""


def rel(racine, p):
    """Le chemin sous `racine` si possible, en `/` ; sinon tel quel, composants joints."""
    r = strip_prefix(p, racine)
    return "/".join(r if r is not None else composants(p))


def canonicalize(p):
    """`Path::canonicalize` : le chemin réel, ou None s'il n'existe pas."""
    p = str(p)
    if not os.path.exists(p):
        return None
    try:
        return os.path.realpath(p)
    except (OSError, ValueError):
        return None


def slug(p):
    """Tout ce qui n'est pas alphanumérique devient un tiret, et une suite de tels
    caractères UN SEUL : deux noms d'agents qui donnent la même clé auraient les
    mêmes dossiers d'état."""
    out = []
    dans = False
    for c in p:
        if c.isascii() and c.isalnum():
            out.append(c)
            dans = False
        elif not dans:
            out.append("-")
            dans = True
    return "".join(out)


def git(p, a):
    import subprocess
    try:
        r = subprocess.run(["git", "-C", str(p)] + list(a), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return False
    return r.returncode == 0


# ── fichiers ────────────────────────────────────────────────────────────────

def _refuse_constante(c):
    raise ValueError(c)


def lis_json(texte):
    return json.loads(texte, parse_constant=_refuse_constante)


def json_indent2(v):
    """Le JSON tel que `serde_json::to_string_pretty` l'écrit (= `indent=2`)."""
    return json.dumps(v, indent=2, ensure_ascii=False)


def json_compact(v):
    """`Value::to_string` : sans espace."""
    return json.dumps(v, separators=(",", ":"), ensure_ascii=False)


def lis(chemin):
    """`fs::read_to_string`. Lève OSError ou UnicodeDecodeError."""
    with open(chemin, encoding="utf-8", newline="") as f:
        return f.read()


def ecrit(chemin, texte):
    """`fs::write`. Lève OSError."""
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        f.write(texte)


def _ecrit_ou_rien(chemin, texte):
    try:
        ecrit(chemin, texte)
    except OSError:
        pass


def _mkdirs(d):
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass


def _mkdirs_ou_refus(d):
    import copilot
    try:
        os.makedirs(d, exist_ok=True)
    except OSError as e:
        raise copilot.Refus(err_es(e))


def _lis_ou_refus(chemin):
    import copilot
    try:
        return lis(chemin)
    except (OSError, UnicodeDecodeError) as e:
        raise copilot.Refus(err_es(e))


def _ecrit_ou_refus(chemin, texte):
    import copilot
    try:
        ecrit(chemin, texte)
    except OSError as e:
        raise copilot.Refus(err_es(e))


def _json_ou_refus(texte, chemin=None):
    import copilot
    try:
        return lis_json(texte)
    except (ValueError, RecursionError) as e:
        raise copilot.Refus(("%s : %s" % (chemin, e)) if chemin is not None else str(e))


# ── profils ─────────────────────────────────────────────────────────────────

def profil_role(p, n, appliquer, rap):
    import agent
    import copilot
    f = agent.profil(p, n)
    if os.path.exists(f):
        raise copilot.Refus("%s existe déjà ; réconcilier le rôle avant de créer cet agent" % f)
    rap.append(("+", "%s — profil et rôle uniques ; livrables dans %s/" % (rel(p, f), agent.banc(n))))
    if appliquer:
        s = agent.nom_de_profil(n)
        texte = ("---\nname: %s\ndescription: Agent %s — rôle propre au projet\n---\n"
                 "Lis brain/mind/%s/state.md et brain/mind/%s/todo.md à la reprise. "
                 "Le harnais applique .github/copilot/perimetres/%s.json.\n\n"
                 "<!-- harnais:role:start -->\n%s<!-- harnais:role:end -->\n"
                 % (s, n, n, n, s, role(n)))
        _mkdirs_ou_refus(os.path.dirname(f))
        _ecrit_ou_refus(f, texte)


def trie(d):
    try:
        return [os.path.join(d, n) for n in sorted(os.listdir(d))]
    except OSError:
        return []


class Disposition(object):
    """OÙ VIVENT LES FAITS ET LES ESPRITS — la seule chose qui change entre les
    deux organisations. En `brain/`, l'esprit d'un agent vit dans le CERVEAU,
    rangé par nom : `agents/<nom>/` ne porte plus que le rôle et les réglages."""

    def __init__(self, racine, cerveau, faits):
        self.racine = racine
        self.cerveau = cerveau
        self.faits = faits

    def esprit(self, n):
        if self.cerveau:
            return os.path.join(self.racine, "brain/mind", n)
        return os.path.join(self.racine, "agents", n, ".mind")

    def esprit_mono(self):
        return os.path.join(self.racine, "brain/mind" if self.cerveau else ".mind")

    def etiquette_faits(self):
        return "brain/fact" if self.cerveau else ".fact"

    def rel(self, p):
        return rel(self.racine, p)


def forme(p):
    """La forme du projet. MULTI se reconnaît à un esprit PAR AGENT, et l'endroit
    où le chercher dépend de l'organisation — chercher au seul ancien endroit
    déclarait « mono » un projet `brain/` déjà converti."""
    j = os.path.join
    cerveau = os.path.isdir(j(p, "brain/fact"))
    disp = Disposition(p, cerveau, j(p, "brain/fact" if cerveau else ".fact"))
    if cerveau:
        etats = [nom(d) for d in trie(j(p, "brain/mind"))
                 if os.path.isdir(d) and os.path.isfile(j(d, "state.md"))]
    else:
        etats = [nom(d) for d in trie(j(p, "agents")) if os.path.isdir(j(d, ".mind"))]
    if etats:
        return "multi", etats, disp
    if cerveau or os.path.isdir(j(p, ".fact")):
        return "mono", [], disp
    return "ancienne", [], disp


# ── les réglages et les périmètres ──────────────────────────────────────────

def reglages_racine(projet, appliquer, rap):
    """Le plugin est déclaré une fois à la racine Git ; chaque agent garde son périmètre local."""
    import copilot
    racine = copilot.racine_git(projet)
    cible = copilot.settings(racine)
    if os.path.isfile(cible):
        d = _json_ou_refus(_lis_ou_refus(cible), cible)
    else:
        d = {}
    avant = copy.deepcopy(d)
    copilot.reglages(d, copilot.paquet())
    if d != avant:
        rap.append(("+", "%s — déclaration Copilot unique à la racine Git" % rel(projet, cible)))
        if appliquer:
            _mkdirs_ou_refus(os.path.dirname(cible))
            _ecrit_ou_refus(cible, json_indent2(d) + "\n")


def perimetre_agent(cible, projet, autres, appliquer, rap):
    """LE PÉRIMÈTRE D'UN AGENT, EN CHEMINS RELATIFS À LA RACINE DU PROJET.

    Jusqu'en 0.15.0 il était écrit en ABSOLU, donc vers le dossier principal :
    dans une copie de travail de l'app, aucune écriture n'y tombait et la garde
    laissait tout passer. Relatif, il se pose sur la copie où l'on travaille.
    Les entrées existantes sous le projet sont réécrites en relatif ; celles
    qui visent un dossier hors du projet restent telles quelles."""
    import agent
    import copilot
    copilot.avertit_settings_agent(cible)
    denies = ["agents/%s" % a for a in autres]
    est_compact = composants(cible)[:-1] == composants(os.path.join(projet, "brain/mind"))
    n_cible = nom(cible)
    if est_compact:
        for a in autres:
            denies.append("brain/mind/%s" % a)
            denies.append(agent.banc(a))
        denies.extend(agent.CONTROLE)
        denies.append("brain/poids.json")
        if not est_qa(n_cible):
            denies.append("brain/fact")
        perimetre = agent.perimetre_compact(projet, n_cible)
    else:
        perimetre = os.path.join(cible, ".github/copilot/perimetre.json")
    nouveau = not os.path.exists(perimetre)
    if not est_compact and nouveau and est_qa(n_cible):
        denies.extend(agent.CONTROLE)
        denies.append("brain/poids.json")
        for a in autres:
            denies.append("brain/mind/%s" % a)
            denies.append(agent.banc(a))
    if os.path.exists(perimetre):
        if est_compact:
            copilot.lis_allow(cible)
        base = canonicalize(projet) or str(projet)
        for chemin in copilot.lis_deny(cible):
            # `\\x` sous Windows n'a pas de lecteur mais a une racine : il n'est
            # PAS relatif au projet, il reste tel qu'écrit.
            if copilot._sans_racine(chemin):
                ecrit_ = rel("", chemin)
            elif not copilot._absolu(chemin):
                ecrit_ = chemin
            else:
                c = canonicalize(chemin) or chemin
                if meme_chemin(c, base):
                    ecrit_ = "."
                elif strip_prefix(c, base) is not None:
                    ecrit_ = rel(base, c)
                else:
                    ecrit_ = chemin
            if ecrit_ and ecrit_ not in denies:
                denies.append(ecrit_)
    rap.append(("+", "%s — %d dossier(s) interdits par la garde Edit|Write" % (rel(projet, perimetre), len(denies))))
    if appliquer:
        _mkdirs_ou_refus(os.path.dirname(perimetre))
        if os.path.exists(perimetre):
            garde = _json_ou_refus(_lis_ou_refus(perimetre))
        else:
            garde = {}
        avant = copy.deepcopy(garde)
        garde["deny"] = denies
        if (est_compact or (nouveau and est_qa(n_cible))) and "allow" not in garde:
            n = n_cible
            cerveau = os.path.isdir(os.path.join(projet, "brain/fact"))
            fact = "brain/fact" if cerveau else ".fact"
            mind = "brain/mind/%s" % n if cerveau else "agents/%s/.mind" % n
            livrables = agent.banc(n) if est_compact else "agents/%s/livrables" % n
            a = allow_par_defaut(n, fact, mind, livrables)
            if a is not None:
                garde["allow"] = a
        if not os.path.exists(perimetre) or garde != avant:
            _ecrit_ou_refus(perimetre, json_indent2(garde) + "\n")


def profil(racine_git, projet, n, esprit, appliquer, rap):
    """LE PROFIL DU MENU D'AGENT — `.github/agents/<nom>.agent.md`, à la racine Git.

    L'app Copilot lance chaque conversation à la racine d'une copie de travail :
    le dossier `agents/<nom>/` ne dit plus qui parle. Ce profil fait apparaître
    l'agent dans le menu du champ de saisie ; le harnais lit ensuite le choix
    dans le journal de session et sert le rôle, l'état et le périmètre (voir
    `agent`). Le profil reste COURT : il ne recopie pas le rôle, qui n'a qu'une
    maison. Sa dernière phrase est le secours d'une session sans harnais.
    Jamais écrasé : un profil existant est peut-être déjà ajusté à la main."""
    import agent
    nom_profil = agent.nom_de_profil(n)
    if not nom_profil:
        rap.append(("⚠", "agent %s : aucun nom de profil possible — profil non écrit" % n))
        return
    f = os.path.join(racine_git, ".github/agents", "%s.agent.md" % nom_profil)
    if os.path.exists(f):
        rap.append(("·", "%s existe : non écrasé" % rel(projet, f)))
        return
    rap.append(("+", "%s — l'agent %s dans le menu d'agent de l'app" % (rel(projet, f), n)))
    if appliquer:
        role_ = "agents/%s/AGENTS.md" % n
        etat = rel(projet, esprit)
        texte = ("---\nname: %s\ndescription: Agent %s de %s — son rôle est dans %s\n---\n"
                 "Tu es l'agent %s de ce projet. À chaque ouverture, le harnais te sert ton rôle (%s), "
                 "ton état (%s/) et ton périmètre d'écriture.\n\n"
                 "S'il ne te les a pas montrés, lis d'abord %s, puis %s/state.md et %s/todo.md, avant toute réponse.\n"
                 % (nom_profil, n, nom(projet), role_, n, role_, etat, role_, etat, etat))
        _mkdirs(os.path.dirname(f))
        _ecrit_ou_rien(f, texte)


def profils_en_collision(tous):
    """Deux agents dont les profils porteraient le même nom : le menu n'en
    montrerait qu'un, et le choix désignerait le mauvais dossier."""
    import agent
    for i, a in enumerate(tous):
        for b in tous[i + 1:]:
            if agent.nom_de_profil(a) == agent.nom_de_profil(b):
                return "%s et %s donnent le même profil « %s »" % (a, b, agent.nom_de_profil(a))
    return None


def mise_a_niveau(p, appliquer):
    """`--profils` : un projet DÉJÀ en équipe, mis à niveau sans nouvel agent."""
    import agent
    import compact
    import copilot
    f, existants, disp = forme(p)
    if f != "multi":
        _e("equipe --profils : ce projet n'est pas en équipe (%s) — rien à mettre à niveau. "
           "Pour le passer en équipe : `harnais equipe --agents A,B`." % f)
        return 1
    c = profils_en_collision(existants)
    if c is not None:
        _e("equipe --profils : %s ; rien n'est écrit" % c)
        return 1
    if any(agent.compact(p, n) for n in existants):
        return compact.main(p, appliquer)
    try:
        racine = copilot.racine_git(p)
    except copilot.Refus as e:
        _e("equipe : %s" % e)
        return 1
    rap = []
    for n in existants:
        d = os.path.join(p, "agents", n)
        autres = [x for x in existants if x != n]
        try:
            perimetre_agent(d, p, autres, appliquer, rap)
        except copilot.Refus as e:
            _e("equipe : %s" % e)
            return 1
        profil(racine, p, n, disp.esprit(n), appliquer, rap)
    _p("── profils — %s (%s)%s" % (nom(p), ", ".join(existants), "" if appliquer else "  [DRY-RUN]"))
    for signe, ligne in rap:
        _p("  %s %s" % (signe, ligne))
    _p("\n── À reprendre à la main")
    _p("  · %s" % a_commiter(existants))
    if not appliquer:
        _p("\nDry-run. Relancer avec --apply pour écrire.")
    return 0


def a_commiter(tous):
    """La dernière consigne, la même pour les deux chemins."""
    import agent
    return ("COMMITER `.github/agents/` et les périmètres : une nouvelle conversation de l'app part de "
            "l'état COMMITÉ, un profil non commité n'apparaît pas dans le menu. Ensuite, choisir l'agent dans le menu "
            "d'agent du champ de saisie (%s) ; dans le CLI, `copilot --agent <nom>` ou une session lancée dans "
            "`agents/<nom>/` pour la forme historique. En compact : `copilot --agent <nom>` "
            "depuis la racine. Sans agent choisi, %s tient la session s'il existe — le briefing le dit."
            % (", ".join(agent.nom_de_profil(n) for n in tous), agent.DEFAUT))


def porte_les_non_herites(projet, cible, appliquer, rap):
    """Le serveur MCP du projet peut être propre à un agent : copier uniquement .mcp.json."""
    for r in [".mcp.json"]:
        src = os.path.join(projet, r)
        if not os.path.isfile(src):
            continue
        rap.append(("+", "%s/%s — copié depuis la racine (ne s'hérite pas)" % (rel(projet, cible), r)))
        if appliquer:
            dst = os.path.join(cible, r)
            if os.path.exists(dst):
                rap.append(("·", "%s existe : non écrasé" % dst))
                continue
            _mkdirs(os.path.dirname(dst))
            try:
                shutil.copy(src, dst)
            except (OSError, shutil.Error):
                pass


def valeur(args, cle):
    it = iter(args)
    for a in it:
        if a == cle:
            return next(it, None)
        if a.startswith(cle + "="):
            return a[len(cle) + 1:]
    return None


AIDE = ("harnais equipe --agents A,B[,C] [--project-root P] [--apply]\n"
        "harnais equipe --profils [--project-root P] [--apply]\n"
        "harnais equipe --compact [--agents A,B] [--project-root P] [--apply]\n\n"
        "Passe un projet mono en équipe (le PREMIER nommé hérite de l'état existant),\n"
        "ou ajoute des agents à un projet déjà en équipe. Chaque agent reçoit son profil\n"
        "`.github/agents/<nom>.agent.md`, qui le fait apparaître dans le menu d'agent de l'app.\n"
        "`--profils` met à niveau un projet déjà en équipe : profils manquants, périmètres\n"
        "en chemins relatifs. `--compact` exporte une équipe existante vers les profils-rôles\n"
        "et périmètres centralisés, ou crée les agents demandés sous cette forme.\n"
        "Les anciens dossiers et livrables ne sont jamais supprimés. À blanc par défaut.")


def main(args):
    import agent
    import carnet
    import compact as compact_mod
    import copilot
    if any(a == "-h" or a == "--help" for a in args):
        _p(AIDE)
        return 0
    if "--compact" in args and not any(a == "--agents" or a.startswith("--agents=") for a in args):
        p = valeur(args, "--project-root")
        if p is None:
            p = "."
        return compact_mod.main(p, any(a == "--apply" or a == "--go" for a in args))
    if "--profils" in args:
        p0 = valeur(args, "--project-root")
        if p0 is None:
            p0 = "."
        p = canonicalize(p0) or p0
        return mise_a_niveau(p, any(a == "--apply" or a == "--go" for a in args))
    liste = valeur(args, "--agents")
    if liste is None:
        _e("harnais equipe : --agents est requis (noms séparés par des virgules ; "
           "le PREMIER hérite de l'état existant)")
        return 2
    appliquer = any(a == "--apply" or a == "--go" for a in args)
    p0 = valeur(args, "--project-root")
    if p0 is None:
        p0 = "."
    p = canonicalize(p0) or p0
    noms = [x.strip() for x in liste.split(",") if x.strip()]
    rap = []     # [(signe, ligne)]
    reste = []

    j = os.path.join
    f, existants, disp = forme(p)
    compact = "--compact" in args or any(agent.compact(p, n) for n in existants)
    if compact and not disp.cerveau:
        _e("equipe : l'architecture compacte exige brain/ ; migrer la mémoire d'abord")
        return 1
    if compact and f == "mono" and any(not os.path.isfile(j(disp.esprit_mono(), n))
                                       for n in ("state.md", "todo.md")):
        _e("equipe : mémoire mono incomplète ; compléter avant la conversion compacte")
        return 1
    copilot.avertit_ancien(p)
    if f == "ancienne":
        _p("Ce projet n'a de faits ni dans `brain/fact/` ni dans `.fact/`. "
           "Lancer d'abord la migration de mémoire, puis revenir.")
        return 1
    if not noms or any(n in existants for n in noms):
        _e("equipe : liste vide ou agent déjà présent ; aucun fichier n'a été écrasé")
        return 1
    if any(n == "." or n == ".." or any(c in n for c in "/\\:") or not agent.nom_de_profil(n)
           for n in noms):
        _e("equipe : nom d'agent invalide ; aucune écriture")
        return 1
    if compact and f == "multi" and any(not agent.compact(p, n) for n in existants):
        _e("equipe : exporter toute l'équipe avec --compact avant d'ajouter un agent compact ; aucune écriture")
        return 1
    if compact and any(os.path.exists(agent.profil(p, n)) for n in noms):
        _e("equipe : un profil demandé existe déjà ; réconcilier avant de créer l'agent")
        return 1
    c = profils_en_collision(list(existants) + list(noms))
    if c is not None:
        _e("equipe : %s — le menu d'agent n'en montrerait qu'un ; aucun fichier n'a été écrit" % c)
        return 1
    try:
        racine = copilot.racine_git(p)
    except copilot.Refus as e:
        _e("equipe : %s" % e)
        return 1
    try:
        reglages_racine(p, appliquer, rap)
    except copilot.Refus as e:
        _e("equipe : %s" % e)
        return 1
    if f == "mono":
        premier = noms[0]
        cible = disp.esprit(premier) if compact else j(p, "agents", premier)
        src, dst = disp.esprit_mono(), disp.esprit(premier)
        # Cerveau : `brain/mind/` NE bouge PAS, ce sont ses FICHIERS qui
        # descendent d'un cran. Ancienne forme : le dossier descend en entier.
        rap.append(("→", "%s -> %s (l'agent qui était là garde sa mémoire)" % (disp.rel(src), disp.rel(dst))))
        if appliquer:
            if disp.cerveau:
                _mkdirs(dst)
                for fic in trie(src):
                    if os.path.isfile(fic):
                        cible_f = j(dst, nom(fic))
                        if not git(p, ["mv", disp.rel(fic), disp.rel(cible_f)]):
                            try:
                                os.rename(fic, cible_f)
                            except OSError:
                                pass
            else:
                _mkdirs(os.path.dirname(dst))
                if not git(p, ["mv", disp.rel(src), disp.rel(dst)]):
                    try:
                        os.rename(src, dst)
                    except OSError:
                        pass
        try:
            perimetre_agent(cible, p, noms[1:], appliquer, rap)
        except copilot.Refus as e:
            _e("equipe : %s" % e)
            return 1
        if not compact:
            porte_les_non_herites(p, cible, appliquer, rap)

        # Le premier agent hérite de l'état, pas d'un rôle : il lui faut le sien.
        if compact:
            try:
                profil_role(p, premier, appliquer, rap)
            except copilot.Refus as e:
                _e("equipe : %s" % e)
                return 1
        elif os.path.exists(j(cible, "CLAUDE.md")):
            rap.append(("⚠", "agents/%s/CLAUDE.md existe : ne pas doubler le rôle" % premier))
        else:
            rap.append(("+", "agents/%s/AGENTS.md — rôle à remplir" % premier))
            if appliquer and not os.path.exists(j(cible, "AGENTS.md")):
                _ecrit_ou_rien(j(cible, "AGENTS.md"), role(premier))
        neufs = noms[1:]
        tous = list(noms)
    else:
        neufs = list(noms)
        tous = list(existants) + list(noms)

    if f == "multi":
        for ancien in existants:
            d = agent.contexte(p, ancien)
            autres = [n for n in tous if n != ancien]
            try:
                perimetre_agent(d, p, autres, appliquer, rap)
            except copilot.Refus as e:
                _e("equipe : %s" % e)
                return 1

    import datetime
    jour = datetime.datetime.now().strftime("%Y-%m-%d")
    for n in neufs:
        d = disp.esprit(n) if compact else j(p, "agents", n)
        esprit = disp.esprit(n)
        rap.append(("+", "%s — esprit neuf ; rôle et périmètre %s" % (
            disp.rel(esprit), "centralisés" if compact else "dans agents/")))
        if appliquer:
            _mkdirs(esprit)
            _mkdirs(d)
            if not compact and not os.path.exists(j(d, "CLAUDE.md")) and not os.path.exists(j(d, "AGENTS.md")):
                _ecrit_ou_rien(j(d, "AGENTS.md"), role(n))
            _ecrit_ou_rien(j(esprit, "state.md"),
                           "---\nmaj: %s\nsante: vert\njalon: [LE_PROCHAIN_CAILLOU de ce lot]\n---\n\n"
                           "# État — %s\n\n[où en est CET agent]\n" % (jour, n))
            _ecrit_ou_rien(j(esprit, "todo.md"), "# À faire — %s\n\n- [ ] [première tâche de ce lot]\n" % n)
        if compact:
            try:
                profil_role(p, n, appliquer, rap)
            except copilot.Refus as e:
                _e("equipe : %s" % e)
                return 1
        autres = [x for x in tous if x != n]
        copilot.avertit_ancien(d)
        try:
            perimetre_agent(d, p, autres, appliquer, rap)
        except copilot.Refus as e:
            _e("equipe : %s" % e)
            return 1
        if not compact:
            porte_les_non_herites(p, d, appliquer, rap)

    # LES PROFILS DU MENU D'AGENT — tous, anciens compris : un projet converti
    # avant 0.16.0 n'en a aucun.
    if not compact:
        for n in tous:
            profil(racine, p, n, disp.esprit(n), appliquer, rap)

    # LE CARNET D'ÉQUIPE — LU partout, il ne serait CRÉÉ nulle part sans cet
    # appel. On appelle la règle qui le place, on ne la recopie pas.
    if appliquer:
        e = carnet.amorce(p)
        if e is not None:
            rap.append(("+", "carnet d'équipe amorcé : %s" % rel(p, e)))
        else:
            rap.append(("⚠", "carnet d'équipe NON amorcé : le programme n'a rien rendu"))
    else:
        rap.append(("+", "carnet d'équipe à amorcer (créé à l'application)"))

    # Le cinquième fichier, qui n'existe qu'en équipe : chacun connaît sa
    # frontière et ignore celle des autres — ici, chacun lit TOUT le découpage.
    fichier_roles = j(disp.faits, "roles.md")
    if os.path.isdir(disp.faits) and not os.path.exists(fichier_roles):
        rap.append(("+", "%s/roles.md — qui tient quoi, à remplir" % disp.etiquette_faits()))
        if appliquer:
            # La maison des faits est NOMMÉE, jamais écrite en dur : le gabarit
            # sert les deux organisations. Écrire `.fact/` en dur le poserait
            # aussi dans un projet en `brain/`.
            texte = _gabarit_roles().replace("[PROJECT_NAME]", nom(p)).replace("[FAITS]", disp.etiquette_faits())
            for i, n in enumerate(tous):
                texte = texte.replace("`<agent-%d>`" % (i + 1), "`%s`" % n)
            _ecrit_ou_rien(fichier_roles, texte)
        reste.append("REMPLIR %s/roles.md — qui tient quoi, et surtout LES ZONES PARTAGÉES. Un "
                     "périmètre propre se lit dans la garde Copilot ; une zone partagée ne se lit nulle part, et c'est là que les "
                     "collisions arrivent. Ce sont des FAITS : ça s'écrit à la demande de @user (` # fact-ok` au commit)."
                     % disp.etiquette_faits())
    reste.append("DÉCOUPER AGENTS.md — le commun reste à la racine, le rôle descend dans %s. "
                 "Contrôle de sortie : aucune phrase du bas ne resterait vraie pour un autre agent."
                 % (".github/agents/<nom>.agent.md" if compact else "agents/<nom>/AGENTS.md"))
    reste.append("ÉCRIRE LES PÉRIMÈTRES en dossiers dans chaque perimetre.json : les dossiers interdits ne couvrent "
                 "que les dossiers d'agents. Le code, lui, n'est pas partagé au hasard — dire qui tient quoi.")
    reste.append(a_commiter(tous))

    _p("── agents — %s (%s)%s" % (nom(p), f, "" if appliquer else "  [DRY-RUN]"))
    for signe, ligne in rap:
        _p("  %s %s" % (signe, ligne))
    _p("\n── À reprendre à la main")
    for r in reste:
        _p("  · %s" % r)
    if not appliquer:
        _p("\nDry-run. Relancer avec --apply pour écrire.")
    return 0
