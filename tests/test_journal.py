# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/journal.rs` (4 tests)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from _isole import Isole
from journal import bloc, deja_journalise, est_un_commit, suffixe_agent


class Essais(Isole):

    def test_ne_reagit_qu_a_un_commit(self):
        self.assertTrue(est_un_commit("git commit -m x"))
        self.assertTrue(est_un_commit("cd /tmp && git -c user.name=x commit -q -F -"))
        # TÉMOINS NÉGATIFS : tout le reste doit passer sans rien écrire.
        self.assertFalse(est_un_commit("git status"))
        self.assertFalse(est_un_commit("git push"))
        self.assertFalse(est_un_commit("commit"))
        self.assertFalse(est_un_commit(""))
        # ET SES FAUX POSITIFS, partagés avec la version Python d'origine : le garde
        # suivant regarde HEAD, donc rien n'est écrit. Les interdire ferait diverger.
        self.assertTrue(est_un_commit("echo git et commit"), "faux positif partagé avec Python")
        self.assertTrue(est_un_commit("git log --format=%s | grep commit"))

    def test_l_empreinte_ferme_les_doublons(self):
        self.assertTrue(deja_journalise("## 10:00 · `abc1234` · main", "abc1234"))
        self.assertFalse(deja_journalise("## 10:00 · `abc1234` · main", "abc12"),
                         "un préfixe n'est PAS l'empreinte — sinon un commit en masquerait un autre")
        self.assertFalse(deja_journalise("", "abc1234"))
        self.assertFalse(deja_journalise("abc", "abc1234"), "journal plus court que l'empreinte")

    def test_le_suffixe_ne_bouge_qu_en_multi_agents(self):
        r = "/tmp/projet"
        self.assertEqual(suffixe_agent(r, None), "")
        self.assertEqual(suffixe_agent(r, "/tmp/projet"), "",
                         "mono-agent : le nom de fichier ne change pas")
        self.assertEqual(suffixe_agent(r, "/tmp/projet/agents/Projet PO"), "-Projet-PO")
        self.assertEqual(suffixe_agent(r, "/tmp/projet/brain/mind/Projet PO"), "-Projet-PO")
        self.assertEqual(suffixe_agent(r, "/tmp/projet/autre/chose"), "")
        self.assertEqual(suffixe_agent(r, "/ailleurs"), "")

    def test_le_bloc_a_la_forme_attendue(self):
        f = ["f%d.rs" % i for i in range(45)]
        b = bloc("10:30", "abc1234", "main", True, "Un sujet", f, "alice")
        self.assertIn("## 10:30 · `abc1234` · main · réécriture (`--amend`)", b)
        self.assertIn("**Un sujet**", b)
        self.assertIn("- … et 5 autres fichiers", b, "le plafond de 40 mord")
        self.assertTrue(b.endswith("<!-- alice -->"))
        court = bloc("10:30", "abc1234", "main", False, "S", f[:2], "M")
        self.assertNotIn("réécriture", court)
        self.assertNotIn("autres fichiers", court)


if __name__ == "__main__":
    unittest.main()
