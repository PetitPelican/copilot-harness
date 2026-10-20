# -*- coding: utf-8 -*-
"""Une question déjà posée ne se repose pas (décision du 14/10/2026, chez Claude :
« pourquoi tu me poses 4 fois la même question ?? »). Le briefing, servi avant
chaque message — ceux d'un pair compris — lit le registre de la garde de fin de
tour. Porté de Claude 0.19."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from _isole import Isole  # noqa: E402
import attente  # noqa: E402
import briefing  # noqa: E402

TODO = """# Ce qui attend

- [ ] !haut @user **Je relance les trois agents ? 1 oui / 2 non**
      1 → je relance.
      2 → rien.
      fini quand → ils répondent.
- [ ] !moyen @user **Je publie la version ? 1 oui / 2 non**
      1 → je publie.
      2 → j'attends.
      fini quand → la version est servie.
"""


class Posees(Isole):

    def setUp(self):
        Isole.setUp(self)
        os.environ["ATTENTE_DESTINATAIRES"] = "user"
        self.addCleanup(os.environ.pop, "ATTENTE_DESTINATAIRES", None)
        os.makedirs(os.path.join(os.environ["COPILOT_PLUGIN_DATA"], "attente"))
        for cible, val in (("racine_de", lambda ici: ("/x/Agent", None)), ("nom_agent", lambda r: "Agent")):
            m = mock.patch.object(attente, cible, val)
            m.start()
            self.addCleanup(m.stop)

    def inscrit(self, *titres):
        with open(attente.registre_posees("Agent"), "w", encoding="utf-8") as h:
            h.write("\n".join(attente.sha16(t) for t in titres))

    def test_rien_de_pose_demande_de_poser_une_fois(self):
        ligne = briefing.ligne_posees(TODO, "/x")
        self.assertIn("pose-la UNE fois", ligne)

    def test_tout_pose_interdit_de_reposer(self):
        titres = [q.titre for q in attente.questions_ouvertes(TODO)]
        self.assertEqual(len(titres), 2)
        self.inscrit(*titres)
        ligne = briefing.ligne_posees(TODO, "/x")
        self.assertIn("Ne les repose PAS", ligne)
        self.assertNotIn("avant tout le reste", ligne)

    def test_une_neuve_une_vue(self):
        """TÉMOIN : la neuve reste à poser — un briefing qui tairait tout passerait
        les deux autres essais."""
        self.inscrit(attente.questions_ouvertes(TODO)[0].titre)
        ligne = briefing.ligne_posees(TODO, "/x")
        self.assertIn("1 nouvelle(s) à poser une fois", ligne)
        self.assertIn("1 autre(s) sont déjà posées", ligne)

    def test_meme_titre_que_la_garde(self):
        """Le registre est écrit par la garde avec SES titres : le briefing doit
        lire les mêmes, sinon une question posée passerait pour neuve."""
        self.assertEqual(attente.questions_ouvertes(TODO)[0].titre,
                         "Je relance les trois agents ? 1 oui / 2 non")

    def test_une_question_pour_un_pair_n_est_pas_une_question_pour_l_humain(self):
        """TÉMOIN : le registre ne retient que les demandes au commanditaire."""
        todo = TODO + "- [ ] !bas @QA **Je garde la page des prix ? 1 oui / 2 non**\n"
        self.assertEqual(len(attente.questions_ouvertes(todo)), 2)

    def test_le_registre_de_la_garde_est_celui_du_briefing(self):
        """La garde écrit `registre_posees(agent)` ; le briefing le lit par la même
        fonction — pas de second chemin qui dériverait."""
        self.inscrit(attente.questions_ouvertes(TODO)[0].titre)
        self.assertEqual([p for _, p in attente.deja_posees(TODO, "Agent")], [True, False])
        self.assertEqual([p for _, p in attente.deja_posees(TODO, "Autre")], [False, False],
                         "le registre est par agent")


if __name__ == "__main__":
    unittest.main()
