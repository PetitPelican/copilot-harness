# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/atelier.rs` (3 tests)."""
import contextlib
import io
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from _isole import Isole, ecris, lis
from atelier import REGISTRE, RegistreInvalide, _gabarit, accueil, main


def _main(args):
    """`main` écrit sur stdout/stderr : on les rend muets, comme `cargo test` les capture."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return main(args)


class Essais(Isole):

    def bac(self, nom):
        """Le `bac` du Rust : un chemin qui n'existe pas encore."""
        d = os.path.join(self.dossier(nom), "atelier-%s" % nom)
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def test_a_blanc_rien_ne_s_ecrit(self):
        d = self.bac("blanc")
        _main(["--racine", d])
        self.assertFalse(os.path.exists(d), "à blanc, pas même la racine")

    def test_ecrit_puis_n_ecrase_rien(self):
        d = self.bac("ecrit")
        _main(["--racine", d, "--utilisateur", "alice", "--go"])
        socle = lis(os.path.join(d, "AGENTS.md"))
        role = lis(os.path.join(d, "cto/AGENTS.md"))
        self.assertEqual(socle, _gabarit("foundation-AGENTS.md").replace("[UTILISATEUR]", "alice"))
        self.assertIn("`@user` désigne alice", socle, "la méthode nomme @user")
        self.assertTrue("alice" in role and "[UTILISATEUR]" not in role)
        # LE RÔLE DIT OÙ SONT LES CHOSES : la racine en absolu, le paquet, et
        # aucun gabarit laissé brut.
        self.assertIn("Racine de l'atelier : `%s`" % d, role, role)
        self.assertTrue("[RACINE]" not in role and "[PAQUET]" not in role)
        self.assertTrue(os.path.isfile(os.path.join(d, "cto/brain/fact/base.md")),
                        "le harnais est posé par adopte")
        self.assertTrue(os.path.exists(os.path.join(d, "cto/.git")), "et son dépôt")
        # relancer ne change rien
        ecris(os.path.join(d, "AGENTS.md"), "à moi")
        _main(["--racine", d, "--go"])
        self.assertEqual(lis(os.path.join(d, "AGENTS.md")), "à moi")

    def test_accueil_seulement_pour_un_cto_sans_projet_declare(self):
        d = self.bac("accueil")
        self.assertIsNone(accueil(d))
        os.makedirs(os.path.join(d, "docs"))
        fichier = os.path.join(d, *REGISTRE.split("/"))
        ecris(fichier, '{"schema":1,"projects":[]}')
        self.assertIn("ACCUEIL CTO", accueil(d))
        ecris(fichier, '{"schema":1,"projects":[{"name":"Test","path":"../Test","profiles":["PO"]}]}')
        self.assertIsNone(accueil(d))
        ecris(fichier, '{"schema":1,"projects":[{}]}')
        with self.assertRaises(RegistreInvalide):
            accueil(d)
        ecris(fichier, "cassé")
        with self.assertRaises(RegistreInvalide):
            accueil(d)


if __name__ == "__main__":
    unittest.main()
