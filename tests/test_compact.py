# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/compact.rs` (5 tests).

Écarts voulus avec le Rust : `outputs/` devient `assets/` (`agent.BANC`), et la liste
autorisée de QA compte `workflow.md` (l'addition du port) — sans effet sur ces essais.
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
import compact
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


def git(d, *args):
    r = subprocess.run(["git", "-c", "commit.gpgsign=false"] + list(args), cwd=d, env=_env(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 0, "git %r : %s" % (args, r.stderr.decode("utf-8", "replace"))


def ecris(p, t):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def lis(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


class Tests(unittest.TestCase):

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

    def temp(self, prefixe):
        d = tempfile.mkdtemp(prefix=prefixe)
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def main(self, p, appliquer):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return compact.main(p, appliquer)

    def test_export_compact_preserve_memoire_et_interdiction_globale(self):
        p = self.temp("compact-export-")
        os.makedirs(os.path.join(p, "brain/fact"))
        git(p, "init", "-q")
        p = os.path.realpath(p)
        memoire._VUS.clear()
        for n in ("OPS", "QA"):
            esprit = os.path.join(p, "brain/mind", n)
            ancien = os.path.join(p, "agents", n)
            os.makedirs(esprit)
            os.makedirs(os.path.join(ancien, ".github/copilot"))
            ecris(os.path.join(esprit, "state.md"), "etat initial")
            ecris(os.path.join(esprit, "todo.md"), "todo initial")
            ecris(os.path.join(ancien, "AGENTS.md"), "# %s\nÉcrire dans agents/%s/livrables/.\n" % (n, n))
            ecris(os.path.join(ancien, ".github/copilot/perimetre.json"),
                  json.dumps({"deny": [p], "custom": True}))
        self.assertEqual(self.main(p, False), 0)
        self.assertFalse(os.path.exists(os.path.join(p, ".github")))
        self.assertEqual(self.main(p, True), 0)
        self.assertEqual(compact.prepare(p), [], "export idempotent")
        for n in ("OPS", "QA"):
            self.assertEqual(lis(os.path.join(p, "brain/mind", n, "state.md")), "etat initial")
            self.assertTrue(os.path.isfile(os.path.join(p, "agents", n, "AGENTS.md")))
            contexte = agent.contexte(p, n)
            garde = json.loads(lis(agent.perimetre_compact(p, n)))
            self.assertIs(garde["custom"], True)
            self.assertIn(".", copilot.lis_deny(contexte))
            self.assertIsNotNone(copilot.decision(
                {"tool_name": "Write", "tool_input": {"file_path": os.path.join(p, "x")}}, contexte))

    def test_export_invalide_necrit_rien(self):
        p = self.temp("compact-invalide-")
        os.makedirs(os.path.join(p, "brain/fact"))
        os.makedirs(os.path.join(p, "brain/mind/OPS"))
        git(p, "init", "-q")
        self.assertEqual(self.main(p, True), 1)
        self.assertFalse(os.path.exists(os.path.join(p, ".github")))

    def test_export_qa_documentaire_preserve_allow_et_restrictions(self):
        p = self.temp("compact-qa-documentaire-")
        os.makedirs(os.path.join(p, "brain/fact"))
        os.makedirs(os.path.join(p, "brain/mind/QA"))
        os.makedirs(os.path.join(p, "agents/QA/.github/copilot"))
        git(p, "init", "-q")
        p = os.path.realpath(p)
        memoire._VUS.clear()
        for f in ("state.md", "todo.md"):
            ecris(os.path.join(p, "brain/mind/QA", f), "initial")
        ecris(os.path.join(p, "agents/QA/AGENTS.md"), equipe.role_qa())
        allow = equipe.allow_par_defaut("QA", "brain/fact", "brain/mind/QA", "agents/QA/livrables")
        ecris(os.path.join(p, "agents/QA/.github/copilot/perimetre.json"),
              json.dumps({"allow": allow, "deny": [".github", "brain/poids.json", "brain/fact/rules.md"]}))
        self.assertEqual(self.main(p, True), 0)
        contexte = agent.contexte(p, "QA")

        def ecrit(f):
            return copilot.decision({"tool_name": "Write", "tool_input": {"file_path": os.path.join(p, f)}}, contexte)
        for f in ("brain/fact/base.md", "brain/mind/QA/todo.md", "%s/QA/plan.md" % agent.BANC):
            self.assertIsNone(ecrit(f), f)
        for f in ("brain/fact/rules.md", "brain/fact/extra.md", "src/code.py", ".github/agents/qa.agent.md"):
            self.assertIsNotNone(ecrit(f), f)
        self.assertEqual(compact.prepare(p), [], "export ne réintroduit pas un refus des faits")

    def test_profils_sans_dossier_agents_resolvent_memoire_et_gardes(self):
        p = self.temp("compact-sans-agents-")
        os.makedirs(os.path.join(p, "brain/fact"))
        os.makedirs(os.path.join(p, ".github/agents"))
        os.makedirs(os.path.join(p, ".github/copilot/perimetres"))
        git(p, "init", "-q")
        p = os.path.realpath(p)
        memoire._VUS.clear()
        for n in ("OPS", "QA"):
            esprit = os.path.join(p, "brain/mind", n)
            os.makedirs(esprit)
            ecris(os.path.join(esprit, "state.md"), "---\nmaj: 2026-10-02\nsante: vert\njalon: essai\n---\n")
            ecris(os.path.join(esprit, "todo.md"), "- [ ] tâche\n")
            ecris(agent.profil(p, n), "---\nname: %s\n---\nRÔLE-%s\n" % (agent.nom_de_profil(n), n))
            ecris(agent.perimetre_compact(p, n), json.dumps({
                "allow": [] if n == "QA" else ["brain/mind/OPS", "%s/OPS" % agent.BANC],
                "deny": ["."] if n == "QA" else ["brain/fact", "brain/mind/QA", "%s/QA" % agent.BANC]}))
        lecture = agent.Lecture(choix=agent.Choix("agent", "ops", 1))
        s = agent.resous(p, lecture)
        self.assertEqual(s.actif, "OPS")
        self.assertEqual(s.place, os.path.join(p, "brain", "mind", "OPS"))
        r = memoire.resous(s.place)
        self.assertEqual(r.nom_agent, "OPS")
        self.assertEqual(r.prefixe_mind, "brain/mind/OPS/")
        self.assertEqual(r.mind, s.place)
        self.assertEqual(agent.lignes_briefing(s)[1], [], "profil déjà chargé par le menu")
        qa = agent.resous(p, agent.Lecture())
        self.assertEqual(qa.actif, "QA")
        self.assertIn("RÔLE-QA", agent.lignes_briefing(qa)[1], "rôle servi au défaut")

        def ecrit(n, f):
            return copilot.decision({"tool_name": "Write", "tool_input": {"file_path": os.path.join(p, f)}},
                                    agent.contexte(p, n))
        self.assertIsNone(ecrit("OPS", "%s/OPS/a.md" % agent.BANC))
        self.assertIsNotNone(ecrit("OPS", "docs/audit/a.md"))
        self.assertIsNotNone(ecrit("OPS", "code.py"))
        self.assertIsNone(ecrit("OPS", "brain/mind/OPS/todo.md"))
        self.assertIsNotNone(ecrit("OPS", "brain/mind/QA/todo.md"))
        ops_garde = agent.perimetre_compact(p, "OPS")
        # Sans `allow`, le périmètre sépare l'agent de ses pairs et ne borne rien d'autre.
        ecris(ops_garde, '{"deny":["brain/mind/QA"]}')
        self.assertIsNone(ecrit("OPS", "docs/audit/a.md"), "sans allow : tout est permis…")
        self.assertIsNone(ecrit("OPS", ".github/mcp.json"), "…y compris la config du projet")
        self.assertIsNotNone(ecrit("OPS", "brain/mind/QA/todo.md"), "…sauf les refus")
        ecris(ops_garde, '{"deny":[]}')
        self.assertIsNone(ecrit("OPS", "%s/OPS/a.md" % agent.BANC), "ni allow ni deny : rien n'est interdit")
        ecris(ops_garde, '{"allow":"invalide","deny":[]}')
        with self.assertRaises(copilot.Refus):
            ecrit("OPS", "%s/OPS/a.md" % agent.BANC)     # allow mal formé : refuse
        self.assertIsNotNone(ecrit("QA", "brain/mind/QA/todo.md"))
        qa_garde = agent.perimetre_compact(p, "QA")
        ecris(qa_garde, "invalide")
        with self.assertRaises(copilot.Refus):
            ecrit("QA", "x.md")
        os.remove(qa_garde)
        with self.assertRaises(copilot.Refus):           # compact sans garde : refuse
            ecrit("QA", "x.md")
        self.assertFalse(os.path.exists(os.path.join(p, "agents")))

    def test_compact_dans_worktree_garde_copie_et_principal(self):
        brut = self.temp("compact-worktree-")
        os.makedirs(os.path.join(brut, "brain/fact"))
        os.makedirs(os.path.join(brut, "brain/mind/OPS"))
        os.makedirs(os.path.join(brut, ".github/agents"))
        os.makedirs(os.path.join(brut, ".github/copilot/perimetres"))
        git(brut, "init", "-q")
        ecris(os.path.join(brut, "brain/fact/base.md"), "faits")
        ecris(os.path.join(brut, "brain/mind/OPS/state.md"), "état")
        ecris(os.path.join(brut, ".github/agents/ops.agent.md"), "---\nname: ops\n---\nrôle")
        ecris(os.path.join(brut, ".github/copilot/perimetres/ops.json"),
              '{"allow":["brain/mind/OPS","%s/OPS"],"deny":["brain/fact"]}' % agent.BANC)
        git(brut, "add", ".")
        git(brut, "commit", "-qm", "test")
        copie = self.temp("compact-worktree-copie-")
        shutil.rmtree(copie)
        git(brut, "worktree", "add", "--detach", "-q", copie)
        p = os.path.realpath(brut)
        w = os.path.realpath(copie)
        memoire._VUS.clear()
        lecture = agent.Lecture(choix=agent.Choix("agent", "ops", 1))
        s = agent.resous(w, lecture)
        self.assertEqual(s.place, os.path.join(w, "brain", "mind", "OPS"))
        self.assertEqual(memoire.resous(s.place).mind, s.place)
        for racine in (p, w):
            self.assertIsNotNone(copilot.decision(
                {"tool_name": "Write", "tool_input": {"file_path": os.path.join(racine, "brain/fact/base.md")}},
                s.place))
        git(brut, "worktree", "remove", "--force", copie)


if __name__ == "__main__":
    unittest.main()
