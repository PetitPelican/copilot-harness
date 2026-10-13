# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/equipe.rs` (6 tests).

Écarts voulus avec le Rust : `outputs/` devient `assets/` (`agent.BANC`), et QA a un
fait de plus dans sa liste autorisée (`workflow.md`, l'addition du port).
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

import agent
import copilot
import equipe
import memoire

RACINE_PAQUET = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _env():
    e = dict(os.environ)
    e.update({"GIT_CONFIG_NOSYSTEM": "1",
              "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
              "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    return e


def git_init(d):
    r = subprocess.run(["git", "init", "-q"], cwd=d, env=_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 0, r.stderr


def ecris(p, t):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def lis(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


class Essais(unittest.TestCase):

    def setUp(self):
        # `memoire.git` garde ses réponses par (dossier, arguments) pour la vie du processus.
        memoire._VUS.clear()
        p = mock.patch.dict(os.environ, {"COPILOT_PLUGIN_ROOT": RACINE_PAQUET})
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.dict(os.environ)
        q.start()
        self.addCleanup(q.stop)
        os.environ.pop("COPILOT_PROJECT_DIR", None)

    def temp(self, prefixe, canonique=False):
        d = tempfile.mkdtemp(prefix=prefixe)
        self.addCleanup(shutil.rmtree, d, True)
        return os.path.realpath(d) if canonique else d

    def main(self, args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return equipe.main(args)

    def test_qa_historique_a_un_allow_documentaire_et_conserve_les_restrictions(self):
        for cerveau in (False, True):
            memoire._VUS.clear()
            p = self.temp("equipe-qa-historique-%s-" % cerveau)
            os.makedirs(os.path.join(p, "brain/fact" if cerveau else ".fact"))
            d = os.path.join(p, "agents/QA")
            os.makedirs(d)
            git_init(p)
            with contextlib.redirect_stderr(io.StringIO()):
                equipe.perimetre_agent(d, p, ["OPS"], True, [])

            def ecrit(f):
                return copilot.decision({"tool_name": "Write", "tool_input": {"file_path": os.path.join(p, f)}}, d)
            fact = "brain/fact/base.md" if cerveau else ".fact/base.md"
            mind = "brain/mind/QA/todo.md" if cerveau else "agents/QA/.mind/todo.md"
            for f in (fact, mind, "agents/QA/livrables/plan.md"):
                self.assertIsNone(ecrit(f), f)
            for f in ("src/code.py", ".env", "docs/audit/source.md", "agents/OPS/livrables/a.md"):
                self.assertIsNotNone(ecrit(f), f)
            self.assertIn("allow", lis(os.path.join(d, ".github/copilot/perimetre.json")))
            ecris(os.path.join(d, ".github/copilot/perimetre.json"), '{"allow":[],"deny":["."]}')
            with contextlib.redirect_stderr(io.StringIO()):
                equipe.perimetre_agent(d, p, ["OPS"], True, [])
            self.assertIsNotNone(ecrit(fact), "mise à niveau ne lève pas un refus existant")

    def test_creation_et_ajout_compacts_sans_dossiers_agents(self):
        p = self.temp("equipe-compact-")
        os.makedirs(os.path.join(p, "brain/fact"))
        os.makedirs(os.path.join(p, "brain/mind"))
        ecris(os.path.join(p, "brain/mind/state.md"), "état mono")
        ecris(os.path.join(p, "brain/mind/todo.md"), "todo mono")
        git_init(p)
        p = os.path.realpath(p)
        memoire._VUS.clear()
        args = ["--project-root", p, "--agents", "OPS,QA", "--compact"]
        self.assertEqual(self.main(args), 0)
        self.assertFalse(os.path.exists(os.path.join(p, ".github")), "dry-run sans écriture")
        args = args + ["--apply"]
        self.assertEqual(self.main(args), 0)
        self.assertFalse(os.path.exists(os.path.join(p, "agents")))
        self.assertTrue(os.path.isfile(agent.profil(p, "OPS")))
        qa = os.path.join(p, "brain/mind/QA")
        self.assertNotIn(".", copilot.lis_deny(qa))

        def ecrit(f, c=qa):
            return copilot.decision({"tool_name": "Write", "tool_input": {"file_path": os.path.join(p, f)}}, c)
        for f in ("brain/fact/base.md", "brain/mind/QA/todo.md", "%s/QA/plan.md" % agent.BANC):
            self.assertIsNone(ecrit(f), f)
        for f in ("brain/fact/autre.md", "brain/fact/base.md/code.py", "brain/mind/OPS/todo.md",
                  "docs/audit/a.md", "src/a.rs", ".env", ".github/agents/qa.agent.md"):
            self.assertIsNotNone(ecrit(f), f)
        self.assertEqual(self.main(["--project-root", p, "--agents", "PO", "--apply"]), 0)
        self.assertFalse(os.path.exists(os.path.join(p, "agents")), "ajout conserve la forme compacte")
        self.assertTrue(os.path.isfile(agent.profil(p, "PO")))
        self.assertIn("%s/PO" % agent.BANC, copilot.lis_deny(os.path.join(p, "brain/mind/OPS")))

    def test_la_mise_a_niveau_ecrit_les_profils_et_des_perimetres_relatifs(self):
        """UN PROJET CONVERTI AVANT 0.16.0 : périmètres absolus vers le dossier
        principal, pas de profils, un profil écrit à la main. `--profils` le met à
        niveau sans rien écraser."""
        d = self.temp("equipe-profils-")
        os.makedirs(os.path.join(d, ".github/agents"))
        git_init(d)
        d = os.path.realpath(d)
        memoire._VUS.clear()
        # Un absolu HORS du projet, sur cette plateforme : `/x` n'en est pas un sous Windows.
        dehors = os.path.join(tempfile.gettempdir(), "hors-projet-%d" % os.getpid())
        os.makedirs(os.path.join(d, "brain/fact"))
        for a in ("OPS", "Projet QA"):
            os.makedirs(os.path.join(d, "brain/mind", a))
            ecris(os.path.join(d, "brain/mind", a, "state.md"), "---\nmaj: 2026-10-01\n---\n")
            os.makedirs(os.path.join(d, "agents", a, ".github/copilot"))
        ecris(os.path.join(d, "agents/OPS/.github/copilot/perimetre.json"),
              json.dumps({"deny": [os.path.join(d, "agents/Projet QA"), dehors]}))
        ecris(os.path.join(d, ".github/agents/ops.agent.md"), "à la main\n")

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(equipe.mise_a_niveau(d, True), 0)
        v = json.loads(lis(os.path.join(d, "agents/OPS/.github/copilot/perimetre.json")))
        self.assertEqual(v["deny"], ["agents/Projet QA", dehors], "relatif sous le projet, absolu hors")
        self.assertEqual(lis(os.path.join(d, ".github/agents/ops.agent.md")), "à la main\n",
                         "un profil existant n'est jamais écrasé")
        qa = lis(os.path.join(d, ".github/agents/projet-qa.agent.md"))
        self.assertTrue(qa.startswith("---\nname: projet-qa\n"), qa)
        self.assertTrue("agents/Projet QA/AGENTS.md" in qa and "brain/mind/Projet QA/state.md" in qa)
        self.assertEqual(agent.correspond("projet-qa", ["OPS", "Projet QA"]), "Projet QA",
                         "le nom écrit dans le profil désigne bien le dossier")

    def test_deux_agents_au_meme_profil_sont_refuses(self):
        self.assertIsNotNone(equipe.profils_en_collision(["QA", "qa"]))
        self.assertIsNotNone(equipe.profils_en_collision(["Q A", "Q-A"]))
        self.assertIsNone(equipe.profils_en_collision(["OPS", "PO", "QA"]))

    def test_conversion_du_deny_racine_ne_le_supprime_pas(self):
        p = self.temp("equipe-deny-racine-")
        d = os.path.join(p, "agents/QA")
        os.makedirs(os.path.join(d, ".github/copilot"))
        git_init(p)
        p = os.path.realpath(p)
        memoire._VUS.clear()
        ecris(os.path.join(d, ".github/copilot/perimetre.json"), json.dumps({"deny": [p]}))
        equipe.perimetre_agent(d, p, ["OPS"], True, [])
        self.assertIn(".", copilot.lis_deny(d))

    def test_deux_noms_qui_donnent_la_meme_cle_se_voient(self):
        self.assertEqual(equipe.slug("/Users/x/Projet Studio"), "-Users-x-Projet-Studio")
        self.assertEqual(equipe.slug("Q A"), equipe.slug("Q-A"),
                         "deux noms, une adresse : la collision que le refus attrape")


if __name__ == "__main__":
    unittest.main()
