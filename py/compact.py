# -*- coding: utf-8 -*-
"""Export explicite vers les profils-rôles et périmètres centralisés.

Port de `harnais/src/compact.rs` (Rust, Copilot 1.3.0) ; le Rust gagne.
Aucun dossier historique, livrable ou fichier de mémoire n'est déplacé.

Seule différence de texte voulue : le dossier des livrables est `assets/`
(`agent.BANC`) ici, `outputs/` dans le Rust. Les messages d'erreur d'un JSON
illisible sont ceux de Python, pas ceux de serde.
"""
import os
import sys

DEBUT = "<!-- harnais:role:start -->"
FIN = "<!-- harnais:role:end -->"


def lit(p):
    """`Ok(Some(texte))`, `Ok(None)` si le fichier manque, sinon lève `Refus`."""
    import copilot
    import equipe
    try:
        return equipe.lis(p)
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as e:
        raise copilot.Refus("%s : %s" % (p, equipe.err_es(e)))


def relatif(p, racine):
    import equipe
    if equipe.meme_chemin(p, racine):
        return "."
    return equipe.rel(racine, p)


def _rstrip(t):
    return t.rstrip()


def prepare(p):
    """Les fichiers à écrire, `[(chemin, texte)]` ; lève `copilot.Refus` si l'export
    est impossible. Ne touche à rien."""
    import agent
    import copilot
    import equipe
    racine = copilot.racine_git(p)
    j = os.path.join
    if not os.path.isdir(j(racine, "brain/fact")):
        raise copilot.Refus("forme compacte : migrer la mémoire vers brain/ d'abord")
    try:
        entrees = os.listdir(j(racine, "brain/mind"))
    except OSError as e:
        raise copilot.Refus("brain/mind : %s" % equipe.err_es(e))
    noms = sorted(n for n in entrees if os.path.isdir(j(racine, "brain/mind", n)))
    if not noms:
        raise copilot.Refus("forme compacte : aucune mémoire d'agent ; créer l'équipe d'abord")
    for i, n in enumerate(noms):
        s = agent.nom_de_profil(n)
        if not s or any(agent.nom_de_profil(a) == s for a in noms[:i]):
            raise copilot.Refus("nom de profil vide ou en collision : %s" % n)
        for f in ("state.md", "todo.md"):
            if not os.path.isfile(j(racine, "brain/mind", n, f)):
                raise copilot.Refus("mémoire incomplète : %s/%s" % (n, f))
    ecrits = []
    for n in noms:
        profil = agent.profil(racine, n)
        ancien = j(racine, "agents", n)
        existant = lit(profil)
        if existant is not None and DEBUT in existant:
            if FIN not in existant:
                raise copilot.Refus("%s : rôle compact incomplet" % profil)
            texte = existant
        else:
            # Les deux lectures ont lieu, même si la première suffit : une erreur
            # sur la seconde refuse l'export, comme dans le Rust.
            r1 = lit(j(ancien, "AGENTS.md"))
            r2 = lit(j(ancien, "CLAUDE.md"))
            role = r1 if r1 is not None else r2
            if existant is not None:
                if existant.startswith("---\n") or existant.startswith("---\r\n"):
                    base = existant
                else:
                    raise copilot.Refus("%s : frontmatter absent ; réconcilier à la main" % profil)
            else:
                base = ("---\nname: %s\ndescription: Agent %s — rôle et mémoire propres au projet\n---\n"
                        % (agent.nom_de_profil(n), n))
            # Un profil déjà autonome n'a pas besoin d'un ancien AGENTS.md.
            if role is not None:
                texte = "%s\n\n%s\n%s%s\n" % (_rstrip(base), DEBUT,
                                              role if role.endswith("\n") else role + "\n", FIN)
            elif existant is not None:
                texte = base
            else:
                raise copilot.Refus("%s : aucun rôle ni profil à exporter" % n)
        rp = relatif(profil, racine)
        texte = texte.replace("agents/%s/AGENTS.md" % n, rp).replace("agents/%s/CLAUDE.md" % n, rp)
        for a in noms:
            texte = texte.replace("agents/%s/livrables" % a, agent.banc(a))
        garde = agent.perimetre_compact(racine, n)
        source = garde if os.path.exists(garde) else j(ancien, ".github/copilot/perimetre.json")
        t = lit(source)
        if t is None:
            raise copilot.Refus("%s : périmètre source absent ; aucune écriture" % source)
        v = equipe._json_ou_refus(t, source)
        liste = v.get("deny") if isinstance(v, dict) else None
        if not isinstance(liste, list):
            raise copilot.Refus("%s : deny doit être une liste" % source)
        deny = []
        for x in liste:
            if not isinstance(x, str):
                raise copilot.Refus("deny doit contenir uniquement des chemins")
            if copilot._absolu(x):
                c = equipe.canonicalize(x) or x
                normalise = relatif(c, racine) if equipe.strip_prefix(c, racine) is not None else x
            else:
                normalise = x.replace("\\", "/")
            if not normalise:
                raise copilot.Refus("chemin deny vide : réconcilier à la main")
            # L'ancien refus de docs/ devient la liste positive : seul le
            # nouveau dossier de livrables propre pourra s'y écrire.
            if (normalise != "docs" or os.path.exists(garde) or not equipe.est_qa(n)) and normalise not in deny:
                deny.append(normalise)
        for a in [a for a in noms if a != n]:
            for interdit in ("brain/mind/%s" % a, agent.banc(a)):
                if interdit not in deny:
                    deny.append(interdit)
        for interdit in list(agent.CONTROLE) + ["brain/poids.json"]:
            if interdit not in deny:
                deny.append(interdit)
        if not equipe.est_qa(n) and "brain/fact" not in deny:
            deny.append("brain/fact")
        v["deny"] = deny
        if not os.path.exists(garde):
            if "allow" in v:
                liste = v["allow"]
                if not isinstance(liste, list):
                    raise copilot.Refus("allow doit être une liste")
                chemins = []
                for x in liste:
                    if not isinstance(x, str) or not x.strip():
                        raise copilot.Refus("allow doit contenir des chemins non vides")
                    chemins.append(x.replace("agents/%s/livrables" % n, agent.banc(n)))
                v["allow"] = chemins
            else:
                a = equipe.allow_par_defaut(n, "brain/fact", "brain/mind/%s" % n, agent.banc(n))
                if a is not None:
                    v["allow"] = a
        else:
            copilot.lis_allow(agent.contexte(racine, n))
        for f, t in ((profil, texte), (garde, equipe.json_indent2(v) + "\n")):
            if lit(f) != t:
                ecrits.append((f, t))
    return ecrits


