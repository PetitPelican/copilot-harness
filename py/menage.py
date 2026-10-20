# -*- coding: utf-8 -*-
"""LE MÉNAGE D'UN PROJET — ou de tout un atelier — sans jamais décider à la
place de quelqu'un.

Port de `harnais/src/menage.rs` (Rust, 0.12.8) ; le Rust gagne. (Le Rust avait
été porté de `agentic-clean.py` le 11/09/2026 : le script n'existait qu'en
Python, donc échouait en silence sur le PC Windows.)

Trois familles, rendues SÉPARÉMENT parce qu'elles n'ont pas la même nature :

  1. CACHES RÉGÉNÉRABLES  supprimés (sous `--apply`), avec la commande qui les
                          refait. Un `node_modules` n'est pas une donnée.
  2. RÉSIDUS DE MIGRATION listés seulement. Ce sont des phrases que quelqu'un a
                          écrites ; seul l'agent du projet sait si elles sont
                          reprises ailleurs.
  3. MÉMOIRE HYPERTROPHIÉE listée seulement. Trier, c'est choisir ce qu'on
                          oublie — un programme n'a pas à le faire.

**Dry-run par défaut.** `--apply` n'agit QUE sur la famille 1.

LE PORTAGE EST À L'OCTET, bizarreries comprises : il rend ce que rendait le
Python sur l'atelier fabriqué de `controles/corpus-menage.sh`, et le témoin
figé AVANT le retrait du script le prouve. Deux bizarreries connues sont
gardées exprès pour cette raison, et se corrigent à part, en le disant :
la « plus ancienne date » est triée comme du texte, et un projet en
`brain/` voit sa mémoire cherchée dans `.memory/`.
"""
import os
import stat
import sys

# Chaque entrée dit COMMENT ça repousse. Sans cette colonne, la suppression
# est un pari ; avec elle, c'est une opération réversible.
# `dist` et `build` n'appartiennent à aucun écosystème : voir `refait_par`.
# `.build` (Swift Package Manager) : absent de la première liste, trouvé par
# un agent de projet en mesurant à la main — 192 Mo invisibles.
CACHES = [
    ("node_modules", "npm ci  (ou pnpm install / yarn install)"),
    (".turbo", "refait seul au prochain `turbo`"),
    (".next", "npm run build"),
    (".astro", "npm run build  (ou `astro sync`)"),
    (".nuxt", "npm run build"),
    (".svelte-kit", "npm run build"),
    (".parcel-cache", "refait seul au prochain build"),
    (".vite", "refait seul au prochain build"),
    ("dist", ""),
    ("build", ""),
    (".venv", "uv sync  (ou python3 -m venv .venv && pip install -r requirements.txt)"),
    ("venv", "uv sync  (ou python3 -m venv venv && pip install -r requirements.txt)"),
    ("__pycache__", "refait seul à l'import suivant"),
    (".mypy_cache", "refait seul au prochain mypy"),
    (".pytest_cache", "refait seul au prochain pytest"),
    (".ruff_cache", "refait seul au prochain ruff"),
    (".gradle", "refait seul au prochain build Gradle"),
    ("DerivedData", "refait seul au prochain build Xcode"),
    (".build", "refait seul au prochain `swift build`"),
    ("Pods", "pod install"),
    ("coverage", "refait seul au prochain run de tests"),
    (".nyc_output", "refait seul au prochain run de tests"),
]
_NOMS_CACHES = frozenset(n for n, _ in CACHES)


def est_cache(nom):
    return nom in _NOMS_CACHES


def ne_pas_descendre(nom):
    """On ne descend jamais DANS un cache : y chercher d'autres caches coûte des
    minutes sur un `node_modules` de 6 Go pour ne rien apprendre."""
    return est_cache(nom) or nom == ".git"


# `MONTENT` nomme des fichiers qui ont une place ailleurs, `ANCIENS` des
# fichiers qui n'en ont plus. Tout le reste de `docs/` est de la matière de
# domaine, qu'on se garde de signaler.
MONTENT = ["state.md", "rules.md", "architecture.md"]
ANCIENS = ["charter.md", "business.md", "clients.md", "overview.md"]
# `docs/` ne contient que de l'écrit à la main (règle du 04/09/2026).
GENERE = [".pdf", ".html", ".png", ".jpg", ".jpeg", ".zip", ".docx", ".xlsx", ".svg"]
SEUIL_LIGNES = 500


class Rapport(object):
    def __init__(self):
        self.caches = []
        self.residus = []
        self.memoire = []


def mo(n):
    return n / 1048576.0


def _p(s=""):
    sys.stdout.write(s + "\n")


