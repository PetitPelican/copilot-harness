# -*- coding: utf-8 -*-
"""UN PROJET LOGÉ DANS UN DÉPÔT DE CODE — `harnais adopte --projet <dossier>`.

Le besoin (2.2.0). Un même dépôt de code héberge plusieurs projets, chacun dans
son dossier. Chaque projet doit avoir SA mémoire, à côté de son code, partagée
entre les personnes qui y travaillent par push et pull, sans dépôt de plus. Une
mémoire à la racine du dépôt mêlerait les projets.

LA CONTRAINTE DE L'APP. Les profils (`.github/agents/`), les réglages
(`.github/copilot/`) et la méthode ne sont lus qu'à la RACINE git. La session
s'ouvre donc à la racine, et c'est l'agent choisi dans le menu qui désigne le
projet :

    .github/agents/<court>-<rôle>.agent.md        profil ET rôle, marqué du dossier
    .github/copilot/perimetres/<court>-<rôle>.json   son périmètre
    <dossier>/brain/fact/                          les faits du projet
    <dossier>/brain/mind/<rôle>/                   l'état de chaque agent
    <dossier>/assets/<rôle>/                       ses livrables
    <dossier>/docs/decisions.md                    le daté
    <dossier>/.logs/                               le journal des commits

Le résolveur (`memoire.porteur_loge`) trouve la mémoire du projet en remontant
depuis l'esprit de l'agent ; le profil porte la marque `agent.MARQUE_PROJET`.

LE PAQUET NE SE DÉCLARE PAS DANS LE DÉPÔT PARTAGÉ : la déclaration du projet
(`.github/copilot/settings.json`) porte le chemin du paquet sur CE poste, faux
sur celui d'à côté. On s'appuie sur l'inscription utilisateur que pose
`install.ps1`, et on le dit.

MIGRATION (`--depuis-racine`) : une mémoire `brain/` commitée à la racine
descend dans le dossier du projet, avec les livrables des rôles nommés ; les
profils et périmètres de la racine prennent le nom du projet et sa marque.
Rien n'est supprimé ; un déplacement suivi par git passe par `git mv`.

À blanc par défaut, `--go` pour écrire. Jamais d'écrasement.
"""
import os
import sys

V = "\x1b[32m"
J = "\x1b[33m"
B = "\x1b[1m"
D = "\x1b[2m"
X = "\x1b[0m"

UNION = ".logs/*.md merge=union"
IGNORE = "brain/workspace/"


def _p(s=""):
    sys.stdout.write(s + "\n")


def _e(s=""):
    sys.stderr.write(s + "\n")


def _valeur(args, cle):
    if cle in args:
        i = args.index(cle)
        if i + 1 < len(args):
            return args[i + 1]
    return None


def nom_profil(court, role):
    """`<court>-<rôle>` en minuscules, réduit aux caractères sûrs."""
    import equipe
    return equipe.slug("%s-%s" % (court, role)).lower().strip("-")


def dossier_relatif(racine, dossier):
    """Le dossier du projet relatif à la racine, écrit avec `/` — ou None s'il est
    la racine elle-même, hors du dépôt, ou introuvable."""
    import equipe
    a = dossier if os.path.isabs(dossier) else os.path.join(racine, dossier)
    a = equipe.canonicalize(a)
    if a is None or not os.path.isdir(a):
        return None
    r = equipe.strip_prefix(a, racine)
    if not r:
        return None
    return "/".join(r)


def corps_profil(rel, role, nom_projet):
    import adopte
    import agent
    return ("Lis %(r)s/brain/mind/%(a)s/state.md et %(r)s/brain/mind/%(a)s/todo.md à la reprise.\n"
            "Ton projet est le dossier `%(r)s` : ta mémoire est dans `%(r)s/brain/`, tes livrables "
            "dans `%(r)s/assets/%(a)s/`. Le reste du dépôt appartient à d'autres projets.\n\n"
            "%(m)s\n\n"
            "<!-- harnais:role:start -->\n%(role)s<!-- harnais:role:end -->\n"
            % {"r": rel, "a": role, "m": agent.marque_projet(rel, role),
               "role": adopte.agents_md_agent(role, nom_projet)})