def main(p, appliquer):
    import agent
    import copilot
    import equipe
    try:
        ecrits = prepare(p)
    except copilot.Refus as e:
        sys.stderr.write("equipe --compact : %s\n" % e)
        return 1
    sys.stdout.write("── Architecture compacte%s\n" % ("" if appliquer else " [DRY-RUN]"))
    for f, texte in ecrits:
        sys.stdout.write("\n── %s ──\n%s\n" % (f, texte))
    sys.stdout.write("Les mémoires, docs et anciens dossiers agents/ restent INCHANGÉS. "
                     "Les rôles exportés utilisent %s/<nom>/ : déplacer les livrables et "
                     "réconcilier les références communes séparément, après accord. "
                     "Les périmètres centralisés deviennent prioritaires. Ne retirer agents/ "
                     "qu'après validation des profils, mémoires et gardes dans une nouvelle session.\n"
                     % agent.BANC)
    if appliquer:
        for f, texte in ecrits:
            try:
                os.makedirs(os.path.dirname(f), exist_ok=True)
                equipe.ecrit(f, texte)
            except OSError as e:
                sys.stderr.write("%s : %s ; export interrompu\n" % (f, equipe.err_es(e)))
                return 1
    else:
        sys.stdout.write("Aucune écriture. Relancer avec --apply pour exporter.\n")
    return 0
