# -*- coding: utf-8 -*-
"""Le contrôle du tronc commun : il voit ce que Claude a changé, et seulement cela."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "outils"))

import tronc_commun as t  # noqa: E402


def pose(dossier, **modules):
    os.makedirs(os.path.join(dossier, "py"), exist_ok=True)
    for nom, source in modules.items():
        with open(os.path.join(dossier, "py", nom + ".py"), "w", encoding="utf-8") as f:
            f.write(source)


BASE = '''
LIMITE = 3

def a(x):
    """Une doc."""
    return x + 1

class C:
    def m(self):
        return LIMITE
'''


class Essais(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.claude = os.path.join(self.tmp.name, "claude")
        self.ici = os.path.join(self.tmp.name, "ici")
        self.pin = os.path.join(self.tmp.name, "pin.json")
        pose(self.claude, mod=BASE, seul_claude="x = 1\n")
        pose(self.ici, mod=BASE.replace("x + 1", "x + 2"), seul_ici="y = 1\n")
        t.enregistre(self.claude, self.ici, self.pin)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rien_n_a_bouge(self):
        self.assertEqual(t.ecarts(self.claude, self.ici, self.pin), [])

    def test_seul_ce_que_claude_a_change_se_voit_pas_nos_divergences(self):
        # Ici diverge déjà (`x + 2`) : ce n'est pas un écart, c'est une décision.
        pose(self.claude, mod=BASE.replace("LIMITE = 3", "LIMITE = 4"))
        self.assertEqual(t.ecarts(self.claude, self.ici, self.pin),
                         [("mod", "LIMITE", "changé chez Claude")])

    def test_une_fonction_changee_nouvelle_ou_retiree(self):
        pose(self.claude, mod=BASE.replace("x + 1", "x + 9") + "\ndef n():\n    return 1\n")
        e = t.ecarts(self.claude, self.ici, self.pin)
        self.assertIn(("mod", "a", "changé chez Claude"), e)
        self.assertIn(("mod", "n", "nouveau chez Claude"), e)
        pose(self.claude, mod="LIMITE = 3\n")
        e = t.ecarts(self.claude, self.ici, self.pin)
        self.assertIn(("mod", "C", "retiré chez Claude"), e)

    def test_ni_doc_ni_commentaire_ni_deplacement_ne_comptent(self):
        pose(self.claude, mod='''
class C:
    # un commentaire
    def m(self):
        """Doc ajoutée."""
        return LIMITE

def a(x):
    return x + 1


LIMITE = 3
''')
        self.assertEqual(t.ecarts(self.claude, self.ici, self.pin), [])

    def test_un_module_qui_n_est_pas_commun_n_est_pas_suivi(self):
        pose(self.claude, seul_claude="x = 2\n")
        self.assertEqual(t.ecarts(self.claude, self.ici, self.pin), [])

    def test_le_code_de_sortie_dit_la_derive(self):
        avant = (t.ENREGISTREMENT, t.RACINE)
        t.ENREGISTREMENT, t.RACINE = self.pin, self.ici
        try:
            self.assertEqual(t.main(["--verifie", self.claude]), 0)
            pose(self.claude, mod=BASE.replace("x + 1", "x + 9"))
            self.assertEqual(t.main(["--verifie", self.claude]), 1)
            # Un épinglage absent n'est pas « rien à porter » : c'est « pas mesuré ».
            os.remove(self.pin)
            self.assertEqual(t.main(["--verifie", self.claude]), 2)
        finally:
            t.ENREGISTREMENT, t.RACINE = avant


if __name__ == "__main__":
    unittest.main()
