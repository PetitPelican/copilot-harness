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
import subprocess
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


# LES RÔLES TYPES (Claude, 14/10/2026). Le commanditaire : « tout ce qu'on a fait aujourd'hui
# doit apparaître si je veux redéployer une autre stack multi agent ». L'organisation
# éprouvée en situation réelle — OPS seul en Production, PO au produit, QA au contrôle et
# guichet unique des questions, NXT aux versions à venir — devient un gabarit :
# `--modeles ops,po,qa` aligné sur `--agents`. Rien d'un projet réel n'y est écrit.
MODELES = ("ops", "po", "qa", "nxt")
_TYPES = {}      # nom d'agent -> modèle, posé par main()


def _gabarit(*morceaux):
    ici = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(os.path.dirname(ici), "skills", "agentic-agents", "templates", *morceaux),
              encoding="utf-8", newline="") as f:
        return f.read()


def _qui(modele, defaut):
    for n, m in _TYPES.items():
        if m == modele:
            return n
    return defaut


def _remplit(texte, nom_agent, projet):
    agents = ", ".join("%s (%s)" % (n, m.upper()) for n, m in _TYPES.items()) or "[LES_AGENTS]"
    for k, v in (("{AGENT}", nom_agent), ("{PROJET}", projet or "[PROJET]"), ("{AGENTS}", agents),
                 ("{PROD}", _qui("ops", "l'agent OPS")), ("{GUICHET}", _qui("qa", "l'agent QA"))):
        texte = texte.replace(k, v)
    return texte


def role(nom, projet=""):
    m = _TYPES.get(nom)
    if m:
        return _remplit(_gabarit("roles", m + ".md"), nom, projet)
    if est_qa(nom):
        return role_qa()
    return ROLE.replace("{}", nom, 1)


def consignes_equipe(projet):
    """L'`AGENTS.md` commun d'une équipe typée : posé seulement s'il n'y en a pas."""
    return _remplit(_gabarit("equipe-AGENTS.md"), "", projet)


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
                 % (s, n, n, n, s, role(n, nom(p))))
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


def perimetre_agent(cible, projet, autres, appliquer, rap, equipe_forme=False):
    """LE PÉRIMÈTRE D'UN AGENT, EN CHEMINS RELATIFS À LA RACINE DU PROJET.

    Jusqu'en 0.15.0 il était écrit en ABSOLU, donc vers le dossier principal :
    dans une copie de travail de l'app, aucune écriture n'y tombait et la garde
    laissait tout passer. Relatif, il se pose sur la copie où l'on travaille.
    Les entrées existantes sous le projet sont réécrites en relatif ; celles
    qui visent un dossier hors du projet restent telles quelles.

    `equipe_forme` : l'équipe « un dossier par agent » (Claude 0.19). La mémoire est
    `fact/` et `agents/<nom>/`, jamais `brain/` : un QA neuf n'y reçoit donc ni les
    chemins du cerveau en refus, ni une liste autorisée qui pointerait `brain/…`."""
    import agent
    import copilot
    copilot.avertit_settings_agent(cible)
    denies = ["agents/%s" % a for a in autres]
    est_compact = (not equipe_forme) and composants(cible)[:-1] == composants(os.path.join(projet, "brain/mind"))
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
    if equipe_forme and nouveau and est_qa(n_cible):
        # QA ne répare pas le code : sa propre copie lui est fermée, comme le harnais.
        denies.extend(agent.CONTROLE)
        denies.append("agents/%s/code" % n_cible)
    elif not est_compact and nouveau and est_qa(n_cible):
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
            if equipe_forme:
                fact, mind, livrables = "fact", "agents/%s" % n, "docs/audit"
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
    import memoire
    if memoire.resous(p).forme == memoire.Forme.Equipe:
        return profils_equipe(memoire.resous(p).projet, appliquer)
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


