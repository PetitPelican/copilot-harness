# -*- coding: utf-8 -*-
"""LE TRONC COMMUN — ce que le harnais Claude a changé depuis qu'on l'a porté ici.

Les deux harnais partagent la plupart de leurs modules. Sans mesure, une mise à
jour du harnais Claude ne passe ici que si quelqu'un y pense — et sinon les deux
dérivent, sans un mot. Cet outil rend la dérive VISIBLE :

    python3 outils/tronc_commun.py --verifie <dossier claude-harnais>
    python3 outils/tronc_commun.py --enregistre <dossier claude-harnais>

`--enregistre` épingle, pour chaque fonction (ou classe, ou constante) d'un
module présent des deux côtés, l'empreinte de sa version CLAUDE au moment où on
l'a portée : à faire une fois qu'une mise à jour est reportée ici, ou écartée
exprès (`outils/tronc-commun.json` le dit, et git garde l'histoire).

`--verifie` rend 1 si une fonction de Claude a changé, est apparue ou a disparu
depuis l'épinglage, et la NOMME : c'est la liste de ce qu'il reste à regarder.
Il ne dit PAS si la version d'ici est bonne — Copilot diverge à dessein à des
centaines d'endroits ; seul ce que Claude a bougé depuis est une question.

L'empreinte est celle de l'arbre syntaxique, sans les docstrings ni les
numéros de ligne : reformater, commenter ou déplacer ne dérange personne ;
changer une instruction, si.
"""
import ast
import hashlib
import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
ENREGISTREMENT = os.path.join(ICI, "tronc-commun.json")
# Les modules d'ici qui n'existent pas chez Claude, ou l'inverse, n'y figurent pas :
# la liste se déduit des deux dossiers.


def _sans_doc(noeud):
    corps = getattr(noeud, "body", None)
    if (isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and corps and isinstance(corps[0], ast.Expr) and isinstance(getattr(corps[0], "value", None), ast.Constant)
            and isinstance(corps[0].value.value, str)):
        corps[:] = corps[1:] or [ast.Pass()]
    for enfant in ast.iter_child_nodes(noeud):
        _sans_doc(enfant)
    return noeud


def _empreinte(noeud):
    return hashlib.sha1(ast.dump(_sans_doc(noeud)).encode("utf-8")).hexdigest()[:10]


def fonctions(chemin):
    """{nom: empreinte} des définitions de premier niveau (et de leurs méthodes)."""
    with open(chemin, encoding="utf-8") as f:
        arbre = ast.parse(f.read())
    sortie = {}
    for n in arbre.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sortie[n.name] = _empreinte(n)
        elif isinstance(n, ast.ClassDef):
            sortie[n.name] = _empreinte(n)
        elif isinstance(n, ast.Assign):
            for c in n.targets:
                if isinstance(c, ast.Name):
                    sortie[c.id] = _empreinte(n)
    return sortie


def modules(dossier):
    return sorted(f[:-3] for f in os.listdir(os.path.join(dossier, "py"))
                  if f.endswith(".py") and f != "__init__.py")


def releve(claude, ici=RACINE):
    """Pour chaque module commun : l'empreinte Claude, et celle d'ici."""
    commun = sorted(set(modules(claude)) & set(modules(ici)))
    out = {}
    for m in commun:
        c = fonctions(os.path.join(claude, "py", m + ".py"))
        i = fonctions(os.path.join(ici, "py", m + ".py"))
        out[m] = {"claude": c, "ici": i}
    return out


def enregistre(claude, ici=RACINE, fichier=ENREGISTREMENT):
    r = releve(claude, ici)
    pin = {"version": 1, "python": "%d.%d" % sys.version_info[:2], "modules": {m: v["claude"] for m, v in r.items()}}
    with open(fichier, "w", encoding="utf-8", newline="\n") as f:
        json.dump(pin, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    return pin


def ecarts(claude, ici=RACINE, fichier=ENREGISTREMENT):
    """Ce que Claude a changé depuis l'épinglage : (module, nom, état)."""
    with open(fichier, encoding="utf-8") as f:
        brut = json.load(f)
    pin = brut["modules"]
    # L'arbre syntaxique change d'une version de Python à l'autre : comparer des
    # empreintes de deux versions rendrait tout « changé ».
    if brut.get("python") != "%d.%d" % sys.version_info[:2]:
        raise RuntimeError("épinglé avec Python %s, lancé avec %d.%d" % (
            brut.get("python"), sys.version_info[0], sys.version_info[1]))
    r = releve(claude, ici)
    out = []
    for m in sorted(set(pin) | set(r)):
        if m not in r:
            out.append((m, "(module)", "disparu chez Claude ou ici"))
            continue
        avant = pin.get(m)
        if avant is None:
            out.append((m, "(module)", "nouveau module commun"))
            continue
        apres = r[m]["claude"]
        for nom in sorted(set(avant) | set(apres)):
            if nom not in apres:
                out.append((m, nom, "retiré chez Claude"))
            elif nom not in avant:
                out.append((m, nom, "nouveau chez Claude"))
            elif avant[nom] != apres[nom]:
                out.append((m, nom, "changé chez Claude"))
    return out


def main(argv):
    if len(argv) != 2 or argv[0] not in ("--verifie", "--enregistre"):
        sys.stderr.write(__doc__.split("\n\n")[1] + "\n")
        return 2
    claude = os.path.abspath(argv[1])
    if not os.path.isdir(os.path.join(claude, "py")):
        sys.stderr.write("pas de py/ dans %s\n" % claude)
        return 2
    if argv[0] == "--enregistre":
        pin = enregistre(claude, RACINE, ENREGISTREMENT)
        print("épinglé : %d modules, %d fonctions" % (len(pin["modules"]),
                                                    sum(len(v) for v in pin["modules"].values())))
        return 0
    try:
        liste = ecarts(claude, RACINE, ENREGISTREMENT)
    except (RuntimeError, OSError) as e:
        sys.stderr.write("%s\n" % e)
        return 2
    for m, nom, etat in liste:
        print("%-14s %-34s %s" % (m, nom, etat))
    if liste:
        print("%d écart(s) : à porter ici, ou à écarter en réépinglant (--enregistre)." % len(liste))
        return 1
    print("rien à porter : le tronc commun est tel qu'épinglé.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
