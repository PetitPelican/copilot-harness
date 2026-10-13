# -*- coding: utf-8 -*-
"""PASSER UN PROJET EN ÉQUIPE — ou lui ajouter un agent.

Port de `harnais/src/equipe.rs` (Rust, 0.12.8) ; le Rust gagne. (Le Rust avait
été porté de `agentic-agents.py` le 11/09/2026 : le script n'existait qu'en
Python, donc échouait en silence sur un Windows sans interpréteur. Il rend à
l'octet ce qu'il rendait sur les projets fabriqués de `controles/equipe.sh`.)

UNE SEULE COMMANDE, DEUX COMPORTEMENTS, ET C'EST LA FORME DU PROJET QUI
DÉCIDE. Sur un projet mono elle convertit et crée les premiers agents ; sur
un projet déjà multi elle en ajoute un.

    en `brain/`      brain/mind/{state,todo}.md -> brain/mind/<premier>/
                     brain/fact/roles.md, carnet dans brain/workspace/
    à l'ancienne     .mind/                     -> agents/<premier>/.mind/
                     .fact/roles.md, carnet dans equipe/
    dans les deux    .claude/settings.json      -> agents/<premier>/.claude/
                     ~/.claude/projects/<slug>/ -> slug du dossier d'agent
                     agents/<autres>/           -> CLAUDE.md de rôle + réglages

CE QU'ELLE NE FAIT PAS : découper le `CLAUDE.md` (éditorial), supprimer
l'ancienne mémoire auto (elle la marque `.migre-<date>`), toucher aux faits,
aux traces ni au code.

LE PIÈGE QU'ELLE EXISTE POUR ÉVITER. La mémoire auto d'un agent est classée
par CHEMIN. Convertir déplace le dossier de travail de `<projet>/` vers
`<projet>/agents/<nom>/` : sans migration, l'agent repart sur une adresse
neuve et vide, et `--resume` ne retrouve plus rien.

**À blanc par défaut.** `--apply` (ou `--go`) pour écrire.

DIVERGENCE CONNUE avec le Rust : le gabarit des rôles ne voyage plus DANS le
programme (`include_str!`) ; il se lit à l'appel dans
`skills/agentic-agents/templates/roles.md` du paquet, à côté de `py/`.
"""
import os
import sys

CATALOGUE = "atelier"
PAQUET = "harnais"
DEPOT = "PetitPelican/claude-harnais"
ROLE = """# {} — rôle

> Le `CLAUDE.md` du projet est **hérité** : il est chargé en même temps que
> celui-ci, à chaque démarrage. N'y recopier AUCUNE de ses phrases. Le test :
> si une phrase resterait vraie pour un autre agent du projet, elle est à
> l'étage au-dessus.

## Ce que cet agent tient

[LE_PÉRIMÈTRE — en dossiers, pas en intentions. « orienté produit » n'empêche
personne de toucher au backend ; la frontière qui tient est celle écrite en
`deny` dans `.claude/settings.json`, à côté.]

## Ce qu'il ne touche pas

[LES_AUTRES_LOTS — et qui les tient.]
"""


def _gabarit_roles():
    ici = os.path.dirname(os.path.abspath(__file__))
    chemin = os.path.join(os.path.dirname(ici), "skills", "agentic-agents", "templates", "roles.md")
    with open(chemin, encoding="utf-8", newline="") as f:
        return f.read()


def role(nom):
    return ROLE.replace("{}", nom, 1)


def _p(s=""):
    sys.stdout.write(s + "\n")


def _panique(msg):
    """Là où le Rust panique (code 101), le Python sort en 101 de même."""
    sys.stdout.flush()
    sys.stderr.write("thread 'main' panicked: %s\n" % msg)
    sys.exit(101)


def maison():
    h = os.environ.get("HOME")
    if h is None:
        h = os.environ.get("USERPROFILE")
    return h if h is not None else ""


