# -*- coding: utf-8 -*-
"""LES TROIS NATURES DE LA MÉMOIRE — fait, croyance, expérience — et TOUS les
poids qui la font vivre, réunis à un seul endroit.

Port de `harnais/src/nature.rs` (Rust, 0.12.8).

Décidé par Maxime le 11/09/2026 (« fais construire les 3 natures ») après que le
CTO a mesuré qu'on n'avait pris à SenseLab que la moitié de son modèle : la
confiance qui bouge avec les résultats, pas les natures qui vieillissent chacune
à sa vitesse.

DEUX AXES, ET ILS NE FONT PAS LE MÊME TRAVAIL.

· le NIVEAU (mesuré · observé · supposé · dit) dit COMMENT une entrée a été
  établie : il fixe d'où part sa confiance ;
· la NATURE dit CE QU'ELLE EST : elle fixe à quelle vitesse elle vieillit — une
  croyance deux fois plus vite qu'un fait, une expérience une fois et demie
  moins vite. Les rapports de SenseLab, repris tels quels.

Un seul point de contact, et il est de définition : UNE SUPPOSITION EST UNE
CROYANCE, où qu'elle soit posée. Déclarer « fait » sur une supposition ne la
fait pas vieillir moins vite : on ne sort de la pente rapide que par une mesure,
jamais par une étiquette.

LA NATURE NE SE DEVINE PAS, ET ELLE SE DÉCLARE RAREMENT. Mesuré le 11/09/2026
sur les 201 notes de l'atelier, avant d'écrire une ligne :
· le type que Claude Code pose sur chaque note (79 consignes, 74 projet, 44
  références) NE SE TRADUIT PAS en nature — les « consignes » sont surtout des
  leçons mesurées, les « références » des faits d'environnement. En tirer la
  nature serait un classement automatique, et on sait ce qu'il vaut : 51
  « mesuré » sur 55 notes le 09/09 ;
· un axe déclaré à la main s'effondre de lui-même : 71 des 77 notes qui portent
  un niveau disent « mesuré ».

La nature vient donc d'abord de la MAISON, dont c'est déjà la règle écrite : les
faits du projet et les leçons de méthode — établies par une mesure — tiennent des
faits ; le carnet d'équipe, qui consigne ce qu'un agent a fait, tient des
expériences. Une entrée ne déclare sa nature que pour contredire sa maison, et
le rapport dit toujours d'où vient celle qu'il affiche.

Les traces datées et l'état d'un agent n'ont PAS de maison ici : rien ne les
fait vieillir aujourd'hui, et une maison sans lecteur n'a pas de poids à porter.
Elles en recevront une le jour où quelque chose les servira.

LA NATURE MULTIPLIE DES DURÉES, JAMAIS UN CHIFFRE. Partout où quelque chose
vieillit — le délai d'endormissement d'une note, le délai d'oubli d'une entrée de
carnet, la péremption d'un fait —, c'est ce délai qu'elle étire ou raccourcit. Le
résultat, lui, fait bouger la confiance de la même façon quelle que soit la
nature : une entrée lue puis démentie a mal guidé, fait ou croyance.

Les chemins chauds n'importent rien ici : `carnet` (pour `sansaccents`) ne se
charge qu'au premier appel qui en a besoin.
"""


class Nature(object):
    """Une constante-chaîne par nature, comme `Forme` dans `memoire`."""
    Fait = "Fait"
    Croyance = "Croyance"
    Experience = "Experience"


class Origine(object):
    """D'où vient la nature affichée — le rapport le dit toujours : une nature
    tirée de la maison n'a pas le poids d'une nature que l'auteur a posée."""
    Supposition = "Supposition"
    Declaree = "Declaree"
    Maison = "Maison"


class Maison(object):
    """Les maisons dont quelque chose fait vieillir le contenu."""
    Faits = "Faits"
    MemoireAuto = "MemoireAuto"
    Carnet = "Carnet"


_MOTS = {Nature.Fait: "fait", Nature.Croyance: "croyance", Nature.Experience: "expérience"}
# Le multiplicateur des DURÉES.
_PENTES = {Nature.Fait: 1.0, Nature.Croyance: 0.5, Nature.Experience: 1.5}


def _sansaccents(s):
    try:
        from carnet import sansaccents
    except ImportError:
        # `carnet` est écrit en parallèle (même nom que le Rust : `sansaccents`).
        # Repli identique à sa définition — À RETIRER quand `py/carnet.py` existe.
        import unicodedata
        return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                       if not unicodedata.combining(c))
    return sansaccents(s)


