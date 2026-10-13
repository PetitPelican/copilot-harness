# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/adopte.rs` (12 tests).

Écarts voulus avec le Rust : `outputs/` devient `assets/` (`agent.BANC`), et le fait
commun `workflow.md` (la seule addition du port) est posé et compté.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

import adopte
import agent
import briefing
import copilot
import memoire
import socle

RACINE_PAQUET = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _env():
    e = dict(os.environ)
    e.update({"GIT_CONFIG_NOSYSTEM": "1",
              "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
              "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    return e


def ecris(p, t):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def lis(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def ecrit_decision(c, d, f):
    """`copilot::decision` d'une écriture de `f` (relatif à `d`) pour l'agent lancé dans `c`."""
    return copilot.decision({"tool_name": "Write", "tool_input": {"file_path": os.path.join(d, f)}}, c)


class Essais(unittest.TestCase):

    def setUp(self):
        # `memoire.git` garde ses réponses par (dossier, arguments) pour la vie du processus.
        memoire._VUS.clear()
        p = mock.patch.dict(os.environ, {"COPILOT_PLUGIN_ROOT": RACINE_PAQUET})
        p.start()
        self.addCleanup(p.stop)
        # Aucune variable de l'agent qui lance les tests ne doit décider du dossier de lancement.
        q = mock.patch.dict(os.environ)
        q.start()
        self.addCleanup(q.stop)
        os.environ.pop("COPILOT_PROJECT_DIR", None)

    def bac(self, nom):
        d = tempfile.mkdtemp(prefix="adopte-%s-" % nom)
        self.addCleanup(shutil.rmtree, d, True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, env=_env(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return d

    def temp(self, prefixe):
        d = tempfile.mkdtemp(prefix=prefixe)
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def main(self, args):
        """`adopte.main` avec ses deux flux captés ; rend le code de sortie."""
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return adopte.main(args)

    def test_adoption_compacte_additive_sans_dossier_agents(self):
        d = self.bac("compact")
        args = [d, "--equipe", "OPS,PO,QA", "--compact"]
        self.assertEqual(self.main(args), 0)
        self.assertFalse(os.path.exists(os.path.join(d, "brain")))
        args = args + ["--go"]
        self.assertEqual(self.main(args), 0)
        self.assertFalse(os.path.exists(os.path.join(d, "agents")))
        for n in ("OPS", "PO", "QA"):
            esprit = os.path.join(d, "brain/mind", n)
            self.assertTrue(os.path.isfile(os.path.join(esprit, "state.md")))
            self.assertTrue(os.path.isfile(os.path.join(esprit, "todo.md")))
            self.assertTrue(os.path.isfile(agent.profil(d, n)))
            self.assertTrue(os.path.isfile(agent.perimetre_compact(d, n)))
        qa = os.path.join(d, "brain/mind/QA")
        self.assertNotIn(".", copilot.lis_deny(qa))
        # Les cinq faits du Rust, plus `workflow.md` (l'addition du port) : 8 entrées
        # avec la mémoire et le dossier de livrables de QA.
        allow = copilot.lis_allow(qa)
        self.assertEqual(len(allow), 8)
        self.assertIn("brain/fact/workflow.md", allow)
        # OPS et PO : une liste de refus seule. Un périmètre les sépare de leurs pairs,
        # il ne borne pas ce qu'ils savent faire.
        for n in ("OPS", "PO"):
            c = os.path.join(d, "brain/mind", n)
            self.assertIsNone(copilot.lis_allow(c), "%s n'a pas de liste autorisée" % n)

            def ecrit(f):
                return ecrit_decision(c, d, f)
            self.assertIsNone(ecrit("%s/%s/a.md" % (agent.BANC, n)))
            self.assertIsNone(ecrit(".github/workflows/ci.yml"), "la CI appartient au projet")
            self.assertIsNone(ecrit(".github/mcp.json"), "la config MCP aussi")
            self.assertIsNone(ecrit("src/code.py"))
            pair = "PO" if n == "OPS" else "OPS"
            self.assertIsNotNone(ecrit("brain/mind/%s/todo.md" % pair), "le territoire d'un pair est refusé")
            self.assertIsNotNone(ecrit("%s/%s/a.md" % (agent.BANC, pair)))
            self.assertIsNotNone(ecrit("brain/fact/base.md"), "les faits n'ont qu'un écrivain")
            self.assertIsNotNone(ecrit(".github/agents/%s.agent.md" % n.lower()),
                                 "le rôle n'est pas modifiable par l'agent")
        ecris(agent.profil(d, "OPS"), "personnalisé")
        self.assertEqual(self.main(args), 0)
        self.assertEqual(lis(agent.profil(d, "OPS")), "personnalisé")

    def test_le_code_externe_est_reference_sans_y_ecrire(self):
        """UN CODE QUI VIT AILLEURS : son adresse entre dans les faits, rien n'entre
        dans son dossier, et un chemin inexistant est refusé."""
        d = self.bac("code-externe")
        code = self.temp("adopte-code-")
        os.makedirs(os.path.join(code, "src"))
        ecris(os.path.join(code, "src/main.py"), "print(1)\n")
        self.assertEqual(self.main([d, "--code", code, "--go"]), 0)
        archi = lis(os.path.join(d, "brain/fact/architecture.md"))
        self.assertIn("## Le code : `%s`" % code, archi)
        e = briefing.etablissements(archi)
        self.assertTrue(any(x[0].startswith("Le code") and x[1] == "dit" for x in e),
                        "ligne d'établissement lisible")
        dans_le_code = []
        for dp, _, fn in os.walk(code):
            dans_le_code.extend(os.path.join(dp, f) for f in fn)
        self.assertEqual(sorted(dans_le_code), [os.path.join(code, "src", "main.py")],
                         "rien n'est écrit dans le code")
        # TÉMOIN : un dossier de code inexistant est refusé, rien n'est posé.
        d2 = self.bac("code-absent")
        self.assertEqual(self.main([d2, "--code", os.path.join(code, "nulle-part"), "--go"]), 1)
        self.assertFalse(os.path.exists(os.path.join(d2, "brain")))

    def test_la_methode_du_projet_nomme_user_d_apres_l_atelier(self):
        """LA MÉTHODE COPIÉE NOMME `@user` QUAND L'ATELIER LE CONNAÎT, et ne laisse
        jamais le gabarit brut sinon."""
        atelier = self.temp("adopte-atelier-")
        projet = os.path.join(atelier, "Mon projet")
        os.makedirs(projet)
        ecris(os.path.join(atelier, "AGENTS.md"),
              adopte._methode_brute().replace("[UTILISATEUR]", "Alice Martin"))
        m = adopte.methode(projet)
        self.assertIn("`@user` désigne Alice Martin, l'humain qui commande l'atelier", m)
        self.assertNotIn("[UTILISATEUR]", m)
        # TÉMOIN : sans atelier qui le nomme, la phrase reste générale.
        os.remove(os.path.join(atelier, "AGENTS.md"))
        m = adopte.methode(projet)
        self.assertIn("`@user` désigne l'humain qui commande l'atelier", m)
        self.assertTrue("[UTILISATEUR]" not in m and "Alice" not in m)

    def test_le_blanc_n_ecrit_rien(self):
        """LE BLANC N'ÉCRIT RIEN — et c'est le contrat, pas un détail. Un passage à
        blanc qui pose un fichier rend le geste irréversible avant d'avoir été
        décidé."""
        d = self.bac("blanc")
        self.assertEqual(self.main([d]), 0)
        self.assertFalse(os.path.exists(os.path.join(d, "brain/fact/base.md")), "le blanc a écrit")
        self.assertFalse(os.path.exists(copilot.settings(d)), "le blanc a écrit les réglages")

    def test_go_pose_le_cerveau_et_branche_le_paquet(self):
        """ET `--go` ÉCRIT VRAIMENT. Le témoin négatif du précédent : sans lui,
        une commande qui n'écrit JAMAIS passerait le premier essai."""
        d = self.bac("go")
        self.assertEqual(self.main([d, "--go"]), 0)
        for f in ("brain/fact/base.md", "brain/fact/workflow.md", "brain/fact/architecture.md",
                  "brain/fact/stack.md", "brain/fact/rules.md", "brain/mind/state.md", "brain/mind/todo.md"):
            self.assertTrue(os.path.exists(os.path.join(d, f)), "%s manque" % f)
        t = lis(copilot.settings(d))
        self.assertIn(copilot.PAQUET, t, "le paquet n'est pas activé")
        self.assertIn('"directory"', t, "la marketplace locale manque")
        j = json.loads(t)
        self.assertEqual(j["extraKnownMarketplaces"]["atelier-copilot"]["source"]["path"], copilot.paquet())
        self.assertFalse(os.path.exists(os.path.join(d, ".claude/settings.json")))

    def test_relancer_ne_change_rien(self):
        """DEUX PASSAGES RENDENT LE MÊME ARBRE. Un outil d'installation qu'on
        n'ose pas relancer n'est pas un outil, c'est un pari."""
        d = self.bac("idem")
        self.main([d, "--go"])
        ecris(os.path.join(d, "brain/fact/base.md"), "MON TEXTE À MOI\n")
        self.main([d, "--go"])
        self.assertEqual(lis(os.path.join(d, "brain/fact/base.md")), "MON TEXTE À MOI\n",
                         "le second passage a écrasé un fichier du projet")

    def test_complete_une_memoire_partielle_sans_ecraser(self):
        d = self.bac("partiel")
        os.makedirs(os.path.join(d, "brain/fact"))
        os.makedirs(os.path.join(d, "brain/mind"))
        for f in ("brain/fact/base.md", "brain/mind/state.md", "brain/mind/todo.md"):
            ecris(os.path.join(d, f), "personnel\n")
        self.assertEqual(self.main([d]), 0)
        self.assertFalse(os.path.exists(os.path.join(d, "brain/fact/stack.md")))
        self.assertEqual(self.main([d, "--go"]), 0)
        for f in socle.FAITS_MONO:
            self.assertTrue(os.path.isfile(os.path.join(d, "brain/fact", f)))
        self.assertTrue(os.path.isfile(os.path.join(d, "brain/fact/workflow.md")))
        self.assertEqual(lis(os.path.join(d, "brain/mind/state.md")), "personnel\n")
        self.assertEqual(self.main([d, "--go"]), 0)

    def test_ajoute_la_methode_sans_remplacer_les_instructions_du_projet(self):
        d = self.bac("instructions")
        f = os.path.join(d, ".github/copilot-instructions.md")
        os.makedirs(os.path.dirname(f))
        ecris(f, "# Instructions personnelles\r\nGarder ce texte.\r\n")
        self.assertEqual(self.main([d]), 0)
        self.assertNotIn(adopte.MARQUEUR_METHODE, lis(f))
        self.assertEqual(self.main([d, "--go"]), 0)
        texte = lis(f)
        self.assertTrue(texte.startswith("# Instructions personnelles\r\nGarder ce texte.\r\n"))
        self.assertIn("# Atelier agentique", texte)
        self.assertEqual(self.main([d, "--go"]), 0)
        self.assertEqual(lis(f), texte)

    def test_une_erreur_de_pose_ne_reussit_pas(self):
        d = self.bac("echec")
        ecris(os.path.join(d, "brain"), "obstacle")
        self.assertEqual(self.main([d, "--go"]), 1)
        self.assertFalse(os.path.exists(copilot.settings(d)))

    def test_les_reglages_existants_survivent(self):
        """LES RÉGLAGES SE FUSIONNENT. Un projet qui a déjà ses permissions doit les
        garder — les écraser couperait ses droits sans le dire."""
        d = self.bac("fusion")
        os.makedirs(os.path.join(d, ".github/copilot"))
        ecris(copilot.settings(d), '{"permissions":{"deny":["Bash(rm*)"]}}')
        self.main([d, "--go"])
        t = lis(copilot.settings(d))
        self.assertIn("Bash(rm*)", t, "les permissions du projet ont été perdues")
        self.assertIn(copilot.PAQUET, t, "le paquet n'a pas été ajouté")

    def test_le_chemin_contenant_un_nom_d_agent_reste_le_projet_cible(self):
        d = self.bac("Agent-A")
        self.assertEqual(self.main([d, "--equipe", "A,B", "--go"]), 0)
        self.assertTrue(os.path.isfile(copilot.settings(d)))
        self.assertTrue(os.path.isfile(os.path.join(d, "agents/A/.github/copilot/perimetre.json")))
        self.assertFalse(os.path.exists(copilot.settings(os.path.join(d, "agents/A"))))

    def test_en_equipe_chacun_a_le_sien(self):
        """EN ÉQUIPE, CHACUN A SON JEU D'ÉTAT — et un jeu partagé serait la panne
        que le multi-agents existe pour éviter."""
        d = self.bac("equipe")
        self.main([d, "--equipe", "PO,QA", "--go"])
        for a in ("PO", "QA"):
            self.assertTrue(os.path.exists(os.path.join(d, "brain/mind", a, "state.md")), "%s sans état" % a)
            self.assertTrue(os.path.exists(os.path.join(d, "agents", a, "AGENTS.md")), "%s sans rôle" % a)
            self.assertEqual(len(copilot.perimetre(os.path.join(d, "agents", a))), 1)
            self.assertFalse(os.path.exists(copilot.settings(os.path.join(d, "agents", a))))
        self.assertTrue(os.path.exists(os.path.join(d, "brain/fact/roles.md")), "la fiche des rôles manque")
        self.assertTrue(os.path.exists(copilot.settings(d)), "réglage unique à la racine")
        self.assertFalse(os.path.exists(os.path.join(d, "brain/mind/state.md")),
                         "un état de projet MONO a été posé en plus des états d'agents")


if __name__ == "__main__":
    unittest.main()