def perimetre(rel, role, roles):
    """Le périmètre d'un agent de projet logé : il n'écrit QUE dans son dossier de
    projet (liste `allow`), jamais dans la mémoire ni les livrables d'un pair, ni
    dans les fichiers qui font tenir le harnais. QA garde sa liste restreinte."""
    import agent
    import equipe
    deny = list(agent.CONTROLE)
    deny.append("%s/brain/poids.json" % rel)
    if not equipe.est_qa(role):
        deny.append("%s/brain/fact" % rel)
    for n in roles:
        if n != role:
            deny.append("%s/brain/mind/%s" % (rel, n))
            deny.append("%s/%s" % (rel, agent.banc(n)))
    allow = equipe.allow_par_defaut(role, "%s/brain/fact" % rel, "%s/brain/mind/%s" % (rel, role),
                                    "%s/%s" % (rel, agent.banc(role)))
    if allow is None:
        allow = [rel]
    return {"deny": deny, "allow": allow}


def _suivi(racine, p):
    import equipe
    return equipe.git(racine, ["ls-files", "--error-unmatch", "--", p])


def _ajoute_ligne(texte, ligne):
    """Le texte avec `ligne` en plus, ou None si elle y est déjà."""
    if ligne in [x.strip() for x in texte.splitlines()]:
        return None
    if texte and not texte.endswith("\n"):
        texte += "\n"
    return texte + ligne + "\n"


def _reecrit_chemin(x, rel):
    """Un chemin d'un périmètre de racine, descendu dans le dossier du projet."""
    import agent
    for pre in ("brain", agent.BANC):
        if x == pre or x.startswith(pre + "/"):
            return "%s/%s" % (rel, x)
    return x