def mot(nature):
    return _MOTS[nature]


def pente(nature):
    """Le multiplicateur des DURÉES."""
    return _PENTES[nature]


def lis(mot_):
    """Un mot déclaré par l'auteur, en français ou dans le vocabulaire de
    SenseLab. UN MOT INCONNU NE VAUT RIEN : il ne devient pas un fait par défaut,
    il laisse la maison décider, comme s'il n'avait pas été écrit.

    Rend une `Nature`, ou None."""
    m = _sansaccents(mot_.strip())
    if m in ("fait", "fact"):
        return Nature.Fait
    if m in ("croyance", "belief"):
        return Nature.Croyance
    if m == "experience":
        return Nature.Experience
    return None


# `Nature::lis(..)`, `n.mot()` et `n.pente()` du Rust : mêmes noms, appelés sur la classe.
Nature.lis = staticmethod(lis)
Nature.mot = staticmethod(mot)
Nature.pente = staticmethod(pente)


def de_la_maison(m):
    if m in (Maison.Faits, Maison.MemoireAuto):
        return Nature.Fait
    return Nature.Experience


def de(maison, niveau, declaree):
    """La nature d'une entrée, et d'où elle vient : `(Nature, Origine)`. L'ORDRE
    EST LA RÈGLE : la supposition d'abord (elle est de définition), la
    déclaration ensuite (elle contredit sa maison), la maison enfin."""
    if niveau is not None and _sansaccents(niveau.strip()) == "suppose":
        return (Nature.Croyance, Origine.Supposition)
    if declaree is not None:
        n = lis(declaree)
        if n is not None:
            return (n, Origine.Declaree)
    return (de_la_maison(maison), Origine.Maison)


# LA LOI DES QUATRE SEMAINES — « un fait non revérifié depuis 4 semaines est
# présumé faux ». Écrite dans les consignes de la machine depuis le début, codée
# nulle part avant le 11/09/2026. C'est la durée d'un FAIT ; la nature la gradue.
PEREMPTION_FAIT_J = 28.0


def duree(n, base):
    return base * pente(n)


# ── d'où part la confiance : le niveau ──────────────────────────────────────

def depart(niveau, maison):
    """Le départ, fixé par le NIVEAU — le `provenance_tier` de SenseLab. C'est la
    moitié qui vaut d'être copiée : un niveau dit QUOI FAIRE pour vérifier, là où
    un nombre saisi à la main ne dit rien.

    DEUX COPIES RÉUNIES, SANS CHANGER LEURS VALEURS — la fin de tour et le carnet
    portaient chacun la leur. Une seule a bougé : `dit` au carnet, 60 → 85 ; sa
    copie ne connaissait pas ce niveau et le rangeait avec l'inconnu. L'inconnu,
    lui, diverge À DESSEIN : une note sans niveau pèse un poids inconnu (50), une
    entrée de carnet est écrite par le hook depuis une tâche cochée — observée
    par construction (60).
    """
    n = _sansaccents(niveau.strip())
    if n == "mesure":
        return 80
    if n == "dit":
        return 85
    if n == "observe":
        return 60
    # « lu » (12/10/2026) : le niveau des experts — lu dans un document, un
    # registre, une pièce reçue. Pas une mesure qu'on peut rejouer, pas un dire :
    # une observation, et elle part du même poids.
    if n == "lu":
        return 60
    if n == "suppose":
        return 40
    return 60 if maison == Maison.Carnet else 50


# ── ce que le résultat fait à ce qu'on avait lu ─────────────────────────────
#
# Les multiplicateurs de SenseLab, relevés dans son code. L'ASYMÉTRIE EST
# DÉLIBÉRÉE : la confiance doit être facile à perdre et lente à reconstruire.

# Une entrée lue, puis un travail que la vérification confirme — un constat qui
# TIENT, une tâche aboutie au carnet.
REUSSITE = 1.03
# Une garde a mordu après la lecture : échec MINEUR — un rappel de forme n'est
# pas un démenti.
GARDE = 0.92
# Un constat démenti deux fois de suite : le vrai démenti.
DEMENTI = 0.90
# Une tâche que son agent déclare échouée au carnet — le coup le plus dur.
ECHEC_DECLARE = 0.85
