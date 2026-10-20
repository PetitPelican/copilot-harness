# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/nature.rs` (6 tests)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from _isole import Isole
from nature import (DEMENTI, ECHEC_DECLARE, GARDE, PEREMPTION_FAIT_J, REUSSITE, Maison, Nature,
                    Origine, de, depart, duree)


class Essais(Isole):

    def test_une_supposition_est_une_croyance_ou_qu_elle_soit_posee(self):
        for m in [Maison.Faits, Maison.Carnet]:
            self.assertEqual(de(m, "supposé", None), (Nature.Croyance, Origine.Supposition))
            self.assertEqual(de(m, "suppose", None)[0], Nature.Croyance, "sans accent aussi")
            # On ne sort pas de la pente rapide par une étiquette.
            self.assertEqual(de(m, "supposé", "fait")[0], Nature.Croyance)

    def test_la_maison_decide_quand_l_entree_ne_dit_rien(self):
        self.assertEqual(de(Maison.Faits, "mesuré", None), (Nature.Fait, Origine.Maison))
        self.assertEqual(de(Maison.Faits, None, None), (Nature.Fait, Origine.Maison))
        self.assertEqual(de(Maison.Carnet, "observé", None), (Nature.Experience, Origine.Maison))
        # TÉMOIN : une fonction qui rendrait « fait » à tout passerait les deux premiers cas.
        self.assertNotEqual(de(Maison.Carnet, None, None)[0], de(Maison.Faits, None, None)[0])

    def test_une_declaration_contredit_sa_maison_et_un_mot_inconnu_ne_vaut_rien(self):
        self.assertEqual(de(Maison.Faits, "mesuré", "croyance"), (Nature.Croyance, Origine.Declaree))
        self.assertEqual(de(Maison.Carnet, None, "fait")[0], Nature.Fait)
        self.assertEqual(de(Maison.Faits, None, "Expérience")[0], Nature.Experience)
        self.assertEqual(de(Maison.Faits, None, "belief")[0], Nature.Croyance, "le mot anglais")
        self.assertEqual(de(Maison.Carnet, None, "peut-être"), (Nature.Experience, Origine.Maison))

    def test_les_pentes_suivent_les_natures(self):
        f = duree(Nature.Fait, PEREMPTION_FAIT_J)
        self.assertEqual(f, 28.0, "la loi des quatre semaines")
        self.assertEqual(duree(Nature.Croyance, PEREMPTION_FAIT_J), f / 2.0)
        self.assertEqual(duree(Nature.Experience, PEREMPTION_FAIT_J), f * 1.5)

    def test_le_depart_reunit_les_deux_copies_sans_changer_leurs_valeurs(self):
        for m in [Maison.Faits, Maison.Carnet]:
            self.assertEqual(depart("mesuré", m), 80)
            self.assertEqual(depart("mesure", m), 80)
            self.assertEqual(depart("observé", m), 60)
            self.assertEqual(depart("supposé", m), 40)
            self.assertEqual(depart("dit", m), 85)
        # Le seul endroit où les deux copies divergeaient À DESSEIN : l'inconnu.
        self.assertEqual(depart("", Maison.Faits), 50)
        self.assertEqual(depart("", Maison.Carnet), 60)

    def test_la_confiance_se_perd_plus_vite_qu_elle_ne_se_gagne(self):
        for e in [GARDE, DEMENTI, ECHEC_DECLARE]:
            self.assertTrue(e < 1.0 and REUSSITE > 1.0)
        # La garde est l'échec le plus doux : un rappel de forme n'est pas un démenti.
        self.assertTrue(GARDE > DEMENTI > ECHEC_DECLARE)
        # « Un échec grave coûte cinq réussites. »
        self.assertTrue(ECHEC_DECLARE * REUSSITE ** 5 < 1.0)


if __name__ == "__main__":
    unittest.main()