def profils_equipe(x, appliquer):
    """`--profils` sur une équipe « un dossier par agent » : les profils du menu qui
    manquent et les périmètres réécrits en chemins relatifs — sans nouvel agent."""
    import copilot
    existants = [n for n in _agents_existants(x) if os.path.isfile(os.path.join(x, "agents", n, "state.md"))]
    c = profils_en_collision(existants)
    if c is not None:
        _e("equipe --profils : %s ; rien n'est écrit" % c)
        return 1
    try:
        racine = copilot.racine_git(x)
    except copilot.Refus as e:
        _e("equipe : %s" % e)
        return 1
    rap = []
    for n in existants:
        d = os.path.join(x, "agents", n)
        try:
            perimetre_agent(d, x, [a for a in existants if a != n], appliquer, rap, equipe_forme=True)
        except copilot.Refus as e:
            _e("equipe : %s" % e)
            return 1
        profil(racine, x, n, d, appliquer, rap)
    _p("── profils — %s (%s)%s" % (nom(x), ", ".join(existants), "" if appliquer else "  [DRY-RUN]"))
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


# ── « UN DOSSIER PAR AGENT » (Claude 0.17-0.19, 14-16/10/2026) ─────────────
#
# Ajouter ou retirer un agent en UNE commande — son dossier, son rôle, son état,
# ses droits, SA copie du code. C'est ce qui empêche les copies de se poser
# ailleurs : le bon geste est le plus court.
#
#     X/                  dépôt de la MÉMOIRE (ignore agents/*/code*/)
#       AGENTS.md         les règles communes de l'équipe (étage 3)
#       fact/ shared/ docs/ assets/
#       .github/          la déclaration du paquet (UNE, à la racine Git) et les
#                         profils du menu d'agent
#       agents/<nom>/     AGENTS.md · state.md · todo.md · code/
#                         .github/copilot/perimetre.json   ses droits
#
# CE QUE COPILOT FAIT AUTREMENT QUE CLAUDE, ET POURQUOI :
#   · pas de `.claude/settings.json` par agent : Copilot ne lit que la racine Git
#     pour la déclaration du paquet, et le périmètre d'écriture passe par la garde
#     de `copilot` (`perimetre.json`, chemins relatifs à la racine de l'équipe) ;
#   · pas de règles `Agent(isolation:worktree)` / `EnterWorktree` (SANS_COPIE_ISOLEE
#     chez Claude) : elles n'existent pas chez Copilot. La garde de commit
#     (`mind_guard.juge_copie`) refuse les copies posées hors du dossier de l'agent ;
#   · pas de `additionalDirectories` : la garde de Copilot ne borne pas la lecture ;
#   · un profil `.github/agents/<nom>.agent.md` par agent, pour le menu d'agent.

def _agents_existants(x):
    return [nom(d) for d in trie(os.path.join(x, "agents")) if os.path.isdir(d)]


def _branche(n):
    return slug(n).strip("-").lower()