def main(args):
    import adopte
    import agent
    import copilot
    import equipe
    import memoire
    import vue
    go = "--go" in args or "--apply" in args
    dossier = _valeur(args, "--projet")
    roles = [x.strip() for x in (_valeur(args, "--equipe") or "").split(",") if x.strip()]
    migre = "--depuis-racine" in args
    if not dossier or not roles:
        _e("adopte --projet DOSSIER --equipe A,B,C [--nom COURT] [--depuis-racine] [--go]")
        return 2
    if any(a in (".", "..") or any(c in a for c in "/\\:") for a in roles):
        _e("adopte : chaque nom d'agent doit être un nom de dossier simple.")
        return 1
    try:
        ici = os.getcwd()
    except OSError:
        ici = "."
    racine = memoire.arbre_courant(ici)
    if racine is None:
        _e("adopte --projet : pas de dépôt git ici — se placer dans le dépôt du code.")
        return 1
    racine = equipe.canonicalize(racine) or racine
    rel = dossier_relatif(racine, dossier)
    if rel is None:
        _e("adopte --projet : %s n'est pas un sous-dossier existant de %s." % (dossier, racine))
        return 1
    court = (_valeur(args, "--nom") or os.path.basename(rel)).strip()
    noms = [nom_profil(court, a) for a in roles]
    if any(not n for n in noms) or len(set(noms)) != len(noms):
        _e("adopte : nom de profil vide ou en collision : %s" % ", ".join(noms))
        return 1
    j = os.path.join
    P = j(racine, *rel.split("/"))
    brain = j(P, "brain")
    nom_projet = court

    _p("%sharnais adopte --projet%s — une mémoire de projet dans un dépôt de code\n" % (B, X))
    _p("  dépôt  : %s" % racine)
    _p("  projet : %s  (profils « %s-… »)\n" % (rel, court))

    # Les profils déjà pris par un AUTRE projet ne se réécrivent pas.
    deja_loges = agent.loges(racine)
    for n, a in zip(noms, roles):
        e = deja_loges.get(n)
        if e is not None and e != (rel, a):
            _e("adopte : le profil %s désigne déjà %s (esprit %s)." % (n, e[0], e[1]))
            return 1
        if e is None and os.path.exists(agent.profil(racine, n)):
            _e("adopte : %s existe et ne porte pas la marque de ce projet : le compléter à la main."
               % agent.profil(racine, n))
            return 1

    deplacements = []   # [(source, cible)]
    retouches = []      # [(chemin, nouveau texte, ancien chemin ou None)]
    if migre:
        racine_brain = j(racine, "brain")
        if not os.path.isdir(racine_brain):
            _e("adopte --depuis-racine : aucune mémoire `brain/` à la racine.")
            return 1
        if os.path.exists(brain):
            _e("adopte --depuis-racine : %s/brain existe déjà — rien ne s'écrase ; "
               "réunir les deux à la main." % rel)
            return 1
        deplacements.append((racine_brain, brain))
        for a in roles:
            src = j(racine, agent.BANC, a)
            if os.path.isdir(src):
                if os.path.exists(j(P, agent.BANC, a)):
                    _e("adopte --depuis-racine : %s/%s/%s existe déjà." % (rel, agent.BANC, a))
                    return 1
                deplacements.append((src, j(P, agent.BANC, a)))
        for n, a in zip(noms, roles):
            vieux = agent.profil(racine, a)
            if os.path.isfile(vieux) and not os.path.exists(agent.profil(racine, n)):
                t = equipe.lis(vieux)
                t = t.replace("name: %s\n" % agent.nom_de_profil(a), "name: %s\n" % n, 1)
                t = t.replace("brain/mind/%s/" % a, "%s/brain/mind/%s/" % (rel, a))
                t = t.replace("%s/%s" % (agent.BANC, a), "%s/%s/%s" % (rel, agent.BANC, a))
                if agent.MARQUE_PROJET not in t:
                    i = t.find(agent.MARQUE_ROLE)
                    m = agent.marque_projet(rel, a) + "\n\n"
                    t = t[:i] + m + t[i:] if i >= 0 else t.rstrip("\n") + "\n\n" + m
                retouches.append((agent.profil(racine, n), t, vieux))
            vg = agent.perimetre_compact(racine, a)
            if os.path.isfile(vg) and not os.path.exists(agent.perimetre_compact(racine, n)):
                try:
                    v = equipe.lis_json(equipe.lis(vg))
                except (ValueError, OSError, UnicodeDecodeError) as e:
                    _e("adopte : %s illisible : %s" % (vg, e))
                    return 1
                if not isinstance(v, dict):
                    _e("adopte : %s n'est pas un objet JSON." % vg)
                    return 1
                for cle in ("deny", "allow"):
                    if isinstance(v.get(cle), list):
                        v[cle] = [_reecrit_chemin(x, rel) if isinstance(x, str) else x for x in v[cle]]
                if "allow" not in v:
                    v["allow"] = [rel]
                retouches.append((agent.perimetre_compact(racine, n), equipe.json_compact(v) + "\n", vg))

    import datetime
    jour = datetime.datetime.now().strftime("%Y-%m-%d")

    def vient(p):
        """Un fichier qui arrivera par le déplacement : la racine l'a déjà."""
        for src, cible in deplacements:
            r = equipe.strip_prefix(p, cible)
            if r is not None and os.path.exists(j(src, *r)):
                return True
        return False

    poser = []   # [(chemin, contenu, quoi)]

    def pose(p, contenu, quoi):
        if os.path.exists(p) or vient(p):
            return
        poser.append((p, contenu, quoi))

    fact = j(brain, "fact")
    pose(j(fact, "base.md"), adopte.base_md(nom_projet), "le cap du projet")
    pose(j(fact, "workflow.md"), adopte.workflow_md(nom_projet), "comment procéder")
    pose(j(fact, "architecture.md"), adopte.architecture_md(nom_projet), "composants et frontières")
    pose(j(fact, "stack.md"), adopte.stack_md(nom_projet), "outils et commandes")
    pose(j(fact, "rules.md"), adopte.rules_md(nom_projet), "invariants du projet")
    pose(j(fact, "roles.md"), adopte.roles_md(roles), "qui tient quoi")
    for a in roles:
        pose(j(brain, "mind", a, "state.md"), adopte.state_md(jour), "l'état de %s" % a)
        pose(j(brain, "mind", a, "todo.md"), adopte.TODO_MD, "ce qui attend %s" % a)
    pose(j(P, "docs", "decisions.md"), equipe.DECISIONS, "le pourquoi de chaque choix, daté")
    deja_retouches = set(c for c, _, _ in retouches)
    for n, a in zip(noms, roles):
        pf = agent.profil(racine, n)
        if pf not in deja_retouches:
            c = ("---\nname: %s\ndescription: Agent %s du projet %s — rôle propre au projet\n%s---\n%s"
                 % (n, a, nom_projet, copilot.entete_modele(), corps_profil(rel, a, nom_projet)))
            pose(pf, c, "profil, rôle et marque de %s" % a)
        pg = agent.perimetre_compact(racine, n)
        if pg not in deja_retouches:
            pose(pg, equipe.json_compact(perimetre(rel, a, roles)) + "\n", "périmètre de %s" % a)

    ajouts = []   # [(chemin, texte complet, quoi)]
    for f, ligne, quoi in ((j(P, ".gitattributes"), UNION, "journaux fusionnés sans conflit"),
                           (j(P, ".gitignore"), IGNORE, "le carnet d'équipe reste local")):
        try:
            avant = equipe.lis(f)
        except FileNotFoundError:
            avant = ""
        except (OSError, UnicodeDecodeError) as e:
            _e("adopte : %s : %s" % (f, equipe.err_es(e)))
            return 1
        t = _ajoute_ligne(avant, ligne)
        if t is not None:
            ajouts.append((f, t, quoi))
    inf = j(racine, ".github", "copilot-instructions.md")
    try:
        texte = adopte.instructions(inf, racine)
    except copilot.Refus as e:
        _e("adopte : %s" % e)
        return 1
    if texte is not None:
        ajouts.append((inf, texte, "la méthode, après le contenu existant"))

    # ── le rapport ───────────────────────────────────────────────────────
    def c_(p):
        return equipe.rel(racine, p)
    if deplacements or retouches:
        _p("  %sDESCEND DE LA RACINE (%d)%s" % (B, len(deplacements) + len(retouches), X))
        for s_, c in deplacements:
            _p("    %-44s %s-> %s%s" % (c_(s_), D, c_(c), X))
        for c, _, s_ in retouches:
            _p("    %-44s %s-> %s%s" % (c_(s_), D, c_(c), X))
    if poser or ajouts:
        _p("  %sÀ POSER (%d)%s" % (B, len(poser) + len(ajouts), X))
        for p, _, quoi in poser + ajouts:
            _p("    %-44s %s%s%s" % (c_(p), D, quoi, X))
    if not (deplacements or retouches or poser or ajouts):
        _p("  %sCe projet est déjà au harnais.%s Rien à poser." % (V, X))

    _p("\n  %sLE PAQUET%s" % (B, X))
    ins = vue.inscriptions()
    if isinstance(ins, vue.Toutes):
        _p("    %sinscrit dans tes réglages utilisateur%s — il se charge dans ce dépôt sans rien y déclarer." % (V, X))
    else:
        _p("    %sPAS inscrit dans tes réglages utilisateur.%s Lance l'installation (install.ps1) : "
           "sans elle, aucun hook ne part et rien ne le dit." % (J, X))
    sf = copilot.settings(racine)
    if os.path.isfile(sf):
        _p("    %s%s existe : s'il déclare le paquet par un chemin de CE poste, ce chemin est faux "
           "chez les autres — ne pas le commiter.%s" % (J, c_(sf), X))
    _p("\n  %sENSUITE, À TA MAIN%s" % (B, X))
    _p("    · remplir `cap:` dans %s/brain/fact/base.md" % rel)
    _p("    · relire les profils : le rôle de chaque agent, ce qu'il tient et ne touche pas")
    _p("    · commiter, pousser ; chacun tire, puis choisit « %s » dans le menu d'agent" % noms[0])

    if not go:
        _p("\n  %sRien n'a été écrit.%s Relance avec %s--go%s pour appliquer." % (J, X, B, X))
        return 0

    for src, cible in deplacements:
        os.makedirs(os.path.dirname(cible), exist_ok=True)
        if _suivi(racine, src):
            if not equipe.git(racine, ["mv", "--", src, cible]):
                _e("adopte : git mv %s %s a échoué." % (c_(src), c_(cible)))
                return 1
        else:
            os.rename(src, cible)
    for cible, contenu, vieux in retouches:
        with open(cible, "x", encoding="utf-8", newline="") as h:
            h.write(contenu)
        if _suivi(racine, vieux):
            equipe.git(racine, ["rm", "-q", "--", vieux])
            equipe.git(racine, ["add", "--", cible])
        else:
            os.remove(vieux)
    n = 0
    for p, contenu, _ in poser:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        try:
            with open(p, "x", encoding="utf-8", newline="") as h:
                h.write(contenu)
            n += 1
        except FileExistsError:
            pass
    for p, contenu, _ in ajouts:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        equipe.ecrit(p, contenu)
        n += 1
    _p("\n  %s%d déplacement(s), %d fichier(s) posé(s).%s" % (V, len(deplacements) + len(retouches), n, X))
    _p("  Ouvre une session à la racine du dépôt et choisis « %s » : le briefing doit nommer %s."
       % (noms[0], rel))
    return 0
