# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/poids.rs` (5 tests)."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

import nature
from poids import (fichiers_dans_commande, inscris, ligne_briefing, lis_json, lues, resultat,
                   retiens, sections)

STACK = ("# Stack\n\n## Le langage\n> **mesuré** · 01/10/2026 — `python --version`\nPython 3.14.\n\n"
         "## Le port\n> **dit** · 01/10/2026 — donné à l'oral\nLe service écoute sur 8080.\n")


class Essais(unittest.TestCase):

    def banc(self, nom):
        d = tempfile.mkdtemp(prefix="harnais-poids-%s-" % nom)
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "brain/fact"))
        with open(os.path.join(d, "brain/fact/stack.md"), "w", encoding="utf-8") as f:
            f.write(STACK)
        return (os.path.join(d, "brain/poids.json"), os.path.join(d, "brain/fact"), os.path.join(d, "etat"))

    def test_une_plage_ne_credite_que_les_sections_qu_elle_touche(self):
        self.assertEqual(list(sections(STACK)), [("Le langage", 3, 6), ("Le port", 7, 9)])
        # La lecture partielle mesurée sur Copilot : view_range [7, 9].
        self.assertEqual(lues("stack.md", STACK, (7, 9)), ["stack.md › Le port"])
        self.assertEqual(len(lues("stack.md", STACK, (1, -1))), 2, "-1 = jusqu'à la fin")
        self.assertEqual(len(lues("stack.md", STACK, None)), 2, "sans plage, tout le fichier")
        # TÉMOIN : une plage avant la première section ne crédite rien.
        self.assertEqual(lues("stack.md", STACK, (1, 2)), [])

    def test_la_commande_shell_qui_lit_compte_celle_qui_ecrit_non(self):
        self.assertEqual(fichiers_dans_commande("Get-Content brain/fact/stack.md"), ["brain/fact/stack.md"])
        self.assertEqual(fichiers_dans_commande(r"type C:\p\brain\fact\rules.md"), [r"C:\p\brain\fact\rules.md"])
        self.assertEqual(fichiers_dans_commande("echo x > brain/fact/stack.md"), [])
        self.assertEqual(fichiers_dans_commande("Set-Content brain/fact/stack.md 'x'"), [])
        self.assertEqual(fichiers_dans_commande("cat brain/fact/notes.md"), [], "pas un fichier de faits")

    def test_une_section_part_de_son_niveau_et_une_journee_ne_compte_qu_une_fois(self):
        poids, fact, _ = self.banc("depart")
        self.assertTrue(inscris(poids, fact, ["stack.md › Le port", "stack.md › Le langage"]))
        self.assertFalse(inscris(poids, fact, ["stack.md › Le port"]), "même jour : rien ne bouge")
        p = lis_json(poids)
        self.assertEqual(p["sections"]["stack.md › Le port"]["conf"], 85, "dit → 85")
        self.assertEqual(p["sections"]["stack.md › Le langage"]["conf"], 80, "mesuré → 80")
        self.assertEqual(p["sections"]["stack.md › Le port"]["jours_lus"], 1)

    def test_le_resultat_ne_touche_que_ce_qui_a_ete_lu_puis_le_registre_se_vide(self):
        poids, fact, etat = self.banc("resultat")
        inscris(poids, fact, ["stack.md › Le port", "stack.md › Le langage"])
        retiens(etat, "S1", poids, ["stack.md › Le port"])
        self.assertEqual(resultat(etat, "S1", nature.DEMENTI), 1)
        p = lis_json(poids)
        self.assertEqual(p["sections"]["stack.md › Le port"]["conf"], 76.5, "85 × 0,90")
        self.assertEqual(p["sections"]["stack.md › Le langage"]["conf"], 80, "TÉMOIN : non lue, intacte")
        self.assertEqual(resultat(etat, "S1", nature.DEMENTI), 0, "le registre a été vidé")
        # Une autre session n'est pas touchée par le verdict de la première.
        retiens(etat, "S2", poids, ["stack.md › Le langage"])
        self.assertEqual(resultat(etat, "S1", nature.DEMENTI), 0)

    def test_le_briefing_ne_dit_rien_tant_que_tout_va_bien(self):
        poids, fact, etat = self.banc("briefing")
        inscris(poids, fact, ["stack.md › Le port"])
        self.assertIsNone(ligne_briefing(poids, fact))
        for _ in range(5):
            retiens(etat, "S", poids, ["stack.md › Le port"])
            resultat(etat, "S", nature.ECHEC_DECLARE)
        l = ligne_briefing(poids, fact)
        self.assertIsNotNone(l, "une section démentie se signale")
        self.assertTrue("stack.md › Le port" in l and "peu sûre" in l, l)


if __name__ == "__main__":
    unittest.main()
