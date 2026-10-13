# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/mind_guard.rs` (5 tests)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from _isole import Isole
from mind_guard import (CHAMPS_REQUIS_FACT, NOMS_MIND, aujourd_hui, autorise, champ, entete,
                        est_du_code, noms_fact, verifie_state)


class Essais(Isole):

    def test_le_plafond_porte_sur_les_noms(self):
        """LE PLAFOND PORTE SUR LES NOMS, et il a deux mots distincts."""
        # Écart voulu : `workflow.md` est un cinquième fichier de faits en Python
        # (commun à tous les agents) ; le Rust n'en admet que quatre + roles.md.
        for n in ["base.md", "architecture.md", "stack.md", "rules.md", "roles.md", "workflow.md"]:
            self.assertIn(n, noms_fact(), "%s devrait être admis" % n)
        # CE QUE LE PLAFOND REFUSE — sinon on épingle une liste qui dit oui à tout.
        for n in ["extra.md", "notes.md", "base.txt", "Base.md"]:
            self.assertNotIn(n, noms_fact(), "%s devrait être refusé" % n)
        self.assertEqual(NOMS_MIND, ["state.md", "todo.md"])
        self.assertNotIn("belief.md", NOMS_MIND)

        # `fact-neuf` VAUT `fact-ok` — la hiérarchie, pas une clé partagée.
        # Sans elle la serrure ne s'ouvrirait jamais : `autorise()` ancre le mot
        # en FIN de commande, deux mots ne peuvent donc pas cohabiter.
        self.assertTrue(autorise("git commit -m x # fact-neuf", "fact-neuf"))
        self.assertFalse(autorise("git commit -m x # fact-ok", "fact-neuf"))
        # ET L'INVERSE RESTE FAUX : `fact-ok` n'autorise pas un 5ᵉ nom.
        self.assertFalse(autorise("git commit -m x # fact-neuf", "mind-neuf"))

    def test_l_echappatoire_se_lit_en_FIN_de_commande(self):
        self.assertTrue(autorise("git commit -m x # mind-ok", "mind-ok"))
        self.assertTrue(autorise("git commit -m x #fact-ok  ", "fact-ok"))
        self.assertTrue(autorise("git commit -m x # fact-ok\n", "fact-ok"))
        # LE DÉFAUT RÉPARÉ : une sous-chaîne n'importe où désarmait le garde.
        self.assertFalse(autorise("git checkout -b essai-fact-ok && git commit -m x", "fact-ok"))
        self.assertFalse(autorise("git commit -m 'répare fact-ok un jour'", "fact-ok"))
        self.assertFalse(autorise("git commit -m x", "mind-ok"))
        # UNE CLÉ, UNE SERRURE : `mind-ok` n'ouvre pas la serrure de `.fact/`.
        self.assertFalse(autorise("git commit -m x # mind-ok", "fact-ok"))

    def test_l_entete_se_lit_comme_le_tableau_de_bord(self):
        e = entete("---\nmaj: 2026-09-09\ncap: aller là   # un commentaire\n---\n\ntexte")
        self.assertEqual(champ(e, "maj"), "2026-09-09")
        self.assertEqual(champ(e, "cap"), "aller là")
        # TÉMOINS NÉGATIFS : pas d'en-tête, en-tête non fermé, texte nu.
        self.assertEqual(entete("texte sans en-tête"), [])
        self.assertEqual(entete("---\nmaj: x\n"), [])
        self.assertEqual(entete(""), [])

    def test_le_state_est_juge_sur_sa_structure_puis_sa_fraicheur(self):
        ok = "---\nmaj: %s\nsante: verte\njalon: x\n---\n" % aujourd_hui()
        self.assertEqual(verifie_state(ok, CHAMPS_REQUIS_FACT), [])
        # structure : sans en-tête, le projet DISPARAÎT du tableau de bord
        m = verifie_state("rien", CHAMPS_REQUIS_FACT)
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0][0], "structure")
        # structure : champ manquant
        m = verifie_state("---\nmaj: %s\n---\n" % aujourd_hui(), CHAMPS_REQUIS_FACT)
        self.assertTrue(any(k == "structure" and "`sante:`" in v for k, v in m))
        # structure : date qui n'est pas une date
        m = verifie_state("---\nmaj: hier\nsante: v\njalon: x\n---\n", CHAMPS_REQUIS_FACT)
        self.assertTrue(any(k == "structure" and "« hier »" in v for k, v in m))
        # fraîcheur : date valide mais pas celle du jour
        m = verifie_state("---\nmaj: 2020-01-01\nsante: v\njalon: x\n---\n", CHAMPS_REQUIS_FACT)
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0][0], "fraicheur")

    def test_le_harnais_de_l_agent_n_est_pas_du_code_projet(self):
        self.assertTrue(est_du_code("src/a.ts", "", ""))
        self.assertTrue(est_du_code("truc.py", "", ""))
        self.assertTrue(est_du_code("agents/ios/src/a.ts", "agents/ios/", ""))
        # LES DEUX JEUX DE PRÉFIXES, et c'est le défaut que ça répare :
        self.assertFalse(est_du_code("agents/ios/.github/copilot/garde.py", "agents/ios/", ""))
        self.assertFalse(est_du_code(".fact/base.md", "", ""))
        self.assertFalse(est_du_code("docs/decisions.md", "", ""))
        self.assertFalse(est_du_code(".logs/2026-09-09.md", "", ""))
        self.assertFalse(est_du_code("site/index.html", "", ""), "rendu généré")
        self.assertTrue(est_du_code("site/_content/a.py", "", ""), "mais son contenu, si")
        self.assertFalse(est_du_code("LISEZMOI.md", "", ""))
        # Ce que produit un agent n'est pas du code projet, quel que soit son format…
        # Écart voulu : le dossier des livrables est `assets/` (agent.BANC) ; `outputs/`
        # et `brain/workbench/` restent reconnus comme anciens noms (assertions du Rust).
        self.assertFalse(est_du_code("assets/OPS/requete.sql", "", ""))
        self.assertFalse(est_du_code("assets/PO/analyse.ipynb", "", ""))
        self.assertFalse(est_du_code("outputs/OPS/requete.sql", "", ""), "ancien nom, toujours lu")
        self.assertFalse(est_du_code("outputs/PO/analyse.ipynb", "", ""), "ancien nom, toujours lu")
        # …mais le même fichier hors du banc, si.
        self.assertTrue(est_du_code("src/requete.sql", "", ""))
        self.assertFalse(est_du_code("brain/workbench/OPS/requete.sql", "", ""),
                         "l'ancien établi reste lu")
        self.assertTrue(est_du_code("brain/requete.sql", "", ""),
                        "le reste de brain/ n'est pas exempté")


if __name__ == "__main__":
    unittest.main()
