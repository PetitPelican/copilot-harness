# -*- coding: utf-8 -*-
"""Port des `#[test]` de `harnais/src/copilot.rs` (3 tests)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "py"))

import copilot
import memoire


def _env():
    e = dict(os.environ)
    e.update({"GIT_CONFIG_NOSYSTEM": "1",
              "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
              "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    return e


def git(d, *a):
    r = subprocess.run(["git", "-c", "commit.gpgsign=false"] + list(a), cwd=d, env=_env(),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 0, "git %r : %s" % (a, r.stderr.decode("utf-8", "replace"))


def ecris(p, t):
    with open(p, "w", encoding="utf-8") as f:
        f.write(t)


class Essais(unittest.TestCase):

    def setUp(self):
        # `memoire.git` garde ses réponses par (dossier, arguments) pour la vie du processus.
        memoire._VUS.clear()

    def temp(self, prefixe):
        d = tempfile.mkdtemp(prefix=prefixe)
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def test_garde_les_deux_formats_et_la_frontiere(self):
        d = self.temp("perimetre-copilot-")
        dossier = os.path.join(d, "agents/voisin")
        os.makedirs(dossier)
        git(d, "init", "-q")
        os.makedirs(os.path.join(d, "agents/moi/.github/copilot"))
        moi = os.path.join(d, "agents/moi")
        ecris(os.path.join(moi, ".github/copilot/perimetre.json"), json.dumps({"deny": [dossier]}))
        dehors = {"tool_name": "Write", "tool_input": {"file_path": os.path.join(d, "agents/voisin/a.rs")}}
        self.assertIsNotNone(copilot.decision(dehors, moi))
        camel_dehors = {"toolName": "create", "toolArgs": {"path": os.path.join(d, "agents/voisin/b.rs")}}
        self.assertIsNotNone(copilot.decision(camel_dehors, moi))
        snake_dedans = {"tool_name": "Edit", "tool_input": {"file_path": os.path.join(d, "agents/moi/b.rs")}}
        self.assertIsNone(copilot.decision(snake_dedans, moi))
        patch = {"toolName": "apply_patch", "toolArgs": {"patch": "*** Begin Patch\n*** Update File: %s\n*** End Patch"
                                                          % os.path.join(d, "agents/voisin/p.rs")}}
        self.assertIsNotNone(copilot.decision(patch, moi))
        raw = {"toolName": "apply_patch", "toolArgs":
               "*** Begin Patch\n*** Update File: %s\n*** Move to: %s\n*** End Patch\n"
               % (os.path.join(d, "agents/moi/p.rs"), os.path.join(d, "agents/voisin/p.rs"))}
        self.assertIsNotNone(copilot.decision(raw, moi))
        with self.assertRaises(copilot.Refus):
            copilot.decision({"toolName": "apply_patch", "toolArgs": "pas du JSON"}, moi)
        dedans = {"toolName": "edit", "toolArgs": {"path": os.path.join(d, "agents/moi/a.rs")}}
        self.assertIsNone(copilot.decision(dedans, moi))
        self.assertIsNone(copilot.decision(
            {"tool_name": "Edit", "tool_input": {"file_path": os.path.join(d, "agents/voisinage/a.rs")}}, moi))
        shutil.rmtree(d)
        self.assertIsNone(copilot.decision(dehors, moi), "sans périmètre : fail-open")
        self.assertIsNone(copilot.decision(raw, moi), "FREEFORM sans périmètre")

    def test_dans_une_copie_la_garde_vise_la_copie_et_le_principal(self):
        """LA COPIE DE L'APP : périmètre écrit à l'ancienne (absolu, dossier
        principal) et à la nouvelle (relatif), session à la racine de la copie,
        harnais placé dans `agents/OPS`. Sans transposition, la garde laissait
        tout passer — mesuré sur un vrai projet."""
        d = self.temp("perimetre-copie-")
        for a in ["OPS/.github/copilot", "PO", "QA"]:
            os.makedirs(os.path.join(d, "agents", a))
        git(d, "init", "-q")
        d = os.path.realpath(d)
        ecris(os.path.join(d, "agents/OPS/.github/copilot/perimetre.json"),
              json.dumps({"deny": [os.path.join(d, "agents/PO"), "agents/QA"]}))
        for a in ["PO", "QA"]:
            ecris(os.path.join(d, "agents", a, "x.md"), "x")
        git(d, "add", "-A")
        git(d, "commit", "-q", "-m", "p")
        # PAS depuis `d` canonique : sous Windows ce serait un chemin `\\?\` que git refuse.
        w = os.path.join(self.temp("perimetre-copie-w-"), "w")
        git(d, "worktree", "add", "-q", "-b", "session", w)
        w = os.path.realpath(w)
        moi = os.path.join(w, "agents/OPS")

        def ecrit(f):
            return copilot.decision({"tool_name": "Write", "tool_input": {"file_path": f}, "cwd": w}, moi)

        self.assertIsNotNone(ecrit(os.path.join(w, "agents/PO/a.md")), "absolu du principal, transposé")
        self.assertIsNotNone(ecrit(os.path.join(w, "agents/QA/a.md")), "relatif, posé sur la copie")
        self.assertIsNotNone(ecrit("agents/PO/b.md"), "chemin relatif lu depuis la session")
        self.assertIsNotNone(ecrit(os.path.join(d, "agents/QA/c.md")), "de la copie vers le principal")
        self.assertIsNone(ecrit(os.path.join(w, "agents/OPS/d.md")), "son propre lot")
        self.assertIsNone(ecrit("agents/OPS/e.md"))
        # Ce que le briefing affiche : la copie, jamais le principal.
        self.assertEqual(copilot.perimetre(moi),
                         [os.path.join(w, "agents/PO"), os.path.join(w, "agents/QA")])
        git(d, "worktree", "remove", "--force", w)

    def test_sdk_choisit_la_version_numerique_disponible(self):
        d = self.temp("copilot-sdk-")
        for v in ["1.9.0-0", "1.10.0-0", "autre", "2.0.0-0"]:
            os.makedirs(os.path.join(d, v))
            if v != "2.0.0-0":
                ecris(os.path.join(d, v, "copilot.exe"), "")
        self.assertEqual(copilot.executable_sdk(d), os.path.join(d, "1.10.0-0/copilot.exe"))


if __name__ == "__main__":
    unittest.main()