def slug(p):
    """Mesuré le 04/09/2026 contre `~/.claude/projects/` : tout ce qui n'est pas
    alphanumérique devient un tiret, et une suite de tels caractères UN SEUL."""
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
        r = subprocess.run(["git", "-C", p] + list(a), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return False
    return r.returncode == 0


# ── chemins : la sémantique de `std::path` ──────────────────────────────────

def _composants(p):
    return p.startswith("/"), [c for c in p.split("/") if c not in ("", ".")]


def strip_prefix(p, base):
    """`Path::strip_prefix` : le reste (en `/`), ou None. Comparaison par COMPOSANTS."""
    rp, cp = _composants(p)
    rb, cb = _composants(base)
    if rp != rb or cp[:len(cb)] != cb:
        return None
    return "/".join(cp[len(cb):])


def file_name(p):
    _, c = _composants(p)
    if not c or c[-1] == "..":
        return None
    return c[-1]


def extension(nom):
    """`Path::extension` d'un nom de fichier."""
    i = nom.rfind(".")
    if i <= 0 or nom == "..":
        return None
    return nom[i + 1:]


def canonicalize(p):
    if not os.path.exists(p):
        return None
    try:
        return os.path.realpath(p)
    except OSError:
        return None


def rel(racine, p):
    r = strip_prefix(p, racine)
    if r is not None:
        return r
    # `components()` d'un chemin absolu porte aussi la racine `/` : elle se joint
    # comme un composant (d'où `//a/b`), exactement ce que fait le Rust.
    rp, cp = _composants(p)
    return "/".join((["/"] if rp else []) + cp)


class Disposition(object):
    """OÙ VIVENT LES FAITS ET LES ESPRITS — la seule chose qui change entre les
    deux organisations. En `brain/`, l'esprit d'un agent vit dans le CERVEAU,
    rangé par nom : `agents/<nom>/` ne porte plus que le rôle et les réglages."""

    def __init__(self, racine, cerveau, faits):
        self.racine = racine
        self.cerveau = cerveau
        self.faits = faits

    def esprit(self, nom):
        if self.cerveau:
            return os.path.join(self.racine, "brain/mind", nom)
        return os.path.join(self.racine, "agents", nom, ".mind")

    def esprit_mono(self):
        return os.path.join(self.racine, "brain/mind" if self.cerveau else ".mind")

    def etiquette_faits(self):
        return "brain/fact" if self.cerveau else ".fact"

    def rel(self, p):
        return rel(self.racine, p)


def trie(d):
    try:
        return [os.path.join(d, n) for n in sorted(os.listdir(d))]
    except OSError:
        return []


def nom(p):
    n = file_name(p)
    return n if n is not None else ""


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


def json_indent2(v):
    """Le JSON tel que `json.dumps(indent=2, ensure_ascii=False)` l'écrit."""
    import json
    return json.dumps(v, indent=2, ensure_ascii=False)


def _lit_objet(chemin):
    import json
    try:
        with open(chemin, encoding="utf-8", newline="") as h:
            v = json.loads(h.read(), parse_constant=_refuse_constante)
    except (OSError, ValueError, RecursionError):
        return {}
    return v if isinstance(v, dict) else {}


def _refuse_constante(c):
    raise ValueError(c)


def reglages_agent(sources, cible, projet, autres, appliquer, rap):
    """Les réglages d'un agent, SOUS LE PAQUET. Les hooks viennent du paquet : on
    RETIRE les déclarations à la main — deux jeux de hooks sur le même
    événement, ce sont deux briefings et personne ne voit lequel a parlé. Il ne
    reste que QUEL PAQUET, et CE QUE CET AGENT N'A PAS LE DROIT DE TOUCHER — en
    `deny` ANCRÉ SUR LE HOME : un motif relatif ne mord pas (mesuré le 04/09)."""
    src = next((s for s in sources if os.path.isfile(s)), None)
    d = _lit_objet(src) if src is not None else {}
    retirees = 0
    if "hooks" in d:
        h = d.pop("hooks")
        if isinstance(h, dict):
            for bl in h.values():
                if isinstance(bl, list):
                    for b in bl:
                        x = b.get("hooks") if isinstance(b, dict) else None
                        retirees += len(x) if isinstance(x, list) else 0

    mk = d.setdefault("extraKnownMarketplaces", {})
    if isinstance(mk, dict):
        mk[CATALOGUE] = {"source": {"source": "github", "repo": DEPOT}}
    ep = d.setdefault("enabledPlugins", {})
    if isinstance(ep, dict):
        ep["%s@%s" % (PAQUET, CATALOGUE)] = True

    perm = d.setdefault("permissions", {})
    if isinstance(perm, dict):
        ancien = perm.get("deny")
        deny = list(ancien) if isinstance(ancien, list) else []
        deny = [x for x in deny if not (isinstance(x, str) and "/agents/" in x)]
        # Ancré sur le home QUAND le projet y est : un `~/` collé devant un
        # chemin absolu ne matche rien, et ne dit pas qu'il ne matche rien.
        h = maison()
        r = strip_prefix(projet, h) if h else None
        ancre = "~/" + r if r is not None else projet
        for a in autres:
            deny.append("Edit(%s/agents/%s/**)" % (ancre, a))
        perm["deny"] = deny
    rap.append(("+", "%s — paquet %s@%s déclaré, %d deny de périmètre%s" % (
        rel(projet, cible), PAQUET, CATALOGUE, len(autres),
        (", %d hooks à la main retirés" % retirees) if retirees > 0 else "")))
    if appliquer:
        try:
            os.makedirs(os.path.dirname(cible), exist_ok=True)
        except OSError:
            pass
        try:
            with open(cible, "w", encoding="utf-8", newline="") as f:
                f.write(json_indent2(d) + "\n")
        except OSError:
            pass


def porte_les_non_herites(projet, cible, appliquer, rap):
    """`.mcp.json` et `settings.local.json` ne remontent PAS depuis un dossier
    d'agent — mesuré le 04/09 : un agent démarré dans `agents/<nom>/` ne voyait
    aucun serveur MCP du projet. On copie, on ne déplace pas."""
    for r in (".mcp.json", ".claude/settings.local.json"):
        src = os.path.join(projet, r)
        if not os.path.isfile(src):
            continue
        rap.append(("+", "%s/%s — copié depuis la racine (ne s'hérite pas)" % (rel(projet, cible), r)))
        if appliquer:
            import shutil
            dst = os.path.join(cible, r)
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
            except OSError:
                pass
            try:
                shutil.copy(src, dst)
            except (OSError, shutil.Error):
                pass


def copie_arbre(src, dst):
    """Lève OSError au premier échec, comme le `?` du Rust."""
    import shutil
    os.makedirs(dst, exist_ok=True)
    with os.scandir(src) as it:
        entrees = list(it)
    for e in entrees:
        s, d = e.path, os.path.join(dst, e.name)
        if e.is_dir(follow_symlinks=False):
            copie_arbre(s, d)
        else:
            shutil.copy(s, d)


def migre_memoire_auto(ancien, neuf, appliquer, rap):
    # DANS UN DÉPÔT, L'ADRESSE NE CHANGE PAS : Claude Code range la mémoire à
    # la racine du dépôt, et `agents/<nom>/` reste dans le même. Déplacer ici,
    # c'est ce qui a coupé Splide en deux le 04/09/2026 — la mémoire partie
    # chez un agent que Claude Code ne lit jamais là, un carnet neuf recommencé
    # à la racine (`socle::dossier_de_la_memoire`).
    import memoire
    if memoire.racine_depot(ancien) is not None:
        rap.append(("·", "mémoire auto : même dépôt, même adresse — rien à migrer"))
        return
    base = os.path.join(maison(), ".claude/projects")
    src = os.path.join(base, slug(ancien))
    dst = os.path.join(base, slug(neuf))
    if not os.path.isdir(src):
        rap.append(("·", "aucune mémoire auto à migrer (%s absent)" % nom(src)))
        return
    if os.path.exists(dst):
        rap.append(("⚠", "%s existe déjà — mémoire auto NON migrée, à fusionner" % nom(dst)))
        return
    n = len([p for p in trie(src) if os.path.isfile(p) and extension(nom(p)) == "jsonl"])
    m = len([p for p in trie(os.path.join(src, "memory")) if extension(nom(p)) == "md"])
    import datetime
    jour = datetime.datetime.now().strftime("%Y%m%d")
    rap.append(("→", "mémoire auto : %s -> %s (%d fils, %d mémoires) ; l'ancien sera marqué .migre-%s" % (
        nom(src), nom(dst), n, m, jour)))
    if appliquer:
        try:
            copie_arbre(src, dst)
        except OSError:
            return
        try:
            os.rename(src, os.path.join(os.path.dirname(src), "%s.migre-%s" % (nom(src), jour)))
        except OSError:
            pass


def valeur(args, cle):
    it = iter(args)
    for a in it:
        if a == cle:
            return next(it, None)
        if a.startswith(cle + "="):
            return a[len(cle) + 1:]
    return None


def _ecrit(chemin, texte):
    try:
        with open(chemin, "w", encoding="utf-8", newline="") as f:
            f.write(texte)
    except OSError:
        pass


def _mkdirs(d):
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass


def main(args):
    if any(a == "-h" or a == "--help" for a in args):
        _p("harnais equipe --agents A,B[,C] [--project-root P] [--apply]\n\n"
           "Passe un projet mono en équipe (le PREMIER nommé hérite de l'état existant),\n"
           "ou ajoute des agents à un projet déjà en équipe. À blanc par défaut.")
        return 0
    liste = valeur(args, "--agents")
    if liste is None:
        sys.stderr.write("harnais equipe : --agents est requis (noms séparés par des virgules ; "
                         "le PREMIER hérite de l'état existant)\n")
        return 2
    appliquer = any(a == "--apply" or a == "--go" for a in args)
    p0 = valeur(args, "--project-root")
    if p0 is None:
        p0 = "."
    c = canonicalize(p0)
    p = c if c is not None else p0
    noms = [x.strip() for x in liste.split(",") if x.strip()]
    rap = []     # [(signe, ligne)]
    reste = []

    j = os.path.join
    f, existants, disp = forme(p)
    if f == "ancienne":
        _p("Ce projet n'a de faits ni dans `brain/fact/` ni dans `.fact/`. "
           "Lancer d'abord la migration de mémoire, puis revenir.")
        return 1
    # Deux agents dont les noms se slugifient pareil partageraient une seule
    # mémoire auto, en silence. Irrattrapable une fois installé.
    vus = []     # [(slug, [noms])], dans l'ordre d'apparition
    for n in list(noms) + list(existants):
        s = slug(n)
        for k, v in vus:
            if k == s:
                v.append(n)
                break
        else:
            vus.append((s, [n]))
    collisions = [", ".join(v) for _, v in vus if len(v) > 1]
    if collisions:
        _p("REFUS — ces noms donnent la même adresse de mémoire auto : %s. "
           "Ils partageraient une seule mémoire sans que rien ne le dise." % " / ".join(collisions))
        return 1
    hook = j(p, ".claude/hooks/briefing.py")
    if os.path.isfile(hook):
        try:
            with open(hook, "rb") as h:
                contenu = h.read().decode("utf-8", "replace")
        except OSError:
            contenu = ""
        if "racines(" not in contenu:
            _p("REFUS — les hooks de ce projet sont d'avant le 04/09/2026 : le briefing ne fait "
               "qu'une remontée et ne verrait jamais les faits depuis un dossier d'agent. Retirer ces hooks locaux et déclarer "
               "le paquet d'abord : `harnais adopte --go`.")
            return 1

    if f == "mono":
        if not noms:
            _panique("index out of bounds: the len is 0 but the index is 0")
        premier = noms[0]
        cible = j(p, "agents", premier)
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
        reglages_agent([j(p, ".claude/settings.json")], j(cible, ".claude/settings.json"),
                       p, noms[1:], appliquer, rap)
        if os.path.isfile(j(p, ".claude/settings.json")):
            rap.append(("−", ".claude/settings.json de la racine SUPPRIMÉ — il ne s'exécute plus "
                             "(les réglages ne s'héritent pas) et quelqu'un l'éditerait un jour en croyant agir sur tous"))
            if appliquer and not git(p, ["rm", "-q", ".claude/settings.json"]):
                try:
                    os.remove(j(p, ".claude/settings.json"))
                except OSError:
                    pass
        porte_les_non_herites(p, cible, appliquer, rap)
        migre_memoire_auto(p, cible, appliquer, rap)
        # Le premier agent hérite de l'état, pas d'un rôle : il lui faut le sien.
        rap.append(("+", "agents/%s/CLAUDE.md — rôle à remplir" % premier))
        if appliquer and not os.path.exists(j(cible, "CLAUDE.md")):
            _ecrit(j(cible, "CLAUDE.md"), role(premier))
        neufs = noms[1:]
        tous = list(noms)
        modeles = [j(p, ".claude/settings.agent.json.example"),
                   j(cible, ".claude/settings.json"), j(p, ".claude/settings.json")]
    else:
        neufs = list(noms)
        tous = list(existants) + list(noms)
        modeles = [j(p, ".claude/settings.agent.json.example")] + [
            j(p, "agents", e, ".claude/settings.json") for e in existants]

    import datetime
    jour = datetime.datetime.now().strftime("%Y-%m-%d")
    for n in neufs:
        d = j(p, "agents", n)
        esprit = disp.esprit(n)
        rap.append(("+", "agents/%s/ — CLAUDE.md de rôle, settings.json ; esprit neuf dans %s" % (n, disp.rel(esprit))))
        if appliquer:
            _mkdirs(esprit)
            _mkdirs(d)
            _ecrit(j(d, "CLAUDE.md"), role(n))
            _ecrit(j(esprit, "state.md"),
                   "---\nmaj: %s\nsante: vert\njalon: [LE_PROCHAIN_CAILLOU de ce lot]\n---\n\n# État — %s\n\n[où en est CET agent]\n" % (jour, n))
            _ecrit(j(esprit, "todo.md"), "# À faire — %s\n\n- [ ] [première tâche de ce lot]\n" % n)
        autres = [x for x in tous if x != n]
        reglages_agent(modeles, j(d, ".claude/settings.json"), p, autres, appliquer, rap)
        porte_les_non_herites(p, d, appliquer, rap)

    # LE CARNET D'ÉQUIPE — LU partout, CRÉÉ nulle part jusqu'au 10/09. On
    # appelle la règle qui le place, on ne la recopie pas.
    if appliquer:
        import carnet
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
            # sert les deux organisations. Écrit `.fact/` jusqu'au 11/09/2026,
            # y compris dans un projet en `brain/` — le Python le posait ainsi.
            texte = _gabarit_roles().replace("[PROJECT_NAME]", nom(p)).replace("[FAITS]", disp.etiquette_faits())
            for i, n in enumerate(tous):
                texte = texte.replace("`<agent-%d>`" % (i + 1), "`%s`" % n)
            _ecrit(fichier_roles, texte)
        reste.append("REMPLIR %s/roles.md — qui tient quoi, et surtout LES ZONES PARTAGÉES. Un "
                     "périmètre propre se lit dans les deny ; une zone partagée ne se lit nulle part, et c'est là que les "
                     "collisions arrivent. Ce sont des FAITS : ça s'écrit à la demande du commanditaire (` # fact-ok` au commit)."
                     % disp.etiquette_faits())
    reste.append("DÉCOUPER LE CLAUDE.md — la seule étape qui ne s'automatise pas. Le commun reste à la "
                 "racine, le rôle descend dans agents/<nom>/CLAUDE.md. Contrôle de sortie : aucune phrase du bas ne "
                 "resterait vraie pour un autre agent.")
    reste.append("ÉCRIRE LES PÉRIMÈTRES en dossiers dans chaque settings.json : les deny posés ne couvrent "
                 "que les dossiers d'agents. Le code, lui, n'est pas partagé au hasard — dire qui tient quoi.")
    reste.append("RELANCER LES SESSIONS tmux DANS les dossiers d'agents, sous des noms slugifiés "
                 "(%s). L'ancienne session à la racine n'a plus d'agent : le briefing l'avertira au lieu de se taire."
                 % ", ".join(slug(n).lower().strip("-") for n in tous))

    _p("── agents — %s (%s)%s" % (nom(p), f, "" if appliquer else "  [DRY-RUN]"))
    for signe, ligne in rap:
        _p("  %s %s" % (signe, ligne))
    _p("\n── À reprendre à la main")
    for r in reste:
        _p("  · %s" % r)
    if not appliquer:
        _p("\nDry-run. Relancer avec --apply pour écrire.")
    return 0