# ── chemins : la sémantique de `std::path` ──────────────────────────────────

def _composants(p):
    """(racine, composants) — la racine est "" (relatif), "/" ou, sous Windows,
    le lecteur ("C:/"). Sous Windows `\\` vaut `/` : sans cela un chemin entier
    n'est qu'UN composant, et rien n'est jamais « sous » le projet (mesuré par
    la CI Windows : ménage aveugle, migration refusée)."""
    if os.name == "nt":
        p = p.replace("\\", "/")
        if p.startswith("//?/"):
            p = p[4:]
        if len(p) >= 2 and p[1] == ":" and p[0].isalpha():
            return p[0].upper() + ":/", [c for c in p[2:].split("/") if c not in ("", ".")]
    return ("/" if p.startswith("/") else ""), [c for c in p.split("/") if c not in ("", ".")]


def strip_prefix(p, base):
    rp, cp = _composants(p)
    rb, cb = _composants(base)
    if rp != rb or cp[:len(cb)] != cb:
        return None
    return "/".join(cp[len(cb):])


def nom_de(p):
    """`file_name()` en texte, vide s'il n'y en a pas."""
    _, c = _composants(p)
    if not c or c[-1] == "..":
        return ""
    return c[-1]


def extension(nom):
    """`Path::extension` d'un nom de fichier (`.spec` seul n'a pas d'extension)."""
    i = nom.rfind(".")
    if i <= 0 or nom == "..":
        return None
    return nom[i + 1:]


def _cle(p):
    """Le tri de `PathBuf` : par COMPOSANTS, pas comme du texte."""
    rp, cp = _composants(p)
    return (rp, cp)


def canonicalize(p):
    if not os.path.exists(p):
        return None
    try:
        return os.path.realpath(p)
    except OSError:
        return None


def entrees(d):
    """Les entrées d'un dossier, triées par nom : le Python suivait l'ordre du
    système de fichiers, qui ne se promet nulle part. Trier ne change rien au
    témoin, et rend le rapport stable d'une machine à l'autre."""
    try:
        return [os.path.join(d, n) for n in sorted(os.listdir(d))]
    except OSError:
        return []


def est_dossier(p):
    """Un dossier tel que `os.walk` le voit : un lien vers un dossier est LISTÉ
    comme dossier, mais jamais parcouru."""
    return os.path.isdir(p)


def est_lien(p):
    return os.path.islink(p)


def dossier_memoire(projet):
    """`docs/` après migration, `.memory/` avant. La FORME décide, jamais la
    simple présence d'un `docs/`."""
    if os.path.isdir(os.path.join(projet, ".fact")):
        return os.path.join(projet, "docs")
    return os.path.join(projet, ".memory")


def poids(chemin, vus):
    """Taille d'une arborescence, comptée comme `du` la compte. Les LIENS DURS
    (pnpm relie ses paquets) ne se comptent qu'une fois par `(device, inode)` —
    sinon 13 950 Mo annoncés sur un projet qui en pèse 9 488. Les liens
    symboliques ne sont jamais suivis."""
    total = 0
    pile = [chemin]
    while pile:
        d = pile.pop()
        for p in entrees(d):
            try:
                m = os.lstat(p)
            except OSError:
                continue
            if stat.S_ISLNK(m.st_mode):
                continue
            if stat.S_ISDIR(m.st_mode):
                pile.append(p)
                continue
            if os.name == "posix" and m.st_nlink > 1:
                cle = (m.st_dev, m.st_ino)
                if cle in vus:
                    continue
                vus.add(cle)
            total += m.st_size
    return total


def ignore_par_git(projet, chemin):
    """`True` ignoré, `False` suivi, `None` pas un dépôt git. C'est le
    discriminant de tout le ménage : le MÊME dossier suivi par git est du
    contenu que quelqu'un a décidé de versionner."""
    if not os.path.exists(os.path.join(projet, ".git")):
        return None
    import subprocess
    try:
        r = subprocess.run(["git", "-C", projet, "check-ignore", "-q", chemin],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, ValueError):
        return None
    return r.returncode == 0


