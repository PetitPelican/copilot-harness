# -*- coding: utf-8 -*-
"""Le carnet des rechutes que la garde SERT : les titres, jamais le détail.

Porté de Claude 0.19. Mesuré chez Claude le 14/10/2026 : la partie lue du carnet
avait gonflé à 855 lignes de récidives. Écart Copilot : le carnet que les agents
écrivent et celui qui est servi sont le MÊME fichier (le dossier d'état), il n'y a
donc pas à tester le défaut de chemin de Claude — seulement qu'il le reste.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from _isole import Isole, ecris  # noqa: E402
import attente  # noqa: E402

CARNET = """# Avant d'affirmer

## Partout

- **Ton instrument a-t-il répondu à LA question posée ?** Long détail
  sur plusieurs lignes, récidives datées, qu'on ne sert pas.
- **Une question écrite par un agent, sur
  deux lignes ?** Son détail.

%s

- **Ajoutée en fin de fichier, sous la ligne d'écriture ?** jamais relue.
""" % attente.SEP_RECHUTES


class Rechutes(Isole):

    def setUp(self):
        Isole.setUp(self)
        self.fichier = attente.rechutes_f()
        self.livre = os.path.join(os.environ["COPILOT_PLUGIN_ROOT"], "rechutes.md")

    def test_le_carnet_ecrit_est_celui_qui_est_servi(self):
        """La lecture et l'écriture n'ont qu'un chemin : le dossier d'état."""
        self.assertEqual(os.path.dirname(self.fichier), os.environ["COPILOT_PLUGIN_DATA"])
        ecris(self.fichier, CARNET)
        r = attente.rechutes()
        self.assertIn("Une question écrite par un agent, sur deux lignes ?", r)

    def test_seuls_les_titres_sont_servis(self):
        ecris(self.fichier, CARNET)
        r = attente.rechutes()
        self.assertIn("- Ton instrument a-t-il répondu à LA question posée ?", r)
        self.assertIn("## Partout", r)
        self.assertNotIn("récidives datées", r)
        self.assertNotIn("Son détail", r)
        self.assertIn(self.fichier, r, "le détail est nommé")

    def test_temoin_sous_la_ligne_d_ecriture_rien_n_est_servi(self):
        """TÉMOIN : une garde qui servirait tout le fichier passerait les autres essais."""
        ecris(self.fichier, CARNET)
        self.assertNotIn("Ajoutée en fin de fichier", attente.rechutes())

    def test_sans_carnet_la_copie_livree_est_resservie_en_titres(self):
        self.assertFalse(os.path.exists(self.fichier))
        r = attente.rechutes()
        self.assertIn("# Avant d'affirmer", r)
        self.assertIn("Le détail de chaque question", r)
        self.assertIn(self.livre, r)

    def test_plafond(self):
        ecris(self.fichier, "\n".join("- **Question %d ?** x" % i for i in range(200)))
        r = attente.rechutes()
        self.assertLessEqual(len(r.splitlines()), attente.RECHUTES_LIGNES_MAX + 3)
        self.assertIn("ligne(s) de plus", r)

    def test_carnet_sans_la_forme_servi_tronque_jamais_vide(self):
        """Un carnet sans `- **titre**` n'est pas avalé : il est servi tel quel."""
        ecris(self.fichier, "une règle écrite en prose\nune autre\n")
        self.assertIn("une règle écrite en prose", attente.rechutes())

    def test_carnet_vide_ne_sert_rien(self):
        ecris(self.fichier, "   \n")
        self.assertEqual(attente.rechutes(), "")


if __name__ == "__main__":
    unittest.main()
