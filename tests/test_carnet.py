# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/carnet.rs` (7 tests)."""
import datetime
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from _isole import Isole, ecris
from carnet import (arrondi0, arrondi1, chiffre, confiances, ecrire_etat, empreinte, entrees,
                    lecture, nb, oubli, resume, slug, vise)


class Essais(Isole):

    def test_l_arrondi_est_celui_de_python_au_pair(self):
        # PIÈGE SILENCIEUX : l'arrondi « au supérieur » ferait 0,5 -> 1.
        self.assertEqual(arrondi0(0.5), 0)
        self.assertEqual(arrondi0(1.5), 2)
        self.assertEqual(arrondi0(2.5), 2)
        self.assertEqual(arrondi1(82.35), 82.3)
        self.assertEqual(arrondi1(80.0 * 1.03), 82.4)

    def test_la_visee_atteint_le_nom_court_et_le_long(self):
        self.assertTrue(vise("PO", "Projet PO"))
        self.assertTrue(vise("Projet PO", "Projet PO"))
        self.assertTrue(vise("tous", "n'importe qui"))
        self.assertTrue(vise("équipe", "Projet QA"), "sans accents, dans les deux sens")
        # TÉMOINS NÉGATIFS : une visée qui rate ne doit RIEN servir.
        self.assertFalse(vise("OPS", "Projet PO"))
        self.assertFalse(vise("", "Projet PO"))
        self.assertFalse(vise("PO", ""))

    def test_le_chiffre_se_tait_avant_deux_mouvements(self):
        c = {}
        c["x"] = {"n": 82.4, "m": 1}
        self.assertIsNone(chiffre(c, "x"), "un seul mouvement : c'est le niveau déguisé")
        c["y"] = {"n": 82.4, "m": 2}
        self.assertEqual(chiffre(c, "y"), 82)
        self.assertIsNone(chiffre(c, "absent"))

    def carnet_essai(self, nom, entrees_):
        """Fabrique un carnet : une entrée par (auteur, texte, visée)."""
        esp = tempfile.mkdtemp(prefix="harnais-carnet-%s-" % nom)
        self.addCleanup(shutil.rmtree, esp, True)
        jour = datetime.date.today().strftime("%Y-%m-%d")
        for i, (auteur, texte, pour) in enumerate(entrees_):
            v = "\n↗ %s : %s" % (pour, texte) if pour is not None else ""
            ecris(os.path.join(esp, "%s-%d.md" % (jour, i)),
                  "## %s 10:0%d · %s · réussi · mesuré\n%s%s\n" % (jour, i, auteur, texte, v))
        return esp

    def test_la_ligne_qui_te_vise_porte_son_empreinte_et_les_autres_non(self):
        """LE SEUL GESTE SOCIAL DU CARNET. La ligne qui demande d'acquitter porte
        l'empreinte ; celle qui ne le demande pas ne la porte pas."""
        esp = self.carnet_essai("vise", [
            ("Projet PO", "la base change de forme", "QA"),
            ("Projet OPS", "le socle a bougé", None),
        ])
        lignes, servis = resume(esp, "Projet QA", 48, 8)
        pour_toi = [l for l in lignes if "POUR TOI" in l]
        self.assertEqual(len(pour_toi), 1, lignes)
        id_ = servis[0] if servis else ""
        self.assertTrue(id_ != "" and ("↩ %s" % id_) in pour_toi[0],
                        "l'empreinte demandée doit être dans la ligne : %r" % (lignes,))
        # TÉMOIN NÉGATIF : l'entrée qui ne vise personne n'en porte pas —
        # sinon « porte une empreinte » ne dirait rien de la visée.
        autres = [l for l in lignes if "POUR TOI" not in l]
        self.assertTrue(len(autres) > 0 and all("↩ " not in l for l in autres), lignes)
        # Et l'empreinte servie est bien celle que le fichier porte : un agent
        # qui la recopie acquitte VRAIMENT cette entrée.
        e = next(e for e in entrees(esp, None) if e.auteur == "Projet PO")
        self.assertEqual(id_, e.id)

    def test_l_instrument_distingue_le_dossier_absent_du_carnet_vide(self):
        """« Absent » et « vide » appellent deux gestes opposés."""
        nulle_part = os.path.join(tempfile.gettempdir(), "harnais-carnet-nulle-part-xyz")
        shutil.rmtree(nulle_part, True)
        v, code = lecture(nulle_part, "X")
        self.assertEqual(code, 2)
        self.assertIn("n'existe pas", v.get("raison") or "", v)

        esp = self.carnet_essai("vide", [])
        v, code = lecture(esp, "X")
        self.assertEqual(code, 0, "un carnet vide n'est pas une erreur")
        self.assertIs(v.get("vide"), True)
        self.assertIsNone(v.get("raison"), "vide n'est pas absent : %r" % (v,))

        # TÉMOIN : un carnet qui porte une entrée ne dit ni l'un ni l'autre.
        esp2 = self.carnet_essai("plein", [("Projet PO", "quelque chose", None)])
        v, code = lecture(esp2, "Projet QA")
        self.assertEqual(code, 0)
        self.assertTrue(v.get("vide") is None and v.get("raison") is None, v)

    def test_l_oubli_suit_la_nature_de_part_et_d_autre_de_chaque_seuil(self):
        esp = os.path.join(tempfile.gettempdir(), "harnais-carnet-oubli-nature-%d" % os.getpid())
        shutil.rmtree(esp, True)
        self.addCleanup(shutil.rmtree, esp, True)
        os.makedirs(os.path.join(esp, ".etat"))

        def il_y_a(n):
            return (datetime.date.today() - datetime.timedelta(days=n)).strftime("%Y-%m-%d")

        d = {}
        for id_, niv, j in [("cro-14", "supposé", 14), ("cro-16", "supposé", 16),
                            ("exp-31", "observé", 31), ("exp-44", "mesuré", 44),
                            ("exp-46", "mesuré", 46)]:
            d[id_] = {"n": 50, "m": 0, "niveau": niv, "vu": il_y_a(j)}
        ecrire_etat(esp, d)
        oubli(esp, 30)
        c = confiances(esp)

        def n(id_):
            return nb(c[id_]["n"])

        # Une CROYANCE attend 15 j : à 14 elle tient, à 16 elle descend d'un cran.
        self.assertEqual(n("cro-14"), 50.0)
        self.assertEqual(n("cro-16"), 48.5)
        # Une EXPÉRIENCE attend 45 j — et à 31 elle tient, là où la règle plate
        # d'avant l'aurait fait descendre. C'est le témoin du changement.
        self.assertEqual(n("exp-31"), 50.0)
        self.assertEqual(n("exp-44"), 50.0)
        self.assertEqual(n("exp-46"), 48.5)

    def test_le_slug_et_l_empreinte_ne_bougent_pas(self):
        self.assertEqual(slug("Projet PO"), "Projet-PO")
        self.assertEqual(slug(""), "agent")
        # L'empreinte est le lien entre l'entrée et sa confiance : si elle
        # change, la confiance devient introuvable EN SILENCE.
        self.assertEqual(len(empreinte("2026-09-09", "10:00", "CTO", "un texte")), 12)
        self.assertNotEqual(empreinte("2026-09-09", "10:00", "CTO", "un texte"),
                            empreinte("2026-09-09", "10:00", "CTO", "un AUTRE texte"))


if __name__ == "__main__":
    unittest.main()