def refait_par(cache):
    """Comment CE dossier-là se reconstruit. `dist/` et `build/` ne disent rien
    de leur écosystème : on regarde ce qui se trouve à côté, puis chez le
    parent — sinon on promet « npm run build » devant un `dist` de PyInstaller."""
    nom = nom_de(cache)
    for n, fixe in CACHES:
        if n == nom:
            if fixe:
                return fixe
            break
    parent = os.path.dirname(cache.rstrip("/")) if cache.rstrip("/") else ""
    grand = os.path.dirname(parent.rstrip("/")) if parent.rstrip("/") else ""
    for d in (parent, grand):
        if not os.path.isdir(d):
            continue
        if any(extension(os.path.basename(p)) == "spec" for p in entrees(d)):
            return "pyinstaller <le .spec d'à côté>"
        if os.path.isfile(os.path.join(d, "package.json")):
            return "npm run build"
        if os.path.isfile(os.path.join(d, "pyproject.toml")):
            return "python -m build  (ou le script de packaging du projet)"
        if os.path.isfile(os.path.join(d, "Cargo.toml")):
            return "cargo build"
    return "LE BUILD DU PROJET — non identifié, vérifier avant de supprimer"


def cherche_caches(projet):
    """Les caches, sans jamais descendre dans un cache déjà trouvé."""
    trouves = []
    pile = [projet]
    while pile:
        d = pile.pop()
        for p in entrees(d):
            if not est_dossier(p):
                continue
            nom = nom_de(p)
            if est_cache(nom):
                trouves.append(p)
            elif not ne_pas_descendre(nom) and not est_lien(p):
                pile.append(p)
    # Par COMPOSANTS, comme `sorted()` trie des chemins Python — pas comme du
    # texte : « app/x » et « app.y » ne se rangent pas pareil.
    trouves.sort(key=_cle)
    return trouves


def relatif(projet, p):
    r = strip_prefix(p, projet)
    if r is not None:
        return r
    rp, cp = _composants(p)
    return rp + "/".join(cp)


def gauche(s, n):
    l = len(s)
    return s if l >= n else s + " " * (n - l)


def famille_caches(projet, rap, appliquer):
    """Supprime — c'est la SEULE famille qui écrit. Le registre des inodes est
    partagé par TOUS les caches du projet : deux `node_modules` pnpm qui
    pointent le même inode ne sont comptés qu'une fois."""
    rendu, vus, menus = 0, set(), []
    for c in cherche_caches(projet):
        p = poids(c, vus)
        rel = relatif(projet, c)
        nom = nom_de(c)
        etat = ignore_par_git(projet, c)
        if etat is False:
            rap.residus.append("%s %8.1f Mo  SUIVI PAR GIT — pas supprimé. C'est un "
                               "problème de .gitignore, pas de ménage." % (gauche(rel, 42), mo(p)))
            continue
        if etat is None and nom in ("dist", "build", "coverage"):
            rap.residus.append("%s %8.1f Mo  hors dépôt git et nom ambigu — pas supprimé, "
                               "vérifier que ce n'est pas de la source." % (gauche(rel, 42), mo(p)))
            continue
        # Un monorepo a vingt `.turbo` vides : on les compte, on ne les
        # détaille pas — un rapport qu'on ne lit pas ne protège de rien.
        if mo(p) < 1.0:
            menus.append(rel)
        else:
            rap.caches.append("%s %8.1f Mo  <- %s" % (gauche(rel, 42), mo(p), refait_par(c)))
        rendu += p
        if appliquer:
            if os.path.islink(c):
                # `remove_dir_all` d'un lien retire le lien, jamais sa cible.
                try:
                    os.unlink(c)
                except OSError:
                    pass
            else:
                import shutil
                shutil.rmtree(c, ignore_errors=True)
    if menus:
        noms = sorted(set(m.rsplit("/", 1)[-1] for m in menus))
        rap.caches.append("%s %8s     %d dossier(s) : %s" % (
            gauche("(caches de moins de 1 Mo)", 42), "<1 Mo", len(menus), ", ".join(noms)))
    return rendu


def fichiers_sous(d):
    """Tous les fichiers sous `d`, récursivement, liens non suivis."""
    out = []
    pile = [d]
    while pile:
        x = pile.pop()
        for p in entrees(x):
            if os.path.isdir(p):
                if not est_lien(p):
                    pile.append(p)
                continue
            out.append(p)
    return out


def mot_rust(c):
    """Un caractère `\\w` au sens du crate `regex` (Unicode) : alphabétique, marque,
    chiffre décimal, ponctuation de liaison (Pc), `Join_Control`. Python ne dit
    pas la même chose : son `\\w` ignore les marques, `‿` et U+200D, et accepte
    `²` ou `½` — d'où des `\\b` qui ne tombent pas au même endroit (mesuré contre
    le binaire, noms de fichiers à marques combinantes)."""
    import unicodedata
    if c in ("\u200c", "\u200d") or "\u24b6" <= c <= "\u24e9":
        return True
    return unicodedata.category(c) in ("Lu", "Ll", "Lt", "Lm", "Lo", "Nl", "Nd", "Mn", "Mc", "Me", "Pc")


