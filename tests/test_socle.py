# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/socle.rs` (2 tests)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from _isole import Isole
from socle import chemin_affiche, chemin_etat


class Essais(Isole):

    def test_le_chemin_annonce_s_ouvre_depuis_ou_on_travaille(self):
        """Les deux sens : relatif sous le dossier de travail, absolu en dehors."""
        ici = "/d/projet/agents/Un Agent"
        # sous le dossier de travail -> relatif
        self.assertEqual(chemin_affiche(ici, ici + "/brain/fact/base.md"), "brain/fact/base.md")
        # en dehors (mémoire déportée) -> absolu, jamais un relatif inventé
        dehors = "/d/projet/memoire/.fact/base.md"
        rendu = chemin_affiche(ici, dehors)
        self.assertEqual(rendu, "/d/projet/memoire/.fact/base.md")
        self.assertNotEqual(rendu, ".fact/base.md", "rend un relatif qui ne s'ouvre pas d'ici")
        # un nom d'agent à espace ne casse rien
        self.assertEqual(chemin_affiche("/d/Projet PO", "/d/Projet PO/x.md"), "x.md")

    def test_les_hooks_et_les_commandes_resolvent_le_meme_etat_copilot_sans_le_creer(self):
        base = os.path.join(tempfile.gettempdir(), "etat-copilot-%d" % os.getpid())
        attendu = os.path.join(base, "plugin-data/atelier-copilot/harnais")
        self.assertEqual(chemin_etat(None, base), attendu)
        self.assertFalse(os.path.exists(attendu), "la simple résolution ne crée rien")
        donnees = os.path.join(base, "donnees-plugin")
        self.assertEqual(chemin_etat(donnees, base), donnees)


if __name__ == "__main__":
    unittest.main()
