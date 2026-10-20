# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/journal.rs` (4 tests)."""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

from _isole import Isole
import journal
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


class Equipe(Isole):
    """v3 · l'agent se tient dans `agents/<nom>/` (la mémoire) et enregistre son code
    par `git -C code commit` : le journal suit le COMMIT, au nom de l'agent."""

    def construis(self):
        import banc_equipe
        self.x = banc_equipe.construis(os.path.realpath(self.dossier("journal-equipe")))
        self.po = os.path.join(self.x, "agents", "PO")
        self.code = os.path.join(self.po, "code")
        with open(os.path.join(self.code, "apps", "app.ts"), "a") as h:
            h.write("// x\n")
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "commit", "-qam", "du code"], cwd=self.code, check=True)

    def joue(self, commande, depuis, declare):
        ici, avant = os.getcwd(), os.environ.get("COPILOT_PROJECT_DIR")
        os.chdir(depuis)
        os.environ["COPILOT_PROJECT_DIR"] = declare
        try:
            journal.main(json.dumps({"tool_input": {"command": commande}}))
        finally:
            os.chdir(ici)
            if avant is None:
                del os.environ["COPILOT_PROJECT_DIR"]
            else:
                os.environ["COPILOT_PROJECT_DIR"] = avant

    def test_le_journal_suit_le_commit_et_porte_le_nom_de_l_agent(self):
        self.construis()
        self.joue("git -C code commit -qam 'du code'", self.po, self.po)
        logs = os.path.join(self.code, journal.DOSSIER)
        noms = os.listdir(logs)
        self.assertEqual(len(noms), 1, noms)
        self.assertTrue(noms[0].endswith("-PO.md"), noms)
        with open(os.path.join(logs, noms[0]), encoding="utf-8") as h:
            self.assertIn("du code", h.read())
        # TÉMOIN : rien n'a été écrit dans la mémoire.
        self.assertFalse(os.path.exists(os.path.join(self.po, journal.DOSSIER)))
        self.assertFalse(os.path.exists(os.path.join(self.x, journal.DOSSIER)))

    def test_le_nom_vient_de_la_position_de_l_agent_pas_de_l_endroit_ou_git_tourne(self):
        """Un `cd code && git commit` : git tourne dans le code, l'agent est déclaré
        dans son dossier — le journal du code porte quand même son nom."""
        self.construis()
        self.joue("cd code && git commit -qam 'du code'", self.po, self.po)
        logs = os.path.join(self.code, journal.DOSSIER)
        noms = os.listdir(logs)
        self.assertEqual(len(noms), 1, noms)
        self.assertTrue(noms[0].endswith("-PO.md"), noms)

    def test_le_nom_d_agent_est_sain_pour_un_nom_de_fichier(self):
        self.assertEqual(journal._slug("Projet PO"), "-Projet-PO")
        self.assertEqual(journal._slug("a/b"), "-a-b")


if __name__ == "__main__":
    unittest.main()