def _frontiere_apres(texte, fin):
    """`\\b` après un caractère de mot : vrai à la fin du texte, ou devant un non-mot."""
    return fin >= len(texte) or not mot_rust(texte[fin])


def _frontiere_avant(texte, debut):
    """`\\b` avant un caractère de mot : vrai au début du texte, ou derrière un non-mot."""
    return debut == 0 or not mot_rust(texte[debut - 1])


def _cherche_borne(motif, texte, avant, apres):
    """Premier résultat de `motif` dont les bords tiennent les `\\b` demandés — comme
    le moteur, qui retente à chaque position suivante quand une frontière échoue."""
    pos = 0
    while True:
        m = motif.search(texte, pos)
        if m is None:
            return None
        if (not avant or _frontiere_avant(texte, m.start())) and \
                (not apres or _frontiere_apres(texte, m.end())):
            return m
        pos = m.start() + 1


def famille_residus(projet, rap):
    """Listée, jamais supprimée."""
    import re
    memoire = dossier_memoire(projet)
    nom_mem = nom_de(memoire)
    if nom_mem == "docs" and os.path.isdir(memoire):
        genere = []
        for f in fichiers_sous(memoire):
            e = extension(os.path.basename(f))
            if e is not None and ("." + e.lower()) in GENERE:
                genere.append(nom_de(f))
        genere.sort()
        if genere:
            tete = ", ".join(genere[:5])
            rap.residus.append("docs/ porte %d fichier(s) qui ressemblent à des sorties de build "
                               "(%s%s) : `docs/` ne contient que de l'écrit à la main — les sortir vers `site/` ou un dossier de build."
                               % (len(genere), tete, ", …" if len(genere) > 5 else ""))
    if os.path.isdir(memoire):
        for f in entrees(memoire):
            if not os.path.isfile(f) or extension(os.path.basename(f)) != "md":
                continue
            n = nom_de(f)
            if n in MONTENT:
                rap.residus.append("%s/%s dit des FAITS ACTUELS : MONTE dans .fact/ ou "
                                   ".mind/, il y a déjà sa place" % (nom_mem, gauche(n, 33)))
            elif n in ANCIENS:
                rap.residus.append("%s/%s taxonomie d'avant le 02/09/2026 : à trier, son "
                                   "contenu se répartit entre .fact/, .mind/ et docs/" % (nom_mem, gauche(n, 33)))
        archive = os.path.join(memoire, "archive")
        if os.path.isdir(archive):
            fs = fichiers_sous(archive)
            couverts = [nom_de(p) for p in fs if nom_de(p) in MONTENT or nom_de(p) in ANCIENS]
            n_couverts = len(couverts)
            couverts = sorted(set(couverts))
            rap.residus.append("docs/archive/%s %d fichier(s), %.1f Mo — dont %d repris "
                               "par .mind/ (%s)" % (gauche("", 25), len(fs), mo(poids(archive, set())), n_couverts,
                                                    ", ".join(couverts) if couverts else "aucun"))
    # `(?i)` : Unicode des deux côtés. Le `\b` du Rust, lui, se refait à la main
    # (`mot_rust`) ; `~\Z` pour le `$` du Rust (fin de texte, jamais avant un `\n`).
    reg_b = re.compile(r"\.(bak|old|orig|sav)", re.IGNORECASE)
    reg_c = re.compile(r"\.bak[-.]|\.avant[-.]|~\Z", re.IGNORECASE)
    pile = [projet]
    trouves = []
    while pile:
        d = pile.pop()
        for p in entrees(d):
            n = nom_de(p)
            if os.path.isdir(p):
                if not ne_pas_descendre(n) and not est_lien(p):
                    pile.append(p)
                continue
            if reg_c.search(n) or _cherche_borne(reg_b, n, False, True):
                trouves.append(p)
    trouves.sort(key=_cle)
    for p in trouves:
        try:
            taille = os.stat(p).st_size
        except OSError:
            taille = 0
        rap.residus.append("%s %8.1f Mo  sauvegarde manuelle" % (gauche(relatif(projet, p), 42), mo(taille)))


def lignes(s):
    """`str::lines` de Rust : coupe sur `\\n`, ôte un `\\r` AVANT un `\\n`, rien d'autre."""
    if not s:
        return []
    parts = s.split("\n")
    if parts[-1] == "":
        parts.pop()
        return [x[:-1] if x.endswith("\r") else x for x in parts]
    return [x[:-1] if (x.endswith("\r") and i < len(parts) - 1) else x for i, x in enumerate(parts)]