def equipe_v3(x, noms, retirer, appliquer, naissance=False):
    """Ajoute (`noms`) ou retire (`retirer`) des agents d'une équipe « un dossier
    par agent ». Rend le code de sortie. À blanc sauf `appliquer`.

    Les périmètres des autres reçoivent UNE ligne (`deny` sur le nouveau dossier) :
    sans elle, un agent existant pourrait écrire chez le nouveau, et rien ne le
    dirait. C'est la seule écriture hors du dossier ajouté — avec le profil du menu
    d'agent et la déclaration du paquet, à la racine Git."""
    import adopte
    import agent
    import copilot
    j = os.path.join
    rap, reste = [], []
    agents = j(x, "agents")
    existants = _agents_existants(x)
    codes = [j(agents, n, "code") for n in existants if os.path.isdir(j(agents, n, "code"))]
    jour = __import__("datetime").date.today().isoformat()
    for n in retirer:
        d = j(agents, n)
        if not os.path.isdir(d):
            rap.append(("✗", "%s : pas d'agent à ce nom" % n))
            continue
        sales = []
        for c in [j(d, e) for e in os.listdir(d) if e == "code" or e.startswith("code-")]:
            o = subprocess.run(["git", "status", "--porcelain"], cwd=c, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
            if o.returncode != 0 or o.stdout.strip():
                sales.append(nom(c))
        if sales:
            rap.append(("✗", "%s : travail non enregistré dans %s — RIEN n'est retiré" % (n, ", ".join(sales))))
            continue
        rap.append(("→", "%s : copies du code retirées (git worktree remove), dossier et profil "
                         "retirés ; son état reste dans l'historique de la mémoire" % n))
        reste.append("retirer la ligne de %s dans `fact/roles.md` (faits : à la demande de @user), et "
                     "ses lignes `deny` dans les périmètres des autres" % n)
        if appliquer:
            # Les copies d'abord : un `worktree remove` lancé DEPUIS la copie à retirer
            # échoue ; on le lance depuis le dépôt qui la porte.
            for c in [j(d, e) for e in os.listdir(d) if e == "code" or e.startswith("code-")]:
                porteur = _porteur_du_code(c)
                subprocess.run(["git", "worktree", "remove", c], cwd=porteur or c,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "rm", "-r", "-q", "--", os.path.relpath(d, x)], cwd=x,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            shutil.rmtree(d, ignore_errors=True)
            try:
                os.remove(agent.profil(x, n))
            except OSError:
                pass
    for n in noms:
        d = j(agents, n)
        if os.path.exists(d):
            rap.append(("·", "%s : existe déjà, rien n'est touché" % n))
            continue
        rap.append(("→", "agents/%s/ : rôle%s, état, tâches, périmètre, profil du menu d'agent" % (
            n, (" type %s" % _TYPES[n].upper()) if n in _TYPES else "")))
        autres = [e for e in existants if e != n]
        if codes:
            rap.append(("→", "agents/%s/code : sa copie du code, branche `%s`" % (n, _branche(n))))
        elif not naissance:
            reste.append("aucune copie du code chez les autres agents : poser `agents/%s/code` à la main" % n)
        if autres:
            rap.append(("→", "périmètre : une ligne `deny` vers agents/%s/ chez %s" % (n, ", ".join(autres))))
        reste.append("décrire %s dans `fact/roles.md` (faits : à la demande de @user)" % n)
        if not appliquer:
            continue
        _mkdirs(d)
        _ecrit_ou_rien(j(d, "AGENTS.md"), role(n, nom(x)) if n in _TYPES else adopte.agents_md_agent(n, nom(x)))
        _ecrit_ou_rien(j(d, "state.md"), adopte.state_md(jour))
        _ecrit_ou_rien(j(d, "todo.md"), adopte.TODO_MD)
        copilot.avertit_ancien(d)
        sous_rap = []
        try:
            perimetre_agent(d, x, autres, True, sous_rap, equipe_forme=True)
            # Les autres : UNE ligne ajoutée, le reste intact (perimetre_agent garde les
            # entrées déjà écrites). Un agent sans périmètre n'en reçoit pas un neuf ici.
            for a in autres:
                da = j(agents, a)
                if os.path.isfile(copilot.fichier_perimetre(da)):
                    perimetre_agent(da, x, [e for e in existants + [n] if e != a], True, sous_rap,
                                    equipe_forme=True)
                else:
                    reste.append("périmètre de %s : aucun fichier, ligne non ajoutée" % a)
        except copilot.Refus as e:
            rap.append(("✗", "périmètre : %s" % e))
            return 1
        try:
            racine_git = copilot.racine_git(x)
            profil(racine_git, x, n, d, True, sous_rap)
        except copilot.Refus:
            reste.append("profil du menu d'agent de %s : pas de racine Git, profil non écrit" % n)
        if codes:
            o = subprocess.run(["git", "worktree", "add", "-q", "-b", _branche(n), j(d, "code")],
                               cwd=codes[0], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if o.returncode != 0:
                reste.append("copie du code de %s non posée : %s" % (n, o.stderr.decode("utf-8", "replace").strip()[:200]))
        existants.append(n)
    # La déclaration du paquet : UNE, à la racine Git.
    if noms:
        try:
            reglages_racine(x, appliquer, rap)
        except copilot.Refus as e:
            if appliquer:
                rap.append(("✗", "déclaration du paquet : %s" % e))
                return 1
            rap.append(("·", "déclaration du paquet à la racine Git (le dépôt n'existe pas encore)"))
    if _TYPES:
        if os.path.exists(j(x, "AGENTS.md")):
            reste.append("règles communes d'équipe (autonomie git, guichet {g}, Production à {o}) : l'AGENTS.md "
                         "du projet existe, le CTO y reporte le gabarit "
                         "`skills/agentic-agents/templates/equipe-AGENTS.md`".format(
                             g=_qui("qa", "QA"), o=_qui("ops", "OPS")))
        else:
            rap.append(("→", "AGENTS.md du projet : règles communes d'équipe (gabarit du paquet)"))
            if appliquer:
                _ecrit_ou_rien(j(x, "AGENTS.md"), consignes_equipe(nom(x)))
    _p("\n  ÉQUIPE — un dossier par agent   %s" % x)
    for sg, l in rap:
        _p("  %s %s" % (sg, l))
    if noms:
        reste.append(a_commiter(existants))
    if reste:
        _p("\n  RESTE À FAIRE")
        for l in reste:
            _p("  - %s" % l)
    if not appliquer:
        _p("\n  À blanc : rien n'est écrit. `--apply` pour le faire.")
    return 1 if any(sg == "✗" for sg, _ in rap) else 0


def _porteur_du_code(c):
    """Le dossier du dépôt qui porte la copie `c` (son checkout principal), ou None."""
    import memoire
    return memoire.racine_depot(c)


# ── NAÎTRE EN ÉQUIPE (Claude 0.19, 16/10/2026) ───────────────────────────
#
# Jusqu'ici une équipe neuve naissait dans la forme d'AVANT (`adopte --equipe` :
# `brain/mind/<nom>/`, des badges sans copie du code), et `demenage` refusait de la
# porter plus loin. Elle naît désormais dans la forme d'aujourd'hui. Le code :
# `--code SRC` le clone chez le premier agent ; sans lui, un dépôt neuf. Les autres
# reçoivent une copie git (`worktree`) du même dépôt.

GITIGNORE_EQUIPE = (
    "# un dossier par agent : chaque copie du code a son propre dépôt\n"
    "agents/*/code*/\n"
    ".env\n.env.*\n"
    "operations.md\n"
    "# accès des connexions (MCP) : jamais sur GitHub\n"
    ".mcp.json\n")

AGENTS_PROJET = """# {PROJET}

<!-- Étage 3 sur 4 : ce qui vaut pour tous les agents de ce projet, et rien que
     ce que les consignes communes ne disent pas. Posé « À REMPLIR » par le
     harnais ; seul le CTO le modifie. -->

À REMPLIR — une phrase sur le produit, et pour qui.

## Règles

À REMPLIR — ce qui vaut pour tout agent de ce projet : branches, Production,
contrôles avant d'envoyer. Une règle par ligne, et ce qu'elle protège.
"""

CARNET_LISEZMOI = """# Le carnet d'équipe

Chaque agent travaille sur SA copie du code : ce qu'il change chez un autre ne
se voit pas tant qu'il ne le dit pas. Pour le dire, sous une tâche que tu coches
dans ton `todo.md`, une ligne :

    ↗ <agent> : <ce que tu as changé chez lui, et où>

Le harnais la range ici et la sert au briefing de l'agent visé jusqu'à ce qu'il
l'acquitte. Le reste de ce dossier : ce que plusieurs agents lisent et écrivent ;
le daté va dans `docs/`, les livrables dans `assets/`.
"""

DECISIONS = "# Décisions\n\nLe pourquoi de chaque choix, daté. Une entrée par décision.\n"


def _git_ok(cwd, *a):
    try:
        o = subprocess.run(["git", "-c", "commit.gpgsign=false"] + list(a), cwd=cwd,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        return False, str(e)
    return o.returncode == 0, o.stderr.decode("utf-8", "replace").strip()


def _regles(projet):
    """Les règles d'une équipe neuve. Avec un agent de type OPS, la Production est
    fermée d'office : c'est l'organisation voulue par le commanditaire le
    14/10/2026 (`main` sur sa seule demande, OPS seul à pousser, laissez-passer).
    L'en-tête est celui que lit le garde de la Production (portage à part)."""
    import adopte
    ops = [n for n, m in _TYPES.items() if m == "ops"]
    if not ops:
        return adopte.rules_md(projet)
    return ("---\nproduction: main, master, production\nproduction-agent: %s\n"
            "production-duree: 15\n---\n\n" % ops[0]) + adopte.rules_md(projet)


def naissance(x, noms, code, appliquer):
    """Monte une équipe NEUVE dans `x`. Rend le code de sortie."""
    import adopte
    import agent
    import copilot
    j = os.path.join
    if not noms:
        _p("harnais adopte --equipe : au moins un nom d'agent")
        return 2
    # 1. Le dossier doit être neuf : y naître par-dessus un code ou une mémoire,
    #    c'est mêler deux dépôts sans que rien ne le dise.
    if os.path.isdir(x):
        presents = [e for e in os.listdir(x) if e not in (".git", ".DS_Store")]
        suivis = subprocess.run(["git", "ls-files"], cwd=x, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE).stdout.strip() if os.path.isdir(j(x, ".git")) else b""
        if presents or suivis:
            _p("REFUS — une équipe naît dans un dossier VIDE : ce dossier porte déjà %s.\n"
               "  Son code ? Monter l'équipe dans un dossier neuf, avec `--code %s`.\n"
               "  Un projet seul qui passe à plusieurs : `harnais equipe --agents …`."
               % (", ".join(sorted(presents)[:5]) or "un dépôt git suivi", x))
            return 1
    # Deux noms qui donnent le même profil dans le menu d'agent : le menu n'en
    # montrerait qu'un (COPILOT : la collision qui compte est celle du profil).
    c = profils_en_collision(noms)
    if c is not None:
        _p("REFUS — %s : le menu d'agent n'en montrerait qu'un." % c)
        return 1
    if any(n in (".", "..") or any(ch in n for ch in "/\\:") or not agent.nom_de_profil(n) for n in noms):
        _p("REFUS — chaque nom d'agent doit être un nom de dossier simple.")
        return 1
    projet = nom(x)
    import datetime
    jour = datetime.date.today().isoformat()
    poses = [(j(x, ".gitignore"), GITIGNORE_EQUIPE),
             (j(x, "fact", "base.md"), adopte.base_md(projet)),
             (j(x, "fact", "stack.md"), adopte.stack_md(projet)),
             (j(x, "fact", "architecture.md"), adopte.architecture_md(projet)),
             (j(x, "fact", "rules.md"), _regles(projet)),
             (j(x, "fact", "workflow.md"), adopte.workflow_md(projet)),
             (j(x, "fact", "roles.md"), adopte.roles_md(noms)),
             (j(x, "docs", "decisions.md"), DECISIONS),
             (j(x, "shared", "LISEZMOI.md"), CARNET_LISEZMOI),
             (j(x, "assets", "LISEZMOI.md"), "# Livrables\n\nLogos, maquettes, exports : un seul "
                                             "exemplaire, ici.\n")]
    if not _TYPES:
        poses.append((j(x, "AGENTS.md"), AGENTS_PROJET.replace("{PROJET}", projet)))
    _p("\n  NAISSANCE D'UNE ÉQUIPE — un dossier par agent   %s" % x)
    dossiers = set(os.path.relpath(f, x).split(os.sep)[0] for f, _ in poses) | {"shared"}
    _p("  → dépôt de la mémoire : %s" % ", ".join(sorted(dossiers)))
    _p("  → code : %s" % (("clone de %s chez %s" % (code, noms[0])) if code else
                          "dépôt neuf chez %s" % noms[0]) +
       (", copie git chez %s" % ", ".join(noms[1:]) if noms[1:] else ""))
    if appliquer:
        _mkdirs(x)
        ok, err = _git_ok(x, "init", "-q", "-b", "main")
        if not ok:
            _p("  ✗ git init de la mémoire : %s" % err)
            return 1
        for f, texte in poses:
            if not os.path.exists(f):
                _mkdirs(os.path.dirname(f))
                _ecrit_ou_rien(f, texte)
    # 2. Les agents : la commande qui en ajoute un, appelée une fois pour tous.
    rc = equipe_v3(x, noms, [], appliquer, naissance=True)
    if not appliquer:
        return rc
    # 3. Le code, une fois les dossiers posés.
    principal = j(x, "agents", noms[0], "code")
    if code:
        ok, err = _git_ok(x, "clone", "-q", code, principal)
    else:
        _mkdirs(principal)
        ok, err = _git_ok(principal, "init", "-q", "-b", "main")
        if ok:
            ok, err = _git_ok(principal, "-c", "user.name=harnais", "-c", "user.email=harnais@atelier",
                              "commit", "-q", "--allow-empty", "-m", "Départ de l'équipe")
    if not ok:
        _p("  ✗ code de %s non posé : %s" % (noms[0], err[:200]))
        return 1
    for n in noms[1:]:
        ok, err = _git_ok(principal, "worktree", "add", "-q", "-b", _branche(n), j(x, "agents", n, "code"))
        if not ok:
            _p("  ✗ copie du code de %s non posée : %s" % (n, err[:200]))
            return 1
    _p("  ✓ code posé : %s" % ", ".join("agents/%s/code" % n for n in noms))
    # Le carnet d'équipe, dans `shared/` : la règle qui le place est dans `carnet`.
    import carnet
    e = carnet.amorce(j(x, "agents", noms[0]))
    _p("  %s carnet d'équipe : %s" % (("✓", rel(x, e)) if e else ("✗", "non amorcé")))
    # La méthode du projet, comme `adopte` la pose partout (jamais écrasée).
    inf = j(x, ".github", "copilot-instructions.md")
    try:
        texte = adopte.instructions(inf, x)
    except copilot.Refus as e_:
        texte = None
        _p("  ✗ méthode du projet : %s" % e_)
    if texte is not None:
        _mkdirs(os.path.dirname(inf))
        _ecrit_ou_rien(inf, texte)
    _p("\n  ENSUITE : remplir le cap (`fact/base.md`), le rôle de chaque agent, puis enregistrer "
       "la mémoire (`git add -A && git commit`). Chaque agent démarre DANS `agents/<nom>/`.")
    return rc


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


AIDE = ("harnais equipe --agents A,B[,C] [--modeles ops,po,qa,nxt] [--project-root P] [--apply]\n"
        "harnais equipe --retire A [--project-root P] [--apply]\n"
        "harnais equipe --profils [--project-root P] [--apply]\n"
        "harnais equipe --compact [--agents A,B] [--project-root P] [--apply]\n\n"
        "Passe un projet mono en équipe (le PREMIER nommé hérite de l'état existant),\n"
        "ou ajoute des agents à un projet déjà en équipe. Chaque agent reçoit son profil\n"
        "`.github/agents/<nom>.agent.md`, qui le fait apparaître dans le menu d'agent de l'app.\n"
        "`--profils` met à niveau un projet déjà en équipe : profils manquants, périmètres\n"
        "en chemins relatifs. `--compact` exporte une équipe existante vers les profils-rôles\n"
        "et périmètres centralisés, ou crée les agents demandés sous cette forme.\n"
        "Sur une équipe « un dossier par agent » (la mémoire à la racine, `agents/<nom>/code`),\n"
        "`--agents` ajoute un agent avec SA copie du code, `--retire` en retire un (refusé s'il\n"
        "reste du travail non enregistré).\n"
        "--modeles : un rôle type par agent (OPS seul en Production, PO produit, QA contrôle\n"
        "et guichet unique des questions, NXT versions à venir) ; sur une équipe neuve,\n"
        "l'AGENTS.md du projet reçoit aussi les règles communes s'il n'existe pas.\n"
        "Les anciens dossiers et livrables ne sont jamais supprimés. À blanc par défaut.")


def main(args):
    import agent
    import carnet
    import compact as compact_mod
    import copilot
    import memoire
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
    if liste is None and valeur(args, "--retire") is not None:
        liste = ""
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
    types = [t.strip().lower() for t in (valeur(args, "--modeles") or "").split(",") if t.strip()]
    if types:
        inconnus = [t for t in types if t not in MODELES]
        if inconnus or len(types) != len(noms):
            _e("harnais equipe : --modeles prend un modèle par agent, dans l'ordre de --agents, "
               "parmi %s%s" % (", ".join(MODELES), (" — inconnu : " + ", ".join(inconnus)) if inconnus else ""))
            return 2
    _TYPES.clear()
    _TYPES.update(zip(noms, types))
    if memoire.resous(p).forme == memoire.Forme.Equipe:
        retirer = [r.strip() for r in (valeur(args, "--retire") or "").split(",") if r.strip()]
        return equipe_v3(memoire.resous(p).projet, noms, retirer, appliquer)
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
                _ecrit_ou_rien(j(cible, "AGENTS.md"), role(premier, nom(p)))
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
                _ecrit_ou_rien(j(d, "AGENTS.md"), role(n, nom(p)))
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
    if _TYPES:
        reste.append("RÈGLES COMMUNES D'ÉQUIPE (autonomie git, guichet %s, Production à %s) : le CTO "
                     "reporte le gabarit `skills/agentic-agents/templates/equipe-AGENTS.md` dans "
                     "l'AGENTS.md du projet" % (_qui("qa", "QA"), _qui("ops", "OPS")))
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