def famille_memoire(projet, rap):
    """Listée, jamais touchée. Trier, c'est choisir ce qu'on oublie."""
    import re
    memoire = dossier_memoire(projet)
    if not os.path.isdir(memoire):
        return
    # Les deux `\b` de chaque branche se refont à la main (`mot_rust`) : voir `_cherche_borne`.
    date = re.compile(r"(20\d\d)[-/](\d\d)[-/](\d\d)|(\d\d)/(\d\d)/(20\d\d)")
    fs = [f for f in fichiers_sous(memoire) if extension(os.path.basename(f)) == "md"]
    fs.sort()
    for f in fs:
        try:
            with open(f, "rb") as h:
                octets = h.read()
        except OSError:
            continue
        texte = octets.decode("utf-8", "replace")
        ls = lignes(texte)
        if len(ls) < SEUIL_LIGNES:
            continue
        # TRIÉES COMME DU TEXTE — la bizarrerie du Python, gardée à l'octet :
        # « 12/05/2026 » passe devant « 2026-03-04 ».
        dates = []
        for l in ls:
            m = _cherche_borne(date, l, True, True)
            if m:
                dates.append(m.group(0))
        dates.sort()
        rap.memoire.append("%s %5d lignes  la plus ancienne entrée datée : %s" % (
            gauche(relatif(projet, f), 42), len(ls), dates[0] if dates else "aucune date lisible"))


def developpe(p):
    if p.startswith("~/"):
        h = os.environ.get("HOME")
        if h is None:
            h = os.environ.get("USERPROFILE")
        if h is not None:
            return os.path.join(h, p[2:])
    return p


def valeur(args, cle):
    it = iter(args)
    for a in it:
        if a == cle:
            return next(it, None)
        if a.startswith(cle + "="):
            return a[len(cle) + 1:]
    return None


def main(args):
    if any(a == "-h" or a == "--help" for a in args):
        _p("harnais menage [--projet P | --racine R] [--apply]\n\n"
           "Fait le ménage d'un projet — ou de tout un atelier — sans jamais décider à la\n"
           "place de quelqu'un. Dry-run par défaut ; `--apply` ne supprime que les caches\n"
           "régénérables, jamais un résidu ni une mémoire.")
        return 0
    appliquer = any(a == "--apply" for a in args)
    racine = valeur(args, "--racine")
    if racine == "":
        racine = None
    if racine is not None:
        r = developpe(racine)
        c = canonicalize(r)
        r = c if c is not None else r
        cibles = [p for p in entrees(r) if os.path.isdir(p) and not nom_de(p).startswith(".")]
    else:
        p = valeur(args, "--projet")
        p = developpe(p if p is not None else ".")
        c = canonicalize(p)
        cibles = [c if c is not None else p]

    _p("Agentic clean — %s" % ("APPLY" if appliquer else "DRY-RUN"))
    _p("Cible%s : %s" % ("s" if len(cibles) > 1 else "", ", ".join(nom_de(c) for c in cibles)))
    _p()

    total = 0
    barre = "═" * 78
    for cible in cibles:
        if not os.path.isdir(cible):
            continue
        rap = Rapport()
        rendu = famille_caches(cible, rap, appliquer)
        famille_residus(cible, rap)
        famille_memoire(cible, rap)
        total += rendu
        if not rap.caches and not rap.residus and not rap.memoire:
            continue
        _p(barre)
        _p("  %s" % nom_de(cible))
        _p(barre)
        if rap.caches:
            _p("\n1. CACHES RÉGÉNÉRABLES — %s (%.1f Mo)" % ("SUPPRIMÉS" if appliquer else "à supprimer", mo(rendu)))
            for m in rap.caches:
                _p("   %s" % m)
        if rap.residus:
            _p("\n2. RÉSIDUS — listés seulement, à trancher par l'agent du projet")
            for m in rap.residus:
                _p("   %s" % m)
        if rap.memoire:
            _p("\n3. MÉMOIRE AU-DELÀ DE %d LIGNES — à découper, jamais automatiquement" % SEUIL_LIGNES)
            for m in rap.memoire:
                _p("   %s" % m)
        _p()
    _p("─" * 78)
    _p("Total récupérable : %.1f Mo" % mo(total))
    if not appliquer:
        _p("\nDry-run. `--apply` supprime la FAMILLE 1 seulement — les familles 2 et 3 ne sont "
           "jamais supprimées par ce script.")
    else:
        _p("\nLes familles 2 et 3 n'ont pas été touchées : elles demandent un jugement sur du "
           "contenu, pas une règle.")
    return 0
